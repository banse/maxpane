"""Tests for CatTownClient -- mocked httpx responses for all RPC calls.

Covers KIBBLE price/stats, competition state, recent catches, staking,
snapshot assembly, retry behaviour, and client lifecycle.
"""

from __future__ import annotations

import asyncio
import time
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maxpane_dashboard.data.cattown_client import (
    _MAX_BLOCK_TS_LOOKUPS,
    _SEL_ACC_REWARD_PER_SHARE,
    _SEL_BALANCE_OF,
    _SEL_GET_CURRENT_COMPETITION,
    _SEL_GET_LEADERBOARD,
    _SEL_GET_RESERVES,
    _SEL_TOTAL_STAKED,
    _SEL_TOTAL_SUPPLY,
    CatTownClient,
    _decode_uint256,
    _pad_address,
)
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

def _json_response(payload: dict, status: int = 200) -> httpx.Response:
    """Build a real httpx.Response carrying a JSON body.

    Used for the cat.town REST endpoints. A bare ``AsyncMock`` response is
    *not* good enough: ``resp.json()`` on one returns an unawaited coroutine,
    so every ``data.get(...)`` raises AttributeError and the code under test
    silently falls into its own except branch. That is exactly the trap
    test_fetch_snapshot_assembles_all fell into (MEDI-39).
    """
    import json

    return httpx.Response(
        status_code=status,
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        request=httpx.Request("GET", "https://api.cat.town/"),
    )


@pytest.fixture
def mock_client():
    """Create a CatTownClient with a mocked httpx.AsyncClient.

    ``inter_call_delay=0.0`` disables the production RPC pacing: the tests
    assert call *counts* and *ordering*, never wall-clock spacing (which has
    its own dedicated test), and 0.12s per call would otherwise add seconds
    to every snapshot test.
    """
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    client = CatTownClient(http_client=mock_http, inter_call_delay=0.0)
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

def _posted_call_targets(mock_http) -> list[tuple[str, str]]:
    """Extract ``(to, data)`` from every eth_call the mock received."""
    targets = []
    for call in mock_http.post.call_args_list:
        payload = call.kwargs.get("json") or {}
        if payload.get("method") != "eth_call":
            continue
        params = payload.get("params") or [{}]
        first = params[0] if isinstance(params[0], dict) else {}
        targets.append((str(first.get("to", "")).lower(), str(first.get("data", ""))))
    return targets


class TestGetKibblePrice:
    @pytest.mark.asyncio
    async def test_get_kibble_price_eth_from_dex(self, mock_client):
        client, mock_http = mock_client
        # 1 WETH = 1e18 wei, 100_000 KIBBLE = 100_000e18 wei
        weth = 1 * 10**18
        kibble = 100_000 * 10**18
        mock_http.post.return_value = _rpc_response(
            _make_reserves_result(weth, kibble)
        )

        price = await client.get_kibble_price_eth()
        # price = weth / kibble = 1e18 / 100_000e18 = 0.00001 WETH per KIBBLE
        assert price == pytest.approx(1e-5)

    @pytest.mark.asyncio
    async def test_price_is_eth_denominated_not_usd(self, mock_client):
        """The returned number is WETH-per-KIBBLE, at live-pool magnitude.

        Pins the unit that the field name now advertises. Reserves are the
        real ones read from the SushiSwap pair on Base (token0=WETH,
        token1=KIBBLE): ~0.2 WETH against ~551k KIBBLE, which is ~3.7e-7
        ETH each -- a number that would be absurd as a USD price and is
        exactly why ``price_usd`` was the wrong name for it.
        """
        client, mock_http = mock_client
        mock_http.post.return_value = _rpc_response(
            _make_reserves_result(204_472_038_970_894_500, 550_925_976_699_960_300_000_000)
        )

        price = await client.get_kibble_price_eth()

        assert price == pytest.approx(3.71e-7, rel=0.01)

    @pytest.mark.asyncio
    async def test_get_kibble_price_zero_reserve(self, mock_client):
        """Returns 0.0 when reserve1 is zero (empty pool)."""
        client, mock_http = mock_client
        mock_http.post.return_value = _rpc_response(
            _make_reserves_result(0, 0)
        )

        price = await client.get_kibble_price_eth()

        assert price == 0.0

    @pytest.mark.asyncio
    async def test_dex_failure_returns_zero_and_warns(self, mock_client, caplog):
        """A failed pool read yields 0.0 and says so at WARNING.

        This is the path the deleted oracle fallback pretended to cover. It
        is exercised here so the degraded behaviour is pinned: no price, a
        loud log line, and no second guess at a different unit.
        """
        client, mock_http = mock_client
        mock_http.post.return_value = _rpc_error_response("execution reverted")

        with caplog.at_level("WARNING", logger="maxpane_dashboard.data.cattown_client"):
            price = await client.get_kibble_price_eth()

        assert price == 0.0
        assert any(
            "KIBBLE price unavailable" in rec.message for rec in caplog.records
        ), caplog.text

    @pytest.mark.asyncio
    async def test_short_reserves_payload_returns_zero_and_warns(self, mock_client, caplog):
        """A truncated getReserves result is 'unknown', not a decoded price."""
        client, mock_http = mock_client
        mock_http.post.return_value = _rpc_response("0x" + _encode_uint256(1))

        with caplog.at_level("WARNING", logger="maxpane_dashboard.data.cattown_client"):
            price = await client.get_kibble_price_eth()

        assert price == 0.0
        assert any("KIBBLE price unavailable" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_no_oracle_fallback_is_attempted(self, mock_client):
        """KIBBLE_ORACLE is never called, on the happy path or the sad one.

        The oracle reverts on latestRoundData()/decimals() on live Base, so
        the old fallback could only ever fail -- and had it worked it would
        have returned a USD price where the DEX path returns ETH. Deleted;
        this test keeps it deleted.
        """
        client, mock_http = mock_client
        mock_http.post.return_value = _rpc_error_response("execution reverted")

        await client.get_kibble_price_eth()

        targets = _posted_call_targets(mock_http)
        assert targets, "expected at least one eth_call"
        assert all(to == client.DEX_POOL.lower() for to, _ in targets), targets
        assert client.KIBBLE_ORACLE.lower() not in {to for to, _ in targets}
        # The Chainlink selectors are gone from the module entirely.
        assert not any(data.startswith(("0xfeaf968c", "0x313ce567")) for _, data in targets)


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
        # 10 WETH / 1_000_000 KIBBLE = 1e-5 ETH each, carried on price_eth.
        assert stats.price_eth == pytest.approx(1e-5)


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


def _fish_log(block_number: int, tx_suffix: int) -> dict:
    """A syntactically valid FishCaught log mined in *block_number*."""
    from maxpane_dashboard.data.cattown_client import _FISH_CAUGHT_TOPIC_FISHING

    name_bytes = b"Tuna"
    data_hex = "0x" + (
        _encode_uint256(tx_suffix)  # mintedId
        + _encode_uint256(128)  # fishName offset
        + _encode_uint256(5500)  # weight (grams)
        + _encode_uint256(1000)  # sellValue
        + _encode_uint256(len(name_bytes))
        + name_bytes.hex().ljust(64, "0")
    )
    return {
        "topics": [
            _FISH_CAUGHT_TOPIC_FISHING,
            "0x" + _pad_address("0xAbCdEf1234567890AbCdEf1234567890AbCdEf12"),
        ],
        "data": data_hex,
        "transactionHash": f"0x{tx_suffix:064x}",
        "blockNumber": hex(block_number),
    }


class TestBlockTimestampBudget:
    """MEDI-16: the block-timestamp resolution must be bounded and memoized.

    ``get_recent_catches`` used to re-fetch every unique block timestamp
    serially on every 30s refresh. With a few dozen blocks in the window and a
    rate-limited public RPC, one refresh outlived the poll interval; the
    screen runs the refresh with ``exclusive=True``, so the next tick
    cancelled the in-flight one and the dashboard never updated again. The
    user sees a hang, not an error -- which is why these tests assert the
    *bound* on RPC work, not merely that the call returns.
    """

    HEAD = 5_000
    BLOCKS = list(range(HEAD - 60, HEAD, 2))  # 30 unique blocks

    def _post(self, *, block_ts_ok: bool = True, counter: dict | None = None):
        counter = {} if counter is None else counter
        counter.setdefault("getBlockByNumber", 0)
        counter.setdefault("blocks_seen", [])
        logs = [_fish_log(bn, i) for i, bn in enumerate(self.BLOCKS)]
        head = self.HEAD

        async def mock_post(url, json=None, **kwargs):
            from maxpane_dashboard.data.cattown_client import (
                _FISH_CAUGHT_TOPIC_FISHING,
            )

            data = json or {}
            method = data.get("method", "")
            if method == "eth_blockNumber":
                return _rpc_response(hex(head))
            if method == "eth_getLogs":
                topics = (data.get("params") or [{}])[0].get("topics", [])
                if topics and topics[0] == _FISH_CAUGHT_TOPIC_FISHING:
                    return _rpc_response(logs)
                return _rpc_response([])
            if method == "eth_getBlockByNumber":
                counter["getBlockByNumber"] += 1
                bn = int((data.get("params") or ["0x0"])[0], 16)
                counter["blocks_seen"].append(bn)
                if not block_ts_ok:
                    return _rpc_error_response("rate limit exceeded")
                return _rpc_response({"timestamp": hex(1_700_000_000 + bn)})
            return _rpc_response("0x" + _encode_uint256(0))

        return mock_post, counter

    @pytest.mark.asyncio
    async def test_timestamp_lookups_are_capped_per_refresh(self, mock_client):
        client, mock_http = mock_client
        post, counter = self._post()
        mock_http.post = AsyncMock(side_effect=post)

        catches = await client.get_recent_catches(block_range=200)

        assert len(catches) == len(self.BLOCKS)
        # 30 unique blocks, but never more than the per-refresh budget.
        assert counter["getBlockByNumber"] == _MAX_BLOCK_TS_LOOKUPS
        assert _MAX_BLOCK_TS_LOOKUPS < len(self.BLOCKS)
        # Newest blocks are prioritised -- those are what the feed shows.
        assert counter["blocks_seen"] == sorted(self.BLOCKS, reverse=True)[
            :_MAX_BLOCK_TS_LOOKUPS
        ]

    @pytest.mark.asyncio
    async def test_second_refresh_reuses_the_memo(self, mock_client):
        """Blocks are immutable, so a resolved timestamp is never re-fetched."""
        client, mock_http = mock_client
        post, counter = self._post()
        mock_http.post = AsyncMock(side_effect=post)

        await client.get_recent_catches(block_range=200)
        first_round = list(counter["blocks_seen"])
        assert first_round

        await client.get_recent_catches(block_range=200)
        second_round = counter["blocks_seen"][len(first_round) :]

        # Nothing from the first round is looked up again; the budget is spent
        # entirely on blocks that were still unresolved.
        assert not (set(second_round) & set(first_round))
        assert set(second_round) <= set(self.BLOCKS)

    @pytest.mark.asyncio
    async def test_repeated_refreshes_converge_to_zero_lookups(self, mock_client):
        """Steady state costs no timestamp RPCs at all."""
        client, mock_http = mock_client
        post, counter = self._post()
        mock_http.post = AsyncMock(side_effect=post)

        for _ in range(4):  # 4 * 12 >= 30 unique blocks
            await client.get_recent_catches(block_range=200)
        settled = counter["getBlockByNumber"]

        await client.get_recent_catches(block_range=200)
        assert counter["getBlockByNumber"] == settled

    @pytest.mark.asyncio
    async def test_failed_lookup_abandons_the_rest_of_the_budget(self, mock_client):
        """One failure means the endpoint is refusing us -- stop, don't grind.

        Without this, a rate-limited RPC costs the full budget x the full
        retry ladder, which is the freeze itself.
        """
        client, mock_http = mock_client
        post, counter = self._post(block_ts_ok=False)
        mock_http.post = AsyncMock(side_effect=post)

        with patch(
            "maxpane_dashboard.data.cattown_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            catches = await client.get_recent_catches(block_range=200)

        assert len(catches) == len(self.BLOCKS)
        # Exactly one block was attempted before bailing out. It is retried
        # across the endpoint pool, so count distinct blocks, not calls.
        assert len(set(counter["blocks_seen"])) == 1

    @pytest.mark.asyncio
    async def test_unresolved_timestamps_are_estimated_not_block_numbers(
        self, mock_client
    ):
        """The old fallback rendered as a 1971 date in the activity feed."""
        client, mock_http = mock_client
        post, _counter = self._post(block_ts_ok=False)
        mock_http.post = AsyncMock(side_effect=post)

        now = time.time()
        with patch(
            "maxpane_dashboard.data.cattown_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            catches = await client.get_recent_catches(block_range=200)

        for catch in catches:
            # Never the block number: ~5000 is 1970-01-01, and a real head
            # block number (~48 million) renders as 1971.
            assert catch.timestamp != catch.block_number
            # A plausible recent wall-clock time instead: the window spans
            # 60 blocks * 2s, so everything lands within a couple of minutes.
            assert now - 300 <= catch.timestamp <= now + 5


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

#: A canned cat.town /fishing/competition/leaderboard body, shaped like the
#: real one: stringified wei prize pool, stringified gram sizes, optional
#: basename, and a zero-size row the parser is supposed to drop.
_API_LEADERBOARD_PAYLOAD = {
    "competition": {
        "startTime": 1_767_052_800,
        "endTime": 1_767_225_599,
        "prizePool": str(4_000 * 10**18),
        "prizesDistributed": False,
        "isActive": True,
    },
    "leaderboard": [
        {
            "rank": 1,
            "player": "0x" + "11" * 20,
            "size": "12500",
            "fishName": "Coelacanth",
            "isShiny": True,
            "basename": "meowmaster.base.eth",
        },
        {
            "rank": 2,
            "player": "0x" + "22" * 20,
            "size": "9000",
            "fishName": "Tuna",
            "isShiny": False,
            "basename": None,
        },
        {
            "rank": 3,
            "player": "0x" + "33" * 20,
            "size": "0",
            "fishName": "Boot",
            "isShiny": False,
            "basename": None,
        },
    ],
}


def _rpc_only_post(
    *,
    total_supply: int,
    burned: int,
    staked: int,
    weth: int,
    kibble_reserve: int,
    competition_raw: str = "0x" + "00" * 384,
    leaderboard_raw: str = "0x" + "00" * 64,
):
    """Build a mock ``post`` covering every JSON-RPC read fetch_snapshot makes.

    Selectors are imported from the module under test rather than copied as
    literals -- the previous hand-copied ``0x75595489``/``0x7c4f7a38`` comments
    matched nothing, so those branches were dead and the competition reads
    silently fell through to the zero default.
    """

    async def mock_post(url, json=None, **kwargs):
        data = json or {}
        method = data.get("method", "")
        params = data.get("params", [{}])
        call_data = params[0].get("data", "") if isinstance(params[0], dict) else ""

        if method == "eth_blockNumber":
            return _rpc_response(hex(5000))
        if method == "eth_getLogs":
            return _rpc_response([])
        if call_data.startswith(_SEL_TOTAL_SUPPLY):
            return _rpc_response("0x" + _encode_uint256(total_supply))
        if call_data.startswith(_SEL_BALANCE_OF):
            return _rpc_response("0x" + _encode_uint256(burned))
        if call_data.startswith(_SEL_TOTAL_STAKED):
            return _rpc_response("0x" + _encode_uint256(staked))
        if call_data.startswith(_SEL_GET_RESERVES):
            return _rpc_response(_make_reserves_result(weth, kibble_reserve))
        if call_data.startswith(_SEL_ACC_REWARD_PER_SHARE):
            return _rpc_response("0x" + _encode_uint256(0))
        if call_data.startswith(_SEL_GET_CURRENT_COMPETITION):
            return _rpc_response(competition_raw)
        if call_data.startswith(_SEL_GET_LEADERBOARD):
            return _rpc_response(leaderboard_raw)
        return _rpc_response("0x" + _encode_uint256(0))

    return mock_post


class TestCompetitionFromApi:
    """The cat.town REST parse -- the primary production path.

    Before MEDI-39 this had zero coverage anywhere in the suite: the only
    test that reached it passed a bare AsyncMock whose ``.json()`` returned an
    unawaited coroutine, so ``_get_competition_from_api`` always died with
    AttributeError and ``get_competition_state`` quietly used the RPC branch.
    """

    @pytest.mark.asyncio
    async def test_api_success_is_parsed(self, mock_client):
        client, mock_http = mock_client
        mock_http.get = AsyncMock(
            return_value=_json_response(_API_LEADERBOARD_PAYLOAD)
        )

        state = await client.get_competition_state()

        # The API branch really ran: no RPC call was made at all.
        mock_http.post.assert_not_called()

        assert state.is_active is True
        assert state.start_time == 1_767_052_800
        assert state.end_time == 1_767_225_599
        # prizePool is the total volume in wei; the split is 70/10/10.
        assert state.total_volume_kibble == pytest.approx(4_000.0)
        assert state.prize_pool_kibble == pytest.approx(400.0)
        assert state.treasure_pool_kibble == pytest.approx(2_800.0)
        assert state.staker_revenue_kibble == pytest.approx(400.0)

        # The zero-size row is dropped, the rest are ranked by weight.
        assert state.num_participants == 2
        assert len(state.entries) == 2
        assert [e.rank for e in state.entries] == [1, 2]
        assert state.entries[0].fish_weight_kg == pytest.approx(12.5)
        assert state.entries[0].fish_species == "Coelacanth"
        assert state.entries[0].rarity == "Shiny"
        # basename is packed as "display|address" for the manager to split,
        # with the .base.eth suffix stripped.
        assert state.entries[0].fisher_address == "meowmaster|0x" + "11" * 20
        assert state.entries[1].fisher_address == "|0x" + "22" * 20
        assert state.entries[1].rarity == "Normal"

    @pytest.mark.asyncio
    async def test_api_failure_falls_back_to_rpc(self, mock_client):
        """When the REST call raises, the onchain branch takes over."""
        client, mock_http = mock_client
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        start = 1_767_052_800
        end = 1_767_225_599
        volume = 4_000 * 10**18
        competition_raw = "0x" + (
            _encode_uint256(0)  # eventId
            + _encode_uint256(0)  # name offset
            + _encode_uint256(start)
            + _encode_uint256(end)
            + _encode_uint256(volume)
            + _encode_uint256(0)  # prizesDistributed
        )
        mock_http.post = AsyncMock(
            side_effect=_rpc_only_post(
                total_supply=0,
                burned=0,
                staked=0,
                weth=0,
                kibble_reserve=0,
                competition_raw=competition_raw,
            )
        )

        state = await client.get_competition_state()

        # The RPC branch really ran.
        assert mock_http.post.call_count > 0
        assert state.start_time == start
        assert state.end_time == end
        assert state.total_volume_kibble == pytest.approx(4_000.0)
        assert state.prize_pool_kibble == pytest.approx(400.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "broken_competition",
        [
            {"prizePool": None},
            {"prizePool": "4000.5"},
        ],
    )
    async def test_api_schema_drift_raises_rather_than_lying(
        self, mock_client, broken_competition
    ):
        """Drift in the leaderboard JSON must surface, not produce a wrong number.

        This is the risk the finding calls out. ``int(comp["prizePool"])``
        raises on a null or decimal-string prize pool, which lets
        ``get_competition_state`` fall back to RPC. Pinning that keeps the
        API parse honest instead of half-parsed.
        """
        client, mock_http = mock_client
        broken = {
            "competition": dict(
                _API_LEADERBOARD_PAYLOAD["competition"], **broken_competition
            ),
            "leaderboard": [],
        }
        mock_http.get = AsyncMock(return_value=_json_response(broken))

        with pytest.raises((TypeError, ValueError)):
            await client._get_competition_from_api()

    @pytest.mark.asyncio
    async def test_api_drift_falls_back_instead_of_reporting_zero(self, mock_client):
        """A broken API payload routes to RPC, not to a zeroed CompetitionState."""
        client, mock_http = mock_client
        broken = {
            "competition": dict(
                _API_LEADERBOARD_PAYLOAD["competition"], prizePool=None
            ),
            "leaderboard": [],
        }
        mock_http.get = AsyncMock(return_value=_json_response(broken))

        volume = 4_000 * 10**18
        competition_raw = "0x" + (
            _encode_uint256(0)
            + _encode_uint256(0)
            + _encode_uint256(1_767_052_800)
            + _encode_uint256(1_767_225_599)
            + _encode_uint256(volume)
            + _encode_uint256(0)
        )
        mock_http.post = AsyncMock(
            side_effect=_rpc_only_post(
                total_supply=0,
                burned=0,
                staked=0,
                weth=0,
                kibble_reserve=0,
                competition_raw=competition_raw,
            )
        )

        state = await client.get_competition_state()

        assert state.total_volume_kibble == pytest.approx(4_000.0)


class TestFetchSnapshot:
    @pytest.mark.asyncio
    async def test_fetch_snapshot_assembles_all(self, mock_client):
        client, mock_http = mock_client

        total_supply = 1_000_000_000 * 10**18
        burned = 100_000_000 * 10**18
        staked = 50_000_000 * 10**18
        weth = 10 * 10**18
        kibble_reserve = 1_000_000 * 10**18

        # Real Response objects, not AsyncMock: see _json_response.
        mock_http.get = AsyncMock(
            return_value=_json_response(_API_LEADERBOARD_PAYLOAD)
        )
        mock_http.post = AsyncMock(
            side_effect=_rpc_only_post(
                total_supply=total_supply,
                burned=burned,
                staked=staked,
                weth=weth,
                kibble_reserve=kibble_reserve,
            )
        )

        snapshot = await client.fetch_snapshot()

        assert isinstance(snapshot, CatTownSnapshot)
        assert snapshot.fetched_at > 0
        assert isinstance(snapshot.kibble, KibbleEconomy)
        assert isinstance(snapshot.competition, CompetitionState)
        assert isinstance(snapshot.staking, StakingState)
        assert isinstance(snapshot.recent_catches, list)
        assert snapshot.kibble.total_supply == pytest.approx(1_000_000_000.0)
        assert snapshot.kibble.burned == pytest.approx(100_000_000.0)
        assert snapshot.staking.total_staked == pytest.approx(50_000_000.0)
        # Competition came from the API path, fully parsed -- the old version
        # of this test asserted only isinstance() and so passed with an
        # all-zero default that no production run would ever produce.
        assert snapshot.competition.num_participants == 2
        assert snapshot.competition.total_volume_kibble == pytest.approx(4_000.0)

    @pytest.mark.asyncio
    async def test_fetch_snapshot_never_leaves_a_coroutine_unawaited(
        self, mock_client
    ):
        """Guards the mock shape itself.

        The suite's only two 'coroutine never awaited' RuntimeWarnings came
        from this test's mock returning coroutines where the code expects
        values. Promote that warning to an error here so the trap cannot be
        reintroduced.
        """
        client, mock_http = mock_client
        mock_http.get = AsyncMock(
            return_value=_json_response(_API_LEADERBOARD_PAYLOAD)
        )
        mock_http.post = AsyncMock(
            side_effect=_rpc_only_post(
                total_supply=0, burned=0, staked=0, weth=0, kibble_reserve=0
            )
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            await client.fetch_snapshot()


# ---------------------------------------------------------------------------
# Tests: Retry behavior
# ---------------------------------------------------------------------------

class TestEndpointFailover:
    """MEDI-17: Cat Town had one hardcoded endpoint and no pacing.

    A 429 burst or an outage at mainnet.base.org bricked the dashboard for the
    whole session while the _safe_* wrappers rendered zeroed data as fresh.
    These tests pin the hardened transport behaviour that ttt/talismans
    already had: rotation, dead-code classification, and inter-call pacing.
    """

    @pytest.fixture
    def failover_client(self):
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        client = CatTownClient(
            rpc_url="https://primary.invalid",
            fallback_rpcs=["https://second.invalid", "https://third.invalid"],
            inter_call_delay=0.0,
            http_client=mock_http,
        )
        return client, mock_http

    @pytest.mark.asyncio
    async def test_dead_status_rotates_without_burning_retries(
        self, failover_client
    ):
        """403/451/52x mean the host is blocking us -- move on immediately."""
        client, mock_http = failover_client
        seen: list[str] = []

        async def mock_post(url, json=None, **kwargs):
            seen.append(url)
            if url == "https://primary.invalid":
                return httpx.Response(
                    status_code=403,
                    request=httpx.Request("POST", url),
                )
            return _rpc_response("0x" + _encode_uint256(7))

        mock_http.post = AsyncMock(side_effect=mock_post)

        result = await client._rpc("eth_call", [{"to": "0x0", "data": "0x0"}, "latest"])

        assert result == "0x" + _encode_uint256(7)
        # Primary hit exactly once (not 3x), then the fallback answered.
        assert seen == ["https://primary.invalid", "https://second.invalid"]

    @pytest.mark.asyncio
    async def test_transient_failure_exhausts_retries_then_rotates(
        self, failover_client
    ):
        client, mock_http = failover_client
        seen: list[str] = []

        async def mock_post(url, json=None, **kwargs):
            seen.append(url)
            if url == "https://primary.invalid":
                return httpx.Response(
                    status_code=503,
                    request=httpx.Request("POST", url),
                )
            return _rpc_response("0x" + _encode_uint256(9))

        mock_http.post = AsyncMock(side_effect=mock_post)
        with patch(
            "maxpane_dashboard.data.cattown_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await client._rpc("eth_blockNumber", [])

        assert result == "0x" + _encode_uint256(9)
        assert seen.count("https://primary.invalid") == 3  # full retry ladder
        assert seen[-1] == "https://second.invalid"

    @pytest.mark.asyncio
    async def test_all_endpoints_failing_raises(self, failover_client):
        """Total failure must raise so error_count climbs and data reads stale.

        The old client had nowhere to rotate to, so this was the only outcome.
        The point of the test is that it is still the outcome once every
        endpoint is exhausted -- rotation must not turn an outage into a
        silently zeroed dashboard.
        """
        client, mock_http = failover_client
        mock_http.post = AsyncMock(
            side_effect=lambda url, **kw: httpx.Response(
                status_code=429, request=httpx.Request("POST", url)
            )
        )

        with patch(
            "maxpane_dashboard.data.cattown_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(RuntimeError, match="all 3 endpoint"):
                await client._rpc("eth_blockNumber", [])

    @pytest.mark.asyncio
    async def test_rate_limit_error_body_rotates(self, failover_client):
        """A 429 delivered as a JSON-RPC error body still rotates."""
        client, mock_http = failover_client

        async def mock_post(url, json=None, **kwargs):
            if url == "https://primary.invalid":
                return _rpc_error_response("rate limit exceeded")
            return _rpc_response("0x" + _encode_uint256(5))

        mock_http.post = AsyncMock(side_effect=mock_post)

        assert await client._rpc("eth_blockNumber", []) == "0x" + _encode_uint256(5)

    @pytest.mark.asyncio
    async def test_contract_revert_does_not_rotate(self, failover_client):
        """A revert is the contract's answer, not the endpoint's fault."""
        client, mock_http = failover_client
        mock_http.post = AsyncMock(return_value=_rpc_error_response("execution reverted"))

        with pytest.raises(RuntimeError, match="RPC error"):
            await client._rpc("eth_call", [{"to": "0x0", "data": "0x0"}, "latest"])

        assert mock_http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_non_json_body_rotates(self, failover_client):
        """HTTP 200 carrying an HTML challenge page must not fail the call."""
        client, mock_http = failover_client

        async def mock_post(url, json=None, **kwargs):
            if url == "https://primary.invalid":
                return httpx.Response(
                    status_code=200,
                    content=b"<html>Just a moment...</html>",
                    headers={"Content-Type": "text/html"},
                    request=httpx.Request("POST", url),
                )
            return _rpc_response("0x" + _encode_uint256(3))

        mock_http.post = AsyncMock(side_effect=mock_post)

        assert await client._rpc("eth_blockNumber", []) == "0x" + _encode_uint256(3)

    @pytest.mark.asyncio
    async def test_calls_are_paced(self):
        """Consecutive RPC calls are spaced by inter_call_delay."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_rpc_response("0x" + _encode_uint256(1)))
        client = CatTownClient(http_client=mock_http, inter_call_delay=0.05)

        slept: list[float] = []

        async def fake_sleep(delay):
            slept.append(delay)

        with patch(
            "maxpane_dashboard.data.cattown_client.asyncio.sleep", fake_sleep
        ):
            await client._rpc("eth_blockNumber", [])
            await client._rpc("eth_blockNumber", [])

        # First call is free; the second waits out the remaining gap.
        assert len(slept) == 1
        assert 0 < slept[0] <= 0.05

    def test_primary_is_not_duplicated_in_the_rotation(self):
        client = CatTownClient(
            rpc_url="https://dup.invalid",
            fallback_rpcs=["https://dup.invalid", "https://other.invalid"],
            http_client=AsyncMock(spec=httpx.AsyncClient),
        )
        assert client._fallback_rpcs == ["https://other.invalid"]

    def test_default_pool_has_real_fallbacks(self):
        """Guards against the pool silently collapsing back to one endpoint."""
        from maxpane_dashboard.data.cattown_client import _FALLBACK_RPCS

        client = CatTownClient(http_client=AsyncMock(spec=httpx.AsyncClient))
        assert len(client._fallback_rpcs) >= 2
        assert set(client._fallback_rpcs) <= set(_FALLBACK_RPCS)
        assert client._rpc_url not in client._fallback_rpcs
        # Keyless by policy -- no API keys in any endpoint URL.
        for url in [client._rpc_url, *client._fallback_rpcs]:
            assert "key" not in url.lower()


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
