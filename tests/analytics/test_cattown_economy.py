"""Tests for Cat Town economy analytics."""

import pytest

from maxpane_dashboard.analytics.cattown_economy import (
    calculate_burn_rate,
    calculate_fishing_volume,
    calculate_identification_ev,
    calculate_kibble_burn_pct,
    calculate_prize_pool_growth,
    calculate_staking_apy,
    format_kibble,
)


class TestBurnRate:
    def test_burn_rate_normal(self) -> None:
        assert calculate_burn_rate([500, 500], 2.0) == 500.0

    def test_burn_rate_zero_span(self) -> None:
        assert calculate_burn_rate([100, 200], 0.0) == 0.0

    def test_burn_rate_empty_list(self) -> None:
        assert calculate_burn_rate([], 5.0) == 0.0


class TestFishingVolume:
    def test_fishing_volume_normal(self) -> None:
        assert calculate_fishing_volume(60, 2.0) == 30.0

    def test_fishing_volume_zero_span(self) -> None:
        assert calculate_fishing_volume(100, 0.0) == 0.0


class TestStakingApy:
    def test_staking_apy_normal(self) -> None:
        # 1M staked, 10K weekly -> (10000/1000000)*52*100 = 52%
        assert calculate_staking_apy(1_000_000, 10_000) == 52.0

    def test_staking_apy_zero_staked(self) -> None:
        assert calculate_staking_apy(0.0, 10_000) == 0.0


class TestKibbleBurnPct:
    def test_burn_pct_normal(self) -> None:
        result = calculate_kibble_burn_pct(553_000_000, 1_000_000_000)
        assert result == pytest.approx(55.3)

    def test_burn_pct_zero_supply(self) -> None:
        assert calculate_kibble_burn_pct(100, 0.0) == 0.0


class TestFormatKibble:
    def test_format_kibble_millions(self) -> None:
        assert format_kibble(1_200_000) == "1.2M"

    def test_format_kibble_thousands(self) -> None:
        assert format_kibble(450_000) == "450.0K"

    def test_format_kibble_small(self) -> None:
        assert format_kibble(999) == "999"


class TestIdentificationEv:
    def test_identification_ev_splits(self) -> None:
        result = calculate_identification_ev(0.001)
        shares = (
            result["treasure_pool_share"]
            + result["staker_share"]
            + result["leaderboard_share"]
            + result["treasury_share"]
            + result["burn_share"]
        )
        assert shares == pytest.approx(result["cost_usd"], abs=1e-10)

    def test_identification_ev_values(self) -> None:
        result = calculate_identification_ev(0.001)
        assert result["cost_usd"] == 0.25
        assert result["treasure_pool_share"] == pytest.approx(0.175)
        assert result["staker_share"] == pytest.approx(0.025)
        assert result["leaderboard_share"] == pytest.approx(0.025)
        assert result["treasury_share"] == pytest.approx(0.01875)
        assert result["burn_share"] == pytest.approx(0.00625)


class TestPrizePoolGrowth:
    def test_prize_pool_growth_normal(self) -> None:
        snapshots = [(0.0, 100.0), (1.0, 200.0)]
        assert calculate_prize_pool_growth(snapshots, 2.0) == 50.0

    def test_prize_pool_growth_single_snapshot(self) -> None:
        assert calculate_prize_pool_growth([(0.0, 100.0)], 2.0) == 0.0
