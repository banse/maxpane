"""Async HTTP/RPC client for Ten Thousand Tokens (TTT) data on Ethereum mainnet.

Three data sources, all keyless:

* Ethereum mainnet JSON-RPC (LlamaRPC + fallbacks): factory + FeeSplitter views,
  event logs, ETH balances.
* DexScreener public API: per-token price / volume / market cap, batched up to
  30 addresses per call.
* Reservoir public NFT API (keyless tier): collection floor price and 24h sales
  count.

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
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_PRIMARY_RPC = "https://cloudflare-eth.com"
_FALLBACK_RPCS = [
    "https://eth.drpc.org",
    "https://rpc.ankr.com/eth",
    "https://eth.llamarpc.com",
]
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (0.5, 1.5)
_REQUEST_TIMEOUT = 10.0
_INTER_CALL_DELAY = 0.05  # seconds between consecutive RPC calls

_DEXSCREENER_BATCH_URL = "https://api.dexscreener.com/tokens/v1/ethereum/{addresses}"
_DEXSCREENER_MAX_BATCH = 30
_RESERVOIR_FLOOR_URL = "https://api.reservoir.tools/collections/v7?contract={contract}"

_MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_FACTORY = "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"
_FEESPLITTER = "0x6e46eaa57e1c7589686e2b0c935e8a8cf907683e"

_LOG_RANGE_PER_CALL = 10_000  # blocks per eth_getLogs call
_SCALE = 10**30  # FeeSplitter SCALE constant (NOT 1e18)
_WEI = 10**18

# Approximate deploy block of the factory. We use this as a lower bound when
# we have nothing in the cache yet. (The factory was deployed in May 2026 --
# we cap the lookback to roughly the most recent ~150_000 blocks ≈ 3 weeks.)
_DEFAULT_LOG_LOOKBACK_BLOCKS = 150_000
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

    Fetches state from Ethereum mainnet RPC, DexScreener, and Reservoir. All
    methods are exception-safe: network failures bubble up as ``None`` /
    empty-list returns rather than raising, so the manager's refresh cycle
    is never killed by a single bad upstream.

    Parameters
    ----------
    primary_rpc, fallback_rpcs:
        Ethereum mainnet JSON-RPC endpoints. If ``primary_rpc`` returns a
        429 or 5xx, the client retries on each of the fallbacks in order.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``. If not provided one
        is created internally and closed on ``close()``.
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

    async def __aenter__(self) -> TTTClient:
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
        endpoints = [self._primary_rpc, *self._fallback_rpcs]
        last_err: BaseException | None = None
        # Status codes meaning "the endpoint itself is broken or blocking us"
        # rather than transient; don't waste retries on them.
        _ENDPOINT_DEAD_CODES = {403, 451, 521, 522, 523, 524, 525, 526}
        for url in endpoints:
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
                    body = resp.json()
                    if "error" in body:
                        err = body["error"]
                        code = err.get("code") if isinstance(err, dict) else None
                        # JSON-RPC codes -32600/-32601/-32602/-32604 are "your
                        # request is malformed" -- those are genuinely caller
                        # errors that won't be fixed by trying another endpoint.
                        # Everything else (Internal error -32603, server-defined
                        # codes like -32046 "Cannot fulfill request") is the
                        # endpoint refusing to handle this call; fall over.
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

    async def fetch_factory_state(self) -> dict[str, int]:
        """Read factory + FeeSplitter state in one multicall.

        Returns a flat dict with keys: ``max_supply``, ``total_minted``,
        ``burn_count``, ``active_shares``, ``acc_eth_per_share``. Missing /
        failed reads are reported as 0.
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
    ) -> list[dict]:
        """Enumerate every NFT->ERC20 deployment in a block range.

        Returns a list of ``{token_id, erc20_address, holder, block_number,
        tx_hash}`` dicts. Use this at startup to discover all 10,000 token
        contracts in one pass.
        """
        logs = await self._get_logs(
            _FACTORY, [_TOPIC_TOKEN_DEPLOYED], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_token_deployed_log(log)
            if decoded is not None:
                out.append(decoded)
        return out

    async def fetch_launched_events(
        self, from_block: int, to_block: int
    ) -> list[dict]:
        """Fetch burn-and-launch events from the factory's ``Launched`` topic.

        Returns ``{token_id, erc20_address, launcher, block_number, tx_hash}``.
        """
        logs = await self._get_logs(
            _FACTORY, [_TOPIC_LAUNCHED], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_launched_log(log)
            if decoded is not None:
                out.append(decoded)
        return out

    async def fetch_deposit_events(
        self, from_block: int, to_block: int
    ) -> list[dict]:
        """Fetch FeeSplitter ``Deposited`` events with full 7-field decode."""
        logs = await self._get_logs(
            _FEESPLITTER, [_TOPIC_DEPOSITED], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_deposited_log(log)
            if decoded is not None:
                out.append(decoded)
        return out

    async def fetch_buyback_events(
        self,
        token_addresses: list[str],
        from_block: int,
        to_block: int,
    ) -> list[dict]:
        """Fetch ``Bought`` events emitted by any of the given ERC20s.

        Returns one dict per event with the source token, caller, eth spent,
        tokens bought, and bounty reward.
        """
        if not token_addresses:
            return []
        addresses = [a.lower() for a in token_addresses]
        # Some RPCs reject array-form `address`; we paginate manually if needed.
        logs = await self._get_logs(
            addresses, [_TOPIC_BOUGHT], from_block, to_block
        )
        out: list[dict] = []
        for log in logs:
            decoded = _decode_bought_log(log)
            if decoded is not None:
                out.append(decoded)
        return out

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

    async def fetch_nft_floor(self) -> dict[str, Any] | None:
        """Get current floor + 24h sales from Reservoir's keyless tier.

        Returns ``{floor_eth, floor_usd, sales_24h}`` or ``None`` if
        Reservoir is unreachable / rate-limited.
        """
        url = _RESERVOIR_FLOOR_URL.format(contract=_FACTORY)
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(
                    url, headers={"Accept": "*/*"}
                )
                if resp.status_code in (401, 403):
                    logger.debug(
                        "Reservoir floor returned %d (keyless rate-limit)",
                        resp.status_code,
                    )
                    return None
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Reservoir {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                payload = resp.json()
                collections = payload.get("collections") or []
                if not collections:
                    return None
                c0 = collections[0]
                floor_ask = c0.get("floorAsk") or {}
                price = floor_ask.get("price") or {}
                amount = price.get("amount") or {}
                floor_eth = _safe_float(amount.get("native"))
                floor_usd = _safe_float(amount.get("usd"))
                volume = c0.get("volume") or {}
                sales_24h_raw = (
                    (c0.get("salesCount") or {}).get("1day")
                    if isinstance(c0.get("salesCount"), dict)
                    else None
                )
                if sales_24h_raw is None:
                    daily_vol = volume.get("1day")
                    sales_24h_raw = None if daily_vol is None else None
                sales_24h: int | None
                try:
                    sales_24h = (
                        int(sales_24h_raw) if sales_24h_raw is not None else None
                    )
                except (TypeError, ValueError):
                    sales_24h = None
                return {
                    "floor_eth": floor_eth if floor_eth > 0 else None,
                    "floor_usd": floor_usd if floor_usd > 0 else None,
                    "sales_24h": sales_24h,
                }
            except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError) as exc:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                else:
                    logger.debug("Reservoir floor failed: %s", exc)
        return None


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


# Public re-exports the manager / cache use.
__all__ = [
    "TTTClient",
    "_DEFAULT_LOG_LOOKBACK_BLOCKS",
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
