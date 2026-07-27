"""Pool B log client for the Fake World Assets (FWA) dashboard.

This module owns **every** ``eth_getLogs`` call the FWA data layer makes. Nothing
else in the dashboard reads events; nothing here reads state. That split is
deliberate — the state pool and the log pool are different endpoints with
different failure modes, and mixing them is how a dashboard ends up believing a
capability probe that lied to it.


Why "Pool B", and why the endpoint list is a whitelist
------------------------------------------------------

The keyless RPCs are **not** interchangeable (findings §3). Only two of them
serve ``eth_getLogs`` at archive depth without a key:

===============================================  =========================
``https://gateway.tenderly.co/public/mainnet``   no block-range cap, but a
                                                 hard **50,000-result** cap,
                                                 returned inside an HTTP 200
``https://eth.drpc.org``                         hard **10,000-block** pages,
                                                 no JSON-RPC batching,
                                                 occasional 408
===============================================  =========================

The batching endpoint used by the state client (WP-6, ``fwa_client.py``) is
**not** on that list, and findings §13.10 explains why the omission has to be
enforced rather than merely documented: that endpoint does *not* flatly refuse
``eth_getLogs``. It serves the method perfectly well inside geth's ~128-block
state-retention window and only refuses older ranges, behind the archive gate.
**A startup capability probe with a short recent range therefore returns a false
positive**, and the client then dies on the first backfill — which by definition
reaches back further than 128 blocks.

Two consequences are baked into this module:

1. **It never capability-probes.** The endpoint capabilities above are measured
   facts recorded in the findings, not something to rediscover at runtime.
2. :data:`LOG_ENDPOINTS` is a **whitelist**, and :class:`FWALogClient` raises
   ``ValueError`` on any endpoint outside it. A blacklist of dead hosts would be
   one forgotten entry away from routing archive queries at a node that answers
   ``403 {"code": -32602, "message": "Archive requests require a personal
   token."}`` — or worse, answers a *narrow* query correctly and a wide one not
   at all.


Pagination is per-endpoint, and shrinking is adaptive
-----------------------------------------------------

``eth.drpc.org`` pages at :data:`DRPC_BLOCK_PAGE` blocks; tenderly has no block
cap and is scanned in one shot. But tenderly's 50,000-*result* cap means the one
event type that most wants a single-shot backfill — ``AcquisitionRequested``, at
58,006 instances all-time — is exactly the one that trips it, and it does so
inside an HTTP 200 body. So the window shrinks adaptively on three error
classes: a block-range cap, a result-count cap (whose ``data`` field names a
narrower range to retry, which is parsed and used), and a free-plan timeout.


Two double-counting traps
-------------------------

1. **``TopListingSet`` arrives in vacate+set PAIRS.** Taking the crown clears the
   incumbent first (``listingId=0``, ``depositor=address(0)``) and sets the
   challenger second, both in one transaction. Of the 33 all-time logs, 16 are
   vacates. A consumer that counts one crown change per log reports 33 reigns
   instead of 17 — and one that takes the last log per block without ordering by
   ``logIndex`` can land on the vacate and render an empty throne. See
   :func:`dedupe_top_listing_set`.

2. **``ConfigSet`` has 27 logs, not 6** (findings §13.11). 21 of them are a
   single launch write in one transaction at the deploy block; only 6 are
   genuine post-launch parameter changes. Unfiltered, the parameter-drift widget
   reports 21 spurious drifts the moment it loads. See :func:`config_history`.

A third trap is not double-counting but is just as easy to ship: keys 1
(``CALLBACK_GAS_LIMIT``), 24 (``VRF_KEY_HASH``) and 63 (``VRF_SERVICE``) are
emitted through ``ConfigSet`` but **rejected by the setters** — they are
constructor-only (findings §13.3). The ``settable`` flag comes from
``abis/fwa/config_keys.json``, never from the §8 prose table, so the widget
cannot imply the owner can still move them.


Events reconstruct price history exactly — against block N-1
------------------------------------------------------------

``AcquisitionRequested`` carries ``acquisitionFee`` and ``totalWeight`` as its
two non-indexed words, so a complete price history is reconstructable from
events alone with no archive *state* access at all. There is one boundary rule
(findings §13.12): the first such log in block N matches the pool state at the
**end of block N-1**, bit-for-bit. Compare it against the end of its own block
and you get a ~0.017% error that reads exactly like a rounding bug.
:func:`price_history` pins each sample to ``block_number - 1`` and says so in
the ``state_block`` field.


Degradation
-----------

Pool B is the design's one genuine single point of failure (PRD §6, §9). When
both endpoints are down this module returns

    ``{"available": False, "reason": "logs endpoint unavailable", ...}``

together with whatever last-good aggregates it already holds and the
``as_of_ts`` those aggregates were captured at. **No public method on
:class:`FWALogClient` raises.** The activity feed and crown history then render
an explicit unavailable state with an "as of HH:MM" marker; the rest of the
dashboard — which is fed by the state pool — keeps working. A silently stale
number presented as live is the one outcome this module exists to prevent.

Topic0 hashes come from ``abis/fwa/topics.json`` (42 events, locally computed
and verified against the 9 recorded in findings §8) and are never hardcoded
here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import httpx

from maxpane_dashboard.data.fwa_models import (
    FWA_SETTLEMENT_OUTCOMES,
    ConfigParam,
    DrawEvent,
    SettlementMix,
)

logger = logging.getLogger(__name__)

__all__ = [
    # endpoints / addresses
    "FWA_CORE_ADDRESS",
    "TENDERLY_GATEWAY",
    "DRPC_GATEWAY",
    "LOG_ENDPOINTS",
    "DRPC_BLOCK_PAGE",
    "ENDPOINT_BLOCK_PAGE",
    "REASON_UNAVAILABLE",
    # metadata
    "topic0",
    "event_signature",
    "load_topics",
    "load_config_keys",
    "SETTLEMENT_EVENTS",
    "OUTCOME_LABELS",
    "LOG_EVENTS",
    # decoders
    "decode_log",
    "decode_logs",
    "DECODERS",
    # aggregations (pure)
    "dedupe_logs",
    "dedupe_top_listing_set",
    "crown_history",
    "crown_summary",
    "settlement_mix",
    "settlement_mix_rows",
    "config_history",
    "config_params",
    "collection_registry",
    "price_history",
    "build_draw_events",
    # client
    "FWALogClient",
    "LogEndpointError",
]


# ---------------------------------------------------------------------------
# Configuration — Pool B only
# ---------------------------------------------------------------------------

FWA_CORE_ADDRESS = "0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c"
"""FWA core. ``CollectionWhitelistSet`` is emitted **here**, not by FWAWhitelist
(findings §13.1) — FWAWhitelist only has the write side (``setCollections`` /
``CollectionsSet``). The 51-collection allowlist is derived from core's logs."""

TENDERLY_GATEWAY = "https://gateway.tenderly.co/public/mainnet"
DRPC_GATEWAY = "https://eth.drpc.org"

LOG_ENDPOINTS: tuple[str, ...] = (TENDERLY_GATEWAY, DRPC_GATEWAY)
"""The complete set of endpoints this module will talk to. A whitelist, checked
in ``__init__``; see the module docstring for why it is not a blacklist."""

DRPC_BLOCK_PAGE = 10_000
"""``eth.drpc.org`` free plan: *"ranges over 10000 blocks are not supported"*."""

ENDPOINT_BLOCK_PAGE: dict[str, int | None] = {
    TENDERLY_GATEWAY: None,  # no block-range cap (a 50,000-RESULT cap still applies)
    DRPC_GATEWAY: DRPC_BLOCK_PAGE,
}

REASON_UNAVAILABLE = "logs endpoint unavailable"
"""The exact string the activity feed and crown history render when Pool B is
down. Stable because widgets and tests both key off it."""

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.4, 1.2)
_REQUEST_TIMEOUT = 20.0
_INTER_CALL_DELAY = 0.05
_MAX_SHRINKS_PER_WINDOW = 24
_MIN_WINDOW_BLOCKS = 1

# HTTP statuses that mean "this endpoint is not going to work at all".
_ENDPOINT_DEAD_CODES = {401, 402, 403, 451, 521, 522, 523, 524, 525, 526}

_ZERO_ADDRESS = "0x" + "0" * 40

_ABI_DIR = Path(__file__).resolve().parents[1] / "abis" / "fwa"


# ---------------------------------------------------------------------------
# Vendored metadata: topics.json + config_keys.json
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_topics() -> dict[str, dict]:
    """Load ``abis/fwa/topics.json`` — 42 events, topic0 + signature + indexed.

    Locally computed at vendoring time and verified bit-for-bit against the nine
    hashes recorded in findings §8. Never recomputed here, and never hardcoded.
    """
    with (_ABI_DIR / "topics.json").open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_config_keys() -> dict[int, dict]:
    """Load ``abis/fwa/config_keys.json`` keyed by ``int``.

    Each entry carries ``name``, ``dispatcher``, ``value_type`` and — the field
    that matters — ``settable``. Three keys emitted through ``ConfigSet`` are
    constructor-only and rejected by ``setUint``/``setAddr`` (findings §13.3);
    the flag is the only correct source for that, not the §8 prose table.
    """
    with (_ABI_DIR / "config_keys.json").open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}


def topic0(event_name: str) -> str:
    """topic0 hash for *event_name*, from the vendored table."""
    try:
        return load_topics()[event_name]["topic0"]
    except KeyError as exc:  # pragma: no cover - programmer error
        raise KeyError(f"unknown FWA event {event_name!r}") from exc


def event_signature(event_name: str) -> str:
    """Canonical solidity signature for *event_name*, from the vendored table."""
    return load_topics()[event_name]["signature"]


LOG_EVENTS: tuple[str, ...] = (
    "AcquisitionRequested",
    "NFTAllocated",
    "NFTKept",
    "DepositorBidAccepted",
    "DepositorBidAcceptedAsTokens",
    "NFTRelisted",
    "UnsettledFinalized",
    "TopListingSet",
    "TopListingFunded",
    "TopListingSettled",
    "ConfigSet",
    "CollectionWhitelistSet",
    "BackingUpdated",
    "NFTListed",
)
"""Every event this module decodes.

``NFTListed`` is here for one reason: ``NFTAllocated`` carries ``requestId`` /
``listingId`` / ``purchaser`` / ``depositor`` / ``value`` / ``randomWord`` and
**no collection address**. The only on-chain link from a listing id to its
collection and token id is ``NFTListed`` (or the WP-6 position sweep, which
:meth:`FWALogClient.draw_events` also accepts as an injected index)."""

SETTLEMENT_EVENTS: dict[str, str] = {
    "DepositorBidAcceptedAsTokens": "bid_fwa",
    "DepositorBidAccepted": "bid_eth",
    "NFTRelisted": "relist",
    "NFTKept": "kept",
    "UnsettledFinalized": "forced",
}
"""Settlement event → the stable machine key from ``FWA_SETTLEMENT_OUTCOMES``."""

OUTCOME_LABELS: dict[str, str] = {
    "bid_fwa": "Accept bid, paid in $FWA",
    "bid_eth": "Accept bid, paid in ETH",
    "relist": "Relisted — purchaser becomes depositor",
    "kept": "Kept the NFT",
    "forced": "Force-finalized",
}
"""Human strings. The feed colours by outcome **and** spells it out (PRD §11)."""

_OUTCOME_AMOUNT_FIELD: dict[str, str] = {
    # Which decoded field is "the ETH leg" of each settlement.
    #
    # bid_fwa uses ``eth_payout_wei``: the purchaser took $FWA, but the event
    # still records the ETH-denominated size of the settlement, and showing that
    # next to a row explicitly labelled "paid in $FWA" is more honest than
    # showing 0. ``token_out`` stays on the decoded dict for anyone who needs it.
    "bid_fwa": "eth_payout_wei",
    "bid_eth": "payout_wei",
    "relist": "to_depositor_wei",
    "kept": "backing_wei",
    "forced": "",  # UnsettledFinalized carries no amount at all
}

# The launch write is one transaction emitting many ConfigSet logs at the deploy
# block. Requiring several logs from a *single* tx at the earliest scanned block
# means a partial backfill that never saw the deploy block cannot mistake an
# ordinary change for the launch write.
_LAUNCH_WRITE_MIN_LOGS = 5


# ---------------------------------------------------------------------------
# Minimal ABI decode helpers (pure stdlib, no eth_abi dependency)
# ---------------------------------------------------------------------------


def _strip0x(hex_str: str) -> str:
    return hex_str[2:] if hex_str.startswith(("0x", "0X")) else hex_str


def _hex_int(value: Any, default: int = 0) -> int:
    """Parse a JSON-RPC hex quantity. Tolerates ints and missing values."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 16)
    except (TypeError, ValueError):
        return default


def _word(data: str, idx: int) -> str:
    raw = _strip0x(data or "")
    return raw[idx * 64 : idx * 64 + 64]


def _uint(data: str, idx: int = 0) -> int:
    """uint256 at 32-byte word *idx* of a data blob (0 when absent)."""
    chunk = _word(data, idx)
    return int(chunk, 16) if chunk else 0


def _bool(data: str, idx: int = 0) -> bool:
    return _uint(data, idx) != 0


def _addr_word(data: str, idx: int = 0) -> str:
    chunk = _word(data, idx)
    return "0x" + chunk[-40:].lower() if chunk else _ZERO_ADDRESS


def _addr_topic(topic: str) -> str:
    """20-byte lowercase address from a 32-byte indexed topic."""
    return "0x" + _strip0x(topic).lower()[-40:]


def _base(log: Mapping[str, Any], event: str) -> dict:
    """The provenance fields every decoded event carries.

    ``log_index`` matters as much as ``block_number``: several FWA events fire
    more than once per block, and both the crown vacate+set pair and the §13.12
    price-history boundary rule depend on ordering by ``(block, log_index)``.
    """
    return {
        "event": event,
        "block_number": _hex_int(log.get("blockNumber")),
        "log_index": _hex_int(log.get("logIndex")),
        "tx_hash": str(log.get("transactionHash") or "0x").lower(),
        # blockTimestamp is served by both Pool B endpoints; 0 means "unknown",
        # never "1970" — callers must treat it as missing.
        "ts": _hex_int(log.get("blockTimestamp")),
        "address": str(log.get("address") or "").lower(),
    }


# ---------------------------------------------------------------------------
# Decoders — one per event.
#
# Word counting discipline: only NON-indexed parameters live in ``data``, in
# declaration order. Every signature below is quoted from the vendored ABI so
# the count is checkable by eye against the code.
# ---------------------------------------------------------------------------


def _decode_acquisition_requested(log: Mapping[str, Any]) -> dict | None:
    """``AcquisitionRequested(uint256 requestId, address purchaser,
    uint256 acquisitionFee, uint256 totalWeight)`` — first two indexed.

    The two data words are the whole reason a price history needs no archive
    state. See :func:`price_history` for the block N-1 boundary rule.
    """
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    data = log.get("data", "0x")
    out = _base(log, "AcquisitionRequested")
    out.update(
        request_id=topics[1].lower(),  # bytes32-shaped VRF request id, kept as hex
        purchaser=_addr_topic(topics[2]),
        acquisition_fee_wei=_uint(data, 0),
        total_weight=_uint(data, 1),
    )
    return out


def _decode_nft_allocated(log: Mapping[str, Any]) -> dict | None:
    """``NFTAllocated(uint256 requestId, uint256 listingId, address purchaser,
    address depositor, uint256 value, uint256 randomWord)`` — first three indexed.

    Note what is **absent**: no collection, no tokenId. Those come from
    ``NFTListed`` or the WP-6 sweep.
    """
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    data = log.get("data", "0x")
    out = _base(log, "NFTAllocated")
    out.update(
        request_id=topics[1].lower(),
        listing_id=_hex_int(topics[2]),
        purchaser=_addr_topic(topics[3]),
        depositor=_addr_word(data, 0),
        value_wei=_uint(data, 1),
        random_word=_uint(data, 2),
    )
    return out


def _decode_nft_kept(log: Mapping[str, Any]) -> dict | None:
    """``NFTKept(uint256 listingId, address purchaser, address depositor,
    uint256 backing)`` — first three indexed, one data word."""
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    out = _base(log, "NFTKept")
    out.update(
        listing_id=_hex_int(topics[1]),
        purchaser=_addr_topic(topics[2]),
        depositor=_addr_topic(topics[3]),
        backing_wei=_uint(log.get("data", "0x"), 0),
        outcome="kept",
    )
    return out


def _decode_depositor_bid_accepted(log: Mapping[str, Any]) -> dict | None:
    """``DepositorBidAccepted(uint256 listingId, address purchaser,
    address depositor, uint256 payout, uint256 retained)`` — TWO data words.

    ``payout`` is what the purchaser received. It is 85% of backing at the live
    ``settlementDiscountBps`` — a payout **rate**, not a discount (models trap 2).
    """
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    data = log.get("data", "0x")
    out = _base(log, "DepositorBidAccepted")
    out.update(
        listing_id=_hex_int(topics[1]),
        purchaser=_addr_topic(topics[2]),
        depositor=_addr_topic(topics[3]),
        payout_wei=_uint(data, 0),
        retained_wei=_uint(data, 1),
        outcome="bid_eth",
    )
    return out


def _decode_depositor_bid_accepted_as_tokens(log: Mapping[str, Any]) -> dict | None:
    """``DepositorBidAcceptedAsTokens(uint256 listingId, address purchaser,
    address depositor, uint256 ethPayout, uint256 retained, uint256 tokenOut)``
    — THREE data words. 73.9% of every settlement in the protocol's history."""
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    data = log.get("data", "0x")
    out = _base(log, "DepositorBidAcceptedAsTokens")
    out.update(
        listing_id=_hex_int(topics[1]),
        purchaser=_addr_topic(topics[2]),
        depositor=_addr_topic(topics[3]),
        eth_payout_wei=_uint(data, 0),
        retained_wei=_uint(data, 1),
        token_out=_uint(data, 2),
        outcome="bid_fwa",
    )
    return out


def _decode_nft_relisted(log: Mapping[str, Any]) -> dict | None:
    """``NFTRelisted(uint256 listingId, uint256 newListingId,
    uint256 toDepositor)`` — the first TWO are indexed, so ``toDepositor`` is
    the only data word. Both ids are uint256 topics, not addresses."""
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    out = _base(log, "NFTRelisted")
    out.update(
        listing_id=_hex_int(topics[1]),
        new_listing_id=_hex_int(topics[2]),
        to_depositor_wei=_uint(log.get("data", "0x"), 0),
        outcome="relist",
    )
    return out


def _decode_unsettled_finalized(log: Mapping[str, Any]) -> dict | None:
    """``UnsettledFinalized(uint256 listingId, address purchaser,
    address depositor)`` — all three indexed, **no data words at all**.

    Zero occurrences all-time. The settlement-mix table still renders the row.
    """
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    out = _base(log, "UnsettledFinalized")
    out.update(
        listing_id=_hex_int(topics[1]),
        purchaser=_addr_topic(topics[2]),
        depositor=_addr_topic(topics[3]),
        outcome="forced",
    )
    return out


def _decode_top_listing_set(log: Mapping[str, Any]) -> dict | None:
    """``TopListingSet(uint256 listingId, address depositor)`` — both indexed,
    empty data.

    ``is_vacate`` is computed here rather than at the aggregation site so that
    every consumer of a decoded log sees the flag, whether or not it remembered
    to call :func:`dedupe_top_listing_set`.
    """
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    listing_id = _hex_int(topics[1])
    holder = _addr_topic(topics[2])
    out = _base(log, "TopListingSet")
    out.update(
        listing_id=listing_id,
        holder=holder,
        is_vacate=(listing_id == 0 and holder == _ZERO_ADDRESS),
    )
    return out


def _decode_top_listing_funded(log: Mapping[str, Any]) -> dict | None:
    """``TopListingFunded(uint256 listingId, uint256 amount, uint256 newPot)``
    — only ``listingId`` is indexed, so TWO data words."""
    topics = log.get("topics") or []
    if len(topics) < 2:
        return None
    data = log.get("data", "0x")
    out = _base(log, "TopListingFunded")
    out.update(
        listing_id=_hex_int(topics[1]),
        amount_wei=_uint(data, 0),
        new_pot_wei=_uint(data, 1),
    )
    return out


def _decode_top_listing_settled(log: Mapping[str, Any]) -> dict | None:
    """``TopListingSettled(uint256 listingId, address depositor,
    uint256 amount)`` — first two indexed, one data word."""
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    out = _base(log, "TopListingSettled")
    out.update(
        listing_id=_hex_int(topics[1]),
        holder=_addr_topic(topics[2]),
        amount_wei=_uint(log.get("data", "0x"), 0),
    )
    return out


def _decode_config_set(log: Mapping[str, Any]) -> dict | None:
    """``ConfigSet(uint256 key, uint256 value)`` — key indexed, value in data.

    The key is resolved through ``config_keys.json``, which is also where the
    ``settable`` flag comes from. Unknown keys resolve to ``"key {n}"`` and
    ``settable=None`` — an unrecognised key means the contract shipped a longer
    key set, and the honest answer is the raw number, not a neighbouring name.
    """
    topics = log.get("topics") or []
    if len(topics) < 2:
        return None
    key = _hex_int(topics[1])
    meta = load_config_keys().get(key)
    out = _base(log, "ConfigSet")
    out.update(
        key=key,
        name=(meta or {}).get("name", f"key {key}"),
        value=_uint(log.get("data", "0x"), 0),
        value_type=(meta or {}).get("value_type", "uint256"),
        dispatcher=(meta or {}).get("dispatcher"),
        settable=(meta or {}).get("settable"),
        known_key=meta is not None,
    )
    return out


def _decode_collection_whitelist_set(log: Mapping[str, Any]) -> dict | None:
    """``CollectionWhitelistSet(address collection, bool allowed)`` — collection
    indexed, ``allowed`` in data. Emitted by FWA **core** (findings §13.1)."""
    topics = log.get("topics") or []
    if len(topics) < 2:
        return None
    out = _base(log, "CollectionWhitelistSet")
    out.update(
        collection=_addr_topic(topics[1]),
        allowed=_bool(log.get("data", "0x"), 0),
    )
    return out


def _decode_backing_updated(log: Mapping[str, Any]) -> dict | None:
    """``BackingUpdated(uint256 listingId, address depositor, uint256 oldBacking,
    uint256 newBacking, uint256 newWeight)`` — THREE data words.

    Its mere existence refutes "backing is immutable for a listing's life"
    (findings §12.1). Each one moves a position's inverse weight, so a cached
    WP-6 sweep must invalidate on these — that is correctness rule 8.
    """
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    data = log.get("data", "0x")
    out = _base(log, "BackingUpdated")
    out.update(
        listing_id=_hex_int(topics[1]),
        depositor=_addr_topic(topics[2]),
        old_backing_wei=_uint(data, 0),
        new_backing_wei=_uint(data, 1),
        new_weight=_uint(data, 2),
    )
    return out


def _decode_nft_listed(log: Mapping[str, Any]) -> dict | None:
    """``NFTListed(uint256 listingId, uint256 slot, address depositor,
    address collection, uint256 tokenId, uint256 weight, uint256 value)``
    — first three indexed, so FOUR data words."""
    topics = log.get("topics") or []
    if len(topics) < 4:
        return None
    data = log.get("data", "0x")
    out = _base(log, "NFTListed")
    out.update(
        listing_id=_hex_int(topics[1]),
        slot=_hex_int(topics[2]),
        depositor=_addr_topic(topics[3]),
        collection=_addr_word(data, 0),
        token_id=_uint(data, 1),
        weight=_uint(data, 2),
        value_wei=_uint(data, 3),
    )
    return out


DECODERS: dict[str, Callable[[Mapping[str, Any]], dict | None]] = {
    "AcquisitionRequested": _decode_acquisition_requested,
    "NFTAllocated": _decode_nft_allocated,
    "NFTKept": _decode_nft_kept,
    "DepositorBidAccepted": _decode_depositor_bid_accepted,
    "DepositorBidAcceptedAsTokens": _decode_depositor_bid_accepted_as_tokens,
    "NFTRelisted": _decode_nft_relisted,
    "UnsettledFinalized": _decode_unsettled_finalized,
    "TopListingSet": _decode_top_listing_set,
    "TopListingFunded": _decode_top_listing_funded,
    "TopListingSettled": _decode_top_listing_settled,
    "ConfigSet": _decode_config_set,
    "CollectionWhitelistSet": _decode_collection_whitelist_set,
    "BackingUpdated": _decode_backing_updated,
    "NFTListed": _decode_nft_listed,
}


@lru_cache(maxsize=1)
def _decoder_by_topic0() -> dict[str, tuple[str, Callable]]:
    return {topic0(name): (name, fn) for name, fn in DECODERS.items()}


def decode_log(log: Mapping[str, Any]) -> dict | None:
    """Decode one raw JSON-RPC log by its topic0. ``None`` when unrecognised.

    Never raises: a malformed log from a flaky endpoint is dropped and counted,
    not allowed to kill a whole backfill page.
    """
    topics = log.get("topics") or []
    if not topics:
        return None
    entry = _decoder_by_topic0().get(str(topics[0]).lower())
    if entry is None:
        return None
    name, fn = entry
    try:
        return fn(log)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("%s decode failed: %s", name, exc)
        return None


def decode_logs(logs: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Decode many logs, dropping the ones that do not decode."""
    out: list[dict] = []
    for log in logs:
        decoded = decode_log(log)
        if decoded is not None:
            out.append(decoded)
    return out


# ---------------------------------------------------------------------------
# Dedupe + aggregations (pure — no network, no client state)
# ---------------------------------------------------------------------------


def _identity(entry: Mapping[str, Any]) -> tuple[int, int, str]:
    """The identity of a log: ``(blockNumber, logIndex, txHash)``.

    Backfill pages and the tail overlap by design (a tail that resumes at
    ``last_seen_block`` re-reads that block so a partially-scanned block is not
    lost). Without an identity key those overlaps become duplicate reigns and
    inflated settlement counts.
    """
    return (
        int(entry.get("block_number", 0)),
        int(entry.get("log_index", 0)),
        str(entry.get("tx_hash", "")),
    )


def _order_key(entry: Mapping[str, Any]) -> tuple[int, int]:
    return (int(entry.get("block_number", 0)), int(entry.get("log_index", 0)))


def dedupe_logs(entries: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Drop repeats by ``(block, logIndex, txHash)`` and sort chronologically.

    This is the *identity* dedupe. The crown's vacate+set pairing is a separate,
    semantic problem — see :func:`dedupe_top_listing_set`.
    """
    seen: dict[tuple[int, int, str], dict] = {}
    for entry in entries:
        seen[_identity(entry)] = dict(entry)
    return sorted(seen.values(), key=_order_key)


def dedupe_top_listing_set(entries: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Collapse ``TopListingSet`` logs into one row per actual reign.

    Taking the crown emits two logs in a single transaction: the incumbent is
    cleared (``listingId == 0``, ``depositor == address(0)``) and the challenger
    is then set. Across all 33 all-time logs there are 16 such pairs, so a naive
    reader reports 33 reigns where there are 17.

    Two things happen here, in order:

    1. identity dedupe on ``(block, logIndex, txHash)`` — kills page overlap;
    2. drop every vacate log — a vacate is the *shadow* of the set that follows
       it in the same transaction, not an event in its own right.

    Ordering by ``(block, logIndex)`` before the drop is what stops the other
    half of the trap: "last log in the block" lands on the vacate roughly half
    the time, and renders an empty throne while someone is wearing the crown.

    A genuine abdication — a vacate with no set after it in the same
    transaction — would leave the crown truly empty. None exists in the
    protocol's history so far, and the live ``vacant`` flag on ``Crown`` is
    authoritative for the *current* state regardless; this function is history.
    """
    ordered = dedupe_logs(entries)
    return [e for e in ordered if not e.get("is_vacate")]


def crown_history(
    set_entries: Iterable[Mapping[str, Any]],
    settled_entries: Iterable[Mapping[str, Any]] = (),
) -> list[dict]:
    """Per-**holder** crown rows matching ``FWA_ROW_KEYS["crown_history"]``.

    Not one row per event: WP-1's contract is an aggregation keyed by wallet
    (``rank``, ``holder``, ``reigns``, ``payout_eth``, ``last_block``,
    ``last_ts``). One wallet currently holds four of the seventeen reigns, which
    is only visible once the vacate logs are gone *and* the sets are grouped.

    Ranked by payout first, then reign count — the leaderboard question is "who
    earned most from the crown", and reign count is the tiebreak.

    ``payout_eth`` is a float because these rows are the presentation payload;
    the exact wei total stays available on :func:`crown_summary`.
    """
    reigns = dedupe_top_listing_set(set_entries)
    payouts = dedupe_logs(settled_entries)

    by_holder: dict[str, dict] = {}

    def _slot(holder: str) -> dict:
        return by_holder.setdefault(
            holder,
            {
                "holder": holder,
                "reigns": 0,
                "payout_wei": 0,
                "last_block": None,
                "last_ts": None,
            },
        )

    for entry in reigns:
        row = _slot(str(entry.get("holder", "")).lower())
        row["reigns"] += 1
        block = int(entry.get("block_number", 0))
        if row["last_block"] is None or block >= row["last_block"]:
            row["last_block"] = block
            ts = int(entry.get("ts", 0))
            row["last_ts"] = ts or None

    for entry in payouts:
        row = _slot(str(entry.get("holder", "")).lower())
        row["payout_wei"] += int(entry.get("amount_wei", 0))
        block = int(entry.get("block_number", 0))
        if row["last_block"] is None or block >= row["last_block"]:
            row["last_block"] = block
            ts = int(entry.get("ts", 0))
            row["last_ts"] = ts or row["last_ts"]

    ranked = sorted(
        by_holder.values(),
        key=lambda r: (-r["payout_wei"], -r["reigns"], r["holder"]),
    )
    return [
        {
            "rank": i,
            "holder": row["holder"],
            "reigns": row["reigns"],
            "payout_eth": row["payout_wei"] / 1e18,
            "last_block": row["last_block"],
            "last_ts": row["last_ts"],
        }
        for i, row in enumerate(ranked, start=1)
    ]


def crown_summary(
    set_entries: Iterable[Mapping[str, Any]],
    settled_entries: Iterable[Mapping[str, Any]] = (),
) -> dict:
    """Crown totals, both deduped and raw.

    ``sets_total`` is the **deduped** reign count, which is what
    ``FWA_DATA_KEYS["crown_sets_total"]`` asks for. ``raw_set_logs`` and
    ``vacate_logs`` are kept alongside it so the 33-vs-17 gap is inspectable
    rather than mysterious: findings §8 counts *logs*, this dashboard counts
    *reigns*, and they are both right about different things.
    """
    ordered = dedupe_logs(set_entries)
    reigns = [e for e in ordered if not e.get("is_vacate")]
    payouts = dedupe_logs(settled_entries)
    amounts = [int(e.get("amount_wei", 0)) for e in payouts]
    return {
        "raw_set_logs": len(ordered),
        "vacate_logs": len(ordered) - len(reigns),
        "sets_total": len(reigns),
        "distinct_holders": len({str(e.get("holder", "")).lower() for e in reigns}),
        "payouts_total": len(payouts),
        "paid_wei": sum(amounts),
        "paid_eth": sum(amounts) / 1e18,
        "largest_payout_wei": max(amounts, default=0),
        "largest_payout_eth": max(amounts, default=0) / 1e18,
    }


def settlement_mix(counts: Mapping[str, int]) -> tuple[SettlementMix, ...]:
    """Five ``SettlementMix`` rows from a mapping of counts.

    *counts* may be keyed either by event name (``"NFTKept"``) or by outcome key
    (``"kept"``); both are accepted so a caller can hand over raw per-event
    tallies without translating first.

    Always five rows, always in :data:`FWA_SETTLEMENT_OUTCOMES` order, even when
    a category is zero — ``UnsettledFinalized`` has never fired and the table
    must show that as ``0``, not omit the row. An empty total yields five zero
    shares rather than a ``ZeroDivisionError``.

    ``share_pct`` is left unrounded so the five values sum to exactly 100.0;
    rounding for display happens at the widget.
    """
    tallies = {key: 0 for key in FWA_SETTLEMENT_OUTCOMES}
    for key, value in (counts or {}).items():
        outcome = SETTLEMENT_EVENTS.get(str(key), str(key))
        if outcome in tallies:
            tallies[outcome] += int(value)
    total = sum(tallies.values())
    return tuple(
        SettlementMix(
            outcome=outcome,
            label=OUTCOME_LABELS[outcome],
            count=tallies[outcome],
            share_pct=(tallies[outcome] / total * 100.0) if total else 0.0,
        )
        for outcome in FWA_SETTLEMENT_OUTCOMES
    )


def settlement_mix_rows(counts: Mapping[str, int]) -> list[dict]:
    """:func:`settlement_mix` flattened to ``FWA_ROW_KEYS["settlement_mix"]``."""
    return [row.model_dump() for row in settlement_mix(counts)]


def _infer_launch_block(entries: Sequence[Mapping[str, Any]]) -> int | None:
    """Identify the deploy-time ``ConfigSet`` bulk write, or ``None``.

    The launch write is *one transaction* emitting many ``ConfigSet`` logs at
    the earliest block in the scan (21 of the 27 all-time logs). Demanding a
    single tx and at least :data:`_LAUNCH_WRITE_MIN_LOGS` of them means a
    partial backfill that never reached the deploy block cannot mistake an
    ordinary parameter change for the launch write and silently hide it.
    """
    if not entries:
        return None
    earliest = min(int(e.get("block_number", 0)) for e in entries)
    at_block = [e for e in entries if int(e.get("block_number", 0)) == earliest]
    if len(at_block) < _LAUNCH_WRITE_MIN_LOGS:
        return None
    if len({str(e.get("tx_hash", "")) for e in at_block}) != 1:
        return None
    return earliest


def config_history(
    entries: Iterable[Mapping[str, Any]],
    *,
    include_launch: bool = False,
    launch_block: int | None = None,
) -> list[dict]:
    """Post-launch ``ConfigSet`` changes, resolved through ``config_keys.json``.

    There are 27 ``ConfigSet`` logs in the protocol's history but only **6**
    genuine parameter changes (findings §13.11). The other 21 are the launch
    write. Filtering them is not cosmetic: unfiltered, the parameter-drift
    widget reports 21 drifts the first time it loads, and a user who sees 21
    owner actions on a contract with an EOA owner and no timelock will read it
    as an alarm.

    Every row carries ``settable`` straight from ``config_keys.json``. Keys 1,
    24 and 63 are ``False`` there — emitted through ``ConfigSet`` at
    construction but rejected by the setters (findings §13.3). The widget must
    not imply the owner can still move them.
    """
    ordered = dedupe_logs(entries)
    if launch_block is None:
        launch_block = _infer_launch_block(ordered)
    rows = []
    for entry in ordered:
        is_launch = launch_block is not None and (
            int(entry.get("block_number", 0)) == launch_block
        )
        if is_launch and not include_launch:
            continue
        row = dict(entry)
        row["is_launch_write"] = is_launch
        rows.append(row)
    return rows


def config_params(
    entries: Iterable[Mapping[str, Any]],
    live_values: Mapping[int, int] | None = None,
    *,
    include_launch: bool = False,
) -> tuple[ConfigParam, ...]:
    """Latest value per key as ``ConfigParam`` models.

    ``is_drift`` compares a live read against the last ``ConfigSet`` for that
    key — **never** against a documented value (PRD §7 rule 6). Absent a live
    read, drift is ``False`` rather than guessed: "unknown" must not render as
    "changed".
    """
    latest: dict[int, dict] = {}
    for row in config_history(entries, include_launch=include_launch):
        latest[int(row["key"])] = row
    out = []
    for key in sorted(latest):
        row = latest[key]
        live = (live_values or {}).get(key)
        out.append(
            ConfigParam(
                key=key,
                name=str(row.get("name", f"key {key}")),
                value=int(live if live is not None else row.get("value", 0)),
                block_number=int(row.get("block_number", 0)),
                is_drift=bool(live is not None and int(live) != int(row.get("value", 0))),
            )
        )
    return tuple(out)


def collection_registry(entries: Iterable[Mapping[str, Any]]) -> dict[str, dict]:
    """Allowlist state per collection, last write wins.

    51 collections were whitelisted on chain and none has been blocked, which
    refutes the docs' "live allowlist is the 16 launch collections" (rule 7 —
    never the docs' 16). Returns every address ever seen with its current
    ``allowed`` flag, so a future de-listing shows up as ``allowed=False``
    rather than vanishing.
    """
    registry: dict[str, dict] = {}
    for entry in dedupe_logs(entries):
        address = str(entry.get("collection", "")).lower()
        if not address:
            continue
        registry[address] = {
            "collection": address,
            "allowed": bool(entry.get("allowed")),
            "block_number": int(entry.get("block_number", 0)),
            "ts": int(entry.get("ts", 0)) or None,
        }
    return registry


def price_history(entries: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Acquisition-price samples reconstructed from ``AcquisitionRequested``.

    The event's two non-indexed words are ``acquisitionFee`` and ``totalWeight``,
    so the full price curve needs no archive *state* access at all.

    **The boundary rule (findings §13.12).** The first such log in block N
    carries the pool state as of the **end of block N-1**, bit-for-bit — verified
    on 7 of 8 consecutive sampled blocks, the exception being a block with an
    earlier state-mutating tx. Each sample therefore reports
    ``state_block = block_number - 1``. Comparing a sample against
    ``acquisitionFee()`` at the end of *its own* block instead yields a 0.017%
    delta that looks exactly like a rounding bug and is not one: at block
    25612701 the last event reads 136237209948799268 while the end-of-block
    state reads 136260883651302691, because the pool moved later in the block.

    Only the **first** event per block is kept, for the same reason: later events
    in a block sit after intra-block mutations and no longer align with any block
    boundary. ``events_in_block`` records how many were collapsed.
    """
    ordered = dedupe_logs(entries)
    by_block: dict[int, dict] = {}
    counts: dict[int, int] = {}
    for entry in ordered:
        block = int(entry.get("block_number", 0))
        counts[block] = counts.get(block, 0) + 1
        if block not in by_block:
            by_block[block] = entry
    out = []
    for block in sorted(by_block):
        entry = by_block[block]
        out.append(
            {
                "block_number": block,
                "state_block": block - 1,  # §13.12 — pin to N-1, never to N
                "log_index": int(entry.get("log_index", 0)),
                "ts": int(entry.get("ts", 0)) or None,
                "acquisition_fee_wei": int(entry.get("acquisition_fee_wei", 0)),
                "total_weight": int(entry.get("total_weight", 0)),
                "events_in_block": counts[block],
            }
        )
    return out


def build_draw_events(
    allocations: Iterable[Mapping[str, Any]],
    settlements: Iterable[Mapping[str, Any]],
    *,
    requests: Iterable[Mapping[str, Any]] = (),
    listing_index: Mapping[int, Mapping[str, Any]] | None = None,
    limit: int = 50,
) -> tuple[DrawEvent, ...]:
    """Activity-feed lines: a VRF draw paired with the settlement that followed.

    Pairing is by ``listing_id``, taking the **earliest** settlement at or after
    the allocation block — a listing can be relisted and settled again, and the
    row for a given draw belongs to that draw's settlement, not a later one.

    Unsettled draws are kept, with ``outcome=""`` and an explicit "awaiting
    settlement" label. Dropping them would make the feed quietly lag the chain
    by up to the settlement window.

    ``collection`` / ``token_id`` are not in ``NFTAllocated``. They come from
    *listing_index* — a ``{listing_id: {"collection", "token_id",
    "collection_name"}}`` map that the manager builds from ``NFTListed`` logs or
    the WP-6 position sweep. Without it the address falls back to the zero
    address and the name to ``None``; the feed shows an unresolved row rather
    than inventing a collection.

    Newest first, capped at *limit*.
    """
    index = listing_index or {}
    request_ts: dict[str, dict] = {
        str(r.get("request_id")): dict(r) for r in requests
    }

    by_listing: dict[int, list[dict]] = {}
    for entry in dedupe_logs(settlements):
        if entry.get("event") not in SETTLEMENT_EVENTS:
            continue
        by_listing.setdefault(int(entry.get("listing_id", 0)), []).append(dict(entry))
    for rows in by_listing.values():
        rows.sort(key=_order_key)

    out: list[DrawEvent] = []
    for alloc in sorted(dedupe_logs(allocations), key=_order_key, reverse=True):
        listing_id = int(alloc.get("listing_id", 0))
        alloc_key = _order_key(alloc)
        settlement = next(
            (s for s in by_listing.get(listing_id, []) if _order_key(s) >= alloc_key),
            None,
        )
        outcome = str(settlement.get("outcome", "")) if settlement else ""
        amount_field = _OUTCOME_AMOUNT_FIELD.get(outcome, "")
        amount_wei = (
            int(settlement.get(amount_field, 0))
            if settlement and amount_field
            else 0
        )

        meta = index.get(listing_id) or {}
        req = request_ts.get(str(alloc.get("request_id")), {})
        ts = int(alloc.get("ts", 0)) or int(req.get("ts", 0))

        token_id = meta.get("token_id")
        out.append(
            DrawEvent(
                ts=ts,
                block_number=int(alloc.get("block_number", 0)),
                tx_hash=str(alloc.get("tx_hash", "0x")),
                purchaser=str(alloc.get("purchaser", _ZERO_ADDRESS)).lower(),
                collection=str(meta.get("collection", _ZERO_ADDRESS)).lower(),
                collection_name=meta.get("collection_name"),
                token_id=int(token_id) if token_id is not None else None,
                outcome=outcome,
                outcome_label=(
                    OUTCOME_LABELS.get(outcome, "") if outcome else "Awaiting settlement"
                ),
                amount_wei=amount_wei,
            )
        )
        if len(out) >= limit:
            break
    return tuple(out)


# ---------------------------------------------------------------------------
# Endpoint error classification
# ---------------------------------------------------------------------------


class LogEndpointError(RuntimeError):
    """An endpoint-level failure. Internal — never escapes a public method.

    ``kind`` is one of:

    ``range_cap``    the endpoint refuses the block span (drpc's 10,000 cap)
    ``result_cap``   too many results; ``suggested_to`` may name a narrower end
    ``timeout``      free-plan timeout, retryable with a smaller window
    ``rate_limit``   429 / -32005 / -32029 — retryable, rotate endpoints
    ``archive``      archive gate; this endpoint cannot serve historical logs
    ``dead``         endpoint is down or now requires a key
    ``transport``    connection-level failure
    ``rpc``          some other JSON-RPC error
    """

    def __init__(self, kind: str, message: str, *, suggested_to: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.suggested_to = suggested_to


_SHRINKABLE = {"range_cap", "result_cap", "timeout"}

# "Try with this block range [0x185d029, 0x186c47d]." — tenderly names a
# narrower range in the error's `data` field. Parsing it beats halving blindly.
_SUGGESTED_RANGE_RE = re.compile(
    r"\[\s*(0x[0-9a-fA-F]+|\d+)\s*,\s*(0x[0-9a-fA-F]+|\d+)\s*\]"
)


def _parse_suggested_to(text: str) -> int | None:
    match = _SUGGESTED_RANGE_RE.search(text or "")
    if not match:
        return None
    raw = match.group(2)
    try:
        return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return None


def _classify_rpc_error(error: Any) -> LogEndpointError:
    """Map a JSON-RPC ``error`` member onto a :class:`LogEndpointError`.

    Several of these arrive inside an **HTTP 200** — the tenderly result cap, the
    auth failure from an endpoint that has quietly started requiring a key, the
    Multicall3 unmarshal error. A client that branches on HTTP status alone
    mishandles all of them, so every response body is checked for an ``error``
    member regardless of status.
    """
    if not isinstance(error, Mapping):
        return LogEndpointError("rpc", str(error))
    code = error.get("code")
    message = str(error.get("message", ""))
    data = str(error.get("data", ""))
    blob = f"{message} {data}".lower()

    if "archive request" in blob or "personal token" in blob:
        return LogEndpointError("archive", message or data)
    if "ranges over" in blob or ("block range" in blob and "not supported" in blob):
        return LogEndpointError("range_cap", message or data)
    if "returned more than" in blob or "more than 50000 results" in blob:
        return LogEndpointError(
            "result_cap", message or data, suggested_to=_parse_suggested_to(data)
        )
    if "timeout" in blob:
        return LogEndpointError("timeout", message or data)
    if code in (-32005, -32029) or "rate limit" in blob or "too many requests" in blob:
        return LogEndpointError("rate_limit", message or data)
    if "api key" in blob or "unauthorized" in blob:
        return LogEndpointError("dead", message or data)
    # drpc reports its range cap with a bespoke code 35 and no standard marker.
    if code == 35:
        return LogEndpointError("range_cap", message or data)
    return LogEndpointError("rpc", message or data or str(error))


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FWALogClient:
    """Pool B log client: backfill, tail, decode, aggregate, degrade.

    Every public method is exception-safe. Failure changes the values and flips
    ``available``; it never removes a key and never raises into the refresh loop.

    Parameters
    ----------
    endpoints:
        Override the endpoint order. Every entry must be in
        :data:`LOG_ENDPOINTS` — anything else raises ``ValueError`` at
        construction, which is where a routing mistake is cheap.
    http_client:
        Inject a pre-configured ``httpx.AsyncClient``. Tests pass one wired to a
        transport that raises on use, which is what proves the suite touches no
        network.
    core_address:
        FWA core. ``CollectionWhitelistSet`` is emitted here (findings §13.1).
    """

    def __init__(
        self,
        endpoints: Sequence[str] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        core_address: str = FWA_CORE_ADDRESS,
    ) -> None:
        chosen = tuple(endpoints) if endpoints else LOG_ENDPOINTS
        for url in chosen:
            if url not in LOG_ENDPOINTS:
                raise ValueError(
                    f"{url!r} is not a Pool B log endpoint. Only {LOG_ENDPOINTS} "
                    "serve eth_getLogs at archive depth keylessly; the state "
                    "pool's batching endpoint answers short recent ranges and "
                    "gates everything older (findings §13.10), so accepting it "
                    "here would pass a capability probe and then fail the first "
                    "backfill."
                )
        if not chosen:
            raise ValueError("at least one Pool B endpoint is required")

        self._endpoints: tuple[str, ...] = chosen
        self._core = core_address
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._request_id = 0
        self._last_rpc_at = 0.0
        self._scan_lock = asyncio.Lock()

        # Per-event store, keyed by log identity so overlapping pages collapse.
        self._store: dict[str, dict[tuple[int, int, str], dict]] = {
            name: {} for name in LOG_EVENTS
        }
        self.last_seen_block: int = 0
        self._scanned_from: int | None = None
        self._available = False
        self._reason: str | None = REASON_UNAVAILABLE
        self._as_of_ts: float | None = None
        self._launch_block: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> FWALogClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True once at least one scan has succeeded and none has since failed."""
        return self._available

    @property
    def unavailable_reason(self) -> str | None:
        return self._reason

    @property
    def as_of_ts(self) -> float | None:
        """Wall-clock time of the last **successful** scan.

        Survives failure on purpose: it is what turns a stale number into an
        honest "as of HH:MM" instead of a lie about being live.
        """
        return self._as_of_ts

    def status(self) -> dict:
        """``{"available", "reason", "as_of_ts", "last_seen_block"}``."""
        return {
            "available": self._available,
            "reason": self._reason,
            "as_of_ts": self._as_of_ts,
            "last_seen_block": self.last_seen_block,
        }

    def _mark_ok(self, to_block: int) -> None:
        self._available = True
        self._reason = None
        self._as_of_ts = time.time()
        self.last_seen_block = max(self.last_seen_block, to_block)

    def _mark_down(self, reason: str = REASON_UNAVAILABLE) -> None:
        self._available = False
        self._reason = reason

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def _post(self, url: str, payload: dict) -> Any:
        """One JSON-RPC round trip. Raises :class:`LogEndpointError` on failure."""
        elapsed = time.monotonic() - self._last_rpc_at
        if self._last_rpc_at > 0 and elapsed < _INTER_CALL_DELAY:
            await asyncio.sleep(_INTER_CALL_DELAY - elapsed)
        self._last_rpc_at = time.monotonic()

        last: LogEndpointError | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.post(url, json=payload)
            except Exception as exc:  # httpx transport errors and injected doubles
                last = LogEndpointError("transport", f"{type(exc).__name__}: {exc}")
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise last from exc

            status = resp.status_code
            body: Any = None
            try:
                body = resp.json()
            except Exception:
                body = None

            # Check for a JSON-RPC error member FIRST: the result cap, the
            # now-keyed auth failure and the unmarshal error all arrive inside
            # an HTTP 200.
            if isinstance(body, Mapping) and body.get("error") is not None:
                err = _classify_rpc_error(body["error"])
                if err.kind == "rate_limit" and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    last = err
                    continue
                raise err
            if isinstance(body, list):
                # Batch-shaped error body (some endpoints answer 429 this way).
                for item in body:
                    if isinstance(item, Mapping) and item.get("error") is not None:
                        raise _classify_rpc_error(item["error"])

            if status in _ENDPOINT_DEAD_CODES:
                raise LogEndpointError("dead", f"HTTP {status} from {url}")
            if status == 429:
                last = LogEndpointError("rate_limit", f"HTTP 429 from {url}")
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise last
            if status == 408:
                raise LogEndpointError("timeout", f"HTTP 408 from {url}")
            if status >= 500:
                last = LogEndpointError("transport", f"HTTP {status} from {url}")
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise last
            if status >= 400:
                raise LogEndpointError("rpc", f"HTTP {status} from {url}")
            if not isinstance(body, Mapping):
                raise LogEndpointError("rpc", f"non-JSON body from {url}")
            return body.get("result")

        raise last or LogEndpointError("transport", f"{url} exhausted retries")

    def _payload(self, method: str, params: list) -> dict:
        self._request_id += 1
        return {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

    # ------------------------------------------------------------------
    # eth_getLogs with per-endpoint pagination + adaptive shrinking
    # ------------------------------------------------------------------

    async def _get_logs_window(
        self, url: str, topics: list, from_block: int, to_block: int
    ) -> list[dict]:
        params = {
            "address": self._core,
            "topics": topics,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        result = await self._post(url, self._payload("eth_getLogs", [params]))
        return list(result) if isinstance(result, list) else []

    async def _scan_endpoint(
        self, url: str, topics: list, from_block: int, to_block: int
    ) -> list[dict]:
        """Scan one endpoint across ``[from_block, to_block]``.

        The page size is the endpoint's *documented block cap* — uncapped on
        tenderly, :data:`DRPC_BLOCK_PAGE` on drpc. On top of that, three error
        classes shrink the current window and retry it: a block-range refusal, a
        result-count cap (using the narrower range the error names, when it names
        one), and a free-plan timeout. Everything else aborts this endpoint so
        the caller can fail over.
        """
        page = ENDPOINT_BLOCK_PAGE.get(url)
        collected: list[dict] = []
        cursor = from_block
        shrinks = 0
        while cursor <= to_block:
            end = to_block if page is None else min(cursor + page - 1, to_block)
            while True:
                try:
                    collected.extend(
                        await self._get_logs_window(url, topics, cursor, end)
                    )
                    break
                except LogEndpointError as err:
                    if err.kind not in _SHRINKABLE:
                        raise
                    span = end - cursor + 1
                    if span <= _MIN_WINDOW_BLOCKS or shrinks >= _MAX_SHRINKS_PER_WINDOW:
                        raise
                    shrinks += 1
                    if (
                        err.suggested_to is not None
                        and cursor <= err.suggested_to < end
                    ):
                        end = err.suggested_to
                    else:
                        end = cursor + max(span // 2, 1) - 1
                    logger.debug(
                        "%s: %s -> shrinking window to [%d..%d]",
                        url,
                        err.kind,
                        cursor,
                        end,
                    )
            cursor = end + 1
        return collected

    async def get_logs(
        self, topics: list, from_block: int, to_block: int
    ) -> list[dict]:
        """Raw logs from the first Pool B endpoint that answers.

        Raises :class:`LogEndpointError` only when **every** endpoint fails; the
        public methods that call this catch it and degrade.
        """
        if from_block > to_block:
            return []
        last: LogEndpointError | None = None
        for url in self._endpoints:
            try:
                return await self._scan_endpoint(url, topics, from_block, to_block)
            except LogEndpointError as err:
                logger.warning("log endpoint %s failed (%s): %s", url, err.kind, err.message)
                last = err
        raise last or LogEndpointError("transport", "no endpoints configured")

    async def head_block(self) -> int:
        """Current head via Pool B, or 0 on failure (never raises)."""
        for url in self._endpoints:
            try:
                result = await self._post(url, self._payload("eth_blockNumber", []))
                return _hex_int(result)
            except LogEndpointError as err:
                logger.debug("eth_blockNumber failed on %s: %s", url, err.message)
        return 0

    # ------------------------------------------------------------------
    # Backfill + tail
    # ------------------------------------------------------------------

    def _ingest(self, raw_logs: Iterable[Mapping[str, Any]]) -> int:
        """Decode and file logs by event, collapsing repeats by identity."""
        added = 0
        for log in raw_logs:
            decoded = decode_log(log)
            if decoded is None:
                continue
            name = decoded["event"]
            bucket = self._store.setdefault(name, {})
            key = _identity(decoded)
            if key not in bucket:
                added += 1
            bucket[key] = decoded
        return added

    async def backfill(
        self,
        from_block: int,
        to_block: int,
        events: Sequence[str] | None = None,
    ) -> dict:
        """One-time full-history scan.

        All requested events go out as a **single ``topics[0]`` OR-filter** —
        ``topics=[[t0, t0, ...]]`` — so a full history costs one pass rather than
        one pass per event type. Where the result cap bites (``AcquisitionRequested``
        alone has 58,006 instances), :meth:`_scan_endpoint` splits the window and
        keeps going; the OR-filter is still the right shape because the splitting
        is per-window, not per-event.

        Returns :meth:`status` plus ``{"added", "from_block", "to_block"}``.
        Never raises — a total failure returns ``available: False`` and leaves
        every previously scanned aggregate intact.
        """
        names = tuple(events) if events else LOG_EVENTS
        wanted = [topic0(name) for name in names]
        async with self._scan_lock:
            try:
                raw = await self.get_logs([wanted], from_block, to_block)
            except LogEndpointError as err:
                self._mark_down(REASON_UNAVAILABLE)
                logger.warning("FWA backfill unavailable: %s", err)
                return {**self.status(), "added": 0, "from_block": from_block,
                        "to_block": to_block}
            added = self._ingest(raw)
            if self._scanned_from is None or from_block < self._scanned_from:
                self._scanned_from = from_block
            self._launch_block = _infer_launch_block(self.entries("ConfigSet"))
            self._mark_ok(to_block)
            return {**self.status(), "added": added, "from_block": from_block,
                    "to_block": to_block}

    async def tail(
        self,
        last_seen_block: int | None = None,
        head: int | None = None,
        events: Sequence[str] | None = None,
    ) -> dict:
        """Incremental scan from ``last_seen_block`` to the head.

        Resumes **at** ``last_seen_block``, not after it. A tail that starts at
        ``last_seen + 1`` loses any log that landed in the boundary block after
        the previous scan read it; re-reading one block is free because the
        identity dedupe collapses the overlap.
        """
        start = self.last_seen_block if last_seen_block is None else last_seen_block
        end = head if head is not None else await self.head_block()
        if end <= 0:
            self._mark_down(REASON_UNAVAILABLE)
            return {**self.status(), "added": 0, "from_block": start, "to_block": end}
        start = max(0, min(start, end))
        return await self.backfill(start, end, events)

    # ------------------------------------------------------------------
    # Stored entries
    # ------------------------------------------------------------------

    def entries(self, event: str) -> list[dict]:
        """Decoded, chronologically ordered entries for one event type."""
        return sorted(self._store.get(event, {}).values(), key=_order_key)

    def event_counts(self) -> dict[str, int]:
        """Per-event counts as scanned. Never all-time unless the scan was."""
        return {name: len(bucket) for name, bucket in self._store.items()}

    # ------------------------------------------------------------------
    # Derived products — all last-good-safe, none raise
    # ------------------------------------------------------------------

    def settlement_mix(self) -> tuple[SettlementMix, ...]:
        """The five-outcome mix from whatever settlement logs are held."""
        counts = {name: len(self._store.get(name, {})) for name in SETTLEMENT_EVENTS}
        return settlement_mix(counts)

    def crown_history(self) -> list[dict]:
        """Per-holder crown rows, vacate logs already dropped."""
        return crown_history(
            self.entries("TopListingSet"), self.entries("TopListingSettled")
        )

    def crown_summary(self) -> dict:
        return crown_summary(
            self.entries("TopListingSet"), self.entries("TopListingSettled")
        )

    def config_history(self, *, include_launch: bool = False) -> list[dict]:
        """Post-launch parameter changes only, unless *include_launch*."""
        return config_history(
            self.entries("ConfigSet"),
            include_launch=include_launch,
            launch_block=self._launch_block,
        )

    def config_params(
        self, live_values: Mapping[int, int] | None = None
    ) -> tuple[ConfigParam, ...]:
        return config_params(self.entries("ConfigSet"), live_values)

    def collection_registry(self) -> dict[str, dict]:
        return collection_registry(self.entries("CollectionWhitelistSet"))

    def allowed_collections(self) -> list[str]:
        """Currently-allowed collection addresses (51 at the research block)."""
        return sorted(
            addr for addr, row in self.collection_registry().items() if row["allowed"]
        )

    def price_history(self) -> list[dict]:
        """Acquisition-fee samples, each pinned to block N-1 (findings §13.12)."""
        return price_history(self.entries("AcquisitionRequested"))

    def listing_index(self) -> dict[int, dict]:
        """``listing_id -> {collection, token_id}`` built from ``NFTListed``.

        The only event-derived way to name the collection behind a draw;
        ``NFTAllocated`` does not carry one.
        """
        index: dict[int, dict] = {}
        for entry in self.entries("NFTListed"):
            index[int(entry.get("listing_id", 0))] = {
                "collection": entry.get("collection", _ZERO_ADDRESS),
                "token_id": entry.get("token_id"),
            }
        return index

    def draw_events(
        self,
        limit: int = 50,
        listing_index: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> tuple[DrawEvent, ...]:
        """Activity-feed lines, newest first.

        *listing_index* overrides the ``NFTListed``-derived one — the manager
        passes the WP-6 sweep here, which also carries display names.
        """
        settlements: list[dict] = []
        for name in SETTLEMENT_EVENTS:
            settlements.extend(self.entries(name))
        return build_draw_events(
            self.entries("NFTAllocated"),
            settlements,
            requests=self.entries("AcquisitionRequested"),
            listing_index=listing_index or self.listing_index(),
            limit=limit,
        )

    def backing_updates(self, since: int = 0) -> list[dict]:
        """``BackingUpdated`` entries at or after *since*.

        The invalidation signal for WP-6's cached position sweep (rule 8): each
        one moves a position's inverse weight, so any sweep pinned before it is
        stale for that listing.
        """
        return [
            e
            for e in self.entries("BackingUpdated")
            if int(e.get("block_number", 0)) >= since
        ]

    def backing_invalidated_since(self, since: int = 0) -> set[int]:
        """Listing ids whose backing moved at or after *since*."""
        return {int(e.get("listing_id", 0)) for e in self.backing_updates(since)}

    # ------------------------------------------------------------------
    # Snapshot + persistence
    # ------------------------------------------------------------------

    def snapshot(self, *, feed_limit: int = 50) -> dict:
        """Everything the manager needs from Pool B, in one dict.

        Always the same keys. When Pool B is down, ``available`` is ``False``,
        ``reason`` is :data:`REASON_UNAVAILABLE`, and the aggregates are the last
        good ones with ``as_of_ts`` saying when they were captured — that is what
        lets the feed print "as of 14:32" instead of pretending to be live. If no
        scan has ever succeeded the aggregates are simply empty; the widget then
        renders unavailable with no stale number to misread.

        **Unit boundary, so the manager does not have to guess.** ``draw_events``
        rows are ``DrawEvent`` dumps and are therefore **wei-native**: they carry
        ``amount_wei``, and the manager converts it to the ``amount_eth`` that
        ``FWA_ROW_KEYS["draw_events"]`` asks for, at the one place conversion is
        allowed to happen. ``crown_history`` is the exception and already carries
        ``payout_eth``: it has no model behind it, so those rows *are* the
        presentation payload. The exact wei total stays on
        :meth:`crown_summary` for anyone who needs it.

        Feeds straight into WP-9's ``FWACache.set_log_aggregates(...)`` with
        ``ts=as_of_ts`` and ``block=last_seen_block``; every value here is
        JSON-serializable.
        """
        summary = self.crown_summary()
        return {
            "available": self._available,
            "reason": self._reason,
            "as_of_ts": self._as_of_ts,
            "last_seen_block": self.last_seen_block,
            "settlement_mix": [row.model_dump() for row in self.settlement_mix()],
            "crown_history": self.crown_history(),
            "crown_sets_total": summary["sets_total"],
            "crown_payouts_total": summary["payouts_total"],
            "crown_paid_eth": summary["paid_eth"],
            "draw_events": [row.model_dump() for row in self.draw_events(feed_limit)],
            "config_history": self.config_history(),
            "collection_registry": self.collection_registry(),
            "allowed_collections": self.allowed_collections(),
            "price_history": self.price_history(),
            "backing_updates": self.backing_updates(),
            "event_counts": self.event_counts(),
        }

    def export_state(self) -> dict:
        """JSON-serializable state for WP-9's cache to persist.

        Deliberately not a cache import: this module does not know how the cache
        stores things, and the cache does not know how logs decode. The manager
        hands this dict over and hands it back through :meth:`import_state` on
        the next run, which is what makes the first-run backfill a one-time cost
        and gives the degraded path a last-good value to show.
        """
        return {
            "version": 1,
            "last_seen_block": self.last_seen_block,
            "scanned_from": self._scanned_from,
            "as_of_ts": self._as_of_ts,
            "launch_block": self._launch_block,
            "events": {
                name: list(bucket.values()) for name, bucket in self._store.items()
            },
        }

    def import_state(self, state: Mapping[str, Any] | None) -> bool:
        """Restore from :meth:`export_state`. Returns ``False`` on bad input.

        Restoring does **not** set ``available``: cached rows are last-good data,
        not proof the endpoint is up. Availability is earned by a live scan.
        """
        if not isinstance(state, Mapping):
            return False
        events = state.get("events")
        if not isinstance(events, Mapping):
            return False
        try:
            for name, rows in events.items():
                bucket = self._store.setdefault(str(name), {})
                for row in rows or []:
                    bucket[_identity(row)] = dict(row)
            self.last_seen_block = int(state.get("last_seen_block") or 0)
            scanned_from = state.get("scanned_from")
            self._scanned_from = int(scanned_from) if scanned_from is not None else None
            as_of = state.get("as_of_ts")
            self._as_of_ts = float(as_of) if as_of is not None else None
            launch = state.get("launch_block")
            self._launch_block = (
                int(launch)
                if launch is not None
                else _infer_launch_block(self.entries("ConfigSet"))
            )
        except (TypeError, ValueError) as exc:
            logger.warning("FWA log state import failed: %s", exc)
            return False
        return True
