"""Tiered cache, last-good slots, folds, series and evidence for THE LIST.

This module owns *when*
:class:`~maxpane_dashboard.data.curator_manager.CuratorManager` may fetch,
*what it may show when a fetch fails*, and *what survives a restart*.  It holds
no client, does no I/O beyond its own JSON file, and imports nothing from the
project except the dependency-free
:mod:`maxpane_dashboard.data.series_points` leaf and the frozen
:mod:`maxpane_dashboard.data.curator_models` dataclasses.

Four refresh tiers, sized from PRD §5:

``fast``    15 s.  One batched ``eth_call`` round, ``eth_getBalance`` and — only
            when a wallet is configured — the six YOU views.
``medium``  60 s.  Incremental ``eth_getLogs`` from the watermark + 1, folded.
``slow``    420 s.  The Blockscout cross-check and gap repair.
``once``    ∞.  The immutables.  Nothing on this contract can change them, so
            this is a genuine forever cache rather than a long TTL.

A failure never marks a tier fetched; it only spaces the retry
(:data:`TIER_FAILURE_BACKOFF_SECONDS`), so a rate-limited host is not hammered
while the last-good payload covers the gap.

**The hour-boundary rule (H2) is structural here, not a convention.**  The
series writer takes *folded ``Deposited`` buckets* and there is deliberately no
parameter through which a state read could enter it: ``currentHourTotal()``
legitimately reads ``0`` at every hour boundary while ``lastActiveHour()`` still
names the previous bucket, and a series fed from that view records the boundary
as a 99.5% crash — 9987.26 → 51.48 ETH across 2026-08-16 21:58:47 UTC, captured
in ``hour_boundary_h1_h2.json``.  The zero would then be *persisted*, so the
corruption outlives the boundary that produced it.

**The settlement latch (H1)** lives here for the same reason: ``isSettled()`` is
the truth and the ``Settled`` event is only the obituary, so the first ``True``
observation is written down with its evidence and never re-read through.  A
later ``False`` or ``None`` is a bad read, a wrong endpoint or a fork — never a
resurrection.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections import deque
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.curator_models import SettlementRecord
from maxpane_dashboard.data.series_points import (
    CLOCK_SKEW_TOLERANCE_SECONDS,
    coerce_points,
)

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = str(Path.home() / ".maxpane" / "curator_cache.json")

#: Bumped only when a *shape* changes.  A file written by a newer MaxPane loads
#: nothing rather than being half-understood.
_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Refresh tiers (PRD §5)
# ---------------------------------------------------------------------------

TIER_FAST = "fast"
TIER_MEDIUM = "medium"
TIER_SLOW = "slow"
TIER_ONCE = "once"

TIERS: tuple[str, ...] = (TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_ONCE)

TIER_TTL_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 420.0,
    # The eight immutables plus POINTS_PER_ETH.  There is no owner power on
    # this contract that reaches a parameter, so a success here is final.
    TIER_ONCE: math.inf,
}

TIER_FAILURE_BACKOFF_SECONDS: dict[str, float] = {
    TIER_FAST: 15.0,
    TIER_MEDIUM: 60.0,
    TIER_SLOW: 120.0,
    # A *failed* once tier must come back: the immutables are unreadable, not
    # unchanging-and-known.  Its infinite TTL applies to success only.
    TIER_ONCE: 60.0,
}


# ---------------------------------------------------------------------------
# Last-good slots — one per independently failing source
# ---------------------------------------------------------------------------

SLOT_STATE = "state"            # the batched eth_call round + eth_getBalance
SLOT_LOGS = "logs"              # the eth_getLogs sweep, folded
SLOT_WALLET = "wallet"          # the six YOU views
SLOT_CONFIG = "config"          # the `once` immutables
SLOT_BLOCKSCOUT = "blockscout"  # the independent cross-check

SLOTS: tuple[str, ...] = (
    SLOT_STATE,
    SLOT_LOGS,
    SLOT_WALLET,
    SLOT_CONFIG,
    SLOT_BLOCKSCOUT,
)


class LastGood:
    """One source's last *successful* payload with the time it arrived.

    ``ts`` is mandatory: it is what lets the title bar render ``as of HH:MM``
    instead of implying the value is live.  A :class:`LastGood` never exists
    without one.
    """

    __slots__ = ("payload", "ts")

    def __init__(self, payload: Any, ts: float) -> None:
        self.payload = payload
        self.ts = float(ts)

    def age_seconds(self, now: float) -> float:
        return max(0.0, float(now) - self.ts)

    def as_of_hhmm(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.ts))

    def to_dict(self) -> dict[str, Any]:
        return {"payload": _jsonable(self.payload), "ts": float(self.ts)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, now: float) -> "LastGood":
        """Rebuild one persisted slot, refusing an unusable or future-dated ``ts``.

        A missing, non-positive or non-finite stamp raises (and the per-slot
        loop in :meth:`CuratorCache.load` drops the slot) rather than defaulting
        to ``0.0``: a sentinel here would claim an as-of time the file never
        held.  A stamp beyond :data:`CLOCK_SKEW_TOLERANCE_SECONDS` in the future
        is what a skewed or hand-edited clock produces, and keeping it would pin
        :meth:`age_seconds` at ``0.0`` forever — a dead source rendering as
        permanently live, which is precisely what a last-good slot exists to
        prevent.
        """
        try:
            ts = float(data.get("ts"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError("curator last-good entry has no usable ts") from None
        if not math.isfinite(ts) or ts <= 0.0 or ts > now + CLOCK_SKEW_TOLERANCE_SECONDS:
            raise ValueError(f"unusable curator last-good ts {ts!r}")
        return cls(payload=data.get("payload"), ts=ts)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LastGood ts={self.ts!r}>"


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
    logger.debug(
        "Dropping non-serialisable %s from the curator cache", type(value).__name__
    )
    return None


class CuratorCache:
    """Tiered TTLs, last-good store, folds, series and the settlement latch.

    Single-threaded asyncio access, no locking, matching the rest of the repo.
    ``clock`` is injectable and every time-taking method also accepts an
    explicit ``now=`` so tests drive expiry without sleeping.
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
                f"unknown curator refresh tier {tier!r}; expected one of {TIERS}"
            )
        return tier

    def is_fresh(self, tier: str, now: float | None = None) -> bool:
        """``True`` while ``tier``'s TTL has not elapsed (i.e. do not fetch).

        "Fresh" answers *whether to attempt a fetch* and nothing else:
        :meth:`mark_failed` advances the same clock, so a tier sitting out a
        failure backoff is "fresh" here while being anything but healthy.  The
        manager tracks health in its own ``_failed_groups``.
        """
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
        """Record a *successful* fetch of ``tier`` and restart its TTL.

        ``once`` restarts an infinite TTL, so a success there is permanent for
        the life of the process (and, once :meth:`save` has run, of the file).
        """
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
        """Record a failed fetch: keep the last-good payload, space the retry.

        Deliberately does **not** touch ``_tier_last_fetch``: a failure is not a
        fetch, and the ``once`` tier must come due again after a failure rather
        than inheriting success's infinite TTL.
        """
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
            raise ValueError(
                f"unknown curator slot {slot!r}; expected one of {SLOTS}"
            )
        return slot

    def store_last_good(
        self, slot: str, payload: Any, *, ts: float | None = None
    ) -> LastGood:
        """Replace ``slot``'s last-good payload.  Always stamped.

        ``payload=None`` is refused: it means *no successful read happened*, and
        storing it would overwrite a good payload — and its provenance — with an
        indistinguishable absence.  Falsy-but-real readings (``[]``, ``0``,
        ``""``, ``{}``) are accepted without complaint; an empty result is a
        fact about the world, not a missing one, and rejecting it would recreate
        the exact "outage vs. genuine zero" conflation this cache exists to
        prevent.
        """
        self._check_slot(slot)
        if payload is None:
            raise ValueError(
                f"store_last_good({slot!r}, None) refused: None means no read "
                "happened, not an empty result — it must never overwrite a good "
                "last-good payload"
            )
        entry = LastGood(payload=payload, ts=self._now(ts))
        self.last_good[slot] = entry
        return entry

    def get_last_good(self, slot: str) -> LastGood | None:
        self._check_slot(slot)
        return self.last_good.get(slot)

    def as_of_ts(self, slot: str) -> float | None:
        entry = self.get_last_good(slot)
        return None if entry is None else entry.ts

    def age_of(self, slot: str, now: float | None = None) -> float | None:
        entry = self.get_last_good(slot)
        return None if entry is None else entry.age_seconds(self._now(now))

    def newest_as_of(self) -> float | None:
        """Timestamp of the freshest successful read across every slot."""
        stamps = [entry.ts for entry in self.last_good.values()]
        return max(stamps) if stamps else None


__all__ = [
    "CuratorCache",
    "DEFAULT_CACHE_PATH",
    "LastGood",
    "SLOTS",
    "SLOT_BLOCKSCOUT",
    "SLOT_CONFIG",
    "SLOT_LOGS",
    "SLOT_STATE",
    "SLOT_WALLET",
    "TIERS",
    "TIER_FAILURE_BACKOFF_SECONDS",
    "TIER_FAST",
    "TIER_MEDIUM",
    "TIER_ONCE",
    "TIER_SLOW",
    "TIER_TTL_SECONDS",
]
