"""Tiered cache, last-good snapshots and persistence for the FWA dashboard (WP-9).

This module owns *when* the FWA manager is allowed to fetch and *what it may show
when a fetch fails*. It holds no clients, performs no I/O other than reading and
writing its own JSON file, and imports nothing from the project except the frozen
:mod:`maxpane_dashboard.data.fwa_models` contract.

It carries five things:

1. **Per-tier TTL tracking** (PRD §6, plan §8.4). ``fast`` 15 s, ``medium`` 60 s,
   ``slow`` 900 s, ``tail`` 30 s, ``once`` never re-runs. The manager asks
   :meth:`FWACache.tiers_due` what to fetch — the intervals live here and are not
   re-implemented anywhere else.
2. **Last-good snapshots** — the mechanism the whole degradation story rests on.
   Each of the three pools gets a slot holding its last *successful* payload with
   the timestamp (and, where meaningful, the block) it came from, so a widget can
   render ``as of HH:MM`` instead of blanking. Pool B (``eth_getLogs``) is the
   design's single point of failure: when it is down the activity feed and crown
   history must show a persisted last-good value with an explicit staleness
   marker. A stale value presented as live is worse than an honest gap, so a
   :class:`LastGood` never exists without its ``ts``.
3. **Hourly time series**, 168 hours (7 days) deep, hour-bucketed exactly like
   ``talismans_cache``: ``$FWA`` price, ``acquisitionFee``, ``active_positions``
   and the crown pot.
4. **``last_seen_block``** per event type, for WP-7's 30 s log tail.
5. **Persistence** to ``~/.maxpane/fwa_cache.json`` via atomic temp+rename,
   fail-soft on a missing or corrupt file (per-section ``try``/``except``, mirrors
   ``talismans_cache`` / ``ttt_cache``).


Two correctness rules this module enforces structurally
-------------------------------------------------------

**Sweeps are whole, block-pinned snapshots — never merged across blocks**
(PRD §7 rule 11). There is deliberately *no* API for caching an individual
position: :meth:`FWACache.set_sweep` takes a block number plus the complete
position sequence and replaces the slot wholesale. A sweep that is not pinned to a
block is refused outright, and a sweep pinned to a block *older* than the stored
one is refused as well, because publishing it would silently walk the odds board
backwards. Stitching positions read at different blocks is exactly the
plausible-looking, silently-wrong failure the pinning exists to prevent.

**``BackingUpdated`` invalidates the cached sweep** (PRD §7 rule 8). Backing is
mutable via ``updateBacking(uint256,uint256) payable``, so a cached position can go
stale while still looking fresh — and a stale backing corrupts the harmonic mean,
and therefore the flagship EV number. :meth:`FWACache.note_backing_updated` flags
the sweep stale and makes the medium tier due immediately. It only does so for an
event *newer* than the swept block: WP-7 backfills the full event history on first
run, and replaying ancient ``BackingUpdated`` events must not invalidate a sweep
that already reflects them.


Sizing: nothing here assumes a position count
---------------------------------------------

The pool grew **+53% in two days** (3,867 → 5,942 positions, findings §13.6). No
TTL, bound or eviction rule in this module is a function of the number of
positions: the hourly deques are time-bounded, the floor map is bounded by the
collection registry, and the sweep slot holds whatever the sweep produced.

The one deliberate consequence: **position lists are never written to disk.** A
persisted sweep would grow without bound with the pool, and on restart it would be
a set of positions read at a block from a previous process — the very thing rule
11 forbids reasoning about. What *is* persisted is the sweep's provenance (block,
timestamp, staleness), so the UI can honestly say when the last complete sweep
happened, and it is restored already flagged stale.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.fwa_models import Position
from maxpane_dashboard.data.series_points import coerce_points

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and sizing
# ---------------------------------------------------------------------------

DEFAULT_CACHE_PATH = str(Path.home() / ".maxpane" / "fwa_cache.json")

_HOURLY_HISTORY_HOURS = 168          # 7 days
_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Refresh tiers (PRD §6 / implementation plan §8.4)
# ---------------------------------------------------------------------------

TIER_FAST = "fast"        # acquisitionFee, pool temperature, VRF queue, crown pot
TIER_MEDIUM = "medium"    # full position sweep -> odds board, chase board, Pull EV
TIER_SLOW = "slow"        # CoinGecko floors, DexScreener, GeckoTerminal OHLCV
TIER_TAIL = "tail"        # eth_getLogs lastSeen -> latest on Pool B
TIER_ONCE = "once"        # config params, 51-collection allowlist, token metadata

TIER_TTL_SECONDS: dict[str, float | None] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 900.0,
    TIER_TAIL: 30.0,
    TIER_ONCE: None,      # None == never expires once fetched
}
"""Tier -> TTL in seconds. ``None`` means "fetch once, never again this install"."""

TIER_FAILURE_BACKOFF_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 120.0,     # CoinGecko/DexScreener are rate-limited; do not hammer
    TIER_TAIL: 30.0,
    TIER_ONCE: 60.0,
}
"""How long a *failed* tier waits before it becomes due again.

A failure never marks a tier fetched — the last-good payload covers the gap — but
retrying on every manager tick would hammer a rate-limited host, so the retry is
spaced. See :meth:`FWACache.mark_failed`.
"""

TIERS: tuple[str, ...] = (TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_TAIL, TIER_ONCE)

# ---------------------------------------------------------------------------
# Last-good slots
# ---------------------------------------------------------------------------

SLOT_HOT_BATCH = "hot_batch"          # Pool A, fast tier
SLOT_SWEEP = "sweep"                  # Pool A, medium tier (block-pinned)
SLOT_LOGS = "log_aggregates"          # Pool B — the single point of failure
SLOT_MARKET = "market"                # Pool C — DexScreener / GeckoTerminal
SLOT_STARTUP = "startup"              # once tier: params, allowlist, token metadata

_PERSISTED_SLOTS: tuple[str, ...] = (
    SLOT_HOT_BATCH,
    SLOT_LOGS,
    SLOT_MARKET,
    SLOT_STARTUP,
)
"""Slots written to disk. ``SLOT_SWEEP`` is intentionally absent (module docstring)."""

# ---------------------------------------------------------------------------
# Hourly series
# ---------------------------------------------------------------------------

SERIES_FWA_PRICE_USD = "fwa_price_usd"
SERIES_ACQUISITION_FEE_ETH = "acquisition_fee_eth"
SERIES_ACTIVE_POSITIONS = "active_positions"
SERIES_CROWN_POT_ETH = "crown_pot_eth"

SERIES_NAMES: tuple[str, ...] = (
    SERIES_FWA_PRICE_USD,
    SERIES_ACQUISITION_FEE_ETH,
    SERIES_ACTIVE_POSITIONS,
    SERIES_CROWN_POT_ETH,
)


def _hour_bucket(ts: float) -> float:
    """Floor a timestamp to the start of its hour."""
    return float(int(ts // 3600) * 3600)


def _jsonable(value: Any, _depth: int = 0) -> Any:
    """Best-effort conversion of a cached payload to JSON-safe primitives.

    Pydantic models are dumped, mappings and sequences recursed, non-finite
    floats nulled and anything else dropped (``None``) rather than coerced —
    fabricating a value on the way to disk would be worse than losing it.
    """
    if _depth > 12:
        return None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _jsonable(dump(), _depth + 1)
        except Exception as exc:          # pragma: no cover - defensive
            logger.debug("model_dump failed while saving FWA cache: %s", exc)
            return None
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return [_jsonable(v, _depth + 1) for v in value]
    logger.debug(
        "Dropping non-serialisable %s from the FWA cache", type(value).__name__
    )
    return None


# ---------------------------------------------------------------------------
# Last-good snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LastGood:
    """One pool's last *successful* payload, with the provenance to label it.

    ``ts`` is mandatory and is the wall-clock time the payload was fetched, which
    is what lets a widget render ``as of HH:MM`` instead of implying the value is
    live. ``block`` is the pinned block where one exists (``None`` for off-chain
    payloads). ``stale`` marks a payload that is known to no longer reflect chain
    state — an invalidated sweep, or anything restored from disk.
    """

    payload: Any
    ts: float
    block: int | None = None
    stale: bool = False
    stale_reason: str = ""

    def age_seconds(self, now: float) -> float:
        """Seconds between ``ts`` and ``now`` (never negative)."""
        return max(0.0, float(now) - float(self.ts))

    def as_of_hhmm(self) -> str:
        """Local-time ``HH:MM`` of ``ts`` — the staleness marker in the UI."""
        return time.strftime("%H:%M", time.localtime(self.ts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": _jsonable(self.payload),
            "ts": float(self.ts),
            "block": None if self.block is None else int(self.block),
            "stale": bool(self.stale),
            "stale_reason": str(self.stale_reason),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LastGood:
        block = data.get("block")
        return cls(
            payload=data.get("payload"),
            ts=float(data.get("ts") or 0.0),
            block=None if block is None else int(block),
            stale=bool(data.get("stale", False)),
            stale_reason=str(data.get("stale_reason") or ""),
        )


class FWACache:
    """Tiered TTL cache, last-good store and hourly series for one FWA process.

    Single-threaded asyncio access — no locking, matching the rest of the repo.

    ``clock`` is injectable so tests can drive TTL expiry with a fake clock and
    never sleep; every method that needs the time also accepts an explicit ``now``.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock

        # Tier bookkeeping: when each tier was last fetched, and when it is due.
        self._tier_last_fetch: dict[str, float] = {}
        self._tier_next_due: dict[str, float] = {}

        # Last-good payloads keyed by slot (see SLOT_* constants).
        self.last_good: dict[str, LastGood] = {}

        # Floors are per collection with per-collection timestamps: the CoinGecko
        # sweep is spaced seconds apart (6 s as the manager builds it) and reaches
        # only some of the collections, so the entries genuinely age at different
        # rates.
        self.floors: dict[str, LastGood] = {}
        #: address -> ERC-721 ``name()``.  Immutable per contract, never expires.
        self.collection_names: dict[str, str] = {}
        #: address -> (verified ENS name, verification timestamp).
        self.ens_names: dict[str, tuple[str, float]] = {}
        #: address -> when we last confirmed it has *no* ENS name.
        self.ens_misses: dict[str, float] = {}

        # Hourly series, 7d deep: name -> deque[(hour_ts, value)].
        self.series: dict[str, deque[tuple[float, float]]] = {
            name: deque(maxlen=_HOURLY_HISTORY_HOURS) for name in SERIES_NAMES
        }

        # Per-event-type log tail watermarks (WP-7).
        self.last_seen_block: dict[str, int] = {}

        # Sweep invalidation bookkeeping (rule 8).
        self.sweep_invalidations: int = 0
        self.last_invalidation_reason: str = ""

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _now(self, now: float | None = None) -> float:
        return float(self._clock()) if now is None else float(now)

    # ------------------------------------------------------------------
    # Tier TTLs
    # ------------------------------------------------------------------

    @staticmethod
    def _check_tier(tier: str) -> str:
        if tier not in TIER_TTL_SECONDS:
            raise ValueError(
                f"unknown FWA refresh tier {tier!r}; expected one of {TIERS}"
            )
        return tier

    def is_fresh(self, tier: str, now: float | None = None) -> bool:
        """``True`` while ``tier``'s TTL has not elapsed (i.e. do not fetch)."""
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        if due_at is None:
            return False
        return self._now(now) < due_at

    def is_due(self, tier: str, now: float | None = None) -> bool:
        """Inverse of :meth:`is_fresh` — the question the manager actually asks."""
        return not self.is_fresh(tier, now)

    def mark_fetched(self, tier: str, now: float | None = None) -> None:
        """Record a *successful* fetch of ``tier`` and restart its TTL."""
        self._check_tier(tier)
        ts = self._now(now)
        self._tier_last_fetch[tier] = ts
        ttl = TIER_TTL_SECONDS[tier]
        self._tier_next_due[tier] = math.inf if ttl is None else ts + ttl

    def mark_failed(
        self,
        tier: str,
        now: float | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Record a failed fetch: keep the last-good payload, space the retry.

        Deliberately does *not* mark the tier fetched — the data is still missing.
        It only stops the manager retrying a dead or rate-limited host on every
        tick (see :data:`TIER_FAILURE_BACKOFF_SECONDS`).
        """
        self._check_tier(tier)
        backoff = (
            TIER_FAILURE_BACKOFF_SECONDS[tier] if retry_after is None
            else float(retry_after)
        )
        self._tier_next_due[tier] = self._now(now) + max(0.0, backoff)

    def expire_tier(self, tier: str) -> None:
        """Make ``tier`` due on the next tick (used by sweep invalidation)."""
        self._check_tier(tier)
        self._tier_next_due.pop(tier, None)

    def tiers_due(self, now: float | None = None) -> tuple[str, ...]:
        """Every tier whose TTL has elapsed, in :data:`TIERS` order.

        This is the manager's single question. Tier intervals are not restated
        anywhere outside this module.
        """
        ts = self._now(now)
        return tuple(t for t in TIERS if not self.is_fresh(t, ts))

    def seconds_until_due(self, tier: str, now: float | None = None) -> float:
        """Seconds until ``tier`` may be fetched again (``0.0`` when due)."""
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        if due_at is None:
            return 0.0
        if due_at == math.inf:
            return math.inf
        return max(0.0, due_at - self._now(now))

    def last_fetch_ts(self, tier: str) -> float | None:
        """Wall-clock time of the last successful fetch of ``tier``."""
        self._check_tier(tier)
        return self._tier_last_fetch.get(tier)

    # ------------------------------------------------------------------
    # Last-good snapshots — generic
    # ------------------------------------------------------------------

    def store_last_good(
        self,
        slot: str,
        payload: Any,
        *,
        ts: float | None = None,
        block: int | None = None,
        stale: bool = False,
        stale_reason: str = "",
    ) -> LastGood:
        """Replace ``slot``'s last-good payload. Always stamped with a timestamp."""
        entry = LastGood(
            payload=payload,
            ts=self._now(ts),
            block=None if block is None else int(block),
            stale=stale,
            stale_reason=stale_reason,
        )
        self.last_good[slot] = entry
        return entry

    def get_last_good(self, slot: str) -> LastGood | None:
        """Return ``slot``'s last-good entry, or ``None`` if nothing succeeded yet."""
        return self.last_good.get(slot)

    def age_of(self, slot: str, now: float | None = None) -> float | None:
        """Age in seconds of ``slot``'s payload, or ``None`` when there is none."""
        entry = self.last_good.get(slot)
        if entry is None:
            return None
        return entry.age_seconds(self._now(now))

    def as_of_ts(self, slot: str) -> float | None:
        """``slot``'s timestamp — feeds ``feed_as_of_ts`` / ``settle_as_of_ts``."""
        entry = self.last_good.get(slot)
        return None if entry is None else entry.ts

    # ------------------------------------------------------------------
    # Last-good snapshots — Pool A hot batch (fast tier)
    # ------------------------------------------------------------------

    def set_hot_batch(
        self,
        payload: Mapping[str, Any],
        *,
        ts: float | None = None,
        block: int | None = None,
    ) -> LastGood:
        """Store the last-good 15 s hot batch (fee, pool temp, VRF queue, crown)."""
        return self.store_last_good(
            SLOT_HOT_BATCH, dict(payload), ts=ts, block=block
        )

    def get_hot_batch(self) -> LastGood | None:
        return self.last_good.get(SLOT_HOT_BATCH)

    # ------------------------------------------------------------------
    # Last-good snapshots — Pool A position sweep (medium tier, block-pinned)
    # ------------------------------------------------------------------

    def set_sweep(
        self,
        block_number: int,
        positions: Sequence[Position],
        *,
        invariants_ok: bool = True,
        ts: float | None = None,
    ) -> bool:
        """Store a *whole* block-pinned position sweep. Returns ``True`` if stored.

        The entire sweep is replaced atomically — there is no way to add a single
        position, because a cache able to stitch positions read at different blocks
        reintroduces the silent corruption block-pinning exists to prevent
        (PRD §7 rule 11).

        Refused, with a warning and no state change:

        * an **unpinned** sweep (``block_number <= 0``) — it cannot be labelled,
          so it cannot be trusted;
        * a sweep pinned to a block **older** than the stored one — publishing it
          would walk the odds board backwards.

        ``invariants_ok=False`` still stores the sweep (the manager needs
        *something* to render) but flags it stale, so the odds board and EV render
        stale rather than wrong.
        """
        block = int(block_number)
        if block <= 0:
            logger.warning(
                "Refusing an unpinned FWA position sweep (block=%s); "
                "every sweep must be block-pinned (rule 11)",
                block_number,
            )
            return False

        current = self.last_good.get(SLOT_SWEEP)
        if current is not None and current.block is not None and block < current.block:
            logger.warning(
                "Refusing FWA sweep at block %d: cache already holds block %d "
                "(sweeps are never merged or rewound across blocks)",
                block,
                current.block,
            )
            return False

        self.store_last_good(
            SLOT_SWEEP,
            tuple(positions),
            ts=ts,
            block=block,
            stale=not invariants_ok,
            stale_reason="" if invariants_ok else "invariant mismatch",
        )
        return True

    def get_sweep(self) -> LastGood | None:
        """The last-good sweep. ``payload`` is a tuple of :class:`Position`."""
        return self.last_good.get(SLOT_SWEEP)

    @property
    def sweep_block(self) -> int | None:
        entry = self.last_good.get(SLOT_SWEEP)
        return None if entry is None else entry.block

    @property
    def sweep_stale(self) -> bool:
        """``True`` when there is no sweep at all, or the stored one is stale."""
        entry = self.last_good.get(SLOT_SWEEP)
        return True if entry is None else entry.stale

    def invalidate_sweep(self, reason: str) -> bool:
        """Flag the cached sweep stale and make the medium tier due immediately.

        Called on ``BackingUpdated`` (rule 8) or an invariant mismatch. The payload
        is kept — a stale sweep labelled stale is still better than a blank board —
        but nothing downstream may present it as current.
        """
        self.sweep_invalidations += 1
        self.last_invalidation_reason = str(reason)
        self.expire_tier(TIER_MEDIUM)
        entry = self.last_good.get(SLOT_SWEEP)
        if entry is None:
            return False
        if entry.stale and entry.stale_reason == reason:
            return True
        self.last_good[SLOT_SWEEP] = replace(
            entry, stale=True, stale_reason=str(reason)
        )
        return True

    def note_backing_updated(self, block_number: int) -> bool:
        """Handle a ``BackingUpdated`` event; returns ``True`` if it invalidated.

        Backing is mutable, so an update at a block *after* the pinned sweep means
        the cached backing — and therefore the harmonic mean and the flagship EV —
        is wrong. Events at or before the swept block are already reflected in it
        and are ignored, which is what keeps WP-7's one-time full-history backfill
        from invalidating every sweep it replays.
        """
        block = int(block_number)
        entry = self.last_good.get(SLOT_SWEEP)
        if entry is None:
            return False
        if entry.block is not None and block <= entry.block:
            return False
        return self.invalidate_sweep(f"BackingUpdated at block {block}")

    def note_invariant_mismatch(self, detail: str = "") -> bool:
        """Handle a runtime aggregate-invariant failure (rule 11)."""
        reason = "invariant mismatch" + (f": {detail}" if detail else "")
        return self.invalidate_sweep(reason)

    # ------------------------------------------------------------------
    # Last-good snapshots — Pool B log aggregates (the single point of failure)
    # ------------------------------------------------------------------

    def set_log_aggregates(
        self,
        payload: Mapping[str, Any],
        *,
        ts: float | None = None,
        block: int | None = None,
    ) -> LastGood:
        """Store the last-good log-derived aggregates.

        Draw events, settlement mix and crown history. When Pool B is down this is
        what the activity feed and crown history render, behind an explicit
        ``as of HH:MM`` marker — never blank, and never presented as live.
        """
        return self.store_last_good(SLOT_LOGS, dict(payload), ts=ts, block=block)

    def get_log_aggregates(self) -> LastGood | None:
        return self.last_good.get(SLOT_LOGS)

    # ------------------------------------------------------------------
    # Last-good snapshots — Pool C market data and floors
    # ------------------------------------------------------------------

    def set_market(
        self, payload: Mapping[str, Any], *, ts: float | None = None
    ) -> LastGood:
        """Store the last-good DexScreener / GeckoTerminal / DefiLlama payload."""
        return self.store_last_good(SLOT_MARKET, dict(payload), ts=ts)

    def get_market(self) -> LastGood | None:
        return self.last_good.get(SLOT_MARKET)

    def set_floor(
        self,
        address: str,
        floor_eth: float | None,
        *,
        source: str = "coingecko",
        note: str = "",
        ts: float | None = None,
    ) -> LastGood:
        """Store one collection's last-good floor, with its own timestamp.

        Floors arrive one collection at a time, seconds apart, and only some of
        the collections are ever priced — 26 of 38 on the last live sweep, and
        that is a measurement, not a constant. Each entry therefore ages
        independently. ``floor_eth=None`` with a ``source`` of
        ``"missing"`` or ``"suppressed"`` is a legitimate cached answer: it records
        that the floor is *known to be unavailable*, which is not the same as never
        having asked.
        """
        addr = str(address).lower()
        entry = LastGood(
            payload={
                "floor_eth": None if floor_eth is None else float(floor_eth),
                "source": str(source),
                "note": str(note),
            },
            ts=self._now(ts),
        )
        self.floors[addr] = entry
        return entry

    def get_floor(self, address: str) -> LastGood | None:
        """Last-good floor entry for one collection, or ``None``."""
        return self.floors.get(str(address).lower())

    def floors_snapshot(self) -> dict[str, LastGood]:
        """Shallow copy of every cached floor, keyed by lower-case address."""
        return dict(self.floors)

    def floor_age_seconds(
        self, address: str, now: float | None = None
    ) -> float | None:
        entry = self.get_floor(address)
        if entry is None:
            return None
        return entry.age_seconds(self._now(now))

    # ------------------------------------------------------------------
    # Display names — collection ``name()`` and verified ENS
    # ------------------------------------------------------------------

    def set_collection_names(self, names: Mapping[str, str]) -> None:
        """Merge on-chain collection names into the cache.

        A deployed ERC-721's ``name()`` is fixed for the life of the contract,
        so these never expire and are merged, never replaced: a batch where a
        few sub-calls failed must not delete the names we already had.
        """
        for addr, name in (names or {}).items():
            key = str(addr).lower()
            text = str(name or "").strip()
            if key and text:
                self.collection_names[key] = text

    def get_collection_name(self, address: str) -> str | None:
        return self.collection_names.get(str(address).lower())

    def collection_names_snapshot(self) -> dict[str, str]:
        return dict(self.collection_names)

    def set_ens_names(
        self, names: Mapping[str, str], *, ts: float | None = None
    ) -> None:
        """Store verified ENS names with the time they were verified.

        Unlike collection names these *do* expire -- a name can be transferred
        or allowed to lapse, and continuing to label an address with someone
        else's former name is worse than showing the hex.  A resolution that
        returns nothing for an address is not recorded, so an RPC failure never
        erases a good name; :meth:`ens_names_fresh` ages entries out instead.
        """
        stamp = self._now(ts)
        for addr, name in (names or {}).items():
            key = str(addr).lower()
            text = str(name or "").strip()
            if key and text:
                self.ens_names[key] = (text, stamp)

    def ens_names_fresh(
        self, ttl_seconds: float, now: float | None = None
    ) -> dict[str, str]:
        """Every cached ENS name still within *ttl_seconds*."""
        cutoff = self._now(now) - float(ttl_seconds)
        return {
            addr: name
            for addr, (name, ts) in self.ens_names.items()
            if ts >= cutoff
        }

    def note_ens_misses(
        self, addresses: Iterable[str], *, ts: float | None = None
    ) -> None:
        """Record addresses that resolved to no name.

        Most wallets have no ENS record -- 36 of 50 in the live feed.  Without
        this, every one of them is re-queried on every tick, because "absent
        from the name map" and "never asked" look identical.  That is four
        multicalls of pure waste per refresh against public endpoints, forever.

        A miss is *not* stored as an empty name: an address that later
        registers a name must be able to pick it up, so misses carry their own
        shorter TTL and expire independently.
        """
        stamp = self._now(ts)
        for addr in addresses or ():
            key = str(addr or "").lower()
            if key:
                self.ens_misses[key] = stamp

    def ens_misses_fresh(
        self, ttl_seconds: float, now: float | None = None
    ) -> set[str]:
        """Addresses known to have no ENS name, still within *ttl_seconds*."""
        cutoff = self._now(now) - float(ttl_seconds)
        return {addr for addr, ts in self.ens_misses.items() if ts >= cutoff}

    # ------------------------------------------------------------------
    # Last-good snapshots — once tier (params, allowlist, token metadata)
    # ------------------------------------------------------------------

    def set_startup(
        self, payload: Mapping[str, Any], *, ts: float | None = None
    ) -> LastGood:
        """Store the once-tier payload: config params, allowlist, token metadata."""
        return self.store_last_good(SLOT_STARTUP, dict(payload), ts=ts)

    def get_startup(self) -> LastGood | None:
        return self.last_good.get(SLOT_STARTUP)

    # ------------------------------------------------------------------
    # Hourly series
    # ------------------------------------------------------------------

    def _bucket_into(self, name: str, now_ts: float, value: float) -> None:
        """Write ``value`` into ``name``'s current hour bucket (overwrite in-hour)."""
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(val):
            return
        deq = self.series.get(name)
        if deq is None:
            return
        bucket = _hour_bucket(now_ts)
        if deq and deq[-1][0] == bucket:
            deq[-1] = (bucket, val)
        else:
            deq.append((bucket, val))

    def sample_series(
        self,
        now_ts: float,
        *,
        fwa_price_usd: float | None = None,
        acquisition_fee_eth: float | None = None,
        active_positions: int | None = None,
        crown_pot_eth: float | None = None,
    ) -> None:
        """Bucket this cycle's values into the hourly series.

        ``None`` means "no value this cycle" and leaves the series untouched — a
        dead source must not punch a zero into a sparkline. Multiple samples inside
        one hour overwrite that hour's bucket rather than appending, exactly like
        ``talismans_cache.sample_distribution``.
        """
        if fwa_price_usd is not None:
            self._bucket_into(SERIES_FWA_PRICE_USD, now_ts, fwa_price_usd)
        if acquisition_fee_eth is not None:
            self._bucket_into(SERIES_ACQUISITION_FEE_ETH, now_ts, acquisition_fee_eth)
        if active_positions is not None:
            self._bucket_into(SERIES_ACTIVE_POSITIONS, now_ts, active_positions)
        if crown_pot_eth is not None:
            self._bucket_into(SERIES_CROWN_POT_ETH, now_ts, crown_pot_eth)

    def get_series(self, name: str) -> list[list[float]]:
        """Return ``[[hour_ts, value], ...]`` oldest first — the sparkline shape."""
        deq = self.series.get(name)
        if not deq:
            return []
        return [[float(ts), float(v)] for (ts, v) in deq]

    # ------------------------------------------------------------------
    # Log tail watermarks
    # ------------------------------------------------------------------

    def update_last_seen_block(self, event_type: str, block_number: int) -> None:
        """Advance one event type's tail watermark. Monotonic — never rewinds."""
        try:
            block = int(block_number)
        except (TypeError, ValueError):
            return
        key = str(event_type)
        if block > self.last_seen_block.get(key, 0):
            self.last_seen_block[key] = block

    def get_last_seen_block(self, event_type: str, default: int = 0) -> int:
        return int(self.last_seen_block.get(str(event_type), default))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _sweep_provenance(self) -> dict[str, Any] | None:
        """Block/timestamp of the last sweep — the positions themselves never go."""
        entry = self.last_good.get(SLOT_SWEEP)
        if entry is None:
            return None
        payload = entry.payload
        try:
            count = len(payload)  # type: ignore[arg-type]
        except TypeError:
            count = 0
        return {
            "ts": float(entry.ts),
            "block": None if entry.block is None else int(entry.block),
            "positions": int(count),
            "stale_reason": entry.stale_reason,
        }

    def save_to_file(self, path: str = DEFAULT_CACHE_PATH) -> None:
        """Persist to disk via atomic temp-then-rename. Never raises."""
        payload: dict[str, Any] = {
            "version": _SCHEMA_VERSION,
            "saved_at": self._now(),
            "last_good": {
                slot: self.last_good[slot].to_dict()
                for slot in _PERSISTED_SLOTS
                if slot in self.last_good
            },
            "sweep_provenance": self._sweep_provenance(),
            "floors": {
                addr: entry.to_dict() for addr, entry in self.floors.items()
            },
            "collection_names": dict(self.collection_names),
            "ens_names": {
                addr: [name, float(ts)]
                for addr, (name, ts) in self.ens_names.items()
            },
            "ens_misses": {a: float(t) for a, t in self.ens_misses.items()},
            "series": {
                name: [[float(ts), float(v)] for (ts, v) in deq]
                for name, deq in self.series.items()
            },
            "last_seen_block": dict(self.last_seen_block),
            # Only the once tier's mark survives a restart: re-running the ~58 s
            # full-history backfill on every launch would be wasteful, and its
            # payload is persisted alongside it. Every other tier must be due
            # immediately after a restart.
            "once_fetched_at": self._tier_last_fetch.get(TIER_ONCE),
            "sweep_invalidations": int(self.sweep_invalidations),
        }
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, path)
            logger.info(
                "FWA cache saved to %s (%d last-good slots, %d floors)",
                path,
                len(payload["last_good"]),
                len(self.floors),
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to save FWA cache: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def load_from_file(self, path: str = DEFAULT_CACHE_PATH) -> None:
        """Load saved state. Silent no-op on a missing or corrupt file.

        Per-section ``try``/``except``: one bad block never costs the others, and
        nothing here ever raises into the manager's constructor.

        Series points are validated one by one, so a ``null``, a string, a
        ``NaN``, a negative value or a future-dated timestamp costs only
        that sample instead of the whole series -- and the drop is logged
        rather than swallowed.
        """
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.info("No FWA cache to load (%s): %s", path, exc)
            return
        if not isinstance(payload, dict):
            logger.warning("FWA cache %s has unexpected shape, skipping", path)
            return

        # Last-good slots (never the sweep's positions).
        try:
            for slot, data in (payload.get("last_good") or {}).items():
                if slot not in _PERSISTED_SLOTS or not isinstance(data, dict):
                    continue
                try:
                    self.last_good[str(slot)] = LastGood.from_dict(data)
                except Exception as exc:
                    logger.debug("Skipping bad last-good slot %s: %s", slot, exc)
        except Exception as exc:
            logger.warning("last_good block bad: %s", exc)

        # Sweep provenance only — restored already flagged stale, because the
        # positions are gone and the block belongs to a previous process.
        try:
            prov = payload.get("sweep_provenance")
            if isinstance(prov, dict) and prov.get("block"):
                self.last_good[SLOT_SWEEP] = LastGood(
                    payload=(),
                    ts=float(prov.get("ts") or 0.0),
                    block=int(prov["block"]),
                    stale=True,
                    stale_reason="restored from disk — positions are not persisted",
                )
        except Exception as exc:
            logger.warning("sweep_provenance block bad: %s", exc)

        # Floors.
        try:
            for addr, data in (payload.get("floors") or {}).items():
                if not isinstance(data, dict):
                    continue
                try:
                    self.floors[str(addr).lower()] = LastGood.from_dict(data)
                except Exception as exc:
                    logger.debug("Skipping bad floor %s: %s", addr, exc)
        except Exception as exc:
            logger.warning("floors block bad: %s", exc)

        # Display names.  Both blocks are per-entry guarded: one malformed row
        # in a hand-edited or half-written cache must not cost every name.
        try:
            for addr, name in (payload.get("collection_names") or {}).items():
                if isinstance(name, str) and name.strip():
                    self.collection_names[str(addr).lower()] = name.strip()
        except Exception as exc:
            logger.warning("collection_names block bad: %s", exc)

        try:
            for addr, entry in (payload.get("ens_names") or {}).items():
                try:
                    name, ts = entry
                    if isinstance(name, str) and name.strip():
                        self.ens_names[str(addr).lower()] = (name.strip(), float(ts))
                except Exception as exc:
                    logger.debug("Skipping bad ENS entry %s: %s", addr, exc)
        except Exception as exc:
            logger.warning("ens_names block bad: %s", exc)

        try:
            for addr, ts in (payload.get("ens_misses") or {}).items():
                try:
                    self.ens_misses[str(addr).lower()] = float(ts)
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("ens_misses block bad: %s", exc)

        # Hourly series.
        try:
            now = self._now()
            skipped = 0
            for name, points in (payload.get("series") or {}).items():
                deq = self.series.get(str(name))
                if deq is None:
                    continue
                good, dropped = coerce_points(points, now=now)
                skipped += dropped
                deq.clear()
                deq.extend(good)
            if skipped:
                logger.warning(
                    "Skipped %d unusable point(s) while loading FWA cache %s",
                    skipped,
                    path,
                )
        except Exception as exc:
            logger.warning("series block bad: %s", exc)

        # Tail watermarks.
        try:
            for key, val in (payload.get("last_seen_block") or {}).items():
                try:
                    self.update_last_seen_block(str(key), int(val))
                except (TypeError, ValueError):
                    continue
        except Exception as exc:
            logger.warning("last_seen_block block bad: %s", exc)

        # Counters.
        try:
            self.sweep_invalidations = int(payload.get("sweep_invalidations") or 0)
        except (TypeError, ValueError):
            self.sweep_invalidations = 0

        # The once tier's mark is only honoured when its payload came back with
        # it; otherwise the startup work has to run again, and skipping it would
        # leave the allowlist and config params permanently empty.
        try:
            once_ts = payload.get("once_fetched_at")
            if once_ts is not None and SLOT_STARTUP in self.last_good:
                self._tier_last_fetch[TIER_ONCE] = float(once_ts)
                self._tier_next_due[TIER_ONCE] = math.inf
        except (TypeError, ValueError) as exc:
            logger.warning("once_fetched_at bad: %s", exc)

        logger.info(
            "Loaded FWA cache from %s: %d last-good slots, %d floors, "
            "%d watermarks, sweep block %s",
            path,
            len(self.last_good),
            len(self.floors),
            len(self.last_seen_block),
            self.sweep_block,
        )


__all__ = [
    "DEFAULT_CACHE_PATH",
    "FWACache",
    "LastGood",
    "SERIES_ACQUISITION_FEE_ETH",
    "SERIES_ACTIVE_POSITIONS",
    "SERIES_CROWN_POT_ETH",
    "SERIES_FWA_PRICE_USD",
    "SERIES_NAMES",
    "SLOT_HOT_BATCH",
    "SLOT_LOGS",
    "SLOT_MARKET",
    "SLOT_STARTUP",
    "SLOT_SWEEP",
    "TIERS",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_MEDIUM",
    "TIER_ONCE",
    "TIER_SLOW",
    "TIER_TAIL",
    "TIER_TTL_SECONDS",
]
