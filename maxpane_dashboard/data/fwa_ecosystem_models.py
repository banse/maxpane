"""Frozen presentation boundary for the FWA NETWORK dashboard.

This module contains no transport, cache, analytics, clock, or Textual code.  It
freezes the exact dictionary consumed by the NETWORK widgets and the exact shape
of every list row in that dictionary.  Chain clients keep amounts as strict
integer wei; ``*_eth`` and ``*_fwa`` values below are the one presentation
boundary where whole-token floats are allowed.

Unavailable readings stay ``None``.  A measured zero therefore remains
distinguishable from a failed read all the way to the widget.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS, Wei

__all__ = [
    "DROP_PHASES",
    "DROP_ROW_KEYS",
    "FLOW_KEYS",
    "FLOW_ROW_KEYS",
    "FWA_NETWORK_DATA_KEYS",
    "FWA_NETWORK_ROW_KEYS",
    "FWA_NETWORK_WIDGET_SIGNATURES",
    "FWA_UMBRELLA_DATA_KEYS",
    "NETWORK_EVENT_ROW_KEYS",
    "PROJECT_FAMILIES",
    "PROJECT_ROW_KEYS",
    "ROW_META_KEYS",
    "SOURCE_BADGES",
    "DropRow",
    "FlowRow",
    "NetworkEventRow",
    "NetworkStateRead",
    "ProjectRow",
    "SourceMeta",
    "blank_network_payload",
]


# ---------------------------------------------------------------------------
# Exact flat-dictionary contract
# ---------------------------------------------------------------------------

FWA_NETWORK_DATA_KEYS: tuple[str, ...] = (
    # NETWORK snapshot/title/hero
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
    # value-flow rail
    "network_flow_rows",
    "network_flow_available",
    "network_flow_history_complete",
    "network_flow_as_of_block",
    "network_flow_as_of_ts",
    "network_flow_stale",
    # FWAIR launches
    "network_drop_rows",
    "network_drops_available",
    "network_drops_as_of_block",
    "network_drops_stale",
    # project surfaces and visible legacy liabilities
    "network_project_rows",
    "network_projects_available",
    "network_projects_as_of_block",
    "network_projects_stale",
    # normalized log activity
    "network_events",
    "network_feed_available",
    "network_feed_unavailable_reason",
    "network_feed_as_of_ts",
    # NETWORK-only source health
    "network_degraded_sources",
    "network_integrity_warning_count",
    "network_last_updated_seconds_ago",
    "network_error_count",
)

FWA_UMBRELLA_DATA_KEYS: tuple[str, ...] = FWA_DATA_KEYS + FWA_NETWORK_DATA_KEYS


# ---------------------------------------------------------------------------
# Exact row contracts and closed vocabularies
# ---------------------------------------------------------------------------

ROW_META_KEYS: tuple[str, ...] = (
    "source_kind",
    "measurement",
    "block_number",
    "observed_at",
    "stale",
    "verified_source",
    "integrity",
)

FLOW_ROW_KEYS: tuple[str, ...] = (
    "key",
    "label",
    "value",
    "unit",
    "configured_bps",
    "state",
    "direction",
    "detail",
    "tx_hash",
) + ROW_META_KEYS

DROP_ROW_KEYS: tuple[str, ...] = (
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
) + ROW_META_KEYS

PROJECT_ROW_KEYS: tuple[str, ...] = (
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
) + ROW_META_KEYS

NETWORK_EVENT_ROW_KEYS: tuple[str, ...] = (
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
) + ROW_META_KEYS

FWA_NETWORK_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "network_flow_rows": FLOW_ROW_KEYS,
    "network_drop_rows": DROP_ROW_KEYS,
    "network_project_rows": PROJECT_ROW_KEYS,
    "network_events": NETWORK_EVENT_ROW_KEYS,
}

FLOW_KEYS: tuple[str, ...] = (
    "protocol_escrow_eth",
    "refund_credits_eth",
    "settlement_payout",
    "crown_share",
    "buyback_gross_eth",
    "buyback_swap_eth",
    "caller_reward_eth",
    "fwa_bought",
    "purchaser_route",
    "depositor_route",
    "burn_route",
    "burned_since_genesis",
    "burn_24h",
    "burn_7d",
    "emissions",
    "rewards_balance",
    "claim_balance",
    "token_buy_allowance_eth",
    "official_integrity",
)

DROP_PHASES: tuple[str, ...] = (
    "uninitialized",
    "escrowing",
    "supporting",
    "launching",
    "complete",
    "failed",
    "unwinding",
    "unknown",
)

PROJECT_FAMILIES: tuple[str, ...] = (
    "pullpool",
    "group_pull",
    "standing_orders",
    "megarip",
    "fwap",
)

SOURCE_BADGES: tuple[str, ...] = (
    "VERIFIED",
    "CHAIN-READ",
    "API STALE",
    "INTEGRITY",
    "DEGRADED",
)


# ---------------------------------------------------------------------------
# Strict row models
# ---------------------------------------------------------------------------

_FROZEN = ConfigDict(frozen=True, extra="forbid", strict=True)

SourceKind = Literal["chain_state", "chain_log", "project_api", "market_api"]
Measurement = Literal["measured", "derived", "estimated"]
Integrity = Literal["ok", "warning", "mismatch", "unknown"]
FlowKey = Literal[
    "protocol_escrow_eth",
    "refund_credits_eth",
    "settlement_payout",
    "crown_share",
    "buyback_gross_eth",
    "buyback_swap_eth",
    "caller_reward_eth",
    "fwa_bought",
    "purchaser_route",
    "depositor_route",
    "burn_route",
    "burned_since_genesis",
    "burn_24h",
    "burn_7d",
    "emissions",
    "rewards_balance",
    "claim_balance",
    "token_buy_allowance_eth",
    "official_integrity",
]
FlowUnit = Literal["eth", "fwa", "bps", "seconds", "blocks", "count", "none"]
FlowDirection = Literal["in", "out", "branch", "state"]
DropPhase = Literal[
    "uninitialized",
    "escrowing",
    "supporting",
    "launching",
    "complete",
    "failed",
    "unwinding",
    "unknown",
]
ProjectFamily = Literal["pullpool", "group_pull", "standing_orders", "megarip", "fwap"]
ProjectPrimaryUnit = Literal["rounds", "packs", "orders", "recovery_pct", "nav_eth"]
SourceBadge = Literal["VERIFIED", "CHAIN-READ", "API STALE", "INTEGRITY", "DEGRADED"]


class NetworkStateRead(BaseModel):
    """Pinned raw core/token state before the presentation conversion.

    EVM-denominated values deliberately end in ``_wei`` and use the existing
    strict :class:`~maxpane_dashboard.data.fwa_models.Wei` alias.  A transport
    failure is ``None``; a chain response of zero is ``0``.
    """

    model_config = _FROZEN

    observed_at: float
    state_block: int | None
    chain_head: int | None
    active_listings: int | None
    pull_quote_wei: Wei | None
    pending_count: int | None
    unsettled_count: int | None
    crown_pot_wei: Wei | None
    token_supply_wei: Wei | None


class SourceMeta(BaseModel):
    """Provenance attached to every NETWORK presentation row."""

    model_config = _FROZEN

    source_kind: SourceKind
    measurement: Measurement
    block_number: int | None
    observed_at: float | None
    stale: bool
    verified_source: bool | None
    integrity: Integrity


class FlowRow(BaseModel):
    """One value-flow rail row at the whole-token presentation boundary."""

    model_config = _FROZEN

    key: FlowKey
    label: str
    value: int | float | None
    unit: FlowUnit
    configured_bps: int | None
    state: str | None
    direction: FlowDirection
    detail: str
    tx_hash: str | None
    source_kind: SourceKind
    measurement: Measurement
    block_number: int | None
    observed_at: float | None
    stale: bool
    verified_source: bool | None
    integrity: Integrity


class DropRow(BaseModel):
    """One manager-enumerated FWAIR launch presentation row."""

    model_config = _FROZEN

    launch_id: int
    launch_address: str
    collection_address: str | None
    collection_name: str | None
    phase: DropPhase
    support_open: bool | None
    token_count: int | None
    supported_count: int | None
    supporter_count: int | None
    launched_count: int | None
    terminal_count: int | None
    backing_eth: float | None
    total_backing_eth: float | None
    artist_credit_eth: float | None
    supporter_principal_eth: float | None
    supporter_reserve_fwa: float | None
    source_kind: SourceKind
    measurement: Measurement
    block_number: int | None
    observed_at: float | None
    stale: bool
    verified_source: bool | None
    integrity: Integrity


class ProjectRow(BaseModel):
    """One current project surface or visible legacy-liability row."""

    model_config = _FROZEN

    family: ProjectFamily
    surface: str
    version: str
    address: str
    is_current: bool
    is_legacy_liability: bool
    lifecycle: str
    primary_label: str
    primary_value: int | float | None
    primary_unit: ProjectPrimaryUnit
    eth_label: str
    eth_value: float | None
    fwa_label: str
    fwa_value: float | None
    detail: str
    source_badge: SourceBadge
    source_kind: SourceKind
    measurement: Measurement
    block_number: int | None
    observed_at: float | None
    stale: bool
    verified_source: bool | None
    integrity: Integrity


class NetworkEventRow(BaseModel):
    """One normalized, source-preserving NETWORK activity event."""

    model_config = _FROZEN

    event_id: str
    ts: int | float | None
    tx_hash: str
    log_index: int
    origin: str
    family: str
    version: str | None
    event_key: str
    event_label: str
    eth_amount: float | None
    fwa_amount: float | None
    detail: str
    source_kind: SourceKind
    measurement: Measurement
    block_number: int | None
    observed_at: float | None
    stale: bool
    verified_source: bool | None
    integrity: Integrity


# ---------------------------------------------------------------------------
# Exact widget dispatch contracts
# ---------------------------------------------------------------------------

FWA_NETWORK_WIDGET_SIGNATURES: dict[str, tuple[str, ...]] = {
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


def blank_network_payload() -> dict[str, object | None]:
    """Return a fresh, complete NETWORK payload with every value unknown."""

    return dict.fromkeys(FWA_NETWORK_DATA_KEYS)
