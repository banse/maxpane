"""Tests for Base chain models and client.

Covers model construction, response parsing for all three upstream APIs,
and full client methods with mocked HTTP responses.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from maxpane_dashboard.data.base_client import BaseChainClient
from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken, TokenLaunch, TrendingPool


# ---------------------------------------------------------------------------
# Fixtures: realistic API response payloads
# ---------------------------------------------------------------------------

DEXSCREENER_PAIR = {
    "baseToken": {
        "address": "0xAbC1230000000000000000000000000000000001",
        "name": "TestToken",
        "symbol": "TEST",
    },
    "priceUsd": "1.23",
    "priceChange": {"m5": 0.5, "h1": 2.1, "h24": -3.4},
    "volume": {"h24": 500000},
    "marketCap": 10000000,
    "fdv": 15000000,
    "liquidity": {"usd": 2000000},
    "pairAddress": "0xPAIR000000000000000000000000000000000001",
    "dexId": "aerodrome",
    "pairCreatedAt": "2025-12-01T00:00:00Z",
}

DEXSCREENER_RESPONSE = {"pairs": [DEXSCREENER_PAIR]}

BANKR_RESPONSE_TEXT = """Here are the top 20 trending tokens on Base:

1. TestToken ($TEST)
   - Price: $1.23
   - 24h Change: -3.4%
   - 24h Volume: $500,000
   - Market Cap: $10,000,000
   - Contract Address: 0xAbC1230000000000000000000000000000000001
   - Note: Popular DeFi token on Base

2. AnotherToken ($ANOT)
   - Price: $0.05
   - 24h Change: +12.5%
   - 24h Volume: $250,000
   - Market Cap: $5,000,000
   - Contract Address: 0xDeF4560000000000000000000000000000000002
   - Note: Meme token gaining traction

3. DuplicateAddr ($DUP)
   - Price: $0.01
   - Contract: 0xAbC1230000000000000000000000000000000001
   - Note: Should be deduplicated
"""

CLANKER_RESPONSE = {
    "data": [
        {
            "contract_address": "0xCLA1000000000000000000000000000000000001",
            "name": "LaunchToken",
            "symbol": "LAUNCH",
            "created_at": "2026-03-27T10:00:00Z",
            "type": "graduated",
            "deployer": "clanker",
            "description": "A test token",
        },
        {
            "contract_address": "0xCLA2000000000000000000000000000000000002",
            "name": "NewCoin",
            "symbol": "NEW",
            "created_at": "2026-03-27T09:30:00Z",
            "type": "active",
            "deployer": "",
            "description": "Deployed using @bankrbot on X",
        },
        {
            "contract_address": "0xCLA3000000000000000000000000000000000003",
            "name": "FreshMint",
            "symbol": "FRESH",
            "created_at": "2026-03-27T09:00:00Z",
            "type": "active",
            "deployer": "",
            "description": "",
        },
    ]
}

CLANKER_DEXSCREENER_PAIR = {
    "baseToken": {
        "address": "0xCLA1000000000000000000000000000000000001",
        "name": "LaunchToken",
        "symbol": "LAUNCH",
    },
    "priceUsd": "0.042",
    "priceChange": {"m5": 12.5, "h1": 35.0, "h24": 150.0},
    "volume": {"h24": 75000},
    "marketCap": 420000,
    "liquidity": {"usd": 50000},
    "txns": {"h24": {"buys": 120, "sells": 45}},
    "pairAddress": "0xPAIR_CLA1",
    "dexId": "uniswap",
}

GECKO_RESPONSE = {
    "data": [
        {
            "id": "base_pool_0x1111",
            "type": "pool",
            "attributes": {
                "address": "0x1111000000000000000000000000000000000001",
                "name": "TEST/WETH",
                "base_token_price_usd": "1.50",
                "price_change_percentage": {"m5": 1.0, "h1": 3.0, "h24": -5.0},
                "volume_usd": {"h24": "750000"},
                "reserve_in_usd": "3000000",
                "market_cap_usd": "12000000",
                "fdv_usd": "18000000",
                "pool_created_at": "2025-11-15T10:30:00Z",
            },
            "relationships": {
                "base_token": {
                    "data": {"id": "base_token_0xaaa", "type": "token"}
                }
            },
        }
    ],
    "included": [
        {
            "id": "base_token_0xaaa",
            "type": "token",
            "attributes": {
                "address": "0xAAA0000000000000000000000000000000000001",
                "name": "GeckoToken",
                "symbol": "GECK",
                "image_url": "https://example.com/geck.png",
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------

class TestBaseTokenModel:
    def test_construction_minimal(self) -> None:
        token = BaseToken(
            address="0x1234",
            name="Foo",
            symbol="FOO",
            price_usd=1.0,
            price_change_5m=None,
            price_change_1h=None,
            price_change_24h=None,
            volume_24h=100.0,
            market_cap=1000.0,
            fdv=None,
            liquidity=500.0,
            pair_address=None,
            dex=None,
            created_at=None,
        )
        assert token.address == "0x1234"
        assert token.symbol == "FOO"
        assert token.price_change_5m is None

    def test_frozen(self) -> None:
        token = BaseToken(
            address="0x1",
            name="T",
            symbol="T",
            price_usd=0,
            price_change_5m=None,
            price_change_1h=None,
            price_change_24h=None,
            volume_24h=0,
            market_cap=0,
            fdv=None,
            liquidity=0,
            pair_address=None,
            dex=None,
            created_at=None,
        )
        with pytest.raises(Exception):
            token.price_usd = 99.0  # type: ignore[misc]

    def test_from_dexscreener_pair(self) -> None:
        token = BaseToken.from_dexscreener_pair(DEXSCREENER_PAIR)
        assert token.address == "0xabc1230000000000000000000000000000000001"
        assert token.name == "TestToken"
        assert token.symbol == "TEST"
        assert token.price_usd == 1.23
        assert token.price_change_5m == 0.5
        assert token.price_change_1h == 2.1
        assert token.price_change_24h == -3.4
        assert token.volume_24h == 500000.0
        assert token.market_cap == 10000000.0
        assert token.fdv == 15000000.0
        assert token.liquidity == 2000000.0
        assert token.dex == "aerodrome"

    def test_from_dexscreener_pair_missing_fields(self) -> None:
        """Gracefully handles missing nested fields."""
        minimal = {"baseToken": {"address": "0x" + "a" * 40}}
        token = BaseToken.from_dexscreener_pair(minimal)
        assert token.price_usd == 0.0
        assert token.price_change_5m is None
        assert token.volume_24h == 0.0


class TestTrendingPoolModel:
    def test_construction(self) -> None:
        pool = TrendingPool(
            pool_address="0xpool",
            token_name="PoolToken",
            token_symbol="PT",
            token_address="0xtoken",
            price_usd=2.5,
            volume_24h=100000,
            price_change_24h=-1.5,
        )
        assert pool.token_symbol == "PT"
        assert pool.price_change_24h == -1.5

    def test_frozen(self) -> None:
        pool = TrendingPool(
            pool_address="0x1",
            token_name="T",
            token_symbol="T",
            token_address="0x2",
            price_usd=0,
            volume_24h=0,
            price_change_24h=0,
        )
        with pytest.raises(Exception):
            pool.price_usd = 99.0  # type: ignore[misc]

    def test_from_gecko_pool(self) -> None:
        # Build token map from included
        token_map = {
            item["id"]: item["attributes"]
            for item in GECKO_RESPONSE["included"]
            if item["type"] == "token"
        }
        pool = TrendingPool.from_gecko_pool(GECKO_RESPONSE["data"][0], token_map)
        assert pool is not None
        assert pool.token_name == "GeckoToken"
        assert pool.token_symbol == "GECK"
        assert pool.token_address == "0xaaa0000000000000000000000000000000000001"
        assert pool.price_usd == 1.5
        assert pool.volume_24h == 750000.0
        assert pool.price_change_24h == -5.0

    def test_from_gecko_pool_missing_token(self) -> None:
        """Returns None when base token address cannot be resolved."""
        pool_data = {
            "attributes": {"address": "0xpool"},
            "relationships": {"base_token": {"data": {"id": "nonexistent"}}},
        }
        result = TrendingPool.from_gecko_pool(pool_data, {})
        assert result is None


class TestBaseSnapshotModel:
    def test_construction(self) -> None:
        snap = BaseSnapshot(
            trending_tokens=(),
            trending_pools=(),
            launches=(),
            fetched_at=time.time(),
        )
        assert len(snap.trending_tokens) == 0
        assert len(snap.launches) == 0
        assert snap.fetched_at > 0


# ---------------------------------------------------------------------------
# TokenLaunch model tests
# ---------------------------------------------------------------------------


class TestTokenLaunchModel:
    def test_construction_minimal(self) -> None:
        launch = TokenLaunch(
            address="0xabc",
            name="Test",
            symbol="TST",
            deployer="clanker",
            created_at=1711540800,
            age_seconds=60,
            initial_liquidity=None,
            current_price=None,
            price_change_5m=None,
            market_cap=None,
            volume_24h=None,
            buy_count=None,
            sell_count=None,
            graduated=False,
        )
        assert launch.address == "0xabc"
        assert launch.deployer == "clanker"
        assert launch.graduated is False

    def test_frozen(self) -> None:
        launch = TokenLaunch(
            address="0x1",
            name="T",
            symbol="T",
            deployer="clanker",
            created_at=0,
            age_seconds=0,
            initial_liquidity=None,
            current_price=None,
            price_change_5m=None,
            market_cap=None,
            volume_24h=None,
            buy_count=None,
            sell_count=None,
            graduated=False,
        )
        with pytest.raises(Exception):
            launch.graduated = True  # type: ignore[misc]

    def test_from_clanker_token_basic(self) -> None:
        raw = CLANKER_RESPONSE["data"][0]
        now = 1711540800.0  # fixed timestamp for deterministic test
        launch = TokenLaunch.from_clanker_token(raw, now=now)
        assert launch.address == "0xcla1000000000000000000000000000000000001"
        assert launch.name == "LaunchToken"
        assert launch.symbol == "LAUNCH"
        assert launch.deployer == "clanker"
        assert launch.graduated is True
        assert launch.current_price is None  # no market data

    def test_from_clanker_token_with_market_data(self) -> None:
        raw = CLANKER_RESPONSE["data"][0]
        now = 1711540800.0
        launch = TokenLaunch.from_clanker_token(
            raw, market_data=CLANKER_DEXSCREENER_PAIR, now=now
        )
        assert launch.current_price == 0.042
        assert launch.price_change_5m == 12.5
        assert launch.market_cap == 420000.0
        assert launch.volume_24h == 75000.0
        assert launch.buy_count == 120
        assert launch.sell_count == 45
        assert launch.initial_liquidity == 50000.0

    def test_from_clanker_token_bankr_deployer(self) -> None:
        raw = CLANKER_RESPONSE["data"][1]
        launch = TokenLaunch.from_clanker_token(raw, now=1711540800.0)
        assert launch.deployer == "bankr"
        assert launch.graduated is False

    def test_from_clanker_token_unknown_deployer(self) -> None:
        raw = CLANKER_RESPONSE["data"][2]
        launch = TokenLaunch.from_clanker_token(raw, now=1711540800.0)
        # Default deployer for Clanker API tokens is "clanker"
        assert launch.deployer == "clanker"


class TestClankerResponseParsing:
    @pytest.mark.asyncio
    async def test_parses_clanker_response(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")

        # Mock both Clanker API and DexScreener calls
        call_count = 0

        async def _mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "clanker.world" in url:
                return _make_response(CLANKER_RESPONSE)
            # DexScreener enrichment
            return _make_response({"pairs": [CLANKER_DEXSCREENER_PAIR]})

        client._request_with_retry = _mock_request  # type: ignore[method-assign]
        client._last_dex_request = 0.0

        launches = await client.get_clanker_launches(limit=30)

        assert len(launches) == 3
        assert launches[0].symbol == "LAUNCH"
        assert launches[0].graduated is True
        # First token should be enriched
        assert launches[0].current_price == 0.042
        await client.close()

    @pytest.mark.asyncio
    async def test_clanker_api_failure_returns_empty(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.HTTPError("Clanker down")
        )

        launches = await client.get_clanker_launches()
        assert launches == []
        await client.close()

    @pytest.mark.asyncio
    async def test_dexscreener_failure_still_returns_launches(self) -> None:
        """If DexScreener fails, launches are returned without market data."""
        client = BaseChainClient(bankr_api_key="test_key")

        call_count = 0

        async def _mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "clanker.world" in url:
                return _make_response(CLANKER_RESPONSE)
            raise httpx.HTTPError("DexScreener down")

        client._request_with_retry = _mock_request  # type: ignore[method-assign]
        client._last_dex_request = 0.0

        launches = await client.get_clanker_launches()
        assert len(launches) == 3
        assert launches[0].current_price is None  # no enrichment
        await client.close()


class TestLaunchStats:
    def test_basic_stats(self) -> None:
        now = time.time()
        launches = [
            TokenLaunch(
                address=f"0x{i}",
                name=f"T{i}",
                symbol=f"T{i}",
                deployer="clanker",
                created_at=int(now - i * 600),  # spaced 10 min apart
                age_seconds=i * 600,
                initial_liquidity=None,
                current_price=None,
                price_change_5m=None,
                market_cap=None,
                volume_24h=None,
                buy_count=None,
                sell_count=None,
                graduated=(i == 0),
            )
            for i in range(6)
        ]

        stats = BaseChainClient.get_launch_stats(launches)

        assert stats["total_launches_1h"] == 6  # all within last hour
        assert stats["graduated_count"] == 1
        assert stats["avg_age"] > 0
        assert stats["launch_rate_per_hour"] > 0

    def test_empty_launches(self) -> None:
        stats = BaseChainClient.get_launch_stats([])
        assert stats["total_launches_1h"] == 0
        assert stats["graduated_count"] == 0
        assert stats["avg_age"] == 0.0
        assert stats["launch_rate_per_hour"] == 0.0

    def test_single_launch(self) -> None:
        now = time.time()
        launches = [
            TokenLaunch(
                address="0x1",
                name="Solo",
                symbol="SOLO",
                deployer="clanker",
                created_at=int(now - 300),
                age_seconds=300,
                initial_liquidity=None,
                current_price=None,
                price_change_5m=None,
                market_cap=None,
                volume_24h=None,
                buy_count=None,
                sell_count=None,
                graduated=True,
            )
        ]
        stats = BaseChainClient.get_launch_stats(launches)
        assert stats["total_launches_1h"] == 1
        assert stats["graduated_count"] == 1


# ---------------------------------------------------------------------------
# Bankr response parsing tests
# ---------------------------------------------------------------------------

class TestBankrParsing:
    def test_parse_addresses_from_response(self) -> None:
        addresses = BaseChainClient.parse_addresses_from_response(BANKR_RESPONSE_TEXT)
        # Should extract 2 unique addresses (third is a duplicate)
        assert len(addresses) == 2
        assert addresses[0] == "0xabc1230000000000000000000000000000000001"
        assert addresses[1] == "0xdef4560000000000000000000000000000000002"

    def test_parse_addresses_empty_text(self) -> None:
        addresses = BaseChainClient.parse_addresses_from_response("")
        assert addresses == []

    def test_parse_addresses_no_matches(self) -> None:
        addresses = BaseChainClient.parse_addresses_from_response(
            "No tokens found today, the market is quiet."
        )
        assert addresses == []

    def test_parse_addresses_contract_without_address_word(self) -> None:
        """Matches 'Contract: 0x...' in addition to 'Contract Address: 0x...'."""
        text = "1. Token ($TKN)\n   - Contract: 0x1234567890abcdef1234567890abcdef12345678\n"
        addresses = BaseChainClient.parse_addresses_from_response(text)
        assert len(addresses) == 1
        assert addresses[0] == "0x1234567890abcdef1234567890abcdef12345678"


# ---------------------------------------------------------------------------
# Client method tests (mocked HTTP)
# ---------------------------------------------------------------------------

def _make_response(json_data: dict | list, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response."""
    import json as json_mod

    return httpx.Response(
        status_code=status_code,
        content=json_mod.dumps(json_data).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://test"),
    )


class TestEnrichTokens:
    @pytest.mark.asyncio
    async def test_enrich_single_batch(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response(DEXSCREENER_RESPONSE)
        )
        client._last_dex_request = 0.0  # skip rate limit wait

        tokens = await client.enrich_tokens(
            ["0xAbC1230000000000000000000000000000000001"]
        )

        assert len(tokens) == 1
        assert tokens[0].symbol == "TEST"
        assert tokens[0].price_usd == 1.23
        await client.close()

    @pytest.mark.asyncio
    async def test_enrich_empty_list(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        tokens = await client.enrich_tokens([])
        assert tokens == []
        await client.close()

    @pytest.mark.asyncio
    async def test_enrich_graceful_on_failure(self) -> None:
        """DexScreener failure returns empty list, not exception."""
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.HTTPError("Connection refused")
        )
        client._last_dex_request = 0.0

        tokens = await client.enrich_tokens(["0x" + "a" * 40])
        assert tokens == []
        await client.close()


class TestGetTrendingPools:
    @pytest.mark.asyncio
    async def test_parses_gecko_response(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response(GECKO_RESPONSE)
        )
        client._last_gecko_request = 0.0

        pools = await client.get_trending_pools()

        assert len(pools) == 1
        assert pools[0].token_name == "GeckoToken"
        assert pools[0].token_symbol == "GECK"
        assert pools[0].price_usd == 1.5
        await client.close()

    @pytest.mark.asyncio
    async def test_graceful_on_failure(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.HTTPError("timeout")
        )
        client._last_gecko_request = 0.0

        pools = await client.get_trending_pools()
        assert pools == []
        await client.close()


class TestGetTrendingTokens:
    @pytest.mark.asyncio
    async def test_gecko_to_dexscreener_pipeline(self) -> None:
        """Trending tokens: GeckoTerminal pools → extract addresses → DexScreener enrichment."""
        client = BaseChainClient(bankr_api_key="test_key")

        # Build a mock GeckoTerminal pool with a token address
        token_map = {
            item["id"]: item
            for item in GECKO_RESPONSE["included"]
            if item["type"] == "token"
        }
        gecko_pool = TrendingPool.from_gecko_pool(GECKO_RESPONSE["data"][0], token_map)
        client.get_trending_pools = AsyncMock(return_value=[gecko_pool])  # type: ignore[method-assign]

        # Mock DexScreener enrichment
        dex_resp = _make_response(DEXSCREENER_RESPONSE)
        client._request_with_retry = AsyncMock(return_value=dex_resp)  # type: ignore[method-assign]
        client._last_dex_request = 0.0

        tokens = await client.get_trending_tokens()

        assert len(tokens) >= 1
        assert tokens[0].symbol == "TEST"
        await client.close()

    @pytest.mark.asyncio
    async def test_gecko_failure_returns_empty(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client.get_trending_pools = AsyncMock(return_value=[])  # type: ignore[method-assign]

        tokens = await client.get_trending_tokens()
        assert tokens == []
        await client.close()


class TestFetchSnapshot:
    @pytest.mark.asyncio
    async def test_concurrent_fetch(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")

        # Stub all three public methods
        client.get_trending_tokens = AsyncMock(return_value=[  # type: ignore[method-assign]
            BaseToken.from_dexscreener_pair(DEXSCREENER_PAIR)
        ])

        token_map = {
            item["id"]: item["attributes"]
            for item in GECKO_RESPONSE["included"]
            if item["type"] == "token"
        }
        gecko_pool = TrendingPool.from_gecko_pool(GECKO_RESPONSE["data"][0], token_map)
        client.get_trending_pools = AsyncMock(return_value=[gecko_pool])  # type: ignore[method-assign]

        mock_launch = TokenLaunch.from_clanker_token(
            CLANKER_RESPONSE["data"][0], now=time.time()
        )
        client.get_clanker_launches = AsyncMock(return_value=[mock_launch])  # type: ignore[method-assign]

        snapshot = await client.fetch_snapshot()

        assert isinstance(snapshot, BaseSnapshot)
        assert len(snapshot.trending_tokens) == 1
        assert len(snapshot.trending_pools) == 1
        assert len(snapshot.launches) == 1
        assert snapshot.fetched_at > 0
        await client.close()

    @pytest.mark.asyncio
    async def test_partial_failure(self) -> None:
        """If one source fails the others still populate."""
        client = BaseChainClient(bankr_api_key="test_key")

        client.get_trending_tokens = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("bankr down")
        )
        client.get_trending_pools = AsyncMock(return_value=[])  # type: ignore[method-assign]
        client.get_clanker_launches = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("clanker down")
        )

        snapshot = await client.fetch_snapshot()

        assert isinstance(snapshot, BaseSnapshot)
        assert len(snapshot.trending_tokens) == 0
        assert len(snapshot.trending_pools) == 0
        assert len(snapshot.launches) == 0
        await client.close()


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        async with BaseChainClient(bankr_api_key="test") as client:
            assert client._bankr_api_key == "test"

    @pytest.mark.asyncio
    async def test_env_fallback(self) -> None:
        with patch.dict("os.environ", {"BANKR_API_KEY": "env_key", "ALCHEMY_API_KEY": "alch_key"}):
            client = BaseChainClient()
            assert client._bankr_api_key == "env_key"
            assert client._alchemy_api_key == "alch_key"
            await client.close()
