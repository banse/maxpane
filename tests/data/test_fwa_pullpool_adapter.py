"""Offline contract tests for PullPool, GroupPull, and order factories."""

from __future__ import annotations

import json
from copy import deepcopy
from inspect import signature
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from maxpane_dashboard.data.evm_abi import decode_uint, strip0x
from maxpane_dashboard.data.fwa_client import MULTICALL3
from maxpane_dashboard.data.fwa_ecosystem_addresses import FWA_TOKEN
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    FWAEcosystemCache,
    Watermark,
    WatermarkKey,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
)
from maxpane_dashboard.data.fwa_logs import LOG_ENDPOINTS
from maxpane_dashboard.data.fwa_projects.base import (
    load_abi_resource,
    load_manifest_abi,
)
from maxpane_dashboard.data.fwa_projects.pullpool import (
    ALL_MANIFESTS,
    LOG_STREAM_BY_KEY,
    ORDER_MANIFESTS,
    PULLPOOL_MANIFESTS,
    STATE_CALLS,
    PullPoolAdapter,
    PullPoolRoundState,
    accumulate_history,
    build_project_rows,
    normalize_events,
    runtime_codehash,
)
from maxpane_dashboard.data.keccak import keccak256_hex
from tests.fwa_ecosystem_fixtures import (
    DenyNetworkTransport,
    FixedClock,
    load_fwa_ecosystem_fixture,
)


def _selector(signature: str) -> str:
    return keccak256_hex(signature.encode("ascii"))[:10]


def _signature(entry: dict[str, Any]) -> str:
    inputs = ",".join(str(item["type"]) for item in entry.get("inputs", []))
    return f"{entry['name']}({inputs})"


def _manifest_key(manifest: Any) -> str:
    return f"{manifest.family}:{manifest.surface}:{manifest.version}"


_MANIFEST_BY_ADDRESS = {manifest.address: manifest for manifest in ALL_MANIFESTS}
_MANIFEST_BY_ID = {
    (manifest.family, manifest.surface, manifest.version): manifest
    for manifest in ALL_MANIFESTS
}
_FUNCTION_BY_ADDRESS_SELECTOR: dict[tuple[str, str], dict[str, Any]] = {}
_EVENT_BY_ID: dict[tuple[str, str], dict[str, Any]] = {}
for _manifest in ALL_MANIFESTS:
    for _entry in load_manifest_abi(_manifest):
        if _entry.get("type") == "function":
            _FUNCTION_BY_ADDRESS_SELECTOR[
                (_manifest.address, _selector(_signature(_entry)))
            ] = _entry
        elif _entry.get("type") == "event":
            _EVENT_BY_ID[(_manifest_key(_manifest), str(_entry["name"]))] = _entry

_BALANCE_OF = _selector("balanceOf(address)")
_IS_DISTRIBUTOR = _selector("isDistributor(address)")
_REAL_RUNTIME_CODEHASH = runtime_codehash
_CODE_BY_ADDRESS = {
    manifest.address: f"0x60{index + 1:02x}"
    for index, manifest in enumerate(ALL_MANIFESTS)
}


def _word(value: Any, kind: str = "uint256") -> str:
    if kind == "address":
        return strip0x(str(value)).lower().rjust(64, "0")
    if kind == "bool":
        value = int(bool(value))
    return f"{int(value):064x}"


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
        call_data = body[
            calldata_start + 64 : calldata_start + 64 + calldata_length * 2
        ]
        calls.append((target.lower(), allow_failure, "0x" + call_data.lower()))
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


def _surface(fixture: dict[str, Any], manifest: Any) -> dict[str, Any]:
    if manifest.surface == "pullpool":
        return fixture["pullpools"][manifest.version]
    if manifest.surface == "group_pull":
        return fixture["group_pull"]
    key = f"{manifest.surface}:{manifest.version}"
    return {"orders_created": fixture["order_factories"][key]}


_FIELD_BY_GETTER = {
    "roundCount": "round_count",
    "accountedEth": "accounted_eth_wei",
    "deprecated": "deprecated",
    "paused": "paused",
    "currentOpenRound": "current_open_round",
    "pendingPullCount": "pending_pull_count",
    "canPayTokens": "can_pay_tokens",
    "fwaAccounted": "accounted_fwa_wei",
    "liveRound": "live_round",
    "buyingRounds": "buying_rounds",
    "orderCount": "orders_created",
}


class SimulatedPullPoolChain:
    """Small semantic Ethereum node backed only by the committed fixtures."""

    def __init__(self, state: dict[str, Any], logs: dict[str, Any]) -> None:
        self.state = state
        self.log_descriptors = logs["events"]
        self.rpc_calls: list[tuple[str, list[Any]]] = []
        self.subcalls: list[tuple[str, str, str]] = []
        self.log_filters: list[dict[str, Any]] = []
        self.failed_calls: set[tuple[str, str]] = set()
        self.failed_log_addresses: set[str] = set()
        self.dependency_overrides: dict[tuple[str, str], str] = {}
        self.distributor_overrides: dict[str, bool] = {}
        self.runtime_mismatches: set[str] = set()
        self.block_hash_overrides: dict[int, str] = {}
        self.include_malformed_log = False

    def _round_result(
        self, manifest: Any, entry: dict[str, Any], round_id: int
    ) -> str:
        surface = _surface(self.state, manifest)
        values = dict(surface["default_round"])
        values.update(surface.get("round_overrides", {}).get(str(round_id), {}))
        components = entry["outputs"][0]["components"]
        return "0x" + "".join(
            _word(values.get(component["name"], 0), component["type"])
            for component in components
        )

    def _token_read(self, calldata: str) -> tuple[bool, str]:
        holder = "0x" + strip0x(calldata)[8:][-40:]
        manifest = _MANIFEST_BY_ADDRESS.get(holder)
        if manifest is None or manifest.role != "pool":
            return False, "0x"
        surface = _surface(self.state, manifest)
        if calldata[:10] == _BALANCE_OF:
            return True, _single(surface["token_balance_wei"])
        if calldata[:10] == _IS_DISTRIBUTOR:
            value = self.distributor_overrides.get(
                _manifest_key(manifest), surface["distributor_enabled"]
            )
            return True, _single(value, "bool")
        return False, "0x"

    def _subcall(self, target: str, calldata: str) -> tuple[bool, str]:
        if target == FWA_TOKEN:
            return self._token_read(calldata)
        manifest = _MANIFEST_BY_ADDRESS.get(target)
        if manifest is None:
            return False, "0x"
        entry = _FUNCTION_BY_ADDRESS_SELECTOR.get((target, calldata[:10]))
        if entry is None:
            return False, "0x"
        name = str(entry["name"])
        key = _manifest_key(manifest)
        if (key, name) in self.failed_calls:
            return False, "0x"

        dependencies = dict(manifest.dependencies)
        if name in dependencies:
            address = self.dependency_overrides.get(
                (key, name), dependencies[name]
            )
            return True, _single(address, "address")
        if name == "getRound":
            round_id = decode_uint("0x" + strip0x(calldata)[8:])
            return True, self._round_result(manifest, entry, round_id)
        field = _FIELD_BY_GETTER.get(name)
        if field is None:
            return False, "0x"
        value = _surface(self.state, manifest)[field]
        output_kind = str(entry["outputs"][0]["type"])
        return True, _single(value, output_kind)

    @staticmethod
    def _event_word(kind: str, value: Any) -> str:
        return _word(value, kind)

    def _encode_event(self, descriptor: dict[str, Any]) -> dict[str, Any]:
        manifest = _MANIFEST_BY_ID[
            (
                descriptor["family"],
                descriptor["surface"],
                descriptor["version"],
            )
        ]
        entry = _EVENT_BY_ID[(_manifest_key(manifest), descriptor["event"])]
        values = descriptor["values"]
        topics = [keccak256_hex(_signature(entry).encode("ascii"))]
        data_words: list[str] = []
        for item in entry.get("inputs", []):
            encoded = self._event_word(item["type"], values[item["name"]])
            (topics if item.get("indexed") else data_words).append(
                "0x" + encoded if item.get("indexed") else encoded
            )
        block = int(descriptor["block_number"])
        return {
            "address": manifest.address,
            "topics": topics,
            "data": "0x" + "".join(data_words),
            "blockNumber": hex(block),
            "blockHash": "0x" + f"{block:064x}",
            "blockTimestamp": hex(int(descriptor["timestamp"])),
            "transactionHash": descriptor["tx_hash"],
            "logIndex": hex(int(descriptor["log_index"])),
            "removed": False,
        }

    def _logs(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        address = str(params["address"]).lower()
        start = int(params["fromBlock"], 16)
        end = int(params["toBlock"], 16)
        topic_group = params["topics"][0]
        accepted = {str(topic).lower() for topic in topic_group}
        rows = []
        for descriptor in self.log_descriptors:
            raw = self._encode_event(descriptor)
            block = int(raw["blockNumber"], 16)
            if (
                raw["address"] == address
                and start <= block <= end
                and raw["topics"][0].lower() in accepted
            ):
                rows.append(raw)
        if self.include_malformed_log:
            rows.append(
                {
                    "address": address,
                    "topics": [next(iter(accepted))],
                    "data": "0x",
                    "blockNumber": hex(start),
                    "transactionHash": "0x1234",
                    "logIndex": "0x0",
                }
            )
        return rows

    def handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        params = payload["params"]
        self.rpc_calls.append((method, params))
        if method == "eth_call":
            assert params[0]["to"].lower() == MULTICALL3
            calls = _decode_aggregate3_calldata(params[0]["data"])
            assert all(allow_failure for _target, allow_failure, _data in calls)
            for target, _allow_failure, calldata in calls:
                self.subcalls.append((target, calldata, params[1]))
            result: Any = _encode_aggregate3_result(
                [self._subcall(target, calldata) for target, _allow, calldata in calls]
            )
        elif method == "eth_getCode":
            address = str(params[0]).lower()
            result = _CODE_BY_ADDRESS[address]
            if address in self.runtime_mismatches:
                result += "ff"
        elif method == "eth_getBlockByNumber":
            block = int(params[0], 16)
            result = {
                "hash": self.block_hash_overrides.get(
                    block,
                    "0x" + f"{block:064x}",
                )
            }
        elif method == "eth_getLogs":
            log_filter = params[0]
            self.log_filters.append(log_filter)
            address = str(log_filter["address"]).lower()
            if address in self.failed_log_addresses:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "error": {"code": -32000, "message": "fixture log failure"},
                    },
                )
            result = self._logs(log_filter)
        else:  # pragma: no cover - unexpected I/O is deliberately loud
            raise AssertionError(f"unexpected RPC method: {method}")
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )


def _fixture(name: str) -> dict[str, Any]:
    return load_fwa_ecosystem_fixture(f"pullpool/{name}.json")


def _fixture_hash(raw: Any) -> str | None:
    for manifest in ALL_MANIFESTS:
        if raw == _CODE_BY_ADDRESS[manifest.address]:
            return manifest.runtime_codehash
    return _REAL_RUNTIME_CODEHASH(raw)


def _adapter(
    http_client: httpx.AsyncClient,
    state: dict[str, Any],
    *,
    page_size: int = 5_000,
    max_pages: int = 2,
) -> PullPoolAdapter:
    return PullPoolAdapter(
        http_client,
        state_endpoints=("https://state.test",),
        log_endpoints=(LOG_ENDPOINTS[0],),
        clock=FixedClock(state["observed_at"]),
        page_size=page_size,
        max_pages=max_pages,
    )


async def _state_and_integrity(
    simulator: SimulatedPullPoolChain,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, DenyNetworkTransport]:
    monkeypatch.setattr(
        "maxpane_dashboard.data.fwa_projects.pullpool.runtime_codehash",
        _fixture_hash,
    )
    transport = DenyNetworkTransport(simulator.handle)
    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, simulator.state)
        try:
            state = await adapter.fetch_state(simulator.state["block_number"])
            integrity = await adapter.fetch_integrity(simulator.state["block_number"])
        finally:
            await adapter.close()
    return state, integrity, transport


def test_vendored_abis_own_every_state_and_dependency_selector() -> None:
    declared_calls = set(_FUNCTION_BY_ADDRESS_SELECTOR)
    token_selectors = {
        _selector(_signature(entry))
        for entry in load_abi_resource("abis/fwa/fwa_token.json")
        if entry.get("type") == "function"
        and entry.get("stateMutability") in ("view", "pure")
    }
    for call in STATE_CALLS:
        if call.address == FWA_TOKEN:
            assert call.calldata[:10] in token_selectors
        else:
            assert (call.address, call.calldata[:10]) in declared_calls

    for manifest in ALL_MANIFESTS:
        functions = {
            str(entry["name"]): entry
            for entry in load_manifest_abi(manifest)
            if entry.get("type") == "function"
        }
        for getter, _expected in manifest.dependencies:
            assert functions[getter]["stateMutability"] in ("view", "pure")
            assert functions[getter].get("inputs", []) == []
            assert (
                manifest.address,
                _selector(f"{getter}()"),
            ) in _FUNCTION_BY_ADDRESS_SELECTOR


def test_wei_native_round_state_is_strict_and_frozen() -> None:
    values = {
        "round_id": 1,
        "state": 0,
        "lifecycle": "unknown",
        "tickets_sold": 1,
        "max_tickets": 10,
        "escrow_wei": 1.5,
        "fee_owed_wei": 0,
        "refund_pool_wei": 0,
        "eth_pot_wei": 0,
        "token_pot_wei": 0,
        "referral_pool_wei": 0,
    }
    with pytest.raises(ValidationError):
        PullPoolRoundState(**values)

    values["escrow_wei"] = 1
    row = PullPoolRoundState(**values)
    with pytest.raises(ValidationError):
        row.escrow_wei = 2


@pytest.mark.asyncio
async def test_state_is_block_pinned_and_keeps_product_accounting_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    state, integrity, transport = await _state_and_integrity(simulator, monkeypatch)

    current = next(surface for surface in state.pullpools if surface.is_current)
    legacy = next(surface for surface in state.pullpools if not surface.is_current)
    assert current.round_count == 367
    assert current.rounds[-1].state == 5
    assert current.rounds[-1].lifecycle == "refunding"
    assert sum(round_.lifecycle == "refunding" for round_ in current.rounds) == 4
    assert sum(round_.lifecycle == "settled" for round_ in current.rounds) == 363
    assert current.accounted_eth_wei == 618943394256984616
    assert legacy.accounted_eth_wei == 0
    assert state.group_pull.round_count == 65
    assert state.group_pull.rounds[-1].state == 5
    assert state.group_pull.rounds[-1].lifecycle == "expired"
    assert state.group_pull.accounted_eth_wei == 1250000000000000000
    assert state.group_pull.accounted_fwa_wei == 250000000000000000000
    assert [factory.orders_created for factory in state.order_factories] == [72, 160, 3]
    assert all(surface.status == "ok" for surface in integrity.surfaces)

    expected_tag = hex(state_fixture["block_number"])
    assert transport.requests
    assert {tag for _target, _calldata, tag in simulator.subcalls} == {expected_tag}
    for method, params in simulator.rpc_calls:
        if method == "eth_call":
            assert params[1] == expected_tag
        elif method == "eth_getCode":
            assert params[1] == expected_tag
    assert "eth_blockNumber" not in [method for method, _params in simulator.rpc_calls]

    rows = build_project_rows(state, integrity=integrity)
    assert all(tuple(row) == PROJECT_ROW_KEYS for row in rows)
    pullpool = next(row for row in rows if row["family"] == "pullpool")
    assert pullpool["primary_label"] == "rounds created"
    assert pullpool["primary_value"] == 367
    assert pullpool["primary_value"] != 367 + 375
    group = next(row for row in rows if row["surface"] == "group_pull")
    assert group["primary_label"] == "packs created"
    assert group["eth_value"] == 1.25
    standing = next(row for row in rows if row["surface"] == "standing_orders")
    assert standing["primary_label"] == "orders created"
    assert "not inferred" in standing["detail"]


@pytest.mark.asyncio
async def test_zero_legacy_liability_is_omitted_but_positive_liability_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_fixture = _fixture("state")
    clean_simulator = SimulatedPullPoolChain(clean_fixture, _fixture("logs"))
    state, integrity, _transport = await _state_and_integrity(
        clean_simulator, monkeypatch
    )
    assert not any(
        row["surface"] == "pullpool" and row["version"] == "v1"
        for row in build_project_rows(state, integrity=integrity)
    )

    liability_fixture = deepcopy(clean_fixture)
    liability_fixture["pullpools"]["v1"]["accounted_eth_wei"] = 7
    liability_simulator = SimulatedPullPoolChain(liability_fixture, _fixture("logs"))
    state, integrity, _transport = await _state_and_integrity(
        liability_simulator, monkeypatch
    )
    legacy = next(
        row
        for row in build_project_rows(state, integrity=integrity)
        if row["surface"] == "pullpool" and row["version"] == "v1"
    )
    assert legacy["is_legacy_liability"] is True
    assert legacy["eth_value"] == 7e-18


@pytest.mark.asyncio
async def test_dependency_mismatch_suppresses_only_that_surface_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    standing_v2 = next(
        manifest
        for manifest in ORDER_MANIFESTS
        if manifest.surface == "standing_orders" and manifest.version == "v2"
    )
    simulator.dependency_overrides[
        (_manifest_key(standing_v2), "pool")
    ] = "0x9999999999999999999999999999999999999999"
    state, integrity, _transport = await _state_and_integrity(simulator, monkeypatch)

    rows = build_project_rows(state, integrity=integrity)
    standing = next(
        row
        for row in rows
        if row["surface"] == "standing_orders" and row["version"] == "v2"
    )
    pullpool = next(row for row in rows if row["family"] == "pullpool")
    assert standing["integrity"] == "mismatch"
    assert standing["source_badge"] == "INTEGRITY"
    assert standing["primary_value"] is None
    assert pullpool["integrity"] == "ok"
    assert pullpool["primary_value"] == 367


@pytest.mark.asyncio
async def test_distributor_loss_is_operational_warning_not_fake_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    current = next(manifest for manifest in PULLPOOL_MANIFESTS if manifest.is_current)
    simulator.distributor_overrides[_manifest_key(current)] = False
    state, integrity, _transport = await _state_and_integrity(simulator, monkeypatch)

    row = next(
        row
        for row in build_project_rows(state, integrity=integrity)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    assert row["integrity"] == "warning"
    assert row["source_badge"] == "DEGRADED"
    assert "FWA claims blocked" in row["lifecycle"]
    assert row["primary_value"] == 367
    assert row["eth_value"] == pytest.approx(0.6189433942569846)


@pytest.mark.asyncio
async def test_failed_satellite_factory_leaves_current_pullpool_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    group_factory = next(
        manifest for manifest in ORDER_MANIFESTS if manifest.surface == "group_orders"
    )
    simulator.failed_calls.add((_manifest_key(group_factory), "orderCount"))
    state, integrity, _transport = await _state_and_integrity(simulator, monkeypatch)

    current = next(surface for surface in state.pullpools if surface.is_current)
    failed = next(
        factory for factory in state.order_factories if factory.surface == "group_orders"
    )
    assert current.available is True
    assert current.round_count == 367
    assert failed.available is False
    assert failed.orders_created is None
    rows = build_project_rows(state, integrity=integrity)
    pullpool = next(row for row in rows if row["family"] == "pullpool")
    group_orders = next(row for row in rows if row["surface"] == "group_orders")
    assert pullpool["source_badge"] == "VERIFIED"
    assert group_orders["source_badge"] == "DEGRADED"
    assert group_orders["primary_value"] is None


@pytest.mark.asyncio
async def test_log_pages_dedupe_overlap_and_emit_cache_compatible_progress() -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    transport = DenyNetworkTransport(simulator.handle)
    key = WatermarkKey(adapter="pullpool", version="v2", topic_group="lifecycle")
    deployment = LOG_STREAM_BY_KEY[key].manifest.deployment_block

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=2, max_pages=2)
        try:
            read = await adapter.fetch_logs(
                deployment,
                deployment + 3,
                stream_keys=(key,),
            )
            last = read.progress[-1]
            watermark = Watermark(
                block_number=last.to_block,
                block_hash=last.last_block_hash or "",
                overlap=2,
                updated_at=state_fixture["observed_at"],
            )
            overlap_read = await adapter.fetch_logs(
                deployment,
                deployment + 5,
                watermarks={key: watermark},
                history_complete=True,
                stream_keys=(key,),
            )
        finally:
            await adapter.close()

    assert read.available is True
    assert read.history_complete is True
    assert read.history_complete_versions == ("pullpool:pullpool:v2",)
    assert len(read.events) == 4
    assert len({event.event_id for event in read.events}) == 4
    assert all(progress.page_complete for progress in read.progress)
    assert all(progress.watermark_key == key for progress in read.progress)
    # A caller flag cannot bless a watermark-resumed tail as full history.
    assert overlap_read.history_complete is False
    assert overlap_read.history_complete_versions == ()
    assert simulator.log_filters[-2]["fromBlock"] == hex(deployment + 2)
    assert len({event.event_id for event in overlap_read.events}) == len(
        overlap_read.events
    )


@pytest.mark.asyncio
async def test_malformed_filtered_log_marks_page_incomplete_without_fake_event() -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    simulator.include_malformed_log = True
    transport = DenyNetworkTransport(simulator.handle)
    key = WatermarkKey(adapter="pullpool", version="v2", topic_group="lifecycle")
    deployment = LOG_STREAM_BY_KEY[key].manifest.deployment_block

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=10, max_pages=1)
        try:
            read = await adapter.fetch_logs(
                deployment,
                deployment,
                stream_keys=(key,),
            )
        finally:
            await adapter.close()

    assert read.available is False
    assert read.history_complete is False
    assert read.history_complete_versions == ()
    assert read.failed_streams == ("pullpool:v2:lifecycle",)
    assert [event.event_key for event in read.events] == ["round_opened"]
    assert read.progress[0].page_complete is False


@pytest.mark.asyncio
async def test_raw_logs_and_history_stale_to_state_never_claim_exact_liability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    monkeypatch.setattr(
        "maxpane_dashboard.data.fwa_projects.pullpool.runtime_codehash",
        _fixture_hash,
    )
    transport = DenyNetworkTransport(simulator.handle)
    current_key = WatermarkKey(
        adapter="pullpool", version="v2", topic_group="lifecycle"
    )
    deployment = LOG_STREAM_BY_KEY[current_key].manifest.deployment_block
    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=2, max_pages=2)
        try:
            state = await adapter.fetch_state(state_fixture["block_number"])
            integrity = await adapter.fetch_integrity(state_fixture["block_number"])
            logs = await adapter.fetch_logs(
                deployment,
                deployment + 3,
                stream_keys=(current_key,),
            )
        finally:
            await adapter.close()

    history = accumulate_history(None, logs)
    raw_row = next(
        row
        for row in build_project_rows(state, logs=logs, integrity=integrity)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    stale_row = next(
        row
        for row in build_project_rows(state, history=history, integrity=integrity)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    assert logs.history_complete is True
    assert history.covers(current_key, deployment + 3)
    assert not history.covers(current_key, state.block_number)
    for row in (raw_row, stale_row):
        assert row["fwa_label"] == "held claims upper bound"
        assert row["fwa_value"] == pytest.approx(155442.97978591107)
        assert "history incomplete" in row["detail"]

    events = normalize_events(logs, integrity=integrity)
    assert all(tuple(event) == NETWORK_EVENT_ROW_KEYS for event in events)
    assert [event["event_key"] for event in events] == [
        "share_claimed",
        "round_reward_credited",
        "round_settled",
        "round_opened",
    ]
    assert all(event["version"] == "v2" for event in events)
    assert all(event["origin"] == "PullPool" for event in events)
    assert events[0]["fwa_amount"] == 200.0


@pytest.mark.asyncio
async def test_accumulated_complete_pages_unlock_exact_liability() -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    transport = DenyNetworkTransport(simulator.handle)
    key = WatermarkKey(adapter="pullpool", version="v2", topic_group="lifecycle")
    deployment = LOG_STREAM_BY_KEY[key].manifest.deployment_block

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=2, max_pages=1)
        try:
            state = await adapter.fetch_state(deployment + 3)
            first = await adapter.fetch_logs(
                deployment,
                deployment + 1,
                stream_keys=(key,),
            )
            second = await adapter.fetch_logs(
                deployment + 2,
                deployment + 3,
                stream_keys=(key,),
            )
        finally:
            await adapter.close()

    history = accumulate_history(accumulate_history(None, first), second)
    assert len({event.event_id for event in history.events}) == 4
    assert history.covers(key, state.block_number)
    row = next(
        row
        for row in build_project_rows(state, history=history)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    assert row["fwa_label"] == "outstanding claims"
    assert row["fwa_value"] == 400.0


@pytest.mark.asyncio
async def test_restart_tail_without_prior_fold_requires_deployment_rebuild() -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    transport = DenyNetworkTransport(simulator.handle)
    key = WatermarkKey(adapter="pullpool", version="v2", topic_group="lifecycle")
    deployment = LOG_STREAM_BY_KEY[key].manifest.deployment_block
    watermark = Watermark(
        block_number=deployment + 2,
        block_hash="0x" + f"{deployment + 2:064x}",
        overlap=1,
        updated_at=state_fixture["observed_at"],
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=2, max_pages=2)
        try:
            state = await adapter.fetch_state(deployment + 3)
            tail = await adapter.fetch_logs(
                deployment,
                deployment + 3,
                watermarks={key: watermark},
                history_complete=True,
                stream_keys=(key,),
            )
            rebuilt = await adapter.fetch_logs(
                deployment,
                deployment + 3,
                stream_keys=(key,),
            )
        finally:
            await adapter.close()

    tail_history = accumulate_history(None, tail)
    assert tail.streams[0].scan_from_block == deployment + 2
    assert tail.history_complete is False
    assert not tail_history.covers(key, state.block_number)
    tail_row = next(
        row
        for row in build_project_rows(state, history=tail_history)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    assert tail_row["fwa_label"] == "held claims upper bound"

    rebuilt_history = accumulate_history(None, rebuilt)
    rebuilt_row = next(
        row
        for row in build_project_rows(state, history=rebuilt_history)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    assert rebuilt_history.covers(key, state.block_number)
    assert rebuilt_row["fwa_label"] == "outstanding claims"
    assert rebuilt_row["fwa_value"] == 400.0


@pytest.mark.asyncio
async def test_reorg_replaces_overlap_before_cache_watermark_advances(
    tmp_path: Path,
) -> None:
    state_fixture = _fixture("state")
    logs_fixture = _fixture("logs")
    simulator = SimulatedPullPoolChain(state_fixture, logs_fixture)
    transport = DenyNetworkTransport(simulator.handle)
    key = WatermarkKey(adapter="pullpool", version="v2", topic_group="lifecycle")
    deployment = LOG_STREAM_BY_KEY[key].manifest.deployment_block
    cache = FWAEcosystemCache(
        path=str(tmp_path / "cache.json"),
        clock=FixedClock(state_fixture["observed_at"]),
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=2, max_pages=2)
        try:
            initial = await adapter.fetch_logs(
                deployment,
                deployment + 3,
                stream_keys=(key,),
            )
            history = accumulate_history(None, initial)
            last = initial.progress[-1]
            cache.set_watermark(
                key,
                block_number=last.to_block,
                block_hash=last.last_block_hash or "",
                overlap=2,
                page_complete=True,
                ts=state_fixture["observed_at"],
            )

            orphan = next(
                event
                for event in simulator.log_descriptors
                if event["tx_hash"] == "0x" + "05" * 32
            )
            replacement = deepcopy(orphan)
            replacement["tx_hash"] = "0x" + "aa" * 32
            replacement["values"]["tokenAmount"] = 100 * 10**18
            simulator.log_descriptors = [
                event
                for event in simulator.log_descriptors
                if event["tx_hash"] != orphan["tx_hash"]
            ]
            simulator.log_descriptors.append(replacement)
            simulator.block_hash_overrides[deployment + 3] = "0x" + "f" * 64

            replacement_read = await adapter.fetch_logs(
                deployment + 5,
                deployment + 5,
                cache=cache,
                stream_keys=(key,),
            )
            assert replacement_read.streams[0].reorged is True
            assert replacement_read.streams[0].scan_from_block == deployment + 2
            assert cache.scan_start(key, deployment_block=deployment) == deployment + 2

            history = accumulate_history(history, replacement_read, cache=cache)
            state = await adapter.fetch_state(deployment + 5)
        finally:
            await adapter.close()

    tx_hashes = {event.tx_hash for event in history.events}
    assert "0x" + "05" * 32 not in tx_hashes
    assert replacement["tx_hash"] in tx_hashes
    assert history.covers(key, state.block_number)
    assert cache.get_watermark(key).block_number == deployment + 5
    row = next(
        row
        for row in build_project_rows(state, history=history)
        if row["surface"] == "pullpool" and row["version"] == "v2"
    )
    assert row["fwa_label"] == "outstanding claims"
    assert row["fwa_value"] == 500.0


@pytest.mark.asyncio
async def test_integrity_mismatch_suppresses_event_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    current = next(manifest for manifest in PULLPOOL_MANIFESTS if manifest.is_current)
    simulator.dependency_overrides[
        (_manifest_key(current), "FWA")
    ] = "0x9999999999999999999999999999999999999999"
    monkeypatch.setattr(
        "maxpane_dashboard.data.fwa_projects.pullpool.runtime_codehash",
        _fixture_hash,
    )
    transport = DenyNetworkTransport(simulator.handle)
    key = WatermarkKey(adapter="pullpool", version="v2", topic_group="lifecycle")
    deployment = LOG_STREAM_BY_KEY[key].manifest.deployment_block

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=10, max_pages=1)
        try:
            integrity = await adapter.fetch_integrity(state_fixture["block_number"])
            logs = await adapter.fetch_logs(
                deployment,
                deployment + 3,
                stream_keys=(key,),
            )
        finally:
            await adapter.close()

    rows = normalize_events(logs, integrity=integrity)
    assert rows
    assert all(row["event_key"] == "integrity_mismatch" for row in rows)
    assert all(row["event_label"] == "Untrusted contract log" for row in rows)
    assert all(row["eth_amount"] is None for row in rows)
    assert all(row["fwa_amount"] is None for row in rows)
    assert all(row["verified_source"] is False for row in rows)
    assert all(row["integrity"] == "mismatch" for row in rows)
    assert all("round" not in row["detail"] for row in rows)


@pytest.mark.asyncio
async def test_group_and_factory_events_keep_their_origin_and_version() -> None:
    state_fixture = _fixture("state")
    logs_fixture = _fixture("logs")
    simulator = SimulatedPullPoolChain(state_fixture, logs_fixture)
    transport = DenyNetworkTransport(simulator.handle)
    start = min(manifest.deployment_block for manifest in ALL_MANIFESTS)
    end = max(int(event["block_number"]) for event in logs_fixture["events"])

    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=100_000, max_pages=1)
        try:
            logs = await adapter.fetch_logs(start, end)
        finally:
            await adapter.close()

    assert logs.history_complete is True
    assert len(logs.history_complete_versions) == len(ALL_MANIFESTS)
    rows = normalize_events(logs)
    assert len(rows) == 9
    by_tx = {row["tx_hash"]: row for row in rows}
    assert by_tx["0x" + "06" * 32]["origin"] == "GroupPull"
    assert by_tx["0x" + "07" * 32]["origin"] == "Standing Orders"
    group_order = by_tx["0x" + "09" * 32]
    assert group_order["origin"] == "Group Orders"
    assert group_order["family"] == "group_pull"
    assert group_order["version"] == "v1"
    assert group_order["event_label"] == "Group order created"
    assert "tickets / round 4" in group_order["detail"]


@pytest.mark.asyncio
async def test_failed_log_satellite_cannot_claim_complete_history() -> None:
    state_fixture = _fixture("state")
    simulator = SimulatedPullPoolChain(state_fixture, _fixture("logs"))
    group_key = WatermarkKey(
        adapter="group_orders", version="v1", topic_group="orders"
    )
    pull_key = WatermarkKey(
        adapter="pullpool", version="v2", topic_group="lifecycle"
    )
    simulator.failed_log_addresses.add(LOG_STREAM_BY_KEY[group_key].manifest.address)
    start = min(
        LOG_STREAM_BY_KEY[pull_key].manifest.deployment_block,
        LOG_STREAM_BY_KEY[group_key].manifest.deployment_block,
    )
    end = max(
        LOG_STREAM_BY_KEY[pull_key].manifest.deployment_block + 3,
        LOG_STREAM_BY_KEY[group_key].manifest.deployment_block + 1,
    )
    transport = DenyNetworkTransport(simulator.handle)
    async with httpx.AsyncClient(transport=transport) as http_client:
        adapter = _adapter(http_client, state_fixture, page_size=100_000, max_pages=1)
        try:
            read = await adapter.fetch_logs(
                start,
                end,
                history_complete=True,
                stream_keys=(pull_key, group_key),
            )
        finally:
            await adapter.close()

    assert read.available is False
    assert read.history_complete is False
    assert read.history_complete_versions == ("pullpool:pullpool:v2",)
    assert read.failed_streams == ("group_orders:v1:orders",)
    assert {event.version for event in read.events} == {"v2"}
    assert any(not progress.page_complete for progress in read.progress)


def test_runtime_hash_and_constructor_boundaries_are_hardened() -> None:
    assert tuple(signature(PullPoolAdapter).parameters) == (
        "http_client",
        "state_endpoints",
        "log_endpoints",
        "clock",
        "page_size",
        "max_pages",
        "overlap",
    )
    assert runtime_codehash("0x6001") == keccak256_hex(bytes.fromhex("6001"))
    assert runtime_codehash("0x") == keccak256_hex(b"")
    assert runtime_codehash("0x1") is None
    assert runtime_codehash("not-hex") is None
    assert runtime_codehash(None) is None

    with pytest.raises(ValueError, match="state_endpoints"):
        PullPoolAdapter(state_endpoints=())
    with pytest.raises(ValueError, match="log_endpoints"):
        PullPoolAdapter(log_endpoints=())
    with pytest.raises(ValueError, match="Pool-B"):
        PullPoolAdapter(log_endpoints=("https://state.test",))
    with pytest.raises(ValueError, match="1..5000"):
        PullPoolAdapter(overlap=5_001)
