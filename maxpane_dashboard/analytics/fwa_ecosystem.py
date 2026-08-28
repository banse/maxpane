"""Pure tokenomics transformations for the FWA NETWORK dashboard.

No function reads a clock, file, environment variable, or network resource.
Callers pass ``now`` and strict wei-native client models in; this module performs
the single wei-to-whole-token presentation conversion and returns exact
``FlowRow`` dictionaries in frozen ``FLOW_KEYS`` order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from maxpane_dashboard.data.fwa_ecosystem_models import (
    FLOW_KEYS,
    FlowRow,
)
from maxpane_dashboard.data.fwa_tokenomics_client import (
    BuybackEvent,
    IntegrityRead,
    TokenomicsLogRead,
    TokenomicsState,
)

WEI_PER_TOKEN = 10**18
GENESIS_SUPPLY_WEI = 1_000_000_000 * WEI_PER_TOKEN
BASIS_POINT_DENOMINATOR = 10_000

__all__ = [
    "BASIS_POINT_DENOMINATOR",
    "GENESIS_SUPPLY_WEI",
    "WEI_PER_TOKEN",
    "BurnSinceGenesis",
    "BuybackAccounting",
    "EmissionState",
    "build_flow_rows",
    "burned_since_genesis",
    "buyback_accounting",
    "emission_state",
    "route_bps_integrity",
    "wei_to_tokens",
]


def _strict_wei(value: int | None, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer number of wei or None")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def wei_to_tokens(value: int | None) -> float | None:
    """Convert strict wei to a whole ETH/FWA float at presentation boundary."""

    checked = _strict_wei(value, "wei value")
    return None if checked is None else checked / WEI_PER_TOKEN


@dataclass(frozen=True, slots=True)
class BurnSinceGenesis:
    burned_wei: int | None
    burned_fwa: float | None
    burned_pct: float | None
    invariant_ok: bool | None


def burned_since_genesis(total_supply_wei: int | None) -> BurnSinceGenesis:
    """Genesis supply minus live supply, guarded against impossible inflation."""

    supply = _strict_wei(total_supply_wei, "total_supply_wei")
    if supply is None:
        return BurnSinceGenesis(None, None, None, None)
    if supply > GENESIS_SUPPLY_WEI:
        return BurnSinceGenesis(None, None, None, False)
    burned = GENESIS_SUPPLY_WEI - supply
    return BurnSinceGenesis(
        burned_wei=burned,
        burned_fwa=wei_to_tokens(burned),
        burned_pct=burned * 100.0 / GENESIS_SUPPLY_WEI,
        invariant_ok=True,
    )


EmissionStatus = Literal["pending", "live", "ended", "unavailable"]


@dataclass(frozen=True, slots=True)
class EmissionState:
    status: EmissionStatus
    start_ts: int | None
    end_ts: int | None
    seconds_remaining: float | None


def emission_state(
    emission_start: int | None,
    emission_duration: int | None,
    *,
    now: float,
) -> EmissionState:
    """Determine schedule state from start+duration, never from legacy rates."""

    if isinstance(now, bool) or not isinstance(now, (int, float)):
        raise TypeError("now must be epoch seconds")
    start = _strict_wei(emission_start, "emission_start")
    duration = _strict_wei(emission_duration, "emission_duration")
    if start is None or duration is None or duration <= 0:
        return EmissionState("unavailable", start, None, None)
    end = start + duration
    if now < start:
        return EmissionState("pending", start, end, float(start - now))
    if now < end:
        return EmissionState("live", start, end, float(end - now))
    return EmissionState("ended", start, end, 0.0)


def route_bps_integrity(
    depositor_bps: int | None,
    purchaser_bps: int | None,
    burn_bps: int | None,
) -> bool | None:
    """Whether all three live route shares are valid and sum to 10,000."""

    values = (depositor_bps, purchaser_bps, burn_bps)
    if any(value is None for value in values):
        return None
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > BASIS_POINT_DENOMINATOR
        for value in values
    ):
        return False
    return sum(values) == BASIS_POINT_DENOMINATOR


@dataclass(frozen=True, slots=True)
class BuybackAccounting:
    gross_eth_wei: int | None
    caller_reward_ok: bool | None
    route_config_ok: bool | None
    routed_sum_ok: bool | None
    routed_amounts_ok: bool | None
    integrity: Literal["ok", "mismatch", "unknown"]


def buyback_accounting(
    event: BuybackEvent | None,
    *,
    caller_reward_bps: int | None,
    depositor_bps: int | None,
    purchaser_bps: int | None,
    burn_bps: int | None,
) -> BuybackAccounting:
    """Validate gross/caller/routing arithmetic against live configuration."""

    config_ok = route_bps_integrity(depositor_bps, purchaser_bps, burn_bps)
    if event is None:
        checks = (None, config_ok, None, None)
        integrity = "mismatch" if False in checks else "unknown"
        return BuybackAccounting(None, None, config_ok, None, None, integrity)

    gross = event.eth_spent_wei + event.caller_reward_wei
    caller_ok: bool | None
    if caller_reward_bps is None:
        caller_ok = None
    elif (
        isinstance(caller_reward_bps, bool)
        or not isinstance(caller_reward_bps, int)
        or not 0 <= caller_reward_bps <= BASIS_POINT_DENOMINATOR
    ):
        caller_ok = False
    else:
        expected = gross * caller_reward_bps // BASIS_POINT_DENOMINATOR
        caller_ok = abs(event.caller_reward_wei - expected) <= 1

    routes = (
        event.to_depositors_wei,
        event.to_purchasers_wei,
        event.burned_wei,
    )
    if any(value is None for value in routes):
        routed_sum_ok = None
        amounts_ok = None
    else:
        dep, purchaser, burned = routes
        assert dep is not None and purchaser is not None and burned is not None
        routed_sum_ok = dep + purchaser + burned == event.amount_bought_wei
        if config_ok is not True:
            amounts_ok = config_ok
        else:
            configured = (
                depositor_bps,
                purchaser_bps,
                burn_bps,
            )
            assert all(value is not None for value in configured)
            expected_routes = tuple(
                event.amount_bought_wei * int(bps) // BASIS_POINT_DENOMINATOR
                for bps in configured
            )
            # Integer division can leave at most two wei of remainder for one
            # of three destinations.  The event sum still has to be exact.
            amounts_ok = routed_sum_ok and all(
                abs(actual - expected) <= 2
                for actual, expected in zip(routes, expected_routes, strict=True)
            )

    checks = (caller_ok, config_ok, routed_sum_ok, amounts_ok)
    if False in checks:
        integrity: Literal["ok", "mismatch", "unknown"] = "mismatch"
    elif None in checks:
        integrity = "unknown"
    else:
        integrity = "ok"
    return BuybackAccounting(
        gross_eth_wei=gross,
        caller_reward_ok=caller_ok,
        route_config_ok=config_ok,
        routed_sum_ok=routed_sum_ok,
        routed_amounts_ok=amounts_ok,
        integrity=integrity,
    )


def _role_integrity(
    integrity: IntegrityRead | None,
    *roles: str,
) -> Literal["ok", "mismatch", "unknown"]:
    if integrity is None:
        return "unknown"
    status = integrity.status_for(*roles)
    if status == "mismatch":
        return "mismatch"
    if status == "ok":
        return "ok"
    return "unknown"


def _value_integrity(
    value: int | float | None,
    source_integrity: Literal["ok", "mismatch", "unknown"],
) -> Literal["ok", "mismatch", "unknown"]:
    if source_integrity == "mismatch":
        return "mismatch"
    if value is None or source_integrity == "unknown":
        return "unknown"
    return "ok"


def _visible(
    value: int | float | None,
    source_integrity: Literal["ok", "mismatch", "unknown"],
) -> int | float | None:
    return None if source_integrity == "mismatch" else value


def _row(
    *,
    key: str,
    label: str,
    value: int | float | None,
    unit: str,
    configured_bps: int | None,
    state: str | None,
    direction: str,
    detail: str,
    tx_hash: str | None,
    source_kind: str,
    measurement: str,
    block_number: int | None,
    observed_at: float | None,
    stale: bool,
    integrity: str,
) -> dict[str, object]:
    return FlowRow(
        key=key,
        label=label,
        value=value,
        unit=unit,
        configured_bps=configured_bps,
        state=state,
        direction=direction,
        detail=detail,
        tx_hash=tx_hash,
        source_kind=source_kind,
        measurement=measurement,
        block_number=block_number,
        observed_at=observed_at,
        stale=stale,
        verified_source=True,
        integrity=integrity,
    ).model_dump()


def _state_label(value: object | None, live: str = "live") -> str:
    return live if value is not None else "unavailable"


def _latest_buyback(logs: TokenomicsLogRead | None) -> BuybackEvent | None:
    if logs is None or not logs.buybacks:
        return None
    return max(
        logs.buybacks,
        key=lambda event: (event.block_number, event.bought_log_index),
    )


def _burn_window(
    logs: TokenomicsLogRead | None,
    *,
    now: float,
    seconds: int,
) -> int | None:
    if logs is None or not logs.burns_available or not logs.history_complete:
        return None
    cutoff = now - seconds
    return sum(
        event.amount_wei
        for event in logs.burns
        if event.block_timestamp is not None and event.block_timestamp >= cutoff
    )


def build_flow_rows(
    state: TokenomicsState,
    *,
    now: float,
    logs: TokenomicsLogRead | None = None,
    integrity: IntegrityRead | None = None,
    state_stale: bool = False,
    logs_stale: bool = False,
) -> list[dict[str, object]]:
    """Build every flow row exactly once and in frozen ``FLOW_KEYS`` order."""

    if isinstance(now, bool) or not isinstance(now, (int, float)):
        raise TypeError("now must be epoch seconds")

    core_integrity = _role_integrity(integrity, "core")
    token_integrity = _role_integrity(integrity, "token", "hook")
    rewards_integrity = _role_integrity(integrity, "rewards")
    state_block = state.state_block
    state_seen = state.observed_at

    rows: list[dict[str, object]] = []

    def state_row(
        key: str,
        label: str,
        raw_value: int | float | None,
        *,
        unit: str,
        direction: str,
        detail: str,
        role_status: Literal["ok", "mismatch", "unknown"],
        measurement: str = "measured",
        configured_bps: int | None = None,
        state_name: str | None = None,
    ) -> None:
        value = _visible(raw_value, role_status)
        row_integrity = _value_integrity(value, role_status)
        rows.append(
            _row(
                key=key,
                label=label,
                value=value,
                unit=unit,
                configured_bps=configured_bps,
                state=state_name or _state_label(value),
                direction=direction,
                detail=detail,
                tx_hash=None,
                source_kind="chain_state",
                measurement=measurement,
                block_number=state_block,
                observed_at=state_seen,
                stale=state_stale,
                integrity=row_integrity,
            )
        )

    state_row(
        "protocol_escrow_eth",
        "ACQUISITION ESCROW",
        wei_to_tokens(state.acquisition_escrow_wei),
        unit="eth",
        direction="state",
        detail="unresolved purchaser funds; a liability, not revenue",
        role_status=core_integrity,
    )
    state_row(
        "refund_credits_eth",
        "REFUND CREDITS",
        wei_to_tokens(state.refund_credit_total_wei),
        unit="eth",
        direction="out",
        detail="pull-based purchaser refunds outstanding",
        role_status=core_integrity,
    )
    state_row(
        "settlement_payout",
        "SETTLEMENT PAYOUT",
        state.settlement_payout_bps,
        unit="bps",
        direction="out",
        detail="purchaser share of backing when accepting the bid",
        role_status=core_integrity,
        configured_bps=state.settlement_payout_bps,
    )
    state_row(
        "crown_share",
        "CROWN SHARE",
        state.crown_share_bps,
        unit="bps",
        direction="branch",
        detail="live share of acquisition distributable routed to the crown",
        role_status=core_integrity,
        configured_bps=state.crown_share_bps,
    )

    latest = _latest_buyback(logs)
    accounting = buyback_accounting(
        latest,
        caller_reward_bps=state.caller_reward_bps,
        depositor_bps=state.route_depositor_bps,
        purchaser_bps=state.route_purchaser_bps,
        burn_bps=state.route_burn_bps,
    )
    buyback_block = None if latest is None else latest.block_number
    buyback_seen = None if logs is None else logs.observed_at
    buyback_tx = None if latest is None else latest.tx_hash
    if accounting.integrity == "mismatch" or token_integrity == "mismatch":
        log_integrity: Literal["ok", "mismatch", "unknown"] = "mismatch"
    elif accounting.integrity == "ok" and token_integrity == "ok":
        log_integrity = "ok"
    else:
        log_integrity = "unknown"

    def buyback_row(
        key: str,
        label: str,
        raw_wei: int | None,
        *,
        direction: str,
        detail: str,
        configured_bps: int | None = None,
    ) -> None:
        converted = wei_to_tokens(raw_wei)
        converted = _visible(converted, log_integrity)
        rows.append(
            _row(
                key=key,
                label=label,
                value=converted,
                unit="eth" if key.endswith("_eth") else "fwa",
                configured_bps=configured_bps,
                state=_state_label(converted, "observed"),
                direction=direction,
                detail=detail,
                tx_hash=buyback_tx,
                source_kind="chain_log",
                measurement="derived" if key == "buyback_gross_eth" else "measured",
                block_number=buyback_block,
                observed_at=buyback_seen,
                stale=logs_stale,
                integrity=_value_integrity(converted, log_integrity),
            )
        )

    buyback_row(
        "buyback_gross_eth",
        "BUYBACK GROSS",
        accounting.gross_eth_wei,
        direction="in",
        detail="swap ETH plus permissionless caller reward",
    )
    buyback_row(
        "buyback_swap_eth",
        "BUYBACK SWAP",
        None if latest is None else latest.eth_spent_wei,
        direction="in",
        detail="ETH reported spent by Bought",
    )
    buyback_row(
        "caller_reward_eth",
        "CALLER REWARD",
        None if latest is None else latest.caller_reward_wei,
        direction="out",
        detail="caller bounty checked against gross ETH",
        configured_bps=state.caller_reward_bps,
    )
    buyback_row(
        "fwa_bought",
        "FWA BOUGHT",
        None if latest is None else latest.amount_bought_wei,
        direction="in",
        detail="token amount reported by Bought",
    )
    buyback_row(
        "purchaser_route",
        "TO PURCHASERS",
        None if latest is None else latest.to_purchasers_wei,
        direction="branch",
        detail="observed route amount beside live configured share",
        configured_bps=state.route_purchaser_bps,
    )
    buyback_row(
        "depositor_route",
        "TO DEPOSITORS",
        None if latest is None else latest.to_depositors_wei,
        direction="branch",
        detail="observed route amount beside live configured share",
        configured_bps=state.route_depositor_bps,
    )
    buyback_row(
        "burn_route",
        "TO BURN",
        None if latest is None else latest.burned_wei,
        direction="branch",
        detail="observed route amount beside live configured share",
        configured_bps=state.route_burn_bps,
    )

    burn = burned_since_genesis(state.total_supply_wei)
    burn_integrity = token_integrity
    if burn.invariant_ok is False:
        burn_integrity = "mismatch"
    state_row(
        "burned_since_genesis",
        "BURNED SINCE GENESIS",
        burn.burned_fwa,
        unit="fwa",
        direction="out",
        detail="1,000,000,000 FWA genesis supply minus live totalSupply",
        role_status=burn_integrity,
        measurement="derived",
    )

    for key, label, seconds in (
        ("burn_24h", "BURN · 24H", 86_400),
        ("burn_7d", "BURN · 7D", 7 * 86_400),
    ):
        burn_wei = _burn_window(logs, now=float(now), seconds=seconds)
        value = wei_to_tokens(burn_wei)
        value = _visible(value, token_integrity)
        rows.append(
            _row(
                key=key,
                label=label,
                value=value,
                unit="fwa",
                configured_bps=None,
                state=(
                    "history incomplete"
                    if logs is not None and not logs.history_complete
                    else _state_label(value, "measured")
                ),
                direction="out",
                detail="supply-reducing Transfer logs in the measured window",
                tx_hash=None,
                source_kind="chain_log",
                measurement="derived",
                block_number=None if logs is None else logs.to_block,
                observed_at=None if logs is None else logs.observed_at,
                stale=logs_stale,
                integrity=_value_integrity(value, token_integrity),
            )
        )

    emissions = emission_state(
        state.emission_start,
        state.emission_duration,
        now=float(now),
    )
    emission_value = _visible(emissions.seconds_remaining, rewards_integrity)
    rows.append(
        _row(
            key="emissions",
            label="EMISSIONS",
            value=emission_value,
            unit="seconds",
            configured_bps=None,
            state=emissions.status if rewards_integrity != "mismatch" else "unavailable",
            direction="state",
            detail=(
                "schedule ended; nonzero legacy rate getters do not restart it"
                if emissions.status == "ended"
                else "state derived only from emissionStart + EMISSION_DURATION"
            ),
            tx_hash=None,
            source_kind="chain_state",
            measurement="derived",
            block_number=state_block,
            observed_at=state_seen,
            stale=state_stale,
            integrity=_value_integrity(emission_value, rewards_integrity),
        )
    )
    state_row(
        "rewards_balance",
        "REWARDS BALANCE",
        wei_to_tokens(state.rewards_balance_wei),
        unit="fwa",
        direction="state",
        detail="live FWA balance held by FWARewards",
        role_status=rewards_integrity,
    )
    state_row(
        "claim_balance",
        "CLAIM BALANCE",
        wei_to_tokens(state.claim_balance_wei),
        unit="fwa",
        direction="state",
        detail="live FWA balance held by the v1 claim contract",
        role_status=_role_integrity(integrity, "token", "v1_claim"),
    )
    state_row(
        "token_buy_allowance_eth",
        "TOKEN BUY ALLOWANCE",
        wei_to_tokens(state.token_buy_allowance_wei),
        unit="eth",
        direction="in",
        detail="accounted purchaser allowance awaiting a reward-token buy",
        role_status=rewards_integrity,
    )

    if integrity is None:
        mismatch_count: int | None = None
        official_status = "unavailable"
        official_integrity: Literal["ok", "mismatch", "unknown"] = "unknown"
    else:
        all_checks = tuple(integrity.codehash_matches.values()) + tuple(
            integrity.dependency_matches.values()
        )
        mismatch_count = sum(result is False for result in all_checks)
        if not all_checks:
            mismatch_count = None
            official_status = "unavailable"
            official_integrity = "unknown"
        elif mismatch_count:
            official_status = "mismatch"
            official_integrity = "mismatch"
        elif any(result is None for result in all_checks):
            official_status = "incomplete"
            official_integrity = "unknown"
        else:
            official_status = "ok"
            official_integrity = "ok"
    rows.append(
        _row(
            key="official_integrity",
            label="OFFICIAL INTEGRITY",
            value=mismatch_count,
            unit="count",
            configured_bps=None,
            state=official_status,
            direction="state",
            detail="runtime codehash and canonical dependency mismatches",
            tx_hash=None,
            source_kind="chain_state",
            measurement="measured",
            block_number=None if integrity is None else integrity.block_number,
            observed_at=None if integrity is None else integrity.observed_at,
            stale=state_stale,
            integrity=official_integrity,
        )
    )

    if tuple(row["key"] for row in rows) != FLOW_KEYS:
        raise AssertionError("flow analytics drifted from frozen FLOW_KEYS order")
    return rows
