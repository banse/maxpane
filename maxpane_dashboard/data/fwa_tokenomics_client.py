"""Block-pinned state and Pool-B logs for FWA tokenomics.

This module extends the existing hardened FWA state client instead of changing
its endpoint/error policy.  Direct state is one Multicall3 batch at an explicit
block tag; the gas-price-sensitive acquisition quote is a separate bounded
``eth_call`` at that same block.  Token logs use :class:`FWALogClient`, whose
archive-capable endpoint whitelist and adaptive paging stay intact.

Every wei field is a strict integer until analytics creates presentation rows.
Failed reads are ``None``.  The existing client's historical ``0`` sentinels
are translated at this boundary and never leak into NETWORK data as facts.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from maxpane_dashboard.data.evm_abi import (
    addr_from_topic,
    decode_address,
    decode_uint,
    encode_address,
    strip0x,
)
from maxpane_dashboard.data.fwa_client import FWAClient, SELECTORS
from maxpane_dashboard.data.fwa_ecosystem_addresses import (
    FWA_CORE,
    FWA_HOOK,
    FWA_REWARDS,
    FWA_TOKEN,
    FWA_V1_CLAIM,
    FWA_VRF,
    OFFICIAL_DEPLOYMENTS,
)
from maxpane_dashboard.data.fwa_logs import (
    FWALogClient,
    LOG_ENDPOINTS,
)
from maxpane_dashboard.data.fwa_models import Wei
from maxpane_dashboard.data.keccak import keccak256_hex

logger = logging.getLogger(__name__)

__all__ = [
    "BOUGHT_TOPIC",
    "BUYBACK_ROUTED_TOPIC",
    "BURN_RECIPIENT_TOPICS",
    "BuybackEvent",
    "BurnEvent",
    "DependencySpec",
    "FWATokenomicsClient",
    "FWATokenomicsLogClient",
    "IntegrityRead",
    "STATE_CALLS",
    "TOKEN_TRANSFER_TOPIC",
    "TokenomicsLogRead",
    "TokenomicsState",
    "runtime_codehash",
]


# ---------------------------------------------------------------------------
# Immutable selectors and topics, checked against the vendored ABIs in tests
# ---------------------------------------------------------------------------

SEL_ACTIVE_LISTING_COUNT = "0x4681a7c6"
SEL_PENDING_ACQUISITION_COUNT = "0x34b1670f"
SEL_UNSETTLED_ACQUISITION_COUNT = "0x3d21f274"
SEL_ACQUISITION_ESCROW_TOTAL = "0x59d973db"
SEL_ACQUISITION_REFUND_TOTAL = "0xb5091d48"
SEL_TOP_LISTING_POT = "0xba20687b"
SEL_SETTLEMENT_DISCOUNT_BPS = "0xfb2dd096"
SEL_TOP_LISTING_SHARE_BPS = "0x823e645a"
SEL_OWNER_ACQUISITION_FEE_BPS = "0x2b0b9641"
SEL_OWNER_SETTLEMENT_FEE_BPS = "0x4a088a42"
SEL_ACCRUED_OWNER_FEES = "0x7b9aa10f"

SEL_TOTAL_SUPPLY = "0x18160ddd"
SEL_ROUTE_DEPOSITOR_BPS = "0x87374239"
SEL_ROUTE_PURCHASER_BPS = "0x898c6150"
SEL_ROUTE_BURN_BPS = "0x224212cb"
SEL_CALLER_REWARD_BPS = "0xbac0a7d6"
SEL_LAST_BUYBACK_BLOCK = "0x0741dc4d"
SEL_BALANCE_OF = "0x70a08231"

SEL_TOKEN_BUY_ALLOWANCE_TOTAL = "0xb74d90cd"
SEL_EMISSION_START = "0x513da948"
SEL_EMISSION_DURATION = "0x2d9c4dd2"
SEL_DEPOSITOR_RATE_PER_SEC = "0xd2b48fff"
SEL_PURCHASER_DAILY_POT = "0xfb894e65"
SEL_CURRENT_EPOCH = "0x76671808"

SEL_REWARDS = "0x9ec5a894"
SEL_VRF_SERVICE = "0x59749e94"
SEL_FWA = "0xd969194b"
SEL_TOKEN = "0xfc0c546a"
SEL_TOKEN_HOOK = "0xd043166b"
SEL_HOOK = "0x7f5a7c7b"
SEL_POOL = "0x16f0115b"

BOUGHT_TOPIC = (
    "0xedba86fd2b22962d534e70ad9b0ff8730de46f636146f2bab6a72cbb1ebbcc53"
)
"""``Bought(address,uint256,uint256,uint256)``."""

BUYBACK_ROUTED_TOPIC = (
    "0x6cd85b822905c8ad7dbbe3a24ffb9a00c6ce2b2471541c56a7e7b8466b0e7ef3"
)
"""``BuybackRouted(uint256,uint256,uint256)``."""

TOKEN_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
"""``Transfer(address,address,uint256)``."""

_ZERO_ADDRESS = "0x" + "0" * 40
def _address_topic(address: str) -> str:
    return "0x" + strip0x(address).lower().rjust(64, "0")


BURN_RECIPIENT_TOPICS: tuple[str, ...] = (
    _address_topic(_ZERO_ADDRESS),
)


# ---------------------------------------------------------------------------
# Strict boundary models
# ---------------------------------------------------------------------------

_STRICT = ConfigDict(frozen=True, extra="forbid", strict=True)


class TokenomicsState(BaseModel):
    """One direct state snapshot; every value was read at ``state_block``."""

    model_config = _STRICT

    observed_at: float
    state_block: int | None
    chain_head: int | None
    gas_price_wei: Wei | None = None
    active_listings: int | None = None
    pending_count: int | None = None
    unsettled_count: int | None = None
    quote_total_wei: Wei | None = None
    acquisition_escrow_wei: Wei | None = None
    refund_credit_total_wei: Wei | None = None
    crown_pot_wei: Wei | None = None
    settlement_payout_bps: int | None = None
    crown_share_bps: int | None = None
    owner_acquisition_fee_bps: int | None = None
    owner_settlement_fee_bps: int | None = None
    accrued_owner_fees_wei: Wei | None = None
    total_supply_wei: Wei | None = None
    route_depositor_bps: int | None = None
    route_purchaser_bps: int | None = None
    route_burn_bps: int | None = None
    caller_reward_bps: int | None = None
    last_buyback_block: int | None = None
    rewards_balance_wei: Wei | None = None
    claim_balance_wei: Wei | None = None
    token_buy_allowance_wei: Wei | None = None
    emission_start: int | None = None
    emission_duration: int | None = None
    depositor_rate_per_sec_wei: Wei | None = None
    purchaser_daily_pot_wei: Wei | None = None
    current_epoch: int | None = None
    failed_fields: tuple[str, ...] = ()


class BuybackEvent(BaseModel):
    """One paired ``Bought`` / ``BuybackRouted`` transaction in strict wei."""

    model_config = _STRICT

    block_number: int
    block_timestamp: int | None
    observed_at: float
    tx_hash: str
    bought_log_index: int
    routed_log_index: int | None
    caller: str
    eth_spent_wei: Wei
    amount_bought_wei: Wei
    caller_reward_wei: Wei
    to_depositors_wei: Wei | None
    to_purchasers_wei: Wei | None
    burned_wei: Wei | None


class BurnEvent(BaseModel):
    """A supply-reducing transfer observed in the token log stream."""

    model_config = _STRICT

    block_number: int
    block_timestamp: int | None
    observed_at: float
    tx_hash: str
    log_index: int
    recipient: str
    amount_wei: Wei


class TokenomicsLogRead(BaseModel):
    """Independently available buyback and burn log groups."""

    model_config = _STRICT

    observed_at: float
    from_block: int
    to_block: int
    history_complete: bool
    buybacks_available: bool
    burns_available: bool
    unavailable_reason: str | None
    buybacks: tuple[BuybackEvent, ...]
    burns: tuple[BurnEvent, ...]


class IntegrityRead(BaseModel):
    """Runtime-code and direct-dependency checks at one pinned block."""

    model_config = _STRICT

    observed_at: float
    block_number: int
    codehash_matches: dict[str, bool | None]
    dependency_matches: dict[str, bool | None]

    def status_for(self, *roles: str) -> str:
        """``ok``, ``mismatch`` or ``unknown`` for the requested roles."""

        checks: list[bool | None] = []
        for role in roles:
            checks.append(self.codehash_matches.get(role))
            checks.extend(
                result
                for name, result in self.dependency_matches.items()
                if name.startswith(role + ".")
            )
        if any(result is False for result in checks):
            return "mismatch"
        if not checks or any(result is None for result in checks):
            return "unknown"
        return "ok"


@dataclass(frozen=True, slots=True)
class StateCall:
    key: str
    address: str
    calldata: str


def _balance_of(address: str) -> str:
    return SEL_BALANCE_OF + encode_address(address)


STATE_CALLS: tuple[StateCall, ...] = (
    StateCall("active_listings", FWA_CORE, SEL_ACTIVE_LISTING_COUNT),
    StateCall("pending_count", FWA_CORE, SEL_PENDING_ACQUISITION_COUNT),
    StateCall("unsettled_count", FWA_CORE, SEL_UNSETTLED_ACQUISITION_COUNT),
    StateCall("acquisition_escrow_wei", FWA_CORE, SEL_ACQUISITION_ESCROW_TOTAL),
    StateCall("refund_credit_total_wei", FWA_CORE, SEL_ACQUISITION_REFUND_TOTAL),
    StateCall("crown_pot_wei", FWA_CORE, SEL_TOP_LISTING_POT),
    StateCall("settlement_payout_bps", FWA_CORE, SEL_SETTLEMENT_DISCOUNT_BPS),
    StateCall("crown_share_bps", FWA_CORE, SEL_TOP_LISTING_SHARE_BPS),
    StateCall(
        "owner_acquisition_fee_bps", FWA_CORE, SEL_OWNER_ACQUISITION_FEE_BPS
    ),
    StateCall(
        "owner_settlement_fee_bps", FWA_CORE, SEL_OWNER_SETTLEMENT_FEE_BPS
    ),
    StateCall("accrued_owner_fees_wei", FWA_CORE, SEL_ACCRUED_OWNER_FEES),
    StateCall("total_supply_wei", FWA_TOKEN, SEL_TOTAL_SUPPLY),
    StateCall("route_depositor_bps", FWA_TOKEN, SEL_ROUTE_DEPOSITOR_BPS),
    StateCall("route_purchaser_bps", FWA_TOKEN, SEL_ROUTE_PURCHASER_BPS),
    StateCall("route_burn_bps", FWA_TOKEN, SEL_ROUTE_BURN_BPS),
    StateCall("caller_reward_bps", FWA_TOKEN, SEL_CALLER_REWARD_BPS),
    StateCall("last_buyback_block", FWA_TOKEN, SEL_LAST_BUYBACK_BLOCK),
    StateCall("rewards_balance_wei", FWA_TOKEN, _balance_of(FWA_REWARDS)),
    StateCall("claim_balance_wei", FWA_TOKEN, _balance_of(FWA_V1_CLAIM)),
    StateCall(
        "token_buy_allowance_wei", FWA_REWARDS, SEL_TOKEN_BUY_ALLOWANCE_TOTAL
    ),
    StateCall("emission_start", FWA_REWARDS, SEL_EMISSION_START),
    StateCall("emission_duration", FWA_REWARDS, SEL_EMISSION_DURATION),
    StateCall(
        "depositor_rate_per_sec_wei", FWA_REWARDS, SEL_DEPOSITOR_RATE_PER_SEC
    ),
    StateCall("purchaser_daily_pot_wei", FWA_REWARDS, SEL_PURCHASER_DAILY_POT),
    StateCall("current_epoch", FWA_REWARDS, SEL_CURRENT_EPOCH),
)


@dataclass(frozen=True, slots=True)
class DependencySpec:
    role: str
    getter: str
    address: str
    selector: str
    expected: str

    @property
    def key(self) -> str:
        return f"{self.role}.{self.getter}"


DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("core", "rewards", FWA_CORE, SEL_REWARDS, FWA_REWARDS),
    DependencySpec("core", "vrfService", FWA_CORE, SEL_VRF_SERVICE, FWA_VRF),
    DependencySpec("rewards", "fwa", FWA_REWARDS, SEL_FWA, FWA_CORE),
    DependencySpec("rewards", "token", FWA_REWARDS, SEL_TOKEN, FWA_TOKEN),
    DependencySpec("rewards", "tokenHook", FWA_REWARDS, SEL_TOKEN_HOOK, FWA_HOOK),
    DependencySpec("token", "hook", FWA_TOKEN, SEL_HOOK, FWA_HOOK),
    DependencySpec("token", "pool", FWA_TOKEN, SEL_POOL, FWA_REWARDS),
    DependencySpec("hook", "token", FWA_HOOK, SEL_TOKEN, FWA_TOKEN),
    DependencySpec("v1_claim", "token", FWA_V1_CLAIM, SEL_TOKEN, FWA_TOKEN),
)


def runtime_codehash(raw_code: str) -> str | None:
    """Keccak hash of RPC bytecode, or ``None`` for a malformed response."""

    if not isinstance(raw_code, str):
        return None
    raw = strip0x(raw_code)
    if len(raw) % 2:
        return None
    try:
        return keccak256_hex(bytes.fromhex(raw))
    except ValueError:
        return None


def _decode_single_uint(raw_data: Any) -> int | None:
    """Decode one ABI uint word, rejecting a short/malformed provider reply."""

    if not isinstance(raw_data, str):
        return None
    raw = strip0x(raw_data)
    if len(raw) < 64:
        return None
    try:
        return decode_uint(raw_data)
    except ValueError:
        return None


def _decode_single_address(raw_data: Any) -> str | None:
    """Decode one ABI address word without turning truncation into mismatch."""

    if not isinstance(raw_data, str):
        return None
    raw = strip0x(raw_data)
    if len(raw) < 64:
        return None
    try:
        return decode_address(raw_data).lower()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Pool-A state client
# ---------------------------------------------------------------------------


class FWATokenomicsClient(FWAClient):
    """The existing FWA state policy plus NETWORK tokenomics reads."""

    def __init__(
        self,
        *args: Any,
        clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._network_clock = clock

    def _observed_at(self) -> float:
        value = self._network_clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("tokenomics clock must return epoch seconds")
        observed = float(value)
        if not math.isfinite(observed) or observed < 0.0:
            raise ValueError("tokenomics clock must return finite epoch seconds")
        return observed

    async def fetch_state(
        self,
        *,
        block_number: int | None = None,
        gas_price_wei: int | None = None,
    ) -> TokenomicsState:
        """Read core/token/rewards state at one explicit block tag.

        ``quoteAcquisitionPrice`` keeps the existing client's gas context and
        bound.  Its historical ``(0, 0, 0)`` failure sentinel is converted to
        ``None`` here.
        """

        observed_at = self._observed_at()
        head = block_number
        if head is None:
            fetched = await self.fetch_block_number()
            head = fetched if fetched > 0 else None
        if head is not None and (
            isinstance(head, bool) or not isinstance(head, int) or head < 0
        ):
            raise ValueError("block_number must be a non-negative int or None")
        if head is None:
            return TokenomicsState(
                observed_at=observed_at,
                state_block=None,
                chain_head=None,
                failed_fields=tuple(call.key for call in STATE_CALLS)
                + ("quote_total_wei",),
            )

        block_tag = hex(head)
        results = await self._multicall(
            [(call.address, call.calldata) for call in STATE_CALLS],
            block_tag,
        )
        values: dict[str, Any] = {}
        failed: list[str] = []
        for index, call in enumerate(STATE_CALLS):
            if index >= len(results):
                values[call.key] = None
                failed.append(call.key)
                continue
            ok, raw = results[index]
            if not ok or not strip0x(raw):
                values[call.key] = None
                failed.append(call.key)
                continue
            decoded = _decode_single_uint(raw)
            if decoded is None:
                values[call.key] = None
                failed.append(call.key)
            else:
                values[call.key] = decoded

        price = gas_price_wei
        if price is None:
            fetched_price = await self.fetch_gas_price()
            price = fetched_price if fetched_price > 0 else None
        if price is not None and (
            isinstance(price, bool) or not isinstance(price, int) or price < 0
        ):
            raise ValueError("gas_price_wei must be a non-negative int or None")
        quote_total: int | None = None
        if price:
            _fee, _vrf, total = await self.quote_acquisition_price(
                price, block=block_tag
            )
            quote_total = total if total > 0 else None
        if quote_total is None:
            failed.append("quote_total_wei")

        return TokenomicsState(
            observed_at=observed_at,
            state_block=head,
            chain_head=head,
            gas_price_wei=price,
            quote_total_wei=quote_total,
            failed_fields=tuple(dict.fromkeys(failed)),
            **values,
        )

    async def fetch_official_integrity(self, block_number: int) -> IntegrityRead:
        """Check the frozen official runtime graph at ``block_number``."""

        if isinstance(block_number, bool) or not isinstance(block_number, int):
            raise ValueError("block_number must be an int")
        if block_number < 0:
            raise ValueError("block_number must be non-negative")
        tag = hex(block_number)
        codehash_matches: dict[str, bool | None] = {}
        for deployment in OFFICIAL_DEPLOYMENTS:
            try:
                raw = await self._rpc(
                    "eth_getCode", [deployment.address, tag]
                )
            except Exception as exc:  # noqa: BLE001 - per-role degradation
                logger.warning(
                    "integrity code read failed for %s: %s",
                    deployment.role,
                    exc,
                )
                codehash_matches[deployment.role] = None
                continue
            digest = runtime_codehash(raw)
            codehash_matches[deployment.role] = (
                None if digest is None else digest == deployment.runtime_codehash
            )

        results = await self._multicall(
            [(spec.address, spec.selector) for spec in DEPENDENCIES], tag
        )
        dependency_matches: dict[str, bool | None] = {}
        for index, spec in enumerate(DEPENDENCIES):
            if index >= len(results):
                dependency_matches[spec.key] = None
                continue
            ok, raw = results[index]
            if not ok or not strip0x(raw):
                dependency_matches[spec.key] = None
                continue
            actual = _decode_single_address(raw)
            if actual is None:
                dependency_matches[spec.key] = None
            else:
                dependency_matches[spec.key] = actual == spec.expected.lower()

        return IntegrityRead(
            observed_at=self._observed_at(),
            block_number=block_number,
            codehash_matches=codehash_matches,
            dependency_matches=dependency_matches,
        )


# ---------------------------------------------------------------------------
# Pool-B token log client
# ---------------------------------------------------------------------------


def _hex_quantity(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    try:
        parsed = int(value, 16)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _uint_word(data: Any, index: int) -> int | None:
    if not isinstance(data, str):
        return None
    raw = strip0x(data)
    start = index * 64
    word = raw[start : start + 64]
    if len(word) != 64:
        return None
    try:
        return int(word, 16)
    except ValueError:
        return None


def _log_base(log: Mapping[str, Any]) -> tuple[int, int, int | None, str] | None:
    block = _hex_quantity(log.get("blockNumber"))
    index = _hex_quantity(log.get("logIndex"))
    timestamp = _hex_quantity(log.get("blockTimestamp"))
    tx_hash = str(log.get("transactionHash") or "").lower()
    if block is None or index is None or not tx_hash.startswith("0x"):
        return None
    return block, index, timestamp if timestamp else None, tx_hash


def _decode_bought(log: Mapping[str, Any]) -> dict[str, Any] | None:
    topics = log.get("topics")
    if not isinstance(topics, list) or len(topics) < 2:
        return None
    if str(topics[0]).lower() != BOUGHT_TOPIC:
        return None
    base = _log_base(log)
    values = tuple(_uint_word(log.get("data"), index) for index in range(3))
    if base is None or any(value is None for value in values):
        return None
    block, log_index, timestamp, tx_hash = base
    return {
        "block_number": block,
        "log_index": log_index,
        "block_timestamp": timestamp,
        "tx_hash": tx_hash,
        "caller": addr_from_topic(str(topics[1])),
        "eth_spent_wei": values[0],
        "amount_bought_wei": values[1],
        "caller_reward_wei": values[2],
    }


def _decode_routed(log: Mapping[str, Any]) -> dict[str, Any] | None:
    topics = log.get("topics")
    if not isinstance(topics, list) or not topics:
        return None
    if str(topics[0]).lower() != BUYBACK_ROUTED_TOPIC:
        return None
    base = _log_base(log)
    values = tuple(_uint_word(log.get("data"), index) for index in range(3))
    if base is None or any(value is None for value in values):
        return None
    block, log_index, timestamp, tx_hash = base
    return {
        "block_number": block,
        "log_index": log_index,
        "block_timestamp": timestamp,
        "tx_hash": tx_hash,
        "to_depositors_wei": values[0],
        "to_purchasers_wei": values[1],
        "burned_wei": values[2],
    }


def _decode_burn(log: Mapping[str, Any], observed_at: float) -> BurnEvent | None:
    topics = log.get("topics")
    if not isinstance(topics, list) or len(topics) < 3:
        return None
    if str(topics[0]).lower() != TOKEN_TRANSFER_TOPIC:
        return None
    recipient_topic = str(topics[2]).lower()
    if recipient_topic not in BURN_RECIPIENT_TOPICS:
        return None
    base = _log_base(log)
    amount = _uint_word(log.get("data"), 0)
    if base is None or amount is None:
        return None
    block, log_index, timestamp, tx_hash = base
    return BurnEvent(
        block_number=block,
        block_timestamp=timestamp,
        observed_at=observed_at,
        tx_hash=tx_hash,
        log_index=log_index,
        recipient=addr_from_topic(recipient_topic),
        amount_wei=amount,
    )


def _pair_buybacks(
    raw_logs: Sequence[Mapping[str, Any]], observed_at: float
) -> tuple[BuybackEvent, ...]:
    bought = [row for log in raw_logs if (row := _decode_bought(log)) is not None]
    routed = [row for log in raw_logs if (row := _decode_routed(log)) is not None]
    routes_by_tx: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for route in routed:
        routes_by_tx.setdefault(
            (route["tx_hash"], route["block_number"]), []
        ).append(route)
    out: dict[tuple[str, int], BuybackEvent] = {}
    for row in bought:
        choices = routes_by_tx.get(
            (row["tx_hash"], row["block_number"]), []
        )
        route = min(
            choices,
            key=lambda item: abs(item["log_index"] - row["log_index"]),
        ) if choices else None
        event = BuybackEvent(
            block_number=row["block_number"],
            block_timestamp=row["block_timestamp"],
            observed_at=observed_at,
            tx_hash=row["tx_hash"],
            bought_log_index=row["log_index"],
            routed_log_index=None if route is None else route["log_index"],
            caller=row["caller"],
            eth_spent_wei=row["eth_spent_wei"],
            amount_bought_wei=row["amount_bought_wei"],
            caller_reward_wei=row["caller_reward_wei"],
            to_depositors_wei=None if route is None else route["to_depositors_wei"],
            to_purchasers_wei=None if route is None else route["to_purchasers_wei"],
            burned_wei=None if route is None else route["burned_wei"],
        )
        out[(event.tx_hash, event.bought_log_index)] = event
    return tuple(
        sorted(out.values(), key=lambda item: (item.block_number, item.bought_log_index))
    )


class FWATokenomicsLogClient:
    """Token-specific reads on the existing keyless archive log pool."""

    def __init__(
        self,
        endpoints: Sequence[str] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
        min_call_interval: float = 0.05,
    ) -> None:
        self._clock = clock
        self._logs = FWALogClient(
            endpoints=endpoints,
            http_client=http_client,
            core_address=FWA_TOKEN,
            min_call_interval=min_call_interval,
        )

    @property
    def endpoints(self) -> tuple[str, ...]:
        return self._logs._endpoints

    async def close(self) -> None:
        await self._logs.close()

    async def __aenter__(self) -> FWATokenomicsLogClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def _observed_at(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("tokenomics log clock must return epoch seconds")
        observed = float(value)
        if not math.isfinite(observed) or observed < 0.0:
            raise ValueError("tokenomics log clock must return finite epoch seconds")
        return observed

    async def fetch_flow_logs(
        self,
        from_block: int,
        to_block: int,
        *,
        history_complete: bool,
    ) -> TokenomicsLogRead:
        """Read buyback/routing and supply-reducing transfers independently."""

        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (from_block, to_block)
        ):
            raise ValueError("log block bounds must be non-negative ints")
        observed_at = self._observed_at()
        buyback_raw: list[dict] = []
        burn_raw: list[dict] = []
        buybacks_available = False
        burns_available = False
        reasons: list[str] = []
        try:
            buyback_raw = await self._logs.get_logs(
                [[BOUGHT_TOPIC, BUYBACK_ROUTED_TOPIC]], from_block, to_block
            )
            buybacks_available = True
        except Exception as exc:  # noqa: BLE001 - independently degraded pool
            logger.warning("FWA buyback logs unavailable: %s", exc)
            reasons.append("buyback logs unavailable")
        try:
            burn_raw = await self._logs.get_logs(
                [TOKEN_TRANSFER_TOPIC, None, list(BURN_RECIPIENT_TOPICS)],
                from_block,
                to_block,
            )
            burns_available = True
        except Exception as exc:  # noqa: BLE001 - independently degraded pool
            logger.warning("FWA burn logs unavailable: %s", exc)
            reasons.append("burn logs unavailable")

        burns_by_id: dict[tuple[str, int], BurnEvent] = {}
        for raw in burn_raw:
            event = _decode_burn(raw, observed_at)
            if event is not None:
                burns_by_id[(event.tx_hash, event.log_index)] = event

        return TokenomicsLogRead(
            observed_at=observed_at,
            from_block=from_block,
            to_block=to_block,
            history_complete=history_complete,
            buybacks_available=buybacks_available,
            burns_available=burns_available,
            unavailable_reason="; ".join(reasons) or None,
            buybacks=_pair_buybacks(buyback_raw, observed_at),
            burns=tuple(
                sorted(
                    burns_by_id.values(),
                    key=lambda item: (item.block_number, item.log_index),
                )
            ),
        )


# Guard the copied topic constants at import without touching an ABI or RPC.
assert BOUGHT_TOPIC == keccak256_hex(b"Bought(address,uint256,uint256,uint256)")
assert BUYBACK_ROUTED_TOPIC == keccak256_hex(
    b"BuybackRouted(uint256,uint256,uint256)"
)
assert TOKEN_TRANSFER_TOPIC == keccak256_hex(b"Transfer(address,address,uint256)")
assert set(LOG_ENDPOINTS), "the inherited Pool-B whitelist must not be empty"
