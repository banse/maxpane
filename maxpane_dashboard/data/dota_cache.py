"""In-memory cache with time-series accumulation for DOTA dashboard data.

The ``DOTACache`` stores the most recent ``DOTASnapshot`` and accumulates
lane frontline histories over time so the dashboard can render sparklines.

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

from maxpane_dashboard.data.dota_models import DOTASnapshot

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, value)
TimeSeriesPoint = tuple[float, float]


class DOTACache:
    """Caches DOTA data and accumulates lane frontline time-series.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self.top_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.mid_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.bot_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self._latest: DOTASnapshot | None = None
        self._last_updated: float | None = None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(self, snapshot: DOTASnapshot) -> None:
        """Store latest snapshot, accumulate lane frontline data points.

        Extracts frontline values from ``game_state.lanes`` for the three
        lanes (top, mid, bot) and appends ``(timestamp, frontline_value)``
        to each history deque.
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at
        ts = snapshot.fetched_at

        if snapshot.game_state is not None and snapshot.game_state.lanes:
            lanes = snapshot.game_state.lanes
            if "top" in lanes:
                self.top_history.append((ts, float(lanes["top"].frontline)))
            if "mid" in lanes:
                self.mid_history.append((ts, float(lanes["mid"].frontline)))
            if "bot" in lanes:
                self.bot_history.append((ts, float(lanes["bot"].frontline)))

    def get_top_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, frontline), ...]`` for the top lane."""
        return list(self.top_history)

    def get_mid_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, frontline), ...]`` for the mid lane."""
        return list(self.mid_history)

    def get_bot_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, frontline), ...]`` for the bot lane."""
        return list(self.bot_history)

    def get_latest(self) -> DOTASnapshot | None:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of data points in the top history (representative)."""
        return len(self.top_history)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        File format::

            {
                "saved_at": <float>,
                "max_history": <int>,
                "top_history": [[ts, val], ...],
                "mid_history": [[ts, val], ...],
                "bot_history": [[ts, val], ...]
            }
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
            "top_history": [list(pt) for pt in self.top_history],
            "mid_history": [list(pt) for pt in self.mid_history],
            "bot_history": [list(pt) for pt in self.bot_history],
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "DOTA cache saved to %s (%d points)",
                path,
                len(self.top_history),
            )
        except OSError as exc:
            logger.warning("Failed to save DOTA cache: %s", exc)
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
            logger.info("No DOTA cache file to load (%s): %s", path, exc)
            return

        if not isinstance(payload, dict):
            logger.warning(
                "DOTA cache file %s has unexpected format, skipping", path
            )
            return

        loaded = 0
        for key, deque_ref in [
            ("top_history", self.top_history),
            ("mid_history", self.mid_history),
            ("bot_history", self.bot_history),
        ]:
            points = payload.get(key, [])
            if not isinstance(points, list):
                continue
            deque_ref.clear()
            for pt in points:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    deque_ref.append((float(pt[0]), float(pt[1])))
            loaded += len(deque_ref)

        logger.info(
            "Loaded DOTA cache from %s: %d total points",
            path,
            loaded,
        )
