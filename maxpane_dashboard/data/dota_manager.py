"""Orchestrates DOTA data fetching, caching, and analytics computation.

The ``DOTAManager`` is the single coordination point between the async
HTTP client, the time-series cache, and the analytics modules.  It exposes
one public coroutine -- ``fetch_and_compute()`` -- that returns a flat dict
ready for widget consumption.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.dota_cache import DOTACache
from maxpane_dashboard.data.dota_client import DOTAClient
from maxpane_dashboard.data.dota_models import DOTASnapshot

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".maxpane"
_CACHE_FILE = _CACHE_DIR / "dota_cache.json"

# Leaderboard is polled every Nth cycle to avoid hammering the API
_LEADERBOARD_POLL_INTERVAL = 5


class DOTAManager:
    """Orchestrates Defense of the Agents data fetching, caching, and analytics.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes (used for status display).
    """

    def __init__(self, poll_interval: int = 30) -> None:
        self.client = DOTAClient()
        self.cache = DOTACache(max_history=120)
        self._poll_interval = poll_interval
        self._error_count = 0
        self._cycle_count: int = 0
        self._last_leaderboard: list[dict[str, Any]] = []

        # Ensure cache directory exists
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Attempt to load persisted history on construction
        self.cache.load_from_file(str(_CACHE_FILE))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Fetch all data, update cache, compute analytics.

        Returns a flat dict with keys organized by dashboard widget.
        """
        self._cycle_count += 1

        # -- Fetch game state and token price every cycle --------------------
        try:
            game_state = await self.client.fetch_game_state()
        except Exception as exc:
            logger.warning("DOTA game state fetch failed: %s", exc)
            self._error_count += 1
            game_state = None

        token_price_usd: float | None = None
        token_price_change_24h: float | None = None
        token_market_cap: float | None = None
        try:
            token_price_usd, token_price_change_24h, token_market_cap = (
                await self.client.fetch_token_price()
            )
        except Exception as exc:
            logger.debug("DOTA token price fetch failed: %s", exc)

        # -- Fetch leaderboard every Nth cycle -------------------------------
        if self._cycle_count % _LEADERBOARD_POLL_INTERVAL == 1 or not self._last_leaderboard:
            try:
                lb_entries = await self.client.fetch_leaderboard()
                self._last_leaderboard = [
                    {
                        "rank": e.rank,
                        "name": e.name,
                        "wins": e.wins,
                        "games": e.games,
                        "win_rate": e.win_rate,
                        "player_type": e.player_type,
                    }
                    for e in lb_entries
                ]
            except Exception as exc:
                logger.warning("DOTA leaderboard fetch failed: %s", exc)

        # -- Build snapshot and update cache ---------------------------------
        snapshot = DOTASnapshot(
            fetched_at=time.time(),
            game_state=game_state,
            leaderboard=[],  # raw entries not needed in snapshot for cache
            token_price_usd=token_price_usd,
            token_price_change_24h=token_price_change_24h,
        )
        self.cache.update(snapshot)

        # -- Extract game state values ---------------------------------------
        tick = 0
        game_number = 1
        winner: str | None = None
        human_base_hp = 0
        orc_base_hp = 0
        base_max_hp = 0
        lanes_data: dict[str, Any] = {}
        heroes_raw: list[Any] = []
        towers_raw: list[Any] = []

        if game_state is not None:
            tick = game_state.tick
            winner = game_state.winner
            lanes_data = game_state.lanes
            heroes_raw = game_state.heroes
            towers_raw = game_state.towers

            # Base HPs
            if "human" in game_state.bases:
                human_base_hp = game_state.bases["human"].hp
                base_max_hp = game_state.bases["human"].max_hp
            if "orc" in game_state.bases:
                orc_base_hp = game_state.bases["orc"].hp
                if base_max_hp == 0:
                    base_max_hp = game_state.bases["orc"].max_hp

        # -- Winning faction from base HPs -----------------------------------
        if winner:
            winning_faction = winner
        elif human_base_hp > orc_base_hp:
            winning_faction = "human"
        elif orc_base_hp > human_base_hp:
            winning_faction = "orc"
        else:
            winning_faction = "tied"

        # -- Lane values for signals -----------------------------------------
        top_fl = lanes_data["top"].frontline if "top" in lanes_data else 0
        mid_fl = lanes_data["mid"].frontline if "mid" in lanes_data else 0
        bot_fl = lanes_data["bot"].frontline if "bot" in lanes_data else 0

        total_human_units = sum(
            lane.human for lane in lanes_data.values()
        ) if lanes_data else 0
        total_orc_units = sum(
            lane.orc for lane in lanes_data.values()
        ) if lanes_data else 0

        # -- Hero counts per faction -----------------------------------------
        human_alive = sum(
            1 for h in heroes_raw if h.faction == "human" and h.alive
        )
        orc_alive = sum(
            1 for h in heroes_raw if h.faction == "orc" and h.alive
        )

        # -- Signals (import with fallback) ----------------------------------
        _sig_default = {
            "label": "",
            "value_str": "--",
            "indicator": "",
            "color": "dim",
        }

        faction_balance_signal = _sig_default
        lane_pressure_signal = _sig_default
        hero_advantage_signal = _sig_default
        recommendation = "Awaiting game data..."

        try:
            from maxpane_dashboard.analytics.dota_signals import (
                compute_faction_balance,
                compute_hero_advantage,
                compute_lane_pressure,
                generate_recommendation,
            )

            faction_balance_signal = _safe_call(
                compute_faction_balance,
                total_human_units,
                total_orc_units,
                default=_sig_default,
            )
            lane_pressure_signal = _safe_call(
                compute_lane_pressure,
                top_fl,
                mid_fl,
                bot_fl,
                default=_sig_default,
            )
            hero_advantage_signal = _safe_call(
                compute_hero_advantage,
                human_alive,
                orc_alive,
                default=_sig_default,
            )
            avg_frontline = (top_fl + mid_fl + bot_fl) / 3.0
            recommendation = _safe_call(
                generate_recommendation,
                total_human_units,
                total_orc_units,
                avg_frontline,
                human_alive,
                orc_alive,
                human_base_hp,
                orc_base_hp,
                base_max_hp,
                winner,
                default="Awaiting game data...",
            )
        except ImportError as exc:
            logger.debug("DOTA signals module not available: %s", exc)

        # -- Heroes by level (top 10, descending) ----------------------------
        heroes_by_level: list[tuple[str, int]] = sorted(
            [(h.name, h.level) for h in heroes_raw],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        # -- Heroes by ability count (top 10, descending) --------------------
        heroes_by_abilities: list[tuple[str, int]] = sorted(
            [(h.name, len(h.abilities)) for h in heroes_raw],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        # -- Heroes as list of dicts for activity feed roster ----------------
        heroes: list[dict[str, Any]] = [
            {
                "name": h.name,
                "faction": h.faction,
                "hero_class": h.hero_class,
                "lane": h.lane,
                "hp": h.hp,
                "max_hp": h.max_hp,
                "alive": h.alive,
                "level": h.level,
                "xp": h.xp,
                "xp_to_next": h.xp_to_next,
                "abilities": [
                    {"id": a.id, "level": a.level} for a in h.abilities
                ],
            }
            for h in heroes_raw
        ]

        # -- Top player from leaderboard ------------------------------------
        top_player_name = ""
        top_player_wins = 0
        top_player_win_rate = 0.0

        if self._last_leaderboard:
            top = self._last_leaderboard[0]
            top_player_name = top.get("name", "")
            top_player_wins = top.get("wins", 0)
            top_player_win_rate = top.get("win_rate", 0.0)

        # -- Sparkline histories from cache ----------------------------------
        top_frontline_history = self.cache.get_top_history()
        mid_frontline_history = self.cache.get_mid_history()
        bot_frontline_history = self.cache.get_bot_history()

        # -- Staleness -------------------------------------------------------
        last_updated_seconds_ago = time.time() - snapshot.fetched_at

        # -- Assemble flat dict ----------------------------------------------
        return {
            # Game state
            "tick": tick,
            "game_number": game_number,
            "winner": winner,
            "winning_faction": winning_faction,
            "human_base_hp": human_base_hp,
            "orc_base_hp": orc_base_hp,
            "base_max_hp": base_max_hp,
            # Token
            "token_price_usd": token_price_usd,
            "token_price_change_24h": token_price_change_24h,
            "token_market_cap": token_market_cap,
            # Leaderboard
            "top_player_name": top_player_name,
            "top_player_wins": top_player_wins,
            "top_player_win_rate": top_player_win_rate,
            "leaderboard": self._last_leaderboard,
            # Sparklines
            "top_frontline_history": top_frontline_history,
            "mid_frontline_history": mid_frontline_history,
            "bot_frontline_history": bot_frontline_history,
            # Signals
            "faction_balance_signal": faction_balance_signal,
            "lane_pressure_signal": lane_pressure_signal,
            "hero_advantage_signal": hero_advantage_signal,
            "recommendation": recommendation,
            # Heroes
            "heroes": heroes,
            "heroes_by_level": heroes_by_level,
            "heroes_by_abilities": heroes_by_abilities,
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
