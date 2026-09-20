"""Competition leaderboard table for Cat Town dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.cattown._chain import EXPLORER
from maxpane_dashboard.widgets.markup_safety import safe_markup


_RARITY_COLORS = {
    "Common": "dim",
    "Uncommon": "white",
    "Rare": "cyan",
    "Epic": "magenta",
    "Legendary": "yellow",
}

#: display budget for the fisher name/address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced. The table's "Fisher"
#: column is already 14 wide (recipe step 6, PRD §5): W(12) + ICON_COLS(2)
#: fits inside it without moving the column width.
_FISHER_COLS = 12


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
            is_top = rank == "1"
            fisher = address_text(
                entry.get("fisher_address", ""),
                label=display_name or None,
                width=_FISHER_COLS,
                style="bold green" if is_top else "",
                explorer=EXPLORER,
            )
            species = safe_markup(entry.get("fish_species", ""))
            weight = entry.get("fish_weight_kg", 0.0)
            rarity = entry.get("rarity", "Common")

            weight_str = f"{weight:.1f}"
            color = _RARITY_COLORS.get(rarity, "dim")
            rarity_str = f"[{color}]{rarity}[/]"

            # Highlight rank 1
            if is_top:
                species = f"[bold]{species}[/]"
                weight_str = f"[bold]{weight_str}[/]"

            table.add_row(rank, fisher, species, weight_str, rarity_str)
