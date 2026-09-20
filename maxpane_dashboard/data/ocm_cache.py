"""In-memory cache with time-series accumulation for Onchain Monsters data.

The ``OCMCache`` stores the most recent ``OCMSnapshot`` and accumulates
supply, staking, OCMD token supply, and cumulative-burn histories over
time so the dashboard can render sparklines and trend indicators.

Everything but ``update()``, the burn downsampler, the holder-count
scalar and the named getters is inherited from
``data/series_cache.SeriesCache``; see that module for the persistence
contract and for why ``record()`` drops ``None`` instead of zero-filling.
This is the cache that made the base's per-series ``max_age`` necessary:
three sparkline series are windowed at a day, the burn series at a week.

Note on the burn series: OCM burns are transfers to ``0xdead...dead`` and
therefore never reduce ``totalSupply``.  The number of burned tokens is
``balanceOf(0xdead)``, exposed as ``snapshot.collection.burned_count``,
and it is the *only* series from which a burn rate may be derived.  The
supply series grows with mints and says nothing about burns.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from maxpane_dashboard.data.ocm_models import OCMSnapshot
from maxpane_dashboard.data.series_cache import (
    SeriesCache,
    SeriesSpec,
    TimeSeriesPoint,
)

logger = logging.getLogger(__name__)

__all__ = ["OCMCache", "TimeSeriesPoint"]

# On-disk schema version.  Bumped to 2 when ``burn_history`` was introduced;
# version-1 files hold no burn data (and their ``cumulative_burned`` scalar was
# always 0 because nothing ever incremented it), so their burn series is
# started from empty rather than migrated.
#
# It must stay the literal 2 under the literal key ``"version"``: bumping it
# routes every live ``~/.maxpane/ocm_cache.json`` through the pre-v2 branch
# below and wipes a burn history that takes a week to rebuild.
_CACHE_VERSION = 2

# Loaded points older than this are dropped: the sparkline series only spans
# ~2h of live polling, so an older point cannot inform the trend and can only
# distort the rate maths (a single ancient point stretches the window).
_SPARKLINE_MAX_AGE_SECONDS = 24 * 3600

# Hard cap on burn samples held in memory (~1 per hour plus one per change).
_BURN_HISTORY_MAXLEN = 400

# The persisted key order, oldest file first.  ``SeriesCache._payload``
# writes ``saved_at``/``max_history`` before the version key and the
# declared series before ``extra_payload``; this file has always led with
# ``version`` and closed with ``holder_count``, and a cache file whose
# keys reshuffle on every save is a diff nobody can read.
_PAYLOAD_KEY_ORDER = (
    "version",
    "saved_at",
    "max_history",
    "supply_history",
    "staked_history",
    "ocmd_supply_history",
    "burn_history",
    "holder_count",
)


class OCMCache(SeriesCache):
    """Caches Onchain Monsters data and accumulates time-series histories.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.  The burn series
        names its own, much larger, ``maxlen``.
    """

    #: Trailing window the burn series is kept over, and the window the burn
    #: rate is expressed in.  ``balanceOf(0xdead)`` is cumulative, so a long
    #: window is both cheap and far more meaningful than the ~2h sparkline
    #: window: burns are rare, and a 2h window would turn a single burn into
    #: an extrapolated ~84/week red alarm.
    BURN_WINDOW_SECONDS: float = 7 * 86400.0

    #: Minimum spacing between burn samples when the value has not changed.
    #: A changed ``burned_count`` is always recorded immediately.
    BURN_SAMPLE_INTERVAL_SECONDS: float = 3600.0

    #: The three sparkline series plus the burn series, which carries both
    #: its own ``maxlen`` and its own, week-long, window.  ``history_size``
    #: counts the first one, as it always has.
    SERIES = (
        SeriesSpec("supply_history", max_age=_SPARKLINE_MAX_AGE_SECONDS),
        SeriesSpec("staked_history", max_age=_SPARKLINE_MAX_AGE_SECONDS),
        SeriesSpec("ocmd_supply_history", max_age=_SPARKLINE_MAX_AGE_SECONDS),
        SeriesSpec(
            "burn_history",
            maxlen=_BURN_HISTORY_MAXLEN,
            max_age=BURN_WINDOW_SECONDS,
        ),
    )
    VERSION_KEY = "version"
    VERSION = _CACHE_VERSION
    NOUN = "OCM cache"

    supply_history: deque[TimeSeriesPoint]
    staked_history: deque[TimeSeriesPoint]
    ocmd_supply_history: deque[TimeSeriesPoint]
    burn_history: deque[TimeSeriesPoint]
    _latest: OCMSnapshot | None

    def __init__(self, max_history: int = 120) -> None:
        super().__init__(max_history)
        self._holder_count: int = 0
        self._holder_count_updated: float = 0.0
        # Schema version of the file the last load read, so the one
        # message about a pre-v2 file can be emitted from ``restore_extra``
        # -- the first hook after ``before_load`` that is handed ``path``,
        # which the message names.
        self._loaded_version: int = self.VERSION

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(self, snapshot: OCMSnapshot) -> None:
        """Store latest snapshot, accumulate time-series data points.

        Appends one data point per series:
        - supply_history: NFT total supply
        - staked_history: staked NFT count
        - ocmd_supply_history: OCMD token total supply
        - burn_history: cumulative burned count (``balanceOf(0xdead)``),
          downsampled -- see :meth:`_append_burn_sample`

        Callers must only pass snapshots whose reads all succeeded; a
        snapshot with ``read_failures`` carries zeros that would poison
        every series (see ``OCMManager.fetch_and_compute``).
        """
        self._mark(snapshot)
        ts = snapshot.fetched_at

        self.record("supply_history", ts, snapshot.collection.total_supply)
        self.record("staked_history", ts, snapshot.staking.total_staked)
        self.record("ocmd_supply_history", ts, snapshot.staking.ocmd_total_supply)
        self._append_burn_sample(ts, float(snapshot.collection.burned_count))

    def _append_burn_sample(self, ts: float, burned: float) -> None:
        """Append a cumulative-burn sample, downsampled to keep a long window.

        A sample is kept when the burned count changed, or when the last
        sample is at least ``BURN_SAMPLE_INTERVAL_SECONDS`` old.  Samples
        older than ``BURN_WINDOW_SECONDS`` are pruned, but at least two are
        always retained so a rate stays computable.

        This stays a hand-written append rather than a ``record()`` call:
        the dedupe and the prune are specific to a cumulative counter
        sampled far more often than it moves.
        """
        if self.burn_history:
            last_ts, last_val = self.burn_history[-1]
            unchanged = burned == last_val
            too_soon = (ts - last_ts) < self.BURN_SAMPLE_INTERVAL_SECONDS
            if unchanged and too_soon:
                return

        self.burn_history.append((ts, burned))

        cutoff = ts - self.BURN_WINDOW_SECONDS
        while len(self.burn_history) > 2 and self.burn_history[0][0] < cutoff:
            self.burn_history.popleft()

    def get_supply_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for NFT total supply."""
        return self.get_series("supply_history")

    def get_staked_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for staked NFT count."""
        return self.get_series("staked_history")

    def get_ocmd_supply_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for OCMD token total supply."""
        return self.get_series("ocmd_supply_history")

    def get_burn_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, cumulative_burned), ...]``.

        This -- not the supply history -- is the input to
        ``analytics.ocm_signals.compute_burn_rate``.
        """
        return self.get_series("burn_history")

    # ------------------------------------------------------------------
    # Additional cached state
    # ------------------------------------------------------------------

    def update_holder_count(self, count: int, *, now: float | None = None) -> None:
        """Update cached holder count and refresh timestamp.

        ``now`` is the clock, injected like every other one in this
        package (rules/data.md, "Inject the clock"): a test that wants to
        age the holder count must not have to move the machine's clock.
        ``None`` falls back to the wall clock for callers that genuinely
        mean "now", which is every production caller today.
        """
        self._holder_count = count
        self._holder_count_updated = time.time() if now is None else now

    @property
    def holder_count(self) -> int:
        """Cached holder count."""
        return self._holder_count

    @property
    def holder_count_updated(self) -> float:
        """Timestamp of last holder count update."""
        return self._holder_count_updated

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def extra_payload(self) -> dict[str, Any]:
        """The one scalar this cache persists beyond its four series."""
        return {"holder_count": self._holder_count}

    def _payload(self) -> dict[str, Any]:
        """The saved payload, in this file's historical key order::

            {
                "version": 2,
                "saved_at": <float>,
                "max_history": <int>,
                "supply_history": [[ts, val], ...],
                "staked_history": [[ts, val], ...],
                "ocmd_supply_history": [[ts, val], ...],
                "burn_history": [[ts, cumulative_burned], ...],
                "holder_count": <int>
            }

        Nothing reads a JSON object's key order, but a save that
        reshuffles a user's file makes every backup diff unreadable for
        no gain, so the base's order is rewritten to this one here rather
        than negotiated in the base class -- frenpet wants its keyed dict
        *before* its series and this one wants its scalar *after*.
        """
        payload = super()._payload()
        ordered = {k: payload.pop(k) for k in _PAYLOAD_KEY_ORDER if k in payload}
        # Anything unexpected still gets written rather than dropped.
        ordered.update(payload)
        return ordered

    def before_load(self, payload: dict[str, Any], version: int) -> None:
        """Withhold the burn series from a pre-v2 file.

        Version-1 files (written before the burn series existed) carry no
        burn data: their burn history is left empty and accumulates from
        the next poll.  Nothing in a v1 file can be migrated into it --
        the supply series is mint data, and ``cumulative_burned`` was
        always 0 because nothing ever incremented it.

        The key is **removed from the payload** rather than the deque
        merely cleared, because the base's restore loop reads
        ``payload["burn_history"]`` immediately after this hook: clearing
        alone would be undone one line later by whatever a stale or
        hand-edited file happens to hold under that key.  A missing key
        coerces to "no points", which is exactly the documented
        behaviour, and the base's clear-before-extend empties the deque.
        Version gating, not key presence, is what decides this
        (``test_ocm_cache.py::test_v1_file_with_an_injected_burn_history_is_ignored``).
        """
        self._loaded_version = version
        if version >= self.VERSION:
            return
        payload.pop("burn_history", None)

    def restore_extra(
        self,
        payload: dict[str, Any],
        *,
        path: str,
        now: float,
        max_age: float | None = None,
    ) -> int:
        """Restore the holder count, and report a pre-v2 file.

        The pre-v2 message is emitted here rather than in
        :meth:`before_load`, which decided the matter: ``before_load``
        is not handed ``path``, and the file's name is the actionable
        half of the sentence.  Both hooks run before the "Skipped ..."
        warning and the closing info line, so the log order is unchanged.

        No point is dropped here -- the holder count is a scalar -- so
        the return is always 0.
        """
        if self._loaded_version < self.VERSION:
            logger.info(
                "OCM cache %s is version %d (pre-burn-series); burn history "
                "starts empty and accumulates from the next poll",
                path,
                self._loaded_version,
            )
        if isinstance(payload.get("holder_count"), (int, float)):
            self._holder_count = int(payload["holder_count"])
        return 0
