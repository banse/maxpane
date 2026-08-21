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
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append((str(request.url), body["method"]))
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x123")
        if body["method"] == "eth_call":
            return _rpc_result(body["id"], _results([(True, 0)]))
        raise AssertionError(f"unexpected RPC method: {body['method']}")

    client, http_client = _client(handler)
    wallet = "0x" + "1" * 40
    await client.scan(PREDEFINED_NFT_COLLECTIONS[0], [wallet])
    await client.scan(PREDEFINED_NFT_COLLECTIONS[1], [wallet])
    assert requests == [
        ("https://eth.invalid", "eth_blockNumber"),
        ("https://eth.invalid", "eth_getCode"),
        ("https://eth.invalid", "eth_call"),
        ("https://base.invalid", "eth_blockNumber"),
        ("https://base.invalid", "eth_getCode"),
        ("https://base.invalid", "eth_call"),
    ]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_dead_endpoint_fails_over_and_total_failure_is_explicit():
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        method = body["method"]
        requests.append((str(request.url), method))
        if method not in {"eth_getCode", "eth_blockNumber", "eth_call"}:
            raise AssertionError(f"unexpected RPC method: {method}")
        if request.url.host == "dead.invalid":
            return httpx.Response(503)
        if request.url.host != "good.invalid":
            raise AssertionError(f"unexpected RPC host: {request.url.host}")
        if method == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if method == "eth_blockNumber":
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
    assert requests == [
        ("https://dead.invalid", "eth_blockNumber"),
        ("https://good.invalid", "eth_blockNumber"),
        ("https://dead.invalid", "eth_getCode"),
        ("https://good.invalid", "eth_getCode"),
        ("https://dead.invalid", "eth_call"),
        ("https://good.invalid", "eth_call"),
    ]

    dead_only = NftHolderClient(
        http_client=http_client,
        rpc_pools={"ethereum": ("https://dead.invalid",)},
        min_interval=0,
    )
    with pytest.raises(NftHolderUnavailable, match="RPC unavailable"):
        await dead_only.scan(
            PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
        )
    assert requests[-1] == ("https://dead.invalid", "eth_blockNumber")
    await client.close()
    await dead_only.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_balance_scans_chunk_at_exactly_500_and_keep_alignment():
    chunks = []
    requests = []
    wallets = [f"0x{index:040x}" for index in range(1, 1002)]

    async def handler(request):
        body = json.loads(request.content)
        requests.append((str(request.url), body["method"]))
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        if body["method"] != "eth_call":
            raise AssertionError(f"unexpected RPC method: {body['method']}")
        count = _call_count(body["params"][0]["data"])
        chunks.append(count)
        return _rpc_result(
            body["id"],
            _results([(True, index % 2) for index in range(count)]),
        )

    client, http_client = _client(handler)
    scan = await client.scan(PREDEFINED_NFT_COLLECTIONS[0], wallets)
    assert chunks == [500, 500, 1]
    assert requests == [
        ("https://eth.invalid", "eth_blockNumber"),
        ("https://eth.invalid", "eth_getCode"),
        ("https://eth.invalid", "eth_call"),
        ("https://eth.invalid", "eth_call"),
        ("https://eth.invalid", "eth_call"),
    ]
    assert (scan.checked, scan.failed) == (1001, 0)
    assert len(scan.holders) == 500
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_scan_pins_code_and_every_multicall_chunk_to_returned_block():
    requests = []
    wallets = [f"0x{index:040x}" for index in range(1, 502)]

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] != "eth_call":
            raise AssertionError(f"unexpected RPC method: {body['method']}")
        count = _call_count(body["params"][0]["data"])
        return _rpc_result(body["id"], _results([(True, 0)] * count))

    client, http_client = _client(handler)
    scan = await client.scan(PREDEFINED_NFT_COLLECTIONS[0], wallets)

    assert scan.block_number == 0x999
    assert [request["method"] for request in requests] == [
        "eth_blockNumber",
        "eth_getCode",
        "eth_call",
        "eth_call",
    ]
    assert [
        (request["method"], request["params"][-1])
        for request in requests
        if request["method"] != "eth_blockNumber"
    ] == [
        ("eth_getCode", "0x999"),
        ("eth_call", "0x999"),
        ("eth_call", "0x999"),
    ]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_subcall_failure_is_incomplete_not_a_false_nonholder():
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append((str(request.url), body["method"]))
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        if body["method"] == "eth_call":
            return _rpc_result(body["id"], _results([
                (True, 0), (False, None)
            ]))
        raise AssertionError(f"unexpected RPC method: {body['method']}")

    client, http_client = _client(handler)
    scan = await client.scan(
        PREDEFINED_NFT_COLLECTIONS[3],
        ["0x" + "1" * 40, "0x" + "2" * 40],
    )
    assert (scan.checked, scan.failed, scan.complete) == (1, 1, False)
    assert requests == [
        ("https://eth.invalid", "eth_blockNumber"),
        ("https://eth.invalid", "eth_getCode"),
        ("https://eth.invalid", "eth_call"),
    ]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_no_code_is_unavailable_and_never_runs_multicall():
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append((str(request.url), body["method"]))
        if body["method"] == "eth_blockNumber":
            return _rpc_result(body["id"], "0x999")
        if body["method"] == "eth_getCode":
            return _rpc_result(body["id"], "0x")
        raise AssertionError(f"unexpected RPC method: {body['method']}")

    client, http_client = _client(handler)
    with pytest.raises(NftHolderUnavailable, match="no contract code"):
        await client.scan(
            PREDEFINED_NFT_COLLECTIONS[0], ["0x" + "1" * 40]
        )
    assert requests == [
        ("https://eth.invalid", "eth_blockNumber"),
        ("https://eth.invalid", "eth_getCode"),
    ]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("malformed_method", "malformed_result"),
    [
        ("eth_getCode", None),
        ("eth_getCode", "not-hex-code"),
        ("eth_blockNumber", "not-a-hex-quantity"),
        ("eth_call", "0xdeadbeef"),
    ],
)
async def test_malformed_primary_result_fails_over_to_healthy_endpoint(
    malformed_method,
    malformed_result,
):
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        method = body["method"]
        requests.append((str(request.url), method))
        if method not in {"eth_getCode", "eth_blockNumber", "eth_call"}:
            raise AssertionError(f"unexpected RPC method: {method}")
        if request.url.host == "malformed.invalid" and method == malformed_method:
            if malformed_result is None:
                return httpx.Response(
                    200,
                    json={"jsonrpc": "2.0", "id": body["id"]},
                )
            return _rpc_result(body["id"], malformed_result)
        if request.url.host not in {"malformed.invalid", "healthy.invalid"}:
            raise AssertionError(f"unexpected RPC host: {request.url.host}")
        if method == "eth_getCode":
            return _rpc_result(body["id"], "0x6000")
        if method == "eth_blockNumber":
            return _rpc_result(body["id"], "0x1")
        return _rpc_result(body["id"], _results([(True, 1)]))

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    client = NftHolderClient(
        http_client=http_client,
        rpc_pools={"ethereum": (
            "https://malformed.invalid", "https://healthy.invalid"
        )},
        min_interval=0,
    )
    wallet = "0x" + "1" * 40
    scan = await client.scan(PREDEFINED_NFT_COLLECTIONS[0], [wallet])
    assert (scan.holders, scan.checked, scan.failed, scan.block_number) == (
        frozenset({wallet}), 1, 0, 1
    )
    failed_at = requests.index(
        ("https://malformed.invalid", malformed_method)
    )
    assert requests[failed_at : failed_at + 2] == [
        ("https://malformed.invalid", malformed_method),
        ("https://healthy.invalid", malformed_method),
    ]
    await client.close()
    await http_client.aclose()


def test_wallet_universe_fingerprint_is_case_and_order_stable():
    first = "0x" + "a" * 40
    second = "0x" + "b" * 40
    assert wallet_universe_fingerprint([second, first.upper()]) == (
        wallet_universe_fingerprint([first, second])
    )
