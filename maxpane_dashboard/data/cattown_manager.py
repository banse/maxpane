"""Orchestrates Cat Town data fetching, caching, and analytics computation.

The ``CatTownManager`` is the single coordination point between the async
RPC client, the time-series cache, and the analytics modules.  It exposes
one public coroutine -- ``fetch_and_compute()`` -- that returns a flat dict
ready for widget consumption.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.cattown_conditions import (
    get_available_fish,
    get_available_treasures,
    get_competition_timing,
    get_current_conditions,
    is_legendary_window,
)

from maxpane_dashboard.analytics.cattown_signals import (
    generate_condition_signal,
    generate_cutoff_signal,
    generate_legendary_signal,
    generate_recommendation,
)
from maxpane_dashboard.data.cattown_cache import CatTownCache
from maxpane_dashboard.data.cattown_client import CatTownClient
from maxpane_dashboard.data.cattown_models import CatTownSnapshot

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "cattown_cache.json"


class CatTownManager:
    """Orchestrates Cat Town data fetching, caching, and analytics.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    """

    def __init__(self, poll_interval: int = 30) -> None:
        self.client = CatTownClient()
        self.cache = CatTownCache(max_history=120)
        self._poll_interval = poll_interval
        self._error_count = 0

        # Attempt to load persisted history on construction
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Fetch all data, update cache, compute analytics.

        Returns a flat dict with keys organized by dashboard widget:

        Hero metrics:
            ``kibble_price_usd``, ``kibble_change_24h``,
            ``competition_state``, ``top_fisher``.

        Leaderboard:
            ``competition_entries``.

        Sparklines:
            ``burn_rate_history``, ``fishing_volume_history``,
            ``prize_pool_history``.

        Signals:
            ``condition_signal``, ``legendary_signal``,
            ``competition_signal``, ``staking_signal``,
            ``kibble_signal``.

        Best plays:
            ``available_fish``, ``available_treasures``.

        Activity feed:
            ``recent_catches``.

        Meta:
            ``error_count``, ``last_updated_seconds_ago``,
            ``poll_interval``.
        """
        try:
            snapshot = await self.client.fetch_snapshot()
        except Exception:
            self._error_count += 1
            raise

        # Fetch raffle ticket count (non-critical, best-effort)
        raffle_total_tickets = 0
        try:
            raffle_total_tickets = await self.client.get_raffle_total_tickets()
        except Exception:
            pass

        # Derive leader weight from competition entries
        leader_weight = 0.0
        if snapshot.competition.entries:
            leader_weight = snapshot.competition.entries[0].fish_weight_kg

        self.cache.update(
            snapshot,
            leader_weight_kg=leader_weight,
            raffle_total_tickets=raffle_total_tickets,
        )
        now = snapshot.fetched_at

        # -- Current conditions -----------------------------------------------
        conditions = _safe_call(get_current_conditions, default={
            "time_of_day": "Unknown",
            "season": "Unknown",
            "weather": "Unknown",
        })

        # -- Competition state dict -------------------------------------------
        comp = snapshot.competition
        competition_timing = _safe_call(get_competition_timing, default={
            "is_active": False,
            "seconds_until_start": 0,
            "seconds_until_end": 0,
        })

        seconds_remaining = 0
        if comp.is_active and comp.end_time > 0:
            seconds_remaining = max(0, comp.end_time - int(now))
        elif competition_timing.get("is_active"):
            seconds_remaining = competition_timing.get("seconds_until_end", 0)

        competition_state = {
            "is_active": comp.is_active,
            "seconds_remaining": seconds_remaining,
            "end_time": comp.end_time,
            "prize_pool_kibble": comp.prize_pool_kibble,
            "total_volume_kibble": comp.total_volume_kibble,
            "treasure_pool_kibble": comp.treasure_pool_kibble,
            "staker_revenue_kibble": comp.staker_revenue_kibble,
            "num_participants": comp.num_participants,
            "week_number": comp.week_number,
        }

        # -- Parse display names from fisher_address field ------------------------
        # The API returns "display_name|address" format; RPC returns plain address.
        # Build a basename_map for activity feed resolution too.
        basename_map: dict[str, str] = {}

        def _parse_fisher(raw_addr: str) -> tuple[str, str]:
            """Split 'name|0xAddr' into (display_name, address)."""
            if "|" in raw_addr:
                name, addr = raw_addr.split("|", 1)
                if name:
                    basename_map[addr.lower()] = name
                return name, addr
            return "", raw_addr

        # -- Top fisher -------------------------------------------------------
        top_fisher: dict[str, Any] | None = None
        if comp.entries:
            top = comp.entries[0]
            name, addr = _parse_fisher(top.fisher_address)
            top_fisher = {
                "address": addr,
                "display_name": name,
                "weight_kg": top.fish_weight_kg,
                "species": top.fish_species,
            }

        # -- Competition entries as list of dicts ----------------------------
        competition_entries = []
        for e in comp.entries:
            name, addr = _parse_fisher(e.fisher_address)
            competition_entries.append({
                "fisher_address": addr,
                "display_name": name,
                "fish_weight_kg": e.fish_weight_kg,
                "fish_species": e.fish_species,
                "rarity": e.rarity,
                "rank": e.rank,
            })

        # Resolve basenames for activity feed addresses not already known
        feed_addrs = [
            c.fisher_address for c in snapshot.recent_catches
            if c.fisher_address.lower() not in basename_map
        ]
        # Deduplicate, limit to 15
        seen: set[str] = set()
        unique_feed: list[str] = []
        for a in feed_addrs:
            low = a.lower()
            if low not in seen:
                unique_feed.append(a)
                seen.add(low)
            if len(unique_feed) >= 15:
                break
        if unique_feed:
            try:
                extra = await self.client.resolve_basenames(unique_feed)
                for addr, name in extra.items():
                    if name:
                        basename_map[addr] = name
            except Exception:
                pass

        # -- Sparkline histories -----------------------------------------------
        prize_pool_history = self.cache.get_prize_pool_history()
        leader_weight_history = self.cache.get_leader_weight_history()
        raffle_tickets_history = self.cache.get_raffle_tickets_history()

        # -- Signals (3 signals + recommendation) --------------------------------
        _sig_default = {"label": "", "value_str": "--", "indicator": "", "color": "dim"}

        condition_signal = _safe_call(
            generate_condition_signal, conditions, default=_sig_default,
        )
        legendary_signal = _safe_call(
            generate_legendary_signal, conditions, default=_sig_default,
        )
        cutoff_signal = _safe_call(
            generate_cutoff_signal, competition_entries, comp.is_active,
            default=_sig_default,
        )
        recommendation = _safe_call(
            generate_recommendation, conditions, competition_entries,
            comp.is_active, seconds_remaining, comp.end_time,
            default="",
        )

        # -- Best plays --------------------------------------------------------
        available_fish = _safe_call(
            get_available_fish, conditions, default=[],
        )
        available_treasures = _safe_call(
            get_available_treasures, conditions, default=[],
        )

        # -- Recent catches as list of dicts -----------------------------------
        recent_catches = [
            {
                "tx_hash": c.tx_hash,
                "fisher_address": c.fisher_address,
                "display_name": basename_map.get(c.fisher_address.lower(), ""),
                "species": c.species,
                "weight_kg": c.weight_kg,
                "rarity": c.rarity,
                "timestamp": c.timestamp,
                "block_number": c.block_number,
            }
            for c in snapshot.recent_catches
        ]

        # -- Staleness ---------------------------------------------------------
        last_updated_seconds_ago = time.time() - snapshot.fetched_at

        # -- Assemble flat dict ------------------------------------------------
        return {
            # Hero metrics
            "kibble_price_usd": snapshot.kibble.price_usd,
            "kibble_change_24h": snapshot.kibble.price_change_24h,
            "competition_state": competition_state,
            "top_fisher": top_fisher,
            # Leaderboard
            "competition_entries": competition_entries,
            # Sparklines
            "prize_pool_history": prize_pool_history,
            "leader_weight_history": leader_weight_history,
            "raffle_tickets_history": raffle_tickets_history,
            # Signals
            "condition_signal": condition_signal,
            "legendary_signal": legendary_signal,
            "cutoff_signal": cutoff_signal,
            "recommendation": recommendation,
            # Best plays
            "available_fish": available_fish,
            "available_treasures": available_treasures,
            # Activity feed
            "recent_catches": recent_catches,
            # Meta
            "error_count": self._error_count,
            "last_updated_seconds_ago": last_updated_seconds_ago,
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
