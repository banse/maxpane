"""Tests for cookie production rate calculations."""

import pytest

from maxpane_dashboard.analytics.production import (
    calculate_production_rate,
    classify_trend,
    format_rate,
)


class TestCalculateProductionRate:
    """Tests for calculate_production_rate."""

    def test_returns_zero_for_empty_samples(self) -> None:
        assert calculate_production_rate([]) == 0.0

    def test_returns_zero_for_single_sample(self) -> None:
        assert calculate_production_rate([(1000.0, 500.0)]) == 0.0

    def test_two_samples_constant_rate(self) -> None:
        # 100 cookies over 1 hour = 100/hr
        samples = [(0.0, 0.0), (3600.0, 100.0)]
        rate = calculate_production_rate(samples)
        assert pytest.approx(rate, abs=0.01) == 100.0

    def test_two_samples_high_rate(self) -> None:
        # 5800 cookies over 1 hour
        samples = [(0.0, 1000.0), (3600.0, 6800.0)]
        rate = calculate_production_rate(samples)
        assert pytest.approx(rate, abs=0.01) == 5800.0

    def test_multiple_samples_linear_growth(self) -> None:
        # Perfectly linear: 1000 cookies/hr
        samples = [
            (0.0, 0.0),
            (3600.0, 1000.0),
            (7200.0, 2000.0),
            (10800.0, 3000.0),
        ]
        rate = calculate_production_rate(samples)
        assert pytest.approx(rate, abs=1.0) == 1000.0

    def test_multiple_samples_noisy_data(self) -> None:
        # Approximately 500/hr with some noise
        samples = [
            (0.0, 0.0),
            (3600.0, 520.0),
            (7200.0, 980.0),
            (10800.0, 1510.0),
        ]
        rate = calculate_production_rate(samples)
        assert 450.0 < rate < 550.0

    def test_returns_zero_for_identical_timestamps(self) -> None:
        samples = [(1000.0, 100.0), (1000.0, 200.0)]
        assert calculate_production_rate(samples) == 0.0

    def test_clamps_negative_rate_to_zero(self) -> None:
        # Decreasing cookies should return 0 (can't have negative production)
        samples = [(0.0, 1000.0), (3600.0, 500.0)]
        assert calculate_production_rate(samples) == 0.0

    def test_fractional_hours(self) -> None:
        # 600 cookies in 30 minutes = 1200/hr
        samples = [(0.0, 0.0), (1800.0, 600.0)]
        rate = calculate_production_rate(samples)
        assert pytest.approx(rate, abs=0.01) == 1200.0


class TestClassifyTrend:
    """Tests for classify_trend."""

    def test_empty_rates_returns_flat(self) -> None:
        assert classify_trend([]) == "flat"

    def test_single_rate_returns_flat(self) -> None:
        assert classify_trend([100.0]) == "flat"

    def test_two_rising_rates(self) -> None:
        # 110 vs avg(100) = 10% increase > 5%
        assert classify_trend([100.0, 110.0]) == "rising"

    def test_two_falling_rates(self) -> None:
        # 90 vs avg(100) = -10% < -5%
        assert classify_trend([100.0, 90.0]) == "falling"

    def test_two_flat_rates(self) -> None:
        # 102 vs avg(100) = 2% -- within 5% threshold
        assert classify_trend([100.0, 102.0]) == "flat"

    def test_three_samples_rising(self) -> None:
        # avg(100, 105) = 102.5, latest 115 -> +12.2% > 5%
        assert classify_trend([100.0, 105.0, 115.0]) == "rising"

    def test_three_samples_falling(self) -> None:
        # avg(100, 95) = 97.5, latest 90 -> -7.7% < -5%
        assert classify_trend([100.0, 95.0, 90.0]) == "falling"

    def test_three_samples_flat(self) -> None:
        # avg(100, 101) = 100.5, latest 102 -> +1.5% -- flat
        assert classify_trend([100.0, 101.0, 102.0]) == "flat"

    def test_uses_last_three_from_longer_list(self) -> None:
        # Only last 3 matter: [200, 210, 250]
        # avg(200, 210) = 205, latest 250 -> +22% -- rising
        assert classify_trend([50.0, 60.0, 200.0, 210.0, 250.0]) == "rising"

    def test_zero_previous_average_with_positive_latest(self) -> None:
        assert classify_trend([0.0, 0.0, 5.0]) == "rising"

    def test_all_zeros(self) -> None:
        assert classify_trend([0.0, 0.0, 0.0]) == "flat"


class TestFormatRate:
    """Tests for format_rate."""

    def test_positive_rate(self) -> None:
        assert format_rate(5800.0) == "+5,800/hr"

    def test_small_positive_rate(self) -> None:
        assert format_rate(120.0) == "+120/hr"

    def test_zero_rate(self) -> None:
        assert format_rate(0.0) == "+0/hr"

    def test_negative_rate(self) -> None:
        assert format_rate(-500.0) == "-500/hr"

    def test_large_rate(self) -> None:
        assert format_rate(1234567.0) == "+1,234,567/hr"

    def test_fractional_rounds(self) -> None:
        assert format_rate(5800.7) == "+5,801/hr"
        assert format_rate(5800.3) == "+5,800/hr"
