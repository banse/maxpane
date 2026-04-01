"""Tests for FrenPet strategic signals."""

import time
from unittest.mock import patch

import pytest

from maxpane_dashboard.analytics.frenpet_signals import (
    calculate_battle_efficiency,
    calculate_rank,
    calculate_tod_status,
    calculate_velocity,
    determine_growth_phase,
    generate_pet_recommendation,
)


class TestCalculateBattleEfficiency:
    """Tests for calculate_battle_efficiency."""

    def test_perfect_record(self) -> None:
        assert calculate_battle_efficiency(10, 0) == 100.0

    def test_no_wins(self) -> None:
        assert calculate_battle_efficiency(0, 10) == 0.0

    def test_fifty_fifty(self) -> None:
        assert calculate_battle_efficiency(5, 5) == 50.0

    def test_no_battles(self) -> None:
        assert calculate_battle_efficiency(0, 0) == 0.0

    def test_realistic_ratio(self) -> None:
        # 7 wins, 3 losses = 70%
        assert pytest.approx(calculate_battle_efficiency(7, 3)) == 70.0


class TestCalculateVelocity:
    """Tests for calculate_velocity."""

    def test_steady_growth(self) -> None:
        # 10000 points per day
        samples = [
            (0.0, 100000.0),
            (86400.0, 110000.0),
            (172800.0, 120000.0),
        ]
        velocity = calculate_velocity(samples)
        assert pytest.approx(velocity, abs=1.0) == 10000.0

    def test_no_growth(self) -> None:
        samples = [
            (0.0, 100000.0),
            (86400.0, 100000.0),
        ]
        velocity = calculate_velocity(samples)
        assert pytest.approx(velocity, abs=0.01) == 0.0

    def test_negative_velocity(self) -> None:
        samples = [
            (0.0, 100000.0),
            (86400.0, 90000.0),
        ]
        velocity = calculate_velocity(samples)
        assert velocity < 0

    def test_single_sample(self) -> None:
        assert calculate_velocity([(0.0, 100000.0)]) == 0.0

    def test_empty_samples(self) -> None:
        assert calculate_velocity([]) == 0.0

    def test_identical_timestamps(self) -> None:
        samples = [(1000.0, 100000.0), (1000.0, 110000.0)]
        assert calculate_velocity(samples) == 0.0


class TestCalculateRank:
    """Tests for calculate_rank."""

    def test_first_place(self) -> None:
        result = calculate_rank(500000, [100000, 200000, 300000, 500000])
        assert result["rank"] == 1
        assert result["total"] == 4
        assert result["distance_to_next"] == 0.0
        assert result["distance_from_prev"] == 200000.0

    def test_last_place(self) -> None:
        result = calculate_rank(100000, [100000, 200000, 300000, 500000])
        assert result["rank"] == 4
        assert result["total"] == 4
        assert result["distance_to_next"] == 100000.0
        assert result["distance_from_prev"] == 0.0

    def test_middle_rank(self) -> None:
        result = calculate_rank(200000, [100000, 200000, 300000, 500000])
        assert result["rank"] == 3
        assert result["distance_to_next"] == 100000.0
        assert result["distance_from_prev"] == 100000.0

    def test_percentile_first_place(self) -> None:
        result = calculate_rank(500000, [100000, 200000, 300000, 500000])
        assert result["percentile"] == 100.0

    def test_percentile_last_place(self) -> None:
        result = calculate_rank(100000, [100000, 200000, 300000, 500000])
        assert result["percentile"] == 25.0

    def test_empty_scores(self) -> None:
        result = calculate_rank(100000, [])
        assert result["rank"] == 1
        assert result["total"] == 0
        assert result["percentile"] == 100.0

    def test_all_same_scores(self) -> None:
        result = calculate_rank(100000, [100000, 100000, 100000])
        assert result["rank"] == 1
        assert result["percentile"] == 100.0


class TestDetermineGrowthPhase:
    """Tests for determine_growth_phase."""

    def test_hatchling(self) -> None:
        assert determine_growth_phase(0) == "Hatchling"
        assert determine_growth_phase(50_000) == "Hatchling"
        assert determine_growth_phase(99_999) == "Hatchling"

    def test_growing(self) -> None:
        assert determine_growth_phase(100_000) == "Growing"
        assert determine_growth_phase(150_000) == "Growing"
        assert determine_growth_phase(199_999) == "Growing"

    def test_competitive(self) -> None:
        assert determine_growth_phase(200_000) == "Competitive"
        assert determine_growth_phase(250_000) == "Competitive"
        assert determine_growth_phase(299_999) == "Competitive"

    def test_apex(self) -> None:
        assert determine_growth_phase(300_000) == "Apex"
        assert determine_growth_phase(1_000_000) == "Apex"


class TestCalculateTodStatus:
    """Tests for calculate_tod_status."""

    def test_safe_status(self) -> None:
        # 72 hours from now
        future = time.time() + 72 * 3600
        with patch("maxpane_dashboard.analytics.frenpet_signals.time") as mock_time:
            mock_time.time.return_value = time.time()
            result = calculate_tod_status(int(future))
        assert result["status"] == "safe"
        assert result["color"] == "green"
        assert result["hours_remaining"] > 48.0

    def test_warning_status(self) -> None:
        now = time.time()
        future = now + 24 * 3600  # 24 hours
        with patch("maxpane_dashboard.analytics.frenpet_signals.time") as mock_time:
            mock_time.time.return_value = now
            result = calculate_tod_status(int(future))
        assert result["status"] == "warning"
        assert result["color"] == "amber"
        assert 6.0 <= result["hours_remaining"] <= 48.0

    def test_critical_status(self) -> None:
        now = time.time()
        future = now + 3 * 3600  # 3 hours
        with patch("maxpane_dashboard.analytics.frenpet_signals.time") as mock_time:
            mock_time.time.return_value = now
            result = calculate_tod_status(int(future))
        assert result["status"] == "critical"
        assert result["color"] == "red"
        assert result["hours_remaining"] < 6.0

    def test_past_timestamp_clamped_to_zero(self) -> None:
        now = time.time()
        past = now - 3600  # 1 hour ago
        with patch("maxpane_dashboard.analytics.frenpet_signals.time") as mock_time:
            mock_time.time.return_value = now
            result = calculate_tod_status(int(past))
        assert result["hours_remaining"] == 0.0
        assert result["status"] == "critical"

    def test_boundary_48_hours(self) -> None:
        now = time.time()
        exactly_48 = now + 48 * 3600
        with patch("maxpane_dashboard.analytics.frenpet_signals.time") as mock_time:
            mock_time.time.return_value = now
            result = calculate_tod_status(int(exactly_48))
        # 48h is in warning range (6-48h boundary is inclusive)
        assert result["status"] == "warning"

    def test_boundary_6_hours(self) -> None:
        # Use integer now to avoid int() truncation shifting below boundary
        now = 1700000000.0
        exactly_6 = now + 6 * 3600
        with patch("maxpane_dashboard.analytics.frenpet_signals.time") as mock_time:
            mock_time.time.return_value = now
            result = calculate_tod_status(int(exactly_6))
        assert result["status"] == "warning"


class TestGeneratePetRecommendation:
    """Tests for generate_pet_recommendation."""

    def test_high_threat_override(self) -> None:
        rec = generate_pet_recommendation(
            phase="Growing",
            battle_efficiency=80.0,
            velocity=5000.0,
            threat_level="high",
            market_conditions={"verdict": "aggressive", "sweet_spot_count": 20},
        )
        assert "DEF" in rec or "shield" in rec

    def test_hatchling_declining(self) -> None:
        rec = generate_pet_recommendation(
            phase="Hatchling",
            battle_efficiency=50.0,
            velocity=-1000.0,
            threat_level="low",
            market_conditions={"verdict": "balanced", "sweet_spot_count": 5},
        )
        assert "Feed" in rec or "feed" in rec

    def test_hatchling_many_targets(self) -> None:
        rec = generate_pet_recommendation(
            phase="Hatchling",
            battle_efficiency=60.0,
            velocity=1000.0,
            threat_level="low",
            market_conditions={"verdict": "aggressive", "sweet_spot_count": 15},
        )
        assert "Farm" in rec or "target" in rec

    def test_growing_low_efficiency(self) -> None:
        rec = generate_pet_recommendation(
            phase="Growing",
            battle_efficiency=40.0,
            velocity=2000.0,
            threat_level="low",
            market_conditions={"verdict": "balanced", "sweet_spot_count": 10},
        )
        assert "win rate" in rec or "target selection" in rec.lower()

    def test_growing_aggressive_market(self) -> None:
        rec = generate_pet_recommendation(
            phase="Growing",
            battle_efficiency=65.0,
            velocity=5000.0,
            threat_level="low",
            market_conditions={"verdict": "aggressive", "sweet_spot_count": 15},
        )
        assert "aggressive" in rec.lower() or "push" in rec.lower()

    def test_competitive_moderate_threat(self) -> None:
        rec = generate_pet_recommendation(
            phase="Competitive",
            battle_efficiency=60.0,
            velocity=3000.0,
            threat_level="medium",
            market_conditions={"verdict": "balanced", "sweet_spot_count": 10},
        )
        assert "DEF" in rec

    def test_apex_dominant(self) -> None:
        rec = generate_pet_recommendation(
            phase="Apex",
            battle_efficiency=75.0,
            velocity=8000.0,
            threat_level="low",
            market_conditions={"verdict": "aggressive", "sweet_spot_count": 20},
        )
        assert "Dominate" in rec or "dominate" in rec

    def test_apex_declining(self) -> None:
        rec = generate_pet_recommendation(
            phase="Apex",
            battle_efficiency=55.0,
            velocity=-2000.0,
            threat_level="low",
            market_conditions={"verdict": "balanced", "sweet_spot_count": 5},
        )
        assert "Defensive" in rec or "defensive" in rec

    def test_returns_string(self) -> None:
        rec = generate_pet_recommendation(
            phase="Growing",
            battle_efficiency=50.0,
            velocity=1000.0,
            threat_level="low",
            market_conditions={"verdict": "balanced", "sweet_spot_count": 5},
        )
        assert isinstance(rec, str)
        assert len(rec) > 0
