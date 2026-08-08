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
async def test_fetch_chain_state_total_outage_returns_none():
    async with _offline_client() as client:
        assert await client.fetch_chain_state() is None
