"""CatTownScreen -- Cat Town Fishing game dashboard as a Textual Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.cattown import (
    CTActivityFeed,
    CTBestPlays,
    CTHeroMetrics,
    CTLeaderboard,
    CTSignals,
    CTSparklines,
)
from maxpane_dashboard.widgets.status_bar import StatusBar


class CatTownScreen(DashboardScreen):
    """Cat Town Fishing game dashboard."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "cat town fishing"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "cattown-refresh"

    #: Transcribed from the six hand-written dispatch blocks, default for
    #: default; the status bar is updated by the base.
    PANELS = (
        (CTHeroMetrics, keys("competition_state", "top_fisher")),
        (CTLeaderboard, keys("competition_entries")),
        (
            CTSparklines,
            keys(
                "prize_pool_history",
                "leader_weight_history",
                "raffle_tickets_history",
            ),
        ),
        (
            CTSignals,
            keys(
                "condition_signal",
                "legendary_signal",
                "cutoff_signal",
                "recommendation",
                recommendation="",
            ),
        ),
        (CTActivityFeed, keys("recent_catches")),
        (CTBestPlays, keys("available_fish", "available_treasures")),
    )

    def compose(self) -> ComposeResult:
        yield Static(
            "Cat Town Fishing · Competition",
            id="title-bar",
        )

        yield CTHeroMetrics()

        with Horizontal(id="middle-row"):
            yield CTLeaderboard()
            with Vertical(id="right-col"):
                yield CTSparklines()
                yield CTSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield CTActivityFeed()
            yield CTBestPlays()

        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        title = self.query_one("#title-bar", Static)
        comp = data.get("competition_state", {})
        if comp and comp.get("is_active"):
            participants = comp.get("num_participants", 0)
            suffix = f"Competition LIVE · {participants} fishers"
        else:
            suffix = "Competition"
        title.update(f"Cat Town Fishing · {suffix}")
