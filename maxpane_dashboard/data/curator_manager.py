"""Orchestrator for the curator dashboard — THE LIST.

One coordination point between three independently failing source groups, four
refresh tiers and one frozen output contract.  Exposes one public coroutine,
:meth:`CuratorManager.fetch_and_compute`, which returns **exactly**
:data:`~maxpane_dashboard.data.curator_models.CURATOR_KEYS` — always, under
every failure combination, and without ever letting an exception escape.

Source groups and how they die
------------------------------

===========  ==========================================  =====================
Group        Client call                                 Dies as
===========  ==========================================  =====================
``state``    ``fetch_state`` + ``fetch_balance`` +       the state RPC pool
             ``fetch_config``                            (publicnode + fallbacks)
``logs``     ``fetch_logs`` + ``fetch_blockscout_logs``  the logs RPC pool
                                                         (tenderly + drpc)
``wallet``   ``fetch_wallet``                            either, or a bad address
===========  ==========================================  =====================

The three names are :data:`~maxpane_dashboard.data.curator_models.CURATOR_DEGRADED_GROUPS`
verbatim, because the title bar renders them verbatim.  A manager that invented
a fourth (``"rpc"``, ``"config"``) would light a banner the screen's formatter
has never seen.

**State and logs sit on different endpoint pools**, so live-state/dead-logs is
the *expected* outage rather than a corner case: the clock, the phase and the
forced-ETH anomaly keep working while the leaderboard, the series, the activity
feed and the clusters go to last-good behind an ``as of HH:MM`` marker.  The
reverse happens too.  Neither one may present the other's absence as a zero.

Four rules this module exists to enforce
----------------------------------------

1. **The settlement latch beats the live read (H1).**  ``isSettled()`` is
   polled on the fast tier and the first ``True`` is handed to
   :meth:`~maxpane_dashboard.data.curator_cache.CuratorCache.observe_settlement`,
   which writes the evidence down once.  From then on an RPC outage degrades
   the freshness marker and never the phase.  ``settle()`` is permissionless, so
   the ``Settled`` *event* is the obituary and fills in the final hour and
   totals if it ever appears — it never creates the verdict.
2. **The series are fed from folded ``Deposited`` logs only (H2).**  The fast
   tier's payload keys and the series writer's inputs are disjoint sets and
   ``test_the_fast_tier_payload_cannot_reach_the_series`` asserts it rather than
   reasoning about it.  The hour comes off the event's *indexed* second topic,
   so no timestamp and no state read participates.
3. **A failed read is ``None``, never ``0``.**  Every reading handed to
   ``build_signals`` is either a real value or ``None``.  This contract has
   three legitimate zeros — the hour total at a boundary, the deficit during
   grace or on a safe hour, and a credited delta above the 1000 ETH cap — and
   each stays distinguishable from an outage.
4. **The balance is always forced ETH (H5).**  Every wei of a deposit is
   refunded in the same transaction, so ``eth_getBalance`` feeds ``forced_eth``
   and nothing else: never a volume, never a TVL, never a hero total.

Where the division happens
--------------------------

Nowhere in this module.  Models are wei-native and ``build_signals`` is the
presentation boundary — it divides once, in ``_eth`` — while the cache's series
writer divides its own buckets once on the way to disk.  Two divisions is how a
number silently becomes 1e-18 of itself, so
``test_the_manager_divides_to_eth_exactly_once`` pins this module's count at
zero.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from datetime import datetime, timezone
from typing import Any

from maxpane_dashboard.analytics.curator_signals import (
    READING_KEYS,
    build_signals,
)
from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data.curator_cache import (
    DEFAULT_CACHE_PATH,
    SLOT_BLOCKSCOUT,
    SLOT_CONFIG,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    CuratorCache,
)
from maxpane_dashboard.data.curator_client import CuratorClient
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CURATOR_KEYS,
    CURATOR_SERIES_KEYS,
    DepositEvent,
)
from maxpane_dashboard.data.evm_abi import addr_from_topic, strip0x
from maxpane_dashboard.data.safe_call import safe_call

logger = logging.getLogger(__name__)


def _opt_int(value: Any) -> int | None:
    """An ``int`` if the value is one, else ``None``.  ``bool`` is not one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# ---------------------------------------------------------------------------
# Log decoding — raw rows in, models out
# ---------------------------------------------------------------------------
#
# The client hands back log rows **verbatim** so that the decoders have exactly
# one caller and one hostile-input suite, and this is that decoder.  It reads
# both dialects the two sources speak, because the Blockscout cross-check has to
# be diffable against the RPC sweep:
#
#   RPC (tenderly / drpc)   blockNumber "0x18937a0"   transactionHash   logIndex
#                           blockTimestamp "0x6a82174f"
#   Blockscout REST         block_number 25770244     transaction_hash  index
#                           block_timestamp "2026-08-16T21:13:35.000000Z"
#
# Two rules run through all of it:
#
# * **A short or malformed payload decodes to ``None``, never to zeros.**  A
#   reverted call and a truncated log both come back as something ``int(x, 16)``
#   would happily turn into a 0, and a 0 here is a deposit that never happened
#   sitting on the leaderboard.
# * **A missing timestamp stays ``None``.**  Every captured row carries one
#   (H14 is struck through), but the fallback batch exists for an endpoint that
#   omits it, and ``ts=None`` renders ``--:--`` where a ``0`` renders
#   1970-01-01 — which looks like data.

#: ``Deposited``'s seven data words, in the order the ABI declares them.
_DEPOSIT_DATA_WORDS = (
    "amount_wei",
    "credited_delta_wei",
    "weight_added_wei",
    "new_weight_wei",
    "tx_count",
    "hour_total_wei",
    "early_bps",
)

#: ``Launched``'s seven data words — no indexed fields at all.
_LAUNCHED_DATA_WORDS = (
    "launch_time",
    "hourly_threshold_wei",
    "grace_period",
    "hour_duration",
    "min_deposit_wei",
    "min_escalation_wei",
    "credit_cap_wei",
)


def _topics(row: Any) -> list[str]:
    """The row's topic array, ``None`` padding dropped (Blockscout pads to 4)."""
    if not isinstance(row, dict):
        return []
    raw = row.get("topics")
    if not isinstance(raw, (list, tuple)):
        return []
    return [t for t in raw if isinstance(t, str)]


def _data_words(row: Any) -> list[str]:
    """The row's data blob split into 32-byte words.  A partial tail is dropped."""
    if not isinstance(row, dict):
        return []
    raw = row.get("data")
    if not isinstance(raw, str):
        return []
    body = strip0x(raw)
    return [body[i : i + 64] for i in range(0, len(body) - len(body) % 64, 64)]


def _hex_or_int(value: Any) -> int | None:
    """An ``int`` from either dialect's number, or ``None``.  Never a ``0`` guess."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value, 16) if value.lower().startswith("0x") else int(value, 10)
        except ValueError:
            return None
    return None


def _row_block(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    return _hex_or_int(row.get("blockNumber", row.get("block_number")))


def _row_log_index(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    return _hex_or_int(row.get("logIndex", row.get("index")))


def _row_tx_hash(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get("transactionHash", row.get("transaction_hash"))
    return value if isinstance(value, str) and value else None


def _row_ts(row: Any) -> float | None:
    """The row's own block timestamp, in epoch seconds, or ``None``.

    Read from the row rather than re-fetched: every captured row on both
    sources carries one, and a client that discards a stamp it was handed pays
    a round trip for nothing (H14, refuted and inverted).
    """
    if not isinstance(row, dict):
        return None
    raw = row.get("blockTimestamp", row.get("block_timestamp"))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    if raw.lower().startswith("0x"):
        value = _hex_or_int(raw)
        return float(value) if value else None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def decode_deposit(row: Any) -> DepositEvent | None:
    """One ``Deposited`` row → :class:`DepositEvent`, or ``None`` if unusable.

    ``contributor`` and ``hour`` are the two **indexed** topics, which is why
    hour bucketing needs no timestamp at all: the hour is in the log and its
    wall clock is ``launchTime + hour × hourDuration``, exact by construction.
    The seven data words are taken raw — nothing derived, nothing divided.
    """
    topics = _topics(row)
    words = _data_words(row)
    if len(topics) < 3 or topics[0].lower() != A.TOPIC_DEPOSITED.lower():
        return None
    if len(words) < len(_DEPOSIT_DATA_WORDS):
        return None
    block = _row_block(row)
    log_index = _row_log_index(row)
    tx_hash = _row_tx_hash(row)
    if block is None or log_index is None or tx_hash is None:
        # Without the de-dupe key a re-org replay renders every deposit twice.
        return None
    try:
        values = {
            name: int(words[i], 16) for i, name in enumerate(_DEPOSIT_DATA_WORDS)
        }
        hour = int(strip0x(topics[2]), 16)
    except ValueError:
        return None
    return DepositEvent(
        contributor=addr_from_topic(topics[1]),
        hour=hour,
        block_number=block,
        tx_hash=tx_hash,
        log_index=log_index,
        ts=_row_ts(row),
        **values,
    )


def decode_first_deposit(row: Any) -> dict | None:
    """One ``FirstDeposit`` row → ``{"contributor", "index", "ts"}``.

    ``index`` is the second **indexed** topic, is 1-based, and maxes at exactly
    ``totalContributors``.  The data word is the contract's own timestamp; the
    row's block stamp is the fallback.
    """
    topics = _topics(row)
    if len(topics) < 3 or topics[0].lower() != A.TOPIC_FIRST_DEPOSIT.lower():
        return None
    try:
        index = int(strip0x(topics[2]), 16)
    except ValueError:
        return None
    words = _data_words(row)
    ts: float | None = None
    if words:
        try:
            stamped = int(words[0], 16)
        except ValueError:
            stamped = 0
        ts = float(stamped) if stamped > 0 else None
    return {
        "contributor": addr_from_topic(topics[1]),
        "index": index,
        "ts": ts if ts is not None else _row_ts(row),
    }


def decode_hour_saved(row: Any) -> dict | None:
    """One ``HourSaved`` row → ``{"hour", "wallet", "ts"}``.  Never fired yet."""
    topics = _topics(row)
    if len(topics) < 3 or topics[0].lower() != A.TOPIC_HOUR_SAVED.lower():
        return None
    try:
        hour = int(strip0x(topics[2]), 16)
    except ValueError:
        return None
    return {"hour": hour, "wallet": addr_from_topic(topics[1]), "ts": _row_ts(row)}


def decode_settled(row: Any) -> dict | None:
    """One ``Settled`` row → the obituary's four values.  Never the latch.

    ``isSettled()`` is derived, so it can flip with no log at all; this row is
    evidence about the past and only fills in details the view cannot give.
    """
    topics = _topics(row)
    words = _data_words(row)
    if len(topics) < 2 or topics[0].lower() != A.TOPIC_SETTLED.lower():
        return None
    if len(words) < 3:
        return None
    try:
        return {
            "hour": int(strip0x(topics[1]), 16),
            "ts": int(words[0], 16),
            "total_contributors": int(words[1], 16),
            "total_volume_wei": int(words[2], 16),
        }
    except ValueError:
        return None


def decode_rescued_total(rows: Any) -> int | None:
    """Sum the ``Rescued`` amounts.  ``None`` when the filter did not read.

    ``0`` is a real answer — the event has never fired on chain and may never —
    so an empty tuple sums to ``0`` while a ``None`` input stays ``None``.
    """
    if rows is None:
        return None
    total = 0
    for row in rows:
        topics = _topics(row)
        words = _data_words(row)
        if len(topics) < 2 or topics[0].lower() != A.TOPIC_RESCUED.lower():
            continue
        if not words:
            continue
        try:
            total += int(words[0], 16)
        except ValueError:
            continue
    return total


def decode_launched(row: Any) -> dict | None:
    """One ``Launched`` row → the seven immutables it announced.

    A **cross-check**, never the source: the ``once`` tier reads the same
    numbers off the contract's own getters, because a log is what the deployer
    said and a getter is what the contract will do.
    """
    topics = _topics(row)
    words = _data_words(row)
    if not topics or topics[0].lower() != A.TOPIC_LAUNCHED.lower():
        return None
    if len(words) < len(_LAUNCHED_DATA_WORDS):
        return None
    try:
        return {
            name: int(words[i], 16) for i, name in enumerate(_LAUNCHED_DATA_WORDS)
        }
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source groups — PRD §5's exact vocabulary, and the screen renders it verbatim
# ---------------------------------------------------------------------------

SOURCE_STATE = "state"
SOURCE_LOGS = "logs"
SOURCE_WALLET = "wallet"

#: Hand-typed rather than derived from ``CURATOR_DEGRADED_GROUPS`` on purpose
#: (CLAUDE.md's redundancy rule): the agreement is asserted by a test, and a
#: derivation would make that test compare a constant against itself.
SOURCES: tuple[str, ...] = (SOURCE_STATE, SOURCE_LOGS, SOURCE_WALLET)

#: group -> the cache slot holding its last-good payload.  ``config`` and
#: ``blockscout`` have slots of their own but no group: the immutables are part
#: of the *state* story the user is told, and Blockscout is a cross-check whose
#: absence degrades the ``logs`` group it checks.
GROUP_SLOT: dict[str, str] = {
    SOURCE_STATE: SLOT_STATE,
    SOURCE_LOGS: SLOT_LOGS,
    SOURCE_WALLET: SLOT_WALLET,
}


#: Exactly the ``READING_KEYS`` entries the fast tier produces.
#:
#: Note what is **absent**: the hour total and the last-active-hour pair.  Both
#: are on :class:`CuratorState`, both are read every 15 s, and neither is a
#: reading ``build_signals`` accepts — the hour history is folded from
#: ``Deposited`` logs alone (H2).  This tuple and
#: :data:`~maxpane_dashboard.data.curator_cache.SERIES_INPUT_KEYS` are asserted
#: disjoint, so the day someone "helpfully" feeds the live hour total into the
#: sparkline, a test says so before a user sees a 99.5% crash that never
#: happened.
FAST_TIER_PAYLOAD_KEYS: tuple[str, ...] = (
    "settled",
    "current_hour",
    "hour_needed_wei",
    "hour_seconds_left",
    "early_bps",
    "volume_wei",
    "contributors",
    "tx_count",
    "forced_balance_wei",
)

#: The ``once`` tier's readings, straight off :class:`CuratorConfig`.
CONFIG_PAYLOAD_KEYS: tuple[str, ...] = (
    "launch_time",
    "grace_period",
    "hour_duration",
    "hourly_threshold_wei",
    "first_judged_hour",
    "points_per_eth",
    "credit_cap_wei",
)


class CuratorManager:
    """Fetches THE LIST across three source groups and returns a flat dict."""

    def __init__(
        self,
        poll_interval: int = 30,
        *,
        client: Any = None,
        cache: Any = None,
        wallet: str | None = None,
        clock: Any = time.time,
        cache_path: str = DEFAULT_CACHE_PATH,
    ) -> None:
        self.poll_interval = poll_interval
        self._clock = clock
        self._cache_path = str(cache_path)
        #: The wallet the YOU row is about.  Read from the **constructor** —
        #: the app passes ``--wallet`` / ``MAXPANE_WALLET`` — never from the
        #: process environment in here, so a test drives it without patching
        #: anything and two managers in one process can watch two wallets.
        self.wallet = wallet or None
        self.client = client if client is not None else CuratorClient()
        self.cache = cache if cache is not None else CuratorCache(
            path=self._cache_path, clock=clock
        )

        self._cycle_count = 0
        self._error_count = 0
        #: Groups whose most recent *attempt* failed.  Cleared on success only,
        #: so a group that failed two cycles ago and is not due to retry yet
        #: stays reported as degraded rather than reading as healthy because its
        #: tier happens to be backed off.
        self._failed_groups: set[str] = set()
        #: True while the folded totals disagree with the contract's own
        #: counters — the slow tier's cross-check sets it and a repair sweep
        #: clears it.
        self._fold_stale = False
        #: Set by the cross-check when the fold looks short: the next medium
        #: tick re-sweeps from here instead of from the watermark.
        self._repair_from_block: int | None = None

        try:
            self.cache.load()
        except Exception as exc:  # noqa: BLE001 — load is fail-soft; belt and braces
            logger.warning("Curator cache load failed: %s", exc)

    # -- lifecycle -----------------------------------------------------------

    def save_cache(self) -> None:
        try:
            self.cache.save()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator cache save failed: %s", exc)

    async def close(self) -> None:
        """Close the client, then persist the cache.  Never raises.

        In that order, and the save happens even when the close raises.  The
        client owns sockets and the cache owns a file; closing first means no
        in-flight response can still be folding rows into the structures the
        save is walking, and saving in a ``finally`` means a client that throws
        on the way out cannot cost the user the whole game's history.
        """
        try:
            await self.client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("closing the curator client failed: %s", exc)
        finally:
            self.save_cache()

    # -- guarded calls and degradation ---------------------------------------

    async def _guard(self, call: Any, name: str) -> Any:
        """Await ``call()``; a raise becomes ``None``, logged, never escaping.

        The clients document ``None`` on failure, so a raise here is a bug in
        the client or a transport surprise — either way it costs one source
        group's reading, not the refresh cycle.
        """
        try:
            return await call()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator %s raised: %s", name, exc)
            return None

    def _note(self, group: str, ok: bool) -> None:
        """Record this cycle's attempt for ``group``.  Unknown names are refused.

        A group name that is not in :data:`SOURCES` would reach the title bar
        verbatim, so it is a programming error rather than a display quirk.
        """
        if group not in SOURCES:
            raise ValueError(
                f"unknown curator source group {group!r}; expected one of {SOURCES}"
            )
        if ok:
            self._failed_groups.discard(group)
        else:
            self._failed_groups.add(group)
            self._error_count += 1

    # -- the fast tier: state + the forced-ETH anomaly (H1, H5) --------------

    async def _pool_state(self, now: float) -> dict[str, Any]:
        """One batched ``eth_call`` round and one ``eth_getBalance``.  Never raises.

        Exactly two requests per fast tick: the eight views travel in a single
        JSON-RPC batch (with ``eth_blockNumber`` as its last entry, so the
        readings and the height describe the same block) and the balance is a
        second call on purpose — it is a **bare int** on the client, so nothing
        can reach it by reading a state object and mistake it for a deposit.

        The balance is **always forced ETH** (H5).  Every wei of a deposit is
        refunded inside the same transaction, so a non-zero balance is an
        anomaly — somebody ``selfdestruct``-ed ETH into the contract — and it
        feeds ``forced_eth`` alone.  It is never a volume, a TVL or a hero
        total, and ``0`` is the *healthy* answer.

        ``settled`` goes to the latch and nowhere else this tier can write.
        **No series is touched here**: :data:`FAST_TIER_PAYLOAD_KEYS` and the
        cache's ``SERIES_INPUT_KEYS`` are disjoint by test (H2).
        """
        state, balance = await asyncio.gather(
            self._guard(self.client.fetch_state, "fetch_state"),
            self._guard(self.client.fetch_balance, "fetch_balance"),
        )
        if state is not None:
            state = dataclasses.replace(state, forced_balance_wei=_opt_int(balance))
            # The one-way latch (H1).  A False or None observation cannot clear
            # a True one, so this is safe to call every tick.
            self.cache.observe_settlement(
                getattr(state, "settled", None),
                block_number=_opt_int(getattr(state, "block_number", None)),
                now=now,
            )

        ok = state is not None and balance is not None
        if ok:
            self.cache.store_last_good(SLOT_STATE, self._state_payload(state), ts=now)
            self.cache.mark_fetched(TIER_FAST, now)
        else:
            # A half-failure keeps whatever did come back for *this* payload but
            # must not overwrite the last-good with a half-empty round, and must
            # not restart the TTL as though the tier were healthy.
            self.cache.mark_failed(TIER_FAST, now)
        self._note(SOURCE_STATE, ok)
        return {"state": state, "ok": ok}

    @staticmethod
    def _state_payload(state: Any) -> dict[str, Any]:
        """``FAST_TIER_PAYLOAD_KEYS`` off one :class:`CuratorState`.

        Field for field, no derivation and no division: the model is wei-native
        and ``build_signals`` is the presentation boundary.
        """
        return {key: getattr(state, key, None) for key in FAST_TIER_PAYLOAD_KEYS}

    async def _pool_config(self, tiers: set[str], now: float) -> dict[str, Any] | None:
        """The ``once`` tier: the eight immutables plus ``POINTS_PER_ETH``.

        Read **live** and never hardcoded (CLAUDE.md), even though
        ``curator_addresses`` pins the same numbers — the pins exist so a test
        can prove the live read agrees, not so the dashboard can skip it.
        Nothing on this contract can change them, so one success is final; a
        *failure* still comes due again after the tier's backoff.
        """
        cached = self.cache.get_last_good(SLOT_CONFIG)
        if TIER_ONCE not in tiers:
            return cached.payload if cached is not None else None
        config = await self._guard(self.client.fetch_config, "fetch_config")
        if config is None:
            self.cache.mark_failed(TIER_ONCE, now)
            self._note(SOURCE_STATE, False)
            return cached.payload if cached is not None else None
        payload = {key: getattr(config, key, None) for key in CONFIG_PAYLOAD_KEYS}
        self.cache.store_last_good(SLOT_CONFIG, payload, ts=now)
        self.cache.mark_fetched(TIER_ONCE, now)
        return payload

    def _client_degradation(self) -> set[str]:
        """The groups the client's own flags implicate.

        Read defensively with ``getattr``: the real client sets all six, but a
        test double implementing only the ``fetch_*`` coroutines need not, and
        this method must not raise because a client is *less* chatty about
        outages.  Each flag is reset at the start of the call it describes, so
        reading it right after that call reflects only this cycle.

        ``log_group_failed`` is the one that matters most.  ``LogSweep``'s
        ``()`` means both "read, nothing matched" and "this filter died", and
        without this dict a dead ``Settled`` filter reads as *the game is
        alive*.
        """
        out: set[str] = set()
        client = self.client
        if getattr(client, "state_failed", False):
            out.add(SOURCE_STATE)
        if getattr(client, "config_failed", False):
            # The `once` tier rides its own schedule but it is part of the same
            # story the user is told about the state pool.
            out.add(SOURCE_STATE)
        if getattr(client, "logs_failed", False):
            out.add(SOURCE_LOGS)
        groups = getattr(client, "log_group_failed", None)
        if isinstance(groups, dict) and any(groups.values()):
            out.add(SOURCE_LOGS)
        if getattr(client, "blockscout_truncated", False):
            out.add(SOURCE_LOGS)
        if self.wallet and getattr(client, "wallet_failed", False):
            out.add(SOURCE_WALLET)
        return out

    def _degraded(self) -> list[str]:
        """Groups the screen must not present as live, sorted, ⊆ :data:`SOURCES`.

        A group is degraded when its last attempt failed, **or** it has never
        produced a payload, **or** the client's own flags say this cycle's read
        was incomplete.

        The one exception is ``wallet`` with no wallet configured: nothing is
        wrong, nothing was attempted, and every ``you_*`` key is ``None``
        because there is nobody to ask about — not because a source died.
        """
        out = set(self._failed_groups)
        for group, slot in GROUP_SLOT.items():
            if group == SOURCE_WALLET and not self.wallet:
                out.discard(group)
                continue
            if self.cache.get_last_good(slot) is None:
                out.add(group)
        out |= self._client_degradation()
        if not self.wallet:
            out.discard(SOURCE_WALLET)
        return sorted(out & set(SOURCES))


__all__ = [
    "CONFIG_PAYLOAD_KEYS",
    "decode_deposit",
    "decode_first_deposit",
    "decode_hour_saved",
    "decode_launched",
    "decode_rescued_total",
    "decode_settled",
    "FAST_TIER_PAYLOAD_KEYS",
    "GROUP_SLOT",
    "SOURCES",
    "SOURCE_LOGS",
    "SOURCE_STATE",
    "SOURCE_WALLET",
    "CuratorManager",
]
