"""DOTAScreen -- Defense of the Agents game dashboard as a Textual Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.dota import (
    DOTAActivityFeed,
    DOTABestPlays,
    DOTAHeroMetrics,
    DOTALeaderboard,
    DOTASignals,
    DOTASparklines,
)
from maxpane_dashboard.widgets.status_bar import StatusBar


class DOTAScreen(DashboardScreen):
    """Defense of the Agents game dashboard."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "defense of the agents"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "dota-refresh"

    #: Transcribed from the six hand-written dispatch blocks, default for
    #: default; the status bar is updated by the base.
    PANELS = (
        (
            DOTAHeroMetrics,
            keys(
                "winning_faction",
                "human_base_hp",
                "orc_base_hp",
                "base_max_hp",
                "winner",
                "token_price_usd",
                "token_price_change_24h",
                "token_market_cap",
                "top_player_name",
                "top_player_wins",
                "top_player_win_rate",
                winning_faction="tied",
                human_base_hp=0,
                orc_base_hp=0,
                base_max_hp=0,
                top_player_name="",
                top_player_wins=0,
                top_player_win_rate=0.0,
            ),
        ),
        (DOTALeaderboard, keys("leaderboard")),
        (
            DOTASparklines,
            keys(
                "top_frontline_history",
                "mid_frontline_history",
                "bot_frontline_history",
            ),
        ),
        (
            DOTASignals,
            keys(
                "faction_balance_signal",
                "lane_pressure_signal",
                "hero_advantage_signal",
                "recommendation",
                recommendation="",
            ),
        ),
        # The "activity feed" slot carries the hero roster on this dashboard.
        (DOTAActivityFeed, keys("heroes")),
        (DOTABestPlays, keys("heroes_by_level", "heroes_by_abilities")),
    )

    def compose(self) -> ComposeResult:
        yield Static(
            "Defense of the Agents · Game #1 · Tick ---",
            id="title-bar",
        )

        yield DOTAHeroMetrics()

        with Horizontal(id="dota-middle-row"):
            yield DOTALeaderboard()
            with Vertical(id="dota-right-col"):
                yield DOTASparklines()
                yield DOTASignals()

        yield Static("─" * 300, id="dota-separator")

        with Horizontal(id="dota-bottom-row"):
            yield DOTAActivityFeed()
            yield DOTABestPlays()

        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        title = self.query_one("#title-bar", Static)
        game_number = data.get("game_number", 1)
        tick = data.get("tick", 0)
        winner = data.get("winner")
        if winner:
            title.update(
                f"Defense of the Agents · Game #{game_number} · GAME OVER"
            )
        else:
            title.update(
                f"Defense of the Agents · Game #{game_number} · Tick {tick}"
            )
