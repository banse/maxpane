"""Offline contract tests for the FWAP v1/v2 adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from maxpane_dashboard.data.evm_abi import ZERO_ADDRESS, strip0x
from maxpane_dashboard.data.fwa_client import MULTICALL3
from maxpane_dashboard.data.fwa_ecosystem_addresses import FWA_CORE
from maxpane_dashboard.data.fwa_ecosystem_models import (
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
)
from maxpane_dashboard.data.fwa_projects.base import load_manifest_abi
from maxpane_dashboard.data.fwa_projects.fwap import (
    EVENT_SPECS,
    FWAP_MANIFESTS,
    STATE_CALLS,
    FWAPAdapter,
    FWAPApiSnapshot,
    FWAPPosition,
    build_project_rows,
    decode_events,
    normalize_events,
    runtime_codehash,
)
from maxpane_dashboard.data.keccak import keccak256_hex
from tests.fwa_ecosystem_fixtures import (
    DenyNetworkTransport,
    FixedClock,
    load_fwa_ecosystem_fixture,
)


def _fixture(name: str) -> dict[str, Any]:
    return load_fwa_ecosystem_fixture(f"fwap/{name}.json")


def _selector(signature: str) -> str:
    return keccak256_hex(signature.encode("ascii"))[:10]


def _signature(entry: Mapping[str, Any]) -> str:
    types = ",".join(str(item["type"]) for item in entry.get("inputs", ()))
    return f"{entry['name']}({types})"


def _word(value: Any, kind: str = "uint256") -> str:
    if kind == "address":
        return strip0x(str(value)).lower().rjust(64, "0")
    if kind == "bool":
        value = int(bool(value))
    number = int(value)
    if number < 0:
        number += 1 << 256
    return f"{number:064x}"


def _single(value: Any, kind: str = "uint256") -> str:
    return "0x" + _word(value, kind)


def _decode_aggregate3_calldata(data: str) -> list[tuple[str, bool, str]]:
    raw = strip0x(data)
    assert raw[:8] == "82ad56cb"
    body = raw[8:]
    array_offset = int(body[:64], 16) * 2
    count = int(body[array_offset : array_offset + 64], 16)
    base = array_offset + 64
    calls: list[tuple[str, bool, str]] = []
    for index in range(count):
        offset = int(body[base + index * 64 : base + (index + 1) * 64], 16) * 2
        start = base + offset
        target = "0x" + body[start + 24 : start + 64]
        allow_failure = bool(int(body[start + 64 : start + 128], 16))
        calldata_offset = int(body[start + 128 : start + 192], 16) * 2
        calldata_start = start + calldata_offset
        calldata_length = int(body[calldata_start : calldata_start + 64], 16)
        calldata = body[
            calldata_start + 64 : calldata_start + 64 + calldata_length * 2
        ]
        calls.append((target.lower(), allow_failure, "0x" + calldata.lower()))
    return calls


def _encode_aggregate3_result(results: list[tuple[bool, str]]) -> str:
    tuples: list[str] = []
    for success, data in results:
        raw = strip0x(data)
        padded = raw + "0" * ((64 - len(raw) % 64) % 64)
        tuples.append(
            f"{int(success):064x}"
            + f"{64:064x}"
            + f"{len(raw) // 2:064x}"
            + padded
        )
    cursor = len(tuples) * 32
    offsets: list[int] = []
    for encoded in tuples:
        offsets.append(cursor)
        cursor += len(encoded) // 2
    return (
        "0x"
        + f"{32:064x}{len(tuples):064x}"
        + "".join(f"{offset:064x}" for offset in offsets)
        + "".join(tuples)
    )


_MANIFEST_BY_ADDRESS = {manifest.address: manifest for manifest in FWAP_MANIFESTS}
_MANIFEST_BY_VERSION_ROLE = {
    (manifest.version, manifest.role): manifest for manifest in FWAP_MANIFESTS
}
_STATE_CALL_BY_TARGET_DATA = {
    (call.address, call.calldata): call for call in STATE_CALLS
}
_FUNCTION_BY_TARGET_SELECTOR: dict[tuple[str, str], Mapping[str, Any]] = {}
_DEPENDENCY_BY_TARGET_SELECTOR: dict[
    tuple[str, str], tuple[str, str]
] = {}
for _manifest in FWAP_MANIFESTS:
    for _entry in load_manifest_abi(_manifest):
        if _entry.get("type") != "function":
            continue
        _function_selector = _selector(_signature(_entry))
        _FUNCTION_BY_TARGET_SELECTOR[(_manifest.address, _function_selector)] = _entry
    for _getter, _expected in _manifest.dependencies:
        _dependency_entry = next(
            entry
            for entry in load_manifest_abi(_manifest)
            if entry.get("type") == "function" and entry.get("name") == _getter
        )
        _DEPENDENCY_BY_TARGET_SELECTOR[
            (_manifest.address, _selector(_signature(_dependency_entry)))
        ] = (_getter, _expected)

_LISTINGS_SELECTOR = _selector("listings(uint256)")
_CODE_BY_ADDRESS = {
    manifest.address: f"0x60{index + 1:02x}"
    for index, manifest in enumerate(FWAP_MANIFESTS)
}
_REAL_RUNTIME_CODEHASH = runtime_codehash


class SimulatedFWAPChain:
    """Small semantic Ethereum node backed only by the FWAP fixture."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = deepcopy(fixture)
        self.rpc_calls: list[tuple[str, list[Any]]] = []
        self.subcalls: list[tuple[str, str, str]] = []
        self.failed_positions: set[tuple[str, int]] = set()
        self.failed_listings: set[int] = set()
        self.failed_dependencies: set[tuple[str, str]] = set()
        self.runtime_mismatches: set[str] = set()
        self.runtime_unavailable: set[str] = set()
        self.summary_overrides: dict[tuple[str, str], Any] = {}
        self.eth_balance_overrides: dict[str, Any] = {}
        self.listing_overrides: dict[int, dict[str, Any]] = {}

    def _summary(self, target: str, calldata: str) -> tuple[bool, str] | None:
        call = _STATE_CALL_BY_TARGET_DATA.get((target, calldata))
        if call is None:
            return None
        override_key = (call.version, call.field)
        if override_key in self.summary_overrides:
            value = self.summary_overrides[override_key]
        else:
            value = self.fixture["versions"][call.version][call.field]
        if value is None:
            return False, "0x"
        if call.output == "epoch":
            return True, "0x" + "".join(_word(item) for item in value)
        if call.output == "bool":
            return True, _single(value, "bool")
        return True, _single(value)

    def _position(self, version: str, position_id: int) -> tuple[bool, str]:
        if (version, position_id) in self.failed_positions:
            return False, "0x"
        positions = self.fixture["versions"][version]["positions"]
        row = next(
            (item for item in positions if item["position_id"] == position_id),
            None,
        )
        if row is None:
            return False, "0x"
        return True, "0x" + "".join(
            (
                _word(row["collection"], "address"),
                _word(row["token_id"]),
                _word(row["backing_wei"]),
                _word(row["listing_id"]),
                _word(row["state"]),
                _word(row["receipt_owner"], "address"),
            )
        )

    def _listing(self, listing_id: int) -> tuple[bool, str]:
        if listing_id in self.failed_listings:
            return False, "0x"
        for version, surface in self.fixture["versions"].items():
            row = next(
                (
                    item
                    for item in surface["positions"]
                    if item["listing_id"] == listing_id
                ),
                None,
            )
            listing = surface["listings"].get(str(listing_id))
            if row is None or listing is None:
                continue
            values = {
                "collection": row["collection"],
                "depositor": _MANIFEST_BY_VERSION_ROLE[(version, "house")].address,
                "purchaser": ZERO_ADDRESS,
                "token_id": row["token_id"],
                "weight": 1,
                "backing_wei": row["backing_wei"],
                "fee_share": 0,
                "fee_debt": 0,
                "slot": listing_id,
                "allocated_at": 0,
                "status": listing["status"],
            }
            values.update(self.listing_overrides.get(listing_id, {}))
            return True, "0x" + "".join(
                (
                    _word(values["collection"], "address"),
                    _word(values["depositor"], "address"),
                    _word(values["purchaser"], "address"),
                    _word(values["token_id"]),
                    _word(values["weight"]),
                    _word(values["backing_wei"]),
                    _word(values["fee_share"]),
                    _word(values["fee_debt"]),
                    _word(values["slot"]),
                    _word(values["allocated_at"]),
                    _word(values["status"]),
                )
            )
        return False, "0x"

    def _subcall(self, target: str, calldata: str) -> tuple[bool, str]:
        summary = self._summary(target, calldata)
        if summary is not None:
            return summary
        if target == FWA_CORE and calldata[:10] == _LISTINGS_SELECTOR:
            return self._listing(int(calldata[10:], 16))
        manifest = _MANIFEST_BY_ADDRESS.get(target)
        if manifest is None:
            return False, "0x"
        entry = _FUNCTION_BY_TARGET_SELECTOR.get((target, calldata[:10]))
        if entry is None:
            return False, "0x"
        name = str(entry["name"])
        if name == "position":
            return self._position(manifest.version, int(calldata[10:], 16))
        dependency = _DEPENDENCY_BY_TARGET_SELECTOR.get((target, calldata[:10]))
        if dependency is not None:
            getter, expected = dependency
            if (target, getter) in self.failed_dependencies:
                return False, "0x"
            return True, _single(expected, "address")
        return False, "0x"

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        payload = json.loads(request.content)
        method = payload["method"]
        params = payload["params"]
        self.rpc_calls.append((method, params))
        if method == "eth_call":
            assert params[0]["to"].lower() == MULTICALL3
            block_tag = params[1]
            calls = _decode_aggregate3_calldata(params[0]["data"])
            assert all(allow_failure for _target, allow_failure, _data in calls)
            for target, _allow_failure, calldata in calls:
                self.subcalls.append((target, calldata, block_tag))
            result: Any = _encode_aggregate3_result(
                [self._subcall(target, calldata) for target, _, calldata in calls]
            )
        elif method == "eth_getBalance":
            house = _MANIFEST_BY_ADDRESS[params[0].lower()]
            value = self.eth_balance_overrides.get(
                house.version,
                self.fixture["versions"][house.version]["house_eth_balance_wei"],
            )
            result = value if isinstance(value, str) else hex(value)
        elif method == "eth_getCode":
            address = params[0].lower()
            if address in self.runtime_unavailable:
                result = "0x"
            elif address in self.runtime_mismatches:
                result = "0x60ff"
            else:
                result = _CODE_BY_ADDRESS[address]
        else:  # pragma: no cover - every unexpected request must be loud
            raise AssertionError(f"unexpected FWAP RPC method: {method}")
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )


@asynccontextmanager
async def _adapter(
    fixture: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_payload: Any = None,
    snapshot_url: str | None = None,
) -> AsyncIterator[
    tuple[FWAPAdapter, SimulatedFWAPChain, DenyNetworkTransport]
]:
    chain = SimulatedFWAPChain(fixture)

    def fixture_codehash(raw: Any) -> str | None:
        for address, code in _CODE_BY_ADDRESS.items():
            if raw == code:
                return _MANIFEST_BY_ADDRESS[address].runtime_codehash
        return _REAL_RUNTIME_CODEHASH(raw)

    monkeypatch.setattr(
        "maxpane_dashboard.data.fwa_projects.fwap.runtime_codehash",
        fixture_codehash,
    )
    state_transport = DenyNetworkTransport(chain.handle)

    def api_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == snapshot_url
        assert "authorization" not in request.headers
        assert "x-api-key" not in request.headers
        return httpx.Response(200, json=deepcopy(api_payload))

    api_transport = DenyNetworkTransport(api_handler)
    async with (
        httpx.AsyncClient(transport=state_transport) as state_http,
        httpx.AsyncClient(transport=api_transport) as api_http,
    ):
        adapter = FWAPAdapter(
            http_client=state_http,
            state_endpoints=["https://state.test"],
            snapshot_url=snapshot_url,
            api_http_client=api_http,
            clock=FixedClock(fixture["observed_at"]),
            min_call_interval=0,
            backoff_seconds=(),
        )
        try:
            yield adapter, chain, api_transport
        finally:
            await adapter.close()


@pytest.mark.asyncio
async def test_reads_v1_and_v2_at_one_explicit_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        read = await adapter.fetch_state(fixture["block_number"])

    v1 = read.surface("v1")
    assert v1.available is True
    assert v1.positions_created == 3
    assert v1.inventory_count == 1
    assert v1.active_count == 1
    assert v1.returned_count == 0
    assert v1.exited_count == 1
    assert v1.terminal_count == 1
    assert v1.book_nav_wei == 4_207_000_000_000_000_000
    assert v1.total_fwa_balance_wei == 600_000_000_000_000_000_000

    v2 = read.surface("v2")
    assert v2.available is True
    assert v2.positions_created == 5
    assert v2.inventory_count == 1
    assert v2.listed_count == 2
    assert v2.active_count == 1
    assert v2.allocated_count == 1
    assert v2.returned_count == 1
    assert v2.recovery_count == 1
    assert v2.active_receipt_count == 5
    assert v2.current_epoch == 7
    assert v2.epoch_duration == 259_200
    assert v2.positions[1].core_listing_match is True

    tag = hex(fixture["block_number"])
    assert chain.rpc_calls
    for method, params in chain.rpc_calls:
        if method == "eth_call":
            assert params[1] == tag
        elif method == "eth_getBalance":
            assert params[1] == tag
    assert chain.subcalls and all(call[2] == tag for call in chain.subcalls)


@pytest.mark.asyncio
async def test_next_position_id_is_not_mislabeled_as_active_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    async with _adapter(fixture, monkeypatch) as (adapter, _chain, _api):
        v2 = (await adapter.fetch_state(fixture["block_number"])).surface("v2")

    assert v2.positions_created == 5
    assert v2.active_count == 1
    assert v2.returned_count == 1
    assert v2.inventory_count == 1


@pytest.mark.asyncio
async def test_failed_position_or_listing_never_becomes_a_zero_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        chain.failed_positions.add(("v1", 2))
        chain.failed_listings.add(202)
        read = await adapter.fetch_state(fixture["block_number"])

    v1 = read.surface("v1")
    v2 = read.surface("v2")
    assert v1.available is False
    assert v1.inventory_count is None
    assert "position:2" in v1.failed_fields
    assert v2.available is False
    assert v2.active_count is None
    assert "listing:202" in v2.failed_fields


@pytest.mark.asyncio
async def test_chain_invariants_are_independent_and_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        chain.summary_overrides[("v2", "share_supply_wei")] = 1
        chain.summary_overrides[("v2", "fwa_liability_wei")] = 999_000 * 10**18
        chain.summary_overrides[("v2", "book_nav_wei")] = 1
        chain.eth_balance_overrides["v2"] = 0
        chain.listing_overrides[201] = {
            "collection": "0x9999999999999999999999999999999999999999"
        }
        v2 = (await adapter.fetch_state(fixture["block_number"])).surface("v2")

    assert set(v2.invariant_failures) == {
        "share_supply_mismatch",
        "fwa_liability_unfunded",
        "nav_below_liquid_capital",
        "eth_balance_below_accounted",
        "core_listing_mismatch",
    }


@pytest.mark.asyncio
async def test_manifest_hashes_and_dependencies_are_checked_at_the_same_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        integrity = await adapter.fetch_integrity(fixture["block_number"])

    assert len(integrity.surfaces) == 6
    assert all(surface.status == "ok" for surface in integrity.surfaces)
    assert all(surface.dependency_matches for surface in integrity.surfaces)
    assert all(
        match is True
        for surface in integrity.surfaces
        for _getter, match in surface.dependency_matches
    )
    tag = hex(fixture["block_number"])
    assert all(
        params[1] == tag
        for method, params in chain.rpc_calls
        if method == "eth_getCode"
    )
    assert chain.subcalls and all(call[2] == tag for call in chain.subcalls)


@pytest.mark.asyncio
async def test_integrity_mismatch_dominates_an_unknown_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    house = _MANIFEST_BY_VERSION_ROLE[("v2", "house")]
    receipt = _MANIFEST_BY_VERSION_ROLE[("v2", "receipt")]
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        chain.runtime_mismatches.add(house.address)
        chain.failed_dependencies.add((receipt.address, "house"))
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])

    assert integrity.status_for_version("v2") == "mismatch"
    row = next(row for row in build_project_rows(state, integrity=integrity) if row["version"] == "v2")
    assert row["source_badge"] == "INTEGRITY"
    assert row["primary_value"] is None
    assert row["eth_value"] is None
    assert row["fwa_value"] is None
    assert row["detail"] == (
        "runtime/dependency integrity mismatch; semantics suppressed"
    )


def _zero_legacy(fixture: dict[str, Any]) -> None:
    legacy = fixture["versions"]["v1"]
    for field in (
        "book_nav_wei",
        "liquid_capital_wei",
        "queued_capital_wei",
        "settlement_inbox_wei",
        "house_eth_balance_wei",
        "house_share_supply_wei",
        "share_supply_wei",
        "house_fwa_balance_wei",
        "share_fwa_balance_wei",
        "fwa_liability_wei",
    ):
        legacy[field] = 0
    legacy["next_position_id"] = 1
    legacy["positions"] = []
    legacy["listings"] = {}


@pytest.mark.asyncio
async def test_v2_is_first_and_zero_clean_v1_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    _zero_legacy(fixture)
    async with _adapter(fixture, monkeypatch) as (adapter, _chain, _api):
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])

    rows = build_project_rows(state, integrity=integrity)
    assert [row["version"] for row in rows] == ["v2"]
    assert tuple(rows[0]) == PROJECT_ROW_KEYS


@pytest.mark.asyncio
async def test_zero_v1_is_retained_when_its_integrity_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    _zero_legacy(fixture)
    receipt = _MANIFEST_BY_VERSION_ROLE[("v1", "receipt")]
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        chain.runtime_mismatches.add(receipt.address)
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])

    rows = build_project_rows(state, integrity=integrity)
    assert [row["version"] for row in rows] == ["v2", "v1"]
    assert rows[1]["source_badge"] == "INTEGRITY"
    assert rows[1]["is_legacy_liability"] is False


@pytest.mark.asyncio
async def test_unknown_zero_legacy_liability_read_remains_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    _zero_legacy(fixture)
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        chain.summary_overrides[("v1", "fwa_liability_wei")] = None
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])

    legacy = next(
        row for row in build_project_rows(state, integrity=integrity)
        if row["version"] == "v1"
    )
    assert legacy["source_badge"] == "DEGRADED"
    assert legacy["lifecycle"] == "unavailable"
    assert legacy["fwa_value"] is None
    assert legacy["is_legacy_liability"] is False


@pytest.mark.asyncio
async def test_unknown_zero_legacy_position_count_remains_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    position = deepcopy(fixture["versions"]["v1"]["positions"][0])
    _zero_legacy(fixture)
    fixture["versions"]["v1"]["next_position_id"] = 2
    fixture["versions"]["v1"]["positions"] = [position]
    async with _adapter(fixture, monkeypatch) as (adapter, chain, _api):
        chain.failed_positions.add(("v1", 1))
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])

    legacy = next(
        row for row in build_project_rows(state, integrity=integrity)
        if row["version"] == "v1"
    )
    assert legacy["source_badge"] == "DEGRADED"
    assert legacy["is_legacy_liability"] is False
    assert "? inventory" in legacy["detail"]


@pytest.mark.asyncio
async def test_fresh_anchored_api_only_annotates_chain_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    api_payload = _fixture("api_fresh")
    url = "https://snapshot.test/fwap"
    async with _adapter(
        fixture,
        monkeypatch,
        api_payload=api_payload,
        snapshot_url=url,
    ) as (adapter, _chain, api_transport):
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])
        api = await adapter.fetch_api_snapshot(fixture["block_number"])

    assert len(api_transport.requests) == 1
    assert api.accepted is True
    assert api.reason == "fresh"
    rows = build_project_rows(state, integrity=integrity, api=api)
    v2 = rows[0]
    assert v2["version"] == "v2"
    assert v2["primary_value"] == 93.874
    assert v2["eth_value"] == 2.434
    assert v2["fwa_value"] == 120_000.0
    assert "projected inventory 8" in v2["detail"]
    assert v2["source_badge"] == "VERIFIED"
    assert v2["source_kind"] == "chain_state"
    legacy = next(row for row in rows if row["version"] == "v1")
    assert legacy["is_legacy_liability"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "reason"),
    (("api_stale", "stale"), ("api_unanchored", "missing_source_anchor")),
)
async def test_stale_or_unanchored_api_is_visible_and_never_overrides_chain(
    fixture_name: str,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    url = "https://snapshot.test/fwap"
    async with _adapter(
        fixture,
        monkeypatch,
        api_payload=_fixture(fixture_name),
        snapshot_url=url,
    ) as (adapter, _chain, _api):
        state = await adapter.fetch_state(fixture["block_number"])
        integrity = await adapter.fetch_integrity(fixture["block_number"])
        api = await adapter.fetch_api_snapshot(fixture["block_number"])

    assert api.reason == reason
    row = build_project_rows(state, integrity=integrity, api=api)[0]
    assert row["primary_value"] == 93.874
    assert row["source_kind"] == "chain_state"
    assert row["source_badge"] == "API STALE"
    if fixture_name == "api_unanchored":
        assert "projected inventory" not in row["detail"]


@pytest.mark.asyncio
async def test_api_is_disabled_by_default_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    async with _adapter(fixture, monkeypatch) as (adapter, _chain, api_transport):
        api = await adapter.fetch_api_snapshot(fixture["block_number"])

    assert api.reason == "disabled"
    assert api.accepted is False
    assert api.snapshot is None
    assert api_transport.requests == []


@pytest.mark.asyncio
async def test_negative_api_source_timestamp_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("state")
    payload = _fixture("api_fresh")
    payload["source_timestamp"] = -0.001
    url = "https://snapshot.test/fwap"
    async with _adapter(
        fixture,
        monkeypatch,
        api_payload=payload,
        snapshot_url=url,
    ) as (adapter, _chain, _api):
        api = await adapter.fetch_api_snapshot(fixture["block_number"])

    assert api.accepted is False
    assert api.reason == "missing_source_anchor"
    assert api.snapshot is None


@pytest.mark.asyncio
async def test_unexpected_api_request_raises() -> None:
    denied = DenyNetworkTransport()
    state_denied = DenyNetworkTransport()
    async with (
        httpx.AsyncClient(transport=denied) as api_http,
        httpx.AsyncClient(transport=state_denied) as state_http,
    ):
        adapter = FWAPAdapter(
            http_client=state_http,
            state_endpoints=["https://state.test"],
            snapshot_url="https://snapshot.test/fwap",
            api_http_client=api_http,
            clock=FixedClock(1_787_932_800.0),
            min_call_interval=0,
            backoff_seconds=(),
        )
        with pytest.raises(AssertionError, match="unexpected network request"):
            await adapter.fetch_api_snapshot(25_860_000)
        await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    (
        "http://snapshot.test/fwap",
        "https://user:secret@snapshot.test/fwap",
        "https://snapshot.test/fwap?api_key=secret",
        "https://snapshot.test/fwap#secret",
    ),
)
async def test_snapshot_url_must_be_credential_free_https(url: str) -> None:
    denied = DenyNetworkTransport()
    async with httpx.AsyncClient(transport=denied) as client:
        with pytest.raises(ValueError, match="credential-free HTTPS"):
            FWAPAdapter(
                http_client=client,
                state_endpoints=["https://state.test"],
                snapshot_url=url,
                api_http_client=client,
            )


def _encode_event(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    spec = next(
        item
        for item in EVENT_SPECS
        if item.manifest.version == descriptor["version"]
        and item.manifest.role == descriptor["role"]
        and item.name == descriptor["event"]
    )
    topics = [spec.topic0]
    data: list[str] = []
    for item in spec.inputs:
        encoded = _word(descriptor["values"][item["name"]], str(item["type"]))
        if item.get("indexed"):
            topics.append("0x" + encoded)
        else:
            data.append(encoded)
    return {
        "address": spec.manifest.address,
        "topics": topics,
        "data": "0x" + "".join(data),
        "blockNumber": hex(int(descriptor["block_number"])),
        "blockTimestamp": hex(int(descriptor["timestamp"])),
        "transactionHash": descriptor["tx_hash"],
        "logIndex": hex(int(descriptor["log_index"])),
        "removed": False,
    }


def test_recorded_events_decode_and_normalize_to_exact_rows() -> None:
    fixture = _fixture("events")
    raw = [_encode_event(item) for item in fixture["events"]]
    read = decode_events(raw, fixture["observed_at"])

    assert [event.event_key for event in read.events] == [
        "exit_requested",
        "fwa_reward_claimed",
        "nft_redeemed",
        "rewards_harvested",
    ]
    rows = normalize_events(read)
    assert all(tuple(row) == NETWORK_EVENT_ROW_KEYS for row in rows)
    by_key = {row["event_key"]: row for row in rows}
    assert by_key["rewards_harvested"]["eth_amount"] == 0.2
    assert by_key["rewards_harvested"]["fwa_amount"] == 10.0
    assert by_key["nft_redeemed"]["eth_amount"] == -0.1
    assert by_key["fwa_reward_claimed"]["fwa_amount"] == 5.0
    assert "shares 1200000000000000000" in by_key["exit_requested"]["detail"]


@pytest.mark.asyncio
async def test_integrity_mismatch_suppresses_fwap_event_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    event_fixture = _fixture("events")
    raw = [_encode_event(item) for item in event_fixture["events"]]
    read = decode_events(raw, event_fixture["observed_at"])
    house = _MANIFEST_BY_VERSION_ROLE[("v2", "house")]
    async with _adapter(state_fixture, monkeypatch) as (adapter, chain, _api):
        chain.runtime_mismatches.add(house.address)
        integrity = await adapter.fetch_integrity(state_fixture["block_number"])

    rows = normalize_events(read, integrity=integrity)
    mismatched = [row for row in rows if row["version"] == "v2"]
    assert len(mismatched) == 2
    assert all(row["event_key"] == "integrity_mismatch" for row in mismatched)
    assert all(row["event_label"] == "Untrusted contract log" for row in mismatched)
    assert all(row["eth_amount"] is None for row in mismatched)
    assert all(row["fwa_amount"] is None for row in mismatched)
    assert all(
        row["detail"]
        == "runtime/dependency integrity mismatch; semantics suppressed"
        for row in mismatched
    )
    assert all(row["verified_source"] is False for row in mismatched)
    assert all(row["integrity"] == "mismatch" for row in mismatched)


def test_event_decoder_deduplicates_and_rejects_malformed_logs() -> None:
    fixture = _fixture("events")
    valid = _encode_event(fixture["events"][0])
    removed = {**valid, "removed": True, "logIndex": "0x2"}
    bad_hash = {**valid, "transactionHash": "0xnot-a-hash", "logIndex": "0x3"}
    extra_data = {**valid, "data": valid["data"] + "00" * 32, "logIndex": "0x4"}
    unknown = {
        **valid,
        "address": "0x9999999999999999999999999999999999999999",
        "logIndex": "0x5",
    }
    read = decode_events(
        [
            None,
            7,
            "not a log",
            [],
            valid,
            deepcopy(valid),
            removed,
            bad_hash,
            extra_data,
            unknown,
        ],
        fixture["observed_at"],
    )
    assert len(read.events) == 1


def test_models_are_strict_frozen_and_wei_native() -> None:
    with pytest.raises(ValidationError):
        FWAPApiSnapshot(
            source_block=1.0,
            source_timestamp=1.0,
            stale=False,
            projected_inventory_count=None,
            inventory_counts=(),
        )
    with pytest.raises(ValidationError):
        FWAPPosition(
            position_id=1,
            collection="0x1111111111111111111111111111111111111111",
            token_id=1,
            backing_wei=1.0,
            listing_id=0,
            state=1,
            lifecycle="inventory",
            receipt_owner="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            listing_status=None,
            listing_lifecycle="unknown",
            core_listing_match=None,
        )
    snapshot = FWAPApiSnapshot(
        source_block=1,
        source_timestamp=1.0,
        stale=False,
        projected_inventory_count=None,
        inventory_counts=(),
    )
    with pytest.raises(ValidationError):
        snapshot.source_block = 2


def test_surface_is_vendored_read_event_only_and_has_no_credentials() -> None:
    assert len(FWAP_MANIFESTS) == 6
    assert {(item.version, item.role) for item in FWAP_MANIFESTS} == {
        (version, role)
        for version in ("v1", "v2")
        for role in ("house", "share", "receipt")
    }
    for manifest in FWAP_MANIFESTS:
        for entry in load_manifest_abi(manifest):
            if entry.get("type") == "function":
                assert entry["stateMutability"] in {"view", "pure"}

    owned = [
        Path("maxpane_dashboard/data/fwa_projects/fwap.py"),
        Path("tests/data/test_fwa_fwap_adapter.py"),
        *Path("tests/fixtures/fwa/ecosystem/fwap").glob("*.json"),
    ]
    forbidden = (
        "author" + "ization:",
        "bear" + "er ",
        "private" + "_key",
        "api" + "-secret",
    )
    for path in owned:
        lowered = path.read_text(encoding="utf-8").lower()
        assert not any(secret in lowered for secret in forbidden)
