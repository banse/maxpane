"""Tiered cache, last-good snapshots, series and signal baselines for SURF (WP4).

This module owns *when* :class:`~maxpane_dashboard.data.surf_manager.SurfManager`
is allowed to fetch, *what it may show when a fetch fails*, and *what state
survives a restart*. It holds no clients, does no I/O other than reading and
writing its own JSON file, and imports nothing from the project except the
dependency-free :mod:`maxpane_dashboard.data.series_points` leaf.

Four refresh tiers, the first three sized from PRD §5:

``fast``        every refresh (TTL 0). Three ``eth_getTransactionCount`` reads
                plus one batched ``eth_call`` round. The announce channel
                emits **no logs**, so nonce polling is the only detector that
                exists for it and the whole "how early am I" claim rests on
                it running every tick.
``medium``      90 s. ``eth_getLogs`` windows, GeckoTerminal/DexScreener, and
                the Blockscout channel bodies — the last only when the nonce
                moved.
``slow``        420 s. Blockscout counters/holders and the dev tx pages.
``launchpad``   600 s, on the curator ``TIER_ANALYSIS`` precedent: a slower
                clock than the title bar's for a detached factory/hook/executor
                and log-aggregate sweep, so its panels carry their own
                `as of HH:MM` and a slow sweep can never block first paint.
``pool4``       600 s, the same shape one layer out: discovery plus three
                getter rounds plus a log window over the pool4 hook, detached,
                with its own ``as of HH:MM``.

The pool4 reserve is **two series, one per network**, and that is the single
least obvious thing in this module. ``pool4`` reads Sepolia until a mainnet
hook is discovered and adopted, so one series would splice a testnet history
onto a mainnet one at the switchover and draw a single sparkline across two
different chains — a line whose left half is a different token on a different
network from its right half, with nothing on screen saying so. The series a
payload publishes is chosen by the network the numbers came from, and neither
series is ever written by the other's readings.

A failure never marks a tier fetched; it only spaces the retry
(:data:`TIER_FAILURE_BACKOFF_SECONDS`), so a rate-limited host is not hammered
while the last-good payload covers the gap.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.series_points import (
    CLOCK_SKEW_TOLERANCE_SECONDS,
    coerce_points,
)

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = str(Path.home() / ".maxpane" / "surf_cache.json")

_SCHEMA_VERSION = 1
_HISTORY_HOURS = 168          # 7 days of hourly buckets

# ---------------------------------------------------------------------------
# Refresh tiers (PRD §5)
# ---------------------------------------------------------------------------

TIER_FAST = "fast"
TIER_MEDIUM = "medium"
TIER_SLOW = "slow"

#: The launchpad / decoy-pool sweep. Its own long tier — modelled on curator's
#: ``TIER_ANALYSIS`` — so the launchpad panels carry an `as of HH:MM` on a
#: slower clock than the title bar's, deliberately. Task 6 hangs a detached
#: sweep off this tier so it cannot block first paint.
TIER_LAUNCHPAD = "launchpad"

#: The pool4 sweep — discovery off the channel rows the manager already has,
#: then the hook / dripper / vault getter rounds and one log window. Its own
#: long tier for ``TIER_LAUNCHPAD``'s reason and no other: the panels behind it
#: carry an ``as of HH:MM`` on a slower clock than the title bar's, on purpose,
#: and the sweep behind it is detached so it can never block first paint.
#:
#: 600 s rather than curator's 1800: this is a handful of ``eth_call`` rounds
#: and a ~24 h log window on one contract, the same order of work as the
#: launchpad sweep and two orders below curator's 8.3 MB published-analysis
#: read. The failure backoff is deliberately much shorter than the TTL — a
#: rate-limited Sepolia endpoint must not cost the panel a full ten minutes.
TIER_POOL4 = "pool4"

TIERS: tuple[str, ...] = (
    TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_LAUNCHPAD, TIER_POOL4,
)

TIER_TTL_SECONDS: dict[str, float] = {
    TIER_FAST: 0.0,       # every refresh — see the module docstring
    TIER_MEDIUM: 90.0,    # PRD §5 says 60-120 s
    TIER_SLOW: 420.0,     # PRD §5 says 5-10 min
    TIER_LAUNCHPAD: 600.0,
    TIER_POOL4: 600.0,
}

TIER_FAILURE_BACKOFF_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 120.0,
    TIER_LAUNCHPAD: 180.0,
    TIER_POOL4: 180.0,
}


# ---------------------------------------------------------------------------
# Last-good slots — one per independently failing source group (PRD §5 meta)
# ---------------------------------------------------------------------------

SLOT_CHAIN = "chain"          # state RPC: nonces + the batched eth_call round
SLOT_CHANNEL = "channel"      # Blockscout channel bodies
SLOT_MARKET = "market"        # GeckoTerminal / DexScreener / CoinGecko
SLOT_LOGS = "logs"            # logs RPC pool (mints, identity writes, v4, Seaport)
SLOT_NFT = "nft"              # Blockscout token counters / holders
SLOT_ACTIVITY = "activity"    # Blockscout dev tx pages
SLOT_LAUNCHPAD = "launchpad"  # factory/hook/executor getters + log aggregates
SLOT_POOL4 = "pool4"          # discovery + hook/vault/dripper getters + flow logs

SLOTS: tuple[str, ...] = (
    SLOT_CHAIN,
    SLOT_CHANNEL,
    SLOT_MARKET,
    SLOT_LOGS,
    SLOT_NFT,
    SLOT_ACTIVITY,
    SLOT_LAUNCHPAD,
    SLOT_POOL4,
)


# ---------------------------------------------------------------------------
# Hourly series (7 days deep)
# ---------------------------------------------------------------------------

SERIES_IMD_SUPPLY = "imd_supply"
SERIES_IMD_PRICE_USD = "imd_price_usd"
SERIES_PARITY_PCT = "parity_pct"

#: The pool4 reserve, **one series per network**. See the module docstring:
#: a single series splices a Sepolia history onto a mainnet one the moment a
#: mainnet hook is adopted, and draws one sparkline across two chains.
SERIES_POOL4_RESERVE_SEPOLIA = "pool4_reserve_sepolia"
SERIES_POOL4_RESERVE_MAINNET = "pool4_reserve_mainnet"

SERIES_NAMES: tuple[str, ...] = (
    SERIES_IMD_SUPPLY,
    SERIES_IMD_PRICE_USD,
    SERIES_PARITY_PCT,
    SERIES_POOL4_RESERVE_SEPOLIA,
    SERIES_POOL4_RESERVE_MAINNET,
)

#: Parity is a *spread* (IMD vs FP) and is legitimately below zero — the live
#: capture is -2.75%. Supply and price cannot be, and a negative one is corruption.
#: The pool4 reserve is a token balance held by a pool: it cannot be negative
#: either. (``pool4_floor_distance`` *can* be, and legitimately is on launch 1 —
#: but that is a derived difference published per cycle, never a stored series.)
SERIES_ALLOW_NEGATIVE: dict[str, bool] = {
    SERIES_IMD_SUPPLY: False,
    SERIES_IMD_PRICE_USD: False,
    SERIES_PARITY_PCT: True,
    SERIES_POOL4_RESERVE_SEPOLIA: False,
    SERIES_POOL4_RESERVE_MAINNET: False,
}

#: pool4 network word -> the reserve series it owns.
#:
#: The two words are **restated here rather than imported** from
#: ``surf_models.POOL4_NETWORKS``, on this repo's redundancy-plus-an-agreement-
#: test pattern (``_GAME_CYCLE``, the ``--game`` choices, the pool4 widgets'
#: own ``NETWORK_WORDS`` — amendment A24). ``tests/data/test_surf_cache_pool4``
#: imports the contract's tuple and asserts set-and-length equality with these
#: keys; deriving them here would make that test compare a constant against
#: itself and it could never fail again. It also keeps this module's standing
#: promise that it imports nothing from the project but the ``series_points``
#: leaf.
POOL4_RESERVE_SERIES: dict[str, str] = {
    "SEPOLIA": SERIES_POOL4_RESERVE_SEPOLIA,
    "MAINNET": SERIES_POOL4_RESERVE_MAINNET,
}


def pool4_reserve_series_name(network: Any) -> str | None:
    """The series ``network``'s reserve readings belong in, or ``None``.

    ``None`` for ``None`` (no sweep has ever completed) *and* for a word
    outside the closed vocabulary — a producer bug, not a new chain, and the
    one thing that must never happen is a reading landing in the wrong
    network's history because a spelling was accepted loosely.
    """
    if not isinstance(network, str):
        return None
    return POOL4_RESERVE_SERIES.get(network)


def _hour_bucket(ts: float) -> float:
    return float(int(ts // 3600) * 3600)


@dataclass(frozen=True)
class LastGood:
    """One source group's last *successful* payload with the time it arrived.

    ``ts`` is mandatory: it is what lets a widget render ``as of HH:MM`` instead
    of implying the value is live. A :class:`LastGood` never exists without it.
    """

    payload: Any
    ts: float

    def age_seconds(self, now: float) -> float:
        return max(0.0, float(now) - float(self.ts))

    def as_of_hhmm(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.ts))

    def to_dict(self) -> dict[str, Any]:
        return {"payload": _jsonable(self.payload), "ts": float(self.ts)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, now: float) -> "LastGood":
        """Rebuild one persisted slot, refusing an unusable or future-dated ``ts``.

        ``ts`` is documented above as mandatory, so a missing, non-positive or
        non-finite one is **dropped** (raises, caught by the per-slot loop in
        ``load()``) rather than defaulted to ``0.0`` -- a sentinel here would
        silently claim an as-of time the file never held. A ``ts`` more than
        :data:`CLOCK_SKEW_TOLERANCE_SECONDS` in the future is exactly what a
        skewed or hand-edited clock produces; keeping it would let
        :meth:`age_seconds` clamp to ``0.0`` forever, rendering a dead source
        as permanently live (CLAUDE.md) -- precisely what a last-good slot
        exists to prevent.
        """
        try:
            ts = float(data.get("ts"))
        except (TypeError, ValueError):
            raise ValueError("SURF last-good entry has no usable ts") from None
        if not math.isfinite(ts) or ts <= 0.0 or ts > now + CLOCK_SKEW_TOLERANCE_SECONDS:
            raise ValueError(f"unusable SURF last-good ts {ts!r}")
        return cls(payload=data.get("payload"), ts=ts)


class _Drop:
    """Sentinel: this value is not usable and must be dropped, never coerced."""

    __slots__ = ()

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return "<drop>"


_DROP = _Drop()


def _jsonable(value: Any, _depth: int = 0) -> Any:
    """Best-effort conversion of a cached payload to JSON-safe primitives.

    Non-finite floats become ``None`` and unknown objects are dropped rather
    than coerced — fabricating a value on the way to disk is worse than losing
    it.
    """
    if _depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return [_jsonable(v, _depth + 1) for v in value]
    logger.debug("Dropping non-serialisable %s from the SURF cache", type(value).__name__)
    return None


# ---------------------------------------------------------------------------
# Signal baselines (PRD §3)
# ---------------------------------------------------------------------------

#: Nested map inside the baselines dict: signal name -> ``{"ts": epoch seconds,
#: "detail": the rendered line}`` of its last FIRED. Persisted so a restart
#: neither resurrects nor loses a FIRED display; whether an entry still
#: *renders* FIRED is ``build_signals``' call, not this module's.
#:
#: The spelling is ``build_signals``' own (``advanced["fired"]``). It is not a
#: free choice: this cache is schema-agnostic, so a key that does not match
#: routes the whole store down the generic scalar branch, where a mapping is
#: dropped — the FIRED map would then be silently discarded every cycle.
BASELINE_FIRED_KEY = "fired"

#: Longest list a baseline value may be (seen tx hashes and the like).
BASELINE_LIST_CAP = 64

#: Longest FIRED ``detail`` string kept. Deliberately far above WP2's
#: ``DETAIL_LIMIT`` (48): that one caps the quoted *message body*, while a
#: rendered detail wraps it in a label, quotes and a ``· last: …`` clause. This
#: bound exists to stop an unbounded third-party string reaching the cache
#: file, not to reformat the line a restart re-renders.
BASELINE_DETAIL_CAP = 200


class SurfCache:
    """Tiered TTLs, last-good store, series and baselines for one SURF process.

    Single-threaded asyncio access, no locking, matching the rest of the repo.
    ``clock`` is injectable and every time-taking method also accepts an explicit
    ``now=`` so tests drive expiry without sleeping.
    """

    def __init__(
        self,
        path: str = DEFAULT_CACHE_PATH,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = str(path)
        self._clock = clock
        self._tier_last_fetch: dict[str, float] = {}
        self._tier_next_due: dict[str, float] = {}
        self.last_good: dict[str, LastGood] = {}
        self.series: dict[str, deque[tuple[float, float]]] = {
            name: deque(maxlen=_HISTORY_HOURS) for name in SERIES_NAMES
        }
        self._baselines: dict[str, Any] = {}
        self.last_supply: float | None = None
        self.burned_cum: float = 0.0
        self._last_supply_block: int | None = None
        # Set by ``load()`` when a restored ``last_supply`` came back with no
        # trustworthy block watermark to compare it against (the field was
        # absent -- an older cache file -- or failed to parse). See
        # ``record_supply`` for why this is not the same as "no watermark
        # yet": a fresh, never-loaded cache has ``last_supply is None`` too,
        # and the ordinary "first read only establishes the baseline" path
        # already handles that case without this flag.
        self._supply_block_unverified: bool = False
        #: pool4's running counter totals, keyed by the same series name the
        #: reserve history uses -- one per network, for the same reason.
        self._pool4_accumulators: dict[str, dict[str, Any]] = {}

    # -- clock ---------------------------------------------------------------

    def _now(self, now: float | None = None) -> float:
        return float(self._clock()) if now is None else float(now)

    # -- tiers ---------------------------------------------------------------

    @staticmethod
    def _check_tier(tier: str) -> str:
        if tier not in TIER_TTL_SECONDS:
            raise ValueError(
                f"unknown SURF refresh tier {tier!r}; expected one of {TIERS}"
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
        return not self.is_fresh(tier, now)

    def tiers_due(self, now: float | None = None) -> tuple[str, ...]:
        """Every tier whose TTL has elapsed, in :data:`TIERS` order."""
        ts = self._now(now)
        return tuple(t for t in TIERS if not self.is_fresh(t, ts))

    def mark_fetched(self, tier: str, now: float | None = None) -> None:
        """Record a *successful* fetch of ``tier`` and restart its TTL."""
        self._check_tier(tier)
        ts = self._now(now)
        self._tier_last_fetch[tier] = ts
        self._tier_next_due[tier] = ts + TIER_TTL_SECONDS[tier]

    def mark_failed(
        self,
        tier: str,
        now: float | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Record a failed fetch: keep the last-good payload, space the retry."""
        self._check_tier(tier)
        backoff = (
            TIER_FAILURE_BACKOFF_SECONDS[tier]
            if retry_after is None
            else float(retry_after)
        )
        self._tier_next_due[tier] = self._now(now) + max(0.0, backoff)

    def seconds_until_due(self, tier: str, now: float | None = None) -> float:
        self._check_tier(tier)
        due_at = self._tier_next_due.get(tier)
        if due_at is None:
            return 0.0
        return max(0.0, due_at - self._now(now))

    def last_fetch_ts(self, tier: str) -> float | None:
        self._check_tier(tier)
        return self._tier_last_fetch.get(tier)

    # -- last-good snapshots -------------------------------------------------

    @staticmethod
    def _check_slot(slot: str) -> str:
        if slot not in SLOTS:
            raise ValueError(f"unknown SURF slot {slot!r}; expected one of {SLOTS}")
        return slot

    def store_last_good(
        self, slot: str, payload: Any, *, ts: float | None = None
    ) -> LastGood:
        """Replace ``slot``'s last-good payload. Always stamped with a timestamp.

        ``payload=None`` is refused: it means *no successful read happened*, and
        storing it would overwrite a good payload (and its provenance) with an
        indistinguishable outage. Falsy-but-real readings (``[]``, ``0``, ``""``,
        ``{}``) are accepted without complaint -- an empty result is a fact about
        the world, not a missing one, and rejecting it would recreate the exact
        "outage vs. genuine zero" conflation this cache exists to prevent.
        """
        self._check_slot(slot)
        if payload is None:
            raise ValueError(
                f"store_last_good({slot!r}, None) refused: None means no read "
                "happened, not an empty result -- it must never overwrite a "
                "good last-good payload"
            )
        entry = LastGood(payload=payload, ts=self._now(ts))
        self.last_good[slot] = entry
        return entry

    def get_last_good(self, slot: str) -> LastGood | None:
        return self.last_good.get(slot)

    def as_of_ts(self, slot: str) -> float | None:
        entry = self.last_good.get(slot)
        return None if entry is None else entry.ts

    def age_of(self, slot: str, now: float | None = None) -> float | None:
        entry = self.last_good.get(slot)
        return None if entry is None else entry.age_seconds(self._now(now))

    def newest_as_of(self) -> float | None:
        """Timestamp of the freshest successful read across every slot."""
        stamps = [e.ts for e in self.last_good.values()]
        return max(stamps) if stamps else None

    # -- series --------------------------------------------------------------

    def _bucket_into(self, name: str, now_ts: float, value: Any) -> None:
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(val):
            return
        if val < 0 and not SERIES_ALLOW_NEGATIVE.get(name, False):
            return
        deq = self.series.get(name)
        if deq is None:
            return
        bucket = _hour_bucket(float(now_ts))
        if not deq or bucket > deq[-1][0]:
            deq.append((bucket, val))
            return
        if deq[-1][0] == bucket:
            deq[-1] = (bucket, val)
            return
        # Out-of-order sample (a backward clock step, or -- once WP4.6 lands --
        # a fresh reading interleaving with points reloaded from disk): merge
        # it in place rather than blindly appending. The sparkline renders a
        # step down as an on-chain burn, so a misordered or duplicated bucket
        # would draw a dip that never happened (CLAUDE.md). Two invariants
        # hold after every call: ``get_series`` stays ascending by timestamp,
        # and no hour ever appears twice.
        points = list(deq)
        idx = bisect.bisect_left([p[0] for p in points], bucket)
        if idx < len(points) and points[idx][0] == bucket:
            points[idx] = (bucket, val)          # same last-wins policy, in place
        else:
            points.insert(idx, (bucket, val))
        self.series[name] = deque(points, maxlen=deq.maxlen)

    def sample_series(
        self,
        now_ts: float,
        *,
        imd_supply: float | None = None,
        imd_price_usd: float | None = None,
        parity_pct: float | None = None,
    ) -> None:
        """Bucket this cycle's values. ``None`` leaves the series untouched.

        A dead source must never write a sentinel into a history series
        (CLAUDE.md): the zero would be persisted and outlive the outage.
        """
        if imd_supply is not None:
            self._bucket_into(SERIES_IMD_SUPPLY, now_ts, imd_supply)
        if imd_price_usd is not None:
            self._bucket_into(SERIES_IMD_PRICE_USD, now_ts, imd_price_usd)
        if parity_pct is not None:
            self._bucket_into(SERIES_PARITY_PCT, now_ts, parity_pct)

    def get_series(self, name: str) -> list[list[float]]:
        """``[[hour_ts, value], ...]`` oldest first — the sparkline shape."""
        deq = self.series.get(name)
        if not deq:
            return []
        return [[float(ts), float(v)] for (ts, v) in deq]

    # -- pool4's two network-namespaced reserve series ------------------------

    def sample_pool4_reserve(
        self, now_ts: float, reserve_imd: float | None, *, network: Any
    ) -> None:
        """Bucket one reserve reading into ``network``'s own series.

        ``None`` leaves **both** series untouched, and so does an unrecognised
        network. Two separate refusals, one rule: a dead read must never write
        a sentinel into a history (CLAUDE.md — the zero is persisted and
        outlives the outage it came from), and a reading whose provenance is
        not a known network has no history it belongs in. Falling back to
        "whichever series we used last" is precisely the splice the two series
        exist to prevent.
        """
        if reserve_imd is None:
            return
        name = pool4_reserve_series_name(network)
        if name is None:
            return
        self._bucket_into(name, now_ts, reserve_imd)

    def fold_pool4_reserve_history(
        self, points: Any, *, network: Any
    ) -> int:
        """Merge log-derived ``[[ts, imd], …]`` points into ``network``'s series.

        The pool's own reserve event carries a timestamp, so a first sweep can
        back-fill hours the cache was not running for instead of drawing a
        one-point sparkline. Every point is a real measured reserve at a real
        block time; nothing here invents one, and ``_bucket_into``'s existing
        out-of-order merge keeps the series ascending with no hour twice.

        Returns the number of points actually folded, so a caller (and a test)
        can tell "the window was quiet" from "the points were unusable".
        ``None`` in — the read failed — folds nothing, like every other
        sentinel guard in this class.
        """
        name = pool4_reserve_series_name(network)
        if name is None or not points:
            return 0
        folded = 0
        for point in points:
            try:
                ts, value = point[0], point[1]
            except (TypeError, IndexError, KeyError):
                continue
            try:
                ts = float(ts)
                value = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(ts) or not math.isfinite(value) or ts <= 0:
                continue
            self._bucket_into(name, ts, value)
            folded += 1
        return folded

    # -- pool4's counter accumulator, also network-namespaced ---------------

    def get_pool4_accumulator(self, network: Any) -> dict[str, Any] | None:
        """``network``'s running counter total, or ``None``.

        ``None`` for an unrecognised network, for the same reason the reserve
        series refuses one: a total accumulated on one chain reconciled against
        another chain's counters is not a weaker check, it is a wrong one.
        A network with no accumulator yet answers ``None`` too -- the caller
        seeds it, because what an unseeded accumulator *is* belongs to the
        module that owns the arithmetic, not to this one.
        """
        name = pool4_reserve_series_name(network)
        if name is None:
            return None
        acc = self._pool4_accumulators.get(name)
        return dict(acc) if isinstance(acc, dict) else None

    def set_pool4_accumulator(self, network: Any, accumulator: Any) -> None:
        """Replace ``network``'s running total. Unknown network: refused."""
        name = pool4_reserve_series_name(network)
        if name is None or not isinstance(accumulator, Mapping):
            return
        self._pool4_accumulators[name] = dict(accumulator)

    @staticmethod
    def _coerce_accumulator(raw: Any) -> dict[str, Any] | None:
        """One persisted accumulator, structurally validated, or ``None``.

        **This is cache-supplied evidence and the validation is why that is
        tolerable.** A hand-edited accumulator could in principle silence the
        counter control or fabricate an alarm, and nothing here can recompute
        two months of sums to find out. Two things bound it, and neither is
        this method:

        * the **alignment** invariant. A forged total is only believed while
          its ``cursor_block`` equals the block the counters were just read at,
          which is a live chain read the forger cannot predict. A stale forgery
          reads ``window-limited``, so a forgery has to be rewritten in lockstep
          with the chain to keep working. It perishes on its own.
        * a discarded accumulator is *safe*: it falls back to single-window
          behaviour, which is the honest ``window-limited``.

        What this does is refuse anything structurally wrong -- a missing or
        non-integer block, a negative or non-integer sum, a stray key -- so a
        malformed file costs the accumulator rather than the startup, on
        ``coerce_points``' precedent.
        """
        if not isinstance(raw, Mapping):
            return None
        genesis = raw.get("genesis_block")
        cursor = raw.get("cursor_block")
        if not isinstance(genesis, int) or isinstance(genesis, bool):
            return None
        if not isinstance(cursor, int) or isinstance(cursor, bool):
            return None
        if genesis < 0 or cursor < genesis:
            return None
        sums = raw.get("sums")
        if not isinstance(sums, Mapping):
            return None
        clean: dict[str, int] = {}
        for key, value in sums.items():
            if not isinstance(key, str):
                return None
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return None
            clean[key] = value
        return {
            "genesis_block": genesis,
            "cursor_block": cursor,
            "sums": clean,
        }

    def get_pool4_reserve_series(self, network: Any) -> list[list[float]] | None:
        """``network``'s reserve history, or ``None`` when there is no network.

        ``None`` and ``[]`` are different claims and the RATCHET panel renders
        them differently: ``None`` is "no sweep has ever completed, so we
        cannot even say which chain this would be about", ``[]`` is "that
        chain's history is empty so far".
        """
        name = pool4_reserve_series_name(network)
        if name is None:
            return None
        return self.get_series(name)

    # -- observed burns --------------------------------------------------------

    def record_supply(
        self, supply: float | None, block_number: int | None = None
    ) -> float | None:
        """Fold one ``totalSupply`` reading in. Returns the burn observed, if any.

        ``None`` in -> ``None`` out and **no state change**: a failed read must be
        incapable of producing a BURN (PRD §6.1). The first successful read only
        establishes the baseline, so it also concludes nothing. A numeric
        *string* is likewise not a reading -- the contract is ``float | None``,
        not "anything ``float()`` tolerates" -- so it is rejected the same way.

        ``block_number``, when supplied, is the block the reading was taken at
        (``ChainState.block_number``, fetched in the same batched call as the
        supply itself). A reading whose block does not strictly advance past
        the last one folded in is treated as a stale replica, not a bridge-in
        or a burn: public RPC pools are load-balanced across nodes that do not
        all see the same head, so an older replica answering after a fresher
        one is routine, not exotic. Such a reading changes **nothing** --
        neither the supply baseline nor the block watermark -- so a later
        in-order reading is still compared against the correct baseline
        instead of one a stale read displaced. Omitting ``block_number``
        (``None``, the default) skips this check entirely and falls back to
        the original value-only behaviour, for any caller that does not yet
        have a block number to offer.
        """
        if supply is None or isinstance(supply, (bool, str)):
            return None
        try:
            value = float(supply)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0:
            return None

        if block_number is not None:
            try:
                block = int(block_number)
            except (TypeError, ValueError):
                return None
            if self._supply_block_unverified:
                # A restart restored ``last_supply`` but not a trustworthy
                # block watermark (missing or corrupt on disk -- see
                # ``load()``). Comparing this reading against that value
                # would be the exact bug this watermark exists to prevent: a
                # stale replica answering first would look "in order" against
                # an absent watermark and get folded in as a burn or a
                # bridge-in. Instead, treat this reading as the new reference
                # point outright and conclude nothing from it, exactly like
                # the very first observation of a fresh cache.
                self._last_supply_block = block
                self._supply_block_unverified = False
                self.last_supply = value
                return None
            if self._last_supply_block is not None and block <= self._last_supply_block:
                # Stale replica: this block was already superseded by one
                # folded in earlier. Ignore it outright -- do not let it
                # re-baseline the accumulator or displace the watermark.
                return None
            self._last_supply_block = block

        previous = self.last_supply
        self.last_supply = value
        if previous is None:
            return None
        if value < previous:
            delta = previous - value
            self.burned_cum += delta
            return delta
        # An increase is an OFT bridge-in, not a negative burn.
        return 0.0

    def observed_burn_total(self) -> float | None:
        """Cumulative burn *since first observation*, or ``None`` if never read.

        Not an all-time total and not obtainable as one: the burns predating
        this cache (~58,849 IMD across 2026-05-16 / 07-31 / 08-05) have no
        keyless source.  ``0.0`` therefore means "nothing observed in the
        window", never "nothing was ever burned" -- consumers must render the
        two differently (see WP3.2 ``SurfHero._update_supply``).
        """
        if self.last_supply is None:
            return None
        return float(self.burned_cum)

    # -- signal baselines ----------------------------------------------------

    @staticmethod
    def _scalar(value: Any) -> Any:
        """A JSON-safe scalar, or the sentinel ``_DROP`` when unusable."""
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else _DROP
        return _DROP

    @staticmethod
    def _sanitise_fired(raw: Any, horizon: float) -> dict[str, dict[str, Any]]:
        """The ``{signal: {"ts", "detail"}}`` store, defensively rebuilt.

        Shape kept deliberately narrow — this is the one nested value the cache
        understands, and it understands it because ``build_signals`` writes it
        and reads it back. Anything that is not a two-field mapping with a
        usable stamp is **dropped**, never repaired: a resurrected FIRED is a
        false alarm and a coerced one is a lie about when it happened. Entries
        in the pre-repair flat shape (``{signal: float}``) land here too and are
        dropped by the same rule, which is the honest outcome — a stamp with no
        detail would restore as a FIRED row quoting nothing.
        """
        fired: dict[str, dict[str, Any]] = {}
        if not isinstance(raw, Mapping):
            return fired
        for sig, entry in raw.items():
            if not isinstance(entry, Mapping):
                logger.debug("Dropping malformed SURF fired entry %r", sig)
                continue
            try:
                stamp = float(entry.get("ts"))      # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            # A future-dated stamp is clock-skew corruption; keeping it would
            # pin the detector at FIRED forever.
            if not math.isfinite(stamp) or not 0.0 < stamp <= horizon:
                continue
            detail = entry.get("detail")
            text = "" if detail is None else str(detail)
            fired[str(sig)] = {"ts": stamp, "detail": text[:BASELINE_DETAIL_CAP]}
        return fired

    def _sanitise_baselines(self, raw: Any, now: float) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            logger.debug("Ignoring non-mapping SURF baselines: %r", type(raw).__name__)
            return {}
        out: dict[str, Any] = {}
        horizon = now + CLOCK_SKEW_TOLERANCE_SECONDS
        for key, value in raw.items():
            name = str(key)
            if name == BASELINE_FIRED_KEY:
                out[name] = self._sanitise_fired(value, horizon)
                continue
            if isinstance(value, (list, tuple)):
                items = [self._scalar(v) for v in list(value)[:BASELINE_LIST_CAP]]
                out[name] = [v for v in items if v is not _DROP]
                continue
            scalar = self._scalar(value)
            if scalar is _DROP:
                logger.debug("Dropping unusable SURF baseline %s=%r", name, value)
                continue
            out[name] = scalar
        return out

    def get_baselines(self) -> dict[str, Any]:
        """A **copy** of the persisted baselines, safe for a caller to mutate.

        The FIRED store is two levels deep, so the inner ``{"ts", "detail"}``
        dicts are copied too — a shallow copy would hand out live references and
        a caller editing a detail would rewrite what the next restart renders.
        """
        out = dict(self._baselines)
        fired = out.get(BASELINE_FIRED_KEY)
        if isinstance(fired, dict):
            out[BASELINE_FIRED_KEY] = {
                name: (dict(entry) if isinstance(entry, dict) else entry)
                for name, entry in fired.items()
            }
        return out

    def set_baselines(self, baselines: Mapping[str, Any], *, now: float | None = None) -> None:
        """Replace the baselines wholesale with ``build_signals``' advanced set.

        Wholesale, never merged: ``build_signals`` returns the *complete* advanced
        set, so merging would let a key it deliberately dropped come back.
        """
        self._baselines = self._sanitise_baselines(baselines, self._now(now))

    # -- persistence ---------------------------------------------------------

    def save(self, path: str | None = None) -> None:
        """Persist to disk via atomic temp-then-rename. Never raises.

        The tier marks are deliberately **not** persisted: after a restart every
        tier is due, because the chain moved while the process was down and the
        announce nonce is the one number the dashboard exists to be early on.
        """
        target = str(path or self.path)
        payload: dict[str, Any] = {
            "version": _SCHEMA_VERSION,
            "saved_at": self._now(),
            "last_good": {
                slot: entry.to_dict() for slot, entry in self.last_good.items()
            },
            "series": {
                name: [[float(ts), float(v)] for (ts, v) in deq]
                for name, deq in self.series.items()
            },
            "baselines": _jsonable(self._baselines),
            "burned_cum": float(self.burned_cum),
            "last_supply": None if self.last_supply is None else float(self.last_supply),
            "last_supply_block": (
                None if self._last_supply_block is None else int(self._last_supply_block)
            ),
            # Kept out of the pool4 last-good slot on purpose: it must advance
            # on every successful sweep, including one whose payload did not
            # change, and it must never enter that slot's content comparison --
            # a cursor that moves every block would make every tick look like
            # new data and the ``as of`` marker would advance for ever.
            "pool4_accumulators": _jsonable(self._pool4_accumulators),
        }
        tmp = target + ".tmp"
        try:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(tmp, "w") as handle:
                json.dump(payload, handle)
            os.replace(tmp, target)
            logger.info(
                "SURF cache saved to %s (%d last-good slots, burned %.0f observed)",
                target,
                len(self.last_good),
                self.burned_cum,
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to save the SURF cache: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def load(self, path: str | None = None, *, now: float | None = None) -> None:
        """Restore saved state. Silent no-op on a missing or corrupt file.

        Per-section ``try``/``except``: one bad block never costs the others, and
        nothing here raises into the manager's constructor. Series points are
        validated one at a time, so a single ``null`` costs that sample rather
        than every dashboard's startup.
        """
        target = str(path or self.path)
        try:
            with open(target) as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.info("No SURF cache to load (%s): %s", target, exc)
            return
        if not isinstance(payload, dict):
            logger.warning("SURF cache %s has an unexpected shape, skipping", target)
            return
        version = payload.get("version")
        if isinstance(version, int) and not isinstance(version, bool) and version > _SCHEMA_VERSION:
            # Written by a newer MaxPane than this one understands. Refusing
            # the whole file (rather than best-effort parsing sections whose
            # shape may have changed) is the same "start fresh" degradation
            # every other corrupt-shape case gets -- a partially-understood
            # future schema is not safer than an empty cache. A *missing*
            # version (every file this code has ever written until now, plus
            # any hand-crafted fixture) is treated as schema 1 and loads
            # normally, so this is additive, not a new failure mode.
            logger.warning(
                "SURF cache %s is from a newer schema (%s > %s), skipping",
                target, version, _SCHEMA_VERSION,
            )
            return

        reference = self._now(now)

        try:
            for slot, data in (payload.get("last_good") or {}).items():
                if slot not in SLOTS or not isinstance(data, dict):
                    continue
                try:
                    self.last_good[str(slot)] = LastGood.from_dict(data, now=reference)
                except Exception as exc:            # noqa: BLE001
                    logger.debug("Skipping bad SURF last-good slot %s: %s", slot, exc)
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF last_good block bad: %s", exc)

        try:
            skipped = 0
            for name, points in (payload.get("series") or {}).items():
                deq = self.series.get(str(name))
                if deq is None:
                    continue
                good, dropped = coerce_points(
                    points,
                    now=reference,
                    allow_negative=SERIES_ALLOW_NEGATIVE.get(str(name), False),
                )
                skipped += dropped
                deq.clear()
                deq.extend(good)
            if skipped:
                logger.warning(
                    "Skipped %d unusable point(s) while loading the SURF cache %s",
                    skipped,
                    target,
                )
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF series block bad: %s", exc)

        try:
            self._baselines = self._sanitise_baselines(
                payload.get("baselines"), reference
            )
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF baselines block bad: %s", exc)
            self._baselines = {}

        try:
            burned = float(payload.get("burned_cum") or 0.0)
            self.burned_cum = burned if math.isfinite(burned) and burned >= 0 else 0.0
        except (TypeError, ValueError):
            self.burned_cum = 0.0

        try:
            supply = payload.get("last_supply")
            value = None if supply is None else float(supply)
            self.last_supply = (
                value if value is not None and math.isfinite(value) and value >= 0
                else None
            )
        except (TypeError, ValueError):
            self.last_supply = None

        # The block watermark that guards ``record_supply`` against a stale
        # RPC replica (see its docstring) must round-trip alongside
        # ``last_supply``, or the exact bug it fixes comes back on every
        # restart: a replica of an already-superseded block would look "in
        # order" against an absent watermark and get folded into burned_cum
        # a second time. A watermark that fails to load is not the same as
        # "no watermark was ever recorded" (a fresh cache) when a
        # ``last_supply`` DID come back -- that combination means the file
        # predates this field, or the field is corrupt, and it is flagged so
        # ``record_supply`` re-establishes the watermark from the next
        # reading instead of comparing against one it cannot verify.
        try:
            raw_block = payload.get("last_supply_block")
            self._last_supply_block = None if raw_block is None else int(raw_block)
        except (TypeError, ValueError):
            self._last_supply_block = None
        self._supply_block_unverified = (
            self._last_supply_block is None and self.last_supply is not None
        )

        try:
            self._pool4_accumulators = {}
            for name, raw in (payload.get("pool4_accumulators") or {}).items():
                if str(name) not in SERIES_NAMES:
                    continue
                clean = self._coerce_accumulator(raw)
                if clean is not None:
                    self._pool4_accumulators[str(name)] = clean
        except Exception as exc:                    # noqa: BLE001
            logger.warning("SURF pool4 accumulator block bad: %s", exc)
            self._pool4_accumulators = {}

        logger.info(
            "Loaded the SURF cache from %s: %d last-good slots, %d baselines",
            target,
            len(self.last_good),
            len(self._baselines),
        )


__all__ = [
    "BASELINE_DETAIL_CAP",
    "BASELINE_FIRED_KEY",
    "BASELINE_LIST_CAP",
    "DEFAULT_CACHE_PATH",
    "LastGood",
    "POOL4_RESERVE_SERIES",
    "SERIES_ALLOW_NEGATIVE",
    "SERIES_IMD_PRICE_USD",
    "SERIES_IMD_SUPPLY",
    "SERIES_NAMES",
    "SERIES_PARITY_PCT",
    "SERIES_POOL4_RESERVE_MAINNET",
    "SERIES_POOL4_RESERVE_SEPOLIA",
    "SLOTS",
    "SLOT_ACTIVITY",
    "SLOT_CHAIN",
    "SLOT_CHANNEL",
    "SLOT_LAUNCHPAD",
    "SLOT_LOGS",
    "SLOT_MARKET",
    "SLOT_NFT",
    "SLOT_POOL4",
    "SurfCache",
    "TIERS",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_LAUNCHPAD",
    "TIER_MEDIUM",
    "TIER_POOL4",
    "TIER_SLOW",
    "TIER_TTL_SECONDS",
    "pool4_reserve_series_name",
]
