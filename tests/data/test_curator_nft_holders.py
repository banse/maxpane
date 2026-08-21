from __future__ import annotations

import json

import httpx
import pytest

from maxpane_dashboard.data.curator_list_filters import (
    PREDEFINED_NFT_COLLECTIONS,
)
from maxpane_dashboard.data.curator_nft_holders import (
    NftHolderClient,
    NftHolderUnavailable,
    wallet_universe_fingerprint,
)
from maxpane_dashboard.data.evm_abi import encode_uint


def _rpc_result(request_id, result):
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": request_id, "result": result},
    )


def _call_count(calldata: str) -> int:
    raw = calldata[10:]
    array_offset = int(raw[:64], 16) * 2
    return int(raw[array_offset : array_offset + 64], 16)


def _results(values: list[tuple[bool, int | None]]) -> str:
    tuples = []
    for success, value in values:
        body = "" if value is None else encode_uint(value)
        padded = body + "0" * ((64 - len(body) % 64) % 64)
        tuples.append(
            encode_uint(1 if success else 0)
            + encode_uint(64)
            + encode_uint(len(body) // 2)
            + padded
        )
    cursor = len(values) * 32
    offsets = []
    for item in tuples:
        offsets.append(encode_uint(cursor))
        cursor += len(item) // 2
    return "0x" + "".join(
        (encode_uint(32), encode_uint(len(values)), *offsets, *tuples)
    )


def _client(handler):
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    client = NftHolderClient(
        http_client=http_client,
        rpc_pools={
            "ethereum": ("https://eth.invalid",),
            "base": ("https://base.invalid",),
        },
        min_interval=0,
    )
    return client, http_client


@pytest.mark.asyncio
async def test_ethereum_and_base_route_to_separate_keyless_pools():
    urls = []

    async def handler(request):
        urls.append(str(request.url))
        body = json.loads(request.content)
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x123")
        return _rpc_result(body["id"], _results([(True, 0)]))

    client, http_client = _client(handler)
    wallet = "0x" + "1" * 40
    await client.scan(PREDEFINED_NFT_COLLECTIONS[0], [wallet])
    await client.scan(PREDEFINED_NFT_COLLECTIONS[1], [wallet])
    assert any(url.startswith("https://eth.invalid") for url in urls)
    assert any(url.startswith("https://base.invalid") for url in urls)
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_dead_endpoint_fails_over_and_total_failure_is_explicit():
    requests = []

    async def handler(request):
        requests.append((request.url.host, json.loads(request.content)["method"]))
        body = json.loads(request.content)
        if request.url.host == "dead.invalid":
            return httpx.Response(503)
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x1")
        return _rpc_result(body["id"], _results([(True, 0)]))

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    client = NftHolderClient(
        http_client=http_client,
        rpc_pools={"ethereum": (
            "https://dead.invalid", "https://good.invalid"
        )},
        min_interval=0,
    )
    await client.scan(
        PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
    )
    assert {host for host, _method in requests} == {
        "dead.invalid", "good.invalid"
    }

    dead_only = NftHolderClient(
        http_client=http_client,
        rpc_pools={"ethereum": ("https://dead.invalid",)},
        min_interval=0,
    )
    with pytest.raises(NftHolderUnavailable, match="RPC unavailable"):
        await dead_only.scan(
            PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
        )
    await client.close()
    await dead_only.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_balance_scans_chunk_at_exactly_500_and_keep_alignment():
    chunks = []
    wallets = [f"0x{index:040x}" for index in range(1, 1002)]

    async def handler(request):
        body = json.loads(request.content)
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        count = _call_count(body["params"][0]["data"])
        chunks.append(count)
        return _rpc_result(
            body["id"],
            _results([(True, index % 2) for index in range(count)]),
        )

    client, http_client = _client(handler)
    scan = await client.scan(PREDEFINED_NFT_COLLECTIONS[0], wallets)
    assert chunks == [500, 500, 1]
    assert (scan.checked, scan.failed) == (1001, 0)
    assert len(scan.holders) == 500
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_subcall_failure_is_incomplete_not_a_false_nonholder():
    methods = []

    async def handler(request):
        body = json.loads(request.content)
        methods.append(body["method"])
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        return _rpc_result(body["id"], _results([
            (True, 0), (False, None)
        ]))

    client, http_client = _client(handler)
    scan = await client.scan(
        PREDEFINED_NFT_COLLECTIONS[3],
        ["0x" + "1" * 40, "0x" + "2" * 40],
    )
    assert (scan.checked, scan.failed, scan.complete) == (1, 1, False)
    assert methods == ["eth_getCode", "eth_blockNumber", "eth_call"]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_no_code_is_unavailable_and_never_runs_multicall():
    methods = []

    async def handler(request):
        body = json.loads(request.content)
        methods.append(body["method"])
        return _rpc_result(body["id"], "0x")

    client, http_client = _client(handler)
    with pytest.raises(NftHolderUnavailable, match="no contract code"):
        await client.scan(
            PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
        )
    assert methods == ["eth_getCode"]
    await client.close()
    await http_client.aclose()


def test_wallet_universe_fingerprint_is_case_and_order_stable():
    first = "0x" + "a" * 40
    second = "0x" + "b" * 40
    assert wallet_universe_fingerprint([second, first.upper()]) == (
        wallet_universe_fingerprint([first, second])
    )
