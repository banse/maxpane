"""In-memory cache with time-series accumulation for Onchain Monsters data.

The ``OCMCache`` stores the most recent ``OCMSnapshot`` and accumulates
supply, staking, OCMD token supply, and cumulative-burn histories over
time so the dashboard can render sparklines and trend indicators.

Note on the burn series: OCM burns are transfers to ``0xdead...dead`` and
therefore never reduce ``totalSupply``.  The number of burned tokens is
``balanceOf(0xdead)``, exposed as ``snapshot.collection.burned_count``,
and it is the *only* series from which a burn rate may be derived.  The
supply series grows with mints and says nothing about burns.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections import deque
from typing import Any

from maxpane_dashboard.data.ocm_models import OCMSnapshot

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, value)
TimeSeriesPoint = tuple[float, float]

# On-disk schema version.  Bumped to 2 when ``burn_history`` was introduced;
# version-1 files hold no burn data (and their ``cumulative_burned`` scalar was
# always 0 because nothing ever incremented it), so their burn series is
# started from empty rather than migrated.
_CACHE_VERSION = 2

# Loaded points older than this are dropped: the sparkline series only spans
# ~2h of live polling, so an older point cannot inform the trend and can only
# distort the rate maths (a single ancient point stretches the window).
_SPARKLINE_MAX_AGE_SECONDS = 24 * 3600

# Tolerance for clock skew when rejecting future-dated points.
_CLOCK_SKEW_TOLERANCE_SECONDS = 300.0

# Hard cap on burn samples held in memory (~1 per hour plus one per change).
_BURN_HISTORY_MAXLEN = 400


class OCMCache:
    """Caches Onchain Monsters data and accumulates time-series histories.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
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

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self.supply_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.staked_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.ocmd_supply_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.burn_history: deque[TimeSeriesPoint] = deque(maxlen=_BURN_HISTORY_MAXLEN)
        self._latest: OCMSnapshot | None = None
        self._last_updated: float | None = None
        self._holder_count: int = 0
        self._holder_count_updated: float = 0.0

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
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at
        ts = snapshot.fetched_at

        self.supply_history.append((ts, float(snapshot.collection.total_supply)))
        self.staked_history.append((ts, float(snapshot.staking.total_staked)))
        self.ocmd_supply_history.append((ts, snapshot.staking.ocmd_total_supply))
        self._append_burn_sample(ts, float(snapshot.collection.burned_count))

    def _append_burn_sample(self, ts: float, burned: float) -> None:
        """Append a cumulative-burn sample, downsampled to keep a long window.

        A sample is kept when the burned count changed, or when the last
        sample is at least ``BURN_SAMPLE_INTERVAL_SECONDS`` old.  Samples
        older than ``BURN_WINDOW_SECONDS`` are pruned, but at least two are
        always retained so a rate stays computable.
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
        return list(self.supply_history)

    def get_staked_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for staked NFT count."""
        return list(self.staked_history)

    def get_ocmd_supply_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for OCMD token total supply."""
        return list(self.ocmd_supply_history)

    def get_burn_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, cumulative_burned), ...]``.

        This -- not the supply history -- is the input to
        ``analytics.ocm_signals.compute_burn_rate``.
        """
        return list(self.burn_history)

    def get_latest(self) -> OCMSnapshot | None:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of data points in the supply history (representative)."""
        return len(self.supply_history)

    # ------------------------------------------------------------------
    # Additional cached state
    # ------------------------------------------------------------------

    def update_holder_count(self, count: int) -> None:
        """Update cached holder count and refresh timestamp."""
        self._holder_count = count
        self._holder_count_updated = time.time()

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

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        File format (version 2)::

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
        """
        payload: dict[str, Any] = {
            "version": _CACHE_VERSION,
            "saved_at": time.time(),
            "max_history": self._max_history,
            "supply_history": [list(pt) for pt in self.supply_history],
            "staked_history": [list(pt) for pt in self.staked_history],
            "ocmd_supply_history": [list(pt) for pt in self.ocmd_supply_history],
            "burn_history": [list(pt) for pt in self.burn_history],
            "holder_count": self._holder_count,
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "OCM cache saved to %s (%d points)",
                path,
                len(self.supply_history),
            )
        except OSError as exc:
            logger.warning("Failed to save OCM cache: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def load_from_file(self, path: str) -> None:
        """Load previously saved history from a JSON file.

        Silently does nothing if the file is missing or corrupted, and
        individually skips points that are malformed (non-numeric, NaN,
        negative), future-dated, or older than the series' window --
        a stale or hand-edited file must never feed a signal wrong values.

        Version-1 files (written before the burn series existed) carry no
        burn data: their burn history is left empty and accumulates from
        the next poll.  Nothing in a v1 file can be migrated into it --
        the supply series is mint data, and ``cumulative_burned`` was
        always 0 because nothing ever incremented it.
        """
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No OCM cache file to load (%s): %s", path, exc)
            return

        if not isinstance(payload, dict):
            logger.warning(
                "OCM cache file %s has unexpected format, skipping", path
            )
            return

        raw_version = payload.get("version")
        version = raw_version if isinstance(raw_version, int) else 1

        now = time.time()
        series: list[tuple[str, deque[TimeSeriesPoint], float]] = [
            ("supply_history", self.supply_history, _SPARKLINE_MAX_AGE_SECONDS),
            ("staked_history", self.staked_history, _SPARKLINE_MAX_AGE_SECONDS),
            (
                "ocmd_supply_history",
                self.ocmd_supply_history,
                _SPARKLINE_MAX_AGE_SECONDS,
            ),
        ]

        if version >= _CACHE_VERSION:
            series.append(
                ("burn_history", self.burn_history, self.BURN_WINDOW_SECONDS)
            )
        else:
            self.burn_history.clear()
            logger.info(
                "OCM cache %s is version %d (pre-burn-series); burn history "
                "starts empty and accumulates from the next poll",
                path,
                version,
            )

        loaded = 0
        skipped = 0
        for key, deque_ref, max_age in series:
            points = payload.get(key, [])
            if not isinstance(points, list):
                continue
            deque_ref.clear()
            for pt in points:
                coerced = _coerce_point(pt, now=now, max_age=max_age)
                if coerced is None:
                    skipped += 1
                    continue
                deque_ref.append(coerced)
            loaded += len(deque_ref)

        # Restore scalar cached state
        if isinstance(payload.get("holder_count"), (int, float)):
            self._holder_count = int(payload["holder_count"])

        if skipped:
            logger.warning(
                "Skipped %d unusable point(s) while loading OCM cache %s",
                skipped,
                path,
            )
        logger.info(
            "Loaded OCM cache from %s: %d total points",
            path,
            loaded,
        )


def _coerce_point(
    pt: Any, *, now: float, max_age: float
) -> TimeSeriesPoint | None:
    """Validate one persisted ``[timestamp, value]`` pair.

    Returns ``None`` -- meaning "drop this point" -- for anything that is
    not a usable sample.  Corrupt-but-valid JSON (``null``, strings,
    ``NaN``) used to raise ``TypeError`` out of ``load_from_file`` and
    abort MaxPane startup for every dashboard, since all managers load
    their caches in ``__init__``.
    """
    if not isinstance(pt, (list, tuple)) or len(pt) != 2:
        return None
    if isinstance(pt[0], bool) or isinstance(pt[1], bool):
        return None
    try:
        ts = float(pt[0])
        val = float(pt[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(ts) and math.isfinite(val)):
        return None
    if ts <= 0 or val < 0:
        return None
    if ts > now + _CLOCK_SKEW_TOLERANCE_SECONDS:
        return None
    if ts < now - max_age:
        return None
    return (ts, val)
