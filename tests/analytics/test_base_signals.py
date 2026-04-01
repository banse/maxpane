"""Tests for Base chain trading signals."""

import pytest

from maxpane_dashboard.analytics.base_signals import (
    calculate_liquidity_ratio,
    detect_volume_spike,
    generate_token_signal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token(**kwargs) -> dict:
    defaults = {
        "price_change_5m": 0.0,
        "price_change_1h": 0.0,
        "price_change_24h": 0.0,
        "volume_24h": 100_000,
        "avg_volume_24h": 50_000,
        "liquidity": 50_000,
        "market_cap": 1_000_000,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# detect_volume_spike
# ---------------------------------------------------------------------------

class TestDetectVolumeSpike:

    def test_spike_detected(self) -> None:
        assert detect_volume_spike(current_vol=400_000, avg_vol=100_000, threshold=3.0) is True

    def test_no_spike(self) -> None:
        assert detect_volume_spike(current_vol=200_000, avg_vol=100_000, threshold=3.0) is False

    def test_exactly_at_threshold(self) -> None:
        # 300_000 is NOT greater than 3.0 * 100_000
        assert detect_volume_spike(current_vol=300_000, avg_vol=100_000, threshold=3.0) is False

    def test_zero_avg_volume(self) -> None:
        assert detect_volume_spike(current_vol=100_000, avg_vol=0, threshold=3.0) is False

    def test_negative_avg_volume(self) -> None:
        assert detect_volume_spike(current_vol=100_000, avg_vol=-1.0, threshold=3.0) is False

    def test_custom_threshold(self) -> None:
        assert detect_volume_spike(current_vol=250_000, avg_vol=100_000, threshold=2.0) is True


# ---------------------------------------------------------------------------
# calculate_liquidity_ratio
# ---------------------------------------------------------------------------

class TestCalculateLiquidityRatio:

    def test_healthy_ratio(self) -> None:
        ratio = calculate_liquidity_ratio(liquidity=100_000, market_cap=1_000_000)
        assert ratio == pytest.approx(0.1)

    def test_thin_ratio(self) -> None:
        ratio = calculate_liquidity_ratio(liquidity=40_000, market_cap=1_000_000)
        assert ratio == pytest.approx(0.04)
        assert ratio < 0.05  # thin

    def test_zero_market_cap(self) -> None:
        assert calculate_liquidity_ratio(liquidity=100_000, market_cap=0) == 0.0

    def test_negative_market_cap(self) -> None:
        assert calculate_liquidity_ratio(liquidity=100_000, market_cap=-1) == 0.0

    def test_equal_liq_and_mcap(self) -> None:
        assert calculate_liquidity_ratio(liquidity=500_000, market_cap=500_000) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# generate_token_signal
# ---------------------------------------------------------------------------

class TestGenerateTokenSignal:

    def test_bullish_signal(self) -> None:
        token = _token(
            price_change_5m=10.0,
            price_change_1h=8.0,
            price_change_24h=5.0,
            volume_24h=400_000,
            avg_volume_24h=100_000,
            liquidity=100_000,
            market_cap=1_000_000,
        )
        signal = generate_token_signal(token)
        assert signal["overall"] == "bullish"
        assert signal["momentum"] > 0
        assert signal["volume_spike"] is True
        assert signal["liq_health"] == "healthy"

    def test_bearish_signal(self) -> None:
        token = _token(
            price_change_5m=-5.0,
            price_change_1h=-4.0,
            price_change_24h=-3.0,
            volume_24h=400_000,
            avg_volume_24h=100_000,
            liquidity=10_000,
            market_cap=1_000_000,
        )
        signal = generate_token_signal(token)
        assert signal["overall"] == "bearish"
        assert signal["liq_health"] == "thin"

    def test_neutral_signal(self) -> None:
        token = _token(
            price_change_5m=0.5,
            price_change_1h=0.1,
            price_change_24h=0.0,
            volume_24h=100_000,
            avg_volume_24h=100_000,
            liquidity=100_000,
            market_cap=1_000_000,
        )
        signal = generate_token_signal(token)
        assert signal["overall"] == "neutral"

    def test_unknown_liq_health_when_no_mcap(self) -> None:
        token = _token(market_cap=0)
        signal = generate_token_signal(token)
        assert signal["liq_health"] == "unknown"

    def test_returns_expected_keys(self) -> None:
        signal = generate_token_signal(_token())
        assert set(signal.keys()) == {"momentum", "volume_spike", "liq_health", "overall"}

    def test_volume_spike_amplifies_bearish(self) -> None:
        token = _token(
            price_change_5m=-6.0,
            price_change_1h=-3.0,
            price_change_24h=-1.0,
            volume_24h=500_000,
            avg_volume_24h=100_000,
            liquidity=100_000,
            market_cap=1_000_000,
        )
        signal = generate_token_signal(token)
        assert signal["volume_spike"] is True
        assert signal["overall"] == "bearish"
