"""In-memory cache with TTL and time-series accumulation.

The ``DataCache`` stores the most recent ``GameSnapshot`` and
accumulates per-bakery cookie counts over time so the dashboard can
render sparklines and trend indicators.

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

from maxpane_dashboard.data.series_points import coerce_points
from maxpane_dashboard.data.snapshot import GameSnapshot

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, cookie_count)
TimeSeriesPoint = tuple[float, float]


class DataCache:
    """Caches API responses and accumulates time-series data.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per bakery. At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self._history: dict[str, deque[TimeSeriesPoint]] = {}
        self._latest: GameSnapshot | None = None
        self._last_updated: float | None = None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(self, snapshot: GameSnapshot, cookie_scale: int = 10_000) -> None:
        """Store the latest snapshot and append cookie counts to history.

        Each bakery's ``tx_count`` (effective/boosted cookies) is divided by
        ``cookie_scale`` to convert from raw on-chain values to display
        cookies, then recorded as a ``(timestamp, value)`` pair keyed by
        bakery name.
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at

        for bakery in snapshot.bakeries:
            key = bakery.name
            if key not in self._history:
                self._history[key] = deque(maxlen=self._max_history)
            display_cookies = int(bakery.tx_count) / cookie_scale
            self._history[key].append(
                (snapshot.fetched_at, display_cookies)
            )

    def get_latest(self) -> GameSnapshot | None:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    def get_cookie_history(self, bakery_name: str) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, cookies), ...]`` for a single bakery.

        Returns an empty list if the bakery has never been seen.
        """
        dq = self._history.get(bakery_name)
        if dq is None:
            return []
        return list(dq)

    def get_all_histories(self) -> dict[str, list[TimeSeriesPoint]]:
        """Return cookie histories for every tracked bakery."""
        return {name: list(dq) for name, dq in self._history.items()}

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of distinct bakeries being tracked."""
        return len(self._history)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        File format::

            {
                "saved_at": <float>,
                "max_history": <int>,
                "histories": {
                    "<bakery_name>": [[ts, cookies], ...],
                    ...
                }
            }
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
            "histories": {
                name: [list(pt) for pt in dq]
                for name, dq in self._history.items()
            },
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info("Cache history saved to %s (%d bakeries)", path, len(self._history))
        except OSError as exc:
            logger.warning("Failed to save cache history: %s", exc)
            # Clean up temp file if rename failed
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
            logger.info("No cache file to load (%s): %s", path, exc)
            return

        histories = payload.get("histories", {})
        if not isinstance(histories, dict):
            logger.warning("Cache file %s has unexpected format, skipping", path)
            return

        loaded = 0
        skipped = 0
        now = time.time()
        for name, points in histories.items():
            if not isinstance(points, list):
                continue
            good, dropped = coerce_points(points, now=now)
            skipped += dropped
            self._history[name] = deque(good, maxlen=self._max_history)
            loaded += 1

        if skipped:
            logger.warning(
                "Skipped %d unusable point(s) while loading cache %s",
                skipped,
                path,
            )
        logger.info(
            "Loaded cache history from %s: %d bakeries, up to %d points each",
            path,
            loaded,
            self._max_history,
        )
