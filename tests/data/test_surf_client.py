"""Tests for maxpane_dashboard.data.surf_client.

**Zero network.** Every test drives the client through an ``httpx.MockTransport``.
There are TWO offline doubles and they are not interchangeable:

* ``_raising_client`` raises ``AssertionError`` on any request, so it proves a
  code path performed **no I/O at all**. It may only be used where nothing is
  fetched — ``MockTransport`` does not wrap handler exceptions, so that
  ``AssertionError`` propagates verbatim through httpx and is caught by none of
  the client's ``except (httpx.HTTPError, ValueError)`` / ``except RuntimeError``
  handlers.
* ``_offline_client`` raises ``httpx.ConnectError`` — a real transport failure
  the client already classifies — so it models a **total outage** and every
  ``fetch_*`` degrades to ``None`` through its normal retry/rotation path. Every
  ``*_outage_returns_none`` test uses this one.

``RecordingTransport`` captures every request so pool separation is asserted
structurally, not assumed. Fixtures are committed slices of real payloads
captured 2026-08-08 (see ``tests/fixtures/surf/client/``); expected values below
were derived by decoding those files, never typed from memory.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data import surf_client
from maxpane_dashboard.data.evm_abi import (
    encode_uint as _encode_uint,
    strip0x as _strip0x,
)
from maxpane_dashboard.data.surf_client import SurfClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "client"


def load_fixture(name: str) -> Any:
    with open(FIXTURES / name) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Transport doubles (mirrors tests/data/test_fwa_client.py)
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


def _raising_client(**kw: Any) -> SurfClient:
    """A client that must not be asked for anything — proves zero I/O.

    Use ONLY where the code path under test issues no request. An
    ``AssertionError`` raised inside a ``MockTransport`` handler is re-raised
    verbatim by httpx (verified against the installed 0.28.1: the transport does
    not wrap handler exceptions), and ``AssertionError`` is not an
    ``httpx.HTTPError``, a ``ValueError`` or a ``RuntimeError`` — so it sails
    straight through every ``except`` clause in ``SurfClient`` and out of the
    fetcher. For "the whole internet is down, return None", use
    ``_offline_client`` below.
    """
    return SurfClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _offline(request: httpx.Request) -> httpx.Response:
    """Fail at the socket, the way a real outage does."""
    raise httpx.ConnectError(
        f"test attempted real network access: {request.method} {request.url}",
        request=request,
    )


def _offline_client(**kw: Any) -> SurfClient:
    """A client whose every request fails at the transport layer.

    ``httpx.ConnectError`` IS an ``httpx.HTTPError``, so ``_rpc_state``,
    ``_rpc_state_batch``, ``_rpc_logs`` and ``_get_json`` all classify it,
    exhaust their retries, rotate through every endpoint and give up — which is
    exactly the total-outage path each ``fetch_*`` must degrade to ``None``
    through. This is the double for every ``*_outage_returns_none`` test.
    """
    return SurfClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_offline)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, method, payload_or_None)``."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[tuple[str, str, Any]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            payload = None
            if request.content:
                try:
                    payload = json.loads(request.content)
                except ValueError:
                    payload = None
            self.requests.append((str(request.url), request.method, payload))
            return handler(request)

        super().__init__(_wrapped)

    def urls(self) -> list[str]:
        return [u for (u, _m, _p) in self.requests]


def _client_on(transport: httpx.MockTransport, **kw: Any) -> SurfClient:
    return SurfClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _rpc_ok(payload: dict, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}


# ---------------------------------------------------------------------------
# WP1.1 — configuration and classification
# ---------------------------------------------------------------------------


def test_state_and_log_pools_are_disjoint_roles():
    client = _raising_client()
    assert client.state_endpoints[0] == "https://ethereum-rpc.publicnode.com"
    # publicnode refuses archive eth_getLogs (CLAUDE.md dead-endpoint table):
    # it must never appear in the logs pool.
    assert all("publicnode" not in u for u in client.log_endpoints)
    assert "https://gateway.tenderly.co/public/mainnet" in client.log_endpoints
    assert "https://eth.drpc.org" in client.log_endpoints


@pytest.mark.parametrize(
    "url",
    [
        "https://eth.llamarpc.com",       # HTTP 521, origin down
        "https://rpc.ankr.com/eth",       # now keyed
        "https://cloudflare-eth.com",     # -32046 on every call
        "https://api.reservoir.tools",    # sunset
        "https://mainnet.infura.io/v3/x", # keyed
    ],
)
def test_banned_host_rejected_at_construction(url):
    with pytest.raises(ValueError):
        SurfClient(state_rpc=url, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(_no_network)))
    with pytest.raises(ValueError):
        SurfClient(log_rpcs=[url], http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(_no_network)))


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        # 1rpc ships its 50-block log cap under -32602 — the *malformed* code.
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}, True),
        ({"code": -32005, "message": "query exceeds max block range"}, True),
        ({"code": -32000, "message": "Unauthorized: You must authenticate"}, True),
        ({"code": -32046, "message": "Cannot fulfill request"}, True),
        # A genuinely malformed request must NOT rotate — it fails the same way
        # on every endpoint and would burn the whole pool.
        ({"code": -32602, "message": "invalid argument 0: json: cannot unmarshal"}, False),
        ({"code": -32601, "message": "the method does not exist"}, False),
        # A non-dict error is unclassifiable: err toward rotation.
        ("boom", True),
    ],
)
def test_endpoint_limitation_classification_is_message_first(err, expected):
    assert surf_client._looks_like_endpoint_limitation(err) is expected


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        ({"code": -32602, "message": "eth_getLogs is limited to 0 - 50 blocks range"}, True),
        ({"code": -32005, "message": "block range is too large, try 25700000-25700001"}, True),
        ({"code": -32000, "message": "Unauthorized: You must authenticate"}, False),
        ({"code": -32602, "message": "invalid argument"}, False),
    ],
)
def test_range_limitation_is_a_narrower_class(err, expected):
    assert surf_client._is_range_limitation(err) is expected


@pytest.mark.asyncio
async def test_rpc_state_rotates_on_dead_status_and_error_body():
    """publicnode answers HTTP 403 → rotate; tenderly answers an error body →
    rotate; the third endpoint answers — the caller sees its result."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        payload = json.loads(request.content)
        if "publicnode" in url:
            return httpx.Response(403, json={})
        if "tenderly" in url:
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32000, "message": "capacity exceeded, upgrade plan"},
            })
        return httpx.Response(200, json=_rpc_ok(payload, "0x92e"))

    async with _client_on(RecordingTransport(handler)) as client:
        result = await client._rpc_state("eth_getTransactionCount",
                                         ["0x" + "11" * 20, "latest"])
    assert result == "0x92e"
    assert len({u.split("/")[2] for u in seen}) == 3  # three distinct hosts tried


@pytest.mark.asyncio
async def test_rpc_state_gives_up_after_all_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(521, json={})

    async with _client_on(RecordingTransport(handler)) as client:
        with pytest.raises(RuntimeError):
            await client._rpc_state("eth_blockNumber", [])


@pytest.mark.asyncio
async def test_close_does_not_close_injected_client():
    http = httpx.AsyncClient(transport=httpx.MockTransport(_no_network))
    client = SurfClient(http_client=http)
    await client.close()
    assert not http.is_closed  # injected clients belong to the caller
    await http.aclose()


# ---------------------------------------------------------------------------
# WP1.2 — fixture integrity
# ---------------------------------------------------------------------------


def test_client_fixtures_are_committed_and_shaped():
    announce = load_fixture("announce_txs_page1.json")
    assert set(announce) == {"items", "next_page_params"}
    assert len(announce["items"]) == 21          # the full channel, one page
    assert announce["next_page_params"] is None
    assert len(load_fixture("dev_txs_page1.json")["items"]) == 30
    assert len(load_fixture("ops_txs_page1.json")["items"]) == 50
    # The register() row is the one non-UTF-8 body — keep it in the slice.
    reg = [t for t in announce["items"]
           if t["hash"].startswith("0xa4ce159e")]
    assert len(reg) == 1 and reg[0]["raw_input"].startswith("0xf2c298be")
    # Markup-hostile message text survived the slice (em-dash post, nonce 8).
    hostile = [t for t in announce["items"] if t["nonce"] == 8
               and t["from"]["hash"] == t["to"]["hash"]]
    assert len(hostile) == 1


def test_the_transfer_slice_can_answer_a_24h_question():
    """The rate fixture must keep timestamps, and must stay small.

    Two independent failure modes: a projection that drops `timestamp` makes
    every row uncountable (the client would report 0 transfers/day, which
    looks like a quiet collection rather than a broken slice), and a slice
    that keeps `token_instance` drags 392 KB of base64 SVG per row into the
    suite.
    """
    page = load_fixture("idmd_transfers_page1.json")
    assert set(page) == {"items", "next_page_params"}
    rows = page["items"]
    assert len(rows) == 25 and all(r.get("timestamp") for r in rows)
    assert page["next_page_params"] is None
    assert all("token_instance" not in json.dumps(r) for r in rows)
    # Newest first, and the whole slice spans well under a day (10.8 h) — so
    # every row counts toward a 24 h window anchored just after the newest.
    stamps = [r["timestamp"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)


# ---------------------------------------------------------------------------
# WP1.2 — the model vocabulary this WP constructs against
# ---------------------------------------------------------------------------


#: Fields WP1 deliberately leaves at their WP0.4 default, with the reason.
#: Anything NOT listed here must actually be passed by this WP — see the
#: `declared - passed` assertion below.
WP1_LEAVES_DEFAULTED: dict[str, set[str]] = {
    # No keyless floor source exists for IDMD in v1 (WP0 open issue 2). The
    # field is pinned to None by WP0.4's own test so the widget can render the
    # explicit unavailable state; filling it would require a keyed API.
    "NftStats": {"floor_eth"},
}


def test_this_wp_constructs_against_wp0s_frozen_field_names():
    """A rename in WP0.4 must fail here, at collection, not at a live refresh.

    Every `fetch_*` below builds its model **by keyword**, so a field WP0 renames
    is a `TypeError` the first time that method runs — which in a client suite
    means the first time a transport double answers, and in production means the
    first refresh after deploy. This test drags that failure forward to import
    time and names the culprit, by asserting the kwargs this WP passes are
    exactly WP0.4's declared fields.

    It is deliberately assertive in **both** directions:

    * `passed - declared` catches WP1 inventing a field WP0 does not have (a
      `TypeError` at the first live refresh).
    * `required - passed` catches WP0 adding a mandatory field WP1 never fills
      (also a `TypeError`).
    * `declared - passed` catches the third and quietest case: WP0 declares a
      field **with a default** and names WP1 as its producer, and WP1 never
      passes it. Nothing raises, every suite stays green, and WP4 reads `None`
      forever. `ChainState.block_number` and `NonceSet.block_number` were
      exactly this — both are `int | None = None`, both are read by WP4's
      `_pool_chain`, and neither was in a constructor call. WP0's rule 1 says a
      field with no producer is a defect to *report*; this assertion is what
      makes it impossible to ship one by accident instead.

    The literal dicts below are deliberately duplicated from the `Consumes` lines
    rather than derived from the dataclasses: deriving them would make the test
    agree with any rename, which is the one thing it must not do.
    """
    import dataclasses

    from maxpane_dashboard.data import surf_models as m

    kwargs_this_wp_passes = {
        m.NonceSet: {"announce", "dev", "ops", "block_number"},
        m.ChainState: {
            "lp_liquidity", "lp_token0", "lp_token1", "lp_fee",
            "lp_tokens_owed0_wei", "lp_tokens_owed1_wei", "lp_owner",
            "lp_imd_wei", "lp_weth_wei",
            "identity_allowed", "imd_supply_wei", "sqrt_price_x96", "pool_tick",
            "imd_name", "imd_symbol", "block_number",
            "lp_state", "lp_position_count",
        },
        m.ChannelTx: {
            "tx_hash", "ts", "nonce", "from_addr", "to_addr", "value_wei",
            "input_hex", "method",
        },
        m.DevTx: {
            "tx_hash", "ts", "wallet_label", "from_addr", "to_addr",
            "counterparty", "counterparty_label", "value_wei", "method", "kind",
            "created_contract",
        },
        m.MarketSnapshot: {
            "imd_price_usd", "imd_price_usd_gecko", "imd_change_24h_pct",
            "imd_vol_24h_usd", "pool_liquidity_usd", "pool_imd", "pool_weth",
            "fp_price_usd", "fdv_usd", "eth_usd", "indexer_name",
            "indexer_symbol", "sources_agree",
        },
        m.LogWindow: {
            "from_block", "to_block", "bridge_mints", "identity_updates",
            "v4_initializes", "seaport_sales",
        },
        m.NftStats: {
            "holders", "total_supply", "transfers_total", "transfers_24h",
            "dev_holdings", "written",
        },
    }
    for model, passed in kwargs_this_wp_passes.items():
        declared = {f.name for f in dataclasses.fields(model)}
        unknown = passed - declared
        assert not unknown, f"{model.__name__}: WP1 passes {unknown}, WP0 has {declared}"
        required = {
            f.name for f in dataclasses.fields(model)
            if f.default is dataclasses.MISSING
        }
        assert not required - passed, (
            f"{model.__name__}: WP0 requires {required - passed}, WP1 never passes it"
        )
        unproduced = declared - passed - WP1_LEAVES_DEFAULTED.get(
            model.__name__, set()
        )
        assert not unproduced, (
            f"{model.__name__}: WP0 declares {unproduced} and names WP1 as the "
            "producer, but WP1 never passes it — it would be None forever with "
            "a green suite. Fill it, or ask WP0 to drop it and add it to "
            "WP1_LEAVES_DEFAULTED with the reason."
        )


# ---------------------------------------------------------------------------
# WP1.3 — fetch_nonces
# ---------------------------------------------------------------------------

#: The newest block any 2026-08-08 capture names (the Seaport purchase's block —
#: see the ground-truth table in this plan's header).  Used as the head the STATE
#: pool reports, so every expected value in this suite stays capture-derived.
#: WP1.9's logs pool has its own, deliberately different head (``LOG_HEAD_BLOCK``);
#: the two are never interchangeable and must never share a name — module globals
#: resolve at call time, so a second ``HEAD_BLOCK = …`` further down this file
#: would silently retune every assertion above it.
HEAD_BLOCK = 25_707_884
#: Derived, never pinned separately: two literals that must agree are two
#: literals that can disagree.
HEAD_BLOCK_HEX = hex(HEAD_BLOCK)  # "0x188456c"


def _nonce_handler(
    values: dict[str, str], block: str | None = HEAD_BLOCK_HEX
) -> Callable[[httpx.Request], httpx.Response]:
    """values maps lowercase address -> hex nonce; answers a JSON-RPC batch.

    ``block`` answers the fourth leg (``eth_blockNumber``); passing ``None``
    makes that one leg error while the three counts still succeed.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        assert isinstance(batch, list), "fetch_nonces must POST one batch array"
        out = []
        for entry in batch:
            if entry["method"] == "eth_blockNumber":
                assert entry["params"] == []
                if block is None:
                    out.append({"jsonrpc": "2.0", "id": entry["id"],
                                "error": {"code": -32005, "message": "rate limit"}})
                else:
                    out.append({"jsonrpc": "2.0", "id": entry["id"],
                                "result": block})
                continue
            assert entry["method"] == "eth_getTransactionCount"
            addr = entry["params"][0].lower()
            out.append({"jsonrpc": "2.0", "id": entry["id"],
                        "result": values[addr]})
        return httpx.Response(200, json=out)

    return handler


LIVE_NONCES = {
    A.ANNOUNCE.lower(): "0xe",     # 14 — channel account nonce 2026-08-08
    A.DEV_WALLET.lower(): "0x92e", # 2350
    A.OPS_WALLET.lower(): "0x26",  # 38
}


@pytest.mark.asyncio
async def test_fetch_nonces_one_batched_post_real_values():
    transport = RecordingTransport(_nonce_handler(dict(LIVE_NONCES)))
    async with _client_on(transport) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert nonces.announce == 14
    assert nonces.dev == 2350
    assert nonces.ops == 38
    # The height the three counts were read at — WP0.4's fourth NonceSet field,
    # which WP4's `_pool_chain` stores as the chain slot's `block`.  It rides
    # the SAME batch array, so it can never describe a different block from the
    # counts beside it.
    assert nonces.block_number == HEAD_BLOCK
    assert len(transport.requests) == 1  # ONE round trip for the fast tier


@pytest.mark.asyncio
async def test_fetch_nonces_pairs_by_id_when_responses_arrive_shuffled():
    """``fetch_nonces`` batches four calls into one POST and must pair each
    response back to its address by request ``id`` — not by its position in
    the response array. No existing test feeds the batch back out of order,
    so that pairing was correct by inspection only. A mis-pairing would
    attribute one wallet's nonce to another, which is worse than reading
    nothing: it produces a false detection instead of an honest gap.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        assert isinstance(batch, list)
        out = []
        for entry in batch:
            if entry["method"] == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": entry["id"],
                            "result": HEAD_BLOCK_HEX})
                continue
            addr = entry["params"][0].lower()
            out.append({"jsonrpc": "2.0", "id": entry["id"],
                        "result": LIVE_NONCES[addr]})
        # Same ids, SHUFFLED array positions — legal JSON-RPC batch behaviour
        # (nothing requires a server to answer in request order) and exactly
        # the case a position-based pairing bug would get wrong.
        shuffled = [out[2], out[0], out[3], out[1]]
        assert {e["id"] for e in shuffled} == {e["id"] for e in out}
        return httpx.Response(200, json=shuffled)

    async with _client_on(RecordingTransport(handler)) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert nonces.announce == 14
    assert nonces.dev == 2350
    assert nonces.ops == 38
    assert nonces.block_number == HEAD_BLOCK


@pytest.mark.asyncio
async def test_fetch_nonces_partial_batch_error_is_field_none_never_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        out = []
        for entry in batch:
            if entry["method"] == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": entry["id"],
                            "result": HEAD_BLOCK_HEX})
                continue
            addr = entry["params"][0].lower()
            if addr == A.DEV_WALLET.lower():
                out.append({"jsonrpc": "2.0", "id": entry["id"],
                            "error": {"code": -32005, "message": "rate limit"}})
            else:
                out.append({"jsonrpc": "2.0", "id": entry["id"], "result": "0xe"})
        return httpx.Response(200, json=out)

    async with _client_on(RecordingTransport(handler)) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert nonces.announce == 14
    assert nonces.dev is None      # failed read: None. 0 here would mean a
    assert nonces.dev != 0         # fresh EOA and reset every baseline.
    assert nonces.ops == 14
    assert nonces.block_number == HEAD_BLOCK  # the height leg is independent


@pytest.mark.asyncio
async def test_fetch_nonces_block_leg_failure_is_none_never_zero():
    """The height leg fails alone; the three counts still arrive.

    ``block_number`` has a default, so it is the one field on this model that a
    constructor can silently omit with every test green — which is exactly what
    happened before this test existed.  Two things are asserted: it is genuinely
    produced (the test above), and a *failed* read of it is ``None``.  ``0``
    would be genesis, and WP4 would render block 0 beside three live nonces.
    """
    handler = _nonce_handler(dict(LIVE_NONCES), block=None)
    async with _client_on(RecordingTransport(handler)) as client:
        nonces = await client.fetch_nonces()
    assert nonces is not None
    assert (nonces.announce, nonces.dev, nonces.ops) == (14, 2350, 38)
    assert nonces.block_number is None
    assert nonces.block_number != 0


@pytest.mark.asyncio
async def test_fetch_nonces_total_outage_returns_none():
    # _offline_client, not _raising_client: this path DOES issue a request, and
    # the outage has to arrive as a transport error the client classifies.
    async with _offline_client() as client:
        assert await client.fetch_nonces() is None


# ---------------------------------------------------------------------------
# WP1.4 — fetch_chain_state
# ---------------------------------------------------------------------------

# Copied idioms from tests/data/test_fwa_client.py (they are test-local there
# too; the shared codec is evm_abi, the harness helpers are per-suite).


def decode_aggregate3_calldata(data: str) -> list[tuple[str, bool, str]]:
    raw = _strip0x(data)
    assert raw[:8] == "82ad56cb", f"not an aggregate3 payload: {raw[:8]}"
    body = raw[8:]
    arr_off = int(body[0:64], 16) * 2
    n = int(body[arr_off:arr_off + 64], 16)
    base = arr_off + 64
    out: list[tuple[str, bool, str]] = []
    for i in range(n):
        off = int(body[base + i * 64: base + (i + 1) * 64], 16) * 2
        s = base + off
        target = "0x" + body[s + 24: s + 64]
        allow = int(body[s + 64: s + 128], 16) != 0
        cd_off = int(body[s + 128: s + 192], 16) * 2
        cs = s + cd_off
        cd_len = int(body[cs: cs + 64], 16)
        out.append((target, allow, "0x" + body[cs + 64: cs + 64 + cd_len * 2]))
    return out


def encode_aggregate3_result(results: list[tuple[bool, str]]) -> str:
    tuples = []
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
    offsets, cursor = [], len(tuples) * 32
    for t in tuples:
        offsets.append(cursor)
        cursor += len(t) // 2
    return ("0x" + _encode_uint(0x20) + _encode_uint(len(tuples))
            + "".join(_encode_uint(o) for o in offsets) + "".join(tuples))


def _word_addr(a: str) -> str:
    return _strip0x(a).lower().rjust(64, "0")


def _word_int(v: int) -> str:
    # evm_abi.encode_uint already two's-complements a negative into a full
    # word (evm_abi.py:183), which is exactly how a node returns int24 ticks.
    return _encode_uint(v)


LP_LIQUIDITY = 2_351_337_420_000_000_000_000   # realistic uint128 for the test
POOL_TICK = 79188                              # ≈ ln(2749.58)/ln(1.0001)
SQRT_PRICE_X96 = int((2749.578620645) ** 0.5 * 2**96)


def encode_positions_return(
    *,
    liquidity: int = LP_LIQUIDITY,
    tick_lower: int = -887200,
    tick_upper: int = 887200,
) -> str:
    """Flat 12-word positions(uint256) return; token0=WETH < token1=IMD.

    Defaults are the live position: full range at spacing 200, so the side
    amounts collapse to the closed form the first LP test asserts against.
    """
    words = [
        _word_int(0),                        # nonce
        _word_addr("0x" + "00" * 20),        # operator
        _word_addr(A.WETH),                  # token0
        _word_addr(A.IMD_TOKEN),             # token1
        _word_int(10000),                    # fee — the 1% tier
        _word_int(tick_lower),               # tickLower (signed int24)
        _word_int(tick_upper),               # tickUpper
        _word_int(liquidity),                # liquidity
        _word_int(0), _word_int(0),          # feeGrowthInside{0,1}
        _word_int(7_345_000_000_000_000_000),      # tokensOwed0
        _word_int(30_784_000_000_000_000_000_000), # tokensOwed1
    ]
    return "0x" + "".join(words)


def encode_slot0_return(*, tick: int = POOL_TICK) -> str:
    words = [
        _word_int(SQRT_PRICE_X96), _word_int(tick),
        _word_int(0), _word_int(1), _word_int(1), _word_int(0), _word_int(1),
    ]
    return "0x" + "".join(words)


def encode_string_return(s: str) -> str:
    b = s.encode()
    padded = b.hex() + "0" * ((64 - (len(b.hex()) % 64)) % 64)
    return "0x" + _encode_uint(0x20) + _encode_uint(len(b)) + padded


def _revert(reason: str) -> str:
    """ABI-encode a Solidity ``revert(reason)`` — ``Error(string)``.

    Selector ``0x08c379a0`` followed by the standard ``string`` ABI encoding
    (``encode_string_return`` already produces exactly that tail). Checked
    byte-for-byte against a real mainnet revert captured for
    ``positions(1167726)`` -> "Invalid token ID", the shape the position now
    reverts with since the 2026-08-17 migration burned it:

        0x08c379a0000...0020000...0010496e76616c696420746f6b656e2049440...0
    """
    return "0x08c379a0" + encode_string_return(reason)[2:]


IMD_SUPPLY_WEI = 2376731868679000000000000  # imd_token.json total_supply


def _chain_state_subcall(target: str, calldata: str) -> tuple[bool, str]:
    sel = "0x" + _strip0x(calldata)[:8]
    t = target.lower()
    if t == A.NFPM.lower() and sel == A.SEL_POSITIONS:
        arg = int(_strip0x(calldata)[8:72], 16)
        assert arg == A.LP_POSITION_ID  # 1167726 — the watched position
        return True, encode_positions_return()
    if t == A.NFPM.lower() and sel == A.SEL_OWNER_OF:
        arg = int(_strip0x(calldata)[8:72], 16)
        assert arg == A.LP_POSITION_ID
        return True, "0x" + _word_addr(A.OPS_WALLET)   # frenpet.eth holds it
    if t == A.IDENTITY_REGISTRY.lower() and sel == A.SEL_IDENTITY_ALLOWED:
        return True, "0x" + _encode_uint(0)  # gate CLOSED on 2026-08-08
    if t == A.IMD_TOKEN.lower() and sel == A.SEL_TOTAL_SUPPLY:
        return True, "0x" + _encode_uint(IMD_SUPPLY_WEI)
    if t == A.POOL_V3.lower() and sel == A.SEL_SLOT0:
        return True, encode_slot0_return()
    if t == A.IMD_TOKEN.lower() and sel == A.SEL_NAME:
        return True, encode_string_return("Identity.md")
    if t == A.IMD_TOKEN.lower() and sel == A.SEL_SYMBOL:
        return True, encode_string_return("IMD")
    if t == surf_client.MULTICALL3.lower() and sel == surf_client._SEL_GET_BLOCK_NUMBER:
        # Multicall3 answering about itself — the eighth leg, so the state and
        # the height it was read at are the same round trip.
        return True, "0x" + _encode_uint(HEAD_BLOCK)
    if t == A.POSITION_MANAGER_V4.lower() and sel == A.SEL_BALANCE_OF:
        # The ninth leg — PositionManager.balanceOf(OPS_WALLET). Verified
        # live: the ops wallet holds exactly one v4 position NFT.
        return True, "0x" + _encode_uint(1)
    return False, "0x"


def _chain_state_handler(
    subcall=_chain_state_subcall,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["method"] == "eth_call"
        call = payload["params"][0]
        assert call["to"].lower() == surf_client.MULTICALL3.lower()
        inner = decode_aggregate3_calldata(call["data"])
        result = encode_aggregate3_result(
            [subcall(t, cd) for (t, _allow, cd) in inner]
        )
        return httpx.Response(200, json=_rpc_ok(payload, result))

    return handler


@pytest.mark.asyncio
async def test_fetch_chain_state_one_multicall_real_values():
    transport = RecordingTransport(_chain_state_handler())
    async with _client_on(transport) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.lp_liquidity == LP_LIQUIDITY
    assert state.lp_token0 == A.WETH.lower()
    assert state.lp_token1 == A.IMD_TOKEN.lower()
    assert state.lp_fee == 10000
    assert state.lp_tokens_owed0_wei == 7_345_000_000_000_000_000
    assert state.lp_tokens_owed1_wei == 30_784_000_000_000_000_000_000
    assert state.lp_owner == A.OPS_WALLET.lower()
    assert state.identity_allowed is False        # closed, NOT None
    assert state.imd_supply_wei == IMD_SUPPLY_WEI
    assert state.sqrt_price_x96 == SQRT_PRICE_X96
    assert state.pool_tick == POOL_TICK
    assert state.imd_name == "Identity.md"
    assert state.imd_symbol == "IMD"
    assert state.block_number == HEAD_BLOCK       # the eighth sub-call
    assert len(transport.requests) == 1           # ONE eth_call round


@pytest.mark.asyncio
async def test_fetch_chain_state_derives_both_lp_side_amounts():
    """PRD §5 hero keys `lp_imd` / `lp_weth` — this is their only producer.

    The captured position is full range (tickLower/Upper = ∓887200), where the
    general v3 formula collapses to L/√P and L·√P; asserting against that
    closed form proves the general implementation is right *here* while the
    concentrated case below proves it is not a hardcoded shortcut.  Sides are
    mapped by ADDRESS (token0 == WETH), never by index: this pool happens to
    order WETH first, and the next one need not.
    """
    async with _client_on(RecordingTransport(_chain_state_handler())) as client:
        state = await client.fetch_chain_state()

    q96 = 1 << 96
    assert state.lp_weth_wei == pytest.approx(LP_LIQUIDITY * q96 / SQRT_PRICE_X96, rel=1e-9)
    assert state.lp_imd_wei == pytest.approx(LP_LIQUIDITY * SQRT_PRICE_X96 / q96, rel=1e-9)
    # And they are wei ints, not floats: the models are wei-native and WP4
    # divides exactly once (WP0.4 test_wei_fields_are_named_wei).
    assert isinstance(state.lp_imd_wei, int) and isinstance(state.lp_weth_wei, int)


@pytest.mark.asyncio
async def test_lp_side_amounts_use_the_real_range_not_the_full_range_shortcut():
    """The day signal 2 fires, the LP is re-added — very likely concentrated.

    A narrower range holds strictly less of both tokens for the same L, and a
    range entirely below spot is 100 % token1.  A full-range shortcut
    (L/√P, L·√P) passes the test above and fails both of these, which is why
    `_decode_positions` must keep `tick_lower` / `tick_upper`.
    """
    def narrow(target, calldata, *, lo, hi):
        sel = "0x" + _strip0x(calldata)[:8]
        if target.lower() == A.NFPM.lower() and sel == A.SEL_POSITIONS:
            return True, encode_positions_return(tick_lower=lo, tick_upper=hi)
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(
        lambda t, cd: narrow(t, cd, lo=78000, hi=80000)
    ))) as client:
        inside = await client.fetch_chain_state()

    q96 = 1 << 96
    assert 0 < inside.lp_weth_wei < LP_LIQUIDITY * q96 / SQRT_PRICE_X96
    assert 0 < inside.lp_imd_wei < LP_LIQUIDITY * SQRT_PRICE_X96 / q96

    # Range entirely BELOW spot (tick 79188): the position is all token1 = IMD.
    async with _client_on(RecordingTransport(_chain_state_handler(
        lambda t, cd: narrow(t, cd, lo=60000, hi=70000)
    ))) as client:
        below = await client.fetch_chain_state()
    assert below.lp_weth_wei == 0     # a REAL zero — the side holds nothing.
    assert below.lp_imd_wei > 0       # (None here would mean "read failed".)


@pytest.mark.asyncio
async def test_lp_side_amounts_are_none_when_any_input_is_missing():
    """No half-derivation.  With slot0 dead we have L but no √P, and an amount
    computed from a missing price is a number nobody can distinguish from a
    real one — the exact shape of the false-BURN bug in PRD §6 rule 1."""
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_SLOT0:
            return False, "0x"
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state.lp_liquidity == LP_LIQUIDITY   # the leg that worked
    assert state.sqrt_price_x96 is None
    assert state.lp_imd_wei is None and state.lp_weth_wei is None


@pytest.mark.asyncio
async def test_fetch_chain_state_uses_exactly_the_frozen_kwargs():
    """The contract freeze, asserted where it can actually bite.

    ``ChainState`` is constructed by keyword in one place; WP0.4 owns the names.
    Comparing against ``CONSTRUCTOR_KWARGS`` here turns a rename in either
    direction into a red test rather than a TypeError at the first live refresh
    — and, worse, a WP4 ``getattr(state, "lp_imd", None)`` that never raises.
    """
    import dataclasses

    from maxpane_dashboard.data.surf_models import ChainState as _CS
    from tests.data.test_surf_models import CONSTRUCTOR_KWARGS

    async with _client_on(RecordingTransport(_chain_state_handler())) as client:
        state = await client.fetch_chain_state()
    assert tuple(f.name for f in dataclasses.fields(_CS)) == CONSTRUCTOR_KWARGS[_CS]
    assert isinstance(state, _CS)


@pytest.mark.asyncio
async def test_fetch_chain_state_decodes_negative_tick_as_signed():
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_SLOT0:
            return True, encode_slot0_return(tick=-79188)
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state.pool_tick == -79188  # unsigned decode would give 2**256-79188


@pytest.mark.asyncio
async def test_fetch_chain_state_failed_subcall_is_field_none():
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_TOTAL_SUPPLY:
            return False, "0x"  # allowFailure miss — e.g. a reverted call
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.imd_supply_wei is None       # a 0 here is a 2.37M-token
    assert state.lp_liquidity == LP_LIQUIDITY  # false-BURN — PRD §6 rule 1
    # identityAllowed's real value IS false — prove failure did not leak in:
    assert state.identity_allowed is False


@pytest.mark.asyncio
async def test_fetch_chain_state_block_number_leg_is_none_when_it_fails():
    """`block_number` is the one ChainState field with a default, which is the
    only reason it needs a test of its own.

    A constructor that simply omits it type-checks, constructs, and passes
    WP1.2's `required - passed` check — and hands WP4's `_pool_chain` a chain
    slot whose `block` is `None` on every refresh forever. Here the eighth
    sub-call reverts, so the field is `None` **because the read failed**, and
    the other seven legs still land.
    """
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == surf_client._SEL_GET_BLOCK_NUMBER:
            return False, "0x"
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.block_number is None
    assert state.block_number != 0             # 0 would render as genesis
    assert state.lp_liquidity == LP_LIQUIDITY  # the round survived


@pytest.mark.asyncio
async def test_fetch_chain_state_failed_subcall_with_plausible_data_is_still_none():
    """A reverted sub-call whose return data still decodes to something
    plausible must still degrade to ``None`` — the ``success`` flag from
    ``aggregate3``'s ``Result[]`` is authoritative, never the shape of the
    bytes behind it.

    ``_chain_state_subcall``'s other failure simulations all use ``(False,
    "0x")`` — empty return data — so ``ok()``'s ``success and strip0x(ret)``
    check is never actually exercised by the ``success`` half: empty data
    already falls through the ``strip0x(ret)`` truthiness check on its own,
    so a decoder that dropped ``success and`` entirely would still pass
    every other test in this suite. This is the case that isolates it.

    ``identity_allowed`` is the worst-case field: the gate's real value
    today IS ``False``, so a decoder that ignores ``success`` and reads a
    failed call's leftover return data of ``true`` would render the OPEN
    state on screen — the exact false-positive PRD §6 rule 1 exists to rule
    out — while a run where the garbage happened to decode ``false`` would
    look correct by coincidence. Only checking ``success`` catches both.
    ``imd_supply_wei`` is the numeric sibling: a failed call whose return
    data decodes to a large non-zero number must not leak through as a real
    supply.
    """
    poisoned_supply = 999_999_000_000_000_000_000_000

    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if sel == A.SEL_IDENTITY_ALLOWED:
            # allowFailure miss, but the return data is NOT empty — it
            # decodes to `true`, the opposite of the gate's real state.
            return False, "0x" + _encode_uint(1)
        if sel == A.SEL_TOTAL_SUPPLY:
            # allowFailure miss, but the return data decodes to a plausible,
            # non-zero supply.
            return False, "0x" + _encode_uint(poisoned_supply)
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.identity_allowed is None       # NOT True, NOT False
    assert state.imd_supply_wei is None
    assert state.imd_supply_wei != poisoned_supply
    # Sibling fields that genuinely succeeded still decode normally — proof
    # the fix degrades only the failed legs, not the whole round.
    assert state.lp_liquidity == LP_LIQUIDITY
    assert state.pool_tick == POOL_TICK
    assert state.block_number == HEAD_BLOCK


@pytest.mark.asyncio
async def test_fetch_chain_state_total_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_chain_state() is None


# ---------------------------------------------------------------------------
# Task 4 — a revert is not a failed read: ChainState.lp_state / lp_position_count
#
# On 2026-08-17 the ops wallet withdrew and burned v3 position 1167726.
# `positions()`/`ownerOf()` now revert `Invalid token ID` /
# `ERC721: owner query for nonexistent token`. Under aggregate3 with
# allowFailure=True, that revert comes back as success=False on the sub-call
# -- a *result*, not an absence -- so it must decode to `lp_state == "gone"`,
# never the same `None` a transport outage produces.
# ---------------------------------------------------------------------------


def test_a_revert_is_gone_not_unknown() -> None:
    """positions(1167726) reverts `Invalid token ID`: the contract answered.

    Collapsing that into None renders a completed, announced migration as a
    failed RPC call -- the exact "we looked and there was nothing" versus "we
    could not look" confusion the conventions forbid.
    """
    state = surf_client._lp_state(
        positions_result=(False, _revert("Invalid token ID")),
        owner_result=(False, _revert("ERC721: owner query for nonexistent token")),
    )
    assert state == "gone"


def test_a_transport_failure_is_still_unknown() -> None:
    """No answer at all stays None -- only a revert is evidence."""
    assert surf_client._lp_state(None, None) is None


def test_a_live_position_is_live() -> None:
    state = surf_client._lp_state(
        positions_result=(True, encode_positions_return(liquidity=123)),
        owner_result=(True, "0x" + _word_addr(A.OPS_WALLET)),
    )
    assert state == "live"


@pytest.mark.asyncio
async def test_fetch_chain_state_a_burned_position_reads_gone_end_to_end():
    """Integration: the actual 2026-08-17 migration shape, through the real
    nine-call multicall round, not just the isolated classifier.

    Both `positions()` and `ownerOf()` revert with a reason. `lp_state` reads
    "gone" and every field that depended on decoding the (nonexistent)
    position data -- liquidity, owner, the derived LP sides -- stays `None`,
    because a revert is evidence about *existence*, not a license to decode
    garbage return data.
    """
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if target.lower() == A.NFPM.lower() and sel == A.SEL_POSITIONS:
            return False, _revert("Invalid token ID")
        if target.lower() == A.NFPM.lower() and sel == A.SEL_OWNER_OF:
            return False, _revert("ERC721: owner query for nonexistent token")
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.lp_state == "gone"
    assert state.lp_liquidity is None
    assert state.lp_owner is None
    assert state.lp_imd_wei is None and state.lp_weth_wei is None
    # Sibling legs that genuinely succeeded still decode normally -- the
    # revert degrades only the two LP-position legs, not the whole round.
    assert state.imd_supply_wei == IMD_SUPPLY_WEI
    assert state.block_number == HEAD_BLOCK


@pytest.mark.asyncio
async def test_fetch_chain_state_live_position_reports_lp_state_live():
    async with _client_on(RecordingTransport(_chain_state_handler())) as client:
        state = await client.fetch_chain_state()
    assert state.lp_state == "live"
    assert state.lp_liquidity == LP_LIQUIDITY


@pytest.mark.asyncio
async def test_fetch_chain_state_reads_v4_position_count():
    """PositionManager.balanceOf(OPS_WALLET) -- verified live: exactly 1."""
    async with _client_on(RecordingTransport(_chain_state_handler())) as client:
        state = await client.fetch_chain_state()
    assert state.lp_position_count == 1


@pytest.mark.asyncio
async def test_fetch_chain_state_lp_position_count_zero_is_representable():
    """0 means "ops holds no v4 position" -- real, and distinct from a failed
    read, per the house rule: a failed read is None, never 0."""
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if target.lower() == A.POSITION_MANAGER_V4.lower() and sel == A.SEL_BALANCE_OF:
            return True, "0x" + _encode_uint(0)
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state.lp_position_count == 0
    assert state.lp_position_count is not None


@pytest.mark.asyncio
async def test_fetch_chain_state_lp_position_count_is_none_on_failed_read():
    def subcall(target, calldata):
        sel = "0x" + _strip0x(calldata)[:8]
        if target.lower() == A.POSITION_MANAGER_V4.lower() and sel == A.SEL_BALANCE_OF:
            return False, "0x"
        return _chain_state_subcall(target, calldata)

    async with _client_on(RecordingTransport(_chain_state_handler(subcall))) as client:
        state = await client.fetch_chain_state()
    assert state is not None
    assert state.lp_position_count is None
    assert state.lp_state == "live"  # sibling leg unaffected


@pytest.mark.asyncio
async def test_fetch_chain_state_v4_balance_call_targets_ops_wallet():
    """The balanceOf argument is the ops wallet, not the dev wallet or some
    other address -- a wrong argument would silently read someone else's v4
    position count and render it as this dashboard's own."""
    transport = RecordingTransport(_chain_state_handler())
    async with _client_on(transport) as client:
        await client.fetch_chain_state()
    _url, _method, payload = transport.requests[0]
    calldata = payload["params"][0]["data"]
    inner = decode_aggregate3_calldata(calldata)
    balance_calls = [
        cd for (t, _allow, cd) in inner
        if t.lower() == A.POSITION_MANAGER_V4.lower()
    ]
    assert len(balance_calls) == 1
    assert balance_calls[0] == A.SEL_BALANCE_OF + _word_addr(A.OPS_WALLET)


# ---------------------------------------------------------------------------
# Task 3 — fetch_pool_v4 (v4 pool state via extsload)
# ---------------------------------------------------------------------------

from maxpane_dashboard.data import surf_v4  # noqa: E402

FIXTURE_V4 = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "surf" / "v4" / "v4_pool_state.json")
    .read_text()
)


def _pool_v4_handler(
    *,
    pool_id: str,
    hook_result: tuple[bool, str] | None,
    slot0_result: tuple[bool, str],
    liquidity_result: tuple[bool, str],
) -> Callable[[httpx.Request], httpx.Response]:
    """Answers the two sequential ``eth_call`` rounds ``fetch_pool_v4`` issues.

    Round 1 is a single-call ``aggregate3`` against
    ``LaunchpadHook.imdEthPoolId()``. Round 2 is a two-call ``aggregate3``
    against ``PoolManager.extsload()``, whose slot arguments are asserted
    against *pool_id* — this is what proves the client recomputed the slot
    from whichever pool id round 1 actually produced, rather than a stale or
    hardcoded pool id leaking into the second round.
    """
    expected_slot0, expected_liq = surf_v4.pool_state_slots(
        pool_id, A.V4_POOLS_MAPPING_SLOT
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["method"] == "eth_call"
        call = payload["params"][0]
        assert call["to"].lower() == surf_client.MULTICALL3.lower()
        inner = decode_aggregate3_calldata(call["data"])
        if len(inner) == 1:
            target, _allow, cd = inner[0]
            assert target.lower() == A.LAUNCHPAD_HOOK.lower()
            assert cd.lower() == A.SEL_IMD_ETH_POOL_ID.lower()
            result = encode_aggregate3_result(
                [hook_result if hook_result is not None else (False, "0x")]
            )
        else:
            assert len(inner) == 2
            for (target, _allow, cd), expected_slot in zip(
                inner, (expected_slot0, expected_liq)
            ):
                assert target.lower() == A.POOL_MANAGER_V4.lower()
                expected_cd = A.SEL_EXTSLOAD + _strip0x(expected_slot)
                assert cd.lower() == expected_cd.lower()
            result = encode_aggregate3_result([slot0_result, liquidity_result])
        return httpx.Response(200, json=_rpc_ok(payload, result))

    return handler


@pytest.mark.asyncio
async def test_fetch_pool_v4_prefers_the_hook_id() -> None:
    """The live id comes from the hook; the constant is only a fallback."""
    hook_id = "0x" + "ab" * 32
    handler = _pool_v4_handler(
        pool_id=hook_id,
        hook_result=(True, hook_id),
        slot0_result=(True, FIXTURE_V4["slot0_word"]),
        liquidity_result=(True, FIXTURE_V4["liquidity_word"]),
    )
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_pool_v4()
    assert state.pool_id == hook_id
    assert state.pool_id_source == "hook"
    assert state.sqrt_price_x96 == FIXTURE_V4["expected"]["sqrt_price_x96"]
    assert state.tick == FIXTURE_V4["expected"]["tick"]
    assert state.lp_fee == FIXTURE_V4["expected"]["lp_fee"]
    assert state.liquidity == FIXTURE_V4["expected"]["liquidity"]


@pytest.mark.asyncio
async def test_fetch_pool_v4_falls_back_and_says_so() -> None:
    """A failed hook read must not silently pretend the constant is live."""
    handler = _pool_v4_handler(
        pool_id=A.POOL_V4_ID_FALLBACK,
        hook_result=(False, "0x"),
        slot0_result=(True, FIXTURE_V4["slot0_word"]),
        liquidity_result=(True, FIXTURE_V4["liquidity_word"]),
    )
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_pool_v4()
    assert state.pool_id == A.POOL_V4_ID_FALLBACK
    assert state.pool_id_source == "fallback"
    assert state.liquidity == FIXTURE_V4["expected"]["liquidity"]


@pytest.mark.asyncio
async def test_fetch_pool_v4_hook_returning_empty_data_also_falls_back() -> None:
    """``allowFailure`` success with empty return data is not a real pool id.

    A ``(True, "0x")`` leg is what a bare EOA or an un-set storage slot can
    look like — success flag set, nothing behind it. Treating that as a live
    id would point the panel at ``bytes32(0)``, not fall back honestly.
    """
    handler = _pool_v4_handler(
        pool_id=A.POOL_V4_ID_FALLBACK,
        hook_result=(True, "0x"),
        slot0_result=(True, FIXTURE_V4["slot0_word"]),
        liquidity_result=(True, FIXTURE_V4["liquidity_word"]),
    )
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_pool_v4()
    assert state.pool_id == A.POOL_V4_ID_FALLBACK
    assert state.pool_id_source == "fallback"


@pytest.mark.asyncio
async def test_fetch_pool_v4_negative_tick_decodes_as_signed_through_the_client() -> None:
    """The signed-int24 hazard, exercised through the real client path too —
    not just the pure ``surf_v4`` unit test."""
    word = "0x" + ("000000" + "ffffff" + "0" * 40).rjust(64, "0")
    handler = _pool_v4_handler(
        pool_id=A.POOL_V4_ID_FALLBACK,
        hook_result=(False, "0x"),
        slot0_result=(True, word),
        liquidity_result=(True, FIXTURE_V4["liquidity_word"]),
    )
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_pool_v4()
    assert state.tick == -1
    assert state.tick != 16_777_215


@pytest.mark.asyncio
async def test_fetch_pool_v4_one_reverted_extsload_leg_degrades_only_that_field() -> None:
    """Every sub-call keeps allowFailure=True: a reverted liquidity slot must
    not blank out the price the sibling slot0 leg already decoded."""
    handler = _pool_v4_handler(
        pool_id=A.POOL_V4_ID_FALLBACK,
        hook_result=(False, "0x"),
        slot0_result=(True, FIXTURE_V4["slot0_word"]),
        liquidity_result=(False, "0x"),
    )
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_pool_v4()
    assert state.sqrt_price_x96 == FIXTURE_V4["expected"]["sqrt_price_x96"]
    assert state.tick == FIXTURE_V4["expected"]["tick"]
    assert state.lp_fee == FIXTURE_V4["expected"]["lp_fee"]
    assert state.liquidity is None


@pytest.mark.asyncio
async def test_fetch_pool_v4_is_exactly_two_state_pool_round_trips() -> None:
    handler = _pool_v4_handler(
        pool_id=A.POOL_V4_ID_FALLBACK,
        hook_result=(False, "0x"),
        slot0_result=(True, FIXTURE_V4["slot0_word"]),
        liquidity_result=(True, FIXTURE_V4["liquidity_word"]),
    )
    transport = RecordingTransport(handler)
    async with _client_on(transport) as client:
        await client.fetch_pool_v4()
    assert len(transport.requests) == 2
    assert all("publicnode" in u for u in transport.urls())


@pytest.mark.asyncio
async def test_fetch_pool_v4_total_outage_still_returns_a_labelled_state() -> None:
    """Unlike every other fetcher, total outage is NOT ``None``: the pool is
    real, so the honest degraded state is a fully-``None``-fielded
    ``PoolV4State`` whose ``pool_id_source`` truthfully says "fallback"."""
    async with _offline_client() as client:
        state = await client.fetch_pool_v4()
    assert state is not None
    assert state.pool_id == A.POOL_V4_ID_FALLBACK
    assert state.pool_id_source == "fallback"
    assert state.sqrt_price_x96 is None
    assert state.tick is None
    assert state.lp_fee is None
    assert state.liquidity is None


# ---------------------------------------------------------------------------
# WP1.5 — fetch_channel_txs
# ---------------------------------------------------------------------------


def _blockscout_handler(
    pages: dict[str, list[dict]],
) -> Callable[[httpx.Request], httpx.Response]:
    """Maps '/addresses/{addr}/transactions' path fragments to page lists.

    Each page list is served in order: first GET gets pages[addr][0], the
    second (with next_page_params echoed as query args) pages[addr][1], etc.
    """
    served: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for addr, plist in pages.items():
            if f"/addresses/{addr}" in path and path.endswith("/transactions"):
                i = served.get(addr, 0)
                served[addr] = i + 1
                return httpx.Response(200, json=plist[min(i, len(plist) - 1)])
        raise AssertionError(f"unexpected Blockscout path: {path}")

    return handler


@pytest.mark.asyncio
async def test_fetch_channel_txs_parses_the_full_page():
    fixture = load_fixture("announce_txs_page1.json")
    handler = _blockscout_handler({A.ANNOUNCE: [fixture]})
    async with _client_on(RecordingTransport(handler)) as client:
        txs = await client.fetch_channel_txs()
    assert txs is not None and len(txs) == 21

    # Newest self-post: nonce 13, the 33-ETH LP announcement (2026-08-07).
    head = txs[0]
    assert head.nonce == 13
    assert head.from_addr == A.ANNOUNCE.lower()
    assert head.to_addr == A.ANNOUNCE.lower()
    assert head.ts == 1786076831.0  # 2026-08-07T04:27:11Z
    assert head.tx_hash.startswith("0xe397869a")
    assert head.input_hex.startswith("0x49206d6f766564")  # "I moved" — raw,
    # undecoded: UTF-8 decoding is analytics/surf_signals.py's job (WP2).

    # The register() action: to = ERC-8004 registry, method preserved.
    reg = [t for t in txs if t.tx_hash.startswith("0xa4ce159e")][0]
    assert reg.from_addr == A.ANNOUNCE.lower()
    assert reg.to_addr == A.ERC8004_REGISTRY.lower()
    assert reg.method == "register"
    assert reg.input_hex.startswith("0xf2c298be")

    # The funding tx: from the dev wallet, 0.054 ETH, empty calldata.
    fund = [t for t in txs if t.tx_hash.startswith("0x632f5dc3")][0]
    assert fund.from_addr == A.DEV_WALLET.lower()
    assert fund.value_wei == 54_000_000_000_000_000
    assert fund.input_hex == "0x"

    # A community reply keeps its own sender (permissionless channel).
    pasta = [t for t in txs if t.tx_hash.startswith("0xdcb8bf92")][0]
    assert pasta.from_addr == "0x1c3a0ad54418fe843953c71df23637de732ce159"
    assert pasta.to_addr == A.ANNOUNCE.lower()


@pytest.mark.asyncio
async def test_fetch_channel_txs_follows_next_page_params_once_per_page():
    fixture = load_fixture("announce_txs_page1.json")
    nxt = {"block_number": 25108773, "index": 224, "items_count": 50}
    page1 = {"items": fixture["items"][:11], "next_page_params": nxt}
    page2 = {"items": fixture["items"][11:], "next_page_params": None}
    transport = RecordingTransport(_blockscout_handler({A.ANNOUNCE: [page1, page2]}))
    async with _client_on(transport) as client:
        txs = await client.fetch_channel_txs()
    assert len(txs) == 21
    assert len(transport.requests) == 2
    # The second GET must carry the server's cursor verbatim as query params.
    second_url = transport.urls()[1]
    assert "block_number=25108773" in second_url and "index=224" in second_url


@pytest.mark.asyncio
async def test_fetch_channel_txs_page_growth_is_bounded():
    """A server that always hands back a cursor must not be followed forever."""
    fixture = load_fixture("announce_txs_page1.json")
    endless = {"items": fixture["items"][:7],
               "next_page_params": {"block_number": 1, "index": 1}}
    transport = RecordingTransport(_blockscout_handler({A.ANNOUNCE: [endless]}))
    async with _client_on(transport) as client:
        txs = await client.fetch_channel_txs()
    assert txs is not None
    assert len(transport.requests) == surf_client.MAX_CHANNEL_PAGES


@pytest.mark.asyncio
async def test_channel_tx_unreadable_nonce_is_none_never_the_genesis_post():
    """`0` is a real nonce here — the channel's first post, the "soon" tx.

    So a row whose `nonce` Blockscout omits or nulls may not be coerced to 0:
    it would silently impersonate that post, and every consumer that keys on
    nonce (the feed's ordering, WP2's new-post detector's baseline) would see
    two rows claiming to be the same tx. `None` says "unread", which is what it
    is. `_parse_dev_tx` already does exactly this for its own optional fields.
    """
    fixture = load_fixture("announce_txs_page1.json")
    rows = [dict(r) for r in fixture["items"][:3]]
    rows[0]["nonce"] = None            # Blockscout nulls it
    rows[1].pop("nonce", None)         # …or omits it entirely
    rows[2]["nonce"] = 0               # …and a genuine 0 must survive as 0
    page = {"items": rows, "next_page_params": None}

    handler = _blockscout_handler({A.ANNOUNCE: [page]})
    async with _client_on(RecordingTransport(handler)) as client:
        txs = await client.fetch_channel_txs()

    assert len(txs) == 3
    assert txs[0].nonce is None and txs[0].nonce != 0
    assert txs[1].nonce is None
    assert txs[2].nonce == 0          # a read that worked and said zero


@pytest.mark.asyncio
async def test_channel_tx_contract_creation_has_to_addr_none_not_empty_string():
    """WP0.4 types `to_addr` `str | None`; a creation has no `to`.

    `""` is a third state nobody declared: it is falsy like `None` but is a
    `str`, so `str(to_addr or "")` in WP4 and `_addr("")` in WP2 both keep
    working while `to_addr is None` — the check WP2's classifier documents for
    "``to = None`` (a deployment)" — quietly stops matching.
    """
    fixture = load_fixture("announce_txs_page1.json")
    row = dict(fixture["items"][0])
    row["to"] = None
    page = {"items": [row], "next_page_params": None}

    handler = _blockscout_handler({A.ANNOUNCE: [page]})
    async with _client_on(RecordingTransport(handler)) as client:
        txs = await client.fetch_channel_txs()
    assert len(txs) == 1
    assert txs[0].to_addr is None
    assert txs[0].to_addr != ""


@pytest.mark.asyncio
async def test_fetch_channel_txs_outage_returns_none_not_empty_list():
    async with _offline_client() as client:
        result = await client.fetch_channel_txs()
    assert result is None  # [] would mean "the channel is empty" — a lie


# ---------------------------------------------------------------------------
# WP1.5 fix round 1 — channel_truncated: page-bound truncation is
# discoverable, not silent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_channel_txs_page_bound_sets_truncated_signal():
    """Hitting MAX_CHANNEL_PAGES while a cursor remains must be discoverable.

    Returning the partial rows is correct and stays — but returning them
    with no signal is the bug: WP4 needs a way to tell "that is everything"
    apart from "we stopped asking", and it cannot invent that fact for
    itself (one owner per file; this client is the only thing that ever
    sees the raw ``next_page_params`` cursor).
    """
    fixture = load_fixture("announce_txs_page1.json")
    endless = {"items": fixture["items"][:7],
               "next_page_params": {"block_number": 1, "index": 1}}
    transport = RecordingTransport(_blockscout_handler({A.ANNOUNCE: [endless]}))
    async with _client_on(transport) as client:
        txs = await client.fetch_channel_txs()
    assert txs is not None
    assert len(transport.requests) == surf_client.MAX_CHANNEL_PAGES
    # The rows actually fetched (7 per page, served MAX_CHANNEL_PAGES times),
    # not an empty stand-in — truncated still means "partial beats nothing".
    assert len(txs) == 7 * surf_client.MAX_CHANNEL_PAGES
    assert client.channel_truncated is True


@pytest.mark.asyncio
async def test_fetch_channel_txs_truncated_signal_is_false_on_a_normal_fetch():
    """A fetch that ends because the server ran out of pages is NOT truncated.

    Guards against a future refactor hardcoding ``channel_truncated = True``:
    the one real fixture page (``next_page_params: null``) must leave the
    signal False, and it must be False even though a *previous* call on the
    same client instance could have left it True — the flag is reset at the
    start of every ``fetch_channel_txs()`` call, never sticky.
    """
    fixture = load_fixture("announce_txs_page1.json")
    handler = _blockscout_handler({A.ANNOUNCE: [fixture]})
    async with _client_on(RecordingTransport(handler)) as client:
        client.channel_truncated = True  # simulate a stale True from a
        # previous refresh cycle; the next call must not inherit it.
        txs = await client.fetch_channel_txs()
    assert txs is not None and len(txs) == 21
    assert client.channel_truncated is False


# ---------------------------------------------------------------------------
# WP1.6 — fetch_dev_activity
# ---------------------------------------------------------------------------


# The senders of the six live ≤1-gwei dust transfers on the two captured pages
# — FIVE distinct addresses, because 0x61ccfd… spoofed the ops wallet twice.
# Six rows, five senders: this is a set of senders, so it has five members and
# the count below must never be "corrected" to six.  Each shares its target's
# first four and last four hex characters — which is exactly what a truncated
# `0x1234…abcdef` rendering shows.  WP0 pins three of them in LIVE_SPOOFS;
# these are all of them, across both wallets.
LIVE_DUST_SENDERS = {
    "0x61ccfd5d33f0f27a2cd5acb558d9281b110df14e",  # ~ LP_FEE_SINK_B (x2)
    "0xf3083828702c1989710ceca517412071c2f60ee6",  # ~ LP_FEE_SINK_A
    "0xf30875988b99489ac71ec2f5069de0dd80b70ee6",  # ~ LP_FEE_SINK_A
    "0x5823d93a369b0aebd798e4557196f23927d84e55",  # ~ DEV_SWEEP
    "0xa4ad23e725bb527dd5cae35b6aa985e7867d5717",  # no cast match, still dust
}


@pytest.mark.asyncio
async def test_fetch_dev_activity_merges_both_wallets_real_rows():
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
    # 80 captured rows; 17 are inbound and never become DevTx rows.
    assert rows is not None and len(rows) == 63

    # The 2026-08-07 33-ETH LP add (ops wallet, multicall to NFPM).
    lp = [r for r in rows if r.tx_hash.startswith("0x90a0f8e2")][0]
    assert lp.wallet_label == "ops"
    assert lp.from_addr == A.OPS_WALLET.lower()
    assert lp.to_addr == A.NFPM.lower()
    assert lp.method == "multicall"
    assert lp.kind == "lp"
    assert lp.value_wei == 33_252_659_725_872_729_307
    assert lp.ts == 1786076603.0  # 2026-08-07T04:23:23Z
    # Labelled from the allowlist, not from any string in the payload.
    assert lp.counterparty == A.NFPM.lower()
    assert lp.counterparty_label == A.KNOWN_LABELS[A.NFPM.lower()]

    # The dev-wallet FWA splitter claims — 12 of them on this page.
    claims = [r for r in rows if r.kind == "fwa claim"]
    assert len(claims) == 12
    assert all(r.counterparty == A.FWA_SPLITTER.lower() for r in claims)
    assert all(r.counterparty_label == "FWA Splitter" for r in claims)

    # Newest-first across the merge.
    assert all(rows[i].ts >= rows[i + 1].ts for i in range(len(rows) - 1))


@pytest.mark.asyncio
async def test_the_kind_vocabulary_matches_the_captured_pages():
    """PRD §4: deploy / LP / burn / bridge / FWA claim / transfer / other.

    Counts are derived from the two capture files, not chosen.  Re-derive them
    from `tests/fixtures/surf/captures/` if a fixture is ever re-sliced.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    counts = Counter(r.kind for r in rows)
    assert counts == Counter({
        "other": 33, "fwa claim": 12, "transfer": 8,
        "lp": 5, "burn": 3, "bridge": 2,
    })
    # Every kind is from the closed vocabulary — a Blockscout `method` string
    # never reaches the widget's label column.  It is attacker-influenced
    # (anyone can deploy a contract with a chosen function name) and unbounded
    # in width.
    assert set(counts) <= surf_client.DEV_TX_KINDS


@pytest.mark.asyncio
async def test_a_deploy_row_is_labelled_from_created_contract():
    """No page in the captures holds a deployment, so this row is synthetic.

    It is the shape PRD §3 signal 4 fires on (the ERC-8004 registration was
    exactly this), and `to` is null on a real deploy — the counterparty has to
    come from `created_contract` or the row renders blank.
    """
    page = load_fixture("dev_txs_page1.json")
    row = dict(page["items"][0])
    row |= {
        "hash": "0x" + "de" * 32,
        "to": None,
        "method": None,
        "created_contract": {"hash": "0x" + "c0" * 20},
    }
    # BOTH wallets must be mapped even when only one carries the row under
    # test: `fetch_dev_activity` gathers the dev page and the ops page, and an
    # address the map does not cover falls through to the handler's
    # `raise AssertionError`.  That is neither an `httpx.HTTPError` nor a
    # `ValueError`, so `_get_json` does not catch it and MockTransport re-raises
    # it verbatim (verified against the installed httpx 0.28.1) — the test would
    # ERROR out of `asyncio.gather` before reaching a single assertion below.
    handler = _blockscout_handler({
        A.DEV_WALLET: [{"items": [row], "next_page_params": None}],
        A.OPS_WALLET: [{"items": [], "next_page_params": None}],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    # An empty ops page is `[]`, not `None`, so the merge keeps going and the
    # synthetic dev row is the only row there is.
    assert len(rows) == 1
    assert rows[0].kind == "deploy"
    assert rows[0].counterparty == "0x" + "c0" * 20
    assert rows[0].counterparty_label is None      # a fresh deploy is unknown


@pytest.mark.asyncio
async def test_poisoning_dust_never_becomes_an_activity_row():
    """PRD §4 + §6.5 — the whole point of the sender keying.

    Six live ≤1-gwei transfers from lookalike addresses sit in these two
    captures today.  Every one of them is inbound, so keying on the sender
    removes all six; none may appear as a row, and none may borrow the label
    of the address it imitates.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    senders = {r.from_addr for r in rows}
    assert senders == {A.DEV_WALLET.lower(), A.OPS_WALLET.lower()}
    assert not (senders & LIVE_DUST_SENDERS)
    # …and the spoofs did not sneak in on the counterparty side either.
    assert not ({r.counterparty for r in rows} & LIVE_DUST_SENDERS)

    # The real fee sinks the spoofs imitate ARE labelled — proving the test
    # discriminates by address and not by "anything that looks like a sink".
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_A.lower()] == "LP-fee sink A"
    assert A.KNOWN_LABELS[A.LP_FEE_SINK_B.lower()] == "LP-fee sink B"


@pytest.mark.asyncio
async def test_an_unknown_counterparty_is_never_labelled():
    """The allowlist has no fallback.  USDT is a real, frequent counterparty
    on the ops page and is deliberately not in the cast: it must stay None so
    WP5 renders it dimmed rather than as a trusted name."""
    # The USDT rows all live on the ops page, but the dev leg of
    # `fetch_dev_activity`'s gather still issues its GET — leave it unmapped and
    # the handler's `raise AssertionError` propagates verbatim through
    # MockTransport (it is not an `httpx.HTTPError`/`ValueError`, so `_get_json`
    # never sees it) and the test errors instead of asserting.  An empty page
    # answers that leg without adding a row.
    handler = _blockscout_handler({
        A.DEV_WALLET: [{"items": [], "next_page_params": None}],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    usdt = [r for r in rows
            if r.counterparty == "0xdac17f958d2ee523a2206206994597c13d831ec7"]
    assert usdt, "the ops page holds USDT transfers"
    assert all(r.counterparty_label is None for r in usdt)
    assert all(
        r.counterparty_label is None
        for r in rows if r.counterparty not in A.KNOWN_LABELS
    )


@pytest.mark.asyncio
async def test_a_prefix_lookalike_counterparty_is_never_labelled():
    """The allowlist match is exact, not a shared-prefix heuristic.

    Neither captured page happens to contain a counterparty whose leading hex
    characters collide with a `KNOWN_LABELS` entry it is not itself — so
    without this synthetic row, a `_label_for` regression to "shared prefix"
    matching (the exact shape a well-meaning "make more addresses readable"
    change would take) would pass every other WP1.6 test in this file while
    still being the poisoning defense's failure mode: a lookalike inheriting
    its target's trusted label.  This row shares NFPM's `0xc364…` prefix and
    is a different address entirely.
    """
    lookalike = "0xc364" + "1" * 32 + "fe88"
    assert lookalike not in A.KNOWN_LABELS
    assert lookalike[:6] == A.NFPM.lower()[:6]

    page = load_fixture("dev_txs_page1.json")
    row = dict(page["items"][0])
    row |= {
        "hash": "0x" + "ab" * 32,
        "to": {"hash": lookalike},
        "method": None,
        "raw_input": "0xdeadbeef",
        "created_contract": None,
    }
    handler = _blockscout_handler({
        A.DEV_WALLET: [{"items": [row], "next_page_params": None}],
        A.OPS_WALLET: [{"items": [], "next_page_params": None}],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()

    assert len(rows) == 1
    assert rows[0].counterparty == lookalike
    assert rows[0].counterparty_label is None


@pytest.mark.asyncio
async def test_fetch_dev_activity_one_wallet_down_is_partial_not_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if A.OPS_WALLET.lower() in str(request.url).lower():
            return httpx.Response(521, json={})
        return _blockscout_handler(
            {A.DEV_WALLET: [load_fixture("dev_txs_page1.json")]}
        )(request)

    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
    # 30 captured dev rows, 4 of them inbound → 26 survive the sender keying.
    assert rows is not None and len(rows) == 26


@pytest.mark.asyncio
async def test_fetch_dev_activity_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_dev_activity() is None


# ---------------------------------------------------------------------------
# WP1.6 fix round 1 — activity_truncated: page-bound truncation is
# discoverable, not silent (mirrors WP1.5's channel_truncated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_dev_activity_page_bound_sets_truncated_signal():
    """Hitting MAX_ACTIVITY_PAGES on either wallet while a cursor remains
    must be discoverable.  The dev/ops pages are the NEW DEPLOY detector's
    only data source — a `created_contract` row that falls off a silently
    truncated page renders as "he has not deployed anything", which is
    exactly the failure this product exists to prevent.
    """
    fixture = load_fixture("dev_txs_page1.json")
    endless = {"items": fixture["items"][:5],
               "next_page_params": {"block_number": 1, "index": 1}}
    handler = _blockscout_handler({
        A.DEV_WALLET: [endless],
        A.OPS_WALLET: [{"items": [], "next_page_params": None}],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
    # Truncated is not the same failure as down: partial rows still return.
    assert rows is not None
    assert client.activity_truncated is True


@pytest.mark.asyncio
async def test_fetch_dev_activity_truncated_signal_is_false_on_a_normal_fetch():
    """A fetch that ends because both servers ran out of pages is NOT
    truncated — and it must say so even though a PREVIOUS call on the same
    client instance left the flag True, proving the reset and not a lucky
    default.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        client.activity_truncated = True  # simulate a stale True from a
        # previous refresh cycle; the next call must not inherit it.
        rows = await client.fetch_dev_activity()
    assert rows is not None and len(rows) == 63
    assert client.activity_truncated is False


# ---------------------------------------------------------------------------
# WP1.7 — fetch_market
# ---------------------------------------------------------------------------


#: ETH/USD as CoinGecko answered on 2026-08-08.  There is no committed capture
#: for this leg (the capture set predates `eth_usd` being a MarketSnapshot
#: field), so it is an inline literal and labelled as one rather than dressed up
#: as fixture-derived.
COINGECKO_ETH_USD = 1917.74


def _market_handler(
    *, dex_imd=True, gecko=True, dex_fp=True, eth=True,
) -> Callable[[httpx.Request], httpx.Response]:
    """Routes ALL FOUR legs `fetch_market` gathers.

    The fourth (CoinGecko) is easy to forget, and forgetting it does not
    degrade anything — ``_get_json`` catches only ``(httpx.HTTPError,
    ValueError)``, so the fallthrough ``AssertionError`` below would escape
    through ``asyncio.gather`` and error every market test instead of failing
    one assertion.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.dexscreener.com" in url and A.IMD_TOKEN.lower() in url.lower():
            if not dex_imd:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=load_fixture("dexscreener_imd.json"))
        if "api.dexscreener.com" in url and A.FP_TOKEN_BASE.lower() in url.lower():
            if not dex_fp:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=load_fixture("dexscreener_fp.json"))
        if "api.geckoterminal.com" in url:
            if not gecko:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=load_fixture("geckoterminal_imd.json"))
        if "coingecko" in url:
            if not eth:
                return httpx.Response(500, json={})
            return httpx.Response(
                200, json={"ethereum": {"usd": COINGECKO_ETH_USD}}
            )
        raise AssertionError(f"unexpected market URL: {url}")

    return handler


@pytest.mark.asyncio
async def test_fetch_market_cross_checked_real_values():
    async with _client_on(RecordingTransport(_market_handler())) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.imd_price_usd == pytest.approx(0.7074)          # DexScreener
    assert snap.imd_price_usd_gecko == pytest.approx(0.7127337345)
    assert snap.sources_agree is True    # 0.751 % diff < 5 % tolerance
    assert snap.imd_change_24h_pct == pytest.approx(30.89)
    assert snap.imd_vol_24h_usd == pytest.approx(244178.0)
    assert snap.pool_liquidity_usd == pytest.approx(548701.21)
    assert snap.pool_imd == pytest.approx(388421.0)
    assert snap.pool_weth == pytest.approx(142.7067)
    assert snap.fdv_usd == pytest.approx(1647147.0)
    # FP parity leg: the MAX-LIQUIDITY Base pair (424,308.81 USD), not the
    # first pair DexScreener happens to order.
    assert snap.fp_price_usd == pytest.approx(0.7274)
    # The fourth leg: eth_usd is a MarketSnapshot field and THIS method fills it
    # (WP4 reads the flat key off the snapshot).  A missing leg here is
    # invisible — the field just stays None forever.
    assert snap.eth_usd == pytest.approx(COINGECKO_ETH_USD)
    # Identity is mutable and GeckoTerminal is STALE ("Vibe Coins"): the
    # snapshot must carry DexScreener's current name and never Gecko's.
    assert snap.indexer_name == "Identity.md"
    assert snap.indexer_symbol == "IMD"


@pytest.mark.asyncio
async def test_fetch_market_gecko_down_degrades_cross_check_not_price():
    async with _client_on(
        RecordingTransport(_market_handler(gecko=False))
    ) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.imd_price_usd == pytest.approx(0.7074)
    assert snap.imd_price_usd_gecko is None
    assert snap.sources_agree is None  # unknown, NOT False and NOT True


@pytest.mark.asyncio
async def test_fetch_market_dexscreener_down_falls_back_to_gecko_price():
    async with _client_on(
        RecordingTransport(_market_handler(dex_imd=False, dex_fp=False))
    ) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.imd_price_usd == pytest.approx(0.7127337345)  # fallback leg
    assert snap.sources_agree is None
    assert snap.fp_price_usd is None
    assert snap.indexer_name is None  # Gecko's stale name must NOT leak in


@pytest.mark.asyncio
async def test_fetch_market_disagreement_is_flagged_not_averaged():
    fixture = load_fixture("dexscreener_imd.json")
    fixture["pairs"][0]["priceUsd"] = "0.90"  # ~23 % off Gecko's 0.7127

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "dexscreener" in url and A.IMD_TOKEN.lower() in url.lower():
            return httpx.Response(200, json=fixture)
        return _market_handler()(request)

    async with _client_on(RecordingTransport(handler)) as client:
        snap = await client.fetch_market()
    assert snap.sources_agree is False
    assert snap.imd_price_usd == pytest.approx(0.90)  # still reported raw


@pytest.mark.asyncio
async def test_fetch_market_coingecko_down_is_none_never_zero():
    """`PriceClient.get_eth_usd()` returns 0.0 on failure. That sentinel must
    not be copied here: an ETH price of 0 makes every ETH-denominated figure
    downstream render as free rather than as unavailable."""
    async with _client_on(RecordingTransport(_market_handler(eth=False))) as client:
        snap = await client.fetch_market()
    assert snap is not None
    assert snap.eth_usd is None
    assert snap.eth_usd != 0.0
    assert snap.imd_price_usd == pytest.approx(0.7074)  # the IMD legs survive


@pytest.mark.asyncio
async def test_fetch_market_total_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_market() is None


# ---------------------------------------------------------------------------
# WP1.8 — fetch_nft_stats
# ---------------------------------------------------------------------------


# The capture's newest IDMD transfer, 2026-08-08T09:51:59Z.  Every clock in
# these tests is expressed relative to it, so the expected counts are a
# property of the fixture rather than of the day the suite runs.
IDMD_NEWEST_TRANSFER_TS = 1786182719.0

# One IdentityHashUpdated log: token id 0, the only identity ever written
# (2026-05-14).  Blockscout's /addresses/{h}/logs shape, trimmed to the three
# fields the client reads.
def _registry_log(token_id: int, topic0: str = A.TOPIC_IDENTITY_HASH_UPDATED) -> dict:
    return {
        "address": {"hash": A.IDENTITY_REGISTRY},
        "topics": [topic0, "0x" + _encode_uint(token_id)],
        "data": "0x",
        "block_number": 25_004_000,
    }


REGISTRY_LOGS_PAGE = {
    "items": [
        _registry_log(0),
        # A second write to the SAME id — still one identity written.
        _registry_log(0),
        # An unrelated event from the same contract (ownership transfer):
        # topic0 filtering, not "every log this address emitted", is the rule.
        _registry_log(7, topic0="0x" + "ab" * 32),
    ],
    "next_page_params": None,
}


def _nft_handler(
    *, rest_up=True, rpc_up=True, dev_balance=3,
    transfers_page=None, registry_page=None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "blockscout" in url:
            if not rest_up:
                return httpx.Response(521, json={})
            path = request.url.path.rstrip("/")
            if path.endswith("/counters"):
                return httpx.Response(200, json=load_fixture("idmd_counters.json"))
            if path.endswith("/transfers"):
                return httpx.Response(200, json=(
                    transfers_page
                    if transfers_page is not None
                    else load_fixture("idmd_transfers_page1.json")
                ))
            if path.endswith("/logs"):
                assert A.IDENTITY_REGISTRY.lower() in path.lower()
                return httpx.Response(200, json=(
                    registry_page if registry_page is not None
                    else REGISTRY_LOGS_PAGE
                ))
            return httpx.Response(200, json=load_fixture("idmd_token.json"))
        payload = json.loads(request.content)
        if not rpc_up:
            return httpx.Response(521, json={})
        assert payload["method"] == "eth_call"
        call = payload["params"][0]
        assert call["to"].lower() == A.IDMD_NFT.lower()
        assert call["data"].startswith(surf_client._SEL_BALANCE_OF)
        assert A.DEV_WALLET.lower()[2:] in call["data"].lower()
        return httpx.Response(
            200, json=_rpc_ok(payload, "0x" + _encode_uint(dev_balance))
        )

    return handler


def _nft_client(transport, *, now: float = IDMD_NEWEST_TRANSFER_TS + 60.0):
    """A client whose clock sits just after the capture's newest transfer."""
    return _client_on(transport, now_fn=lambda: now)


@pytest.mark.asyncio
async def test_fetch_nft_stats_real_values():
    async with _nft_client(RecordingTransport(_nft_handler())) as client:
        stats = await client.fetch_nft_stats()
    assert stats is not None
    assert stats.holders == 667          # idmd_token.json holders_count
    assert stats.total_supply == 2000    # minted out on launch day
    assert stats.transfers_total == 7411 # idmd_counters.json — LIFETIME
    assert stats.dev_holdings == 3       # balanceOf(dev) — he buys his own
    # The whole 25-row slice sits inside the 24 h window (it spans 10.8 h),
    # so the rate is the page count — NOT the lifetime counter beside it.
    assert stats.transfers_24h == 25.0
    assert stats.transfers_24h != stats.transfers_total
    assert stats.written == 1            # IDMD #0, the only identity written
    assert stats.floor_eth is None       # no keyless source, pinned


@pytest.mark.asyncio
async def test_transfers_24h_is_a_window_not_a_page_count():
    """Move the clock forward and rows fall out of the window.

    The derivation must be "rows newer than now-24h", not "rows on the page".
    The clock has to move far enough to actually cross the window's trailing
    edge, and the page only spans 10.77 h: at +6 h the cutoff is still
    ``newest - 18 h``, older than every row on it, so the count would be 25 and
    this test would be byte-identical to ``test_fetch_nft_stats_real_values``.
    At **+18 h** the cutoff is ``newest - 6 h`` = 1786161119, which lands
    between row 15 (5.907 h old, inside) and row 16 (8.197 h old, outside) —
    16 rows. Any anchor in (newest + 15.81 h, newest + 18.09 h] gives 16;
    18 h sits comfortably inside that and states the cutoff in round hours.
    """
    async with _nft_client(
        RecordingTransport(_nft_handler()),
        now=IDMD_NEWEST_TRANSFER_TS + 18 * 3600.0,
    ) as client:
        stats = await client.fetch_nft_stats()
    assert stats.transfers_24h == 16.0
    # NOT 25: that is the answer for a cutoff older than the whole page, and
    # "change the expectation to 25" is the repair that makes this test vacuous.
    assert stats.transfers_24h != 25.0


@pytest.mark.asyncio
async def test_transfers_24h_is_none_when_the_window_outruns_the_page_bound():
    """A lower bound is not a rate.

    A server that keeps handing back a cursor while every row is still inside
    the window means the client never saw the edge of the day. `None` renders
    the unavailable state; the partial count would render as fact.
    """
    fixture = load_fixture("idmd_transfers_page1.json")
    endless = {"items": fixture["items"], "next_page_params": {"index": 1}}
    transport = RecordingTransport(_nft_handler(transfers_page=endless))
    async with _nft_client(transport) as client:
        stats = await client.fetch_nft_stats()
    assert stats is not None
    assert stats.transfers_24h is None
    assert stats.transfers_total == 7411   # the lifetime leg still answered
    transfer_gets = [u for u in transport.urls() if u.endswith("/transfers")
                     or "/transfers?" in u]
    assert len(transfer_gets) == surf_client.MAX_NFT_TRANSFER_PAGES


@pytest.mark.asyncio
async def test_written_counts_distinct_ids_and_only_the_right_topic():
    """1/2000 — and it stays 1 when the same token is re-written."""
    async with _nft_client(RecordingTransport(_nft_handler())) as client:
        stats = await client.fetch_nft_stats()
    assert stats.written == 1

    two = {"items": [_registry_log(0), _registry_log(1337)],
           "next_page_params": None}
    async with _nft_client(
        RecordingTransport(_nft_handler(registry_page=two))
    ) as client:
        stats = await client.fetch_nft_stats()
    assert stats.written == 2

    # A registry that emitted nothing yet is 0 written — a real value, and
    # the one case where 0 must NOT become None.
    empty = {"items": [], "next_page_params": None}
    async with _nft_client(
        RecordingTransport(_nft_handler(registry_page=empty))
    ) as client:
        stats = await client.fetch_nft_stats()
    assert stats.written == 0


@pytest.mark.asyncio
async def test_fetch_nft_stats_rest_down_still_reports_dev_holdings():
    async with _nft_client(RecordingTransport(_nft_handler(rest_up=False))) as client:
        stats = await client.fetch_nft_stats()
    assert stats is not None
    assert stats.holders is None and stats.transfers_total is None
    assert stats.transfers_24h is None and stats.written is None
    assert stats.dev_holdings == 3


@pytest.mark.asyncio
async def test_fetch_nft_stats_everything_down_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_nft_stats() is None


# ---------------------------------------------------------------------------
# WP1.9 — fetch_recent_logs
# ---------------------------------------------------------------------------

#: The head the LOGS pool reports — deliberately NOT ``HEAD_BLOCK`` (WP1.3's
#: state-pool head, 25,707,884).  The two pools answer ``eth_blockNumber``
#: independently and this suite must not pretend otherwise, so they get
#: different names as well as different values.  Reusing the name would be worse
#: than confusing: module globals resolve at call time, so the later definition
#: would win for the WHOLE file and quietly break WP1.3's assertions.
LOG_HEAD_BLOCK = 25_709_000


def _addr_topic(addr: str) -> str:
    return "0x" + _strip0x(addr).lower().rjust(64, "0")


def _fake_log(topic0: str, address: str, **extra: Any) -> dict:
    return {
        "address": address.lower(),
        "topics": [topic0, *extra.pop("topics", [])],
        "data": extra.pop("data", "0x"),
        "blockNumber": hex(extra.pop("block", LOG_HEAD_BLOCK - 5)),
        "transactionHash": extra.pop("tx", "0x" + "ab" * 32),
        "logIndex": "0x0",
    }


def _topics_match(log_topics: list, flt_topics: list) -> bool:
    """Real ``eth_getLogs`` topic semantics: positional, ``None`` = wildcard,
    a list = OR at that position.

    The double MUST honour positions. ``fetch_recent_logs`` asks for
    ``Initialize`` twice — IMD as ``currency0`` (topic 2), then as ``currency1``
    (topic 3) — and merges the two answers without deduping, because on a real
    chain IMD is only ever one of the two. A position-blind handler serves the
    same row to both queries and the merged group holds a phantom duplicate,
    which is a defect in the DOUBLE, not in the client.
    """
    for i, want in enumerate(flt_topics):
        if want is None:
            continue
        if i >= len(log_topics):
            return False
        got = str(log_topics[i]).lower()
        if isinstance(want, (list, tuple)):
            if got not in {str(w).lower() for w in want}:
                return False
        elif got != str(want).lower():
            return False
    return True


def _logs_handler(
    logs_by_topic0: dict[str, list[dict]],
    *, range_errors_before_success: int = 0,
) -> Callable[[httpx.Request], httpx.Response]:
    state = {"range_errors_left": range_errors_before_success,
             "windows_seen": []}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "eth_blockNumber":
            return httpx.Response(200, json=_rpc_ok(payload, hex(LOG_HEAD_BLOCK)))
        assert payload["method"] == "eth_getLogs", payload["method"]
        flt = payload["params"][0]
        window = int(flt["toBlock"], 16) - int(flt["fromBlock"], 16)
        state["windows_seen"].append(window)
        if state["range_errors_left"] > 0:
            state["range_errors_left"] -= 1
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32005,
                          # a DECREMENTING suggested range — following it
                          # verbatim livelocks (CLAUDE.md hazard).
                          "message": "block range is too large, try "
                                     f"{LOG_HEAD_BLOCK - 1}-{LOG_HEAD_BLOCK}"},
            })
        topic0 = flt["topics"][0]
        rows = [
            log for log in logs_by_topic0.get(topic0, [])
            if _topics_match(log["topics"], flt["topics"])
        ]
        return httpx.Response(200, json=_rpc_ok(payload, rows))

    handler.state = state  # type: ignore[attr-defined]
    return handler


def _standard_logs() -> dict[str, list[dict]]:
    idmd_word = _strip0x(A.IDMD_NFT).lower().rjust(64, "0")
    return {
        A.TOPIC_TRANSFER: [
            _fake_log(A.TOPIC_TRANSFER, A.IMD_TOKEN, topics=[
                "0x" + "0" * 64, _addr_topic(A.OPS_WALLET)]),
        ],
        A.TOPIC_IDENTITY_HASH_UPDATED: [],
        # topics = [Initialize, poolId, currency0, currency1] — IMD sits at
        # topic 2, i.e. it is currency0 here.  A pool can only ever have IMD on
        # ONE side, which is why `_topics_match` must answer exactly one of the
        # client's two Initialize queries.
        A.TOPIC_V4_INITIALIZE: [
            _fake_log(A.TOPIC_V4_INITIALIZE, A.POOL_MANAGER_V4, topics=[
                "0x" + "11" * 32, _addr_topic(A.IMD_TOKEN),
                _addr_topic("0x" + "c0" * 20)]),
        ],
        A.TOPIC_SEAPORT_ORDER_FULFILLED: [
            _fake_log(A.TOPIC_SEAPORT_ORDER_FULFILLED, surf_client._SEAPORT,
                      topics=["0x" + "22" * 32, "0x" + "33" * 32],
                      data="0x" + "00" * 31 + "01" + idmd_word),
            # An OrderFulfilled for some OTHER collection — must be dropped
            # by the IDMD pre-filter.
            _fake_log(A.TOPIC_SEAPORT_ORDER_FULFILLED, surf_client._SEAPORT,
                      topics=["0x" + "44" * 32, "0x" + "55" * 32],
                      data="0x" + "ee" * 96),
        ],
    }


@pytest.mark.asyncio
async def test_fetch_recent_logs_filters_and_pools():
    handler = _logs_handler(_standard_logs())
    transport = RecordingTransport(handler)
    async with _client_on(transport) as client:
        window = await client.fetch_recent_logs()
    assert window is not None
    assert window.to_block == LOG_HEAD_BLOCK
    assert window.from_block == LOG_HEAD_BLOCK - surf_client.LOG_WINDOW_BLOCKS
    assert len(window.bridge_mints) == 1
    assert window.identity_updates == ()          # empty is DATA, not failure
    # ONE Initialize row, from TWO queries: the fixture log carries IMD at
    # topic 2 (currency0), so the currency0 query matches it and the currency1
    # query answers []. `_topics_match` is what makes the double behave like a
    # real node here — a position-blind one would hand the same row to both
    # queries and the un-deduped merge below would hold it twice.
    assert len(window.v4_initializes) == 1
    assert len(window.seaport_sales) == 1         # the non-IDMD row was dropped

    # Every request in this method went to the LOGS pool — never publicnode.
    assert transport.urls(), "no requests recorded"
    for url in transport.urls():
        assert "publicnode" not in url

    # The bridge-mint filter is exact: Transfer, from == 0x0, to ∈ {dev, ops}.
    getlogs = [p for (_u, _m, p) in transport.requests
               if p and p.get("method") == "eth_getLogs"]
    mint = [p for p in getlogs
            if p["params"][0]["topics"][0] == A.TOPIC_TRANSFER][0]
    flt = mint["params"][0]
    assert flt["address"].lower() == A.IMD_TOKEN.lower()
    assert flt["topics"][1] == "0x" + "0" * 64
    assert sorted(t.lower() for t in flt["topics"][2]) == sorted(
        [_addr_topic(A.DEV_WALLET), _addr_topic(A.OPS_WALLET)])

    # The v4 Initialize filter matches IMD as EITHER currency (two topics-OR
    # calls or one per position — assert both positions were queried).
    init_calls = [p for p in getlogs
                  if p["params"][0]["topics"][0] == A.TOPIC_V4_INITIALIZE]
    assert len(init_calls) == 2
    positions = set()
    for p in init_calls:
        topics = p["params"][0]["topics"]
        for i in (2, 3):
            if len(topics) > i and topics[i] == _addr_topic(A.IMD_TOKEN):
                positions.add(i)
    assert positions == {2, 3}


@pytest.mark.asyncio
async def test_fetch_recent_logs_halves_window_never_follows_suggestion():
    handler = _logs_handler(_standard_logs(), range_errors_before_success=1)
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()
    assert window is not None
    seen = handler.state["windows_seen"]
    assert seen[0] == surf_client.LOG_WINDOW_BLOCKS
    assert seen[1] == surf_client.LOG_WINDOW_BLOCKS // 2  # halved…
    assert 1 not in seen  # …and the endpoint's 1-block suggestion was IGNORED


@pytest.mark.asyncio
async def test_fetch_recent_logs_shrink_is_bounded_then_none():
    handler = _logs_handler(_standard_logs(), range_errors_before_success=99)
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()
    assert window is None  # bounded retries, then honest failure — no livelock
    assert len(handler.state["windows_seen"]) <= (
        (surf_client._LOG_MAX_SHRINKS + 1) * 5 * 2  # filters x endpoints cap
    )


@pytest.mark.asyncio
async def test_fetch_recent_logs_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_recent_logs() is None


def _logs_handler_single_group_dies(
    logs_by_topic0: dict[str, list[dict]], *, dying_topic0: str,
) -> Callable[[httpx.Request], httpx.Response]:
    """Like ``_logs_handler``, but requests for ``dying_topic0`` NEVER
    recover — every attempt range-errors, so ``_get_logs_shrinking``'s bounded
    loop exhausts and that ONE group returns ``None`` while every other group
    is served normally from *logs_by_topic0*. This is what proves
    ``log_group_failed`` is keyed per-group, not a single fetch-wide bit.
    """
    state = {"windows_seen": []}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "eth_blockNumber":
            return httpx.Response(200, json=_rpc_ok(payload, hex(LOG_HEAD_BLOCK)))
        assert payload["method"] == "eth_getLogs", payload["method"]
        flt = payload["params"][0]
        window = int(flt["toBlock"], 16) - int(flt["fromBlock"], 16)
        state["windows_seen"].append(window)
        topic0 = flt["topics"][0]
        if topic0 == dying_topic0:
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32005,
                          "message": "block range is too large, try "
                                     f"{LOG_HEAD_BLOCK - 1}-{LOG_HEAD_BLOCK}"},
            })
        rows = [
            log for log in logs_by_topic0.get(topic0, [])
            if _topics_match(log["topics"], flt["topics"])
        ]
        return httpx.Response(200, json=_rpc_ok(payload, rows))

    handler.state = state  # type: ignore[attr-defined]
    return handler


@pytest.mark.asyncio
async def test_fetch_recent_logs_flags_only_the_group_that_failed():
    """A single filter dying degrades ONLY its own group — the LogWindow's
    tuple still can't say so (an exhausted group looks exactly like an empty
    one), which is why ``log_group_failed`` is the thing this test actually
    asserts against.
    """
    handler = _logs_handler_single_group_dies(
        _standard_logs(), dying_topic0=A.TOPIC_IDENTITY_HASH_UPDATED,
    )
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()
    assert window is not None
    # The three healthy groups still came through with real data.
    assert len(window.bridge_mints) == 1
    assert len(window.v4_initializes) == 1
    assert len(window.seaport_sales) == 1
    # identity_updates degraded to () — indistinguishable from "nothing
    # happened" in the tuple alone; the flag below is the only place this
    # was a failure and not a quiet gate.
    assert window.identity_updates == ()
    assert client.log_group_failed == {
        "bridge_mints": False,
        "identity_updates": True,
        "v4_initializes": False,
        "seaport_sales": False,
    }


@pytest.mark.asyncio
async def test_fetch_recent_logs_resets_group_flags_on_a_clean_call():
    """Primed all-True beforehand, so a clean call proves the per-call RESET
    (mirrors ``channel_truncated`` / ``activity_truncated``), not a default
    that happens to already read ``False``.
    """
    handler = _logs_handler(_standard_logs())
    async with _client_on(RecordingTransport(handler)) as client:
        client.log_group_failed = {k: True for k in client.log_group_failed}
        window = await client.fetch_recent_logs()
    assert window is not None
    assert client.log_group_failed == {
        "bridge_mints": False,
        "identity_updates": False,
        "v4_initializes": False,
        "seaport_sales": False,
    }


def test_seaport_address_is_labeled():
    assert surf_client._SEAPORT in A.KNOWN_LABELS  # one cast list, no drift


# ---------------------------------------------------------------------------
# WP1.9b — the hand-over contract
# ---------------------------------------------------------------------------

# Field-for-field, what WP4's decoders index into.  Keep in sync with the
# hand-over table in the WP1 header; a failure here is a WP1 defect, and a
# change here needs WP4's agreement.
#
# ``logIndex`` joined this set when the ordering fix landed. ``ts`` alone is not
# a total order over an event stream — two events in one block share a
# timestamp, and a whole sweep shares one when the endpoint omits
# ``blockTimestamp`` — so WP4 orders on ``(ts, blockNumber, logIndex)``. A
# client that dropped ``logIndex`` would leave a genuinely new event invisible
# behind an equally-stamped one.
_REQUIRED_LOG_FIELDS = {
    "topics", "data", "blockNumber", "logIndex", "transactionHash",
}


def _rich_log(topic0: str, address: str, **extra: Any) -> dict:
    """A log with every field a real endpoint sends, including the optional
    ``blockTimestamp`` that tenderly returns and drpc does not."""
    return {
        **_fake_log(topic0, address, **extra),
        "blockTimestamp": hex(1_786_076_339),
        "logIndex": "0x2c",
        "removed": False,
    }


@pytest.mark.asyncio
async def test_every_log_row_reaches_the_manager_with_its_decodable_fields():
    """The contract WP4's decoders are written against."""
    handler = _logs_handler(_standard_logs())
    async with _client_on(RecordingTransport(handler)) as client:
        window = await client.fetch_recent_logs()

    groups = (window.bridge_mints, window.identity_updates,
              window.v4_initializes, window.seaport_sales)
    rows = [r for group in groups for r in group]
    assert rows, "fixture must produce rows in at least one group"
    for row in rows:
        assert _REQUIRED_LOG_FIELDS <= set(row), row
        assert isinstance(row["topics"], list) and row["topics"]
        assert str(row["data"]).startswith("0x")
        assert row["transactionHash"]


@pytest.mark.asyncio
async def test_log_row_topics_survive_in_the_served_order():
    """``topics`` order is content, not just presence.

    ``topics[1]`` carries a position-dependent token id — the WP1 header's
    hazard table calls it the highest-consequence field after the hook
    address. The test above only proves ``topics`` is a non-empty list; a
    "canonicalising" edit that sorted or otherwise permuted the list would
    slip straight past it while silently corrupting every downstream decode.
    This pins full element-for-element, IN-ORDER equality against what the
    endpoint actually served.
    """
    logs = _standard_logs()
    expected = {
        "bridge": list(logs[A.TOPIC_TRANSFER][0]["topics"]),
        "v4": list(logs[A.TOPIC_V4_INITIALIZE][0]["topics"]),
        "seaport": list(logs[A.TOPIC_SEAPORT_ORDER_FULFILLED][0]["topics"]),
    }
    # Every fixture row's topics are pairwise distinct, so a reversal is
    # guaranteed to differ from the original — otherwise the assertion below
    # would be vacuously true even against a client that silently reordered.
    for topics in expected.values():
        assert len(set(topics)) == len(topics)

    async with _client_on(RecordingTransport(_logs_handler(logs))) as client:
        window = await client.fetch_recent_logs()

    assert window.bridge_mints[0]["topics"] == expected["bridge"]
    assert window.v4_initializes[0]["topics"] == expected["v4"]
    assert window.seaport_sales[0]["topics"] == expected["seaport"]


@pytest.mark.asyncio
async def test_the_full_data_word_run_survives_untruncated():
    """`hooks` is data word 2 of a v4 Initialize — five words in.

    A client that kept only the first word would leave WP4 reading "" for
    hooks, which is falsy, which reads as hookless, which pins the hero to
    NOT LIVE forever.  This is the single highest-consequence field in the
    dashboard, so it gets its own test.
    """
    hooks_word = _strip0x(A.VIBECOINS_HOOK).lower().rjust(64, "0")
    data = "0x" + "".join([
        "0" * 60 + "2710",          # fee = 10000
        "0" * 60 + "00c8",          # tickSpacing = 200
        hooks_word,                 # word 2 — hooks
        "0" * 63 + "1",             # sqrtPriceX96
        "0" * 64,                   # tick
    ])
    logs = _standard_logs()
    logs[A.TOPIC_V4_INITIALIZE] = [
        _fake_log(A.TOPIC_V4_INITIALIZE, A.POOL_MANAGER_V4,
                  topics=["0x" + "11" * 32, _addr_topic(A.IMD_TOKEN),
                          _addr_topic(A.WETH)],
                  data=data),
    ]

    async with _client_on(RecordingTransport(_logs_handler(logs))) as client:
        window = await client.fetch_recent_logs()

    row = window.v4_initializes[0]
    assert row["data"] == data                       # byte-for-byte
    assert len(_strip0x(row["data"])) == 64 * 5      # all five words
    # Decoded the way WP4 will decode it, as a cross-check of the contract.
    assert "0x" + _strip0x(row["data"])[64 * 2 + 24:64 * 3] == \
        A.VIBECOINS_HOOK.lower()
    assert len(row["topics"]) == 4                   # id + both currencies


@pytest.mark.asyncio
async def test_block_timestamp_is_passed_through_when_the_endpoint_sends_it():
    """Optional upstream field, and the difference between a true FIRED age
    and "just now" for every event (WP4's `_log_ts` prefers it)."""
    logs = {
        A.TOPIC_TRANSFER: [
            _rich_log(A.TOPIC_TRANSFER, A.IMD_TOKEN,
                      topics=["0x" + "0" * 64, _addr_topic(A.OPS_WALLET)],
                      data="0x" + f"{10**22:064x}"),
        ],
        A.TOPIC_IDENTITY_HASH_UPDATED: [],
        A.TOPIC_V4_INITIALIZE: [],
        A.TOPIC_SEAPORT_ORDER_FULFILLED: [],
    }
    async with _client_on(RecordingTransport(_logs_handler(logs))) as client:
        window = await client.fetch_recent_logs()

    row = window.bridge_mints[0]
    assert row["blockTimestamp"] == hex(1_786_076_339)
    # The amount word is intact too — 10,000 IMD at 18 decimals.
    assert int(row["data"], 16) == 10**22


def test_the_client_never_decodes_a_log_itself():
    """One owner for the log decoders, and it is WP4.

    A second copy here would drift from the manager's and the two would
    disagree about launch day.  Matching on WP4's helper names rather than on
    words like "hooks" keeps this from firing on an explanatory comment.
    """
    source = Path(surf_client.__file__).read_text()
    for banned in ("_word_addr", "_log_ts", "_v4_launch_rows"):
        assert banned not in source, (
            f"{banned} is WP4's; surf_client must hand over raw rows"
        )
    # The dev-activity labelling IS this module's (WP0.4 forces it), so the
    # allowlist lookup is expected here and only here.
    assert "_label_for" in source


# ---------------------------------------------------------------------------
# fetch_tx_senders — the v4-launch corroboration read
# ---------------------------------------------------------------------------
#
# Uniswap v4 ``initialize()`` is permissionless, so an ``Initialize`` log for
# IMD with a non-zero hook proves only that *somebody* paid gas.  The one thing
# a stranger cannot forge is the signature on the transaction that emitted it,
# and this is the read that recovers it.  The manager decides what the answer
# means; this module only refuses to invent one.


def _tx_handler(senders: dict[str, str]):
    """Answer an ``eth_getTransactionByHash`` batch from a hash -> from map.

    A hash absent from *senders* comes back as a JSON-RPC ``error`` — the way a
    pruning or lagging endpoint answers for a transaction it does not hold.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)
        assert isinstance(batch, list), "fetch_tx_senders must POST one batch"
        out = []
        for entry in batch:
            assert entry["method"] == "eth_getTransactionByHash", entry["method"]
            tx = str(entry["params"][0]).lower()
            if tx in senders:
                out.append(_rpc_ok(entry, {"hash": tx, "from": senders[tx],
                                           "to": A.POOL_MANAGER_V4}))
            else:
                out.append({"jsonrpc": "2.0", "id": entry["id"],
                            "error": {"code": -32000, "message": "not found"}})
        return httpx.Response(200, json=out)

    return handler


_LAUNCH_TX = "0x" + "5c" * 32
_STRANGER_TX = "0x" + "6d" * 32


@pytest.mark.asyncio
async def test_fetch_tx_senders_reads_the_signer_off_the_state_pool():
    transport = RecordingTransport(
        _tx_handler({_LAUNCH_TX: A.DEV_WALLET, _STRANGER_TX: "0x" + "ee" * 20})
    )
    async with _client_on(transport) as client:
        senders = await client.fetch_tx_senders([_LAUNCH_TX, _STRANGER_TX])

    # Lowercased on both sides: the RPC answers lowercase and the vendored
    # constants are checksummed, so a case-sensitive caller would read the
    # dev's own launch as a stranger's.
    assert senders == {
        _LAUNCH_TX: A.DEV_WALLET.lower(),
        _STRANGER_TX: "0x" + "ee" * 20,
    }
    # STATE pool only — publicnode indexes transactions and the logs pool is
    # reserved for the archive-range reads it is chosen for.
    assert transport.urls() == [client.state_endpoints[0]]


@pytest.mark.asyncio
async def test_an_unreadable_transaction_is_absent_not_a_zero_address():
    """"We could not read who sent it" and "a stranger sent it" are the two
    answers the launch corroboration exists to keep apart.  A zero address, an
    empty string or any other placeholder here reads as *attributed to nobody*,
    which is a stranger — and that turns an outage into a confident NOT LIVE on
    the one event this dashboard exists to catch.
    """
    async with _client_on(RecordingTransport(_tx_handler({}))) as client:
        senders = await client.fetch_tx_senders([_LAUNCH_TX])
    assert senders == {}

    async with _offline_client() as client:
        assert await client.fetch_tx_senders([_LAUNCH_TX]) == {}


@pytest.mark.asyncio
async def test_fetch_tx_senders_issues_no_request_for_an_empty_list():
    """The everyday case is zero hooked pools; it must cost zero requests."""
    async with _raising_client() as client:
        assert await client.fetch_tx_senders([]) == {}


@pytest.mark.asyncio
async def test_fetch_tx_senders_asks_for_each_hash_once():
    transport = RecordingTransport(_tx_handler({_LAUNCH_TX: A.DEV_WALLET}))
    async with _client_on(transport) as client:
        await client.fetch_tx_senders([_LAUNCH_TX, _LAUNCH_TX.upper(), _LAUNCH_TX])
    (_url, _method, payload), = transport.requests
    assert len(payload) == 1


# ---------------------------------------------------------------------------
# WP1.10 — structural guards
# ---------------------------------------------------------------------------

import ast
import inspect

from maxpane_dashboard.data import surf_client as _mod


def _public_fetchers() -> list[str]:
    """Every public ``fetch_*`` name defined on ``SurfClient``, live.

    Fix round 1 finding (MINOR): a hardcoded list matched the seven real
    fetchers today, but an eighth added later would silently escape the
    outage sweep and the zero-turn sweep below — the one place that
    guarantees every fetcher degrades to ``None`` rather than ``0`` or an
    exception. Derived from ``dir(SurfClient)`` instead, so a new fetcher is
    swept automatically.

    ``fetch_tx_senders`` is one explicit exclusion, and the reason is that
    the two sweeps below would assert the wrong contract for it. It is not a
    source-group fetcher: it takes a list of hashes and answers a **per-hash
    map**, so its outage encoding is *absence of a key*, not a ``None`` return
    — a ``None`` there would say "the whole lookup is unavailable" about a
    batch in which some hashes resolved and others did not. Its own outage
    behaviour is pinned by
    ``test_an_unreadable_transaction_is_absent_not_a_zero_address``, which
    drives it through ``_offline_client`` exactly as these sweeps do.

    ``fetch_pool_v4`` is the second exclusion, for the mirror-image reason:
    ``PoolV4State``'s own docstring (WP0/Task 1's frozen contract) says "the
    pool is real, so there is no does-not-exist case here" — every field
    degrades to ``None`` on a failed read, but the method always hands back a
    ``PoolV4State``, never a bare ``None``, so a downstream caller can always
    read ``.pool_id_source`` to learn whether even the *fallback* constant is
    all it got. Its own outage behaviour is pinned by
    ``test_fetch_pool_v4_total_outage_still_returns_a_labelled_state``.

    ``fetch_launchpad`` is the third exclusion, on exactly the ``fetch_pool_v4``
    precedent: ``LaunchpadState`` always comes back, all-``None``-fielded on a
    total outage, never a bare ``None`` — pinned by
    ``test_fetch_launchpad_total_outage_still_returns_a_labelled_state``.

    ``fetch_decoy_pool_count`` is the fourth: it is not a source-group
    fetcher either — it takes a required ``real_pool_id`` argument (so the
    zero-args ``getattr(client, name)()`` call these two sweeps make would
    ``TypeError`` before ever reaching the transport) and its outage encoding
    is the tuple ``(None, None)``, not a bare ``None``. Its own outage
    behaviour is pinned by ``test_fetch_decoy_pool_count_total_outage_is_none_none``.
    """
    return sorted(
        name for name in dir(SurfClient)
        if name.startswith("fetch_") and not name.startswith("_")
        and name not in (
            "fetch_tx_senders", "fetch_pool_v4",
            "fetch_launchpad", "fetch_decoy_pool_count",
        )
    )


FETCHERS = _public_fetchers()


def test_frozen_surface_is_complete():
    assert FETCHERS, "no public fetch_* method found on SurfClient"
    for name in FETCHERS:
        fn = getattr(SurfClient, name)
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", FETCHERS)
async def test_every_fetcher_survives_total_outage_as_none(name):
    """PRD success criterion 3: full outage → explicit degraded state.

    Every request fails at the transport layer, so this proves each method
    survives its retries, its endpoint rotation and its ``asyncio.gather``
    without letting an exception escape into the refresh loop.

    ``_offline_client``, not ``_raising_client``: these methods all DO issue
    requests, and an ``AssertionError`` from a ``MockTransport`` handler is not
    an ``httpx.HTTPError`` — it would propagate out of the fetcher and error
    all seven cases instead of asserting anything.
    """
    async with _offline_client() as client:
        result = await getattr(client, name)()
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", FETCHERS)
async def test_no_fetcher_turns_outage_into_zero(name):
    """A failed read is None, never 0 / [] / {} (CLAUDE.md convention)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(521, json={})

    async with _client_on(RecordingTransport(handler)) as client:
        result = await getattr(client, name)()
    assert result is None
    assert result != 0 and result != [] and result != {}


def test_state_pool_is_structurally_logless():
    """No state-pool CODE may spell eth_getLogs.

    A capability probe is the failure mode: publicnode answers a narrow
    recent range and 403s the backfill, so the safe rule is that no state-
    pool helper can even name the method (mirrors
    test_no_eth_getlogs_in_this_module in the FWA suite).

    Fix round 1 finding (CRITICAL): the original version sliced the raw
    source on ``code.split("async def _rpc_logs")[0]``, so it only ever
    inspected ``_post_rpc`` / ``_rpc_state`` / ``_rpc_state_batch`` — every
    function defined ABOVE ``_rpc_logs`` in the file. ``fetch_nonces`` and
    ``fetch_chain_state``, the module's two biggest state-pool consumers,
    are defined below it and were never inspected at all; a reviewer proved
    this by planting ``_BOGUS_ROUTE = "eth_getLogs"`` inside ``fetch_nonces``
    and watching the old guard pass.

    Rebuilt on ``ast`` instead of a text slice, and keyed on WHAT a function
    IS (does it own the logs pool?) rather than WHERE it sits in the file: the
    WP1 header freezes "the string ``eth_getLogs`` appears only in the logs
    section of the module", and the logs section is exactly the three
    functions named in ``_LOG_SECTION_FUNCS``. Every ``eth_getLogs`` STRING
    CONSTANT anywhere else in the module — module-level code (the original
    ``STATE_RPC_PRIMARY``-adjacent probe) or any function regardless of its
    textual position (the ``fetch_nonces`` case above) — fails this test.
    Docstrings are explicitly exempted throughout (by AST node identity, not
    by string-stripping): the module docstring, ``_LogRangeError``'s and
    ``_addr_topic``'s docstrings all name ``eth_getLogs`` in prose, and prose
    must stay free to name the thing it forbids.
    """
    tree = ast.parse(Path(_mod.__file__).read_text())

    # Every docstring's Constant node, by identity — the ONE thing allowed to
    # say "eth_getLogs" anywhere in the module, prose being prose.
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstring_ids.add(id(body[0].value))

    # The logs section, named — not wherever it happens to sit in the file.
    _LOG_SECTION_FUNCS = {"_rpc_logs", "_get_logs_shrinking", "fetch_recent_logs"}
    protected_ids: set[int] = set()
    found_log_funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name in _LOG_SECTION_FUNCS:
            found_log_funcs.add(node.name)
            protected_ids.update(id(n) for n in ast.walk(node))
    assert found_log_funcs == _LOG_SECTION_FUNCS, (
        "expected the logs section to be exactly "
        f"{sorted(_LOG_SECTION_FUNCS)}, found {sorted(found_log_funcs)} — "
        "a rename here means this guard is silently checking nothing"
    )

    offending = [
        f"line {getattr(node, 'lineno', '?')}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and "eth_getLogs" in node.value
        and id(node) not in docstring_ids
        and id(node) not in protected_ids
    ]
    assert not offending, (
        "'eth_getLogs' appears as CODE outside the logs section "
        f"{sorted(_LOG_SECTION_FUNCS)}: {offending}"
    )


def test_client_module_never_reads_the_wall_clock_directly():
    """time.time() is injected as now_fn; time.monotonic (pacing) is fine."""
    source = Path(_mod.__file__).read_text()
    assert "time.time()" not in source


@pytest.mark.asyncio
async def test_no_fetcher_invents_a_zero_timestamp():
    """The sweep for the sentinel that would disable BRIDGE STAGE.

    0.0 is the one value that is both falsy AND a valid float: it survives
    every `if ts:` guard downstream while meaning 1970, i.e. an event that can
    never be recent enough to fire.  No parsed `ts` may be 0.0 — a row whose
    timestamp could not be parsed is dropped, never zero-stamped.

    THREE addresses, because this test drives two fetchers: `fetch_dev_activity`
    GETs the dev and ops pages, and `fetch_channel_txs` GETs the announce
    address.  A missing entry does not degrade to `None` here — the handler
    raises `AssertionError`, which is neither an `httpx.HTTPError` nor a
    `ValueError`, so `_get_json` lets it through and MockTransport re-raises it
    verbatim (httpx 0.28.1): the test errors instead of sweeping anything.
    """
    handler = _blockscout_handler({
        A.DEV_WALLET: [load_fixture("dev_txs_page1.json")],
        A.OPS_WALLET: [load_fixture("ops_txs_page1.json")],
        A.ANNOUNCE: [load_fixture("announce_txs_page1.json")],
    })
    async with _client_on(RecordingTransport(handler)) as client:
        rows = await client.fetch_dev_activity()
        channel = await client.fetch_channel_txs()

    # All 21 announce rows and all 80 dev/ops rows carry a real Blockscout
    # timestamp, so every surviving row must clear the 2020-09 floor.
    assert rows and channel
    for row in [*rows, *channel]:
        assert row.ts > 1_600_000_000.0, row


def test_every_log_group_is_a_tuple_never_none():
    """WP0 froze the four groups as tuple[dict, ...]; WP4 iterates them.

    This pins only the container — a `None` reaching a `for` loop in the
    manager is the failure it prevents.  The *contents* are pinned by
    WP1.9b's hand-over tests.
    """
    from maxpane_dashboard.data.surf_models import LogWindow as _LW

    window = _LW(from_block=1, to_block=2)
    for name in ("bridge_mints", "identity_updates",
                 "v4_initializes", "seaport_sales"):
        assert getattr(window, name) == ()


def test_degradation_signals_are_part_of_the_clients_contract():
    """``channel_truncated`` / ``activity_truncated`` / ``log_group_failed``
    exist so WP4 can surface a degraded state (their own docstrings say so).
    This pins their presence, falsy defaults and types on a FRESHLY
    constructed client — no fetch has run — and pins ``log_group_failed``'s
    keys against ``LogWindow``'s ACTUAL dataclass field names, not a
    hardcoded list, so a later refactor that quietly renames or drops one of
    the four groups fails HERE instead of leaving the manager reading an
    attribute that no longer exists.
    """
    import dataclasses

    from maxpane_dashboard.data.surf_models import LogWindow as _LW

    client = _raising_client()  # constructed only — no request may be issued

    assert client.channel_truncated is False
    assert isinstance(client.channel_truncated, bool)
    assert client.activity_truncated is False
    assert isinstance(client.activity_truncated, bool)

    assert isinstance(client.log_group_failed, dict)
    assert client.log_group_failed, "must have the four groups, not be empty"
    assert all(v is False for v in client.log_group_failed.values())
    assert all(isinstance(v, bool) for v in client.log_group_failed.values())

    log_window_group_fields = {
        f.name for f in dataclasses.fields(_LW)
        if f.name not in ("from_block", "to_block")
    }
    assert set(client.log_group_failed) == log_window_group_fields


# ---------------------------------------------------------------------------
# Task 5 — fetch_launchpad and fetch_decoy_pool_count
#
# Fixtures live under tests/fixtures/surf/launchpad/ (a dedicated
# subdirectory, per test_the_fixtures_root_holds_directories_only), and were
# generated from the ground-truth values read live on 2026-08-23: coinCount =
# 146, imdToBurn = 15.062422197243027626 IMD, totalRealImd =
# 20,577.661206302839565537 IMD, burnFeeBps = 50, creatorFeeBps = 50,
# totalCreatorEthOwed = 0.074934283907946169 ETH, executor tokenBalance =
# 953674883767 wei, minBridgeAmount = 0.
# ---------------------------------------------------------------------------

LAUNCHPAD_FIXTURES = Path(__file__).parent.parent / "fixtures" / "surf" / "launchpad"


def _load_launchpad(name: str) -> Any:
    with open(LAUNCHPAD_FIXTURES / name) as fh:
        return json.load(fh)


def _word(v: int) -> str:
    return "0x" + _encode_uint(v)


def _client_with_canned_calls(
    calls: dict[tuple[str, str], str], *, head_block: int = 30_000_000,
) -> SurfClient:
    """A client whose ``eth_call`` aggregate3 sub-calls answer only *calls*
    (keyed lowercase ``(target, selector)`` -> a raw return word); every
    other sub-call reverts ``(False, "0x")``, mirroring ``_chain_state_subcall``.
    ``eth_blockNumber`` answers *head_block*; ``eth_getLogs`` answers an
    empty list -- the minimal double for a test that only cares about one
    getter's representable-zero contract, not the log sweep.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "eth_blockNumber":
            return httpx.Response(200, json=_rpc_ok(payload, hex(head_block)))
        if payload["method"] == "eth_getLogs":
            return httpx.Response(200, json=_rpc_ok(payload, []))
        assert payload["method"] == "eth_call"
        call = payload["params"][0]
        assert call["to"].lower() == surf_client.MULTICALL3.lower()
        inner = decode_aggregate3_calldata(call["data"])
        results = [
            (True, calls[(t.lower(), cd[:10].lower())])
            if (t.lower(), cd[:10].lower()) in calls else (False, "0x")
            for (t, _allow, cd) in inner
        ]
        result = encode_aggregate3_result(results)
        return httpx.Response(200, json=_rpc_ok(payload, result))

    return _client_on(httpx.MockTransport(handler))


def _client_with_canned_logs(
    rows: list[dict], *, head_block: int | None = None,
) -> SurfClient:
    """A client whose LOGS pool answers ``eth_getLogs`` with *rows*
    (real position-aware topic matching via ``_topics_match``) and
    ``eth_blockNumber`` with a head safely above every row's own block. Does
    not answer ``eth_call`` at all -- for tests that exercise exactly one
    getLogs sweep and never touch the state pool.
    """
    if head_block is None:
        head_block = max(
            (int(r.get("blockNumber", "0x0"), 16) for r in rows), default=0
        ) + 1000

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "eth_blockNumber":
            return httpx.Response(200, json=_rpc_ok(payload, hex(head_block)))
        assert payload["method"] == "eth_getLogs", payload["method"]
        flt = payload["params"][0]
        matched = [r for r in rows if _topics_match(r["topics"], flt["topics"])]
        return httpx.Response(200, json=_rpc_ok(payload, matched))

    return _client_on(httpx.MockTransport(handler))


def _launchpad_fixture_handler(
    reads: dict, logs_data: dict, prices_by_pool_id: dict[str, int],
) -> Callable[[httpx.Request], httpx.Response]:
    """The full launchpad-tier double: eight getters, three log sweeps
    (keyed by their filter's ``topics[0]``) and the follow-up
    ``spotPriceEthPerCoin`` round for whichever rows ``fetch_launchpad``
    decides to price.
    """
    sel_to_key = {
        A.SEL_IMD_TO_BURN.lower(): "imd_to_burn_wei",
        A.SEL_TOTAL_REAL_IMD.lower(): "total_real_imd_wei",
        A.SEL_BURN_FEE_BPS.lower(): "burn_fee_bps",
        A.SEL_CREATOR_FEE_BPS.lower(): "creator_fee_bps",
        A.SEL_TOTAL_CREATOR_ETH_OWED.lower(): "creator_eth_owed_wei",
        A.SEL_COIN_COUNT.lower(): "coin_count",
        A.SEL_TOKEN_BALANCE.lower(): "executor_balance_wei",
        A.SEL_MIN_BRIDGE_AMOUNT.lower(): "min_bridge_wei",
    }
    logs_by_topic0 = {
        A.TOPIC_LAUNCHED: logs_data["launched"],
        A.TOPIC_CURVE_SWAP: logs_data["curve_swap"],
        A.TOPIC_IMD_BURNED: logs_data["imd_burned"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        if method == "eth_blockNumber":
            return httpx.Response(
                200, json=_rpc_ok(payload, hex(logs_data["head_block"]))
            )
        if method == "eth_getLogs":
            flt = payload["params"][0]
            topic0 = flt["topics"][0]
            return httpx.Response(
                200, json=_rpc_ok(payload, logs_by_topic0.get(topic0, []))
            )
        assert method == "eth_call", method
        call = payload["params"][0]
        assert call["to"].lower() == surf_client.MULTICALL3.lower()
        inner = decode_aggregate3_calldata(call["data"])
        results: list[tuple[bool, str]] = []
        for _target, _allow, cd in inner:
            sel = cd[:10].lower()
            if sel == A.SEL_SPOT_PRICE_ETH_PER_COIN.lower():
                pool_id = "0x" + cd[10:]
                price = prices_by_pool_id.get(pool_id)
                results.append(
                    (True, _word(price)) if price is not None else (False, "0x")
                )
                continue
            key = sel_to_key.get(sel)
            value = reads.get(key) if key else None
            results.append((True, _word(value)) if value is not None else (False, "0x"))
        result = encode_aggregate3_result(results)
        return httpx.Response(200, json=_rpc_ok(payload, result))

    return handler


@pytest.mark.asyncio
async def test_launchpad_fetch_never_touches_the_network_in_tests() -> None:
    """Every request this method makes must route through the injected
    transport -- proven by handing it one that raises on any dispatch, the
    same technique the whole suite relies on for "no test touches the
    network" (CLAUDE.md hard constraint 3). ``fetch_launchpad`` genuinely
    does issue requests, so the raise from ``_raising_client``'s double must
    propagate straight out, exactly as its own module docstring describes.
    """
    async with _raising_client() as client:
        with pytest.raises(AssertionError):
            await client.fetch_launchpad()


@pytest.mark.asyncio
async def test_zero_accrued_imd_is_zero_not_none() -> None:
    """A representable zero: 'we looked, nothing accrued'."""
    async with _client_with_canned_calls(
        {(A.LAUNCHPAD_HOOK.lower(), A.SEL_IMD_TO_BURN.lower()): _word(0)}
    ) as client:
        state = await client.fetch_launchpad()
    assert state.imd_to_burn_wei == 0
    # every other getter was never provided by the double -> a real failure,
    # never a zero borrowed from the one leg that WAS provided.
    assert state.total_real_imd_wei is None
    assert state.coin_count is None
    assert state.executor_balance_wei is None


@pytest.mark.asyncio
async def test_fetch_launchpad_total_outage_still_returns_a_labelled_state() -> None:
    """Unlike most fetchers, total outage is NOT a bare ``None`` here: the
    launchpad is real, so the honest degraded state is an all-``None``-fielded
    ``LaunchpadState`` with an empty coin tuple -- the same contract
    ``fetch_pool_v4`` already keeps."""
    async with _offline_client() as client:
        state = await client.fetch_launchpad()
    assert state.coin_count is None
    assert state.imd_to_burn_wei is None
    assert state.total_real_imd_wei is None
    assert state.burn_fee_bps is None
    assert state.creator_fee_bps is None
    assert state.creator_eth_owed_wei is None
    assert state.executor_balance_wei is None
    assert state.min_bridge_wei is None
    assert state.coins == ()
    assert state.swap_count is None
    assert state.trader_count is None
    assert state.burned_total_wei is None
    # Fix round 2: mirrors `all_swaps` -- the CurveSwap sweep itself failed,
    # so the full distribution is exactly as unread as the capped one.
    assert state.swaps_by_coin is None


@pytest.mark.asyncio
async def test_fetch_launchpad_ranks_and_decodes_the_real_fixture() -> None:
    """End to end off the committed fixtures: getters, three log sweeps and
    the price-of-rendered-rows round.  The hostile ``[/x]`` ticker and its
    markup-laden name flow through RAW -- escaping is Task 11's job, never
    this layer's.
    """
    reads = _load_launchpad("launchpad_reads.json")
    logs_data = _load_launchpad("launchpad_logs.json")
    launches = [surf_client._decode_launched_log(r) for r in logs_data["launched"]]
    assert all(l is not None for l in launches)
    # A synthetic price per launched coin so the follow-up round is
    # exercised end to end and not just left at None.
    prices = {l["pool_id"]: 5_000_000_000_000 + i for i, l in enumerate(launches)}

    handler = _launchpad_fixture_handler(reads, logs_data, prices)
    transport = RecordingTransport(handler)
    async with _client_on(transport, now_fn=lambda: 2_000_000_000.0) as client:
        state = await client.fetch_launchpad()

    # The eight getters, verbatim off the fixture (ground truth 2026-08-23).
    assert state.coin_count == reads["coin_count"]
    assert state.imd_to_burn_wei == reads["imd_to_burn_wei"]
    assert state.total_real_imd_wei == reads["total_real_imd_wei"]
    assert state.burn_fee_bps == reads["burn_fee_bps"]
    assert state.creator_fee_bps == reads["creator_fee_bps"]
    assert state.creator_eth_owed_wei == reads["creator_eth_owed_wei"]
    assert state.executor_balance_wei == reads["executor_balance_wei"]
    assert state.min_bridge_wei == reads["min_bridge_wei"]

    # Lifetime aggregates, decoded from all 25 CurveSwap rows (24 attributed
    # + 1 whose poolId matches no launch, still counted here per fix round 1
    # point 7) and all 3 ImdBurned rows -- independent of the 1h window.
    assert state.swap_count == 25
    assert state.trader_count == 12
    assert state.burned_total_wei == 3_299_000_000_000_000_000  # 3,299 IMD

    # Ranking: ICE has 9 in-window swaps, the most of any coin. Attribution
    # is by poolId (CurveSwap carries no coin-address field at all -- fix
    # round 1), never by a field that happens to hold an address.
    tickers = [c.ticker for c in state.coins]
    assert None not in tickers          # the unattributed swap never ranks
    assert tickers[0] == "ICE"
    ice = state.coins[0]
    assert ice.swaps_1h == 9
    # Fix round 2: the full distribution agrees with the rendered row for a
    # ticker both cover -- same sweep, two independent counters, and this is
    # the one fixture-backed proof they never drift apart.
    assert state.swaps_by_coin["ICE"] == ice.swaps_1h == 9
    ice_pool_id = next(l["pool_id"] for l in launches if l["ticker"] == "ICE")
    assert ice.price_eth == pytest.approx(prices[ice_pool_id] / 1e18)
    assert ice.age_s == pytest.approx(
        (logs_data["head_block"] - 26_022_000) * 12.0
    )
    # change_1h_pct is derived from logs alone (ethAmount/coinAmount, first
    # vs last in-hour swap for that coin) -- no price field exists on the
    # real CurveSwap event. ICE's swaps rise; DAOs' two swaps are flat.
    assert ice.change_1h_pct == pytest.approx(7.272727272726032)
    daos = next(c for c in state.coins if c.ticker == "DAOs")
    assert daos.change_1h_pct == pytest.approx(0.0)   # a measured flat hour
    k256 = next(c for c in state.coins if c.ticker == "K-256")
    assert k256.change_1h_pct is None                 # one swap: unmeasurable

    # The hostile ticker exists in the fixture and survives completely raw:
    # no escaping happens at this layer (Task 11 owns that, at render time).
    assert "[/x]" in tickers
    hostile = next(c for c in state.coins if c.ticker == "[/x]")
    assert hostile.name == "[bold red]hostile[/]"


@pytest.mark.asyncio
async def test_fetch_launchpad_uses_the_standing_pool_split() -> None:
    """State calls go to publicnode; every ``eth_getLogs`` (and the logs
    pool's own ``eth_blockNumber``) goes to tenderly/drpc."""
    reads = _load_launchpad("launchpad_reads.json")
    logs_data = _load_launchpad("launchpad_logs.json")
    handler = _launchpad_fixture_handler(reads, logs_data, {})
    transport = RecordingTransport(handler)
    async with _client_on(transport, now_fn=lambda: 2_000_000_000.0) as client:
        await client.fetch_launchpad()

    calls = [(u, p.get("method")) for (u, _m, p) in transport.requests if p]
    state_urls = [u for u, m in calls if m == "eth_call"]
    logs_urls = [u for u, m in calls if m in ("eth_getLogs", "eth_blockNumber")]
    assert state_urls, "no eth_call requests recorded"
    assert logs_urls, "no logs-pool requests recorded"
    assert all("publicnode" in u for u in state_urls)
    assert all("publicnode" not in u for u in logs_urls)


@pytest.mark.asyncio
async def test_decoy_count_excludes_the_real_pool() -> None:
    """38 Initialize logs, one of which is the live pool: 37 decoys."""
    rows = _load_launchpad("v4_initializes.json")["rows"]
    async with _client_with_canned_logs(rows) as client:
        count, newest = await client.fetch_decoy_pool_count(
            real_pool_id=A.POOL_V4_ID_FALLBACK
        )
    assert count == 37
    assert newest["fee"] == 80000


@pytest.mark.asyncio
async def test_decoy_count_zero_decoys_is_representable_not_none() -> None:
    """We looked, and the only Initialize log was the real pool: 0, not
    unknown."""
    real = A.POOL_V4_ID_FALLBACK
    only_real = [
        row for row in _load_launchpad("v4_initializes.json")["rows"]
        if str(row["topics"][1]).lower() == real.lower()
    ]
    assert only_real  # sanity: the fixture really does contain the real row
    async with _client_with_canned_logs(only_real) as client:
        count, newest = await client.fetch_decoy_pool_count(real_pool_id=real)
    assert count == 0
    assert newest is None


@pytest.mark.asyncio
async def test_fetch_decoy_pool_count_total_outage_is_none_none() -> None:
    async with _offline_client() as client:
        count, newest = await client.fetch_decoy_pool_count(
            real_pool_id=A.POOL_V4_ID_FALLBACK
        )
    assert count is None
    assert newest is None


@pytest.mark.asyncio
async def test_fetch_decoy_pool_count_filters_currency1_equals_imd() -> None:
    """The filter is exact: TOPIC_V4_INITIALIZE, currency1 == IMD -- not
    currency0, and not left as a wildcard."""
    rows = _load_launchpad("v4_initializes.json")["rows"]

    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "eth_blockNumber":
            return httpx.Response(200, json=_rpc_ok(payload, hex(26_100_000)))
        assert payload["method"] == "eth_getLogs"
        flt = payload["params"][0]
        assert flt["address"].lower() == A.POOL_MANAGER_V4.lower()
        assert flt["topics"][0] == A.TOPIC_V4_INITIALIZE
        assert flt["topics"][1] is None
        assert flt["topics"][2] is None
        assert flt["topics"][3].lower() == _addr_topic(A.IMD_TOKEN)
        matched = [r for r in rows if _topics_match(r["topics"], flt["topics"])]
        return httpx.Response(200, json=_rpc_ok(payload, matched))

    transport = RecordingTransport(_handler)
    async with _client_on(transport) as client:
        count, _newest = await client.fetch_decoy_pool_count(
            real_pool_id=A.POOL_V4_ID_FALLBACK
        )
    assert count == 37


# ---------------------------------------------------------------------------
# Task 5 fix round 1 (2026-08-24) — CurveSwap has no coin-address field
#
# The original guess read topics[2] as a coin address; the real, verified
# LaunchpadHook ABI has NO such field at all (topics[2] is trader, topics[3]
# is router). Attribution to a launched coin was, and remains, done by
# joining CurveSwap.poolId against the Launched sweep -- this test is the
# assertion the OLD fixture could never fail, because it was generated from
# the same wrong assumption the decoder held.
# ---------------------------------------------------------------------------


def _minimal_launched_row(pool_id: str, creator: str, name: str, ticker: str,
                           block: int) -> dict:
    def _str_enc(s: str) -> str:
        b = s.encode("utf-8")
        data_hex = b.hex()
        padded = data_hex + "0" * ((64 - (len(data_hex) % 64)) % 64 if data_hex else 0)
        return _encode_uint(len(b)) + padded

    name_enc, ticker_enc = _str_enc(name), _str_enc(ticker)
    name_off = 4 * 32
    ticker_off = name_off + len(name_enc) // 2
    data = (
        "0x" + _encode_uint(name_off) + _encode_uint(ticker_off)
        + _encode_uint(10**27) + _encode_uint(6695853418114)
        + name_enc + ticker_enc
    )
    return {
        "address": A.LAUNCHPAD_FACTORY.lower(),
        "topics": [A.TOPIC_LAUNCHED, pool_id, _addr_topic("0x" + "ca" * 20),
                   _addr_topic(creator)],
        "data": data,
        "blockNumber": hex(block),
        "transactionHash": "0x" + "01" * 32,
    }


def _minimal_curve_swap_row(pool_id: str, trader: str, router: str,
                             block: int, tx: int) -> dict:
    data = (
        "0x" + _encode_uint(1)                 # buy
        + _encode_uint(6695853418114)           # ethAmount
        + _encode_uint(66958534181140)          # imdAmount
        + _encode_uint(10**18)                  # coinAmount
        + _encode_uint(33_000_000_000)          # creatorFeeEth
        + _encode_uint(330_000_000)             # burnFeeImd
    )
    return {
        "address": A.LAUNCHPAD_HOOK.lower(),
        "topics": [A.TOPIC_CURVE_SWAP, pool_id, _addr_topic(trader),
                   _addr_topic(router)],
        "data": data,
        "blockNumber": hex(block),
        "transactionHash": "0x" + f"{tx:064x}",
    }


@pytest.mark.asyncio
async def test_a_curve_swap_is_attributed_by_pool_id_and_an_unknown_pool_id_is_skipped() -> None:
    """A CurveSwap whose poolId matches a launched coin increments that
    coin's swaps_1h; one whose poolId matches nothing is skipped -- never
    crashes the rank -- and still counts toward the lifetime swap total.
    """
    reads = _load_launchpad("launchpad_reads.json")
    head = 30_000_000
    pid_foo = "0x" + "11" * 32
    pid_unknown = "0x" + "99" * 32

    logs_data = {
        "head_block": head,
        "launched": [
            _minimal_launched_row(pid_foo, A.DEV_WALLET, "Foo Coin", "FOO",
                                   head - 1000),
        ],
        "curve_swap": [
            _minimal_curve_swap_row(pid_foo, "0x" + "aa" * 20, "0x" + "bb" * 20,
                                     head - 100, 1),
            _minimal_curve_swap_row(pid_foo, "0x" + "cc" * 20, "0x" + "bb" * 20,
                                     head - 50, 2),
            # Matches no Launched row at all -- must be skipped from the
            # rank, not raise, and still count in the lifetime total.
            _minimal_curve_swap_row(pid_unknown, "0x" + "dd" * 20, "0x" + "bb" * 20,
                                     head - 30, 3),
        ],
        "imd_burned": [],
    }
    handler = _launchpad_fixture_handler(reads, logs_data, {})
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_launchpad()  # must not raise

    assert [c.ticker for c in state.coins] == ["FOO"]
    assert state.coins[0].swaps_1h == 2       # only the two matched swaps
    assert state.swap_count == 3              # all three, incl. the unknown one
    assert state.trader_count == 3            # 0xaa.., 0xcc.., 0xdd.. all distinct


# ---------------------------------------------------------------------------
# Fix round 2 (2026-08-24) -- swaps_by_coin must be the FULL population, not
# the LAUNCHPAD_RENDER_LIMIT-capped slice `coins` carries. hot_coin_threshold
# takes a median, and a median of only the busiest 20 coins runs several
# times too high -- this is the test that would catch feeding it the wrong
# distribution, which every test above (built from small, sub-cap fixtures)
# cannot.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swaps_by_coin_is_the_full_population_not_the_rendered_cap() -> None:
    """20 coins get 8 in-window swaps each (more than the render cap of 20
    coins can hold once the 25 quiet ones are added); 25 more get exactly 1
    each. 45 active coins total -- comfortably over ``LAUNCHPAD_RENDER_LIMIT``
    (20), so the render cap genuinely bites and only the 20 hot coins survive
    into ``state.coins``.

    The true population median is 1 (25 of 45 coins have exactly one swap),
    giving a threshold at the floor (5). The median of just the rendered
    top 20 (all eights) is 8, giving a threshold of 24 -- the exact
    "threshold near 24 instead of near the floor of 5" the fix-round-2
    controller message described. This test asserts the correct, full-
    population number is what ``LaunchpadState.swaps_by_coin`` actually
    carries, and separately proves the capped list -- fix round 1's bug --
    would have produced the wrong one.
    """
    from maxpane_dashboard.analytics.surf_launchpad import hot_coin_threshold

    reads = _load_launchpad("launchpad_reads.json")
    head = 30_000_000
    launched_block = head - 1000     # outside the hour window; Launched
                                      # doesn't need to be inside it
    swap_block = head - 10           # comfortably inside LAUNCHPAD_HOUR_BLOCKS

    launched_rows: list[dict] = []
    curve_swap_rows: list[dict] = []
    tx = 0
    for i in range(20):
        pool_id = "0x" + format(i + 1, "064x")
        ticker = f"HOT{i}"
        launched_rows.append(
            _minimal_launched_row(
                pool_id, A.DEV_WALLET, ticker, ticker, launched_block
            )
        )
        for _ in range(8):
            tx += 1
            trader = "0x" + format(tx, "040x")
            curve_swap_rows.append(
                _minimal_curve_swap_row(
                    pool_id, trader, "0x" + "bb" * 20, swap_block, tx
                )
            )
    for i in range(25):
        pool_id = "0x" + format(i + 101, "064x")
        ticker = f"QUIET{i}"
        launched_rows.append(
            _minimal_launched_row(
                pool_id, A.DEV_WALLET, ticker, ticker, launched_block
            )
        )
        tx += 1
        trader = "0x" + format(tx, "040x")
        curve_swap_rows.append(
            _minimal_curve_swap_row(pool_id, trader, "0x" + "bb" * 20, swap_block, tx)
        )

    logs_data = {
        "head_block": head,
        "launched": launched_rows,
        "curve_swap": curve_swap_rows,
        "imd_burned": [],
    }
    handler = _launchpad_fixture_handler(reads, logs_data, {})
    async with _client_on(RecordingTransport(handler)) as client:
        state = await client.fetch_launchpad()

    # The render cap genuinely bites: 45 active coins, only 20 rendered.
    assert len(state.coins) == 20
    assert {c.swaps_1h for c in state.coins} == {8}
    assert all(c.ticker.startswith("HOT") for c in state.coins)

    # The full population is what LaunchpadState carries, not the 20 rendered.
    assert state.swaps_by_coin is not None
    assert len(state.swaps_by_coin) == 45
    assert sum(1 for v in state.swaps_by_coin.values() if v == 8) == 20
    assert sum(1 for v in state.swaps_by_coin.values() if v == 1) == 25

    full_threshold = hot_coin_threshold(state.swaps_by_coin)
    capped_threshold = hot_coin_threshold(
        {c.ticker: c.swaps_1h for c in state.coins}
    )
    assert full_threshold == 5        # the floor: true median is 1
    assert capped_threshold == 24     # the fix-round-1 bug, reproduced
    assert full_threshold < capped_threshold, (
        "the full-population threshold must be materially lower than the "
        "one a render-capped distribution would have produced"
    )
