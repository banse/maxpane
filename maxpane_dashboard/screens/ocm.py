"""OCMScreen -- Onchain Monsters collection analytics dashboard as a Textual Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.ocm import (
    OCMActivityFeed,
    OCMHeroMetrics,
    OCMSignals,
    OCMSparklines,
    OCMStakingOverview,
    OCMSupplyBreakdown,
)
from maxpane_dashboard.widgets.status_bar import StatusBar


class OCMScreen(DashboardScreen):
    """Onchain Monsters collection analytics dashboard.

    Lifecycle and dispatch come from
    :class:`~maxpane_dashboard.screens.dashboard_screen.DashboardScreen`; this
    screen only declares its words, its worker name, its panels and its layout.
    It has no title logic, so it sets no ``_update_title``.
    """

    #: The status bar's words for this dashboard.
    GAME_NAME = "onchain monsters"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "ocm-refresh"

    #: Transcribed from the six hand-written dispatch blocks this screen used
    #: to carry, default for default; the status bar is updated by the base.
    PANELS = (
        (
            OCMHeroMetrics,
            keys(
                "total_supply",
                "minted_pct",
                "total_staked",
                "staking_ratio",
                "current_minting_cost_ocmd",
            ),
        ),
        (
            OCMStakingOverview,
            keys(
                "total_staked",
                "net_supply",
                "staking_ratio",
                "ocmd_total_supply",
                "daily_emission",
                "days_to_earn_mint",
                "burned_count",
                "remaining",
                "faucet_open",
                "time_to_next_tier",
                faucet_open=True,
                time_to_next_tier="",
            ),
        ),
        (
            OCMSparklines,
            keys("supply_history", "staked_history", "ocmd_supply_history"),
        ),
        (
            OCMSignals,
            keys(
                "staking_signal",
                "mint_velocity_signal",
                "burn_rate_signal",
                "recommendation",
                recommendation="",
            ),
        ),
        (OCMActivityFeed, keys("recent_events")),
        (
            OCMSupplyBreakdown,
            keys(
                "total_supply",
                "burned_count",
                "net_supply",
                "remaining",
                "minted_pct",
                "recent_mints",
                "recent_burns",
                recent_mints=0,
                recent_burns=0,
            ),
        ),
    )

    def compose(self) -> ComposeResult:
        yield Static(
            "Onchain Monsters · Collection Analytics",
            id="title-bar",
        )

        yield OCMHeroMetrics()

        with Horizontal(id="middle-row"):
            yield OCMStakingOverview()
            with Vertical(id="right-col"):
                yield OCMSparklines()
                yield OCMSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield OCMActivityFeed()
            yield OCMSupplyBreakdown()

        yield StatusBar()
