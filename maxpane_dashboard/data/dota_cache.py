"""In-memory cache with time-series accumulation for DOTA dashboard data.

The ``DOTACache`` stores the most recent ``DOTASnapshot`` and accumulates
lane frontline histories over time so the dashboard can render sparklines.

Everything but ``update()`` and the named getters is inherited from
``data/series_cache.SeriesCache``; see that module for the persistence
contract and for why ``record()`` drops ``None`` instead of zero-filling.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import logging
from collections import deque

from maxpane_dashboard.data.dota_models import DOTASnapshot
from maxpane_dashboard.data.series_cache import (
    SeriesCache,
    SeriesSpec,
    TimeSeriesPoint,
)

logger = logging.getLogger(__name__)

__all__ = ["DOTACache", "TimeSeriesPoint"]

# Lane key in ``game_state.lanes`` -> the series it feeds.
_LANE_SERIES = (("top", "top_history"), ("mid", "mid_history"), ("bot", "bot_history"))


class DOTACache(SeriesCache):
    """Caches DOTA data and accumulates lane frontline time-series.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    SERIES = (
        SeriesSpec("top_history"),
        SeriesSpec("mid_history"),
        SeriesSpec("bot_history"),
    )
    NOUN = "DOTA cache"

    top_history: deque[TimeSeriesPoint]
    mid_history: deque[TimeSeriesPoint]
    bot_history: deque[TimeSeriesPoint]
    _latest: DOTASnapshot | None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(self, snapshot: DOTASnapshot) -> None:
        """Store latest snapshot, accumulate lane frontline data points.

        Extracts frontline values from ``game_state.lanes`` for the three
        lanes (top, mid, bot) and appends ``(timestamp, frontline_value)``
        to each history deque.

        A lane the game state does not carry -- or a game state that
        could not be read at all -- records **nothing** for that lane.
        A zero here is a real frontline position (the lane is level), so
        zero-filling an absent lane would draw a battle that never
        happened.
        """
        self._mark(snapshot)
        ts = snapshot.fetched_at

        if snapshot.game_state is not None and snapshot.game_state.lanes:
            lanes = snapshot.game_state.lanes
            for lane_key, series_name in _LANE_SERIES:
                if lane_key in lanes:
                    self.record(series_name, ts, lanes[lane_key].frontline)

    def get_top_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, frontline), ...]`` for the top lane."""
        return self.get_series("top_history")

    def get_mid_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, frontline), ...]`` for the mid lane."""
        return self.get_series("mid_history")

    def get_bot_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, frontline), ...]`` for the bot lane."""
        return self.get_series("bot_history")
