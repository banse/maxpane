"""Population stats panel for FrenPet General View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class Population(Vertical):
    """Panel showing total/active/hibernated/shielded/in_cooldown counts."""

    DEFAULT_CSS = """
    Population > .pop-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    Population > .pop-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("POPULATION", classes="pop-title")
        yield Static("[dim]  Loading...[/]", id="pop-content", classes="pop-body")

    def update_data(self, population_stats: dict) -> None:
        """Update population counts from analytics dict."""
        total = population_stats.get("total", 0)
        active = population_stats.get("active", 0)
        hibernated = population_stats.get("hibernated", 0)
        shielded = population_stats.get("shielded", 0)
        in_cooldown = population_stats.get("in_cooldown", 0)

        lines = [
            f"  [dim]Total:[/]        [bold white]{total:,}[/]",
            f"  [dim]Active:[/]       [green]{active:,}[/]",
            f"  [dim]Hibernated:[/]   [yellow]{hibernated:,}[/]",
            f"  [dim]Shielded:[/]     [dim]{shielded:,}[/]",
            f"  [dim]In Cooldown:[/]  [dim]{in_cooldown:,}[/]",
        ]

        self.query_one("#pop-content", Static).update("\n".join(lines))
