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

# Fraction of the previous sample below which a new cookie count is read as
# a season reset rather than a normal fluctuation.  Cookie counts only fall
# when a boost expires, and boost multipliers top out around 2-3x, so an
# expiry cannot cost 90% of the count.  A season rollover resets the same
# bakery *name* to near zero, which regresses to a negative slope that
# ``calculate_production_rate`` clamps to 0 -- making the leader look
# stalled and every boost EV negative.
SEASON_RESET_DROP_RATIO = 0.1


def _is_season_reset(previous: float, current: float) -> bool:
    """True when *current* is too far below *previous* to be a boost expiry."""
    if previous <= 0:
        return False
    return current < previous * SEASON_RESET_DROP_RATIO


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

        Histories are keyed by bakery *name*, which is not season-scoped:
        the same bakery competing in the next season starts again from
        near zero under the same key.  A collapse to below
        ``SEASON_RESET_DROP_RATIO`` of the last sample is therefore taken
        as a reset and the bakery's history is dropped, so the production
        rate is regressed over the new season only.
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at

        for bakery in snapshot.bakeries:
            key = bakery.name
            display_cookies = int(bakery.tx_count) / cookie_scale
            dq = self._history.get(key)
            if dq is None:
                dq = deque(maxlen=self._max_history)
                self._history[key] = dq
            elif dq and _is_season_reset(dq[-1][1], display_cookies):
                logger.info(
                    "Cookie count for %s collapsed %.0f -> %.0f; "
                    "treating as season reset and clearing its history",
                    key,
                    dq[-1][1],
                    display_cookies,
                )
                dq.clear()
            dq.append((snapshot.fetched_at, display_cookies))

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

    def load_from_file(self, path: str, *, max_age: float | None = None) -> None:
        """Load previously saved history from a JSON file.

        Silently does nothing if the file is missing or corrupted.
        Existing in-memory data is replaced on successful load.

        Individual points are validated: anything unusable (``null``, a
        string, ``NaN``, a wrong-length entry, a negative value, a
        future-dated timestamp) is dropped and counted rather than
        raising, because every manager loads its cache in ``__init__``
        and one bad value used to abort MaxPane startup for every
        dashboard.

        Parameters
        ----------
        max_age:
            Drop points older than this many seconds.  Restoring the full
            file regardless of age is what made production rates wrong for
            the first hour after a restart: ``calculate_production_rate``
            regresses over whatever is in the deque, so a day-old cluster
            plus a fresh one yields the long-run average rate, and a
            season's worth of stale points yields a negative slope clamped
            to 0 (leader_rate=0, every boost EV negative, gap_analysis
            reporting gap_rate 0).  Callers should pass the sparkline
            window -- ``max_history * poll_interval``.  ``None`` keeps the
            old load-everything behaviour.
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
            good, dropped = coerce_points(points, now=now, max_age=max_age)
            skipped += dropped
            if not good:
                # Every point aged out (or was unusable): leave the bakery
                # untracked rather than seeding an empty deque.
                continue
            self._history[name] = deque(good, maxlen=self._max_history)
            loaded += 1

        if skipped:
            logger.warning(
                "Skipped %d unusable or expired point(s) while loading cache %s",
                skipped,
                path,
            )
        logger.info(
            "Loaded cache history from %s: %d bakeries, up to %d points each",
            path,
            loaded,
            self._max_history,
        )
