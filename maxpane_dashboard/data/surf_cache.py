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


__all__ = [
    "DEFAULT_CACHE_PATH",
    "SurfCache",
    "TIERS",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_MEDIUM",
    "TIER_SLOW",
    "TIER_TTL_SECONDS",
]
