"""Pinned FWAP v1/v2 state, integrity, events, and optional API context.

Chain state is authoritative.  Every House, Share, Receipt dependency, FWA
listing, balance, and runtime read carries the caller's explicit block tag.
The optional project snapshot is disabled by default and can only annotate a
row after supplying its own source block and timestamp; it never replaces a
chain value.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.evm_abi import (
    ZERO_ADDRESS,
    decode_address,
    decode_uint,
    encode_address,
    encode_uint,
    strip0x,
)
from maxpane_dashboard.data.fwa_client import FWAClient
from maxpane_dashboard.data.fwa_ecosystem_addresses import FWA_CORE, FWA_TOKEN
from maxpane_dashboard.data.fwa_ecosystem_models import (
    NETWORK_EVENT_ROW_KEYS,
    PROJECT_ROW_KEYS,
    NetworkEventRow,
    ProjectRow,
)
from maxpane_dashboard.data.fwa_models import Wei
from maxpane_dashboard.data.keccak import keccak256_hex

from .base import ProjectManifest, load_abi_resource, load_manifest_abi
from .registry import get_project_manifest

_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True)
_WEI_PER_TOKEN = 10**18
_MAX_POSITIONS = 20_000
_API_STALE_AFTER_SECONDS = 120.0
_API_TIMEOUT_SECONDS = 6.0

IntegrityStatus = Literal["ok", "warning", "mismatch", "unknown"]
PositionLifecycle = Literal[
    "none", "inventory", "listed", "returned", "recovery", "lost", "exited", "unknown"
]
ListingLifecycle = Literal[
    "none", "active", "allocated", "withdrawn", "settled", "unknown"
]

POSITION_STATES: tuple[PositionLifecycle, ...] = (
    "none",
    "inventory",
    "listed",
    "returned",
    "recovery",
    "lost",
    "exited",
)
LISTING_STATES: tuple[ListingLifecycle, ...] = (
    "none",
    "active",
    "allocated",
    "withdrawn",
    "settled",
)


def _manifest(version: str, role: str) -> ProjectManifest:
    return get_project_manifest("fwap", role, version, role)


FWAP_MANIFESTS: tuple[ProjectManifest, ...] = tuple(
    _manifest(version, role)
    for version in ("v1", "v2")
    for role in ("house", "share", "receipt")
)
FWAP_MANIFEST_BY_VERSION_ROLE: Mapping[tuple[str, str], ProjectManifest] = {
    (manifest.version, manifest.role): manifest for manifest in FWAP_MANIFESTS
}
FWAP_VERSIONS: tuple[str, str] = ("v1", "v2")


def _abi_function(
    manifest: ProjectManifest, name: str, inputs: tuple[str, ...] = ()
) -> Mapping[str, Any]:
    matches = []
    for entry in load_manifest_abi(manifest):
        if entry.get("type") != "function" or entry.get("name") != name:
            continue
        declared = tuple(item.get("type") for item in entry.get("inputs") or ())
        if declared == inputs:
            matches.append(entry)
    if len(matches) != 1:
        raise ValueError(
            f"{manifest.abi_resource} has {len(matches)} matches for {name}{inputs}"
        )
    if matches[0].get("stateMutability") not in {"view", "pure"}:
        raise ValueError(f"FWAP read surface contains mutating function {name}")
    return matches[0]


def _signature(entry: Mapping[str, Any]) -> str:
    inputs = ",".join(str(item.get("type")) for item in entry.get("inputs") or ())
    return f"{entry['name']}({inputs})"


def _selector(
    manifest: ProjectManifest, name: str, inputs: tuple[str, ...] = ()
) -> str:
    return keccak256_hex(_signature(_abi_function(manifest, name, inputs)).encode())[:10]


_HOUSE_V2 = FWAP_MANIFEST_BY_VERSION_ROLE[("v2", "house")]
_FWA_CORE_ABI = load_abi_resource("abis/fwa/fwa_core.json")


def _core_selector(name: str, inputs: tuple[str, ...]) -> str:
    matches = [
        entry
        for entry in _FWA_CORE_ABI
        if entry.get("type") == "function"
        and entry.get("name") == name
        and tuple(item.get("type") for item in entry.get("inputs") or ()) == inputs
    ]
    if len(matches) != 1 or matches[0].get("stateMutability") != "view":
        raise ValueError(f"vendored FWA ABI lacks unique view {name}{inputs}")
    return keccak256_hex(_signature(matches[0]).encode())[:10]


SEL_LISTINGS = _core_selector("listings", ("uint256",))
SEL_BALANCE_OF = keccak256_hex(b"balanceOf(address)")[:10]


@dataclass(frozen=True, slots=True)
class StateCall:
    version: str
    field: str
    address: str
    calldata: str
    output: Literal["uint", "bool", "epoch"] = "uint"


def _state_calls() -> tuple[StateCall, ...]:
    calls: list[StateCall] = []
    for version in FWAP_VERSIONS:
        house = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "house")]
        share = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "share")]
        for field, getter in (
            ("next_position_id", "nextPositionId"),
            ("book_nav_wei", "bookNav"),
            ("liquid_capital_wei", "liquidCapital"),
            ("queued_capital_wei", "queuedCapital"),
            ("settlement_inbox_wei", "settlementInbox"),
            ("house_share_supply_wei", "totalSupply"),
        ):
            calls.append(
                StateCall(version, field, house.address, _selector(house, getter))
            )
        calls.append(
            StateCall(
                version,
                "fee_reconciliation_required",
                house.address,
                _selector(house, "feeReconciliationRequired"),
                "bool",
            )
        )
        if version == "v2":
            calls.append(
                StateCall(
                    version,
                    "epoch",
                    house.address,
                    _selector(house, "epochInfo"),
                    "epoch",
                )
            )
        calls.extend(
            (
                StateCall(
                    version,
                    "share_supply_wei",
                    share.address,
                    _selector(share, "totalSupply"),
                ),
                StateCall(
                    version,
                    "fwa_liability_wei",
                    share.address,
                    _selector(share, "fwaLiability"),
                ),
                StateCall(
                    version,
                    "house_fwa_balance_wei",
                    FWA_TOKEN,
                    SEL_BALANCE_OF + encode_address(house.address),
                ),
                StateCall(
                    version,
                    "share_fwa_balance_wei",
                    FWA_TOKEN,
                    SEL_BALANCE_OF + encode_address(share.address),
                ),
            )
        )
    return tuple(calls)


STATE_CALLS = _state_calls()


class FWAPPosition(BaseModel):
    """One House position with its downstream FWA listing status."""

    model_config = _STRICT

    position_id: int
    collection: str
    token_id: int
    backing_wei: Wei
    listing_id: int
    state: int
    lifecycle: PositionLifecycle
    receipt_owner: str
    listing_status: int | None
    listing_lifecycle: ListingLifecycle
    core_listing_match: bool | None


class FWAPSurfaceState(BaseModel):
    """One generation's complete, wei-native state at a single block."""

    model_config = _STRICT

    version: str
    address: str
    share_address: str
    receipt_address: str
    is_current: bool
    observed_at: float
    block_number: int
    available: bool
    positions_created: int | None
    positions: tuple[FWAPPosition, ...]
    position_counts_complete: bool
    inventory_count: int | None
    listed_count: int | None
    active_count: int | None
    allocated_count: int | None
    returned_count: int | None
    recovery_count: int | None
    lost_count: int | None
    exited_count: int | None
    terminal_count: int | None
    active_receipt_count: int | None
    book_nav_wei: Wei | None
    liquid_capital_wei: Wei | None
    queued_capital_wei: Wei | None
    settlement_inbox_wei: Wei | None
    house_eth_balance_wei: Wei | None
    house_share_supply_wei: Wei | None
    share_supply_wei: Wei | None
    house_fwa_balance_wei: Wei | None
    share_fwa_balance_wei: Wei | None
    total_fwa_balance_wei: Wei | None
    fwa_liability_wei: Wei | None
    fee_reconciliation_required: bool | None
    current_epoch: int | None
    epoch_duration: int | None
    pending_epoch_duration: int | None
    epoch_ends_at: int | None
    invariant_failures: tuple[str, ...]
    failed_fields: tuple[str, ...]


class FWAPRead(BaseModel):
    model_config = _STRICT

    observed_at: float
    block_number: int
    surfaces: tuple[FWAPSurfaceState, ...]

    def surface(self, version: str) -> FWAPSurfaceState:
        for surface in self.surfaces:
            if surface.version == version:
                return surface
        raise KeyError(version)


class ManifestIntegrity(BaseModel):
    model_config = _STRICT

    version: str
    role: str
    address: str
    block_number: int
    codehash_match: bool | None
    dependency_matches: tuple[tuple[str, bool | None], ...]
    status: IntegrityStatus


class FWAPIntegrityRead(BaseModel):
    model_config = _STRICT

    observed_at: float
    block_number: int
    surfaces: tuple[ManifestIntegrity, ...]

    def status_for_version(self, version: str) -> IntegrityStatus:
        selected = [surface.status for surface in self.surfaces if surface.version == version]
        if any(status == "mismatch" for status in selected):
            return "mismatch"
        if not selected or any(status == "unknown" for status in selected):
            return "unknown"
        if any(status == "warning" for status in selected):
            return "warning"
        return "ok"


class FWAPApiSnapshot(BaseModel):
    """Anchored project-API context; never a source for chain metrics."""

    model_config = _STRICT

    source_block: int
    source_timestamp: float
    stale: bool
    projected_inventory_count: int | None
    inventory_counts: tuple[tuple[str, int], ...]


class FWAPApiRead(BaseModel):
    model_config = _STRICT

    observed_at: float
    available: bool
    accepted: bool
    reason: str
    snapshot: FWAPApiSnapshot | None


class FWAPEvent(BaseModel):
    model_config = _STRICT

    address: str
    role: str
    version: str
    event_key: str
    event_label: str
    block_number: int
    block_timestamp: int | None
    tx_hash: str
    log_index: int
    eth_amount_wei: Wei | None
    fwa_amount_wei: Wei | None
    detail: str

    @property
    def event_id(self) -> str:
        return f"1:{self.address}:{self.tx_hash}:{self.log_index}"


class FWAPEventRead(BaseModel):
    model_config = _STRICT

    observed_at: float
    events: tuple[FWAPEvent, ...]


def _finite_time(clock: Callable[[], float], label: str) -> float:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} clock must return epoch seconds")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} clock must return finite epoch seconds")
    return value


def _block_tag(block_number: int) -> str:
    if (
        isinstance(block_number, bool)
        or not isinstance(block_number, int)
        or block_number < 0
    ):
        raise ValueError("block_number must be a non-negative int")
    return hex(block_number)


def _hex_words(raw: Any, count: int) -> str | None:
    if not isinstance(raw, str) or not raw.startswith("0x"):
        return None
    value = strip0x(raw)
    if len(value) != count * 64:
        return None
    try:
        bytes.fromhex(value)
    except ValueError:
        return None
    return "0x" + value.lower()


def _uint(raw: Any) -> int | None:
    value = _hex_words(raw, 1)
    return None if value is None else decode_uint(value)


def _bool(raw: Any) -> bool | None:
    value = _uint(raw)
    return None if value not in (0, 1) else bool(value)


def _epoch(raw: Any) -> tuple[int, int, int, int] | None:
    value = _hex_words(raw, 4)
    if value is None:
        return None
    return tuple(decode_uint(value, index) for index in range(4))  # type: ignore[return-value]


def _hex_quantity(raw: Any) -> int | None:
    if not isinstance(raw, str) or not raw.startswith("0x") or len(raw) <= 2:
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None
    return value if value >= 0 else None


def _address_word(raw: str, index: int) -> str:
    return decode_address(raw, index).lower()


def _position(position_id: int, raw: Any) -> FWAPPosition | None:
    value = _hex_words(raw, 6)
    if value is None:
        return None
    collection = _address_word(value, 0)
    state = decode_uint(value, 4)
    if collection == ZERO_ADDRESS or state <= 0 or state >= len(POSITION_STATES):
        return None
    receipt_owner = _address_word(value, 5)
    return FWAPPosition(
        position_id=position_id,
        collection=collection,
        token_id=decode_uint(value, 1),
        backing_wei=decode_uint(value, 2),
        listing_id=decode_uint(value, 3),
        state=state,
        lifecycle=POSITION_STATES[state],
        receipt_owner=receipt_owner,
        listing_status=None,
        listing_lifecycle="unknown",
        core_listing_match=None,
    )


def _listing(position: FWAPPosition, raw: Any, house: str) -> FWAPPosition | None:
    value = _hex_words(raw, 11)
    if value is None:
        return None
    status = decode_uint(value, 10)
    if status >= len(LISTING_STATES):
        return None
    matches = (
        status != 0
        and _address_word(value, 0) == position.collection
        and _address_word(value, 1) == house
        and decode_uint(value, 3) == position.token_id
        and decode_uint(value, 5) == position.backing_wei
    )
    return position.model_copy(
        update={
            "listing_status": status,
            "listing_lifecycle": LISTING_STATES[status],
            "core_listing_match": matches,
        }
    )


def runtime_codehash(raw_code: Any) -> str | None:
    if not isinstance(raw_code, str):
        return None
    raw = strip0x(raw_code)
    if not raw or len(raw) % 2:
        return None
    try:
        return keccak256_hex(bytes.fromhex(raw))
    except ValueError:
        return None


def _integrity_status(
    codehash: bool | None, dependencies: Sequence[bool | None]
) -> IntegrityStatus:
    values = (codehash, *dependencies)
    if any(value is False for value in values):
        return "mismatch"
    if any(value is None for value in values):
        return "unknown"
    return "ok"


class FWAPAdapter(FWAClient):
    """Read-only FWAP adapter with independently injectable state and API HTTP."""

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        state_endpoints: Sequence[str] | None = None,
        snapshot_url: str | None = None,
        api_http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
        min_call_interval: float = 0.05,
        backoff_seconds: tuple[float, ...] = (0.4, 1.2),
    ) -> None:
        if isinstance(state_endpoints, (str, bytes)):
            raise ValueError("state_endpoints must be a sequence of URLs")
        endpoints = tuple(state_endpoints or ())
        if state_endpoints is not None and not endpoints:
            raise ValueError("state_endpoints cannot be empty")
        kwargs: dict[str, Any] = {
            "http_client": http_client,
            "inter_call_delay": min_call_interval,
            "backoff_seconds": backoff_seconds,
        }
        if endpoints:
            kwargs["primary_rpc"] = endpoints[0]
            kwargs["fallback_rpcs"] = list(endpoints[1:])
        super().__init__(**kwargs)
        if endpoints:
            # FWAClient maps an empty fallback list to its defaults.  Preserve
            # the caller's exact injected endpoint set instead.
            self._fallback_rpcs = list(endpoints[1:])
        if snapshot_url is not None:
            parsed = urlparse(snapshot_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or bool(parsed.query)
                or bool(parsed.fragment)
            ):
                raise ValueError("snapshot_url must be a credential-free HTTPS URL")
        self._snapshot_url = snapshot_url
        self._api_client = api_http_client
        self._owns_api_client = False
        if snapshot_url is not None and self._api_client is None:
            self._api_client = httpx.AsyncClient(
                timeout=httpx.Timeout(_API_TIMEOUT_SECONDS),
                follow_redirects=False,
                headers={"Accept": "application/json"},
            )
            self._owns_api_client = True
        self._fwap_clock = clock

    def _now(self) -> float:
        return _finite_time(self._fwap_clock, "FWAP")

    async def close(self) -> None:
        if self._owns_api_client and self._api_client is not None:
            await self._api_client.aclose()
        await super().close()

    async def fetch_state(self, block_number: int) -> FWAPRead:
        """Read both generations and all positions at exactly ``block_number``."""

        tag = _block_tag(block_number)
        observed_at = self._now()
        results = await self._multicall(
            [(call.address, call.calldata) for call in STATE_CALLS], tag
        )
        values: dict[str, dict[str, Any]] = {version: {} for version in FWAP_VERSIONS}
        failed: dict[str, list[str]] = {version: [] for version in FWAP_VERSIONS}
        for index, call in enumerate(STATE_CALLS):
            ok, raw = results[index] if index < len(results) else (False, "0x")
            decoded: Any = None
            if ok:
                if call.output == "bool":
                    decoded = _bool(raw)
                elif call.output == "epoch":
                    decoded = _epoch(raw)
                else:
                    decoded = _uint(raw)
            if decoded is None:
                failed[call.version].append(call.field)
            values[call.version][call.field] = decoded

        position_specs: list[tuple[str, int, str]] = []
        for version in FWAP_VERSIONS:
            next_id = values[version].get("next_position_id")
            if (
                isinstance(next_id, int)
                and not isinstance(next_id, bool)
                and 1 <= next_id <= _MAX_POSITIONS + 1
            ):
                house = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "house")]
                position_specs.extend(
                    (version, position_id, house.address)
                    for position_id in range(1, next_id)
                )
            elif next_id is not None:
                values[version]["next_position_id"] = None
                failed[version].append("next_position_id_out_of_range")

        position_results = await self._multicall(
            [
                (
                    house,
                    _selector(
                        FWAP_MANIFEST_BY_VERSION_ROLE[(version, "house")],
                        "position",
                        ("uint256",),
                    )
                    + encode_uint(position_id),
                )
                for version, position_id, house in position_specs
            ],
            tag,
        )
        positions: dict[str, list[FWAPPosition]] = {
            version: [] for version in FWAP_VERSIONS
        }
        for index, (version, position_id, _house) in enumerate(position_specs):
            ok, raw = (
                position_results[index]
                if index < len(position_results)
                else (False, "0x")
            )
            decoded = _position(position_id, raw) if ok else None
            if decoded is None:
                failed[version].append(f"position:{position_id}")
            else:
                positions[version].append(decoded)

        listing_specs: list[tuple[str, int, FWAPPosition, str]] = []
        for version in FWAP_VERSIONS:
            house = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "house")].address
            for position in positions[version]:
                if position.lifecycle == "listed" and position.listing_id == 0:
                    failed[version].append("listing:0")
            listing_specs.extend(
                (version, index, position, house)
                for index, position in enumerate(positions[version])
                if position.lifecycle == "listed" and position.listing_id > 0
            )
        listing_results = await self._multicall(
            [
                (FWA_CORE, SEL_LISTINGS + encode_uint(position.listing_id))
                for _version, _index, position, _house in listing_specs
            ],
            tag,
        )
        for result_index, (version, position_index, position, house) in enumerate(
            listing_specs
        ):
            ok, raw = (
                listing_results[result_index]
                if result_index < len(listing_results)
                else (False, "0x")
            )
            decoded = _listing(position, raw, house) if ok else None
            if decoded is None:
                failed[version].append(f"listing:{position.listing_id}")
            else:
                positions[version][position_index] = decoded

        eth_balances: dict[str, int | None] = {}
        for version in FWAP_VERSIONS:
            house = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "house")]
            try:
                raw_balance = await self._rpc(
                    "eth_getBalance", [house.address, tag]
                )
            except RuntimeError:
                balance = None
            else:
                balance = _hex_quantity(raw_balance)
            eth_balances[version] = balance
            if balance is None:
                failed[version].append("house_eth_balance_wei")

        surfaces: list[FWAPSurfaceState] = []
        for version in FWAP_VERSIONS:
            house = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "house")]
            share = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "share")]
            receipt = FWAP_MANIFEST_BY_VERSION_ROLE[(version, "receipt")]
            data = values[version]
            next_id = data.get("next_position_id")
            created = next_id - 1 if isinstance(next_id, int) else None
            decoded_positions = tuple(positions[version])
            positions_complete = (
                created is not None
                and len(decoded_positions) == created
                and not any(field.startswith("listing:") for field in failed[version])
            )

            def count_position(lifecycle: str) -> int | None:
                if not positions_complete:
                    return None
                return sum(item.lifecycle == lifecycle for item in decoded_positions)

            inventory = count_position("inventory")
            listed = count_position("listed")
            returned = count_position("returned")
            recovery = count_position("recovery")
            lost = count_position("lost")
            exited = count_position("exited")
            active = (
                sum(item.listing_lifecycle == "active" for item in decoded_positions)
                if positions_complete
                else None
            )
            allocated = (
                sum(item.listing_lifecycle == "allocated" for item in decoded_positions)
                if positions_complete
                else None
            )
            unsynced_terminal = (
                sum(
                    item.lifecycle == "listed"
                    and item.listing_lifecycle in {"withdrawn", "settled"}
                    for item in decoded_positions
                )
                if positions_complete
                else None
            )
            terminal = (
                (lost or 0) + (exited or 0) + (unsynced_terminal or 0)
                if positions_complete
                else None
            )
            active_receipts = (
                sum(
                    item.lifecycle in {"inventory", "listed", "returned", "recovery"}
                    for item in decoded_positions
                )
                if positions_complete
                else None
            )

            house_fwa = data.get("house_fwa_balance_wei")
            share_fwa = data.get("share_fwa_balance_wei")
            total_fwa = (
                house_fwa + share_fwa
                if isinstance(house_fwa, int) and isinstance(share_fwa, int)
                else None
            )
            invariants: list[str] = []
            if (
                data.get("house_share_supply_wei") is not None
                and data.get("share_supply_wei") is not None
                and data["house_share_supply_wei"] != data["share_supply_wei"]
            ):
                invariants.append("share_supply_mismatch")
            if (
                total_fwa is not None
                and data.get("fwa_liability_wei") is not None
                and total_fwa < data["fwa_liability_wei"]
            ):
                invariants.append("fwa_liability_unfunded")
            if (
                data.get("book_nav_wei") is not None
                and data.get("liquid_capital_wei") is not None
                and data["book_nav_wei"] < data["liquid_capital_wei"]
            ):
                invariants.append("nav_below_liquid_capital")
            accounted = (
                data.get("liquid_capital_wei"),
                data.get("queued_capital_wei"),
                data.get("settlement_inbox_wei"),
            )
            if (
                eth_balances[version] is not None
                and all(isinstance(value, int) for value in accounted)
                and eth_balances[version] < sum(accounted)
            ):
                invariants.append("eth_balance_below_accounted")
            if any(item.core_listing_match is False for item in decoded_positions):
                invariants.append("core_listing_mismatch")

            epoch = data.get("epoch")
            required = (
                "next_position_id",
                "book_nav_wei",
                "liquid_capital_wei",
                "queued_capital_wei",
                "settlement_inbox_wei",
                "house_share_supply_wei",
                "share_supply_wei",
                "fwa_liability_wei",
                "house_fwa_balance_wei",
                "share_fwa_balance_wei",
                "fee_reconciliation_required",
            )
            summary_complete = all(data.get(field) is not None for field in required)
            if version == "v2":
                summary_complete = summary_complete and epoch is not None
            surfaces.append(
                FWAPSurfaceState(
                    version=version,
                    address=house.address,
                    share_address=share.address,
                    receipt_address=receipt.address,
                    is_current=house.is_current,
                    observed_at=observed_at,
                    block_number=block_number,
                    available=bool(
                        summary_complete
                        and positions_complete
                        and eth_balances[version] is not None
                    ),
                    positions_created=created,
                    positions=decoded_positions,
                    position_counts_complete=positions_complete,
                    inventory_count=inventory,
                    listed_count=listed,
                    active_count=active,
                    allocated_count=allocated,
                    returned_count=returned,
                    recovery_count=recovery,
                    lost_count=lost,
                    exited_count=exited,
                    terminal_count=terminal,
                    active_receipt_count=active_receipts,
                    book_nav_wei=data.get("book_nav_wei"),
                    liquid_capital_wei=data.get("liquid_capital_wei"),
                    queued_capital_wei=data.get("queued_capital_wei"),
                    settlement_inbox_wei=data.get("settlement_inbox_wei"),
                    house_eth_balance_wei=eth_balances[version],
                    house_share_supply_wei=data.get("house_share_supply_wei"),
                    share_supply_wei=data.get("share_supply_wei"),
                    house_fwa_balance_wei=house_fwa,
                    share_fwa_balance_wei=share_fwa,
                    total_fwa_balance_wei=total_fwa,
                    fwa_liability_wei=data.get("fwa_liability_wei"),
                    fee_reconciliation_required=data.get(
                        "fee_reconciliation_required"
                    ),
                    current_epoch=epoch[0] if epoch is not None else None,
                    epoch_duration=epoch[1] if epoch is not None else None,
                    pending_epoch_duration=epoch[2] if epoch is not None else None,
                    epoch_ends_at=epoch[3] if epoch is not None else None,
                    invariant_failures=tuple(invariants),
                    failed_fields=tuple(dict.fromkeys(failed[version])),
                )
            )
        return FWAPRead(
            observed_at=observed_at,
            block_number=block_number,
            surfaces=tuple(surfaces),
        )

    async def fetch_integrity(self, block_number: int) -> FWAPIntegrityRead:
        """Check all six manifest hashes and declared dependency getters."""

        tag = _block_tag(block_number)
        observed_at = self._now()
        codehashes: dict[tuple[str, str], bool | None] = {}
        for manifest in FWAP_MANIFESTS:
            try:
                raw = await self._rpc("eth_getCode", [manifest.address, tag])
            except RuntimeError:
                match = None
            else:
                digest = runtime_codehash(raw)
                match = None if digest is None else digest == manifest.runtime_codehash
            codehashes[(manifest.version, manifest.role)] = match

        dependency_specs: list[tuple[ProjectManifest, str, str]] = []
        for manifest in FWAP_MANIFESTS:
            for getter, expected in manifest.dependencies:
                dependency_specs.append((manifest, getter, expected))
        dependency_results = await self._multicall(
            [
                (manifest.address, _selector(manifest, getter))
                for manifest, getter, _expected in dependency_specs
            ],
            tag,
        )
        dependencies: dict[tuple[str, str], list[tuple[str, bool | None]]] = {
            (manifest.version, manifest.role): [] for manifest in FWAP_MANIFESTS
        }
        for index, (manifest, getter, expected) in enumerate(dependency_specs):
            ok, raw = (
                dependency_results[index]
                if index < len(dependency_results)
                else (False, "0x")
            )
            match: bool | None = None
            value = _hex_words(raw, 1) if ok else None
            if value is not None:
                match = decode_address(value).lower() == expected
            dependencies[(manifest.version, manifest.role)].append((getter, match))

        surfaces = []
        for manifest in FWAP_MANIFESTS:
            key = (manifest.version, manifest.role)
            pairs = tuple(dependencies[key])
            surfaces.append(
                ManifestIntegrity(
                    version=manifest.version,
                    role=manifest.role,
                    address=manifest.address,
                    block_number=block_number,
                    codehash_match=codehashes[key],
                    dependency_matches=pairs,
                    status=_integrity_status(
                        codehashes[key], [value for _getter, value in pairs]
                    ),
                )
            )
        return FWAPIntegrityRead(
            observed_at=observed_at,
            block_number=block_number,
            surfaces=tuple(surfaces),
        )

    async def fetch_api_snapshot(self, chain_block: int) -> FWAPApiRead:
        """Fetch optional context; reject any payload without a source anchor."""

        _block_tag(chain_block)
        observed_at = self._now()
        if self._snapshot_url is None:
            return FWAPApiRead(
                observed_at=observed_at,
                available=False,
                accepted=False,
                reason="disabled",
                snapshot=None,
            )
        assert self._api_client is not None
        try:
            response = await self._api_client.get(
                self._snapshot_url, headers={"Accept": "application/json"}
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return FWAPApiRead(
                observed_at=observed_at,
                available=False,
                accepted=False,
                reason="http_error",
                snapshot=None,
            )
        try:
            payload = response.json()
        except ValueError:
            return FWAPApiRead(
                observed_at=observed_at,
                available=True,
                accepted=False,
                reason="invalid_json",
                snapshot=None,
            )
        snapshot, reason = _api_snapshot(payload, chain_block, observed_at)
        return FWAPApiRead(
            observed_at=observed_at,
            available=True,
            accepted=snapshot is not None,
            reason=reason,
            snapshot=snapshot,
        )


def _api_snapshot(
    payload: Any, chain_block: int, observed_at: float
) -> tuple[FWAPApiSnapshot | None, str]:
    if not isinstance(payload, Mapping):
        return None, "invalid_payload"
    source_block = payload.get("source_block")
    source_timestamp = payload.get("source_timestamp")
    if (
        isinstance(source_block, bool)
        or not isinstance(source_block, int)
        or source_block < 0
        or isinstance(source_timestamp, bool)
        or not isinstance(source_timestamp, (int, float))
    ):
        return None, "missing_source_anchor"
    source_time = float(source_timestamp)
    if not math.isfinite(source_time) or source_time < 0:
        return None, "missing_source_anchor"
    if source_block > chain_block:
        return None, "source_ahead_of_chain"
    if source_time > observed_at:
        return None, "source_time_in_future"
    raw_stale = payload.get("stale", False)
    if not isinstance(raw_stale, bool):
        return None, "invalid_stale_flag"
    projected = payload.get("projected_inventory_count")
    if projected is not None and (
        isinstance(projected, bool) or not isinstance(projected, int) or projected < 0
    ):
        return None, "invalid_inventory"
    raw_counts = payload.get("inventory_counts", {})
    if not isinstance(raw_counts, Mapping) or len(raw_counts) > 64:
        return None, "invalid_inventory"
    counts: list[tuple[str, int]] = []
    for key, value in raw_counts.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or key.strip() != key
            or len(key) > 64
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            return None, "invalid_inventory"
        counts.append((key, value))
    stale = bool(
        raw_stale
        or source_block < chain_block
        or observed_at - source_time > _API_STALE_AFTER_SECONDS
    )
    return (
        FWAPApiSnapshot(
            source_block=source_block,
            source_timestamp=source_time,
            stale=stale,
            projected_inventory_count=projected,
            inventory_counts=tuple(sorted(counts)),
        ),
        "stale" if stale else "fresh",
    )


def _wei(value: int | None) -> float | None:
    return None if value is None else value / _WEI_PER_TOKEN


def _legacy_liability_values(
    surface: FWAPSurfaceState,
) -> tuple[int | None, ...]:
    return (
        surface.queued_capital_wei,
        surface.settlement_inbox_wei,
        surface.fwa_liability_wei,
        surface.house_share_supply_wei,
        surface.share_supply_wei,
        surface.active_receipt_count,
    )


def _has_legacy_liability(surface: FWAPSurfaceState) -> bool:
    return any(
        value is not None and value > 0
        for value in _legacy_liability_values(surface)
    )


def _legacy_liability_unknown(surface: FWAPSurfaceState) -> bool:
    return any(value is None for value in _legacy_liability_values(surface))


def _api_detail(api: FWAPApiRead | None) -> tuple[str, bool]:
    if api is None or api.reason == "disabled":
        return "", False
    if not api.available:
        return f" · API unavailable ({api.reason})", True
    if not api.accepted or api.snapshot is None:
        return f" · API ignored ({api.reason})", True
    snapshot = api.snapshot
    detail = f" · API {'stale' if snapshot.stale else 'anchored'} @ {snapshot.source_block}"
    if snapshot.projected_inventory_count is not None:
        detail += f" · projected inventory {snapshot.projected_inventory_count}"
    return detail, snapshot.stale


def build_project_rows(
    state: FWAPRead,
    *,
    integrity: FWAPIntegrityRead | None = None,
    api: FWAPApiRead | None = None,
    stale: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Emit current v2 and only liability/integrity-bearing legacy v1."""

    rows: list[dict[str, Any]] = []
    api_note, api_problem = _api_detail(api)
    for surface in sorted(state.surfaces, key=lambda item: not item.is_current):
        legacy_liability = not surface.is_current and _has_legacy_liability(surface)
        legacy_unknown = (
            not surface.is_current and _legacy_liability_unknown(surface)
        )
        status: IntegrityStatus = (
            "unknown" if integrity is None else integrity.status_for_version(surface.version)
        )
        if status != "mismatch" and surface.invariant_failures:
            status = "warning"
        semantic_ok = status != "mismatch"
        if status == "mismatch":
            badge = "INTEGRITY"
        elif status in {"unknown", "warning"} or not surface.available:
            badge = "DEGRADED"
        elif surface.is_current and api_problem:
            badge = "API STALE"
        else:
            badge = "VERIFIED"
        if not semantic_ok:
            lifecycle = "integrity mismatch"
        elif not surface.available:
            lifecycle = "unavailable"
        elif surface.fee_reconciliation_required:
            lifecycle = "fee reconciliation"
        elif surface.current_epoch is not None:
            lifecycle = f"epoch {surface.current_epoch}"
        elif _has_legacy_liability(surface):
            lifecycle = "legacy active"
        else:
            lifecycle = "legacy settled"

        def shown(value: int | None) -> float | None:
            return _wei(value) if semantic_ok else None

        detail = (
            f"{surface.positions_created if surface.positions_created is not None else '?'} created"
            f" · {surface.inventory_count if surface.inventory_count is not None else '?'} inventory"
            f" · {surface.active_count if surface.active_count is not None else '?'} active"
            f" · {surface.allocated_count if surface.allocated_count is not None else '?'} allocated"
            f" · {surface.returned_count if surface.returned_count is not None else '?'} returned"
            f" · {surface.terminal_count if surface.terminal_count is not None else '?'} terminal"
            f" · queued {_wei(surface.queued_capital_wei) if semantic_ok else None} ETH"
            f" · held {_wei(surface.total_fwa_balance_wei) if semantic_ok else None} FWA"
        )
        if surface.is_current:
            detail += api_note
        row = ProjectRow(
            family="fwap",
            surface="house",
            version=surface.version,
            address=surface.address,
            is_current=surface.is_current,
            is_legacy_liability=legacy_liability,
            lifecycle=lifecycle,
            primary_label="book NAV",
            primary_value=shown(surface.book_nav_wei),
            primary_unit="nav_eth",
            eth_label="liquid capital",
            eth_value=shown(surface.liquid_capital_wei),
            fwa_label="FWA liability",
            fwa_value=shown(surface.fwa_liability_wei),
            detail=detail,
            source_badge=badge,
            source_kind="chain_state",
            measurement="derived",
            block_number=surface.block_number,
            observed_at=surface.observed_at,
            stale=bool(stale),
            verified_source=True,
            integrity=status,
        ).model_dump()
        assert tuple(row) == PROJECT_ROW_KEYS
        if surface.is_current or legacy_liability or legacy_unknown or status != "ok":
            rows.append(row)
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class EventSpec:
    manifest: ProjectManifest
    name: str
    topic0: str
    inputs: tuple[Mapping[str, Any], ...]


_EVENT_NAMES: Mapping[str, tuple[str, ...]] = {
    "house": (
        "InventoryContributed",
        "InventoryActivated",
        "PositionSynced",
        "NftRedeemed",
        "Redeemed",
        "RewardsHarvested",
        "QueuedCapitalWithdrawn",
    ),
    "share": ("FwaRewardClaimed", "ExitRequested"),
    "receipt": ("ExitRequested",),
}


def _event_specs() -> tuple[EventSpec, ...]:
    specs: list[EventSpec] = []
    for manifest in FWAP_MANIFESTS:
        abi = load_manifest_abi(manifest)
        for name in _EVENT_NAMES[manifest.role]:
            matches = [
                entry
                for entry in abi
                if entry.get("type") == "event" and entry.get("name") == name
            ]
            if not matches:
                continue
            if len(matches) != 1:
                raise ValueError(f"ambiguous FWAP event {name} in {manifest.abi_resource}")
            entry = matches[0]
            signature = _signature(entry)
            specs.append(
                EventSpec(
                    manifest=manifest,
                    name=name,
                    topic0=keccak256_hex(signature.encode()),
                    inputs=tuple(entry.get("inputs") or ()),
                )
            )
    return tuple(specs)


EVENT_SPECS = _event_specs()
_EVENT_BY_ADDRESS_TOPIC = {
    (spec.manifest.address, spec.topic0): spec for spec in EVENT_SPECS
}
_EVENT_LABELS: Mapping[str, tuple[str, str]] = {
    "InventoryContributed": ("inventory_contributed", "Inventory contributed"),
    "InventoryActivated": ("inventory_activated", "Inventory activated"),
    "PositionSynced": ("position_synced", "Position synchronized"),
    "NftRedeemed": ("nft_redeemed", "NFT redeemed"),
    "Redeemed": ("shares_redeemed", "Shares redeemed"),
    "RewardsHarvested": ("rewards_harvested", "Rewards harvested"),
    "QueuedCapitalWithdrawn": ("capital_withdrawn", "Queued capital withdrawn"),
    "FwaRewardClaimed": ("fwa_reward_claimed", "FWA reward claimed"),
    "ExitRequested": ("exit_requested", "Exit requested"),
}


def _quantity(raw: Any) -> int | None:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if not isinstance(raw, str) or not raw.startswith("0x") or len(raw) <= 2:
        return None
    try:
        value = int(raw, 16)
    except ValueError:
        return None
    return value if value >= 0 else None


def _event_value(kind: str, word: str) -> Any:
    value = int(word, 16)
    if kind == "address":
        return "0x" + word[-40:].lower()
    if kind == "bool":
        if value not in (0, 1):
            raise ValueError("malformed bool")
        return bool(value)
    if kind.startswith("int") and value >= 1 << 255:
        return value - (1 << 256)
    return value


def _decode_event(spec: EventSpec, raw: Mapping[str, Any]) -> FWAPEvent | None:
    if raw.get("removed") is True:
        return None
    topics = raw.get("topics")
    if not isinstance(topics, list) or not topics:
        return None
    indexed_count = sum(bool(item.get("indexed")) for item in spec.inputs)
    data_count = len(spec.inputs) - indexed_count
    if len(topics) != indexed_count + 1:
        return None
    block = _quantity(raw.get("blockNumber"))
    timestamp = _quantity(raw.get("blockTimestamp"))
    log_index = _quantity(raw.get("logIndex"))
    tx_hash = str(raw.get("transactionHash") or "").lower()
    if block is None or log_index is None or len(tx_hash) != 66:
        return None
    try:
        if not tx_hash.startswith("0x"):
            return None
        int(tx_hash[2:], 16)
    except ValueError:
        return None
    data = strip0x(str(raw.get("data") or ""))
    if len(data) != data_count * 64:
        return None
    topic_index = 1
    data_index = 0
    values: dict[str, Any] = {}
    try:
        for item in spec.inputs:
            kind = str(item.get("type") or "")
            name = str(item.get("name") or "")
            if kind in {"bytes", "string"} or kind.endswith("[]"):
                return None
            if item.get("indexed"):
                if topic_index >= len(topics):
                    return None
                word = strip0x(str(topics[topic_index]))
                topic_index += 1
            else:
                word = data[data_index * 64 : (data_index + 1) * 64]
                data_index += 1
            if len(word) != 64:
                return None
            values[name] = _event_value(kind, word)
    except (TypeError, ValueError):
        return None

    eth: int | None = None
    fwa: int | None = None
    if spec.name == "InventoryActivated":
        eth = values.get("backing")
    elif spec.name == "NftRedeemed":
        eth = values.get("ethPnl")
    elif spec.name == "Redeemed":
        eth = values.get("ethAmount")
    elif spec.name == "RewardsHarvested":
        eth, fwa = values.get("ethAmount"), values.get("fwaAmount")
    elif spec.name == "QueuedCapitalWithdrawn":
        eth = values.get("ethAmount")
    elif spec.name == "FwaRewardClaimed":
        fwa = values.get("amount")
    event_key, event_label = _EVENT_LABELS[spec.name]
    details: list[str] = []
    for key, label in (
        ("positionId", "position"),
        ("eligibleEpoch", "eligible epoch"),
        ("sharesBurned", "shares"),
        ("shares", "shares"),
        ("tokenId", "token"),
        ("state", "state"),
        ("receipt", "receipt wei"),
        ("loss", "loss wei"),
    ):
        value = values.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            details.append(f"{label} {value}")
    return FWAPEvent(
        address=spec.manifest.address,
        role=spec.manifest.role,
        version=spec.manifest.version,
        event_key=event_key,
        event_label=event_label,
        block_number=block,
        block_timestamp=timestamp,
        tx_hash=tx_hash,
        log_index=log_index,
        eth_amount_wei=eth,
        fwa_amount_wei=fwa,
        detail=" · ".join(details),
    )


def decode_events(raw_logs: Sequence[Any], observed_at: float) -> FWAPEventRead:
    """Decode recorded/paged logs without owning a log transport or watermark."""

    now = _finite_time(lambda: observed_at, "FWAP event")
    events: dict[str, FWAPEvent] = {}
    for raw in raw_logs:
        if not isinstance(raw, Mapping):
            continue
        address = str(raw.get("address") or "").lower()
        topics = raw.get("topics")
        topic0 = str(topics[0]).lower() if isinstance(topics, list) and topics else ""
        spec = _EVENT_BY_ADDRESS_TOPIC.get((address, topic0))
        if spec is None:
            continue
        event = _decode_event(spec, raw)
        if event is not None:
            events[event.event_id] = event
    return FWAPEventRead(
        observed_at=now,
        events=tuple(
            sorted(
                events.values(),
                key=lambda item: (item.block_number, item.log_index),
                reverse=True,
            )
        ),
    )


def normalize_events(
    read: FWAPEventRead,
    *,
    integrity: FWAPIntegrityRead | None = None,
    stale: bool = False,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for event in read.events:
        status: IntegrityStatus = (
            "unknown" if integrity is None else integrity.status_for_version(event.version)
        )
        row = NetworkEventRow(
            event_id=event.event_id,
            ts=event.block_timestamp,
            tx_hash=event.tx_hash,
            log_index=event.log_index,
            origin=f"FWAP {event.role.title()}",
            family="fwap",
            version=event.version,
            event_key=event.event_key,
            event_label=event.event_label,
            eth_amount=_wei(event.eth_amount_wei),
            fwa_amount=_wei(event.fwa_amount_wei),
            detail=event.detail,
            source_kind="chain_log",
            measurement="measured",
            block_number=event.block_number,
            observed_at=read.observed_at,
            stale=bool(stale),
            verified_source=True,
            integrity=status,
        ).model_dump()
        assert tuple(row) == NETWORK_EVENT_ROW_KEYS
        rows.append(row)
    return tuple(rows)


__all__ = [
    "EVENT_SPECS",
    "FWAP_MANIFESTS",
    "FWAP_VERSIONS",
    "LISTING_STATES",
    "POSITION_STATES",
    "STATE_CALLS",
    "FWAPAdapter",
    "FWAPApiRead",
    "FWAPApiSnapshot",
    "FWAPEvent",
    "FWAPEventRead",
    "FWAPIntegrityRead",
    "FWAPPosition",
    "FWAPRead",
    "FWAPSurfaceState",
    "ManifestIntegrity",
    "build_project_rows",
    "decode_events",
    "normalize_events",
    "runtime_codehash",
]
