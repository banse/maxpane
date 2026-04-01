"""Async HTTP client for Onchain Monsters data from Ethereum mainnet RPC.

Read-only -- fetches NFT collection state, staking stats, and recent
activity via eth_call and eth_getLogs.  Uses httpx.AsyncClient with
exponential-backoff retries, matching the pattern established by the
CatTown client.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from typing import Any

import httpx

from maxpane_dashboard.data.ocm_models import (
    OCMActivityEvent,
    OCMCollectionStats,
    OCMSnapshot,
    OCMStakingStats,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (2.0, 4.0, 8.0)
_REQUEST_TIMEOUT = 15.0
_INTER_CALL_DELAY = 0.5  # seconds between consecutive RPC calls
_WEI = 10**18

# ---------------------------------------------------------------------------
# RPC endpoint
# ---------------------------------------------------------------------------

_RPC_URL = os.environ.get("MAXPANE_ETH_RPC_URL", "https://ethereum-rpc.publicnode.com")

# ---------------------------------------------------------------------------
# Contract addresses
# ---------------------------------------------------------------------------

_NFT_ADDRESS = "0xaA5D0f2E6d008117B16674B0f00B6FCa46e3EFC4"
_OCMD_ADDRESS = "0x10971797FcB9925d01bA067e51A6F8333Ca000B1"
_FAUCET_ADDRESS = "0xd495a9955550c20d03197c8ba3f3a8c7f8d17eb3"

# ---------------------------------------------------------------------------
# Function selectors (first 4 bytes of keccak256 hash of signature)
# ---------------------------------------------------------------------------

_SEL_TOTAL_SUPPLY = "0x18160ddd"        # totalSupply()
_SEL_BALANCE_OF = "0x70a08231"          # balanceOf(address)

# Selectors for NFT-specific reads.
# NOTE: These need keccak256 verification against the verified Etherscan ABI.
# To verify: Web3.keccak(text="currentMintingCost()")[:4].hex()
# If the selector is wrong the eth_call will return 0x or revert silently.
_SEL_CURRENT_MINTING_COST = "0x9b7fb032"  # currentMintingCost() -- verified via web3_sha3
_SEL_IS_CLOSED = "0xc2b6b58c"             # isClosed() -- VERIFY

# ---------------------------------------------------------------------------
# ERC-721 Transfer event topic
# ---------------------------------------------------------------------------

_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
_ZERO_ADDR_TOPIC = "0x" + "0" * 64

# ---------------------------------------------------------------------------
# OCMD staking contract address (held NFTs = staked NFTs)
# ---------------------------------------------------------------------------

_OCMD_ADDR_PADDED = _OCMD_ADDRESS[2:].lower().zfill(64)
_OCMD_ADDR_TOPIC = "0x" + _OCMD_ADDR_PADDED

# ---------------------------------------------------------------------------
# Burn address (Onchain Monsters uses 0xdead...dead, not the zero address)
# ---------------------------------------------------------------------------

_BURN_ADDRESS = "0xdeaDDeADDEaDdeaDdEAddEADDEAdDeadDEADDEaD"
_BURN_ADDR_PADDED = _BURN_ADDRESS[2:].lower().zfill(64)
_BURN_ADDR_TOPIC = "0x" + _BURN_ADDR_PADDED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pad_address(addr: str) -> str:
    """Zero-pad an address to 32 bytes for ABI encoding."""
    return addr[2:].lower().zfill(64)


def _decode_uint256(hex_str: str) -> int:
    """Decode a single uint256 from a hex string (with or without 0x prefix)."""
    raw = hex_str[2:] if hex_str.startswith("0x") else hex_str
    if not raw:
        return 0
    return int(raw[:64], 16)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OCMClient:
    """Fetches Onchain Monsters data from Ethereum mainnet RPC.

    All public RPC calls are serialized (no concurrent requests) to
    respect rate limits on free endpoints.

    Parameters
    ----------
    rpc_url:
        Ethereum mainnet JSON-RPC endpoint.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  If not provided
        one is created internally and closed on ``close()``.
    """

    def __init__(
        self,
        rpc_url: str = _RPC_URL,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._rpc_url = rpc_url
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._request_id = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> OCMClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: retry helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(
        self, url: str, json_body: dict[str, Any]
    ) -> httpx.Response:
        """POST with exponential-backoff retries on transient failures."""
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.post(url, json=json_body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.StreamError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_SECONDS[attempt]
                    logger.debug(
                        "POST %s failed (attempt %d/%d): %s -- retrying in %.1fs",
                        url,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.debug(
                        "POST %s failed after %d attempts: %s",
                        url,
                        _MAX_RETRIES,
                        exc,
                    )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Internal: RPC primitives
    # ------------------------------------------------------------------

    async def _rpc(self, method: str, params: list) -> Any:
        """Send a JSON-RPC request with retry.

        Returns the ``result`` field from the JSON-RPC response.
        Raises ``RuntimeError`` on JSON-RPC error responses.
        """
        # Throttle consecutive calls to avoid 429s on free RPCs
        if self._request_id > 0:
            await asyncio.sleep(_INTER_CALL_DELAY)
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        resp = await self._post_with_retry(self._rpc_url, payload)
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"RPC error: {body['error']}")
        return body.get("result", "0x")

    async def _eth_call(self, to: str, data: str, block: str = "latest") -> str:
        """Execute a read-only ``eth_call`` via JSON-RPC."""
        return await self._rpc("eth_call", [{"to": to, "data": data}, block])

    async def _eth_block_number(self) -> int:
        """Get the current block number."""
        result = await self._rpc("eth_blockNumber", [])
        return int(result, 16)

    async def _eth_get_block_timestamp(self, block_num: int) -> int:
        """Get the timestamp of a block (unix seconds)."""
        result = await self._rpc(
            "eth_getBlockByNumber", [hex(block_num), False]
        )
        return int(result["timestamp"], 16)

    async def _eth_get_logs(
        self,
        address: str,
        topics: list,
        from_block: int,
        to_block: int | str = "latest",
    ) -> list:
        """Fetch event logs via ``eth_getLogs``."""
        fb = hex(from_block)
        tb = hex(to_block) if isinstance(to_block, int) else to_block
        return await self._rpc(
            "eth_getLogs",
            [
                {
                    "address": address,
                    "topics": topics,
                    "fromBlock": fb,
                    "toBlock": tb,
                }
            ],
        )

    # ------------------------------------------------------------------
    # Public API: fetch_snapshot
    # ------------------------------------------------------------------

    async def fetch_snapshot(self) -> OCMSnapshot:
        """Fetch all Onchain Monsters data and return an OCMSnapshot.

        All RPC calls are serialized (one after another) to respect rate
        limits on free Ethereum RPC endpoints.
        """
        now = time.time()

        # 1. NFT totalSupply
        total_supply = await self._safe_read_uint(
            _NFT_ADDRESS, _SEL_TOTAL_SUPPLY, "NFT totalSupply"
        )

        # 2. NFT currentMintingCost (raw wei of OCMD)
        current_minting_cost = await self._safe_read_uint(
            _NFT_ADDRESS, _SEL_CURRENT_MINTING_COST, "currentMintingCost"
        )

        # 3. OCMD totalSupply (wei -> float)
        ocmd_total_supply_wei = await self._safe_read_uint(
            _OCMD_ADDRESS, _SEL_TOTAL_SUPPLY, "OCMD totalSupply"
        )
        ocmd_total_supply = ocmd_total_supply_wei / _WEI

        # 4. NFTs held by OCMD contract = staked count
        total_staked = await self._safe_read_uint(
            _NFT_ADDRESS,
            f"{_SEL_BALANCE_OF}{_pad_address(_OCMD_ADDRESS)}",
            "NFT balanceOf(OCMD)",
        )

        # 5. Faucet isClosed
        faucet_closed_raw = await self._safe_read_uint(
            _FAUCET_ADDRESS, _SEL_IS_CLOSED, "isClosed"
        )
        faucet_open = faucet_closed_raw == 0

        # 6. NFTs held by burn address = total burned count
        total_burned = await self._safe_read_uint(
            _NFT_ADDRESS,
            f"{_SEL_BALANCE_OF}{_pad_address(_BURN_ADDRESS)}",
            "NFT balanceOf(burn address)",
        )

        # 7. Get current block number
        try:
            current_block = await self._eth_block_number()
        except Exception as exc:
            logger.debug("Failed to get block number: %s", exc)
            current_block = 0

        # 7-9. Scan recent blocks for Transfer events and classify
        recent_events: list[OCMActivityEvent] = []
        if current_block > 0:
            recent_events, _recent_burns = await self._scan_recent_activity(
                current_block, block_range=500
            )

        # 10. Build derived stats and snapshot
        max_supply = 10_000
        net_supply = total_supply - total_burned
        remaining = max(0, max_supply - total_supply)
        minted_pct = (total_supply / max_supply * 100) if max_supply > 0 else 0.0

        collection = OCMCollectionStats(
            total_supply=total_supply,
            max_supply=max_supply,
            current_minting_cost=current_minting_cost,
            burned_count=total_burned,
            net_supply=net_supply,
            remaining=remaining,
            minted_pct=minted_pct,
        )

        # Staking-derived fields
        # daily_emission: each staked NFT earns 1 OCMD/day
        daily_emission = float(total_staked) * 1.0
        staking_ratio = (
            (total_staked / net_supply * 100) if net_supply > 0 else 0.0
        )
        # days_to_earn_mint: how many days of staking 1 NFT to afford mint cost
        mint_cost_ocmd = current_minting_cost / _WEI if current_minting_cost > 0 else 0.0
        days_to_earn_mint = mint_cost_ocmd / 1.0 if mint_cost_ocmd > 0 else 0.0

        staking = OCMStakingStats(
            total_staked=total_staked,
            ocmd_total_supply=ocmd_total_supply,
            daily_emission=daily_emission,
            staking_ratio=staking_ratio,
            days_to_earn_mint=days_to_earn_mint,
        )

        # TODO: holder_count requires scanning full Transfer history which is
        # too expensive for every poll. Set to 0 here; the manager will handle
        # this with caching.
        holder_count = 0

        return OCMSnapshot(
            fetched_at=now,
            collection=collection,
            staking=staking,
            holder_count=holder_count,
            faucet_open=faucet_open,
            recent_events=recent_events,
        )

    # ------------------------------------------------------------------
    # Internal: safe uint256 reader
    # ------------------------------------------------------------------

    async def _safe_read_uint(
        self, contract: str, calldata: str, label: str
    ) -> int:
        """Read a single uint256 from a contract, returning 0 on failure."""
        try:
            raw = await self._eth_call(contract, calldata)
            return _decode_uint256(raw)
        except Exception as exc:
            logger.debug("Failed to read %s: %s", label, exc)
            return 0

    # ------------------------------------------------------------------
    # Internal: recent activity scanning
    # ------------------------------------------------------------------

    async def _scan_recent_activity(
        self, current_block: int, block_range: int = 500
    ) -> tuple[list[OCMActivityEvent], int]:
        """Scan recent blocks for NFT Transfer events and classify them.

        Returns (events, burned_count_in_range).

        Classification rules based on ERC-721 Transfer(from, to, tokenId):
        - from == 0x0  -> mint
        - to   == 0x0  -> burn
        - to   == OCMD -> stake
        - from == OCMD -> unstake
        """
        from_block = max(0, current_block - block_range)

        try:
            logs = await self._eth_get_logs(
                address=_NFT_ADDRESS,
                topics=[_TRANSFER_TOPIC],
                from_block=from_block,
            )
        except Exception as exc:
            logger.debug("Failed to fetch Transfer logs: %s", exc)
            return [], 0

        # First pass: classify each log entry
        raw_events: list[dict[str, Any]] = []
        burned_count = 0

        for log in logs:
            try:
                topics = log.get("topics", [])
                if len(topics) < 4:
                    continue

                tx_hash = log.get("transactionHash", "0x")
                block_num = int(log.get("blockNumber", "0x0"), 16)

                from_topic = topics[1].lower()
                to_topic = topics[2].lower()
                token_id = int(topics[3], 16)

                from_addr = "0x" + from_topic[-40:]
                to_addr = "0x" + to_topic[-40:]

                # Classify event type
                if from_topic == _ZERO_ADDR_TOPIC:
                    event_type = "mint"
                    actor = to_addr
                elif to_topic == _ZERO_ADDR_TOPIC or to_topic == _BURN_ADDR_TOPIC:
                    event_type = "burn"
                    actor = from_addr
                    burned_count += 1
                elif to_topic == _OCMD_ADDR_TOPIC:
                    event_type = "stake"
                    actor = from_addr
                elif from_topic == _OCMD_ADDR_TOPIC:
                    event_type = "unstake"
                    actor = to_addr
                else:
                    # Plain transfer -- skip for activity feed
                    continue

                raw_events.append(
                    {
                        "tx_hash": tx_hash,
                        "block_number": block_num,
                        "event_type": event_type,
                        "actor_address": actor,
                        "token_id": token_id,
                    }
                )
            except (ValueError, IndexError, KeyError) as exc:
                logger.debug("Skipping malformed Transfer log: %s", exc)

        # Group stake/unstake by tx_hash to get count per transaction
        tx_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        single_events: list[dict[str, Any]] = []

        for evt in raw_events:
            if evt["event_type"] in ("stake", "unstake"):
                tx_groups[evt["tx_hash"]].append(evt)
            else:
                single_events.append(evt)

        # Build activity events
        events: list[OCMActivityEvent] = []

        # Single events (mint, burn) -- one per log entry
        for evt in single_events:
            events.append(
                OCMActivityEvent(
                    tx_hash=evt["tx_hash"],
                    block_number=evt["block_number"],
                    timestamp=evt["block_number"],  # placeholder, resolved below
                    event_type=evt["event_type"],
                    actor_address=evt["actor_address"],
                    token_id=evt["token_id"],
                    count=1,
                )
            )

        # Grouped events (stake, unstake) -- one per tx_hash with count
        for tx_hash, group in tx_groups.items():
            first = group[0]
            events.append(
                OCMActivityEvent(
                    tx_hash=tx_hash,
                    block_number=first["block_number"],
                    timestamp=first["block_number"],  # placeholder, resolved below
                    event_type=first["event_type"],
                    actor_address=first["actor_address"],
                    token_id=first["token_id"] if len(group) == 1 else None,
                    count=len(group),
                )
            )

        # Estimate timestamps from block numbers to avoid hundreds of RPC calls.
        # Fetch the current block's timestamp as anchor, then extrapolate
        # using Ethereum's ~12s block time for older blocks.
        now_ts = int(time.time())
        anchor_block = current_block
        anchor_ts = now_ts
        try:
            anchor_ts = await self._eth_get_block_timestamp(current_block)
        except Exception:
            pass

        block_ts: dict[int, int] = {}
        for bn in {e.block_number for e in events}:
            block_ts[bn] = max(0, anchor_ts - (anchor_block - bn) * 12)

        # Rebuild with estimated timestamps (models are frozen, use model_copy)
        events = [
            e.model_copy(
                update={"timestamp": block_ts.get(e.block_number, 0)}
            )
            for e in events
        ]

        # Sort by block number descending (newest first)
        events.sort(key=lambda e: e.block_number, reverse=True)

        return events, burned_count
