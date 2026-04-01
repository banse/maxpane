"""DOTAScreen -- Defense of the Agents game dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.dota_manager import DOTAManager
from maxpane_dashboard.widgets.dota import (
    DOTAActivityFeed,
    DOTABestPlays,
    DOTAHeroMetrics,
    DOTALeaderboard,
    DOTASignals,
    DOTASparklines,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class DOTAScreen(Screen):
    """Defense of the Agents game dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, manager: DOTAManager, poll_interval: int = 30, name: str = "dota", **kwargs):
        super().__init__(name=name, **kwargs)
        self._manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Static(
            "Defense of the Agents \u00b7 Game #1 \u00b7 Tick ---",
            id="title-bar",
        )

        yield DOTAHeroMetrics()

        with Horizontal(id="dota-middle-row"):
            yield DOTALeaderboard()
            with Vertical(id="dota-right-col"):
                yield DOTASparklines()
                yield DOTASignals()

        yield Static("\u2500" * 300, id="dota-separator")

        with Horizontal(id="dota-bottom-row"):
            yield DOTAActivityFeed()
            yield DOTABestPlays()

        yield StatusBar()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("defense of the agents")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="dota-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="dota-refresh")

    async def _do_refresh(self) -> None:
        try:
            data = await self._manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("Refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=getattr(self._manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Title bar
        try:
            title = self.query_one("#title-bar", Static)
            game_number = data.get("game_number", 1)
            tick = data.get("tick", 0)
            winner = data.get("winner")
            if winner:
                title.update(
                    f"Defense of the Agents \u00b7 Game #{game_number} \u00b7 GAME OVER"
                )
            else:
                title.update(
                    f"Defense of the Agents \u00b7 Game #{game_number} \u00b7 Tick {tick}"
                )
        except Exception:
            pass

        # Hero metrics
        try:
            self.query_one(DOTAHeroMetrics).update_data(
                winning_faction=data.get("winning_faction", "tied"),
                human_base_hp=data.get("human_base_hp", 0),
                orc_base_hp=data.get("orc_base_hp", 0),
                base_max_hp=data.get("base_max_hp", 0),
                winner=data.get("winner"),
                token_price_usd=data.get("token_price_usd"),
                token_price_change_24h=data.get("token_price_change_24h"),
                token_market_cap=data.get("token_market_cap"),
                top_player_name=data.get("top_player_name", ""),
                top_player_wins=data.get("top_player_wins", 0),
                top_player_win_rate=data.get("top_player_win_rate", 0.0),
            )
        except Exception as exc:
            logger.debug("Failed to update DOTAHeroMetrics: %s", exc)

        # Leaderboard
        try:
            self.query_one(DOTALeaderboard).update_data(
                leaderboard=data.get("leaderboard"),
            )
        except Exception as exc:
            logger.debug("Failed to update DOTALeaderboard: %s", exc)

        # Sparklines
        try:
            self.query_one(DOTASparklines).update_data(
                top_frontline_history=data.get("top_frontline_history"),
                mid_frontline_history=data.get("mid_frontline_history"),
                bot_frontline_history=data.get("bot_frontline_history"),
            )
        except Exception as exc:
            logger.debug("Failed to update DOTASparklines: %s", exc)

        # Signals
        try:
            self.query_one(DOTASignals).update_data(
                faction_balance_signal=data.get("faction_balance_signal"),
                lane_pressure_signal=data.get("lane_pressure_signal"),
                hero_advantage_signal=data.get("hero_advantage_signal"),
                recommendation=data.get("recommendation", ""),
            )
        except Exception as exc:
            logger.debug("Failed to update DOTASignals: %s", exc)

        # Activity feed (hero roster)
        try:
            self.query_one(DOTAActivityFeed).update_data(
                heroes=data.get("heroes"),
            )
        except Exception as exc:
            logger.debug("Failed to update DOTAActivityFeed: %s", exc)

        # Best plays
        try:
            self.query_one(DOTABestPlays).update_data(
                heroes_by_level=data.get("heroes_by_level"),
                heroes_by_abilities=data.get("heroes_by_abilities"),
            )
        except Exception as exc:
            logger.debug("Failed to update DOTABestPlays: %s", exc)

        # Status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data.get("last_updated_seconds_ago", 0),
                error_count=data.get("error_count", 0),
                poll_interval=data.get("poll_interval", self._poll_interval),
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)

    def action_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="dota-refresh")
