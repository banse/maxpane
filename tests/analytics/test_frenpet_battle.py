"""Tests for FrenPet battle calculations."""

import math

import pytest

from maxpane_dashboard.analytics.frenpet_battle import (
    SCORE_DECIMALS,
    calculate_loss,
    calculate_reward,
    calculate_reward_risk_ratio,
    calculate_win_probability,
    evaluate_target,
)


class TestCalculateWinProbability:
    """Tests for calculate_win_probability."""

    def test_equal_stats(self) -> None:
        assert calculate_win_probability(50, 50) == 0.5

    def test_higher_atk(self) -> None:
        # 81 / (81 + 48) = 81/129 ~ 0.6279
        wp = calculate_win_probability(81, 48)
        assert pytest.approx(wp, abs=0.001) == 0.6279

    def test_lower_atk(self) -> None:
        # 81 / (81 + 155) = 81/236 ~ 0.3432
        wp = calculate_win_probability(81, 155)
        assert pytest.approx(wp, abs=0.001) == 0.3432

    def test_zero_atk(self) -> None:
        assert calculate_win_probability(0, 50) == 0.0

    def test_zero_def(self) -> None:
        assert calculate_win_probability(50, 0) == 1.0

    def test_both_zero(self) -> None:
        assert calculate_win_probability(0, 0) == 0.0

    def test_very_high_atk(self) -> None:
        wp = calculate_win_probability(1000, 1)
        assert wp > 0.99


class TestCalculateLoss:
    """Tests for calculate_loss."""

    def test_standard_score(self) -> None:
        assert calculate_loss(77200) == pytest.approx(386.0)

    def test_zero_score(self) -> None:
        assert calculate_loss(0) == 0.0

    def test_large_score(self) -> None:
        assert calculate_loss(2_400_000) == pytest.approx(12_000.0)

    def test_small_score(self) -> None:
        assert calculate_loss(100) == pytest.approx(0.5)


class TestCalculateReward:
    """Tests for calculate_reward."""

    def test_weaker_target(self) -> None:
        """score=77200, target=230000, ATK=81, DEF=48 -> win_prob ~0.6279."""
        wp = calculate_win_probability(81, 48)
        reward = calculate_reward(77200, 230000, wp)
        # attacker_base = 386, raw_reward = 386 * 1.7 = 656.2
        # cap = 230000 * 0.005 = 1150
        # reward = min(656.2, 1150) = 656.2
        assert pytest.approx(reward, abs=1.0) == 656.2

    def test_stronger_target(self) -> None:
        """score=77200, target=2.4M, ATK=81, DEF=155 -> win_prob ~0.3432."""
        wp = calculate_win_probability(81, 155)
        reward = calculate_reward(77200, 2_400_000, wp)
        # attacker_base = 386 / 10 = 38.6
        # odds_pct = 34.32
        # raw_reward = 38.6 * (1 + (50 - 34.32) + 0.7) = 38.6 * 17.38 = 670.868
        # cap = 2400000 * 0.005 / 10 = 1200
        # reward = min(670.868, 1200) = 670.868
        assert pytest.approx(reward, abs=1.0) == 670.87

    def test_hibernated_target_doubles_cap(self) -> None:
        """Hibernated targets have 2x cap."""
        wp = 0.7  # attacking weaker
        # Non-hibernated: cap = 100000 * 0.005 = 500
        reward_normal = calculate_reward(50000, 100000, wp, target_hibernated=False)
        # Hibernated: cap = 100000 * 0.005 * 2 = 1000
        reward_hib = calculate_reward(50000, 100000, wp, target_hibernated=True)

        # attacker_base = 250, raw_reward = 250 * 1.7 = 425
        # Both under caps, so hibernation doesn't change reward here
        assert reward_normal == reward_hib  # raw < both caps

    def test_hibernated_target_cap_effective(self) -> None:
        """When raw_reward exceeds non-hibernated cap, hibernation matters."""
        wp = 0.7
        # Large my_score, small target_score to hit cap
        # my_loss = 500000 * 0.005 = 2500, raw = 2500 * 1.7 = 4250
        # normal cap = 10000 * 0.005 = 50
        # hib cap = 10000 * 0.005 * 2 = 100
        reward_normal = calculate_reward(500000, 10000, wp, target_hibernated=False)
        reward_hib = calculate_reward(500000, 10000, wp, target_hibernated=True)
        assert reward_normal == pytest.approx(50.0)
        assert reward_hib == pytest.approx(100.0)

    def test_zero_score_attacker(self) -> None:
        reward = calculate_reward(0, 100000, 0.6)
        assert reward == 0.0

    def test_zero_score_target(self) -> None:
        reward = calculate_reward(77200, 0, 0.6)
        # raw = 386 * 1.7 = 656.2, cap = 0
        assert reward == 0.0


class TestCalculateRewardRiskRatio:
    """Tests for calculate_reward_risk_ratio."""

    def test_weaker_target_ratio(self) -> None:
        """score=77200, ATK=81, target=230000, DEF=48 -> ratio ~2.87."""
        ratio = calculate_reward_risk_ratio(77200, 81, 230000, 48)
        assert pytest.approx(ratio, abs=0.05) == 2.87

    def test_stronger_target_ratio(self) -> None:
        """score=77200, ATK=81, target=2.4M, DEF=155 -> ratio ~0.91."""
        ratio = calculate_reward_risk_ratio(77200, 81, 2_400_000, 155)
        assert pytest.approx(ratio, abs=0.05) == 0.91

    def test_equal_stats_ratio(self) -> None:
        # Equal ATK and DEF, equal scores -> ratio based on 1.7x multiplier
        ratio = calculate_reward_risk_ratio(100000, 50, 100000, 50)
        # wp=0.5, loss=500, reward=min(500*1.7, 500)=500
        # ratio = (500*0.5)/(500*0.5) = 1.0
        assert pytest.approx(ratio, abs=0.05) == 1.0

    def test_zero_score_returns_zero(self) -> None:
        ratio = calculate_reward_risk_ratio(0, 50, 100000, 50)
        assert ratio == 0.0

    def test_zero_def_returns_inf(self) -> None:
        """Win probability = 1.0, lose_prob = 0 -> inf."""
        ratio = calculate_reward_risk_ratio(77200, 81, 230000, 0)
        assert ratio == float("inf")


class TestEvaluateTarget:
    """Tests for evaluate_target."""

    def test_strong_recommendation(self) -> None:
        """High ratio, high win prob -> strong."""
        result = evaluate_target(
            my_score=77200,
            my_atk=81,
            my_def=60,
            target_score=230000,
            target_atk=30,
            target_def=48,
        )
        assert result["recommendation"] == "strong"
        assert result["win_prob"] > 0.55
        assert result["ratio"] > 2.0
        assert result["ev"] > 0

    def test_avoid_recommendation(self) -> None:
        """Very unfavorable matchup -> avoid."""
        result = evaluate_target(
            my_score=10000,
            my_atk=20,
            my_def=20,
            target_score=500000,
            target_atk=100,
            target_def=200,
        )
        assert result["recommendation"] == "avoid"
        assert result["win_prob"] < 0.15

    def test_result_keys(self) -> None:
        result = evaluate_target(
            my_score=100000,
            my_atk=50,
            my_def=50,
            target_score=100000,
            target_atk=50,
            target_def=50,
        )
        expected_keys = {"win_prob", "could_win", "could_lose", "ratio", "ev", "recommendation"}
        assert set(result.keys()) == expected_keys

    def test_hibernated_flag_passed_through(self) -> None:
        normal = evaluate_target(
            my_score=500000, my_atk=80, my_def=60,
            target_score=10000, target_atk=30, target_def=40,
            target_hibernated=False,
        )
        hib = evaluate_target(
            my_score=500000, my_atk=80, my_def=60,
            target_score=10000, target_atk=30, target_def=40,
            target_hibernated=True,
        )
        # Hibernated cap is 2x, so reward should be higher (if cap-limited)
        assert hib["could_win"] >= normal["could_win"]

    def test_ev_positive_for_favorable_matchup(self) -> None:
        result = evaluate_target(
            my_score=77200, my_atk=81, my_def=60,
            target_score=230000, target_atk=30, target_def=48,
        )
        assert result["ev"] > 0

    def test_could_lose_equals_half_percent(self) -> None:
        result = evaluate_target(
            my_score=200000, my_atk=50, my_def=50,
            target_score=200000, target_atk=50, target_def=50,
        )
        assert result["could_lose"] == pytest.approx(1000.0)
