"""Tests for the keyless Talismans Ethereum-mainnet RPC client.

All tests run against canned JSON-RPC responses (monkeypatched ``_rpc`` or an
injected fake ``httpx.AsyncClient``) -- no real network.
"""

from __future__ import annotations

from typing import Any

import pytest

from maxpane_dashboard.data.talismans_client import (
    TalismansClient,
    _SEL_OWNER_OF,
    _SEL_TOKEN_DATA,
    _decode_bonded_log,
    _decode_cleaved_log,
    _decode_cut_log,
    _decode_merged_log,
    _decode_token_data,
    _decode_transfer_log,
    _encode_uint,
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

    async def fake_rpc(method, params):
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
        ]
    )

    async def fake_rpc(method, params):
        assert method == "eth_call"
        return blob

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    flags = await client.fetch_collection_flags()
    assert flags == {
        "total_supply": 1536,
        "genesis_minted": 1536,
        "bond_cleave_enabled": True,
        "cut_merge_enabled": False,
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

    async def fake_rpc(method, params):
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

    async def fake_rpc(method, params):
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

    async def fake_rpc(method, params):
        assert method == "eth_getLogs"
        # topics filter must be the 4-way OR
        topics = params[0]["topics"]
        assert isinstance(topics[0], list) and len(topics[0]) == 4
        return [bonded_log, cleaved_log]

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    ops = await client.fetch_operation_logs(100, 200)
    assert len(ops) == 2
    assert {o["op_type"] for o in ops} == {"bond", "cleave"}
    await client.close()


@pytest.mark.asyncio
async def test_fetch_operation_logs_paging(monkeypatch):
    """A >50k range must split into multiple eth_getLogs calls."""
    client = TalismansClient()
    calls: list[tuple[int, int]] = []

    async def fake_rpc(method, params):
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

    async def fake_rpc(method, params):
        assert method == "eth_getLogs"
        assert params[0]["topics"] == [
            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        ]
        return [transfer_log]

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    out = await client.fetch_transfer_logs(1, 100)
    assert len(out) == 1
    assert out[0]["token_id"] == 255
    assert out[0]["to"] == _OPERATOR
    await client.close()
