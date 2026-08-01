"""Keyless Ethereum-mainnet **state** client for the Fake World Assets (FWA) dashboard.

This is *Pool A* — ``eth_call`` / ``eth_getBalance`` / ``eth_blockNumber`` only,
batched through Multicall3.  Event-log reads are **not** done here: publicnode
gates them behind an archive token and the log pool lives in ``fwa_logs.py``
(WP-7).  Keeping the two pools in separate modules is what stops a client from
capability-probing publicnode with a narrow recent range, concluding logs work,
and then failing on the first backfill (findings §13.10).

What this module is responsible for
-----------------------------------

1. :meth:`FWAClient.fetch_hot_batch` — one Multicall3 ``eth_call`` covering ~47
   views across all 8 FWA contracts, feeding the 15 s tier.
2. :meth:`FWAClient.quote_acquisition_price` — the price primitive, called with
   an **explicit ``gasPrice`` and a bounded ``gas``**.
3. :meth:`FWAClient.sweep_positions` — the block-pinned free-list slot sweep,
   with the three on-chain aggregate invariants asserted **at runtime**.
4. :meth:`FWAClient.fetch_eth_balance` — the only source of "ETH the protocol
   holds".

The five traps this module encodes
----------------------------------

**TRAP 1 — the free list leaves permanent holes in the slot space.**
``slotToListing`` is 1-indexed and non-contiguous: ``_allocateSlot()`` reuses a
free list, so withdrawn listings leave holes for ever.  Scanning
``slot = 1..activeListingCount()`` finds *fewer* positions than exist, and the
shortfall is invisible: at block 25612701 it found **3,604 of 3,867**, the
recomputed ``weightedBackingTotal`` was short by exactly ``263.000e36`` and the
derived ``acquisitionFee`` was wrong by 765,340,893,316,672 wei — a plausible
number, wrong in the third significant figure of the flagship metric.  The
correct recipe scans slots *upward from 1, skipping zeros, until
``activeListingCount()`` non-zero ids have been collected*, which currently
needs roughly 1.1x that many slots.  See :func:`_collect_listing_ids`.

**TRAP 2 — the block must be pinned across the whole sweep.**  The pool mutates
every few seconds (24 listings and 95 new ids moved in 46 blocks).  Every call
in a sweep carries the same ``blockTag``; results are never merged across
blocks.  A partial or block-smeared sweep is a **defect, not a degraded state**
(PRD §7 rule 11) — it is reported with ``invariants_ok=False`` so the odds board
renders *stale*, never *wrong*.

**TRAP 3 — ``weightedBackingTotal`` is not TVL.**  It is ``Σ(weight × backing)
≈ activeListingCount × 1e36``: neither wei nor ETH.  It is returned only inside
the sweep report, for the invariant check.  The TVL source is
:meth:`FWAClient.fetch_eth_balance` on FWA core (PRD §7 rule 4).

**TRAP 4 — Multicall3 ``Call3.callData`` must carry no ``0x`` prefix.**  Leaving
it on embeds the literal characters ``30 78`` in the bytes field and the node
rejects the whole payload with *"cannot unmarshal invalid hex string"*.
:func:`maxpane_dashboard.data.evm_abi.encode_call3` strips it (the shared
codec, where the trap was already solved) and
``tests/data/test_fwa_client.py::test_aggregate3_encoding_has_no_0x_in_calldata``
pins that behaviour.

**TRAP 5 — the VRF fee is gas-price dependent and is NOT waived.**
``quoteAcquisitionPrice()`` proxies ``FWAVRFService.requestFee()``, which reads
``tx.gasprice``.  Every zero reading during research was an unset-``gasPrice``
artifact: same block, 1 gwei → 0.00104 ETH, 50 gwei → 0.052 ETH (findings
§13.9).  :meth:`FWAClient.quote_acquisition_price` therefore *requires* a gas
price, always sends a bounded ``gas``, and returns the contract's tuple
unchanged.  The VRF leg is never computed, never summed from two sources and
never assumed to be zero.

Endpoints
---------

Pool A is ``ethereum-rpc.publicnode.com`` (the only keyless endpoint that
batches reliably — Multicall3 at ≤ 500 sub-calls per ``eth_call``) with
``cloudflare-eth.com`` and ``1rpc.io/eth`` as state fallbacks.  Banned hosts
(dead, keyed, or rate-limited to uselessness) are rejected by the constructor
rather than merely documented.

All public methods are exception-safe: a dead upstream surfaces as an empty /
zero return plus a flag, never as an exception escaping into the refresh loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.data import ens
from maxpane_dashboard.data.evm_abi import (
    ZERO_ADDRESS as _ZERO_ADDRESS,
    decode_address as _decode_address,
    decode_aggregate3_result as _decode_aggregate3_result,
    decode_string,
    decode_uint as _decode_uint,
    encode_address as _encode_address,
    encode_aggregate3 as _encode_aggregate3,
    encode_call3 as _encode_call3,
    encode_uint as _encode_uint,
    pad_left as _pad_left,
    strip0x as _strip0x,
)
from maxpane_dashboard.data.fwa_models import Position
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES as _ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Endpoints — Pool A (state only)
# ---------------------------------------------------------------------------

_PRIMARY_RPC = "https://ethereum-rpc.publicnode.com"
_FALLBACK_RPCS = [
    "https://cloudflare-eth.com",
    "https://1rpc.io/eth",
]

#: Hosts that are dead, now keyed, or rate-limited into uselessness
#: (findings §3 + ``tests/fixtures/fwa/rpc_errors.json``).  Configuring one is a
#: programming error, so the constructor raises instead of silently degrading.
_BANNED_RPC_HOSTS = frozenset(
    {
        "eth.llamarpc.com",  # HTTP 521, origin down
        "rpc.ankr.com",  # now requires an API key
        "eth-mainnet.g.alchemy.com",  # keyed
        "mainnet.infura.io",  # keyed
        "api.opensea.io",  # keyed
        "api.reservoir.tools",  # sunset
    }
)

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 15.0
#: publicnode 429s under aggressive batching; ~0.12 s spacing was stable (§11).
_INTER_CALL_DELAY = 0.12

#: Multicall3 tolerated 500 sub-calls per ``eth_call`` against publicnode (§6.5).
MULTICALL_MAX_CALLS = 500

#: Bounded ``gas`` for every gas-price-sensitive quote (§7, §13.9).
_QUOTE_GAS_BOUND = "0x200000"

#: Extra slots scanned beyond ``activeListingCount``, as a multiplier.  Slots
#: 1..4,500 were needed to find 3,867 positions; the pool then grew 53% in two
#: days, so this is sized from the **live** count, never a constant (§13.6).
SLOT_SCAN_HEADROOM = 1.2
#: Absolute floor on the headroom so tiny pools still clear their holes.
SLOT_SCAN_MIN_EXTRA = 64

#: How long a fetched ``eth_gasPrice`` is reused for quoting.
_GAS_PRICE_TTL = 60.0


# ---------------------------------------------------------------------------
# Contract registry (findings §2; addresses re-confirmed in every WP-3 fixture)
# ---------------------------------------------------------------------------

FWA_CORE = "0xb276f62db0ce8ca2ca5bc522695be604521eac1c"
FWA_REWARDS = "0x6a1a1c0cfb3d3c538e13d36d608a5bcaa992fc78"
FWA_VRF_SERVICE = "0xa084c33fb7a467307452898b8d58165ebd2e5d9f"
FWA_TOKEN = "0xa0df17b5ac76ababa36e1450e2cbcd18a620c845"
FWA_TOKEN_HOOK = "0x2c67eba8a50af0db5fba55f725247a75cbda6444"
FWA_CLAIM = "0xd4085d38855f17edf0b1ccbfad7b3846fb305655"
FWA_WHITELIST = "0x854352b275cf6a0dffcf2983c986fbe9345e17c3"
FWA_SPLITTER = "0x1c175b9f0e8c73ed3e677e1cbb1b5a2dd4373bfe"

MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"

#: Re-exported from :mod:`evm_abi` (part of this module's public surface).
ZERO_ADDRESS = _ZERO_ADDRESS

FWA_CONTRACTS: dict[str, str] = {
    "FWA": FWA_CORE,
    "FWARewards": FWA_REWARDS,
    "FWAVRFService": FWA_VRF_SERVICE,
    "FWAToken": FWA_TOKEN,
    "FWATokenHook": FWA_TOKEN_HOOK,
    "FWAClaim": FWA_CLAIM,
    "FWAWhitelist": FWA_WHITELIST,
    "Splitter": FWA_SPLITTER,
}


# ---------------------------------------------------------------------------
# Selectors — hardcoded so runtime never touches the ABI files, cross-checked
# against ``maxpane_dashboard/abis/fwa/selectors.json`` by a test.
# ---------------------------------------------------------------------------

SELECTORS: dict[str, str] = {
    # -- Multicall3
    "aggregate3((address,bool,bytes)[])": "0x82ad56cb",
    # -- FWA core: pricing & pool aggregates
    "quoteAcquisitionPrice()": "0x987df4cd",
    "acquisitionFee()": "0x38f5f005",
    "totalWeight()": "0x96c82e57",
    "weightedBackingTotal()": "0xd6eb0dbd",
    "activeListingCount()": "0x4681a7c6",
    "nextListingId()": "0xaaccf1ec",
    "feeShareTotal()": "0x4c68b3b9",
    "BPS()": "0x249d39e9",
    # -- FWA core: positions
    "listings(uint256)": "0xde74e57b",
    "slotToListing(uint256)": "0xe2881eb7",
    "collectionWhitelisted(address)": "0x666cd313",
    # -- FWA core: crown
    "topListingId()": "0xee35bc33",
    "topListingPot()": "0xba20687b",
    "topThresholdBps()": "0x6a6e8c70",
    "topListingShareBps()": "0x823e645a",
    # -- FWA core: economic parameters
    "ownerAcquisitionFeeBps()": "0x2b0b9641",
    "ownerSettlementFeeBps()": "0x4a088a42",
    "settlementDiscountBps()": "0xfb2dd096",
    "retainedToProtocol()": "0x5b69ae6a",
    "selectionSlippageBps()": "0x40ef7ee1",
    "selectionTimeoutBlocks()": "0xdf881bd1",
    "settlementWindow()": "0xb4a7bdf9",
    "finalizeWindow()": "0x8600e5cb",
    # -- FWA core: balances, escrow, queue
    "accruedOwnerFees()": "0x7b9aa10f",
    "acquisitionEscrowTotal()": "0x59d973db",
    "acquisitionRefundCreditTotal()": "0xb5091d48",
    "reservedStagedCount()": "0xfa36793f",
    "pendingAcquisitionCount()": "0x34b1670f",
    "unsettledAcquisitionCount()": "0x3d21f274",
    "unfulfilledVrfCount()": "0xa66e8ae2",
    "lastIssuedSequence()": "0xc367b0d2",
    "nextSequenceToProcess()": "0xc4c873e6",
    # -- FWARewards
    "emissionStart()": "0x513da948",
    "EMISSION_DURATION()": "0x2d9c4dd2",
    "currentEpoch()": "0x76671808",
    "hotGap()": "0xd420f120",
    "coldGap()": "0xa3975f95",
    "forcedTokenShareBps()": "0xc890e267",
    "lastAcquisitionTs()": "0x7e10c38e",
    "sqrtBackingTotal()": "0xd33e5daa",
    "tokenBuyAllowanceTotal()": "0xb74d90cd",
    "tokenShareBps(uint256)": "0xacffd600",
    # -- FWAVRFService
    "subscriptionNativeBalance()": "0x864df900",
    "minimumSubscriptionBuffer()": "0x2c2dccbd",
    "availableProcessorSurplus()": "0xe4665406",
    # -- FWAToken
    "totalSupply()": "0x18160ddd",
    "symbol()": "0x95d89b41",
    "launched()": "0x8091f3bf",
    "lastBuybackBlock()": "0x0741dc4d",
    # -- FWATokenHook
    "externalBuysEnabled()": "0x953386d9",
    # -- FWAWhitelist
    "TTT_AMOUNT()": "0x23f2a9b7",
    "ttt()": "0xd59809c5",
    # -- Splitter
    "totalReceived()": "0xa3c2c462",
    "claimablePerToken()": "0xcc3dcf09",
    "NFT_ADDRESS()": "0xb32c5c45",
    # -- FWAClaim
    "token()": "0xfc0c546a",
    # -- ERC-721, read against arbitrary collection contracts
    "name()": "0x06fdde03",
}

_SEL_AGGREGATE3 = SELECTORS["aggregate3((address,bool,bytes)[])"]
_SEL_LISTINGS = SELECTORS["listings(uint256)"]
_SEL_SLOT_TO_LISTING = SELECTORS["slotToListing(uint256)"]
_SEL_QUOTE = SELECTORS["quoteAcquisitionPrice()"]
_SEL_TOKEN_SHARE_BPS = SELECTORS["tokenShareBps(uint256)"]
_SEL_COLLECTION_WHITELISTED = SELECTORS["collectionWhitelisted(address)"]
#: ERC-721 ``name()`` — read against arbitrary collection contracts, so it is
#: only ever issued with ``allowFailure=True``.
_SEL_ERC721_NAME = SELECTORS["name()"]


# ---------------------------------------------------------------------------
# FWA-specific ABI decoding.
#
# The generic hex/ABI primitives these build on used to be copied verbatim from
# ``talismans_client``; they now live in :mod:`maxpane_dashboard.data.evm_abi`
# and are imported above (MEDI-17).  ``encode_call3`` there already strips the
# ``0x`` from callData — that is findings §6.5 TRAP 4, pre-solved; do not
# "clean it up".
# ---------------------------------------------------------------------------


def _decode_int(hex_data: str, word_idx: int = 0) -> int:
    """Decode a **signed** int256 at word slot *word_idx*.

    ``forcedTokenShareBps()`` returns ``-1`` (all-``f`` word) to mean "dynamic".
    Decoding it unsigned yields ``2**256 - 1``, which is a decode bug, not a
    huge share (``fwa_models`` trap 4).
    """
    value = _decode_uint(hex_data, word_idx)
    if value >= 1 << 255:
        value -= 1 << 256
    return value


def _decode_bool(hex_data: str, word_idx: int = 0) -> bool:
    return _decode_uint(hex_data, word_idx) != 0


def _decode_string(hex_data: str) -> str:
    """Decode a dynamic ``string`` return (offset word, length word, bytes)."""
    raw = _strip0x(hex_data)
    if len(raw) < 128:
        return ""
    try:
        offset = int(raw[0:64], 16) * 2
        length = int(raw[offset : offset + 64], 16)
        body = raw[offset + 64 : offset + 64 + length * 2]
        return bytes.fromhex(body).decode("utf-8", errors="replace")
    except (ValueError, IndexError):
        return ""


# ---------------------------------------------------------------------------
# Position decoding
# ---------------------------------------------------------------------------

#: ``listings(uint256)`` returns a flat 11-tuple of static types, so the return
#: is head-only: 11 x 32 = 352 bytes.  No dynamic-tuple offset word (unlike the
#: Talismans ``tokenData`` trap) — but the byte length is still asserted, because
#: a short return means a revert, not a small position.
LISTING_RETURN_BYTES = 352

_LISTING_WORDS = (
    "collection",  # 0 address
    "depositor",  # 1 address
    "purchaser",  # 2 address  (source name; Position calls it `allocatee`, §13.4)
    "tokenId",  # 3 uint256
    "weight",  # 4 uint256 — inverse: 1e36 // value
    "value",  # 5 uint256 — backing in wei
    "feeShare",  # 6 uint256 — always 1 (§13.2)
    "feeDebt",  # 7 uint256
    "slot",  # 8 uint256 — 1-indexed, non-contiguous
    "allocatedAt",  # 9 uint64
    "status",  # 10 uint8 — 1 == Active
)


def decode_listing(raw_hex: str, listing_id: int) -> Position | None:
    """Decode one ``listings(uint256)`` return into a :class:`Position`.

    Returns ``None`` when the return is short (a revert, an empty
    ``allowFailure`` miss, or a listing id that no longer exists) rather than
    fabricating a zero-backed position: a zero backing would make
    ``1e36 // backing`` explode and would quietly drag every aggregate.

    ``allocatee`` is normalised from the on-chain zero address to ``None`` so no
    widget can render ``0x0000…`` as a purchaser.  The struct field is named
    ``purchaser`` in ``src/FWA.sol``; ``Position.allocatee`` keeps the model-side
    name deliberately (findings §13.4).
    """
    raw = _strip0x(raw_hex or "")
    if len(raw) < LISTING_RETURN_BYTES * 2:
        return None
    try:
        collection = _decode_address(raw, 0)
        depositor = _decode_address(raw, 1)
        purchaser = _decode_address(raw, 2)
        token_id = _decode_uint(raw, 3)
        weight = _decode_uint(raw, 4)
        value = _decode_uint(raw, 5)
        fee_share = _decode_uint(raw, 6)
        fee_debt = _decode_uint(raw, 7)
        slot = _decode_uint(raw, 8)
        allocated_at = _decode_uint(raw, 9)
        status = _decode_uint(raw, 10)
    except (ValueError, IndexError) as exc:
        logger.debug("listing %s decode failed: %s", listing_id, exc)
        return None

    if value <= 0:
        # minBacking is 0.01 ETH; a zero here is a dead slot, not a position.
        return None

    return Position(
        listing_id=listing_id,
        collection=collection,
        depositor=depositor,
        allocatee=None if purchaser == ZERO_ADDRESS else purchaser,
        token_id=token_id,
        weight=weight,
        backing_wei=value,
        fee_share=fee_share,
        fee_debt=fee_debt,
        slot=slot,
        allocated_at=allocated_at,
        status=status,
    )


# ---------------------------------------------------------------------------
# The runtime invariant check (findings §6.2 — "ship this as a runtime
# assertion, not just a test")
# ---------------------------------------------------------------------------


def check_sweep_invariants(
    positions: list[Position],
    *,
    expected_count: int,
    total_weight_onchain: int,
    weighted_backing_total_onchain: int,
    acquisition_fee_onchain: int,
    fee_share_total_onchain: int | None = None,
    surcharge_bps: int = fwa_ev.DEFAULT_SURCHARGE_BPS,
) -> dict[str, Any]:
    """Recompute the three on-chain aggregates from a swept position set.

    Returns a report dict; ``report["invariants_ok"]`` is ``True`` only when the
    row count matches ``activeListingCount()`` **and** all three aggregates
    reproduce bit-for-bit at the pinned block::

        Σ (1e36 // value)                        == totalWeight()
        Σ (weight * value)                       == weightedBackingTotal()
        (Σ weighted // Σ weight) * 11000 // 10000 == acquisitionFee()

    The third is deliberately two sequential floor divisions
    (:func:`fwa_ev.acquisition_fee_wei`); collapsing them into one expression
    changes the integer by up to a wei and the check would then fail on a
    correct sweep.

    A mismatch is logged at ERROR and reported — never raised.  The manager
    marks the odds board stale; nothing derived from an incomplete sweep is
    published (PRD §7 rule 11).
    """
    backings = [p.backing_wei for p in positions if p.backing_wei > 0]
    computed_tw = fwa_ev.total_weight(backings)
    computed_wbt = fwa_ev.weighted_backing_total(backings)
    computed_fee = fwa_ev.acquisition_fee_wei(
        computed_wbt, computed_tw, surcharge_bps
    )
    backing_total = sum(backings)

    # Free per-row check: the contract stores `weight`, we recompute it.
    weight_mismatches = sum(
        1
        for p in positions
        if p.backing_wei > 0 and p.weight != fwa_ev.inverse_weight(p.backing_wei)
    )

    mismatches: list[str] = []
    if len(positions) != expected_count:
        mismatches.append(
            f"count {len(positions)} != activeListingCount {expected_count}"
        )
    if computed_tw != total_weight_onchain:
        mismatches.append(
            f"totalWeight {computed_tw} != onchain {total_weight_onchain}"
        )
    if computed_wbt != weighted_backing_total_onchain:
        mismatches.append(
            "weightedBackingTotal "
            f"{computed_wbt} != onchain {weighted_backing_total_onchain} "
            f"(short by {weighted_backing_total_onchain - computed_wbt})"
        )
    if computed_fee != acquisition_fee_onchain:
        mismatches.append(
            f"acquisitionFee {computed_fee} != onchain {acquisition_fee_onchain} "
            f"(off by {computed_fee - acquisition_fee_onchain} wei)"
        )
    if weight_mismatches:
        mismatches.append(f"{weight_mismatches} rows fail weight == 1e36 // value")
    if (
        fee_share_total_onchain is not None
        and fee_share_total_onchain != expected_count
    ):
        mismatches.append(
            f"feeShareTotal {fee_share_total_onchain} != activeListingCount "
            f"{expected_count}"
        )

    ok = not mismatches
    if not ok:
        logger.error(
            "FWA sweep invariants FAILED — refusing to publish derived numbers: %s",
            "; ".join(mismatches),
        )

    return {
        "invariants_ok": ok,
        "collected": len(positions),
        "expected": expected_count,
        "mismatches": tuple(mismatches),
        "total_weight_computed": computed_tw,
        "total_weight_onchain": total_weight_onchain,
        "weighted_backing_total_computed": computed_wbt,
        "weighted_backing_total_onchain": weighted_backing_total_onchain,
        "acquisition_fee_computed": computed_fee,
        "acquisition_fee_onchain": acquisition_fee_onchain,
        "backing_total_wei": backing_total,
        "weight_mismatches": weight_mismatches,
    }


# ---------------------------------------------------------------------------
# Hot-tier view table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ViewSpec:
    """One no-argument view in the hot Multicall3 batch."""

    key: str  # key in the dict fetch_hot_batch returns
    contract: str  # registry label, e.g. "FWA"
    signature: str  # e.g. "acquisitionFee()"
    kind: str  # uint | int | bool | address | string

    @property
    def address(self) -> str:
        return FWA_CONTRACTS[self.contract]

    @property
    def selector(self) -> str:
        return SELECTORS[self.signature]


def _v(key: str, contract: str, signature: str, kind: str = "uint") -> ViewSpec:
    return ViewSpec(key=key, contract=contract, signature=signature, kind=kind)


#: The 15 s tier.  One Multicall3 ``eth_call`` across all 8 contracts.
#:
#: ``quoteAcquisitionPrice()`` is deliberately **not** in here: it needs an
#: explicit ``tx.gasprice`` and a bounded ``gas``, and bounding gas for a
#: 47-sub-call batch is a different problem from bounding it for one view.  It
#: is issued as its own ``eth_call`` by :meth:`FWAClient.fetch_hot_batch`.
#: ``tokenShareBps(uint256)`` is likewise separate — its argument is the gap
#: derived from ``lastAcquisitionTs()``, which this batch is what reads.
HOT_VIEWS: tuple[ViewSpec, ...] = (
    # -- FWA core: pool aggregates & price
    _v("acquisition_fee", "FWA", "acquisitionFee()"),
    _v("total_weight", "FWA", "totalWeight()"),
    _v("weighted_backing_total", "FWA", "weightedBackingTotal()"),
    _v("active_listing_count", "FWA", "activeListingCount()"),
    _v("next_listing_id", "FWA", "nextListingId()"),
    _v("fee_share_total", "FWA", "feeShareTotal()"),
    _v("bps", "FWA", "BPS()"),
    # -- FWA core: crown
    _v("top_listing_id", "FWA", "topListingId()"),
    _v("top_listing_pot", "FWA", "topListingPot()"),
    _v("top_threshold_bps", "FWA", "topThresholdBps()"),
    _v("top_listing_share_bps", "FWA", "topListingShareBps()"),
    # -- FWA core: economic parameters
    _v("settlement_discount_bps", "FWA", "settlementDiscountBps()"),
    _v("retained_to_protocol", "FWA", "retainedToProtocol()", "bool"),
    _v("owner_acquisition_fee_bps", "FWA", "ownerAcquisitionFeeBps()"),
    _v("owner_settlement_fee_bps", "FWA", "ownerSettlementFeeBps()"),
    _v("selection_slippage_bps", "FWA", "selectionSlippageBps()"),
    _v("selection_timeout_blocks", "FWA", "selectionTimeoutBlocks()"),
    _v("settlement_window", "FWA", "settlementWindow()"),
    _v("finalize_window", "FWA", "finalizeWindow()"),
    # -- FWA core: balances, escrow, queue
    _v("accrued_owner_fees", "FWA", "accruedOwnerFees()"),
    _v("acquisition_escrow_total", "FWA", "acquisitionEscrowTotal()"),
    _v("acquisition_refund_credit_total", "FWA", "acquisitionRefundCreditTotal()"),
    _v("reserved_staged_count", "FWA", "reservedStagedCount()"),
    _v("pending_acquisition_count", "FWA", "pendingAcquisitionCount()"),
    _v("unsettled_acquisition_count", "FWA", "unsettledAcquisitionCount()"),
    _v("unfulfilled_vrf_count", "FWA", "unfulfilledVrfCount()"),
    _v("last_issued_sequence", "FWA", "lastIssuedSequence()"),
    _v("next_sequence_to_process", "FWA", "nextSequenceToProcess()"),
    # -- FWARewards
    _v("emission_start", "FWARewards", "emissionStart()"),
    _v("emission_duration", "FWARewards", "EMISSION_DURATION()"),
    _v("current_epoch", "FWARewards", "currentEpoch()"),
    _v("hot_gap", "FWARewards", "hotGap()"),
    _v("cold_gap", "FWARewards", "coldGap()"),
    # SIGNED int256: -1 == dynamic.  Unsigned decoding gives 2**256-1 (trap 4).
    _v("forced_token_share_bps", "FWARewards", "forcedTokenShareBps()", "int"),
    _v("last_acquisition_ts", "FWARewards", "lastAcquisitionTs()"),
    _v("sqrt_backing_total", "FWARewards", "sqrtBackingTotal()"),
    _v("token_buy_allowance_total", "FWARewards", "tokenBuyAllowanceTotal()"),
    # -- FWAVRFService
    _v("subscription_native_balance", "FWAVRFService", "subscriptionNativeBalance()"),
    _v("minimum_subscription_buffer", "FWAVRFService", "minimumSubscriptionBuffer()"),
    _v("available_processor_surplus", "FWAVRFService", "availableProcessorSurplus()"),
    # -- FWAToken
    _v("token_total_supply", "FWAToken", "totalSupply()"),
    _v("token_launched", "FWAToken", "launched()", "bool"),
    _v("last_buyback_block", "FWAToken", "lastBuybackBlock()"),
    _v("token_symbol", "FWAToken", "symbol()", "string"),
    # -- FWATokenHook
    _v("external_buys_enabled", "FWATokenHook", "externalBuysEnabled()", "bool"),
    # -- FWAWhitelist
    _v("ttt_amount", "FWAWhitelist", "TTT_AMOUNT()"),
    # -- Splitter
    _v("splitter_total_received", "Splitter", "totalReceived()"),
    _v("splitter_claimable_per_token", "Splitter", "claimablePerToken()"),
)

#: Keys :meth:`FWAClient.fetch_hot_batch` adds on top of :data:`HOT_VIEWS`.
HOT_EXTRA_KEYS: tuple[str, ...] = (
    "quote_fee_wei",
    "quote_vrf_wei",
    "quote_total_wei",
    "quote_gas_price_wei",
    "token_share_bps",
)

#: Meta keys, always present.
HOT_META_KEYS: tuple[str, ...] = ("_ok", "_failed", "_fetched_at", "_error")

#: Every key ``fetch_hot_batch()`` returns — exactly, always.  Same discipline
#: as ``FWA_DATA_KEYS``: a dead source changes values and flips ``_ok``, it never
#: removes a key, so the manager can never ``KeyError`` on a degraded tick.
FWA_HOT_KEYS: tuple[str, ...] = (
    tuple(v.key for v in HOT_VIEWS) + HOT_EXTRA_KEYS + HOT_META_KEYS
)

_DECODERS = {
    "uint": lambda d: _decode_uint(d, 0),
    "int": lambda d: _decode_int(d, 0),
    "bool": lambda d: _decode_bool(d, 0),
    "address": lambda d: _decode_address(d, 0),
    "string": _decode_string,
}


def decode_view_results(
    views: tuple[ViewSpec, ...] | list[ViewSpec],
    results: list[tuple[bool, str]],
) -> tuple[dict[str, Any], list[str]]:
    """Map an ``aggregate3`` result list onto ``{view.key: value}``.

    A failed or missing sub-call yields ``None`` — never ``0``.  Several of
    these views legitimately read zero (``TTT_AMOUNT() == 0``,
    ``lastBuybackBlock() == 0``, ``externalBuysEnabled() == false``), so
    collapsing failure onto zero would make a dead RPC indistinguishable from a
    disabled feature.  Returns ``(values, failed_keys)``.
    """
    values: dict[str, Any] = {}
    failed: list[str] = []
    for i, spec in enumerate(views):
        if i >= len(results):
            values[spec.key] = None
            failed.append(spec.key)
            continue
        ok, data = results[i]
        if not ok or not _strip0x(data):
            values[spec.key] = None
            failed.append(spec.key)
            continue
        try:
            values[spec.key] = _DECODERS[spec.kind](data)
        except (ValueError, IndexError, KeyError) as exc:
            logger.debug("decode of %s failed: %s", spec.signature, exc)
            values[spec.key] = None
            failed.append(spec.key)
    return values, failed


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FWAClient(OwnedHttpClient):
    """Async, keyless, state-only RPC client for the FWA protocol.

    Every public method is exception-safe: a network failure surfaces as an
    empty / zero return plus a flag, never as an exception escaping into the
    dashboard's refresh loop.

    Parameters
    ----------
    primary_rpc, fallback_rpcs:
        Pool A endpoints.  A banned host (dead / keyed / useless — see
        :data:`_BANNED_RPC_HOSTS`) raises ``ValueError`` at construction.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  Tests inject one built
        on a transport double so no socket is ever opened.
    inter_call_delay, backoff_seconds:
        Pacing knobs, overridable so tests do not sleep.
    """

    def __init__(
        self,
        primary_rpc: str = _PRIMARY_RPC,
        fallback_rpcs: list[str] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        inter_call_delay: float = _INTER_CALL_DELAY,
        backoff_seconds: tuple[float, ...] = _BACKOFF_SECONDS,
    ) -> None:
        endpoints = [primary_rpc, *(fallback_rpcs or _FALLBACK_RPCS)]
        for url in endpoints:
            host = (urlparse(url).hostname or "").lower()
            if host in _BANNED_RPC_HOSTS:
                raise ValueError(
                    f"{url} is a banned RPC host (dead, keyed or rate-limited "
                    "into uselessness) — see fwa_client._BANNED_RPC_HOSTS"
                )
        self._primary_rpc = primary_rpc
        self._fallback_rpcs = list(fallback_rpcs or _FALLBACK_RPCS)
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._inter_call_delay = inter_call_delay
        self._backoff_seconds = backoff_seconds
        self._request_id = 0
        self._last_rpc_at: float = 0.0

        # single-flight state for sweep_positions
        self._sweep_running = False
        self._last_sweep: tuple[int, list[Position], dict[str, Any]] | None = None

        # cached eth_gasPrice, so the 15 s tier does not re-ask every tick
        self._gas_price_wei: int = 0
        self._gas_price_at: float = 0.0

    # Lifecycle (close / __aenter__ / __aexit__) comes from OwnedHttpClient.

    @property
    def endpoints(self) -> list[str]:
        """Pool A endpoints in rotation order."""
        return [self._primary_rpc, *self._fallback_rpcs]

    # ------------------------------------------------------------------
    # Internal: RPC plumbing with retry + fallback rotation
    # ------------------------------------------------------------------

    async def _rpc(self, method: str, params: list) -> Any:
        """Send one JSON-RPC call with retry and endpoint rotation.

        Returns the ``result`` field.  Raises ``RuntimeError`` only after every
        endpoint has failed — callers catch that and degrade.

        Note the ``error``-inside-HTTP-200 case: publicnode's rate limiter,
        ankr's auth wall and Multicall3's unmarshal complaint all arrive with a
        200 status, so branching on status alone mis-handles them
        (``rpc_errors.json`` warning).
        """
        self._last_rpc_at = await pace(self._last_rpc_at, self._inter_call_delay)

        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)
        last_err: BaseException | None = None
        for url in self.endpoints:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._client.post(url, json=payload)
                    if resp.status_code in _ENDPOINT_DEAD_CODES:
                        # Dead / keyed / archive-gated: rotate, do not retry.
                        last_err = RuntimeError(
                            f"RPC {url} returned {resp.status_code}"
                        )
                        break
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"RPC {url} returned {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    body = resp.json()
                    if isinstance(body, dict) and "error" in body:
                        # Includes -32602 archive refusals and rate limits that
                        # arrive inside a 200.  Rotate rather than raise: the
                        # next endpoint may well serve it.
                        last_err = RuntimeError(f"RPC {url} error: {body['error']}")
                        break
                    if isinstance(body, list):
                        last_err = RuntimeError(
                            f"RPC {url} returned a batch response to a single call"
                        )
                        break
                    return body.get("result", "0x")
                except (httpx.HTTPError, httpx.StreamError, ValueError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1 and self._backoff_seconds:
                        delay = self._backoff_seconds[
                            min(attempt, len(self._backoff_seconds) - 1)
                        ]
                        if delay > 0:
                            await asyncio.sleep(delay)
                    else:
                        logger.debug(
                            "%s failed on %s after %d attempts: %s",
                            method,
                            url,
                            attempt + 1,
                            exc,
                        )
                        break
        raise RuntimeError(f"RPC {method} failed on all endpoints; last_err={last_err}")

    async def _eth_call(
        self,
        to: str,
        data: str,
        block: str = "latest",
        *,
        gas: str | None = None,
        gas_price_wei: int | None = None,
    ) -> str:
        call: dict[str, str] = {"to": to, "data": data}
        if gas is not None:
            call["gas"] = gas
        if gas_price_wei is not None:
            call["gasPrice"] = hex(gas_price_wei)
        return await self._rpc("eth_call", [call, block])

    async def _multicall(
        self, calls: list[tuple[str, str]], block: str = "latest"
    ) -> list[tuple[bool, str]]:
        """Batch ``eth_call``s through Multicall3 ``aggregate3``.

        Input tuples are ``(target, callData)``; every sub-call runs with
        ``allowFailure=True`` so one bad target cannot kill the batch.  The list
        is split into chunks of at most :data:`MULTICALL_MAX_CALLS`, and the
        returned list is always the same length as ``calls`` — a chunk that
        fails wholesale is padded with ``(False, "0x")`` so indices stay aligned
        with the request.

        ``block`` is threaded through unchanged: a pinned sweep passes its
        ``blockTag`` here and every chunk lands on the same block (TRAP 2).
        """
        if not calls:
            return []
        out: list[tuple[bool, str]] = []
        for start in range(0, len(calls), MULTICALL_MAX_CALLS):
            chunk = calls[start : start + MULTICALL_MAX_CALLS]
            data = _encode_aggregate3([(t, cd, True) for (t, cd) in chunk])
            try:
                raw = await self._eth_call(MULTICALL3, data, block)
            except Exception as exc:  # noqa: BLE001 — degrade, never escape
                logger.warning(
                    "multicall(%d calls @ %s) failed: %s", len(chunk), block, exc
                )
                out.extend((False, "0x") for _ in chunk)
                continue
            decoded = _decode_aggregate3_result(raw)
            if len(decoded) != len(chunk):
                logger.warning(
                    "multicall returned %d results for %d calls @ %s",
                    len(decoded),
                    len(chunk),
                    block,
                )
                decoded = decoded[: len(chunk)]
                decoded += [(False, "0x")] * (len(chunk) - len(decoded))
            out.extend(decoded)
        return out

    # ------------------------------------------------------------------
    # Public: cheap single reads
    # ------------------------------------------------------------------

    async def fetch_block_number(self) -> int:
        """Current head block, or ``0`` on failure."""
        try:
            return int(await self._rpc("eth_blockNumber", []), 16)
        except Exception as exc:  # noqa: BLE001
            logger.warning("eth_blockNumber failed: %s", exc)
            return 0

    async def fetch_eth_balance(self, address: str = FWA_CORE) -> int:
        """``eth_getBalance(address)`` in wei — **the only TVL source**.

        PRD §7 rule 4: ``weightedBackingTotal()`` is ``Σ(weight × backing) ≈
        count × 1e36``, dimensionless, and reads like a count of ETH.  Rendering
        it as value held is a factual error.  This balance (backing + escrow +
        accrued fees + crown pot) is what the protocol actually holds.

        Returns ``0`` on failure.
        """
        try:
            result = await self._rpc("eth_getBalance", [address, "latest"])
            return int(result, 16)
        except Exception as exc:  # noqa: BLE001
            logger.warning("eth_getBalance(%s) failed: %s", address, exc)
            return 0

    async def fetch_gas_price(self, *, max_age: float = _GAS_PRICE_TTL) -> int:
        """Current ``eth_gasPrice`` in wei, cached for *max_age* seconds.

        Exists because :meth:`quote_acquisition_price` may not be called without
        one: the VRF leg is a function of ``tx.gasprice`` and an unset gas price
        silently reports it as zero (§13.9).  Returns ``0`` on failure, which
        the caller must treat as "cannot quote", not as "free".
        """
        now = time.monotonic()
        if self._gas_price_wei > 0 and (now - self._gas_price_at) < max_age:
            return self._gas_price_wei
        try:
            result = await self._rpc("eth_gasPrice", [])
            value = int(result, 16)
        except Exception as exc:  # noqa: BLE001
            logger.warning("eth_gasPrice failed: %s", exc)
            return 0
        if value > 0:
            self._gas_price_wei = value
            self._gas_price_at = now
        return value

    # ------------------------------------------------------------------
    # Public: the price quote
    # ------------------------------------------------------------------

    async def quote_acquisition_price(
        self, gas_price_wei: int, *, block: str = "latest"
    ) -> tuple[int, int, int]:
        """``quoteAcquisitionPrice()`` → ``(fee_wei, vrf_wei, total_wei)``.

        Sends an **explicit ``gasPrice``** and a **bounded ``gas``**
        (:data:`_QUOTE_GAS_BOUND`).  Both matter:

        * ``FWAVRFService.requestFee()`` reads ``tx.gasprice``.  With no gas
          price the VRF leg comes back 0 — which is what made two research
          agents conclude the fee was waived.  It is not: at the same block,
          1 gwei → 0.00104 ETH and 50 gwei → 0.052 ETH (§13.9).
        * bounding ``gas`` costs nothing and forecloses the
          ``insufficient funds for gas * price`` class of rejection (§7; the
          error did not reproduce on every node, which is exactly why the bound
          is unconditional rather than reactive).

        The three integers are returned **as the contract reported them**.  The
        caller renders the VRF leg from this tuple: never recomputed from
        ``serviceGasEstimate × gasPrice × margin``, never summed from a second
        source, never assumed zero.

        Returns ``(0, 0, 0)`` on failure — the caller flags the price tile
        unavailable rather than showing a free pull.
        """
        if gas_price_wei < 0:
            raise ValueError(f"gas_price_wei must be >= 0, got {gas_price_wei}")
        if gas_price_wei == 0:
            logger.warning(
                "quoteAcquisitionPrice called with gasPrice=0 — the VRF leg will "
                "read 0, which is an artifact of the gas price, not a waiver"
            )
        try:
            raw = await self._eth_call(
                FWA_CORE,
                _SEL_QUOTE,
                block,
                gas=_QUOTE_GAS_BOUND,
                gas_price_wei=gas_price_wei,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("quoteAcquisitionPrice failed: %s", exc)
            return (0, 0, 0)
        if len(_strip0x(raw)) < 3 * 64:
            logger.warning("quoteAcquisitionPrice returned a short tuple: %r", raw)
            return (0, 0, 0)
        return (
            _decode_uint(raw, 0),
            _decode_uint(raw, 1),
            _decode_uint(raw, 2),
        )

    async def fetch_token_share_bps(self, gap_seconds: int) -> int | None:
        """``FWARewards.tokenShareBps(gap)`` — the live purchaser surcharge share.

        Read, never recomputed: the ramp's linearity between ``hotGap()`` and
        ``coldGap()`` is unconfirmed, so a locally interpolated value would be a
        guess wearing a live number's clothes.  ``None`` means the read failed
        and the caller must label any fallback as an estimate.
        """
        try:
            raw = await self._eth_call(
                FWA_REWARDS, _SEL_TOKEN_SHARE_BPS + _encode_uint(max(0, gap_seconds))
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("tokenShareBps(%s) failed: %s", gap_seconds, exc)
            return None
        if not _strip0x(raw):
            return None
        return _decode_uint(raw, 0)

    # ------------------------------------------------------------------
    # Public: the hot batch
    # ------------------------------------------------------------------

    async def fetch_hot_batch(
        self,
        *,
        gas_price_wei: int | None = None,
        include_quote: bool = True,
        include_token_share: bool = True,
    ) -> dict[str, Any]:
        """One Multicall3 batch of the ~47 views feeding the 15 s tier.

        Always returns every key in :data:`FWA_HOT_KEYS`.  A view that failed to
        read is ``None``, never ``0``; ``_failed`` lists those keys and ``_ok``
        is ``True`` only when nothing failed.

        Deliberately **unpinned** (``latest``): hot single reads must not be
        pinned (§11).  Only the position sweep pins a block.

        Two follow-up ``eth_call``s ride along when requested:

        * ``quoteAcquisitionPrice()``, which needs its own ``gasPrice`` and
          ``gas`` bound (see :meth:`quote_acquisition_price`);
        * ``tokenShareBps(gap)``, whose argument is derived from the
          ``lastAcquisitionTs()`` this batch just read.
        """
        out: dict[str, Any] = dict.fromkeys(FWA_HOT_KEYS)
        out["_failed"] = ()
        out["_error"] = None
        out["_fetched_at"] = time.time()

        calls = [(v.address, v.selector) for v in HOT_VIEWS]
        try:
            results = await self._multicall(calls)
        except Exception as exc:  # noqa: BLE001
            logger.warning("hot batch failed: %s", exc)
            out["_ok"] = False
            out["_failed"] = tuple(v.key for v in HOT_VIEWS)
            out["_error"] = str(exc)
            return out

        values, failed = decode_view_results(HOT_VIEWS, results)
        out.update(values)

        if include_quote:
            price = gas_price_wei
            if price is None:
                price = await self.fetch_gas_price()
            out["quote_gas_price_wei"] = price or None
            if price:
                fee, vrf, total = await self.quote_acquisition_price(price)
                if total > 0:
                    out["quote_fee_wei"] = fee
                    out["quote_vrf_wei"] = vrf
                    out["quote_total_wei"] = total
                else:
                    failed.extend(["quote_fee_wei", "quote_vrf_wei", "quote_total_wei"])
            else:
                failed.extend(
                    [
                        "quote_gas_price_wei",
                        "quote_fee_wei",
                        "quote_vrf_wei",
                        "quote_total_wei",
                    ]
                )

        if include_token_share:
            last_ts = out.get("last_acquisition_ts")
            if isinstance(last_ts, int) and last_ts > 0:
                gap = max(0, int(time.time()) - last_ts)
                share = await self.fetch_token_share_bps(gap)
                out["token_share_bps"] = share
                if share is None:
                    failed.append("token_share_bps")
            else:
                failed.append("token_share_bps")

        out["_failed"] = tuple(failed)
        out["_ok"] = not failed
        return out

    async def fetch_collections_whitelisted(
        self, addresses: list[str], *, block: str = "latest"
    ) -> dict[str, bool | None]:
        """``collectionWhitelisted(address)`` for many collections in one batch.

        Lives on FWA **core**, not on FWAWhitelist — the whitelist contract only
        holds the write side (``setCollections``).  Findings §13.1; the work-package
        text groups it wrongly.

        A failed sub-call maps to ``None``, distinct from a genuine ``False``.
        """
        if not addresses:
            return {}
        calls = [
            (FWA_CORE, _SEL_COLLECTION_WHITELISTED + _encode_address(a))
            for a in addresses
        ]
        results = await self._multicall(calls, block)
        out: dict[str, bool | None] = {}
        for i, addr in enumerate(addresses):
            if i >= len(results):
                out[addr.lower()] = None
                continue
            ok, data = results[i]
            out[addr.lower()] = _decode_bool(data) if ok and _strip0x(data) else None
        return out

    # ------------------------------------------------------------------
    # Public: the block-pinned position sweep
    # ------------------------------------------------------------------

    async def sweep_positions(
        self, *, headroom: float = SLOT_SCAN_HEADROOM
    ) -> tuple[int, list[Position], dict[str, Any]]:
        """Enumerate every live position at one pinned block.

        Returns ``(block_number, positions, report)`` where ``report`` always
        carries ``invariants_ok`` / ``collected`` / ``expected``.

        The recipe (findings §6.1), in order, with every call carrying the same
        ``blockTag``:

        1. pin ``blockTag = eth_blockNumber()``
        2. read ``activeListingCount()``, ``totalWeight()``,
           ``weightedBackingTotal()``, ``acquisitionFee()``, ``feeShareTotal()``
           at that block
        3. batch ``slotToListing(slot)`` upward from slot 1, **skipping zeros**,
           stopping once ``activeListingCount`` non-zero ids are collected —
           never at ``slot == activeListingCount`` (TRAP 1)
        4. batch ``listings(id)`` for every collected id at the same block
        5. recompute the three aggregates and compare bit-for-bit
           (:func:`check_sweep_invariants`)

        On shortfall or mismatch the positions collected so far are still
        returned, with ``invariants_ok=False``, so the manager can mark the odds
        board stale.  **Nothing derived from an incomplete sweep may be
        published** — a partial sweep produces a plausible total, which is worse
        than no total (PRD §7 rule 11).

        Single-flight: if a sweep is already running the caller gets the
        previous result immediately with ``report["skipped"] = True``.  The tick
        is skipped, never queued — queueing a 3-second sweep behind a 60-second
        cadence is how a dashboard ends up rendering a block from ten minutes
        ago.
        """
        if self._sweep_running:
            if self._last_sweep is not None:
                block, positions, report = self._last_sweep
                return (block, positions, {**report, "skipped": True})
            return (
                0,
                [],
                {
                    "invariants_ok": False,
                    "collected": 0,
                    "expected": 0,
                    "skipped": True,
                    "mismatches": ("sweep already running, no previous result",),
                },
            )

        self._sweep_running = True
        try:
            return await self._sweep_positions_inner(headroom=headroom)
        except Exception as exc:  # noqa: BLE001 — never escape into the loop
            logger.warning("position sweep failed: %s", exc)
            return (
                0,
                [],
                {
                    "invariants_ok": False,
                    "collected": 0,
                    "expected": 0,
                    "skipped": False,
                    "error": str(exc),
                    "mismatches": (f"sweep failed: {exc}",),
                },
            )
        finally:
            self._sweep_running = False

    async def _sweep_positions_inner(
        self, *, headroom: float
    ) -> tuple[int, list[Position], dict[str, Any]]:
        block_number = await self.fetch_block_number()
        if block_number <= 0:
            return (
                0,
                [],
                {
                    "invariants_ok": False,
                    "collected": 0,
                    "expected": 0,
                    "skipped": False,
                    "mismatches": ("eth_blockNumber failed — cannot pin a block",),
                },
            )
        block_tag = hex(block_number)

        # Step 2 — the pinned aggregates, in one batch at the pinned block.
        agg_specs = (
            ("active_listing_count", "activeListingCount()"),
            ("total_weight", "totalWeight()"),
            ("weighted_backing_total", "weightedBackingTotal()"),
            ("acquisition_fee", "acquisitionFee()"),
            ("fee_share_total", "feeShareTotal()"),
        )
        agg_results = await self._multicall(
            [(FWA_CORE, SELECTORS[sig]) for (_k, sig) in agg_specs], block_tag
        )
        agg: dict[str, int | None] = {}
        for i, (key, _sig) in enumerate(agg_specs):
            ok, data = agg_results[i] if i < len(agg_results) else (False, "0x")
            agg[key] = _decode_uint(data) if ok and _strip0x(data) else None

        expected = agg["active_listing_count"]
        if expected is None:
            return (
                block_number,
                [],
                {
                    "invariants_ok": False,
                    "collected": 0,
                    "expected": 0,
                    "block_number": block_number,
                    "skipped": False,
                    "mismatches": ("activeListingCount() unreadable at pinned block",),
                },
            )
        if expected == 0:
            return (
                block_number,
                [],
                {
                    "invariants_ok": True,
                    "collected": 0,
                    "expected": 0,
                    "block_number": block_number,
                    "skipped": False,
                    "mismatches": (),
                },
            )

        # Step 3 — the slot scan.
        listing_ids, slots_scanned, zero_slots = await self._collect_listing_ids(
            expected, block_tag, headroom
        )

        # Step 4 — the positions, same block.
        positions = await self._fetch_listings(listing_ids, block_tag)

        # Step 5 — the runtime invariant assertion.
        report = check_sweep_invariants(
            positions,
            expected_count=expected,
            total_weight_onchain=agg["total_weight"] or 0,
            weighted_backing_total_onchain=agg["weighted_backing_total"] or 0,
            acquisition_fee_onchain=agg["acquisition_fee"] or 0,
            fee_share_total_onchain=agg["fee_share_total"],
        )
        report.update(
            {
                "block_number": block_number,
                "slots_scanned": slots_scanned,
                "zero_slots": zero_slots,
                "ids_collected": len(listing_ids),
                "skipped": False,
            }
        )

        result = (block_number, positions, report)
        self._last_sweep = result
        return result

    async def _collect_listing_ids(
        self, expected: int, block_tag: str, headroom: float
    ) -> tuple[list[int], int, int]:
        """Scan ``slotToListing`` upward from slot 1, skipping zeros.

        **This is the free-list trap.**  The slot space is 1-indexed and
        non-contiguous: ``_allocateSlot()`` reuses a free list, so a withdrawn
        listing leaves a permanent hole and live positions sit at slots far above
        ``activeListingCount()``.  Stopping at ``slot == activeListingCount``
        found 3,604 of 3,867 at block 25612701 and understated
        ``weightedBackingTotal`` by exactly ``263e36`` — a number that looks
        right because ``weightedBackingTotal ≈ count × 1e36``, so the shortfall
        wears the shape of a smaller pool rather than a broken scan.

        The loop is therefore bounded by the **count of non-zero ids collected**,
        with the slot budget only as a runaway guard.  The budget is sized from
        the live ``activeListingCount()`` — never a constant: the pool went from
        3,867 to 5,942 in two days (§13.6).

        Returns ``(listing_ids, slots_scanned, zero_slots_seen)``.
        """
        budget = int(expected * max(1.0, headroom)) + SLOT_SCAN_MIN_EXTRA
        listing_ids: list[int] = []
        zero_slots = 0
        slot = 1
        while len(listing_ids) < expected and slot <= budget:
            width = min(MULTICALL_MAX_CALLS, budget - slot + 1)
            calls = [
                (FWA_CORE, _SEL_SLOT_TO_LISTING + _encode_uint(s))
                for s in range(slot, slot + width)
            ]
            results = await self._multicall(calls, block_tag)
            for ok, data in results:
                if not ok or not _strip0x(data):
                    continue
                listing_id = _decode_uint(data)
                if listing_id == 0:
                    zero_slots += 1  # a free-list hole; skip it, do not stop
                    continue
                listing_ids.append(listing_id)
            slot += width

        slots_scanned = slot - 1
        if len(listing_ids) < expected:
            logger.error(
                "slot scan exhausted its %d-slot budget with %d/%d ids — the pool "
                "grew mid-sweep or the headroom is too tight; results will be "
                "marked stale",
                budget,
                len(listing_ids),
                expected,
            )
        return listing_ids, slots_scanned, zero_slots

    async def _fetch_listings(
        self, listing_ids: list[int], block_tag: str
    ) -> list[Position]:
        """Batch-read ``listings(id)`` for every collected id at the pinned block."""
        if not listing_ids:
            return []
        calls = [
            (FWA_CORE, _SEL_LISTINGS + _encode_uint(i)) for i in listing_ids
        ]
        results = await self._multicall(calls, block_tag)
        positions: list[Position] = []
        for i, listing_id in enumerate(listing_ids):
            if i >= len(results):
                break
            ok, data = results[i]
            if not ok:
                continue
            position = decode_listing(data, listing_id)
            if position is not None:
                positions.append(position)
        return positions

    # ------------------------------------------------------------------
    # Public: display names
    # ------------------------------------------------------------------

    async def fetch_collection_names(
        self, addresses: Sequence[str]
    ) -> dict[str, str]:
        """Read ERC-721 ``name()`` for each collection address.

        Returns only the addresses that answered with a usable string; the
        caller keeps its short-address fallback for the rest.  Never raises.

        This is the *authoritative* source for a collection's label and it is
        free: one ``aggregate3`` covers the whole pool.  The odds board used to
        take names from the marketplace floor lookup as a side effect, so a
        collection was named only if it also happened to be priced -- 1 of 52
        in practice, leaving the board a wall of hex.  ``name()`` answers for
        all of them, including CryptoPunks via its 721 wrapper.

        ``allowFailure`` is what makes this safe to point at arbitrary
        addresses: a contract with no ``name()`` (or none at all) comes back as
        a failed sub-call rather than reverting the batch.
        """
        wanted: list[str] = []
        seen: set[str] = set()
        for addr in addresses or ():
            key = str(addr or "").lower()
            if key.startswith("0x") and len(key) == 42 and key not in seen:
                seen.add(key)
                wanted.append(key)
        if not wanted:
            return {}

        try:
            results = await self._multicall([(a, _SEL_ERC721_NAME) for a in wanted])
        except Exception as exc:  # noqa: BLE001 — cosmetic read, degrade quietly
            logger.warning("collection name batch failed: %s", exc)
            return {}

        out: dict[str, str] = {}
        for addr, (ok, data) in zip(wanted, results):
            if not ok:
                continue
            name = decode_string(data)
            if name:
                out[addr] = name
        logger.debug("resolved %d/%d collection names", len(out), len(wanted))
        return out

    async def fetch_ens_names(
        self, addresses: Sequence[str], *, limit: int = ens.MAX_ADDRESSES
    ) -> dict[str, str]:
        """Reverse-resolve wallet addresses to **forward-verified** ENS names.

        Thin pass-through to :func:`maxpane_dashboard.data.ens.resolve_names`
        with this client's multicall, so ENS inherits the same endpoint pool
        and failure handling as every other read.  See that module for why the
        forward check is not optional.
        """
        try:
            return await ens.resolve_names(addresses, self._multicall, limit=limit)
        except Exception as exc:  # noqa: BLE001 — cosmetic read, degrade quietly
            logger.warning("ENS batch failed: %s", exc)
            return {}


__all__ = [
    "FWAClient",
    "ViewSpec",
    "HOT_VIEWS",
    "FWA_HOT_KEYS",
    "HOT_EXTRA_KEYS",
    "HOT_META_KEYS",
    "SELECTORS",
    "FWA_CONTRACTS",
    "FWA_CORE",
    "FWA_REWARDS",
    "FWA_VRF_SERVICE",
    "FWA_TOKEN",
    "FWA_TOKEN_HOOK",
    "FWA_CLAIM",
    "FWA_WHITELIST",
    "FWA_SPLITTER",
    "MULTICALL3",
    "MULTICALL_MAX_CALLS",
    "SLOT_SCAN_HEADROOM",
    "SLOT_SCAN_MIN_EXTRA",
    "LISTING_RETURN_BYTES",
    "ZERO_ADDRESS",
    "check_sweep_invariants",
    "decode_listing",
    "decode_view_results",
    "_decode_aggregate3_result",
    "_decode_address",
    "_decode_bool",
    "_decode_int",
    "_decode_string",
    "_decode_uint",
    "_encode_address",
    "_encode_aggregate3",
    "_encode_call3",
    "_encode_uint",
    "_pad_left",
    "_strip0x",
]
