"""Tests for Base Trading Overview signal generators."""

import math

import pytest

from maxpane_dashboard.analytics.base_overview_signals import (
    compute_all_signals,
    compute_buy_sell_ratio,
    compute_volume_trend,
    compute_whale_activity,
    generate_recommendation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token(**kwargs) -> dict:
    defaults = {
        "buys_24h": 100,
        "sells_24h": 80,
        "volume_24h": 50_000.0,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# compute_buy_sell_ratio
# ---------------------------------------------------------------------------

class TestComputeBuySellRatio:

    def test_bullish(self) -> None:
        tokens = [_token(buys_24h=200, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Bullish"
        assert result["color"] == "green"
        assert result["value"] == pytest.approx(2.0)

    def test_bearish(self) -> None:
        tokens = [_token(buys_24h=50, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Bearish"
        assert result["color"] == "red"
        assert result["value"] == pytest.approx(0.5)

    def test_neutral(self) -> None:
        tokens = [_token(buys_24h=100, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Neutral"
        assert result["color"] == "yellow"
        assert result["value"] == pytest.approx(1.0)

    def test_boundary_above_1_2(self) -> None:
        # 1.21 should be Bullish
        tokens = [_token(buys_24h=121, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Bullish"

    def test_boundary_exactly_1_2(self) -> None:
        # Exactly 1.2 is NOT > 1.2 so should be Neutral
        tokens = [_token(buys_24h=120, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Neutral"

    def test_boundary_exactly_0_8(self) -> None:
        # Exactly 0.8 is NOT < 0.8 so should be Neutral
        tokens = [_token(buys_24h=80, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Neutral"

    def test_boundary_below_0_8(self) -> None:
        tokens = [_token(buys_24h=79, sells_24h=100)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Bearish"

    def test_zero_sells_with_buys(self) -> None:
        tokens = [_token(buys_24h=50, sells_24h=0)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Bullish"
        assert result["color"] == "green"
        assert math.isinf(result["value"])

    def test_zero_sells_zero_buys(self) -> None:
        tokens = [_token(buys_24h=0, sells_24h=0)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Neutral"
        assert result["color"] == "yellow"
        assert result["value"] == 0.0

    def test_empty_token_list(self) -> None:
        result = compute_buy_sell_ratio([])
        assert result["label"] == "Neutral"
        assert result["value"] == 0.0

    def test_none_buys_and_sells(self) -> None:
        tokens = [_token(buys_24h=None, sells_24h=None)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Neutral"
        assert result["value"] == 0.0

    def test_none_buys_some_sells(self) -> None:
        tokens = [_token(buys_24h=None, sells_24h=50)]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Bearish"
        assert result["value"] == pytest.approx(0.0)

    def test_aggregates_multiple_tokens(self) -> None:
        tokens = [
            _token(buys_24h=100, sells_24h=50),
            _token(buys_24h=100, sells_24h=50),
        ]
        result = compute_buy_sell_ratio(tokens)
        # 200 / 100 = 2.0
        assert result["value"] == pytest.approx(2.0)
        assert result["label"] == "Bullish"

    def test_missing_fields_treated_as_none(self) -> None:
        tokens = [{}]
        result = compute_buy_sell_ratio(tokens)
        assert result["label"] == "Neutral"


# ---------------------------------------------------------------------------
# compute_volume_trend
# ---------------------------------------------------------------------------

class TestComputeVolumeTrend:

    def test_rising(self) -> None:
        result = compute_volume_trend(110.0, 100.0)
        assert result["label"] == "Rising"
        assert result["color"] == "green"

    def test_falling(self) -> None:
        result = compute_volume_trend(90.0, 100.0)
        assert result["label"] == "Falling"
        assert result["color"] == "red"

    def test_flat(self) -> None:
        result = compute_volume_trend(103.0, 100.0)
        assert result["label"] == "Flat"
        assert result["color"] == "yellow"

    def test_exactly_5_percent_up(self) -> None:
        # Exactly 5% is NOT > 5%, so Flat
        result = compute_volume_trend(105.0, 100.0)
        assert result["label"] == "Flat"

    def test_exactly_5_percent_down(self) -> None:
        # Exactly -5% is NOT < -5%, so Flat
        result = compute_volume_trend(95.0, 100.0)
        assert result["label"] == "Flat"

    def test_zero_previous_positive_current(self) -> None:
        result = compute_volume_trend(100.0, 0.0)
        assert result["label"] == "Rising"
        assert result["color"] == "green"

    def test_zero_previous_zero_current(self) -> None:
        result = compute_volume_trend(0.0, 0.0)
        assert result["label"] == "Flat"
        assert result["color"] == "yellow"

    def test_negative_previous(self) -> None:
        result = compute_volume_trend(100.0, -10.0)
        assert result["label"] == "Rising"

    def test_both_zero(self) -> None:
        result = compute_volume_trend(0.0, 0.0)
        assert result["label"] == "Flat"


# ---------------------------------------------------------------------------
# compute_whale_activity
# ---------------------------------------------------------------------------

class TestComputeWhaleActivity:

    def test_high(self) -> None:
        result = compute_whale_activity(10)
        assert result["label"] == "High"
        assert result["color"] == "green"

    def test_moderate(self) -> None:
        result = compute_whale_activity(3)
        assert result["label"] == "Moderate"
        assert result["color"] == "yellow"

    def test_low(self) -> None:
        result = compute_whale_activity(1)
        assert result["label"] == "Low"
        assert result["color"] == "dim"

    def test_boundary_6_is_high(self) -> None:
        result = compute_whale_activity(6)
        assert result["label"] == "High"

    def test_boundary_5_is_moderate(self) -> None:
        result = compute_whale_activity(5)
        assert result["label"] == "Moderate"

    def test_boundary_2_is_moderate(self) -> None:
        result = compute_whale_activity(2)
        assert result["label"] == "Moderate"

    def test_boundary_1_is_low(self) -> None:
        result = compute_whale_activity(1)
        assert result["label"] == "Low"

    def test_zero(self) -> None:
        result = compute_whale_activity(0)
        assert result["label"] == "Low"
        assert result["color"] == "dim"


# ---------------------------------------------------------------------------
# generate_recommendation
# ---------------------------------------------------------------------------

class TestGenerateRecommendation:

    def test_all_bullish(self) -> None:
        rec = generate_recommendation("Bullish", "Rising", "High")
        assert "momentum" in rec.lower() or "trend favors longs" in rec.lower()

    def test_all_bearish(self) -> None:
        rec = generate_recommendation("Bearish", "Falling", "Low")
        assert "reversal" in rec.lower() or "declining" in rec.lower()

    def test_mixed_volume_rising(self) -> None:
        rec = generate_recommendation("Neutral", "Rising", "Moderate")
        assert "mixed signals" in rec.lower() or "confirmation" in rec.lower()

    def test_whale_accumulation_quiet(self) -> None:
        rec = generate_recommendation("Neutral", "Flat", "High")
        assert "whale" in rec.lower() or "breakout" in rec.lower()

    def test_whale_high_falling_volume(self) -> None:
        rec = generate_recommendation("Bullish", "Falling", "High")
        assert "whale" in rec.lower() or "breakout" in rec.lower()

    def test_bullish_flat_volume(self) -> None:
        rec = generate_recommendation("Bullish", "Flat", "Moderate")
        assert "follow-through" in rec.lower() or "confirmation" in rec.lower()

    def test_bearish_rising_volume(self) -> None:
        rec = generate_recommendation("Bearish", "Rising", "Moderate")
        assert "caution" in rec.lower() or "sell pressure" in rec.lower()

    def test_default_fallback(self) -> None:
        rec = generate_recommendation("Neutral", "Flat", "Moderate")
        assert "mixed signals" in rec.lower() or "wait" in rec.lower()

    def test_returns_string(self) -> None:
        rec = generate_recommendation("Bullish", "Rising", "High")
        assert isinstance(rec, str)
        assert len(rec) > 0


# ---------------------------------------------------------------------------
# compute_all_signals
# ---------------------------------------------------------------------------

class TestComputeAllSignals:

    def test_returns_expected_keys(self) -> None:
        tokens = [_token()]
        result = compute_all_signals(tokens, prev_volume=40_000.0, whale_count=3)
        expected_keys = {
            "buy_sell_ratio",
            "buy_sell_label",
            "buy_sell_color",
            "volume_label",
            "volume_color",
            "whale_label",
            "whale_color",
            "recommendation",
        }
        assert set(result.keys()) == expected_keys

    def test_aggregates_volume_from_tokens(self) -> None:
        tokens = [
            _token(volume_24h=30_000.0),
            _token(volume_24h=30_000.0),
        ]
        # Total = 60_000, prev = 50_000 => 20% up => Rising
        result = compute_all_signals(tokens, prev_volume=50_000.0, whale_count=0)
        assert result["volume_label"] == "Rising"

    def test_empty_tokens(self) -> None:
        result = compute_all_signals([], prev_volume=0.0, whale_count=0)
        assert result["buy_sell_label"] == "Neutral"
        assert result["volume_label"] == "Flat"
        assert result["whale_label"] == "Low"
        assert isinstance(result["recommendation"], str)

    def test_bullish_scenario(self) -> None:
        tokens = [_token(buys_24h=300, sells_24h=100, volume_24h=200_000.0)]
        result = compute_all_signals(tokens, prev_volume=100_000.0, whale_count=10)
        assert result["buy_sell_label"] == "Bullish"
        assert result["volume_label"] == "Rising"
        assert result["whale_label"] == "High"

    def test_none_volume_in_tokens(self) -> None:
        tokens = [_token(volume_24h=None)]
        result = compute_all_signals(tokens, prev_volume=100.0, whale_count=0)
        # volume should be 0, previous 100 => Falling
        assert result["volume_label"] == "Falling"
