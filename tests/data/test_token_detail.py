"""Tests for token detail fetching -- model, client, and manager.

Covers:
- TokenDetail model construction and DexScreener parsing
- BaseChainClient.get_token_detail with mocked HTTP
- BaseChainClient.get_token_trades with mocked GeckoTerminal
- BaseManager token selection and on-demand fetching
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from maxpane_dashboard.data.base_client import BaseChainClient
from maxpane_dashboard.data.base_manager import BaseManager
from maxpane_dashboard.data.base_models import TokenDetail


# ---------------------------------------------------------------------------
# Fixtures: realistic API response payloads
# ---------------------------------------------------------------------------

DEXSCREENER_TOKEN_RESPONSE: dict[str, Any] = {
    "pairs": [
        {
            "chainId": "base",
            "baseToken": {
                "address": "0xAbC1230000000000000000000000000000000001",
                "name": "DetailToken",
                "symbol": "DTK",
            },
            "quoteToken": {
                "address": "0xWETH",
                "name": "Wrapped Ether",
                "symbol": "WETH",
            },
            "priceUsd": "2.50",
            "priceChange": {"m5": 1.2, "h1": -0.8, "h24": 5.5},
            "volume": {"h24": 750000},
            "marketCap": 25000000,
            "fdv": 30000000,
            "liquidity": {"usd": 5000000},
            "pairAddress": "0xPAIR_DTK_WETH",
            "dexId": "aerodrome",
            "pairCreatedAt": "2026-01-15T12:00:00Z",
            "labels": ["v3-0.3%"],
            "txns": {
                "h24": {"buys": 450, "sells": 210},
                "h1": {"buys": 35, "sells": 12},
            },
        },
        # Lower-liquidity pair on Base -- should NOT be selected
        {
            "chainId": "base",
            "baseToken": {
                "address": "0xAbC1230000000000000000000000000000000001",
                "name": "DetailToken",
                "symbol": "DTK",
            },
            "quoteToken": {"symbol": "USDC"},
            "priceUsd": "2.49",
            "priceChange": {"h24": 5.3},
            "volume": {"h24": 50000},
            "marketCap": 25000000,
            "liquidity": {"usd": 100000},
            "pairAddress": "0xPAIR_DTK_USDC",
            "dexId": "uniswap",
            "txns": {"h24": {"buys": 10, "sells": 5}, "h1": {"buys": 1, "sells": 0}},
        },
    ]
}

# Pair on a different chain (should be filtered out)
DEXSCREENER_MULTICHAIN_RESPONSE: dict[str, Any] = {
    "pairs": [
        {
            "chainId": "ethereum",
            "baseToken": {"address": "0xETH_TOKEN", "name": "EthToken", "symbol": "ET"},
            "quoteToken": {"symbol": "USDT"},
            "priceUsd": "10.0",
            "liquidity": {"usd": 9000000},
            "txns": {"h24": {}, "h1": {}},
        },
        {
            "chainId": "base",
            "baseToken": {"address": "0xBASE_TOKEN", "name": "BaseToken", "symbol": "BT"},
            "quoteToken": {"symbol": "WETH"},
            "priceUsd": "1.0",
            "liquidity": {"usd": 2000000},
            "pairAddress": "0xBASE_PAIR",
            "txns": {"h24": {"buys": 100, "sells": 50}, "h1": {"buys": 10, "sells": 5}},
        },
    ]
}

GECKO_TRADES_RESPONSE: dict[str, Any] = {
    "data": [
        {
            "id": "trade_1",
            "type": "trade",
            "attributes": {
                "block_timestamp": "2026-03-27T14:30:00Z",
                "kind": "buy",
                "price_from_in_usd": "2.50",
                "from_token_amount": "100.5",
                "volume_in_usd": "251.25",
                "tx_from_address": "0xBuyer1",
            },
        },
        {
            "id": "trade_2",
            "type": "trade",
            "attributes": {
                "block_timestamp": "2026-03-27T14:29:00Z",
                "kind": "sell",
                "price_to_in_usd": "2.48",
                "to_token_amount": "50.0",
                "volume_in_usd": "124.00",
                "tx_from_address": "0xSeller1",
            },
        },
        {
            "id": "trade_3",
            "type": "trade",
            "attributes": {
                "block_timestamp": "2026-03-27T14:28:00Z",
                "kind": "buy",
                "price_from_in_usd": "2.45",
                "from_token_amount": "200.0",
                "volume_in_usd": "490.00",
                "tx_from_address": "0xBuyer2",
            },
        },
    ]
}


# ---------------------------------------------------------------------------
# Helper
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


# ---------------------------------------------------------------------------
# TokenDetail model tests
# ---------------------------------------------------------------------------

class TestTokenDetailModel:
    def test_construction_minimal(self) -> None:
        detail = TokenDetail(
            address="0x1234",
            name="Test",
            symbol="TST",
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
            base_token_symbol="TST",
            quote_token_symbol="WETH",
            fee_tier=None,
            buys_24h=0,
            sells_24h=0,
            buys_1h=0,
            sells_1h=0,
            price_history=[],
        )
        assert detail.address == "0x1234"
        assert detail.base_token_symbol == "TST"
        assert detail.quote_token_symbol == "WETH"
        assert detail.buys_24h == 0
        assert detail.price_history == []

    def test_frozen(self) -> None:
        detail = TokenDetail(
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
            base_token_symbol="T",
            quote_token_symbol="Q",
            fee_tier=None,
            buys_24h=0,
            sells_24h=0,
            buys_1h=0,
            sells_1h=0,
            price_history=[],
        )
        with pytest.raises(Exception):
            detail.price_usd = 99.0  # type: ignore[misc]

    def test_from_dexscreener_pair(self) -> None:
        pair = DEXSCREENER_TOKEN_RESPONSE["pairs"][0]
        detail = TokenDetail.from_dexscreener_pair(pair)

        assert detail.address == "0xabc1230000000000000000000000000000000001"
        assert detail.name == "DetailToken"
        assert detail.symbol == "DTK"
        assert detail.price_usd == 2.50
        assert detail.price_change_5m == 1.2
        assert detail.price_change_1h == -0.8
        assert detail.price_change_24h == 5.5
        assert detail.volume_24h == 750000.0
        assert detail.market_cap == 25000000.0
        assert detail.fdv == 30000000.0
        assert detail.liquidity == 5000000.0
        assert detail.pair_address == "0xPAIR_DTK_WETH"
        assert detail.dex == "aerodrome"
        assert detail.base_token_symbol == "DTK"
        assert detail.quote_token_symbol == "WETH"
        assert detail.fee_tier == "v3-0.3%"
        assert detail.buys_24h == 450
        assert detail.sells_24h == 210
        assert detail.buys_1h == 35
        assert detail.sells_1h == 12
        assert detail.price_history == []

    def test_from_dexscreener_pair_missing_fields(self) -> None:
        """Gracefully handles missing nested fields."""
        minimal: dict[str, Any] = {
            "baseToken": {"address": "0x" + "a" * 40},
            "txns": {},
        }
        detail = TokenDetail.from_dexscreener_pair(minimal)
        assert detail.price_usd == 0.0
        assert detail.price_change_5m is None
        assert detail.buys_24h == 0
        assert detail.sells_24h == 0
        assert detail.buys_1h == 0
        assert detail.sells_1h == 0
        assert detail.quote_token_symbol == "???"
        assert detail.fee_tier is None

    def test_from_dexscreener_pair_no_labels(self) -> None:
        """fee_tier is None when labels list is empty."""
        pair = dict(DEXSCREENER_TOKEN_RESPONSE["pairs"][0])
        pair["labels"] = []
        detail = TokenDetail.from_dexscreener_pair(pair)
        assert detail.fee_tier is None


# ---------------------------------------------------------------------------
# Client: get_token_detail tests
# ---------------------------------------------------------------------------

class TestGetTokenDetail:
    @pytest.mark.asyncio
    async def test_selects_highest_liquidity_base_pair(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response(DEXSCREENER_TOKEN_RESPONSE)
        )
        client._last_dex_request = 0.0

        detail = await client.get_token_detail(
            "0xAbC1230000000000000000000000000000000001"
        )

        assert detail is not None
        assert detail.pair_address == "0xPAIR_DTK_WETH"
        assert detail.liquidity == 5000000.0
        assert detail.quote_token_symbol == "WETH"
        await client.close()

    @pytest.mark.asyncio
    async def test_filters_to_base_chain(self) -> None:
        """When multiple chains are present, only Base pairs are considered."""
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response(DEXSCREENER_MULTICHAIN_RESPONSE)
        )
        client._last_dex_request = 0.0

        detail = await client.get_token_detail("0xBASE_TOKEN")

        assert detail is not None
        assert detail.pair_address == "0xBASE_PAIR"
        assert detail.name == "BaseToken"
        await client.close()

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_pairs(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response({"pairs": []})
        )
        client._last_dex_request = 0.0

        detail = await client.get_token_detail("0xNONEXISTENT")
        assert detail is None
        await client.close()

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.HTTPError("DexScreener down")
        )
        client._last_dex_request = 0.0

        detail = await client.get_token_detail("0xFAIL")
        assert detail is None
        await client.close()


# ---------------------------------------------------------------------------
# Client: get_token_trades tests
# ---------------------------------------------------------------------------

class TestGetTokenTrades:
    @pytest.mark.asyncio
    async def test_parses_gecko_trades(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response(GECKO_TRADES_RESPONSE)
        )
        client._last_gecko_request = 0.0

        trades = await client.get_token_trades("0xPAIR_DTK_WETH")

        assert len(trades) == 3
        assert trades[0]["type"] == "buy"
        assert trades[0]["price_usd"] == 2.50
        assert trades[0]["amount_token"] == 100.5
        assert trades[0]["amount_usd"] == 251.25
        assert trades[0]["maker"] == "0xBuyer1"
        assert trades[0]["timestamp"] == "2026-03-27T14:30:00Z"

        assert trades[1]["type"] == "sell"
        assert trades[1]["price_usd"] == 2.48
        await client.close()

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response(GECKO_TRADES_RESPONSE)
        )
        client._last_gecko_request = 0.0

        trades = await client.get_token_trades("0xPAIR", limit=2)
        assert len(trades) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self) -> None:
        """Graceful degradation when GeckoTerminal fails."""
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.HTTPError("GeckoTerminal down")
        )
        client._last_gecko_request = 0.0

        trades = await client.get_token_trades("0xFAIL")
        assert trades == []
        await client.close()

    @pytest.mark.asyncio
    async def test_handles_empty_response(self) -> None:
        client = BaseChainClient(bankr_api_key="test_key")
        client._request_with_retry = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_response({"data": []})
        )
        client._last_gecko_request = 0.0

        trades = await client.get_token_trades("0xPAIR")
        assert trades == []
        await client.close()


# ---------------------------------------------------------------------------
# Manager: token selection and on-demand fetching
# ---------------------------------------------------------------------------

class TestManagerTokenSelection:
    def _make_manager(self) -> BaseManager:
        """Build a manager with stubbed-out cache and client."""
        with patch("maxpane_dashboard.data.base_manager.BaseTokenCache") as MockCache:
            MockCache.return_value.load_from_file.return_value = None
            mgr = BaseManager(
                poll_interval=30,
                bankr_api_key="test_key",
            )
        return mgr

    def test_select_token(self) -> None:
        mgr = self._make_manager()
        assert mgr._selected_token is None

        mgr.select_token("0xAbCdEf")
        assert mgr._selected_token == "0xabcdef"

    def test_select_token_empty(self) -> None:
        mgr = self._make_manager()
        mgr.select_token("0xABC")
        mgr.select_token("")
        assert mgr._selected_token is None

    @pytest.mark.asyncio
    async def test_fetch_selected_token_none_selected(self) -> None:
        mgr = self._make_manager()
        result = await mgr.fetch_selected_token()
        assert result is None
        await mgr.close()

    @pytest.mark.asyncio
    async def test_fetch_selected_token_success(self) -> None:
        mgr = self._make_manager()
        mgr.select_token("0xAbC1230000000000000000000000000000000001")

        # Mock client methods
        mgr.client.get_token_detail = AsyncMock(  # type: ignore[method-assign]
            return_value=TokenDetail.from_dexscreener_pair(
                DEXSCREENER_TOKEN_RESPONSE["pairs"][0]
            )
        )
        mgr.client.get_token_trades = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"type": "buy", "price_usd": 2.50}]
        )

        result = await mgr.fetch_selected_token()

        assert result is not None
        assert result["token_detail"] is not None
        assert result["token_detail"].symbol == "DTK"
        assert len(result["recent_trades"]) == 1
        assert "momentum" in result["token_signal"]
        assert "overall" in result["token_signal"]
        await mgr.close()

    @pytest.mark.asyncio
    async def test_get_token_detail_trades_failure_graceful(self) -> None:
        """Trades failure does not prevent token detail from returning."""
        mgr = self._make_manager()

        detail = TokenDetail.from_dexscreener_pair(
            DEXSCREENER_TOKEN_RESPONSE["pairs"][0]
        )
        mgr.client.get_token_detail = AsyncMock(return_value=detail)  # type: ignore[method-assign]
        mgr.client.get_token_trades = AsyncMock(  # type: ignore[method-assign]
            side_effect=httpx.HTTPError("trades API down")
        )

        result = await mgr.get_token_detail(
            "0xAbC1230000000000000000000000000000000001"
        )

        assert result["token_detail"] is not None
        assert result["token_detail"].symbol == "DTK"
        assert result["recent_trades"] == []
        assert result["token_signal"]["overall"] in ("bullish", "neutral", "bearish")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_get_token_detail_not_found(self) -> None:
        """When DexScreener returns no data, result has None detail."""
        mgr = self._make_manager()
        mgr.client.get_token_detail = AsyncMock(return_value=None)  # type: ignore[method-assign]

        result = await mgr.get_token_detail("0xNONEXISTENT")

        assert result["token_detail"] is None
        assert result["recent_trades"] == []
        assert result["token_signal"] == {}
        await mgr.close()

    @pytest.mark.asyncio
    async def test_get_token_detail_no_pair_address(self) -> None:
        """When detail has no pair_address, trades are skipped."""
        mgr = self._make_manager()

        # Create a detail with no pair_address
        pair_data = dict(DEXSCREENER_TOKEN_RESPONSE["pairs"][0])
        pair_data["pairAddress"] = None
        detail = TokenDetail.from_dexscreener_pair(pair_data)

        mgr.client.get_token_detail = AsyncMock(return_value=detail)  # type: ignore[method-assign]
        mgr.client.get_token_trades = AsyncMock(return_value=[])  # type: ignore[method-assign]

        result = await mgr.get_token_detail(
            "0xAbC1230000000000000000000000000000000001"
        )

        # Trades endpoint should not be called
        mgr.client.get_token_trades.assert_not_called()
        assert result["recent_trades"] == []
        await mgr.close()
