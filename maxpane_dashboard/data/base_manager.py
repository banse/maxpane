"""Orchestrates Base chain data fetching, caching, and analytics computation.

The ``BaseManager`` is the single coordination point between the async
API client, the time-series cache, and the analytics modules.  It exposes
one public coroutine -- ``fetch_and_compute()`` -- that returns a flat dict
ready for widget consumption.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load API keys from baseboard .env if available
_BASEBOARD_ENV_PATH = os.getenv("MAXPANE_BASEBOARD_ENV", "")
_BASEBOARD_ENV = Path(_BASEBOARD_ENV_PATH) if _BASEBOARD_ENV_PATH else None
if _BASEBOARD_ENV is not None and _BASEBOARD_ENV.exists():
    load_dotenv(str(_BASEBOARD_ENV), override=False)

from maxpane_dashboard.analytics.base_signals import generate_token_signal
from maxpane_dashboard.analytics.base_tokens import (
    calculate_momentum_score,
    classify_token_status,
    get_top_movers,
    get_volume_leaders,
)
from maxpane_dashboard.data.base_cache import BaseTokenCache
from maxpane_dashboard.data.base_client import BaseChainClient
from maxpane_dashboard.data.base_models import BaseToken, TokenDetail, TokenLaunch

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "base_cache.json"


class BaseManager:
    """Orchestrates Base chain data fetching, caching, and analytics.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    bankr_api_key:
        Optional Bankr API key.  Falls back to ``BANKR_API_KEY`` env var.
    alchemy_api_key:
        Optional Alchemy API key.  Falls back to ``ALCHEMY_API_KEY`` env var.
    remote_only:
        When ``True``, the manager fetches data exclusively from DexScreener
        (no Bankr, GeckoTerminal, or Clanker).  Used by the Base Trading
        Overview dashboard.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        bankr_api_key: str | None = None,
        alchemy_api_key: str | None = None,
        *,
        remote_only: bool = False,
    ) -> None:
        self.client = BaseChainClient(
            bankr_api_key=bankr_api_key,
            alchemy_api_key=alchemy_api_key,
        )
        self.cache = BaseTokenCache(max_history=120)
        self._poll_interval = poll_interval
        self._error_count = 0
        self._selected_token: str | None = None
        self._remote_only = remote_only

        # Attempt to load persisted history on construction
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Fetch all data, update cache, compute analytics.

        Returns a dict with keys:

        Token data:
            ``trending_tokens``, ``trending_pools``.

        Analytics:
            ``top_gainers``, ``top_losers``, ``volume_leaders``,
            ``token_signals``, ``token_statuses``.

        Time-series:
            ``price_histories``.

        Overview (only when ``remote_only=True``):
            ``eth_price``, ``eth_change_24h``, ``gas_price``,
            ``total_volume``, ``top_gainer_name``, ``top_gainer_pct``,
            ``gainers``, ``losers``, ``buy_sell_signal``, ``volume_signal``,
            ``whale_signal``, ``recommendation``, ``whale_trades``,
            ``volume_history``, ``eth_price_history``, ``trade_count_history``.

        Meta:
            ``error_count``, ``last_updated_seconds_ago``, ``poll_interval``.
        """
        try:
            snapshot = await self.client.fetch_snapshot(
                remote_only=self._remote_only,
            )
        except Exception:
            self._error_count += 1
            raise

        self.cache.update(snapshot)
        tokens = list(snapshot.trending_tokens)
        pools = list(snapshot.trending_pools)
        launches = sorted(snapshot.launches, key=lambda t: t.created_at, reverse=True)

        # -- Top movers (24h) ---------------------------------------------
        top_gainers, top_losers = _safe_call(
            get_top_movers,
            tokens,
            "price_change_24h",
            5,
            default=([], []),
        )

        # -- Volume leaders ------------------------------------------------
        volume_leaders = _safe_call(
            get_volume_leaders,
            tokens,
            10,
            default=[],
        )

        # -- Per-token signals and statuses --------------------------------
        token_signals: dict[str, dict[str, Any]] = {}
        token_statuses: dict[str, str] = {}

        for token in tokens:
            addr = token.address
            token_signals[addr] = _safe_call(
                generate_token_signal,
                token,
                default={
                    "momentum": 0.0,
                    "volume_spike": False,
                    "liq_health": "unknown",
                    "overall": "neutral",
                },
            )
            token_statuses[addr] = _safe_call(
                classify_token_status,
                token,
                default="stable",
            )

        # -- Launch analytics ------------------------------------------------
        launch_stats = self.client.get_launch_stats(launches)
        graduated_launches = [t for t in launches if t.graduated]

        # -- Price histories from cache ------------------------------------
        price_histories = self.cache.get_all_histories()

        # -- Staleness ----------------------------------------------------
        last_updated_seconds_ago = time.time() - snapshot.fetched_at

        # -- Assemble widget data dict ------------------------------------
        result: dict[str, Any] = {
            # Token data
            "trending_tokens": tokens,
            "trending_pools": pools,
            # Launch data
            "launches": launches,
            "launch_stats": launch_stats,
            "graduated_launches": graduated_launches,
            # Analytics
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "volume_leaders": volume_leaders,
            "token_signals": token_signals,
            "token_statuses": token_statuses,
            # Time-series
            "price_histories": price_histories,
            # Meta
            "error_count": self._error_count,
            "last_updated_seconds_ago": last_updated_seconds_ago,
            "poll_interval": self._poll_interval,
        }

        # -- Overview enrichment (remote_only mode) -----------------------
        if self._remote_only:
            result.update(await self._compute_overview(tokens, snapshot.fetched_at))

        return result

    async def _compute_overview(
        self,
        tokens: list[BaseToken],
        fetched_at: float,
    ) -> dict[str, Any]:
        """Compute overview-specific data for the Base Trading Overview dashboard.

        Fetches ETH price and gas price, computes aggregate metrics from
        trending tokens, records time-series points, and runs overview
        signal computation.
        """
        import asyncio as _asyncio

        # Fetch ETH price and gas price concurrently
        eth_result, gas_price = await _asyncio.gather(
            self.client.get_eth_price(),
            self.client.get_base_gas_price(),
        )
        eth_price, eth_change_24h = eth_result

        # Aggregate metrics from trending tokens
        total_volume = sum(t.volume_24h for t in tokens)
        total_trades = sum(t.buys_24h + t.sells_24h for t in tokens)

        # Top gainer
        tokens_with_change = [
            t for t in tokens if t.price_change_24h is not None
        ]
        if tokens_with_change:
            top_gainer = max(tokens_with_change, key=lambda t: t.price_change_24h or 0.0)
            top_gainer_name = f"{top_gainer.name} ({top_gainer.symbol})"
            top_gainer_pct = f"{top_gainer.price_change_24h:+.1f}%" if top_gainer.price_change_24h else "+0.0%"
        else:
            top_gainer_name = "N/A"
            top_gainer_pct = "0.0%"

        # Gainers and losers (top 10 each)
        sorted_by_change = sorted(
            tokens_with_change,
            key=lambda t: t.price_change_24h or 0.0,
            reverse=True,
        )
        gainers: list[tuple[str, str]] = [
            (t.name, f"{t.price_change_24h:+.1f}%")
            for t in sorted_by_change[:10]
            if (t.price_change_24h or 0.0) > 0
        ]
        losers: list[tuple[str, str]] = [
            (t.name, f"{t.price_change_24h:+.1f}%")
            for t in reversed(sorted_by_change)
            if (t.price_change_24h or 0.0) < 0
        ][:10]

        # Volume trend from cache (compare to previous point)
        prev_volume_history = self.cache.get_volume_history()
        prev_volume = prev_volume_history[-1][1] if prev_volume_history else 0.0

        # Record overview time-series point
        self.cache.record_overview_point(
            timestamp=fetched_at,
            total_volume=total_volume,
            eth_price=eth_price,
            trade_count=total_trades,
        )

        # Activity feed: all tokens sorted by volume with buy/sell data
        whale_trades: list[dict[str, Any]] = [
            {
                "symbol": t.symbol,
                "volume_24h": t.volume_24h,
                "buys_24h": t.buys_24h,
                "sells_24h": t.sells_24h,
                "price_change_24h": t.price_change_24h,
                "liquidity": t.liquidity,
            }
            for t in sorted(tokens, key=lambda t: t.volume_24h, reverse=True)
        ]

        # Signal computation
        try:
            from maxpane_dashboard.analytics.base_overview_signals import (
                compute_buy_sell_ratio,
                compute_volume_trend,
                compute_whale_activity,
                generate_recommendation,
            )

            bs = compute_buy_sell_ratio(tokens)
            buy_sell_signal = bs.get("label", "Neutral")

            vt = compute_volume_trend(total_volume, prev_volume)
            volume_signal = vt.get("label", "Flat")

            # Whale activity: count tokens with >$100K individual volume
            whale_count = sum(1 for t in tokens if t.volume_24h >= 100_000)
            wa = compute_whale_activity(whale_count)
            whale_signal = wa.get("label", "Low")

            recommendation = generate_recommendation(
                buy_sell_signal, volume_signal, whale_signal,
            )
        except Exception as exc:
            logger.warning("Overview signal computation failed: %s", exc)
            buy_sell_signal = "Neutral"
            volume_signal = "Flat"
            whale_signal = "Low"
            recommendation = "Waiting for data..."

        return {
            "eth_price": eth_price,
            "eth_change_24h": eth_change_24h,
            "gas_price": gas_price,
            "total_volume": total_volume,
            "top_gainer_name": top_gainer_name,
            "top_gainer_pct": top_gainer_pct,
            "gainers": gainers,
            "losers": losers,
            "buy_sell_signal": buy_sell_signal,
            "volume_signal": volume_signal,
            "whale_signal": whale_signal,
            "recommendation": recommendation,
            "whale_trades": whale_trades,
            "volume_history": self.cache.get_volume_history(),
            "eth_price_history": self.cache.get_eth_price_history(),
            "trade_count_history": self.cache.get_trade_count_history(),
        }

    # ------------------------------------------------------------------
    # Token detail (on-demand, not part of poll cycle)
    # ------------------------------------------------------------------

    def select_token(self, address: str) -> None:
        """Set the token address for the detail view.

        Call this when the user navigates to the Token Detail panel.
        """
        self._selected_token = address.lower() if address else None

    async def get_token_detail(self, address: str) -> dict[str, Any]:
        """Fetch detail for a specific token.

        Called on-demand when the user selects a token.  Returns a dict
        with keys ``token_detail``, ``recent_trades``, ``token_signal``.
        Each degrades independently on failure.
        """
        detail = await self.client.get_token_detail(address)

        trades: list[dict[str, Any]] = []
        if detail and detail.pair_address:
            try:
                trades = await self.client.get_token_trades(detail.pair_address)
            except Exception as exc:
                logger.warning("Trades fetch failed for %s: %s", address, exc)

        signal: dict[str, Any] = {}
        if detail:
            signal = _safe_call(
                generate_token_signal,
                detail,
                default={
                    "momentum": 0.0,
                    "volume_spike": False,
                    "liq_health": "unknown",
                    "overall": "neutral",
                },
            )

        return {
            "token_detail": detail,
            "recent_trades": trades,
            "token_signal": signal,
        }

    async def fetch_selected_token(self) -> dict[str, Any] | None:
        """Fetch detail for the currently selected token.

        Returns ``None`` if no token is selected.  Otherwise delegates
        to :meth:`get_token_detail`.
        """
        if not self._selected_token:
            return None
        return await self.get_token_detail(self._selected_token)

    def save_cache(self) -> None:
        """Persist cache to disk."""
        self.cache.save_to_file(str(_CACHE_FILE))

    async def close(self) -> None:
        """Shut down the HTTP client and persist cache."""
        self.save_cache()
        await self.client.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_call(fn: Any, *args: Any, default: Any = None) -> Any:
    """Call *fn* with *args*, returning *default* on any exception.

    Logs a warning so failures are visible but never crash the dashboard.
    """
    try:
        return fn(*args)
    except Exception as exc:
        logger.warning("Analytics call %s failed: %s", fn.__name__, exc)
        return default
