"""Async HTTP/RPC client for the Talismans ERC721 collection on Ethereum mainnet.

A single keyless data source: Ethereum mainnet JSON-RPC (publicnode + fallbacks)
for the verified Talismans contract at ``_CONTRACT``. We read collection-level
flags, enumerate per-token state via Multicall3, and decode the four
shape-mutation events (Bonded / Cleaved / Cut / Merged) plus ERC721 ``Transfer``.

Critical contract semantics (see ``docs/talismans_abi_recon.md``):

* There is NO ``ERC721Enumerable.tokenByIndex`` -- enumerate token ids via a
  Multicall3 sweep of ``tokenData(id)`` + ``ownerOf(id)``.
* ``tokenData(uint256)`` returns an ABI tuple
  ``(uint256[] cores, uint8 materialId, uint8 form, uint8 coreCount, uint16 seed)``.
  The first head word is the byte-offset to the dynamic ``cores`` array.
* The four mutation events each carry a trailing non-indexed ``address operator``.
  ``Cut`` is the odd one out: its data has TWO non-indexed words --
  ``(uint256 index, address operator)`` -- so the operator is the SECOND word.
* ``nextTransformId()`` is the authoritative id allocator for every
  post-genesis token. Token ids are NOT discoverable from logs alone (see
  :data:`_LOG_RPCS` below), so enumeration seeds ``genesisMinted+1 ..
  nextTransformId()-1`` and lets the ``tokenData``/``ownerOf`` sweep filter
  the dead ones.

Endpoint reality (probed live 2026-07-27, all four Talismans RPCs plus five
candidates; see :data:`_LOG_RPCS`): ``eth_call`` and ``eth_getLogs`` need
*different* endpoint pools. The former works nearly everywhere; the latter is
served keylessly by almost nobody.

Structurally a clone of :mod:`maxpane_dashboard.data.ttt_client`: the
``_rpc`` / ``_eth_call`` / ``_get_logs`` / ``_multicall`` machinery and the
pure-stdlib ABI encode/decode helpers are reused verbatim.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_PRIMARY_RPC = "https://ethereum.publicnode.com"  # fast + reliable for eth_call

# State-read fallbacks. Probed live 2026-07-27 with ``nextTransformId()`` on
# ``_CONTRACT``: cloudflare-eth.com now answers ``-32603 Internal error`` to
# every request and rpc.ankr.com/eth answers ``-32000 Unauthorized: You must
# authenticate your request with an API key`` — i.e. two of the three original
# fallbacks were dead, leaving publicnode with no real redundancy.
_FALLBACK_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",
    "https://eth.merkle.io",
]

# ``eth_getLogs`` needs its OWN pool, because the state-read pool cannot serve
# it. Probed live 2026-07-27 against this contract's four operation topics:
#
#   gateway.tenderly.co  250,000-block span in ONE call            <- best
#   eth.drpc.org         10,000-block cap, code 35 "ranges over
#                        10000 blocks are not supported on free plan"
#   ethereum.publicnode  EVERY archive-depth range refused with
#                        -32602 "Archive requests require a personal token"
#   eth.merkle.io        -32601 "Method not found" (no eth_getLogs at all)
#   1rpc.io/eth          -32602 "eth_getLogs is limited to 0 - 50 blocks range"
#   blastapi             -32600, 10-block cap
#   rpc.flashbots.net    -32602 "block range extends beyond current head block"
#   eth.llamarpc.com     HTTP 521 (down)
#
# publicnode's archive gate is why the code review saw "0 events in the 250k
# window" on a live contract that had events in it: -32602 was in the old
# terminal-code set, so it aborted the whole call *before* any fallback ran,
# and _get_logs then swallowed the exception. publicnode stays in the pool last
# only because it does serve the shallow ~128-block head window.
_LOG_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.drpc.org",
    "https://ethereum.publicnode.com",
]

_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 10.0
_INTER_CALL_DELAY = 0.05  # seconds between consecutive RPC calls
_ENDPOINT_DEAD_CODES = {401, 402, 403, 451, 521, 522, 523, 524, 525, 526}

_CONTRACT = "0x724d5beffe9a84a87ad1af83713f80600e5f5774"
_MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"

_LOG_RANGE_PER_CALL = 50_000  # tenderly serves this comfortably
_DEFAULT_LOG_LOOKBACK_BLOCKS = 250_000

# Adaptive paging for eth_getLogs (see :meth:`TalismansClient._get_logs`).
_MAX_LOG_SHRINKS = 8      # per chunk; 50_000 -> 195 blocks worst case
_MIN_LOG_WINDOW = 1
_LOG_WINDOW_GROWTH_AFTER = 4  # consecutive clean pages before widening again

# Multicall3 chunk size for the token-state sweep (2 calls per id).
_TOKEN_STATE_CHUNK = 150

# ---------------------------------------------------------------------------
# Function selectors (first 4 bytes of keccak256 of the signature)
# ---------------------------------------------------------------------------

_SEL_TOTAL_SUPPLY = "0x18160ddd"  # totalSupply()
_SEL_GENESIS_MINTED = "0x153de143"  # genesisMinted()
_SEL_BOND_ENABLED = "0xd11543fd"  # bondAndCleaveEnabled()
_SEL_CUTMERGE_ENABLED = "0xdafa0f1a"  # cutAndMergeEnabled()
_SEL_NEXT_TRANSFORM_ID = "0x98e1870d"  # nextTransformId() -> uint256
_SEL_TOKEN_DATA = "0xb4b5b48f"  # tokenData(uint256) -> (uint256[],uint8,uint8,uint8,uint16)
_SEL_OWNER_OF = "0x6352211e"  # ownerOf(uint256)
_SEL_AGGREGATE3 = "0x82ad56cb"  # aggregate3(Call3[])

# ---------------------------------------------------------------------------
# Event topic0 hashes (from docs/talismans_abi_recon.md)
# ---------------------------------------------------------------------------

# Bonded(uint256 indexed a, uint256 indexed b, uint256 indexed bondedId, address operator)
_TOPIC_BONDED = "0xf4d7559aa146406a2a7769decb3cc99cb5c91d0c4b37c8c48ef43b5df27dac8d"
# Cleaved(uint256 indexed tokenId, uint256 indexed lithicId, uint256 indexed lumicId, address operator)
_TOPIC_CLEAVED = "0x46ba0b66389416f9b9efdb0acff2fa246aeca62e3a0b23cf1f2503daef255209"
# Cut(uint256 indexed tokenId, uint256 indexed headId, uint256 indexed tailId, uint256 index, address operator)
_TOPIC_CUT = "0x8a931aa6e7978064180abf7fe0fad5724567980368d0620b07f12c150063455a"
# Merged(uint256 indexed a, uint256 indexed b, uint256 indexed mergedId, address operator)
_TOPIC_MERGED = "0x16c20a9d07670de1acd6a4887d37d0bd6e908958838c007bdab074541130d1e0"
# Transfer(address indexed from, address indexed to, uint256 indexed tokenId)
_TOPIC_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

_OP_TOPICS = [_TOPIC_BONDED, _TOPIC_CLEAVED, _TOPIC_CUT, _TOPIC_MERGED]


# ---------------------------------------------------------------------------
# Minimal ABI encode/decode helpers (pure-stdlib, no eth_abi dep)
# ---------------------------------------------------------------------------


def _strip0x(hex_str: str) -> str:
    return hex_str[2:] if hex_str.startswith("0x") else hex_str


def _pad_left(hex_no_0x: str, width: int = 64) -> str:
    """Left-pad a hex string with zeros to *width* characters."""
    return hex_no_0x.lower().rjust(width, "0")


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


def _encode_uint(value: int) -> str:
    """Encode an integer as a 32-byte hex word (no 0x prefix)."""
    if value < 0:
        value &= (1 << 256) - 1
    return _pad_left(hex(value)[2:], 64)


def _encode_address(addr: str) -> str:
    """Encode an address as a 32-byte hex word (no 0x prefix)."""
    return _pad_left(_strip0x(addr).lower(), 64)


def _encode_call3(target: str, call_data: str, allow_failure: bool = True) -> str:
    """Encode a single Call3 struct (no 0x prefix).

    A Call3 is dynamic because of the bytes field; the actual array encoding is
    handled by :func:`_encode_aggregate3`.
    """
    cd = _strip0x(call_data)
    head = (
        _encode_address(target)
        + _pad_left("01" if allow_failure else "00", 64)
        + _pad_left("60", 64)
    )
    cd_len = len(cd) // 2
    cd_padded = cd + "0" * ((64 - (len(cd) % 64)) % 64)
    tail = _pad_left(hex(cd_len)[2:], 64) + cd_padded
    return head + tail


def _encode_aggregate3(calls: list[tuple[str, str, bool]]) -> str:
    """Build calldata for ``aggregate3(Call3[])``.

    Each input tuple is ``(target_address, callData_hex, allow_failure)``.
    Returns a hex string prefixed with ``0x``.
    """
    selector = _SEL_AGGREGATE3
    body = ""
    body += _pad_left("20", 64)  # offset to dynamic array
    body += _pad_left(hex(len(calls))[2:], 64)  # array length

    encoded_tuples = [_encode_call3(t, cd, af) for (t, cd, af) in calls]
    n = len(encoded_tuples)
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
            tup_start = elements_base + elt_off_bytes * 2
            success = int(raw[tup_start : tup_start + 64], 16) != 0
            bytes_off = int(raw[tup_start + 64 : tup_start + 128], 16)
            bytes_chars_start = tup_start + bytes_off * 2
            bytes_len = int(raw[bytes_chars_start : bytes_chars_start + 64], 16)
            body = raw[
                bytes_chars_start + 64 : bytes_chars_start + 64 + bytes_len * 2
            ]
            results.append((success, "0x" + body))
        return results
    except (ValueError, IndexError) as exc:
        logger.warning("Failed to decode aggregate3 result: %s", exc)
        return []


def _decode_token_data(hex_data: str) -> tuple[list[int], int, int, int, int]:
    """Decode ``tokenData`` return ``(uint256[] cores, uint8 materialId, uint8 form, uint8 coreCount, uint16 seed)``.

    The return is a single *dynamic* tuple (it contains a dynamic ``uint256[]``),
    so ABI-encoding wraps it behind a leading head offset word (typically
    ``0x20``).  We dereference that to find the tuple start, then read the
    tuple's own head: word 0 = byte-offset to the ``cores`` array (relative to
    the tuple start), words 1-4 = materialId / form / coreCount / seed; at
    ``tuple_start + cores_offset`` we read the array length then the core words.

    On empty / reverted input returns the graceful empty ``([], 0, 0, 0, 0)``.
    """
    raw = _strip0x(hex_data)
    # leading tuple offset word + 5 tuple head words = 6 words minimum
    if not raw or len(raw) < 6 * 64:
        return ([], 0, 0, 0, 0)
    try:
        tuple_offset_bytes = int(raw[0:64], 16)
        ts = tuple_offset_bytes * 2  # char index of the tuple start

        cores_offset_bytes = int(raw[ts : ts + 64], 16)
        material_id = int(raw[ts + 64 : ts + 128], 16)
        form = int(raw[ts + 128 : ts + 192], 16)
        core_count = int(raw[ts + 192 : ts + 256], 16)
        seed = int(raw[ts + 256 : ts + 320], 16)

        base = ts + cores_offset_bytes * 2  # char index of the cores length word
        length = int(raw[base : base + 64], 16)
        cores: list[int] = []
        for i in range(length):
            word_start = base + 64 + i * 64
            word = raw[word_start : word_start + 64]
            if not word:
                break
            cores.append(int(word, 16))
        return (cores, material_id, form, core_count, seed)
    except (ValueError, IndexError) as exc:
        logger.debug("tokenData decode failed: %s", exc)
        return ([], 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Event decoders
# ---------------------------------------------------------------------------


def _decode_bonded_log(log: dict) -> dict | None:
    """Decode ``Bonded(a, b, bondedId, operator)`` -> normalized op dict."""
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        return {
            "op_type": "bond",
            "token_id_a": int(topics[1], 16),
            "token_id_b": int(topics[2], 16),
            "result_id": int(topics[3], 16),
            "operator": _decode_address(log.get("data", "0x"), 0),
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash", "0x"),
            "timestamp": 0,  # placeholder — manager fills via block-number approximation
        }
    except Exception as exc:
        logger.debug("Bonded decode failed: %s", exc)
        return None


def _decode_cleaved_log(log: dict) -> dict | None:
    """Decode ``Cleaved(tokenId, lithicId, lumicId, operator)`` -> op dict.

    Cleave produces two ids; ``result_id`` holds lithicId, ``result_id_b``
    holds lumicId.
    """
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        return {
            "op_type": "cleave",
            "token_id_a": int(topics[1], 16),
            "token_id_b": None,
            "result_id": int(topics[2], 16),
            "result_id_b": int(topics[3], 16),
            "operator": _decode_address(log.get("data", "0x"), 0),
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash", "0x"),
            "timestamp": 0,  # placeholder — manager fills via block-number approximation
        }
    except Exception as exc:
        logger.debug("Cleaved decode failed: %s", exc)
        return None


def _decode_cut_log(log: dict) -> dict | None:
    """Decode ``Cut(tokenId, headId, tailId, index, operator)`` -> op dict.

    Data has TWO non-indexed words: ``index`` (word 0) then ``operator``
    (word 1). The operator is therefore the SECOND data word.
    """
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        return {
            "op_type": "cut",
            "token_id_a": int(topics[1], 16),
            "token_id_b": None,
            "result_id": int(topics[2], 16),
            "result_id_b": int(topics[3], 16),
            "operator": _decode_address(log.get("data", "0x"), 1),
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash", "0x"),
            "timestamp": 0,  # placeholder — manager fills via block-number approximation
        }
    except Exception as exc:
        logger.debug("Cut decode failed: %s", exc)
        return None


def _decode_merged_log(log: dict) -> dict | None:
    """Decode ``Merged(a, b, mergedId, operator)`` -> normalized op dict."""
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        return {
            "op_type": "merge",
            "token_id_a": int(topics[1], 16),
            "token_id_b": int(topics[2], 16),
            "result_id": int(topics[3], 16),
            "operator": _decode_address(log.get("data", "0x"), 0),
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash", "0x"),
            "timestamp": 0,  # placeholder — manager fills via block-number approximation
        }
    except Exception as exc:
        logger.debug("Merged decode failed: %s", exc)
        return None


def _decode_transfer_log(log: dict) -> dict | None:
    """Decode ERC721 ``Transfer(from, to, tokenId)`` -> normalized dict."""
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        return {
            "from": _addr_from_topic(topics[1]),
            "to": _addr_from_topic(topics[2]),
            "token_id": int(topics[3], 16),
            "block_number": int(log.get("blockNumber", "0x0"), 16),
            "tx_hash": log.get("transactionHash", "0x"),
        }
    except Exception as exc:
        logger.debug("Transfer decode failed: %s", exc)
        return None


_OP_DECODERS = {
    _TOPIC_BONDED: _decode_bonded_log,
    _TOPIC_CLEAVED: _decode_cleaved_log,
    _TOPIC_CUT: _decode_cut_log,
    _TOPIC_MERGED: _decode_merged_log,
}


# ---------------------------------------------------------------------------
# JSON-RPC error classification
# ---------------------------------------------------------------------------


class TalismansRpcError(RuntimeError):
    """A classified JSON-RPC failure.

    Subclasses ``RuntimeError`` so every existing ``except Exception`` /
    ``except RuntimeError`` site keeps working unchanged.

    ``kind`` is one of:

    ``range_cap``   the endpoint refuses this block span (drpc's 10,000 cap)
    ``result_cap``  too many results; ``suggested_to`` may name a narrower end
    ``timeout``     upstream timeout; retryable with a smaller window
    ``rate_limit``  429 / -32005 / -32029 — a smaller window does not help
    ``archive``     archive gate; this endpoint cannot serve historical data
    ``dead``        endpoint is down or has started requiring an API key
    ``transport``   connection-level failure
    ``rpc``         some other JSON-RPC error
    """

    def __init__(
        self, kind: str, message: str, *, suggested_to: int | None = None
    ) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.suggested_to = suggested_to


_SHRINKABLE = {"range_cap", "result_cap", "timeout"}
"""Kinds where **the same query over a smaller block window will succeed**.

Deliberately narrow. ``rate_limit`` is excluded because a smaller window buys
no quota — retrying harder is how a keyless endpoint starts refusing you
outright. ``archive`` is excluded because that gate is on *depth*, not
*width*: publicnode refuses a 100-block archive range exactly as it refuses a
250,000-block one (verified live). ``dead`` / ``rpc`` are excluded because
shrinking an error we do not understand turns one failed request into eight.
"""

_RESULT_CAP_MARKERS = (
    "returned more than",       # geth/tenderly: "Query returned more than N results"
    "too many logs",            # drpc
    "narrow your filter",       # drpc
    "exceeds max results",      # drpc
    "response size exceeded",   # common third-party phrasing
    "query timeout exceeded",   # geth's result-cap-shaped timeout
)

_RANGE_CAP_MARKERS = (
    "ranges over",              # drpc: "ranges over 10000 blocks are not supported"
    "is limited to",            # 1rpc: "eth_getLogs is limited to 0 - 50 blocks range"
    "block range",              # blastapi / flashbots phrasings
    "range is too large",
    "exceed maximum block range",
)

# Live-observed "retry with a narrower range" shapes:
#
#   blastapi: "this block range should work: [0x18708eb, 0x18708f4]"  bracketed hex
#   drpc:     "retry with the range 25583616-25585541"                bare decimal
#
# The bare-decimal branch demands two 6+ digit numbers so it cannot match the
# bare result count in "narrow your filter: 20000".
_SUGGESTED_RANGE_RE = re.compile(
    r"\[\s*(0x[0-9a-fA-F]+|\d+)\s*,\s*(0x[0-9a-fA-F]+|\d+)\s*\]"
    r"|(?<![\w.])(\d{6,})\s*-\s*(\d{6,})(?![\w.])"
)

_MIN_SUGGESTION_SHRINK = 0.9
"""A suggested retry range must drop at least 10% of the window to be used.

Provider suggestions are hints, not instructions. blastapi answers a
250,000-block request with a 10-block window pinned to the *end* of the
request, so its ``to`` is essentially the ``to`` we already asked for —
following it verbatim would "shrink" the window by nothing and burn the whole
shrink budget without converging. Requiring a material shrink degrades that
case to a clean halving while still honouring honest suggestions.
"""


def _parse_suggested_to(text: str) -> int | None:
    """Upper bound of a provider-suggested retry range, or ``None``."""
    match = _SUGGESTED_RANGE_RE.search(text or "")
    if not match:
        return None
    raw = match.group(2) or match.group(4)
    if not raw:
        return None
    try:
        return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return None


def _classify_rpc_error(error: Any) -> TalismansRpcError:
    """Map a JSON-RPC ``error`` member onto a :class:`TalismansRpcError`.

    Classification is driven by the message **text**, not the code, because the
    codes are worthless here — every one of these was read off the wire on
    2026-07-27 and they all share code ``-32602`` or ``-32600``:

    * publicnode  ``-32602`` "Archive requests require a personal token"
    * 1rpc        ``-32602`` "eth_getLogs is limited to 0 - 50 blocks range"
    * flashbots   ``-32602`` "block range extends beyond current head block"
    * blastapi    ``-32600`` "You can make eth_getLogs requests with up to a
      10 block range"

    An archive gate, a range cap and a nonsense error, all indistinguishable by
    code. Order matters below: rate limiting is matched on text first, since a
    429 body that reads "request a personal token ..." would otherwise be
    relabelled as a permanent archive gate.
    """
    if not isinstance(error, dict):
        return TalismansRpcError("rpc", str(error))
    code = error.get("code")
    message = str(error.get("message", ""))
    data = str(error.get("data", ""))
    blob = f"{message} {data}".lower()
    detail = message or data or str(error)

    if "rate limit" in blob or "too many requests" in blob:
        return TalismansRpcError("rate_limit", detail)
    if "archive" in blob:
        return TalismansRpcError("archive", detail)
    if any(marker in blob for marker in _RESULT_CAP_MARKERS):
        return TalismansRpcError(
            "result_cap",
            detail,
            suggested_to=_parse_suggested_to(f"{data} {message}"),
        )
    if any(marker in blob for marker in _RANGE_CAP_MARKERS):
        return TalismansRpcError(
            "range_cap",
            detail,
            suggested_to=_parse_suggested_to(f"{data} {message}"),
        )
    if "timeout" in blob or "timed out" in blob or code == 30:
        return TalismansRpcError("timeout", detail)
    if code in (-32005, -32029):
        return TalismansRpcError("rate_limit", detail)
    if "api key" in blob or "unauthorized" in blob or "authenticate" in blob:
        return TalismansRpcError("dead", detail)
    if code == -32601:  # method not found — this endpoint lacks the RPC
        return TalismansRpcError("dead", detail)
    # drpc reports its range cap with a bespoke code 35 and no standard marker.
    if code == 35:
        return TalismansRpcError("range_cap", detail)
    return TalismansRpcError("rpc", detail)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TalismansClient:
    """Async client for Talismans on-chain data.

    All methods are exception-safe: network failures bubble up as ``0`` /
    empty-collection returns rather than raising, so the manager's refresh
    cycle is never killed by a single bad upstream.

    Parameters
    ----------
    primary_rpc, fallback_rpcs:
        Ethereum mainnet JSON-RPC endpoints. If ``primary_rpc`` returns a 429
        or 5xx, the client retries on each of the fallbacks in order.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``. If not provided one is
        created internally and closed on ``close()``.
    """

    def __init__(
        self,
        primary_rpc: str = _PRIMARY_RPC,
        fallback_rpcs: list[str] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._primary_rpc = primary_rpc
        self._fallback_rpcs = list(fallback_rpcs or _FALLBACK_RPCS)
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._request_id = 0
        self._last_rpc_at: float = 0.0
        # Learned eth_getLogs page size; shrinks on a provider's range/result
        # cap and grows back after a run of clean pages.
        self._log_window = _LOG_RANGE_PER_CALL
        self._log_window_ok = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> TalismansClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: RPC plumbing with retry + fallback
    # ------------------------------------------------------------------

    async def _rpc(
        self, method: str, params: list, endpoints: list[str] | None = None
    ) -> Any:
        """Send a JSON-RPC call with retry + RPC fallback.

        Returns the ``result`` field on success. Raises
        :class:`TalismansRpcError` (a ``RuntimeError``) if every endpoint fails
        after every retry.

        A JSON-RPC ``error`` member **never** short-circuits the remaining
        endpoints. It used to: codes ``-32600/-32601/-32602/-32604`` were
        treated as terminal protocol errors and re-raised immediately. Live
        probing shows not one of those codes means "the request is malformed
        everywhere" — publicnode returns ``-32602`` for its archive gate, 1rpc
        for its 50-block cap, blastapi returns ``-32600`` for its 10-block cap,
        merkle ``-32601`` because it has no ``eth_getLogs``. All four are
        per-endpoint conditions that the very next endpoint answers correctly,
        so the old short-circuit turned one picky provider into a total outage.
        The cost of the change is bounded: a genuinely malformed call now costs
        one round trip per endpoint instead of one.

        When every endpoint fails, the raised error prefers a *shrinkable*
        classification over the chronologically last one, so a caller that can
        narrow its block window still learns that narrowing would help even if
        some later endpoint failed for an unrelated reason.
        """
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
        urls = list(endpoints) if endpoints else [
            self._primary_rpc,
            *self._fallback_rpcs,
        ]
        errors: list[TalismansRpcError] = []
        for url in urls:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._client.post(url, json=payload)
                    try:
                        body = resp.json()
                    except Exception:
                        body = None

                    # A JSON-RPC ``error`` member is classified before any 4xx
                    # status handling, because the HTTP status carries no
                    # information about *which* error it is. Live, on one and
                    # the same over-long eth_getLogs range:
                    #
                    #   eth.drpc.org  HTTP 400 + "ranges over 10000 blocks"
                    #   publicnode    HTTP 403 + "Archive requests require..."
                    #   1rpc.io/eth   HTTP 200 + "limited to 0 - 50 blocks"
                    #
                    # drpc's is the one error in that set a narrower window
                    # actually fixes, and it is the one wearing a 4xx. Letting
                    # raise_for_status() run first demotes the most recoverable
                    # error we get to an opaque transport failure — which is
                    # exactly what it did until a live drpc-only backfill
                    # exposed it. 5xx is excluded here so a server-side blip
                    # still gets its backoff retry whatever the body says.
                    if (
                        resp.status_code < 500
                        and isinstance(body, dict)
                        and body.get("error") is not None
                    ):
                        classified = _classify_rpc_error(body["error"])
                        logger.debug(
                            "%s on %s -> %s: %s",
                            method,
                            url,
                            classified.kind,
                            classified.message,
                        )
                        errors.append(classified)
                        break  # try next endpoint

                    # Checked before the 5xx retry: the Cloudflare 52x codes are
                    # >= 500 but mean "this endpoint is gone", so retrying them
                    # only spends backoff on a host that will not answer.
                    if resp.status_code in _ENDPOINT_DEAD_CODES:
                        errors.append(
                            TalismansRpcError(
                                "dead", f"{url} returned {resp.status_code}"
                            )
                        )
                        break
                    if resp.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"RPC {url} returned {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    if resp.status_code == 429:
                        errors.append(
                            TalismansRpcError("rate_limit", f"{url} returned 429")
                        )
                        break
                    resp.raise_for_status()
                    if not isinstance(body, dict):
                        errors.append(
                            TalismansRpcError("rpc", f"{url} returned non-JSON body")
                        )
                        break
                    return body.get("result", "0x")
                except (httpx.HTTPError, httpx.StreamError) as exc:
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
                        errors.append(TalismansRpcError("transport", str(exc)))
                        break

        # Prefer a shrinkable diagnosis so _get_logs can act on it.
        chosen = next(
            (e for e in errors if e.kind in _SHRINKABLE),
            errors[-1] if errors else None,
        )
        if chosen is None:
            raise TalismansRpcError("rpc", f"{method} failed on all endpoints")
        raise TalismansRpcError(
            chosen.kind,
            f"{method} failed on all {len(urls)} endpoints; last={chosen.message}",
            suggested_to=chosen.suggested_to,
        )

    async def _eth_call(self, to: str, data: str, block: str = "latest") -> str:
        return await self._rpc("eth_call", [{"to": to, "data": data}, block])

    async def _eth_block_number(self) -> int:
        result = await self._rpc("eth_blockNumber", [])
        return int(result, 16)

    @staticmethod
    def _shrunk_end(cursor: int, chunk_end: int, suggested_to: int | None) -> int:
        """Pick a narrower ``toBlock`` for a chunk the endpoint refused.

        Halves the window, unless the provider suggested an end that lies
        inside it *and* removes at least ``1 - _MIN_SUGGESTION_SHRINK`` of it.
        """
        span = chunk_end - cursor + 1
        if (
            suggested_to is not None
            and cursor <= suggested_to < chunk_end
            and (suggested_to - cursor + 1) <= _MIN_SUGGESTION_SHRINK * span
        ):
            return suggested_to
        return cursor + max(_MIN_LOG_WINDOW, span // 2) - 1

    async def _get_logs(
        self,
        address: str | list[str],
        topics: list,
        from_block: int,
        to_block: int,
    ) -> tuple[list[dict], int]:
        """Fetch event logs, paged, reporting **how far the scan actually got**.

        Returns ``(logs, last_complete_block)`` where every block in
        ``[from_block, last_complete_block]`` was successfully scanned. On a
        total failure of the very first page that is ``from_block - 1``, i.e.
        "no progress" — callers must not advance a watermark past it.

        This return shape is the fix for the silent-drop bug: the previous
        implementation caught each page's exception, logged it at ``debug`` and
        skipped to the next page, so the method could return ``[]`` from a
        complete outage while looking exactly like a genuinely empty range. The
        caller then advanced its watermark over the gap and the events in it —
        along with the result token ids that are the only id-discovery
        mechanism besides genesis seeding — were lost permanently.

        A refused page is retried on a narrower window first, but only when the
        refusal is one the narrowing can actually fix (see :data:`_SHRINKABLE`).
        The learned window persists across pages, so a 10,000-block-capped
        provider costs one shrink for the whole scan rather than one per page.
        """
        if from_block > to_block:
            return [], to_block
        all_logs: list[dict] = []
        cursor = from_block
        while cursor <= to_block:
            chunk_end = min(cursor + self._log_window - 1, to_block)
            shrinks = 0
            while True:
                params = {
                    "address": address,
                    "topics": topics,
                    "fromBlock": hex(cursor),
                    "toBlock": hex(chunk_end),
                }
                try:
                    logs = await self._rpc("eth_getLogs", [params], _LOG_RPCS)
                    break
                except TalismansRpcError as exc:
                    if (
                        exc.kind in _SHRINKABLE
                        and shrinks < _MAX_LOG_SHRINKS
                        and chunk_end > cursor
                    ):
                        shrinks += 1
                        chunk_end = self._shrunk_end(
                            cursor, chunk_end, exc.suggested_to
                        )
                        self._log_window = chunk_end - cursor + 1
                        self._log_window_ok = 0
                        logger.debug(
                            "eth_getLogs %s: narrowing to [%d..%d]",
                            exc.kind,
                            cursor,
                            chunk_end,
                        )
                        continue
                    logger.warning(
                        "eth_getLogs [%d..%d] failed (%s: %s); scan stops at %d",
                        cursor,
                        chunk_end,
                        exc.kind,
                        exc.message,
                        cursor - 1,
                    )
                    return all_logs, cursor - 1
                except Exception as exc:  # pragma: no cover - defensive
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
                    "eth_getLogs [%d..%d] returned %s, not a list; scan stops at %d",
                    cursor,
                    chunk_end,
                    type(logs).__name__,
                    cursor - 1,
                )
                return all_logs, cursor - 1

            all_logs.extend(logs)
            cursor = chunk_end + 1

            # Widen again after a run of clean pages, so one transient refusal
            # does not pin the client to a tiny window for the rest of its life.
            if self._log_window < _LOG_RANGE_PER_CALL:
                self._log_window_ok += 1
                if self._log_window_ok >= _LOG_WINDOW_GROWTH_AFTER:
                    self._log_window = min(
                        _LOG_RANGE_PER_CALL, self._log_window * 2
                    )
                    self._log_window_ok = 0
        return all_logs, to_block

    async def _multicall(self, calls: list[tuple[str, str]]) -> list[tuple[bool, str]]:
        """Batch many eth_calls into one Multicall3 ``aggregate3``.

        Each input tuple is ``(target_address, callData_hex)``. All calls run
        with ``allowFailure=True`` so one bad target doesn't kill the batch.
        Returns a list of ``(success, returnData)`` in the same order.

        Raises ``TalismansRpcError`` / ``RuntimeError`` when the *transport*
        failed -- every endpoint exhausted, or a reply that does not decode
        into one ``Result`` per call. A per-call revert inside a healthy
        multicall is still reported in-band as ``(False, "0x")``.

        Keeping those two apart is what makes the callers' error handling real
        (MEDI-27, MEDI-28). This used to catch everything and return
        ``[(False, "0x")] * len(calls)``, so an RPC blip was indistinguishable
        from "every call reverted": ``fetch_collection_flags`` answered
        ``total_supply=0`` and ``fetch_token_states`` answered ``{}``, the
        manager's ``except`` branches were unreachable dead code, and the
        dashboard reported an empty collection -- persisting the zeros into the
        hourly sparkline, where ``forge_momentum_signal`` read them as a
        bullish green "CONSOLIDATING" that a network error had manufactured.
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

    async def fetch_collection_flags(self) -> dict:
        """Read collection-level flags in one multicall.

        Returns ``{total_supply, genesis_minted, next_transform_id,
        bond_cleave_enabled, cut_merge_enabled}``.

        Raises if the multicall itself could not be made (MEDI-28), so the
        manager falls back to its cached counts instead of reporting a
        collection that has ceased to exist. An individual read that reverts on
        a healthy node is still reported as 0/False.

        ``next_transform_id`` is the contract's id allocator for post-genesis
        tokens and is what makes enumeration complete on a fresh install — see
        :meth:`TalismansManager._seed_transform_ids`.
        """
        calls = [
            (_CONTRACT, _SEL_TOTAL_SUPPLY),
            (_CONTRACT, _SEL_GENESIS_MINTED),
            (_CONTRACT, _SEL_BOND_ENABLED),
            (_CONTRACT, _SEL_CUTMERGE_ENABLED),
            (_CONTRACT, _SEL_NEXT_TRANSFORM_ID),
        ]
        results = await self._multicall(calls)

        def _u(idx: int) -> int:
            if idx >= len(results):
                return 0
            ok, data = results[idx]
            return _decode_uint(data) if ok else 0

        return {
            "total_supply": _u(0),
            "genesis_minted": _u(1),
            "bond_cleave_enabled": bool(_u(2)),
            "cut_merge_enabled": bool(_u(3)),
            "next_transform_id": _u(4),
        }

    async def fetch_transfer_logs(
        self, from_block: int, to_block: int
    ) -> tuple[list[dict], int]:
        """Fetch ERC721 ``Transfer`` logs in a block range.

        Returns ``(events, last_complete_block)``; each event is a
        ``{from, to, token_id, block_number, tx_hash}`` dict. See
        :meth:`_get_logs` for the watermark contract.
        """
        logs, scanned_to = await self._get_logs(
            _CONTRACT, [_TOPIC_TRANSFER], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_transfer_log(log)
            if decoded is not None:
                out.append(decoded)
        return out, scanned_to

    async def fetch_operation_logs(
        self, from_block: int, to_block: int
    ) -> tuple[list[dict], int]:
        """Fetch the four shape-mutation events (Bonded/Cleaved/Cut/Merged).

        Uses a single ``topics[0]`` OR-filter so one paged scan covers all four
        event types. Returns ``(ops, last_complete_block)`` — the caller must
        advance its scan watermark to ``last_complete_block``, never to the
        requested ``to_block``, or a refused page silently loses its events and
        the result token ids they carry.
        """
        logs, scanned_to = await self._get_logs(
            _CONTRACT, [_OP_TOPICS], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            topics = log.get("topics", [])
            if not topics:
                continue
            decoder = _OP_DECODERS.get(topics[0])
            if decoder is None:
                continue
            decoded = decoder(log)
            if decoded is not None:
                out.append(decoded)
        return out, scanned_to

    async def fetch_token_states(
        self, token_ids: list[int]
    ) -> dict[int, dict]:
        """Batch-read ``tokenData`` + ``ownerOf`` for each id via Multicall3.

        Calls run with ``allowFailure=True`` in chunks of ``_TOKEN_STATE_CHUNK``
        ids. Returns ``{id: {core_count, material_id, form, seed, owner}}`` for
        LIVE ids only -- ids are skipped when the ``tokenData`` call failed,
        ``core_count == 0``, or ``ownerOf`` reverted. Those three are real
        answers about a token: burned, consumed by a bond/merge, or never
        minted.

        Raises if any chunk's multicall could not be made (MEDI-27). A
        truncated sweep must not be mistaken for a shrunken collection: the
        caller rebuilds its whole registry from this dict, so a partial return
        would delete every token in the chunks that failed.
        """
        if not token_ids:
            return {}
        out: dict[int, dict] = {}
        for start in range(0, len(token_ids), _TOKEN_STATE_CHUNK):
            chunk = token_ids[start : start + _TOKEN_STATE_CHUNK]
            calls: list[tuple[str, str]] = []
            for tid in chunk:
                arg = _encode_uint(tid)
                calls.append((_CONTRACT, _SEL_TOKEN_DATA + arg))
                calls.append((_CONTRACT, _SEL_OWNER_OF + arg))
            results = await self._multicall(calls)
            for i, tid in enumerate(chunk):
                td_idx = 2 * i
                ow_idx = 2 * i + 1
                if ow_idx >= len(results):
                    continue
                td_ok, td_data = results[td_idx]
                ow_ok, ow_data = results[ow_idx]
                if not td_ok or not ow_ok:
                    continue
                cores, material_id, form, core_count, seed = _decode_token_data(
                    td_data
                )
                if core_count == 0:
                    continue
                out[tid] = {
                    "core_count": core_count,
                    "material_id": material_id,
                    "form": form,
                    "seed": seed,
                    "owner": _decode_address(ow_data, 0),
                }
        return out


# Public re-exports the manager / cache use.
__all__ = [
    "TalismansClient",
    "TalismansRpcError",
    "_CONTRACT",
    "_MULTICALL3",
    "_DEFAULT_LOG_LOOKBACK_BLOCKS",
    "_LOG_RANGE_PER_CALL",
    "_LOG_RPCS",
    "_SEL_NEXT_TRANSFORM_ID",
    "_classify_rpc_error",
    "_parse_suggested_to",
    "_TOPIC_BONDED",
    "_TOPIC_CLEAVED",
    "_TOPIC_CUT",
    "_TOPIC_MERGED",
    "_TOPIC_TRANSFER",
    "_SEL_TOKEN_DATA",
    "_SEL_OWNER_OF",
    "_decode_token_data",
    "_decode_bonded_log",
    "_decode_cleaved_log",
    "_decode_cut_log",
    "_decode_merged_log",
    "_decode_transfer_log",
    "_encode_uint",
    "_pad_left",
    "_strip0x",
]
