"""Read-only PullPool, GroupPull, and order-factory adapter.

The adapter has two deliberately separate paths:

* state uses the existing hardened FWA Pool-A client and pins every call to an
  explicit block;
* history uses the existing archive-capable Pool-B log client, bounded pages,
  and cache-compatible :class:`WatermarkKey` identities.

All internal amounts remain strict integer wei.  ETH/FWA floats appear only in
``build_project_rows`` and ``normalize_events``, the frozen presentation
boundary consumed by NETWORK widgets.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.evm_abi import (
    decode_address,
    encode_address,
    encode_uint,
    strip0x,
)
from maxpane_dashboard.data.fwa_client import FWAClient
from maxpane_dashboard.data.fwa_ecosystem_addresses import FWA_TOKEN
from maxpane_dashboard.data.fwa_ecosystem_cache import (
    FWAEcosystemCache,
    MAX_REORG_OVERLAP,
    Watermark,
    WatermarkKey,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
    NetworkEventRow,
    ProjectRow,
)
from maxpane_dashboard.data.fwa_logs import FWALogClient, LOG_ENDPOINTS
from maxpane_dashboard.data.fwa_models import Wei
from maxpane_dashboard.data.keccak import keccak256_hex

from .base import ProjectManifest, load_manifest_abi
from .registry import GROUP_PULL, get_project_manifest

logger = logging.getLogger(__name__)

_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True)
_WEI_PER_TOKEN = 10**18
_DEFAULT_PAGE_SIZE = 5_000
_DEFAULT_MAX_PAGES = 2
_DEFAULT_OVERLAP = 12
_MAX_ROUNDS = 10_000

PullPoolLifecycle = Literal[
    "open", "pulling", "claimable", "settled", "refunding", "unknown"
]
GroupPullLifecycle = Literal[
    "selling", "buying", "collecting", "distributing", "expired", "unknown"
]
IntegrityStatus = Literal["ok", "warning", "mismatch", "unknown"]

PULLPOOL_STATE_NAMES: tuple[PullPoolLifecycle, ...] = (
    "unknown",
    "open",
    "pulling",
    "claimable",
    "settled",
    "refunding",
)
GROUP_PULL_STATE_NAMES: tuple[GroupPullLifecycle, ...] = (
    "unknown",
    "selling",
    "buying",
    "collecting",
    "distributing",
    "expired",
)


def _selector(signature: str) -> str:
    return keccak256_hex(signature.encode("ascii"))[:10]


SEL_ROUND_COUNT = _selector("roundCount()")
SEL_ACCOUNTED_ETH = _selector("accountedEth()")
SEL_DEPRECATED = _selector("deprecated()")
SEL_PAUSED = _selector("paused()")
SEL_CURRENT_OPEN_ROUND = _selector("currentOpenRound()")
SEL_PENDING_PULL_COUNT = _selector("pendingPullCount()")
SEL_CAN_PAY_TOKENS = _selector("canPayTokens()")
SEL_FWA_ACCOUNTED = _selector("fwaAccounted()")
SEL_LIVE_ROUND = _selector("liveRound()")
SEL_BUYING_ROUNDS = _selector("buyingRounds()")
SEL_ORDER_COUNT = _selector("orderCount()")
SEL_BALANCE_OF = _selector("balanceOf(address)")
SEL_IS_DISTRIBUTOR = _selector("isDistributor(address)")
SEL_GET_ROUND = _selector("getRound(uint256)")


def _manifest(family: str, surface: str, version: str, role: str) -> ProjectManifest:
    return get_project_manifest(family, surface, version, role)


PULLPOOL_MANIFESTS: tuple[ProjectManifest, ...] = (
    _manifest("pullpool", "pullpool", "v1", "pool"),
    _manifest("pullpool", "pullpool", "v2", "pool"),
)
GROUP_PULL_MANIFEST = _manifest("group_pull", "group_pull", "v1", "pool")
ORDER_MANIFESTS: tuple[ProjectManifest, ...] = (
    _manifest("standing_orders", "standing_orders", "v1", "factory"),
    _manifest("standing_orders", "standing_orders", "v2", "factory"),
    _manifest("group_pull", "group_orders", "v1", "factory"),
)
ALL_MANIFESTS: tuple[ProjectManifest, ...] = (
    *PULLPOOL_MANIFESTS,
    GROUP_PULL_MANIFEST,
    *ORDER_MANIFESTS,
)


def _manifest_key(manifest: ProjectManifest) -> str:
    return f"{manifest.family}:{manifest.surface}:{manifest.version}"


def _abi_entry(manifest: ProjectManifest, kind: str, name: str) -> dict[str, Any]:
    matches = [
        entry
        for entry in load_manifest_abi(manifest)
        if entry.get("type") == kind and entry.get("name") == name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{manifest.abi_resource} must contain exactly one {kind} {name}"
        )
    return matches[0]


def _round_component_indices(manifest: ProjectManifest) -> dict[str, int]:
    entry = _abi_entry(manifest, "function", "getRound")
    outputs = entry.get("outputs") or []
    components = outputs[0].get("components") if outputs else None
    if not isinstance(components, list):
        raise ValueError(f"{manifest.abi_resource} getRound has no tuple output")
    return {
        str(component.get("name")): index
        for index, component in enumerate(components)
    }


_PULL_ROUND_INDEX = {
    manifest.version: _round_component_indices(manifest)
    for manifest in PULLPOOL_MANIFESTS
}
_GROUP_ROUND_INDEX = _round_component_indices(GROUP_PULL_MANIFEST)


class PullPoolRoundState(BaseModel):
    model_config = _STRICT

    round_id: int
    state: int
    lifecycle: PullPoolLifecycle
    tickets_sold: int
    max_tickets: int
    escrow_wei: Wei
    fee_owed_wei: Wei
    refund_pool_wei: Wei
    eth_pot_wei: Wei
    token_pot_wei: Wei
    referral_pool_wei: Wei


class GroupPullRoundState(BaseModel):
    model_config = _STRICT

    round_id: int
    state: int
    lifecycle: GroupPullLifecycle
    tickets_sold: int
    escrow_wei: Wei
    eth_pool_wei: Wei
    eth_paid_wei: Wei
    fwa_pot_wei: Wei
    fwa_paid_wei: Wei
    aborted: bool


class PullPoolSurfaceState(BaseModel):
    model_config = _STRICT

    version: str
    address: str
    is_current: bool
    observed_at: float
    block_number: int
    available: bool
    round_count: int | None
    accounted_eth_wei: Wei | None
    token_balance_wei: Wei | None
    distributor_enabled: bool | None
    can_pay_tokens: bool | None
    paused: bool | None
    deprecated: bool | None
    current_open_round: int | None
    pending_pull_count: int | None
    rounds: tuple[PullPoolRoundState, ...]
    failed_fields: tuple[str, ...]


class GroupPullSurfaceState(BaseModel):
    model_config = _STRICT

    version: str
    address: str
    observed_at: float
    block_number: int
    available: bool
    round_count: int | None
    accounted_eth_wei: Wei | None
    accounted_fwa_wei: Wei | None
    token_balance_wei: Wei | None
    distributor_enabled: bool | None
    paused: bool | None
    deprecated: bool | None
    live_round: int | None
    buying_rounds: int | None
    rounds: tuple[GroupPullRoundState, ...]
    failed_fields: tuple[str, ...]


class OrderFactoryState(BaseModel):
    model_config = _STRICT

    family: str
    surface: str
    version: str
    address: str
    is_current: bool
    observed_at: float
    block_number: int
    available: bool
    orders_created: int | None
    failed_fields: tuple[str, ...]


class PullPoolRead(BaseModel):
    """All WP-05 state surfaces at one explicit Ethereum block."""

    model_config = _STRICT

    observed_at: float
    block_number: int
    pullpools: tuple[PullPoolSurfaceState, ...]
    group_pull: GroupPullSurfaceState
    order_factories: tuple[OrderFactoryState, ...]


class SurfaceIntegrity(BaseModel):
    model_config = _STRICT

    surface_key: str
    address: str
    block_number: int
    codehash_match: bool | None
    dependency_matches: tuple[tuple[str, bool | None], ...]
    status: IntegrityStatus


class PullPoolIntegrityRead(BaseModel):
    model_config = _STRICT

    observed_at: float
    block_number: int
    surfaces: tuple[SurfaceIntegrity, ...]

    def status_for(self, manifest: ProjectManifest) -> IntegrityStatus:
        key = _manifest_key(manifest)
        for surface in self.surfaces:
            if surface.surface_key == key:
                return surface.status
        return "unknown"


class PullPoolEvent(BaseModel):
    """One decoded project log before whole-token presentation conversion."""

    model_config = _STRICT

    address: str
    family: str
    surface: str
    version: str
    event_key: str
    event_label: str
    block_number: int
    block_timestamp: int | None
    tx_hash: str
    log_index: int
    round_id: int | None
    eth_amount_wei: Wei | None
    fwa_amount_wei: Wei | None
    detail: str

    @property
    def event_id(self) -> str:
        return f"1:{self.address.lower()}:{self.tx_hash.lower()}:{self.log_index}"


class LogProgress(BaseModel):
    model_config = _STRICT

    adapter: str
    version: str
    topic_group: str
    from_block: int
    to_block: int
    last_block_hash: str | None
    page_complete: bool
    overlap: int

    @property
    def watermark_key(self) -> WatermarkKey:
        return WatermarkKey(
            adapter=self.adapter,
            version=self.version,
            topic_group=self.topic_group,
        )


class PullPoolLogRead(BaseModel):
    model_config = _STRICT

    observed_at: float
    requested_from_block: int
    requested_to_block: int
    available: bool
    history_complete: bool
    history_complete_versions: tuple[str, ...]
    failed_streams: tuple[str, ...]
    events: tuple[PullPoolEvent, ...]
    progress: tuple[LogProgress, ...]
    streams: tuple["LogStreamRead", ...]


class LogStreamRead(BaseModel):
    """Canonicality and scan bounds for one versioned log stream."""

    model_config = _STRICT

    adapter: str
    version: str
    topic_group: str
    deployment_block: int
    scan_from_block: int
    requested_to_block: int
    complete_through_block: int | None
    watermark_hash_match: bool | None
    reorged: bool

    @property
    def watermark_key(self) -> WatermarkKey:
        return WatermarkKey(
            adapter=self.adapter,
            version=self.version,
            topic_group=self.topic_group,
        )


class BlockCoverage(BaseModel):
    model_config = _STRICT

    from_block: int
    through_block: int


class StreamCoverage(BaseModel):
    model_config = _STRICT

    adapter: str
    version: str
    topic_group: str
    deployment_block: int
    ranges: tuple[BlockCoverage, ...]

    @property
    def watermark_key(self) -> WatermarkKey:
        return WatermarkKey(
            adapter=self.adapter,
            version=self.version,
            topic_group=self.topic_group,
        )

    def covers(self, through_block: int) -> bool:
        return bool(
            self.ranges
            and self.ranges[0].from_block <= self.deployment_block
            and self.ranges[0].through_block >= through_block
        )


class PullPoolHistory(BaseModel):
    """Deduped events plus explicit contiguous block coverage per stream.

    A persisted watermark is only a scan cursor.  After a process restart the
    matching prior ``PullPoolHistory`` fold must also be restored; without it,
    an overlap/tail read cannot prove deployment-to-state coverage and callers
    must rebuild from the stream's deployment block.
    """

    model_config = _STRICT

    observed_at: float
    events: tuple[PullPoolEvent, ...]
    coverage: tuple[StreamCoverage, ...]

    def coverage_for(self, key: WatermarkKey) -> StreamCoverage | None:
        return next(
            (item for item in self.coverage if item.watermark_key == key),
            None,
        )

    def covers(self, key: WatermarkKey, through_block: int) -> bool:
        coverage = self.coverage_for(key)
        return coverage is not None and coverage.covers(through_block)


@dataclass(frozen=True, slots=True)
class StateCall:
    surface_key: str
    field: str
    address: str
    calldata: str
    output: Literal["uint", "bool", "address"] = "uint"


@dataclass(frozen=True, slots=True)
class EventSpec:
    manifest: ProjectManifest
    name: str
    topic0: str
    inputs: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class LogStream:
    manifest: ProjectManifest
    watermark_key: WatermarkKey
    events: tuple[EventSpec, ...]


_EVENT_NAMES: dict[tuple[str, str], tuple[str, ...]] = {
    ("pullpool", "pullpool"): (
        "RoundOpened",
        "TicketsPurchased",
        "Pulled",
        "RoundClaimable",
        "RoundSettled",
        "RoundVoided",
        "ShareClaimed",
        "RefundClaimed",
        "RoundRewardCredited",
        "ReferralRecorded",
        "ReferralClaimed",
    ),
    ("group_pull", "group_pull"): (
        "RoundOpened",
        "Entered",
        "RoundBuying",
        "RoundDistributing",
        "RoundExpired",
        "RoundAborted",
        "Claimed",
        "BountyPaid",
        "PoolRoundBought",
        "PoolRoundCollected",
    ),
    ("standing_orders", "standing_orders"): ("OrderCreated",),
    ("group_pull", "group_orders"): ("OrderCreated",),
}


def _event_signature(entry: Mapping[str, Any]) -> str:
    types = ",".join(str(item.get("type")) for item in entry.get("inputs") or [])
    return f"{entry.get('name')}({types})"


def _event_spec(manifest: ProjectManifest, name: str) -> EventSpec:
    entry = _abi_entry(manifest, "event", name)
    signature = _event_signature(entry)
    return EventSpec(
        manifest=manifest,
        name=name,
        topic0=keccak256_hex(signature.encode("ascii")),
        inputs=tuple(entry.get("inputs") or ()),
    )


def _stream_adapter(manifest: ProjectManifest) -> str:
    if manifest.surface == "group_orders":
        return "group_orders"
    return manifest.family


def _watermark_id(key: WatermarkKey) -> str:
    return f"{key.adapter}:{key.version}:{key.topic_group}"


LOG_STREAMS: tuple[LogStream, ...] = tuple(
    LogStream(
        manifest=manifest,
        watermark_key=WatermarkKey(
            adapter=_stream_adapter(manifest),
            version=manifest.version,
            topic_group="orders" if manifest.role == "factory" else "lifecycle",
        ),
        events=tuple(
            _event_spec(manifest, name)
            for name in _EVENT_NAMES[(manifest.family, manifest.surface)]
            if any(
                entry.get("type") == "event" and entry.get("name") == name
                for entry in load_manifest_abi(manifest)
            )
        ),
    )
    for manifest in ALL_MANIFESTS
)
LOG_STREAM_BY_KEY: Mapping[WatermarkKey, LogStream] = {
    stream.watermark_key: stream for stream in LOG_STREAMS
}
LOG_STREAM_BY_ADDRESS: Mapping[str, LogStream] = {
    stream.manifest.address: stream for stream in LOG_STREAMS
}


def _summary_calls() -> tuple[StateCall, ...]:
    calls: list[StateCall] = []
    for manifest in PULLPOOL_MANIFESTS:
        key = _manifest_key(manifest)
        calls.extend(
            (
                StateCall(key, "round_count", manifest.address, SEL_ROUND_COUNT),
                StateCall(key, "accounted_eth_wei", manifest.address, SEL_ACCOUNTED_ETH),
                StateCall(key, "deprecated", manifest.address, SEL_DEPRECATED, "bool"),
                StateCall(key, "paused", manifest.address, SEL_PAUSED, "bool"),
                StateCall(
                    key,
                    "token_balance_wei",
                    FWA_TOKEN,
                    SEL_BALANCE_OF + encode_address(manifest.address),
                ),
                StateCall(
                    key,
                    "distributor_enabled",
                    FWA_TOKEN,
                    SEL_IS_DISTRIBUTOR + encode_address(manifest.address),
                    "bool",
                ),
            )
        )
        if manifest.version == "v2":
            calls.extend(
                (
                    StateCall(
                        key,
                        "current_open_round",
                        manifest.address,
                        SEL_CURRENT_OPEN_ROUND,
                    ),
                    StateCall(
                        key,
                        "pending_pull_count",
                        manifest.address,
                        SEL_PENDING_PULL_COUNT,
                    ),
                    StateCall(
                        key,
                        "can_pay_tokens",
                        manifest.address,
                        SEL_CAN_PAY_TOKENS,
                        "bool",
                    ),
                )
            )

    group_key = _manifest_key(GROUP_PULL_MANIFEST)
    calls.extend(
        (
            StateCall(group_key, "round_count", GROUP_PULL, SEL_ROUND_COUNT),
            StateCall(group_key, "accounted_eth_wei", GROUP_PULL, SEL_ACCOUNTED_ETH),
            StateCall(group_key, "accounted_fwa_wei", GROUP_PULL, SEL_FWA_ACCOUNTED),
            StateCall(group_key, "deprecated", GROUP_PULL, SEL_DEPRECATED, "bool"),
            StateCall(group_key, "paused", GROUP_PULL, SEL_PAUSED, "bool"),
            StateCall(group_key, "live_round", GROUP_PULL, SEL_LIVE_ROUND),
            StateCall(group_key, "buying_rounds", GROUP_PULL, SEL_BUYING_ROUNDS),
            StateCall(
                group_key,
                "token_balance_wei",
                FWA_TOKEN,
                SEL_BALANCE_OF + encode_address(GROUP_PULL),
            ),
            StateCall(
                group_key,
                "distributor_enabled",
                FWA_TOKEN,
                SEL_IS_DISTRIBUTOR + encode_address(GROUP_PULL),
                "bool",
            ),
        )
    )
    for manifest in ORDER_MANIFESTS:
        calls.append(
            StateCall(
                _manifest_key(manifest),
                "orders_created",
                manifest.address,
                SEL_ORDER_COUNT,
            )
        )
    return tuple(calls)


STATE_CALLS = _summary_calls()


def _decode_call(raw: str, output: str) -> int | bool | str:
    body = _abi_body(raw, exact_words=1)
    if output == "address":
        if body[:24] != "0" * 24:
            raise ValueError("ABI address has non-zero padding")
        return decode_address("0x" + body).lower()
    value = int(body, 16)
    if output == "bool":
        if value not in (0, 1):
            raise ValueError("ABI bool is not zero or one")
        return bool(value)
    return value


def _word(raw: str, index: int) -> int:
    body = _abi_body(raw, min_words=index + 1)
    return int(body[index * 64 : (index + 1) * 64], 16)


def _bool_word(raw: str, index: int) -> bool:
    value = _word(raw, index)
    if value not in (0, 1):
        raise ValueError("ABI bool is not zero or one")
    return bool(value)


def _abi_body(
    raw: Any,
    *,
    exact_words: int | None = None,
    min_words: int | None = None,
) -> str:
    if not isinstance(raw, str) or not raw.startswith("0x"):
        raise ValueError("ABI response must be 0x-prefixed hex")
    body = raw[2:]
    if len(body) % 64:
        raise ValueError("ABI response is not word-aligned")
    if exact_words is not None and len(body) != exact_words * 64:
        raise ValueError("ABI response has the wrong word count")
    if min_words is not None and len(body) < min_words * 64:
        raise ValueError("ABI response is truncated")
    try:
        bytes.fromhex(body)
    except ValueError as exc:
        raise ValueError("ABI response is not hex") from exc
    return body


def _pull_round(version: str, round_id: int, raw: str) -> PullPoolRoundState:
    indices = _PULL_ROUND_INDEX[version]
    state = _word(raw, indices["state"])
    lifecycle: PullPoolLifecycle = (
        PULLPOOL_STATE_NAMES[state] if state < len(PULLPOOL_STATE_NAMES) else "unknown"
    )
    return PullPoolRoundState(
        round_id=round_id,
        state=state,
        lifecycle=lifecycle,
        tickets_sold=_word(raw, indices["ticketsSold"]),
        max_tickets=_word(raw, indices["maxTickets"]),
        escrow_wei=_word(raw, indices["escrow"]),
        fee_owed_wei=_word(raw, indices["feeOwed"]),
        refund_pool_wei=_word(raw, indices["refundPool"]),
        eth_pot_wei=_word(raw, indices["ethPot"]),
        token_pot_wei=_word(raw, indices["tokenPot"]),
        referral_pool_wei=(
            _word(raw, indices["referralPool"])
            if "referralPool" in indices
            else 0
        ),
    )


def _group_round(round_id: int, raw: str) -> GroupPullRoundState:
    state = _word(raw, _GROUP_ROUND_INDEX["state"])
    lifecycle: GroupPullLifecycle = (
        GROUP_PULL_STATE_NAMES[state]
        if state < len(GROUP_PULL_STATE_NAMES)
        else "unknown"
    )
    return GroupPullRoundState(
        round_id=round_id,
        state=state,
        lifecycle=lifecycle,
        tickets_sold=_word(raw, _GROUP_ROUND_INDEX["ticketsSold"]),
        escrow_wei=_word(raw, _GROUP_ROUND_INDEX["escrow"]),
        eth_pool_wei=_word(raw, _GROUP_ROUND_INDEX["ethPool"]),
        eth_paid_wei=_word(raw, _GROUP_ROUND_INDEX["ethPaid"]),
        fwa_pot_wei=_word(raw, _GROUP_ROUND_INDEX["fwaPot"]),
        fwa_paid_wei=_word(raw, _GROUP_ROUND_INDEX["fwaPaid"]),
        aborted=_bool_word(raw, _GROUP_ROUND_INDEX["aborted"]),
    )


def _hex_quantity(value: Any) -> int | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    raw = value[2:]
    if not raw or (len(raw) > 1 and raw.startswith("0")):
        return None
    try:
        out = int(raw, 16)
    except ValueError:
        return None
    return out


def _decode_topic_value(kind: str, value: str) -> Any:
    if kind == "address":
        return _decode_call(value, "address")
    if kind == "bool":
        return _decode_call(value, "bool")
    return _decode_call(value, "uint")


def _decode_data_value(kind: str, data: str, index: int) -> Any:
    body = _abi_body(data, min_words=index + 1)
    word = "0x" + body[index * 64 : (index + 1) * 64]
    if kind == "address":
        return _decode_call(word, "address")
    if kind == "bool":
        return _decode_call(word, "bool")
    return _decode_call(word, "uint")


_EVENT_KEY = {
    "RoundOpened": ("round_opened", "Round opened"),
    "TicketsPurchased": ("tickets_purchased", "Tickets purchased"),
    "Pulled": ("round_pulled", "FWA pull submitted"),
    "RoundClaimable": ("round_claimable", "Round claimable"),
    "RoundSettled": ("round_settled", "Round settled"),
    "RoundVoided": ("round_voided", "Round refunding"),
    "ShareClaimed": ("share_claimed", "Pool share claimed"),
    "RefundClaimed": ("refund_claimed", "Refund claimed"),
    "RoundRewardCredited": ("round_reward_credited", "FWA reward credited"),
    "ReferralRecorded": ("referral_recorded", "Referral recorded"),
    "ReferralClaimed": ("referral_claimed", "Referral claimed"),
    "Entered": ("pack_entered", "Group pack entered"),
    "RoundBuying": ("pack_buying", "Group pack buying"),
    "RoundDistributing": ("pack_distributing", "Group pack distributing"),
    "RoundExpired": ("pack_expired", "Group pack expired"),
    "RoundAborted": ("pack_aborted", "Group pack aborted"),
    "Claimed": ("pack_claimed", "Group pack claimed"),
    "BountyPaid": ("bounty_paid", "Crank bounty paid"),
    "PoolRoundBought": ("pool_round_bought", "Pool round bought"),
    "PoolRoundCollected": ("pool_round_collected", "Pool round collected"),
    "OrderCreated": ("order_created", "Standing order created"),
}


def _origin(manifest: ProjectManifest) -> str:
    return {
        "pullpool": "PullPool",
        "group_pull": "GroupPull",
        "standing_orders": "Standing Orders",
        "group_orders": "Group Orders",
    }.get(manifest.surface, manifest.surface)


def _event_amounts(name: str, values: Mapping[str, Any]) -> tuple[int | None, int | None]:
    eth_field = {
        "TicketsPurchased": "paid",
        "Pulled": "spent",
        "RoundSettled": "ethPot",
        "RoundVoided": "refundPool",
        "ShareClaimed": "ethAmount",
        "RefundClaimed": "amount",
        "ReferralClaimed": "amount",
        "Entered": "paid",
        "RoundDistributing": "ethPool",
        "RoundExpired": "returned",
        "RoundAborted": "unspentReturned",
        "Claimed": "ethAmount",
        "BountyPaid": "amount",
        "PoolRoundBought": "spent",
        "PoolRoundCollected": "ethCollected",
    }.get(name)
    fwa_field = {
        "RoundSettled": "tokenPot",
        "ShareClaimed": "tokenAmount",
        "RoundRewardCredited": "amount",
        "RoundDistributing": "fwaPot",
        "Claimed": "fwaAmount",
        "PoolRoundCollected": "fwaCollected",
    }.get(name)
    eth = values.get(eth_field) if eth_field else None
    fwa = values.get(fwa_field) if fwa_field else None
    return (
        eth if isinstance(eth, int) and not isinstance(eth, bool) else None,
        fwa if isinstance(fwa, int) and not isinstance(fwa, bool) else None,
    )


def _decode_event(spec: EventSpec, raw: Mapping[str, Any]) -> PullPoolEvent | None:
    if raw.get("removed") is True:
        return None
    if str(raw.get("address") or "").lower() != spec.manifest.address:
        return None
    topics = raw.get("topics")
    if not isinstance(topics, list) or not topics:
        return None
    if len(topics) != 1 + sum(bool(item.get("indexed")) for item in spec.inputs):
        return None
    if any(
        not isinstance(topic, str)
        or len(topic) != 66
        or not topic.startswith("0x")
        for topic in topics
    ):
        return None
    try:
        for topic in topics:
            bytes.fromhex(topic[2:])
    except ValueError:
        return None
    if str(topics[0]).lower() != spec.topic0:
        return None
    block = _hex_quantity(raw.get("blockNumber"))
    log_index = _hex_quantity(raw.get("logIndex"))
    timestamp = _hex_quantity(raw.get("blockTimestamp"))
    tx_hash = str(raw.get("transactionHash") or "").lower()
    if (
        block is None
        or log_index is None
        or len(tx_hash) != 66
        or not tx_hash.startswith("0x")
    ):
        return None
    try:
        bytes.fromhex(tx_hash[2:])
    except ValueError:
        return None

    values: dict[str, Any] = {}
    topic_index = 1
    data_index = 0
    data = str(raw.get("data") or "0x")
    try:
        nonindexed_count = sum(not bool(item.get("indexed")) for item in spec.inputs)
        _abi_body(data, exact_words=nonindexed_count)
        for item in spec.inputs:
            name = str(item.get("name") or "")
            kind = str(item.get("type") or "")
            if kind.endswith("[]") or kind in ("bytes", "string"):
                return None
            if item.get("indexed"):
                if topic_index >= len(topics):
                    return None
                values[name] = _decode_topic_value(kind, str(topics[topic_index]))
                topic_index += 1
            else:
                values[name] = _decode_data_value(kind, data, data_index)
                data_index += 1
    except (TypeError, ValueError, IndexError):
        return None

    event_key, label = _EVENT_KEY[spec.name]
    if spec.name == "OrderCreated" and spec.manifest.surface == "group_orders":
        label = "Group order created"
    round_id = values.get("roundId")
    if not isinstance(round_id, int) or isinstance(round_id, bool):
        round_id = None
    eth_amount, fwa_amount = _event_amounts(spec.name, values)
    detail_parts: list[str] = []
    if round_id is not None:
        detail_parts.append(f"round {round_id}")
    for key, label_part in (
        ("quantity", "tickets"),
        ("tickets", "tickets"),
        ("ticketsPerRound", "tickets / round"),
        ("poolRoundId", "pool round"),
        ("outcome", "outcome"),
    ):
        value = values.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            detail_parts.append(f"{label_part} {value}")

    return PullPoolEvent(
        address=spec.manifest.address,
        family=spec.manifest.family,
        surface=spec.manifest.surface,
        version=spec.manifest.version,
        event_key=event_key,
        event_label=label,
        block_number=block,
        block_timestamp=timestamp if timestamp and timestamp > 0 else None,
        tx_hash=tx_hash,
        log_index=log_index,
        round_id=round_id,
        eth_amount_wei=eth_amount,
        fwa_amount_wei=fwa_amount,
        detail=" · ".join(detail_parts),
    )


def _status(codehash: bool | None, dependencies: Sequence[bool | None]) -> IntegrityStatus:
    checks = [codehash, *dependencies]
    if any(value is False for value in checks):
        return "mismatch"
    if not checks or any(value is None for value in checks):
        return "unknown"
    return "ok"


def runtime_codehash(raw_code: Any) -> str | None:
    """Return the runtime-bytecode keccak, or ``None`` for malformed RPC data."""

    if not isinstance(raw_code, str):
        return None
    raw = strip0x(raw_code)
    if len(raw) % 2:
        return None
    try:
        return keccak256_hex(bytes.fromhex(raw))
    except ValueError:
        return None


class PullPoolAdapter(FWAClient):
    """Pinned state and bounded history for PullPool's deployed surfaces."""

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        state_endpoints: Sequence[str] | None = None,
        log_endpoints: Sequence[str] | None = None,
        clock: Callable[[], float] = time.time,
        page_size: int = _DEFAULT_PAGE_SIZE,
        max_pages: int = _DEFAULT_MAX_PAGES,
        overlap: int = _DEFAULT_OVERLAP,
    ) -> None:
        if isinstance(state_endpoints, (str, bytes)):
            raise ValueError("state_endpoints must be a sequence of URLs")
        if isinstance(log_endpoints, (str, bytes)):
            raise ValueError("log_endpoints must be a sequence of URLs")
        endpoints = tuple(state_endpoints or ())
        requested_log_endpoints = (
            None if log_endpoints is None else tuple(log_endpoints)
        )
        if state_endpoints is not None and not endpoints:
            raise ValueError("state_endpoints cannot be empty")
        if requested_log_endpoints is not None and not requested_log_endpoints:
            raise ValueError("log_endpoints cannot be empty")
        chosen_log_endpoints = requested_log_endpoints or LOG_ENDPOINTS
        if any(endpoint not in LOG_ENDPOINTS for endpoint in chosen_log_endpoints):
            raise ValueError("log_endpoints must use the hardened Pool-B whitelist")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise ValueError("page_size must be a positive int")
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("max_pages must be a positive int")
        if (
            isinstance(overlap, bool)
            or not isinstance(overlap, int)
            or overlap < 1
            or overlap > MAX_REORG_OVERLAP
        ):
            raise ValueError(f"overlap must be in 1..{MAX_REORG_OVERLAP}")
        kwargs: dict[str, Any] = {
            "http_client": http_client,
        }
        if endpoints:
            kwargs["primary_rpc"] = endpoints[0]
            kwargs["fallback_rpcs"] = list(endpoints[1:])
        super().__init__(**kwargs)
        if endpoints:
            # FWAClient treats an empty fallback list as "use defaults".  An
            # explicit adapter endpoint list must remain exact and keyless.
            self._fallback_rpcs = list(endpoints[1:])
        self._clock = clock
        self._page_size = page_size
        self._max_pages = max_pages
        self._overlap = overlap
        self._log_endpoints = chosen_log_endpoints
        self._log_http_client = http_client
        self._log_clients: dict[str, FWALogClient] = {}

    def _now(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("PullPool clock must return epoch seconds")
        value = float(value)
        if value != value or value in (float("inf"), float("-inf")) or value < 0:
            raise ValueError("PullPool clock must return finite epoch seconds")
        return value

    def _log_client(self, address: str) -> FWALogClient:
        client = self._log_clients.get(address)
        if client is None:
            client = FWALogClient(
                endpoints=self._log_endpoints,
                http_client=self._log_http_client,
                core_address=address,
            )
            self._log_clients[address] = client
        return client

    async def close(self) -> None:
        for client in self._log_clients.values():
            await client.close()
        self._log_clients.clear()
        await super().close()

    @staticmethod
    def _validate_block(block_number: int) -> str:
        if (
            isinstance(block_number, bool)
            or not isinstance(block_number, int)
            or block_number < 0
        ):
            raise ValueError("block_number must be a non-negative int")
        return hex(block_number)

    async def fetch_state(self, block_number: int) -> PullPoolRead:
        """Read every state surface at exactly ``block_number``."""

        block_tag = self._validate_block(block_number)
        observed_at = self._now()
        results = await self._multicall(
            [(call.address, call.calldata) for call in STATE_CALLS], block_tag
        )
        values: dict[str, dict[str, Any]] = {
            _manifest_key(manifest): {} for manifest in ALL_MANIFESTS
        }
        failed: dict[str, list[str]] = {key: [] for key in values}
        for index, call in enumerate(STATE_CALLS):
            ok, raw = results[index] if index < len(results) else (False, "0x")
            if not ok or not strip0x(raw):
                values[call.surface_key][call.field] = None
                failed[call.surface_key].append(call.field)
                continue
            try:
                values[call.surface_key][call.field] = _decode_call(raw, call.output)
            except (TypeError, ValueError):
                values[call.surface_key][call.field] = None
                failed[call.surface_key].append(call.field)

        round_specs: list[tuple[ProjectManifest, int]] = []
        for manifest in (*PULLPOOL_MANIFESTS, GROUP_PULL_MANIFEST):
            key = _manifest_key(manifest)
            count = values[key].get("round_count")
            if (
                isinstance(count, int)
                and not isinstance(count, bool)
                and 0 <= count <= _MAX_ROUNDS
            ):
                round_specs.extend((manifest, round_id) for round_id in range(1, count + 1))
            elif count is not None:
                failed[key].append("round_count_out_of_range")
                values[key]["round_count"] = None

        round_results = await self._multicall(
            [
                (manifest.address, SEL_GET_ROUND + encode_uint(round_id))
                for manifest, round_id in round_specs
            ],
            block_tag,
        )
        decoded_rounds: dict[str, list[Any]] = {
            _manifest_key(manifest): []
            for manifest in (*PULLPOOL_MANIFESTS, GROUP_PULL_MANIFEST)
        }
        for index, (manifest, round_id) in enumerate(round_specs):
            key = _manifest_key(manifest)
            ok, raw = round_results[index] if index < len(round_results) else (False, "0x")
            if not ok or not strip0x(raw):
                failed[key].append(f"getRound:{round_id}")
                continue
            try:
                row = (
                    _group_round(round_id, raw)
                    if manifest is GROUP_PULL_MANIFEST
                    else _pull_round(manifest.version, round_id, raw)
                )
            except (TypeError, ValueError, IndexError):
                failed[key].append(f"getRound:{round_id}")
                continue
            decoded_rounds[key].append(row)

        pullpools: list[PullPoolSurfaceState] = []
        for manifest in PULLPOOL_MANIFESTS:
            key = _manifest_key(manifest)
            surface = values[key]
            count = surface.get("round_count")
            rounds = tuple(decoded_rounds[key])
            complete_rounds = count is not None and len(rounds) == count
            critical = count is not None and surface.get("accounted_eth_wei") is not None
            pullpools.append(
                PullPoolSurfaceState(
                    version=manifest.version,
                    address=manifest.address,
                    is_current=manifest.is_current,
                    observed_at=observed_at,
                    block_number=block_number,
                    available=bool(critical and complete_rounds),
                    round_count=count,
                    accounted_eth_wei=surface.get("accounted_eth_wei"),
                    token_balance_wei=surface.get("token_balance_wei"),
                    distributor_enabled=surface.get("distributor_enabled"),
                    can_pay_tokens=surface.get("can_pay_tokens"),
                    paused=surface.get("paused"),
                    deprecated=surface.get("deprecated"),
                    current_open_round=surface.get("current_open_round"),
                    pending_pull_count=surface.get("pending_pull_count"),
                    rounds=rounds,
                    failed_fields=tuple(dict.fromkeys(failed[key])),
                )
            )

        group_key = _manifest_key(GROUP_PULL_MANIFEST)
        group_values = values[group_key]
        group_count = group_values.get("round_count")
        group_rounds = tuple(decoded_rounds[group_key])
        group_complete = group_count is not None and len(group_rounds) == group_count
        group_critical = (
            group_count is not None
            and group_values.get("accounted_eth_wei") is not None
            and group_values.get("accounted_fwa_wei") is not None
        )
        group = GroupPullSurfaceState(
            version=GROUP_PULL_MANIFEST.version,
            address=GROUP_PULL_MANIFEST.address,
            observed_at=observed_at,
            block_number=block_number,
            available=bool(group_critical and group_complete),
            round_count=group_count,
            accounted_eth_wei=group_values.get("accounted_eth_wei"),
            accounted_fwa_wei=group_values.get("accounted_fwa_wei"),
            token_balance_wei=group_values.get("token_balance_wei"),
            distributor_enabled=group_values.get("distributor_enabled"),
            paused=group_values.get("paused"),
            deprecated=group_values.get("deprecated"),
            live_round=group_values.get("live_round"),
            buying_rounds=group_values.get("buying_rounds"),
            rounds=group_rounds,
            failed_fields=tuple(dict.fromkeys(failed[group_key])),
        )

        order_states = tuple(
            OrderFactoryState(
                family=manifest.family,
                surface=manifest.surface,
                version=manifest.version,
                address=manifest.address,
                is_current=manifest.is_current,
                observed_at=observed_at,
                block_number=block_number,
                available=values[_manifest_key(manifest)].get("orders_created") is not None,
                orders_created=values[_manifest_key(manifest)].get("orders_created"),
                failed_fields=tuple(dict.fromkeys(failed[_manifest_key(manifest)])),
            )
            for manifest in ORDER_MANIFESTS
        )
        return PullPoolRead(
            observed_at=observed_at,
            block_number=block_number,
            pullpools=tuple(pullpools),
            group_pull=group,
            order_factories=order_states,
        )

    async def fetch_integrity(self, block_number: int) -> PullPoolIntegrityRead:
        """Check runtime hashes and every manifest-declared dependency."""

        block_tag = self._validate_block(block_number)
        observed_at = self._now()
        codehashes: dict[str, bool | None] = {}
        for manifest in ALL_MANIFESTS:
            key = _manifest_key(manifest)
            try:
                raw = await self._rpc("eth_getCode", [manifest.address, block_tag])
            except RuntimeError:
                codehashes[key] = None
            else:
                observed_hash = runtime_codehash(raw)
                codehashes[key] = (
                    None
                    if observed_hash is None
                    else observed_hash.lower() == manifest.runtime_codehash.lower()
                )

        dependency_specs: list[tuple[ProjectManifest, str, str]] = []
        for manifest in ALL_MANIFESTS:
            for getter, expected in manifest.dependencies:
                entry = _abi_entry(manifest, "function", getter)
                if entry.get("inputs"):
                    raise ValueError(
                        f"dependency getter {getter} on {manifest.address} needs arguments"
                    )
                dependency_specs.append((manifest, getter, expected))

        dependency_results = await self._multicall(
            [
                (manifest.address, _selector(f"{getter}()"))
                for manifest, getter, _expected in dependency_specs
            ],
            block_tag,
        )
        dependencies: dict[str, list[tuple[str, bool | None]]] = {
            _manifest_key(manifest): [] for manifest in ALL_MANIFESTS
        }
        for index, (manifest, getter, expected) in enumerate(dependency_specs):
            ok, raw = (
                dependency_results[index]
                if index < len(dependency_results)
                else (False, "0x")
            )
            match: bool | None = None
            if ok and strip0x(raw):
                try:
                    match = _decode_call(raw, "address") == expected.lower()
                except (TypeError, ValueError):
                    match = None
            dependencies[_manifest_key(manifest)].append((getter, match))

        surfaces: list[SurfaceIntegrity] = []
        for manifest in ALL_MANIFESTS:
            key = _manifest_key(manifest)
            pairs = tuple(dependencies[key])
            surfaces.append(
                SurfaceIntegrity(
                    surface_key=key,
                    address=manifest.address,
                    block_number=block_number,
                    codehash_match=codehashes[key],
                    dependency_matches=pairs,
                    status=_status(codehashes[key], [value for _name, value in pairs]),
                )
            )
        return PullPoolIntegrityRead(
            observed_at=observed_at,
            block_number=block_number,
            surfaces=tuple(surfaces),
        )

    async def _block_hash(self, block_number: int) -> str | None:
        try:
            raw = await self._rpc("eth_getBlockByNumber", [hex(block_number), False])
        except RuntimeError:
            return None
        if not isinstance(raw, Mapping):
            return None
        block_hash = str(raw.get("hash") or "").lower()
        if len(block_hash) != 66 or not block_hash.startswith("0x"):
            return None
        try:
            int(block_hash[2:], 16)
        except ValueError:
            return None
        return block_hash

    async def fetch_logs(
        self,
        from_block: int,
        to_block: int,
        *,
        watermarks: Mapping[WatermarkKey, Watermark] | None = None,
        cache: FWAEcosystemCache | None = None,
        history_complete: bool = False,
        stream_keys: Sequence[WatermarkKey] | None = None,
    ) -> PullPoolLogRead:
        """Fetch bounded pages after validating every persisted watermark hash.

        ``history_complete`` is retained as a compatibility hint but has no
        authority.  Only explicit block coverage accumulated by
        :func:`accumulate_history` can certify an exact historical liability.
        """

        self._validate_block(from_block)
        self._validate_block(to_block)
        if from_block > to_block:
            raise ValueError("from_block must not exceed to_block")
        if not isinstance(history_complete, bool):
            raise ValueError("history_complete must be a bool")
        if cache is not None and not isinstance(cache, FWAEcosystemCache):
            raise TypeError("cache must be an FWAEcosystemCache")
        if cache is not None and watermarks is not None:
            raise ValueError("pass cache or watermarks, not both")
        observed_at = self._now()
        chosen = (
            tuple(LOG_STREAM_BY_KEY[key] for key in stream_keys)
            if stream_keys is not None
            else LOG_STREAMS
        )
        watermark_map = watermarks or {}
        decoded: dict[str, PullPoolEvent] = {}
        progress: list[LogProgress] = []
        stream_reads: list[LogStreamRead] = []
        failed_streams: list[str] = []
        complete_versions: set[str] = set()

        for stream in chosen:
            key = stream.watermark_key
            watermark = (
                cache.get_watermark(key)
                if cache is not None
                else watermark_map.get(key)
            )
            overlap = watermark.overlap if watermark is not None else self._overlap
            start = max(stream.manifest.deployment_block, from_block)
            hash_match: bool | None = None
            reorged = False
            if watermark is not None:
                live_hash = await self._block_hash(watermark.block_number)
                resume = max(
                    stream.manifest.deployment_block,
                    watermark.block_number + 1 - overlap,
                )
                if live_hash is None:
                    failed_streams.append(_watermark_id(key))
                    stream_reads.append(
                        LogStreamRead(
                            adapter=key.adapter,
                            version=key.version,
                            topic_group=key.topic_group,
                            deployment_block=stream.manifest.deployment_block,
                            scan_from_block=resume,
                            requested_to_block=to_block,
                            complete_through_block=None,
                            watermark_hash_match=None,
                            reorged=False,
                        )
                    )
                    continue
                hash_match = live_hash == watermark.block_hash.lower()
                if cache is not None:
                    reorged = cache.reconcile_block_hash(
                        key,
                        live_hash,
                        deployment_block=stream.manifest.deployment_block,
                    )
                    resume = cache.scan_start(
                        key,
                        deployment_block=stream.manifest.deployment_block,
                    )
                else:
                    reorged = not hash_match
                # A reorg rewind is mandatory even if the caller supplied a
                # later tail start.  A matching watermark may respect it.
                start = resume if reorged else max(start, resume)
            initial_start = start
            stream_ok = True
            complete_through: int | None = None
            for _page in range(self._max_pages):
                if start > to_block:
                    break
                end = min(start + self._page_size - 1, to_block)
                try:
                    raw_logs = await self._log_client(stream.manifest.address).get_logs(
                        [[event.topic0 for event in stream.events]], start, end
                    )
                except Exception as exc:  # noqa: BLE001 - one stream degrades alone
                    logger.warning("%s logs unavailable: %s", stream.watermark_key, exc)
                    failed_streams.append(_watermark_id(stream.watermark_key))
                    progress.append(
                        LogProgress(
                            adapter=stream.watermark_key.adapter,
                            version=stream.watermark_key.version,
                            topic_group=stream.watermark_key.topic_group,
                            from_block=start,
                            to_block=end,
                            last_block_hash=None,
                            page_complete=False,
                            overlap=overlap,
                        )
                    )
                    stream_ok = False
                    break

                by_topic = {event.topic0: event for event in stream.events}
                decode_failed = False
                for raw in raw_logs:
                    if not isinstance(raw, Mapping):
                        decode_failed = True
                        continue
                    topics = raw.get("topics")
                    topic0 = str(topics[0]).lower() if isinstance(topics, list) and topics else ""
                    spec = by_topic.get(topic0)
                    if spec is None:
                        decode_failed = True
                        continue
                    event = _decode_event(spec, raw)
                    if (
                        event is None
                        or event.block_number < start
                        or event.block_number > end
                    ):
                        decode_failed = True
                        continue
                    decoded[event.event_id] = event

                block_hash = await self._block_hash(end)
                complete = block_hash is not None and not decode_failed
                progress.append(
                    LogProgress(
                        adapter=stream.watermark_key.adapter,
                        version=stream.watermark_key.version,
                        topic_group=stream.watermark_key.topic_group,
                        from_block=start,
                        to_block=end,
                        last_block_hash=block_hash,
                        page_complete=complete,
                        overlap=overlap,
                    )
                )
                if not complete:
                    failed_streams.append(_watermark_id(stream.watermark_key))
                    stream_ok = False
                    break
                complete_through = end
                start = end + 1

            stream_reads.append(
                LogStreamRead(
                    adapter=key.adapter,
                    version=key.version,
                    topic_group=key.topic_group,
                    deployment_block=stream.manifest.deployment_block,
                    scan_from_block=initial_start,
                    requested_to_block=to_block,
                    complete_through_block=complete_through,
                    watermark_hash_match=hash_match,
                    reorged=reorged,
                )
            )
            if (
                stream_ok
                and initial_start == stream.manifest.deployment_block
                and complete_through is not None
                and complete_through >= to_block
            ):
                complete_versions.add(
                    f"{stream.manifest.family}:{stream.manifest.surface}:{stream.manifest.version}"
                )

        events = tuple(
            sorted(
                decoded.values(),
                key=lambda event: (event.block_number, event.log_index),
                reverse=True,
            )
        )
        expected_complete = {
            f"{stream.manifest.family}:{stream.manifest.surface}:{stream.manifest.version}"
            for stream in chosen
        }
        all_complete = not failed_streams and expected_complete <= complete_versions
        return PullPoolLogRead(
            observed_at=observed_at,
            requested_from_block=from_block,
            requested_to_block=to_block,
            available=bool(chosen) and not failed_streams,
            history_complete=all_complete,
            history_complete_versions=tuple(sorted(complete_versions)),
            failed_streams=tuple(dict.fromkeys(failed_streams)),
            events=events,
            progress=tuple(progress),
            streams=tuple(stream_reads),
        )


def _merge_coverage(ranges: Sequence[BlockCoverage]) -> tuple[BlockCoverage, ...]:
    ordered = sorted(ranges, key=lambda item: (item.from_block, item.through_block))
    merged: list[BlockCoverage] = []
    for item in ordered:
        if item.from_block > item.through_block:
            raise ValueError("coverage range starts after it ends")
        if not merged or item.from_block > merged[-1].through_block + 1:
            merged.append(item)
            continue
        previous = merged[-1]
        merged[-1] = BlockCoverage(
            from_block=previous.from_block,
            through_block=max(previous.through_block, item.through_block),
        )
    return tuple(merged)


def _truncate_coverage(
    ranges: Sequence[BlockCoverage], from_block: int
) -> tuple[BlockCoverage, ...]:
    kept: list[BlockCoverage] = []
    for item in ranges:
        if item.from_block >= from_block:
            continue
        kept.append(
            BlockCoverage(
                from_block=item.from_block,
                through_block=min(item.through_block, from_block - 1),
            )
        )
    return tuple(kept)


def _event_stream_key(event: PullPoolEvent) -> WatermarkKey:
    stream = LOG_STREAM_BY_ADDRESS[event.address.lower()]
    return stream.watermark_key


def accumulate_history(
    previous: PullPoolHistory | None,
    read: PullPoolLogRead,
    *,
    cache: FWAEcosystemCache | None = None,
) -> PullPoolHistory:
    """Replace scanned overlap and merge only fully canonical log pages.

    A reorg drops every prior event and coverage range at or after its forced
    rewind before canonical replacement pages are added.  When *cache* is
    supplied, watermark advancement happens only after the new frozen history
    has validated successfully.
    """

    if previous is not None and not isinstance(previous, PullPoolHistory):
        raise TypeError("previous must be PullPoolHistory or None")
    if not isinstance(read, PullPoolLogRead):
        raise TypeError("read must be PullPoolLogRead")
    if cache is not None and not isinstance(cache, FWAEcosystemCache):
        raise TypeError("cache must be an FWAEcosystemCache")

    events = {
        event.event_id: event for event in (() if previous is None else previous.events)
    }
    coverage = {
        item.watermark_key: item
        for item in (() if previous is None else previous.coverage)
    }
    progress_by_key: dict[WatermarkKey, list[LogProgress]] = {}
    for page in read.progress:
        progress_by_key.setdefault(page.watermark_key, []).append(page)

    for scan in read.streams:
        key = scan.watermark_key
        current = coverage.get(key)
        ranges = list(() if current is None else current.ranges)
        if scan.reorged:
            ranges = list(_truncate_coverage(ranges, scan.scan_from_block))
            events = {
                event_id: event
                for event_id, event in events.items()
                if not (
                    _event_stream_key(event) == key
                    and event.block_number >= scan.scan_from_block
                )
            }

        complete_pages = [
            page
            for page in progress_by_key.get(key, [])
            if page.page_complete and page.last_block_hash is not None
        ]
        for page in complete_pages:
            events = {
                event_id: event
                for event_id, event in events.items()
                if not (
                    _event_stream_key(event) == key
                    and page.from_block <= event.block_number <= page.to_block
                )
            }
            ranges.append(
                BlockCoverage(
                    from_block=page.from_block,
                    through_block=page.to_block,
                )
            )

        for event in read.events:
            if _event_stream_key(event) != key:
                continue
            if any(
                page.from_block <= event.block_number <= page.to_block
                for page in complete_pages
            ):
                events[event.event_id] = event

        coverage[key] = StreamCoverage(
            adapter=key.adapter,
            version=key.version,
            topic_group=key.topic_group,
            deployment_block=scan.deployment_block,
            ranges=_merge_coverage(ranges),
        )

    history = PullPoolHistory(
        observed_at=read.observed_at,
        events=tuple(
            sorted(
                events.values(),
                key=lambda event: (event.block_number, event.log_index),
                reverse=True,
            )
        ),
        coverage=tuple(
            coverage[key] for key in sorted(coverage)
        ),
    )

    if cache is not None:
        scans = {scan.watermark_key: scan for scan in read.streams}
        for page in read.progress:
            if not page.page_complete or page.last_block_hash is None:
                continue
            prior = cache.get_watermark(page.watermark_key)
            scan = scans[page.watermark_key]
            if (
                prior is not None
                and page.to_block < prior.block_number
                and not scan.reorged
            ):
                continue
            cache.set_watermark(
                page.watermark_key,
                block_number=page.to_block,
                block_hash=page.last_block_hash,
                overlap=page.overlap,
                page_complete=True,
                ts=read.observed_at,
            )
    return history


def _wei_float(value: int | None) -> float | None:
    return None if value is None else value / _WEI_PER_TOKEN


def _counts(rows: Sequence[Any], names: Sequence[str]) -> dict[str, int]:
    counts = {name: 0 for name in names}
    counts["unknown"] = 0
    for row in rows:
        lifecycle = str(row.lifecycle)
        counts[lifecycle if lifecycle in counts else "unknown"] += 1
    return counts


def _pull_lifecycle(surface: PullPoolSurfaceState) -> str:
    if not surface.available:
        return "unavailable"
    counts = _counts(surface.rounds, PULLPOOL_STATE_NAMES)
    for name in ("open", "pulling", "claimable", "refunding", "settled", "unknown"):
        if counts[name]:
            lifecycle = name
            break
    else:
        lifecycle = "deprecated" if surface.deprecated else "idle"
    if surface.paused:
        lifecycle += " · paused"
    if surface.distributor_enabled is False or surface.can_pay_tokens is False:
        lifecycle += " · FWA claims blocked"
    return lifecycle


def _group_lifecycle(surface: GroupPullSurfaceState) -> str:
    if not surface.available:
        return "unavailable"
    counts = _counts(surface.rounds, GROUP_PULL_STATE_NAMES)
    for name in (
        "selling",
        "buying",
        "collecting",
        "distributing",
        "expired",
        "unknown",
    ):
        if counts[name]:
            lifecycle = name
            break
    else:
        lifecycle = "deprecated" if surface.deprecated else "idle"
    if surface.paused:
        lifecycle += " · paused"
    if surface.distributor_enabled is False:
        lifecycle += " · FWA claims blocked"
    return lifecycle


def _pull_fwa_liability(
    version: str,
    state_block: int,
    history: PullPoolHistory | None,
) -> int | None:
    key = WatermarkKey(
        adapter="pullpool",
        version=version,
        topic_group="lifecycle",
    )
    if history is None or not history.covers(key, state_block):
        return None
    credited = 0
    paid = 0
    for event in history.events:
        if event.family != "pullpool" or event.version != version:
            continue
        if event.block_number > state_block:
            continue
        if event.event_key in ("round_settled", "round_reward_credited"):
            credited += event.fwa_amount_wei or 0
        elif event.event_key == "share_claimed":
            paid += event.fwa_amount_wei or 0
    if paid > credited:
        return None
    return credited - paid


def _integrity_for(
    manifest: ProjectManifest,
    integrity: PullPoolIntegrityRead | None,
    *,
    operational_warning: bool = False,
) -> IntegrityStatus:
    status: IntegrityStatus = (
        "unknown" if integrity is None else integrity.status_for(manifest)
    )
    if status != "mismatch" and operational_warning:
        return "warning"
    return status


def _source_badge(status: IntegrityStatus, available: bool) -> str:
    if status == "mismatch":
        return "INTEGRITY"
    if status in ("warning", "unknown") or not available:
        return "DEGRADED"
    return "VERIFIED"


def _project_row(**kwargs: Any) -> dict[str, Any]:
    dumped = ProjectRow.model_validate(kwargs).model_dump()
    assert tuple(dumped) == PROJECT_ROW_KEYS
    return dumped


def build_project_rows(
    state: PullPoolRead,
    *,
    logs: PullPoolLogRead | None = None,
    history: PullPoolHistory | None = None,
    integrity: PullPoolIntegrityRead | None = None,
    stale: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Build rows; only accumulated deployment-to-state history is exact.

    ``logs`` remains accepted for manager compatibility, but a raw page read
    never proves completeness and therefore cannot drive exact liabilities.
    """

    if not isinstance(stale, bool):
        raise ValueError("stale must be a bool")
    if logs is not None and not isinstance(logs, PullPoolLogRead):
        raise TypeError("logs must be PullPoolLogRead or None")
    if history is not None and not isinstance(history, PullPoolHistory):
        raise TypeError("history must be PullPoolHistory or None")
    rows: list[dict[str, Any]] = []
    manifests = {manifest.version: manifest for manifest in PULLPOOL_MANIFESTS}
    for surface in state.pullpools:
        manifest = manifests[surface.version]
        exact_fwa = _pull_fwa_liability(
            surface.version,
            surface.block_number,
            history,
        )
        fwa_wei = exact_fwa if exact_fwa is not None else surface.token_balance_wei
        fwa_label = (
            "outstanding claims"
            if exact_fwa is not None
            else "held claims upper bound"
        )
        blocked = surface.distributor_enabled is False or surface.can_pay_tokens is False
        underfunded = (
            exact_fwa is not None
            and surface.token_balance_wei is not None
            and surface.token_balance_wei < exact_fwa
        )
        status = _integrity_for(
            manifest,
            integrity,
            operational_warning=blocked or underfunded,
        )
        counts = _counts(surface.rounds, PULLPOOL_STATE_NAMES)
        semantic_ok = status != "mismatch"
        if not semantic_ok:
            detail = "runtime/dependency integrity mismatch; metrics suppressed"
        elif not surface.available:
            detail = "round lifecycle unavailable"
        else:
            detail = (
                f"{counts['open']} open · {counts['pulling']} pulling · "
                f"{counts['claimable']} claimable · {counts['settled']} settled · "
                f"{counts['refunding']} refunding"
            )
        if semantic_ok:
            if exact_fwa is None:
                detail += " · FWA history incomplete; held balance is an upper bound"
            elif underfunded:
                detail += " · held FWA is below event-derived claims"
        row = _project_row(
            family="pullpool",
            surface="pullpool",
            version=surface.version,
            address=surface.address,
            is_current=surface.is_current,
            is_legacy_liability=not surface.is_current,
            lifecycle=_pull_lifecycle(surface) if semantic_ok else "integrity mismatch",
            primary_label="rounds created",
            primary_value=surface.round_count if semantic_ok else None,
            primary_unit="rounds",
            eth_label="accounted liability",
            eth_value=_wei_float(surface.accounted_eth_wei) if semantic_ok else None,
            fwa_label=fwa_label,
            fwa_value=_wei_float(fwa_wei) if semantic_ok else None,
            detail=detail,
            source_badge=_source_badge(status, surface.available),
            source_kind="chain_state",
            measurement="derived",
            block_number=surface.block_number,
            observed_at=surface.observed_at,
            stale=stale,
            verified_source=True,
            integrity=status,
        )
        if surface.is_current or (
            (row["eth_value"] or 0) > 0
            or (row["fwa_value"] or 0) > 0
            or status != "ok"
        ):
            rows.append(row)

    group = state.group_pull
    group_status = _integrity_for(
        GROUP_PULL_MANIFEST,
        integrity,
        operational_warning=(
            group.distributor_enabled is False
            or (
                group.token_balance_wei is not None
                and group.accounted_fwa_wei is not None
                and group.token_balance_wei < group.accounted_fwa_wei
            )
        ),
    )
    group_counts = _counts(group.rounds, GROUP_PULL_STATE_NAMES)
    group_semantic_ok = group_status != "mismatch"
    if not group_semantic_ok:
        group_detail = "runtime/dependency integrity mismatch; metrics suppressed"
    elif not group.available:
        group_detail = "pack lifecycle unavailable"
    else:
        group_detail = (
            f"{group_counts['selling']} selling · {group_counts['buying']} buying · "
            f"{group_counts['collecting']} collecting · "
            f"{group_counts['distributing']} distributing · "
            f"{group_counts['expired']} expired"
        )
    rows.append(
        _project_row(
            family="group_pull",
            surface="group_pull",
            version=group.version,
            address=group.address,
            is_current=True,
            is_legacy_liability=False,
            lifecycle=(
                _group_lifecycle(group) if group_semantic_ok else "integrity mismatch"
            ),
            primary_label="packs created",
            primary_value=group.round_count if group_semantic_ok else None,
            primary_unit="packs",
            eth_label="accounted liability",
            eth_value=(
                _wei_float(group.accounted_eth_wei) if group_semantic_ok else None
            ),
            fwa_label="accounted liability",
            fwa_value=(
                _wei_float(group.accounted_fwa_wei) if group_semantic_ok else None
            ),
            detail=group_detail,
            source_badge=_source_badge(group_status, group.available),
            source_kind="chain_state",
            measurement="derived",
            block_number=group.block_number,
            observed_at=group.observed_at,
            stale=stale,
            verified_source=True,
            integrity=group_status,
        )
    )

    order_manifests = {
        (manifest.family, manifest.surface, manifest.version): manifest
        for manifest in ORDER_MANIFESTS
    }
    for factory in state.order_factories:
        manifest = order_manifests[(factory.family, factory.surface, factory.version)]
        status = _integrity_for(manifest, integrity)
        semantic_ok = status != "mismatch"
        lifecycle = "creation registry" if factory.available else "unavailable"
        if not semantic_ok:
            lifecycle = "integrity mismatch"
        detail = (
            "runtime/dependency integrity mismatch; factory semantics suppressed"
            if not semantic_ok
            else (
                "cumulative creations; active, filled, cancelled, and claimable "
                "states are not inferred from the factory counter"
            )
        )
        row = _project_row(
            family=factory.family,
            surface=factory.surface,
            version=factory.version,
            address=factory.address,
            is_current=factory.is_current,
            is_legacy_liability=False,
            lifecycle=lifecycle,
            primary_label="orders created",
            primary_value=factory.orders_created if semantic_ok else None,
            primary_unit="orders",
            eth_label="factory liability",
            eth_value=None,
            fwa_label="factory liability",
            fwa_value=None,
            detail=detail,
            source_badge=_source_badge(status, factory.available),
            source_kind="chain_state",
            measurement="measured",
            block_number=factory.block_number,
            observed_at=factory.observed_at,
            stale=stale,
            verified_source=True,
            integrity=status,
        )
        if factory.is_current or status != "ok":
            rows.append(row)
    return tuple(rows)


def normalize_events(
    read: PullPoolLogRead,
    *,
    integrity: PullPoolIntegrityRead | None = None,
    stale: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Convert strict-wei adapter events into exact NETWORK event rows."""

    if not isinstance(stale, bool):
        raise ValueError("stale must be a bool")
    manifests = {manifest.address: manifest for manifest in ALL_MANIFESTS}
    normalized: dict[str, dict[str, Any]] = {}
    for event in read.events:
        manifest = manifests[event.address]
        status = _integrity_for(manifest, integrity)
        semantic_ok = status != "mismatch"
        row = NetworkEventRow(
            event_id=event.event_id,
            ts=event.block_timestamp,
            tx_hash=event.tx_hash,
            log_index=event.log_index,
            origin=_origin(manifest),
            family=event.family,
            version=event.version,
            event_key=event.event_key if semantic_ok else "integrity_mismatch",
            event_label=event.event_label if semantic_ok else "Untrusted contract log",
            eth_amount=(
                _wei_float(event.eth_amount_wei) if semantic_ok else None
            ),
            fwa_amount=(
                _wei_float(event.fwa_amount_wei) if semantic_ok else None
            ),
            detail=(
                event.detail
                if semantic_ok
                else "runtime/dependency integrity mismatch; semantics suppressed"
            ),
            source_kind="chain_log",
            measurement="measured",
            block_number=event.block_number,
            observed_at=read.observed_at,
            stale=stale,
            verified_source=True if semantic_ok else False,
            integrity=status,
        ).model_dump()
        assert tuple(row) == NETWORK_EVENT_ROW_KEYS
        normalized[row["event_id"]] = row
    return tuple(
        sorted(
            normalized.values(),
            key=lambda row: (row["block_number"] or -1, row["log_index"]),
            reverse=True,
        )
    )


__all__ = [
    "ALL_MANIFESTS",
    "BlockCoverage",
    "GROUP_PULL_STATE_NAMES",
    "LOG_STREAMS",
    "LOG_STREAM_BY_ADDRESS",
    "LOG_STREAM_BY_KEY",
    "ORDER_MANIFESTS",
    "PULLPOOL_MANIFESTS",
    "PULLPOOL_STATE_NAMES",
    "STATE_CALLS",
    "GroupPullRoundState",
    "GroupPullSurfaceState",
    "LogProgress",
    "LogStream",
    "LogStreamRead",
    "OrderFactoryState",
    "PullPoolAdapter",
    "PullPoolEvent",
    "PullPoolHistory",
    "PullPoolIntegrityRead",
    "PullPoolLogRead",
    "PullPoolRead",
    "PullPoolRoundState",
    "PullPoolSurfaceState",
    "StreamCoverage",
    "SurfaceIntegrity",
    "accumulate_history",
    "build_project_rows",
    "normalize_events",
    "runtime_codehash",
]
