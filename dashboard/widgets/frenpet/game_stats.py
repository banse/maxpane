"""Global game statistics panel for FrenPet General View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from dashboard.analytics.leaderboard import format_cookies


class GameStats(Vertical):
    """Panel showing total score, avg score, median score, avg ATK/DEF."""

    DEFAULT_CSS = """
    GameStats > .gs-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameStats > .gs-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("GAME STATS", classes="gs-title")
        yield Static("[dim]  Loading...[/]", id="gs-content", classes="gs-body")

    def update_data(self, population_stats: dict) -> None:
        """Update game stats from analytics dict."""
        total_score = population_stats.get("total_score", 0.0)
        avg_score = population_stats.get("avg_score", 0.0)
        median_score = population_stats.get("median_score", 0.0)
        avg_atk = population_stats.get("avg_atk", 0.0)
        avg_def = population_stats.get("avg_def", 0.0)

        lines = [
            f"  [dim]Total Score:[/]    [bold white]{format_cookies(total_score)}[/]",
            f"  [dim]Avg Score:[/]      [bold white]{format_cookies(avg_score)}[/]",
            f"  [dim]Median Score:[/]   [bold white]{format_cookies(median_score)}[/]",
            f"  [dim]Avg ATK/DEF:[/]    [bold white]{int(avg_atk)}/{int(avg_def)}[/]",
        ]

        self.query_one("#gs-content", Static).update("\n".join(lines))
