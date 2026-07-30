"""In-memory cache with time-series accumulation for FrenPet data.

The ``FrenPetCache`` stores the most recent ``FrenPetSnapshot`` and
accumulates per-pet score histories over time so the dashboard can
render sparklines and trend indicators.

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
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from typing import Any

from maxpane_dashboard.data.frenpet_models import FrenPetSnapshot
from maxpane_dashboard.data.series_points import coerce_points

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, score)
TimeSeriesPoint = tuple[float, float]

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


class FrenPetCache:
    """Caches FrenPet data and accumulates per-pet score time-series.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per pet.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self._pet_histories: dict[int, deque[TimeSeriesPoint]] = {}
        self._latest: FrenPetSnapshot | None = None
        self._last_updated: float | None = None
        # Population-level time series
        self.active_pets_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.total_score_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.battle_rate_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(self, snapshot: FrenPetSnapshot, battle_rate: float = 0.0) -> None:
        """Store latest snapshot, accumulate score and population histories.

        Score histories are recorded for every managed pet in the
        snapshot.  Each data point is ``(fetched_at, score)``.
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at
        ts = snapshot.fetched_at

        # Population-level time series
        self.active_pets_history.append(
            (ts, float(snapshot.population.active))
        )
        total_score = sum(float(p.score) for p in snapshot.population.pets)
        self.total_score_history.append((ts, total_score))
        self.battle_rate_history.append((ts, battle_rate))

        managed_ids: set[int] = set()
        for pet in snapshot.managed_pets:
            pet_id = pet.id
            managed_ids.add(pet_id)
            if pet_id not in self._pet_histories:
                self._pet_histories[pet_id] = deque(maxlen=self._max_history)
            self._pet_histories[pet_id].append(
                (snapshot.fetched_at, float(pet.score))
            )

        # Also record score histories for top pets (leaderboard sparklines).
        # Skip pets already recorded as managed to avoid duplicate entries.
        for pet in snapshot.top_pets[:10]:
            pet_id = pet.id
            if pet_id in managed_ids:
                continue
            if pet_id not in self._pet_histories:
                self._pet_histories[pet_id] = deque(maxlen=self._max_history)
            self._pet_histories[pet_id].append(
                (snapshot.fetched_at, float(pet.score))
            )

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

    def get_latest(self) -> FrenPetSnapshot | None:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of distinct pets being tracked."""
        return len(self._pet_histories)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        File format::

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
        payload: dict[str, Any] = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "saved_at": time.time(),
            "max_history": self._max_history,
            "histories": {
                str(pid): [list(pt) for pt in dq]
                for pid, dq in self._pet_histories.items()
            },
        }
        for name in _POPULATION_SERIES:
            payload[name] = [
                [float(ts), float(val)] for (ts, val) in getattr(self, name)
            ]

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "FrenPet cache saved to %s (%d pets, %d population points)",
                path,
                len(self._pet_histories),
                sum(len(getattr(self, name)) for name in _POPULATION_SERIES),
            )
        except OSError as exc:
            logger.warning("Failed to save FrenPet cache: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def load_from_file(self, path: str, *, now: float | None = None) -> None:
        """Load previously saved history from a JSON file.

        Silently does nothing if the file is missing or corrupted.
        Existing in-memory data is replaced on successful load.

        Individual points are validated: anything unusable (``null``, a
        string, ``NaN``, a wrong-length entry, a negative score, a
        future-dated timestamp) is dropped and counted rather than
        raising, because every manager loads its cache in ``__init__``
        and one bad value used to abort MaxPane startup for every
        dashboard.

        A pre-v2 file has no population series; that is loaded as "no
        history yet" and never as an error (see the module docstring).

        Parameters
        ----------
        now:
            Reference clock, in epoch seconds, used to validate the
            persisted points -- a point dated in the future is
            corruption, not history.  Passing it explicitly is what
            keeps this method a pure function of its inputs: reaching
            for ``time.time()`` internally makes the same file load
            differently depending on when it is read, and on a machine
            whose clock ran fast when the file was *written* it silently
            empties the series it just saved.  ``None`` falls back to the
            wall clock for callers that genuinely mean "now";
            ``FrenPetManager`` passes an explicit one.
        """
        reference = time.time() if now is None else now
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No FrenPet cache file to load (%s): %s", path, exc)
            return

        if not isinstance(payload, dict):
            logger.warning(
                "FrenPet cache file %s has unexpected format, skipping", path
            )
            return

        try:
            version = int(payload.get("schema_version") or 1)
        except (TypeError, ValueError):
            version = 1

        histories = payload.get("histories", {})
        if not isinstance(histories, dict):
            logger.warning(
                "FrenPet cache file %s has unexpected format, skipping", path
            )
            return

        loaded = 0
        skipped = 0
        for pid_str, points in histories.items():
            if not isinstance(points, list):
                continue
            try:
                pid = int(pid_str)
            except (ValueError, TypeError):
                continue
            good, dropped = coerce_points(points, now=reference)
            skipped += dropped
            dq: deque[TimeSeriesPoint] = deque(good, maxlen=self._max_history)
            self._pet_histories[pid] = dq
            loaded += 1

        # Population-level series (schema 2+).  ``coerce_points`` maps a
        # missing key -- every pre-v2 file -- to ``([], 0)``, so an
        # upgrade starts these empty and keeps the per-pet histories
        # above untouched.
        population_loaded = 0
        for name in _POPULATION_SERIES:
            series: deque[TimeSeriesPoint] = getattr(self, name)
            good, dropped = coerce_points(payload.get(name), now=reference)
            skipped += dropped
            series.clear()
            series.extend(good)
            population_loaded += len(series)

        if version < _CACHE_SCHEMA_VERSION:
            logger.info(
                "FrenPet cache %s is schema v%d; per-pet history (%d pets) "
                "kept in full, population trend series start empty because "
                "that version never wrote them. Nothing discarded.",
                path,
                version,
                loaded,
            )

        if skipped:
            logger.warning(
                "Skipped %d unusable point(s) while loading FrenPet cache %s",
                skipped,
                path,
            )
        logger.info(
            "Loaded FrenPet cache from %s: %d pets, %d population points, "
            "up to %d points each",
            path,
            loaded,
            population_loaded,
            self._max_history,
        )
