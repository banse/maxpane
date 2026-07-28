"""Async HTTP/RPC client for Ten Thousand Tokens (TTT) data on Ethereum mainnet.

Two data sources, all keyless:

* Ethereum mainnet JSON-RPC: factory + FeeSplitter views, event logs, ETH
  balances. Split across **two endpoint pools** -- see the Endpoints section
  below; the hosts that batch Multicall3 well are exactly the ones that refuse
  ``eth_getLogs``.
* DexScreener public API: per-token price / volume / market cap, batched up to
  30 addresses per call.

The NFT collection floor price used to be a fourth source (Reservoir) and is
now **dropped**: Reservoir was sunset (its host no longer resolves) and no
keyless replacement covers this collection. See :data:`TTTClient.FLOOR_SOURCE`
for the probe record and :data:`FLOOR_UNAVAILABLE_REASON` for what the manager
reports instead.

Critical contract semantics (see ``docs/tenthousandtokens_abi_recon.md``):

* The factory's launch event is ``Launched(uint256,address,address,string)`` --
  NOT ``BurnAndLaunch``. The hook also emits ``PoolLaunched`` in the same tx;
  we filter on the factory event because it indexes ``tokenId``.
* The factory's mint-time event is ``TokenDeployed(uint256,address,address)``
  which lets us discover every per-NFT ERC20 address (10,000 of them) cheaply.
* ``FeeSplitter.Deposited`` has 7 fields including the four pre-split shares.
  The ``holderShare`` field directly gives the 30%-bucket amount -- no
  multiplication needed.
* ``feeSplitter.SCALE() == 1e30`` (NOT 1e18). All ``accETHPerShare`` math uses
  this divisor.
* Per-token buyback reservoir = ``eth_getBalance(token_address)``. There is
  NO ``reservoir()`` view on the ERC20.

Follows the patterns in :mod:`maxpane_dashboard.data.ocm_client` for RPC retry
and fallback, and :mod:`maxpane_dashboard.data.base_client` for DexScreener
batching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Endpoints
#
# State reads and log reads MUST use different pools: the endpoints that batch
# Multicall3 well are exactly the ones that refuse ``eth_getLogs``. This is a
# structural requirement, not a preference.
#
# Verified live against mainnet on the date below by probing what this client
# actually does, at the depth it actually does it (aggregate3 over the factory
# + FeeSplitter, and a 10k-block ``eth_getLogs`` page at head-150k, which is
# ``_DEFAULT_LOG_LOOKBACK_BLOCKS`` deep). A narrow *recent* log probe is
# misleading -- publicnode answers those and then 403s on the backfill.
# ---------------------------------------------------------------------------

#: Date the endpoint sets below were last probed against mainnet. Bump it (and
#: re-probe) whenever the lists change -- ``test_ttt_client`` asserts the lists
#: match this record so silent rot shows up as a failing test, not as a dead
#: dashboard. Live results are recorded in ``_ENDPOINT_PROBE``.
ENDPOINTS_VERIFIED_ON = "2026-07-28"

#: Pool A -- state / views. publicnode is the strongest keyless batcher.
_PRIMARY_RPC = "https://ethereum-rpc.publicnode.com"
_FALLBACK_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",
    "https://1rpc.io/eth",
]

#: Pool B -- ``eth_getLogs`` only. Every Pool A primary refuses archive log
#: ranges, so this pool is separate and deliberately short.
_LOG_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",  # no block-range cap
    "https://eth.drpc.org",  # hard 10k-block cap == _LOG_RANGE_PER_CALL
]

#: What each host actually did on ``ENDPOINTS_VERIFIED_ON``. Kept in code
#: rather than only in docs because the previous set rotted silently: three of
#: the four configured hosts had died and nothing failed loudly.
_ENDPOINT_PROBE: dict[str, str] = {
    # -- in use --------------------------------------------------------------
    "ethereum-rpc.publicnode.com": (
        "state OK (aggregate3 over 5 views); eth_getLogs HTTP 403 at both "
        "recent and archive depth -- state pool only"
    ),
    "gateway.tenderly.co": (
        "state OK; eth_getLogs OK at head-10k and head-150k, no range cap -- "
        "both pools"
    ),
    "eth.drpc.org": (
        "state OK; eth_getLogs OK at both depths, hard 10k-block page cap -- "
        "both pools"
    ),
    "1rpc.io": (
        "state OK; eth_getLogs refused with -32602 'eth_getLogs is limited to "
        "0 - 50 blocks range' -- state pool only, and the reason error codes "
        "cannot be trusted (see _looks_like_endpoint_limitation)"
    ),
    # -- rejected ------------------------------------------------------------
    "cloudflare-eth.com": (
        "DEAD: eth_blockNumber -> -32046 'Cannot fulfill request', "
        "eth_call -> -32603 'Internal error'. Was this client's primary."
    ),
    "rpc.ankr.com": "DEAD: -32000 'Unauthorized: You must authenticate...' (now keyed)",
    "eth.llamarpc.com": "DEAD: HTTP 521, origin down",
    "eth.merkle.io": "REJECTED: eth_getLogs HTTP 400/429, eth_getBalance 429",
    "rpc.flashbots.net": "REJECTED: eth_call HTTP 403, logs 504 (tx-relay, not a data RPC)",
    "api.reservoir.tools": "DEAD: DNS failure, API sunset (see the floor-price note)",
}

#: Hosts that are dead, now keyed, or useless for this workload. Configuring
#: one is a programming error, so the constructor raises rather than silently
#: degrading to a dashboard that shows zeros. Mirrors ``fwa_client``.
_BANNED_RPC_HOSTS = frozenset(
    {
        "cloudflare-eth.com",  # -32046 / -32603 on every call
        "rpc.ankr.com",  # now requires an API key
        "eth.llamarpc.com",  # HTTP 521, origin down
        "eth-mainnet.g.alchemy.com",  # keyed
        "mainnet.infura.io",  # keyed
        "api.reservoir.tools",  # sunset
        "api.opensea.io",  # keyed
    }
)

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 15.0
#: publicnode 429s under aggressive batching; ~0.12s spacing was the stable
#: figure measured for the same host in ``fwa_client``.
_INTER_CALL_DELAY = 0.12

_DEXSCREENER_BATCH_URL = "https://api.dexscreener.com/tokens/v1/ethereum/{addresses}"
_DEXSCREENER_MAX_BATCH = 30

#: Why the NFT floor metric is absent. Surfaced by the manager next to the
#: ``None`` floor keys so the reason is legible instead of the metric simply
#: rendering blank. See :data:`TTTClient.FLOOR_SOURCE` for the full probe.
FLOOR_UNAVAILABLE_REASON = (
    "no keyless source (Reservoir sunset; collection absent from CoinGecko)"
)
# tenthousandtokens.net Next.js SSR homepage embeds the full per-token state
# (price, mcap, volume24h, ...) as escaped JSON. Scraping it gives us 100%
# coverage of launched tokens (vs DexScreener's partial indexing).
_TTT_SITE_URL = "https://www.tenthousandtokens.net/"

_MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_FACTORY = "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"
_FEESPLITTER = "0x6e46eaa57e1c7589686e2b0c935e8a8cf907683e"

_LOG_RANGE_PER_CALL = 10_000  # blocks per eth_getLogs call
_SCALE = 10**30  # FeeSplitter SCALE constant (NOT 1e18)
_WEI = 10**18

#: Block the factory's code first appears at, found by binary search on
#: ``eth_getCode`` (2026-07-28); the FeeSplitter follows three blocks later.
#: First-run scans start here rather than at a rolling offset from head.
#:
#: This replaces a 150,000-block rolling lookback that had silently gone stale:
#: all 121 ``Launched`` events sit in blocks 25,130,773..25,216,572, which by
#: 2026-07-28 was 410k-496k blocks behind head -- entirely outside the window.
#: A fresh install therefore discovered **zero** tokens, advanced its watermark
#: past them, and could never find them again, leaving the leaderboard, market
#: data, reservoirs and per-token fees permanently empty. A rolling window
#: cannot be used for discovery of a finite, historical event set: it rots as
#: the chain advances. An absolute floor does not.
_FACTORY_DEPLOY_BLOCK = 25_093_598

#: Retained for callers that still want a bounded first-run window; the scan
#: floor is ``max(_FACTORY_DEPLOY_BLOCK, head - this)``, so it only bites if
#: the factory is ever older than this many blocks.
_DEFAULT_LOG_LOOKBACK_BLOCKS = 1_000_000
# On steady-state polls we look back this far for incremental scans -- much
# smaller and bounded by `_LOG_RANGE_PER_CALL`.
_INCREMENTAL_LOG_LOOKBACK = 5_000

# ---------------------------------------------------------------------------
# Function selectors (first 4 bytes of keccak256 of the signature)
# Pre-computed; verified against ttt_factory.json / ttt_fee_splitter.json /
# ttt_erc20.json / multicall3.json.
# ---------------------------------------------------------------------------

# Factory
_SEL_MAX_SUPPLY = "0x32cb6b0c"          # MAX_SUPPLY()
_SEL_TOTAL_MINTED = "0xa2309ff8"        # totalMinted()

# FeeSplitter
_SEL_BURN_COUNT = "0x524773ce"          # burnCount()
_SEL_ACTIVE_SHARES = "0xbfefcd7b"       # activeShares()
_SEL_ACC_ETH_PER_SHARE = "0xf1644aa3"   # accETHPerShare()

# ERC20
_SEL_SYMBOL = "0x95d89b41"              # symbol()
_SEL_DECIMALS = "0x313ce567"            # decimals()

# Multicall3
_SEL_AGGREGATE3 = "0x82ad56cb"          # aggregate3(Call3[])
_SEL_GET_ETH_BALANCE = "0x4d2301cc"     # getEthBalance(address)

# ---------------------------------------------------------------------------
# Event topic hashes (from docs/tenthousandtokens_abi_recon.md)
# ---------------------------------------------------------------------------

_TOPIC_LAUNCHED = (
    "0xcd0c803f63c8f47c477dceca7e7b639ce5fe037e50d64fe6a845e7abf75a98f6"
)
_TOPIC_TOKEN_DEPLOYED = (
    "0x9334c9b0e49f1735472cc9700c1aac0d7c5ca7e46f77c3a71f0995c81b3a9587"
)
_TOPIC_DEPOSITED = (
    "0x354721bce0f1b29ebf3646e2e2c6d15259383d9493f4bb62300f579d2ad57692"
)
_TOPIC_BOUGHT = (
    "0xedba86fd2b22962d534e70ad9b0ff8730de46f636146f2bab6a72cbb1ebbcc53"
)


# ---------------------------------------------------------------------------
# Minimal ABI encode/decode helpers (pure-stdlib, no eth_abi dep)
# ---------------------------------------------------------------------------


#: Message fragments that mean "*this endpoint* will not serve this request" --
#: capability caps, archive gates, auth walls, plan limits. Providers ship
#: these under codes that also mean "your request is malformed": 1rpc's
#: 50-block log cap arrives as **-32602**, the same code as genuine bad input,
#: and publicnode's archive gate is a plain-language message too. Classifying
#: on the code alone therefore aborts the whole fallback chain at the first
#: endpoint that simply cannot do the job. Match on the message instead.
#: (Fragments below were taken from live responses, see ``_ENDPOINT_PROBE``.)
_ENDPOINT_LIMITATION_PATTERNS = (
    "limited to",
    "block range",
    "range is too large",
    "ranges over",
    "exceeds",
    "too large",
    "too many",
    "archive",
    "personal token",
    "api key",
    "unauthorized",
    "authenticate",
    "free plan",
    "upgrade",
    "not supported",
    "unsupported",
    "capacity",
    "rate limit",
    "timeout",
    "try again",
    "cannot fulfill",
)

#: JSON-RPC codes whose *conventional* meaning is "the caller's request is
#: malformed". Only consulted once the message has been cleared of endpoint
#: limitation language above.
_MALFORMED_REQUEST_CODES = {-32600, -32601, -32602, -32604, -32700}


def _looks_like_endpoint_limitation(err: Any) -> bool:
    """True if *err* reads as "this endpoint can't", not "this request is bad".

    Errs toward ``True`` on purpose: falling over to the next endpoint after a
    genuine caller bug costs a few wasted requests and reaches the same final
    failure, whereas treating a capability limit as terminal takes the whole
    dashboard offline while healthy endpoints sit unused.
    """
    if not isinstance(err, dict):
        return True
    message = str(err.get("message") or "").lower()
    if any(frag in message for frag in _ENDPOINT_LIMITATION_PATTERNS):
        return True
    return err.get("code") not in _MALFORMED_REQUEST_CODES


def _strip0x(hex_str: str) -> str:
    return hex_str[2:] if hex_str.startswith("0x") else hex_str


def _to_hex(b: bytes) -> str:
    return "0x" + b.hex()


def _pad_left(hex_no_0x: str, width: int = 64) -> str:
    """Left-pad a hex string with zeros to *width* characters."""
    return hex_no_0x.lower().rjust(width, "0")


def _addr_to_topic(addr: str) -> str:
    """Convert an address to a 32-byte topic (left-zero-padded)."""
    return "0x" + _pad_left(_strip0x(addr).lower(), 64)


def _addr_from_topic(topic: str) -> str:
    """Convert a 32-byte topic back to a 20-byte address (lowercase 0x...)."""
    return "0x" + _strip0x(topic).lower()[-40:]


def _decode_uint(hex_data: str, word_idx: int = 0) -> int:
    """Decode a uint256 at word slot *word_idx* of a hex blob."""
    raw = _strip0x(hex_data)
    start = word_idx * 64
    chunk = raw[start : start + 64]
    if not chunk:
        return 0
    return int(chunk, 16)


def _decode_address(hex_data: str, word_idx: int = 0) -> str:
    """Decode an address at word slot *word_idx* (lower 20 bytes)."""
    raw = _strip0x(hex_data)
    start = word_idx * 64
    chunk = raw[start : start + 64]
    if not chunk:
        return "0x" + "0" * 40
    return "0x" + chunk[-40:].lower()


def _decode_string_dynamic(hex_data: str, offset_word: int) -> str:
    """Decode a dynamic ``string`` whose offset header lives at *offset_word*.

    Solidity ABI for a single dynamic string return: a 32-byte length word
    immediately followed by the UTF-8 bytes padded to a 32-byte boundary.
    For a top-level return where the function returns ``(string)`` the layout
    starts with an offset word pointing at the length word.
    """
    raw = _strip0x(hex_data)
    if not raw:
        return ""
    try:
        # offset is in bytes from start of data; convert to char index (x2)
        offset_bytes = int(raw[offset_word * 64 : (offset_word + 1) * 64], 16)
        offset_chars = offset_bytes * 2
        length_bytes = int(raw[offset_chars : offset_chars + 64], 16)
        if length_bytes <= 0 or length_bytes > 1024:
            return ""
        body = raw[offset_chars + 64 : offset_chars + 64 + length_bytes * 2]
        return bytes.fromhex(body).decode("utf-8", errors="replace")
    except (ValueError, IndexError) as exc:
        logger.debug("string decode failed: %s", exc)
        return ""


def _encode_uint(value: int) -> str:
    """Encode an integer as a 32-byte hex word (no 0x prefix)."""
    if value < 0:
        # Two's complement for int256 (we only need positive here, but be safe)
        value &= (1 << 256) - 1
    return _pad_left(hex(value)[2:], 64)


def _encode_address(addr: str) -> str:
    """Encode an address as a 32-byte hex word (no 0x prefix)."""
    return _pad_left(_strip0x(addr).lower(), 64)


def _encode_call3(target: str, call_data: str, allow_failure: bool = True) -> str:
    """Encode a single Call3 struct (no 0x prefix).

    A Call3 is dynamic because of the bytes field, so this is just the
    *inline* representation in head-of-tuple terms. The actual array
    encoding is handled by ``_encode_aggregate3``.
    """
    cd = _strip0x(call_data)
    # The dynamic field offset within this tuple is: 3 words (target + bool
    # + offset header) -- i.e. 0x60.
    head = (
        _encode_address(target)
        + _pad_left("01" if allow_failure else "00", 64)
        + _pad_left("60", 64)
    )
    # Tail: length-prefixed bytes, padded to 32-byte boundary
    cd_len = len(cd) // 2
    cd_padded = cd + "0" * ((64 - (len(cd) % 64)) % 64)
    tail = _pad_left(hex(cd_len)[2:], 64) + cd_padded
    return head + tail


def _encode_aggregate3(calls: list[tuple[str, str, bool]]) -> str:
    """Build calldata for ``aggregate3(Call3[])``.

    Each input tuple is ``(target_address, callData_hex, allow_failure)``.
    Returns a hex string prefixed with ``0x``.
    """
    # Selector + offset to dynamic array
    selector = _SEL_AGGREGATE3
    body = ""
    # The array param: head is just an offset (always 0x20 for one dynamic arg)
    body += _pad_left("20", 64)
    # Array length
    body += _pad_left(hex(len(calls))[2:], 64)

    # Encode each Call3 separately, then build head-of-tuple offsets pointing
    # at each one. Since each Call3 is itself dynamic (it contains `bytes`),
    # the array's element-encoding is: N offsets pointing inside the array's
    # body, followed by the concatenated encoded tuples.
    encoded_tuples = [_encode_call3(t, cd, af) for (t, cd, af) in calls]
    n = len(encoded_tuples)
    # First n words are offsets (in bytes) from the start of the array body
    # (i.e. immediately after the length word).
    offsets: list[int] = []
    cursor = n * 32  # in bytes
    for tup in encoded_tuples:
        offsets.append(cursor)
        cursor += len(tup) // 2
    body += "".join(_pad_left(hex(o)[2:], 64) for o in offsets)
    body += "".join(encoded_tuples)
    return selector + body


def _decode_aggregate3_result(hex_data: str) -> list[tuple[bool, str]]:
    """Decode the return of ``aggregate3``: ``Result[] (bool success, bytes returnData)``.

    Returns a list of ``(success, returnData_hex)`` tuples.
    """
    raw = _strip0x(hex_data)
    if not raw:
        return []
    try:
        # First word: offset to the dynamic array (typically 0x20)
        # Next word: array length
        # Then N offsets pointing to each Result tuple
        # Then for each Result: success word + offset to bytes + length + data
        array_offset_bytes = int(raw[0:64], 16)
        base = array_offset_bytes * 2  # in chars
        length = int(raw[base : base + 64], 16)
        elements_base = base + 64

        results: list[tuple[bool, str]] = []
        for i in range(length):
            elt_off_bytes = int(
                raw[elements_base + i * 64 : elements_base + (i + 1) * 64],
                16,
            )
            # Result tuple lives at elements_base + 2*elt_off_bytes
            tup_start = elements_base + elt_off_bytes * 2
            success = int(raw[tup_start : tup_start + 64], 16) != 0
            # bytes offset inside the Result tuple (relative to tup_start)
            bytes_off = int(raw[tup_start + 64 : tup_start + 128], 16)
            bytes_chars_start = tup_start + bytes_off * 2
            bytes_len = int(
                raw[bytes_chars_start : bytes_chars_start + 64], 16
            )
            body = raw[
                bytes_chars_start + 64 : bytes_chars_start + 64 + bytes_len * 2
            ]
            results.append((success, "0x" + body))
        return results
    except (ValueError, IndexError) as exc:
        logger.warning("Failed to decode aggregate3 result: %s", exc)
        return []


def _decode_log_index(log: dict) -> int | None:
    """Position of a log within its block, or ``None`` if the node omits it.

    Carried through every decoder so the cache can tell two genuinely
    distinct logs of the same type, for the same token, in the same
    transaction apart when de-duplicating.
    """
    raw = log.get("logIndex")
    if raw is None:
        return None
    try:
        return int(raw, 16) if isinstance(raw, str) else int(raw)
    except (TypeError, ValueError):
        return None


def _decode_deposited_log(log: dict) -> dict | None:
    """Decode one ``Deposited(token, sender, total, launcher, tokenWorks, punkStrategy, holder)`` log.

    Returns ``{token, sender, total, launcher_share, tokenworks_share,
    punkstrategy_share, holder_share, block_number, tx_hash}`` or ``None`` on
    decode failure.
    """
    try:
        topics = log.get("topics", [])
        if len(topics) < 3:
            return None
        token = _addr_from_topic(topics[1])
        sender = _addr_from_topic(topics[2])
        data = log.get("data", "0x")
        total = _decode_uint(data, 0)
        launcher_share = _decode_uint(data, 1)
        tokenworks_share = _decode_uint(data, 2)
        punkstrategy_share = _decode_uint(data, 3)
        holder_share = _decode_uint(data, 4)
        return {
            "token": token,
            "sender": sender,
            "total": total,
            "launcher_share": launcher_share,
            "tokenworks_share": tokenworks_share,
            "punkstrategy_share": punkstrategy_share,
            "holder_share": holder_share,
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "log_index": _decode_log_index(log),
            "tx_hash": log.get("transactionHash", "0x"),
        }
    except Exception as exc:
        logger.debug("Deposited decode failed: %s", exc)
        return None


def _decode_launched_log(log: dict) -> dict | None:
    """Decode one factory ``Launched(tokenId, token, launcher, imageURI)`` log."""
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        token_id = int(topics[1], 16)
        erc20_addr = _addr_from_topic(topics[2])
        launcher = _addr_from_topic(topics[3])
        return {
            "token_id": token_id,
            "erc20_address": erc20_addr,
            "launcher": launcher,
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "log_index": _decode_log_index(log),
            "tx_hash": log.get("transactionHash", "0x"),
        }
    except Exception as exc:
        logger.debug("Launched decode failed: %s", exc)
        return None


def _decode_token_deployed_log(log: dict) -> dict | None:
    """Decode one factory ``TokenDeployed(tokenId, token, holder)`` log."""
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        token_id = int(topics[1], 16)
        erc20_addr = _addr_from_topic(topics[2])
        holder = _addr_from_topic(topics[3])
        return {
            "token_id": token_id,
            "erc20_address": erc20_addr,
            "holder": holder,
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "log_index": _decode_log_index(log),
            "tx_hash": log.get("transactionHash", "0x"),
        }
    except Exception as exc:
        logger.debug("TokenDeployed decode failed: %s", exc)
        return None


def _decode_bought_log(log: dict) -> dict | None:
    """Decode one ERC20 ``Bought(caller, ethSpent, amountBought, callerReward)`` log."""
    try:
        topics = log.get("topics", [])
        if len(topics) < 2:
            return None
        caller = _addr_from_topic(topics[1])
        data = log.get("data", "0x")
        eth_spent = _decode_uint(data, 0)
        amount_bought = _decode_uint(data, 1)
        caller_reward = _decode_uint(data, 2)
        return {
            "token": (log.get("address") or "").lower(),
            "caller": caller,
            "eth_spent": eth_spent,
            "amount_bought": amount_bought,
            "caller_reward": caller_reward,
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "log_index": _decode_log_index(log),
            "tx_hash": log.get("transactionHash", "0x"),
        }
    except Exception as exc:
        logger.debug("Bought decode failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TTTClient:
    """Async client for TTT data sources.

    Fetches state from Ethereum mainnet RPC and DexScreener.

    Failure contract -- a failed read is never a zero:

    * The HTTP sources (DexScreener, the site scrape) degrade to ``None`` /
      empty returns, because "no market data" is a real, common answer.
    * The contract reads (:meth:`fetch_factory_state`,
      :meth:`fetch_token_metadata`, :meth:`fetch_token_reservoirs`) **raise**
      when the transport failed, so the manager can tell "RPC down" from
      "the value is genuinely 0" and count it as an error. Per-call reverts
      inside a healthy multicall are still reported in-band.
    * The log scans return ``(events, last_complete_block)`` so a refused page
      holds the caller's watermark instead of silently skipping its blocks.

    Parameters
    ----------
    primary_rpc, fallback_rpcs:
        Pool A -- state / view endpoints. If one fails, the client rotates
        through the rest in order. A banned host (dead, keyed, or useless for
        this workload -- see :data:`_BANNED_RPC_HOSTS`) raises ``ValueError``
        at construction rather than silently degrading to a zeroed dashboard.
    log_rpcs:
        Pool B -- endpoints used for ``eth_getLogs`` only. Kept separate
        because the best state batchers refuse archive log ranges.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``. If not provided one
        is created internally and closed on ``close()``.
    """

    def __init__(
        self,
        primary_rpc: str = _PRIMARY_RPC,
        fallback_rpcs: list[str] | None = None,
        *,
        log_rpcs: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._primary_rpc = primary_rpc
        self._fallback_rpcs = list(
            _FALLBACK_RPCS if fallback_rpcs is None else fallback_rpcs
        )
        self._log_rpcs = list(_LOG_RPCS if log_rpcs is None else log_rpcs)
        for url in [primary_rpc, *self._fallback_rpcs, *self._log_rpcs]:
            host = urlparse(url).hostname or ""
            if host in _BANNED_RPC_HOSTS:
                raise ValueError(
                    f"{url} is a banned RPC host (dead, keyed, or useless for "
                    f"this workload) -- see ttt_client._BANNED_RPC_HOSTS and "
                    f"_ENDPOINT_PROBE. Probed {ENDPOINTS_VERIFIED_ON}: "
                    f"{_ENDPOINT_PROBE.get(host, 'no probe record')}"
                )
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._request_id = 0
        self._last_rpc_at: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> TTTClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: RPC plumbing with retry + fallback
    # ------------------------------------------------------------------

    async def _rpc(
        self, method: str, params: list, *, endpoints: list[str] | None = None
    ) -> Any:
        """Send a JSON-RPC call with retry + endpoint rotation.

        Returns the ``result`` field on success. Raises ``RuntimeError`` if
        every endpoint fails after every retry.

        *endpoints* selects the pool; it defaults to Pool A (state). Log reads
        pass Pool B, because the Pool A hosts refuse archive ``eth_getLogs``.
        """
        # Throttle inter-call latency on a per-instance basis so the same
        # client doesn't hammer a public endpoint within one refresh cycle.
        elapsed = time.monotonic() - self._last_rpc_at
        if self._last_rpc_at > 0 and elapsed < _INTER_CALL_DELAY:
            await asyncio.sleep(_INTER_CALL_DELAY - elapsed)
        self._last_rpc_at = time.monotonic()

        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        pool = (
            list(endpoints)
            if endpoints is not None
            else [self._primary_rpc, *self._fallback_rpcs]
        )
        last_err: BaseException | None = None
        # Status codes meaning "the endpoint itself is broken or blocking us"
        # rather than transient; don't waste retries on them.
        _ENDPOINT_DEAD_CODES = {401, 402, 403, 451, 521, 522, 523, 524, 525, 526}
        for url in pool:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._client.post(url, json=payload)
                    if resp.status_code in _ENDPOINT_DEAD_CODES:
                        # Endpoint-level failure: skip to next endpoint immediately.
                        last_err = httpx.HTTPStatusError(
                            f"RPC {url} returned {resp.status_code}",
                            request=resp.request, response=resp,
                        )
                        break
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"RPC {url} returned {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    try:
                        body = resp.json()
                    except ValueError as exc:
                        # HTTP 200 carrying an HTML challenge / proxy error
                        # page. This used to escape ``_rpc`` uncaught, so the
                        # first bad endpoint failed the call outright while
                        # healthy fallbacks went untried.
                        last_err = RuntimeError(
                            f"RPC {url} returned a non-JSON body: {exc}"
                        )
                        break  # try next endpoint
                    if not isinstance(body, dict):
                        last_err = RuntimeError(
                            f"RPC {url} returned a non-object body: {type(body).__name__}"
                        )
                        break
                    if "error" in body:
                        err = body["error"]
                        # Classify on the MESSAGE, not the code. Providers reuse
                        # codes for unrelated meanings -- 1rpc reports its
                        # 50-block eth_getLogs cap as -32602, the same code as
                        # genuine malformed input, and treating that as terminal
                        # aborted the whole fallback chain before any healthy
                        # endpoint was tried.
                        if _looks_like_endpoint_limitation(err):
                            last_err = RuntimeError(f"RPC {url} error: {err}")
                            break  # try next endpoint
                        raise RuntimeError(f"RPC error: {err}")
                    return body.get("result", "0x")
                except (httpx.HTTPError, httpx.StreamError) as exc:
                    last_err = exc
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    else:
                        logger.debug(
                            "%s failed on %s after %d attempts: %s",
                            method,
                            url,
                            _MAX_RETRIES,
                            exc,
                        )
                        # Move on to next endpoint
                        break
                except RuntimeError:
                    raise
        raise RuntimeError(
            f"RPC {method} failed on all endpoints; last_err={last_err}"
        )

    async def _eth_call(self, to: str, data: str, block: str = "latest") -> str:
        return await self._rpc("eth_call", [{"to": to, "data": data}, block])

    async def _eth_block_number(self) -> int:
        result = await self._rpc("eth_blockNumber", [])
        return int(result, 16)

    async def _eth_get_balance(self, addr: str) -> int:
        result = await self._rpc("eth_getBalance", [addr, "latest"])
        return int(result, 16) if result and result != "0x" else 0

    async def _eth_get_block(self, block_num: int) -> dict | None:
        try:
            return await self._rpc(
                "eth_getBlockByNumber", [hex(block_num), False]
            )
        except Exception as exc:
            logger.debug("eth_getBlockByNumber(%s) failed: %s", block_num, exc)
            return None

    async def _get_logs(
        self,
        address: str | list[str],
        topics: list,
        from_block: int,
        to_block: int,
    ) -> tuple[list[dict], int]:
        """Fetch event logs, paged, reporting **how far the scan actually got**.

        Returns ``(logs, last_complete_block)``: every block in
        ``[from_block, last_complete_block]`` was successfully scanned. A total
        failure of the very first page yields ``from_block - 1`` -- "no
        progress" -- and callers must not advance a watermark past it.

        The return shape is the fix for MEDI-29. This used to catch each page's
        exception, log it at ``debug`` and skip to the next page, so a refused
        chunk produced a *partial* list that looked exactly like a genuinely
        sparse range. ``TTTManager._scan_events`` then set
        ``last_seen_block[topic] = current_block`` and persisted it, and since
        steady-state scans only look back ``_INCREMENTAL_LOG_LOOKBACK`` blocks,
        the skipped range was never read again for the life of the cache. Any
        ``Launched`` token in it never entered ``cache.tokens`` (``register_token``
        is only reachable via ``apply_launch``), permanently missing from the
        leaderboard, the fee table, metadata refresh and buyback scans.
        """
        if from_block > to_block:
            return [], to_block
        all_logs: list[dict] = []
        cursor = from_block
        while cursor <= to_block:
            chunk_end = min(cursor + _LOG_RANGE_PER_CALL - 1, to_block)
            params = {
                "address": address,
                "topics": topics,
                "fromBlock": hex(cursor),
                "toBlock": hex(chunk_end),
            }
            try:
                # Pool B: the Pool A hosts refuse archive log ranges
                # (publicnode 403s, 1rpc caps at 50 blocks).
                logs = await self._rpc(
                    "eth_getLogs", [params], endpoints=self._log_rpcs
                )
            except Exception as exc:
                logger.warning(
                    "eth_getLogs [%d..%d] failed: %s; scan stops at %d",
                    cursor,
                    chunk_end,
                    exc,
                    cursor - 1,
                )
                return all_logs, cursor - 1
            if not isinstance(logs, list):
                logger.warning(
                    "eth_getLogs [%d..%d] returned %s, not a list; "
                    "scan stops at %d",
                    cursor,
                    chunk_end,
                    type(logs).__name__,
                    cursor - 1,
                )
                return all_logs, cursor - 1
            all_logs.extend(logs)
            cursor = chunk_end + 1
        return all_logs, to_block

    async def _multicall(self, calls: list[tuple[str, str]]) -> list[tuple[bool, str]]:
        """Batch many eth_calls into one Multicall3 ``aggregate3``.

        Each input tuple is ``(target_address, callData_hex)``. All calls run
        with ``allowFailure=True`` so one bad target doesn't kill the batch.
        Returns a list of ``(success, returnData)`` in the same order.

        Raises ``RuntimeError`` when the *transport* failed -- every endpoint
        exhausted, or a reply that does not decode into one ``Result`` per
        call. This is deliberately different from a per-call revert, which is
        reported in-band as ``(False, "0x")``.

        The distinction is the whole point (MEDI-31). This used to swallow the
        outage and return ``[(False, "0x")] * len(calls)``, which is
        indistinguishable from "every contract reverted": callers turned it
        into ``burn_count=0`` / ``active_shares=0`` / ``reservoir=0``, the
        manager's ``except`` branch never fired, ``_error_count`` stayed 0, and
        the dashboard rendered a confident, plausible, entirely false picture
        of the chain -- then persisted a ``(hour, 0)`` point into the 7-day
        sparkline, so one outage outlived itself.
        """
        if not calls:
            return []
        payload_calls = [(t, cd, True) for (t, cd) in calls]
        data = _encode_aggregate3(payload_calls)
        raw = await self._eth_call(_MULTICALL3, data)
        results = _decode_aggregate3_result(raw)
        if len(results) != len(calls):
            raise RuntimeError(
                f"multicall({len(calls)} calls) returned {len(results)} "
                f"results; the reply is not a well-formed aggregate3 Result[]"
            )
        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_block_number(self) -> int:
        """Get the current block number, or 0 on failure."""
        try:
            return await self._eth_block_number()
        except Exception as exc:
            logger.warning("eth_blockNumber failed: %s", exc)
            return 0

    async def fetch_factory_state(self) -> dict[str, int]:
        """Read factory + FeeSplitter state in one multicall.

        Returns a flat dict with keys: ``max_supply``, ``total_minted``,
        ``burn_count``, ``active_shares``, ``acc_eth_per_share``.

        Raises ``RuntimeError`` if the multicall itself could not be made
        (MEDI-31) -- an outage must not be rendered as a chain where nothing
        has ever burned. An individual read that reverts on a healthy node is
        still reported as 0, which is the only honest answer for a selector
        the deployed contract does not implement.
        """
        calls = [
            (_FACTORY, _SEL_MAX_SUPPLY),
            (_FACTORY, _SEL_TOTAL_MINTED),
            (_FEESPLITTER, _SEL_BURN_COUNT),
            (_FEESPLITTER, _SEL_ACTIVE_SHARES),
            (_FEESPLITTER, _SEL_ACC_ETH_PER_SHARE),
        ]
        results = await self._multicall(calls)

        def _u(idx: int) -> int:
            if idx >= len(results):
                return 0
            ok, data = results[idx]
            return _decode_uint(data) if ok else 0

        return {
            "max_supply": _u(0) or 10_000,
            "total_minted": _u(1),
            "burn_count": _u(2),
            "active_shares": _u(3),
            "acc_eth_per_share": _u(4),
        }

    async def fetch_token_deployed_events(
        self, from_block: int, to_block: int
    ) -> tuple[list[dict], int]:
        """Enumerate every NFT->ERC20 deployment in a block range.

        Returns ``(events, last_complete_block)``; each event is a
        ``{token_id, erc20_address, holder, block_number, tx_hash}`` dict. See
        :meth:`_get_logs` for the watermark contract.
        """
        logs, scanned_to = await self._get_logs(
            _FACTORY, [_TOPIC_TOKEN_DEPLOYED], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_token_deployed_log(log)
            if decoded is not None:
                out.append(decoded)
        return out, scanned_to

    async def fetch_launched_events(
        self, from_block: int, to_block: int
    ) -> tuple[list[dict], int]:
        """Fetch burn-and-launch events from the factory's ``Launched`` topic.

        Returns ``([{token_id, erc20_address, launcher, block_number,
        tx_hash}], last_complete_block)``. See :meth:`_get_logs`.
        """
        logs, scanned_to = await self._get_logs(
            _FACTORY, [_TOPIC_LAUNCHED], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_launched_log(log)
            if decoded is not None:
                out.append(decoded)
        return out, scanned_to

    async def fetch_deposit_events(
        self, from_block: int, to_block: int
    ) -> tuple[list[dict], int]:
        """Fetch FeeSplitter ``Deposited`` events with full 7-field decode.

        Returns ``(events, last_complete_block)``. See :meth:`_get_logs`.
        """
        logs, scanned_to = await self._get_logs(
            _FEESPLITTER, [_TOPIC_DEPOSITED], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_deposited_log(log)
            if decoded is not None:
                out.append(decoded)
        return out, scanned_to

    async def fetch_buyback_events(
        self,
        token_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> tuple[list[dict], int]:
        """Fetch ``Bought`` events emitted by any of the given ERC20s.

        Returns ``(events, last_complete_block)``; each event carries the
        source token, caller, eth spent, tokens bought, and bounty reward. See
        :meth:`_get_logs` for the watermark contract.

        With no addresses there is nothing to scan, so the range counts as
        fully covered: ``([], to_block)``.
        """
        if not token_addresses:
            return [], to_block
        addresses = [a.lower() for a in token_addresses]
        # Some RPCs reject array-form `address`; we paginate manually if needed.
        logs, scanned_to = await self._get_logs(
            addresses, [_TOPIC_BOUGHT], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_bought_log(log)
            if decoded is not None:
                out.append(decoded)
        return out, scanned_to

    async def fetch_token_metadata(
        self, addresses: list[str]
    ) -> dict[str, tuple[str, int]]:
        """Batch ``symbol()`` + ``decimals()`` for every address.

        Returns ``{lower_addr: (symbol, decimals)}``. Missing tokens are
        omitted from the result.
        """
        if not addresses:
            return {}
        calls: list[tuple[str, str]] = []
        for addr in addresses:
            calls.append((addr, _SEL_SYMBOL))
            calls.append((addr, _SEL_DECIMALS))
        results = await self._multicall(calls)
        out: dict[str, tuple[str, int]] = {}
        for i, addr in enumerate(addresses):
            sym_ok, sym_data = results[2 * i] if 2 * i < len(results) else (False, "0x")
            dec_ok, dec_data = (
                results[2 * i + 1] if 2 * i + 1 < len(results) else (False, "0x")
            )
            if not (sym_ok and dec_ok):
                continue
            symbol = _decode_string_dynamic(sym_data, 0).strip()
            try:
                decimals = _decode_uint(dec_data) or 18
            except Exception:
                decimals = 18
            if not symbol:
                continue
            out[addr.lower()] = (symbol, int(decimals))
        return out

    async def fetch_token_reservoirs(
        self, addresses: list[str]
    ) -> dict[str, int]:
        """Batch-read each ERC20's plain ETH balance (the buyback reservoir).

        Uses Multicall3's ``getEthBalance(address)`` so we get all balances
        in one round-trip. Returns ``{lower_addr: wei}``.
        """
        if not addresses:
            return {}
        calls = [
            (_MULTICALL3, _SEL_GET_ETH_BALANCE + _encode_address(addr))
            for addr in addresses
        ]
        results = await self._multicall(calls)
        out: dict[str, int] = {}
        for addr, (ok, data) in zip(addresses, results):
            if ok:
                out[addr.lower()] = _decode_uint(data)
            else:
                out[addr.lower()] = 0
        return out

    async def fetch_market_data(
        self, addresses: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Batch DexScreener for per-token market info.

        Returns ``{lower_addr: {price_usd, change_h24, volume_h24, mcap}}``.
        Missing / un-indexed tokens are absent from the dict. Network errors
        return an empty dict (caller falls back to cache).
        """
        if not addresses:
            return {}
        lowered = [a.lower() for a in addresses]
        chunks = [
            lowered[i : i + _DEXSCREENER_MAX_BATCH]
            for i in range(0, len(lowered), _DEXSCREENER_MAX_BATCH)
        ]
        out: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            url = _DEXSCREENER_BATCH_URL.format(addresses=",".join(chunk))
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._client.get(url)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"DexScreener {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    data = resp.json()
                    pairs: list[dict[str, Any]]
                    if isinstance(data, list):
                        pairs = data
                    else:
                        pairs = data.get("pairs", []) or []
                    for pair in pairs:
                        base_addr = (
                            (pair.get("baseToken") or {}).get("address") or ""
                        ).lower()
                        if not base_addr or base_addr in out:
                            continue
                        change_h24 = (pair.get("priceChange") or {}).get("h24")
                        vol_h24 = (pair.get("volume") or {}).get("h24")
                        out[base_addr] = {
                            "price_usd": _safe_float(pair.get("priceUsd")),
                            "change_h24": _safe_float(change_h24),
                            "volume_h24": _safe_float(vol_h24),
                            "mcap": _safe_float(
                                pair.get("marketCap") or pair.get("fdv")
                            ),
                        }
                    break  # success, next chunk
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    else:
                        logger.debug(
                            "DexScreener batch %d addrs failed: %s",
                            len(chunk),
                            exc,
                        )
        return out

    async def fetch_site_market_data(self) -> dict[str, dict[str, Any]]:
        """Scrape per-token market data from tenthousandtokens.net SSR HTML.

        The site's homepage embeds the full state of every launched token
        (price, marketCap, volume24h, change, holders count, last trade, etc.)
        as escaped JSON inside the React-Server-Components flight payload.
        Returns ``{lower_addr: {price_usd, change_h24, volume_h24, mcap}}`` --
        same shape as :meth:`fetch_market_data` so the manager can swap
        sources without touching the cache schema. Returns ``{}`` on any
        network or parse failure (manager keeps last-known values).
        """
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(
                    _TTT_SITE_URL,
                    headers={"Accept": "text/html", "User-Agent": "maxpane-dashboard"},
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"tenthousandtokens.net {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return _parse_site_market_data(resp.text)
            except (httpx.HTTPError, ValueError) as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                else:
                    logger.debug("site market data fetch failed: %s", exc)
        return {}

    #: The NFT floor price has NO keyless source. Probed 2026-07-28:
    #:
    #: * ``api.reservoir.tools`` -- DNS failure, the API was sunset. This is
    #:   what the method used to call, on a 2-retry loop, every other cycle.
    #: * CoinGecko ``/nfts/ethereum/contract/{factory}`` -- HTTP 404 "nft
    #:   collection not found"; the collection is absent from CoinGecko search
    #:   entirely, so FWA's replacement source does not cover TTT.
    #: * ``tenthousandtokens.net`` -- the SSR payload carries 40 per-token
    #:   fields but no collection floor; the page only links out to OpenSea.
    #: * OpenSea's API requires a key, which this project forbids.
    #:
    #: The metric is therefore DROPPED rather than left calling a dead host.
    #: Nothing rendered it in any case: no screen or widget reads ``floor_eth``,
    #: ``floor_usd``, ``sales_24h`` or ``floor_history``. The manager keeps the
    #: keys, pinned to ``None`` with :data:`FLOOR_UNAVAILABLE_REASON` alongside,
    #: so a future widget shows an explicit "unavailable" rather than a
    #: fabricated 0.0 -- and so re-adding a source is a one-method change.
    FLOOR_SOURCE = None


# ---------------------------------------------------------------------------
# Small utility shared with the manager
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float:
    """Best-effort float conversion -- returns 0.0 on any failure."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


_SITE_TOKEN_RE = re.compile(
    r'\{"id":\d+,"address":"0x[a-f0-9]{40}".*?"refundable":(?:true|false)\}'
)


def _parse_site_market_data(html: str) -> dict[str, dict[str, Any]]:
    """Extract per-token market data from tenthousandtokens.net SSR HTML.

    The site embeds the React-Server-Components payload as escaped JSON
    inside <script> tags. We unescape and use a regex to pull out each
    token's full object (every token entry ends with ``"refundable":bool``
    which is a stable terminator). Returns the same shape as DexScreener's
    :meth:`fetch_market_data`: ``{lower_addr: {price_usd, change_h24,
    volume_h24, mcap}}``.
    """
    # The RSC flight payload escapes quotes once (\") and backslashes once
    # (\\). Reverse both so the regex can match plain JSON objects.
    text = html.replace('\\"', '"').replace('\\\\', '\\')
    out: dict[str, dict[str, Any]] = {}
    for match in _SITE_TOKEN_RE.finditer(text):
        try:
            obj = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        addr = (obj.get("address") or "").lower()
        if not addr:
            continue
        # change_h24 can be a number, a string like "$-0", or absent.
        # The container is usually a dict but the site occasionally ships
        # it as a placeholder string (e.g. "$11"); guard with isinstance.
        change_container = obj.get("priceChangePercentByTimeframe")
        raw_change = (
            change_container.get("24h") if isinstance(change_container, dict) else None
        )
        change_h24: float | None
        if isinstance(raw_change, (int, float)):
            change_h24 = float(raw_change)
        elif isinstance(raw_change, str):
            # Strip "$" / "%" / whitespace and try float.
            cleaned = raw_change.replace("$", "").replace("%", "").strip()
            try:
                change_h24 = float(cleaned)
            except ValueError:
                change_h24 = None
        else:
            change_h24 = None
        out[addr] = {
            "price_usd": _safe_float(obj.get("price")),
            "change_h24": change_h24,
            "volume_h24": _safe_float(obj.get("volume24h")),
            "mcap": _safe_float(obj.get("marketCap")),
        }
    return out


# Public re-exports the manager / cache use.
__all__ = [
    "TTTClient",
    "ENDPOINTS_VERIFIED_ON",
    "FLOOR_UNAVAILABLE_REASON",
    "_DEFAULT_LOG_LOOKBACK_BLOCKS",
    "_FACTORY_DEPLOY_BLOCK",
    "_INCREMENTAL_LOG_LOOKBACK",
    "_SCALE",
    "_WEI",
    "_FACTORY",
    "_FEESPLITTER",
    "_TOPIC_LAUNCHED",
    "_TOPIC_TOKEN_DEPLOYED",
    "_TOPIC_DEPOSITED",
    "_TOPIC_BOUGHT",
    "_safe_float",
]
