"""Tests for GameDataClient with mocked HTTP responses."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from maxpane_dashboard.data.client import GameDataClient
from maxpane_dashboard.data.models import (
    ActivityEvent,
    BakeryDetail,
    BakeryMember,
    BakerySummary,
    Season,
    unwrap_trpc,
)
from maxpane_dashboard.data.price import PriceClient


# ---------------------------------------------------------------------------
# Sample API response data (mirrors .planning/api-responses.json)
# ---------------------------------------------------------------------------

AGENT_JSON: dict[str, Any] = {
    "name": "Bakery",
    "version": "1.0",
    "generatedAt": "2026-03-27T04:26:31.659Z",
    "network": {
        "name": "Abstract",
        "chainId": 2741,
        "rpcHttp": "https://api.mainnet.abs.xyz",
        "explorer": "https://abscan.org",
        "currency": "ETH",
        "walletModel": "Abstract Global Wallet",
    },
    "contracts": {
        "seasonManager": "0x327E83B8517f60973473B2f2cA0eC3a0FEBB5676",
        "prizePool": "0x7FDF300dbe9588faB6787C2875376C8a0521Eb72",
        "playerRegistry": "0x663D69eCFF14b4dbD245cdac03f2e1DEb68Ed250",
        "clanRegistry": "0xbffCc2C852f6b6E5CFeF8630a43B6CD06194E1AC",
        "boostManager": "0xa8a91aC36dD6a1055D36bA18aE91348f3AA3d7F9",
        "bakery": "0xaEB8Eef0deAbA98E3B65f6311DD7F997e72B837a",
    },
    "liveState": {
        "currentSeasonId": 3,
        "isSeasonActive": True,
        "buyInWei": "2000000000000000",
        "buyInEth": "0.002",
        "vrfFeeWei": "22006155000000",
        "vrfFeeEth": "0.000022006155",
        "minimumRequiredWeiExcludingGas": "2022006155000000",
        "minimumRequiredEthExcludingGas": "0.002022006155",
        "referralWeights": {
            "referredWeightBps": 10500,
            "notReferredWeightBps": 10000,
            "referralBonusBps": 500,
        },
        "gameplayCaps": {
            "cookieScale": 10000,
            "maxActiveBoosts": 5,
            "maxActiveDebuffs": 5,
            "leavePenaltyBps": 10000,
        },
        "activeBoostCatalog": [],
    },
    "liveDataStatus": "fresh",
}

SEASON_RESPONSE: dict[str, Any] = {
    "result": {
        "data": {
            "json": [
                {
                    "id": 3,
                    "startTime": "1774535903",
                    "endTime": "1775746803",
                    "claimDeadline": None,
                    "protocolFeeBps": 0,
                    "seedAmount": "1202790473899446784",
                    "resultsRoot": None,
                    "finalized": False,
                    "ended": False,
                    "isActive": True,
                    "prizePool": "2856090473899446784",
                }
            ]
        }
    }
}

TOP_BAKERIES_RESPONSE: dict[str, Any] = {
    "result": {
        "data": {
            "json": {
                "items": [
                    {
                        "id": 58,
                        "name": "Cockring Cakehouse",
                        "creator": "0x67016b9194c606a23d14b893e63fb1bb24632bfc",
                        "leader": "0x67016b9194c606a23d14b893e63fb1bb24632bfc",
                        "topCook": "0xb5748a472adfa371244cdc5a0a13189410cf8097",
                        "memberCount": 263,
                        "activeCookCount": 18,
                        "seasonId": 3,
                        "createdAt": "1774542117",
                        "txCount": "1392714836",
                        "rawTxCount": "1340959823",
                        "buffs": 0,
                        "debuffs": 5,
                        "activeBuffs": [],
                        "activeDebuffs": [],
                    }
                ],
                "nextCursor": None,
            }
        }
    }
}

BAKERY_DETAIL_RESPONSE: dict[str, Any] = {
    "result": {
        "data": {
            "json": {
                "id": 58,
                "name": "Cockring Cakehouse",
                "creator": "0x67016b9194c606a23d14b893e63fb1bb24632bfc",
                "leader": "0x67016b9194c606a23d14b893e63fb1bb24632bfc",
                "topCook": None,
                "memberCount": 264,
                "activeCookCount": None,
                "seasonId": 3,
                "createdAt": "1774542117",
                "txCount": "1392714836",
                "rawTxCount": "1340959823",
                "buffs": 0,
                "debuffs": 5,
            }
        }
    }
}

MEMBERS_RESPONSE: dict[str, Any] = {
    "result": {
        "data": {
            "json": {
                "items": [
                    {
                        "seasonId": 3,
                        "address": "0xb5748a472adfa371244cdc5a0a13189410cf8097",
                        "bakeryId": 58,
                        "txCount": "69705916",
                        "effectiveTxCount": "73191211",
                        "referrerBonus": "0",
                        "referralCount": 0,
                        "referrer": None,
                        "registeredAt": "1774544122",
                    }
                ],
                "nextCursor": None,
            }
        }
    }
}

ACTIVITY_RESPONSE: dict[str, Any] = {
    "result": {
        "data": {
            "json": [
                {
                    "type": "simple",
                    "title": "joined the bakery",
                    "description": "",
                    "launcher": "0xace4fd0f8ff152d0ebbf01d6b6263f7e9745deb6",
                    "timestamp": "1774585632",
                    "boostTypeName": None,
                    "boostMultiplierBps": None,
                    "boostDuration": None,
                    "isShield": None,
                    "isOutgoing": True,
                    "success": True,
                    "linkedBakeryId": None,
                    "linkedBakeryName": None,
                }
            ]
        }
    }
}


# ---------------------------------------------------------------------------
# Mock transport
# ---------------------------------------------------------------------------

def _make_transport(routes: dict[str, Any]) -> httpx.MockTransport:
    """Build a mock transport that maps URL path prefixes to JSON responses.

    *routes* maps a URL substring to the JSON body that should be returned.
    Unmatched URLs return 404.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, body in routes.items():
            if pattern in url:
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def _make_client(routes: dict[str, Any]) -> GameDataClient:
    """Create a ``GameDataClient`` backed by a mock transport."""
    transport = _make_transport(routes)
    http_client = httpx.AsyncClient(transport=transport)
    price_transport = _make_transport(
        {"coingecko": {"ethereum": {"usd": 2500.0}}}
    )
    price_http = httpx.AsyncClient(transport=price_transport)
    price_client = PriceClient(http_client=price_http)
    return GameDataClient(
        base_url="https://www.rugpullbakery.com",
        price_client=price_client,
        http_client=http_client,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetAgentConfig:
    @pytest.mark.asyncio
    async def test_parses_agent_json(self) -> None:
        client = _make_client({"agent.json": AGENT_JSON})
        config = await client.get_agent_config()
        assert config.name == "Bakery"
        assert config.version == "1.0"
        assert config.network.chain_id == 2741
        assert config.live_state.current_season_id == 3


class TestGetActiveSeason:
    @pytest.mark.asyncio
    async def test_returns_active_season(self) -> None:
        client = _make_client({"getActiveSeason": SEASON_RESPONSE})
        season = await client.get_active_season()
        assert season.id == 3
        assert season.is_active is True
        assert season.prize_pool == "2856090473899446784"


class TestGetTopBakeries:
    @pytest.mark.asyncio
    async def test_returns_bakery_list(self) -> None:
        client = _make_client({"getTopBakeries": TOP_BAKERIES_RESPONSE})
        bakeries = await client.get_top_bakeries()
        assert len(bakeries) == 1
        assert bakeries[0].name == "Cockring Cakehouse"
        assert bakeries[0].tx_count == "1392714836"

    @pytest.mark.asyncio
    async def test_pagination_stops_at_null_cursor(self) -> None:
        client = _make_client({"getTopBakeries": TOP_BAKERIES_RESPONSE})
        bakeries = await client.get_top_bakeries(max_pages=10)
        # With null nextCursor, should stop after first page
        assert len(bakeries) == 1


class TestGetBakeryById:
    @pytest.mark.asyncio
    async def test_returns_detail(self) -> None:
        client = _make_client({"getBakeryById": BAKERY_DETAIL_RESPONSE})
        detail = await client.get_bakery_by_id(58)
        assert detail.id == 58
        assert detail.member_count == 264
        assert detail.active_cook_count is None


class TestGetBakeryMembers:
    @pytest.mark.asyncio
    async def test_returns_member_list(self) -> None:
        client = _make_client({"getBakeryMembers": MEMBERS_RESPONSE})
        members = await client.get_bakery_members(58, 3)
        assert len(members) == 1
        assert members[0].address == "0xb5748a472adfa371244cdc5a0a13189410cf8097"
        assert members[0].effective_tx_count == "73191211"


class TestGetActivityFeed:
    @pytest.mark.asyncio
    async def test_returns_events(self) -> None:
        client = _make_client({"getActivityFeed": ACTIVITY_RESPONSE})
        events = await client.get_activity_feed(58, 3)
        assert len(events) == 1
        assert events[0].type == "simple"
        assert events[0].title == "joined the bakery"


class TestFetchAll:
    @pytest.mark.asyncio
    async def test_returns_unified_snapshot(self) -> None:
        routes = {
            "agent.json": AGENT_JSON,
            "getActiveSeason": SEASON_RESPONSE,
            "getTopBakeries": TOP_BAKERIES_RESPONSE,
            "getActivityFeed": ACTIVITY_RESPONSE,
        }
        client = _make_client(routes)
        snapshot = await client.fetch_all()

        assert snapshot.season.id == 3
        assert len(snapshot.bakeries) == 1
        assert snapshot.bakeries[0].name == "Cockring Cakehouse"
        assert snapshot.eth_price_usd == 2500.0
        assert snapshot.fetched_at > 0


class TestRetryBehavior:
    @pytest.mark.asyncio
    async def test_retries_on_server_error(self) -> None:
        """Verify the client retries and eventually succeeds."""
        call_count = 0

        def flaky_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(500, json={"error": "server error"})
            return httpx.Response(200, json=SEASON_RESPONSE)

        transport = httpx.MockTransport(flaky_handler)
        http_client = httpx.AsyncClient(transport=transport)
        client = GameDataClient(
            base_url="https://www.rugpullbakery.com",
            http_client=http_client,
        )

        season = await client.get_active_season()
        assert season.id == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        """Verify the client raises after exhausting retries."""

        def always_fail(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "down"})

        transport = httpx.MockTransport(always_fail)
        http_client = httpx.AsyncClient(transport=transport)
        client = GameDataClient(
            base_url="https://www.rugpullbakery.com",
            http_client=http_client,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_active_season()


class TestPriceClient:
    @pytest.mark.asyncio
    async def test_fetches_price(self) -> None:
        transport = _make_transport(
            {"simple/price": {"ethereum": {"usd": 3200.50}}}
        )
        http = httpx.AsyncClient(transport=transport)
        pc = PriceClient(http_client=http)
        price = await pc.get_eth_usd()
        assert price == 3200.50

    @pytest.mark.asyncio
    async def test_returns_cached_on_second_call(self) -> None:
        call_count = 0

        def counting_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"ethereum": {"usd": 2000.0}})

        transport = httpx.MockTransport(counting_handler)
        http = httpx.AsyncClient(transport=transport)
        pc = PriceClient(cache_seconds=300, http_client=http)

        p1 = await pc.get_eth_usd()
        p2 = await pc.get_eth_usd()
        assert p1 == p2 == 2000.0
        assert call_count == 1  # second call used cache

    @pytest.mark.asyncio
    async def test_returns_zero_on_failure(self) -> None:
        def fail_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "fail"})

        transport = httpx.MockTransport(fail_handler)
        http = httpx.AsyncClient(transport=transport)
        pc = PriceClient(http_client=http)

        price = await pc.get_eth_usd()
        assert price == 0.0
