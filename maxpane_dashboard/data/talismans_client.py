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
* ``publicnode`` caps ``eth_getLogs`` at 50_000 blocks per call (-32701 if
  exceeded), so all log scans page at ``_LOG_RANGE_PER_CALL``.

Structurally a clone of :mod:`maxpane_dashboard.data.ttt_client`: the
``_rpc`` / ``_eth_call`` / ``_get_logs`` / ``_multicall`` machinery and the
pure-stdlib ABI encode/decode helpers are reused verbatim.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_PRIMARY_RPC = "https://ethereum.publicnode.com"  # recon-verified reliable + eth_getLogs works
_FALLBACK_RPCS = [
    "https://cloudflare-eth.com",
    "https://eth.drpc.org",
    "https://rpc.ankr.com/eth",
]
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 10.0
_INTER_CALL_DELAY = 0.05  # seconds between consecutive RPC calls
_ENDPOINT_DEAD_CODES = {403, 451, 521, 522, 523, 524, 525, 526}

_CONTRACT = "0x724d5beffe9a84a87ad1af83713f80600e5f5774"
_MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"

_LOG_RANGE_PER_CALL = 50_000  # publicnode hard cap (-32701 if exceeded)
_DEFAULT_LOG_LOOKBACK_BLOCKS = 250_000
_INCREMENTAL_LOG_LOOKBACK = 10_000

# Multicall3 chunk size for the token-state sweep (2 calls per id).
_TOKEN_STATE_CHUNK = 150

# ---------------------------------------------------------------------------
# Function selectors (first 4 bytes of keccak256 of the signature)
# ---------------------------------------------------------------------------

_SEL_TOTAL_SUPPLY = "0x18160ddd"  # totalSupply()
_SEL_GENESIS_MINTED = "0x153de143"  # genesisMinted()
_SEL_BOND_ENABLED = "0xd11543fd"  # bondAndCleaveEnabled()
_SEL_CUTMERGE_ENABLED = "0xdafa0f1a"  # cutAndMergeEnabled()
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


def _to_hex(b: bytes) -> str:
    return "0x" + b.hex()


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

    The first head word is the byte-offset to the dynamic ``cores`` array; the
    next 4 head words are materialId / form / coreCount / seed; at ``offset/32``
    we read the array length then that many core words.

    On empty / reverted input returns the graceful empty ``([], 0, 0, 0, 0)``.
    """
    raw = _strip0x(hex_data)
    if not raw or len(raw) < 5 * 64:
        return ([], 0, 0, 0, 0)
    try:
        cores_offset_bytes = int(raw[0:64], 16)
        material_id = int(raw[64:128], 16)
        form = int(raw[128:192], 16)
        core_count = int(raw[192:256], 16)
        seed = int(raw[256:320], 16)

        base = cores_offset_bytes * 2  # char index of the cores length word
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
            "timestamp": 0,
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
            "timestamp": 0,
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
            "timestamp": 0,
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
            "timestamp": 0,
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

    async def _rpc(self, method: str, params: list) -> Any:
        """Send a JSON-RPC call with retry + RPC fallback.

        Returns the ``result`` field on success. Raises ``RuntimeError`` if
        every endpoint fails after every retry.
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
        endpoints = [self._primary_rpc, *self._fallback_rpcs]
        last_err: BaseException | None = None
        for url in endpoints:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await self._client.post(url, json=payload)
                    if resp.status_code in _ENDPOINT_DEAD_CODES:
                        last_err = httpx.HTTPStatusError(
                            f"RPC {url} returned {resp.status_code}",
                            request=resp.request,
                            response=resp,
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
                    if "error" in body:
                        err = body["error"]
                        code = err.get("code") if isinstance(err, dict) else None
                        if code in {-32600, -32601, -32602, -32604}:
                            raise RuntimeError(f"RPC error: {err}")
                        last_err = RuntimeError(f"RPC {url} error: {err}")
                        break  # try next endpoint
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

    async def _get_logs(
        self,
        address: str | list[str],
        topics: list,
        from_block: int,
        to_block: int,
    ) -> list[dict]:
        """Fetch event logs with auto-pagination at ``_LOG_RANGE_PER_CALL``."""
        if from_block > to_block:
            return []
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
                logs = await self._rpc("eth_getLogs", [params])
            except Exception as exc:
                logger.debug(
                    "eth_getLogs [%d..%d] failed: %s", cursor, chunk_end, exc
                )
                cursor = chunk_end + 1
                continue
            if isinstance(logs, list):
                all_logs.extend(logs)
            cursor = chunk_end + 1
        return all_logs

    async def _multicall(self, calls: list[tuple[str, str]]) -> list[tuple[bool, str]]:
        """Batch many eth_calls into one Multicall3 ``aggregate3``.

        Each input tuple is ``(target_address, callData_hex)``. All calls run
        with ``allowFailure=True`` so one bad target doesn't kill the batch.
        Returns a list of ``(success, returnData)`` in the same order.
        """
        if not calls:
            return []
        payload_calls = [(t, cd, True) for (t, cd) in calls]
        data = _encode_aggregate3(payload_calls)
        try:
            raw = await self._eth_call(_MULTICALL3, data)
        except Exception as exc:
            logger.warning("multicall(%d calls) failed: %s", len(calls), exc)
            return [(False, "0x") for _ in calls]
        return _decode_aggregate3_result(raw)

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

        Returns ``{total_supply, genesis_minted, bond_cleave_enabled,
        cut_merge_enabled}``. Missing / failed reads are reported as 0/False.
        """
        calls = [
            (_CONTRACT, _SEL_TOTAL_SUPPLY),
            (_CONTRACT, _SEL_GENESIS_MINTED),
            (_CONTRACT, _SEL_BOND_ENABLED),
            (_CONTRACT, _SEL_CUTMERGE_ENABLED),
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
        }

    async def fetch_transfer_logs(
        self, from_block: int, to_block: int
    ) -> list[dict]:
        """Fetch ERC721 ``Transfer`` logs in a block range.

        Returns ``{from, to, token_id, block_number, tx_hash}`` dicts.
        """
        logs = await self._get_logs(
            _CONTRACT, [_TOPIC_TRANSFER], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_transfer_log(log)
            if decoded is not None:
                out.append(decoded)
        return out

    async def fetch_operation_logs(
        self, from_block: int, to_block: int
    ) -> list[dict]:
        """Fetch the four shape-mutation events (Bonded/Cleaved/Cut/Merged).

        Uses a single ``topics[0]`` OR-filter so one paged scan covers all
        four event types. Returns a merged list of normalized op dicts.
        """
        logs = await self._get_logs(
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
        return out

    async def fetch_token_states(
        self, token_ids: list[int]
    ) -> dict[int, dict]:
        """Batch-read ``tokenData`` + ``ownerOf`` for each id via Multicall3.

        Calls run with ``allowFailure=True`` in chunks of ``_TOKEN_STATE_CHUNK``
        ids. Returns ``{id: {core_count, material_id, form, seed, owner}}`` for
        LIVE ids only -- ids are skipped when the ``tokenData`` call failed,
        ``core_count == 0``, or ``ownerOf`` reverted.
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
    "_CONTRACT",
    "_MULTICALL3",
    "_DEFAULT_LOG_LOOKBACK_BLOCKS",
    "_INCREMENTAL_LOG_LOOKBACK",
    "_LOG_RANGE_PER_CALL",
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
