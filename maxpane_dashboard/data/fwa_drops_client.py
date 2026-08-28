"""Block-pinned enumeration of FWAIR launches.

The FWAIR manager is the only launch registry.  This client reads
``nextLaunchId()`` and walks its ids in bounded pages; no launch address, name,
or row count is compiled into MAXPANE.  Page results accumulate in memory so a
stable registry is eventually covered without building a call list
proportional to an untrusted manager count.  Manager and child state is read
through the existing state-pool Multicall3 client at one explicit block tag.

Child semantics are published only when the live runtime hash matches the
manager's live ``launchRuntimeCodeHash()`` and the manager/core/token links all
agree.  A failed id is a local hole: enumeration always continues with later
ids.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.evm_abi import (
    ZERO_ADDRESS,
    decode_address,
    decode_string,
    decode_uint,
    encode_address,
    encode_uint,
    strip0x,
)
from maxpane_dashboard.data.fwa_client import FWAClient
from maxpane_dashboard.data.fwa_ecosystem_addresses import (
    FWA_CORE,
    FWA_TOKEN,
    FWAIR_MANAGER,
    FWAIR_WHITELIST_AUTHORITY,
    OFFICIAL_BY_ROLE,
)
from maxpane_dashboard.data.fwa_ecosystem_models import (
    DROP_PHASES,
    NETWORK_EVENT_ROW_KEYS,
    DropRow,
    NetworkEventRow,
)
from maxpane_dashboard.data.fwa_logs import FWALogClient
from maxpane_dashboard.data.fwa_models import Wei
from maxpane_dashboard.data.fwa_projects import load_abi_resource
from maxpane_dashboard.data.keccak import keccak256_hex

logger = logging.getLogger(__name__)

_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_WEI_PER_TOKEN = 10**18
_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True)

# One refresh reads roughly twenty child views plus one runtime hash per launch.
# Bound the page, not the registry: later launches stay discoverable and a
# hostile ``nextLaunchId`` cannot cause proportional allocation or RPC calls.
# Sixteen also leaves headroom under the manager's eight-second tier timeout.
MAX_LAUNCHES_PER_REFRESH = 16
_LAUNCH_RETRIES_PER_REFRESH = 4


# ---------------------------------------------------------------------------
# Vendored ABI -> immutable read selectors
# ---------------------------------------------------------------------------


def _function_signature(entry: Mapping[str, Any]) -> str:
    inputs = entry.get("inputs")
    if not isinstance(inputs, list):
        raise ValueError("ABI function inputs must be an array")
    types: list[str] = []
    for item in inputs:
        if not isinstance(item, Mapping) or not isinstance(item.get("type"), str):
            raise ValueError("ABI function input must declare a type")
        types.append(item["type"])
    return f"{entry['name']}({','.join(types)})"


def _view_selector(
    abi: Sequence[Mapping[str, Any]], name: str, inputs: tuple[str, ...] = ()
) -> str:
    matches = [
        entry
        for entry in abi
        if entry.get("type") == "function"
        and entry.get("name") == name
        and tuple(
            item.get("type")
            for item in entry.get("inputs", ())
            if isinstance(item, Mapping)
        )
        == inputs
    ]
    if len(matches) != 1:
        raise ValueError(f"vendored ABI has {len(matches)} matches for {name}{inputs}")
    entry = matches[0]
    if entry.get("stateMutability") not in {"view", "pure"}:
        raise ValueError(f"FWAIR read surface contains mutating function {name}")
    return keccak256_hex(_function_signature(entry).encode("utf-8"))[:10]


_MANAGER_ABI = load_abi_resource("abis/fwa/fwair_manager.json")
_LAUNCH_ABI = load_abi_resource("abis/fwa/fwair_launch.json")

MANAGER_SELECTORS: Mapping[str, str] = MappingProxyType(
    {
        "nextLaunchId()": _view_selector(_MANAGER_ABI, "nextLaunchId"),
        "launchRuntimeCodeHash()": _view_selector(
            _MANAGER_ABI, "launchRuntimeCodeHash"
        ),
        "fwa()": _view_selector(_MANAGER_ABI, "fwa"),
        "whitelistAuthority()": _view_selector(
            _MANAGER_ABI, "whitelistAuthority"
        ),
        "launches(uint256)": _view_selector(
            _MANAGER_ABI, "launches", ("uint256",)
        ),
        "isLaunch(address)": _view_selector(
            _MANAGER_ABI, "isLaunch", ("address",)
        ),
    }
)

_LAUNCH_FUNCTIONS: tuple[str, ...] = (
    "manager",
    "fwa",
    "rewardToken",
    "launchId",
    "collection",
    "phase",
    "registered",
    "supportStart",
    "supportDeadline",
    "tokenCount",
    "supportedCount",
    "supporterCount",
    "launchedCount",
    "terminalCount",
    "backingPrice",
    "totalRequiredBacking",
    "artistETHCredit",
    "totalPrincipalCredit",
    "supporterTokenReserve",
)
LAUNCH_SELECTORS: Mapping[str, str] = MappingProxyType(
    {f"{name}()": _view_selector(_LAUNCH_ABI, name) for name in _LAUNCH_FUNCTIONS}
)
COLLECTION_NAME_SELECTOR = keccak256_hex(b"name()")[:10]


def _event_signature(entry: Mapping[str, Any]) -> str:
    inputs = entry.get("inputs")
    if not isinstance(inputs, list):
        raise ValueError("ABI event inputs must be an array")
    return f"{entry['name']}({','.join(str(item['type']) for item in inputs)})"


_EVENT_PRESENTATION: Mapping[str, tuple[str, str, str | None, str | None]] = (
    MappingProxyType(
        {
            "LaunchRegistered": (
                "drop_created",
                "Drop created",
                "backingPrice",
                None,
            ),
            "CollectionActivated": (
                "launched",
                "Collection activated",
                "totalBacking",
                None,
            ),
            "LaunchEmergencyFailed": (
                "terminal",
                "Drop emergency failed",
                None,
                None,
            ),
            "PositionSupported": ("supported", "Position supported", "backing", None),
            "PositionLaunched": ("launched", "Position launched", "backing", None),
            "LaunchFailed": ("terminal", "Drop failed", "refundableBacking", None),
            "LaunchFullySupported": (
                "supported",
                "Drop fully supported",
                "totalBacking",
                None,
            ),
            "SupportReady": (
                "support_ready",
                "Support ready",
                "totalRequiredBacking",
                None,
            ),
            "FailedPositionFinalized": (
                "terminal",
                "Failed position finalized",
                "refundCredited",
                None,
            ),
            "UnlaunchedPositionFinalized": (
                "terminal",
                "Unlaunched position finalized",
                "refundCredited",
                None,
            ),
            "SupporterETHClaimed": (
                "claimed",
                "Supporter ETH claimed",
                "amount",
                None,
            ),
            "ArtistETHClaimed": (
                "claimed",
                "Artist ETH claimed",
                "amount",
                None,
            ),
            "ArtistETHAccrued": (
                "reward_accrued",
                "Artist ETH accrued",
                "amount",
                None,
            ),
            "PrincipalCredited": (
                "reward_accrued",
                "Supporter principal credited",
                "amount",
                None,
            ),
            "ListingFeeHarvested": (
                "reward_harvested",
                "Listing fee harvested",
                "amount",
                None,
            ),
            "FWAETHReceived": (
                "settled",
                "FWA ETH received",
                "amount",
                None,
            ),
            "SettlementPrincipalAssigned": (
                "settled",
                "Settlement principal assigned",
                "principalAmount",
                None,
            ),
            "SupporterTokensClaimed": (
                "claimed",
                "Supporter reward claimed",
                None,
                None,
            ),
            "SupporterTokensAccrued": (
                "reward_accrued",
                "Supporter reward accrued",
                None,
                None,
            ),
            "RewardTokensHarvested": (
                "reward_harvested",
                "Reward tokens harvested",
                None,
                None,
            ),
            "SupporterSharesInitialized": (
                "reward_initialized",
                "Supporter shares initialized",
                None,
                None,
            ),
            "NFTClaimed": ("claimed", "NFT claimed", None, None),
            "PhaseChanged": ("phase_changed", "Phase changed", None, None),
        }
    )
)


def _event_specs(
    abi: Sequence[Mapping[str, Any]],
) -> Mapping[str, Mapping[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    for entry in abi:
        name = entry.get("name")
        if entry.get("type") != "event" or name not in _EVENT_PRESENTATION:
            continue
        selected[keccak256_hex(_event_signature(entry).encode())] = entry
    return MappingProxyType(selected)


FWAIR_MANAGER_EVENT_SPECS = _event_specs(_MANAGER_ABI)
FWAIR_LAUNCH_EVENT_SPECS = _event_specs(_LAUNCH_ABI)


# ---------------------------------------------------------------------------
# Strict chain-state boundary
# ---------------------------------------------------------------------------


class FWAIRLaunchState(BaseModel):
    """One integrity-checked child snapshot, still wei-native."""

    model_config = _STRICT

    launch_id: int
    launch_address: str
    collection_address: str
    collection_name: str
    phase_index: int
    support_start: int | None
    support_deadline: int | None
    token_count: int | None
    supported_count: int | None
    supporter_count: int | None
    launched_count: int | None
    terminal_count: int | None
    backing_wei: Wei | None
    total_backing_wei: Wei | None
    artist_credit_wei: Wei | None
    supporter_principal_wei: Wei | None
    supporter_reserve_wei: Wei | None


class FWAIRDropsRead(BaseModel):
    """Result of one manager enumeration at a common state block."""

    model_config = _STRICT

    observed_at: float
    state_block: int | None
    chain_head: int | None
    block_timestamp: int | None
    next_launch_id: int | None
    available: bool
    integrity: Literal["ok", "warning", "mismatch", "unknown"]
    rows: tuple[DropRow, ...]
    holes: tuple[int, ...]
    integrity_mismatch_ids: tuple[int, ...]
    issues: tuple[str, ...]

    @property
    def valid_count(self) -> int:
        """Number of fully decoded rows (integrity warning rows excluded)."""

        return sum(row.integrity == "ok" for row in self.rows)


class FWAIREventRead(BaseModel):
    """One bounded FWAIR manager-or-child event page."""

    model_config = _STRICT

    observed_at: float
    address: str
    from_block: int
    to_block: int
    available: bool
    history_complete: bool
    page_complete: bool
    last_complete_block_hash: str | None
    events: tuple[NetworkEventRow, ...]
    unavailable_reason: str | None
    decode_failures: int = 0


def _event_quantity(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    try:
        parsed = int(value, 16 if value.startswith(("0x", "0X")) else 10)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _event_value(type_name: str, word: str) -> int | bool | str | None:
    if len(word) != 64:
        return None
    try:
        if type_name == "address":
            return decode_address("0x" + word)
        if type_name == "bool":
            value = int(word, 16)
            return bool(value) if value in (0, 1) else None
        if type_name.startswith("uint"):
            return int(word, 16)
    except ValueError:
        return None
    if type_name == "bytes32":
        return "0x" + word.lower()
    return None


def normalize_fwair_events(
    address: str,
    raw_logs: Sequence[Any],
    *,
    observed_at: float,
    from_block: int,
    to_block: int,
    integrity: Literal["ok", "warning", "mismatch", "unknown"] = "unknown",
    stale: bool = False,
) -> tuple[tuple[NetworkEventRow, ...], int]:
    """Decode one FWAIR address without trusting mismatched semantics."""

    if integrity not in {"ok", "warning", "mismatch", "unknown"}:
        raise ValueError("integrity must be ok, warning, mismatch, or unknown")
    if not isinstance(stale, bool):
        raise ValueError("stale must be bool")
    canonical_address = str(address).lower()
    if not _ADDRESS_RE.fullmatch(canonical_address):
        raise ValueError("FWAIR event address must be canonical")
    specs = (
        FWAIR_MANAGER_EVENT_SPECS
        if canonical_address == FWAIR_MANAGER
        else FWAIR_LAUNCH_EVENT_SPECS
    )
    semantic_ok = integrity != "mismatch"
    rows: dict[str, NetworkEventRow] = {}
    failures = 0
    for raw in raw_logs:
        if not isinstance(raw, Mapping) or raw.get("removed") is True:
            failures += 1
            continue
        topics = raw.get("topics")
        data = strip0x(str(raw.get("data") or ""))
        raw_address = str(raw.get("address") or "").lower()
        topic0 = (
            str(topics[0]).lower()
            if isinstance(topics, list) and topics
            else ""
        )
        entry = specs.get(topic0)
        inputs = () if entry is None else entry.get("inputs", ())
        if not isinstance(inputs, list):
            inputs = ()
        expected_topics = 1 + sum(
            item.get("indexed") is True
            for item in inputs
            if isinstance(item, Mapping)
        )
        expected_data_words = sum(
            item.get("indexed") is not True
            for item in inputs
            if isinstance(item, Mapping)
        )
        if (
            raw_address != canonical_address
            or entry is None
            or not isinstance(topics, list)
            or len(topics) != expected_topics
            or len(data) != expected_data_words * 64
        ):
            failures += 1
            continue
        values: dict[str, Any] = {}
        topic_index = 1
        data_index = 0
        valid = True
        for item in entry.get("inputs", ()):
            if not isinstance(item, Mapping):
                valid = False
                break
            if item.get("indexed") is True:
                if not isinstance(topics, list) or topic_index >= len(topics):
                    valid = False
                    break
                word = strip0x(str(topics[topic_index])).rjust(64, "0")
                topic_index += 1
            else:
                word = data[data_index * 64 : (data_index + 1) * 64]
                data_index += 1
            value = _event_value(str(item.get("type")), word)
            name = item.get("name")
            if not isinstance(name, str) or value is None:
                valid = False
                break
            values[name] = value
        block_number = _event_quantity(raw.get("blockNumber"))
        log_index = _event_quantity(raw.get("logIndex"))
        tx_hash = str(raw.get("transactionHash") or "").lower()
        if (
            not valid
            or block_number is None
            or not from_block <= block_number <= to_block
            or log_index is None
            or not _BYTES32_RE.fullmatch(tx_hash)
        ):
            failures += 1
            continue
        name = str(entry["name"])
        event_key, event_label, eth_field, fwa_field = _EVENT_PRESENTATION[name]
        if name in {
            "SupporterTokensClaimed",
            "SupporterTokensAccrued",
            "RewardTokensHarvested",
        } and values.get("token") == FWA_TOKEN:
            fwa_field = "amount"
            event_label = {
                "SupporterTokensClaimed": "Supporter FWA claimed",
                "SupporterTokensAccrued": "Supporter FWA accrued",
                "RewardTokensHarvested": "FWA rewards harvested",
            }[name]
        if name == "PhaseChanged" and semantic_ok:
            phase = phase_name(values.get("newPhase"))
            event_label = f"Phase {phase}"
            if phase in {"complete", "failed", "unwinding"}:
                event_key = "terminal"

        def amount(field: str | None) -> float | None:
            value = None if field is None else values.get(field)
            return value / _WEI_PER_TOKEN if isinstance(value, int) else None

        ignored = {field for field in (eth_field, fwa_field) if field is not None}
        detail_parts: list[str] = []
        for key, value in values.items():
            if key in ignored:
                continue
            if isinstance(value, str) and _ADDRESS_RE.fullmatch(value):
                detail_parts.append(f"{key} {value[:8]}…{value[-4:]}")
            elif isinstance(value, bool):
                detail_parts.append(f"{key} {'yes' if value else 'no'}")
            elif isinstance(value, int):
                detail_parts.append(f"{key} {value}")
        row = NetworkEventRow(
            event_id=f"1:{canonical_address}:{tx_hash}:{log_index}",
            ts=_event_quantity(
                raw.get("blockTimestamp", raw.get("timestamp"))
            ),
            tx_hash=tx_hash,
            log_index=log_index,
            origin=(
                "FWAIR Manager"
                if canonical_address == FWAIR_MANAGER
                else "FWAIR Drop"
            ),
            family="drop",
            version=None,
            event_key=event_key if semantic_ok else "integrity_mismatch",
            event_label=event_label if semantic_ok else "Untrusted contract log",
            eth_amount=amount(eth_field) if semantic_ok else None,
            fwa_amount=amount(fwa_field) if semantic_ok else None,
            detail=(
                " · ".join(detail_parts)
                if semantic_ok
                else "runtime/dependency integrity mismatch; semantics suppressed"
            ),
            source_kind="chain_log",
            measurement="measured",
            block_number=block_number,
            observed_at=observed_at,
            stale=stale,
            verified_source=semantic_ok,
            integrity=integrity,
        )
        assert tuple(row.model_dump()) == NETWORK_EVENT_ROW_KEYS
        rows[row.event_id] = row
    return (
        tuple(
            sorted(
                rows.values(),
                key=lambda row: (row.block_number or -1, row.log_index),
                reverse=True,
            )
        ),
        failures,
    )


_PHASE_BY_INDEX: Mapping[int, str] = MappingProxyType(
    {index: phase for index, phase in enumerate(DROP_PHASES[:-1])}
)


def phase_name(value: int) -> str:
    """Map the seven Solidity enum values to the frozen lowercase vocabulary."""

    if isinstance(value, bool) or not isinstance(value, int):
        return "unknown"
    return _PHASE_BY_INDEX.get(value, "unknown")


def runtime_codehash(raw_code: Any) -> str | None:
    """Return Ethereum's runtime keccak, or ``None`` for malformed RPC data."""

    if not isinstance(raw_code, str):
        return None
    raw = strip0x(raw_code)
    if len(raw) % 2:
        return None
    try:
        return keccak256_hex(bytes.fromhex(raw))
    except ValueError:
        return None


def _drop_row(
    state: FWAIRLaunchState,
    *,
    block_number: int,
    block_timestamp: int | None,
    observed_at: float,
) -> DropRow:
    phase = phase_name(state.phase_index)
    support_open: bool | None
    if phase == "unknown":
        support_open = None
    elif phase != "supporting":
        support_open = False
    elif (
        block_timestamp is not None
        and state.support_start is not None
        and state.support_deadline is not None
    ):
        support_open = (
            state.support_start <= block_timestamp <= state.support_deadline
        )
    else:
        support_open = None

    def token_amount(value: int | None) -> float | None:
        return None if value is None else value / _WEI_PER_TOKEN

    return DropRow(
        launch_id=state.launch_id,
        launch_address=state.launch_address,
        collection_address=state.collection_address,
        collection_name=state.collection_name,
        phase=phase,
        support_open=support_open,
        token_count=state.token_count,
        supported_count=state.supported_count,
        supporter_count=state.supporter_count,
        launched_count=state.launched_count,
        terminal_count=state.terminal_count,
        backing_eth=token_amount(state.backing_wei),
        total_backing_eth=token_amount(state.total_backing_wei),
        artist_credit_eth=token_amount(state.artist_credit_wei),
        supporter_principal_eth=token_amount(state.supporter_principal_wei),
        supporter_reserve_fwa=token_amount(state.supporter_reserve_wei),
        source_kind="chain_state",
        measurement="measured",
        block_number=block_number,
        observed_at=observed_at,
        stale=False,
        verified_source=True,
        integrity="ok",
    )


def _mismatch_row(launch_id: int, address: str, block: int, observed: float) -> DropRow:
    """Keep an integrity failure visible without publishing untrusted semantics."""

    return DropRow(
        launch_id=launch_id,
        launch_address=address,
        collection_address=None,
        collection_name=None,
        phase="unknown",
        support_open=None,
        token_count=None,
        supported_count=None,
        supporter_count=None,
        launched_count=None,
        terminal_count=None,
        backing_eth=None,
        total_backing_eth=None,
        artist_credit_eth=None,
        supporter_principal_eth=None,
        supporter_reserve_fwa=None,
        source_kind="chain_state",
        measurement="measured",
        block_number=block,
        observed_at=observed,
        stale=False,
        verified_source=False,
        integrity="mismatch",
    )


# ---------------------------------------------------------------------------
# Defensive static-output decoders
# ---------------------------------------------------------------------------


def _word(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = strip0x(raw)
    if len(value) != 64:
        return None
    try:
        bytes.fromhex(value)
    except ValueError:
        return None
    return "0x" + value.lower()


def _uint(raw: Any) -> int | None:
    value = _word(raw)
    return None if value is None else decode_uint(value)


def _address(raw: Any) -> str | None:
    value = _word(raw)
    if value is None:
        return None
    decoded = decode_address(value).lower()
    return decoded if _ADDRESS_RE.fullmatch(decoded) else None


def _bool(raw: Any) -> bool | None:
    value = _uint(raw)
    return None if value not in {0, 1} else bool(value)


def _bytes32(raw: Any) -> str | None:
    value = _word(raw)
    if value is None or not _BYTES32_RE.fullmatch(value):
        return None
    return value


def _successful(result: tuple[bool, str] | None) -> str | None:
    if result is None or not result[0]:
        return None
    return result[1]


def _decode_block_timestamp(raw: Any) -> int | None:
    if not isinstance(raw, Mapping):
        return None
    timestamp = raw.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        value = int(timestamp, 16)
    except ValueError:
        return None
    return value if value >= 0 else None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FWAIRDropsClient(FWAClient):
    """Enumerate and validate every FWAIR launch known to the live manager."""

    def __init__(
        self,
        *args: Any,
        clock: Callable[[], float] = time.time,
        log_endpoints: Sequence[str] | None = None,
        log_http_client: Any = None,
        log_min_call_interval: float = 0.05,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._drops_clock = clock
        self._log_endpoints = log_endpoints
        self._log_http_client = log_http_client
        self._log_min_call_interval = log_min_call_interval
        self._event_clients: dict[str, FWALogClient] = {}
        self._launch_rows: dict[int, DropRow] = {}
        self._launch_holes: dict[int, None] = {}
        self._launch_issues: dict[int, tuple[str, ...]] = {}
        self._launch_scan_cursor = 1
        self._known_next_launch_id: int | None = None
        self._known_launch_runtime_hash: str | None = None
        self._last_drop_state_block: int | None = None

    def _event_client(self, address: str) -> FWALogClient:
        client = self._event_clients.get(address)
        if client is None:
            client = FWALogClient(
                endpoints=self._log_endpoints,
                http_client=self._log_http_client,
                core_address=address,
                min_call_interval=self._log_min_call_interval,
            )
            self._event_clients[address] = client
        return client

    async def close(self) -> None:
        for client in self._event_clients.values():
            await client.close()
        self._event_clients.clear()
        await super().close()

    def _clear_launch_cache(self) -> None:
        self._launch_rows.clear()
        self._launch_holes.clear()
        self._launch_issues.clear()
        self._launch_scan_cursor = 1
        self._known_next_launch_id = None
        self._known_launch_runtime_hash = None
        self._last_drop_state_block = None

    def _prune_launch_cache(self, next_launch_id: int) -> None:
        """Discard accumulator entries outside the live manager id range."""

        for launch_id in tuple(self._launch_rows):
            if not 1 <= launch_id < next_launch_id:
                self._launch_rows.pop(launch_id, None)
        for launch_id in tuple(self._launch_holes):
            if not 1 <= launch_id < next_launch_id:
                self._launch_holes.pop(launch_id, None)
        for launch_id in tuple(self._launch_issues):
            if not 1 <= launch_id < next_launch_id:
                self._launch_issues.pop(launch_id, None)

    def _trim_launch_failure_metadata(self) -> None:
        """Keep hostile registries from growing retry metadata forever."""

        while len(self._launch_issues) > MAX_LAUNCHES_PER_REFRESH:
            launch_id = next(iter(self._launch_issues))
            self._launch_issues.pop(launch_id, None)
            self._launch_holes.pop(launch_id, None)
        for launch_id in tuple(self._launch_holes):
            if launch_id not in self._launch_issues:
                self._launch_holes.pop(launch_id, None)

    def _launch_page(
        self,
        *,
        next_launch_id: int,
        state_block: int,
        expected_child_hash: str,
    ) -> tuple[tuple[int, ...], int, bool]:
        """Choose at most one page, favoring newly appended launch ids."""

        reset = (
            (
                self._last_drop_state_block is not None
                and state_block < self._last_drop_state_block
            )
            or (
                self._known_next_launch_id is not None
                and next_launch_id < self._known_next_launch_id
            )
            or (
                self._known_launch_runtime_hash is not None
                and expected_child_hash != self._known_launch_runtime_hash
            )
        )
        known_next = None if reset else self._known_next_launch_id
        cursor = 1 if reset else self._launch_scan_cursor
        total = next_launch_id - 1
        if total <= MAX_LAUNCHES_PER_REFRESH:
            return tuple(range(1, next_launch_id)), 1, reset

        retry_ids = (
            ()
            if reset
            else tuple(
                launch_id
                for launch_id in self._launch_issues
                if 1 <= launch_id < next_launch_id
            )[:_LAUNCH_RETRIES_PER_REFRESH]
        )
        selected: list[int] = []
        selected_ids: set[int] = set()

        def add_ids(ids: Sequence[int]) -> None:
            for launch_id in ids:
                if len(selected) >= MAX_LAUNCHES_PER_REFRESH:
                    return
                if launch_id not in selected_ids:
                    selected.append(launch_id)
                    selected_ids.add(launch_id)

        # Always reserve one slot for the ordinary cursor.  New ids receive the
        # remaining priority capacity, while a small retry slice prevents a
        # transient failure from waiting for a huge cursor wrap.
        new_budget = MAX_LAUNCHES_PER_REFRESH - len(retry_ids) - 1
        if known_next is None:
            new_start = max(1, next_launch_id - new_budget)
            add_ids(range(new_start, next_launch_id))
        elif next_launch_id > known_next:
            new_start = max(known_next, next_launch_id - new_budget)
            add_ids(range(new_start, next_launch_id))
        add_ids(retry_ids)

        cursor_budget = MAX_LAUNCHES_PER_REFRESH - len(selected)
        start = cursor if 1 <= cursor <= total else 1
        end = min(total, start + cursor_budget - 1)
        add_ids(range(start, end + 1))
        next_cursor = 1 if end >= total else end + 1
        return tuple(selected), next_cursor, reset

    def _observed_at(self) -> float:
        value = self._drops_clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("drops clock must return epoch seconds")
        observed = float(value)
        if not math.isfinite(observed) or observed < 0.0:
            raise ValueError("drops clock must return finite epoch seconds")
        return observed

    def _empty(
        self,
        *,
        observed_at: float,
        state_block: int | None,
        integrity: Literal["mismatch", "unknown"],
        issue: str,
        next_launch_id: int | None = None,
    ) -> FWAIRDropsRead:
        return FWAIRDropsRead(
            observed_at=observed_at,
            state_block=state_block,
            chain_head=state_block,
            block_timestamp=None,
            next_launch_id=next_launch_id,
            available=False,
            integrity=integrity,
            rows=(),
            holes=(),
            integrity_mismatch_ids=(),
            issues=(issue,),
        )

    async def _codehash(self, address: str, block_tag: str) -> str | None:
        try:
            raw = await self._rpc("eth_getCode", [address, block_tag])
        except Exception as exc:  # noqa: BLE001 - one child must not stop later ids
            logger.warning("FWAIR code read failed for %s: %s", address, exc)
            return None
        return runtime_codehash(raw)

    async def fetch_drops(
        self, *, block_number: int | None = None
    ) -> FWAIRDropsRead:
        """Read all manager ids at one block; isolate failures to their launch id."""

        if isinstance(block_number, bool) or (
            block_number is not None and not isinstance(block_number, int)
        ):
            raise ValueError("block_number must be a non-negative int or None")
        if block_number is not None and block_number < 0:
            raise ValueError("block_number must be a non-negative int or None")

        observed_at = self._observed_at()
        state_block = block_number
        if state_block is None:
            fetched = await self.fetch_block_number()
            state_block = fetched if fetched > 0 else None
        if state_block is None:
            return self._empty(
                observed_at=observed_at,
                state_block=None,
                integrity="unknown",
                issue="state_block_unavailable",
            )

        block_tag = hex(state_block)
        manager_hash = await self._codehash(FWAIR_MANAGER, block_tag)
        if manager_hash is None:
            return self._empty(
                observed_at=observed_at,
                state_block=state_block,
                integrity="unknown",
                issue="manager_code_unavailable",
            )
        if manager_hash != OFFICIAL_BY_ROLE["fwair_manager"].runtime_codehash:
            self._clear_launch_cache()
            return self._empty(
                observed_at=observed_at,
                state_block=state_block,
                integrity="mismatch",
                issue="manager_codehash_mismatch",
            )

        header_signatures = (
            "nextLaunchId()",
            "launchRuntimeCodeHash()",
            "fwa()",
            "whitelistAuthority()",
        )
        header = await self._multicall(
            [(FWAIR_MANAGER, MANAGER_SELECTORS[signature]) for signature in header_signatures],
            block_tag,
        )
        values = [_successful(header[i] if i < len(header) else None) for i in range(4)]
        next_launch_id = _uint(values[0])
        expected_child_hash = _bytes32(values[1])
        manager_fwa = _address(values[2])
        manager_authority = _address(values[3])
        if (
            next_launch_id is None
            or next_launch_id < 1
            or expected_child_hash is None
            or expected_child_hash == "0x" + "0" * 64
        ):
            return self._empty(
                observed_at=observed_at,
                state_block=state_block,
                integrity="unknown",
                issue="manager_state_unavailable",
            )
        if manager_fwa != FWA_CORE or manager_authority != FWAIR_WHITELIST_AUTHORITY:
            self._clear_launch_cache()
            return self._empty(
                observed_at=observed_at,
                state_block=state_block,
                integrity="mismatch",
                issue="manager_dependency_mismatch",
            )
        issues: list[str] = []
        try:
            block_raw = await self._rpc(
                "eth_getBlockByNumber", [block_tag, False]
            )
        except Exception as exc:  # noqa: BLE001 - only support_open becomes unknown
            logger.warning("FWAIR block timestamp read failed: %s", exc)
            block_timestamp = None
        else:
            block_timestamp = _decode_block_timestamp(block_raw)
        if block_timestamp is None:
            issues.append("block_timestamp_unavailable")

        launch_ids, next_scan_cursor, reset_cache = self._launch_page(
            next_launch_id=next_launch_id,
            state_block=state_block,
            expected_child_hash=expected_child_hash,
        )
        launch_results = await self._multicall(
            [
                (
                    FWAIR_MANAGER,
                    MANAGER_SELECTORS["launches(uint256)"] + encode_uint(launch_id),
                )
                for launch_id in launch_ids
            ],
            block_tag,
        )

        holes: list[int] = []
        launch_issues: dict[int, list[str]] = {}

        def record_issue(launch_id: int, suffix: str) -> None:
            issue = f"launch_{launch_id}_{suffix}"
            launch_issues.setdefault(launch_id, []).append(issue)

        candidates: list[tuple[int, str]] = []
        for index, launch_id in enumerate(launch_ids):
            raw = _successful(
                launch_results[index] if index < len(launch_results) else None
            )
            address = _address(raw)
            if address is None or address == ZERO_ADDRESS:
                holes.append(launch_id)
                record_issue(launch_id, "address_unavailable")
                continue
            candidates.append((launch_id, address))

        child_signatures = tuple(f"{name}()" for name in _LAUNCH_FUNCTIONS)
        calls: list[tuple[str, str]] = []
        for _launch_id, address in candidates:
            calls.append(
                (
                    FWAIR_MANAGER,
                    MANAGER_SELECTORS["isLaunch(address)"] + encode_address(address),
                )
            )
            calls.extend((address, LAUNCH_SELECTORS[signature]) for signature in child_signatures)
        child_results = await self._multicall(calls, block_tag)
        stride = 1 + len(child_signatures)

        states_without_names: list[tuple[FWAIRLaunchState, str]] = []
        mismatch_rows: list[DropRow] = []

        for candidate_index, (launch_id, address) in enumerate(candidates):
            start = candidate_index * stride
            result_slice = child_results[start : start + stride]
            if len(result_slice) != stride:
                holes.append(launch_id)
                record_issue(launch_id, "child_read_failed")
                continue
            is_launch = _bool(_successful(result_slice[0]))
            raw_by_signature = {
                signature: _successful(result_slice[index + 1])
                for index, signature in enumerate(child_signatures)
            }

            child_manager = _address(raw_by_signature["manager()"])
            child_fwa = _address(raw_by_signature["fwa()"])
            child_token = _address(raw_by_signature["rewardToken()"])
            child_id = _uint(raw_by_signature["launchId()"])
            collection = _address(raw_by_signature["collection()"])
            phase_index = _uint(raw_by_signature["phase()"])
            registered = _bool(raw_by_signature["registered()"])
            critical = (
                is_launch,
                child_manager,
                child_fwa,
                child_token,
                child_id,
                collection,
                phase_index,
                registered,
            )
            if any(value is None for value in critical):
                holes.append(launch_id)
                record_issue(launch_id, "child_read_failed")
                continue

            actual_child_hash = await self._codehash(address, block_tag)
            if actual_child_hash is None:
                holes.append(launch_id)
                record_issue(launch_id, "child_code_unavailable")
                continue

            links_match = (
                is_launch is True
                and registered is True
                and child_manager == FWAIR_MANAGER
                and child_fwa == FWA_CORE
                and child_token == FWA_TOKEN
                and child_id == launch_id
            )
            if actual_child_hash != expected_child_hash or not links_match:
                record_issue(launch_id, "integrity_mismatch")
                mismatch_rows.append(
                    _mismatch_row(launch_id, address, state_block, observed_at)
                )
                continue
            if collection == ZERO_ADDRESS:
                holes.append(launch_id)
                record_issue(launch_id, "collection_unavailable")
                continue

            # The name is filled after one collection-name Multicall below.
            states_without_names.append(
                (
                    FWAIRLaunchState(
                        launch_id=launch_id,
                        launch_address=address,
                        collection_address=collection,
                        collection_name="pending",
                        phase_index=phase_index,
                        support_start=_uint(raw_by_signature["supportStart()"]),
                        support_deadline=_uint(raw_by_signature["supportDeadline()"]),
                        token_count=_uint(raw_by_signature["tokenCount()"]),
                        supported_count=_uint(raw_by_signature["supportedCount()"]),
                        supporter_count=_uint(raw_by_signature["supporterCount()"]),
                        launched_count=_uint(raw_by_signature["launchedCount()"]),
                        terminal_count=_uint(raw_by_signature["terminalCount()"]),
                        backing_wei=_uint(raw_by_signature["backingPrice()"]),
                        total_backing_wei=_uint(
                            raw_by_signature["totalRequiredBacking()"]
                        ),
                        artist_credit_wei=_uint(
                            raw_by_signature["artistETHCredit()"]
                        ),
                        supporter_principal_wei=_uint(
                            raw_by_signature["totalPrincipalCredit()"]
                        ),
                        supporter_reserve_wei=_uint(
                            raw_by_signature["supporterTokenReserve()"]
                        ),
                    ),
                    collection,
                )
            )

        name_results = await self._multicall(
            [(collection, COLLECTION_NAME_SELECTOR) for _, collection in states_without_names],
            block_tag,
        )
        valid_rows: list[DropRow] = []
        for index, (pending, _collection) in enumerate(states_without_names):
            raw_name = _successful(
                name_results[index] if index < len(name_results) else None
            )
            name = decode_string(raw_name or "")
            if name is None or not name.strip():
                holes.append(pending.launch_id)
                record_issue(pending.launch_id, "name_unavailable")
                continue
            state = pending.model_copy(update={"collection_name": name})
            valid_rows.append(
                _drop_row(
                    state,
                    block_number=state_block,
                    block_timestamp=block_timestamp,
                    observed_at=observed_at,
                )
            )

        if reset_cache:
            self._clear_launch_cache()
        self._prune_launch_cache(next_launch_id)
        refreshed_rows = {
            row.launch_id: row for row in (*valid_rows, *mismatch_rows)
        }
        for launch_id in launch_ids:
            self._launch_holes.pop(launch_id, None)
            self._launch_issues.pop(launch_id, None)
            row = refreshed_rows.get(launch_id)
            if row is not None:
                self._launch_rows[launch_id] = row
        for launch_id in holes:
            self._launch_holes[launch_id] = None
        self._launch_issues.update(
            {
                launch_id: tuple(values)
                for launch_id, values in launch_issues.items()
            }
        )
        self._trim_launch_failure_metadata()
        self._launch_scan_cursor = next_scan_cursor
        self._known_next_launch_id = next_launch_id
        self._known_launch_runtime_hash = expected_child_hash
        self._last_drop_state_block = state_block

        fresh_ids = set(refreshed_rows)
        rows = tuple(
            row
            if launch_id in fresh_ids
            else row.model_copy(update={"stale": True})
            for launch_id, row in sorted(self._launch_rows.items())
        )
        holes_tuple = tuple(sorted(self._launch_holes))
        mismatch_tuple = tuple(
            row.launch_id for row in rows if row.integrity == "mismatch"
        )
        cached_issues = tuple(
            issue
            for launch_id in sorted(self._launch_issues)
            for issue in self._launch_issues[launch_id]
        )
        global_issues = tuple(issues)
        partial = len(launch_ids) < next_launch_id - 1
        aggregate_issues = (
            global_issues
            + cached_issues
            + (("launch_enumeration_partial",) if partial else ())
        )
        if mismatch_tuple:
            integrity: Literal["ok", "warning", "mismatch", "unknown"] = "mismatch"
        elif aggregate_issues:
            integrity = "warning"
        else:
            integrity = "ok"
        return FWAIRDropsRead(
            observed_at=observed_at,
            state_block=state_block,
            chain_head=state_block,
            block_timestamp=block_timestamp,
            next_launch_id=next_launch_id,
            available=True,
            integrity=integrity,
            rows=rows,
            holes=holes_tuple,
            integrity_mismatch_ids=mismatch_tuple,
            issues=aggregate_issues,
        )

    async def fetch_events(
        self,
        address: str,
        *,
        from_block: int,
        to_block: int,
        history_complete: bool = False,
        integrity: Literal["ok", "warning", "mismatch", "unknown"] = "unknown",
    ) -> FWAIREventRead:
        """Read one dynamic manager/child stream through Pool B."""

        canonical_address = str(address).lower()
        if not _ADDRESS_RE.fullmatch(canonical_address):
            raise ValueError("FWAIR event address must be canonical")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (from_block, to_block)
        ):
            raise ValueError("FWAIR event bounds must be non-negative ints")
        if from_block > to_block:
            raise ValueError("FWAIR event from_block must not exceed to_block")
        if not isinstance(history_complete, bool):
            raise ValueError("history_complete must be bool")
        if integrity not in {"ok", "warning", "mismatch", "unknown"}:
            raise ValueError("integrity must be ok, warning, mismatch, or unknown")
        observed_at = self._observed_at()
        client = self._event_client(canonical_address)
        specs = (
            FWAIR_MANAGER_EVENT_SPECS
            if canonical_address == FWAIR_MANAGER
            else FWAIR_LAUNCH_EVENT_SPECS
        )
        try:
            raw_logs = await client.get_logs(
                [list(specs)], from_block, to_block
            )
        except Exception as exc:  # noqa: BLE001 -- independent Pool-B failure
            logger.warning("FWAIR logs unavailable for %s: %s", canonical_address, exc)
            return FWAIREventRead(
                observed_at=observed_at,
                address=canonical_address,
                from_block=from_block,
                to_block=to_block,
                available=False,
                history_complete=False,
                page_complete=False,
                last_complete_block_hash=None,
                events=(),
                unavailable_reason="FWAIR logs unavailable",
            )
        events, failures = normalize_fwair_events(
            canonical_address,
            raw_logs,
            observed_at=observed_at,
            from_block=from_block,
            to_block=to_block,
            integrity=integrity,
        )
        block_hash = await client.fetch_block_hash(to_block)
        complete = failures == 0 and block_hash is not None
        return FWAIREventRead(
            observed_at=observed_at,
            address=canonical_address,
            from_block=from_block,
            to_block=to_block,
            available=True,
            history_complete=history_complete and complete,
            page_complete=complete,
            last_complete_block_hash=block_hash if complete else None,
            events=events,
            unavailable_reason=(
                None if complete else "FWAIR event page incomplete"
            ),
            decode_failures=failures,
        )


__all__ = [
    "COLLECTION_NAME_SELECTOR",
    "FWAIRDropsClient",
    "FWAIRDropsRead",
    "FWAIREventRead",
    "FWAIR_LAUNCH_EVENT_SPECS",
    "FWAIR_MANAGER_EVENT_SPECS",
    "FWAIRLaunchState",
    "LAUNCH_SELECTORS",
    "MAX_LAUNCHES_PER_REFRESH",
    "MANAGER_SELECTORS",
    "phase_name",
    "normalize_fwair_events",
    "runtime_codehash",
]
