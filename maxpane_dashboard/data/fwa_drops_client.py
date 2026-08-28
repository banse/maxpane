"""Block-pinned enumeration of FWAIR launches.

The FWAIR manager is the only launch registry.  This client reads
``nextLaunchId()`` and walks every id below it; no launch address, name, or row
count is compiled into MAXPANE.  Manager and child state is read through the
existing state-pool Multicall3 client at one explicit block tag.

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
from maxpane_dashboard.data.fwa_ecosystem_models import DROP_PHASES, DropRow
from maxpane_dashboard.data.fwa_models import Wei
from maxpane_dashboard.data.fwa_projects import load_abi_resource
from maxpane_dashboard.data.keccak import keccak256_hex

logger = logging.getLogger(__name__)

_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_WEI_PER_TOKEN = 10**18
_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True)


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
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._drops_clock = clock

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
    ) -> FWAIRDropsRead:
        return FWAIRDropsRead(
            observed_at=observed_at,
            state_block=state_block,
            chain_head=state_block,
            block_timestamp=None,
            next_launch_id=None,
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

        launch_ids = list(range(1, next_launch_id))
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
        candidates: list[tuple[int, str]] = []
        for index, launch_id in enumerate(launch_ids):
            raw = _successful(
                launch_results[index] if index < len(launch_results) else None
            )
            address = _address(raw)
            if address is None or address == ZERO_ADDRESS:
                holes.append(launch_id)
                issues.append(f"launch_{launch_id}_address_unavailable")
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
        mismatch_ids: list[int] = []

        for candidate_index, (launch_id, address) in enumerate(candidates):
            start = candidate_index * stride
            result_slice = child_results[start : start + stride]
            if len(result_slice) != stride:
                holes.append(launch_id)
                issues.append(f"launch_{launch_id}_child_read_failed")
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
                issues.append(f"launch_{launch_id}_child_read_failed")
                continue

            actual_child_hash = await self._codehash(address, block_tag)
            if actual_child_hash is None:
                holes.append(launch_id)
                issues.append(f"launch_{launch_id}_child_code_unavailable")
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
                mismatch_ids.append(launch_id)
                issues.append(f"launch_{launch_id}_integrity_mismatch")
                mismatch_rows.append(
                    _mismatch_row(launch_id, address, state_block, observed_at)
                )
                continue
            if collection == ZERO_ADDRESS:
                holes.append(launch_id)
                issues.append(f"launch_{launch_id}_collection_unavailable")
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
                issues.append(f"launch_{pending.launch_id}_name_unavailable")
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

        rows = tuple(sorted((*valid_rows, *mismatch_rows), key=lambda row: row.launch_id))
        holes_tuple = tuple(sorted(set(holes)))
        mismatch_tuple = tuple(sorted(set(mismatch_ids)))
        if mismatch_tuple:
            integrity: Literal["ok", "warning", "mismatch", "unknown"] = "mismatch"
        elif issues:
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
            issues=tuple(issues),
        )


__all__ = [
    "COLLECTION_NAME_SELECTOR",
    "FWAIRDropsClient",
    "FWAIRDropsRead",
    "FWAIRLaunchState",
    "LAUNCH_SELECTORS",
    "MANAGER_SELECTORS",
    "phase_name",
    "runtime_codehash",
]
