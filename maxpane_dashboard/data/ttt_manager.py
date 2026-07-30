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
6. Sample burns into the hourly deques.
7. Compute 24h rolling counters and run signal analytics.
8. Return a flat dict.

The ETH/USD price uses the existing :class:`PriceClient` TTL cache (300s).

The NFT floor metric is **unavailable**: its only source (Reservoir) was
sunset and no keyless replacement covers this collection. The ``floor_eth`` /
``floor_usd`` / ``sales_24h`` keys are still emitted, pinned to ``None`` and
accompanied by ``floor_unavailable_reason``, so a consumer renders an explicit
"unavailable" rather than a fabricated zero. See ``ttt_client.FLOOR_SOURCE``.
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
    _FACTORY_DEPLOY_BLOCK,
    _INCREMENTAL_LOG_LOOKBACK,
    _SCALE,
    _WEI,
    FLOOR_UNAVAILABLE_REASON,
    TTTClient,
)

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "ttt_cache.json"

# Blocks of deliberate overlap on every incremental scan, so a shallow L1
# reorg between two polls can't drop an event permanently. The re-delivered
# events are suppressed by TTTCache's idempotency guard, so the overlap costs
# nothing but is the reason that guard has to exist.
_REORG_MARGIN_BLOCKS = 12

# Addresses per `eth_getLogs` call when scanning per-token `Bought` events.
# Public RPCs are happy with an address array this size (the reservoir
# multicall uses the same batch size), and every chunk is scanned each cycle,
# so this bounds the size of one request -- it does not bound how many tokens
# get scanned.
_BOUGHT_ADDRESS_CHUNK = 200


def _safe_call(fn: Any, *args: Any, default: Any = None) -> Any:
    """Call *fn* with *args*, returning *default* on exception."""
    try:
        return fn(*args)
    except Exception as exc:
        logger.debug("Analytics call %s failed: %s", getattr(fn, "__name__", fn), exc)
        return default


def _age_str(launch_block: int, current_block: int) -> str:
    """Human-readable age of a launch (block-delta -> "Nb" or rough time).

    Returns ``"?"`` when the head block is unknown (``current_block <= 0``,
    which is what ``fetch_block_number`` returns on a failed read). The old
    ``max(0, ...)`` clamp turned that into ``"0b"`` for every row at once, so
    an RPC outage read as "the entire collection launched this block" (LOW-5).
    """
    if current_block <= 0:
        return "?"
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
        # Last factory read that actually came back from chain, so an outage
        # can show stale-but-true numbers instead of a confident zero.
        self._last_factory: dict[str, int] | None = None

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache.load_from_file(str(_CACHE_FILE), now=time.time())

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
        factory_ok = True
        try:
            factory = await factory_task
            self._last_factory = dict(factory)
        except Exception as exc:
            factory_ok = False
            self._error_count += 1
            logger.warning("factory state fetch failed: %s", exc)
            # Prefer the last reading we actually got from chain. A stale
            # burn count next to a raised error_count is honest; a fresh-looking
            # zero is not (MEDI-31). The all-zero dict is only for the case
            # where we have never had a successful read at all.
            factory = dict(self._last_factory) if self._last_factory else {
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

        # -- 5+10) Market data + ETH/USD in parallel ----------------------
        # DexScreener and CoinGecko are independent HTTP origins; run them
        # concurrently to cut total wall time. There is no floor fetch: its
        # source is gone (see the module docstring).
        market_task = asyncio.create_task(self._refresh_market_data())
        eth_usd_task = asyncio.create_task(self.price_client.get_eth_usd())

        try:
            await market_task
        except Exception as exc:
            logger.debug("market data fetch failed: %s", exc)

        try:
            eth_usd = await eth_usd_task
        except Exception as exc:
            logger.debug("ETH price fetch failed: %s", exc)
            eth_usd = 0.0

        # -- 7) Sample hourly buckets ------------------------------------
        # floor is always None now; sample_burns_and_floor ignores None.
        # Only sample from a factory read that actually happened: the hourly
        # bucket is overwrite-by-hour and gets persisted, so one sample taken
        # during an outage can leave a permanent dip in the 7-day sparkline if
        # no good cycle lands in the same hour (MEDI-31).
        if factory_ok:
            self.cache.sample_burns_and_floor(
                now, factory["burn_count"], self._last_floor_eth
            )
        # Total 24h volume across all tokens with market data; mirrors the
        # burns/floor sampling pattern so the sparkline widget has a uniform
        # source.
        total_volume_usd = sum(
            float(t.volume_usd_h24 or 0.0)
            for t in self.cache.tokens.values()
        )
        self.cache.sample_volume(now, total_volume_usd)

        # Aggregate total market cap (USD + ETH) across tokens with market
        # data. Computed AFTER eth_usd is available so the ETH-denominated
        # value is meaningful. CR1.
        mcap_contributors = [
            float(t.market_cap_usd)
            for t in self.cache.tokens.values()
            if t.market_cap_usd is not None
        ]
        total_mcap_usd = sum(mcap_contributors) if mcap_contributors else 0.0
        total_mcap_token_count = len(mcap_contributors)
        total_mcap_eth: float | None = (
            (total_mcap_usd / eth_usd) if (eth_usd and eth_usd > 0) else None
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

        # `fetch_block_number` reports a failed read as 0, which is not a block
        # height -- it is "we don't know". Signals whose whole meaning is a
        # distance from the head are therefore suppressed for the cycle rather
        # than computed against a fictional head (LOW-5); the snapshot builder
        # renders a `None` signal as a dim "--" row, which is the honest
        # answer. Block-independent signals (buybacks-ready, concentration)
        # are unaffected and keep updating.
        block_known = current_block > 0

        if factory_state is not None:
            fresh = (
                _safe_call(fresh_launch_alert, recent_events, current_block, now)
                if block_known
                else None
            )
            br = _safe_call(buybacks_ready_signal, tokens_list, default=None)
            dw = (
                _safe_call(
                    decay_window_signal, tokens_list, current_block, default=None
                )
                if block_known
                else None
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

        # -- 13) Activity feed (last 25 as dicts, sorted by block desc) ----
        # CR3: sort at read time by block_number desc so multi-day scans
        # display in correct chronological order regardless of insertion
        # order. The activity_log insertion path is unchanged.
        activity = [
            e.model_dump()
            for e in self.cache.get_activity_for_display(limit=25)
        ]

        last_updated_seconds_ago = max(0.0, time.time() - now)

        burns_history = [list(pt) for pt in self.cache.burns_hourly]
        floor_history = [list(pt) for pt in self.cache.floor_hourly]
        volume_history = [list(pt) for pt in self.cache.volume_hourly]

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
            # Always None -- metric dropped, reason carried alongside so a
            # consumer can render "unavailable" instead of a blank or a zero.
            "floor_eth": self._last_floor_eth,
            "floor_usd": self._last_floor_usd,
            "floor_unavailable_reason": FLOOR_UNAVAILABLE_REASON,
            # Leaderboard
            "top_tokens_by_volume": top_tokens_by_volume,
            # Aggregate market cap (CR1)
            "total_mcap_usd": total_mcap_usd,
            "total_mcap_eth": total_mcap_eth,
            "total_mcap_token_count": total_mcap_token_count,
            # Sparkline
            "burns_history": burns_history,
            "floor_history": floor_history,
            "volume_history": volume_history,
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
            """First block of this cycle's scan for *topic_name*.

            Steady state starts just after the watermark, minus a small reorg
            margin -- NOT at ``current_block - _INCREMENTAL_LOG_LOOKBACK``.
            This used to be a ``min()`` (CRIT-1), which pinned every scan to
            the full 5,000-block window and re-applied ~16.7h of events on
            every 30s poll.

            ``_INCREMENTAL_LOG_LOOKBACK`` is the *floor*: after a long
            downtime we scan at most that many blocks rather than paging
            through the whole gap, which is what the constant was always
            documented to mean.
            """
            last = self.cache.last_seen_block.get(topic_name, 0)
            if last <= 0:
                # First run: start at the factory's deploy block, not at a
                # rolling offset from head. The launch history is finite and
                # already ~500k blocks old, so a rolling window misses it
                # entirely and the watermark then advances past it forever.
                return max(
                    0,
                    _FACTORY_DEPLOY_BLOCK,
                    current_block - default_lookback,
                )
            return max(
                0,
                last + 1 - _REORG_MARGIN_BLOCKS,
                current_block - _INCREMENTAL_LOG_LOOKBACK,
            )

        def _advance(topic_name: str, from_block: int, scanned_to: int) -> None:
            """Move the watermark to the last block actually scanned.

            Never to ``current_block`` (MEDI-29): the client stops at the first
            page it could not fetch, and advancing over that page would drop
            its events permanently -- the next cycle starts after the gap and
            the ``_INCREMENTAL_LOG_LOOKBACK`` floor never reaches back into it.
            """
            if scanned_to < from_block:
                self._error_count += 1
                logger.warning(
                    "%s scan made no progress from block %d; watermark held "
                    "at %s",
                    topic_name,
                    from_block,
                    self.cache.last_seen_block.get(topic_name),
                )
                return
            self.cache.last_seen_block[topic_name] = scanned_to
            if scanned_to < current_block:
                # Partial progress is persisted and the remainder retried next
                # cycle, so no block is ever skipped over.
                self._error_count += 1
                logger.warning(
                    "%s scan incomplete: reached %d of %d",
                    topic_name,
                    scanned_to,
                    current_block,
                )

        # Launched (factory)
        try:
            fb = _from("Launched", _DEFAULT_LOG_LOOKBACK_BLOCKS)
            launches, scanned_to = await self.client.fetch_launched_events(
                fb, current_block
            )
            for ev in launches:
                ts = await self._block_timestamp(ev["block_number"], now, current_block)
                self.cache.apply_launch(
                    token_id=ev["token_id"],
                    address=ev["erc20_address"],
                    launcher=ev["launcher"],
                    block_number=ev["block_number"],
                    timestamp=ts,
                    tx_hash=ev["tx_hash"],
                    log_index=ev.get("log_index"),
                )
            _advance("Launched", fb, scanned_to)
        except Exception as exc:
            self._error_count += 1
            logger.warning("Launched scan failed: %s", exc)

        # Deposited (FeeSplitter)
        try:
            fb = _from("Deposited", _DEFAULT_LOG_LOOKBACK_BLOCKS)
            deposits, scanned_to = await self.client.fetch_deposit_events(
                fb, current_block
            )
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
                    log_index=ev.get("log_index"),
                )
            _advance("Deposited", fb, scanned_to)
        except Exception as exc:
            self._error_count += 1
            logger.warning("Deposited scan failed: %s", exc)

        # Bought (per-ERC20). Only scan if we have known tokens.
        #
        # Every known token is scanned, in address-list chunks (LOW-16). This
        # used to pass `known[:200]`, and since `cache.tokens` is insertion-
        # ordered by launch and never re-sorted, that was the 200 *oldest*
        # launches: past 200 tokens, buybacks on everything newer -- i.e. the
        # most actively traded end of the collection -- were never requested.
        # The omission was permanent, not just delayed, because the watermark
        # below still advanced over those blocks.
        #
        # Picking a "better" 200 (newest, or richest reservoir) would only move
        # the blind spot, so we cover the whole set instead. The watermark is
        # advanced to the *minimum* progress across chunks, so one refused
        # chunk holds the whole topic back; re-delivered events from the
        # already-scanned chunks are absorbed by the cache's idempotency guard.
        known = list(self.cache.tokens.keys())
        if known:
            try:
                fb = _from("Bought", _DEFAULT_LOG_LOOKBACK_BLOCKS)
                chunks = [
                    known[i : i + _BOUGHT_ADDRESS_CHUNK]
                    for i in range(0, len(known), _BOUGHT_ADDRESS_CHUNK)
                ]
                buys: list[dict] = []
                scanned_to = current_block
                for chunk in chunks:
                    chunk_buys, chunk_to = await self.client.fetch_buyback_events(
                        chunk, fb, current_block
                    )
                    buys.extend(chunk_buys)
                    scanned_to = min(scanned_to, chunk_to)
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
                        log_index=ev.get("log_index"),
                    )
                _advance("Bought", fb, scanned_to)
            except Exception as exc:
                self._error_count += 1
                logger.warning("Bought scan failed: %s", exc)

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
        """Pull per-token market data; falls back through 2 sources.

        Primary: tenthousandtokens.net SSR HTML scrape -- 100% coverage of
        launched tokens (vs DexScreener's partial indexing) and includes
        every token the site shows. Fallback: DexScreener batch (used when
        the site is unreachable or its HTML structure changes).
        """
        addresses = list(self.cache.tokens.keys())
        if not addresses:
            return
        # Site scrape first.
        site_market: dict[str, dict] = {}
        try:
            site_market = await self.client.fetch_site_market_data()
        except Exception as exc:
            logger.debug("site market data fetch failed: %s", exc)
        # If the site returned nothing usable, fall back to DexScreener.
        if not site_market:
            try:
                site_market = await self.client.fetch_market_data(addresses)
            except Exception as exc:
                logger.debug("DexScreener fallback failed: %s", exc)
                return
        for addr, md in site_market.items():
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
