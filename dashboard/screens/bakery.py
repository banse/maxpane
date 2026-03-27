"""BakeryScreen -- RugPull Bakery game dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from dashboard.data.manager import DataManager
from dashboard.widgets.hero_metrics import HeroMetrics
from dashboard.widgets.leaderboard import Leaderboard
from dashboard.widgets.cookie_chart import CookieChart
from dashboard.widgets.activity_feed import ActivityFeed
from dashboard.widgets.signals_panel import SignalsPanel
from dashboard.widgets.ev_table import EVTable
from dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class BakeryScreen(Screen):
    """RugPull Bakery game dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, data_manager: DataManager, poll_interval: int, **kwargs):
        super().__init__(**kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        # Title bar
        yield Static(
            "RugPull Bakery \u00b7 Season ?",
            id="title-bar",
        )

        # Hero metrics row
        yield HeroMetrics()

        # Middle row: leaderboard (left) | cookie chart + signals (right)
        with Horizontal(id="middle-row"):
            yield Leaderboard()
            with Vertical(id="right-col"):
                yield CookieChart()
                yield SignalsPanel()

        # Dashed separator
        yield Static(
            "\u2500" * 300,
            id="separator",
        )

        # Bottom row: activity feed (left) | EV table (right)
        with Horizontal(id="bottom-row"):
            yield ActivityFeed()
            yield EVTable()

        # Status bar
        yield StatusBar()

    def on_screen_resume(self) -> None:
        """Start polling when this screen is active."""
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        # Update status bar with current theme name
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("rugpull bakery")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        """Stop polling when switching away."""
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        """Trigger an immediate refresh when the screen appears."""
        self.run_worker(self._do_refresh(), exclusive=True, name="bakery-refresh")

    def _schedule_refresh(self) -> None:
        """Schedule a refresh via a worker so it runs async."""
        self.run_worker(self._do_refresh(), exclusive=True, name="bakery-refresh")

    async def _do_refresh(self) -> None:
        """Fetch data and update all widgets."""
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.error("Refresh failed: %s", exc)
            # Update status bar to reflect the error
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=self._data_manager._error_count,
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Update title bar with season
        try:
            title = self.query_one("#title-bar", Static)
            title.update(
                f"RugPull Bakery \u00b7 Season {data['season_id']}"
            )
        except Exception:
            pass

        # Update hero metrics
        try:
            self.query_one(HeroMetrics).update_data(
                prize_pool_eth=data["prize_pool_eth"],
                prize_pool_usd=data["prize_pool_usd"],
                hours_remaining=data["hours_remaining"],
                season_id=data["season_id"],
                season_active=data["season_active"],
                leader_name=data["leader_name"],
                leader_cookies=data["leader_cookies"],
                leader_rate=data["leader_rate"],
            )
        except Exception as exc:
            logger.warning("Failed to update HeroMetrics: %s", exc)

        # Update leaderboard
        try:
            self.query_one(Leaderboard).update_data(
                bakeries=data["bakeries"],
                production_rates=data["production_rates"],
                prize_pool_usd=data["prize_pool_usd"],
            )
        except Exception as exc:
            logger.warning("Failed to update Leaderboard: %s", exc)

        # Update cookie chart
        try:
            self.query_one(CookieChart).update_data(
                histories=data["chart_histories"],
            )
        except Exception as exc:
            logger.warning("Failed to update CookieChart: %s", exc)

        # Update activity feed
        try:
            self.query_one(ActivityFeed).update_data(
                events=data["events"],
            )
        except Exception as exc:
            logger.warning("Failed to update ActivityFeed: %s", exc)

        # Update signals panel
        try:
            self.query_one(SignalsPanel).update_data(
                late_join_ev=data["late_join_ev"],
                gap_analysis=data["gap_analysis"],
                dominance=data["dominance"],
                recommendation=data["recommendation"],
            )
        except Exception as exc:
            logger.warning("Failed to update SignalsPanel: %s", exc)

        # Update EV table
        try:
            self.query_one(EVTable).update_data(
                boost_rankings=data["boost_rankings"],
                attack_rankings=data["attack_rankings"],
            )
        except Exception as exc:
            logger.warning("Failed to update EVTable: %s", exc)

        # Update status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=data["last_updated_seconds_ago"],
                error_count=data["error_count"],
                poll_interval=data["poll_interval"],
            )
        except Exception as exc:
            logger.warning("Failed to update StatusBar: %s", exc)

    def action_refresh(self) -> None:
        """Immediate refresh triggered by the 'r' keybinding."""
        self.run_worker(self._do_refresh(), exclusive=True, name="bakery-refresh")
