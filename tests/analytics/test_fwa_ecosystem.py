"""Pure tests for FWA NETWORK value-flow analytics."""

from __future__ import annotations

import inspect

import pytest

from maxpane_dashboard.analytics.fwa_ecosystem import (
    GENESIS_SUPPLY_WEI,
    build_flow_rows,
    burned_since_genesis,
    buyback_accounting,
    emission_state,
    route_bps_integrity,
    wei_to_tokens,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    FLOW_KEYS,
    FLOW_ROW_KEYS,
)
from maxpane_dashboard.data.fwa_tokenomics_client import (
    BuybackEvent,
    BurnEvent,
    IntegrityRead,
    TokenomicsLogRead,
    TokenomicsState,
)
from tests.fwa_ecosystem_fixtures import load_fwa_ecosystem_fixture


STATE = load_fwa_ecosystem_fixture("core/state_snapshot.json")
LOGS = load_fwa_ecosystem_fixture("core/flow_logs.json")
NOW = LOGS["observed_at"]


def _state(**changes: object) -> TokenomicsState:
    values = {**STATE["state"], **changes}
    return TokenomicsState(
        observed_at=STATE["observed_at"],
        state_block=STATE["block_number"],
        chain_head=STATE["block_number"],
        gas_price_wei=STATE["gas_price_wei"],
        quote_total_wei=STATE["quote"]["total_wei"],
        failed_fields=(),
        **values,
    )


def _buyback(**changes: object) -> BuybackEvent:
    values = {**LOGS["buyback"], **changes}
    return BuybackEvent(
        block_number=values["block_number"],
        block_timestamp=values["block_timestamp"],
        observed_at=LOGS["observed_at"],
        tx_hash=values["tx_hash"],
        bought_log_index=values["bought_log_index"],
        routed_log_index=values["routed_log_index"],
        caller=values["caller"],
        eth_spent_wei=values["eth_spent_wei"],
        amount_bought_wei=values["amount_bought_wei"],
        caller_reward_wei=values["caller_reward_wei"],
        to_depositors_wei=values["to_depositors_wei"],
        to_purchasers_wei=values["to_purchasers_wei"],
        burned_wei=values["burned_wei"],
    )


def _logs(*, history_complete: bool = True) -> TokenomicsLogRead:
    burns = tuple(
        BurnEvent(
            block_number=row["block_number"],
            block_timestamp=row["block_timestamp"],
            observed_at=LOGS["observed_at"],
            tx_hash=row["tx_hash"],
            log_index=row["log_index"],
            recipient=row["recipient"],
            amount_wei=row["amount_wei"],
        )
        for row in LOGS["burns"]
    )
    return TokenomicsLogRead(
        observed_at=LOGS["observed_at"],
        from_block=LOGS["from_block"],
        to_block=LOGS["to_block"],
        history_complete=history_complete,
        buybacks_available=True,
        burns_available=True,
        unavailable_reason=None,
        buybacks=(_buyback(),),
        burns=burns,
    )


def _integrity(**code_changes: bool | None) -> IntegrityRead:
    codehashes = {
        "core": True,
        "rewards": True,
        "token": True,
        "hook": True,
        "v1_claim": True,
        **code_changes,
    }
    dependencies = {
        "core.rewards": True,
        "core.vrfService": True,
        "rewards.fwa": True,
        "rewards.token": True,
        "rewards.tokenHook": True,
        "token.hook": True,
        "token.pool": True,
        "hook.token": True,
        "v1_claim.token": True,
    }
    return IntegrityRead(
        observed_at=NOW,
        block_number=STATE["block_number"],
        codehash_matches=codehashes,
        dependency_matches=dependencies,
    )


def _by_key(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["key"]): row for row in rows}


def test_wei_conversion_is_strict_and_preserves_none_and_zero() -> None:
    assert wei_to_tokens(None) is None
    assert wei_to_tokens(0) == 0.0
    assert wei_to_tokens(10**18) == 1.0
    with pytest.raises(TypeError):
        wei_to_tokens(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        wei_to_tokens(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        wei_to_tokens(-1)


def test_genesis_burn_is_guarded_against_an_impossible_supply() -> None:
    live = STATE["state"]["total_supply_wei"]
    summary = burned_since_genesis(live)
    assert summary.burned_wei == GENESIS_SUPPLY_WEI - live
    assert summary.burned_fwa == pytest.approx(13_619_263.227288231)
    assert summary.burned_pct == pytest.approx(1.3619263227288232)
    assert summary.invariant_ok is True

    impossible = burned_since_genesis(GENESIS_SUPPLY_WEI + 1)
    assert impossible.burned_wei is None
    assert impossible.burned_pct is None
    assert impossible.invariant_ok is False


def test_emission_state_uses_only_start_duration_and_injected_now() -> None:
    start = STATE["state"]["emission_start"]
    duration = STATE["state"]["emission_duration"]
    assert emission_state(start, duration, now=start - 1).status == "pending"
    assert emission_state(start, duration, now=start + 1).status == "live"
    ended = emission_state(start, duration, now=NOW)
    assert ended.status == "ended"
    assert ended.seconds_remaining == 0.0
    assert ended.end_ts == start + duration
    # There is intentionally no rate input through which a nonzero legacy
    # depositorRatePerSec could revive this ended schedule.
    assert "rate" not in inspect.signature(emission_state).parameters


def test_live_route_split_is_read_not_copied_from_old_research() -> None:
    state = _state()
    assert route_bps_integrity(
        state.route_depositor_bps,
        state.route_purchaser_bps,
        state.route_burn_bps,
    ) is True
    assert (
        state.route_purchaser_bps,
        state.route_depositor_bps,
        state.route_burn_bps,
    ) == (4000, 3000, 3000)
    assert route_bps_integrity(4000, 4000, 3000) is False
    assert route_bps_integrity(None, 4000, 3000) is None


def test_buyback_gross_caller_and_routes_reconcile_with_integer_remainder() -> None:
    state = _state()
    event = _buyback()
    result = buyback_accounting(
        event,
        caller_reward_bps=state.caller_reward_bps,
        depositor_bps=state.route_depositor_bps,
        purchaser_bps=state.route_purchaser_bps,
        burn_bps=state.route_burn_bps,
    )
    assert result.gross_eth_wei == 5_722_834_282_592_458
    assert result.caller_reward_ok is True
    assert result.route_config_ok is True
    assert result.routed_sum_ok is True
    assert result.routed_amounts_ok is True
    assert result.integrity == "ok"


def test_buyback_invariant_mutations_are_detected() -> None:
    state = _state()
    bad_caller = _buyback(caller_reward_wei=1)
    assert buyback_accounting(
        bad_caller,
        caller_reward_bps=state.caller_reward_bps,
        depositor_bps=state.route_depositor_bps,
        purchaser_bps=state.route_purchaser_bps,
        burn_bps=state.route_burn_bps,
    ).integrity == "mismatch"

    assert buyback_accounting(
        _buyback(),
        caller_reward_bps=state.caller_reward_bps,
        depositor_bps=4000,
        purchaser_bps=4000,
        burn_bps=3000,
    ).integrity == "mismatch"


def test_flow_rows_are_exact_ordered_and_fixture_mutations_reach_output() -> None:
    mutation = STATE["mutation"]
    baseline = _by_key(
        build_flow_rows(
            _state(),
            now=NOW,
            logs=_logs(),
            integrity=_integrity(),
        )
    )
    rows = build_flow_rows(
        _state(**mutation),
        now=NOW,
        logs=_logs(),
        integrity=_integrity(),
    )
    assert tuple(row["key"] for row in rows) == FLOW_KEYS
    assert all(tuple(row) == FLOW_ROW_KEYS for row in rows)
    by_key = _by_key(rows)

    assert baseline["settlement_payout"]["value"] == 9000
    assert baseline["crown_share"]["value"] == 50
    assert by_key["settlement_payout"]["value"] == 8750
    assert by_key["settlement_payout"]["configured_bps"] == 8750
    assert by_key["crown_share"]["value"] == 75
    assert by_key["crown_share"]["configured_bps"] == 75
    assert by_key["purchaser_route"]["configured_bps"] == 4000
    assert by_key["depositor_route"]["configured_bps"] == 3000
    assert by_key["burn_route"]["configured_bps"] == 3000
    assert by_key["buyback_gross_eth"]["value"] == pytest.approx(
        0.005722834282592458
    )
    assert by_key["emissions"]["state"] == "ended"
    assert by_key["emissions"]["value"] == 0.0
    # Fixture retains a nonzero legacy rate to prove it did not drive state.
    assert STATE["state"]["depositor_rate_per_sec_wei"] > 0
    assert by_key["official_integrity"]["value"] == 0
    assert by_key["settlement_payout"]["value"] != baseline[
        "settlement_payout"
    ]["value"]
    assert by_key["crown_share"]["value"] != baseline["crown_share"]["value"]


def test_burn_windows_require_complete_history_and_use_event_timestamps() -> None:
    complete = _by_key(
        build_flow_rows(
            _state(), now=NOW, logs=_logs(), integrity=_integrity()
        )
    )
    assert complete["burn_24h"]["value"] == pytest.approx(500_000.0)
    assert complete["burn_7d"]["value"] == pytest.approx(1_500_000.0)

    incomplete = _by_key(
        build_flow_rows(
            _state(),
            now=NOW,
            logs=_logs(history_complete=False),
            integrity=_integrity(),
        )
    )
    assert incomplete["burn_24h"]["value"] is None
    assert incomplete["burn_7d"]["value"] is None
    assert incomplete["burn_7d"]["state"] == "history incomplete"


def test_codehash_mismatch_suppresses_only_affected_semantics() -> None:
    rows = _by_key(
        build_flow_rows(
            _state(),
            now=NOW,
            logs=_logs(),
            integrity=_integrity(token=False),
        )
    )
    assert rows["protocol_escrow_eth"]["value"] == pytest.approx(
        STATE["state"]["acquisition_escrow_wei"] / 10**18
    )
    assert rows["burned_since_genesis"]["value"] is None
    assert rows["fwa_bought"]["value"] is None
    assert rows["purchaser_route"]["value"] is None
    assert rows["official_integrity"]["value"] == 1
    assert rows["official_integrity"]["integrity"] == "mismatch"


def test_unavailable_read_remains_none_instead_of_becoming_zero() -> None:
    rows = _by_key(
        build_flow_rows(
            _state(refund_credit_total_wei=None),
            now=NOW,
            logs=None,
            integrity=_integrity(),
        )
    )
    assert rows["refund_credits_eth"]["value"] is None
    assert rows["refund_credits_eth"]["state"] == "unavailable"
    assert rows["buyback_gross_eth"]["value"] is None
    assert rows["burn_24h"]["value"] is None


def test_analytics_has_no_wallclock_dependency() -> None:
    source = inspect.getsource(build_flow_rows)
    assert "time.time" not in source
    assert "datetime.now" not in source
    assert "now:" in source
