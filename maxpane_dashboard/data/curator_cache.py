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

#: Bumped only when a *shape* changes.  A file whose version is absent, older or
#: newer loads **nothing** rather than being half-understood: a
#: partially-understood schema is not safer than an empty cache, and this file
#: has no legacy readers to be kind to.
_SCHEMA_VERSION = 1

#: Longest history either series keeps: 30 days of hourly points.  The game may
#: outlive that (H15); the oldest points are dropped, never the newest.
MAX_SERIES_POINTS = 720

#: Wei per ETH.  The **only** division site outside
#: ``analytics.curator_signals``: the series are persisted in the presentation
#: unit the sparklines render, and dividing twice is how a number silently
#: becomes 1e-18 of itself.
_WEI = 10**18


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


# ---------------------------------------------------------------------------
# The two persisted series (CURATOR_SERIES_KEYS)
# ---------------------------------------------------------------------------

SERIES_VOLUME = "volume_series"
SERIES_CONTRIBUTORS = "contributors_series"

SERIES_NAMES: tuple[str, ...] = (SERIES_VOLUME, SERIES_CONTRIBUTORS)

#: The *inputs* the series writers consume, named so the manager's disjointness
#: test (H2) can assert against them rather than reason about them.  Neither is
#: a state reading, and neither can become one without this tuple changing.
SERIES_INPUT_KEYS: tuple[str, ...] = ("buckets", "contributor_total")


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
        #: ``{series name: {bucket start ts: value}}``.  A dict rather than a
        #: deque because every cycle re-records the whole folded history: an
        #: upsert keyed by the bucket's own wall clock is idempotent, keeps the
        #: series ascending and can never grow a duplicate hour.
        self._series: dict[str, dict[float, float]] = {
            name: {} for name in SERIES_NAMES
        }

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

    # -- series --------------------------------------------------------------

    @staticmethod
    def _check_series(name: str) -> str:
        if name not in SERIES_NAMES:
            raise ValueError(
                f"unknown curator series {name!r}; expected one of {SERIES_NAMES}"
            )
        return name

    def get_series(self, name: str) -> list[list[float]]:
        """``[[bucket_ts, value], …]`` oldest first — the sparkline shape.

        Bounded to the newest :data:`MAX_SERIES_POINTS`; the values are already
        in presentation units (ETH for volume, a count for contributors), so
        nothing downstream divides again.
        """
        self._check_series(name)
        points = sorted(self._series[name].items())
        return [[float(ts), float(value)] for ts, value in points[-MAX_SERIES_POINTS:]]

    # -- persistence ---------------------------------------------------------

    def _payload(self) -> dict[str, Any]:
        return {
            "version": _SCHEMA_VERSION,
            "saved_at": self._now(),
            "last_good": {
                slot: entry.to_dict() for slot, entry in self.last_good.items()
            },
            "series": {name: self.get_series(name) for name in SERIES_NAMES},
        }

    def save(self, path: str | None = None) -> None:
        """Persist to disk via atomic temp-then-rename.  Never raises.

        Temp + rename, so a kill mid-write leaves the previous file intact: a
        half-written JSON document is a cache that loads nothing, and the fold
        it holds is the whole leaderboard.

        The tier marks are deliberately **not** persisted.  After a restart
        every tier is due, because the chain moved while the process was down
        and the one number this dashboard exists to be current about is an hour
        deadline.
        """
        target = str(path or self.path)
        tmp = target + ".tmp"
        try:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._payload(), handle)
            os.replace(tmp, target)
            logger.info(
                "Curator cache saved to %s (%d last-good slot(s))",
                target,
                len(self.last_good),
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to save the curator cache: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def load(self, path: str | None = None, *, now: float | None = None) -> None:
        """Restore saved state.  Silent no-op on a missing or corrupt file.

        Per-section ``try``/``except``: one bad block never costs the others and
        nothing here raises into the manager's constructor.  Series points are
        validated one at a time through
        :func:`~maxpane_dashboard.data.series_points.coerce_points`, so a single
        ``null`` costs that sample rather than every dashboard's startup — the
        bug that once aborted MaxPane for users who owned no curator cache at
        all.
        """
        target = str(path or self.path)
        try:
            with open(target, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.info("No curator cache to load (%s): %s", target, exc)
            return
        if not isinstance(payload, dict):
            logger.warning("Curator cache %s has an unexpected shape, skipping", target)
            return

        version = payload.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != _SCHEMA_VERSION:
            # Absent, older or newer: all three are "written by something whose
            # shapes this reader has not agreed with".  Loading nothing is the
            # same degradation every corrupt file gets, and it is honest —
            # guessing at a section whose shape may have moved is how a fold
            # comes back subtly wrong with no symptom.
            logger.warning(
                "Curator cache %s carries schema %r, not %r — loading nothing",
                target,
                version,
                _SCHEMA_VERSION,
            )
            return

        reference = self._now(now)

        try:
            for slot, data in (payload.get("last_good") or {}).items():
                if slot not in SLOTS or not isinstance(data, dict):
                    continue
                try:
                    self.last_good[str(slot)] = LastGood.from_dict(data, now=reference)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Skipping bad curator last-good slot %s: %s", slot, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator last_good block bad: %s", exc)

        try:
            dropped_total = 0
            for name, raw in (payload.get("series") or {}).items():
                if name not in SERIES_NAMES:
                    continue
                good, dropped = coerce_points(raw, now=reference)
                dropped_total += dropped
                self._series[str(name)] = {float(ts): float(v) for ts, v in good}
            if dropped_total:
                logger.warning(
                    "Skipped %d unusable point(s) while loading the curator cache %s",
                    dropped_total,
                    target,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator series block bad: %s", exc)

        logger.info(
            "Loaded the curator cache from %s: %d last-good slot(s), %d volume point(s)",
            target,
            len(self.last_good),
            len(self._series[SERIES_VOLUME]),
        )


__all__ = [
    "MAX_SERIES_POINTS",
    "SERIES_CONTRIBUTORS",
    "SERIES_INPUT_KEYS",
    "SERIES_NAMES",
    "SERIES_VOLUME",
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
