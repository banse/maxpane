"""Block-pinned MegaRip v1-v3 state and versioned activity.

MegaRip generations are independent campaigns.  This adapter reads all three
at one explicit state block, validates their pinned runtime and canonical FWA
dependencies, and only then publishes campaign semantics.  MegaRip v3 remains
``CHAIN-READ`` even when every check passes because its source is unverified.

State and history deliberately stay separate.  State uses the existing Pool A
Multicall client; logs use one hardened Pool B client per deployed address.
Historical event completeness never affects current liabilities: ETH comes
from the contract's aggregate ledger and FWA comes from cumulative received
minus cumulative paid accounting.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.evm_abi import (
    decode_address,
    decode_uint,
    encode_address,
    strip0x,
)
from maxpane_dashboard.data.fwa_client import FWAClient
from maxpane_dashboard.data.fwa_ecosystem_models import (
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
    NetworkEventRow,
    ProjectRow,
)
from maxpane_dashboard.data.fwa_logs import FWALogClient
from maxpane_dashboard.data.fwa_models import Wei
from maxpane_dashboard.data.keccak import keccak256_hex

from .base import ProjectManifest, load_abi_resource, load_manifest_abi
from .registry import manifests_for_family

logger = logging.getLogger(__name__)

_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True)
_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_TX_HASH_RE = _BYTES32_RE
_WEI_PER_TOKEN = 10**18

Integrity = Literal["ok", "warning", "mismatch", "unknown"]


# ---------------------------------------------------------------------------
# Vendored ABI -> immutable selector/topic surfaces
# ---------------------------------------------------------------------------


def _abi_signature(entry: Mapping[str, Any]) -> str:
    name = entry.get("name")
    inputs = entry.get("inputs")
    if not isinstance(name, str) or not isinstance(inputs, list):
        raise ValueError("ABI entry must declare a name and input array")
    types: list[str] = []
    for item in inputs:
        if not isinstance(item, Mapping) or not isinstance(item.get("type"), str):
            raise ValueError("ABI input must declare a type")
        types.append(item["type"])
    return f"{name}({','.join(types)})"


def _view_selector(abi: Sequence[Mapping[str, Any]], name: str) -> str:
    matches = [
        entry
        for entry in abi
        if entry.get("type") == "function"
        and entry.get("name") == name
        and entry.get("inputs") == []
    ]
    if len(matches) != 1:
        raise ValueError(f"vendored MegaRip ABI has {len(matches)} {name}() reads")
    if matches[0].get("stateMutability") not in {"view", "pure"}:
        raise ValueError(f"MegaRip read surface contains mutating {name}()")
    return keccak256_hex(_abi_signature(matches[0]).encode())[:10]


def _one_arg_view_selector(
    abi: Sequence[Mapping[str, Any]], name: str, argument_type: str
) -> str:
    matches = [
        entry
        for entry in abi
        if entry.get("type") == "function"
        and entry.get("name") == name
        and [item.get("type") for item in entry.get("inputs", ())]
        == [argument_type]
    ]
    if len(matches) != 1:
        raise ValueError(
            f"vendored ABI has {len(matches)} {name}({argument_type}) reads"
        )
    if matches[0].get("stateMutability") not in {"view", "pure"}:
        raise ValueError(f"read surface contains mutating {name}({argument_type})")
    return keccak256_hex(_abi_signature(matches[0]).encode())[:10]


MEGARIP_MANIFESTS: tuple[ProjectManifest, ...] = manifests_for_family("megarip")
_MANIFEST_BY_VERSION: Mapping[str, ProjectManifest] = MappingProxyType(
    {manifest.version: manifest for manifest in MEGARIP_MANIFESTS}
)

_COMMON_READS: tuple[str, ...] = (
    "state",
    "totalDeposited",
    "depositorCount",
    "pullsDone",
    "pot",
    "totalPaid",
    "potRemaining",
    "accountedEth",
    "acquisitionSpend",
    "pullBudget",
    "bountyReserve",
    "auctionEscrow",
    "pendingRefundTotal",
    "activeCount",
)
_FWA_READS: tuple[str, ...] = (
    "fwaReceived",
    "fwaTotalPaid",
    "fwaOperatorClaimable",
)


def _state_selectors(manifest: ProjectManifest) -> Mapping[str, str]:
    abi = load_manifest_abi(manifest)
    names = [*_COMMON_READS, *(getter for getter, _ in manifest.dependencies)]
    if manifest.version != "v1":
        names.extend(_FWA_READS)
    return MappingProxyType({name: _view_selector(abi, name) for name in names})


STATE_SELECTORS_BY_VERSION: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        manifest.version: _state_selectors(manifest)
        for manifest in MEGARIP_MANIFESTS
    }
)

_TOKEN_ABI = load_abi_resource("abis/fwa/fwa_token.json")
TOKEN_IS_DISTRIBUTOR_SELECTOR = _one_arg_view_selector(
    _TOKEN_ABI, "isDistributor", "address"
)


def _event_entries(manifest: ProjectManifest) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        entry
        for entry in load_manifest_abi(manifest)
        if entry.get("type") == "event"
    )


_EVENT_ABI_BY_VERSION: Mapping[str, tuple[Mapping[str, Any], ...]] = MappingProxyType(
    {
        manifest.version: _event_entries(manifest)
        for manifest in MEGARIP_MANIFESTS
    }
)
EVENT_TOPICS_BY_VERSION: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        version: MappingProxyType(
            {
                str(entry["name"]): keccak256_hex(_abi_signature(entry).encode())
                for entry in entries
            }
        )
        for version, entries in _EVENT_ABI_BY_VERSION.items()
    }
)


# ---------------------------------------------------------------------------
# Strict wei-native state/log boundaries
# ---------------------------------------------------------------------------


class MegaRipCampaignState(BaseModel):
    """One version at one block; failed reads remain ``None``."""

    model_config = _STRICT

    version: str
    address: str
    is_current: bool
    source_verified: bool
    observed_at: float
    block_number: int
    semantic_available: bool
    integrity: Integrity
    actual_codehash: str | None
    dependency_reads: tuple[tuple[str, str | None], ...]
    lifecycle_index: int | None = None
    total_deposited_wei: Wei | None = None
    depositor_count: int | None = None
    pulls_done: int | None = None
    pot_wei: Wei | None = None
    total_paid_wei: Wei | None = None
    eth_claims_outstanding_wei: Wei | None = None
    accounted_eth_wei: Wei | None = None
    acquisition_spend_wei: Wei | None = None
    pull_budget_wei: Wei | None = None
    bounty_reserve_wei: Wei | None = None
    auction_escrow_wei: Wei | None = None
    pending_refund_total_wei: Wei | None = None
    active_count: int | None = None
    fwa_received_wei: Wei | None = None
    fwa_total_paid_wei: Wei | None = None
    fwa_outstanding_wei: Wei | None = None
    fwa_operator_claimable_wei: Wei | None = None
    fwa_distributor: bool | None = None
    issues: tuple[str, ...] = ()


class MegaRipStateRead(BaseModel):
    """All three generations at one common block plus presentation rows."""

    model_config = _STRICT

    observed_at: float
    state_block: int | None
    chain_head: int | None
    available: bool
    integrity: Integrity
    campaigns: tuple[MegaRipCampaignState, ...]
    rows: tuple[ProjectRow, ...]
    issues: tuple[str, ...]


class MegaRipEventRead(BaseModel):
    """One complete-or-not log page and its cache-watermark proof."""

    model_config = _STRICT

    observed_at: float
    version: str
    from_block: int
    to_block: int
    available: bool
    history_complete: bool
    page_complete: bool
    last_complete_block: int | None
    last_complete_block_hash: str | None
    events: tuple[NetworkEventRow, ...]
    unavailable_reason: str | None
    issues: tuple[str, ...]


# ---------------------------------------------------------------------------
# Defensive static decoders and pure accounting
# ---------------------------------------------------------------------------


def _word(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = strip0x(raw).lower()
    if len(value) != 64:
        return None
    try:
        bytes.fromhex(value)
    except ValueError:
        return None
    return "0x" + value


def _uint(raw: Any) -> int | None:
    word = _word(raw)
    return None if word is None else decode_uint(word)


def _address(raw: Any) -> str | None:
    word = _word(raw)
    if word is None:
        return None
    address = decode_address(word).lower()
    return address if _ADDRESS_RE.fullmatch(address) else None


def _bool(raw: Any) -> bool | None:
    value = _uint(raw)
    return None if value not in {0, 1} else bool(value)


def _successful(result: tuple[bool, str] | None) -> str | None:
    if result is None or result[0] is not True:
        return None
    return result[1]


def runtime_codehash(raw_code: Any) -> str | None:
    """Keccak of non-empty runtime bytecode, or ``None`` for malformed data."""

    if not isinstance(raw_code, str):
        return None
    raw = strip0x(raw_code).lower()
    if not raw or len(raw) % 2:
        return None
    try:
        return keccak256_hex(bytes.fromhex(raw))
    except ValueError:
        return None


_LIFECYCLE_BY_INDEX: Mapping[int, str] = MappingProxyType(
    {0: "pending", 1: "funding", 2: "pulling", 3: "finalized"}
)


def lifecycle_name(value: int | None) -> str:
    """Map the source enum without inventing a state for a bad read."""

    if isinstance(value, bool) or not isinstance(value, int):
        return "unknown"
    return _LIFECYCLE_BY_INDEX.get(value, "unknown")


def gross_recovery_pct(campaign: MegaRipCampaignState) -> float | None:
    """Final pot divided by deposits, only after the campaign finalized."""

    if (
        lifecycle_name(campaign.lifecycle_index) != "finalized"
        or campaign.pot_wei is None
        or campaign.total_deposited_wei is None
        or campaign.total_deposited_wei == 0
    ):
        return None
    return campaign.pot_wei * 100.0 / campaign.total_deposited_wei


def _whole_tokens(value: int | None) -> float | None:
    return None if value is None else value / _WEI_PER_TOKEN


def _compact_tokens(value: int | None, unit: str) -> str:
    if value is None:
        return f"n/a {unit}"
    rendered = f"{value / _WEI_PER_TOKEN:.6f}".rstrip("0").rstrip(".")
    return f"{rendered or '0'} {unit}"


def _source_badge(campaign: MegaRipCampaignState) -> str:
    if campaign.integrity == "mismatch":
        return "INTEGRITY"
    if not campaign.semantic_available or campaign.integrity != "ok":
        return "DEGRADED"
    return "VERIFIED" if campaign.source_verified else "CHAIN-READ"


def _campaign_detail(campaign: MegaRipCampaignState) -> str:
    if campaign.integrity == "mismatch":
        return "runtime/dependency/accounting mismatch · semantics suppressed"
    if not campaign.semantic_available:
        return "chain state unavailable"

    parts: list[str] = []
    if campaign.depositor_count is not None:
        parts.append(f"{campaign.depositor_count} depositors")
    if campaign.pulls_done is not None:
        parts.append(f"{campaign.pulls_done} pulls")
    if lifecycle_name(campaign.lifecycle_index) == "finalized":
        parts.append(f"final pot {_compact_tokens(campaign.pot_wei, 'ETH')}")
        parts.append(
            "ETH claims "
            + _compact_tokens(campaign.eth_claims_outstanding_wei, "ETH")
        )
    if campaign.version != "v1":
        if campaign.fwa_received_wei == 0:
            parts.append("no FWA distributed")
        if campaign.fwa_distributor is False:
            parts.append("distributor disabled")
        elif campaign.fwa_distributor is None:
            parts.append("distributor status unavailable")
    if not campaign.source_verified:
        parts.append("source unverified")
    if campaign.issues:
        parts.append("partial chain read")
    return " · ".join(parts) or "chain state"


def campaign_row(campaign: MegaRipCampaignState) -> ProjectRow:
    """Convert one strict campaign snapshot at the presentation boundary."""

    legacy_liability = not campaign.is_current and bool(
        (campaign.accounted_eth_wei or 0) > 0
        or (campaign.fwa_outstanding_wei or 0) > 0
    )
    return ProjectRow(
        family="megarip",
        surface="campaign",
        version=campaign.version,
        address=campaign.address,
        is_current=campaign.is_current,
        is_legacy_liability=legacy_liability,
        lifecycle=lifecycle_name(campaign.lifecycle_index),
        primary_label="GROSS RECOVERY",
        primary_value=gross_recovery_pct(campaign),
        primary_unit="recovery_pct",
        eth_label="ACCOUNTED ETH",
        eth_value=_whole_tokens(campaign.accounted_eth_wei),
        fwa_label="OUTSTANDING FWA",
        fwa_value=_whole_tokens(campaign.fwa_outstanding_wei),
        detail=_campaign_detail(campaign),
        source_badge=_source_badge(campaign),
        source_kind="chain_state",
        measurement="derived",
        block_number=campaign.block_number,
        observed_at=campaign.observed_at,
        stale=False,
        verified_source=campaign.source_verified,
        integrity=campaign.integrity,
    )


def project_rows(campaigns: Sequence[MegaRipCampaignState]) -> tuple[ProjectRow, ...]:
    """Current first, then only visible legacy liabilities/integrity rows."""

    by_version = {campaign.version: campaign for campaign in campaigns}
    ordered = [
        *(by_version[version] for version in ("v3", "v1", "v2") if version in by_version)
    ]
    rows: list[ProjectRow] = []
    for campaign in ordered:
        row = campaign_row(campaign)
        if campaign.is_current or row.is_legacy_liability or row.integrity != "ok":
            rows.append(row)
    return tuple(rows)


def _suppressed_campaign(
    manifest: ProjectManifest,
    *,
    block_number: int,
    observed_at: float,
    actual_codehash: str | None,
    dependency_reads: tuple[tuple[str, str | None], ...],
    integrity: Literal["mismatch", "unknown"],
    issues: tuple[str, ...],
) -> MegaRipCampaignState:
    return MegaRipCampaignState(
        version=manifest.version,
        address=manifest.address,
        is_current=manifest.is_current,
        source_verified=manifest.source_status == "verified",
        observed_at=observed_at,
        block_number=block_number,
        semantic_available=False,
        integrity=integrity,
        actual_codehash=actual_codehash,
        dependency_reads=dependency_reads,
        issues=issues,
    )


def _aggregate_integrity(campaigns: Sequence[MegaRipCampaignState]) -> Integrity:
    statuses = {campaign.integrity for campaign in campaigns}
    if "mismatch" in statuses:
        return "mismatch"
    if "unknown" in statuses:
        return "unknown"
    if "warning" in statuses:
        return "warning"
    return "ok"


# ---------------------------------------------------------------------------
# Static event normalization
# ---------------------------------------------------------------------------


_EVENT_PRESENTATION: Mapping[str, tuple[str, str, str | None, str | None]] = (
    MappingProxyType(
        {
            "Scheduled": ("scheduled", "Scheduled", None, None),
            "Opened": ("funding_opened", "Funding opened", None, None),
            "Deposited": ("funded", "Funded", "eth", "amount"),
            "Withdrawn": ("funding_withdrawn", "Funding withdrawn", "eth", "amount"),
            "Locked": ("locked", "Locked", "eth", "total"),
            "PullRequested": ("pull_requested", "Pull requested", "eth", "fee"),
            "Allocated": ("allocated", "Allocated", "eth", "backing"),
            "BidPlaced": ("bid_placed", "Bid placed", "eth", "amount"),
            "AuctionExtended": ("auction_extended", "Auction extended", None, None),
            "AuctionSettled": ("auction_settled", "Auction settled", "eth", "price"),
            "WinnerUndeliverable": (
                "winner_undeliverable",
                "Winner undeliverable",
                "eth",
                "refund",
            ),
            "RefundCredited": ("refund_credited", "Refund credited", "eth", "amount"),
            "RefundWithdrawn": ("refund_withdrawn", "Refund withdrawn", "eth", "amount"),
            "StuckSold": ("stuck_sold", "Stuck NFT sold", "eth", "price"),
            "SettledBid": ("settled", "Settled bid", "eth", "proceeds"),
            "RewardsClaimed": ("rewards_claimed", "Rewards claimed", "fwa", "amount"),
            "RewardsSold": ("rewards_sold", "Rewards sold", "eth", "eth"),
            "FwaClaimed": ("fwa_claimed", "FWA claimed", "fwa", "amount"),
            "Finalized": ("finalized", "Finalized", "eth", "pot"),
            "Claimed": ("claimed", "ETH claimed", "eth", "amount"),
            "AcquisitionVoided": (
                "acquisition_voided",
                "Acquisition voided",
                None,
                None,
            ),
            "ForcedNftCustody": (
                "forced_nft_custody",
                "Forced NFT custody",
                "eth",
                "price",
            ),
            "ForcedBidRecovered": (
                "forced_bid_recovered",
                "Forced bid recovered",
                None,
                None,
            ),
            "StuckExpired": ("stuck_expired", "Stuck NFT expired", None, None),
            "BountyPaid": ("bounty_paid", "Bounty paid", "eth", "amount"),
            "StrayAbsorbed": ("stray_absorbed", "Stray ETH absorbed", "eth", "amount"),
            "KeeperBountiesSet": (
                "keeper_bounties_set",
                "Keeper bounties set",
                None,
                None,
            ),
        }
    )
)


def _quantity(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if not isinstance(raw, str):
        return None
    try:
        value = int(raw, 16 if raw.startswith(("0x", "0X")) else 10)
    except ValueError:
        return None
    return value if value >= 0 else None


def _event_value(type_name: str, word: str) -> int | bool | str | None:
    raw = "0x" + word
    if type_name == "address":
        return _address(raw)
    if type_name == "bool":
        return _bool(raw)
    if type_name.startswith("uint"):
        return _uint(raw)
    return None


def _event_timestamp(raw: Mapping[str, Any]) -> int | float | None:
    for key in ("blockTimestamp", "timestamp", "ts"):
        value = raw.get(key)
        if isinstance(value, float) and math.isfinite(value) and value >= 0:
            return value
        parsed = _quantity(value)
        if parsed is not None:
            return parsed
    return None


def _event_detail(values: Mapping[str, Any], amount_field: str | None) -> str:
    parts: list[str] = []
    for key, value in values.items():
        if key == amount_field:
            continue
        if isinstance(value, str) and _ADDRESS_RE.fullmatch(value):
            parts.append(f"{key} {value[:8]}…{value[-4:]}")
        elif isinstance(value, bool):
            parts.append(f"{key} {'yes' if value else 'no'}")
        elif isinstance(value, int):
            parts.append(f"{key} {value}")
    return " · ".join(parts)


def _normalize_event(
    manifest: ProjectManifest,
    raw: Mapping[str, Any],
    *,
    observed_at: float,
    from_block: int,
    to_block: int,
) -> NetworkEventRow | None:
    if raw.get("removed") is True:
        return None
    raw_address = str(raw.get("address", "")).lower()
    if (
        not _ADDRESS_RE.fullmatch(raw_address)
        or raw_address != manifest.address
    ):
        return None
    topics = raw.get("topics")
    data = raw.get("data")
    if not isinstance(topics, list) or not topics or not isinstance(data, str):
        return None
    topic0 = str(topics[0]).lower()
    entries = _EVENT_ABI_BY_VERSION[manifest.version]
    entry = next(
        (
            candidate
            for candidate in entries
            if EVENT_TOPICS_BY_VERSION[manifest.version].get(str(candidate["name"]))
            == topic0
        ),
        None,
    )
    if entry is None:
        return None

    inputs = entry.get("inputs")
    if not isinstance(inputs, list):
        return None
    indexed = [item for item in inputs if item.get("indexed") is True]
    plain = [item for item in inputs if item.get("indexed") is not True]
    if len(topics) != 1 + len(indexed):
        return None
    data_raw = strip0x(data).lower()
    if len(data_raw) != len(plain) * 64:
        return None
    try:
        bytes.fromhex(data_raw)
    except ValueError:
        return None

    values: dict[str, Any] = {}
    topic_index = 1
    data_index = 0
    for item in inputs:
        type_name = item.get("type")
        name = item.get("name")
        if not isinstance(type_name, str) or not isinstance(name, str):
            return None
        if item.get("indexed") is True:
            topic = strip0x(str(topics[topic_index])).lower()
            topic_index += 1
            if len(topic) != 64:
                return None
            word = topic
        else:
            word = data_raw[data_index * 64 : (data_index + 1) * 64]
            data_index += 1
        value = _event_value(type_name, word)
        if value is None:
            return None
        values[name] = value

    tx_hash = str(raw.get("transactionHash", "")).lower()
    block_number = _quantity(raw.get("blockNumber"))
    log_index = _quantity(raw.get("logIndex"))
    if (
        not _TX_HASH_RE.fullmatch(tx_hash)
        or block_number is None
        or log_index is None
        or block_number < from_block
        or block_number > to_block
    ):
        return None

    event_name = str(entry["name"])
    event_key, event_label, amount_unit, amount_field = _EVENT_PRESENTATION.get(
        event_name,
        (event_name.lower(), event_name, None, None),
    )
    amount = values.get(amount_field) if amount_field is not None else None
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int)):
        return None
    eth_amount = _whole_tokens(amount) if amount_unit == "eth" else None
    fwa_amount = _whole_tokens(amount) if amount_unit == "fwa" else None
    event_id = f"1:{manifest.address}:{tx_hash}:{log_index}"
    return NetworkEventRow(
        event_id=event_id,
        ts=_event_timestamp(raw),
        tx_hash=tx_hash,
        log_index=log_index,
        origin=manifest.address,
        family="megarip",
        version=manifest.version,
        event_key=event_key,
        event_label=event_label,
        eth_amount=eth_amount,
        fwa_amount=fwa_amount,
        detail=_event_detail(values, amount_field),
        source_kind="chain_log",
        measurement="measured",
        block_number=block_number,
        observed_at=observed_at,
        stale=False,
        verified_source=manifest.source_status == "verified",
        integrity="ok",
    )


def normalize_events(
    manifest: ProjectManifest,
    raw_logs: Sequence[Any],
    *,
    observed_at: float,
    from_block: int,
    to_block: int,
) -> tuple[tuple[NetworkEventRow, ...], int]:
    """Normalize/dedupe one page; count malformed rows for watermark safety."""

    rows: dict[str, NetworkEventRow] = {}
    failures = 0
    for raw in raw_logs:
        if not isinstance(raw, Mapping):
            failures += 1
            continue
        row = _normalize_event(
            manifest,
            raw,
            observed_at=observed_at,
            from_block=from_block,
            to_block=to_block,
        )
        if row is None:
            failures += 1
            continue
        rows[row.event_id] = row
    return (
        tuple(
            sorted(
                rows.values(),
                key=lambda row: (row.block_number or 0, row.log_index),
                reverse=True,
            )
        ),
        failures,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MegaRipAdapter(FWAClient):
    """Read all MegaRip generations without keys, signing, or mutations."""

    def __init__(
        self,
        *args: Any,
        clock: Callable[[], float] = time.time,
        log_endpoints: Sequence[str] | None = None,
        log_http_client: httpx.AsyncClient | None = None,
        log_min_call_interval: float = 0.05,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._megarip_clock = clock
        self._log_endpoints = tuple(log_endpoints) if log_endpoints is not None else None
        self._log_http_client = log_http_client
        self._log_min_call_interval = log_min_call_interval
        self._version_logs: dict[str, FWALogClient] = {}

    def _observed_at(self) -> float:
        value = self._megarip_clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("MegaRip clock must return epoch seconds")
        observed = float(value)
        if not math.isfinite(observed) or observed < 0:
            raise ValueError("MegaRip clock must return finite epoch seconds")
        return observed

    @staticmethod
    def _validate_block(value: int | None, *, label: str) -> None:
        if isinstance(value, bool) or (
            value is not None and (not isinstance(value, int) or value < 0)
        ):
            raise ValueError(f"{label} must be a non-negative int or None")

    @staticmethod
    def _validate_required_block(value: Any, *, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative int")

    async def close(self) -> None:
        for client in self._version_logs.values():
            await client.close()
        self._version_logs.clear()
        await super().close()

    def _log_client(self, manifest: ProjectManifest) -> FWALogClient:
        client = self._version_logs.get(manifest.version)
        if client is None:
            client = FWALogClient(
                endpoints=self._log_endpoints,
                http_client=self._log_http_client,
                core_address=manifest.address,
                min_call_interval=self._log_min_call_interval,
            )
            self._version_logs[manifest.version] = client
        return client

    async def _codehash(self, manifest: ProjectManifest, block_tag: str) -> str | None:
        try:
            raw = await self._rpc("eth_getCode", [manifest.address, block_tag])
        except Exception as exc:  # noqa: BLE001 - isolate one generation
            logger.warning("MegaRip %s code read failed: %s", manifest.version, exc)
            return None
        return runtime_codehash(raw)

    async def fetch_state(
        self, *, block_number: int | None = None
    ) -> MegaRipStateRead:
        """Read and validate v1-v3 at exactly one block tag."""

        self._validate_block(block_number, label="block_number")
        observed_at = self._observed_at()
        state_block = block_number
        if state_block is None:
            fetched = await self.fetch_block_number()
            state_block = fetched if fetched > 0 else None
        if state_block is None:
            return MegaRipStateRead(
                observed_at=observed_at,
                state_block=None,
                chain_head=None,
                available=False,
                integrity="unknown",
                campaigns=(),
                rows=(),
                issues=("state_block_unavailable",),
            )

        block_tag = hex(state_block)
        codehashes: dict[str, str | None] = {}
        for manifest in MEGARIP_MANIFESTS:
            codehashes[manifest.version] = await self._codehash(manifest, block_tag)

        calls: list[tuple[str, str]] = []
        slices: dict[str, tuple[int, tuple[str, ...]]] = {}
        for manifest in MEGARIP_MANIFESTS:
            names = tuple(STATE_SELECTORS_BY_VERSION[manifest.version])
            start = len(calls)
            calls.extend(
                (
                    manifest.address,
                    STATE_SELECTORS_BY_VERSION[manifest.version][name],
                )
                for name in names
            )
            if manifest.version != "v1":
                token_address = dict(manifest.dependencies)["FWA_TOKEN"]
                calls.append(
                    (
                        token_address,
                        TOKEN_IS_DISTRIBUTOR_SELECTOR
                        + encode_address(manifest.address),
                    )
                )
                names = (*names, "isDistributor")
            slices[manifest.version] = (start, names)

        results = await self._multicall(calls, block_tag)
        campaigns: list[MegaRipCampaignState] = []
        aggregate_issues: list[str] = []

        for manifest in MEGARIP_MANIFESTS:
            start, names = slices[manifest.version]
            raw_by_name = {
                name: _successful(
                    results[start + index]
                    if start + index < len(results)
                    else None
                )
                for index, name in enumerate(names)
            }
            dependency_reads = tuple(
                (getter, _address(raw_by_name.get(getter)))
                for getter, _expected in manifest.dependencies
            )
            issues: list[str] = []
            actual_hash = codehashes[manifest.version]
            if actual_hash is None:
                issues.append("runtime_code_unavailable")
            elif actual_hash != manifest.runtime_codehash:
                issues.append("runtime_codehash_mismatch")

            unknown_dependencies = [
                getter for getter, value in dependency_reads if value is None
            ]
            mismatched_dependencies = [
                getter
                for (getter, expected), (_read_getter, value) in zip(
                    manifest.dependencies, dependency_reads, strict=True
                )
                if value is not None and value != expected
            ]
            issues.extend(
                f"{getter}_dependency_unavailable"
                for getter in unknown_dependencies
            )
            issues.extend(
                f"{getter}_dependency_mismatch"
                for getter in mismatched_dependencies
            )

            mismatch = (
                actual_hash is not None
                and actual_hash != manifest.runtime_codehash
            ) or bool(mismatched_dependencies)
            unknown_integrity = actual_hash is None or bool(unknown_dependencies)
            if mismatch or unknown_integrity:
                integrity: Literal["mismatch", "unknown"] = (
                    "mismatch" if mismatch else "unknown"
                )
                campaign = _suppressed_campaign(
                    manifest,
                    block_number=state_block,
                    observed_at=observed_at,
                    actual_codehash=actual_hash,
                    dependency_reads=dependency_reads,
                    integrity=integrity,
                    issues=tuple(issues),
                )
                campaigns.append(campaign)
                aggregate_issues.extend(
                    f"{manifest.version}:{issue}" for issue in issues
                )
                continue

            lifecycle = _uint(raw_by_name.get("state"))
            total_deposited = _uint(raw_by_name.get("totalDeposited"))
            depositor_count = _uint(raw_by_name.get("depositorCount"))
            pulls_done = _uint(raw_by_name.get("pullsDone"))
            pot = _uint(raw_by_name.get("pot"))
            total_paid = _uint(raw_by_name.get("totalPaid"))
            pot_remaining_read = _uint(raw_by_name.get("potRemaining"))
            accounted_eth = _uint(raw_by_name.get("accountedEth"))
            acquisition_spend = _uint(raw_by_name.get("acquisitionSpend"))
            pull_budget = _uint(raw_by_name.get("pullBudget"))
            bounty_reserve = _uint(raw_by_name.get("bountyReserve"))
            auction_escrow = _uint(raw_by_name.get("auctionEscrow"))
            pending_refunds = _uint(raw_by_name.get("pendingRefundTotal"))
            active_count = _uint(raw_by_name.get("activeCount"))
            fwa_received = _uint(raw_by_name.get("fwaReceived"))
            fwa_total_paid = _uint(raw_by_name.get("fwaTotalPaid"))
            fwa_operator = _uint(raw_by_name.get("fwaOperatorClaimable"))
            fwa_distributor = _bool(raw_by_name.get("isDistributor"))

            required = {
                "state": lifecycle,
                "totalDeposited": total_deposited,
                "depositorCount": depositor_count,
                "pullsDone": pulls_done,
                "pot": pot,
                "totalPaid": total_paid,
                "potRemaining": pot_remaining_read,
                "accountedEth": accounted_eth,
                "acquisitionSpend": acquisition_spend,
                "pullBudget": pull_budget,
                "bountyReserve": bounty_reserve,
                "auctionEscrow": auction_escrow,
                "pendingRefundTotal": pending_refunds,
                "activeCount": active_count,
            }
            if manifest.version != "v1":
                required.update(
                    {
                        "fwaReceived": fwa_received,
                        "fwaTotalPaid": fwa_total_paid,
                        "fwaOperatorClaimable": fwa_operator,
                        "isDistributor": fwa_distributor,
                    }
                )
            issues.extend(
                f"{name}_unavailable"
                for name, value in required.items()
                if value is None
            )

            claims_outstanding = (
                pot - total_paid
                if pot is not None and total_paid is not None and pot >= total_paid
                else None
            )
            fwa_outstanding = (
                fwa_received - fwa_total_paid
                if fwa_received is not None
                and fwa_total_paid is not None
                and fwa_received >= fwa_total_paid
                else None
            )

            invariant_issues: list[str] = []
            if lifecycle is not None and lifecycle not in _LIFECYCLE_BY_INDEX:
                invariant_issues.append("lifecycle_out_of_range")
            if pot is not None and total_paid is not None and pot < total_paid:
                invariant_issues.append("paid_exceeds_pot")
            if (
                claims_outstanding is not None
                and pot_remaining_read is not None
                and claims_outstanding != pot_remaining_read
            ):
                invariant_issues.append("pot_remaining_mismatch")
            if (
                total_deposited is not None
                and acquisition_spend is not None
                and acquisition_spend > total_deposited
            ):
                invariant_issues.append("acquisition_spend_exceeds_deposits")
            if (
                fwa_received is not None
                and fwa_total_paid is not None
                and fwa_received < fwa_total_paid
            ):
                invariant_issues.append("fwa_paid_exceeds_received")
            if lifecycle in {0, 1}:
                budget_liability = total_deposited
            elif lifecycle in {2, 3}:
                budget_liability = pull_budget
            else:
                # Without the lifecycle read we cannot know whether deposits
                # or pullBudget is the active ledger bucket.  Keep the
                # invariant unavailable instead of manufacturing a mismatch.
                budget_liability = None
            ledger_parts = (
                budget_liability,
                bounty_reserve,
                auction_escrow,
                pending_refunds,
                claims_outstanding,
            )
            if (
                accounted_eth is not None
                and all(value is not None for value in ledger_parts)
                and accounted_eth != sum(value for value in ledger_parts if value is not None)
            ):
                invariant_issues.append("accounted_eth_ledger_mismatch")

            if invariant_issues:
                issues.extend(invariant_issues)
                campaign = _suppressed_campaign(
                    manifest,
                    block_number=state_block,
                    observed_at=observed_at,
                    actual_codehash=actual_hash,
                    dependency_reads=dependency_reads,
                    integrity="mismatch",
                    issues=tuple(issues),
                )
            else:
                campaign = MegaRipCampaignState(
                    version=manifest.version,
                    address=manifest.address,
                    is_current=manifest.is_current,
                    source_verified=manifest.source_status == "verified",
                    observed_at=observed_at,
                    block_number=state_block,
                    semantic_available=True,
                    integrity="warning" if issues else "ok",
                    actual_codehash=actual_hash,
                    dependency_reads=dependency_reads,
                    lifecycle_index=lifecycle,
                    total_deposited_wei=total_deposited,
                    depositor_count=depositor_count,
                    pulls_done=pulls_done,
                    pot_wei=pot,
                    total_paid_wei=total_paid,
                    eth_claims_outstanding_wei=claims_outstanding,
                    accounted_eth_wei=accounted_eth,
                    acquisition_spend_wei=acquisition_spend,
                    pull_budget_wei=pull_budget,
                    bounty_reserve_wei=bounty_reserve,
                    auction_escrow_wei=auction_escrow,
                    pending_refund_total_wei=pending_refunds,
                    active_count=active_count,
                    fwa_received_wei=fwa_received,
                    fwa_total_paid_wei=fwa_total_paid,
                    fwa_outstanding_wei=fwa_outstanding,
                    fwa_operator_claimable_wei=fwa_operator,
                    fwa_distributor=fwa_distributor,
                    issues=tuple(issues),
                )
            campaigns.append(campaign)
            aggregate_issues.extend(
                f"{manifest.version}:{issue}" for issue in issues
            )

        campaign_tuple = tuple(campaigns)
        rows = project_rows(campaign_tuple)
        current = next(
            (campaign for campaign in campaign_tuple if campaign.is_current),
            None,
        )
        return MegaRipStateRead(
            observed_at=observed_at,
            state_block=state_block,
            chain_head=state_block,
            available=bool(current and current.semantic_available),
            integrity=_aggregate_integrity(campaign_tuple),
            campaigns=campaign_tuple,
            rows=rows,
            issues=tuple(aggregate_issues),
        )

    async def _block_hash(self, block_number: int) -> str | None:
        try:
            raw = await self._rpc(
                "eth_getBlockByNumber", [hex(block_number), False]
            )
        except Exception as exc:  # noqa: BLE001 - prevents unsafe watermark only
            logger.warning("MegaRip watermark block read failed: %s", exc)
            return None
        if not isinstance(raw, Mapping):
            return None
        block_hash = str(raw.get("hash", "")).lower()
        return block_hash if _BYTES32_RE.fullmatch(block_hash) else None

    async def fetch_events(
        self,
        version: str,
        *,
        from_block: int,
        to_block: int,
        history_complete: bool = False,
    ) -> MegaRipEventRead:
        """Read one versioned log page and expose safe watermark inputs."""

        if version not in _MANIFEST_BY_VERSION:
            raise ValueError(f"unknown MegaRip version: {version!r}")
        self._validate_required_block(from_block, label="from_block")
        self._validate_required_block(to_block, label="to_block")
        if not isinstance(history_complete, bool):
            raise ValueError("history_complete must be bool")
        observed_at = self._observed_at()
        manifest = _MANIFEST_BY_VERSION[version]
        effective_from = max(from_block, manifest.deployment_block)
        complete_history = history_complete or effective_from == manifest.deployment_block

        if effective_from > to_block:
            block_hash = await self._block_hash(to_block)
            page_complete = block_hash is not None
            return MegaRipEventRead(
                observed_at=observed_at,
                version=version,
                from_block=effective_from,
                to_block=to_block,
                available=True,
                history_complete=complete_history and page_complete,
                page_complete=page_complete,
                last_complete_block=to_block if page_complete else None,
                last_complete_block_hash=block_hash,
                events=(),
                unavailable_reason=None,
                issues=(
                    ()
                    if page_complete
                    else ("watermark_block_hash_unavailable",)
                ),
            )

        topics = [list(EVENT_TOPICS_BY_VERSION[version].values())]
        client = self._log_client(manifest)
        try:
            raw_logs = await client.get_logs(topics, effective_from, to_block)
        except Exception as exc:  # noqa: BLE001 - Pool B degrades independently
            logger.warning("MegaRip %s logs unavailable: %s", version, exc)
            return MegaRipEventRead(
                observed_at=observed_at,
                version=version,
                from_block=effective_from,
                to_block=to_block,
                available=False,
                history_complete=False,
                page_complete=False,
                last_complete_block=None,
                last_complete_block_hash=None,
                events=(),
                unavailable_reason="MegaRip logs unavailable",
                issues=("logs_unavailable",),
            )

        events, decode_failures = normalize_events(
            manifest,
            raw_logs,
            observed_at=observed_at,
            from_block=effective_from,
            to_block=to_block,
        )
        issues: list[str] = []
        if decode_failures:
            issues.append(f"{decode_failures}_event_decode_failed")
        block_hash = await self._block_hash(to_block)
        if block_hash is None:
            issues.append("watermark_block_hash_unavailable")
        page_complete = not issues
        return MegaRipEventRead(
            observed_at=observed_at,
            version=version,
            from_block=effective_from,
            to_block=to_block,
            available=True,
            history_complete=complete_history and page_complete,
            page_complete=page_complete,
            last_complete_block=to_block if page_complete else None,
            last_complete_block_hash=block_hash if page_complete else None,
            events=events,
            unavailable_reason=None,
            issues=tuple(issues),
        )


# Import-time contract checks catch accidental row/model drift immediately.
assert tuple(ProjectRow.model_fields) == PROJECT_ROW_KEYS
assert tuple(NetworkEventRow.model_fields) == NETWORK_EVENT_ROW_KEYS
assert tuple(_MANIFEST_BY_VERSION) == ("v1", "v2", "v3")


__all__ = [
    "EVENT_TOPICS_BY_VERSION",
    "MEGARIP_MANIFESTS",
    "STATE_SELECTORS_BY_VERSION",
    "TOKEN_IS_DISTRIBUTOR_SELECTOR",
    "MegaRipAdapter",
    "MegaRipCampaignState",
    "MegaRipEventRead",
    "MegaRipStateRead",
    "campaign_row",
    "gross_recovery_pct",
    "lifecycle_name",
    "normalize_events",
    "project_rows",
    "runtime_codehash",
]
