"""In-memory cache with time-series accumulation for Cat Town data.

The ``CatTownCache`` stores the most recent ``CatTownSnapshot`` and
accumulates price, volume, burn, and prize pool histories over time so
the dashboard can render sparklines and trend indicators.

Everything but ``update()`` and the named getters is inherited from
``data/series_cache.SeriesCache``; see that module for the persistence
contract and for why ``record()`` drops ``None`` instead of zero-filling.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import logging
from collections import deque

from maxpane_dashboard.data.cattown_models import CatTownSnapshot
from maxpane_dashboard.data.series_cache import (
    SeriesCache,
    SeriesSpec,
    TimeSeriesPoint,
)

logger = logging.getLogger(__name__)

__all__ = ["CatTownCache", "TimeSeriesPoint"]


class CatTownCache(SeriesCache):
    """Caches Cat Town data and accumulates time-series histories.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    SERIES = (
        SeriesSpec("prize_pool_history"),
        SeriesSpec("leader_weight_history"),
        SeriesSpec("raffle_tickets_history"),
    )
    NOUN = "CatTown cache"

    prize_pool_history: deque[TimeSeriesPoint]
    leader_weight_history: deque[TimeSeriesPoint]
    raffle_tickets_history: deque[TimeSeriesPoint]
    _latest: CatTownSnapshot | None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(
        self,
        snapshot: CatTownSnapshot,
        leader_weight_kg: float | None = None,
        raffle_total_tickets: int | None = None,
    ) -> None:
        """Store latest snapshot, accumulate time-series data points.

        Appends one data point per series:
        - prize_pool_history: competition prize pool in KIBBLE
        - leader_weight_history: #1 fish weight in kg
        - raffle_tickets_history: total raffle tickets sold this round

        ``None`` for either optional argument means the manager could not
        read that value this cycle -- a failed raffle request, or a
        competition with no entries to take a leader from -- and the
        series simply gets no point.  It used to get a ``0``, which this
        cache then persisted: a dead raffle endpoint became "zero tickets
        sold" for as long as the file lived.
        """
        self._mark(snapshot)
        ts = snapshot.fetched_at

        self.record("prize_pool_history", ts, snapshot.competition.prize_pool_kibble)
        self.record("leader_weight_history", ts, leader_weight_kg)
        self.record("raffle_tickets_history", ts, raffle_total_tickets)

    def get_prize_pool_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, pool), ...]`` for competition prize pool."""
        return self.get_series("prize_pool_history")

    def get_leader_weight_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, kg), ...]`` for #1 fish weight."""
        return self.get_series("leader_weight_history")

    def get_raffle_tickets_history(self) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, tickets), ...]`` for raffle ticket count."""
        return self.get_series("raffle_tickets_history")
