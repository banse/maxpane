"""Offline contract tests for the MegaRip v1-v3 adapter."""

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

from maxpane_dashboard.data.evm_abi import decode_uint, strip0x
from maxpane_dashboard.data.fwa_client import MULTICALL3
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    FWAEcosystemCache,
    WatermarkKey,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
)
from maxpane_dashboard.data.fwa_logs import TENDERLY_GATEWAY
from maxpane_dashboard.data.fwa_projects.megarip import (
    EVENT_TOPICS_BY_VERSION,
    MEGARIP_MANIFESTS,
    STATE_SELECTORS_BY_VERSION,
    TOKEN_IS_DISTRIBUTOR_SELECTOR,
    MegaRipAdapter,
    MegaRipCampaignState,
    gross_recovery_pct,
    lifecycle_name,
    runtime_codehash,
)
from maxpane_dashboard.data.keccak import keccak256_hex
from tests.fwa_ecosystem_fixtures import (
    DenyNetworkTransport,
    FixedClock,
    load_fwa_ecosystem_fixture,
)

_REAL_RUNTIME_CODEHASH = runtime_codehash
_MANIFEST_BY_VERSION = {manifest.version: manifest for manifest in MEGARIP_MANIFESTS}
_VERSION_BY_ADDRESS = {
    manifest.address: manifest.version for manifest in MEGARIP_MANIFESTS
}
_VALID_CODE_BY_VERSION = {"v1": "0x6001", "v2": "0x6002", "v3": "0x6003"}
_MISMATCH_CODE = "0x60ff"


def _fixture(name: str) -> dict[str, Any]:
    return load_fwa_ecosystem_fixture(f"megarip/{name}.json")


def _uint_word(value: int | bool) -> str:
    return "0x" + f"{int(value):064x}"


def _address_word(value: str) -> str:
    return "0x" + strip0x(value).lower().rjust(64, "0")


def _decode_aggregate3_calldata(data: str) -> list[tuple[str, bool, str]]:
    raw = strip0x(data)
    assert raw[:8] == "82ad56cb"
    body = raw[8:]
    array_offset = int(body[:64], 16) * 2
    count = int(body[array_offset : array_offset + 64], 16)
    base = array_offset + 64
    calls: list[tuple[str, bool, str]] = []
    for index in range(count):
        tuple_offset = int(
            body[base + index * 64 : base + (index + 1) * 64], 16
        ) * 2
        start = base + tuple_offset
        target = "0x" + body[start + 24 : start + 64]
        allow_failure = int(body[start + 64 : start + 128], 16) != 0
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


class SimulatedMegaRipState:
    """Semantic Ethereum state node behind an offline HTTP transport."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture
        self.rpc_calls: list[tuple[str, list[Any]]] = []
        self.subcalls: list[tuple[str, str, str]] = []

    def _campaign_read(
        self, version: str, name: str
    ) -> tuple[bool, str]:
        if name in self.fixture.get("failed_reads", {}).get(version, []):
            return False, "0x"
        manifest = _MANIFEST_BY_VERSION[version]
        dependencies = dict(manifest.dependencies)
        if name in dependencies:
            override = self.fixture.get("dependency_overrides", {}).get(
                version, {}
            ).get(name)
            return True, _address_word(override or dependencies[name])
        values = self.fixture["versions"][version]
        if name not in values:
            return False, "0x"
        return True, _uint_word(values[name])

    def _subcall(self, target: str, calldata: str) -> tuple[bool, str]:
        version = _VERSION_BY_ADDRESS.get(target)
        if version is not None:
            by_selector = {
                selector: name
                for name, selector in STATE_SELECTORS_BY_VERSION[version].items()
            }
            name = by_selector.get(calldata[:10])
            return (False, "0x") if name is None else self._campaign_read(version, name)

        if calldata[:10] == TOKEN_IS_DISTRIBUTOR_SELECTOR:
            campaign_address = "0x" + strip0x(calldata)[8:][-40:]
            campaign_version = _VERSION_BY_ADDRESS.get(campaign_address)
            if campaign_version is None:
                return False, "0x"
            if "isDistributor" in self.fixture.get("failed_reads", {}).get(
                campaign_version, []
            ):
                return False, "0x"
            return True, _uint_word(
                self.fixture["versions"][campaign_version]["isDistributor"]
            )
        return False, "0x"

    def handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload["method"]
        params = payload["params"]
        self.rpc_calls.append((method, params))
        if method == "eth_blockNumber":
            result: Any = hex(self.fixture["block_number"])
        elif method == "eth_getCode":
            address = params[0].lower()
            version = _VERSION_BY_ADDRESS[address]
            if version in self.fixture.get("code_unavailable_versions", []):
                result = "0x"
            elif version in self.fixture.get("codehash_mismatch_versions", []):
                result = _MISMATCH_CODE
            else:
                result = _VALID_CODE_BY_VERSION[version]
        elif method == "eth_call":
            assert params[0]["to"].lower() == MULTICALL3
            block_tag = params[1]
            calls = _decode_aggregate3_calldata(params[0]["data"])
            assert all(allow_failure for _target, allow_failure, _data in calls)
            for target, _allow, calldata in calls:
                self.subcalls.append((target, calldata, block_tag))
            result = _encode_aggregate3_result(
                [self._subcall(target, calldata) for target, _, calldata in calls]
            )
        elif method == "eth_getBlockByNumber":
            result = (
                {}
                if self.fixture.get("block_hash_unavailable")
                else {"hash": self.fixture["block_hash"]}
            )
        else:  # pragma: no cover - unexpected network behaviour must be loud
            raise AssertionError(f"unexpected state RPC method: {method}")
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )


class SimulatedMegaRipLogs:
    """Address-filtered archive log node; never serves unrelated versions."""

    def __init__(self, logs: dict[str, list[Any]]) -> None:
        self.logs = logs
        self.requests: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["method"] == "eth_getLogs"
        params = payload["params"][0]
        self.requests.append(params)
        version = _VERSION_BY_ADDRESS[params["address"].lower()]
        assert params["topics"] == [list(EVENT_TOPICS_BY_VERSION[version].values())]
        result = deepcopy(self.logs.get(version, []))
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )


@asynccontextmanager
async def _adapter(
    fixture: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    logs: dict[str, list[Any]] | None = None,
) -> AsyncIterator[tuple[MegaRipAdapter, SimulatedMegaRipState, SimulatedMegaRipLogs]]:
    state_node = SimulatedMegaRipState(fixture)
    log_node = SimulatedMegaRipLogs(logs or {"v1": [], "v2": [], "v3": []})

    def fixture_codehash(raw: Any) -> str | None:
        for version, code in _VALID_CODE_BY_VERSION.items():
            if raw == code:
                return _MANIFEST_BY_VERSION[version].runtime_codehash
        return _REAL_RUNTIME_CODEHASH(raw)

    monkeypatch.setattr(
        "maxpane_dashboard.data.fwa_projects.megarip.runtime_codehash",
        fixture_codehash,
    )
    state_transport = DenyNetworkTransport(state_node.handle)
    log_transport = DenyNetworkTransport(log_node.handle)
    async with (
        httpx.AsyncClient(transport=state_transport) as state_http,
        httpx.AsyncClient(transport=log_transport) as log_http,
    ):
        adapter = MegaRipAdapter(
            primary_rpc="https://state.test",
            fallback_rpcs=["https://state-fallback.test"],
            http_client=state_http,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=FixedClock(fixture["observed_at"]),
            log_endpoints=[TENDERLY_GATEWAY],
            log_http_client=log_http,
            log_min_call_interval=0,
        )
        try:
            yield adapter, state_node, log_node
        finally:
            await adapter.close()


def test_selected_surface_comes_only_from_committed_manifests_and_abis() -> None:
    assert tuple(STATE_SELECTORS_BY_VERSION) == ("v1", "v2", "v3")
    assert tuple(STATE_SELECTORS_BY_VERSION["v1"])[0:4] == (
        "state",
        "totalDeposited",
        "depositorCount",
        "pullsDone",
    )
    assert "fwaReceived" not in STATE_SELECTORS_BY_VERSION["v1"]
    assert "fwaReceived" in STATE_SELECTORS_BY_VERSION["v2"]
    assert "fwaReceived" in STATE_SELECTORS_BY_VERSION["v3"]
    assert "depositorAt" not in STATE_SELECTORS_BY_VERSION["v3"]
    assert "claimable" not in STATE_SELECTORS_BY_VERSION["v3"]
    assert EVENT_TOPICS_BY_VERSION["v3"]["Finalized"] == keccak256_hex(
        b"Finalized(uint256)"
    )
    assert _MANIFEST_BY_VERSION["v3"].source_status == "unverified"


def test_strict_campaign_boundary_rejects_float_wei_and_is_frozen() -> None:
    base = dict(
        version="v3",
        address=_MANIFEST_BY_VERSION["v3"].address,
        is_current=True,
        source_verified=False,
        observed_at=1.0,
        block_number=1,
        semantic_available=True,
        integrity="ok",
        actual_codehash=_MANIFEST_BY_VERSION["v3"].runtime_codehash,
        dependency_reads=(),
    )
    with pytest.raises(ValidationError):
        MegaRipCampaignState(**base, accounted_eth_wei=1.5)
    campaign = MegaRipCampaignState(**base, accounted_eth_wei=0)
    with pytest.raises(ValidationError):
        campaign.accounted_eth_wei = 1
    with pytest.raises(ValidationError):
        MegaRipCampaignState(**base, invented=1)


@pytest.mark.asyncio
async def test_three_generations_reconcile_at_one_block_and_emit_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    async with _adapter(fixture, monkeypatch) as (adapter, node, _logs):
        result = await adapter.fetch_state(block_number=fixture["block_number"])

    assert result.available is True
    assert result.integrity == "ok"
    assert result.state_block == fixture["block_number"]
    assert tuple(campaign.version for campaign in result.campaigns) == (
        "v1",
        "v2",
        "v3",
    )
    # v1 is finalized and fully discharged; v2 remains liability-bearing.
    assert tuple(row.version for row in result.rows) == ("v3", "v2")
    assert all(tuple(row.model_dump()) == PROJECT_ROW_KEYS for row in result.rows)

    current = result.rows[0]
    assert current.is_current is True
    assert current.is_legacy_liability is False
    assert current.lifecycle == "finalized"
    assert current.primary_label == "GROSS RECOVERY"
    assert current.primary_value == pytest.approx(67.18372607814908)
    assert current.primary_unit == "recovery_pct"
    assert current.eth_label == "ACCOUNTED ETH"
    assert current.eth_value == pytest.approx(0.2815000697863766)
    assert current.fwa_label == "OUTSTANDING FWA"
    assert current.fwa_value == 0.0
    assert current.source_badge == "CHAIN-READ"
    assert current.verified_source is False
    assert "source unverified" in current.detail
    assert "distributor disabled" in current.detail
    assert "return" not in json.dumps(current.model_dump()).lower()

    legacy = result.rows[1]
    assert legacy.version == "v2"
    assert legacy.is_legacy_liability is True
    assert legacy.eth_value == 0.01
    assert legacy.fwa_value == 10.0
    assert legacy.source_badge == "VERIFIED"

    state_v3 = result.campaigns[2]
    assert state_v3.depositor_count == 42
    assert state_v3.pulls_done == 126
    assert state_v3.eth_claims_outstanding_wei == 281500069786376591
    assert state_v3.accounted_eth_wei == 281500069786376591
    assert state_v3.fwa_distributor is False
    assert state_v3.fwa_outstanding_wei == 0

    tag = hex(fixture["block_number"])
    assert node.subcalls
    assert all(subcall[2] == tag for subcall in node.subcalls)
    code_calls = [params for method, params in node.rpc_calls if method == "eth_getCode"]
    assert len(code_calls) == 3
    assert all(params[1] == tag for params in code_calls)


@pytest.mark.asyncio
async def test_three_unclaimed_depositors_use_aggregate_claim_accounting_not_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    logs = _fixture("events")
    async with _adapter(fixture, monkeypatch, logs=logs) as (adapter, _state, _log):
        state = await adapter.fetch_state(block_number=fixture["block_number"])
        history = await adapter.fetch_events(
            "v3",
            from_block=_MANIFEST_BY_VERSION["v3"].deployment_block + 1,
            to_block=fixture["block_number"],
            history_complete=False,
        )

    v3 = state.campaigns[2]
    assert v3.depositor_count == 42
    assert v3.eth_claims_outstanding_wei == (
        v3.pot_wei - v3.total_paid_wei
    )
    # The partial page contains only one claim log.  Current liability is unchanged.
    assert history.history_complete is False
    assert sum(event.event_key == "claimed" for event in history.events) == 1
    assert v3.eth_claims_outstanding_wei == 281500069786376591
    assert "depositorAt" not in STATE_SELECTORS_BY_VERSION["v3"]
    assert "claimable" not in STATE_SELECTORS_BY_VERSION["v3"]


@pytest.mark.asyncio
async def test_zero_deposits_never_fabricate_a_recovery_percentage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    v3 = fixture["versions"]["v3"]
    v3.update(
        {
            "totalDeposited": 0,
            "pot": 0,
            "totalPaid": 0,
            "potRemaining": 0,
            "accountedEth": 0,
            "acquisitionSpend": 0,
        }
    )
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _logs):
        result = await adapter.fetch_state(block_number=fixture["block_number"])

    current = result.rows[0]
    assert current.primary_label == "GROSS RECOVERY"
    assert current.primary_value is None
    assert gross_recovery_pct(result.campaigns[2]) is None


@pytest.mark.asyncio
async def test_funding_ledger_uses_deposits_before_pull_budget_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    v3 = fixture["versions"]["v3"]
    v3.update(
        {
            "state": 1,
            "pot": 0,
            "totalPaid": 0,
            "potRemaining": 0,
            "accountedEth": v3["totalDeposited"],
            "acquisitionSpend": 0,
            "pullBudget": 0,
        }
    )
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _logs):
        result = await adapter.fetch_state(block_number=fixture["block_number"])

    current = result.campaigns[2]
    assert current.integrity == "ok"
    assert lifecycle_name(current.lifecycle_index) == "funding"
    assert result.rows[0].primary_value is None


@pytest.mark.asyncio
async def test_failed_lifecycle_read_during_funding_skips_ambiguous_ledger_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    v3 = fixture["versions"]["v3"]
    v3.update(
        {
            "state": 1,
            "pot": 0,
            "totalPaid": 0,
            "potRemaining": 0,
            "accountedEth": v3["totalDeposited"],
            "acquisitionSpend": 0,
            "pullBudget": 0,
        }
    )
    fixture["failed_reads"] = {"v3": ["state"]}
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _logs):
        result = await adapter.fetch_state(block_number=fixture["block_number"])

    current = result.campaigns[2]
    assert current.lifecycle_index is None
    assert current.integrity == "warning"
    assert current.semantic_available is True
    assert current.accounted_eth_wei == v3["totalDeposited"]
    assert "state_unavailable" in current.issues
    assert "accounted_eth_ledger_mismatch" not in current.issues
    assert result.rows[0].source_badge == "DEGRADED"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["codehash", "dependency", "accounting"])
async def test_current_v3_integrity_failures_suppress_all_semantics(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    if failure == "codehash":
        fixture["codehash_mismatch_versions"] = ["v3"]
    elif failure == "dependency":
        fixture["dependency_overrides"] = {
            "v3": {"FWA": "0x0000000000000000000000000000000000000001"}
        }
    else:
        fixture["versions"]["v3"]["accountedEth"] += 1

    async with _adapter(fixture, monkeypatch) as (adapter, _state, _logs):
        result = await adapter.fetch_state(block_number=fixture["block_number"])

    current_state = result.campaigns[2]
    current_row = result.rows[0]
    assert current_state.integrity == "mismatch"
    assert current_state.semantic_available is False
    assert current_state.total_deposited_wei is None
    assert current_state.accounted_eth_wei is None
    assert current_state.fwa_outstanding_wei is None
    assert current_row.version == "v3"
    assert current_row.source_badge == "INTEGRITY"
    assert current_row.primary_value is None
    assert current_row.eth_value is None
    assert current_row.fwa_value is None
    assert current_row.verified_source is False
    assert "semantics suppressed" in current_row.detail


@pytest.mark.asyncio
async def test_failed_subread_is_none_not_zero_and_marks_row_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    fixture["failed_reads"] = {"v3": ["pot"]}
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _logs):
        result = await adapter.fetch_state(block_number=fixture["block_number"])

    campaign = result.campaigns[2]
    row = result.rows[0]
    assert campaign.pot_wei is None
    assert campaign.eth_claims_outstanding_wei is None
    assert campaign.integrity == "warning"
    assert row.primary_value is None
    assert row.source_badge == "DEGRADED"


@pytest.mark.asyncio
async def test_events_are_versioned_deduped_newest_first_and_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    logs = _fixture("events")
    v3_manifest = _MANIFEST_BY_VERSION["v3"]
    async with _adapter(fixture, monkeypatch, logs=logs) as (adapter, _state, log_node):
        result = await adapter.fetch_events(
            "v3",
            from_block=v3_manifest.deployment_block,
            to_block=fixture["block_number"],
        )

    assert result.available is True
    assert result.page_complete is True
    assert result.history_complete is True
    assert result.last_complete_block == fixture["block_number"]
    assert result.last_complete_block_hash == fixture["block_hash"]
    assert tuple(event.event_key for event in result.events) == (
        "claimed",
        "finalized",
        "funded",
    )
    assert len(result.events) == 3  # duplicate claim log collapsed by event_id
    assert all(
        tuple(event.model_dump()) == NETWORK_EVENT_ROW_KEYS
        for event in result.events
    )
    newest = result.events[0]
    assert newest.event_id == (
        "1:0x58a1d8daf6d68eec8b350684e8fecc4379d13d7d:"
        "0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc:4"
    )
    assert newest.eth_amount == pytest.approx(0.2815000697863766)
    assert newest.fwa_amount is None
    assert newest.verified_source is False
    assert newest.integrity == "unknown"
    assert newest.source_kind == "chain_log"
    assert newest.version == "v3"
    assert log_node.requests[0]["address"] == v3_manifest.address


@pytest.mark.asyncio
async def test_v2_fwa_event_uses_token_amount_and_verified_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    logs = _fixture("events")
    async with _adapter(fixture, monkeypatch, logs=logs) as (adapter, _state, _log):
        result = await adapter.fetch_events(
            "v2",
            from_block=_MANIFEST_BY_VERSION["v2"].deployment_block,
            to_block=fixture["block_number"],
            integrity="ok",
        )

    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_key == "fwa_claimed"
    assert event.eth_amount is None
    assert event.fwa_amount == 10.0
    assert event.verified_source is True
    assert event.integrity == "ok"


@pytest.mark.asyncio
async def test_integrity_mismatch_suppresses_megarip_event_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    logs = _fixture("events")
    manifest = _MANIFEST_BY_VERSION["v2"]
    async with _adapter(fixture, monkeypatch, logs=logs) as (adapter, _state, _log):
        result = await adapter.fetch_events(
            "v2",
            from_block=manifest.deployment_block,
            to_block=fixture["block_number"],
            integrity="mismatch",
        )

    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_key == "integrity_mismatch"
    assert event.event_label == "Untrusted contract log"
    assert event.eth_amount is None
    assert event.fwa_amount is None
    assert event.detail == (
        "runtime/dependency integrity mismatch; semantics suppressed"
    )
    assert event.verified_source is False
    assert event.integrity == "mismatch"


@pytest.mark.asyncio
async def test_malformed_log_page_cannot_advance_cache_watermark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture("finalized")
    logs = _fixture("events")
    logs["v3"].append({"removed": True})
    manifest = _MANIFEST_BY_VERSION["v3"]
    async with _adapter(fixture, monkeypatch, logs=logs) as (adapter, _state, _log):
        result = await adapter.fetch_events(
            "v3",
            from_block=manifest.deployment_block,
            to_block=fixture["block_number"],
        )

    assert result.available is True
    assert result.page_complete is False
    assert result.last_complete_block is None
    assert result.last_complete_block_hash is None
    assert result.history_complete is False
    assert result.events  # valid rows remain usable, only the cursor is held back

    cache = FWAEcosystemCache(
        path=str(tmp_path / "cache.json"),
        clock=FixedClock(fixture["observed_at"]),
    )
    key = WatermarkKey("megarip", "v3", "activity")
    assert cache.set_watermark(
        key,
        block_number=result.to_block,
        block_hash=fixture["block_hash"],
        overlap=12,
        page_complete=result.page_complete,
    ) is None
    assert cache.get_watermark(key) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "violation",
    ("non_mapping", "spoofed_address", "below_range", "above_range"),
)
async def test_log_provenance_or_bounds_violation_holds_watermark(
    violation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    logs: dict[str, list[Any]] = _fixture("events")
    manifest = _MANIFEST_BY_VERSION["v3"]
    if violation == "non_mapping":
        logs["v3"].append("not a log object")
    elif violation == "spoofed_address":
        logs["v3"][0]["address"] = _MANIFEST_BY_VERSION["v2"].address
    elif violation == "below_range":
        logs["v3"][0]["blockNumber"] = hex(manifest.deployment_block - 1)
    else:
        logs["v3"][0]["blockNumber"] = hex(fixture["block_number"] + 1)

    async with _adapter(fixture, monkeypatch, logs=logs) as (adapter, _state, _log):
        result = await adapter.fetch_events(
            "v3",
            from_block=manifest.deployment_block,
            to_block=fixture["block_number"],
        )

    assert result.available is True
    assert result.page_complete is False
    assert result.last_complete_block is None
    assert result.last_complete_block_hash is None
    assert result.history_complete is False
    assert result.issues == ("1_event_decode_failed",)


@pytest.mark.asyncio
async def test_complete_page_provides_exact_cache_watermark_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture("finalized")
    manifest = _MANIFEST_BY_VERSION["v3"]
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _log):
        result = await adapter.fetch_events(
            "v3",
            from_block=manifest.deployment_block,
            to_block=fixture["block_number"],
        )

    assert result.page_complete
    assert result.last_complete_block is not None
    assert result.last_complete_block_hash is not None
    cache = FWAEcosystemCache(
        path=str(tmp_path / "cache.json"),
        clock=FixedClock(fixture["observed_at"]),
    )
    key = WatermarkKey("megarip", "v3", "activity")
    watermark = cache.set_watermark(
        key,
        block_number=result.last_complete_block,
        block_hash=result.last_complete_block_hash,
        overlap=12,
        page_complete=result.page_complete,
    )
    assert watermark is not None
    assert watermark.block_number == fixture["block_number"]
    assert watermark.block_hash == fixture["block_hash"]


@pytest.mark.asyncio
async def test_missing_watermark_hash_holds_page_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    fixture["block_hash_unavailable"] = True
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _log):
        result = await adapter.fetch_events(
            "v3",
            from_block=_MANIFEST_BY_VERSION["v3"].deployment_block,
            to_block=fixture["block_number"],
        )
    assert result.available is True
    assert result.page_complete is False
    assert result.last_complete_block is None
    assert result.last_complete_block_hash is None
    assert result.issues == ("watermark_block_hash_unavailable",)


@pytest.mark.asyncio
async def test_adapter_rejects_bad_bounds_versions_and_wallclock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture("finalized")
    async with _adapter(fixture, monkeypatch) as (adapter, _state, _logs):
        with pytest.raises(ValueError, match="block_number"):
            await adapter.fetch_state(block_number=-1)
        with pytest.raises(ValueError, match="unknown MegaRip version"):
            await adapter.fetch_events("v4", from_block=1, to_block=2)
        with pytest.raises(ValueError, match="from_block"):
            await adapter.fetch_events("v3", from_block=True, to_block=2)
        with pytest.raises(ValueError, match="from_block"):
            await adapter.fetch_events(  # type: ignore[arg-type]
                "v3", from_block=None, to_block=2
            )
        with pytest.raises(ValueError, match="to_block"):
            await adapter.fetch_events(  # type: ignore[arg-type]
                "v3", from_block=1, to_block=None
            )
        with pytest.raises(ValueError, match="to_block"):
            await adapter.fetch_events("v3", from_block=1, to_block=True)
        with pytest.raises(ValueError, match="to_block"):
            await adapter.fetch_events("v3", from_block=1, to_block=-1)
        with pytest.raises(ValueError, match="history_complete"):
            await adapter.fetch_events(
                "v3", from_block=1, to_block=2, history_complete=1
            )
        with pytest.raises(ValueError, match="integrity"):
            await adapter.fetch_events(
                "v3",
                from_block=1,
                to_block=2,
                integrity="trusted",  # type: ignore[arg-type]
            )

    transport = DenyNetworkTransport()
    async with httpx.AsyncClient(transport=transport) as http_client:
        bad_clock = MegaRipAdapter(
            primary_rpc="https://state.test",
            fallback_rpcs=[],
            http_client=http_client,
            inter_call_delay=0,
            backoff_seconds=(),
            clock=lambda: float("nan"),
        )
        with pytest.raises(ValueError, match="finite epoch"):
            await bad_clock.fetch_state(block_number=fixture["block_number"])
        await bad_clock.close()
    assert transport.requests == []
