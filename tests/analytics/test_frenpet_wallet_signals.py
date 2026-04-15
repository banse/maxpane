"""Tests for FrenPet wallet strategic signals."""

import pytest

from maxpane_dashboard.analytics.frenpet_wallet_signals import (
    classify_fp_rate,
    classify_pool_share,
    classify_win_rate,
    compute_apr,
    compute_pool_share,
    compute_win_rate,
    find_most_efficient,
    find_top_earner,
    generate_wallet_recommendation,
)


class TestComputePoolShare:
    """Tests for compute_pool_share."""

    def test_zero_total_shares(self) -> None:
        assert compute_pool_share(100, 0) == 0.0

    def test_zero_user_shares(self) -> None:
        assert compute_pool_share(0, 1000) == 0.0

    def test_full_ownership(self) -> None:
        assert compute_pool_share(1000, 1000) == 100.0

    def test_one_percent(self) -> None:
        assert pytest.approx(compute_pool_share(10, 1000)) == 1.0

    def test_small_fraction(self) -> None:
        result = compute_pool_share(1, 100_000)
        assert pytest.approx(result) == 0.001


class TestComputeApr:
    """Tests for compute_apr."""

    def test_zero_days_elapsed(self) -> None:
        assert compute_apr(1_000_000_000_000_000_000, 100, 0.001, 0.0) == 0.0

    def test_zero_shares(self) -> None:
        assert compute_apr(1_000_000_000_000_000_000, 0, 0.001, 30.0) == 0.0

    def test_zero_price(self) -> None:
        assert compute_apr(1_000_000_000_000_000_000, 100, 0.0, 30.0) == 0.0

    def test_negative_days(self) -> None:
        assert compute_apr(1_000_000_000_000_000_000, 100, 0.001, -5.0) == 0.0

    def test_positive_apr(self) -> None:
        # 1 ETH earned, 100 shares at 0.01 ETH each = 1 ETH cost basis
        # Over 365 days: 100% annual return
        eth_wei = 1_000_000_000_000_000_000  # 1 ETH
        result = compute_apr(eth_wei, 100, 0.01, 365.0)
        assert pytest.approx(result, rel=0.01) == 100.0

    def test_partial_year(self) -> None:
        # 0.1 ETH earned over 36.5 days with 1 ETH cost basis
        # daily = 0.1 / 36.5, annual = daily * 365 = 1.0 => 100%
        eth_wei = 100_000_000_000_000_000  # 0.1 ETH
        result = compute_apr(eth_wei, 100, 0.01, 36.5)
        assert pytest.approx(result, rel=0.01) == 100.0


class TestComputeWinRate:
    """Tests for compute_win_rate."""

    def test_no_battles(self) -> None:
        assert compute_win_rate(0, 0) == 0.0

    def test_all_wins(self) -> None:
        assert compute_win_rate(10, 0) == 100.0

    def test_all_losses(self) -> None:
        assert compute_win_rate(0, 10) == 0.0

    def test_even_split(self) -> None:
        assert compute_win_rate(5, 5) == 50.0

    def test_realistic(self) -> None:
        assert pytest.approx(compute_win_rate(7, 3)) == 70.0


class TestClassifyFpRate:
    """Tests for classify_fp_rate."""

    def test_earning(self) -> None:
        assert classify_fp_rate(100) == ("earning", "green")

    def test_idle(self) -> None:
        assert classify_fp_rate(0) == ("idle", "dim")

    def test_large_rate(self) -> None:
        assert classify_fp_rate(999_999) == ("earning", "green")


class TestClassifyWinRate:
    """Tests for classify_win_rate."""

    def test_strong(self) -> None:
        assert classify_win_rate(75.0) == ("strong", "green")

    def test_strong_boundary(self) -> None:
        assert classify_win_rate(60.0) == ("strong", "green")

    def test_balanced(self) -> None:
        assert classify_win_rate(50.0) == ("balanced", "yellow")

    def test_balanced_boundary(self) -> None:
        assert classify_win_rate(40.0) == ("balanced", "yellow")

    def test_weak(self) -> None:
        assert classify_win_rate(30.0) == ("weak", "red")

    def test_zero(self) -> None:
        assert classify_win_rate(0.0) == ("weak", "red")


class TestClassifyPoolShare:
    """Tests for classify_pool_share."""

    def test_large(self) -> None:
        assert classify_pool_share(5.0) == ("large", "green")

    def test_large_boundary(self) -> None:
        assert classify_pool_share(1.0) == ("large", "green")

    def test_medium(self) -> None:
        assert classify_pool_share(0.5) == ("medium", "yellow")

    def test_medium_boundary(self) -> None:
        assert classify_pool_share(0.1) == ("medium", "yellow")

    def test_small(self) -> None:
        assert classify_pool_share(0.05) == ("small", "dim")

    def test_zero(self) -> None:
        assert classify_pool_share(0.0) == ("small", "dim")


class TestGenerateWalletRecommendation:
    """Tests for generate_wallet_recommendation."""

    def test_inactive_wallet(self) -> None:
        result = generate_wallet_recommendation(0.0, 0.0, 0, 0)
        assert "Inactive" in result

    def test_no_fp_earning(self) -> None:
        result = generate_wallet_recommendation(0.5, 60.0, 0, 1_000_000)
        assert "FP earning stopped" in result

    def test_low_win_rate(self) -> None:
        result = generate_wallet_recommendation(0.5, 30.0, 100, 1_000_000)
        assert "Low win rate" in result

    def test_strong_position(self) -> None:
        result = generate_wallet_recommendation(2.0, 70.0, 100, 1_000_000)
        assert "Strong position" in result

    def test_small_pool_share(self) -> None:
        result = generate_wallet_recommendation(0.05, 55.0, 100, 1_000_000)
        assert "Small pool share" in result

    def test_balanced(self) -> None:
        result = generate_wallet_recommendation(0.5, 55.0, 100, 1_000_000)
        assert "Balanced" in result


class TestFindTopEarner:
    """Tests for find_top_earner."""

    def test_empty_list(self) -> None:
        assert find_top_earner([]) is None

    def test_single_pet(self) -> None:
        pets = [{"name": "Alpha", "score": 50000, "wins": 10, "losses": 5}]
        result = find_top_earner(pets)
        assert result is not None
        assert result["name"] == "Alpha"
        assert result["score"] == 50000
        assert result["win_rate"] == 66.7

    def test_multiple_pets(self) -> None:
        pets = [
            {"name": "Alpha", "score": 50000, "wins": 10, "losses": 5},
            {"name": "Beta", "score": 80000, "wins": 20, "losses": 10},
            {"name": "Gamma", "score": 30000, "wins": 5, "losses": 2},
        ]
        result = find_top_earner(pets)
        assert result is not None
        assert result["name"] == "Beta"
        assert result["score"] == 80000

    def test_pet_with_no_battles(self) -> None:
        pets = [{"name": "Newbie", "score": 1000, "wins": 0, "losses": 0}]
        result = find_top_earner(pets)
        assert result is not None
        assert result["win_rate"] == 0.0

    def test_missing_fields_use_defaults(self) -> None:
        pets = [{"score": 5000}]
        result = find_top_earner(pets)
        assert result is not None
        assert result["name"] == "Unknown"
        assert result["wins"] == 0


class TestFindMostEfficient:
    """Tests for find_most_efficient."""

    def test_empty_list(self) -> None:
        assert find_most_efficient([]) is None

    def test_no_qualifying_pets(self) -> None:
        pets = [
            {"name": "Alpha", "score": 50000, "wins": 5, "losses": 3},
            {"name": "Beta", "score": 30000, "wins": 2, "losses": 1},
        ]
        assert find_most_efficient(pets, min_battles=10) is None

    def test_single_qualifying_pet(self) -> None:
        pets = [
            {"name": "Alpha", "score": 50000, "wins": 8, "losses": 4},
            {"name": "Beta", "score": 30000, "wins": 2, "losses": 1},
        ]
        result = find_most_efficient(pets, min_battles=10)
        assert result is not None
        assert result["name"] == "Alpha"
        assert result["win_rate"] == 66.7

    def test_multiple_qualifying_best_rate(self) -> None:
        pets = [
            {"name": "Alpha", "score": 50000, "wins": 7, "losses": 5},
            {"name": "Beta", "score": 30000, "wins": 9, "losses": 3},
            {"name": "Gamma", "score": 80000, "wins": 6, "losses": 6},
        ]
        result = find_most_efficient(pets, min_battles=10)
        assert result is not None
        assert result["name"] == "Beta"
        assert result["win_rate"] == 75.0

    def test_custom_min_battles(self) -> None:
        pets = [
            {"name": "Alpha", "score": 50000, "wins": 3, "losses": 2},
        ]
        result = find_most_efficient(pets, min_battles=5)
        assert result is not None
        assert result["name"] == "Alpha"

    def test_default_min_battles(self) -> None:
        pets = [
            {"name": "Alpha", "score": 50000, "wins": 5, "losses": 4},
        ]
        # 9 total battles, default min is 10
        assert find_most_efficient(pets) is None
