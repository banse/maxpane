"""Leaderboard template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and a DataTable.
Uses fixed-width columns, zebra stripes, and cursor_type="row".
Highlights the leader row with bold markup.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_overview_leaderboard.py
  - maxpane_dashboard/widgets/cattown/ct_leaderboard.py
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static


def _short_addr(address: str) -> str:
    """Shorten a wallet address to 0xABCD..1234 format."""
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


class GameLeaderboard(Vertical):
    """Leaderboard panel with DataTable of top entries.

    Rename for your game, e.g. ``CTLeaderboard``, ``DOTALeaderboard``.
    Update column definitions and update_data() to match your schema.
    """

    DEFAULT_CSS = """
    GameLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LEADERBOARD")
        table = DataTable(id="game-leaderboard-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#game-leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        # Adapt columns to your game
        table.add_column("#", width=4)
        table.add_column("Name", width=16)
        table.add_column("Score", width=12)
        table.add_column("Detail", width=12)
        table.add_column("Status", width=10)

    def update_data(self, entries: list[dict] | None = None) -> None:
        """Clear and repopulate the leaderboard table with live data.

        Adapt the dict keys to your game's leaderboard schema.
        """
        table = self.query_one("#game-leaderboard-table", DataTable)
        table.clear()

        if not entries:
            table.add_row("--", "No data", "--", "--", "--")
            return

        for idx, entry in enumerate(entries[:10], start=1):
            name = entry.get("name", "") or _short_addr(entry.get("address", "?"))
            score = entry.get("score", 0)
            detail = entry.get("detail", "")
            status = entry.get("status", "")

            # Format score with K/M/B suffix
            score_f = float(score)
            if score_f >= 1_000_000_000:
                score_str = f"{score_f / 1_000_000_000:.1f}B"
            elif score_f >= 1_000_000:
                score_str = f"{score_f / 1_000_000:.1f}M"
            elif score_f >= 1_000:
                score_str = f"{score_f / 1_000:.1f}K"
            else:
                score_str = f"{score_f:,.0f}"

            # Highlight the leader row
            if idx == 1:
                name = f"[bold]{name}[/]"
                score_str = f"[bold]{score_str}[/]"

            table.add_row(str(idx), name, score_str, str(detail), str(status))
