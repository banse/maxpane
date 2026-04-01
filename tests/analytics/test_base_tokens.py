"""Tests for Base chain token analytics."""

import pytest

from maxpane_dashboard.analytics.base_tokens import (
    calculate_momentum_score,
    classify_token_status,
    format_change,
    format_market_cap,
    format_price,
    format_volume,
    get_top_movers,
    get_volume_leaders,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _token(**kwargs) -> dict:
    """Build a minimal token dict with sensible defaults."""
    defaults = {
        "address": "0xabc",
        "name": "TestToken",
        "symbol": "TST",
        "price_usd": 1.0,
        "price_change_5m": 0.0,
        "price_change_1h": 0.0,
        "price_change_24h": 0.0,
        "volume_24h": 100_000,
        "market_cap": 1_000_000,
        "fdv": 2_000_000,
        "liquidity": 50_000,
        "pair_address": "0xpair",
        "dex": "aerodrome",
        "created_at": "2026-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return defaults


@pytest.fixture
def sample_tokens() -> list[dict]:
    return [
        _token(name="MoonCoin", symbol="MOON", price_change_24h=42.0, price_change_1h=15.0, price_change_5m=8.0, volume_24h=5_000_000),
        _token(name="StableCoin", symbol="STBL", price_change_24h=0.1, price_change_1h=0.0, price_change_5m=0.0, volume_24h=2_000_000),
        _token(name="DumpCoin", symbol="DUMP", price_change_24h=-35.0, price_change_1h=-10.0, price_change_5m=-3.0, volume_24h=800_000),
        _token(name="MidCoin", symbol="MID", price_change_24h=5.0, price_change_1h=2.0, price_change_5m=1.0, volume_24h=1_200_000),
        _token(name="RecoverCoin", symbol="REC", price_change_24h=-15.0, price_change_1h=3.0, price_change_5m=1.0, volume_24h=900_000),
        _token(name="PumpCoin", symbol="PUMP", price_change_24h=20.0, price_change_1h=12.0, price_change_5m=7.0, volume_24h=3_000_000),
        _token(name="NullCoin", symbol="NUL", price_change_24h=None, volume_24h=100),
    ]


# ---------------------------------------------------------------------------
# format_price
# ---------------------------------------------------------------------------

class TestFormatPrice:

    def test_above_one_dollar(self) -> None:
        assert format_price(1234.56) == "$1,234.56"

    def test_one_dollar(self) -> None:
        assert format_price(1.0) == "$1.00"

    def test_above_one_cent(self) -> None:
        assert format_price(0.0123) == "$0.0123"

    def test_small_price(self) -> None:
        result = format_price(0.000042)
        assert result.startswith("$0.000")
        assert "42" in result

    def test_very_small_price_subscript(self) -> None:
        result = format_price(0.000000042)
        # Should use subscript notation for 7 leading zeros
        assert "$0.0" in result
        assert "42" in result

    def test_zero(self) -> None:
        assert format_price(0.0) == "$0.00"

    def test_none_returns_zero(self) -> None:
        assert format_price(None) == "$0.00"


# ---------------------------------------------------------------------------
# format_market_cap / format_volume
# ---------------------------------------------------------------------------

class TestFormatMarketCap:

    def test_zero(self) -> None:
        assert format_market_cap(0) == "$0"

    def test_hundreds(self) -> None:
        assert format_market_cap(500) == "$500"

    def test_thousands(self) -> None:
        assert format_market_cap(12_000) == "$12.0K"

    def test_millions(self) -> None:
        assert format_market_cap(1_200_000) == "$1.2M"

    def test_billions(self) -> None:
        assert format_market_cap(3_400_000_000) == "$3.4B"

    def test_format_volume_same_as_mcap(self) -> None:
        assert format_volume(48_200_000) == "$48.2M"


# ---------------------------------------------------------------------------
# format_change
# ---------------------------------------------------------------------------

class TestFormatChange:

    def test_positive(self) -> None:
        result = format_change(32.4)
        assert "+32.4%" in result
        assert "[green]" in result

    def test_negative(self) -> None:
        result = format_change(-8.1)
        assert "-8.1%" in result
        assert "[red]" in result

    def test_none(self) -> None:
        result = format_change(None)
        assert "[dim]" in result
        assert "—" in result

    def test_zero(self) -> None:
        result = format_change(0.0)
        assert "0.0%" in result
        assert "[dim]" in result


# ---------------------------------------------------------------------------
# get_top_movers
# ---------------------------------------------------------------------------

class TestGetTopMovers:

    def test_returns_gainers_and_losers(self, sample_tokens: list) -> None:
        gainers, losers = get_top_movers(sample_tokens, key="price_change_24h", limit=3)
        assert len(gainers) <= 3
        assert len(losers) <= 3
        # Top gainer should be MoonCoin (+42%)
        assert gainers[0]["symbol"] == "MOON"
        # Top loser should be DumpCoin (-35%)
        assert losers[0]["symbol"] == "DUMP"

    def test_gainers_only_positive(self, sample_tokens: list) -> None:
        gainers, _ = get_top_movers(sample_tokens, limit=10)
        for t in gainers:
            assert t["price_change_24h"] > 0

    def test_losers_only_negative(self, sample_tokens: list) -> None:
        _, losers = get_top_movers(sample_tokens, limit=10)
        for t in losers:
            assert t["price_change_24h"] < 0

    def test_excludes_none_values(self, sample_tokens: list) -> None:
        gainers, losers = get_top_movers(sample_tokens, limit=10)
        all_symbols = [t["symbol"] for t in gainers + losers]
        assert "NUL" not in all_symbols

    def test_different_timeframe(self, sample_tokens: list) -> None:
        gainers, _ = get_top_movers(sample_tokens, key="price_change_1h", limit=2)
        assert gainers[0]["symbol"] == "MOON"

    def test_empty_list(self) -> None:
        gainers, losers = get_top_movers([])
        assert gainers == []
        assert losers == []


# ---------------------------------------------------------------------------
# get_volume_leaders
# ---------------------------------------------------------------------------

class TestGetVolumeLeaders:

    def test_sorted_by_volume(self, sample_tokens: list) -> None:
        leaders = get_volume_leaders(sample_tokens, limit=3)
        assert len(leaders) == 3
        assert leaders[0]["symbol"] == "MOON"  # 5M volume

    def test_limit_respected(self, sample_tokens: list) -> None:
        leaders = get_volume_leaders(sample_tokens, limit=2)
        assert len(leaders) == 2


# ---------------------------------------------------------------------------
# calculate_momentum_score
# ---------------------------------------------------------------------------

class TestCalculateMomentumScore:

    def test_positive_momentum(self) -> None:
        token = _token(price_change_5m=10.0, price_change_1h=5.0, price_change_24h=2.0)
        score = calculate_momentum_score(token)
        # 10*0.5 + 5*0.3 + 2*0.2 = 5 + 1.5 + 0.4 = 6.9
        assert score == pytest.approx(6.9)

    def test_negative_momentum(self) -> None:
        token = _token(price_change_5m=-8.0, price_change_1h=-4.0, price_change_24h=-2.0)
        score = calculate_momentum_score(token)
        assert score == pytest.approx(-8 * 0.5 + -4 * 0.3 + -2 * 0.2)

    def test_none_treated_as_zero(self) -> None:
        token = _token(price_change_5m=None, price_change_1h=None, price_change_24h=10.0)
        score = calculate_momentum_score(token)
        assert score == pytest.approx(10.0 * 0.2)

    def test_all_zero(self) -> None:
        token = _token()
        assert calculate_momentum_score(token) == 0.0

    def test_recent_changes_weighted_more(self) -> None:
        # Same magnitude in 5m vs 24h should yield different contributions
        token_recent = _token(price_change_5m=10.0, price_change_1h=0.0, price_change_24h=0.0)
        token_old = _token(price_change_5m=0.0, price_change_1h=0.0, price_change_24h=10.0)
        assert calculate_momentum_score(token_recent) > calculate_momentum_score(token_old)


# ---------------------------------------------------------------------------
# classify_token_status
# ---------------------------------------------------------------------------

class TestClassifyTokenStatus:

    def test_pumping(self) -> None:
        token = _token(price_change_5m=8.0, price_change_1h=15.0, price_change_24h=30.0)
        assert classify_token_status(token) == "pumping"

    def test_recovering(self) -> None:
        token = _token(price_change_5m=1.0, price_change_1h=3.0, price_change_24h=-15.0)
        assert classify_token_status(token) == "recovering"

    def test_crashed(self) -> None:
        token = _token(price_change_5m=-1.0, price_change_1h=-5.0, price_change_24h=-35.0)
        assert classify_token_status(token) == "crashed"

    def test_dumping(self) -> None:
        token = _token(price_change_5m=-2.0, price_change_1h=-8.0, price_change_24h=-5.0)
        assert classify_token_status(token) == "dumping"

    def test_stable(self) -> None:
        token = _token(price_change_5m=0.5, price_change_1h=1.0, price_change_24h=2.0)
        assert classify_token_status(token) == "stable"

    def test_none_values_treated_as_zero(self) -> None:
        token = _token(price_change_5m=None, price_change_1h=None, price_change_24h=None)
        assert classify_token_status(token) == "stable"
