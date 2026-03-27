"""Top 10 leaderboard table for FrenPet General View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.leaderboard import format_cookies


def _status_label(pet) -> str:
    """Return a Rich-markup status string for a FrenPet model."""
    # pet.status: 0 = alive, 2 = hibernated
    if pet.status != 0:
        return "[red]Hibernated[/]"
    # We don't have real-time shield info at widget level,
    # so infer from shield_expires vs a rough "now" (0 means no shield).
    if pet.shield_expires > 0:
        return "[yellow]Shielded[/]"
    return "[green]Active[/]"


class TopLeaderboard(Vertical):
    """DataTable showing top 10 pets by score."""

    DEFAULT_CSS = """
    TopLeaderboard > .lb-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TopLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TOP 10", classes="lb-title")
        table = DataTable(id="fp-lb-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#fp-lb-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Pet", width=10)
        table.add_column("Score", width=10)
        table.add_column("ATK/DEF", width=10)
        table.add_column("Status", width=12)

    def update_data(self, top_pets: list) -> None:
        """Clear and repopulate with top pet data.

        ``top_pets`` is a list of ``FrenPet`` model instances.
        """
        table = self.query_one("#fp-lb-table", DataTable)
        table.clear()

        if not top_pets:
            table.add_row("--", "No data", "--", "--", "--")
            return

        for idx, pet in enumerate(top_pets[:10], start=1):
            score_str = format_cookies(float(pet.score))
            atk_def = f"{pet.attack_points}/{pet.defense_points}"
            status = _status_label(pet)

            if idx == 1:
                name_str = f"[bold]#{pet.id}[/]"
                score_str = f"[bold]{score_str}[/]"
            else:
                name_str = f"#{pet.id}"

            table.add_row(
                str(idx),
                name_str,
                score_str,
                atk_def,
                status,
            )
