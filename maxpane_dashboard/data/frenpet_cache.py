"""In-memory cache with time-series accumulation for FrenPet data.

The ``FrenPetCache`` stores the most recent ``FrenPetSnapshot`` and
accumulates per-pet score histories over time so the dashboard can
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

from maxpane_dashboard.data.frenpet_models import FrenPetSnapshot

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, score)
TimeSeriesPoint = tuple[float, float]


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
                "saved_at": <float>,
                "max_history": <int>,
                "histories": {
                    "<pet_id>": [[ts, score], ...],
                    ...
                }
            }
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
            "histories": {
                str(pid): [list(pt) for pt in dq]
                for pid, dq in self._pet_histories.items()
            },
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "FrenPet cache saved to %s (%d pets)", path, len(self._pet_histories)
            )
        except OSError as exc:
            logger.warning("Failed to save FrenPet cache: %s", exc)
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
            logger.info("No FrenPet cache file to load (%s): %s", path, exc)
            return

        histories = payload.get("histories", {})
        if not isinstance(histories, dict):
            logger.warning(
                "FrenPet cache file %s has unexpected format, skipping", path
            )
            return

        loaded = 0
        for pid_str, points in histories.items():
            if not isinstance(points, list):
                continue
            try:
                pid = int(pid_str)
            except (ValueError, TypeError):
                continue
            dq: deque[TimeSeriesPoint] = deque(maxlen=self._max_history)
            for pt in points:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    dq.append((float(pt[0]), float(pt[1])))
            self._pet_histories[pid] = dq
            loaded += 1

        logger.info(
            "Loaded FrenPet cache from %s: %d pets, up to %d points each",
            path,
            loaded,
            self._max_history,
        )
