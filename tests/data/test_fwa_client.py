"""Tests for the FWA Pool-A state client.

**Zero network.**  Every test either exercises a pure function or drives the
client through an ``httpx.MockTransport``.  Two doubles enforce it:

* :func:`_raising_client` — a client whose transport raises on *any* request.
  Pure-function tests use it, so a stray ``await`` that reaches the wire fails
  loudly instead of quietly dialling mainnet.
* :class:`SimChain` — a scripted mainnet that decodes real ``aggregate3``
  calldata produced by the client's own encoder, dispatches each sub-call, and
  re-encodes a real ``Result[]``.  Nothing is stubbed at the method level, so
  the encoder, the chunker, the block pinning and the decoder are all under
  test end-to-end.

Fixture-backed assertions come from ``tests/fixtures/fwa/`` (WP-3, live-captured
and block-pinned).  Where a fixture states a number, the test asserts against
the fixture rather than against a literal copied out of prose.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from urllib.parse import urlparse

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.data import fwa_client
from maxpane_dashboard.data.fwa_client import (
    _FALLBACK_RPCS,
    FWA_CORE,
    FWA_HOT_KEYS,
    FWA_REWARDS,
    FWA_WHITELIST,
    HOT_VIEWS,
    MULTICALL3,
    MULTICALL_MAX_CALLS,
    SELECTORS,
    FWAClient,
    ViewSpec,
    _decode_aggregate3_result,
    _decode_int,
    _decode_uint,
    _encode_aggregate3,
    _encode_uint,
    _strip0x,
    check_sweep_invariants,
    decode_listing,
    decode_view_results,
)
from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fwa"


def load_fixture(name: str) -> dict:
    with open(FIXTURES / name) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Transport doubles
# ---------------------------------------------------------------------------


def _no_network(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(
        f"test attempted real network access: {request.method} {request.url}"
    )


def _raising_client() -> FWAClient:
    """A client that cannot reach the network — proves a test stayed offline."""
    return FWAClient(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_no_network)),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
    )


class RecordingTransport(httpx.MockTransport):
    """MockTransport that keeps every ``(url, json_payload)`` it was handed."""

    def __init__(self, handler: Callable[[str, dict], httpx.Response]) -> None:
        self.requests: list[tuple[str, dict]] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.requests.append((str(request.url), payload))
            return handler(str(request.url), payload)

        super().__init__(_wrapped)

    def calls(self, method: str) -> list[dict]:
        return [p for _u, p in self.requests if p.get("method") == method]


def _client_on(transport: httpx.MockTransport, **kw: Any) -> FWAClient:
    return FWAClient(
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0, 0.0),
        **kw,
    )


def _ok(payload: dict, result: Any) -> httpx.Response:
    return httpx.Response(
        200, json={"jsonrpc": "2.0", "id": payload.get("id"), "result": result}
    )


# ---------------------------------------------------------------------------
# ABI helpers the harness needs (calldata decode / result encode)
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


def encode_aggregate3_result(results: list[tuple[bool, str]]) -> str:
    """Encode ``Result[] (bool success, bytes returnData)`` exactly as a node would."""
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
    return (
        "0x"
        + _encode_uint(0x20)
        + _encode_uint(len(tuples))
        + "".join(_encode_uint(o) for o in offsets)
        + "".join(tuples)
    )


def encode_listing(
    *,
    collection: str,
    depositor: str,
    purchaser: str,
    token_id: int,
    weight: int,
    value: int,
    fee_share: int = 1,
    fee_debt: int = 0,
    slot: int = 0,
    allocated_at: int = 0,
    status: int = 1,
) -> str:
    """Encode the flat 11-tuple exactly as ``listings(uint256)`` returns it."""

    def addr(a: str) -> str:
        return _strip0x(a).lower().rjust(64, "0")

    return "0x" + "".join(
        [
            addr(collection),
            addr(depositor),
            addr(purchaser),
            _encode_uint(token_id),
            _encode_uint(weight),
            _encode_uint(value),
            _encode_uint(fee_share),
            _encode_uint(fee_debt),
            _encode_uint(slot),
            _encode_uint(allocated_at),
            _encode_uint(status),
        ]
    )


# ---------------------------------------------------------------------------
# SimChain — a scripted mainnet for the sweep tests
# ---------------------------------------------------------------------------

_ZERO_WORD = "0x" + "0" * 64


class SimChain:
    """A deterministic stand-in for mainnet state at one block."""

    def __init__(
        self,
        *,
        block_number: int,
        backings: list[int],
        slot_map: dict[int, int],
        balance_wei: int = 0,
    ) -> None:
        self.block_number = block_number
        self.balance_wei = balance_wei
        self.slot_map = slot_map  # slot -> listing_id (missing/0 == free-list hole)
        self.backings = backings
        self.listing_backing: dict[int, int] = {}
        self.listing_slot: dict[int, int] = {}
        for i, slot in enumerate(sorted(slot_map)):
            listing_id = slot_map[slot]
            self.listing_backing[listing_id] = backings[i]
            self.listing_slot[listing_id] = slot

        self.total_weight = fwa_ev.total_weight(backings)
        self.weighted_backing_total = fwa_ev.weighted_backing_total(backings)
        self.acquisition_fee = fwa_ev.acquisition_fee_wei(
            self.weighted_backing_total, self.total_weight
        )
        self.active_listing_count = len(backings)

    # -- sub-call dispatch -------------------------------------------------

    def call(self, target: str, calldata: str) -> tuple[bool, str]:
        selector = _strip0x(calldata)[:8]
        arg_hex = _strip0x(calldata)[8:]
        arg = int(arg_hex[:64], 16) if arg_hex else 0
        sel = "0x" + selector

        if sel == SELECTORS["slotToListing(uint256)"]:
            return (True, "0x" + _encode_uint(self.slot_map.get(arg, 0)))
        if sel == SELECTORS["listings(uint256)"]:
            backing = self.listing_backing.get(arg)
            if backing is None:
                return (True, "0x" + "0" * (352 * 2))
            return (
                True,
                encode_listing(
                    collection="0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e",
                    depositor="0x00000000000000000000000000000000000000aa",
                    purchaser="0x" + "0" * 40,
                    token_id=arg,
                    weight=fwa_ev.inverse_weight(backing),
                    value=backing,
                    slot=self.listing_slot[arg],
                ),
            )
        if sel == SELECTORS["activeListingCount()"]:
            return (True, "0x" + _encode_uint(self.active_listing_count))
        if sel == SELECTORS["feeShareTotal()"]:
            return (True, "0x" + _encode_uint(self.active_listing_count))
        if sel == SELECTORS["totalWeight()"]:
            return (True, "0x" + _encode_uint(self.total_weight))
        if sel == SELECTORS["weightedBackingTotal()"]:
            return (True, "0x" + _encode_uint(self.weighted_backing_total))
        if sel == SELECTORS["acquisitionFee()"]:
            return (True, "0x" + _encode_uint(self.acquisition_fee))
        return (False, "0x")

    # -- transport handler -------------------------------------------------

    def handler(self, _url: str, payload: dict) -> httpx.Response:
        method = payload.get("method")
        if method == "eth_blockNumber":
            return _ok(payload, hex(self.block_number))
        if method == "eth_getBalance":
            return _ok(payload, hex(self.balance_wei))
        if method == "eth_gasPrice":
            return _ok(payload, hex(1_000_000_000))
        if method == "eth_call":
            call = payload["params"][0]
            if call["to"].lower() == MULTICALL3:
                inner = decode_aggregate3_calldata(call["data"])
                return _ok(
                    payload,
                    encode_aggregate3_result(
                        [self.call(t, cd) for (t, _allow, cd) in inner]
                    ),
                )
            ok, data = self.call(call["to"], call["data"])
            return _ok(payload, data if ok else "0x")
        raise AssertionError(f"unexpected RPC method {method}")


# ---------------------------------------------------------------------------
# WP-3 smoke
# ---------------------------------------------------------------------------


def test_all_fixtures_have_meta():
    files = sorted(FIXTURES.glob("*.json"))
    assert len(files) >= 20, "WP-3 shipped 21 fixtures"
    for path in files:
        with open(path) as fh:
            data = json.load(fh)
        assert "_meta" in data, f"{path.name} has no _meta block"
        assert data["_meta"].get("keyless") is True, f"{path.name} is not keyless"
        assert data["_meta"].get("captured_at"), f"{path.name} has no capture time"


# ---------------------------------------------------------------------------
# Configuration guards
# ---------------------------------------------------------------------------


def test_no_eth_getlogs_in_this_module():
    """Pool A never queries logs — publicnode gates them behind an archive token.

    A static check, because the failure mode is a *capability probe*: a short
    recent range succeeds on publicnode, the client concludes logs work, and the
    first historical backfill fails (findings §13.10).  The safe rule is that
    the string never appears in this module at all; logs are ``fwa_logs.py``'s
    job.
    """
    source = Path(fwa_client.__file__).read_text()
    assert "getLogs" not in source
    assert "fromBlock" not in source and "toBlock" not in source


def test_endpoint_list_has_no_banned_host():
    client = _raising_client()
    joined = " ".join(client.endpoints)
    for banned in ("llamarpc", "ankr", "alchemy", "infura"):
        assert banned not in joined
    assert client.endpoints[0] == "https://ethereum-rpc.publicnode.com"


def test_banned_host_is_rejected_at_construction():
    with pytest.raises(ValueError, match="banned RPC host"):
        FWAClient(primary_rpc="https://eth.llamarpc.com")
    with pytest.raises(ValueError, match="banned RPC host"):
        FWAClient(fallback_rpcs=["https://rpc.ankr.com/eth"])


def test_selectors_match_vendored_selectors_json():
    """Hardcoded selectors are cross-checked against the WP-2 vendored table."""
    vendored = json.loads(
        (
            Path(fwa_client.__file__).resolve().parents[1]
            / "abis"
            / "fwa"
            / "selectors.json"
        ).read_text()
    )
    for signature, selector in SELECTORS.items():
        assert signature in vendored, f"{signature} missing from selectors.json"
        assert vendored[signature] == selector, signature


def test_hot_views_are_unique_and_cover_all_eight_contracts():
    keys = [v.key for v in HOT_VIEWS]
    assert len(keys) == len(set(keys))
    contracts = {v.contract for v in HOT_VIEWS}
    assert contracts >= {
        "FWA",
        "FWARewards",
        "FWAVRFService",
        "FWAToken",
        "FWATokenHook",
        "FWAWhitelist",
        "Splitter",
    }
    assert set(FWA_HOT_KEYS) >= set(keys)


# ---------------------------------------------------------------------------
# Multicall3 encoding — TRAP 4
# ---------------------------------------------------------------------------


def test_aggregate3_encoding_has_no_0x_in_calldata():
    """The inner ``callData`` must be embedded WITHOUT its ``0x`` prefix.

    Leaving it on puts the literal bytes ``30 78`` in the bytes field and the
    node rejects the whole payload with *"cannot unmarshal invalid hex string
    into Go struct field TransactionArgs.data"* (``rpc_errors.json ->
    multicall3_invalid_hex_callData``).  The fixture's own prescribed check is
    "the finished data string contains '0x' exactly once, at index 0".
    """
    data = _encode_aggregate3(
        [
            (FWA_CORE, SELECTORS["acquisitionFee()"], True),
            (FWA_REWARDS, SELECTORS["hotGap()"], True),
            (FWA_CORE, SELECTORS["listings(uint256)"] + _encode_uint(56508), True),
        ]
    )
    assert data.startswith("0x")
    assert data.count("0x") == 1
    assert "3078" not in data[2:]  # no encoded "0x" characters anywhere

    inner = decode_aggregate3_calldata(data)
    assert [cd for (_t, _a, cd) in inner] == [
        SELECTORS["acquisitionFee()"],
        SELECTORS["hotGap()"],
        SELECTORS["listings(uint256)"] + _encode_uint(56508),
    ]


def test_encode_call3_strips_the_0x_prefix_from_calldata():
    """The stripping is in ``_encode_call3`` itself, not in its callers.

    Copied from ``talismans_client._encode_call3`` where the trap was already
    solved; pinned here so a later "cleanup" cannot reintroduce it.  With the
    prefix left on, the bytes length word would read 0x25 (37) instead of 0x24
    (36) and the body would begin ``3078`` — the ASCII for ``0x``.
    """
    with_prefix = fwa_client._encode_call3(
        FWA_CORE, "0xde74e57b" + _encode_uint(1), True
    )
    without_prefix = fwa_client._encode_call3(
        FWA_CORE, "de74e57b" + _encode_uint(1), True
    )
    assert with_prefix == without_prefix
    assert "3078" not in with_prefix
    # length word sits at offset 3 (target, allowFailure, bytes-offset)
    assert int(with_prefix[3 * 64 : 4 * 64], 16) == 36  # 4-byte selector + 1 word


def test_aggregate3_encoding_matches_live_captured_calldata():
    """Bit-for-bit against three live-captured ``aggregate3`` payloads."""
    positions = load_fixture("aggregate3_positions.json")
    inner = decode_aggregate3_calldata(positions["request"]["params"][0]["data"])
    rebuilt = _encode_aggregate3([(t, cd, a) for (t, a, cd) in inner])
    assert rebuilt.lower() == positions["request"]["params"][0]["data"].lower()

    slots = load_fixture("aggregate3_slots.json")
    for batch in slots["batches"]:
        calls = [
            (FWA_CORE, SELECTORS["slotToListing(uint256)"] + _encode_uint(s), True)
            for s in range(batch["start_slot"], batch["start_slot"] + batch["count"])
        ]
        assert (
            _encode_aggregate3(calls).lower()
            == batch["request"]["params"][0]["data"].lower()
        )

    hot = load_fixture("hot_batch.json")
    calls = [(c["address"], c["selector"], c["allowFailure"]) for c in hot["calls"]]
    assert (
        _encode_aggregate3(calls).lower()
        == hot["request"]["params"][0]["data"].lower()
    )


def test_aggregate3_decode_handles_failed_call():
    """An ``allowFailure`` miss keeps its slot; it must not shift the batch."""
    fixture = load_fixture("aggregate3_positions.json")
    decoded = _decode_aggregate3_result(fixture["raw_return_data"])
    expected = fixture["expected_decoded"]["elements"]

    assert len(decoded) == len(expected) == 5
    assert [ok for ok, _ in decoded] == fixture["expected_decoded"]["success_flags"]

    # index 2 is the deliberate miss: acquisitionsEnabled() does not exist.
    assert decoded[2] == (False, "0x")
    assert fixture["calls"][2]["expect_success"] is False

    # The three real listings after it are still aligned with their ids.
    for element in expected:
        if not element["success"]:
            continue
        ok, data = decoded[element["index"]]
        assert ok
        assert data.lower() == element["returnData"].lower()
        position = decode_listing(data, element["listingId"])
        assert position is not None
        assert position.listing_id == element["listingId"]


async def test_aggregate3_chunking_never_exceeds_500():
    """A 1,203-call request is split into chunks of at most 500, in order."""
    seen: list[int] = []

    def handler(_url: str, payload: dict) -> httpx.Response:
        inner = decode_aggregate3_calldata(payload["params"][0]["data"])
        seen.append(len(inner))
        return _ok(
            payload,
            encode_aggregate3_result(
                [(True, "0x" + _encode_uint(int(_strip0x(cd)[8:] or "0", 16)))
                 for (_t, _a, cd) in inner]
            ),
        )

    transport = RecordingTransport(handler)
    client = _client_on(transport)
    calls = [
        (FWA_CORE, SELECTORS["slotToListing(uint256)"] + _encode_uint(i))
        for i in range(1, 1204)
    ]
    results = await client._multicall(calls)

    assert seen == [500, 500, 203]
    assert max(seen) <= MULTICALL_MAX_CALLS
    assert len(results) == 1203
    # order preserved across chunk boundaries
    assert [_decode_uint(d) for _ok_, d in results] == list(range(1, 1204))


# ---------------------------------------------------------------------------
# Hot batch decoding
# ---------------------------------------------------------------------------


def _views_from_fixture(hot: dict) -> list[ViewSpec]:
    """Build a view list matching the fixture's captured call order."""
    kinds = {
        "symbol()": "string",
        "token()": "address",
        "ttt()": "address",
        "NFT_ADDRESS()": "address",
        "externalBuysEnabled()": "bool",
        "forcedTokenShareBps()": "int",
    }
    views = []
    for call in hot["calls"]:
        signature = call["signature"]
        assert signature in SELECTORS, f"{signature} missing from fwa_client.SELECTORS"
        assert SELECTORS[signature] == call["selector"]
        views.append(
            ViewSpec(
                key=signature,
                contract=call["contract"],
                signature=signature,
                kind=kinds.get(signature, "uint"),
            )
        )
    return views


def test_hot_batch_decodes_all_views():
    """Decode the live-captured 36-view batch and cross-check the aggregates."""
    hot = load_fixture("hot_batch.json")
    views = _views_from_fixture(hot)
    results = _decode_aggregate3_result(hot["raw_return_data"])
    assert len(results) == len(views) == hot["_meta"]["view_count"]

    values, failed = decode_view_results(views, results)
    assert failed == []

    pinned = load_fixture("pinned_aggregates.json")["README"][
        f"block_{hot['_meta']['block_number']}"
    ]
    assert values["acquisitionFee()"] == pinned["acquisitionFee"]
    assert values["totalWeight()"] == pinned["totalWeight"]
    assert values["weightedBackingTotal()"] == pinned["weightedBackingTotal"]
    assert values["activeListingCount()"] == pinned["activeListingCount"]
    assert values["feeShareTotal()"] == pinned["feeShareTotal"]
    assert values["topListingId()"] == pinned["topListingId"]
    assert values["topListingPot()"] == pinned["topListingPot"]

    # feeShareTotal == activeListingCount: feeShare is 1 per position and fees
    # split EQUALLY.  The Listing struct's "sqrt(backing)" comment is stale
    # (findings §13.2) — this is the free runtime invariant that settles it.
    assert values["feeShareTotal()"] == values["activeListingCount()"]

    # settlementDiscountBps is the purchaser PAYOUT rate (85%), not a discount.
    assert values["settlementDiscountBps()"] == 8500
    assert values["BPS()"] == 10_000

    # Non-uint kinds
    assert values["symbol()"] == "FWA"
    assert values["externalBuysEnabled()"] is False
    assert values["token()"] == "0xa0df17b5ac76ababa36e1450e2cbcd18a620c845"
    assert values["ttt()"] == "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"

    # The crown tithe is live 100 bps, not the documented 500 — read, never
    # hardcoded (PRD §7 rule 6).
    assert values["topListingShareBps()"] == 100
    assert values["topThresholdBps()"] == 1000


def test_forced_token_share_bps_decodes_negative_one():
    """``forcedTokenShareBps()`` is a SIGNED int256; -1 means "dynamic"."""
    hot = load_fixture("hot_batch.json")
    idx = next(
        c["index"] for c in hot["calls"] if c["signature"] == "forcedTokenShareBps()"
    )
    _ok_flag, raw = _decode_aggregate3_result(hot["raw_return_data"])[idx]
    assert _strip0x(raw) == "f" * 64

    assert _decode_int(raw) == -1
    # Decoding it unsigned yields 2**256-1, which is a decode bug, not a share.
    assert _decode_uint(raw) == 2**256 - 1
    assert _decode_uint(raw) != _decode_int(raw)

    spec = next(v for v in HOT_VIEWS if v.key == "forced_token_share_bps")
    assert spec.kind == "int"
    values, _failed = decode_view_results([spec], [(True, raw)])
    assert values["forced_token_share_bps"] == -1


def test_decode_view_results_failure_is_none_not_zero():
    """A failed read must be ``None``: several of these views legitimately read 0."""
    specs = [
        next(v for v in HOT_VIEWS if v.key == "ttt_amount"),
        next(v for v in HOT_VIEWS if v.key == "last_buyback_block"),
    ]
    values, failed = decode_view_results(specs, [(False, "0x"), (True, _ZERO_WORD)])
    assert values["ttt_amount"] is None  # read failed
    assert values["last_buyback_block"] == 0  # genuinely zero: no buyback ever ran
    assert failed == ["ttt_amount"]


async def test_hot_batch_returns_full_key_set_even_when_dead():
    """Every key in ``FWA_HOT_KEYS``, always — a dead source flips ``_ok``."""

    def dead(_url: str, _payload: dict) -> httpx.Response:
        return httpx.Response(503, text="down")

    client = _client_on(RecordingTransport(dead))
    out = await client.fetch_hot_batch()
    assert set(out) == set(FWA_HOT_KEYS)
    assert out["_ok"] is False
    assert out["acquisition_fee"] is None
    assert len(out["_failed"]) >= len(HOT_VIEWS)


# ---------------------------------------------------------------------------
# listings() decoding
# ---------------------------------------------------------------------------


def test_listings_decode_bit_exact():
    """All 11 fields of the largest position (221 ETH) from live-captured bytes."""
    fixture = load_fixture("listings_56508.json")
    raw = fixture["raw_return_data"]
    assert len(_strip0x(raw)) // 2 == fixture["raw_return_byte_length"] == 352

    expected = fixture["expected_decoded"]
    position = decode_listing(raw, fixture["_meta"]["listing_id"])
    assert position is not None

    assert position.listing_id == 56508
    assert position.collection == expected["collection"].lower()
    assert position.depositor == expected["depositor"].lower()
    # allocatee: on-chain address(0) is normalised to None so no widget can
    # render 0x0000... as a purchaser.  The struct field is `purchaser` in
    # source (findings §13.4); the model-side name is deliberate.
    assert expected["allocatee"] == "0x" + "0" * 40
    assert position.allocatee is None
    assert position.token_id == expected["tokenId"]
    assert position.weight == expected["weight"]
    assert position.backing_wei == expected["value"]
    assert position.fee_share == expected["feeShare"] == 1
    assert position.fee_debt == expected["feeDebt"]
    assert position.slot == expected["slot"]
    assert position.allocated_at == expected["allocatedAt"]
    assert position.status == expected["status"] == 1

    # Weight is INVERSE to backing: 1e36 // value, exact.
    assert fixture["invariant"]["holds"] is True
    assert position.weight == fwa_ev.inverse_weight(position.backing_wei)
    assert position.backing_wei == 221 * 10**18

    # Same listing 46 blocks earlier.
    #
    # DISCREPANCY, recorded deliberately: the fixture's cross-check note says
    # "value/weight/slot unchanged, feeDebt drifts", but the two captured
    # payloads are byte-identical, so feeDebt did NOT move between blocks
    # 25612655 and 25612701 for this listing.  The pinned aggregates *did* move
    # over those 46 blocks (acquisitionFee -568250870717417 wei), so the block
    # pinning rule is unaffected — only the note is wrong.  Asserting what the
    # bytes actually say keeps the test honest.
    earlier_raw = fixture["cross_check_block_25612655"]["raw_return_data"]
    earlier = decode_listing(earlier_raw, 56508)
    assert earlier is not None
    assert earlier.backing_wei == position.backing_wei
    assert earlier.weight == position.weight
    assert earlier.slot == position.slot
    assert earlier_raw.lower() == raw.lower()
    assert earlier.fee_debt == position.fee_debt


def test_decode_listing_rejects_short_and_empty_returns():
    assert decode_listing("0x", 1) is None
    assert decode_listing("", 1) is None
    assert decode_listing("0x" + "0" * 200, 1) is None
    # Full-length but all-zero: a dead slot, not a zero-backed position.  Letting
    # it through would make 1e36 // 0 explode inside the invariant check.
    assert decode_listing("0x" + "0" * 704, 1) is None


# ---------------------------------------------------------------------------
# The free-list slot scan — TRAP 1
# ---------------------------------------------------------------------------


def test_slot_scan_skips_zeros():
    """Live-captured slot batches contain real holes; zeros are skipped, not stops."""
    fixture = load_fixture("aggregate3_slots.json")
    for batch in fixture["batches"]:
        expected = batch["expected_decoded"]
        results = _decode_aggregate3_result(batch["raw_return_data"])
        ids = [_decode_uint(d) if ok else 0 for ok, d in results]
        assert ids == expected["listing_ids"]

        nonzero = [i for i in ids if i != 0]
        zeros = [
            batch["start_slot"] + i for i, v in enumerate(ids) if v == 0
        ]
        assert zeros == expected["zero_slots"]
        assert len(nonzero) == expected["nonzero_count"]
        assert len(zeros) == expected["zero_count"]

    # Slots 572-611 alone hold 8 holes in 40 slots: the holes are not a rare
    # tail event, they are 20% of that window.
    assert fixture["batches"][1]["expected_decoded"]["zero_count"] == 8


def test_free_list_hole_trap_fixture_is_self_consistent():
    """The trap block's own arithmetic, asserted so the numbers cannot drift."""
    trap = load_fixture("aggregate3_slots.json")["free_list_hole_trap"]
    naive = trap["naive_scan_slots_1_to_activeListingCount"]

    assert naive["ids_found"] + naive["ids_missed"] == trap["activeListingCount"]
    assert naive["ids_found"] == 3604 and naive["ids_missed"] == 263
    assert (
        naive["weightedBackingTotal"] + naive["weightedBackingTotal_shortfall"]
        == naive["weightedBackingTotal_correct"]
    )
    assert naive["weightedBackingTotal_shortfall_over_1e36"] == 263.0
    assert (
        naive["acquisitionFee"] - naive["acquisitionFee_correct"]
        == naive["acquisitionFee_error_wei"]
        == 765_340_893_316_672
    )
    # It fails by 0.56% — small enough to look like a live move, big enough to
    # misprice a pull.  That is the whole danger.
    error_pct = abs(naive["acquisitionFee_error_wei"]) / naive["acquisitionFee_correct"]
    assert 0.001 < error_pct < 0.01

    # Holes are structural: 333 in slots 1..4200, highest occupied slot 4148,
    # i.e. 281 slots beyond activeListingCount still hold live positions.
    assert trap["highest_occupied_slot"] > trap["activeListingCount"]
    assert trap["total_holes_in_slots_1_to_4200"] == 333


def _build_free_list_geometry() -> tuple[dict[int, int], list[int], set[int]]:
    """A 3,867-position slot map with the fixture's exact hole geometry.

    Reproduces the numbers in ``free_list_hole_trap``: 3,867 live positions,
    263 holes inside slots 1..3,867 (so a naive scan finds 3,604), 263 positions
    living *above* slot 3,867, highest occupied slot 4,148, 333 holes in
    1..4,200.  Backing values are the real ones captured at block 25612701.
    """
    trap = load_fixture("aggregate3_slots.json")["free_list_hole_trap"]
    distribution = load_fixture("backing_distribution.json")
    backings = [int(v) for v in distribution["backing_values_wei"]]
    # The fixture stores the values sorted ascending.  Slot order is unrelated to
    # backing size on chain, so shuffle deterministically before assigning them
    # to slots — leaving them sorted would put every large position above the
    # count boundary and make the naive scan's error unrealistically large.
    random.Random(25612701).shuffle(backings)

    count = trap["activeListingCount"]
    found_naive = trap["naive_scan_slots_1_to_activeListingCount"]["ids_found"]
    missed = trap["naive_scan_slots_1_to_activeListingCount"]["ids_missed"]
    top_slot = trap["highest_occupied_slot"]
    assert len(backings) == count

    # 263 holes spread through slots 1..count
    holes = {round(k * count / (missed + 1)) for k in range(1, missed + 1)}
    assert len(holes) == missed
    low_slots = [s for s in range(1, count + 1) if s not in holes]
    assert len(low_slots) == found_naive

    # the 263 positions the naive scan never sees, packed just under top_slot
    span = list(range(count + 1, top_slot + 1))
    step = len(span) / missed
    high_slots = sorted({span[min(int(k * step), len(span) - 1)] for k in range(missed)})
    while len(high_slots) < missed:  # pragma: no cover - geometry is deterministic
        for s in span:
            if s not in high_slots:
                high_slots.append(s)
                break
        high_slots.sort()
    high_slots[-1] = top_slot

    slots = sorted(low_slots + high_slots)
    assert len(slots) == count
    slot_map = {slot: 1000 + i for i, slot in enumerate(slots)}
    return slot_map, backings, holes


async def test_slot_scan_stops_on_count_not_on_slot_index():
    """The 3,604-of-3,867 regression guard.

    Two scans over identical chain state:

    * the client's recipe — scan upward, skip zeros, **stop once
      ``activeListingCount()`` non-zero ids are collected** — finds all 3,867 and
      every aggregate reproduces bit-for-bit;
    * the naive ``slot = 1..activeListingCount`` scan finds 3,604, does not
      crash, does not look wrong, and understates ``weightedBackingTotal`` by
      almost exactly 263e36 — because ``weightedBackingTotal ≈ count × 1e36``,
      the wrong number wears the shape of a slightly smaller pool.

    The second half is the point: the *only* thing that catches it is the
    aggregate invariant check, which must therefore run in production and not
    just here.
    """
    trap_geometry = load_fixture("aggregate3_slots.json")["free_list_hole_trap"]
    slot_map, backings, _holes = _build_free_list_geometry()
    chain = SimChain(block_number=25612701, backings=backings, slot_map=slot_map)
    transport = RecordingTransport(chain.handler)
    client = _client_on(transport)

    block, positions, report = await client.sweep_positions()

    assert block == 25612701
    assert report["collected"] == report["expected"] == chain.active_listing_count
    assert report["invariants_ok"] is True
    assert report["mismatches"] == ()
    # slots above activeListingCount were genuinely needed
    assert report["slots_scanned"] > chain.active_listing_count
    assert report["slots_scanned"] >= trap_geometry["highest_occupied_slot"]
    assert report["zero_slots"] == report["slots_scanned"] - report["collected"]
    assert max(p.slot for p in positions) > chain.active_listing_count

    # 1 aggregate read + 9 slot batches + 8 listing batches, none over 500 calls.
    eth_calls = transport.calls("eth_call")
    assert len(eth_calls) == 18
    widths = [
        len(decode_aggregate3_calldata(p["params"][0]["data"])) for p in eth_calls
    ]
    assert max(widths) <= MULTICALL_MAX_CALLS

    # --- now the naive scan over the same state ---------------------------
    naive_ids = [
        slot_map[s] for s in range(1, chain.active_listing_count + 1) if s in slot_map
    ]
    trap = load_fixture("aggregate3_slots.json")["free_list_hole_trap"]
    assert len(naive_ids) == trap["naive_scan_slots_1_to_activeListingCount"]["ids_found"]

    naive_positions = [p for p in positions if p.listing_id in set(naive_ids)]
    naive_report = check_sweep_invariants(
        naive_positions,
        expected_count=chain.active_listing_count,
        total_weight_onchain=chain.total_weight,
        weighted_backing_total_onchain=chain.weighted_backing_total,
        acquisition_fee_onchain=chain.acquisition_fee,
    )

    assert naive_report["invariants_ok"] is False
    assert naive_report["collected"] == 3604
    shortfall = (
        naive_report["weighted_backing_total_onchain"]
        - naive_report["weighted_backing_total_computed"]
    )
    assert round(shortfall / 10**36, 3) == 263.0
    # ...and the flagship metric is quietly wrong, not obviously broken.
    assert (
        naive_report["acquisition_fee_computed"]
        != naive_report["acquisition_fee_onchain"]
    )
    fee_error = abs(
        naive_report["acquisition_fee_computed"]
        - naive_report["acquisition_fee_onchain"]
    )
    assert 0 < fee_error / naive_report["acquisition_fee_onchain"] < 0.02


# ---------------------------------------------------------------------------
# The sweep — pinning and invariants
# ---------------------------------------------------------------------------


def _small_chain(*, block_number: int = 25612701, holes: bool = True) -> SimChain:
    backings = [
        15 * 10**15,
        10**17,
        15 * 10**16,
        3 * 10**17,
        221 * 10**18,
        5 * 10**16,
        7 * 10**17,
    ]
    if holes:
        # slot 3, 6 and 9 are free-list holes; two positions live above count=7
        slots = [1, 2, 4, 5, 7, 8, 11]
    else:
        slots = list(range(1, len(backings) + 1))
    slot_map = {slot: 500 + i for i, slot in enumerate(slots)}
    return SimChain(
        block_number=block_number,
        backings=backings,
        slot_map=slot_map,
        balance_wei=2_340_905_117_595_043_174_540,
    )


async def test_sweep_pins_block_on_every_call():
    """Every ``eth_call`` in a sweep carries the same pinned ``blockTag``.

    An unpinned 6-minute scan returned rows whose totals did not match on-chain:
    the pool moved 24 listings in 46 blocks.  Nothing in a sweep may say
    ``latest`` (TRAP 2, PRD §7 rule 11).
    """
    chain = _small_chain()
    transport = RecordingTransport(chain.handler)
    client = _client_on(transport)

    block, positions, report = await client.sweep_positions()
    assert block == chain.block_number
    assert report["invariants_ok"] is True

    eth_calls = transport.calls("eth_call")
    assert eth_calls, "the sweep issued no eth_call"
    tags = {payload["params"][1] for payload in eth_calls}
    assert tags == {hex(chain.block_number)}
    assert "latest" not in tags
    # aggregates, slot scan and listings all landed on the one pinned block
    assert len(transport.calls("eth_blockNumber")) == 1


async def test_sweep_invariants_pass():
    chain = _small_chain()
    client = _client_on(RecordingTransport(chain.handler))
    block, positions, report = await client.sweep_positions()

    assert block == chain.block_number
    assert len(positions) == chain.active_listing_count == 7
    assert report["invariants_ok"] is True
    assert report["mismatches"] == ()
    assert report["total_weight_computed"] == chain.total_weight
    assert report["weighted_backing_total_computed"] == chain.weighted_backing_total
    assert report["acquisition_fee_computed"] == chain.acquisition_fee
    assert report["backing_total_wei"] == sum(chain.backings)
    assert report["weight_mismatches"] == 0
    # positions found above activeListingCount prove the holes were skipped
    assert max(p.slot for p in positions) == 11 > report["expected"]


async def test_sweep_invariants_fail_marks_stale():
    """A truncated slot space is reported stale, never rendered as a total."""
    chain = _small_chain()
    # Simulate the pool growing mid-sweep: the count says 7, the slot map only
    # exposes 5 ids.  This is exactly the shape of a partial sweep.
    for slot in (8, 11):
        chain.slot_map.pop(slot)

    client = _client_on(RecordingTransport(chain.handler))
    block, positions, report = await client.sweep_positions()

    assert block == chain.block_number
    assert report["invariants_ok"] is False
    assert report["collected"] == 5
    assert report["expected"] == 7
    assert any("count 5" in m for m in report["mismatches"])
    assert any("weightedBackingTotal" in m for m in report["mismatches"])
    # The rows we did get are still returned so the manager can show a stale
    # board — but the flag is what stops them being published as current.
    assert len(positions) == 5


def test_check_sweep_invariants_catches_fee_share_drift():
    """``feeShareTotal() == activeListingCount()`` is a free invariant (§13.2)."""
    position = decode_listing(load_fixture("listings_56508.json")["raw_return_data"], 56508)
    assert position is not None
    tw = fwa_ev.total_weight([position.backing_wei])
    wbt = fwa_ev.weighted_backing_total([position.backing_wei])
    fee = fwa_ev.acquisition_fee_wei(wbt, tw)

    good = check_sweep_invariants(
        [position],
        expected_count=1,
        total_weight_onchain=tw,
        weighted_backing_total_onchain=wbt,
        acquisition_fee_onchain=fee,
        fee_share_total_onchain=1,
    )
    assert good["invariants_ok"] is True

    bad = check_sweep_invariants(
        [position],
        expected_count=1,
        total_weight_onchain=tw,
        weighted_backing_total_onchain=wbt,
        acquisition_fee_onchain=fee,
        fee_share_total_onchain=2,
    )
    assert bad["invariants_ok"] is False
    assert any("feeShareTotal" in m for m in bad["mismatches"])


def test_acquisition_fee_uses_two_floor_divisions():
    """Collapsing the two divisions would break the invariant on a good sweep."""
    pinned = load_fixture("pinned_aggregates.json")["README"]["block_25612701"]
    wbt = pinned["weightedBackingTotal"]
    tw = pinned["totalWeight"]
    assert fwa_ev.acquisition_fee_wei(wbt, tw) == pinned["acquisitionFee"]
    collapsed = wbt * 11000 // (tw * 10000)
    assert collapsed != pinned["acquisitionFee"]


async def test_single_flight_skips_overlapping_sweep():
    """A second caller gets the previous result at once; the tick is skipped."""
    chain = _small_chain()
    transport = RecordingTransport(chain.handler)
    client = _client_on(transport)

    first = await client.sweep_positions()
    assert first[2]["invariants_ok"] is True
    calls_after_first = len(transport.requests)

    # Pretend a sweep is in flight and re-enter.
    client._sweep_running = True
    block, positions, report = await client.sweep_positions()
    client._sweep_running = False

    assert report["skipped"] is True
    assert block == first[0]
    assert positions == first[1]
    assert len(transport.requests) == calls_after_first  # nothing was queued


async def test_single_flight_without_previous_result_is_degraded_not_empty_success():
    client = _raising_client()
    client._sweep_running = True
    block, positions, report = await client.sweep_positions()
    assert (block, positions) == (0, [])
    assert report["skipped"] is True
    assert report["invariants_ok"] is False


# ---------------------------------------------------------------------------
# quoteAcquisitionPrice — the gas-price gotcha
# ---------------------------------------------------------------------------


def _quote_handler(fixture: dict) -> Callable[[str, dict], httpx.Response]:
    """Serve the live-captured quote for whichever gasPrice the client sends."""
    by_price = {
        s["gasPrice_wei"]: s["quoteAcquisitionPrice"]["raw_return_data"]
        for s in fixture["samples"]
    }

    def handler(_url: str, payload: dict) -> httpx.Response:
        call = payload["params"][0]
        price = int(call["gasPrice"], 16) if "gasPrice" in call else None
        return _ok(payload, by_price[price])

    return handler


async def test_quote_passes_explicit_gasprice_and_gas():
    """Both ``gasPrice`` and a bounded ``gas`` go on the wire, every time."""
    fixture = load_fixture("quote_acquisition_price.json")
    transport = RecordingTransport(_quote_handler(fixture))
    client = _client_on(transport)

    await client.quote_acquisition_price(1_000_000_000)

    call = transport.calls("eth_call")[0]["params"][0]
    assert call["to"] == FWA_CORE
    assert call["data"] == SELECTORS["quoteAcquisitionPrice()"]
    assert call["gasPrice"] == hex(1_000_000_000)
    assert call["gas"] == "0x200000"
    assert int(call["gas"], 16) > 0


async def test_quote_vrf_leg_is_gas_price_dependent_and_not_waived():
    """§13.9: every zero VRF reading was an unset-``gasPrice`` artifact."""
    fixture = load_fixture("quote_acquisition_price.json")
    transport = RecordingTransport(_quote_handler(fixture))
    client = _client_on(transport)

    for sample in fixture["samples"]:
        if sample["gasPrice_wei"] is None:
            continue  # the client never sends an unset gasPrice
        fee, vrf, total = await client.quote_acquisition_price(sample["gasPrice_wei"])
        expected = sample["expected_decoded"]
        assert (fee, vrf, total) == (expected["fee"], expected["vrf"], expected["total"])

    conclusion = fixture["conclusion"]["vrf_component_by_gas_price"]
    assert conclusion["1 gwei"] == 1_040_000_000_000_000
    assert conclusion["50 gwei"] == 52_000_000_000_000_000
    assert conclusion["1 gwei"] != conclusion["50 gwei"] != 0
    # The fee leg does NOT move with gas price; only the VRF leg does.
    fee_by_price = set(fixture["conclusion"]["fee_component_by_gas_price"].values())
    assert len(fee_by_price) == 1


async def test_quote_returns_tuple_not_sum():
    """The three integers are the contract's, unmodified — never recomputed."""
    fixture = load_fixture("quote_acquisition_price.json")
    sample = next(s for s in fixture["samples"] if s["gasPrice_wei"] == 50_000_000_000)
    transport = RecordingTransport(_quote_handler(fixture))
    client = _client_on(transport)

    fee, vrf, total = await client.quote_acquisition_price(50_000_000_000)
    expected = sample["expected_decoded"]

    assert fee == expected["fee"]
    assert vrf == expected["vrf"]
    assert total == expected["total"]
    # It happens to be a sum here, but the client must render the returned third
    # word, not compute fee+vrf: only one eth_call, only one source of truth.
    assert total == _decode_uint(sample["quoteAcquisitionPrice"]["raw_return_data"], 2)
    assert fee == fixture["conclusion"]["acquisitionFee_onchain"]


async def test_quote_degrades_to_zero_tuple_on_failure():
    def dead(_url: str, _payload: dict) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _client_on(RecordingTransport(dead))
    assert await client.quote_acquisition_price(1_000_000_000) == (0, 0, 0)


# ---------------------------------------------------------------------------
# TVL source
# ---------------------------------------------------------------------------


async def test_eth_balance_used_for_tvl_not_weighted_backing_total():
    """``eth_getBalance(core)`` is the only value-held source (PRD §7 rule 4)."""
    pinned = load_fixture("pinned_aggregates.json")["README"]["block_25612701"]
    balance = pinned["fwa_core_eth_balance_wei"]

    def handler(_url: str, payload: dict) -> httpx.Response:
        assert payload["method"] == "eth_getBalance"
        assert payload["params"][0] == FWA_CORE
        return _ok(payload, hex(balance))

    transport = RecordingTransport(handler)
    client = _client_on(transport)
    assert await client.fetch_eth_balance() == balance

    # weightedBackingTotal is ~count x 1e36: dimensionless, three orders of
    # magnitude away from the real balance, and reads like "3,867 ETH".
    wbt = pinned["weightedBackingTotal"]
    assert round(wbt / (pinned["activeListingCount"] * 10**36), 6) == 1.0
    assert wbt / 10**18 > 1_000 * (balance / 10**18)
    # ...and it is structurally barred from ever reaching a widget.
    assert "weighted_backing_total" not in FWA_DATA_KEYS
    assert "core_balance_eth" in FWA_DATA_KEYS


# ---------------------------------------------------------------------------
# Endpoint rotation
# ---------------------------------------------------------------------------


async def test_fallback_rotation_on_429():
    """A live-captured publicnode 429 rotates to the next endpoint, same tick."""
    rate_limit_body = load_fixture("rpc_errors.json")["errors"][
        "publicnode_rate_limit_429"
    ]["raw_body"]
    hit: list[str] = []

    def handler(url: str, payload: dict) -> httpx.Response:
        hit.append(url)
        if "publicnode" in url:
            return httpx.Response(
                429, text=rate_limit_body, headers={"content-type": "application/json"}
            )
        return _ok(payload, hex(25_621_159))

    transport = RecordingTransport(handler)
    client = _client_on(transport)

    assert await client.fetch_block_number() == 25_621_159
    assert any("publicnode" in u for u in hit)
    # Asserted against the configured pool rather than a named host: this
    # used to name cloudflare, which went red as a *failure* when that dead
    # endpoint was finally removed. What matters is that rotation happens and
    # that the primary is tried first.
    fallback_hosts = [urlparse(u).hostname for u in _FALLBACK_RPCS]
    assert any(urlparse(u).hostname in fallback_hosts for u in hit), (
        f"never rotated off the primary; hit {hit}"
    )
    first_fallback = next(
        i for i, u in enumerate(hit) if urlparse(u).hostname in fallback_hosts
    )
    assert first_fallback > 0, "a fallback was tried before the primary"


async def test_error_inside_http_200_rotates():
    """ankr-style: ``error`` arrives with HTTP 200, so status alone is not enough."""
    body = load_fixture("rpc_errors.json")["errors"]["ankr_now_keyed"]["raw_body"]
    assert load_fixture("rpc_errors.json")["errors"]["ankr_now_keyed"]["http_status"] == 200

    def handler(url: str, payload: dict) -> httpx.Response:
        if "publicnode" in url:
            return httpx.Response(
                200, text=body, headers={"content-type": "application/json"}
            )
        return _ok(payload, hex(42))

    client = _client_on(RecordingTransport(handler))
    assert await client.fetch_block_number() == 42


async def test_all_endpoints_dead_returns_degraded():
    """Nothing escapes into the refresh loop when every endpoint is down."""

    def dead(_url: str, _payload: dict) -> httpx.Response:
        return httpx.Response(521, text="error code: 521\n")

    transport = RecordingTransport(dead)
    client = _client_on(transport)

    assert await client.fetch_block_number() == 0
    assert await client.fetch_eth_balance() == 0
    assert await client.fetch_gas_price() == 0
    assert await client.quote_acquisition_price(10**9) == (0, 0, 0)
    assert await client.fetch_token_share_bps(120) is None
    assert await client._multicall([(FWA_CORE, SELECTORS["acquisitionFee()"])]) == [
        (False, "0x")
    ]

    block, positions, report = await client.sweep_positions()
    assert (block, positions) == (0, [])
    assert report["invariants_ok"] is False
    assert report["collected"] == 0

    hot = await client.fetch_hot_batch()
    assert set(hot) == set(FWA_HOT_KEYS)
    assert hot["_ok"] is False

    # every endpoint was tried before giving up -- counted from the configured
    # pool rather than hardcoded, so retiring a dead endpoint (cloudflare) or
    # adding a verified one does not read as a regression here.
    tried = {u.split("//")[1].split("/")[0] for u, _p in transport.requests}
    assert len(tried) == 1 + len(_FALLBACK_RPCS)

# ---------------------------------------------------------------------------
# collectionWhitelisted lives on core, not on the whitelist contract (§13.1)
# ---------------------------------------------------------------------------


async def test_collection_whitelisted_targets_core_not_the_whitelist_contract():
    targets: list[str] = []

    def handler(_url: str, payload: dict) -> httpx.Response:
        inner = decode_aggregate3_calldata(payload["params"][0]["data"])
        results = []
        for target, _allow, cd in inner:
            targets.append(target)
            addr = "0x" + _strip0x(cd)[8:][24:64]
            results.append((True, "0x" + _encode_uint(1 if addr.endswith("fb2e") else 0)))
        return _ok(payload, encode_aggregate3_result(results))

    client = _client_on(RecordingTransport(handler))
    out = await client.fetch_collections_whitelisted(
        [
            "0x26D7Ad0E930b54b84C00DAad077Ee31Ba9e2Fb2E",
            "0x0000000000000000000000000000000000000001",
        ]
    )

    assert set(targets) == {FWA_CORE}
    assert FWA_WHITELIST not in targets
    assert out["0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"] is True
    assert out["0x0000000000000000000000000000000000000001"] is False


# ---------------------------------------------------------------------------
# Hot batch, end to end
# ---------------------------------------------------------------------------


async def test_fetch_hot_batch_end_to_end_shape():
    """One multicall + the two gas-priced follow-ups, all keys populated."""
    quote_fixture = load_fixture("quote_acquisition_price.json")
    quote_raw = next(
        s["quoteAcquisitionPrice"]["raw_return_data"]
        for s in quote_fixture["samples"]
        if s["gasPrice_wei"] == 1_000_000_000
    )

    def handler(_url: str, payload: dict) -> httpx.Response:
        if payload["method"] == "eth_gasPrice":
            return _ok(payload, hex(1_000_000_000))
        call = payload["params"][0]
        if call["to"].lower() == MULTICALL3:
            inner = decode_aggregate3_calldata(call["data"])
            out = []
            for _t, _a, cd in inner:
                sel = "0x" + _strip0x(cd)[:8]
                if sel == SELECTORS["symbol()"]:
                    out.append(
                        (
                            True,
                            "0x"
                            + _encode_uint(0x20)
                            + _encode_uint(3)
                            + "465741".ljust(64, "0"),
                        )
                    )
                elif sel == SELECTORS["forcedTokenShareBps()"]:
                    out.append((True, "0x" + "f" * 64))
                elif sel == SELECTORS["lastAcquisitionTs()"]:
                    out.append((True, "0x" + _encode_uint(1_784_900_000)))
                else:
                    out.append((True, "0x" + _encode_uint(7)))
            return _ok(payload, encode_aggregate3_result(out))
        if call["data"] == SELECTORS["quoteAcquisitionPrice()"]:
            return _ok(payload, quote_raw)
        if call["data"].startswith(SELECTORS["tokenShareBps(uint256)"]):
            assert call["to"] == FWA_REWARDS
            return _ok(payload, "0x" + _encode_uint(4321))
        raise AssertionError(f"unexpected eth_call {call}")

    transport = RecordingTransport(handler)
    client = _client_on(transport)
    out = await client.fetch_hot_batch()

    assert set(out) == set(FWA_HOT_KEYS)
    assert out["_ok"] is True
    assert out["_failed"] == ()
    assert out["acquisition_fee"] == 7
    assert out["token_symbol"] == "FWA"
    assert out["forced_token_share_bps"] == -1  # signed, not 2**256-1
    assert out["token_share_bps"] == 4321
    assert out["quote_gas_price_wei"] == 1_000_000_000
    assert out["quote_vrf_wei"] == 1_040_000_000_000_000
    assert out["quote_total_wei"] == out["quote_fee_wei"] + out["quote_vrf_wei"]

    # exactly one batched multicall — the hot tier is one round trip plus the
    # two calls that cannot share it (gas-priced quote, gap-dependent share)
    multicalls = [
        p
        for _u, p in transport.requests
        if p.get("method") == "eth_call"
        and p["params"][0]["to"].lower() == MULTICALL3
    ]
    assert len(multicalls) == 1
    assert len(decode_aggregate3_calldata(multicalls[0]["params"][0]["data"])) == len(
        HOT_VIEWS
    )
    # hot reads are deliberately unpinned (§11); only the sweep pins a block
    assert all(p["params"][1] == "latest" for p in transport.calls("eth_call"))
