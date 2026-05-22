"""Orchestrator for the Ten Thousand Tokens (TTT) dashboard.

Single coordination point between :class:`TTTClient` (RPC + HTTP fetch),
:class:`TTTCache` (persistent state), and the signal analytics in
:mod:`maxpane_dashboard.analytics.ttt_signals`. Exposes one public coroutine,
``fetch_and_compute()``, which returns the flat dict consumed by the widget
layer.

Cycle behaviour (each refresh):

1. Pull factory + FeeSplitter state in one multicall.
2. Incremental event scan (Launched, Deposited, Bought) since
   ``cache.last_seen_block``.
3. For any new tokens, batch-fetch symbol / decimals (once-only).
4. Batch-fetch each launched token's ETH balance (reservoir) via Multicall3.
5. Batch DexScreener for per-token market data.
6. Sample burns + floor into the hourly deques.
7. Compute 24h rolling counters and run signal analytics.
8. Return a flat dict.

The Reservoir floor call is throttled to every second cycle (~60s) and the
ETH/USD price uses the existing :class:`PriceClient` TTL cache (300s).
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.ttt_signals import (
    HOLDER_FEE_SHARE,
    buybacks_ready_signal,
    claim_math_scenarios,
    concentration_signal,
    decay_window_signal,
    fresh_launch_alert,
    top_fee_engines,
)
from maxpane_dashboard.data.price import PriceClient
from maxpane_dashboard.data.ttt_cache import TTTCache
from maxpane_dashboard.data.ttt_client import (
    _DEFAULT_LOG_LOOKBACK_BLOCKS,
    _INCREMENTAL_LOG_LOOKBACK,
    _SCALE,
    _WEI,
    TTTClient,
)

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "ttt_cache.json"

_RESERVOIR_REFRESH_EVERY_N_CYCLES = 2  # ~60s when poll_interval=30


def _safe_call(fn: Any, *args: Any, default: Any = None) -> Any:
    """Call *fn* with *args*, returning *default* on exception."""
    try:
        return fn(*args)
    except Exception as exc:
        logger.debug("Analytics call %s failed: %s", getattr(fn, "__name__", fn), exc)
        return default


def _age_str(launch_block: int, current_block: int) -> str:
    """Human-readable age of a launch (block-delta -> "Nb" or rough time)."""
    blocks = max(0, current_block - launch_block)
    if blocks < 300:
        return f"{blocks}b"
    seconds = blocks * 12  # rough ~12s/block
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


class TTTManager:
    """Pulls TTT data, updates cache, computes analytics, returns flat dict.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    """

    def __init__(self, poll_interval: int = 30) -> None:
        self.client = TTTClient()
        self.price_client = PriceClient()
        self.cache = TTTCache()
        self._poll_interval = poll_interval
        self._cycle_count = 0
        self._error_count = 0
        self._last_floor_eth: float | None = None
        self._last_floor_usd: float | None = None
        self._last_sales_24h: int | None = None

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Run one full refresh cycle and return the flat dashboard dict.

        Idempotent and exception-safe at the per-source level: a network
        failure in one source returns ``None`` / cached values, never raises
        out of this method (modulo a total RPC outage, in which case the
        first multicall raises and ``_error_count`` increments).
        """
        now = time.time()
        self._cycle_count += 1

        # -- 1) Factory + FeeSplitter state and block number in parallel --
        # These have no inter-dependency; run them concurrently so we don't
        # serialize three independent RPCs through _INTER_CALL_DELAY.
        factory_task = asyncio.create_task(self.client.fetch_factory_state())
        block_task = asyncio.create_task(self.client.fetch_block_number())
        try:
            factory = await factory_task
        except Exception as exc:
            self._error_count += 1
            logger.warning("factory state fetch failed: %s", exc)
            factory = {
                "max_supply": 10_000,
                "total_minted": 0,
                "burn_count": 0,
                "active_shares": 10_000,
                "acc_eth_per_share": 0,
            }
        try:
            current_block = await block_task
        except Exception as exc:
            logger.debug("block number fetch failed: %s", exc)
            current_block = 0

        # -- 2) Event scans (incremental) ---------------------------------
        await self._scan_events(current_block, now)

        # -- 3) Token metadata for any newly registered tokens ------------
        await self._fill_missing_metadata()

        # -- 4) Reservoirs (per-token ETH balance) ------------------------
        await self._refresh_reservoirs()

        # -- 5+6+10) Market data + NFT floor + ETH/USD in parallel --------
        # DexScreener, Reservoir, and CoinGecko are independent HTTP origins;
        # run them concurrently to cut total wall time.
        do_floor = (
            self._cycle_count % _RESERVOIR_REFRESH_EVERY_N_CYCLES == 1
        )
        market_task = asyncio.create_task(self._refresh_market_data())
        floor_task = (
            asyncio.create_task(self.client.fetch_nft_floor()) if do_floor else None
        )
        eth_usd_task = asyncio.create_task(self.price_client.get_eth_usd())

        try:
            await market_task
        except Exception as exc:
            logger.debug("market data fetch failed: %s", exc)

        if floor_task is not None:
            try:
                floor = await floor_task
                if floor is not None:
                    self._last_floor_eth = floor.get("floor_eth")
                    self._last_floor_usd = floor.get("floor_usd")
                    self._last_sales_24h = floor.get("sales_24h")
            except Exception as exc:
                logger.debug("floor fetch failed: %s", exc)

        try:
            eth_usd = await eth_usd_task
        except Exception as exc:
            logger.debug("ETH price fetch failed: %s", exc)
            eth_usd = 0.0

        # -- 7) Sample hourly buckets ------------------------------------
        self.cache.sample_burns_and_floor(
            now, factory["burn_count"], self._last_floor_eth
        )

        # -- 8) Prune old + recompute rolling 24h counters ---------------
        self.cache.prune_old(now)
        self.cache.recompute_rolling_counters(now)

        # -- 9) Per-token fee rollup -------------------------------------
        for addr in list(self.cache.tokens.keys()):
            fees_24h, fees_total = self.cache.per_token_fees(addr, now)
            self.cache.update_token_fees(addr, fees_24h, fees_total)

        # -- 11) Analytics ------------------------------------------------
        tokens_list = list(self.cache.tokens.values())
        recent_events = list(self.cache.activity_log)

        from maxpane_dashboard.data.ttt_models import TTTFactoryState

        try:
            burned_pct = (
                factory["burn_count"] / factory["max_supply"] * 100.0
                if factory["max_supply"] > 0
                else 0.0
            )
            # `total_eth_to_holders_wei` is the cumulative 30%-bucket all-time.
            # We don't have a full-history sum on first run, so we approximate
            # as `accETHPerShare * activeShares / SCALE` -- this is the total
            # currently distributable across un-burned NFTs and is the closest
            # numeric we can compute from on-chain state alone.
            total_to_holders_wei = (
                factory["acc_eth_per_share"]
                * max(factory["active_shares"], 0)
                // _SCALE
            )
            factory_state = TTTFactoryState(
                max_supply=factory["max_supply"],
                burn_count=factory["burn_count"],
                total_minted=factory["total_minted"],
                unburned=factory["active_shares"]
                or (factory["max_supply"] - factory["burn_count"]),
                burned_pct=burned_pct,
                acc_eth_per_share=factory["acc_eth_per_share"],
                total_eth_to_holders_wei=total_to_holders_wei,
                current_block=current_block,
            )
        except Exception as exc:
            logger.warning("could not build TTTFactoryState: %s", exc)
            factory_state = None

        eth_to_holders_24h = self.cache.eth_to_holders_24h_wei / _WEI

        if factory_state is not None:
            fresh = _safe_call(
                fresh_launch_alert, recent_events, current_block, now
            )
            br = _safe_call(buybacks_ready_signal, tokens_list, default=None)
            dw = _safe_call(
                decay_window_signal, tokens_list, current_block, default=None
            )
            conc = _safe_call(
                concentration_signal, factory_state, eth_to_holders_24h,
                default=None,
            )
            claims = _safe_call(
                claim_math_scenarios, factory_state, eth_to_holders_24h,
                default=[],
            )
        else:
            fresh = br = dw = conc = None
            claims = []

        # -- 12) Leaderboard + top fee engines ----------------------------
        top_by_vol = sorted(
            tokens_list,
            key=lambda t: (t.volume_usd_h24 or 0.0),
            reverse=True,
        )[:10]
        top_tokens_by_volume = [
            {
                "rank": i + 1,
                "address": t.address,
                "symbol": t.symbol or "???",
                "price_usd": t.price_usd,
                "change_h24": t.price_change_h24,
                "vol_usd_h24": t.volume_usd_h24,
                "mcap_usd": t.market_cap_usd,
                "age_str": _age_str(t.launch_block, current_block),
            }
            for i, t in enumerate(top_by_vol)
        ]

        top_fees = _safe_call(top_fee_engines, tokens_list, 10, default=[])
        top_fee_engines_dicts = [
            {
                "rank": i + 1,
                "address": t.address,
                "symbol": t.symbol or "???",
                "fees_24h_eth": t.fees_eth_24h,
                "fees_lifetime_eth": t.fees_eth_lifetime,
                "fees_per_vol_pct": (
                    (t.fees_eth_24h * eth_usd / t.volume_usd_h24 * 100.0)
                    if (t.volume_usd_h24 or 0) > 0 and eth_usd > 0
                    else 0.0
                ),
            }
            for i, t in enumerate(top_fees)
        ]

        # -- 13) Activity feed (last 25 as dicts) ------------------------
        activity = [e.model_dump() for e in list(self.cache.activity_log)[:25]]

        last_updated_seconds_ago = max(0.0, time.time() - now)

        burns_history = [list(pt) for pt in self.cache.burns_hourly]
        floor_history = [list(pt) for pt in self.cache.floor_hourly]

        def _sig_dump(s: Any) -> dict | None:
            if s is None:
                return None
            try:
                return s.model_dump()
            except Exception:
                return None

        return {
            # Title bar
            "launches": factory["burn_count"],
            "max_supply": factory["max_supply"],
            # Hero metrics
            "unburned": factory_state.unburned if factory_state else factory["max_supply"],
            "burned_pct": factory_state.burned_pct if factory_state else 0.0,
            "launches_24h": self.cache.launches_24h,
            "holder_pool_eth_total": (
                factory_state.total_eth_to_holders_wei / _WEI
                if factory_state
                else 0.0
            ),
            "holder_pool_eth_24h": eth_to_holders_24h,
            "floor_eth": self._last_floor_eth,
            "floor_usd": self._last_floor_usd,
            # Leaderboard
            "top_tokens_by_volume": top_tokens_by_volume,
            # Sparkline
            "burns_history": burns_history,
            "floor_history": floor_history,
            # Signals
            "fresh_launch_signal": _sig_dump(fresh),
            "buybacks_ready_signal": _sig_dump(br) or {
                "label": "Buybacks ready",
                "value_str": "--",
                "indicator": "►",
                "color": "dim",
            },
            "decay_window_signal": _sig_dump(dw) or {
                "label": "Decay window",
                "value_str": "--",
                "indicator": "►",
                "color": "dim",
            },
            "concentration_signal": _sig_dump(conc) or {
                "label": "Concentration",
                "value_str": "--",
                "indicator": "►",
                "color": "dim",
            },
            # Activity feed (last 25)
            "activity_events": activity,
            # Bottom-right α
            "top_fee_engines": top_fee_engines_dicts,
            # Bottom-right γ
            "claim_math_scenarios": claims,
            # Meta
            "eth_usd": eth_usd,
            "current_block": current_block,
            "last_updated_seconds_ago": last_updated_seconds_ago,
            "error_count": self._error_count,
            "poll_interval": self._poll_interval,
            "active_view": "fees",
            # Misc context surfaced for widgets / tests
            "holder_fee_share": HOLDER_FEE_SHARE,
            "sales_24h": self._last_sales_24h,
        }

    def save_cache(self) -> None:
        self.cache.save_to_file(str(_CACHE_FILE))

    async def close(self) -> None:
        self.save_cache()
        await self.client.close()
        await self.price_client.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _scan_events(self, current_block: int, now: float) -> None:
        """Incrementally fetch and apply Launched / Deposited / Bought events."""
        if current_block <= 0:
            return

        # Defaults: on first run, look back a moderate window (NOT full history,
        # which would be many minutes of RPC traffic). Subsequent runs use the
        # tighter incremental window from cache.
        def _from(topic_name: str, default_lookback: int) -> int:
            last = self.cache.last_seen_block.get(topic_name, 0)
            if last <= 0:
                return max(0, current_block - default_lookback)
            return max(0, min(last + 1, current_block - _INCREMENTAL_LOG_LOOKBACK))

        # Launched (factory)
        try:
            fb = _from("Launched", _DEFAULT_LOG_LOOKBACK_BLOCKS)
            launches = await self.client.fetch_launched_events(fb, current_block)
            for ev in launches:
                ts = await self._block_timestamp(ev["block_number"], now, current_block)
                self.cache.apply_launch(
                    token_id=ev["token_id"],
                    address=ev["erc20_address"],
                    launcher=ev["launcher"],
                    block_number=ev["block_number"],
                    timestamp=ts,
                    tx_hash=ev["tx_hash"],
                )
            self.cache.last_seen_block["Launched"] = current_block
        except Exception as exc:
            logger.debug("Launched scan failed: %s", exc)

        # Deposited (FeeSplitter)
        try:
            fb = _from("Deposited", _DEFAULT_LOG_LOOKBACK_BLOCKS)
            deposits = await self.client.fetch_deposit_events(fb, current_block)
            for ev in deposits:
                ts = await self._block_timestamp(ev["block_number"], now, current_block)
                self.cache.apply_deposit(
                    token=ev["token"],
                    sender=ev["sender"],
                    holder_share_wei=ev["holder_share"],
                    total_wei=ev["total"],
                    block_number=ev["block_number"],
                    timestamp=ts,
                    tx_hash=ev["tx_hash"],
                )
            self.cache.last_seen_block["Deposited"] = current_block
        except Exception as exc:
            logger.debug("Deposited scan failed: %s", exc)

        # Bought (per-ERC20). Only scan if we have known tokens.
        known = list(self.cache.tokens.keys())
        if known:
            try:
                fb = _from("Bought", _DEFAULT_LOG_LOOKBACK_BLOCKS)
                # Cap the address list to a sane size to keep RPCs happy
                buys = await self.client.fetch_buyback_events(
                    known[:200], fb, current_block
                )
                for ev in buys:
                    ts = await self._block_timestamp(
                        ev["block_number"], now, current_block
                    )
                    self.cache.apply_buyback(
                        token=ev["token"],
                        caller=ev["caller"],
                        eth_spent_wei=ev["eth_spent"],
                        caller_reward_wei=ev["caller_reward"],
                        block_number=ev["block_number"],
                        timestamp=ts,
                        tx_hash=ev["tx_hash"],
                    )
                self.cache.last_seen_block["Bought"] = current_block
            except Exception as exc:
                logger.debug("Bought scan failed: %s", exc)

    async def _fill_missing_metadata(self) -> None:
        """Fetch symbol/decimals for any token that still has them None."""
        missing = [
            addr for addr, t in self.cache.tokens.items() if not t.symbol
        ]
        if not missing:
            return
        # Cap per-cycle work
        missing = missing[:50]
        try:
            metadata = await self.client.fetch_token_metadata(missing)
        except Exception as exc:
            logger.debug("metadata batch failed: %s", exc)
            return
        for addr, (symbol, decimals) in metadata.items():
            self.cache.update_token_metadata(addr, symbol, decimals)

    async def _refresh_reservoirs(self) -> None:
        """Refresh per-token ETH balances (the buyback reservoirs)."""
        addresses = list(self.cache.tokens.keys())
        if not addresses:
            return
        # Multicall comfortably handles 200 in one tx; chunk above that.
        chunks = [addresses[i : i + 200] for i in range(0, len(addresses), 200)]
        for chunk in chunks:
            try:
                balances = await self.client.fetch_token_reservoirs(chunk)
            except Exception as exc:
                logger.debug("reservoir batch failed: %s", exc)
                continue
            for addr, wei in balances.items():
                self.cache.update_token_reservoir(addr, wei)

    async def _refresh_market_data(self) -> None:
        addresses = list(self.cache.tokens.keys())
        if not addresses:
            return
        try:
            market = await self.client.fetch_market_data(addresses)
        except Exception as exc:
            logger.debug("market data batch failed: %s", exc)
            return
        for addr, md in market.items():
            self.cache.update_token_market(
                addr,
                price_usd=md.get("price_usd"),
                change_h24=md.get("change_h24"),
                volume_h24=md.get("volume_h24"),
                mcap=md.get("mcap"),
            )

    async def _block_timestamp(
        self, block_num: int, now: float, current_block: int
    ) -> int:
        """Approximate the unix timestamp of a block.

        We do NOT do per-block RPC reads -- that would blow the budget. Instead,
        we anchor on the current block at the current wall-clock time and
        extrapolate backwards at ~12 seconds per block (Ethereum L1).
        """
        if current_block <= 0 or block_num <= 0:
            return int(now)
        return max(0, int(now) - (current_block - block_num) * 12)


__all__ = ["TTTManager"]
