"""Offline contract tests for the FWA NETWORK presentation boundary."""

from __future__ import annotations

import inspect
import json

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from maxpane_dashboard.data.fwa_ecosystem_models import (
    DROP_PHASES,
    DROP_ROW_KEYS,
    FLOW_KEYS,
    FLOW_ROW_KEYS,
    FWA_NETWORK_DATA_KEYS,
    FWA_NETWORK_ROW_KEYS,
    FWA_NETWORK_WIDGET_SIGNATURES,
    FWA_UMBRELLA_DATA_KEYS,
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_FAMILIES,
    PROJECT_ROW_KEYS,
    ROW_META_KEYS,
    SOURCE_BADGES,
    DropRow,
    FlowRow,
    NetworkEventRow,
    NetworkStateRead,
    ProjectRow,
    SourceMeta,
    blank_network_payload,
)
from maxpane_dashboard.data.fwa_models import (
    FWA_DATA_KEYS,
    FWA_ROW_KEYS,
    FWA_WIDGET_SIGNATURES,
)
from tests import fwa_ecosystem_fixtures
from tests.fwa_ecosystem_fixtures import DenyNetworkTransport, FixedClock


EXPECTED_NETWORK_KEYS = (
    "network_ready",
    "network_state_block",
    "network_chain_head",
    "network_state_stale",
    "network_active_listings",
    "network_pull_quote_eth",
    "network_pending_count",
    "network_unsettled_count",
    "network_crown_pot_eth",
    "network_token_supply_fwa",
    "network_burned_since_genesis_fwa",
    "network_burned_since_genesis_pct",
    "network_last_buyback_age_s",
    "network_drop_count",
    "network_project_family_count",
    "network_project_healthy_count",
    "network_project_degraded_count",
    "network_project_unverified_count",
    "network_flow_rows",
    "network_flow_available",
    "network_flow_history_complete",
    "network_flow_as_of_block",
    "network_flow_as_of_ts",
    "network_flow_stale",
    "network_drop_rows",
    "network_drops_available",
    "network_drops_as_of_block",
    "network_drops_stale",
    "network_project_rows",
    "network_projects_available",
    "network_projects_as_of_block",
    "network_projects_stale",
    "network_events",
    "network_feed_available",
    "network_feed_unavailable_reason",
    "network_feed_as_of_ts",
    "network_degraded_sources",
    "network_integrity_warning_count",
    "network_last_updated_seconds_ago",
    "network_error_count",
)

EXPECTED_META_KEYS = (
    "source_kind",
    "measurement",
    "block_number",
    "observed_at",
    "stale",
    "verified_source",
    "integrity",
)

EXPECTED_FLOW_KEYS = (
    "key",
    "label",
    "value",
    "unit",
    "configured_bps",
    "state",
    "direction",
    "detail",
    "tx_hash",
) + EXPECTED_META_KEYS

EXPECTED_DROP_KEYS = (
    "launch_id",
    "launch_address",
    "collection_address",
    "collection_name",
    "phase",
    "support_open",
    "token_count",
    "supported_count",
    "supporter_count",
    "launched_count",
    "terminal_count",
    "backing_eth",
    "total_backing_eth",
    "artist_credit_eth",
    "supporter_principal_eth",
    "supporter_reserve_fwa",
) + EXPECTED_META_KEYS

EXPECTED_PROJECT_KEYS = (
    "family",
    "surface",
    "version",
    "address",
    "is_current",
    "is_legacy_liability",
    "lifecycle",
    "primary_label",
    "primary_value",
    "primary_unit",
    "eth_label",
    "eth_value",
    "fwa_label",
    "fwa_value",
    "detail",
    "source_badge",
) + EXPECTED_META_KEYS

EXPECTED_EVENT_KEYS = (
    "event_id",
    "ts",
    "tx_hash",
    "log_index",
    "origin",
    "family",
    "version",
    "event_key",
    "event_label",
    "eth_amount",
    "fwa_amount",
    "detail",
) + EXPECTED_META_KEYS

EXPECTED_WIDGET_SIGNATURES = {
    "FWANetworkHero": (
        "network_ready",
        "network_state_block",
        "network_state_stale",
        "network_active_listings",
        "network_pull_quote_eth",
        "network_pending_count",
        "network_unsettled_count",
        "network_crown_pot_eth",
        "network_token_supply_fwa",
        "network_burned_since_genesis_fwa",
        "network_burned_since_genesis_pct",
        "network_last_buyback_age_s",
        "network_drop_count",
        "network_project_family_count",
        "network_project_healthy_count",
        "network_project_degraded_count",
        "network_project_unverified_count",
    ),
    "FWAFlowRail": (
        "network_flow_rows",
        "network_flow_available",
        "network_flow_history_complete",
        "network_flow_as_of_block",
        "network_flow_as_of_ts",
        "network_flow_stale",
    ),
    "FWAIRDropBoard": (
        "network_drop_rows",
        "network_drops_available",
        "network_drops_as_of_block",
        "network_drops_stale",
    ),
    "FWAEcosystemRegistry": (
        "network_project_rows",
        "network_projects_available",
        "network_projects_as_of_block",
        "network_projects_stale",
    ),
    "FWANetworkActivity": (
        "network_events",
        "network_feed_available",
        "network_feed_unavailable_reason",
        "network_feed_as_of_ts",
    ),
}


def _meta() -> dict[str, object]:
    return {
        "source_kind": "chain_log",
        "measurement": "measured",
        "block_number": 25_849_738,
        "observed_at": 1_787_872_000.0,
        "stale": False,
        "verified_source": True,
        "integrity": "ok",
    }


def _models() -> tuple[BaseModel, ...]:
    state = NetworkStateRead(
        observed_at=1_787_872_000.0,
        state_block=25_849_738,
        chain_head=25_849_740,
        active_listings=6_185,
        pull_quote_wei=72_300_000_000_000_000,
        pending_count=3,
        unsettled_count=3,
        crown_pot_wei=3_622_000_000_000_000_000,
        token_supply_wei=986_380_736_772_700_000_000_000_000,
    )
    meta = SourceMeta(**_meta())
    flow = FlowRow(
        key="buyback_gross_eth",
        label="BUYBACK GROSS",
        value=0.005722834282592458,
        unit="eth",
        configured_bps=None,
        state="live",
        direction="in",
        detail="swap plus caller reward",
        tx_hash="0x" + "ab" * 32,
        **_meta(),
    )
    drop = DropRow(
        launch_id=2,
        launch_address="0x" + "12" * 20,
        collection_address="0x" + "34" * 20,
        collection_name="FWAIR #2",
        phase="complete",
        support_open=False,
        token_count=1_000,
        supported_count=1_000,
        supporter_count=448,
        launched_count=1_000,
        terminal_count=448,
        backing_eth=31.25,
        total_backing_eth=31.25,
        artist_credit_eth=0.5,
        supporter_principal_eth=30.0,
        supporter_reserve_fwa=12_500.0,
        **_meta(),
    )
    project = ProjectRow(
        family="pullpool",
        surface="pool",
        version="v2",
        address="0x03c45c9c594b19ca5fde54f38c7e6b6a5f2329d7",
        is_current=True,
        is_legacy_liability=False,
        lifecycle="refunding",
        primary_label="ROUNDS",
        primary_value=367,
        primary_unit="rounds",
        eth_label="REFUNDS",
        eth_value=1.25,
        fwa_label="REWARDS",
        fwa_value=50_000.0,
        detail="current production pool",
        source_badge="VERIFIED",
        **_meta(),
    )
    event = NetworkEventRow(
        event_id="1:0x" + "12" * 20 + ":0x" + "ab" * 32 + ":7",
        ts=1_787_872_000,
        tx_hash="0x" + "ab" * 32,
        log_index=7,
        origin="FWA",
        family="fwa",
        version=None,
        event_key="buyback",
        event_label="BUYBACK",
        eth_amount=0.005722834282592458,
        fwa_amount=767.71,
        detail="fee-funded purchase",
        **_meta(),
    )
    return state, meta, flow, drop, project, event


def test_network_data_keys_match_the_approved_contract_exactly():
    assert FWA_NETWORK_DATA_KEYS == EXPECTED_NETWORK_KEYS
    assert len(FWA_NETWORK_DATA_KEYS) == 40
    assert all(key.startswith("network_") for key in FWA_NETWORK_DATA_KEYS)


def test_umbrella_is_the_ordered_disjoint_union_without_changing_pulls():
    assert set(FWA_DATA_KEYS).isdisjoint(FWA_NETWORK_DATA_KEYS)
    assert FWA_UMBRELLA_DATA_KEYS == FWA_DATA_KEYS + FWA_NETWORK_DATA_KEYS
    assert len(FWA_UMBRELLA_DATA_KEYS) == len(set(FWA_UMBRELLA_DATA_KEYS))


def test_existing_pulls_contracts_are_not_aliased_or_extended():
    assert FWA_NETWORK_ROW_KEYS is not FWA_ROW_KEYS
    assert FWA_NETWORK_WIDGET_SIGNATURES is not FWA_WIDGET_SIGNATURES
    assert set(FWA_NETWORK_ROW_KEYS).isdisjoint(FWA_ROW_KEYS)
    assert set(FWA_NETWORK_WIDGET_SIGNATURES).isdisjoint(FWA_WIDGET_SIGNATURES)


def test_network_widget_signatures_match_the_approved_contract_exactly():
    assert FWA_NETWORK_WIDGET_SIGNATURES == EXPECTED_WIDGET_SIGNATURES
    for widget, kwargs in FWA_NETWORK_WIDGET_SIGNATURES.items():
        assert len(kwargs) == len(set(kwargs)), widget
        assert set(kwargs) <= set(FWA_NETWORK_DATA_KEYS), widget


def test_row_schemas_match_the_approved_contract_exactly():
    assert ROW_META_KEYS == EXPECTED_META_KEYS
    assert FLOW_ROW_KEYS == EXPECTED_FLOW_KEYS
    assert DROP_ROW_KEYS == EXPECTED_DROP_KEYS
    assert PROJECT_ROW_KEYS == EXPECTED_PROJECT_KEYS
    assert NETWORK_EVENT_ROW_KEYS == EXPECTED_EVENT_KEYS
    assert FWA_NETWORK_ROW_KEYS == {
        "network_flow_rows": EXPECTED_FLOW_KEYS,
        "network_drop_rows": EXPECTED_DROP_KEYS,
        "network_project_rows": EXPECTED_PROJECT_KEYS,
        "network_events": EXPECTED_EVENT_KEYS,
    }
    assert set(FWA_NETWORK_ROW_KEYS) <= set(FWA_NETWORK_DATA_KEYS)


@pytest.mark.parametrize(
    ("model", "keys"),
    (
        (SourceMeta, EXPECTED_META_KEYS),
        (FlowRow, EXPECTED_FLOW_KEYS),
        (DropRow, EXPECTED_DROP_KEYS),
        (ProjectRow, EXPECTED_PROJECT_KEYS),
        (NetworkEventRow, EXPECTED_EVENT_KEYS),
    ),
)
def test_model_fields_are_in_the_same_order_as_their_row_schema(model, keys):
    assert tuple(model.model_fields) == keys


def test_presentation_model_dumps_have_exact_ordered_row_shapes():
    rows = _models()[2:]
    expected = (
        FLOW_ROW_KEYS,
        DROP_ROW_KEYS,
        PROJECT_ROW_KEYS,
        NETWORK_EVENT_ROW_KEYS,
    )
    assert tuple(tuple(row.model_dump()) for row in rows) == expected


@pytest.mark.parametrize("model", _models())
def test_models_are_frozen(model):
    first_field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError):
        setattr(model, first_field, None)


@pytest.mark.parametrize("model", _models())
def test_models_forbid_extra_fields(model):
    with pytest.raises(ValidationError):
        type(model)(**model.model_dump(), surprise=1)


@pytest.mark.parametrize(
    "field",
    ("pull_quote_wei", "crown_pot_wei", "token_supply_wei"),
)
def test_network_state_rejects_floats_in_wei_fields(field):
    data = _models()[0].model_dump()
    data[field] = 1.0
    with pytest.raises(ValidationError):
        NetworkStateRead(**data)


def test_network_state_distinguishes_unavailable_from_measured_zero():
    data = _models()[0].model_dump()
    data["crown_pot_wei"] = None
    assert NetworkStateRead(**data).crown_pot_wei is None
    data["crown_pot_wei"] = 0
    assert NetworkStateRead(**data).crown_pot_wei == 0


def test_nullable_values_are_still_required_and_zero_is_preserved():
    data = next(model for model in _models() if isinstance(model, FlowRow)).model_dump()
    data["value"] = 0
    assert FlowRow(**data).value == 0
    data.pop("value")
    with pytest.raises(ValidationError):
        FlowRow(**data)


@pytest.mark.parametrize(
    ("model", "field", "bad_value"),
    (
        (SourceMeta, "source_kind", "website"),
        (FlowRow, "key", "tvl"),
        (FlowRow, "unit", "usd"),
        (DropRow, "phase", "minting"),
        (ProjectRow, "family", "unknown_project"),
        (ProjectRow, "source_badge", "TRUSTED"),
    ),
)
def test_closed_vocabularies_reject_unknown_values(model, field, bad_value):
    instance = next(item for item in _models() if isinstance(item, model))
    data = instance.model_dump()
    data[field] = bad_value
    with pytest.raises(ValidationError):
        model(**data)


def test_closed_vocabulary_constants_are_exact():
    assert FLOW_KEYS == (
        "protocol_escrow_eth", "refund_credits_eth", "settlement_payout",
        "crown_share", "buyback_gross_eth", "buyback_swap_eth",
        "caller_reward_eth", "fwa_bought", "purchaser_route",
        "depositor_route", "burn_route", "burned_since_genesis",
        "burn_24h", "burn_7d", "emissions", "rewards_balance",
        "claim_balance", "token_buy_allowance_eth", "official_integrity",
    )
    assert DROP_PHASES == (
        "uninitialized", "escrowing", "supporting", "launching",
        "complete", "failed", "unwinding", "unknown",
    )
    assert PROJECT_FAMILIES == (
        "pullpool", "group_pull", "standing_orders", "megarip", "fwap",
    )
    assert SOURCE_BADGES == (
        "VERIFIED", "CHAIN-READ", "API STALE", "INTEGRITY", "DEGRADED",
    )


def test_blank_network_payload_is_complete_all_none_and_fresh():
    first = blank_network_payload()
    second = blank_network_payload()
    assert tuple(first) == FWA_NETWORK_DATA_KEYS
    assert all(value is None for value in first.values())
    assert first is not second
    first["network_ready"] = True
    assert second["network_ready"] is None


def test_presentation_rows_do_not_leak_wei_fields():
    for keys in FWA_NETWORK_ROW_KEYS.values():
        assert not any(key.endswith("_wei") for key in keys)


def test_module_has_no_io_client_cache_analytics_or_textual_imports():
    from maxpane_dashboard.data import fwa_ecosystem_models

    source = inspect.getsource(fwa_ecosystem_models)
    for banned in (
        "textual",
        "httpx",
        "requests",
        "aiohttp",
        "fwa_client",
        "fwa_cache",
        "fwa_manager",
        "analytics",
        "pathlib",
        "subprocess",
    ):
        assert f"import {banned}" not in source
        assert f"from {banned}" not in source


def test_shared_fixture_loader_reads_only_below_its_root(tmp_path, monkeypatch):
    fixture = tmp_path / "core" / "state.json"
    fixture.parent.mkdir()
    fixture.write_text(json.dumps({"block": 25_849_738}), encoding="utf-8")
    monkeypatch.setattr(
        fwa_ecosystem_fixtures,
        "FWA_ECOSYSTEM_FIXTURES",
        tmp_path,
    )

    assert fwa_ecosystem_fixtures.load_fwa_ecosystem_fixture(
        "core/state.json"
    ) == {"block": 25_849_738}
    with pytest.raises(ValueError):
        fwa_ecosystem_fixtures.load_fwa_ecosystem_fixture("../outside.json")
    with pytest.raises(ValueError):
        fwa_ecosystem_fixtures.load_fwa_ecosystem_fixture(tmp_path / "core/state.json")


def test_fixed_clock_is_callable_and_advances_only_explicitly():
    clock = FixedClock(100.0)
    assert clock() == 100.0
    assert clock.time() == 100.0
    assert clock.advance(2.5) == 102.5
    assert clock() == 102.5


def test_deny_network_transport_raises_on_every_unhandled_request():
    transport = DenyNetworkTransport()
    with httpx.Client(transport=transport) as client:
        with pytest.raises(AssertionError, match="unexpected network request"):
            client.get("https://rpc.example.invalid")
    assert len(transport.requests) == 1


def test_deny_network_transport_allows_an_explicit_test_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/state"
        return httpx.Response(200, json={"result": "0x1"})

    transport = DenyNetworkTransport(handler)
    with httpx.Client(transport=transport) as client:
        response = client.post("https://rpc.example.invalid/state")
    assert response.json() == {"result": "0x1"}
    assert len(transport.requests) == 1
