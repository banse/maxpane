"""Async HTTP client for Cat Town Fishing data from Base chain RPC.

Read-only -- fetches game state via eth_call and eth_getLogs.
Uses httpx.AsyncClient with exponential-backoff retries, matching the
pattern established by the FrenPet client.
"""

from __future__ import annotations

import asyncio
import logging
import os
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
from maxpane_dashboard.data.evm_abi import (
    decode_uint256 as _decode_uint256,
    pad_address as _pad_address,
)
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES as _ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 15.0
_WEI = 10**18

#: Minimum gap between JSON-RPC calls from one client instance. Cat Town
#: issues its reads serially, and unpaced bursts are what earn the 429s.
_INTER_CALL_DELAY = 0.12

#: Base produces a block every 2 seconds. Used only to estimate the wall-clock
#: time of a block we could not fetch this cycle.
_BASE_BLOCK_SECONDS = 2.0

#: Per-refresh budget for eth_getBlockByNumber lookups, and the lifetime size
#: of the block -> timestamp memo. The budget keeps a cold start well inside
#: the 30s poll interval; the memo means later refreshes need almost none.
_MAX_BLOCK_TS_LOOKUPS = 12
_BLOCK_TS_CACHE_MAX = 2048

#: JSON-RPC error-message fragments that mean "this endpoint won't serve this",
#: not "this request is malformed". Matched on the message, never the code:
#: providers reuse codes freely, so classifying on the code turns a per-host
#: capability limit into a terminal failure and the fallback chain is skipped.
_ENDPOINT_LIMITATION_PATTERNS = (
    "rate limit",
    "ratelimit",
    "too many requests",
    "exceeded",
    "quota",
    "capacity",
    "throttl",
    "block range",
    "query returned more than",
    "method not found",
    "method not supported",
    "unsupported method",
    "not available",
    "unauthorized",
    "forbidden",
)

#: Public Base endpoints tried in order when the primary refuses. Keyless by
#: policy -- every MaxPane dashboard must run without API keys. These are not
#: probe-verified the way ttt_client's pool is (see its _ENDPOINT_PROBE); a
#: dud simply costs one rotation step, so the pool is strictly better than the
#: single hardcoded host it replaces. Probe and prune when convenient.
_FALLBACK_RPCS = [
    "https://base.llamarpc.com",
    "https://base-rpc.publicnode.com",
    "https://base.drpc.org",
]


class _EndpointDead(httpx.HTTPError):
    """The endpoint is blocking or broken -- rotate, don't retry.

    Subclasses ``httpx.HTTPError`` so any caller that only catches httpx
    errors still degrades the way it always did.
    """


def _looks_like_endpoint_limitation(err: Any) -> bool:
    """True if a JSON-RPC error body reads as "this endpoint can't"."""
    if not isinstance(err, dict):
        return False
    message = str(err.get("message") or "").lower()
    return any(frag in message for frag in _ENDPOINT_LIMITATION_PATTERNS)

# ---------------------------------------------------------------------------
# Function selectors (first 4 bytes of keccak256 hash)
# ---------------------------------------------------------------------------

# ERC-20
_SEL_TOTAL_SUPPLY = "0x18160ddd"
_SEL_BALANCE_OF = "0x70a08231"

# Sushi V2 Pair
_SEL_GET_RESERVES = "0x0902f1ac"

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


class CatTownClient(OwnedHttpClient):
    """Fetches Cat Town Fishing data from Base chain RPC.

    Parameters
    ----------
    rpc_url:
        Primary Base mainnet JSON-RPC endpoint. Overridable per deployment
        via the ``MAXPANE_BASE_RPC_URL`` environment variable.
    fallback_rpcs:
        Endpoints tried, in order, when the primary is down or blocking us.
        Without these a single outage at ``mainnet.base.org`` bricked the
        whole dashboard for the session.
    inter_call_delay:
        Minimum seconds between JSON-RPC calls from this instance. Cat Town's
        reads are serial and unpaced bursts are what earn the 429s. Tests pass
        ``0.0``.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  If not provided
        one is created internally and closed on ``close()``.
    """

    RPC_URL = os.environ.get("MAXPANE_BASE_RPC_URL", "https://mainnet.base.org")

    # Contract addresses
    KIBBLE_TOKEN = "0x64cc19A52f4D631eF5BE07947CABA14aE00c52Eb"
    # Deployed and referenced by the cat.town frontend, but NOT a Chainlink
    # aggregator: live eth_call on Base returns "execution reverted" for both
    # latestRoundData() (0xfeaf968c) and decimals() (0x313ce567), re-verified
    # 2026-07-30. Nothing in this client reads it -- the KIBBLE price comes
    # from DEX_POOL reserves. Do not wire it up as a price source without
    # first establishing what its actual interface is.
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
        fallback_rpcs: list[str] | None = None,
        inter_call_delay: float = _INTER_CALL_DELAY,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._rpc_url = rpc_url
        self._fallback_rpcs = list(
            _FALLBACK_RPCS if fallback_rpcs is None else fallback_rpcs
        )
        # Never try the primary twice in one rotation.
        self._fallback_rpcs = [u for u in self._fallback_rpcs if u != rpc_url]
        self._inter_call_delay = inter_call_delay
        self._last_rpc_at: float = 0.0
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._request_id = 0
        #: block number -> unix timestamp. Blocks are immutable, so this is
        #: valid for the lifetime of the client. See _resolve_block_timestamps.
        self._block_ts_cache: dict[int, int] = {}

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

    # Lifecycle (close / __aenter__ / __aexit__) comes from OwnedHttpClient.

    # ------------------------------------------------------------------
    # Internal: retry helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(self, url: str, json_body: dict[str, Any]) -> httpx.Response:
        """POST with exponential-backoff retries on transient failures.

        Raises ``_EndpointDead`` -- not the underlying ``HTTPStatusError`` --
        when the status says the host itself is blocking or broken, so the
        caller rotates to the next endpoint instead of burning the ladder.
        """
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.post(url, json=json_body)
                if resp.status_code in _ENDPOINT_DEAD_CODES:
                    raise _EndpointDead(f"{url} returned {resp.status_code}")
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except _EndpointDead:
                # Not transient: retrying this host just wastes the ladder.
                raise
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

    async def _throttle(self) -> None:
        """Space consecutive JSON-RPC calls by ``_inter_call_delay``."""
        if self._inter_call_delay <= 0:
            return
        self._last_rpc_at = await pace(self._last_rpc_at, self._inter_call_delay)

    # ------------------------------------------------------------------
    # Internal: RPC primitives
    # ------------------------------------------------------------------

    async def _rpc(self, method: str, params: list) -> Any:
        """Send a JSON-RPC request with throttle, retry and endpoint rotation.

        Returns the ``result`` field from the JSON-RPC response. Raises
        ``RuntimeError`` if every endpoint fails, or immediately on a genuine
        JSON-RPC error (a reverted call is the contract's answer, not the
        endpoint's fault -- rotating on it would triple the request count for
        no gain).
        """
        await self._throttle()

        self._request_id += 1
        payload = jsonrpc_payload(self._request_id, method, params)

        last_err: BaseException | None = None
        for url in [self._rpc_url, *self._fallback_rpcs]:
            try:
                resp = await self._post_with_retry(url, payload)
            except _EndpointDead as exc:
                last_err = exc
                logger.debug("RPC endpoint %s is refusing us: %s", url, exc)
                continue
            except (httpx.HTTPError, httpx.StreamError) as exc:
                last_err = exc
                continue

            try:
                body = resp.json()
            except ValueError as exc:
                # HTTP 200 carrying an HTML challenge or proxy error page.
                last_err = RuntimeError(f"RPC {url} returned a non-JSON body: {exc}")
                continue
            if not isinstance(body, dict):
                last_err = RuntimeError(
                    f"RPC {url} returned a non-object body: {type(body).__name__}"
                )
                continue
            if "error" in body:
                err = body["error"]
                if _looks_like_endpoint_limitation(err):
                    last_err = RuntimeError(f"RPC {url} error: {err}")
                    continue
                raise RuntimeError(f"RPC error: {err}")
            return body.get("result", "0x")

        raise RuntimeError(
            f"{method} failed on all {1 + len(self._fallback_rpcs)} endpoint(s): "
            f"{last_err}"
        )

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

    def _estimate_block_timestamp(
        self, block_num: int, current_block: int, now: float
    ) -> int:
        """Approximate a block's wall-clock time from Base's fixed block time.

        Used only when the real timestamp is unavailable this cycle. Costs no
        RPC call and lands within seconds of the truth, whereas the previous
        fallback (timestamp = block number) rendered as a 1971 date.
        """
        behind = max(0, current_block - block_num)
        return int(now - behind * _BASE_BLOCK_SECONDS)

    async def _resolve_block_timestamps(
        self,
        block_numbers: set[int] | list[int],
        *,
        current_block: int,
        now: float | None = None,
    ) -> dict[int, int]:
        """Map block number -> unix timestamp, memoized and budgeted.

        Three properties matter here, all of them load-bearing for the 30s
        refresh loop (the screen runs it with ``exclusive=True``, so a refresh
        that outlives the poll interval is cancelled by the next tick and the
        dashboard never updates again):

        1. **Memoized across refreshes.** Blocks are immutable, so a resolved
           timestamp is cached on the client for its lifetime. Steady-state
           refreshes only look up blocks mined since the last poll.
        2. **Budgeted.** At most ``_MAX_BLOCK_TS_LOOKUPS`` uncached blocks are
           fetched per call, newest first. A cold start over a 5000-block
           window sees dozens of unique blocks; serial lookups of all of them
           against a rate-limited public RPC is exactly the freeze.
        3. **Fails fast.** The first failed lookup abandons the rest of the
           budget -- if the endpoint is refusing us, the remaining calls would
           each burn the full retry ladder for nothing.

        Anything left unresolved is estimated from the block height, never set
        to the block number.
        """
        now = time.time() if now is None else now
        requested = list(block_numbers)
        resolved: dict[int, int] = {}
        missing: list[int] = []

        for bn in requested:
            cached = self._block_ts_cache.get(bn)
            if cached is not None:
                resolved[bn] = cached
            else:
                missing.append(bn)

        # Newest blocks first: those are the ones at the top of the feed.
        for bn in sorted(set(missing), reverse=True)[:_MAX_BLOCK_TS_LOOKUPS]:
            try:
                ts = await self._eth_get_block_timestamp(bn)
            except Exception as exc:
                logger.debug(
                    "Block timestamp lookup failed at block %d; estimating the "
                    "rest of this cycle: %s",
                    bn,
                    exc,
                )
                break
            self._block_ts_cache[bn] = ts
            resolved[bn] = ts

        self._trim_block_ts_cache()

        for bn in requested:
            if bn not in resolved:
                resolved[bn] = self._estimate_block_timestamp(bn, current_block, now)
        return resolved

    def _trim_block_ts_cache(self) -> None:
        """Bound the memo so a long-running session can't grow without limit."""
        overflow = len(self._block_ts_cache) - _BLOCK_TS_CACHE_MAX
        if overflow <= 0:
            return
        # Oldest blocks are the least likely to appear in a recent-events feed.
        for bn in sorted(self._block_ts_cache)[:overflow]:
            del self._block_ts_cache[bn]

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

    async def get_kibble_price_eth(self) -> float:
        """Get the KIBBLE price **denominated in ETH** from DEX pool reserves.

        Calls ``getReserves()`` on the SushiSwap V2 pool. Verified on Base:
        ``token0()`` is WETH (0x4200...0006) and ``token1()`` is KIBBLE, so
        ``reserve0 / reserve1`` is WETH per KIBBLE -- an ETH price, on the
        order of 1e-7. It is *not* USD, and no ETH/USD conversion happens
        anywhere in the Cat Town data layer; every field carrying this value
        is named ``*_eth`` for that reason.

        There is deliberately no oracle fallback. ``KIBBLE_ORACLE`` is not a
        Chainlink aggregator (see the note on the constant), so the former
        fallback could only ever raise, and it would have returned USD if it
        had worked -- a silent unit switch on the degraded path.

        Returns ``0.0`` when the pool read fails or the pool is empty.
        Callers must treat ``0.0`` as "unknown", never as a real price.
        """
        try:
            hex_result = await self._eth_call(self.DEX_POOL, _SEL_GET_RESERVES)
            raw = hex_result[2:] if hex_result.startswith("0x") else hex_result
            if len(raw) >= 128:
                reserve0 = int(raw[0:64], 16)   # WETH (18 decimals)
                reserve1 = int(raw[64:128], 16)  # KIBBLE (18 decimals)
                if reserve1 > 0:
                    return reserve0 / reserve1
            logger.warning(
                "KIBBLE price unavailable: DEX pool returned no usable reserves "
                "(%d hex chars); reporting 0.0",
                len(raw),
            )
        except Exception as exc:
            logger.warning("KIBBLE price unavailable: DEX getReserves failed: %s", exc)

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
            price_eth = await self.get_kibble_price_eth()
        except Exception:
            price_eth = 0.0

        return KibbleEconomy.from_raw(
            price_eth=price_eth,
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

        # Resolve block timestamps for all unique blocks. Memoized and
        # budgeted -- see _resolve_block_timestamps.
        block_ts = await self._resolve_block_timestamps(
            {c.block_number for c in catches},
            current_block=current_block,
        )

        # Rebuild with real timestamps (FishCatch is frozen)
        catches = [
            c.model_copy(update={"timestamp": block_ts[c.block_number]})
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
                price_eth=0.0,
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
