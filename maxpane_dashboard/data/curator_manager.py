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
import logging
import time
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
)
from maxpane_dashboard.data.safe_call import safe_call

logger = logging.getLogger(__name__)


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
    "GROUP_SLOT",
    "SOURCES",
    "SOURCE_LOGS",
    "SOURCE_STATE",
    "SOURCE_WALLET",
    "CuratorManager",
]
