"""Tests for CatTownClient -- mocked httpx responses for all RPC calls.

Covers KIBBLE price/stats, competition state, recent catches, staking,
snapshot assembly, retry behaviour, and client lifecycle.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maxpane_dashboard.data.cattown_client import CatTownClient, _decode_uint256, _pad_address
from maxpane_dashboard.data.cattown_models import (
    CatTownSnapshot,
    CompetitionEntry,
    CompetitionState,
    FishCatch,
    KibbleEconomy,
    StakingState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rpc_response(result: str, request_id: int = 1, status: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with a JSON-RPC result."""
    import json

    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})
    return httpx.Response(
        status_code=status,
        content=body.encode(),
        headers={"Content-Type": "application/json"},
        request=httpx.Request("POST", "https://mainnet.base.org"),
    )


def _rpc_error_response(message: str = "execution reverted") -> httpx.Response:
    """Build a mock httpx.Response with a JSON-RPC error."""
    import json

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": message}})
    return httpx.Response(
        status_code=200,
        content=body.encode(),
        headers={"Content-Type": "application/json"},
        request=httpx.Request("POST", "https://mainnet.base.org"),
    )


def _encode_uint256(value: int) -> str:
    """Encode an integer as a 64-char hex string (32 bytes, no 0x prefix)."""
    return hex(value)[2:].zfill(64)


def _make_reserves_result(weth_reserve: int, kibble_reserve: int, timestamp: int = 1000) -> str:
    """Build hex result for getReserves(): reserve0, reserve1, blockTimestampLast."""
    return "0x" + _encode_uint256(weth_reserve) + _encode_uint256(kibble_reserve) + _encode_uint256(timestamp)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    """Create a CatTownClient with a mocked httpx.AsyncClient."""
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    client = CatTownClient(http_client=mock_http)
    return client, mock_http


# ---------------------------------------------------------------------------
# Tests: decode helpers
# ---------------------------------------------------------------------------

class TestDecodeHelpers:
    def test_decode_uint256_basic(self):
        hex_val = "0x" + _encode_uint256(42)
        assert _decode_uint256(hex_val) == 42

    def test_decode_uint256_large(self):
        val = 10**18
        hex_val = "0x" + _encode_uint256(val)
        assert _decode_uint256(hex_val) == val

    def test_decode_uint256_empty(self):
        assert _decode_uint256("0x") == 0
        assert _decode_uint256("") == 0

    def test_pad_address(self):
        addr = "0x64cc19A52f4D631eF5BE07947CABA14aE00c52Eb"
        padded = _pad_address(addr)
        assert len(padded) == 64
        assert padded.startswith("000000000000000000000000")
        assert padded.endswith("64cc19a52f4d631ef5be07947caba14ae00c52eb")


# ---------------------------------------------------------------------------
# Tests: KIBBLE price from DEX
# ---------------------------------------------------------------------------

class TestGetKibblePrice:
    @pytest.mark.asyncio
    async def test_get_kibble_price_from_dex(self, mock_client):
        client, mock_http = mock_client
        # 1 WETH = 1e18 wei, 100_000 KIBBLE = 100_000e18 wei
        weth = 1 * 10**18
        kibble = 100_000 * 10**18
        mock_http.post.return_value = _rpc_response(
            _make_reserves_result(weth, kibble)
        )

        price = await client.get_kibble_price()
        # price = weth / kibble = 1e18 / 100_000e18 = 0.00001
        assert price == pytest.approx(1e-5)

    @pytest.mark.asyncio
    async def test_get_kibble_price_zero_reserve(self, mock_client):
        """Returns 0.0 when reserve1 is zero (empty pool)."""
        client, mock_http = mock_client
        # Both reserves zero
        mock_http.post.return_value = _rpc_response(
            _make_reserves_result(0, 0)
        )

        price = await client.get_kibble_price()
        # Falls through DEX (reserve1==0), then oracle also fails -> 0.0
        # Need to set up oracle fallback to also return something parseable
        # Actually, since reserve1 == 0, DEX branch skips. Oracle call also uses mock.
        # The mock will return same response for oracle calls, which won't parse.
        assert price == 0.0


# ---------------------------------------------------------------------------
# Tests: KIBBLE stats
# ---------------------------------------------------------------------------

class TestGetKibbleStats:
    @pytest.mark.asyncio
    async def test_get_kibble_stats(self, mock_client):
        client, mock_http = mock_client

        total_supply = 1_000_000_000 * 10**18
        burned = 100_000_000 * 10**18
        staked = 50_000_000 * 10**18
        weth = 10 * 10**18
        kibble_reserve = 1_000_000 * 10**18

        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            data = json or {}
            params = data.get("params", [{}])
            call_data = params[0].get("data", "") if isinstance(params[0], dict) else ""

            if call_data.startswith("0x18160ddd"):  # totalSupply
                return _rpc_response("0x" + _encode_uint256(total_supply))
            elif call_data.startswith("0x70a08231"):  # balanceOf
                return _rpc_response("0x" + _encode_uint256(burned))
            elif call_data.startswith("0x817b1cd2"):  # getTotalStaked
                return _rpc_response("0x" + _encode_uint256(staked))
            elif call_data.startswith("0x0902f1ac"):  # getReserves (for price)
                return _rpc_response(_make_reserves_result(weth, kibble_reserve))
            else:
                return _rpc_response("0x" + _encode_uint256(0))

        mock_http.post = AsyncMock(side_effect=mock_post)

        stats = await client.get_kibble_stats()

        assert isinstance(stats, KibbleEconomy)
        assert stats.total_supply == pytest.approx(1_000_000_000.0)
        assert stats.burned == pytest.approx(100_000_000.0)
        assert stats.circulating == pytest.approx(900_000_000.0)
        assert stats.staked_total == pytest.approx(50_000_000.0)


# ---------------------------------------------------------------------------
# Tests: Recent catches (event logs)
# ---------------------------------------------------------------------------

class TestGetRecentCatches:
    @pytest.mark.asyncio
    async def test_get_recent_catches(self, mock_client):
        client, mock_http = mock_client

        from maxpane_dashboard.data.cattown_client import _FISH_CAUGHT_TOPIC_FISHING

        # Build a synthetic FishCaught log entry
        # Non-indexed data: mintedId(uint256), fishName(string offset), weight(uint256), sellValue(uint256)
        minted_id = _encode_uint256(42)
        name_offset = _encode_uint256(128)  # 4 * 32 bytes offset to string data
        weight = _encode_uint256(5500)  # 5.5 kg in grams
        sell_value = _encode_uint256(1000)

        # String encoding: length + padded utf-8 bytes
        fish_name = "Tuna"
        name_bytes = fish_name.encode("utf-8")
        name_len = _encode_uint256(len(name_bytes))
        name_hex = name_bytes.hex().ljust(64, "0")

        data_hex = "0x" + minted_id + name_offset + weight + sell_value + name_len + name_hex

        fisher_topic = "0x" + _pad_address("0xAbCdEf1234567890AbCdEf1234567890AbCdEf12")

        sample_log = {
            "topics": [_FISH_CAUGHT_TOPIC_FISHING, fisher_topic],
            "data": data_hex,
            "transactionHash": "0xdeadbeef",
            "blockNumber": "0x100",
        }

        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            data = json or {}
            method = data.get("method", "")
            if method == "eth_blockNumber":
                return _rpc_response(hex(1000))
            elif method == "eth_getLogs":
                import json as json_mod
                params = data.get("params", [{}])
                topics = params[0].get("topics", []) if params else []
                # Only return the fish log for the FishCaught topic
                if topics and topics[0] == _FISH_CAUGHT_TOPIC_FISHING:
                    result = [sample_log]
                else:
                    result = []
                body = json_mod.dumps({"jsonrpc": "2.0", "id": 1, "result": result})
                return httpx.Response(
                    status_code=200,
                    content=body.encode(),
                    headers={"Content-Type": "application/json"},
                    request=httpx.Request("POST", "https://mainnet.base.org"),
                )
            return _rpc_response("0x" + _encode_uint256(0))

        mock_http.post = AsyncMock(side_effect=mock_post)

        catches = await client.get_recent_catches(block_range=200)

        assert len(catches) == 1
        catch = catches[0]
        assert isinstance(catch, FishCatch)
        assert catch.weight_kg == pytest.approx(5.5)
        assert catch.species == "Tuna"
        assert catch.tx_hash == "0xdeadbeef"
        assert "abcdef1234567890" in catch.fisher_address.lower()


# ---------------------------------------------------------------------------
# Tests: Staking state
# ---------------------------------------------------------------------------

class TestGetStakingState:
    @pytest.mark.asyncio
    async def test_get_staking_state(self, mock_client):
        client, mock_http = mock_client

        total_staked = 200_000_000 * 10**18
        acc_reward = 500 * 10**18

        async def mock_post(url, json=None, **kwargs):
            data = json or {}
            params = data.get("params", [{}])
            call_data = params[0].get("data", "") if isinstance(params[0], dict) else ""

            if call_data.startswith("0x817b1cd2"):  # getTotalStaked
                return _rpc_response("0x" + _encode_uint256(total_staked))
            elif call_data.startswith("0x939d6237"):  # accRewardPerShare
                return _rpc_response("0x" + _encode_uint256(acc_reward))
            return _rpc_response("0x" + _encode_uint256(0))

        mock_http.post = AsyncMock(side_effect=mock_post)

        state = await client.get_staking_state()

        assert isinstance(state, StakingState)
        assert state.total_staked == pytest.approx(200_000_000.0)
        assert state.user_staked == 0.0  # read-only, no user context


# ---------------------------------------------------------------------------
# Tests: Snapshot assembly
# ---------------------------------------------------------------------------

class TestFetchSnapshot:
    @pytest.mark.asyncio
    async def test_fetch_snapshot_assembles_all(self, mock_client):
        client, mock_http = mock_client

        total_supply = 1_000_000_000 * 10**18
        burned = 100_000_000 * 10**18
        staked = 50_000_000 * 10**18
        weth = 10 * 10**18
        kibble_reserve = 1_000_000 * 10**18

        async def mock_post(url, json=None, **kwargs):
            data = json or {}
            method = data.get("method", "")
            params = data.get("params", [{}])
            call_data = params[0].get("data", "") if isinstance(params[0], dict) else ""

            if method == "eth_blockNumber":
                return _rpc_response(hex(5000))
            elif method == "eth_getLogs":
                import json as json_mod
                body = json_mod.dumps({"jsonrpc": "2.0", "id": 1, "result": []})
                return httpx.Response(
                    status_code=200,
                    content=body.encode(),
                    headers={"Content-Type": "application/json"},
                    request=httpx.Request("POST", "https://mainnet.base.org"),
                )
            elif call_data.startswith("0x18160ddd"):  # totalSupply
                return _rpc_response("0x" + _encode_uint256(total_supply))
            elif call_data.startswith("0x70a08231"):  # balanceOf
                return _rpc_response("0x" + _encode_uint256(burned))
            elif call_data.startswith("0x817b1cd2"):  # getTotalStaked
                return _rpc_response("0x" + _encode_uint256(staked))
            elif call_data.startswith("0x0902f1ac"):  # getReserves
                return _rpc_response(_make_reserves_result(weth, kibble_reserve))
            elif call_data.startswith("0x939d6237"):  # accRewardPerShare
                return _rpc_response("0x" + _encode_uint256(0))
            elif call_data.startswith("0x75595489"):  # getCurrentCompetition
                # Return minimal valid competition data
                return _rpc_response("0x" + "00" * 384)
            elif call_data.startswith("0x7c4f7a38"):  # getLeaderboard
                return _rpc_response("0x" + "00" * 64)
            else:
                return _rpc_response("0x" + _encode_uint256(0))

        mock_http.post = AsyncMock(side_effect=mock_post)

        snapshot = await client.fetch_snapshot()

        assert isinstance(snapshot, CatTownSnapshot)
        assert snapshot.fetched_at > 0
        assert isinstance(snapshot.kibble, KibbleEconomy)
        assert isinstance(snapshot.competition, CompetitionState)
        assert isinstance(snapshot.staking, StakingState)
        assert isinstance(snapshot.recent_catches, list)
        assert snapshot.kibble.total_supply == pytest.approx(1_000_000_000.0)


# ---------------------------------------------------------------------------
# Tests: Retry behavior
# ---------------------------------------------------------------------------

class TestRetryBehavior:
    @pytest.mark.asyncio
    async def test_rpc_failure_retries(self, mock_client):
        """Verify that transient 503 errors trigger retries."""
        client, mock_http = mock_client

        error_response = httpx.Response(
            status_code=503,
            content=b"Service Unavailable",
            request=httpx.Request("POST", "https://mainnet.base.org"),
        )
        success_response = _rpc_response("0x" + _encode_uint256(100))

        mock_http.post = AsyncMock(
            side_effect=[error_response, error_response, success_response]
        )

        with patch("maxpane_dashboard.data.cattown_client.asyncio.sleep", new_callable=AsyncMock):
            result = await client._rpc("eth_call", [{"to": "0x0", "data": "0x0"}, "latest"])

        assert result == "0x" + _encode_uint256(100)
        assert mock_http.post.call_count == 3

    @pytest.mark.asyncio
    async def test_rpc_error_raises(self, mock_client):
        """JSON-RPC error field raises RuntimeError."""
        client, mock_http = mock_client
        mock_http.post.return_value = _rpc_error_response("execution reverted")

        with pytest.raises(RuntimeError, match="RPC error"):
            await client._rpc("eth_call", [{"to": "0x0", "data": "0x0"}, "latest"])


# ---------------------------------------------------------------------------
# Tests: Client lifecycle
# ---------------------------------------------------------------------------

class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_close_closes_owned_client(self):
        """Client created without external httpx closes its own client."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        client = CatTownClient.__new__(CatTownClient)
        client._rpc_url = CatTownClient.RPC_URL
        client._client = mock_http
        client._owns_client = True
        client._request_id = 0

        await client.close()
        mock_http.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_does_not_close_external_client(self):
        """Client created with external httpx does not close it."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        client = CatTownClient(http_client=mock_http)

        await client.close()
        mock_http.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Async context manager calls close."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        client = CatTownClient.__new__(CatTownClient)
        client._rpc_url = CatTownClient.RPC_URL
        client._client = mock_http
        client._owns_client = True
        client._request_id = 0

        async with client:
            pass

        mock_http.aclose.assert_called_once()
