"""Tests for strategic signal calculations."""

import math

import pytest

from dashboard.analytics.signals import (
    calculate_gap_analysis,
    calculate_late_join_ev,
    calculate_leader_dominance,
    generate_recommendation,
)


class TestCalculateLateJoinEv:
    """Tests for calculate_late_join_ev."""

    def test_positive_ev_scenario(self) -> None:
        result = calculate_late_join_ev(
            prize_pool_eth=10.0,
            eth_price_usd=3000.0,
            member_count=20,
            buy_in_eth=0.05,
            win_probability=0.10,
        )
        # EV = 0.10 * 30000 - 150 = 3000 - 150 = 2850
        assert result["ev_usd"] == 2850.0
        assert result["breakeven_probability"] == pytest.approx(150.0 / 30000.0, abs=0.0001)
        assert "Positive EV" in result["recommendation"]

    def test_negative_ev_low_probability(self) -> None:
        result = calculate_late_join_ev(
            prize_pool_eth=10.0,
            eth_price_usd=3000.0,
            member_count=20,
            buy_in_eth=0.05,
            win_probability=0.001,
        )
        assert result["ev_usd"] < 0
        assert "win probability too low" in result["recommendation"]

    def test_negative_ev_high_buyin(self) -> None:
        result = calculate_late_join_ev(
            prize_pool_eth=1.0,
            eth_price_usd=3000.0,
            member_count=5,
            buy_in_eth=2.0,
            win_probability=0.20,
        )
        # EV = 0.20 * 3000 - 6000 = 600 - 6000 = -5400
        assert result["ev_usd"] < 0
        # breakeven = 6000/3000 = 2.0 > 0.5
        assert result["breakeven_probability"] > 0.5
        assert "buy-in too high" in result["recommendation"]

    def test_zero_prize_pool(self) -> None:
        result = calculate_late_join_ev(
            prize_pool_eth=0.0,
            eth_price_usd=3000.0,
            member_count=10,
            buy_in_eth=0.05,
            win_probability=0.10,
        )
        assert result["ev_usd"] < 0
        assert result["breakeven_probability"] == 1.0

    def test_returns_expected_keys(self) -> None:
        result = calculate_late_join_ev(1.0, 3000.0, 10, 0.05, 0.10)
        assert "ev_usd" in result
        assert "breakeven_probability" in result
        assert "recommendation" in result


class TestCalculateGapAnalysis:
    """Tests for calculate_gap_analysis."""

    def test_behind_and_closing(self) -> None:
        result = calculate_gap_analysis(
            leader_cookies=10000.0,
            leader_rate=500.0,
            your_cookies=8000.0,
            your_rate=700.0,
            hours_remaining=20.0,
        )
        assert result["current_gap"] == 2000.0
        assert result["gap_rate"] == -200.0  # closing at 200/hr
        assert result["projected_final_gap"] == 2000.0 + (-200.0 * 20.0)  # -2000
        assert result["catchable"] is True

    def test_behind_and_widening(self) -> None:
        result = calculate_gap_analysis(
            leader_cookies=10000.0,
            leader_rate=700.0,
            your_cookies=8000.0,
            your_rate=500.0,
            hours_remaining=20.0,
        )
        assert result["current_gap"] == 2000.0
        assert result["gap_rate"] == 200.0  # widening
        assert result["catchable"] is False

    def test_already_leading(self) -> None:
        result = calculate_gap_analysis(
            leader_cookies=8000.0,
            leader_rate=500.0,
            your_cookies=10000.0,
            your_rate=600.0,
            hours_remaining=10.0,
        )
        assert result["current_gap"] == -2000.0  # you're ahead
        assert result["catchable"] is True  # projected gap is negative

    def test_exactly_tied(self) -> None:
        result = calculate_gap_analysis(
            leader_cookies=5000.0,
            leader_rate=500.0,
            your_cookies=5000.0,
            your_rate=500.0,
            hours_remaining=10.0,
        )
        assert result["current_gap"] == 0.0
        assert result["gap_rate"] == 0.0
        assert result["projected_final_gap"] == 0.0
        assert result["catchable"] is True

    def test_zero_hours_remaining(self) -> None:
        result = calculate_gap_analysis(
            leader_cookies=10000.0,
            leader_rate=500.0,
            your_cookies=8000.0,
            your_rate=700.0,
            hours_remaining=0.0,
        )
        assert result["projected_final_gap"] == 2000.0
        assert result["catchable"] is False


class TestCalculateLeaderDominance:
    """Tests for calculate_leader_dominance."""

    def test_typical_dominance(self) -> None:
        assert calculate_leader_dominance(31000.0, 10000.0) == 3.1

    def test_equal_cookies(self) -> None:
        assert calculate_leader_dominance(5000.0, 5000.0) == 1.0

    def test_second_place_zero(self) -> None:
        assert calculate_leader_dominance(5000.0, 0.0) == float("inf")

    def test_both_zero(self) -> None:
        assert calculate_leader_dominance(0.0, 0.0) == 1.0

    def test_leader_zero_second_positive(self) -> None:
        assert calculate_leader_dominance(0.0, 5000.0) == 0.0


class TestGenerateRecommendation:
    """Tests for generate_recommendation."""

    def test_leader_with_commanding_lead(self) -> None:
        gap = {"catchable": True, "gap_rate": 0.0}
        rec = generate_recommendation(dominance=4.0, hours_remaining=10.0, your_rank=1, gap_analysis=gap)
        assert "Hold steady" in rec

    def test_leader_with_narrow_lead(self) -> None:
        gap = {"catchable": True, "gap_rate": 0.0}
        rec = generate_recommendation(dominance=1.2, hours_remaining=10.0, your_rank=1, gap_analysis=gap)
        assert "Boost now" in rec

    def test_trailing_gap_insurmountable(self) -> None:
        gap = {"catchable": False, "gap_rate": 100.0}
        rec = generate_recommendation(dominance=6.0, hours_remaining=10.0, your_rank=3, gap_analysis=gap)
        assert "Join #1" in rec

    def test_trailing_but_catchable_and_closing(self) -> None:
        gap = {"catchable": True, "gap_rate": -100.0}
        rec = generate_recommendation(dominance=1.5, hours_remaining=10.0, your_rank=2, gap_analysis=gap)
        assert "Stay the course" in rec

    def test_trailing_low_time_and_closing(self) -> None:
        gap = {"catchable": True, "gap_rate": -100.0}
        rec = generate_recommendation(dominance=1.3, hours_remaining=2.0, your_rank=2, gap_analysis=gap)
        assert "Boost now" in rec

    def test_trailing_not_catchable_low_time(self) -> None:
        gap = {"catchable": False, "gap_rate": 50.0}
        rec = generate_recommendation(dominance=2.0, hours_remaining=1.0, your_rank=2, gap_analysis=gap)
        assert "Concede" in rec

    def test_trailing_catchable_but_widening(self) -> None:
        gap = {"catchable": True, "gap_rate": 50.0}
        rec = generate_recommendation(dominance=1.5, hours_remaining=10.0, your_rank=2, gap_analysis=gap)
        assert "Attack leader" in rec

    def test_returns_string(self) -> None:
        gap = {"catchable": True, "gap_rate": 0.0}
        rec = generate_recommendation(dominance=1.0, hours_remaining=5.0, your_rank=1, gap_analysis=gap)
        assert isinstance(rec, str)
        assert len(rec) > 0
