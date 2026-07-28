"""Tests for the keyless Talismans Ethereum-mainnet RPC client.

All tests run against canned JSON-RPC responses (monkeypatched ``_rpc`` or an
injected fake ``httpx.AsyncClient``) -- no real network.
"""

from __future__ import annotations

from typing import Any

import pytest

import httpx

from maxpane_dashboard.data.talismans_client import (
    TalismansClient,
    TalismansRpcError,
    _LOG_RANGE_PER_CALL,
    _SEL_NEXT_TRANSFORM_ID,
    _SEL_OWNER_OF,
    _SEL_TOKEN_DATA,
    _classify_rpc_error,
    _decode_bonded_log,
    _decode_cleaved_log,
    _decode_cut_log,
    _decode_merged_log,
    _decode_token_data,
    _decode_transfer_log,
    _encode_uint,
    _parse_suggested_to,
)


# ---------------------------------------------------------------------------
# Task 3.2: _decode_token_data
# ---------------------------------------------------------------------------


def test_decode_token_data_token1():
    # EXACT live-chain return for tokenData(1) — note the leading 0x20 tuple
    # offset word: the return is a single dynamic tuple, so it is ABI-wrapped.
    hexdata = (
        "0x"
        "0000000000000000000000000000000000000000000000000000000000000020"  # tuple offset = 32
        "00000000000000000000000000000000000000000000000000000000000000a0"  # offset to cores[] = 160 (rel. to tuple)
        "0000000000000000000000000000000000000000000000000000000000000000"  # materialId 0
        "0000000000000000000000000000000000000000000000000000000000000002"  # form 2
        "0000000000000000000000000000000000000000000000000000000000000002"  # coreCount 2
        "00000000000000000000000000000000000000000000000000000000000026bc"  # seed 0x26bc
        "0000000000000000000000000000000000000000000000000000000000000002"  # cores length 2
        "0000000000000000000000000000000000000000000000000000000000ce1880"  # core0
        "000000000000000000000000000000000000000000000000000000000054e880"  # core1
    )
    cores, material_id, form, core_count, seed = _decode_token_data(hexdata)
    assert material_id == 0 and form == 2 and core_count == 2 and seed == 0x26BC
    assert cores == [0xCE1880, 0x54E880]


def test_decode_token_data_empty_revert():
    assert _decode_token_data("0x") == ([], 0, 0, 0, 0)
    assert _decode_token_data("") == ([], 0, 0, 0, 0)


def test_decode_token_data_single_core():
    hexdata = (
        "0x"
        "0000000000000000000000000000000000000000000000000000000000000020"  # tuple offset = 32
        "00000000000000000000000000000000000000000000000000000000000000a0"  # offset 160 (rel. to tuple)
        "0000000000000000000000000000000000000000000000000000000000000003"  # materialId 3
        "0000000000000000000000000000000000000000000000000000000000000001"  # form 1
        "0000000000000000000000000000000000000000000000000000000000000001"  # coreCount 1
        "0000000000000000000000000000000000000000000000000000000000001234"  # seed
        "0000000000000000000000000000000000000000000000000000000000000001"  # cores length 1
        "00000000000000000000000000000000000000000000000000000000000abcde"  # core0
    )
    cores, material_id, form, core_count, seed = _decode_token_data(hexdata)
    assert cores == [0xABCDE]
    assert material_id == 3 and form == 1 and core_count == 1 and seed == 0x1234


# ---------------------------------------------------------------------------
# Task 3.3: event decoders
# ---------------------------------------------------------------------------

_OPERATOR = "0xb9bb10d46ef46068b876f0ffa27016eca5dee8ab"
_OPERATOR_WORD = "000000000000000000000000b9bb10d46ef46068b876f0ffa27016eca5dee8ab"


def test_decode_bonded_log_real_sample():
    log = {
        "topics": [
            "0xf4d7559aa146406a2a7769decb3cc99cb5c91d0c4b37c8c48ef43b5df27dac8d",
            "0x0000000000000000000000000000000000000000000000000000000000000106",
            "0x0000000000000000000000000000000000000000000000000000000000000107",
            "0x0000000000000000000000000000000000000000000000000000000000000601",
        ],
        "data": "0x" + _OPERATOR_WORD,
        "blockNumber": "0x10",
        "transactionHash": "0xabc",
    }
    out = _decode_bonded_log(log)
    assert out["op_type"] == "bond"
    assert out["token_id_a"] == 262
    assert out["token_id_b"] == 263
    assert out["result_id"] == 1537
    assert out["operator"] == _OPERATOR
    assert out["block_number"] == 16
    assert out["tx_hash"] == "0xabc"
    assert out["timestamp"] == 0


def test_decode_cleaved_log():
    log = {
        "topics": [
            "0x46ba0b66389416f9b9efdb0acff2fa246aeca62e3a0b23cf1f2503daef255209",
            "0x0000000000000000000000000000000000000000000000000000000000000010",  # tokenId 16
            "0x0000000000000000000000000000000000000000000000000000000000000020",  # lithicId 32
            "0x0000000000000000000000000000000000000000000000000000000000000030",  # lumicId 48
        ],
        "data": "0x" + _OPERATOR_WORD,
        "blockNumber": "0x2",
        "transactionHash": "0xdef",
    }
    out = _decode_cleaved_log(log)
    assert out["op_type"] == "cleave"
    assert out["token_id_a"] == 16
    assert out["token_id_b"] is None
    assert out["result_id"] == 32
    assert out["result_id_b"] == 48
    assert out["operator"] == _OPERATOR


def test_decode_cut_log_operator_is_second_word():
    # data has TWO words: index (word 0) then operator (word 1)
    index_word = "0000000000000000000000000000000000000000000000000000000000000005"
    log = {
        "topics": [
            "0x8a931aa6e7978064180abf7fe0fad5724567980368d0620b07f12c150063455a",
            "0x0000000000000000000000000000000000000000000000000000000000000041",  # tokenId 65
            "0x0000000000000000000000000000000000000000000000000000000000000042",  # headId 66
            "0x0000000000000000000000000000000000000000000000000000000000000043",  # tailId 67
        ],
        "data": "0x" + index_word + _OPERATOR_WORD,
        "blockNumber": "0x3",
        "transactionHash": "0x111",
    }
    out = _decode_cut_log(log)
    assert out["op_type"] == "cut"
    assert out["token_id_a"] == 65
    assert out["token_id_b"] is None
    assert out["result_id"] == 66
    assert out["result_id_b"] == 67
    # operator must come from data word 1, not word 0
    assert out["operator"] == _OPERATOR


def test_decode_merged_log():
    log = {
        "topics": [
            "0x16c20a9d07670de1acd6a4887d37d0bd6e908958838c007bdab074541130d1e0",
            "0x0000000000000000000000000000000000000000000000000000000000000001",
            "0x0000000000000000000000000000000000000000000000000000000000000002",
            "0x0000000000000000000000000000000000000000000000000000000000000003",
        ],
        "data": "0x" + _OPERATOR_WORD,
        "blockNumber": "0x4",
        "transactionHash": "0x222",
    }
    out = _decode_merged_log(log)
    assert out["op_type"] == "merge"
    assert out["token_id_a"] == 1
    assert out["token_id_b"] == 2
    assert out["result_id"] == 3
    assert out["operator"] == _OPERATOR


def test_decode_transfer_log():
    log = {
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x0000000000000000000000000000000000000000000000000000000000000000",  # from zero
            "0x" + _OPERATOR_WORD,  # to operator
            "0x00000000000000000000000000000000000000000000000000000000000000ff",  # tokenId 255
        ],
        "data": "0x",
        "blockNumber": "0x5",
        "transactionHash": "0x333",
    }
    out = _decode_transfer_log(log)
    assert out["from"] == "0x" + "0" * 40
    assert out["to"] == _OPERATOR
    assert out["token_id"] == 255
    assert out["block_number"] == 5
    assert out["tx_hash"] == "0x333"


def test_decode_log_malformed_returns_none():
    assert _decode_bonded_log({"topics": [], "data": "0x"}) is None
    assert _decode_transfer_log({"topics": ["0x", "0x"], "data": "0x"}) is None


# ---------------------------------------------------------------------------
# Task 3.4: public async methods (canned transport)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, result: Any):
        self._result = result
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"jsonrpc": "2.0", "id": 1, "result": self._result}


def _aggregate3_return(results: list[tuple[bool, str]]) -> str:
    """Hand-build an ``aggregate3`` return blob for the given (success, data)."""
    from maxpane_dashboard.data.talismans_client import _pad_left, _strip0x

    n = len(results)
    head = _pad_left("20", 64)  # offset to array
    head += _pad_left(hex(n)[2:], 64)  # array length
    # Encode each Result tuple (success, bytes)
    tuples: list[str] = []
    for ok, data in results:
        raw = _strip0x(data)
        body_len = len(raw) // 2
        padded = raw + "0" * ((64 - (len(raw) % 64)) % 64)
        tup = (
            _pad_left("01" if ok else "00", 64)
            + _pad_left("40", 64)  # offset to bytes inside tuple
            + _pad_left(hex(body_len)[2:], 64)
            + padded
        )
        tuples.append(tup)
    # Offsets (in bytes) from start of array body
    offsets: list[int] = []
    cursor = n * 32
    for tup in tuples:
        offsets.append(cursor)
        cursor += len(tup) // 2
    body = "".join(_pad_left(hex(o)[2:], 64) for o in offsets) + "".join(tuples)
    return "0x" + head + body


@pytest.mark.asyncio
async def test_fetch_block_number(monkeypatch):
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        assert method == "eth_blockNumber"
        return "0x1234"

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    assert await client.fetch_block_number() == 0x1234
    await client.close()


@pytest.mark.asyncio
async def test_fetch_collection_flags(monkeypatch):
    client = TalismansClient()

    blob = _aggregate3_return(
        [
            (True, "0x" + _encode_uint(1536)),  # totalSupply
            (True, "0x" + _encode_uint(1536)),  # genesisMinted
            (True, "0x" + _encode_uint(1)),  # bondAndCleaveEnabled = true
            (True, "0x" + _encode_uint(0)),  # cutAndMergeEnabled = false
            (True, "0x" + _encode_uint(1757)),  # nextTransformId
        ]
    )

    async def fake_rpc(method, params, endpoints=None):
        assert method == "eth_call"
        return blob

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    flags = await client.fetch_collection_flags()
    assert flags == {
        "total_supply": 1536,
        "genesis_minted": 1536,
        "bond_cleave_enabled": True,
        "cut_merge_enabled": False,
        "next_transform_id": 1757,
    }
    await client.close()


@pytest.mark.asyncio
async def test_fetch_token_states_skips_reverted(monkeypatch):
    client = TalismansClient()

    # token 1: live (tokenData ok with cores, ownerOf ok)
    # token 2: reverted ownerOf -> skipped
    token1_data = (
        "0x"
        "0000000000000000000000000000000000000000000000000000000000000020"  # tuple offset
        "00000000000000000000000000000000000000000000000000000000000000a0"
        "0000000000000000000000000000000000000000000000000000000000000000"  # material 0
        "0000000000000000000000000000000000000000000000000000000000000002"  # form 2
        "0000000000000000000000000000000000000000000000000000000000000002"  # coreCount 2
        "00000000000000000000000000000000000000000000000000000000000026bc"  # seed
        "0000000000000000000000000000000000000000000000000000000000000002"
        "0000000000000000000000000000000000000000000000000000000000ce1880"
        "000000000000000000000000000000000000000000000000000000000054e880"
    )
    owner1 = "0x" + _OPERATOR_WORD

    captured = {}

    async def fake_rpc(method, params, endpoints=None):
        # capture the aggregate3 calldata for the assertion
        captured["data"] = params[0]["data"]
        return _aggregate3_return(
            [
                (True, token1_data),  # token1 tokenData
                (True, owner1),  # token1 ownerOf
                (True, token1_data),  # token2 tokenData
                (False, "0x"),  # token2 ownerOf reverted
            ]
        )

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    states = await client.fetch_token_states([1, 2])
    assert set(states.keys()) == {1}
    assert states[1]["core_count"] == 2
    assert states[1]["material_id"] == 0
    assert states[1]["form"] == 2
    assert states[1]["seed"] == 0x26BC
    assert states[1]["owner"] == _OPERATOR

    # calldata must embed tokenData + ownerOf selectors and the token ids
    cd = captured["data"]
    assert _SEL_TOKEN_DATA[2:] in cd
    assert _SEL_OWNER_OF[2:] in cd
    await client.close()


@pytest.mark.asyncio
async def test_fetch_token_states_skips_zero_core_count(monkeypatch):
    client = TalismansClient()
    # tokenData with coreCount==0 -> token considered dead/burned
    dead_data = (
        "0x"
        "0000000000000000000000000000000000000000000000000000000000000020"  # tuple offset
        "00000000000000000000000000000000000000000000000000000000000000a0"
        "0000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000"  # coreCount 0
        "0000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000"  # length 0
    )
    owner = "0x" + _OPERATOR_WORD

    async def fake_rpc(method, params, endpoints=None):
        return _aggregate3_return([(True, dead_data), (True, owner)])

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    states = await client.fetch_token_states([99])
    assert states == {}
    await client.close()


@pytest.mark.asyncio
async def test_fetch_operation_logs_merges(monkeypatch):
    client = TalismansClient()

    bonded_log = {
        "topics": [
            "0xf4d7559aa146406a2a7769decb3cc99cb5c91d0c4b37c8c48ef43b5df27dac8d",
            "0x0000000000000000000000000000000000000000000000000000000000000106",
            "0x0000000000000000000000000000000000000000000000000000000000000107",
            "0x0000000000000000000000000000000000000000000000000000000000000601",
        ],
        "data": "0x" + _OPERATOR_WORD,
        "blockNumber": "0x10",
        "transactionHash": "0xa",
    }
    cleaved_log = {
        "topics": [
            "0x46ba0b66389416f9b9efdb0acff2fa246aeca62e3a0b23cf1f2503daef255209",
            "0x0000000000000000000000000000000000000000000000000000000000000010",
            "0x0000000000000000000000000000000000000000000000000000000000000020",
            "0x0000000000000000000000000000000000000000000000000000000000000030",
        ],
        "data": "0x" + _OPERATOR_WORD,
        "blockNumber": "0x11",
        "transactionHash": "0xb",
    }

    async def fake_rpc(method, params, endpoints=None):
        assert method == "eth_getLogs"
        # topics filter must be the 4-way OR
        topics = params[0]["topics"]
        assert isinstance(topics[0], list) and len(topics[0]) == 4
        return [bonded_log, cleaved_log]

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    ops, scanned_to = await client.fetch_operation_logs(100, 200)
    assert scanned_to == 200
    assert len(ops) == 2
    assert {o["op_type"] for o in ops} == {"bond", "cleave"}
    await client.close()


@pytest.mark.asyncio
async def test_fetch_operation_logs_paging(monkeypatch):
    """A >50k range must split into multiple eth_getLogs calls."""
    client = TalismansClient()
    calls: list[tuple[int, int]] = []

    async def fake_rpc(method, params, endpoints=None):
        assert method == "eth_getLogs"
        calls.append(
            (int(params[0]["fromBlock"], 16), int(params[0]["toBlock"], 16))
        )
        return []

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client.fetch_operation_logs(0, 120_000)
    # 50k cap -> [0..49999], [50000..99999], [100000..120000]
    assert len(calls) == 3
    assert calls[0] == (0, 49_999)
    assert calls[1] == (50_000, 99_999)
    assert calls[2] == (100_000, 120_000)
    await client.close()


@pytest.mark.asyncio
async def test_fetch_transfer_logs(monkeypatch):
    client = TalismansClient()
    transfer_log = {
        "topics": [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x0000000000000000000000000000000000000000000000000000000000000000",
            "0x" + _OPERATOR_WORD,
            "0x00000000000000000000000000000000000000000000000000000000000000ff",
        ],
        "data": "0x",
        "blockNumber": "0x5",
        "transactionHash": "0x333",
    }

    async def fake_rpc(method, params, endpoints=None):
        assert method == "eth_getLogs"
        assert params[0]["topics"] == [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        ]
        return [transfer_log]

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    out, scanned_to = await client.fetch_transfer_logs(1, 100)
    assert scanned_to == 100
    assert len(out) == 1
    assert out[0]["token_id"] == 255
    assert out[0]["to"] == _OPERATOR
    await client.close()


# ---------------------------------------------------------------------------
# HIGH-5: JSON-RPC error classification
#
# Every ``error`` payload below was captured from the live endpoint named in
# its comment on 2026-07-27. They are the reason classification keys on the
# message text and not the code: four different conditions share -32602/-32600.
# ---------------------------------------------------------------------------

_LIVE_ERRORS = {
    "publicnode_archive_gate": (
        {
            "code": -32602,
            "message": (
                "Archive requests require a personal token. "
                "Get one at: https://www.allnodes.com/publicnode"
            ),
        },
        "archive",
    ),
    "drpc_range_cap": (
        {"code": 35, "message": "ranges over 10000 blocks are not supported on free plan"},
        "range_cap",
    ),
    "onerpc_range_cap": (
        {"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"},
        "range_cap",
    ),
    "blastapi_range_cap": (
        {
            "code": -32600,
            "message": (
                "You can make eth_getLogs requests with up to a 10 block range. "
                "Based on your parameters, this block range should work: "
                "[0x18708eb, 0x18708f4]"
            ),
        },
        "range_cap",
    ),
    "flashbots_head_range": (
        {"code": -32602, "message": "block range extends beyond current head block"},
        "range_cap",
    ),
    "ankr_needs_key": (
        {
            "code": -32000,
            "message": (
                "Unauthorized: You must authenticate your request with an API key."
            ),
        },
        "dead",
    ),
    "merkle_no_method": ({"code": -32601, "message": "Method not found"}, "dead"),
    "cloudflare_internal": ({"code": -32603, "message": "Internal error"}, "rpc"),
    "geth_result_cap": (
        {"code": -32005, "message": "query returned more than 10000 results"},
        "result_cap",
    ),
}


@pytest.mark.parametrize(
    ("name", "payload", "expected"),
    [(k, v[0], v[1]) for k, v in _LIVE_ERRORS.items()],
)
def test_classify_live_rpc_errors(name, payload, expected):
    assert _classify_rpc_error(payload).kind == expected, name


def test_archive_gate_is_not_shrinkable():
    """publicnode gates on *depth*, not width — narrowing cannot help.

    Classifying it as a range cap would make _get_logs burn its whole shrink
    budget on a window that is refused identically at every size.
    """
    from maxpane_dashboard.data.talismans_client import _SHRINKABLE

    err = _classify_rpc_error(_LIVE_ERRORS["publicnode_archive_gate"][0])
    assert err.kind not in _SHRINKABLE


def test_rate_limit_text_wins_over_archive_wording():
    """A 429 body advertising a 'personal token' must not read as an archive gate.

    Same shape as publicnode's archive message; opposite meaning (transient vs
    permanent), so the rate-limit test has to run first.
    """
    err = _classify_rpc_error(
        {
            "code": -32005,
            "message": "Rate limit exceeded. To obtain higher limits, "
            "please request a personal token from the archive team.",
        }
    )
    assert err.kind == "rate_limit"


def test_result_cap_beats_rate_limit_code():
    """-32005 is a rate-limit code for some providers and a result cap for others."""
    err = _classify_rpc_error(_LIVE_ERRORS["geth_result_cap"][0])
    assert err.kind == "result_cap"


def test_parse_suggested_to_hex_and_decimal():
    assert _parse_suggested_to("should work: [0x18708eb, 0x18708f4]") == 0x18708F4
    assert _parse_suggested_to("retry with the range 25583616-25585541") == 25585541
    # A bare result count must not be mistaken for a block range.
    assert _parse_suggested_to("narrow your filter: 20000") is None
    assert _parse_suggested_to("no numbers here") is None


def test_suggestion_is_ignored_unless_it_shrinks_materially():
    """blastapi suggests a window pinned to the END of the request.

    Its ``to`` is effectively the ``to`` we already asked for, so following it
    verbatim would not narrow anything and would loop until the shrink budget
    ran out. A non-material suggestion must degrade to a clean halving.
    """
    # Suggestion equal to the current end: no shrink at all -> halve instead.
    # span is 50_001 blocks, so a halving lands on 1_000 + 25_000 - 1.
    assert TalismansClient._shrunk_end(1_000, 51_000, 50_999) == 25_999
    # Honest suggestion inside the window and materially smaller -> honoured.
    assert TalismansClient._shrunk_end(1_000, 51_000, 11_000) == 11_000
    # No suggestion -> halve.
    assert TalismansClient._shrunk_end(0, 99, None) == 49


# ---------------------------------------------------------------------------
# HIGH-5: _rpc must fail over, never short-circuit
# ---------------------------------------------------------------------------


def _transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_minus_32602_falls_through_to_next_endpoint():
    """The regression that produced the review's phantom '0 events in window'.

    publicnode answers every archive-depth eth_getLogs with -32602. That code
    used to be treated as a terminal protocol error and re-raised immediately,
    so the three healthy fallbacks were never tried and the whole scan came
    back empty. It must now be a per-endpoint failure.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "publicnode" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": _LIVE_ERRORS["publicnode_archive_gate"][0],
                },
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0xbeef"})

    client = TalismansClient(
        primary_rpc="https://ethereum.publicnode.com",
        fallback_rpcs=["https://good.example"],
        http_client=_transport(handler),
    )
    assert await client._rpc("eth_call", [{}]) == "0xbeef"
    assert len(seen) == 2 and "good.example" in seen[1]
    await client.close()


@pytest.mark.asyncio
async def test_rpc_raises_classified_error_when_all_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": _LIVE_ERRORS["drpc_range_cap"][0],
            },
        )

    client = TalismansClient(
        primary_rpc="https://a.example",
        fallback_rpcs=["https://b.example"],
        http_client=_transport(handler),
    )
    with pytest.raises(TalismansRpcError) as excinfo:
        await client._rpc("eth_getLogs", [{}])
    assert excinfo.value.kind == "range_cap"
    await client.close()


@pytest.mark.asyncio
async def test_rpc_prefers_shrinkable_diagnosis_over_last_error():
    """A later endpoint's unrelated failure must not mask 'narrowing would help'."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = (
            _LIVE_ERRORS["drpc_range_cap"][0]
            if "a.example" in str(request.url)
            else _LIVE_ERRORS["merkle_no_method"][0]
        )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": payload})

    client = TalismansClient(
        primary_rpc="https://a.example",
        fallback_rpcs=["https://z.example"],
        http_client=_transport(handler),
    )
    with pytest.raises(TalismansRpcError) as excinfo:
        await client._rpc("eth_getLogs", [{}])
    assert excinfo.value.kind == "range_cap"
    await client.close()


# ---------------------------------------------------------------------------
# HIGH-5: _get_logs reports how far it actually got
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_stops_at_last_complete_block(monkeypatch):
    """A refused page must stop the scan, not be skipped over.

    The old code logged the failure at debug and jumped to the next page, so
    the caller advanced its watermark past events it never read.
    """
    client = TalismansClient()
    calls: list[tuple[int, int]] = []

    async def fake_rpc(method, params, endpoints=None):
        lo = int(params[0]["fromBlock"], 16)
        hi = int(params[0]["toBlock"], 16)
        calls.append((lo, hi))
        if lo >= 50_000:  # second page is refused outright
            raise TalismansRpcError("dead", "endpoint gone")
        return [{"blockNumber": "0x1"}]

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    logs, scanned_to = await client._get_logs("0xa", [], 0, 149_999)
    assert scanned_to == 49_999, "watermark must not pass the refused page"
    assert len(logs) == 1
    # The scan stopped; it did not carry on to the third page.
    assert calls == [(0, 49_999), (50_000, 99_999)]
    await client.close()


@pytest.mark.asyncio
async def test_get_logs_reports_no_progress_on_first_page_failure(monkeypatch):
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        raise TalismansRpcError("archive", "archive gate")

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    logs, scanned_to = await client._get_logs("0xa", [], 1_000, 60_000)
    assert logs == []
    assert scanned_to == 999, "from_block - 1 means 'nothing was scanned'"
    await client.close()


@pytest.mark.asyncio
async def test_get_logs_shrinks_on_range_cap_and_completes(monkeypatch):
    """drpc's 10k cap must be learned, not fatal — and learned only once."""
    client = TalismansClient()
    attempts: list[tuple[int, int]] = []

    async def fake_rpc(method, params, endpoints=None):
        lo = int(params[0]["fromBlock"], 16)
        hi = int(params[0]["toBlock"], 16)
        attempts.append((lo, hi))
        if hi - lo + 1 > 10_000:
            raise TalismansRpcError(
                "range_cap", "ranges over 10000 blocks are not supported on free plan"
            )
        return []

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    logs, scanned_to = await client._get_logs("0xa", [], 0, 29_999)
    assert scanned_to == 29_999, "the full range must still be covered"
    assert logs == []
    # Pages are contiguous with no gaps: every block is covered exactly once.
    accepted = [(lo, hi) for (lo, hi) in attempts if hi - lo + 1 <= 10_000]
    assert accepted[0][0] == 0
    for prev, nxt in zip(accepted, accepted[1:]):
        assert nxt[0] == prev[1] + 1
    assert accepted[-1][1] == 29_999
    await client.close()


@pytest.mark.asyncio
async def test_get_logs_non_shrinkable_error_is_not_retried(monkeypatch):
    """An archive gate must fail the page immediately, not shrink 8 times."""
    client = TalismansClient()
    attempts = 0

    async def fake_rpc(method, params, endpoints=None):
        nonlocal attempts
        attempts += 1
        raise TalismansRpcError("archive", "Archive requests require a personal token")

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    _, scanned_to = await client._get_logs("0xa", [], 0, 200_000)
    assert attempts == 1
    assert scanned_to == -1
    await client.close()


@pytest.mark.asyncio
async def test_get_logs_empty_range_returns_to_block():
    client = TalismansClient()
    assert await client._get_logs("0xa", [], 500, 400) == ([], 400)
    await client.close()


@pytest.mark.asyncio
async def test_get_logs_uses_the_log_endpoint_pool(monkeypatch):
    """Log scans must target the log pool, not the state-read pool."""
    from maxpane_dashboard.data.talismans_client import _LOG_RPCS

    client = TalismansClient()
    used: list[Any] = []

    async def fake_rpc(method, params, endpoints=None):
        used.append(endpoints)
        return []

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client._get_logs("0xa", [], 0, 10)
    assert used == [_LOG_RPCS]
    await client.close()


def test_log_pool_excludes_nothing_that_cannot_serve_logs():
    """Probed live: merkle has no eth_getLogs, ankr/cloudflare are unusable."""
    from maxpane_dashboard.data.talismans_client import _LOG_RPCS

    for dead in ("merkle.io", "rpc.ankr.com", "cloudflare-eth.com", "llamarpc"):
        assert not any(dead in url for url in _LOG_RPCS), dead
    assert any("tenderly" in url for url in _LOG_RPCS), "need an archive log source"


# ---------------------------------------------------------------------------
# HIGH-4: nextTransformId is read alongside the other collection flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collection_flags_request_includes_next_transform_id(monkeypatch):
    client = TalismansClient()
    captured: dict[str, Any] = {}

    async def fake_rpc(method, params, endpoints=None):
        captured["data"] = params[0]["data"]
        return _aggregate3_return(
            [
                (True, "0x" + _encode_uint(1354)),
                (True, "0x" + _encode_uint(1536)),
                (True, "0x" + _encode_uint(1)),
                (True, "0x" + _encode_uint(0)),
                (True, "0x" + _encode_uint(1757)),
            ]
        )

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    flags = await client.fetch_collection_flags()
    assert _SEL_NEXT_TRANSFORM_ID[2:] in captured["data"]
    assert flags["next_transform_id"] == 1757
    await client.close()


@pytest.mark.asyncio
async def test_collection_flags_next_transform_id_zero_when_call_fails(monkeypatch):
    """A failed read must report 0 so the manager can tell it apart from a real value."""
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        return _aggregate3_return(
            [
                (True, "0x" + _encode_uint(1354)),
                (True, "0x" + _encode_uint(1536)),
                (True, "0x" + _encode_uint(1)),
                (True, "0x" + _encode_uint(0)),
                (False, "0x"),
            ]
        )

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    flags = await client.fetch_collection_flags()
    assert flags["next_transform_id"] == 0
    await client.close()


# ---------------------------------------------------------------------------
# MEDI-27 / MEDI-28: transport failure is not "everything reverted"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collection_flags_raise_when_the_multicall_cannot_be_made(monkeypatch):
    """An outage must not read as a collection with 0 tokens in it.

    While ``_multicall`` swallowed this, ``fetch_collection_flags`` answered
    ``total_supply=0`` and the manager's cached-flags fallback was unreachable
    dead code: the dashboard showed 0 live tokens and ``forge_momentum_signal``
    turned the resulting drop into a green "CONSOLIDATING" that no market event
    had produced.
    """
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        raise RuntimeError("every endpoint exhausted")

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    with pytest.raises(RuntimeError):
        await client.fetch_collection_flags()
    await client.close()


@pytest.mark.asyncio
async def test_token_states_raise_when_a_chunk_cannot_be_fetched(monkeypatch):
    """MEDI-27: a truncated sweep is not a shrunken collection.

    ``TalismansManager`` rebuilds its whole registry from this dict, so a
    partial return would delete every token in the chunks that failed.
    """
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        raise RuntimeError("multicall endpoint down")

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    with pytest.raises(RuntimeError):
        await client.fetch_token_states([1, 2, 3])
    await client.close()


@pytest.mark.asyncio
async def test_a_multicall_reply_with_the_wrong_arity_is_a_transport_failure(
    monkeypatch,
):
    """A short ``Result[]`` cannot be mapped back onto the calls we made.

    The old ``_u(idx)`` guard turned every unmatched index into 0, so a
    truncated reply silently zeroed the tail of the batch.
    """
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        return _aggregate3_return([(True, "0x" + _encode_uint(1354))])

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    with pytest.raises(RuntimeError, match="well-formed aggregate3"):
        await client.fetch_collection_flags()
    await client.close()


@pytest.mark.asyncio
async def test_a_healthy_multicall_full_of_reverts_still_returns_zeros(monkeypatch):
    """The other half of the contract: a revert is an answer, not an outage."""
    client = TalismansClient()

    async def fake_rpc(method, params, endpoints=None):
        return _aggregate3_return([(False, "0x")] * 5)

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    flags = await client.fetch_collection_flags()
    assert flags["total_supply"] == 0
    assert flags["bond_cleave_enabled"] is False
    await client.close()


def test_default_log_page_size_is_sane():
    assert _LOG_RANGE_PER_CALL == 50_000


# ---------------------------------------------------------------------------
# HIGH-5: the HTTP status carries no information about which error it is
#
# Live, on one and the same over-long eth_getLogs range:
#   eth.drpc.org  HTTP 400 + range cap   <- the only SHRINKABLE one
#   publicnode    HTTP 403 + archive gate
#   1rpc.io/eth   HTTP 200 + range cap
# Classifying on status would demote the single most recoverable error to an
# opaque transport failure. A live drpc-only backfill is how that was caught.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shrinkable_error_inside_an_http_400_is_still_classified():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "id": 1,
                "jsonrpc": "2.0",
                "error": _LIVE_ERRORS["drpc_range_cap"][0],
            },
        )

    client = TalismansClient(
        primary_rpc="https://drpc.example",
        fallback_rpcs=[],
        http_client=_transport(handler),
    )
    with pytest.raises(TalismansRpcError) as excinfo:
        await client._rpc("eth_getLogs", [{}])
    assert excinfo.value.kind == "range_cap", "must not degrade to 'transport'"
    await client.close()


@pytest.mark.asyncio
async def test_archive_gate_inside_an_http_403_is_classified_from_the_body():
    """403 is in the dead-code set, but the body says precisely why."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": _LIVE_ERRORS["publicnode_archive_gate"][0],
            },
        )

    client = TalismansClient(
        primary_rpc="https://publicnode.example",
        fallback_rpcs=[],
        http_client=_transport(handler),
    )
    with pytest.raises(TalismansRpcError) as excinfo:
        await client._rpc("eth_getLogs", [{}])
    assert excinfo.value.kind == "archive"
    await client.close()


@pytest.mark.asyncio
async def test_http_400_range_cap_drives_a_real_shrink_to_completion(monkeypatch):
    """End-to-end of the live drpc case: 400 -> shrink -> full coverage."""
    monkeypatch.setattr(
        "maxpane_dashboard.data.talismans_client._BACKOFF_SECONDS", (0, 0)
    )
    served: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        params = _json.loads(request.content)["params"][0]
        lo, hi = int(params["fromBlock"], 16), int(params["toBlock"], 16)
        if hi - lo + 1 > 10_000:
            return httpx.Response(
                400,
                json={
                    "id": 1,
                    "jsonrpc": "2.0",
                    "error": _LIVE_ERRORS["drpc_range_cap"][0],
                },
            )
        served.append((lo, hi))
        return httpx.Response(200, json={"id": 1, "jsonrpc": "2.0", "result": []})

    client = TalismansClient(
        primary_rpc="https://drpc.example",
        fallback_rpcs=[],
        http_client=_transport(handler),
    )
    logs, scanned_to = await client._get_logs("0xa", [], 0, 59_999)
    assert scanned_to == 59_999, "a 10k-capped provider must still complete"
    assert logs == []
    assert served[0][0] == 0 and served[-1][1] == 59_999
    for prev, nxt in zip(served, served[1:]):
        assert nxt[0] == prev[1] + 1, "no gaps between accepted pages"
    await client.close()


@pytest.mark.asyncio
async def test_5xx_is_retried_before_failing_the_endpoint(monkeypatch):
    """A server blip deserves a backoff retry, whatever the body says."""
    monkeypatch.setattr(
        "maxpane_dashboard.data.talismans_client._BACKOFF_SECONDS", (0, 0)
    )
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(502, json={"error": {"code": -1, "message": "bad gw"}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x2a"})

    client = TalismansClient(
        primary_rpc="https://flaky.example",
        fallback_rpcs=[],
        http_client=_transport(handler),
    )
    assert await client._rpc("eth_call", [{}]) == "0x2a"
    assert hits["n"] == 2
    await client.close()


@pytest.mark.asyncio
async def test_non_json_body_does_not_crash_the_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(521, text="error code: 521")  # llamarpc, live

    client = TalismansClient(
        primary_rpc="https://down.example",
        fallback_rpcs=[],
        http_client=_transport(handler),
    )
    with pytest.raises(TalismansRpcError) as excinfo:
        await client._rpc("eth_call", [{}])
    assert excinfo.value.kind == "dead"
    await client.close()
