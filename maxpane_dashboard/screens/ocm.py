"""OCMScreen -- Onchain Monsters collection analytics dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.widgets.ocm import (
    OCMActivityFeed,
    OCMHeroMetrics,
    OCMSignals,
    OCMSparklines,
    OCMStakingOverview,
    OCMSupplyBreakdown,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class OCMScreen(Screen):
    """Onchain Monsters collection analytics dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def __init__(self, manager: OCMManager, poll_interval: int = 60, name: str = "ocm", **kwargs):
        super().__init__(name=name, **kwargs)
        self._manager = manager
        self._poll_interval = poll_interval
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield Static(
            "Onchain Monsters \u00b7 Collection Analytics",
            id="title-bar",
        )

        yield OCMHeroMetrics()

        with Horizontal(id="middle-row"):
            yield OCMStakingOverview()
            with Vertical(id="right-col"):
                yield OCMSparklines()
                yield OCMSignals()

        yield Static("\u2500" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield OCMActivityFeed()
            yield OCMSupplyBreakdown()

        yield StatusBar()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("onchain monsters")
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ocm-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ocm-refresh")

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

        # Hero metrics
        try:
            self.query_one(OCMHeroMetrics).update_data(
                total_supply=data.get("total_supply"),
                minted_pct=data.get("minted_pct"),
                total_staked=data.get("total_staked"),
                staking_ratio=data.get("staking_ratio"),
                current_minting_cost_ocmd=data.get("current_minting_cost_ocmd"),
            )
        except Exception as exc:
            logger.debug("Failed to update OCMHeroMetrics: %s", exc)

        # Staking overview
        try:
            self.query_one(OCMStakingOverview).update_data(
                total_staked=data.get("total_staked"),
                net_supply=data.get("net_supply"),
                staking_ratio=data.get("staking_ratio"),
                ocmd_total_supply=data.get("ocmd_total_supply"),
                daily_emission=data.get("daily_emission"),
                days_to_earn_mint=data.get("days_to_earn_mint"),
                burned_count=data.get("burned_count"),
                remaining=data.get("remaining"),
                faucet_open=data.get("faucet_open", True),
                time_to_next_tier=data.get("time_to_next_tier", ""),
            )
        except Exception as exc:
            logger.debug("Failed to update OCMStakingOverview: %s", exc)

        # Sparklines
        try:
            self.query_one(OCMSparklines).update_data(
                supply_history=data.get("supply_history"),
                staked_history=data.get("staked_history"),
                ocmd_supply_history=data.get("ocmd_supply_history"),
            )
        except Exception as exc:
            logger.debug("Failed to update OCMSparklines: %s", exc)

        # Signals
        try:
            self.query_one(OCMSignals).update_data(
                staking_signal=data.get("staking_signal"),
                mint_velocity_signal=data.get("mint_velocity_signal"),
                burn_rate_signal=data.get("burn_rate_signal"),
                recommendation=data.get("recommendation", ""),
            )
        except Exception as exc:
            logger.debug("Failed to update OCMSignals: %s", exc)

        # Activity feed
        try:
            self.query_one(OCMActivityFeed).update_data(
                recent_events=data.get("recent_events"),
            )
        except Exception as exc:
            logger.debug("Failed to update OCMActivityFeed: %s", exc)

        # Supply breakdown
        try:
            self.query_one(OCMSupplyBreakdown).update_data(
                total_supply=data.get("total_supply"),
                burned_count=data.get("burned_count"),
                net_supply=data.get("net_supply"),
                remaining=data.get("remaining"),
                minted_pct=data.get("minted_pct"),
                recent_mints=data.get("recent_mints", 0),
                recent_burns=data.get("recent_burns", 0),
            )
        except Exception as exc:
            logger.debug("Failed to update OCMSupplyBreakdown: %s", exc)

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
        self.run_worker(self._do_refresh(), exclusive=True, name="ocm-refresh")
