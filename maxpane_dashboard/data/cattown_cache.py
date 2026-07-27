"""In-memory cache with time-series accumulation for Cat Town data.

The ``CatTownCache`` stores the most recent ``CatTownSnapshot`` and
accumulates price, volume, burn, and prize pool histories over time so
the dashboard can render sparklines and trend indicators.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from typing import Any

from maxpane_dashboard.data.cattown_models import CatTownSnapshot
from maxpane_dashboard.data.series_points import coerce_points

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, value)
TimeSeriesPoint = tuple[float, float]


class CatTownCache:
    """Caches Cat Town data and accumulates time-series histories.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self.prize_pool_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.leader_weight_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.raffle_tickets_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self._latest: CatTownSnapshot | None = None
        self._last_updated: float | None = None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(
        self,
        snapshot: CatTownSnapshot,
        leader_weight_kg: float = 0.0,
        raffle_total_tickets: int = 0,
    ) -> None:
        """Store latest snapshot, accumulate time-series data points.

        Appends one data point per series:
        - prize_pool_history: competition prize pool in KIBBLE
        - leader_weight_history: #1 fish weight in kg
        - raffle_tickets_history: total raffle tickets sold this round
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at
        ts = snapshot.fetched_at

        self.prize_pool_history.append((ts, snapshot.competition.prize_pool_kibble))
        self.leader_weight_history.append((ts, leader_weight_kg))
        self.raffle_tickets_history.append((ts, float(raffle_total_tickets)))

    def get_prize_pool_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, pool), ...]`` for competition prize pool."""
        return list(self.prize_pool_history)

    def get_leader_weight_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, kg), ...]`` for #1 fish weight."""
        return list(self.leader_weight_history)

    def get_raffle_tickets_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, tickets), ...]`` for raffle ticket count."""
        return list(self.raffle_tickets_history)

    def get_latest(self) -> CatTownSnapshot | None:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of data points in the price history (representative)."""
        return len(self.prize_pool_history)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        File format::

            {
                "saved_at": <float>,
                "max_history": <int>,
                "prize_pool_history": [[ts, val], ...],
                "leader_weight_history": [[ts, val], ...],
                "raffle_tickets_history": [[ts, val], ...]
            }
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
            "prize_pool_history": [list(pt) for pt in self.prize_pool_history],
            "leader_weight_history": [list(pt) for pt in self.leader_weight_history],
            "raffle_tickets_history": [list(pt) for pt in self.raffle_tickets_history],
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "CatTown cache saved to %s (%d points)",
                path,
                len(self.prize_pool_history),
            )
        except OSError as exc:
            logger.warning("Failed to save CatTown cache: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def load_from_file(self, path: str) -> None:
        """Load previously saved history from a JSON file.

        Silently does nothing if the file is missing or corrupted.
        Existing in-memory data is replaced on successful load.

        Individual points are validated: anything unusable (``null``, a
        string, ``NaN``, a wrong-length entry, a negative value, a
        future-dated timestamp) is dropped and counted rather than
        raising, because every manager loads its cache in ``__init__``
        and one bad value used to abort MaxPane startup for every
        dashboard.
        """
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No CatTown cache file to load (%s): %s", path, exc)
            return

        if not isinstance(payload, dict):
            logger.warning(
                "CatTown cache file %s has unexpected format, skipping", path
            )
            return

        loaded = 0
        skipped = 0
        now = time.time()
        for key, deque_ref in [
            ("prize_pool_history", self.prize_pool_history),
            ("leader_weight_history", self.leader_weight_history),
            ("raffle_tickets_history", self.raffle_tickets_history),
        ]:
            points = payload.get(key, [])
            if not isinstance(points, list):
                continue
            good, dropped = coerce_points(points, now=now)
            skipped += dropped
            deque_ref.clear()
            deque_ref.extend(good)
            loaded += len(deque_ref)

        if skipped:
            logger.warning(
                "Skipped %d unusable point(s) while loading CatTown cache %s",
                skipped,
                path,
            )
        logger.info(
            "Loaded CatTown cache from %s: %d total points",
            path,
            loaded,
        )
