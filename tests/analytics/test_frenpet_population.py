"""Tests for FrenPet population analytics."""

import pytest

from dashboard.analytics.frenpet_population import (
    calculate_market_conditions,
    calculate_population_stats,
    calculate_score_distribution,
    calculate_threat_level,
)


# -- Fixtures --

SAMPLE_PETS = [
    {"score": 5_000, "atk": 20, "def": 15, "hibernated": False},
    {"score": 25_000, "atk": 40, "def": 30, "hibernated": False},
    {"score": 75_000, "atk": 55, "def": 50, "hibernated": True},
    {"score": 150_000, "atk": 70, "def": 65, "hibernated": False},
    {"score": 350_000, "atk": 90, "def": 85, "hibernated": False},
    {"score": 600_000, "atk": 100, "def": 95, "hibernated": True},
]


class TestCalculateScoreDistribution:
    """Tests for calculate_score_distribution."""

    def test_all_tiers_populated(self) -> None:
        dist = calculate_score_distribution(SAMPLE_PETS)
        assert dist == {
            "0-10K": 1,
            "10-50K": 1,
            "50-100K": 1,
            "100-200K": 1,
            "200-500K": 1,
            "500K+": 1,
        }

    def test_empty_population(self) -> None:
        dist = calculate_score_distribution([])
        for count in dist.values():
            assert count == 0

    def test_all_in_one_bucket(self) -> None:
        pets = [{"score": 1000}, {"score": 2000}, {"score": 9999}]
        dist = calculate_score_distribution(pets)
        assert dist["0-10K"] == 3
        assert sum(dist.values()) == 3

    def test_boundary_values(self) -> None:
        """Test exact boundary scores."""
        pets = [
            {"score": 9_999},   # 0-10K
            {"score": 10_000},  # 10-50K
            {"score": 49_999},  # 10-50K
            {"score": 50_000},  # 50-100K
            {"score": 100_000}, # 100-200K
            {"score": 200_000}, # 200-500K
            {"score": 500_000}, # 500K+
        ]
        dist = calculate_score_distribution(pets)
        assert dist["0-10K"] == 1
        assert dist["10-50K"] == 2
        assert dist["50-100K"] == 1
        assert dist["100-200K"] == 1
        assert dist["200-500K"] == 1
        assert dist["500K+"] == 1


class TestCalculatePopulationStats:
    """Tests for calculate_population_stats."""

    def test_basic_stats(self) -> None:
        stats = calculate_population_stats(SAMPLE_PETS)
        assert stats["total"] == 6
        assert stats["active"] == 4
        assert stats["hibernated"] == 2

    def test_average_score(self) -> None:
        stats = calculate_population_stats(SAMPLE_PETS)
        expected_avg = sum(p["score"] for p in SAMPLE_PETS) / len(SAMPLE_PETS)
        assert pytest.approx(stats["avg_score"]) == expected_avg

    def test_median_score_even_count(self) -> None:
        stats = calculate_population_stats(SAMPLE_PETS)
        # Sorted: 5000, 25000, 75000, 150000, 350000, 600000
        # Median of 6 = (75000 + 150000) / 2 = 112500
        assert stats["median_score"] == 112_500.0

    def test_median_score_odd_count(self) -> None:
        pets = SAMPLE_PETS[:5]  # 5 pets
        stats = calculate_population_stats(pets)
        # Sorted: 5000, 25000, 75000, 150000, 350000
        # Median = 75000
        assert stats["median_score"] == 75_000

    def test_total_score(self) -> None:
        stats = calculate_population_stats(SAMPLE_PETS)
        expected_total = sum(p["score"] for p in SAMPLE_PETS)
        assert stats["total_score"] == expected_total

    def test_empty_population(self) -> None:
        stats = calculate_population_stats([])
        assert stats["total"] == 0
        assert stats["avg_score"] == 0.0
        assert stats["median_score"] == 0.0

    def test_single_pet(self) -> None:
        stats = calculate_population_stats([SAMPLE_PETS[0]])
        assert stats["total"] == 1
        assert stats["median_score"] == 5_000
        assert stats["avg_score"] == 5_000


class TestCalculateMarketConditions:
    """Tests for calculate_market_conditions."""

    def test_available_targets_excludes_shielded_and_cooldown(self) -> None:
        pets = [
            {"score": 100000, "atk": 50, "def": 40, "shielded": False, "in_cooldown": False},
            {"score": 100000, "atk": 50, "def": 40, "shielded": True, "in_cooldown": False},
            {"score": 100000, "atk": 50, "def": 40, "shielded": False, "in_cooldown": True},
            {"score": 100000, "atk": 50, "def": 40, "shielded": True, "in_cooldown": True},
        ]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["available_targets"] == 1

    def test_sweet_spot_counting(self) -> None:
        """ATK=80 vs DEF=40 -> wp = 80/120 = 0.667 (in 60-80% sweet spot)."""
        pets = [
            {"score": 100000, "atk": 50, "def": 40},
            {"score": 100000, "atk": 50, "def": 40},
            {"score": 100000, "atk": 50, "def": 40},
        ]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["sweet_spot_count"] == 3

    def test_hibernation_rate(self) -> None:
        pets = [
            {"score": 100000, "atk": 50, "def": 40, "hibernated": True},
            {"score": 100000, "atk": 50, "def": 40, "hibernated": False},
            {"score": 100000, "atk": 50, "def": 40, "hibernated": False},
            {"score": 100000, "atk": 50, "def": 40, "hibernated": False},
        ]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["hibernation_rate"] == pytest.approx(0.25)

    def test_shield_rate(self) -> None:
        pets = [
            {"score": 100000, "atk": 50, "def": 40, "shielded": True},
            {"score": 100000, "atk": 50, "def": 40, "shielded": True},
            {"score": 100000, "atk": 50, "def": 40, "shielded": False},
            {"score": 100000, "atk": 50, "def": 40, "shielded": False},
        ]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["shield_rate"] == pytest.approx(0.5)

    def test_target_density_high(self) -> None:
        # 25 pets all in sweet spot (ATK=80, DEF=40 -> wp=0.667)
        pets = [{"score": 100000, "atk": 50, "def": 40} for _ in range(25)]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["target_density"] == "high"

    def test_target_density_low(self) -> None:
        # 3 pets, all in sweet spot but < 5
        pets = [{"score": 100000, "atk": 50, "def": 40} for _ in range(3)]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["target_density"] == "low"

    def test_verdict_aggressive(self) -> None:
        pets = [{"score": 100000, "atk": 50, "def": 40} for _ in range(25)]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["verdict"] == "aggressive"

    def test_verdict_conservative_high_hibernation(self) -> None:
        pets = [
            {"score": 100000, "atk": 50, "def": 40, "hibernated": True}
            for _ in range(10)
        ]
        conditions = calculate_market_conditions(pets, my_atk=80, my_def=60)
        assert conditions["verdict"] == "conservative"

    def test_empty_population(self) -> None:
        conditions = calculate_market_conditions([], my_atk=80, my_def=60)
        assert conditions["available_targets"] == 0
        assert conditions["verdict"] == "conservative"


class TestCalculateThreatLevel:
    """Tests for calculate_threat_level."""

    def test_low_threats(self) -> None:
        """Only 2 pets with ATK > my_def."""
        pets = [
            {"atk": 30},  # 30/(30+80) = 0.27 -> not a threat
            {"atk": 40},  # 40/120 = 0.33 -> not a threat
            {"atk": 90},  # 90/170 = 0.53 -> threat
            {"atk": 100}, # 100/180 = 0.56 -> threat
        ]
        result = calculate_threat_level(pets, my_score=100000, my_def=80)
        assert result["threat_count"] == 2
        assert result["threat_level"] == "low"

    def test_medium_threats(self) -> None:
        pets = [{"atk": 100} for _ in range(10)]  # All threats vs DEF=80
        result = calculate_threat_level(pets, my_score=100000, my_def=80)
        assert result["threat_count"] == 10
        assert result["threat_level"] == "medium"

    def test_high_threats(self) -> None:
        pets = [{"atk": 100} for _ in range(20)]
        result = calculate_threat_level(pets, my_score=100000, my_def=80)
        assert result["threat_count"] == 20
        assert result["threat_level"] == "high"

    def test_no_threats(self) -> None:
        pets = [{"atk": 10} for _ in range(5)]  # All wp < 0.5 vs DEF=80
        result = calculate_threat_level(pets, my_score=100000, my_def=80)
        assert result["threat_count"] == 0
        assert result["threat_level"] == "low"

    def test_empty_population(self) -> None:
        result = calculate_threat_level([], my_score=100000, my_def=80)
        assert result["threat_count"] == 0
        assert result["threat_level"] == "low"
