"""Orchestrates data fetching, caching, and analytics computation.

The ``DataManager`` is the single coordination point between the async API
client, the time-series cache, and the analytics modules.  It exposes one
public coroutine -- ``fetch_and_compute()`` -- that returns a flat dict
ready for widget consumption.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.ev import rank_attacks, rank_boosts
from maxpane_dashboard.analytics.production import calculate_production_rate
from maxpane_dashboard.analytics.signals import (
    calculate_gap_analysis,
    calculate_late_join_ev,
    calculate_leader_dominance,
    generate_recommendation,
)
from maxpane_dashboard.data.cache import DataCache
from maxpane_dashboard.data.client import GameDataClient
from maxpane_dashboard.data.snapshot import GameSnapshot

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "history_cache.json"

# Wei-to-ETH divisor
_WEI = 10**18

# Cookie scale: raw on-chain values are display_cookies * COOKIE_SCALE
_COOKIE_SCALE = 10_000


class DataManager:
    """Orchestrates data fetching, caching, and analytics computation.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    """

    def __init__(self, poll_interval: int = 30) -> None:
        self.client = GameDataClient()
        self.cache = DataCache(max_history=120)
        self._poll_interval = poll_interval
        self._error_count = 0
        self._last_snapshot: GameSnapshot | None = None

        # Attempt to load persisted history on construction
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Fetch all data, update cache, compute analytics.

        Returns a dict with all computed values keyed for each widget's
        ``update_data()`` signature.  On failure the ``_error_count`` is
        incremented and the exception re-raised so the caller can decide
        how to handle it (e.g. show stale data).
        """
        try:
            snapshot = await self.client.fetch_all()
        except Exception:
            self._error_count += 1
            raise

        self._last_snapshot = snapshot
        self.cache.update(snapshot)

        # ── Derived values ────────────────────────────────────────────
        season = snapshot.season
        bakeries = snapshot.bakeries
        eth_price = snapshot.eth_price_usd
        agent_config = snapshot.agent_config

        # Prize pool
        prize_pool_eth = int(season.prize_pool) / _WEI
        prize_pool_usd = prize_pool_eth * eth_price

        # Season countdown
        end_ts = int(season.end_time)
        now = time.time()
        remaining_seconds = max(end_ts - now, 0)
        hours_remaining = remaining_seconds / 3600.0
        season_active = season.is_active and remaining_seconds > 0

        # Leader info (tx_count is raw; divide by cookie scale for display)
        leader_name = bakeries[0].name if bakeries else "---"
        leader_cookies = int(bakeries[0].tx_count) / _COOKIE_SCALE if bakeries else 0.0
        second_cookies = int(bakeries[1].tx_count) / _COOKIE_SCALE if len(bakeries) > 1 else 0.0

        # ── Production rates from cache histories ─────────────────────
        production_rates: dict[str, float] = {}
        for b in bakeries:
            history = self.cache.get_cookie_history(b.name)
            production_rates[b.name] = calculate_production_rate(history)

        leader_rate = production_rates.get(leader_name, 0.0)

        # ── EV rankings ──────────────────────────────────────────────
        boost_rankings = rank_boosts(leader_rate)
        attack_rankings = rank_attacks(leader_rate)

        # ── Signals ──────────────────────────────────────────────────
        buy_in_eth = float(agent_config.live_state.buy_in_eth)
        member_count = bakeries[0].member_count if bakeries else 1

        # Top-3 probability: approximate as min(3, num_bakeries) / num_bakeries
        num_bakeries = max(len(bakeries), 1)
        top3_probability = min(3, num_bakeries) / num_bakeries

        late_join_ev = calculate_late_join_ev(
            prize_pool_eth=prize_pool_eth,
            eth_price_usd=eth_price,
            member_count=member_count,
            buy_in_eth=buy_in_eth,
            win_probability=top3_probability,
        )

        # Top-3 cookie values for gap analysis
        third_cookies = int(bakeries[2].tx_count) / _COOKIE_SCALE if len(bakeries) > 2 else 0.0
        fourth_cookies = int(bakeries[3].tx_count) / _COOKIE_SCALE if len(bakeries) > 3 else 0.0

        # Gap analysis -- from #2's perspective vs #1
        your_cookies = second_cookies
        your_rate = production_rates.get(
            bakeries[1].name if len(bakeries) > 1 else "", 0.0
        )
        gap_to_leader = calculate_gap_analysis(
            leader_cookies=leader_cookies,
            leader_rate=leader_rate,
            your_cookies=your_cookies,
            your_rate=your_rate,
            hours_remaining=hours_remaining,
        )

        # Gap analysis -- #4's perspective vs #3 (for "outside top 3" recommendation)
        fourth_rate = production_rates.get(
            bakeries[3].name if len(bakeries) > 3 else "", 0.0
        )
        third_rate = production_rates.get(
            bakeries[2].name if len(bakeries) > 2 else "", 0.0
        )
        gap_to_third = calculate_gap_analysis(
            leader_cookies=third_cookies,
            leader_rate=third_rate,
            your_cookies=fourth_cookies,
            your_rate=fourth_rate,
            hours_remaining=hours_remaining,
        ) if len(bakeries) > 3 else None

        dominance = calculate_leader_dominance(leader_cookies, second_cookies)

        recommendation = generate_recommendation(
            dominance=dominance,
            hours_remaining=hours_remaining,
            your_rank=2,
            gap_analysis=gap_to_leader,
        )

        # ── Cookie chart histories (top 3) ────────────────────────────
        chart_histories: dict[str, list[tuple[float, float]]] = {}
        for b in bakeries[:3]:
            chart_histories[b.name] = self.cache.get_cookie_history(b.name)

        # ── Staleness ─────────────────────────────────────────────────
        last_updated_seconds_ago = time.time() - snapshot.fetched_at

        # ── Assemble widget data dict ─────────────────────────────────
        return {
            # hero_metrics
            "prize_pool_eth": prize_pool_eth,
            "prize_pool_usd": prize_pool_usd,
            "hours_remaining": hours_remaining,
            "season_id": season.id,
            "season_active": season_active,
            "leader_name": leader_name,
            "leader_cookies": leader_cookies,
            "leader_rate": leader_rate,
            # leaderboard
            "bakeries": bakeries,
            "production_rates": production_rates,
            # cookie_chart
            "chart_histories": chart_histories,
            # activity_feed
            "events": snapshot.activity,
            # signals_panel
            "late_join_ev": late_join_ev,
            "gap_analysis": gap_to_leader,  # backward compat key for SignalsPanel
            "gap_to_third": gap_to_third,
            "dominance": dominance,
            "recommendation": recommendation,
            # ev_table
            "boost_rankings": boost_rankings,
            "attack_rankings": attack_rankings,
            # status_bar
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
