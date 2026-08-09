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


__all__ = [
    "DEFAULT_CACHE_PATH",
    "LastGood",
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
