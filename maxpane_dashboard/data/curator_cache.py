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
parameter through which a state read could enter it — the live hour-total view
legitimately reads ``0`` at every hour boundary while the last-active-hour view
still names the previous bucket, and a series fed from it records the boundary
as a 99.5% crash (9987.26 → 51.48 ETH across 2026-08-16 21:58:47 UTC, captured
in ``hour_boundary_h1_h2.json``).  The zero would then be *persisted*, so the
corruption outlives the boundary that produced it.  The two banned spellings are
absent from this module by test, not by care.

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

from maxpane_dashboard.data.curator_models import (
    ContributorRow,
    DepositEvent,
    SettlementRecord,
)
from maxpane_dashboard.data import ens
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

#: Longest raw ``Deposited`` history kept on disk and in memory.  The fold, the
#: hour buckets, the clusters and the activity feed are all recomputed from it
#: every cycle, so a drop here is a leaderboard that is a *lower bound* rather
#: than a wrong number — and it is logged with its count so a truncated history
#: stays discoverable.  231 events landed in the first four hours of the game;
#: this holds roughly a hundred days at that pace.  Compaction of the folded
#: table is PRD §12 material, not v1 (H15).
MAX_PERSISTED_EVENTS = 25_000

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


def _stamp(value: Any) -> float | None:
    """A usable epoch-second timestamp, or ``None``.  Never a ``0``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    ts = float(value)
    if not math.isfinite(ts) or ts <= 0.0:
        return None
    return ts


def _opt_int(value: Any) -> int | None:
    """An ``int`` if the value is one, else ``None``.  ``bool`` is not one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float(value: Any) -> float | None:
    """A finite ``float`` if the value is a real number, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _pair(entry: Any) -> tuple[float, Any] | None:
    """One ``(timestamp, value)`` bucket, or ``None`` when it is not one."""
    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
        return None
    ts = _stamp(entry[0])
    if ts is None:
        return None
    return ts, entry[1]


#: Every ``DepositEvent`` field that must be an ``int`` for the row to be usable.
_EVENT_INT_FIELDS = (
    "hour",
    "amount_wei",
    "credited_delta_wei",
    "weight_added_wei",
    "new_weight_wei",
    "tx_count",
    "hour_total_wei",
    "early_bps",
    "block_number",
    "log_index",
)

#: The same for a folded ``ContributorRow``.  ``first_hour`` / ``first_index`` /
#: ``points`` are legitimately ``None`` and are validated separately.
_ROW_INT_FIELDS = ("weight_wei", "credit_wei", "tx_count")


def _event_key(event: Any) -> tuple[str, int] | None:
    """``(tx_hash, log_index)`` — the de-dupe key, or ``None`` if unusable."""
    tx_hash = getattr(event, "tx_hash", None)
    log_index = _opt_int(getattr(event, "log_index", None))
    if not isinstance(tx_hash, str) or not tx_hash or log_index is None:
        return None
    return tx_hash.lower(), log_index


def _event_to_dict(event: DepositEvent) -> dict[str, Any]:
    return {
        "contributor": event.contributor,
        "hour": event.hour,
        "amount_wei": event.amount_wei,
        "credited_delta_wei": event.credited_delta_wei,
        "weight_added_wei": event.weight_added_wei,
        "new_weight_wei": event.new_weight_wei,
        "tx_count": event.tx_count,
        "hour_total_wei": event.hour_total_wei,
        "early_bps": event.early_bps,
        "block_number": event.block_number,
        "tx_hash": event.tx_hash,
        "log_index": event.log_index,
        "ts": event.ts,
    }


def _event_from_dict(raw: Any) -> DepositEvent | None:
    """One persisted event, or ``None`` when a field is missing or wrong.

    Dropped, never repaired: a deposit with a defaulted amount is a wrong
    leaderboard row, and a wrong row is worse than a short table.  ``ts`` is the
    one field allowed to be absent — a missing stamp renders ``--:--``.
    """
    if not isinstance(raw, Mapping):
        return None
    if not isinstance(raw.get("contributor"), str):
        return None
    if not isinstance(raw.get("tx_hash"), str):
        return None
    values: dict[str, Any] = {}
    for field in _EVENT_INT_FIELDS:
        value = _opt_int(raw.get(field))
        if value is None:
            return None
        values[field] = value
    return DepositEvent(
        contributor=raw["contributor"],
        tx_hash=raw["tx_hash"],
        ts=_stamp(raw.get("ts")),
        **values,
    )


def _row_to_dict(row: ContributorRow) -> dict[str, Any]:
    return {
        "address": row.address,
        "weight_wei": row.weight_wei,
        "credit_wei": row.credit_wei,
        "tx_count": row.tx_count,
        "first_hour": row.first_hour,
        "first_index": row.first_index,
        "points": row.points,
    }


def _row_from_dict(raw: Any) -> ContributorRow | None:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("address"), str):
        return None
    values: dict[str, Any] = {}
    for field in _ROW_INT_FIELDS:
        value = _opt_int(raw.get(field))
        if value is None:
            return None
        values[field] = value
    return ContributorRow(
        address=raw["address"],
        first_hour=_opt_int(raw.get("first_hour")),
        first_index=_opt_int(raw.get("first_index")),
        points=_opt_int(raw.get("points")),
        **values,
    )


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
        #: The settlement latch: the first ``isSettled() == True`` observation
        #: with its evidence.  Once set, never re-read through and never
        #: cleared.
        self._settlement: SettlementRecord | None = None
        #: The ``Settled`` log's four words, filed whether or not the latch
        #: exists yet.  It is the obituary, not the verdict.
        self._obituary: dict[str, Any] = {}
        #: The raw decoded ``Deposited`` history, oldest first, de-duplicated on
        #: ``(tx_hash, log_index)``.  Kept because the sweep is *incremental*:
        #: after the first backfill the client only ever hands back the new
        #: rows, so this is the only place the rest of the game exists.
        self._events: list[DepositEvent] = []
        self._event_keys: set[tuple[str, int]] = set()
        #: How many events the cap has dropped from this cache — **persisted**,
        #: so it means the same thing after a relaunch as it does inside one
        #: process.  Surfaced so a truncated history is discoverable rather than
        #: silently short.
        #:
        #: It has to survive the file, because the manager's cross-check reads
        #: it (``seen = len(events()) + dropped_events``) to decide whether the
        #: fold is short against the contract's own counter, which never forgets.
        #: As a per-process counter it reset to 0 on every launch, so the first
        #: cross-check after a restart declared the fold short, scheduled a full
        #: re-sweep from the creation block, re-dropped the same overflow and
        #: published ``degraded`` — once per launch, forever, from the day the
        #: cap first trips.
        self.dropped_events: int = 0
        self._first_deposits: list[dict] = []
        self._hour_saved: list[dict] = []
        self._rescued_total_wei: int | None = None
        self._fold: list[ContributorRow] = []
        self._last_seen_block: int | None = None
        self._clusters: list[dict] = []
        #: Verified reverse-ENS names and known misses (:class:`ens.NameStore`).
        #: Shared implementation rather than a fourth private copy of the same
        #: TTL logic -- see that class for why a miss is not an empty name.
        self.ens = ens.NameStore(self._clock)

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

    def expire(self, tier: str) -> None:
        """Make ``tier`` due immediately, as if it had never been fetched.

        For a **configuration change that invalidates what the tier fetched** —
        today, the reader setting a different wallet, which makes the whole
        wallet half of the fast tier's answers belong to somebody else.  It is
        not the failure path: :meth:`mark_failed` owns those, and it *spaces*
        the retry where this one un-spaces it.  ``_tier_last_fetch`` is left
        alone for the same reason it is in ``mark_failed`` — expiring a tier is
        not a fetch, and ``as of`` provenance must keep pointing at the real
        one.
        """
        self._check_tier(tier)
        self._tier_next_due.pop(tier, None)

    def drop_last_good(self, slot: str) -> None:
        """Forget ``slot``'s last-good payload entirely.

        The counterpart to :meth:`expire`: when a payload stops being *about*
        the thing the reader is now looking at, serving it behind an
        ``as of HH:MM`` marker is worse than serving nothing, because the marker
        says "stale" while the number says "yours".  Idempotent — dropping an
        empty slot is not an error.
        """
        self._check_slot(slot)
        self.last_good.pop(slot, None)

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

    def record_hour_buckets(self, buckets: Any, *, now: float | None = None) -> int:
        """Fold this cycle's hourly volume into the persisted series.

        ``buckets`` is an iterable of ``(bucket_start_ts, volume_wei)`` pairs —
        the folded ``Deposited`` history, each hour already anchored to its own
        wall clock by ``analytics.curator_signals.bucket_start_ts``
        (``launchTime + hour × hourDuration``, exact by construction, no
        timestamp read required).  Returns the number of points written.

        **There is deliberately no other parameter.**  Not a state reading, not
        a "current hour total", not an override for the newest bucket: the
        signature itself is what makes H2 unviolatable, and
        ``test_the_series_writer_takes_folded_buckets_not_a_state_reading``
        asserts the parameter set exactly.  A live hour-total view drops to
        ``0`` at every boundary while the previous bucket is still the last
        active one; recording that reading would persist a crash that never
        happened.

        A **genuinely silent hour is a zero and is written**, which is why the
        rule is "from logs only" rather than "never write a zero": a judged hour
        that took in nothing is the most important point on the chart.

        Wei divides to ETH here, once — the same presentation boundary
        ``build_signals`` applies, so the two agree and nothing downstream
        divides again.
        """
        written = 0
        for entry in buckets or ():
            pair = _pair(entry)
            if pair is None:
                continue
            ts, wei = pair
            if isinstance(wei, bool) or not isinstance(wei, (int, float)):
                continue
            if wei < 0 or not math.isfinite(float(wei)):
                continue
            self._series[SERIES_VOLUME][ts] = float(wei) / _WEI
            written += 1
        self._trim(SERIES_VOLUME)
        return written

    def record_contributor_count(
        self, total: Any, *, ts: Any, now: float | None = None
    ) -> bool:
        """Record the cumulative contributor count for the bucket at ``ts``.

        ``total`` comes from the **fold** (how many addresses the ``Deposited``
        /``FirstDeposit`` history has seen by that hour), never from
        ``stats()``: mixing a live counter into a per-hour history would make
        the newest point a different measurement from every point before it,
        and an outage in the counter would then write a hole into the middle of
        the chart.

        ``None`` in → nothing written and ``False`` returned.  A failed read is
        never a zero, and a zero in a persisted series outlives the outage.
        """
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            return False
        if total < 0 or not math.isfinite(float(total)):
            return False
        stamp = _stamp(ts)
        if stamp is None:
            return False
        self._series[SERIES_CONTRIBUTORS][stamp] = float(total)
        self._trim(SERIES_CONTRIBUTORS)
        return True

    def _trim(self, name: str) -> None:
        """Keep the newest :data:`MAX_SERIES_POINTS` buckets, drop the oldest."""
        points = self._series[name]
        if len(points) <= MAX_SERIES_POINTS:
            return
        keep = sorted(points)[-MAX_SERIES_POINTS:]
        dropped = len(points) - len(keep)
        self._series[name] = {ts: points[ts] for ts in keep}
        logger.info(
            "Curator %s exceeded %d points; dropped the %d oldest",
            name,
            MAX_SERIES_POINTS,
            dropped,
        )

    def get_series(self, name: str) -> list[list[float]]:
        """``[[bucket_ts, value], …]`` oldest first — the sparkline shape.

        Bounded to the newest :data:`MAX_SERIES_POINTS`; the values are already
        in presentation units (ETH for volume, a count for contributors), so
        nothing downstream divides again.
        """
        self._check_series(name)
        points = sorted(self._series[name].items())
        return [[float(ts), float(value)] for ts, value in points[-MAX_SERIES_POINTS:]]

    # -- the raw event history, the fold and the watermark -------------------

    def store_events(self, events: Any, *, now: float | None = None) -> int:
        """Merge newly swept ``Deposited`` events in.  Returns how many were new.

        De-duplicated on ``(tx_hash, log_index)``, the model's own key: without
        it a re-org replay or an overlapping sweep window renders every deposit
        twice and doubles the leaderboard.  Kept oldest-first by
        ``(block_number, log_index)`` so the activity feed's "newest last" and
        the cluster detector's block windows both read straight off the list.

        The cap drops the **oldest** events and counts the drop
        (:data:`MAX_PERSISTED_EVENTS`, :attr:`dropped_events`).
        """
        added = 0
        for event in events or ():
            key = _event_key(event)
            if key is None or key in self._event_keys:
                continue
            self._event_keys.add(key)
            self._events.append(event)
            added += 1
        if added:
            self._events.sort(key=lambda e: (e.block_number, e.log_index))
        if len(self._events) > MAX_PERSISTED_EVENTS:
            overflow = len(self._events) - MAX_PERSISTED_EVENTS
            for event in self._events[:overflow]:
                self._event_keys.discard(_event_key(event))
            self._events = self._events[overflow:]
            self.dropped_events += overflow
            logger.warning(
                "Curator event history exceeded %d rows; dropped the %d oldest "
                "(%d dropped this process). The folded totals are now a lower "
                "bound; the contract's own counters are not.",
                MAX_PERSISTED_EVENTS,
                overflow,
                self.dropped_events,
            )
        return added

    def events(self) -> list[DepositEvent]:
        """The whole raw ``Deposited`` history, oldest first."""
        return list(self._events)

    def store_first_deposits(self, rows: Any) -> None:
        """``FirstDeposit`` rows, merged on ``contributor`` (1-based index)."""
        merged = {row["contributor"].lower(): row for row in self._first_deposits}
        for row in rows or ():
            if not isinstance(row, Mapping):
                continue
            who = row.get("contributor")
            index = _opt_int(row.get("index"))
            if not isinstance(who, str) or index is None:
                continue
            merged[who.lower()] = {
                "contributor": who,
                "index": index,
                "ts": _stamp(row.get("ts")),
            }
        self._first_deposits = sorted(merged.values(), key=lambda r: r["index"])

    def first_deposits(self) -> list[dict]:
        return [dict(row) for row in self._first_deposits]

    def store_hour_saved(self, rows: Any) -> None:
        """``HourSaved`` rows, merged on ``hour``.  Never fired on chain yet."""
        merged = {row["hour"]: row for row in self._hour_saved}
        for row in rows or ():
            if not isinstance(row, Mapping):
                continue
            hour = _opt_int(row.get("hour"))
            wallet = row.get("wallet")
            if hour is None or not isinstance(wallet, str):
                continue
            merged[hour] = {"hour": hour, "wallet": wallet, "ts": _stamp(row.get("ts"))}
        self._hour_saved = sorted(merged.values(), key=lambda r: r["hour"])

    def hour_saved(self) -> list[dict]:
        return [dict(row) for row in self._hour_saved]

    def store_rescued_total(self, total_wei: Any) -> None:
        """The summed ``Rescued`` amounts.  ``0`` is real; ``None`` is unread."""
        value = _opt_int(total_wei)
        if value is None or value < 0:
            return
        self._rescued_total_wei = value

    def rescued_total_wei(self) -> int | None:
        return self._rescued_total_wei

    def store_fold(
        self, rows: Any, *, last_block: int | None, now: float | None = None
    ) -> None:
        """Persist the folded contributor table and advance the watermark.

        **Only a successful sweep may call this.**  The watermark is where the
        next incremental sweep starts, so advancing it on a failure skips that
        block range *forever*: the leaderboard would be permanently wrong with
        no symptom, which is why the slow tier's gap repair exists at all.

        ``last_block=None`` stores the rows and leaves the watermark where it
        is — the honest combination for a sweep whose head we could not read.
        The watermark never moves backwards either: a lagging replica answering
        after a fresher one must not re-open a range that is already folded in.
        """
        table: list[ContributorRow] = []
        for row in rows or ():
            if isinstance(row, ContributorRow):
                table.append(row)
        self._fold = table
        block = _opt_int(last_block)
        if block is None:
            return
        if self._last_seen_block is None or block > self._last_seen_block:
            self._last_seen_block = block

    def fold_rows(self) -> list[ContributorRow]:
        return list(self._fold)

    def last_seen_block(self) -> int | None:
        """The newest block a **successful** sweep covered, or ``None``.

        ``None`` means "backfill from the creation block" — never "start from
        now".  Starting from the head would leave the whole game unfolded with
        an empty leaderboard and no error anywhere.
        """
        return self._last_seen_block

    # -- cluster (fan-out pattern) state -------------------------------------

    def store_clusters(self, rows: Any, *, now: float | None = None) -> None:
        """Persist this cycle's fan-out patterns.  Pattern language only.

        The **share of total points is not persisted**: it is a ratio against a
        total that changes every hour, so a restored one would be a stale
        percentage rendered next to live absolutes.  It is recomputed from the
        live fold each cycle and is ``None`` until it has been.
        """
        kept: list[dict] = []
        for row in rows or ():
            if not isinstance(row, Mapping):
                continue
            first_block = _opt_int(row.get("first_block"))
            last_block = _opt_int(row.get("last_block"))
            size = _opt_int(row.get("size"))
            if first_block is None or last_block is None or size is None:
                continue
            kept.append(
                {
                    "size": size,
                    "amount_eth": _opt_float(row.get("amount_eth")),
                    "first_block": first_block,
                    "last_block": last_block,
                    "points": _opt_int(row.get("points")),
                    "points_share_pct": _opt_float(row.get("points_share_pct")),
                }
            )
        self._clusters = kept

    def clusters(self) -> list[dict]:
        return [dict(row) for row in self._clusters]

    def _load_clusters(self, raw: Any) -> None:
        """Restore the patterns the retained history can still corroborate.

        A cluster whose block window has fallen out of the retained event
        history is **dropped**, not rendered: the rows that evidenced it are
        gone, and a flag nothing can be traced back to is an accusation with no
        witness.  Every restored share is ``None`` — see :meth:`store_clusters`.
        """
        self._clusters = []
        if not isinstance(raw, (list, tuple)):
            return
        oldest = self._events[0].block_number if self._events else None
        restored: list[dict] = []
        dropped = 0
        for row in raw:
            if not isinstance(row, Mapping):
                dropped += 1
                continue
            first_block = _opt_int(row.get("first_block"))
            last_block = _opt_int(row.get("last_block"))
            size = _opt_int(row.get("size"))
            if first_block is None or last_block is None or size is None:
                dropped += 1
                continue
            if oldest is None or first_block < oldest:
                dropped += 1
                continue
            restored.append(
                {
                    "size": size,
                    "amount_eth": _opt_float(row.get("amount_eth")),
                    "first_block": first_block,
                    "last_block": last_block,
                    "points": _opt_int(row.get("points")),
                    # Never restored from disk: a ratio against a total that
                    # changes every hour.
                    "points_share_pct": None,
                }
            )
        self._clusters = restored
        if dropped:
            logger.info(
                "Dropped %d persisted cluster(s) the retained history no longer covers",
                dropped,
            )

    # -- the settlement evidence latch (H1) ----------------------------------

    def observe_settlement(
        self,
        settled: Any,
        *,
        block_number: int | None,
        now: float | None = None,
    ) -> SettlementRecord | None:
        """Fold one ``isSettled()`` observation into the latch.

        The **first** ``True`` is written down with its evidence —
        ``{value, block_number, observed_at}`` — and never re-read through.
        From then on the dashboard renders SETTLED through any outage: an
        outage degrades the *freshness* marker, never the phase.

        A later ``False`` or ``None`` **cannot** clear it.  The contract's own
        predicate is one-way (``_settled || _isShort(currentHour())``, and
        deposits revert ``AlreadySettled`` afterwards), so a later ``False`` can
        only be a bad read, a wrong endpoint or a fork; a ``None`` is an outage,
        which is the case this latch exists for.  Unlike surf's hook detector
        this cannot be griefed: it reads a predicate the contract enforces, not
        an attacker-emittable log.

        Only ``True`` latches.  ``False`` is a real, useful reading — the game
        is running — but it is *live state*, not evidence, and writing a
        ``settled=False`` record would give the phase machine a second source of
        truth to disagree with.

        Returns the record in force, or ``None`` while nothing has been latched.
        """
        if self._settlement is None and settled is True:
            self._settlement = SettlementRecord(
                settled=True,
                block_number=_opt_int(block_number),
                observed_at=self._now(now),
            )
            logger.warning(
                "THE LIST settled: latched at block %s, observed at %s",
                self._settlement.block_number,
                self._settlement.observed_at,
            )
        return self.settlement_record()

    def settlement_record(self) -> SettlementRecord | None:
        """The latched observation, with the obituary filled in if it arrived.

        Reads the **persisted record**, never a live value: making this
        transparent to the current read is the exact mutation PRD §8 mandates
        proving against, because it silently re-couples the phase to the state
        pool it was decoupled from.
        """
        if self._settlement is None:
            return None
        if not self._obituary:
            return self._settlement
        return SettlementRecord(
            settled=self._settlement.settled,
            block_number=self._settlement.block_number,
            observed_at=self._settlement.observed_at,
            settled_hour=self._obituary.get("settled_hour"),
            settled_at_ts=self._obituary.get("settled_at_ts"),
            total_contributors=self._obituary.get("total_contributors"),
            total_volume_wei=self._obituary.get("total_volume_wei"),
        )

    def record_settled_event(
        self,
        hour: Any = None,
        ts: Any = None,
        contributors: Any = None,
        volume_wei: Any = None,
    ) -> None:
        """File the ``Settled`` log's four words — the obituary, not the latch.

        A ``Settled`` log with no prior view observation must **not** create the
        latch: the event is evidence about the past and the view is evidence
        about now.  In practice they agree, but ``settle()`` is permissionless
        and its log is the one piece of this that a third party emits at a time
        of their choosing, so a log-only latch is the hazard PRD §3 names one
        level down.  The obituary waits here until the view confirms.
        """
        self._obituary = {
            "settled_hour": _opt_int(hour),
            "settled_at_ts": _opt_int(ts),
            "total_contributors": _opt_int(contributors),
            "total_volume_wei": _opt_int(volume_wei),
        }

    def _settlement_to_dict(self) -> dict[str, Any] | None:
        record = self._settlement
        if record is None:
            return None
        return {
            "settled": bool(record.settled),
            "block_number": record.block_number,
            "observed_at": float(record.observed_at),
        }

    def _load_settlement(self, raw: Any) -> None:
        """Re-validate a persisted record rather than believing it.

        The surf ``hook_status`` lesson: never trust the boolean a file happened
        to contain.  A record without both evidence fields, or carrying a
        non-bool verdict, is discarded — a latch restored from corruption would
        pin the hero to SETTLED for the life of the file.
        """
        self._settlement = None
        if not isinstance(raw, Mapping):
            return
        if raw.get("settled") is not True:
            return
        if "block_number" not in raw or "observed_at" not in raw:
            return
        block = raw.get("block_number")
        if block is not None and (isinstance(block, bool) or not isinstance(block, int)):
            return
        observed = _stamp(raw.get("observed_at"))
        if observed is None:
            return
        self._settlement = SettlementRecord(
            settled=True, block_number=_opt_int(block), observed_at=observed
        )

    # -- persistence ---------------------------------------------------------

    def _payload(self) -> dict[str, Any]:
        return {
            "version": _SCHEMA_VERSION,
            "saved_at": self._now(),
            "last_good": {
                slot: entry.to_dict() for slot, entry in self.last_good.items()
            },
            "series": {name: self.get_series(name) for name in SERIES_NAMES},
            "settlement": self._settlement_to_dict(),
            "settled_event": dict(self._obituary) if self._obituary else None,
            "events": [_event_to_dict(e) for e in self._events],
            # Persisted with the events it belongs to: the retained rows are a
            # lower bound on the history and this is how much lower.  Adding a
            # key does not move `_SCHEMA_VERSION` -- an older file simply has
            # none and restores the 0 it always had.
            "dropped_events": int(self.dropped_events),
            # Persisted with the events it belongs to: the retained rows are a
            # lower bound on the history and this is how much lower.  Adding a
            # key does not move `_SCHEMA_VERSION` -- an older file simply has
            # none and restores the 0 it always had.
            "first_deposits": [dict(row) for row in self._first_deposits],
            "hour_saved": [dict(row) for row in self._hour_saved],
            "rescued_total_wei": self._rescued_total_wei,
            "fold": [_row_to_dict(row) for row in self._fold],
            "last_seen_block": self._last_seen_block,
            "clusters": [
                {k: v for k, v in row.items() if k != "points_share_pct"}
                for row in self._clusters
            ],
            # Verified ENS names and known misses, with their own TTLs (PRD §13
            # A9).  Persisted so a relaunch does not re-resolve every rendered
            # wallet; adding the key does not move `_SCHEMA_VERSION`, since an
            # older file simply has none and starts empty.
            "ens": self.ens.as_dict(),
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

        try:
            self.ens.load(payload.get("ens"))
        except Exception as exc:  # noqa: BLE001 -- names are decoration
            logger.warning("Curator ENS block bad: %s", exc)

        try:
            dropped = 0
            for raw in payload.get("events") or ():
                event = _event_from_dict(raw)
                if event is None:
                    dropped += 1
                    continue
                key = _event_key(event)
                if key is None or key in self._event_keys:
                    dropped += 1
                    continue
                self._event_keys.add(key)
                self._events.append(event)
            self._events.sort(key=lambda e: (e.block_number, e.log_index))
            if dropped:
                logger.warning(
                    "Dropped %d unusable event row(s) from the curator cache %s",
                    dropped,
                    target,
                )
            # Assigned, not accumulated: this is a *restore* of one file's
            # counter onto a fresh cache (the manager loads once, in
            # ``__init__``), so loading the same file twice must not double it.
            # A negative, a bool or a non-number is not a count and leaves the 0.
            saved_drop = _opt_int(payload.get("dropped_events"))
            if saved_drop is not None and saved_drop > 0:
                self.dropped_events = saved_drop
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator events block bad: %s", exc)

        try:
            self.store_first_deposits(payload.get("first_deposits"))
            self.store_hour_saved(payload.get("hour_saved"))
            self.store_rescued_total(payload.get("rescued_total_wei"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator log-row block bad: %s", exc)

        try:
            dropped = 0
            rows: list[ContributorRow] = []
            for raw in payload.get("fold") or ():
                row = _row_from_dict(raw)
                if row is None:
                    dropped += 1
                    continue
                rows.append(row)
            self._fold = rows
            self._last_seen_block = _opt_int(payload.get("last_seen_block"))
            if dropped:
                logger.warning(
                    "Dropped %d unusable fold row(s) from the curator cache %s",
                    dropped,
                    target,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator fold block bad: %s", exc)

        try:
            self._load_clusters(payload.get("clusters"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator clusters block bad: %s", exc)
            self._clusters = []

        try:
            self._load_settlement(payload.get("settlement"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator settlement block bad: %s", exc)
            self._settlement = None

        try:
            event = payload.get("settled_event")
            if isinstance(event, Mapping):
                self.record_settled_event(
                    hour=event.get("settled_hour"),
                    ts=event.get("settled_at_ts"),
                    contributors=event.get("total_contributors"),
                    volume_wei=event.get("total_volume_wei"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator settled-event block bad: %s", exc)

        logger.info(
            "Loaded the curator cache from %s: %d last-good slot(s), %d volume point(s)",
            target,
            len(self.last_good),
            len(self._series[SERIES_VOLUME]),
        )


__all__ = [
    "MAX_PERSISTED_EVENTS",
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
