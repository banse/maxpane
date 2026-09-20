"""In-memory cache with time-series accumulation for FrenPet data.

The ``FrenPetCache`` stores the most recent ``FrenPetSnapshot`` and
accumulates per-pet score histories over time so the dashboard can
render sparklines and trend indicators.

Everything but ``update()``, the per-pet dict and the named getters is
inherited from ``data/series_cache.SeriesCache``; see that module for
the persistence contract and for why ``record()`` drops ``None``
instead of zero-filling.  The three population-level series are declared
as ``SERIES`` and therefore remain **public deque attributes** --
``frenpet_manager.py`` reads them by name when it assembles the widget
dict, and so do this file's tests.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.

Schema versioning
-----------------
``schema_version`` 1 files hold only ``histories`` (the per-pet score
series).  The three population-level series -- ``active_pets_history``,
``total_score_history`` and ``battle_rate_history`` -- were accumulated
on every poll and rendered as the Score Trends sparklines, but
``save_to_file`` never wrote them, so they were rebuilt from zero on
every restart and the overview's three trend lines were flat for the
first few minutes of every session.

Version 2 persists them.  The upgrade is purely additive, so a v1 file
loads as "no population history yet":

* **Kept in full** -- ``histories``.  Its on-disk shape is unchanged and
  a v1 file's per-pet series is loaded exactly as before.
* **Started empty** -- the three population series, because a v1 file
  simply does not contain them.  A missing key is absence, not
  corruption: it must not be logged as an error and must never be a
  reason to drop the per-pet histories that *are* there.

Nothing is discarded on upgrade.  There is no v2 -> v1 downgrade path;
an older build reading a v2 file ignores the keys it does not know.

The key is ``schema_version`` and the value is 2, and neither may move:
renaming it to the base class's default ``"version"`` would make every
existing ``~/.maxpane/frenpet_cache.json`` read as v1 and start the
three population series empty -- the exact regression schema 2 exists
to fix.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from maxpane_dashboard.data.frenpet_models import FrenPetSnapshot
from maxpane_dashboard.data.series_cache import (
    SeriesCache,
    SeriesSpec,
    TimeSeriesPoint,
)

logger = logging.getLogger(__name__)

__all__ = ["FrenPetCache", "TimeSeriesPoint"]

# On-disk schema version.  Bumped to 2 when the population-level series
# started being persisted; see the module docstring for what a pre-v2
# load keeps and what it starts empty.
_CACHE_SCHEMA_VERSION = 2

#: Population-level series persisted from v2 on.  Attribute name doubles
#: as the JSON key.
_POPULATION_SERIES = (
    "active_pets_history",
    "total_score_history",
    "battle_rate_history",
)

# The persisted key order, oldest file first.  ``SeriesCache._payload``
# writes ``saved_at``/``max_history`` before the version key and the
# declared series before ``extra_payload``; this file has always led with
# ``schema_version`` and put ``histories`` ahead of the three population
# series.  Nothing reads a JSON object's key order, but a save that
# reshuffles a user's file makes every backup diff unreadable for no gain.
_PAYLOAD_KEY_ORDER = (
    "schema_version",
    "saved_at",
    "max_history",
    "histories",
    *_POPULATION_SERIES,
)


class FrenPetCache(SeriesCache):
    """Caches FrenPet data and accumulates per-pet score time-series.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per pet.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    SERIES = tuple(SeriesSpec(name) for name in _POPULATION_SERIES)
    VERSION_KEY = "schema_version"
    VERSION = _CACHE_SCHEMA_VERSION
    NOUN = "FrenPet cache"
    SIZE_NOUN = "pets"

    active_pets_history: deque[TimeSeriesPoint]
    total_score_history: deque[TimeSeriesPoint]
    battle_rate_history: deque[TimeSeriesPoint]
    _latest: FrenPetSnapshot | None

    def __init__(self, max_history: int = 120) -> None:
        super().__init__(max_history)
        # Keyed by ``int`` pet id; the JSON keys are ``str(pid)``.
        self._pet_histories: dict[int, deque[TimeSeriesPoint]] = {}
        # Number of pet histories the last load restored, or ``None``
        # when the load bailed out on a malformed ``histories`` value.
        # Read only by _log_loaded, which must stay silent in that case.
        self._loaded_pets: int | None = None
        # Schema version of the file the last load read, so the one
        # message about a pre-v2 file can be emitted from ``restore_extra``
        # -- the first hook after ``before_load`` that knows both the
        # file's name and how many pets came out of it, the two numbers
        # that message exists to state.
        self._loaded_version: int = self.VERSION

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(
        self, snapshot: FrenPetSnapshot, battle_rate: float | None = None
    ) -> None:
        """Store latest snapshot, accumulate score and population histories.

        Score histories are recorded for every managed pet in the
        snapshot.  Each data point is ``(fetched_at, score)``.

        ``battle_rate is None`` means "the attacks feed could not be
        read this cycle", and the point is dropped rather than recorded
        as ``0.0``.  This series is persisted, so a sentinel zero written
        during an outage is indistinguishable afterwards from a genuine
        lull and drags the Battles sparkline's scale down for the rest of
        the history's life (CLAUDE.md: *a failed read is ``None``, never
        ``0``*).
        """
        self._mark(snapshot)
        ts = snapshot.fetched_at

        # Population-level time series
        self.record("active_pets_history", ts, snapshot.population.active)
        total_score = sum(float(p.score) for p in snapshot.population.pets)
        self.record("total_score_history", ts, total_score)
        self.record("battle_rate_history", ts, battle_rate)

        managed_ids: set[int] = set()
        for pet in snapshot.managed_pets:
            pet_id = pet.id
            managed_ids.add(pet_id)
            self._pet_series(pet_id).append(
                (snapshot.fetched_at, float(pet.score))
            )

        # Also record score histories for top pets (leaderboard sparklines).
        # Skip pets already recorded as managed to avoid duplicate entries.
        for pet in snapshot.top_pets[:10]:
            pet_id = pet.id
            if pet_id in managed_ids:
                continue
            self._pet_series(pet_id).append(
                (snapshot.fetched_at, float(pet.score))
            )

    def _pet_series(self, pet_id: int) -> deque[TimeSeriesPoint]:
        """Return the history deque for ``pet_id``, creating it if new."""
        dq = self._pet_histories.get(pet_id)
        if dq is None:
            dq = deque(maxlen=self._max_history)
            self._pet_histories[pet_id] = dq
        return dq

    def get_pet_score_history(self, pet_id: int) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, score), ...]`` for a single pet.

        Returns an empty list if the pet has never been seen.
        """
        dq = self._pet_histories.get(pet_id)
        if dq is None:
            return []
        return list(dq)

    def get_top_pet_score_histories(
        self, pet_ids: list[int]
    ) -> dict[int, list[TimeSeriesPoint]]:
        """Return score histories for a specific set of pet IDs.

        Useful for retrieving sparkline data for leaderboard pets.
        Missing IDs are returned with empty lists.
        """
        return {pid: self.get_pet_score_history(pid) for pid in pet_ids}

    def get_all_histories(self) -> dict[int, list[TimeSeriesPoint]]:
        """Return score histories for every tracked pet."""
        return {pid: list(dq) for pid, dq in self._pet_histories.items()}

    @property
    def history_size(self) -> int:
        """Number of distinct pets being tracked."""
        return len(self._pet_histories)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def extra_payload(self) -> dict[str, Any]:
        """The per-pet histories; the three population series are ``SERIES``."""
        return {
            "histories": {
                str(pid): [list(pt) for pt in dq]
                for pid, dq in self._pet_histories.items()
            }
        }

    def _payload(self) -> dict[str, Any]:
        """The saved payload, in this file's historical key order::

            {
                "schema_version": 2,
                "saved_at": <float>,
                "max_history": <int>,
                "histories": {
                    "<pet_id>": [[ts, score], ...],
                    ...
                },
                "active_pets_history": [[ts, count], ...],
                "total_score_history": [[ts, score], ...],
                "battle_rate_history": [[ts, per_hour], ...]
            }

        The three population series are what the overview's Score Trends
        sparklines draw.  They were accumulated every poll and dropped on
        exit until schema 2; see the module docstring.
        """
        payload = super()._payload()
        ordered = {k: payload.pop(k) for k in _PAYLOAD_KEY_ORDER if k in payload}
        # Anything unexpected still gets written rather than dropped.
        ordered.update(payload)
        return ordered

    def before_load(self, payload: dict[str, Any], version: int) -> None:
        """Remember the file's schema version for :meth:`restore_extra`.

        Nothing has to be migrated: a pre-v2 file simply has no
        population keys, and a missing key coerces to "no points", so the
        three series start empty on their own.  What is owed is the one
        info line saying so, and that needs the pet count.
        """
        self._loaded_version = version

    def restore_extra(
        self,
        payload: dict[str, Any],
        *,
        path: str,
        now: float,
        max_age: float | None = None,
    ) -> int:
        """Rebuild the per-pet histories from ``payload["histories"]``.

        Merge, not replace: a pet id already tracked in memory but absent
        from the file keeps its deque.  Every caller loads before its
        first ``update()`` so nothing live depends on the choice, but it
        is the shape all three keyed caches share and it is pinned rather
        than left to drift (follow-up #48).

        ``max_age`` is deliberately not forwarded: these histories have
        never been windowed on load, and starting now would silently
        shorten every user's restored sparkline (follow-up #42).
        """
        raw = payload.get("histories", {})
        if not isinstance(raw, dict):
            logger.warning(
                "%s file %s has unexpected format, skipping", self.NOUN, path
            )
            self._loaded_pets = None
            return 0

        series, skipped = self.coerce_keyed(raw, now=now)
        loaded = 0
        for key, good in series.items():
            # ``coerce_keyed`` hands back string keys (JSON has no other
            # kind); the in-memory dict is keyed by the int pet id the
            # manager and the widgets look up.
            try:
                pid = int(key)
            except (ValueError, TypeError):
                continue
            self._pet_histories[pid] = deque(good, maxlen=self._max_history)
            loaded += 1

        self._loaded_pets = loaded
        if self._loaded_version < self.VERSION:
            logger.info(
                "%s %s is schema v%d; per-pet history (%d pets) "
                "kept in full, population trend series start empty because "
                "that version never wrote them. Nothing discarded.",
                self.NOUN,
                path,
                self._loaded_version,
                loaded,
            )
        return skipped

    def _log_loaded(self, path: str, loaded: int) -> None:
        """The closing info line: pets first, then the population points."""
        if self._loaded_pets is None:
            return
        logger.info(
            "Loaded %s from %s: %d pets, %d population points, "
            "up to %d points each",
            self.NOUN,
            path,
            self._loaded_pets,
            loaded,
            self._max_history,
        )
