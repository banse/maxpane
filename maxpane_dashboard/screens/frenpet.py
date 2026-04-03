"""FrenPetScreen -- FrenPet game dashboard (Overview-only mode)."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.frenpet_manager import FrenPetManager
from maxpane_dashboard.widgets.frenpet.overview import (
    FPBattleActivity,
    FPBestPlays,
    FPGameSignals,
    FPOverviewHero,
    FPOverviewLeaderboard,
    FPScoreTrends,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class FrenPetScreen(Screen):
    """FrenPet game dashboard (Overview only)."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(
        self,
        manager: FrenPetManager,
        poll_interval: int = 30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Static("FrenPet \u00b7 Overview", id="title-bar")
        yield FPOverviewHero()
        with Horizontal(id="middle-row"):
            yield FPOverviewLeaderboard()
            with Vertical(id="right-col"):
                yield FPScoreTrends()
                yield FPGameSignals()
        yield Static("\u2500" * 300, id="separator")
        with Horizontal(id="bottom-row"):
            yield FPBattleActivity()
            yield FPBestPlays()
        yield StatusBar()

    def on_screen_resume(self) -> None:
        """Start polling when this screen is active."""
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("frenpet")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        """Stop polling when switching away."""
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        """Trigger an immediate refresh when the screen appears."""
        self.run_worker(self._do_refresh(), exclusive=True, name="frenpet-refresh")

    def _schedule_refresh(self) -> None:
        """Schedule a refresh via a worker so it runs async."""
        self.run_worker(self._do_refresh(), exclusive=True, name="frenpet-refresh")

    async def _do_refresh(self) -> None:
        """Fetch data and update all overview widgets."""
        try:
            data = await self._manager.fetch_and_compute()
        except Exception as exc:
            logger.error("FrenPet refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=self._manager._error_count,
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        top_pets = data.get("top_pets", [])

        # Title bar
        try:
            title = self.query_one("#title-bar", Static)
            population_stats = data.get("population_stats", {})
            total = population_stats.get("total_pets", 0)
            active = population_stats.get("active_pets", 0)
            if total:
                title.update(
                    f"FrenPet \u00b7 Overview \u00b7 {active}/{total} active"
                )
            else:
                title.update("FrenPet \u00b7 Overview")
        except Exception:
            pass

        # Hero metrics
        try:
            fp_reward_pool = data.get("fp_reward_pool", 0.0)
            game_start_ts = data.get("game_start_timestamp", 1709251200)
            leader_pet = data.get("top_pet") or (top_pets[0] if top_pets else None)
            self.query_one(FPOverviewHero).update_data(
                fp_reward_pool=fp_reward_pool,
                game_start_timestamp=game_start_ts,
                top_pet=leader_pet,
            )
        except Exception as exc:
            logger.warning("Failed to update FPOverviewHero: %s", exc)

        # Leaderboard
        try:
            self.query_one(FPOverviewLeaderboard).update_data(top_pets)
        except Exception as exc:
            logger.warning("Failed to update FPOverviewLeaderboard: %s", exc)

        # Score trends (population-level sparklines)
        try:
            score_histories = data.get("overview_score_histories", {})
            self.query_one(FPScoreTrends).update_data(
                top_pets=top_pets,
                score_histories=score_histories,
                active_pets_history=data.get("active_pets_history"),
                total_score_history=data.get("total_score_history"),
                battle_rate_history=data.get("battle_rate_history"),
            )
        except Exception as exc:
            logger.warning("Failed to update FPScoreTrends: %s", exc)

        # Game signals
        try:
            self.query_one(FPGameSignals).update_data(
                battle_rate=data.get("global_battle_rate", 0.0),
                win_rate=data.get("global_win_rate", 50.0),
                hibernation_rate=data.get("hibernation_rate", 0.0),
                dominance=data.get("top_dominance", 1.0),
                recommendation=data.get("overview_recommendation", ""),
            )
        except Exception as exc:
            logger.warning("Failed to update FPGameSignals: %s", exc)

        # Battle activity
        try:
            self.query_one(FPBattleActivity).update_data(
                recent_attacks=data.get("recent_attacks", []),
                pet_names=data.get("pet_names"),
            )
        except Exception as exc:
            logger.warning("Failed to update FPBattleActivity: %s", exc)

        # Best plays
        try:
            self.query_one(FPBestPlays).update_data(
                top_earners=data.get("top_earners", []),
                rising_stars=data.get("rising_stars", []),
            )
        except Exception as exc:
            logger.warning("Failed to update FPBestPlays: %s", exc)

        # Status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.warning("Failed to update StatusBar: %s", exc)

    def action_refresh(self) -> None:
        """Immediate refresh triggered by the 'r' keybinding."""
        self.run_worker(self._do_refresh(), exclusive=True, name="frenpet-refresh")
