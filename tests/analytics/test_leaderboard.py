"""Tests for leaderboard analytics and formatting."""

import pytest

from maxpane_dashboard.analytics.leaderboard import (
    calculate_prize_per_member,
    format_cookies,
    format_gap,
)


class TestCalculatePrizePerMember:
    """Tests for calculate_prize_per_member."""

    def test_even_split(self) -> None:
        assert calculate_prize_per_member(1000.0, 10) == 100.0

    def test_single_member(self) -> None:
        assert calculate_prize_per_member(5000.0, 1) == 5000.0

    def test_zero_members(self) -> None:
        assert calculate_prize_per_member(5000.0, 0) == 0.0

    def test_negative_members(self) -> None:
        assert calculate_prize_per_member(5000.0, -1) == 0.0

    def test_zero_pool(self) -> None:
        assert calculate_prize_per_member(0.0, 10) == 0.0

    def test_fractional_result(self) -> None:
        result = calculate_prize_per_member(1000.0, 3)
        assert pytest.approx(result, abs=0.01) == 333.33


class TestFormatGap:
    """Tests for format_gap."""

    def test_leader_shows_dash(self) -> None:
        assert format_gap(10000.0, 10000.0) == "\u2014"

    def test_ahead_of_leader_shows_dash(self) -> None:
        # Edge case: if cookies > leader_cookies
        assert format_gap(11000.0, 10000.0) == "\u2014"

    def test_small_gap(self) -> None:
        result = format_gap(9500.0, 10000.0)
        assert result == "-500"

    def test_medium_gap(self) -> None:
        # 5400 behind -> -5.4K
        result = format_gap(4600.0, 10000.0)
        assert result == "-5.4K"

    def test_large_gap(self) -> None:
        # 94600 behind -> -94.6K
        result = format_gap(5400.0, 100000.0)
        assert result == "-94.6K"

    def test_million_gap(self) -> None:
        result = format_gap(0.0, 1500000.0)
        assert result == "-1.5M"


class TestFormatCookies:
    """Tests for format_cookies."""

    def test_zero(self) -> None:
        assert format_cookies(0.0) == "0"

    def test_small_number(self) -> None:
        assert format_cookies(800.0) == "800"

    def test_one_k(self) -> None:
        assert format_cookies(1500.0) == "1.5K"

    def test_ten_k(self) -> None:
        assert format_cookies(12500.0) == "12.5K"

    def test_hundred_k(self) -> None:
        assert format_cookies(139300.0) == "139.3K"

    def test_one_m(self) -> None:
        assert format_cookies(1500000.0) == "1.5M"

    def test_exactly_1000(self) -> None:
        assert format_cookies(1000.0) == "1.0K"

    def test_negative(self) -> None:
        assert format_cookies(-5000.0) == "-5.0K"

    def test_large_millions(self) -> None:
        assert format_cookies(12500000.0) == "12.5M"

    def test_just_under_1000(self) -> None:
        assert format_cookies(999.0) == "999"
