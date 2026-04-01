"""Async HTTP client for Cat Town Fishing data from Base chain RPC.

Read-only -- fetches game state via eth_call and eth_getLogs.
Uses httpx.AsyncClient with exponential-backoff retries, matching the
pattern established by the FrenPet client.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from maxpane_dashboard.data.cattown_models import (
    CatTownSnapshot,
    CompetitionEntry,
    CompetitionState,
    FishCatch,
    KibbleEconomy,
    StakingState,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 15.0
_WEI = 10**18

# ---------------------------------------------------------------------------
# Function selectors (first 4 bytes of keccak256 hash)
# ---------------------------------------------------------------------------

# ERC-20
_SEL_TOTAL_SUPPLY = "0x18160ddd"
_SEL_BALANCE_OF = "0x70a08231"

# Sushi V2 Pair
_SEL_GET_RESERVES = "0x0902f1ac"

# Kibble Oracle (Chainlink-style)
_SEL_LATEST_ROUND_DATA = "0xfeaf968c"
_SEL_DECIMALS = "0x313ce567"

# Competition contract (keccak256 selectors verified via web3_sha3)
_SEL_CURRENT_COMPETITION = "0x0b34ec22"  # currentCompetition()
_SEL_GET_CURRENT_COMPETITION = "0x37f0c78a"  # getCurrentCompetition()
_SEL_GET_LEADERBOARD = "0x6d763a6e"  # getLeaderboard()
_SEL_IS_COMPETITION_ACTIVE = "0x444c3d9a"  # isCompetitionActive()
_SEL_LEADERBOARD_ENTRY = "0xbf368399"  # leaderboard(uint256)

# Revenue Share contract (keccak256 selectors verified via web3_sha3)
_SEL_TOTAL_STAKED = "0x817b1cd2"  # totalStaked()
_SEL_GET_TOTAL_STAKED = "0x0917e776"  # getTotalStaked()
_SEL_ACC_REWARD_PER_SHARE = "0x939d6237"  # accRewardPerShare()

# Event topic hashes (keccak256 of event signatures, verified via web3_sha3)
_FISH_CAUGHT_TOPIC_FISHING = (
    "0xbdd7fb12f889937eb75677706f3b6d43e42635923d7efd45cfb490483331b581"
)
_COMP_CATCH_TOPIC = (
    "0xdcbebda4e44cbfcade8939a17d7b0731453f819d89f24b4244f5f8ad1c645258"
)
_TREASURE_FOUND_TOPIC = (
    "0x3d65ec52ab7c01000be60a6f93b8f7840a5bb35127fe6f1edf48973392855a40"
)


def _pad_address(addr: str) -> str:
    """Zero-pad an address to 32 bytes for ABI encoding."""
    return addr[2:].lower().zfill(64)


def _decode_uint256(hex_str: str) -> int:
    """Decode a single uint256 from a hex string (with or without 0x prefix)."""
    raw = hex_str[2:] if hex_str.startswith("0x") else hex_str
    if not raw:
        return 0
    return int(raw[:64], 16)


class CatTownClient:
    """Fetches Cat Town Fishing data from Base chain RPC.

    Parameters
    ----------
    rpc_url:
        Base mainnet JSON-RPC endpoint.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  If not provided
        one is created internally and closed on ``close()``.
    """

    RPC_URL = "https://mainnet.base.org"

    # Contract addresses
    KIBBLE_TOKEN = "0x64cc19A52f4D631eF5BE07947CABA14aE00c52Eb"
    KIBBLE_ORACLE = "0xE97B7ab01837A4CbF8C332181A2048EEE4033FB7"
    FISHING_GAME = "0xC05Dde2e6E4c5E13E3f78B6Cb4436CFEf6d7AbD3"
    COMPETITION = "0x62a8F851AEB7d333e07445E59457eD150CEE2B7a"
    REVENUE_SHARE = "0x9e1Ced3b5130EBfff428eE0Ff471e4Df5383C0a1"
    DEX_POOL = "0x8e93c90503391427bff2a945b990c2192c0de6cf"
    BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"
    BASENAME_API = "https://api.cat.town/v1/basename"
    COMPETITION_API = "https://api.cat.town/v1/fishing/competition"
    RAFFLE_API = "https://api.cat.town/v1/tickets/leaderboard"

    def __init__(
        self,
        rpc_url: str = RPC_URL,
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

    # ------------------------------------------------------------------
    # Public API: Raffle data
    # ------------------------------------------------------------------

    async def get_raffle_total_tickets(self) -> int:
        """Get total raffle tickets sold this round from cat.town API."""
        resp = await self._client.get(self.RAFFLE_API, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("totalTickets", 0)

    # ------------------------------------------------------------------
    # Public API: Basename resolution
    # ------------------------------------------------------------------

    async def resolve_basenames(self, addresses: list[str]) -> dict[str, str | None]:
        """Resolve Basenames (*.base.eth) for a list of addresses.

        Returns a dict mapping address -> display name (basename without
        .base.eth suffix, or None if no basename registered).
        """
        result: dict[str, str | None] = {}
        for addr in addresses:
            try:
                resp = await self._client.get(
                    f"{self.BASENAME_API}/{addr}",
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    basename = data.get("basename")
                    if basename:
                        # Strip .base.eth or .eth suffix for display
                        display = basename
                        for suffix in (".base.eth", ".eth"):
                            if display.endswith(suffix):
                                display = display[: -len(suffix)]
                                break
                        result[addr.lower()] = display
                    else:
                        result[addr.lower()] = None
                else:
                    result[addr.lower()] = None
            except Exception:
                result[addr.lower()] = None
        return result

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> CatTownClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: retry helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(self, url: str, json_body: dict[str, Any]) -> httpx.Response:
        """POST with exponential-backoff retries on transient failures."""
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.post(url, json=json_body)
                if resp.status_code >= 500:
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
        """Execute a read-only ``eth_call`` via JSON-RPC.

        Returns the hex-encoded result string (with ``0x`` prefix).
        """
        return await self._rpc("eth_call", [{"to": to, "data": data}, block])

    async def _eth_block_number(self) -> int:
        """Get the current block number."""
        result = await self._rpc("eth_blockNumber", [])
        return int(result, 16)

    async def _eth_get_block_timestamp(self, block_num: int) -> int:
        """Get the timestamp of a block (unix seconds)."""
        result = await self._rpc("eth_getBlockByNumber", [hex(block_num), False])
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
            [{"address": address, "topics": topics, "fromBlock": fb, "toBlock": tb}],
        )

    # ------------------------------------------------------------------
    # Public API: KIBBLE token reads
    # ------------------------------------------------------------------

    async def get_kibble_price(self) -> float:
        """Get KIBBLE price in ETH from DEX pool reserves.

        Calls ``getReserves()`` on the SushiSwap V2 pool.
        token0 = WETH, token1 = KIBBLE.
        Price in ETH = reserve0 / reserve1.

        Falls back to the KIBBLE oracle (Chainlink-style) if the DEX
        call fails.
        """
        # Try DEX pool first
        try:
            hex_result = await self._eth_call(self.DEX_POOL, _SEL_GET_RESERVES)
            raw = hex_result[2:] if hex_result.startswith("0x") else hex_result
            if len(raw) >= 128:
                reserve0 = int(raw[0:64], 16)   # WETH (18 decimals)
                reserve1 = int(raw[64:128], 16)  # KIBBLE (18 decimals)
                if reserve1 > 0:
                    return reserve0 / reserve1
        except Exception as exc:
            logger.debug("DEX pool getReserves failed: %s", exc)

        # Fallback: oracle latestRoundData
        try:
            hex_result = await self._eth_call(self.KIBBLE_ORACLE, _SEL_LATEST_ROUND_DATA)
            raw = hex_result[2:] if hex_result.startswith("0x") else hex_result
            if len(raw) >= 320:
                # answer is the second uint256 (offset 64..128), signed int256
                answer = int(raw[64:128], 16)
                # Get oracle decimals
                dec_result = await self._eth_call(self.KIBBLE_ORACLE, _SEL_DECIMALS)
                dec_raw = dec_result[2:] if dec_result.startswith("0x") else dec_result
                decimals = int(dec_raw[:64], 16) if dec_raw else 8
                return answer / (10 ** decimals)
        except Exception as exc:
            logger.debug("KIBBLE oracle fallback failed: %s", exc)

        return 0.0

    async def get_kibble_stats(self) -> KibbleEconomy:
        """Get KIBBLE token economy stats: totalSupply, burned, staked, price.

        Calls are issued in parallel with ``asyncio.gather``.
        """
        # Serialize calls to avoid public RPC rate limits
        try:
            total_supply_raw = await self._eth_call(self.KIBBLE_TOKEN, _SEL_TOTAL_SUPPLY)
            total_supply_wei = _decode_uint256(total_supply_raw)
        except Exception:
            total_supply_wei = 0

        try:
            burned_raw = await self._eth_call(
                self.KIBBLE_TOKEN,
                f"{_SEL_BALANCE_OF}{_pad_address(self.BURN_ADDRESS)}",
            )
            burned_wei = _decode_uint256(burned_raw)
        except Exception:
            burned_wei = 0

        try:
            staked_raw = await self._eth_call(self.REVENUE_SHARE, _SEL_TOTAL_STAKED)
            staked_wei = _decode_uint256(staked_raw)
        except Exception:
            staked_wei = 0

        try:
            price = await self.get_kibble_price()
        except Exception:
            price = 0.0

        return KibbleEconomy.from_raw(
            price_usd=price,
            total_supply_wei=total_supply_wei,
            burned_wei=burned_wei,
            staked_wei=staked_wei,
        )

    # ------------------------------------------------------------------
    # Public API: Competition reads (cat.town REST API primary, RPC fallback)
    # ------------------------------------------------------------------

    async def get_competition_state(self) -> CompetitionState:
        """Get competition state and leaderboard.

        Primary: cat.town REST API (fast, includes basenames).
        Fallback: onchain RPC reads.
        """
        # Try the cat.town API first -- single HTTP call, no rate limits
        try:
            return await self._get_competition_from_api()
        except Exception as exc:
            logger.debug("cat.town API failed, falling back to RPC: %s", exc)

        return await self._get_competition_from_rpc()

    async def _get_competition_from_api(self) -> CompetitionState:
        """Fetch competition data from cat.town REST API."""
        import time as _time

        resp = await self._client.get(
            f"{self.COMPETITION_API}/leaderboard?_t={int(_time.time() * 1000)}",
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()

        comp = data.get("competition", {})
        start_time = comp.get("startTime", 0)
        end_time = comp.get("endTime", 0)
        total_volume_wei = int(comp.get("prizePool", "0"))
        distributed = comp.get("prizesDistributed", False)
        is_active = comp.get("isActive", False)
        if not is_active:
            is_active = start_time > 0 and _time.time() < end_time and not distributed

        total_volume = total_volume_wei / _WEI
        week_number = int(start_time / (7 * 86400)) if start_time > 0 else 0

        # Parse leaderboard entries (API includes basenames)
        entries: list[CompetitionEntry] = []
        for item in data.get("leaderboard", []):
            rank = item.get("rank", 0)
            player = item.get("player", "")
            size = int(item.get("size", "0"))
            fish_name = item.get("fishName", "Unknown")
            is_shiny = item.get("isShiny", False)
            basename = item.get("basename")

            if size == 0 or not player:
                continue

            # Store basename in fisher_address field as "basename|address"
            # so the manager can split it out
            if basename:
                display = basename
                for suffix in (".base.eth", ".eth"):
                    if display.endswith(suffix):
                        display = display[: -len(suffix)]
                        break
                addr_with_name = f"{display}|{player}"
            else:
                addr_with_name = f"|{player}"

            entries.append(CompetitionEntry(
                fisher_address=addr_with_name,
                fish_weight_kg=size / 1000.0,
                fish_species=fish_name,
                rarity="Shiny" if is_shiny else "Normal",
                rank=rank,
            ))

        # Sort by weight and re-rank
        entries.sort(key=lambda e: e.fish_weight_kg, reverse=True)
        for i, entry in enumerate(entries):
            entries[i] = CompetitionEntry(
                fisher_address=entry.fisher_address,
                fish_weight_kg=entry.fish_weight_kg,
                fish_species=entry.fish_species,
                rarity=entry.rarity,
                rank=i + 1,
            )

        return CompetitionState(
            week_number=week_number,
            is_active=is_active,
            total_volume_kibble=total_volume,
            prize_pool_kibble=total_volume * 0.10,
            treasure_pool_kibble=total_volume * 0.70,
            staker_revenue_kibble=total_volume * 0.10,
            num_participants=len(entries),
            start_time=start_time,
            end_time=end_time,
            entries=entries,
        )

    async def _get_competition_from_rpc(self) -> CompetitionState:
        """Fallback: fetch competition from onchain RPC."""
        # Get competition metadata
        try:
            hex_result = await self._eth_call(
                self.COMPETITION, _SEL_GET_CURRENT_COMPETITION
            )
            raw = hex_result[2:] if hex_result.startswith("0x") else hex_result
        except Exception as exc:
            logger.debug("getCurrentCompetition failed: %s", exc)
            raw = ""

        # Parse: (bytes32 eventId, string name, uint256 startTime,
        #         uint256 endTime, uint256 totalVolume, bool prizesDistributed)
        # Note: the contract field is named "prizePool" in the ABI but it
        # actually holds the total KIBBLE volume (all identification fees).
        # The real prize pool is 10% of that, per the revenue split:
        # 70% treasure, 10% prize pool, 10% stakers, 7.5% treasury, 2.5% burn.
        start_time = 0
        end_time = 0
        total_volume_wei = 0
        is_active = False
        week_number = 0

        if len(raw) >= 384:
            start_time = int(raw[128:192], 16)
            end_time = int(raw[192:256], 16)
            total_volume_wei = int(raw[256:320], 16)
            distributed = int(raw[320:384], 16) != 0
            is_active = start_time > 0 and time.time() < end_time and not distributed
            if start_time > 0:
                week_number = int(start_time / (7 * 86400))

        total_volume = total_volume_wei / _WEI

        # Fetch leaderboard entries
        entries = await self.get_competition_leaderboard()

        return CompetitionState(
            week_number=week_number,
            is_active=is_active,
            total_volume_kibble=total_volume,
            prize_pool_kibble=total_volume * 0.10,
            treasure_pool_kibble=total_volume * 0.70,
            staker_revenue_kibble=total_volume * 0.10,
            num_participants=len(entries),
            start_time=start_time,
            end_time=end_time,
            entries=entries,
        )

    async def get_competition_leaderboard(self) -> list[CompetitionEntry]:
        """Get the full competition leaderboard via getLeaderboard().

        Returns a fixed-size tuple[50] of structs in a single RPC call.
        Each struct: (address player, uint256 size, uint256 timestamp,
        string fishName, uint256 tokenId, bool isShiny).
        """
        try:
            hex_result = await self._eth_call(
                self.COMPETITION, _SEL_GET_LEADERBOARD
            )
            raw = hex_result[2:] if hex_result.startswith("0x") else hex_result
        except Exception as exc:
            logger.debug("getLeaderboard failed: %s", exc)
            return []

        if len(raw) < 128:
            return []

        entries: list[CompetitionEntry] = []
        try:
            # Return is a tuple[50] of structs with dynamic strings.
            # First 64 hex = offset pointer to array data.
            # Then 50 offset pointers (each relative to array start).
            array_offset = int(raw[0:64], 16) * 2  # byte to hex offset

            offsets: list[int] = []
            for i in range(50):
                ptr_start = array_offset + i * 64
                if ptr_start + 64 > len(raw):
                    break
                offsets.append(int(raw[ptr_start : ptr_start + 64], 16))

            for offset in offsets:
                base = array_offset + offset * 2
                if base + 384 > len(raw):
                    break

                player = "0x" + raw[base + 24 : base + 64]
                size = int(raw[base + 64 : base + 128], 16)

                if size == 0 or player == "0x" + "0" * 40:
                    continue

                # fishName: dynamic string, offset pointer at struct slot 3
                name_ptr = int(raw[base + 192 : base + 256], 16) * 2
                name_base = base + name_ptr
                fish_name = "Unknown"
                if name_base + 64 <= len(raw):
                    name_len = int(raw[name_base : name_base + 64], 16)
                    name_hex = raw[name_base + 64 : name_base + 64 + name_len * 2]
                    try:
                        fish_name = bytes.fromhex(name_hex).decode("utf-8", errors="replace")
                    except (ValueError, UnicodeDecodeError):
                        pass

                is_shiny = int(raw[base + 320 : base + 384], 16) != 0

                entries.append(CompetitionEntry(
                    fisher_address=player,
                    fish_weight_kg=size / 1000.0,
                    fish_species=fish_name,
                    rarity="Shiny" if is_shiny else "Normal",
                    rank=0,
                ))
        except (ValueError, IndexError) as exc:
            logger.debug("Error parsing leaderboard: %s", exc)

        # Sort by weight descending and assign ranks
        entries.sort(key=lambda e: e.fish_weight_kg, reverse=True)
        for i, entry in enumerate(entries):
            entries[i] = CompetitionEntry(
                fisher_address=entry.fisher_address,
                fish_weight_kg=entry.fish_weight_kg,
                fish_species=entry.fish_species,
                rarity=entry.rarity,
                rank=i + 1,
            )
        return entries

    # ------------------------------------------------------------------
    # Public API: Recent fish catches (event logs)
    # ------------------------------------------------------------------

    async def get_recent_catches(self, block_range: int = 5000) -> list[FishCatch]:
        """Get recent fish catches AND treasure finds from the Fishing Game.

        Scans the last ``block_range`` blocks for FishCaught and TreasureFound
        events, merges them by block number, and returns newest first.

        FishCaught(address indexed user, uint256 mintedId, string fishName,
                   uint256 weight, uint256 sellValue)
        TreasureFound(address indexed user, uint256 mintedId,
                      string treasureName, uint256 sellValue)
        """
        try:
            current_block = await self._eth_block_number()
        except Exception as exc:
            logger.debug("Failed to get block number: %s", exc)
            return []

        from_block = max(0, current_block - block_range)
        catches: list[FishCatch] = []

        # --- FishCaught events ---
        try:
            fish_logs = await self._eth_get_logs(
                address=self.FISHING_GAME,
                topics=[_FISH_CAUGHT_TOPIC_FISHING],
                from_block=from_block,
            )
        except Exception as exc:
            logger.debug("Failed to fetch FishCaught logs: %s", exc)
            fish_logs = []

        for log in fish_logs:
            try:
                topics = log.get("topics", [])
                data_hex = log.get("data", "0x")[2:]
                tx_hash = log.get("transactionHash", "0x")
                block_num = int(log.get("blockNumber", "0x0"), 16)
                fisher = "0x" + topics[1][-40:] if len(topics) > 1 else "0x" + "0" * 40

                # Data: uint256 mintedId, string fishName, uint256 weight, uint256 sellValue
                if len(data_hex) < 256:
                    continue

                name_offset = int(data_hex[64:128], 16) * 2
                weight = int(data_hex[128:192], 16)

                fish_name = "Unknown"
                if name_offset + 64 <= len(data_hex):
                    name_len = int(data_hex[name_offset : name_offset + 64], 16)
                    name_hex = data_hex[name_offset + 64 : name_offset + 64 + name_len * 2]
                    try:
                        fish_name = bytes.fromhex(name_hex).decode("utf-8", errors="replace")
                    except (ValueError, UnicodeDecodeError):
                        pass

                catches.append(FishCatch(
                    tx_hash=tx_hash,
                    fisher_address=fisher,
                    species=fish_name,
                    weight_kg=weight / 1000.0,
                    rarity="fish",
                    timestamp=block_num,
                    block_number=block_num,
                ))
            except (ValueError, IndexError, KeyError) as exc:
                logger.debug("Skipping malformed FishCaught log: %s", exc)

        # --- TreasureFound events ---
        try:
            treasure_logs = await self._eth_get_logs(
                address=self.FISHING_GAME,
                topics=[_TREASURE_FOUND_TOPIC],
                from_block=from_block,
            )
        except Exception as exc:
            logger.debug("Failed to fetch TreasureFound logs: %s", exc)
            treasure_logs = []

        for log in treasure_logs:
            try:
                topics = log.get("topics", [])
                data_hex = log.get("data", "0x")[2:]
                tx_hash = log.get("transactionHash", "0x")
                block_num = int(log.get("blockNumber", "0x0"), 16)
                fisher = "0x" + topics[1][-40:] if len(topics) > 1 else "0x" + "0" * 40

                # Data: uint256 mintedId, string treasureName, uint256 sellValue
                # (3 non-indexed params, no weight field)
                if len(data_hex) < 192:
                    continue

                name_offset = int(data_hex[64:128], 16) * 2
                sell_value = int(data_hex[128:192], 16)

                treasure_name = "Unknown Treasure"
                if name_offset + 64 <= len(data_hex):
                    name_len = int(data_hex[name_offset : name_offset + 64], 16)
                    name_hex = data_hex[name_offset + 64 : name_offset + 64 + name_len * 2]
                    try:
                        treasure_name = bytes.fromhex(name_hex).decode("utf-8", errors="replace")
                    except (ValueError, UnicodeDecodeError):
                        pass

                catches.append(FishCatch(
                    tx_hash=tx_hash,
                    fisher_address=fisher,
                    species=treasure_name,
                    weight_kg=sell_value / 1e18,  # sell value in wei -> KIBBLE
                    rarity="treasure",
                    timestamp=block_num,
                    block_number=block_num,
                ))
            except (ValueError, IndexError, KeyError) as exc:
                logger.debug("Skipping malformed TreasureFound log: %s", exc)

        # Resolve block timestamps for all unique blocks
        unique_blocks = {c.block_number for c in catches}
        block_ts: dict[int, int] = {}
        for bn in unique_blocks:
            try:
                block_ts[bn] = await self._eth_get_block_timestamp(bn)
            except Exception:
                block_ts[bn] = bn  # fallback to block number

        # Rebuild with real timestamps (FishCatch is frozen)
        catches = [
            c.model_copy(update={"timestamp": block_ts.get(c.block_number, c.block_number)})
            for c in catches
        ]

        # Sort by block number descending (newest first)
        catches.sort(key=lambda c: c.block_number, reverse=True)
        return catches

    # ------------------------------------------------------------------
    # Public API: Staking / Revenue Share
    # ------------------------------------------------------------------

    async def get_staking_state(self) -> StakingState:
        """Get KIBBLE staking state from the Revenue Share contract.

        Reads totalStaked and accRewardPerShare in parallel.
        """
        # Serialize to avoid rate limits.
        # Use totalStaked() which returns wei; getTotalStaked() returns human-scale int.
        try:
            total_raw = await self._eth_call(self.REVENUE_SHARE, _SEL_TOTAL_STAKED)
            total_staked_wei = _decode_uint256(total_raw)
        except Exception:
            total_staked_wei = 0

        try:
            acc_raw = await self._eth_call(self.REVENUE_SHARE, _SEL_ACC_REWARD_PER_SHARE)
            acc_reward = _decode_uint256(acc_raw)
        except Exception:
            acc_reward = 0

        return StakingState.from_raw(
            total_staked_wei=total_staked_wei,
            user_staked_wei=0,  # no user context in read-only mode
            pending_rewards_wei=0,
            weekly_revenue_wei=acc_reward,  # best proxy without historical tracking
        )

    # ------------------------------------------------------------------
    # Orchestrator: unified snapshot
    # ------------------------------------------------------------------

    async def fetch_snapshot(self) -> CatTownSnapshot:
        """Fetch all Cat Town data in parallel and return a CatTownSnapshot.

        Each sub-call is wrapped in try/except for graceful degradation --
        individual failures produce safe defaults rather than crashing the
        entire snapshot.
        """
        now = time.time()

        # Serialize calls to avoid hitting public RPC rate limits.
        # Each sub-call already uses gather internally for its own sub-reads.
        kibble = await self._safe_kibble_stats()
        competition = await self._safe_competition_state()
        catches = await self._safe_recent_catches()
        staking = await self._safe_staking_state()

        return CatTownSnapshot(
            fetched_at=now,
            kibble=kibble,
            competition=competition,
            recent_catches=catches,
            staking=staking,
        )

    # ------------------------------------------------------------------
    # Internal: safe wrappers for snapshot assembly
    # ------------------------------------------------------------------

    async def _safe_kibble_stats(self) -> KibbleEconomy:
        try:
            return await self.get_kibble_stats()
        except Exception as exc:
            logger.debug("Failed to fetch kibble stats: %s", exc)
            return KibbleEconomy(
                price_usd=0.0,
                total_supply=0.0,
                circulating=0.0,
                burned=0.0,
                staked_total=0.0,
                price_change_24h=0.0,
            )

    async def _safe_competition_state(self) -> CompetitionState:
        try:
            return await self.get_competition_state()
        except Exception as exc:
            logger.debug("Failed to fetch competition state: %s", exc)
            return CompetitionState(
                week_number=0,
                is_active=False,
                total_volume_kibble=0.0,
                prize_pool_kibble=0.0,
                treasure_pool_kibble=0.0,
                staker_revenue_kibble=0.0,
                num_participants=0,
                start_time=0,
                end_time=0,
                entries=[],
            )

    async def _safe_recent_catches(self) -> list[FishCatch]:
        try:
            return await self.get_recent_catches()
        except Exception as exc:
            logger.debug("Failed to fetch recent catches: %s", exc)
            return []

    async def _safe_staking_state(self) -> StakingState:
        try:
            return await self.get_staking_state()
        except Exception as exc:
            logger.debug("Failed to fetch staking state: %s", exc)
            return StakingState(
                total_staked=0.0,
                user_staked=0.0,
                pending_rewards=0.0,
                weekly_revenue=0.0,
            )
