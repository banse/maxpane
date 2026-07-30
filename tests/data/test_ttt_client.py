"""Tests for the keyless TTT (Ten Thousand Tokens) Ethereum-mainnet client.

**Zero network.** Every test either exercises a pure function or drives the
client through an ``httpx.MockTransport``. Two doubles enforce it:

* :func:`_offline_client` — a client whose transport raises on *any* request,
  so a stray ``await`` that reaches the wire fails loudly instead of quietly
  dialling mainnet.
* :class:`SimChain` — a scripted mainnet that decodes the real ``aggregate3``
  calldata produced by the client's own encoder, dispatches each sub-call, and
  re-encodes a real ``Result[]``. Nothing is stubbed at the method level, so
  the encoder, the multicall chunking and the decoder are under test together.

Priority (HIGH-6): the decoders come first — an off-by-one word offset in
``_decode_aggregate3_result`` or ``_decode_string_dynamic`` returns *plausible
but wrong* numbers for every launched token, which nothing else would catch.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import ttt_client
from maxpane_dashboard.data.ttt_client import (
    _FACTORY,
    _FEESPLITTER,
    _MULTICALL3,
    _SEL_ACC_ETH_PER_SHARE,
    _SEL_ACTIVE_SHARES,
    _SEL_BURN_COUNT,
    _SEL_DECIMALS,
    _SEL_GET_ETH_BALANCE,
    _SEL_MAX_SUPPLY,
    _SEL_SYMBOL,
    _SEL_TOTAL_MINTED,
    _TOPIC_BOUGHT,
    _TOPIC_DEPOSITED,
    _TOPIC_LAUNCHED,
    TTTClient,
    _addr_from_topic,
    _addr_to_topic,
    _decode_address,
    _decode_aggregate3_result,
    _decode_bought_log,
    _decode_deposited_log,
    _decode_launched_log,
    _decode_log_index,
    _decode_string_dynamic,
    _decode_token_deployed_log,
    _decode_uint,
    _encode_address,
    _encode_aggregate3,
    _encode_uint,
    _parse_site_market_data,
    _safe_float,
    _strip0x,
)

WEI = 10**18


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the retry backoff and inter-call throttle so tests are instant."""
    monkeypatch.setattr(ttt_client, "_BACKOFF_SECONDS", (0.0, 0.0))
    monkeypatch.setattr(ttt_client, "_INTER_CALL_DELAY", 0.0)


# ---------------------------------------------------------------------------
# Transport doubles
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


def _offline_client() -> TTTClient:
    """A client that cannot reach the network — proves a test stayed offline."""
    return TTTClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, payload)`` it was handed."""

    def __init__(self, handler: Callable[[str, dict], httpx.Response]) -> None:
        self.requests: list[tuple[str, Any]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            try:
                payload = json.loads(request.content) if request.content else None
            except ValueError:
                payload = None
            self.requests.append((str(request.url), payload))
            return handler(str(request.url), payload)

        super().__init__(_wrapped)

    def calls(self, method: str) -> list[dict]:
        return [
            p
            for _u, p in self.requests
            if isinstance(p, dict) and p.get("method") == method
        ]


def _client_on(transport: httpx.MockTransport, **kw: Any) -> TTTClient:
    return TTTClient(http_client=httpx.AsyncClient(transport=transport), **kw)


def _ok(payload: dict, result: Any) -> httpx.Response:
    return httpx.Response(
        200, json={"jsonrpc": "2.0", "id": (payload or {}).get("id"), "result": result}
    )


# ---------------------------------------------------------------------------
# ABI helpers the harness needs (calldata decode / Result[] encode)
# ---------------------------------------------------------------------------


def decode_aggregate3_calldata(data: str) -> list[tuple[str, bool, str]]:
    """Inverse of ``_encode_aggregate3``: ``[(target, allowFailure, callData)]``."""
    raw = _strip0x(data)
    assert raw[:8] == "82ad56cb", f"not an aggregate3 payload: {raw[:8]}"
    body = raw[8:]
    arr_off = int(body[0:64], 16) * 2
    n = int(body[arr_off : arr_off + 64], 16)
    base = arr_off + 64
    out: list[tuple[str, bool, str]] = []
    for i in range(n):
        off = int(body[base + i * 64 : base + (i + 1) * 64], 16) * 2
        s = base + off
        target = "0x" + body[s + 24 : s + 64]
        allow = int(body[s + 64 : s + 128], 16) != 0
        cd_off = int(body[s + 128 : s + 192], 16) * 2
        cs = s + cd_off
        cd_len = int(body[cs : cs + 64], 16)
        out.append((target, allow, "0x" + body[cs + 64 : cs + 64 + cd_len * 2]))
    return out


def encode_aggregate3_result(
    results: list[tuple[bool, str]], *, array_offset: int = 0x20
) -> str:
    """Encode ``Result[] (bool success, bytes returnData)`` exactly as a node would.

    ``array_offset`` is settable so a test can prove the decoder follows the
    header word instead of assuming the conventional 0x20.
    """
    tuples: list[str] = []
    for success, data in results:
        raw = _strip0x(data)
        n_bytes = len(raw) // 2
        padded = raw + "0" * ((64 - (len(raw) % 64)) % 64)
        tuples.append(
            _encode_uint(1 if success else 0)
            + _encode_uint(0x40)
            + _encode_uint(n_bytes)
            + padded
        )
    offsets: list[int] = []
    cursor = len(tuples) * 32
    for t in tuples:
        offsets.append(cursor)
        cursor += len(t) // 2
    pad_words = (array_offset - 0x20) // 32
    return (
        "0x"
        + _encode_uint(array_offset)
        + "0" * 64 * pad_words
        + _encode_uint(len(tuples))
        + "".join(_encode_uint(o) for o in offsets)
        + "".join(tuples)
    )


def encode_string_return(text: str) -> str:
    """Encode a solidity ``returns (string)`` value."""
    body = text.encode("utf-8").hex()
    padded = body + "0" * ((64 - (len(body) % 64)) % 64)
    return "0x" + _encode_uint(0x20) + _encode_uint(len(text.encode("utf-8"))) + padded


# ---------------------------------------------------------------------------
# SimChain — a scripted mainnet
# ---------------------------------------------------------------------------


class SimChain:
    """Deterministic stand-in for mainnet at one block."""

    def __init__(
        self,
        *,
        block_number: int = 23_000_000,
        max_supply: int = 10_000,
        total_minted: int = 10_000,
        burn_count: int = 1_234,
        active_shares: int = 8_766,
        acc_eth_per_share: int = 7 * 10**26,
        balances: dict[str, int] | None = None,
        symbols: dict[str, str] | None = None,
        decimals: dict[str, int] | None = None,
        reverting: set[str] | None = None,
        balance_read_fails: set[str] | None = None,
        logs: list[dict] | None = None,
    ) -> None:
        self.block_number = block_number
        self.max_supply = max_supply
        self.total_minted = total_minted
        self.burn_count = burn_count
        self.active_shares = active_shares
        self.acc_eth_per_share = acc_eth_per_share
        self.balances = {k.lower(): v for k, v in (balances or {}).items()}
        self.symbols = {k.lower(): v for k, v in (symbols or {}).items()}
        self.decimals = {k.lower(): v for k, v in (decimals or {}).items()}
        self.reverting = {a.lower() for a in (reverting or set())}
        # Addresses whose Multicall3.getEthBalance sub-call comes back
        # ``(false, "0x")``. `reverting` can't express this: these calls target
        # Multicall3 itself, not the token.
        self.balance_read_fails = {a.lower() for a in (balance_read_fails or set())}
        self.logs = list(logs or [])
        self.log_queries: list[dict] = []

    # -- sub-call dispatch -------------------------------------------------

    def call(self, target: str, calldata: str) -> tuple[bool, str]:
        target = target.lower()
        sel = "0x" + _strip0x(calldata)[:8]
        arg = _strip0x(calldata)[8:]
        if target in self.reverting:
            return (False, "0x")
        if target == _FACTORY:
            if sel == _SEL_MAX_SUPPLY:
                return (True, "0x" + _encode_uint(self.max_supply))
            if sel == _SEL_TOTAL_MINTED:
                return (True, "0x" + _encode_uint(self.total_minted))
        if target == _FEESPLITTER:
            if sel == _SEL_BURN_COUNT:
                return (True, "0x" + _encode_uint(self.burn_count))
            if sel == _SEL_ACTIVE_SHARES:
                return (True, "0x" + _encode_uint(self.active_shares))
            if sel == _SEL_ACC_ETH_PER_SHARE:
                return (True, "0x" + _encode_uint(self.acc_eth_per_share))
        if target == _MULTICALL3.lower() and sel == _SEL_GET_ETH_BALANCE:
            who = "0x" + arg[24:64]
            if who in self.balance_read_fails:
                return (False, "0x")
            return (True, "0x" + _encode_uint(self.balances.get(who, 0)))
        if sel == _SEL_SYMBOL:
            sym = self.symbols.get(target)
            if sym is None:
                return (False, "0x")
            return (True, encode_string_return(sym))
        if sel == _SEL_DECIMALS:
            if target not in self.symbols and target not in self.decimals:
                return (False, "0x")
            return (True, "0x" + _encode_uint(self.decimals.get(target, 18)))
        return (False, "0x")

    # -- JSON-RPC dispatch -------------------------------------------------

    def rpc(self, payload: dict) -> Any:
        method = payload["method"]
        if method == "eth_blockNumber":
            return hex(self.block_number)
        if method == "eth_getBalance":
            return hex(self.balances.get(payload["params"][0].lower(), 0))
        if method == "eth_getLogs":
            params = payload["params"][0]
            self.log_queries.append(params)
            lo = int(params["fromBlock"], 16)
            hi = int(params["toBlock"], 16)
            return [
                log
                for log in self.logs
                if lo <= int(log["blockNumber"], 16) <= hi
                and _matches_address(log, params.get("address"))
                and _matches_topics(log, params.get("topics"))
            ]
        if method == "eth_call":
            call = payload["params"][0]
            data = call["data"]
            assert call["to"].lower() == _MULTICALL3.lower()
            sub = decode_aggregate3_calldata(data)
            return encode_aggregate3_result(
                [self.call(t, cd) for (t, _allow, cd) in sub]
            )
        raise AssertionError(f"SimChain got unexpected method {method}")

    def transport(self) -> RecordingTransport:
        return RecordingTransport(lambda _url, payload: _ok(payload, self.rpc(payload)))


def _matches_address(log: dict, address: Any) -> bool:
    if address is None:
        return True
    if isinstance(address, str):
        return log["address"].lower() == address.lower()
    return log["address"].lower() in {a.lower() for a in address}


def _matches_topics(log: dict, topics: Any) -> bool:
    if not topics:
        return True
    return log["topics"][0].lower() == str(topics[0]).lower()


# ---------------------------------------------------------------------------
# Fixture log builders (shapes match the live event ABIs)
# ---------------------------------------------------------------------------

_TOKEN_A = "0x" + "aa" * 20
_TOKEN_B = "0x" + "bb" * 20
_ACTOR = "0x" + "c0" * 20


def deposited_log(
    *,
    token: str = _TOKEN_A,
    sender: str = _ACTOR,
    total: int = 10 * WEI,
    shares: tuple[int, int, int, int] = (4 * WEI, 2 * WEI, 1 * WEI, 3 * WEI),
    block: int = 23_000_000,
    tx: str = "0x" + "11" * 32,
    log_index: int | None = 5,
) -> dict:
    launcher, tokenworks, punk, holder = shares
    log = {
        "address": _FEESPLITTER,
        "topics": [_TOPIC_DEPOSITED, _addr_to_topic(token), _addr_to_topic(sender)],
        "data": "0x"
        + _encode_uint(total)
        + _encode_uint(launcher)
        + _encode_uint(tokenworks)
        + _encode_uint(punk)
        + _encode_uint(holder),
        "blockNumber": hex(block),
        "transactionHash": tx,
    }
    if log_index is not None:
        log["logIndex"] = hex(log_index)
    return log


def launched_log(
    *,
    token_id: int = 4242,
    token: str = _TOKEN_A,
    launcher: str = _ACTOR,
    block: int = 23_000_000,
    tx: str = "0x" + "22" * 32,
    log_index: int | None = 3,
) -> dict:
    log = {
        "address": _FACTORY,
        "topics": [
            _TOPIC_LAUNCHED,
            "0x" + _encode_uint(token_id),
            _addr_to_topic(token),
            _addr_to_topic(launcher),
        ],
        "data": "0x",
        "blockNumber": hex(block),
        "transactionHash": tx,
    }
    if log_index is not None:
        log["logIndex"] = hex(log_index)
    return log


def bought_log(
    *,
    token: str = _TOKEN_A,
    caller: str = _ACTOR,
    eth_spent: int = WEI // 2,
    amount_bought: int = 999 * WEI,
    caller_reward: int = WEI // 100,
    block: int = 23_000_000,
    tx: str = "0x" + "33" * 32,
    log_index: int | None = 1,
) -> dict:
    log = {
        "address": token,
        "topics": [_TOPIC_BOUGHT, _addr_to_topic(caller)],
        "data": "0x"
        + _encode_uint(eth_spent)
        + _encode_uint(amount_bought)
        + _encode_uint(caller_reward),
        "blockNumber": hex(block),
        "transactionHash": tx,
    }
    if log_index is not None:
        log["logIndex"] = hex(log_index)
    return log


# ===========================================================================
# 1. Word-level primitives
# ===========================================================================


def test_decode_uint_indexes_by_word_not_by_byte():
    blob = "0x" + _encode_uint(1) + _encode_uint(2) + _encode_uint(3)
    assert [_decode_uint(blob, i) for i in range(3)] == [1, 2, 3]
    # Past the end is 0, not an exception and not a wrapped read.
    assert _decode_uint(blob, 3) == 0
    assert _decode_uint("0x") == 0


def test_decode_address_takes_the_low_20_bytes_of_its_word():
    blob = "0x" + _encode_uint(0) + _encode_address(_TOKEN_B)
    assert _decode_address(blob, 1) == _TOKEN_B
    assert _decode_address(blob, 0) == "0x" + "0" * 40
    assert _decode_address("0x", 0) == "0x" + "0" * 40


def test_topic_address_roundtrip():
    assert _addr_from_topic(_addr_to_topic(_TOKEN_A)) == _TOKEN_A
    # A topic with dirty high bytes still yields the low 20.
    dirty = "0x" + "ff" * 12 + _strip0x(_TOKEN_B)
    assert _addr_from_topic(dirty) == _TOKEN_B


def test_encode_uint_is_a_single_left_padded_word():
    assert len(_encode_uint(1)) == 64
    assert _encode_uint(0x1234).endswith("1234")
    assert _encode_uint(0) == "0" * 64


# ===========================================================================
# 2. _decode_string_dynamic  (symbol() decoding)
# ===========================================================================


def test_decode_string_dynamic_reads_the_offset_header():
    assert _decode_string_dynamic(encode_string_return("PEPE"), 0) == "PEPE"


def test_decode_string_dynamic_follows_a_non_standard_offset():
    """The offset word is authoritative — not an assumed 0x20.

    An implementation that hardcoded 'length is at word 1' would return
    garbage here, which is exactly the silent-wrongness class this guards.
    """
    body = "PEPE".encode().hex()
    blob = (
        "0x"
        + _encode_uint(0x40)  # data starts two words in, not one
        + _encode_uint(0xDEAD)  # filler the decoder must skip
        + _encode_uint(4)
        + body
        + "0" * (64 - len(body))
    )
    assert _decode_string_dynamic(blob, 0) == "PEPE"


def test_decode_string_dynamic_handles_multiword_and_empty_and_absurd_lengths():
    long_sym = "A" * 40  # spans two data words
    assert _decode_string_dynamic(encode_string_return(long_sym), 0) == long_sym
    assert _decode_string_dynamic(encode_string_return(""), 0) == ""
    assert _decode_string_dynamic("0x", 0) == ""
    # Length word claiming > 1024 bytes is refused rather than read.
    absurd = "0x" + _encode_uint(0x20) + _encode_uint(9999) + "00" * 32
    assert _decode_string_dynamic(absurd, 0) == ""


def test_decode_string_dynamic_survives_garbage_without_raising():
    # Truncated body, non-hex, and a wildly out-of-range offset.
    assert _decode_string_dynamic("0x" + _encode_uint(0x20) + _encode_uint(8), 0) == ""
    assert _decode_string_dynamic("0xzz", 0) == ""
    assert _decode_string_dynamic("0x" + _encode_uint(0xFFFF), 0) == ""


# ===========================================================================
# 3. aggregate3 encode / decode  (the highest-risk decoder)
# ===========================================================================


def test_encode_aggregate3_roundtrips_through_an_independent_decoder():
    calls = [
        (_FACTORY, _SEL_MAX_SUPPLY, True),
        (_FEESPLITTER, _SEL_BURN_COUNT, False),
        (_MULTICALL3, _SEL_GET_ETH_BALANCE + _encode_address(_TOKEN_A), True),
    ]
    decoded = decode_aggregate3_calldata(_encode_aggregate3(calls))
    assert [(t, a) for (t, a, _cd) in decoded] == [
        (_FACTORY, True),
        (_FEESPLITTER, False),
        (_MULTICALL3.lower(), True),
    ]
    assert decoded[0][2] == _SEL_MAX_SUPPLY
    assert decoded[2][2] == _SEL_GET_ETH_BALANCE + _encode_address(_TOKEN_A)


def test_encode_aggregate3_pads_odd_length_calldata_to_a_word_boundary():
    """A 36-byte getEthBalance payload must be tail-padded to 64 bytes."""
    cd = _SEL_GET_ETH_BALANCE + _encode_address(_TOKEN_A)  # 4 + 32 bytes
    raw = _strip0x(_encode_aggregate3([(_MULTICALL3, cd, True)]))
    assert len(raw[8:]) % 64 == 0
    assert decode_aggregate3_calldata("0x" + raw)[0][2] == cd


def test_decode_aggregate3_result_exact_layout():
    """Hand-built blob, byte-for-byte, with values a word shift would scramble."""
    blob = encode_aggregate3_result(
        [
            (True, "0x" + _encode_uint(10_000)),
            (False, "0x"),
            (True, "0x" + _encode_uint(3 * WEI)),
        ]
    )
    out = _decode_aggregate3_result(blob)
    assert [ok for ok, _ in out] == [True, False, True]
    assert _decode_uint(out[0][1]) == 10_000
    assert out[1][1] == "0x"
    assert _decode_uint(out[2][1]) == 3 * WEI


def test_decode_aggregate3_result_follows_a_shifted_array_offset():
    """The leading offset word is authoritative, not assumed to be 0x20."""
    blob = encode_aggregate3_result(
        [(True, "0x" + _encode_uint(42))], array_offset=0x40
    )
    out = _decode_aggregate3_result(blob)
    assert len(out) == 1 and _decode_uint(out[0][1]) == 42


def test_decode_aggregate3_result_preserves_multiword_returndata():
    """A two-word return must come back whole — not truncated to one word."""
    payload = "0x" + _encode_uint(7) + _encode_uint(9)
    out = _decode_aggregate3_result(encode_aggregate3_result([(True, payload)]))
    assert out[0][1] == payload
    assert (_decode_uint(out[0][1], 0), _decode_uint(out[0][1], 1)) == (7, 9)


def test_decode_aggregate3_result_on_empty_and_truncated_input():
    assert _decode_aggregate3_result("0x") == []
    assert _decode_aggregate3_result("") == []
    # A blob cut mid-array decodes to fewer entries or none, but never raises.
    full = _strip0x(encode_aggregate3_result([(True, "0x" + _encode_uint(1))] * 3))
    assert isinstance(_decode_aggregate3_result("0x" + full[: len(full) // 2]), list)


# ===========================================================================
# 4. Event-log decoders
# ===========================================================================


def test_decode_deposited_log_maps_every_share_to_its_own_word():
    """Field order is load-bearing: holderShare is word 4, not word 1 or 3."""
    log = deposited_log(shares=(4 * WEI, 2 * WEI, 1 * WEI, 3 * WEI), total=10 * WEI)
    d = _decode_deposited_log(log)
    assert d["token"] == _TOKEN_A
    assert d["sender"] == _ACTOR
    assert d["total"] == 10 * WEI
    assert d["launcher_share"] == 4 * WEI
    assert d["tokenworks_share"] == 2 * WEI
    assert d["punkstrategy_share"] == 1 * WEI
    assert d["holder_share"] == 3 * WEI
    assert d["block_number"] == 23_000_000
    assert d["log_index"] == 5
    assert d["tx_hash"] == "0x" + "11" * 32


def test_decode_deposited_log_rejects_a_log_missing_indexed_topics():
    log = deposited_log()
    log["topics"] = log["topics"][:2]
    assert _decode_deposited_log(log) is None


def test_decode_launched_log_reads_token_id_from_topic1():
    d = _decode_launched_log(launched_log(token_id=4242))
    assert d["token_id"] == 4242
    assert d["erc20_address"] == _TOKEN_A
    assert d["launcher"] == _ACTOR
    assert d["block_number"] == 23_000_000
    assert d["log_index"] == 3


def test_decode_launched_log_needs_all_three_indexed_topics():
    log = launched_log()
    log["topics"] = log["topics"][:3]
    assert _decode_launched_log(log) is None


def test_decode_token_deployed_log():
    log = launched_log(token_id=77, token=_TOKEN_B, launcher=_ACTOR)
    d = _decode_token_deployed_log(log)
    assert (d["token_id"], d["erc20_address"], d["holder"]) == (77, _TOKEN_B, _ACTOR)


def test_decode_bought_log_takes_the_token_from_the_emitting_address():
    """``Bought`` has no indexed token — it must come from ``log.address``."""
    d = _decode_bought_log(
        bought_log(token=_TOKEN_B, eth_spent=WEI // 2, caller_reward=WEI // 100)
    )
    assert d["token"] == _TOKEN_B
    assert d["caller"] == _ACTOR
    assert d["eth_spent"] == WEI // 2
    assert d["amount_bought"] == 999 * WEI
    assert d["caller_reward"] == WEI // 100
    assert d["log_index"] == 1


def test_decode_bought_log_without_caller_topic_is_none():
    log = bought_log()
    log["topics"] = [_TOPIC_BOUGHT]
    assert _decode_bought_log(log) is None


@pytest.mark.parametrize(
    "raw,expected",
    [("0x0", 0), ("0x1f", 31), (7, 7), (None, None), ("nonsense", None), ({}, None)],
)
def test_decode_log_index_accepts_hex_or_int_and_never_raises(raw, expected):
    log = {} if raw is None else {"logIndex": raw}
    assert _decode_log_index(log) == expected


def test_decoders_default_missing_block_and_hash_instead_of_raising():
    log = deposited_log()
    del log["blockNumber"]
    del log["transactionHash"]
    d = _decode_deposited_log(log)
    assert d["block_number"] == 0
    assert d["tx_hash"] == "0x"


# ===========================================================================
# 5. Client methods against SimChain (encoder + decoder end to end)
# ===========================================================================


async def test_fetch_factory_state_maps_each_call_to_its_own_key():
    """Five sub-calls, five distinct values — a shifted result index swaps them."""
    chain = SimChain(
        max_supply=10_000,
        total_minted=9_999,
        burn_count=1_234,
        active_shares=8_766,
        acc_eth_per_share=7 * 10**26,
    )
    async with _client_on(chain.transport()) as client:
        state = await client.fetch_factory_state()
    assert state == {
        "max_supply": 10_000,
        "total_minted": 9_999,
        "burn_count": 1_234,
        "active_shares": 8_766,
        "acc_eth_per_share": 7 * 10**26,
    }


async def test_fetch_factory_state_falls_back_to_10000_supply_when_call_reverts():
    chain = SimChain(reverting={_FACTORY})
    async with _client_on(chain.transport()) as client:
        state = await client.fetch_factory_state()
    assert state["max_supply"] == 10_000
    assert state["total_minted"] == 0
    assert state["burn_count"] == 1_234  # FeeSplitter still answered


async def test_fetch_factory_state_raises_when_the_whole_rpc_is_down():
    """MEDI-31: an outage is not a chain where nothing has ever burned.

    This used to return ``burn_count=0, active_shares=0`` — indistinguishable
    from a real reading — so the manager's ``except`` branch never ran,
    ``_error_count`` stayed 0, and the dashboard rendered '0/10,000 burned'
    with a fresh, error-free status bar.
    """
    def _boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    async with _client_on(httpx.MockTransport(_boom)) as client:
        with pytest.raises(RuntimeError):
            await client.fetch_factory_state()


async def test_a_reverting_read_inside_a_healthy_multicall_is_still_zero():
    """The other half of MEDI-31: a revert is a real answer, not an outage."""
    chain = SimChain(reverting={_FEESPLITTER})
    async with _client_on(chain.transport()) as client:
        state = await client.fetch_factory_state()
    assert state["total_minted"] == 10_000        # factory answered
    assert state["burn_count"] == 0               # FeeSplitter reverted
    assert state["active_shares"] == 0


async def test_a_multicall_reply_with_the_wrong_arity_is_a_transport_failure():
    """A truncated ``Result[]`` cannot be mapped back onto the calls we made."""
    def handler(_url: str, payload: dict) -> httpx.Response:
        # One Result for a five-call batch: silently dropping four reads would
        # zero four of the five factory fields.
        return _ok(payload, encode_aggregate3_result([(True, "0x" + _encode_uint(1))]))

    async with _client_on(RecordingTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="well-formed aggregate3"):
            await client.fetch_factory_state()


async def test_fetch_token_reservoirs_pairs_every_balance_with_its_own_address():
    """The regression HIGH-6 named: a word-shift here mis-prices every token."""
    balances = {_TOKEN_A: 3 * WEI, _TOKEN_B: 1, "0x" + "cc" * 20: 0}
    chain = SimChain(balances=balances)
    async with _client_on(chain.transport()) as client:
        out = await client.fetch_token_reservoirs(list(balances))
    assert out == {a.lower(): v for a, v in balances.items()}


async def test_fetch_token_reservoirs_reports_a_genuinely_empty_reservoir_as_zero():
    """Zero is a real, common reading — most fresh launches have one — which
    is exactly why a *failed* read must not also render as zero (LOW-15)."""
    chain = SimChain(balances={_TOKEN_A: 5 * WEI})
    async with _client_on(chain.transport()) as client:
        out = await client.fetch_token_reservoirs([_TOKEN_A, _TOKEN_B])
    assert out == {_TOKEN_A.lower(): 5 * WEI, _TOKEN_B.lower(): 0}


async def test_fetch_token_reservoirs_omits_addresses_whose_read_failed():
    """LOW-15: a failed sub-call used to be written out as 0 wei, which
    `update_token_reservoir` then wrote over the last known balance — the
    "Buybacks ready" signal collapsed to 0 for a cycle with nothing having
    changed on-chain. Omission lets the caller keep its cached value, matching
    `fetch_token_metadata`."""
    chain = SimChain(
        balances={_TOKEN_A: 5 * WEI, _TOKEN_B: 7 * WEI},
        balance_read_fails={_TOKEN_B},
    )
    async with _client_on(chain.transport()) as client:
        out = await client.fetch_token_reservoirs([_TOKEN_A, _TOKEN_B])
    assert out == {_TOKEN_A.lower(): 5 * WEI}
    assert _TOKEN_B.lower() not in out


async def test_a_failed_reservoir_read_does_not_shift_the_survivors():
    """The omission must drop the entry, not the slot: mispairing here
    mis-prices every token after the failure (the HIGH-6 class of bug)."""
    c_addr = "0x" + "cc" * 20
    chain = SimChain(
        balances={_TOKEN_A: 1 * WEI, _TOKEN_B: 2 * WEI, c_addr: 3 * WEI},
        balance_read_fails={_TOKEN_B},
    )
    async with _client_on(chain.transport()) as client:
        out = await client.fetch_token_reservoirs([_TOKEN_A, _TOKEN_B, c_addr])
    assert out == {_TOKEN_A.lower(): 1 * WEI, c_addr.lower(): 3 * WEI}


async def test_fetch_token_reservoirs_no_addresses_makes_no_request():
    client = _offline_client()
    assert await client.fetch_token_reservoirs([]) == {}
    await client.close()


async def test_fetch_token_metadata_keeps_symbol_and_decimals_aligned():
    """symbol/decimals are interleaved 2i / 2i+1 — an off-by-one mislabels tokens."""
    c_addr = "0x" + "cc" * 20
    chain = SimChain(
        symbols={_TOKEN_A: "AAA", _TOKEN_B: "BBB", c_addr: "CCC"},
        decimals={_TOKEN_A: 18, _TOKEN_B: 6, c_addr: 9},
    )
    async with _client_on(chain.transport()) as client:
        out = await client.fetch_token_metadata([_TOKEN_A, _TOKEN_B, c_addr])
    assert out == {
        _TOKEN_A.lower(): ("AAA", 18),
        _TOKEN_B.lower(): ("BBB", 6),
        c_addr.lower(): ("CCC", 9),
    }


async def test_fetch_token_metadata_skips_a_reverting_token_without_shifting_others():
    """The middle token reverts; the third must keep its own symbol."""
    c_addr = "0x" + "cc" * 20
    chain = SimChain(
        symbols={_TOKEN_A: "AAA", c_addr: "CCC"},
        decimals={_TOKEN_A: 18, c_addr: 9},
    )
    async with _client_on(chain.transport()) as client:
        out = await client.fetch_token_metadata([_TOKEN_A, _TOKEN_B, c_addr])
    assert out == {_TOKEN_A.lower(): ("AAA", 18), c_addr.lower(): ("CCC", 9)}


async def test_fetch_token_metadata_drops_tokens_with_an_empty_symbol():
    chain = SimChain(symbols={_TOKEN_A: ""}, decimals={_TOKEN_A: 18})
    async with _client_on(chain.transport()) as client:
        assert await client.fetch_token_metadata([_TOKEN_A]) == {}


async def test_fetch_block_number_and_its_failure_sentinel():
    chain = SimChain(block_number=23_456_789)
    async with _client_on(chain.transport()) as client:
        assert await client.fetch_block_number() == 23_456_789

    def _boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    async with _client_on(httpx.MockTransport(_boom)) as client:
        assert await client.fetch_block_number() == 0


# ===========================================================================
# 6. Log fetching + pagination
# ===========================================================================


async def test_fetch_deposit_events_filters_by_topic_and_decodes_each_log():
    chain = SimChain(
        logs=[
            deposited_log(block=23_000_001, tx="0x" + "a1" * 32, log_index=0),
            deposited_log(
                token=_TOKEN_B, block=23_000_002, tx="0x" + "a2" * 32, log_index=1
            ),
            bought_log(block=23_000_003),  # different topic, must not appear
        ]
    )
    async with _client_on(chain.transport()) as client:
        out, scanned_to = await client.fetch_deposit_events(23_000_000, 23_000_010)
    assert [d["token"] for d in out] == [_TOKEN_A, _TOKEN_B]
    assert [d["block_number"] for d in out] == [23_000_001, 23_000_002]
    assert scanned_to == 23_000_010


async def test_fetch_launched_events_decodes_from_the_factory_topic():
    chain = SimChain(logs=[launched_log(token_id=1), launched_log(token_id=2)])
    async with _client_on(chain.transport()) as client:
        out, scanned_to = await client.fetch_launched_events(22_999_999, 23_000_001)
    assert [d["token_id"] for d in out] == [1, 2]
    assert scanned_to == 23_000_001


async def test_fetch_buyback_events_queries_the_token_addresses():
    chain = SimChain(
        logs=[bought_log(token=_TOKEN_A), bought_log(token=_TOKEN_B, log_index=2)]
    )
    async with _client_on(chain.transport()) as client:
        out, _ = await client.fetch_buyback_events(
            [_TOKEN_A], 23_000_000, 23_000_000
        )
    assert [d["token"] for d in out] == [_TOKEN_A]
    assert chain.log_queries[0]["address"] == [_TOKEN_A]


async def test_fetch_buyback_events_with_no_tokens_makes_no_request():
    """Nothing to scan means the range is covered, not refused."""
    client = _offline_client()
    assert await client.fetch_buyback_events([], 1, 2) == ([], 2)
    await client.close()


async def test_get_logs_paginates_at_10k_blocks_and_covers_the_range_exactly():
    chain = SimChain(logs=[deposited_log(block=23_015_000)])
    async with _client_on(chain.transport()) as client:
        out, scanned_to = await client.fetch_deposit_events(23_000_000, 23_025_000)
    assert len(out) == 1
    assert scanned_to == 23_025_000
    windows = [
        (int(q["fromBlock"], 16), int(q["toBlock"], 16)) for q in chain.log_queries
    ]
    assert windows == [
        (23_000_000, 23_009_999),
        (23_010_000, 23_019_999),
        (23_020_000, 23_025_000),
    ]


async def test_get_logs_with_inverted_range_makes_no_request():
    client = _offline_client()
    assert await client.fetch_deposit_events(100, 99) == ([], 99)
    await client.close()


# ===========================================================================
# 7. RPC plumbing: retry, fallback, error classification
# ===========================================================================


async def test_rpc_falls_over_to_a_fallback_endpoint_after_a_5xx():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "primary" in str(request.url):
            return httpx.Response(503, json={})
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": hex(999)}
        )

    client = TTTClient(
        primary_rpc="https://primary.invalid",
        fallback_rpcs=["https://fallback.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 999
    assert any("fallback" in u for u in seen)
    await client.close()


async def test_rpc_skips_a_dead_endpoint_without_burning_its_retries():
    attempts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        attempts[host] = attempts.get(host, 0) + 1
        if host == "dead.invalid":
            return httpx.Response(403, json={})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1"})

    client = TTTClient(
        primary_rpc="https://dead.invalid",
        fallback_rpcs=["https://alive.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 1
    assert attempts["dead.invalid"] == 1  # 403 is terminal, not retried
    await client.close()


async def test_rpc_treats_a_malformed_request_error_as_terminal():
    """-32602 is our bug, not the endpoint's — don't shop it around."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602}}
        )

    client = TTTClient(
        primary_rpc="https://a.invalid",
        fallback_rpcs=["https://b.invalid", "https://c.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 0  # swallowed by the public wrapper
    assert len(calls) == 1
    await client.close()


async def test_rpc_shops_a_server_defined_error_to_the_next_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.invalid":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32046}}
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x2a"})

    client = TTTClient(
        primary_rpc="https://a.invalid",
        fallback_rpcs=["https://b.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 42
    await client.close()


async def test_multicall_raises_instead_of_reporting_zero_balances():
    """An unreachable node must not read as 'every reservoir is empty'."""
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    async with _client_on(httpx.MockTransport(_boom)) as client:
        with pytest.raises(RuntimeError):
            await client.fetch_token_reservoirs([_TOKEN_A, _TOKEN_B])


async def test_get_logs_stops_at_the_last_page_it_completed():
    """MEDI-29: a refused page ends the scan; it does not get skipped over.

    The old behaviour logged the failure at ``debug``, advanced the cursor and
    carried on, so the caller got a partial list that was indistinguishable
    from a sparse range — and then advanced its watermark past the gap.
    """
    chain = SimChain(
        logs=[deposited_log(block=23_005_000), deposited_log(block=23_015_000)]
    )
    real = chain.rpc
    seen = {"n": 0}

    def flaky(payload: dict) -> Any:
        if payload["method"] == "eth_getLogs":
            seen["n"] += 1
            if seen["n"] > 1:          # first page fine, second page dies
                raise httpx.ConnectError("page 2 died")
        return real(payload)

    def handler(_url: str, payload: dict) -> httpx.Response:
        return _ok(payload, flaky(payload))

    async with _client_on(RecordingTransport(handler)) as client:
        out, scanned_to = await client.fetch_deposit_events(
            23_000_000, 23_019_999
        )

    # Page 1 [23_000_000..23_009_999] landed; page 2 did not, and we say so.
    assert [d["block_number"] for d in out] == [23_005_000]
    assert scanned_to == 23_009_999
    assert scanned_to < 23_019_999


async def test_get_logs_reports_no_progress_when_the_first_page_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("all log endpoints down")

    async with _client_on(httpx.MockTransport(handler)) as client:
        out, scanned_to = await client.fetch_launched_events(
            23_000_000, 23_009_999
        )
    assert out == []
    assert scanned_to == 22_999_999, "from_block - 1 means 'nothing scanned'"


async def test_a_non_list_log_reply_ends_the_scan_rather_than_counting_as_empty():
    def handler(_url: str, payload: dict) -> httpx.Response:
        return _ok(payload, {"unexpected": "object"})

    async with _client_on(RecordingTransport(handler)) as client:
        out, scanned_to = await client.fetch_launched_events(100, 200)
    assert out == []
    assert scanned_to == 99


# ===========================================================================
# 8. HTTP sources: DexScreener, site scrape, Reservoir floor
# ===========================================================================


async def test_fetch_market_data_batches_at_30_addresses_per_request():
    addrs = ["0x" + f"{i:040x}" for i in range(65)]
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=[])

    async with _client_on(httpx.MockTransport(handler)) as client:
        await client.fetch_market_data(addrs)
    assert len(urls) == 3
    assert [u.rsplit("/", 1)[-1].count(",") + 1 for u in urls] == [30, 30, 5]


async def test_fetch_market_data_extracts_the_first_pair_per_base_token():
    pairs = [
        {
            "baseToken": {"address": _TOKEN_A.upper()},
            "priceUsd": "0.0042",
            "priceChange": {"h24": -12.5},
            "volume": {"h24": 91000.0},
            "marketCap": 420000.0,
        },
        {  # second pair for the same token: ignored
            "baseToken": {"address": _TOKEN_A},
            "priceUsd": "999",
            "priceChange": {"h24": 1},
            "volume": {"h24": 1},
            "marketCap": 1,
        },
        {  # fdv fallback when marketCap is absent
            "baseToken": {"address": _TOKEN_B},
            "priceUsd": "1.5",
            "priceChange": {},
            "volume": {},
            "fdv": 777.0,
        },
    ]

    async with _client_on(
        httpx.MockTransport(lambda r: httpx.Response(200, json=pairs))
    ) as client:
        out = await client.fetch_market_data([_TOKEN_A, _TOKEN_B])
    assert out[_TOKEN_A.lower()] == {
        "price_usd": 0.0042,
        "change_h24": -12.5,
        "volume_h24": 91000.0,
        "mcap": 420000.0,
    }
    assert out[_TOKEN_B.lower()]["mcap"] == 777.0
    assert out[_TOKEN_B.lower()]["change_h24"] == 0.0


async def test_fetch_market_data_returns_empty_on_persistent_failure():
    async with _client_on(
        httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    ) as client:
        assert await client.fetch_market_data([_TOKEN_A]) == {}


async def test_fetch_market_data_with_no_addresses_makes_no_request():
    client = _offline_client()
    assert await client.fetch_market_data([]) == {}
    await client.close()


def test_parse_site_market_data_unescapes_the_rsc_payload():
    token = (
        '{"id":7,"address":"' + _TOKEN_A + '","price":0.0031,'
        '"marketCap":31000,"volume24h":1200.5,'
        '"priceChangePercentByTimeframe":{"24h":-4.25},"refundable":false}'
    )
    html = '<script>self.__next_f.push([1,"' + token.replace('"', '\\"') + '"])</script>'
    out = _parse_site_market_data(html)
    assert out[_TOKEN_A] == {
        "price_usd": 0.0031,
        "change_h24": -4.25,
        "volume_h24": 1200.5,
        "mcap": 31000.0,
    }


def test_parse_site_market_data_normalises_string_and_missing_change_values():
    def entry(addr: str, change: str) -> str:
        return (
            '{"id":1,"address":"' + addr + '","price":1,"marketCap":2,'
            '"volume24h":3,"priceChangePercentByTimeframe":' + change +
            ',"refundable":true}'
        )

    html = (
        entry(_TOKEN_A, '{"24h":"$-0.5"}')
        + entry(_TOKEN_B, '"$11"')  # container ships as a bare string
        + entry("0x" + "cc" * 20, '{"24h":"n/a"}')
    )
    out = _parse_site_market_data(html)
    assert out[_TOKEN_A]["change_h24"] == -0.5
    assert out[_TOKEN_B]["change_h24"] is None
    assert out["0x" + "cc" * 20]["change_h24"] is None


def test_parse_site_market_data_on_html_without_tokens():
    assert _parse_site_market_data("<html><body>nothing here</body></html>") == {}


async def test_fetch_site_market_data_returns_empty_on_http_failure():
    async with _client_on(
        httpx.MockTransport(lambda r: httpx.Response(503, text=""))
    ) as client:
        assert await client.fetch_site_market_data() == {}


@pytest.mark.parametrize(
    "raw,expected",
    [(None, 0.0), ("1.5", 1.5), (2, 2.0), ("", 0.0), ("abc", 0.0), ({}, 0.0)],
)
def test_safe_float(raw, expected):
    assert _safe_float(raw) == expected


# ===========================================================================
# 9. Lifecycle
# ===========================================================================


async def test_client_does_not_close_an_injected_http_client():
    http = httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    client = TTTClient(http_client=http)
    await client.close()
    assert not http.is_closed
    await http.aclose()


async def test_client_closes_the_http_client_it_created(monkeypatch):
    client = TTTClient()
    await client.close()
    assert client._client.is_closed


# ===========================================================================
# 10. Endpoint configuration — the rot detector
# ===========================================================================
#
# The previous endpoint set died silently: cloudflare-eth.com (the primary),
# rpc.ankr.com and eth.llamarpc.com were all dead, and nothing in the suite
# noticed. These tests do NOT touch the network — they pin the configuration
# to a dated, probed record so a future reader can see when it was last
# verified, and so changing it without re-probing fails loudly.


def test_the_endpoint_set_matches_its_dated_probe_record():
    """Every configured host must carry a probe note; bump the date when editing."""
    from urllib.parse import urlparse

    from maxpane_dashboard.data.ttt_client import (
        _ENDPOINT_PROBE,
        _FALLBACK_RPCS,
        _LOG_RPCS,
        _PRIMARY_RPC,
        ENDPOINTS_VERIFIED_ON,
    )

    assert ENDPOINTS_VERIFIED_ON == "2026-07-28", (
        "endpoint lists changed? re-probe against mainnet and update the date"
    )
    for url in [_PRIMARY_RPC, *_FALLBACK_RPCS, *_LOG_RPCS]:
        host = urlparse(url).hostname
        assert host in _ENDPOINT_PROBE, (
            f"{host} is configured but has no entry in _ENDPOINT_PROBE — "
            "probe it live before shipping it"
        )


def test_the_configured_pools_are_exactly_the_probed_survivors():
    from maxpane_dashboard.data.ttt_client import (
        _FALLBACK_RPCS,
        _LOG_RPCS,
        _PRIMARY_RPC,
    )

    assert _PRIMARY_RPC == "https://ethereum-rpc.publicnode.com"
    assert _FALLBACK_RPCS == [
        "https://gateway.tenderly.co/public/mainnet",
        "https://eth.drpc.org",
        "https://1rpc.io/eth",
    ]
    # Pool B is log-capable only: publicnode 403s and 1rpc caps at 50 blocks.
    assert _LOG_RPCS == [
        "https://gateway.tenderly.co/public/mainnet",
        "https://eth.drpc.org",
    ]


def test_state_and_log_pools_are_distinct_because_batchers_refuse_logs():
    from maxpane_dashboard.data.ttt_client import _LOG_RPCS, _PRIMARY_RPC

    assert _PRIMARY_RPC not in _LOG_RPCS, (
        "the best state batcher refuses eth_getLogs — pools must not collapse"
    )


@pytest.mark.parametrize(
    "dead_url",
    [
        "https://cloudflare-eth.com",
        "https://rpc.ankr.com/eth",
        "https://eth.llamarpc.com",
        "https://api.reservoir.tools",
        "https://eth-mainnet.g.alchemy.com/v2/abc",
    ],
)
def test_configuring_a_dead_or_keyed_host_raises_at_construction(dead_url):
    """Fail loudly at construction rather than degrade to a zeroed dashboard."""
    with pytest.raises(ValueError, match="banned RPC host"):
        TTTClient(primary_rpc=dead_url)
    with pytest.raises(ValueError, match="banned RPC host"):
        TTTClient(fallback_rpcs=[dead_url])
    with pytest.raises(ValueError, match="banned RPC host"):
        TTTClient(log_rpcs=[dead_url])


def test_no_banned_host_is_in_the_default_configuration():
    from urllib.parse import urlparse

    from maxpane_dashboard.data.ttt_client import (
        _BANNED_RPC_HOSTS,
        _FALLBACK_RPCS,
        _LOG_RPCS,
        _PRIMARY_RPC,
    )

    configured = {
        urlparse(u).hostname for u in [_PRIMARY_RPC, *_FALLBACK_RPCS, *_LOG_RPCS]
    }
    assert configured.isdisjoint(_BANNED_RPC_HOSTS)


def test_the_default_client_constructs_without_touching_the_network():
    client = TTTClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    )
    assert client._log_rpcs and client._fallback_rpcs


# ===========================================================================
# 11. Error classification — message text, not code
# ===========================================================================


@pytest.mark.parametrize(
    "err,expect_fallover,why",
    [
        # Live-captured provider responses (see _ENDPOINT_PROBE).
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"},
         True, "1rpc range cap wears the malformed-input code"),
        ({"code": -32602, "message": "ranges over 10000 blocks are not supported "
                                     "on free plan"}, True, "drpc page cap"),
        ({"code": -32602, "message": "Archive requests require a personal token."},
         True, "publicnode archive gate"),
        ({"code": -32000, "message": "Unauthorized: You must authenticate your "
                                     "request with an API key."}, True, "ankr auth wall"),
        ({"code": -32046, "message": "Cannot fulfill request"}, True, "cloudflare"),
        ({"code": -32603, "message": "Internal error"}, True, "transient server error"),
        ({"code": -32602, "message": "block range extends beyond current head block"},
         True, "flashbots range complaint"),
        # Genuinely our bug, and free of capability language.
        ({"code": -32601, "message": "the method eth_foo does not exist"},
         False, "unknown method is terminal"),
        ({"code": -32700, "message": "parse error"}, False, "malformed JSON is terminal"),
        ({"code": -32600, "message": "invalid request"}, False, "terminal"),
        # Non-dict / unparseable errors: fall over rather than give up.
        ("a bare string error", True, "unstructured errors are not proof of our bug"),
        (None, True, "no structure at all"),
    ],
)
def test_endpoint_limitation_classification(err, expect_fallover, why):
    from maxpane_dashboard.data.ttt_client import _looks_like_endpoint_limitation

    assert _looks_like_endpoint_limitation(err) is expect_fallover, why


async def test_a_range_cap_on_one_endpoint_does_not_abort_the_chain():
    """The regression: -32602 used to be terminal, so 1rpc killed every call."""
    tried: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tried.append(request.url.host)
        if request.url.host == "capped.invalid":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "error": {
                    "code": -32602,
                    "message": "eth_getLogs is limited to 0 - 50 blocks range",
                }},
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": []})

    client = TTTClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        log_rpcs=["https://capped.invalid", "https://uncapped.invalid"],
    )
    out, scanned_to = await client.fetch_deposit_events(23_000_000, 23_000_100)
    assert out == []
    assert scanned_to == 23_000_100, "the healthy endpoint completed the range"
    assert "uncapped.invalid" in tried, "the healthy log endpoint was never tried"
    await client.close()


async def test_an_archive_gate_falls_over_to_the_next_log_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gated.invalid":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "error": {
                    "code": -32602,
                    "message": "Archive requests require a personal token.",
                }},
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": [launched_log(token_id=5)]},
        )

    client = TTTClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        log_rpcs=["https://gated.invalid", "https://archive.invalid"],
    )
    out, scanned_to = await client.fetch_launched_events(23_000_000, 23_000_010)
    assert [d["token_id"] for d in out] == [5]
    assert scanned_to == 23_000_010
    await client.close()


async def test_a_non_json_body_falls_over_instead_of_escaping():
    """HTTP 200 + an HTML challenge page used to kill the call outright."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.invalid":
            return httpx.Response(200, text="<html>Attention Required! | Cloudflare</html>")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x2a"})

    client = TTTClient(
        primary_rpc="https://html.invalid",
        fallback_rpcs=["https://healthy.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 42
    await client.close()


async def test_a_non_object_json_body_also_falls_over():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "weird.invalid":
            return httpx.Response(200, json=["not", "an", "object"])
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x7"})

    client = TTTClient(
        primary_rpc="https://weird.invalid",
        fallback_rpcs=["https://healthy.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 7
    await client.close()


# ===========================================================================
# 12. Pool routing
# ===========================================================================


async def test_log_reads_go_to_the_log_pool_and_state_reads_do_not():
    hosts: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        hosts.setdefault(payload["method"], []).append(request.url.host)
        result = [] if payload["method"] == "eth_getLogs" else "0x1"
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    client = TTTClient(
        primary_rpc="https://state.invalid",
        fallback_rpcs=[],
        log_rpcs=["https://logs.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await client.fetch_block_number()
    await client.fetch_deposit_events(23_000_000, 23_000_010)

    assert hosts["eth_blockNumber"] == ["state.invalid"]
    assert hosts["eth_getLogs"] == ["logs.invalid"]
    await client.close()


async def test_a_dead_state_pool_does_not_stop_log_reads():
    """The pools fail independently — that is the point of splitting them."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] != "eth_getLogs":
            return httpx.Response(503, json={})
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": [deposited_log()]}
        )

    client = TTTClient(
        primary_rpc="https://state.invalid",
        fallback_rpcs=[],
        log_rpcs=["https://logs.invalid"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_block_number() == 0        # state degraded
    logs, scanned_to = await client.fetch_deposit_events(1, 100)
    assert (len(logs), scanned_to) == (1, 100)   # logs still fine
    await client.close()


def test_the_reservoir_floor_fetcher_is_gone():
    """Its host no longer resolves; a call to it must not exist to be made."""
    from maxpane_dashboard.data import ttt_client as mod

    assert not hasattr(TTTClient, "fetch_nft_floor")
    assert not hasattr(mod, "_RESERVOIR_FLOOR_URL")
    # And it can never be configured back in by accident.
    assert "api.reservoir.tools" in mod._BANNED_RPC_HOSTS
    assert mod.TTTClient.FLOOR_SOURCE is None
    assert "Reservoir" in mod.FLOOR_UNAVAILABLE_REASON
