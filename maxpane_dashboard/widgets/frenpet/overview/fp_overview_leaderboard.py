"""Pet leaderboard table for the FrenPet Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static


class FPOverviewLeaderboard(Vertical):
    """Leaderboard panel with DataTable of top pets."""

    DEFAULT_CSS = """
    FPOverviewLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPOverviewLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LEADERBOARD", classes="fpo-lb-title")
        table = DataTable(id="fpo-lb-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#fpo-lb-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Pet ID", width=10)
        table.add_column("Score", width=12)
        table.add_column("ATK/DEF", width=12)
        table.add_column("Status", width=10)

    def update_data(self, top_pets: list) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        table = self.query_one("#fpo-lb-table", DataTable)
        table.clear()

        if not top_pets:
            table.add_row("--", "No data", "--", "--", "--")
            return

        for idx, pet in enumerate(top_pets[:10], start=1):
            pet_id = getattr(pet, "id", "?")
            score = float(getattr(pet, "score", 0))
            atk = getattr(pet, "attack_points", 0)
            defense = getattr(pet, "defense_points", 0)
            status = getattr(pet, "status", 1)

            # Format score
            if score >= 1_000_000_000:
                score_str = f"{score / 1_000_000_000:.1f}B"
            elif score >= 1_000_000:
                score_str = f"{score / 1_000_000:.1f}M"
            elif score >= 1_000:
                score_str = f"{score / 1_000:.1f}K"
            else:
                score_str = f"{score:,.0f}"

            atk_def_str = f"{atk}/{defense}"

            # Status: 1 = active, 0 or other = hibernated
            if status == 1:
                status_str = "[green]Active[/]"
            else:
                status_str = "[red]Hibernated[/]"

            # Highlight the leader row
            if idx == 1:
                id_str = f"[bold]#{pet_id}[/]"
                score_str = f"[bold]{score_str}[/]"
            else:
                id_str = f"#{pet_id}"

            table.add_row(
                str(idx),
                id_str,
                score_str,
                atk_def_str,
                status_str,
            )
