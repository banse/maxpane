"""Competition leaderboard table for Cat Town dashboard.

The title, its blank row, the table's cursor/zebra/columns and the
clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s -- this panel
is that base's **first subscriber** (Branch 7, WP-A), which is why the base
was deferred out of Branch 6. What stays here is what only Cat Town knows:
the address cell, the rarity colour and the rank-1 bolding.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.cattown._chain import EXPLORER
from maxpane_dashboard.widgets.cattown._fmt import _RARITY_COLORS
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import TableLeaderboard

#: display budget for the fisher name/address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced. The table's "Fisher"
#: column is already 14 wide (recipe step 6, PRD §5): W(12) + ICON_COLS(2)
#: fits inside it without moving the column width.
_FISHER_COLS = 12


class CTLeaderboard(TableLeaderboard):
    """Competition leaderboard with DataTable of top fishers."""

    TITLE = "COMPETITION LEADERBOARD"

    TABLE_ID = "ct-leaderboard-table"

    COLUMNS = (
        ("#", 4),
        ("Fisher", 14),
        ("Best Fish", 18),
        ("Weight (kg)", 12),
        ("Rarity", 12),
    )

    EMPTY_ROW = ("--", "No data", "--", "--", "--")

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this table's colours and scrollbar.
    DEFAULT_CSS = """
    CTLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        competition_entries: list[dict] | None = None,
    ) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        self.render_table(competition_entries)

    def build_row(self, index: int, entry: dict) -> tuple:
        """One fisher's row. Rank 1 is bold; the fisher cell carries the icon."""
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

        return (rank, fisher, species, weight_str, rarity_str)
