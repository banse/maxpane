"""Orchestrates Onchain Monsters data fetching, caching, and analytics computation.

The ``OCMManager`` is the single coordination point between the async
RPC client, the time-series cache, and the analytics modules.  It exposes
one public coroutine -- ``fetch_and_compute()`` -- that returns a flat dict
ready for widget consumption.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.ocm_signals import (
    compute_burn_rate,
    compute_mint_velocity,
    generate_burn_rate_signal,
    generate_mint_velocity_signal,
    generate_recommendation,
    generate_staking_signal,
)
from maxpane_dashboard.data.ocm_cache import OCMCache
from maxpane_dashboard.data.ocm_client import OCMClient
from maxpane_dashboard.data.ocm_models import OCMSnapshot

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "ocm_cache.json"


class OCMManager:
    """Orchestrates Onchain Monsters data fetching, caching, and analytics.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    """

    def __init__(self, poll_interval: int = 60) -> None:
        self.client = OCMClient()
        self.cache = OCMCache(max_history=120)
        self._poll_interval = poll_interval
        self._error_count = 0

        # Ensure cache directory exists
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Attempt to load persisted history on construction
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Fetch all data, update cache, compute analytics.

        Returns a flat dict with keys organized by dashboard widget:

        Hero metrics:
            ``total_supply``, ``minted_pct``, ``holder_count``,
            ``avg_per_holder``, ``current_minting_cost_ocmd``.

        Staking overview:
            ``total_staked``, ``net_supply``, ``staking_ratio``,
            ``ocmd_total_supply``, ``daily_emission``,
            ``days_to_earn_mint``, ``burned_count``, ``remaining``.

        Sparklines:
            ``supply_history``, ``staked_history``,
            ``ocmd_supply_history``.

        Signals:
            ``staking_signal``, ``mint_velocity_signal``,
            ``burn_rate_signal``, ``recommendation``.

        Activity feed:
            ``recent_events``.

        Meta:
            ``error_count``, ``last_updated_seconds_ago``,
            ``poll_interval``.
        """
        try:
            snapshot = await self.client.fetch_snapshot()
        except Exception:
            self._error_count += 1
            raise

        # -- Update cache with latest snapshot --------------------------------
        self.cache.update(snapshot)

        # -- Derived values ---------------------------------------------------
        # Use cached holder_count if snapshot reports 0 (holder scan is expensive)
        holder_count = snapshot.holder_count or self.cache.holder_count
        net_supply = snapshot.collection.net_supply
        avg_per_holder = net_supply / max(1, holder_count)
        current_minting_cost_ocmd = snapshot.collection.current_minting_cost / 10**18

        # -- Sparkline histories ----------------------------------------------
        supply_history = self.cache.get_supply_history()
        staked_history = self.cache.get_staked_history()
        ocmd_supply_history = self.cache.get_ocmd_supply_history()

        # -- Signals (3 signals + recommendation) -----------------------------
        _sig_default = {"label": "", "value_str": "--", "indicator": "", "color": "dim"}

        staking_signal = _safe_call(
            generate_staking_signal, snapshot.staking.staking_ratio,
            default=_sig_default,
        )

        velocity = _safe_call(
            compute_mint_velocity, supply_history,
            default=0.0,
        )
        mint_velocity_signal = _safe_call(
            generate_mint_velocity_signal, velocity,
            default=_sig_default,
        )

        burn_rate = _safe_call(
            compute_burn_rate, supply_history,
            default=0.0,
        )
        burn_rate_signal = _safe_call(
            generate_burn_rate_signal, burn_rate,
            default=_sig_default,
        )

        # Determine supply trend direction for recommendation
        supply_trend_up = False
        if len(supply_history) >= 2:
            supply_trend_up = supply_history[-1][1] > supply_history[0][1]

        recommendation = _safe_call(
            generate_recommendation,
            snapshot.staking.staking_ratio,
            velocity,
            burn_rate,
            supply_trend_up,
            default="",
        )

        # -- Tier & activity counts -------------------------------------------
        total_supply = snapshot.collection.total_supply
        _TIERS = [(0, 1999, 0), (2000, 3999, 1), (4000, 5999, 2), (6000, 7999, 3), (8000, 9999, 4)]
        time_to_next_tier = ""
        for _start, end, _cost in _TIERS:
            if total_supply <= end:
                until_next = end - total_supply + 1
                if velocity and velocity > 0:
                    days = until_next / velocity
                    if days < 1:
                        time_to_next_tier = f"{until_next:,} mints ({days * 24:.0f}h at current rate)"
                    else:
                        time_to_next_tier = f"{until_next:,} mints (~{days:.0f}d at current rate)"
                else:
                    time_to_next_tier = f"{until_next:,} mints to go"
                break

        recent_mints = sum(1 for e in snapshot.recent_events if e.event_type == "mint")
        recent_burns = sum(1 for e in snapshot.recent_events if e.event_type == "burn")

        # -- Recent events as list of dicts -----------------------------------
        recent_events = [
            {
                "tx_hash": e.tx_hash,
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "actor_address": e.actor_address,
                "token_id": e.token_id,
                "count": e.count,
            }
            for e in snapshot.recent_events
        ]

        # -- Staleness --------------------------------------------------------
        last_updated_seconds_ago = time.time() - snapshot.fetched_at

        # -- Assemble flat dict -----------------------------------------------
        return {
            # Hero metrics
            "total_supply": snapshot.collection.total_supply,
            "minted_pct": snapshot.collection.minted_pct,
            "holder_count": holder_count,
            "avg_per_holder": avg_per_holder,
            "current_minting_cost_ocmd": current_minting_cost_ocmd,
            # Staking overview
            "total_staked": snapshot.staking.total_staked,
            "net_supply": net_supply,
            "staking_ratio": snapshot.staking.staking_ratio,
            "ocmd_total_supply": snapshot.staking.ocmd_total_supply,
            "daily_emission": snapshot.staking.daily_emission,
            "days_to_earn_mint": snapshot.staking.days_to_earn_mint,
            "burned_count": snapshot.collection.burned_count,
            "remaining": snapshot.collection.remaining,
            "faucet_open": snapshot.faucet_open,
            "time_to_next_tier": time_to_next_tier,
            # Sparklines
            "supply_history": supply_history,
            "staked_history": staked_history,
            "ocmd_supply_history": ocmd_supply_history,
            # Signals
            "staking_signal": staking_signal,
            "mint_velocity_signal": mint_velocity_signal,
            "burn_rate_signal": burn_rate_signal,
            "recommendation": recommendation,
            # Activity feed
            "recent_events": recent_events,
            # Supply breakdown extras
            "recent_mints": recent_mints,
            "recent_burns": recent_burns,
            # Meta
            "last_updated_seconds_ago": last_updated_seconds_ago,
            "error_count": self._error_count,
            "poll_interval": self._poll_interval,
        }

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
        logger.debug("Analytics call %s failed: %s", fn.__name__, exc)
        return default
