"""Offline contract tests for manager-enumerated FWAIR drops."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from maxpane_dashboard.data.evm_abi import decode_uint, strip0x
from maxpane_dashboard.data.fwa_client import MULTICALL3
from maxpane_dashboard.data.fwa_drops_client import (
    COLLECTION_NAME_SELECTOR,
    FWAIRDropsClient,
    FWAIRDropsRead,
    FWAIR_LAUNCH_EVENT_SPECS,
    FWAIR_MANAGER_EVENT_SPECS,
    FWAIRLaunchState,
    LAUNCH_SELECTORS,
    MANAGER_SELECTORS,
    MAX_LAUNCHES_PER_REFRESH,
    normalize_fwair_events,
    phase_name,
    runtime_codehash,
)
from maxpane_dashboard.data.fwa_ecosystem_addresses import (
    FWA_CORE,
    FWA_TOKEN,
    FWAIR_MANAGER,
    FWAIR_WHITELIST_AUTHORITY,
    OFFICIAL_BY_ROLE,
)
from maxpane_dashboard.data.fwa_ecosystem_models import DROP_PHASES, DROP_ROW_KEYS
from maxpane_dashboard.data.fwa_projects import load_abi_resource
from maxpane_dashboard.data.keccak import keccak256_hex
from tests.fwa_ecosystem_fixtures import (
    DenyNetworkTransport,
    FixedClock,
    load_fwa_ecosystem_fixture,
)

_REAL_RUNTIME_CODEHASH = runtime_codehash
_VALID_CHILD_CODE = "0x6001"
_MISMATCH_CHILD_CODE = "0x6002"
_MANAGER_CODE = "0x6000"
_CHILD_CODEHASH = _REAL_RUNTIME_CODEHASH(_VALID_CHILD_CODE)
assert _CHILD_CODEHASH is not None


def _uint_word(value: int) -> str:
    return "0x" + f"{value:064x}"


def _address_word(value: str) -> str:
    return "0x" + strip0x(value).lower().rjust(64, "0")


def _string_result(value: str) -> str:
    raw = value.encode("utf-8").hex()
    padded = raw + "0" * ((64 - len(raw) % 64) % 64)
    return "0x" + f"{32:064x}{len(value.encode('utf-8')):064x}" + padded


def _event_word(type_name: str, value: Any) -> str:
    if type_name == "address":
        return strip0x(str(value)).lower().rjust(64, "0")
    if type_name == "bool":
        return f"{int(bool(value)):064x}"
    if type_name == "bytes32":
        return strip0x(str(value)).lower().rjust(64, "0")
    return f"{int(value):064x}"


def _event_log(
    *,
    address: str,
    event: str,
    values: dict[str, Any],
    block: int,
    index: int,
) -> dict[str, Any]:
    specs = (
        FWAIR_MANAGER_EVENT_SPECS
        if address == FWAIR_MANAGER
        else FWAIR_LAUNCH_EVENT_SPECS
    )
    topic0, entry = next(
        (topic, candidate)
        for topic, candidate in specs.items()
        if candidate["name"] == event
    )
    topics = [topic0]
    data: list[str] = []
    for item in entry["inputs"]:
        encoded = _event_word(item["type"], values[item["name"]])
        (topics if item["indexed"] else data).append(
            "0x" + encoded if item["indexed"] else encoded
        )
    return {
        "address": address,
        "topics": topics,
        "data": "0x" + "".join(data),
        "blockNumber": hex(block),
        "blockTimestamp": hex(1_787_000_000 + block),
        "transactionHash": "0x" + f"{block * 10 + index:064x}",
        "logIndex": hex(index),
        "removed": False,
    }


def _decode_aggregate3_calldata(data: str) -> list[tuple[str, bool, str]]:
    """Inverse of the shared aggregate3 encoder."""

    raw = strip0x(data)
    assert raw[:8] == "82ad56cb"
    body = raw[8:]
    array_offset = int(body[:64], 16) * 2
    count = int(body[array_offset : array_offset + 64], 16)
    base = array_offset + 64
    calls: list[tuple[str, bool, str]] = []
    for index in range(count):
        tuple_offset = int(body[base + index * 64 : base + (index + 1) * 64], 16) * 2
        start = base + tuple_offset
        target = "0x" + body[start + 24 : start + 64]
        allow_failure = int(body[start + 64 : start + 128], 16) != 0
        calldata_offset = int(body[start + 128 : start + 192], 16) * 2
        calldata_start = start + calldata_offset
        calldata_length = int(body[calldata_start : calldata_start + 64], 16)
        call_data = body[
            calldata_start + 64 : calldata_start + 64 + calldata_length * 2
        ]
        calls.append((target.lower(), allow_failure, "0x" + call_data.lower()))
    return calls


def _encode_aggregate3_result(results: list[tuple[bool, str]]) -> str:
    """Encode Solidity ``Result[] (bool success, bytes returnData)``."""

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


_CHILD_FIELD_BY_SIGNATURE = {
    "supportStart()": "support_start",
    "supportDeadline()": "support_deadline",
    "tokenCount()": "token_count",
    "supportedCount()": "supported_count",
    "supporterCount()": "supporter_count",
    "launchedCount()": "launched_count",
    "terminalCount()": "terminal_count",
    "backingPrice()": "backing_wei",
    "totalRequiredBacking()": "total_backing_wei",
    "artistETHCredit()": "artist_credit_wei",
    "totalPrincipalCredit()": "supporter_principal_wei",
    "supporterTokenReserve()": "supporter_reserve_wei",
}
_MANAGER_SIGNATURE_BY_SELECTOR = {
    selector: signature for signature, selector in MANAGER_SELECTORS.items()
}
_CHILD_SIGNATURE_BY_SELECTOR = {
    selector: signature for signature, selector in LAUNCH_SELECTORS.items()
}


class SimulatedFWAIR:
    """A semantic, deterministic Ethereum node behind a deny-network transport."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture
        self.rpc_calls: list[tuple[str, list[Any]]] = []
        self.subcalls: list[tuple[str, str, str]] = []

    @property
    def launches(self) -> dict[str, Any]:
        return self.fixture["launches"]

    def _launch_by_address(self, address: str) -> tuple[int, dict[str, Any]] | None:
        for raw_id, launch in self.launches.items():
            if isinstance(launch, dict) and launch["address"].lower() == address:
                return int(raw_id), launch
        return None

    def _launch_by_collection(self, address: str) -> tuple[int, dict[str, Any]] | None:
        for raw_id, launch in self.launches.items():
            if isinstance(launch, dict) and launch["collection"].lower() == address:
                return int(raw_id), launch
        return None

    def _manager_read(self, signature: str, calldata: str) -> tuple[bool, str]:
        if signature in self.fixture.get("failed_manager_calls", []):
            return False, "0x"
        if signature == "nextLaunchId()":
            return True, _uint_word(self.fixture["next_launch_id"])
        if signature == "launchRuntimeCodeHash()":
            return True, self.fixture.get(
                "launch_runtime_codehash", _CHILD_CODEHASH
            )
        if signature == "fwa()":
            return True, _address_word(self.fixture.get("manager_fwa", FWA_CORE))
        if signature == "whitelistAuthority()":
            return True, _address_word(
                self.fixture.get("manager_authority", FWAIR_WHITELIST_AUTHORITY)
            )
        if signature == "launches(uint256)":
            launch_id = decode_uint("0x" + strip0x(calldata)[8:])
            launch = self.launches.get(str(launch_id))
            address = launch["address"] if isinstance(launch, dict) else "0x" + "0" * 40
            return True, _address_word(address)
        if signature == "isLaunch(address)":
            address = "0x" + strip0x(calldata)[8:][-40:]
            found = self._launch_by_address(address)
            value = bool(found and found[1].get("is_launch", True))
            return True, _uint_word(int(value))
        return False, "0x"

    def _child_read(
        self, launch_id: int, launch: dict[str, Any], signature: str
    ) -> tuple[bool, str]:
        if signature in launch.get("failed_calls", []):
            return False, "0x"
        if signature == "manager()":
            return True, _address_word(launch.get("manager", FWAIR_MANAGER))
        if signature == "fwa()":
            return True, _address_word(launch.get("fwa", FWA_CORE))
        if signature == "rewardToken()":
            return True, _address_word(launch.get("reward_token", FWA_TOKEN))
        if signature == "launchId()":
            return True, _uint_word(launch.get("reported_launch_id", launch_id))
        if signature == "collection()":
            return True, _address_word(launch["collection"])
        if signature == "phase()":
            return True, _uint_word(launch["phase"])
        if signature == "registered()":
            return True, _uint_word(int(launch.get("registered", True)))
        field = _CHILD_FIELD_BY_SIGNATURE.get(signature)
        if field is not None:
            return True, _uint_word(launch[field])
        return False, "0x"

    def _subcall(self, target: str, calldata: str) -> tuple[bool, str]:
        selector = calldata[:10]
        if target == FWAIR_MANAGER:
            signature = _MANAGER_SIGNATURE_BY_SELECTOR.get(selector)
            return (
                self._manager_read(signature, calldata)
                if signature is not None
                else (False, "0x")
            )
        launch_match = self._launch_by_address(target)
        if launch_match is not None:
            launch_id, launch = launch_match
            signature = _CHILD_SIGNATURE_BY_SELECTOR.get(selector)
            return (
                self._child_read(launch_id, launch, signature)
                if signature is not None
                else (False, "0x")
            )
        collection_match = self._launch_by_collection(target)
        if collection_match is not None and selector == COLLECTION_NAME_SELECTOR:
            _launch_id, launch = collection_match
            if launch.get("name_call_failed"):
                return False, "0x"
            if launch.get("malformed_name"):
                return True, "0x1234"
            return True, _string_result(launch["name"])
        return False, "0x"

    def handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        params = payload["params"]
        self.rpc_calls.append((method, params))
        if method == "eth_blockNumber":
            result: Any = hex(self.fixture.get("head", self.fixture["block_number"]))
        elif method == "eth_getBlockByNumber":
            timestamp = self.fixture.get("block_timestamp")
            result = {} if timestamp is None else {"timestamp": hex(timestamp)}
        elif method == "eth_getCode":
            address = params[0].lower()
            if address == FWAIR_MANAGER:
                result = (
                    "0x6003" if self.fixture.get("manager_runtime_mismatch") else _MANAGER_CODE
                )
            else:
                match = self._launch_by_address(address)
                if match is None or match[1].get("code_unavailable"):
                    result = "not-hex"
                elif match[1].get("runtime_mismatch"):
                    result = _MISMATCH_CHILD_CODE
                else:
                    result = _VALID_CHILD_CODE
        elif method == "eth_call":
            assert params[0]["to"].lower() == MULTICALL3
            tag = params[1]
            calls = _decode_aggregate3_calldata(params[0]["data"])
            assert all(allow_failure for _, allow_failure, _ in calls)
            for target, _allow, calldata in calls:
                self.subcalls.append((target, calldata, tag))
            result = _encode_aggregate3_result(
                [self._subcall(target, calldata) for target, _, calldata in calls]
            )
        else:  # pragma: no cover - an unexpected method must be loud
            raise AssertionError(f"unexpected RPC method: {method}")
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )


async def _run(
    fixture: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    explicit_block: bool = False,
) -> tuple[Any, SimulatedFWAIR, DenyNetworkTransport]:
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)

    _patch_runtime_hash(monkeypatch)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        result = await client.fetch_drops(
            block_number=fixture["block_number"] if explicit_block else None
        )
    return result, simulator, transport


def _patch_runtime_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    def manager_aware_hash(raw: Any) -> str | None:
        if raw == _MANAGER_CODE:
            return OFFICIAL_BY_ROLE["fwair_manager"].runtime_codehash
        return _REAL_RUNTIME_CODEHASH(raw)

    monkeypatch.setattr(
        "maxpane_dashboard.data.fwa_drops_client.runtime_codehash",
        manager_aware_hash,
    )


def _fixture(name: str) -> dict[str, Any]:
    return load_fwa_ecosystem_fixture(f"drops/{name}.json")


@pytest.mark.parametrize("index,expected", tuple(enumerate(DROP_PHASES[:-1])))
def test_seven_source_phases_map_to_frozen_vocabulary(index: int, expected: str) -> None:
    assert phase_name(index) == expected


@pytest.mark.parametrize("value", [-1, 7, 999, True, "2", None])
def test_unknown_or_malformed_phase_never_claims_a_known_state(value: Any) -> None:
    assert phase_name(value) == "unknown"


def test_selected_surface_is_derived_from_vendored_view_abis() -> None:
    abi_by_resource = {
        "manager": load_abi_resource("abis/fwa/fwair_manager.json"),
        "launch": load_abi_resource("abis/fwa/fwair_launch.json"),
    }
    declared: dict[str, dict[str, str]] = {"manager": {}, "launch": {}}
    for role, abi in abi_by_resource.items():
        for entry in abi:
            if entry.get("type") != "function":
                continue
            signature = (
                f"{entry['name']}("
                + ",".join(item["type"] for item in entry.get("inputs", []))
                + ")"
            )
            declared[role][signature] = entry["stateMutability"]
    for signature, selector in MANAGER_SELECTORS.items():
        assert declared["manager"][signature] == "view"
        assert selector == keccak256_hex(signature.encode())[:10]
    for signature, selector in LAUNCH_SELECTORS.items():
        assert declared["launch"][signature] == "view"
        assert selector == keccak256_hex(signature.encode())[:10]
    assert COLLECTION_NAME_SELECTOR == keccak256_hex(b"name()")[:10]


def test_wei_native_launch_state_rejects_float() -> None:
    values = {
        "launch_id": 1,
        "launch_address": "0x" + "1" * 40,
        "collection_address": "0x" + "2" * 40,
        "collection_name": "Drop",
        "phase_index": 2,
        "support_start": 1,
        "support_deadline": 2,
        "token_count": 1,
        "supported_count": 1,
        "supporter_count": 1,
        "launched_count": 0,
        "terminal_count": 0,
        "backing_wei": 1.5,
        "total_backing_wei": 1,
        "artist_credit_wei": 0,
        "supporter_principal_wei": 0,
        "supporter_reserve_wei": 0,
    }
    with pytest.raises(ValidationError):
        FWAIRLaunchState(**values)


@pytest.mark.asyncio
async def test_two_launches_decode_exact_rows_and_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    result, _simulator, _transport = await _run(fixture, monkeypatch)

    assert result.available is True
    assert result.integrity == "ok"
    assert result.next_launch_id == 3
    assert result.registry_fingerprint == _CHILD_CODEHASH
    assert result.enumeration_reset is False
    assert result.valid_count == 2
    assert result.holes == ()
    assert [row.launch_id for row in result.rows] == [1, 2]
    assert all(tuple(row.model_dump()) == DROP_ROW_KEYS for row in result.rows)
    first, second = result.rows
    assert first.collection_name == "First Drop"
    assert first.phase == "complete"
    assert first.support_open is False
    assert first.backing_eth == 0.25
    assert first.total_backing_eth == 27.75
    assert first.artist_credit_eth == 0.0
    assert second.phase == "supporting"
    assert second.support_open is True
    assert second.supporter_count == 145
    assert second.supporter_reserve_fwa == pytest.approx(11555.862078983022)
    assert second.block_number == fixture["block_number"]
    assert second.observed_at == fixture["observed_at"]
    with pytest.raises(ValidationError, match="registry_fingerprint"):
        FWAIRDropsRead.model_validate(
            {**result.model_dump(), "registry_fingerprint": "0x1234"}
        )
    with pytest.raises(ValidationError, match="enumeration_reset"):
        FWAIRDropsRead.model_validate(
            {**result.model_dump(), "enumeration_reset": 1}
        )


@pytest.mark.asyncio
async def test_every_manager_child_code_and_name_read_uses_one_block_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    result, simulator, transport = await _run(fixture, monkeypatch)
    expected_tag = hex(fixture["block_number"])

    assert result.state_block == fixture["block_number"]
    assert transport.requests
    assert all(tag == expected_tag for _, _, tag in simulator.subcalls)
    for method, params in simulator.rpc_calls:
        if method == "eth_call":
            assert params[1] == expected_tag
        elif method == "eth_getCode":
            assert params[1] == expected_tag
        elif method == "eth_getBlockByNumber":
            assert params == [expected_tag, False]


@pytest.mark.asyncio
async def test_explicit_block_skips_head_lookup_but_keeps_every_read_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    result, simulator, _transport = await _run(
        fixture, monkeypatch, explicit_block=True
    )
    assert result.available
    assert "eth_blockNumber" not in [method for method, _ in simulator.rpc_calls]
    assert {tag for _, _, tag in simulator.subcalls} == {hex(fixture["block_number"])}


@pytest.mark.asyncio
async def test_zero_address_hole_does_not_suppress_later_valid_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _simulator, _transport = await _run(
        _fixture("hole_then_valid"), monkeypatch
    )
    assert result.available
    assert result.integrity == "warning"
    assert result.holes == (2,)
    assert [row.launch_id for row in result.rows] == [1, 3]
    assert result.rows[-1].collection_name == "Later Valid Drop"


@pytest.mark.asyncio
async def test_failed_child_is_a_hole_and_later_id_still_decodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("third_launch")
    fixture["launches"]["2"]["failed_calls"] = ["manager()"]
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    assert result.holes == (2,)
    assert [row.launch_id for row in result.rows] == [1, 3]
    assert "launch_2_child_read_failed" in result.issues


@pytest.mark.asyncio
async def test_malformed_collection_name_is_a_hole_not_an_enumeration_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("third_launch")
    fixture["launches"]["2"]["malformed_name"] = True
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    assert result.holes == (2,)
    assert [row.launch_id for row in result.rows] == [1, 3]
    assert "launch_2_name_unavailable" in result.issues


@pytest.mark.asyncio
async def test_new_third_launch_appears_from_next_launch_id_without_code_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("third_launch")
    result, simulator, _transport = await _run(fixture, monkeypatch)
    assert [row.launch_id for row in result.rows] == [1, 2, 3]
    assert result.rows[-1].collection_name == "New Third Drop"
    launch_getter_calls = [
        calldata
        for target, calldata, _ in simulator.subcalls
        if target == FWAIR_MANAGER
        and calldata.startswith(MANAGER_SELECTORS["launches(uint256)"])
    ]
    assert len(launch_getter_calls) == fixture["next_launch_id"] - 1


@pytest.mark.asyncio
async def test_child_runtime_mismatch_suppresses_all_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _simulator, _transport = await _run(
        _fixture("hash_mismatch"), monkeypatch
    )
    assert result.integrity == "mismatch"
    assert result.integrity_mismatch_ids == (2,)
    assert result.holes == ()
    assert result.valid_count == 1
    row = result.rows[1]
    assert row.launch_id == 2
    assert row.integrity == "mismatch"
    assert row.verified_source is False
    assert row.phase == "unknown"
    for key in DROP_ROW_KEYS[2:16]:
        assert row.model_dump()[key] is None or key == "phase"


@pytest.mark.asyncio
async def test_child_dependency_mismatch_is_visible_but_not_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["launches"]["1"]["manager"] = "0x" + "9" * 40
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    row = result.rows[0]
    assert row.launch_id == 1
    assert row.integrity == "mismatch"
    assert row.collection_address is None
    assert result.integrity_mismatch_ids == (1,)
    assert result.valid_count == 1


@pytest.mark.asyncio
async def test_manager_dependency_mismatch_makes_enumeration_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["manager_fwa"] = "0x" + "9" * 40
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    assert result.available is False
    assert result.integrity == "mismatch"
    assert result.rows == ()
    assert result.issues == ("manager_dependency_mismatch",)


@pytest.mark.asyncio
async def test_manager_runtime_mismatch_stops_before_untrusted_manager_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["manager_runtime_mismatch"] = True
    result, simulator, _transport = await _run(fixture, monkeypatch)
    assert result.available is False
    assert result.integrity == "mismatch"
    assert result.registry_fingerprint is None
    assert result.enumeration_reset is False
    assert result.issues == ("manager_codehash_mismatch",)
    assert [method for method, _ in simulator.rpc_calls] == [
        "eth_blockNumber",
        "eth_getCode",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch_kind", ["codehash", "dependency"])
async def test_manager_mismatch_latches_reset_until_successful_recovery(
    monkeypatch: pytest.MonkeyPatch,
    mismatch_kind: str,
) -> None:
    fixture = _fixture("two_launches")
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        cold = await client.fetch_drops()
        assert cold.enumeration_reset is False

        if mismatch_kind == "codehash":
            fixture["manager_runtime_mismatch"] = True
        else:
            fixture["manager_fwa"] = "0x" + "9" * 40
        mismatch = await client.fetch_drops()
        assert mismatch.available is False
        assert mismatch.enumeration_reset is False
        assert mismatch.registry_fingerprint == (
            None if mismatch_kind == "codehash" else _CHILD_CODEHASH
        )

        fixture.pop(
            "manager_runtime_mismatch"
            if mismatch_kind == "codehash"
            else "manager_fwa"
        )
        fixture["failed_manager_calls"] = ["nextLaunchId()"]
        unavailable = await client.fetch_drops()
        assert unavailable.available is False
        assert unavailable.enumeration_reset is False
        assert unavailable.registry_fingerprint == _CHILD_CODEHASH

        fixture.pop("failed_manager_calls")
        recovered = await client.fetch_drops()
        steady = await client.fetch_drops()

    assert recovered.available is True
    assert recovered.registry_fingerprint == _CHILD_CODEHASH
    assert recovered.enumeration_reset is True
    assert steady.enumeration_reset is False


@pytest.mark.asyncio
async def test_runtime_fingerprint_change_resets_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)
    changed_fingerprint = _REAL_RUNTIME_CODEHASH(_MISMATCH_CHILD_CODE)
    assert changed_fingerprint is not None

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        cold = await client.fetch_drops()
        assert cold.enumeration_reset is False

        fixture["launch_runtime_codehash"] = changed_fingerprint
        for launch in fixture["launches"].values():
            launch["runtime_mismatch"] = True
        fixture["block_number"] += 1
        changed = await client.fetch_drops()
        steady = await client.fetch_drops()

    assert changed.available is True
    assert changed.integrity == "ok"
    assert changed.registry_fingerprint == changed_fingerprint
    assert changed.enumeration_reset is True
    assert steady.enumeration_reset is False


@pytest.mark.asyncio
async def test_hostile_launch_count_keeps_all_calls_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["next_launch_id"] = 2**255

    result, simulator, _transport = await _run(fixture, monkeypatch)

    assert result.available is True
    assert result.integrity == "warning"
    assert result.next_launch_id == 2**255
    assert [row.launch_id for row in result.rows] == [1]
    assert result.issues[-1] == "launch_enumeration_partial"
    launch_getter_ids = [
        decode_uint("0x" + strip0x(calldata)[8:])
        for target, calldata, _tag in simulator.subcalls
        if target == FWAIR_MANAGER
        and calldata.startswith(MANAGER_SELECTORS["launches(uint256)"])
    ]
    assert len(launch_getter_ids) == MAX_LAUNCHES_PER_REFRESH
    assert launch_getter_ids == [
        *range(2**255 - MAX_LAUNCHES_PER_REFRESH + 1, 2**255),
        1,
    ]


@pytest.mark.asyncio
async def test_repeated_hostile_counts_bound_calls_and_failure_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["next_launch_id"] = 2**255
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        for _cycle in range(12):
            subcall_start = len(simulator.subcalls)
            rpc_start = len(simulator.rpc_calls)
            result = await client.fetch_drops()
            cycle_subcalls = simulator.subcalls[subcall_start:]
            cycle_rpcs = simulator.rpc_calls[rpc_start:]
            launch_getters = [
                calldata
                for target, calldata, _tag in cycle_subcalls
                if target == FWAIR_MANAGER
                and calldata.startswith(MANAGER_SELECTORS["launches(uint256)"])
            ]
            assert len(launch_getters) <= MAX_LAUNCHES_PER_REFRESH
            assert len(cycle_rpcs) <= MAX_LAUNCHES_PER_REFRESH + 12
            assert len(result.holes) <= MAX_LAUNCHES_PER_REFRESH
            assert len(client._launch_holes) <= MAX_LAUNCHES_PER_REFRESH
            assert len(client._launch_issues) <= MAX_LAUNCHES_PER_REFRESH
            assert set(client._launch_holes) <= set(client._launch_issues)
            assert sum(
                issue.startswith("launch_")
                and issue != "launch_enumeration_partial"
                for issue in result.issues
            ) <= MAX_LAUNCHES_PER_REFRESH

    assert {row.launch_id for row in result.rows} == {1, 2}


@pytest.mark.asyncio
async def test_failed_new_launch_is_retried_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    clock = FixedClock(fixture["observed_at"])
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=clock,
        )
        await client.fetch_drops()
        launch_17 = deepcopy(fixture["launches"]["2"])
        launch_17.update(
            {
                "address": "0x1000000000000000000000000000000000000011",
                "collection": "0x2000000000000000000000000000000000000011",
                "name": "Seventeenth Drop",
                "failed_calls": ["manager()"],
            }
        )
        fixture["launches"]["17"] = launch_17
        fixture["next_launch_id"] = 18
        fixture["block_number"] += 1
        fixture["block_timestamp"] += 1
        clock.advance(1)
        failed = await client.fetch_drops()
        assert 17 in failed.holes
        assert 17 not in {row.launch_id for row in failed.rows}

        launch_17.pop("failed_calls")
        recovered = None
        for _attempt in range(4):
            fixture["block_number"] += 1
            fixture["block_timestamp"] += 1
            clock.advance(1)
            candidate = await client.fetch_drops()
            if 17 in {row.launch_id for row in candidate.rows}:
                recovered = candidate
                break

    assert recovered is not None
    recovered_by_id = {row.launch_id: row for row in recovered.rows}
    assert 17 not in recovered.holes
    assert all(not issue.startswith("launch_17_") for issue in recovered.issues)
    assert recovered_by_id[17].collection_name == "Seventeenth Drop"
    assert recovered_by_id[17].stale is False


@pytest.mark.asyncio
async def test_cancelled_page_leaves_accumulator_and_cursor_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["next_launch_id"] = 18
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        await client.fetch_drops()
        fixture["manager_runtime_mismatch"] = True
        mismatch = await client.fetch_drops()
        assert mismatch.available is False
        assert mismatch.registry_fingerprint is None
        assert mismatch.enumeration_reset is False
        fixture.pop("manager_runtime_mismatch")

        def accumulator_state() -> tuple[Any, ...]:
            return (
                dict(client._launch_rows),
                dict(client._launch_holes),
                dict(client._launch_issues),
                client._launch_scan_cursor,
                client._known_next_launch_id,
                client._known_launch_runtime_hash,
                client._last_drop_state_block,
                client._enumeration_reset_pending,
            )

        before = accumulator_state()
        expected_page, expected_cursor, _reset = client._launch_page(
            next_launch_id=fixture["next_launch_id"],
            state_block=fixture["block_number"],
            expected_child_hash=_CHILD_CODEHASH,
        )
        original_multicall = client._multicall
        multicall_count = 0

        async def cancel_page(calls: Any, block: str = "latest") -> Any:
            nonlocal multicall_count
            multicall_count += 1
            if multicall_count == 2:
                raise asyncio.CancelledError
            return await original_multicall(calls, block)

        monkeypatch.setattr(client, "_multicall", cancel_page)
        with pytest.raises(asyncio.CancelledError):
            await client.fetch_drops()
        assert accumulator_state() == before

        monkeypatch.setattr(client, "_multicall", original_multicall)
        subcall_start = len(simulator.subcalls)
        resumed = await client.fetch_drops()
        resumed_getters = [
            decode_uint("0x" + strip0x(calldata)[8:])
            for target, calldata, _tag in simulator.subcalls[subcall_start:]
            if target == FWAIR_MANAGER
            and calldata.startswith(MANAGER_SELECTORS["launches(uint256)"])
        ]

    assert resumed_getters == list(expected_page)
    assert client._launch_scan_cursor == expected_cursor
    assert resumed.enumeration_reset is True
    assert client._enumeration_reset_pending is False


@pytest.mark.asyncio
async def test_two_pages_at_same_block_converge_to_complete_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    for launch_id in range(3, 18):
        launch = deepcopy(fixture["launches"]["2"])
        launch.update(
            {
                "address": "0x1" + f"{launch_id:039x}",
                "collection": "0x2" + f"{launch_id:039x}",
                "name": f"Drop {launch_id}",
            }
        )
        fixture["launches"][str(launch_id)] = launch
    fixture["next_launch_id"] = 18
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        first = await client.fetch_drops(block_number=fixture["block_number"])
        second = await client.fetch_drops(block_number=fixture["block_number"])

    assert len(first.rows) == MAX_LAUNCHES_PER_REFRESH
    assert "launch_enumeration_partial" in first.issues
    assert first.integrity == "warning"
    assert second.enumeration_reset is False
    assert second.registry_fingerprint == _CHILD_CODEHASH
    assert len(second.rows) == 17
    assert second.holes == ()
    assert second.integrity == "ok"
    assert "launch_enumeration_partial" not in second.issues
    assert all(row.block_number == fixture["block_number"] for row in second.rows)
    assert all(row.stale is False for row in second.rows)


@pytest.mark.asyncio
async def test_new_launch_page_accumulates_rows_and_marks_old_rows_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    clock = FixedClock(fixture["observed_at"])
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=clock,
        )
        first = await client.fetch_drops()
        assert [row.launch_id for row in first.rows] == [1, 2]

        launch_33 = deepcopy(fixture["launches"]["2"])
        launch_33.update(
            {
                "address": "0x1000000000000000000000000000000000000021",
                "collection": "0x2000000000000000000000000000000000000021",
                "name": "Thirty Third Drop",
            }
        )
        fixture["launches"]["33"] = launch_33
        fixture["next_launch_id"] = 34
        fixture["block_number"] += 1
        fixture["block_timestamp"] += 1
        clock.advance(1)
        call_start = len(simulator.subcalls)

        second = await client.fetch_drops()
        second_calls = simulator.subcalls[call_start:]
        second_getter_ids = [
            decode_uint("0x" + strip0x(calldata)[8:])
            for target, calldata, _tag in second_calls
            if target == FWAIR_MANAGER
            and calldata.startswith(MANAGER_SELECTORS["launches(uint256)"])
        ]

        assert len(second_getter_ids) == MAX_LAUNCHES_PER_REFRESH
        assert 33 in second_getter_ids
        assert second.integrity == "warning"
        assert "launch_enumeration_partial" in second.issues
        assert [row.launch_id for row in second.rows] == [1, 2, 33]
        row_by_id = {row.launch_id: row for row in second.rows}
        assert row_by_id[1].stale is False
        assert row_by_id[2].stale is True
        assert row_by_id[2].observed_at == first.observed_at
        assert row_by_id[33].stale is False
        assert row_by_id[33].collection_name == "Thirty Third Drop"

        fixture["block_number"] += 1
        fixture["block_timestamp"] += 1
        clock.advance(1)
        call_start = len(simulator.subcalls)
        third = await client.fetch_drops()
        third_getters = [
            calldata
            for target, calldata, _tag in simulator.subcalls[call_start:]
            if target == FWAIR_MANAGER
            and calldata.startswith(MANAGER_SELECTORS["launches(uint256)"])
        ]
        assert len(third_getters) <= MAX_LAUNCHES_PER_REFRESH
        assert [row.launch_id for row in third.rows] == [1, 2, 33]
        third_by_id = {row.launch_id: row for row in third.rows}
        assert third_by_id[1].stale is True
        assert third_by_id[2].stale is False
        assert third_by_id[33].stale is True


@pytest.mark.asyncio
async def test_launch_registry_shrink_discards_future_accumulator_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    launch_33 = deepcopy(fixture["launches"]["2"])
    launch_33.update(
        {
            "address": "0x1000000000000000000000000000000000000021",
            "collection": "0x2000000000000000000000000000000000000021",
            "name": "Thirty Third Drop",
        }
    )
    fixture["launches"]["33"] = launch_33
    fixture["next_launch_id"] = 34
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        initial = await client.fetch_drops()
        assert 33 in {row.launch_id for row in initial.rows}
        assert initial.enumeration_reset is False

        fixture["next_launch_id"] = 3
        fixture["launches"].pop("33")
        fixture["block_number"] += 1
        shrunk = await client.fetch_drops()
        steady = await client.fetch_drops()

    assert [row.launch_id for row in shrunk.rows] == [1, 2]
    assert shrunk.enumeration_reset is True
    assert steady.enumeration_reset is False
    assert all(row.stale is False for row in shrunk.rows)
    assert shrunk.holes == ()
    assert shrunk.integrity_mismatch_ids == ()
    assert "launch_enumeration_partial" not in shrunk.issues
    assert all(not issue.startswith("launch_33_") for issue in shrunk.issues)


@pytest.mark.asyncio
async def test_block_rollback_resets_enumeration_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
        )
        cold = await client.fetch_drops()
        assert cold.enumeration_reset is False

        fixture["block_number"] -= 1
        rollback = await client.fetch_drops()
        steady = await client.fetch_drops()

    assert rollback.enumeration_reset is True
    assert rollback.state_block == fixture["block_number"]
    assert steady.enumeration_reset is False


@pytest.mark.asyncio
async def test_transient_child_failure_keeps_last_good_row_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    simulator = SimulatedFWAIR(fixture)
    transport = DenyNetworkTransport(simulator.handle)
    clock = FixedClock(fixture["observed_at"])
    _patch_runtime_hash(monkeypatch)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=clock,
        )
        first = await client.fetch_drops()
        first_by_id = {row.launch_id: row for row in first.rows}

        fixture["launches"]["1"]["failed_calls"] = ["manager()"]
        fixture["block_number"] += 1
        fixture["block_timestamp"] += 1
        clock.advance(1)
        failed = await client.fetch_drops()
        failed_by_id = {row.launch_id: row for row in failed.rows}

        assert [row.launch_id for row in failed.rows] == [1, 2]
        assert failed.holes == (1,)
        assert "launch_1_child_read_failed" in failed.issues
        assert failed.integrity == "warning"
        assert failed_by_id[1].collection_name == "First Drop"
        assert failed_by_id[1].block_number == first_by_id[1].block_number
        assert failed_by_id[1].observed_at == first_by_id[1].observed_at
        assert failed_by_id[1].stale is True
        assert failed_by_id[2].block_number == fixture["block_number"]
        assert failed_by_id[2].stale is False

        fixture["launches"]["1"].pop("failed_calls")
        fixture["block_number"] += 1
        fixture["block_timestamp"] += 1
        clock.advance(1)
        recovered = await client.fetch_drops()

    recovered_by_id = {row.launch_id: row for row in recovered.rows}
    assert recovered.holes == ()
    assert "launch_1_child_read_failed" not in recovered.issues
    assert recovered_by_id[1].block_number == fixture["block_number"]
    assert recovered_by_id[1].observed_at == clock.value
    assert recovered_by_id[1].stale is False


@pytest.mark.asyncio
async def test_optional_metric_failure_stays_none_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["launches"]["1"]["failed_calls"] = ["artistETHCredit()"]
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    row = result.rows[0]
    assert row.integrity == "ok"
    assert row.artist_credit_eth is None
    assert row.total_backing_eth == 27.75


@pytest.mark.asyncio
async def test_missing_block_timestamp_only_makes_support_window_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["block_timestamp"] = None
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    assert result.available is True
    assert result.integrity == "warning"
    assert result.rows[0].support_open is False
    assert result.rows[1].support_open is None
    assert result.issues[0] == "block_timestamp_unavailable"


@pytest.mark.asyncio
async def test_unknown_phase_does_not_claim_the_support_window_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    fixture["launches"]["2"]["phase"] = 7
    result, _simulator, _transport = await _run(fixture, monkeypatch)
    assert result.rows[1].phase == "unknown"
    assert result.rows[1].support_open is None


@pytest.mark.asyncio
async def test_only_vendored_read_selectors_are_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("two_launches")
    _result, simulator, _transport = await _run(fixture, monkeypatch)
    allowed_manager = set(MANAGER_SELECTORS.values())
    allowed_child = set(LAUNCH_SELECTORS.values())
    collections = {
        launch["collection"] for launch in fixture["launches"].values() if launch
    }
    for target, calldata, _tag in simulator.subcalls:
        selector = calldata[:10]
        if target == FWAIR_MANAGER:
            assert selector in allowed_manager
        elif target in collections:
            assert selector == COLLECTION_NAME_SELECTOR
        else:
            assert selector in allowed_child


def test_runtime_hash_rejects_malformed_data_and_hashes_bytecode() -> None:
    assert runtime_codehash("0x6001") == keccak256_hex(bytes.fromhex("6001"))
    assert runtime_codehash("0x1") is None
    assert runtime_codehash("not-hex") is None
    assert runtime_codehash(None) is None


def test_fwair_manager_and_child_events_normalize_to_network_rows() -> None:
    launch = _fixture("two_launches")["launches"]["1"]
    child = launch["address"]
    manager_log = _event_log(
        address=FWAIR_MANAGER,
        event="LaunchRegistered",
        values={
            "launch": child,
            "artist": "0x" + "3" * 40,
            "collection": launch["collection"],
            "launchId": 1,
            "startTokenId": 100,
            "tokenCount": 3,
            "backingPrice": 1_500_000_000_000_000_000,
            "maxSupportPerWallet": 2,
            "supportStart": 1_000,
            "supportDeadline": 2_000,
        },
        block=100,
        index=1,
    )
    manager_rows, failures = normalize_fwair_events(
        FWAIR_MANAGER,
        [manager_log],
        observed_at=1_787_000_200.0,
        from_block=100,
        to_block=102,
        integrity="ok",
    )
    assert failures == 0
    assert len(manager_rows) == 1
    assert manager_rows[0].family == "drop"
    assert manager_rows[0].event_key == "drop_created"
    assert manager_rows[0].eth_amount == 1.5
    assert manager_rows[0].integrity == "ok"

    supported = _event_log(
        address=child,
        event="PositionSupported",
        values={
            "tokenId": 101,
            "supporter": "0x" + "4" * 40,
            "backing": 2_000_000_000_000_000_000,
            "walletSupportCount": 1,
            "totalSupported": 2,
            "refundableBacking": 4_000_000_000_000_000_000,
        },
        block=101,
        index=2,
    )
    claimed = _event_log(
        address=child,
        event="SupporterTokensClaimed",
        values={
            "supporter": "0x" + "4" * 40,
            "recipient": "0x" + "5" * 40,
            "token": FWA_TOKEN,
            "amount": 42_000_000_000_000_000_000,
            "remainingPoolReserve": 8_000_000_000_000_000_000,
        },
        block=102,
        index=3,
    )
    other_reward = _event_log(
        address=child,
        event="SupporterTokensClaimed",
        values={
            "supporter": "0x" + "4" * 40,
            "recipient": "0x" + "5" * 40,
            "token": "0x" + "6" * 40,
            "amount": 99_000_000_000_000_000_000,
            "remainingPoolReserve": 7_000_000_000_000_000_000,
        },
        block=103,
        index=4,
    )
    child_rows, failures = normalize_fwair_events(
        child,
        [supported, claimed, other_reward],
        observed_at=1_787_000_200.0,
        from_block=100,
        to_block=103,
        integrity="ok",
    )
    assert failures == 0
    assert [row.event_key for row in child_rows] == [
        "claimed",
        "claimed",
        "supported",
    ]
    assert child_rows[0].event_label == "Supporter reward claimed"
    assert child_rows[0].fwa_amount is None
    assert child_rows[1].event_label == "Supporter FWA claimed"
    assert child_rows[1].fwa_amount == 42.0
    assert child_rows[2].eth_amount == 2.0
    assert all(row.verified_source for row in child_rows)


def test_fwair_event_mismatch_suppresses_semantics_and_malformed_blocks_page() -> None:
    launch = _fixture("two_launches")["launches"]["1"]
    raw = _event_log(
        address=launch["address"],
        event="PositionSupported",
        values={
            "tokenId": 101,
            "supporter": "0x" + "4" * 40,
            "backing": 2_000_000_000_000_000_000,
            "walletSupportCount": 1,
            "totalSupported": 2,
            "refundableBacking": 4_000_000_000_000_000_000,
        },
        block=101,
        index=2,
    )
    rows, failures = normalize_fwair_events(
        launch["address"],
        [raw],
        observed_at=1_787_000_200.0,
        from_block=100,
        to_block=102,
        integrity="mismatch",
    )
    assert failures == 0
    assert rows[0].event_key == "integrity_mismatch"
    assert rows[0].event_label == "Untrusted contract log"
    assert rows[0].eth_amount is None
    assert rows[0].fwa_amount is None
    assert rows[0].verified_source is False
    assert rows[0].detail == (
        "runtime/dependency integrity mismatch; semantics suppressed"
    )

    malformed = {**raw, "data": "0x" + "z" * 64}
    rows, failures = normalize_fwair_events(
        launch["address"],
        [malformed],
        observed_at=1_787_000_200.0,
        from_block=100,
        to_block=102,
    )
    assert rows == ()
    assert failures == 1

    extra_word = {**raw, "data": str(raw["data"]) + "0" * 64}
    rows, failures = normalize_fwair_events(
        launch["address"],
        [extra_word],
        observed_at=1_787_000_200.0,
        from_block=100,
        to_block=102,
    )
    assert rows == ()
    assert failures == 1


@pytest.mark.parametrize("integrity", ["trusted", "", None])
def test_fwair_event_integrity_is_closed_vocabulary(integrity: Any) -> None:
    with pytest.raises(ValueError, match="integrity"):
        normalize_fwair_events(
            FWAIR_MANAGER,
            [],
            observed_at=1.0,
            from_block=1,
            to_block=1,
            integrity=integrity,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 1.5, True, "123"])
async def test_invalid_explicit_block_is_rejected_before_rpc(value: Any) -> None:
    transport = DenyNetworkTransport()
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
        )
        with pytest.raises(ValueError):
            await client.fetch_drops(block_number=value)
    assert transport.requests == []


@pytest.mark.asyncio
async def test_invalid_clock_is_rejected_before_rpc() -> None:
    transport = DenyNetworkTransport()
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FWAIRDropsClient(
            primary_rpc="https://rpc.test",
            fallback_rpcs=["https://fallback.test"],
            http_client=http_client,
            inter_call_delay=0,
            clock=lambda: True,
        )
        with pytest.raises(ValueError, match="clock"):
            await client.fetch_drops(block_number=1)
    assert transport.requests == []


def test_production_module_does_not_embed_fixture_launch_addresses() -> None:
    source = Path("maxpane_dashboard/data/fwa_drops_client.py").read_text(
        encoding="utf-8"
    ).lower()
    for fixture_name in (
        "two_launches",
        "hole_then_valid",
        "third_launch",
        "hash_mismatch",
    ):
        fixture = deepcopy(_fixture(fixture_name))
        for launch in fixture["launches"].values():
            if launch:
                assert launch["address"].lower() not in source
                assert launch["collection"].lower() not in source
