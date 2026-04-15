"""Tests for FrenPet performance strategic signals."""

import pytest
from types import SimpleNamespace

from maxpane_dashboard.analytics.frenpet_perf_signals import (
    classify_avg_win_rate,
    classify_velocity,
    classify_weakest,
    color_velocity,
    compute_avg_win_rate,
    compute_total_velocity,
    find_weakest_pet,
    generate_perf_recommendation,
)


def _pet(
    name: str = "TestPet",
    score: int = 10000,
    win_qty: int = 0,
    loss_qty: int = 0,
    attack_points: int = 100,
    defense_points: int = 100,
) -> SimpleNamespace:
    """Helper to create a pet-like object with the expected attributes."""
    return SimpleNamespace(
        name=name,
        score=score,
        win_qty=win_qty,
        loss_qty=loss_qty,
        attack_points=attack_points,
        defense_points=defense_points,
    )


class TestComputeAvgWinRate:
    """Tests for compute_avg_win_rate."""

    def test_empty_list(self) -> None:
        assert compute_avg_win_rate([]) == 0.0

    def test_zero_battles(self) -> None:
        pets = [_pet(win_qty=0, loss_qty=0)]
        assert compute_avg_win_rate(pets) == 0.0

    def test_single_pet_all_wins(self) -> None:
        pets = [_pet(win_qty=10, loss_qty=0)]
        assert compute_avg_win_rate(pets) == 100.0

    def test_single_pet_all_losses(self) -> None:
        pets = [_pet(win_qty=0, loss_qty=10)]
        assert compute_avg_win_rate(pets) == 0.0

    def test_single_pet_even(self) -> None:
        pets = [_pet(win_qty=5, loss_qty=5)]
        assert compute_avg_win_rate(pets) == 50.0

    def test_multiple_pets_combined(self) -> None:
        pets = [
            _pet(name="A", win_qty=7, loss_qty=3),
            _pet(name="B", win_qty=3, loss_qty=7),
        ]
        # 10 wins / 20 battles = 50%
        assert compute_avg_win_rate(pets) == 50.0

    def test_multiple_pets_weighted(self) -> None:
        pets = [
            _pet(name="A", win_qty=90, loss_qty=10),  # 90% but 100 battles
            _pet(name="B", win_qty=1, loss_qty=9),  # 10% but 10 battles
        ]
        # 91 wins / 110 battles ~= 82.7%
        result = compute_avg_win_rate(pets)
        assert pytest.approx(result, rel=0.01) == 82.727

    def test_mix_of_active_and_idle(self) -> None:
        pets = [
            _pet(name="Active", win_qty=8, loss_qty=2),
            _pet(name="Idle", win_qty=0, loss_qty=0),
        ]
        # 8 wins / 10 battles = 80%
        assert compute_avg_win_rate(pets) == 80.0


class TestComputeTotalVelocity:
    """Tests for compute_total_velocity."""

    def test_empty_dict(self) -> None:
        assert compute_total_velocity({}) == 0.0

    def test_single_pet(self) -> None:
        assert compute_total_velocity({1: 150.5}) == 150.5

    def test_multiple_pets(self) -> None:
        velocities = {1: 100.0, 2: 200.0, 3: 50.0}
        assert compute_total_velocity(velocities) == 350.0

    def test_negative_velocities(self) -> None:
        velocities = {1: 100.0, 2: -50.0}
        assert compute_total_velocity(velocities) == 50.0

    def test_all_negative(self) -> None:
        velocities = {1: -100.0, 2: -50.0}
        assert compute_total_velocity(velocities) == -150.0

    def test_zero_velocities(self) -> None:
        velocities = {1: 0.0, 2: 0.0}
        assert compute_total_velocity(velocities) == 0.0


class TestClassifyVelocity:
    """Tests for classify_velocity."""

    def test_growing(self) -> None:
        assert classify_velocity(100.0) == ("growing", "green")

    def test_growing_small_positive(self) -> None:
        assert classify_velocity(0.001) == ("growing", "green")

    def test_stalled(self) -> None:
        assert classify_velocity(0.0) == ("stalled", "dim")

    def test_declining(self) -> None:
        assert classify_velocity(-50.0) == ("declining", "red")

    def test_declining_small_negative(self) -> None:
        assert classify_velocity(-0.001) == ("declining", "red")


class TestClassifyAvgWinRate:
    """Tests for classify_avg_win_rate."""

    def test_strong(self) -> None:
        assert classify_avg_win_rate(75.0) == ("strong", "green")

    def test_strong_boundary(self) -> None:
        assert classify_avg_win_rate(60.0) == ("strong", "green")

    def test_balanced(self) -> None:
        assert classify_avg_win_rate(50.0) == ("balanced", "yellow")

    def test_balanced_boundary(self) -> None:
        assert classify_avg_win_rate(40.0) == ("balanced", "yellow")

    def test_weak(self) -> None:
        assert classify_avg_win_rate(30.0) == ("weak", "red")

    def test_zero(self) -> None:
        assert classify_avg_win_rate(0.0) == ("weak", "red")


class TestFindWeakestPet:
    """Tests for find_weakest_pet."""

    def test_empty_list(self) -> None:
        assert find_weakest_pet([]) is None

    def test_no_qualifying_pets(self) -> None:
        pets = [
            _pet(name="A", win_qty=5, loss_qty=3),
            _pet(name="B", win_qty=2, loss_qty=1),
        ]
        assert find_weakest_pet(pets, min_battles=10) is None

    def test_single_qualifying_pet(self) -> None:
        pets = [
            _pet(name="Alpha", win_qty=7, loss_qty=5),
            _pet(name="Beta", win_qty=2, loss_qty=1),
        ]
        result = find_weakest_pet(pets, min_battles=10)
        assert result is not None
        assert result["name"] == "Alpha"
        assert result["win_rate"] == 58.3

    def test_multiple_qualifying_finds_weakest(self) -> None:
        pets = [
            _pet(name="Strong", win_qty=9, loss_qty=3),   # 75%
            _pet(name="Weak", win_qty=4, loss_qty=8),      # 33.3%
            _pet(name="Medium", win_qty=6, loss_qty=6),    # 50%
        ]
        result = find_weakest_pet(pets, min_battles=10)
        assert result is not None
        assert result["name"] == "Weak"
        assert result["win_rate"] == 33.3

    def test_default_min_battles(self) -> None:
        pets = [_pet(name="A", win_qty=5, loss_qty=4)]
        # 9 battles < default 10
        assert find_weakest_pet(pets) is None

    def test_custom_min_battles(self) -> None:
        pets = [_pet(name="A", win_qty=3, loss_qty=2)]
        result = find_weakest_pet(pets, min_battles=5)
        assert result is not None
        assert result["name"] == "A"
        assert result["win_rate"] == 60.0

    def test_all_zero_battles(self) -> None:
        pets = [_pet(name="Idle", win_qty=0, loss_qty=0)]
        assert find_weakest_pet(pets) is None

    def test_exact_min_battles_boundary(self) -> None:
        pets = [_pet(name="Edge", win_qty=6, loss_qty=4)]
        result = find_weakest_pet(pets, min_battles=10)
        assert result is not None
        assert result["name"] == "Edge"
        assert result["win_rate"] == 60.0


class TestClassifyWeakest:
    """Tests for classify_weakest."""

    def test_strong(self) -> None:
        assert classify_weakest(80.0) == ("strong", "green")

    def test_strong_boundary(self) -> None:
        assert classify_weakest(70.0) == ("strong", "green")

    def test_ok(self) -> None:
        assert classify_weakest(65.0) == ("ok", "yellow")

    def test_ok_boundary(self) -> None:
        assert classify_weakest(60.0) == ("ok", "yellow")

    def test_needs_work(self) -> None:
        assert classify_weakest(50.0) == ("needs work", "red")

    def test_zero(self) -> None:
        assert classify_weakest(0.0) == ("needs work", "red")


class TestGeneratePerfRecommendation:
    """Tests for generate_perf_recommendation."""

    def test_no_data(self) -> None:
        result = generate_perf_recommendation(0.0, 0.0, None)
        assert "No battle data" in result

    def test_declining_velocity(self) -> None:
        result = generate_perf_recommendation(60.0, -50.0, None)
        assert "declining" in result

    def test_weak_pet_dragging(self) -> None:
        weakest = {"name": "Kalle", "win_rate": 45.0}
        result = generate_perf_recommendation(55.0, 100.0, weakest)
        assert "Kalle" in result
        assert "dragging" in result

    def test_low_overall_win_rate(self) -> None:
        result = generate_perf_recommendation(35.0, 100.0, None)
        assert "Low overall" in result

    def test_excellent_performance(self) -> None:
        result = generate_perf_recommendation(75.0, 200.0, None)
        assert "Excellent" in result

    def test_strong_win_rate(self) -> None:
        result = generate_perf_recommendation(65.0, 0.0, None)
        assert "Strong win rate" in result

    def test_balanced(self) -> None:
        result = generate_perf_recommendation(50.0, 100.0, None)
        assert "Balanced" in result

    def test_weakest_above_threshold(self) -> None:
        weakest = {"name": "Duder", "win_rate": 55.0}
        result = generate_perf_recommendation(55.0, 100.0, weakest)
        # win_rate >= 50, so should not mention dragging
        assert "Balanced" in result

    def test_excellent_with_weakest_ok(self) -> None:
        weakest = {"name": "Walter", "win_rate": 60.0}
        result = generate_perf_recommendation(72.0, 300.0, weakest)
        assert "Excellent" in result


class TestColorVelocity:
    """Tests for color_velocity."""

    def test_green(self) -> None:
        assert color_velocity(200.0) == "green"

    def test_green_high(self) -> None:
        assert color_velocity(500.0) == "green"

    def test_cyan(self) -> None:
        assert color_velocity(150.0) == "cyan"

    def test_cyan_boundary(self) -> None:
        assert color_velocity(100.0) == "cyan"

    def test_yellow(self) -> None:
        assert color_velocity(75.0) == "yellow"

    def test_yellow_boundary(self) -> None:
        assert color_velocity(50.0) == "yellow"

    def test_dim(self) -> None:
        assert color_velocity(25.0) == "dim"

    def test_dim_zero(self) -> None:
        assert color_velocity(0.0) == "dim"

    def test_dim_negative(self) -> None:
        assert color_velocity(-10.0) == "dim"
