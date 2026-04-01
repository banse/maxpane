"""CatTownScreen -- Cat Town Fishing game dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.cattown_manager import CatTownManager
from maxpane_dashboard.widgets.cattown import (
    CTActivityFeed,
    CTBestPlays,
    CTHeroMetrics,
    CTLeaderboard,
    CTSignals,
    CTSparklines,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class CatTownScreen(Screen):
    """Cat Town Fishing game dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, data_manager: CatTownManager, poll_interval: int, **kwargs):
        super().__init__(**kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Static(
            "Cat Town Fishing \u00b7 Competition",
            id="title-bar",
        )

        yield CTHeroMetrics()

        with Horizontal(id="middle-row"):
            yield CTLeaderboard()
            with Vertical(id="right-col"):
                yield CTSparklines()
                yield CTSignals()

        yield Static("\u2500" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield CTActivityFeed()
            yield CTBestPlays()

        yield StatusBar()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("cat town fishing")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="cattown-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="cattown-refresh")

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.debug("Refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Title bar
        try:
            title = self.query_one("#title-bar", Static)
            comp = data.get("competition_state", {})
            if comp and comp.get("is_active"):
                participants = comp.get("num_participants", 0)
                suffix = f"Competition LIVE \u00b7 {participants} fishers"
            else:
                suffix = "Competition"
            title.update(f"Cat Town Fishing \u00b7 {suffix}")
        except Exception:
            pass

        # Hero metrics
        try:
            self.query_one(CTHeroMetrics).update_data(
                competition_state=data.get("competition_state"),
                top_fisher=data.get("top_fisher"),
            )
        except Exception as exc:
            logger.debug("Failed to update CTHeroMetrics: %s", exc)

        # Leaderboard
        try:
            self.query_one(CTLeaderboard).update_data(
                competition_entries=data.get("competition_entries"),
            )
        except Exception as exc:
            logger.debug("Failed to update CTLeaderboard: %s", exc)

        # Sparklines
        try:
            self.query_one(CTSparklines).update_data(
                prize_pool_history=data.get("prize_pool_history"),
                leader_weight_history=data.get("leader_weight_history"),
                raffle_tickets_history=data.get("raffle_tickets_history"),
            )
        except Exception as exc:
            logger.debug("Failed to update CTSparklines: %s", exc)

        # Signals
        try:
            self.query_one(CTSignals).update_data(
                condition_signal=data.get("condition_signal"),
                legendary_signal=data.get("legendary_signal"),
                cutoff_signal=data.get("cutoff_signal"),
                recommendation=data.get("recommendation", ""),
            )
        except Exception as exc:
            logger.debug("Failed to update CTSignals: %s", exc)

        # Activity feed
        try:
            self.query_one(CTActivityFeed).update_data(
                recent_catches=data.get("recent_catches"),
            )
        except Exception as exc:
            logger.debug("Failed to update CTActivityFeed: %s", exc)

        # Best plays
        try:
            self.query_one(CTBestPlays).update_data(
                available_fish=data.get("available_fish"),
                available_treasures=data.get("available_treasures"),
            )
        except Exception as exc:
            logger.debug("Failed to update CTBestPlays: %s", exc)

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
        self.run_worker(self._do_refresh(), exclusive=True, name="cattown-refresh")
