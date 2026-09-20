"""BaseTerminalScreen -- Base chain overview dashboard as a Textual Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.base.overview import (
    BTOverviewHero,
    BTOverviewLeaderboard,
    BTSparklines,
    BTSignals,
    BTActivityFeed,
    BTBestPlays,
)
from maxpane_dashboard.widgets.status_bar import StatusBar


class BaseTerminalScreen(DashboardScreen):
    """Base chain overview dashboard."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "base terminal"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "base-refresh"

    #: Transcribed from the six hand-written dispatch blocks, default for
    #: default; the status bar is updated by the base.
    PANELS = (
        (
            BTOverviewHero,
            keys(
                "eth_price",
                "eth_change_24h",
                "total_volume",
                "top_gainer_name",
                "top_gainer_pct",
            ),
        ),
        (BTOverviewLeaderboard, keys("trending_tokens", trending_tokens=[])),
        (
            BTSparklines,
            keys("volume_history", "eth_price_history", "trade_count_history"),
        ),
        (
            BTSignals,
            keys(
                "buy_sell_signal",
                "volume_signal",
                "whale_signal",
                "recommendation",
                recommendation="",
            ),
        ),
        (BTActivityFeed, keys("whale_trades")),
        (BTBestPlays, keys("gainers", "losers")),
    )

    def compose(self) -> ComposeResult:
        yield Static(
            "BASE TERMINAL · $ETH ...",
            id="title-bar",
        )

        yield BTOverviewHero()

        with Horizontal(id="middle-row"):
            yield BTOverviewLeaderboard()
            with Vertical(id="right-col"):
                yield BTSparklines()
                yield BTSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield BTActivityFeed()
            yield BTBestPlays()

        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        eth_price = data.get("eth_price", "...")
        gas_price = data.get("gas_price", "...")
        title = self.query_one("#title-bar", Static)
        title.update(
            f"BASE TERMINAL · $ETH {eth_price} · Gas {gas_price}"
        )
