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
from collections.abc import Mapping
from typing import Any

from maxpane_dashboard.analytics.curator_signals import (
    READING_KEYS,
    bucket_start_ts,
    build_signals,
    fold_deposits,
    hourly_buckets,
)
from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data import ens
from maxpane_dashboard.data import curator_clusters
from maxpane_dashboard.data.curator_cache import (
    DEFAULT_CACHE_PATH,
    SLOT_BLOCKSCOUT,
    SLOT_CONFIG,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    TIER_ANALYSIS,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    CuratorCache,
)
from maxpane_dashboard.data.curator_client import LOG_GROUPS, CuratorClient
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CURATOR_KEYS,
    CURATOR_SERIES_KEYS,
    DepositEvent,
)
from maxpane_dashboard.data.evm_abi import addr_from_topic, strip0x
from maxpane_dashboard.data.safe_call import safe_call as _safe_call

logger = logging.getLogger(__name__)


def _opt_int(value: Any) -> int | None:
    """An ``int`` if the value is one, else ``None``.  ``bool`` is not one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _looks_like_address(value: Any) -> bool:
    """A 20-byte hex address, checked locally before a request is spent on it."""
    if not isinstance(value, str):
        return False
    body = value[2:] if value.lower().startswith("0x") else value
    if len(value) != 42 or len(body) != 40:
        return False
    try:
        int(body, 16)
    except ValueError:
        return False
    return True


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

#: The five row keys whose emptiness is a claim about the chain rather than
#: about this install.  ``None`` = the source did not read; ``[]`` = it read and
#: found nothing.  The series keys are deliberately absent: they are this
#: cache's own history, and an empty one is a fact about the install.
#:
#: ``you_ladder_rows`` belongs here for the same reason as the other four and
#: for a sharper one: an empty ladder rendered as fact says *you have never
#: deposited* to somebody who has, which is the one claim on the wallet view a
#: reader would act on.
_SOURCE_BACKED_ROW_KEYS: tuple[str, ...] = (
    "leaderboard_rows",
    "activity_rows",
    "closest_call_rows",
    "cluster_rows",
    "you_ladder_rows",
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
        analysis_transport: Any = None,
        analysis_sleep: Any = None,
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
        #: The newest fast-tier answers, re-served while that tier is still
        #: fresh.  This is **not** a last-good store and it is deliberately not
        #: the cache's: it is set on every *attempted* fast tick, to ``None``
        #: when the attempt failed, so it can never outlive the tier's own TTL.
        #: Serving a reading from twelve seconds ago is what a 15 s TTL means;
        #: serving one from across an outage is what PRD §11's row 1 forbids,
        #: and the two are kept apart by clearing these on failure.
        self._fast_state: Any = None
        self._fast_wallet: Any = None
        #: The detached slow-tier cross-check, or ``None`` when none is in
        #: flight.  See :meth:`_spawn_crosscheck` for why it is not awaited.
        self._crosscheck_task: Any = None
        #: The detached Tier-B+C analysis sweep, on the exact same pattern.
        self._analysis_task: Any = None
        #: True only while the most recent analysis sweep RAN and failed to
        #: publish.  "Could not run yet" (no events, no live-read config) is a
        #: different fact and never sets it — see :meth:`_pool_analysis`.
        self._analysis_failed = False
        #: Once-per-process marker for the missing-library log line.
        self._sybilkit_missing_logged = False
        #: The enrichment session for the detached sweep.  A test injects an
        #: ``httpx`` transport (and a no-op ``sleep``) here; production leaves
        #: both ``None`` and the sweep borrows the client's own HTTP session.
        #: With neither available the sweep runs tier A only and opens
        #: **nothing** — which is what keeps a bare test double socket-free.
        self._analysis_transport = analysis_transport
        self._analysis_sleep = analysis_sleep

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
        """Stop both detached tasks, close the client, then persist the cache.

        Never raises.  In that order, and the save happens even when the close
        raises.  The detached cross-check holds the same client, so it is
        cancelled and awaited *first* -- closing sockets out from under a task
        that is still paging is how a clean quit turns into a traceback on the
        way down -- and the analysis sweep borrows the same session, so it is
        stopped right beside it for the same reason.  The client owns sockets
        and the cache owns a file; closing before saving means no in-flight
        response can still be folding rows into the structures the save is
        walking, and saving in a ``finally`` means a client that throws on the
        way out cannot cost the user the whole game's history.
        """
        await self._cancel_crosscheck()
        await self._cancel_analysis()
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
        # One extra live read rides the slot WITHOUT joining the readings:
        # `CONFIG_PAYLOAD_KEYS` mirrors the frozen `READING_KEYS` one for one,
        # and `build_signals` has no use for the minimum -- but the analysis
        # sweep's preset refuses to exist without it (ruling R13: everyone
        # sends the minimum, so the minimum identifies nobody).  `_readings`
        # iterates `CONFIG_PAYLOAD_KEYS`, so this key never reaches it.
        payload["min_deposit_wei"] = _opt_int(
            getattr(config, "min_deposit_wei", None)
        )
        self.cache.store_last_good(SLOT_CONFIG, payload, ts=now)
        self.cache.mark_fetched(TIER_ONCE, now)
        return payload

    # -- the fast tier, second half: the YOU views ---------------------------

    async def _pool_wallet(self, now: float) -> Any:
        """The six argument-taking views, and **only** when a wallet is set.

        With no wallet configured this makes **zero** requests and returns
        ``None``: every ``you_*`` key is then ``None`` because there is nobody
        to ask about, which is a different fact from a source being down and is
        reported differently (:meth:`_degraded` never names ``wallet`` in that
        case).

        An address that cannot be one is rejected **here**, before any request:
        sending garbage to a public node to be told what we could have checked
        locally is both rude and slow, and the failure is reported as a wallet
        degradation rather than an outage.

        A wallet that is not on the list is a **successful** read, not a
        failure: the contract answers ``minDeposit`` for a stranger, which is
        exactly the number that wallet needs and the most useful thing on the
        row.
        """
        if not self.wallet:
            return None
        if not _looks_like_address(self.wallet):
            logger.warning(
                "Curator wallet %r is not an address; the YOU row is unavailable "
                "and nothing was sent to the node",
                self.wallet,
            )
            self._note(SOURCE_WALLET, False)
            return None
        state = await self._guard(
            lambda: self.client.fetch_wallet(self.wallet), "fetch_wallet"
        )
        ok = state is not None and not getattr(self.client, "wallet_failed", False)
        if ok:
            self.cache.store_last_good(SLOT_WALLET, {"address": self.wallet}, ts=now)
        self._note(SOURCE_WALLET, ok)
        return state

    # -- the medium tier: the log sweep and the fold -------------------------

    def _sweep_from_block(self) -> int:
        """Where the next sweep starts.

        A repair range wins, then the watermark + 1, then the creation block.
        **Never the head**: an absent watermark means "we have never folded
        anything", and starting from now would leave the whole game unfolded
        behind an empty leaderboard with no error anywhere.  The full backfill
        is one sweep in practice — 377 rows from block 25 769 870, validated in
        the research.
        """
        if self._repair_from_block is not None:
            return max(A.CREATION_BLOCK, self._repair_from_block)
        watermark = self.cache.last_seen_block()
        if watermark is None:
            return A.CREATION_BLOCK
        return max(A.CREATION_BLOCK, watermark + 1)

    def _log_group_failed(self) -> dict[str, bool]:
        """The client's per-filter failure dict, defensively.

        ``LogSweep``'s ``()`` is ambiguous — "read, nothing matched" or "this
        filter died" — and only this dict tells them apart.  A double that does
        not define it is treated as "nothing failed", which is what a client
        that cannot report partial failure is in fact claiming.
        """
        flags = getattr(self.client, "log_group_failed", None)
        if not isinstance(flags, dict):
            return dict.fromkeys(LOG_GROUPS, False)
        return {group: bool(flags.get(group)) for group in LOG_GROUPS}

    def _logs_read_groups(self) -> set[str]:
        """Which log groups have ever been read successfully, across restarts.

        This is what separates ``[]`` from ``None`` for a group whose history is
        legitimately empty: ``HourSaved`` and ``Rescued`` have never fired on
        chain, so "read it, found nothing" is the *expected* answer and must not
        render as an outage — while a group nobody has ever managed to read must
        not render as an empty game.
        """
        entry = self.cache.get_last_good(SLOT_LOGS)
        payload = entry.payload if entry is not None else None
        groups = payload.get("groups_read") if isinstance(payload, dict) else None
        return {g for g in groups if g in LOG_GROUPS} if isinstance(groups, list) else set()

    async def _pool_logs(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Sweep, decode, fold and persist.  Never raises.

        Incremental by design: after the first backfill the client only hands
        back rows newer than the watermark, so the cache is the only place the
        rest of the game exists.  The watermark advances **only** on a
        successful sweep — advancing it on a failure would skip that range
        forever, and the leaderboard would be permanently wrong with no symptom.
        """
        if TIER_MEDIUM not in tiers:
            return {"ok": None, "swept": False}

        from_block = self._sweep_from_block()
        sweep = await self._guard(
            lambda: self.client.fetch_logs(from_block), "fetch_logs"
        )
        if sweep is None:
            self.cache.mark_failed(TIER_MEDIUM, now)
            self._note(SOURCE_LOGS, False)
            return {"ok": False, "swept": True, "from_block": from_block}

        failed = self._log_group_failed()
        decoded = [decode_deposit(row) for row in getattr(sweep, "deposits", ())]
        events = [event for event in decoded if event is not None]
        if len(events) != len(decoded):
            logger.warning(
                "Curator sweep: %d of %d Deposited row(s) did not decode and were "
                "dropped rather than zeroed",
                len(decoded) - len(events),
                len(decoded),
            )
        self.cache.store_events(events, now=now)

        firsts = [decode_first_deposit(row) for row in getattr(sweep, "first_deposits", ())]
        self.cache.store_first_deposits([row for row in firsts if row is not None])
        saved = [decode_hour_saved(row) for row in getattr(sweep, "hour_saved", ())]
        self.cache.store_hour_saved([row for row in saved if row is not None])
        if not failed["rescued"]:
            self.cache.store_rescued_total(
                decode_rescued_total(getattr(sweep, "rescued", ()))
            )
        for row in getattr(sweep, "settled", ()):
            obituary = decode_settled(row)
            if obituary is not None:
                # The obituary only. The verdict is the view's, and the latch
                # refuses to be created by a log (H1).
                self.cache.record_settled_event(
                    hour=obituary["hour"],
                    ts=obituary["ts"],
                    contributors=obituary["total_contributors"],
                    volume_wei=obituary["total_volume_wei"],
                )

        # The watermark is where the *next* sweep starts, so it may only move
        # over a range every filter actually covered.  A sweep in which one
        # topic filter died read that range for five groups and not for the
        # sixth, and advancing past it would skip the sixth's rows **forever** —
        # ``store_fold``'s own contract, and the failure the gap-repair tier
        # exists because of.  ``last_block=None`` is its documented "rows in,
        # watermark unchanged" combination: what arrived is kept, and the range
        # is swept again next tick.
        covered = not any(failed.values())
        if not covered:
            logger.warning(
                "Curator sweep from block %d had a dead filter (%s); the rows it "
                "did return are folded but the watermark stays put so the range "
                "is re-read rather than skipped",
                from_block,
                ", ".join(sorted(g for g, dead in failed.items() if dead)),
            )
        self._refold(
            config,
            last_block=_opt_int(getattr(sweep, "to_block", None)) if covered else None,
            now=now,
        )

        groups_read = self._logs_read_groups() | {
            group for group, dead in failed.items() if not dead
        }
        self.cache.store_last_good(
            SLOT_LOGS,
            {
                "groups_read": sorted(groups_read),
                "events": len(self.cache.events()),
                "last_block": self.cache.last_seen_block(),
            },
            ts=now,
        )
        self.cache.mark_fetched(TIER_MEDIUM, now)
        # A partial sweep is still a sweep: the rows that arrived are folded and
        # persisted, and the groups that died reach the user through `degraded`
        # rather than through a silently empty table.
        self._note(SOURCE_LOGS, not any(failed.values()))
        if self._repair_from_block is not None:
            logger.info(
                "Curator gap repair swept from block %d and completed", from_block
            )
            self._repair_from_block = None
            self._fold_stale = False
        return {
            "ok": True,
            "swept": True,
            "from_block": from_block,
            "sweep": sweep,
            "failed": failed,
        }

    def _refold(
        self, config: dict[str, Any] | None, *, last_block: int | None, now: float
    ) -> None:
        """Re-run the pure folds over the whole persisted history.

        Every fold is a pure function of the events, so this is idempotent and
        the cheapest correct thing: a sweep that recovers a missed range simply
        produces the right answer next cycle instead of patching a running
        total.  The analytics calls go through ``_safe_call`` so a fold bug costs
        one number rather than the cycle.
        """
        cfg = config or {}
        events = self.cache.events()
        # ``default=None`` rather than ``[]``: a fold that *raised* is not a fold
        # that found nobody.  Handing ``[]`` on to ``store_fold`` would blank the
        # leaderboard, advance the watermark past the range that produced it and
        # — before the curve below was written per hour — launder the failure
        # into a literal ``0`` in a *persisted* series, which is the one thing
        # the house rule forbids outright.
        rows = _safe_call(
            fold_deposits,
            events,
            self.cache.first_deposits(),
            points_per_eth=cfg.get("points_per_eth"),
            default=None,
        )
        if rows is None:
            logger.warning(
                "Curator fold over %d event(s) failed; keeping the previous table "
                "and the watermark rather than publishing an empty one",
                len(events),
            )
        else:
            self.cache.store_fold(rows, last_block=last_block, now=now)

        buckets = _safe_call(
            hourly_buckets,
            events,
            launch_time=cfg.get("launch_time"),
            hour_duration=cfg.get("hour_duration"),
            first_judged_hour=cfg.get("first_judged_hour"),
            hourly_threshold_wei=cfg.get("hourly_threshold_wei"),
            default=[],
        )
        # Without the launch anchor a bucket has no wall clock, so there is
        # nothing honest to plot: the series waits for the `once` tier rather
        # than inventing a timeline.
        #
        # Both curves are written **per bucket**, walking the dense hourly fold
        # in order and accumulating the joiners of each hour — the same running
        # sum ``build_signals`` computes, so the persisted history and the
        # freshly computed one are the same curve rather than one point of it.
        # Stamping a single cumulative total at the newest bucket produced a
        # one-point series, and a sparkline with one point renders
        # "waiting for data..." forever however long the game has run.
        joined_by_hour: dict[int, int] = {}
        for row in rows or ():
            first_hour = getattr(row, "first_hour", None)
            if first_hour is not None:
                joined_by_hour[first_hour] = joined_by_hour.get(first_hour, 0) + 1
        pairs = []
        joined: list[tuple[float, int]] = []
        running = 0
        for bucket in buckets or ():
            running += joined_by_hour.get(bucket.hour, 0)
            stamp = _safe_call(
                bucket_start_ts,
                bucket.hour,
                cfg.get("launch_time"),
                cfg.get("hour_duration"),
            )
            if stamp is not None:
                pairs.append([stamp, bucket.volume_wei])
                joined.append((stamp, running))
        if pairs:
            self.cache.record_hour_buckets(pairs, now=now)
        # Only a fold that actually ran may write the contributor curve: a
        # failed one has no count, and ``0`` is not the count of a failure.
        if rows is not None:
            for stamp, total in joined:
                self.cache.record_contributor_count(total, ts=stamp, now=now)

    # -- the slow tier: the independent cross-check and gap repair -----------

    def _spawn_crosscheck(
        self, tiers: set[str], now: float, state: Any, config: dict[str, Any] | None
    ) -> Any:
        """Start the cross-check **detached**; never wait for it.

        Awaiting it inside the cycle put the whole dashboard behind a read of
        the contract's *entire* log history, on every launch and on every slow
        tick.  Measured through the real app: first payload after **201.2 s**,
        of which ``fetch_blockscout_logs`` was 202.6 of 203.8 s in cycle 0
        while the next cycle took 0.8 s.  The fold that drives every panel was
        ready in under a second and the reader watched an empty SIGNALS rail --
        the doomsday clock this dashboard exists for -- for three and a half
        minutes.  Blockscout pages 50 logs at a time and the contract is past
        19 500 of them and climbing, so the wait grows with the game and the
        slow tier's own 420 s period does not.

        Nothing downstream needs the answer *this* cycle.  The cross-check
        publishes no key: it either agrees with the fold or schedules a repair
        sweep by setting ``_repair_from_block``, which the next medium tick
        reads.  Skipping it entirely is already a supported, tested state
        (``{"ok": None, "checked": False}``), so a payload built before it
        lands is a payload this manager was always allowed to produce.

        One at a time.  While a sweep is in flight the slow tier stays *due*
        (only the call itself marks it), so every cycle offers again and the
        guard here is what keeps a 200-second read from stacking up thirty
        deep behind a 30-second poll.

        ``now`` is the spawn time, deliberately: it stamps the last-good slot
        and therefore the ``as of HH:MM`` marker, and a marker that claims the
        *end* of a three-minute read is a marker claiming data is fresher than
        it is.

        **What this does not fix.**  The sweep still costs O(whole history)
        every slow tick, and the history grows while :data:`TIER_SLOW`'s 420 s
        period does not — at the launch-week rate the two cross over within a
        day, after which the guard above simply runs one sweep after another in
        the background.  That is bandwidth, not latency, and no reader waits on
        it; a cross-check that pages only down to a persisted verified-to-block
        watermark is the real answer and is PRD §12 material, not v1.
        """
        if TIER_SLOW not in tiers:
            return None
        running = self._crosscheck_task
        if running is not None and not running.done():
            logger.debug("Curator cross-check still in flight; not starting another")
            return running
        self._crosscheck_task = asyncio.ensure_future(
            self._crosscheck_detached(tiers, now, state, config)
        )
        return self._crosscheck_task

    async def _crosscheck_detached(
        self, tiers: set[str], now: float, state: Any, config: dict[str, Any] | None
    ) -> None:
        """:meth:`_pool_crosscheck` with nobody to raise at.

        A detached task's exception surfaces at garbage-collection time as an
        "exception was never retrieved" line and never as a degraded source,
        so it is caught here.  ``CancelledError`` is re-raised: that one is
        :meth:`close` doing its job.
        """
        try:
            await self._pool_crosscheck(tiers, now, state, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            logger.warning("Curator cross-check failed: %s", exc)

    async def _cancel_crosscheck(self) -> None:
        """Stop an in-flight cross-check and wait for it to actually be gone."""
        task = self._crosscheck_task
        self._crosscheck_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            logger.debug("curator cross-check stopped on close: %s", exc)

    async def _pool_crosscheck(
        self, tiers: set[str], now: float, state: Any, config: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Diff the fold against an independent source and the contract's counters.

        Two checks, both of which end in *re-sweep*, never in a quietly wrong
        number:

        * **Blockscout** serves the same logs over a different transport.  Any
          ``Deposited`` row it has that the fold does not is a gap, and the
          oldest such block is where the repair sweep starts.
        * **``stats()``** is the contract's own deposit counter.  It is only
          comparable when the fold covers the block the counter was read at —
          the two are read seconds apart on *different endpoint pools*, so a
          fold that is merely younger is not a fold that is short.
        """
        if TIER_SLOW not in tiers:
            return {"ok": None, "checked": False}

        rows = await self._guard(
            self.client.fetch_blockscout_logs, "fetch_blockscout_logs"
        )
        gap_block: int | None = None
        if rows is None:
            # The cross-check is unavailable, which is not the same as the logs
            # being unavailable: the fold still stands on the RPC sweep.
            self.cache.mark_failed(TIER_SLOW, now)
        else:
            known = {
                (event.tx_hash.lower(), event.log_index)
                for event in self.cache.events()
            }
            watermark = self.cache.last_seen_block()
            for row in rows:
                event = decode_deposit(row)
                if event is None:
                    continue
                if (event.tx_hash.lower(), event.log_index) in known:
                    continue
                if watermark is None or event.block_number > watermark:
                    # Newer than anything we have swept is not a gap: the two
                    # sources are read minutes apart and Blockscout is often
                    # ahead. Only a row *inside* the range we claim to have
                    # folded is evidence that we missed something.
                    continue
                gap_block = (
                    event.block_number
                    if gap_block is None
                    else min(gap_block, event.block_number)
                )
            self.cache.store_last_good(
                SLOT_BLOCKSCOUT, {"rows": len(rows), "gap_block": gap_block}, ts=now
            )
            self.cache.mark_fetched(TIER_SLOW, now)

        counter = _opt_int(getattr(state, "tx_count", None))
        state_block = _opt_int(getattr(state, "block_number", None))
        watermark = self.cache.last_seen_block()
        covered = (
            counter is not None
            and state_block is not None
            and watermark is not None
            and watermark >= state_block
        )
        # The cap counts.  ``MAX_PERSISTED_EVENTS`` drops the OLDEST rows once
        # the history outgrows it, and the cache says so in as many words: "the
        # folded totals are now a lower bound; the contract's own counters are
        # not".  Comparing the retained rows against a counter that has never
        # forgotten anything therefore declares the fold short *permanently*
        # once the cap trips — a full re-sweep from the creation block on every
        # slow tick, each one re-dropping the overflow, plus a `degraded` that
        # never clears.  What we have seen is retained + dropped.
        seen = len(self.cache.events()) + max(
            0, _opt_int(getattr(self.cache, "dropped_events", 0)) or 0
        )
        if covered and seen < counter:
            logger.warning(
                "Curator fold is short: %d folded deposits (%d retained + %d the "
                "history cap dropped) against the contract's own %d at block %s "
                "— re-sweeping",
                seen,
                len(self.cache.events()),
                seen - len(self.cache.events()),
                counter,
                state_block,
            )
            gap_block = A.CREATION_BLOCK if gap_block is None else min(
                gap_block, A.CREATION_BLOCK
            )

        if gap_block is not None:
            # Publish the shortfall rather than the number: the fold is stale
            # until the repair sweep lands, and `degraded` is how the user is
            # told.
            self._fold_stale = True
            self._repair_from_block = gap_block
            self._note(SOURCE_LOGS, False)
            # The repair runs on the next medium tick, so bring it forward.
            self.cache.mark_failed(TIER_MEDIUM, now, retry_after=0.0)
        return {"ok": rows is not None, "checked": True, "gap_block": gap_block}

    # -- the analysis tier: the detached Tier-B+C sweep (WP3) ----------------

    def _spawn_analysis(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> Any:
        """Start the analysis sweep **detached**; never wait for it.

        :meth:`_spawn_crosscheck`'s pattern, verbatim, for the same measured
        reason: a full tier-C funding pass is minutes long (~200 lookups at
        Blockscout's ~3 req/s per sweep, and that is the *bounded* version),
        and awaiting it in-cycle would put the doomsday clock behind it.
        Nothing downstream needs the answer this cycle: the sweep publishes
        into ``SLOT_CLUSTERS`` and the **next** cycle's merge reads it; a
        payload built before it lands is the already-supported "analysis not
        yet run" state.

        One at a time: while a sweep is in flight the analysis tier stays due
        (only :meth:`_pool_analysis` marks it), so every cycle offers again
        and the guard here is what keeps a minutes-long read from stacking up
        behind a 30-second poll.  ``now`` is the spawn time and stamps the
        slot — a marker taken at the end of a long read claims the data is
        fresher than it is.
        """
        if TIER_ANALYSIS not in tiers:
            return None
        running = self._analysis_task
        if running is not None and not running.done():
            logger.debug("Curator analysis sweep still in flight; not starting another")
            return running
        self._analysis_task = asyncio.ensure_future(
            self._analysis_detached(tiers, now, config)
        )
        return self._analysis_task

    async def _analysis_detached(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> None:
        """:meth:`_pool_analysis` with nobody to raise at.

        Same shape as :meth:`_crosscheck_detached`: a detached task's
        exception surfaces as an "exception was never retrieved" line at GC
        time and never as a degraded source, so it is caught here.  A sweep
        that RAN and failed marks its tier failed (backoff) and sets
        ``_analysis_failed`` — which lights the ``logs`` banner **only while
        there is no analysis last-good to serve** (see :meth:`_degraded`).
        ``CancelledError`` is re-raised: that one is :meth:`close` working.
        """
        try:
            await self._pool_analysis(tiers, now, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            self._analysis_failed = True
            # Completion time, not spawn time (M4): a sweep that took 200 s to
            # die must not have those 200 s deducted from its retry spacing.
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            logger.warning("Curator analysis sweep failed: %s", exc)

    async def _cancel_analysis(self) -> None:
        """Stop an in-flight analysis sweep and wait for it to be gone."""
        task = self._analysis_task
        self._analysis_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            logger.debug("curator analysis sweep stopped on close: %s", exc)

    def _analysis_session(self) -> tuple[Any, Any]:
        """``(client, transport)`` the enrichment fetch may use.

        An injected transport wins (tests); otherwise the real client's own
        ``httpx`` session is borrowed (production — ``_client`` is the
        attribute every ``OwnedHttpClient`` subclass carries, and the sweep is
        cancelled in :meth:`close` *before* that session closes).  A double
        with neither means the sweep fetches nothing and runs tier A only —
        no test can open a socket by forgetting to inject.
        """
        if self._analysis_transport is not None:
            return None, self._analysis_transport
        return getattr(self.client, "_client", None), None

    async def _pool_analysis(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> dict[str, Any]:
        """One bounded, resumable Tier-B+C sweep, published as a last-good.

        The rule (PRD §4, ruling R3): candidates only, never the population.
        The adapter picks the tier-A component members plus a small control
        margin, extends the accumulated fingerprint/funding coverage by one
        budgeted pass (the cursor rides in the slot payload), and re-runs the
        pure analysis over everything held.  The pure folds run in a worker
        thread: ~0.4 s of detect over a real history would otherwise stall
        the TUI's event loop twice an hour.

        "Cannot run yet" — no events folded, or the ``once`` tier has not
        produced the live rate and minimum — is **not** a failed sweep: the
        tier is spaced (so the offer is not re-made every cycle) and no
        degradation lights, because whichever source is actually missing
        already tells its own story.
        """
        if TIER_ANALYSIS not in tiers:
            return {"ok": None, "swept": False}
        if not curator_clusters.SYBILKIT_AVAILABLE:
            # The guarded-import compatibility story (fix round 1): until
            # maxpane's own dependency list can name sybilkit (it is not on
            # PyPI yet), absence is the cannot-run state — spaced retry, no
            # banner, the twelve keys in their honest not-yet-run None.
            if not self._sybilkit_missing_logged:
                self._sybilkit_missing_logged = True
                logger.info(
                    "sybilkit is not installed; the linked-wallet analysis "
                    "panels stay in their unavailable state"
                )
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": None, "swept": False}
        cfg = config if isinstance(config, dict) else {}
        events = self.cache.events()
        rate = _opt_int(cfg.get("points_per_eth"))
        minimum = _opt_int(cfg.get("min_deposit_wei"))
        if not events or rate is None or rate <= 0 or minimum is None:
            # Completion-time stamp (M4): the retry clock must not have the
            # sweep's own duration deducted from it.  Freshness stamps stay
            # spawn-time — only failures are stamped at completion.
            # Deliberately does NOT clear `_analysis_failed`: a failed sweep
            # followed by a cannot-run one keeps its banner state (ledgered
            # fix-round-1 deferral; the sequence takes a config slot decaying
            # mid-flight, which nothing produces today).
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": None, "swept": False}

        firsts = self.cache.first_deposits()
        entry = self.cache.analysis_last_good()
        prior = (
            entry.payload.get("enrichment")
            if entry is not None and isinstance(entry.payload, dict)
            else None
        )
        preset = curator_clusters.build_preset(rate, minimum)
        funding_wanted, tx_wanted = await asyncio.to_thread(
            curator_clusters.candidate_targets, events, firsts, preset
        )
        client, transport = self._analysis_session()
        enrich = await curator_clusters.fetch_enrichment(
            tx_wanted=tx_wanted,
            funding_wanted=funding_wanted,
            state=prior,
            client=client,
            transport=transport,
            sleep=self._analysis_sleep,
        )
        result = await asyncio.to_thread(
            lambda: curator_clusters.build_analysis(
                events,
                firsts,
                txs=enrich.txs,
                funding=enrich.funding,
                wallet=self.wallet,
                config=preset,
            )
        )
        payload = curator_clusters.slot_payload(
            result, enrichment=enrich.state()
        )
        self.cache.store_analysis(payload, ts=now)
        # M2: the enrichment health decides the RETRY clock, never the
        # publish.  The tier-A(+accumulated) result above is data-wise honest
        # either way; but a pass in which every source that was asked a
        # question was down should retry on the failure backoff, not wait out
        # the full TTL — and a partial outage is logged so a one-sided
        # coverage stall is discoverable.
        attempted = [
            ok for ok in (enrich.tx_ok, enrich.funding_ok) if ok is not None
        ]
        if attempted and not any(attempted):
            logger.warning(
                "Curator analysis sweep published on held data only: every "
                "enrichment source that was asked a question was unreachable; "
                "retrying on the failure backoff"
            )
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
        else:
            if False in attempted:
                dead = "fingerprints" if enrich.tx_ok is False else "funding"
                logger.warning(
                    "Curator analysis sweep published with the %s source "
                    "unreachable; its coverage extends next sweep", dead
                )
            self.cache.mark_fetched(TIER_ANALYSIS, now)
        self._analysis_failed = False
        return {"ok": True, "swept": True}

    # -- the WP3 seam --------------------------------------------------------

    def _log_reading(
        self, name: str, values: list, *, swept: bool, failed: bool = False
    ) -> list | None:
        """``[]`` when the read happened and found nothing; ``None`` when it did not.

        Collapsing the two makes a dead logs pool indistinguishable from a quiet
        chain — and *quiet* is the state that kills this contract, so the
        difference is the whole dashboard.

        Three questions in order, and the order is the point:

        1. **Do we hold rows?**  Then serve them.  The fold is accumulated and
           is last-good by construction, behind the ``as of HH:MM`` marker.
        2. **Did *this group's own filter* die in this sweep?**  Then ``None``.
           ``swept`` is a fact about the sweep, not about the group: a sweep
           whose ``deposits`` filter died still returns a ``LogSweep``, so
           keying off it alone reads a dead filter as "read it, found nothing"
           — the exact conflation 1ba8370 fixed one level up, reintroduced one
           level down.  It only bites while a group has no history, which is to
           say on the first run.
        3. **Has anyone ever read this group?**  Then ``[]``: ``HourSaved`` and
           ``Rescued`` have never fired on chain, so "read it, found nothing" is
           the *expected* answer and must not render as an outage.
        """
        if values:
            return values
        if failed:
            return None
        if swept or name in self._logs_read_groups():
            return []
        return None

    def _readings(
        self,
        *,
        state: Any = None,
        config: Any = None,
        logs: Any = None,
        wallet_state: Any = None,
        log_groups_failed: Any = None,
    ) -> dict[str, Any]:
        """Everything ``build_signals`` reads, and only that.

        Three provenances, deliberately different:

        * **fast-tier values are live-only.**  A dead state pool means the
          clock, the phase truth, ``earlyBps`` and the forced-ETH row are
          ``None`` and render *unavailable* — not a stale number wearing a live
          face (PRD §11's degradation matrix, row 1).
        * **config comes from the cache**, because immutables cannot go stale.
          Reading them once and remembering is not staleness, it is what
          ``once`` means.
        * **log-derived values come from the accumulated fold**, which *is*
          last-good and is served behind the ``as of HH:MM`` marker.  The sweep
          is incremental, so this is the only place the game's history exists.

        The settlement record is the latch, not a read: it beats whatever
        ``isSettled()`` said this cycle (H1).
        """
        cfg = config if isinstance(config, dict) else {}
        swept = logs is not None
        # Per-filter, not per-sweep.  Absent means "nothing is known to have
        # failed", which is what a caller that cannot report partial failure is
        # in fact claiming.
        dead = log_groups_failed if isinstance(log_groups_failed, dict) else {}
        read: dict[str, Any] = {key: None for key in READING_KEYS}

        for key in FAST_TIER_PAYLOAD_KEYS:
            read[key] = getattr(state, key, None)
        for key in CONFIG_PAYLOAD_KEYS:
            read[key] = cfg.get(key)

        # Whether a *historical* rank is computable at all: the cap drops the
        # oldest rows, and a rank counted over what survived would count fewer
        # competitors than existed.  See `analytics.you_ladder`.
        read["history_complete"] = self.cache.dropped_events == 0

        read["deposits"] = self._log_reading(
            "deposits",
            self.cache.events(),
            swept=swept,
            failed=bool(dead.get("deposits")),
        )
        read["first_deposits"] = self._log_reading(
            "first_deposits",
            self.cache.first_deposits(),
            swept=swept,
            failed=bool(dead.get("first_deposits")),
        )
        read["hour_saved"] = self._log_reading(
            "hour_saved",
            self.cache.hour_saved(),
            swept=swept,
            failed=bool(dead.get("hour_saved")),
        )
        read["rescued_total_wei"] = self.cache.rescued_total_wei()

        read["settlement_record"] = self.cache.settlement_record()
        read["wallet_state"] = wallet_state
        return read

    # -- public API ----------------------------------------------------------

    def set_wallet(self, address: str | None) -> bool:
        """Point the YOU row at a different wallet.  Returns whether it moved.

        The constructor is still the normal way in (``--wallet`` /
        ``MAXPANE_WALLET``); this is the reader changing their mind at runtime,
        from the screen's ``w`` key.  It is deliberately more than
        ``self.wallet = address``, because three pieces of state are *about the
        old address* and each would otherwise render under the new one:

        * ``_fast_wallet`` — the within-TTL re-serve.  Left alone, the previous
          wallet's rank, credit and "next ≥" survive on screen under somebody
          else's address for up to one fast tier;
        * the ``wallet`` last-good slot, whose payload is literally
          ``{"address": <the old one>}`` — dropped rather than re-served behind
          an ``as of`` marker.

        Dropping that slot also settles the stale-failure question, which is why
        ``_failed_groups`` is **not** touched here: :meth:`_degraded` degrades a
        group whose last-good is absent, so between the switch and the first
        successful read the new wallet reads as degraded either way — which is
        the honest state, since nothing has been read about it yet.  Discarding
        the old address's failure as well would change nothing observable, and
        this repo does not keep code no test can pin.

        The fast tier is then expired so the next cycle actually refetches: a
        tier with 12 of its 15 seconds left is "fresh", and without this the row
        stays empty after a keypress that looked like it worked.

        The **analysis linkage needs no expiry at all**: the B+C sweep is
        about the population, not about one wallet, so ``you_linked_*`` /
        ``you_clean_rank`` are re-answered by the next cycle's merge from the
        **already-held** analysis last-good (:meth:`_merge_analysis` asks
        ``curator_clusters.you_linkage`` about ``self.wallet`` every cycle).
        Expiring :data:`TIER_ANALYSIS` here would burn a minutes-long sweep to
        re-learn facts the slot already holds.

        A no-op when the address is unchanged (including ``""``/``None`` both
        meaning *no wallet*), so a reader who re-types the same address does not
        pay a refetch or lose their last-good.
        """
        normalised = address or None
        if normalised == self.wallet:
            return False
        self.wallet = normalised
        self._fast_wallet = None
        self.cache.drop_last_good(SLOT_WALLET)
        self.cache.expire(TIER_FAST)
        return True

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Run one refresh cycle and return the flat dashboard dict.

        **No exception escapes.**  A total failure still returns the full key
        set with every value ``None`` and ``degraded`` naming what died,
        because a widget can render an explicit unavailable state but cannot
        render a traceback.  The screen's own ``try``/``except`` is belt and
        braces for a mis-wired manager, never the documented outage path.
        """
        try:
            return await self._cycle()
        except Exception as exc:  # noqa: BLE001 — the outermost guard
            self._error_count += 1
            logger.exception("Curator refresh cycle failed outright: %s", exc)
            payload = self._blank_payload()
            payload["degraded"] = sorted(SOURCES)
            self._stamp(payload)
            return payload

    async def _cycle(self) -> dict[str, Any]:
        now = float(self._clock())
        self._cycle_count += 1
        tiers = set(self.cache.tiers_due(now))

        # The immutables first: the fold and the series both need the launch
        # anchor, and everything else is independent of them.
        config = await self._pool_config(tiers, now)

        # Both halves of the fast tier ride the same pool and the same tick —
        # and both are **gated on the tier**, the way the medium and slow halves
        # are.  Ungated, `TIER_TTL_SECONDS["fast"]` and its failure backoff are
        # decorative: `--poll-interval 5` is accepted (`_MIN_POLL_INTERVAL`), so
        # the eight-view batch, the balance and the six YOU views were being
        # re-sent three times per declared 15 s window against keyless public
        # endpoints, and a rate-limited host was hammered rather than backed
        # off.  PRD §5 sizes this tier at 15 s; this is where that number takes
        # effect.
        if TIER_FAST in tiers:
            state_out, wallet_state = await asyncio.gather(
                self._pool_state(now), self._pool_wallet(now)
            )
            state = state_out.get("state")
            self._fast_state = state
            self._fast_wallet = wallet_state
        else:
            state = self._fast_state
            wallet_state = self._fast_wallet

        logs_out = await self._pool_logs(tiers, now, config)
        # Started, not awaited: it reads the whole log history over a second
        # transport and takes minutes, while publishing no key.  See
        # `_spawn_crosscheck`.
        self._spawn_crosscheck(tiers, now, state, config)
        # Started, not awaited, for the same reason: the bounded funding pass
        # alone is ~70 s of paced requests.  The NEXT cycle's merge reads what
        # it publishes.  See `_spawn_analysis`.
        self._spawn_analysis(tiers, now, config)

        readings = self._readings(
            state=state,
            config=config,
            logs=logs_out.get("sweep"),
            wallet_state=wallet_state,
            log_groups_failed=logs_out.get("failed"),
        )
        signals = _safe_call(build_signals, readings, now_ts=now, default=None)
        if not isinstance(signals, dict):
            logger.warning("build_signals returned %r — publishing the blank contract", signals)
            payload = self._blank_payload()
            # `degraded` is recomputed from SOURCE health below, and the sources
            # may all be perfectly healthy — the analytics are what died.  Left
            # alone this publishes 49 None values under `degraded == []`, i.e. a
            # total internal failure wearing the face of a healthy picture, and
            # `_safe_call` intercepts the most likely internal failure before the
            # outermost handler (which does exactly this) can ever see it.
            self._failed_groups.update(SOURCES)
        else:
            payload = dict(signals)

        # ``build_signals`` defaults its six list keys to ``[]`` — total over
        # hostile input, which is right for it and wrong for the four
        # SOURCE-BACKED ones here.  WP0 froze "a None list means the source is
        # dead, [] means genuinely nothing", and the widgets branch on it: left
        # as ``[]``, a dead logs pool would assert that nobody has ever
        # deposited.  The distinction is only knowable at this seam, because
        # only the manager knows whether the read happened.
        if readings.get("deposits") is None:
            for key in _SOURCE_BACKED_ROW_KEYS:
                if not payload.get(key):
                    payload[key] = None

        # The persisted series outlive one cycle's fold: they hold the hours
        # whose events the history cap has since dropped, and they survive a
        # restart. An empty one is left as ``build_signals`` produced it.
        for key in CURATOR_SERIES_KEYS:
            stored = self.cache.get_series(key)
            if stored:
                payload[key] = stored

        # The analysis merge runs BEFORE the ENS labelling (the WP3 brief
        # sketched after) for one reason: the clean list's identity cells are
        # the leaderboard's exactly, and a merge that ran second would hand
        # the labeller rows it never saw.
        _safe_call(self._merge_analysis, payload)

        await self._label_with_ens(payload, now)

        payload["degraded"] = self._degraded()
        self._stamp(payload)
        return self._finalise(payload)

    # -- the analysis merge (WP3.4) ------------------------------------------

    def _merge_analysis(self, payload: dict[str, Any]) -> None:
        """Merge the detached sweep's last-good into the flat dict.  In place.

        The ENS-merge shape: ``build_signals`` never sees these keys, the
        adapter's lookups fill them, and the widget's unavailable states do
        the rest.  Three states, never collapsed:

        * **no last-good** — every analysis key stays ``None`` (the blank
          payload's own value; an ``[]`` here would be an empty table
          asserting nobody is linked, off a read that never happened) and
          ``link_conf`` is seeded ``None`` on every leaderboard row (R9);
        * **analyzed, nothing linked** — ``operators_count == 0`` with real
          empty rows, a representable zero;
        * **analyzed and linked** — rows, counts, the reader's linkage, and
          the ``flagged_points_share_pct`` **override-with-fallback** (plan
          §6 risk 2 as pre-ruled): the analysis's share wins when it carries
          one, Tier A's ``build_signals`` value stands otherwise.

        Rows are **copied** out of the slot: the ENS labeller writes ``name``
        onto the payload's rows next, and writing into the cached slot would
        persist names into the analysis payload where they outlive every name
        TTL.  ``analysis_as_of_hhmm`` is the slot's own spawn-time stamp —
        the sweep's freshness moves on its own schedule, never the fast
        tier's.
        """
        entry = self.cache.analysis_last_good()
        slot = (
            entry.payload
            if entry is not None and isinstance(entry.payload, Mapping)
            else None
        )
        rows = payload.get("leaderboard_rows")
        curator_clusters.merge_leaderboard_grade(
            rows if isinstance(rows, list) else None, slot
        )
        if slot is None:
            return
        for key in ("operator_rows", "segment_rows", "clean_list_rows"):
            value = slot.get(key)
            payload[key] = (
                [dict(row) for row in value if isinstance(row, Mapping)]
                if isinstance(value, list)
                else None
            )
        for key in (
            "operators_count",
            "clean_points",
            "clean_contributors",
            "points_total",
        ):
            payload[key] = _opt_int(slot.get(key))
        share = slot.get("flagged_points_share_pct")
        if isinstance(share, (int, float)) and not isinstance(share, bool):
            payload["flagged_points_share_pct"] = float(share)
        payload["analysis_as_of_hhmm"] = entry.as_of_hhmm()
        if self.wallet:
            payload.update(curator_clusters.you_linkage(self.wallet, slot))

    # -- reverse ENS (PRD §13 A9) --------------------------------------------

    def _rendered_addresses(self, payload: Mapping[str, Any]) -> list[str]:
        """Every address this payload will put on screen, and nothing else.

        Resolving the whole contributor table would be thousands of addresses
        for ten visible rows.  The set is: the leaderboard's rows, the activity
        feed's, the two signal wallets, the savior column, and the reader's own.
        """
        out: list[str] = []
        # ``clean_list_rows`` renders the same identity cell the leaderboard
        # does (bounded: the adapter caps the rendered slice), so its
        # addresses are part of the on-screen set — after the analysis merge,
        # which is why the merge runs first.
        for key in ("leaderboard_rows", "activity_rows", "clean_list_rows"):
            for row in payload.get(key) or ():
                if isinstance(row, dict) and isinstance(row.get("address"), str):
                    out.append(row["address"])
        for row in payload.get("closest_call_rows") or ():
            if isinstance(row, dict) and isinstance(row.get("savior"), str):
                out.append(row["savior"])
        for key in ("whale_wallet", "last_saved_wallet"):
            value = payload.get(key)
            if isinstance(value, str):
                out.append(value)
        if isinstance(self.wallet, str):
            out.append(self.wallet)
        return out

    async def _label_with_ens(self, payload: dict[str, Any], now: float) -> None:
        """Attach verified reverse-ENS names to the addresses being rendered.

        Cosmetic by construction: every failure path here leaves the payload
        exactly as it was, and every widget falls back to the shortened hex.
        Nothing is resolved twice -- a fresh name and a fresh *miss* both mean
        "do not ask" (see :class:`ens.NameStore`), and without the miss half
        most wallets would be re-queried on every tick forever, because most
        wallets have no reverse record.
        """
        known = self.cache.ens.names_fresh(ens.DEFAULT_TTL_SECONDS, now)
        misses = self.cache.ens.misses_fresh(ens.MISS_TTL_SECONDS, now)

        wanted: list[str] = []
        seen: set[str] = set()
        for addr in self._rendered_addresses(payload):
            key = addr.lower()
            if key in known or key in misses or key in seen:
                continue
            seen.add(key)
            wanted.append(addr)

        if wanted:
            resolved = await self._guard(
                lambda: self.client.fetch_ens_names(wanted), "fetch_ens_names"
            ) or {}
            if resolved:
                _safe_call(self.cache.ens.set_names, resolved, ts=now)
                known = {**known, **{a.lower(): n for a, n in resolved.items()}}
            # Everything asked for and not answered has no name.  Recorded so
            # the next cycle does not ask again; a shorter TTL lets a wallet
            # that registers one be picked up.
            _safe_call(
                self.cache.ens.note_misses,
                [a for a in wanted if a.lower() not in known],
                ts=now,
            )

        if not known:
            return

        for key in ("leaderboard_rows", "activity_rows", "clean_list_rows"):
            for row in payload.get(key) or ():
                if isinstance(row, dict) and isinstance(row.get("address"), str):
                    row["name"] = known.get(row["address"].lower())
        for row in payload.get("closest_call_rows") or ():
            if isinstance(row, dict) and isinstance(row.get("savior"), str):
                row["savior_name"] = known.get(row["savior"].lower())
        for src, dst in (
            ("whale_wallet", "whale_ens"),
            ("last_saved_wallet", "last_saved_ens"),
        ):
            value = payload.get(src)
            if isinstance(value, str):
                payload[dst] = known.get(value.lower())
        if isinstance(self.wallet, str):
            payload["you_ens"] = known.get(self.wallet.lower())

    def _stamp(self, payload: dict[str, Any]) -> None:
        """Fill the freshness marker from the newest *successful* read.

        It moves only when something actually answered, which is what makes the
        settlement case honest: after the endpoints die the phase word stays
        SETTLED and this marker is what freezes, so the reader can see exactly
        how old the picture is.
        """
        stamp = None
        try:
            stamp = self.cache.newest_as_of()
        except Exception as exc:  # noqa: BLE001
            logger.debug("curator as-of lookup failed: %s", exc)
        payload["as_of"] = stamp
        payload["as_of_hhmm"] = (
            time.strftime("%H:%M", time.localtime(stamp)) if stamp else None
        )

    # -- contract enforcement ------------------------------------------------

    def _finalise(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return exactly :data:`CURATOR_KEYS`, no more and no less.

        A key this manager invents is dropped and logged rather than shipped: a
        screen that has to ask whether a key exists is a screen with a silent
        fallback arm.
        """
        out = self._blank_payload()
        for key, value in data.items():
            if key in out:
                out[key] = value
            else:
                logger.error(
                    "CuratorManager produced %r, which is not in CURATOR_KEYS — dropped",
                    key,
                )
        return out

    def _blank_payload(self) -> dict[str, Any]:
        """Every key present, every source down, nothing invented.

        The four **source-backed** row keys stay ``None``.  WP0 froze the pair
        of meanings and the widgets act on them: a ``None`` list means *source
        dead* and renders the unavailable state, while ``[]`` means *genuinely
        nothing* and renders "no deposits yet".  Seeding ``[]`` here would make
        a dead logs pool assert that nobody has ever deposited.

        The two **series** keys are different and stay ``[]``: they are this
        cache's own history rather than a source's answer, and an empty history
        is a fact about this install, not about the network.
        """
        payload: dict[str, Any] = dict.fromkeys(CURATOR_KEYS)
        payload["degraded"] = []
        for key in CURATOR_SERIES_KEYS:
            payload[key] = []
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
        # The analysis sweep is enrichment folded over the log story (plan §6
        # risk 7 — no new group name; the title bar's vocabulary is frozen).
        # A failed sweep lights ``logs`` ONLY while there is no analysis
        # last-good to serve: with one, the keys ride behind their own
        # ``analysis_as_of_hhmm`` marker and nothing lights; and a sweep that
        # has never been *able* to run is not a failure at all
        # (``_analysis_failed`` stays False on the cannot-run path).
        if self._analysis_failed and self.cache.analysis_last_good() is None:
            out.add(SOURCE_LOGS)
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
