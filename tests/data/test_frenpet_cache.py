"""Tests for FrenPetCache: time-series accumulation, limits, persistence."""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from maxpane_dashboard.data.frenpet_cache import FrenPetCache
from maxpane_dashboard.data.frenpet_models import FrenPet, FrenPetPopulation, FrenPetSnapshot


# ---------------------------------------------------------------------------
# Fixtures -- minimal valid models for snapshot construction
# ---------------------------------------------------------------------------

def _make_pet(
    pet_id: int = 1,
    score: int = 50_000,
    **overrides: object,
) -> FrenPet:
    defaults = dict(
        id=pet_id,
        score=score,
        attack_points=100,
        defense_points=80,
        level=5,
        status=0,
        last_attacked=0,
        last_attack_used=0,
        shield_expires=0,
        time_until_starving=int(time.time()) + 86400,
        staking_perks_until=0,
        wheel_last_spin=0,
        pet_wins=10,
        win_qty=10,
        loss_qty=5,
        shrooms=0,
        name=f"Pet{pet_id}",
        owner="0xabc",
    )
    defaults.update(overrides)
    return FrenPet(**defaults)  # type: ignore[arg-type]


def _make_snapshot(
    managed_pets: list[FrenPet] | None = None,
    all_pets: list[FrenPet] | None = None,
    fetched_at: float | None = None,
) -> FrenPetSnapshot:
    ts = fetched_at or time.time()
    managed = managed_pets if managed_pets is not None else [_make_pet(1, 50_000), _make_pet(2, 75_000)]
    population_pets = all_pets if all_pets is not None else managed
    population = FrenPetPopulation.from_pets(list(population_pets), now=ts)
    return FrenPetSnapshot(
        population=population,
        managed_pets=tuple(managed),
        top_pets=tuple(population_pets[:10]),
        fetched_at=ts,
    )


# ---------------------------------------------------------------------------
# Tests: Update and history accumulation
# ---------------------------------------------------------------------------

class TestFrenPetCacheUpdate:
    def test_update_stores_latest(self) -> None:
        cache = FrenPetCache(max_history=10)
        snap = _make_snapshot()
        cache.update(snap)
        assert cache.get_latest() is snap

    def test_update_records_score_history(self) -> None:
        cache = FrenPetCache(max_history=10)
        snap = _make_snapshot(
            managed_pets=[_make_pet(1, 50_000)],
            fetched_at=100.0,
        )
        cache.update(snap)

        history = cache.get_pet_score_history(1)
        assert len(history) == 1
        assert history[0] == (100.0, 50_000.0)

    def test_multiple_updates_accumulate(self) -> None:
        cache = FrenPetCache(max_history=10)

        for i in range(5):
            snap = _make_snapshot(
                managed_pets=[_make_pet(1, 50_000 + i * 100)],
                fetched_at=float(100 + i * 30),
            )
            cache.update(snap)

        history = cache.get_pet_score_history(1)
        assert len(history) == 5
        assert history[0][0] < history[-1][0]
        assert history[0][1] == 50_000.0
        assert history[-1][1] == 50_400.0

    def test_multiple_pets_tracked_independently(self) -> None:
        cache = FrenPetCache(max_history=10)
        snap = _make_snapshot(
            managed_pets=[_make_pet(1, 10_000), _make_pet(2, 20_000)],
            fetched_at=100.0,
        )
        cache.update(snap)

        h1 = cache.get_pet_score_history(1)
        h2 = cache.get_pet_score_history(2)
        assert len(h1) == 1
        assert len(h2) == 1
        assert h1[0][1] == 10_000.0
        assert h2[0][1] == 20_000.0

    def test_last_updated_tracks_latest(self) -> None:
        cache = FrenPetCache()
        assert cache.last_updated is None

        snap = _make_snapshot(fetched_at=42.0)
        cache.update(snap)
        assert cache.last_updated == 42.0


# ---------------------------------------------------------------------------
# Tests: History limits
# ---------------------------------------------------------------------------

class TestFrenPetCacheHistoryLimits:
    def test_max_history_enforced(self) -> None:
        cache = FrenPetCache(max_history=3)

        for i in range(10):
            snap = _make_snapshot(
                managed_pets=[_make_pet(1, 1000 + i)],
                fetched_at=float(i),
            )
            cache.update(snap)

        history = cache.get_pet_score_history(1)
        assert len(history) == 3
        # Should keep the last 3 entries
        assert history[0][1] == 1007.0
        assert history[1][1] == 1008.0
        assert history[2][1] == 1009.0

    def test_unknown_pet_returns_empty(self) -> None:
        cache = FrenPetCache()
        assert cache.get_pet_score_history(999) == []

    def test_get_all_histories(self) -> None:
        cache = FrenPetCache(max_history=10)
        snap = _make_snapshot(
            managed_pets=[_make_pet(1, 10_000), _make_pet(2, 20_000)],
        )
        cache.update(snap)

        all_h = cache.get_all_histories()
        assert 1 in all_h
        assert 2 in all_h
        assert len(all_h) == 2

    def test_history_size_property(self) -> None:
        cache = FrenPetCache(max_history=10)
        assert cache.history_size == 0

        snap = _make_snapshot(
            managed_pets=[_make_pet(1, 10_000), _make_pet(2, 20_000)],
        )
        cache.update(snap)
        assert cache.history_size == 2


# ---------------------------------------------------------------------------
# Tests: Empty state
# ---------------------------------------------------------------------------

class TestFrenPetCacheEmptyState:
    def test_empty_cache_returns_none(self) -> None:
        cache = FrenPetCache()
        assert cache.get_latest() is None
        assert cache.last_updated is None
        assert cache.history_size == 0

    def test_empty_snapshot_no_managed(self) -> None:
        cache = FrenPetCache()
        snap = _make_snapshot(managed_pets=[], all_pets=[_make_pet(1)])
        cache.update(snap)
        assert cache.get_latest() is snap
        # Top pets are now tracked even without managed pets (for sparklines)
        assert cache.history_size == 1


# ---------------------------------------------------------------------------
# Tests: Persistence
# ---------------------------------------------------------------------------

class TestFrenPetCachePersistence:
    def test_save_and_load_roundtrip(self) -> None:
        cache = FrenPetCache(max_history=10)

        for i in range(5):
            snap = _make_snapshot(
                managed_pets=[
                    _make_pet(1, 10_000 + i * 100),
                    _make_pet(2, 20_000 + i * 50),
                ],
                fetched_at=float(1000 + i),
            )
            cache.update(snap)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            cache.save_to_file(path)

            # Verify file exists and is valid JSON
            with open(path) as f:
                saved = json.load(f)
            assert "histories" in saved
            assert "1" in saved["histories"]
            assert len(saved["histories"]["1"]) == 5

            # Load into a fresh cache
            cache2 = FrenPetCache(max_history=10)
            cache2.load_from_file(path)

            h1 = cache2.get_pet_score_history(1)
            assert len(h1) == 5
            assert h1[0] == (1000.0, 10_000.0)
            assert h1[-1] == (1004.0, 10_400.0)

            h2 = cache2.get_pet_score_history(2)
            assert len(h2) == 5
        finally:
            os.unlink(path)

    def test_load_missing_file_is_silent(self) -> None:
        cache = FrenPetCache()
        cache.load_from_file("/nonexistent/path/frenpet_cache.json")
        assert cache.get_latest() is None

    def test_load_corrupted_file_is_silent(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {{{")
            path = f.name

        try:
            cache = FrenPetCache()
            cache.load_from_file(path)
            assert cache.history_size == 0
        finally:
            os.unlink(path)

    def test_save_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "frenpet_cache.json")
            cache = FrenPetCache(max_history=5)
            snap = _make_snapshot(fetched_at=1.0)
            cache.update(snap)
            cache.save_to_file(path)
            assert os.path.exists(path)

    def test_load_preserves_max_history(self) -> None:
        """Loading into a cache with smaller max_history truncates correctly."""
        cache = FrenPetCache(max_history=10)
        for i in range(8):
            snap = _make_snapshot(
                managed_pets=[_make_pet(1, 1000 + i)],
                fetched_at=float(i),
            )
            cache.update(snap)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            cache.save_to_file(path)

            cache2 = FrenPetCache(max_history=3)
            cache2.load_from_file(path)
            # All 8 points loaded but deque maxlen=3 keeps last 3
            h = cache2.get_pet_score_history(1)
            assert len(h) == 3
            assert h[0][1] == 1005.0
        finally:
            os.unlink(path)
