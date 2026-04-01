"""In-memory cache with time-series accumulation for Onchain Monsters data.

The ``OCMCache`` stores the most recent ``OCMSnapshot`` and accumulates
supply, staking, and OCMD token supply histories over time so the
dashboard can render sparklines and trend indicators.

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

from maxpane_dashboard.data.ocm_models import OCMSnapshot

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, value)
TimeSeriesPoint = tuple[float, float]


class OCMCache:
    """Caches Onchain Monsters data and accumulates time-series histories.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self.supply_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.staked_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.ocmd_supply_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self._latest: OCMSnapshot | None = None
        self._last_updated: float | None = None
        self._cumulative_burned: int = 0
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
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at
        ts = snapshot.fetched_at

        self.supply_history.append((ts, float(snapshot.collection.total_supply)))
        self.staked_history.append((ts, float(snapshot.staking.total_staked)))
        self.ocmd_supply_history.append((ts, snapshot.staking.ocmd_total_supply))

    def get_supply_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for NFT total supply."""
        return list(self.supply_history)

    def get_staked_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for staked NFT count."""
        return list(self.staked_history)

    def get_ocmd_supply_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for OCMD token total supply."""
        return list(self.ocmd_supply_history)

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

    def update_burned_count(self, count: int) -> None:
        """Increment cumulative burned count from events."""
        self._cumulative_burned += count

    def update_holder_count(self, count: int) -> None:
        """Update cached holder count and refresh timestamp."""
        self._holder_count = count
        self._holder_count_updated = time.time()

    @property
    def cumulative_burned(self) -> int:
        """Accumulated burn count from events."""
        return self._cumulative_burned

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

        File format::

            {
                "saved_at": <float>,
                "max_history": <int>,
                "supply_history": [[ts, val], ...],
                "staked_history": [[ts, val], ...],
                "ocmd_supply_history": [[ts, val], ...],
                "cumulative_burned": <int>,
                "holder_count": <int>
            }
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
            "supply_history": [list(pt) for pt in self.supply_history],
            "staked_history": [list(pt) for pt in self.staked_history],
            "ocmd_supply_history": [list(pt) for pt in self.ocmd_supply_history],
            "cumulative_burned": self._cumulative_burned,
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

        Silently does nothing if the file is missing or corrupted.
        Existing in-memory data is replaced on successful load.
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

        loaded = 0
        for key, deque_ref in [
            ("supply_history", self.supply_history),
            ("staked_history", self.staked_history),
            ("ocmd_supply_history", self.ocmd_supply_history),
        ]:
            points = payload.get(key, [])
            if not isinstance(points, list):
                continue
            deque_ref.clear()
            for pt in points:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    deque_ref.append((float(pt[0]), float(pt[1])))
            loaded += len(deque_ref)

        # Restore scalar cached state
        if isinstance(payload.get("cumulative_burned"), (int, float)):
            self._cumulative_burned = int(payload["cumulative_burned"])
        if isinstance(payload.get("holder_count"), (int, float)):
            self._holder_count = int(payload["holder_count"])

        logger.info(
            "Loaded OCM cache from %s: %d total points",
            path,
            loaded,
        )
