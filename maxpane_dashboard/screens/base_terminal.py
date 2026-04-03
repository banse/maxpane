"""BaseTerminalScreen -- Base chain overview dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.base_manager import BaseManager
from maxpane_dashboard.widgets.base.overview import (
    BTOverviewHero,
    BTOverviewLeaderboard,
    BTSparklines,
    BTSignals,
    BTActivityFeed,
    BTBestPlays,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class BaseTerminalScreen(Screen):
    """Base chain overview dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, manager: BaseManager, poll_interval: int = 30, **kwargs):
        super().__init__(**kwargs)
        self._manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Static(
            "BASE TERMINAL \u00b7 $ETH ...",
            id="title-bar",
        )

        yield BTOverviewHero()

        with Horizontal(id="middle-row"):
            yield BTOverviewLeaderboard()
            with Vertical(id="right-col"):
                yield BTSparklines()
                yield BTSignals()

        yield Static("\u2500" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield BTActivityFeed()
            yield BTBestPlays()

        yield StatusBar()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("base terminal")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="base-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="base-refresh")

    async def _do_refresh(self) -> None:
        try:
            data = await self._manager.fetch_and_compute()
        except Exception as exc:
            logger.error("Base Terminal refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=0,
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Title bar
        eth_price = data.get("eth_price", "...")
        gas_price = data.get("gas_price", "...")
        try:
            title = self.query_one("#title-bar", Static)
            title.update(
                f"BASE TERMINAL \u00b7 $ETH {eth_price} \u00b7 Gas {gas_price}"
            )
        except Exception:
            pass

        # Hero metrics
        try:
            self.query_one(BTOverviewHero).update_data(
                eth_price=data.get("eth_price"),
                eth_change_24h=data.get("eth_change_24h"),
                total_volume=data.get("total_volume"),
                top_gainer_name=data.get("top_gainer_name"),
                top_gainer_pct=data.get("top_gainer_pct"),
            )
        except Exception as exc:
            logger.warning("Failed to update BTOverviewHero: %s", exc)

        # Leaderboard
        try:
            self.query_one(BTOverviewLeaderboard).update_data(
                trending_tokens=data.get("trending_tokens", []),
            )
        except Exception as exc:
            logger.warning("Failed to update BTOverviewLeaderboard: %s", exc)

        # Sparklines
        try:
            self.query_one(BTSparklines).update_data(
                volume_history=data.get("volume_history"),
                eth_price_history=data.get("eth_price_history"),
                trade_count_history=data.get("trade_count_history"),
            )
        except Exception as exc:
            logger.warning("Failed to update BTSparklines: %s", exc)

        # Signals
        try:
            self.query_one(BTSignals).update_data(
                buy_sell_signal=data.get("buy_sell_signal"),
                volume_signal=data.get("volume_signal"),
                whale_signal=data.get("whale_signal"),
                recommendation=data.get("recommendation", ""),
            )
        except Exception as exc:
            logger.warning("Failed to update BTSignals: %s", exc)

        # Activity feed
        try:
            self.query_one(BTActivityFeed).update_data(
                whale_trades=data.get("whale_trades"),
            )
        except Exception as exc:
            logger.warning("Failed to update BTActivityFeed: %s", exc)

        # Best plays
        try:
            self.query_one(BTBestPlays).update_data(
                gainers=data.get("gainers"),
                losers=data.get("losers"),
            )
        except Exception as exc:
            logger.warning("Failed to update BTBestPlays: %s", exc)

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
        self.run_worker(self._do_refresh(), exclusive=True, name="base-refresh")
