"""Your pets ranked in the population for FrenPet General View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.leaderboard import format_cookies


def _percentile_color(percentile: float) -> str:
    """Return color based on percentile ranking (lower is better)."""
    if percentile <= 10.0:
        return "green"
    elif percentile <= 25.0:
        return "yellow"
    return "dim"


class PetsInContext(Vertical):
    """Panel showing managed pets with their rank and percentile."""

    DEFAULT_CSS = """
    PetsInContext > .pic-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    PetsInContext > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("YOUR PETS IN CONTEXT", classes="pic-title")
        yield DataTable(id="pic-table")

    def on_mount(self) -> None:
        table = self.query_one("#pic-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Pet", width=8)
        table.add_column("Score", width=10)
        table.add_column("Rank", width=10)
        table.add_column("Percentile", width=10)

    def update_data(self, pet_ranks: dict, managed_pets: list) -> None:
        """Update pet context display.

        ``pet_ranks`` maps pet ID to rank info dict with
        ``rank``, ``total``, and ``percentile`` keys.
        ``managed_pets`` is a list of ``FrenPet`` model instances.
        """
        table = self.query_one("#pic-table", DataTable)
        table.clear()

        if not managed_pets:
            table.add_row("--", "[dim]No wallet configured[/]", "--", "--")
            return

        for pet in managed_pets:
            rank_info = pet_ranks.get(pet.id, {})
            rank = rank_info.get("rank", 0)
            percentile = rank_info.get("percentile", 100.0)
            score_str = format_cookies(float(pet.score))
            color = _percentile_color(percentile)

            table.add_row(
                f"[{color}]#{pet.id}[/]",
                f"[bold white]{score_str}[/]",
                f"[{color}]#{rank}[/]",
                f"[{color}]top {percentile:.0f}%[/]",
            )
