"""Competition leaderboard table for Cat Town dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static


_RARITY_COLORS = {
    "Common": "dim",
    "Uncommon": "white",
    "Rare": "cyan",
    "Epic": "magenta",
    "Legendary": "yellow",
}


def _short_addr(address: str) -> str:
    """Shorten a wallet address to 0xABCD..1234 format."""
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


class CTLeaderboard(Vertical):
    """Competition leaderboard with DataTable of top fishers."""

    DEFAULT_CSS = """
    CTLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CTLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("COMPETITION LEADERBOARD")
        table = DataTable(id="ct-leaderboard-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#ct-leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Fisher", width=14)
        table.add_column("Best Fish", width=18)
        table.add_column("Weight (kg)", width=12)
        table.add_column("Rarity", width=12)

    def update_data(
        self,
        competition_entries: list[dict] | None = None,
    ) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        table = self.query_one("#ct-leaderboard-table", DataTable)
        table.clear()

        if not competition_entries:
            table.add_row("--", "No data", "--", "--", "--")
            return

        for entry in competition_entries[:10]:
            rank = str(entry.get("rank", "?"))
            display_name = entry.get("display_name", "")
            fisher = display_name if display_name else _short_addr(entry.get("fisher_address", ""))
            species = entry.get("fish_species", "")
            weight = entry.get("fish_weight_kg", 0.0)
            rarity = entry.get("rarity", "Common")

            weight_str = f"{weight:.1f}"
            color = _RARITY_COLORS.get(rarity, "dim")
            rarity_str = f"[{color}]{rarity}[/]"

            # Highlight rank 1
            if rank == "1":
                fisher = f"[bold green]{fisher}[/]"
                species = f"[bold]{species}[/]"
                weight_str = f"[bold]{weight_str}[/]"

            table.add_row(rank, fisher, species, weight_str, rarity_str)
