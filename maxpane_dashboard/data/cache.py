"""In-memory cache with TTL and time-series accumulation.

The ``DataCache`` stores the most recent ``GameSnapshot`` and
accumulates per-bakery cookie counts over time so the dashboard can
render sparklines and trend indicators.

There are no *fixed* series here: the history is a dict keyed by bakery
name, so ``SERIES`` is empty and the whole payload rides on the
``extra_payload``/``restore_extra`` hooks.  Everything else -- the
atomic write, the open/JSON-decode guard, the ``isinstance(payload,
dict)`` guard this loader used to lack, the injected clock and the
"Skipped ..." warning -- is inherited from
``data/series_cache.SeriesCache``.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from maxpane_dashboard.data.series_cache import (
    SeriesCache,
    TimeSeriesPoint,
)
from maxpane_dashboard.data.snapshot import GameSnapshot

logger = logging.getLogger(__name__)

__all__ = ["DataCache", "TimeSeriesPoint", "SEASON_RESET_DROP_RATIO"]

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


class DataCache(SeriesCache):
    """Caches API responses and accumulates time-series data.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per bakery. At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    #: No fixed series: every series here is keyed by bakery name.
    SERIES = ()
    NOUN = "cache history"
    SIZE_NOUN = "bakeries"

    _latest: GameSnapshot | None

    def __init__(self, max_history: int = 120) -> None:
        super().__init__(max_history)
        self._history: dict[str, deque[TimeSeriesPoint]] = {}
        # Number of bakeries the last load restored, or ``None`` when the
        # load bailed out on a malformed ``histories`` value.  Read only
        # by _log_loaded, which must stay silent in that case.
        self._loaded_bakeries: int | None = None

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
        self._mark(snapshot)

        # A failed bakeries fetch is ``None`` and records nothing -- never a
        # point, never a reset (follow-up #35).
        for bakery in snapshot.bakeries or ():
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
    def history_size(self) -> int:
        """Number of distinct bakeries being tracked."""
        return len(self._history)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def extra_payload(self) -> dict[str, Any]:
        """The one key this cache persists beyond the base's two.

        The written file is ``{"saved_at", "max_history", "histories"}``
        and carries **no version key**; it never has, and adding one
        would make an older MaxPane read its own file as a downgrade.
        """
        return {
            "histories": {
                name: [list(pt) for pt in dq]
                for name, dq in self._history.items()
            }
        }

    def restore_extra(
        self,
        payload: dict[str, Any],
        *,
        path: str,
        now: float,
        max_age: float | None = None,
    ) -> int:
        """Rebuild ``_history`` from ``payload["histories"]``.

        ``max_age`` is the caller's window -- ``manager.py`` passes the
        sparkline window, because ``calculate_production_rate`` regresses
        over whatever is in the deque and a day-old cluster plus a fresh
        one yields the long-run average rate.

        A bakery whose points have all aged out (or were all unusable) is
        left **untracked** rather than seeded with an empty deque: an
        empty deque is a bakery we are following with nothing to show,
        and ``history_size`` counts it.
        """
        raw = payload.get("histories", {})
        if not isinstance(raw, dict):
            logger.warning(
                "%s file %s has unexpected format, skipping", self.NOUN, path
            )
            self._loaded_bakeries = None
            return 0

        series, skipped = self.coerce_keyed(raw, now=now, max_age=max_age)
        loaded = 0
        for name, good in series.items():
            if not good:
                continue
            self._history[name] = deque(good, maxlen=self._max_history)
            loaded += 1

        self._loaded_bakeries = loaded
        return skipped

    def _log_loaded(self, path: str, loaded: int) -> None:
        """The closing info line, in bakeries rather than points."""
        if self._loaded_bakeries is None:
            return
        logger.info(
            "Loaded %s from %s: %d bakeries, up to %d points each",
            self.NOUN,
            path,
            self._loaded_bakeries,
            self._max_history,
        )
