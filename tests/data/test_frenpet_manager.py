"""Tests for FrenPetManager: orchestration, analytics, alert generation."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.data.frenpet_models import FrenPet, FrenPetPopulation, FrenPetSnapshot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_pet(
    pet_id: int = 1,
    score: int = 50_000,
    **overrides: object,
) -> FrenPet:
    now = int(time.time())
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
        time_until_starving=now + 86400 * 3,  # 3 days out (safe)
        staking_perks_until=0,
        wheel_last_spin=0,
        pet_wins=20,
        win_qty=20,
        loss_qty=10,
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
    managed = managed_pets if managed_pets is not None else [
        _make_pet(1, 50_000),
        _make_pet(2, 75_000),
    ]
    pop_pets = all_pets or [
        _make_pet(1, 50_000),
        _make_pet(2, 75_000),
        _make_pet(3, 120_000, owner="0xother"),
        _make_pet(4, 200_000, owner="0xother"),
        _make_pet(5, 350_000, owner="0xother"),
    ]
    population = FrenPetPopulation.from_pets(pop_pets, now=ts)
    return FrenPetSnapshot(
        population=population,
        managed_pets=tuple(managed),
        top_pets=tuple(pop_pets[:10]),
        fetched_at=ts,
    )


EXPECTED_KEYS = {
    # General view
    "population_stats",
    "score_distribution",
    "top_pets",
    "recent_attacks",
    "global_battle_rate",
    # Wallet view
    "managed_pets",
    "total_score",
    "combined_win_rate",
    "pet_score_histories",
    "alerts",
    # Pet view
    "pet_evaluations",
    "market_conditions",
    "threat_levels",
    # Signals
    "pet_velocities",
    "pet_ranks",
    # Overview hero cards
    "fp_reward_pool",
    "game_start_timestamp",
    "top_pet",
    "overview_total_score",
    # Overview signals
    "global_win_rate",
    "shield_rate",
    "top_dominance",
    "overview_recommendation",
    # Overview best plays
    "top_earners",
    "rising_stars",
    # Overview sparklines
    "overview_score_histories",
    # Meta
    "error_count",
    "last_updated_seconds_ago",
    "poll_interval",
}


# ---------------------------------------------------------------------------
# Tests: basic fetch_and_compute
# ---------------------------------------------------------------------------

class TestFrenPetManagerFetchAndCompute:
    @pytest.mark.asyncio
    async def test_all_expected_keys_present(self) -> None:
        manager = FrenPetManager(
            poll_interval=30,
            wallet_address="0xabc",
        )
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        assert EXPECTED_KEYS.issubset(result.keys()), (
            f"Missing keys: {EXPECTED_KEYS - result.keys()}"
        )

    @pytest.mark.asyncio
    async def test_managed_pets_returned(self) -> None:
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        assert len(result["managed_pets"]) == 2
        assert result["total_score"] == 125_000.0
        # 20 wins / 30 total for each pet => combined 40 / 60 => ~66.67%
        assert abs(result["combined_win_rate"] - 66.666) < 0.1

    @pytest.mark.asyncio
    async def test_population_stats_computed(self) -> None:
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        stats = result["population_stats"]
        assert stats["total"] == 5
        assert stats["total_score"] > 0

    @pytest.mark.asyncio
    async def test_pet_evaluations_per_managed_pet(self) -> None:
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        evals = result["pet_evaluations"]
        assert 1 in evals
        assert 2 in evals
        assert "phase" in evals[1]
        assert "tod_status" in evals[1]
        assert "battle_efficiency" in evals[1]

    @pytest.mark.asyncio
    async def test_score_distribution_computed(self) -> None:
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        dist = result["score_distribution"]
        assert isinstance(dist, dict)
        assert sum(dist.values()) == 5  # all 5 pets classified


# ---------------------------------------------------------------------------
# Tests: spectator mode (no wallet)
# ---------------------------------------------------------------------------

class TestFrenPetManagerSpectatorMode:
    @pytest.mark.asyncio
    async def test_no_wallet_empty_managed(self) -> None:
        manager = FrenPetManager(wallet_address=None)
        snapshot = _make_snapshot(managed_pets=[])

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        assert result["managed_pets"] == []
        assert result["total_score"] == 0.0
        assert result["combined_win_rate"] == 0.0
        assert result["pet_evaluations"] == {}
        assert result["pet_velocities"] == {}
        assert result["pet_ranks"] == {}
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_spectator_still_has_population_stats(self) -> None:
        manager = FrenPetManager(wallet_address=None)
        snapshot = _make_snapshot(managed_pets=[])

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        assert result["population_stats"]["total"] == 5
        assert len(result["top_pets"]) == 5


# ---------------------------------------------------------------------------
# Tests: alert generation
# ---------------------------------------------------------------------------

class TestFrenPetManagerAlerts:
    @pytest.mark.asyncio
    async def test_critical_tod_alert(self) -> None:
        """Pet starving in < 6 hours triggers critical alert."""
        now = int(time.time())
        critical_pet = _make_pet(
            pet_id=1,
            score=50_000,
            time_until_starving=now + 3600 * 2,  # 2 hours
        )
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot(managed_pets=[critical_pet])

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        alerts = result["alerts"]
        assert len(alerts) >= 1
        critical = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical) == 1
        assert critical[0]["pet_id"] == 1
        assert critical[0]["type"] == "tod_critical"

    @pytest.mark.asyncio
    async def test_warning_tod_alert(self) -> None:
        """Pet starving in 6-24 hours triggers warning alert."""
        now = int(time.time())
        warning_pet = _make_pet(
            pet_id=1,
            score=50_000,
            time_until_starving=now + 3600 * 12,  # 12 hours
        )
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot(managed_pets=[warning_pet])

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        alerts = result["alerts"]
        assert len(alerts) >= 1
        warnings = [a for a in alerts if a["severity"] == "warning"]
        assert len(warnings) == 1
        assert warnings[0]["type"] == "tod_warning"

    @pytest.mark.asyncio
    async def test_no_alert_when_safe(self) -> None:
        """Pet with plenty of time generates no alert."""
        manager = FrenPetManager(wallet_address="0xabc")
        # Default fixture has 3-day TOD => safe
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        assert result["alerts"] == []


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

class TestFrenPetManagerErrorHandling:
    @pytest.mark.asyncio
    async def test_fetch_failure_increments_error_count(self) -> None:
        manager = FrenPetManager(wallet_address="0xabc")

        with patch.object(
            manager.client,
            "fetch_snapshot",
            new=AsyncMock(side_effect=RuntimeError("network down")),
        ):
            with pytest.raises(RuntimeError, match="network down"):
                await manager.fetch_and_compute()

        assert manager._error_count == 1

    @pytest.mark.asyncio
    async def test_attack_fetch_failure_graceful(self) -> None:
        """Recent attacks failure should not crash the whole computation."""
        manager = FrenPetManager(wallet_address="0xabc")
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client,
            "get_recent_attacks",
            new=AsyncMock(side_effect=RuntimeError("attack query failed")),
        ):
            result = await manager.fetch_and_compute()

        # Should still return a complete result
        assert EXPECTED_KEYS.issubset(result.keys())
        assert result["recent_attacks"] == []
        assert result["global_battle_rate"] == 0.0


# ---------------------------------------------------------------------------
# Tests: meta fields
# ---------------------------------------------------------------------------

class TestFrenPetManagerMeta:
    @pytest.mark.asyncio
    async def test_meta_fields(self) -> None:
        manager = FrenPetManager(poll_interval=45, wallet_address="0xabc")
        snapshot = _make_snapshot()

        with patch.object(
            manager.client, "fetch_snapshot", new=AsyncMock(return_value=snapshot)
        ), patch.object(
            manager.client, "get_recent_attacks", new=AsyncMock(return_value=[])
        ):
            result = await manager.fetch_and_compute()

        assert result["poll_interval"] == 45
        assert result["error_count"] == 0
        assert isinstance(result["last_updated_seconds_ago"], float)
        assert result["last_updated_seconds_ago"] >= 0.0
