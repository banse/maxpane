"""Player leaderboard table for Defense of the Agents dashboard.

The title, its blank row, the table's cursor/zebra/columns and the
clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s (Branch 7,
WP-A). This table seeds no ``Loading...`` row and never did.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import TableLeaderboard


class DOTALeaderboard(TableLeaderboard):
    """Player leaderboard with DataTable of top players."""

    TITLE = "LEADERBOARD"

    TABLE_ID = "dota-leaderboard-table"

    COLUMNS = (
        ("#", 4),
        ("Player", 18),
        ("Wins", 8),
        ("Games", 8),
        ("Win Rate", 10),
        ("Type", 10),
    )

    #: Twice cattown's: this panel has the same height and half the row
    #: content, and the table scrolls.
    ROW_CAP = 20

    EMPTY_ROW = ("--", "No data", "--", "--", "--", "--")

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this table's colours and scrollbar.
    DEFAULT_CSS = """
    DOTALeaderboard > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        leaderboard: list[dict] | None = None,
    ) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        self.render_table(leaderboard)

    def build_row(self, index: int, entry: dict) -> tuple:
        """One player's row. Rank 1 is bold and green."""
        rank = str(entry.get("rank", "?"))
        name = safe_markup(entry.get("name", "Unknown"))
        wins = str(entry.get("wins", 0))
        games = str(entry.get("games", 0))
        win_rate = entry.get("win_rate", 0.0)
        player_type = safe_markup(entry.get("player_type", ""))

        wr_str = f"{win_rate:.0f}%"

        # Highlight rank 1
        if rank == "1":
            name = f"[bold green]{name}[/]"
            wins = f"[bold]{wins}[/]"
            wr_str = f"[bold]{wr_str}[/]"

        return (rank, name, wins, games, wr_str, player_type)
