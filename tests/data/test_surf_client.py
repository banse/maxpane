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
