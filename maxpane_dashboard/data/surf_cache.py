"""Tiered cache, last-good snapshots, series and signal baselines for SURF (WP4).

This module owns *when* :class:`~maxpane_dashboard.data.surf_manager.SurfManager`
is allowed to fetch, *what it may show when a fetch fails*, and *what state
survives a restart*. It holds no clients, does no I/O other than reading and
writing its own JSON file, and imports nothing from the project except the
dependency-free :mod:`maxpane_dashboard.data.series_points` leaf.

Three refresh tiers, sized from PRD §5:

``fast``    every refresh (TTL 0). Three ``eth_getTransactionCount`` reads plus
            one batched ``eth_call`` round. The announce channel emits **no
            logs**, so nonce polling is the only detector that exists for it and
            the whole "how early am I" claim rests on it running every tick.
``medium``  90 s. ``eth_getLogs`` windows, GeckoTerminal/DexScreener, and the
            Blockscout channel bodies — the last only when the nonce moved.
``slow``    420 s. Blockscout counters/holders and the dev tx pages.

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

TIERS: tuple[str, ...] = (TIER_FAST, TIER_MEDIUM, TIER_SLOW)

TIER_TTL_SECONDS: dict[str, float] = {
    TIER_FAST: 0.0,       # every refresh — see the module docstring
    TIER_MEDIUM: 90.0,    # PRD §5 says 60-120 s
    TIER_SLOW: 420.0,     # PRD §5 says 5-10 min
}

TIER_FAILURE_BACKOFF_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 120.0,
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

SLOTS: tuple[str, ...] = (
    SLOT_CHAIN,
    SLOT_CHANNEL,
    SLOT_MARKET,
    SLOT_LOGS,
    SLOT_NFT,
    SLOT_ACTIVITY,
)


# ---------------------------------------------------------------------------
# Hourly series (7 days deep)
# ---------------------------------------------------------------------------

SERIES_IMD_SUPPLY = "imd_supply"
SERIES_IMD_PRICE_USD = "imd_price_usd"
SERIES_PARITY_PCT = "parity_pct"

SERIES_NAMES: tuple[str, ...] = (
    SERIES_IMD_SUPPLY,
    SERIES_IMD_PRICE_USD,
    SERIES_PARITY_PCT,
)

#: Parity is a *spread* (IMD vs FP) and is legitimately below zero — the live
#: capture is -2.75%. Supply and price cannot be, and a negative one is corruption.
SERIES_ALLOW_NEGATIVE: dict[str, bool] = {
    SERIES_IMD_SUPPLY: False,
    SERIES_IMD_PRICE_USD: False,
    SERIES_PARITY_PCT: True,
}


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
    def from_dict(cls, data: Mapping[str, Any]) -> "LastGood":
        return cls(payload=data.get("payload"), ts=float(data.get("ts") or 0.0))


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


__all__ = [
    "BASELINE_DETAIL_CAP",
    "BASELINE_FIRED_KEY",
    "BASELINE_LIST_CAP",
    "DEFAULT_CACHE_PATH",
    "LastGood",
    "SERIES_ALLOW_NEGATIVE",
    "SERIES_IMD_PRICE_USD",
    "SERIES_IMD_SUPPLY",
    "SERIES_NAMES",
    "SERIES_PARITY_PCT",
    "SLOTS",
    "SLOT_ACTIVITY",
    "SLOT_CHAIN",
    "SLOT_CHANNEL",
    "SLOT_LOGS",
    "SLOT_MARKET",
    "SLOT_NFT",
    "SurfCache",
    "TIERS",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_MEDIUM",
    "TIER_SLOW",
    "TIER_TTL_SECONDS",
]
