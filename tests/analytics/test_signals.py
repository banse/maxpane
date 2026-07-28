"""Tests for strategic signal calculations."""

import math

import pytest

from maxpane_dashboard.analytics.signals import (
    calculate_gap_analysis,
    calculate_late_join_ev,
    calculate_leader_dominance,
    generate_recommendation,
)


class TestCalculateLateJoinEv:
    """Tests for calculate_late_join_ev.

    MEDI-8: the payout leg used to be ``win_probability * whole_pool``,
    ignoring both the confirmed 70/20/10 split and the ``member_count``
    parameter it accepted but never read.  The SignalsPanel renders
    ``ev_usd`` verbatim, so a 30-member leader was shown a figure ~90x too
    large -- and against a *finalized* season (which still reports a pool)
    it read "Positive EV -- consider joining" for a season nobody could
    join.
    """

    def test_positive_ev_scenario(self) -> None:
        result = calculate_late_join_ev(
            prize_pool_eth=10.0,
            eth_price_usd=3000.0,
            member_count=2,
            buy_in_eth=0.05,
            win_probability=0.10,
        )
        # pool = $30,000; mean top-3 share = 1/3; split across 2 members
        # => $5,000 per member if the bakery places.
        # EV = 0.10 * 5000 - 150 = 500 - 150 = 350
        assert result["ev_usd"] == 350.0
        assert result["breakeven_probability"] == pytest.approx(150.0 / 5000.0, abs=0.0001)
        assert "Positive EV" in result["recommendation"]

    def test_payout_is_the_split_share_divided_among_members(self) -> None:
        """The two corrections that MEDI-8 asked for, measured separately."""
        pool_usd = 10.0 * 3000.0
        common = dict(
            prize_pool_eth=10.0,
            eth_price_usd=3000.0,
            buy_in_eth=0.0,  # isolate the payout leg
            win_probability=1.0,
        )

        solo = calculate_late_join_ev(member_count=1, **common)
        # Not the whole pool: the mean of the 70/20/10 split.
        assert solo["ev_usd"] == pytest.approx(pool_usd / 3.0, abs=0.01)
        assert solo["ev_usd"] != pytest.approx(pool_usd, abs=1.0)

        # ...and that share is split among the bakery's members.
        crowded = calculate_late_join_ev(member_count=30, **common)
        assert crowded["ev_usd"] == pytest.approx(solo["ev_usd"] / 30.0, abs=0.01)

    def test_thirty_member_leader_is_not_shown_a_five_figure_ev(self) -> None:
        """Regression for the live reproduction in the review.

        The reviewer observed ``ev_usd=9749.3`` for the season-10 leader.
        With the same inputs the corrected formula must land roughly two
        orders of magnitude lower.
        """
        old_style_ev = 0.3 * (10.0 * 3000.0)  # win_prob * whole pool
        result = calculate_late_join_ev(
            prize_pool_eth=10.0,
            eth_price_usd=3000.0,
            member_count=30,
            buy_in_eth=0.05,
            win_probability=0.3,
        )
        assert result["ev_usd"] < old_style_ev / 50

    def test_ended_season_is_minus_the_buy_in_regardless_of_pool(self) -> None:
        """A finalized season still reports a pool; it cannot be joined."""
        result = calculate_late_join_ev(
            prize_pool_eth=100.0,
            eth_price_usd=3000.0,
            member_count=2,
            buy_in_eth=0.05,
            win_probability=1.0,
            season_active=False,
        )
        assert result["ev_usd"] == pytest.approx(-150.0)
        assert "Positive EV" not in result["recommendation"]
        assert "Season over" in result["recommendation"]

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
        # payout_if_top3 = 3000/3/5 = 200; EV = 0.20 * 200 - 6000
        assert result["ev_usd"] < 0
        # breakeven = 6000/200 = 30 > 0.5
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

    def test_zero_member_count_does_not_divide_by_zero(self) -> None:
        result = calculate_late_join_ev(
            prize_pool_eth=10.0,
            eth_price_usd=3000.0,
            member_count=0,
            buy_in_eth=0.0,
            win_probability=1.0,
        )
        assert result["ev_usd"] == pytest.approx(30000.0 / 3.0, abs=0.01)

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
