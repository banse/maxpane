"""Player leaderboard table for Defense of the Agents dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static


class DOTALeaderboard(Vertical):
    """Player leaderboard with DataTable of top players."""

    DEFAULT_CSS = """
    DOTALeaderboard > .dota-lb-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    DOTALeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LEADERBOARD", classes="dota-lb-title")
        table = DataTable(id="dota-leaderboard-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#dota-leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Player", width=18)
        table.add_column("Wins", width=8)
        table.add_column("Games", width=8)
        table.add_column("Win Rate", width=10)
        table.add_column("Type", width=10)

    def update_data(
        self,
        leaderboard: list[dict] | None = None,
    ) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        table = self.query_one("#dota-leaderboard-table", DataTable)
        table.clear()

        if not leaderboard:
            table.add_row("--", "No data", "--", "--", "--", "--")
            return

        for entry in leaderboard[:20]:
            rank = str(entry.get("rank", "?"))
            name = entry.get("name", "Unknown")
            wins = str(entry.get("wins", 0))
            games = str(entry.get("games", 0))
            win_rate = entry.get("win_rate", 0.0)
            player_type = entry.get("player_type", "")

            wr_str = f"{win_rate:.0f}%"

            # Highlight rank 1
            if rank == "1":
                name = f"[bold green]{name}[/]"
                wins = f"[bold]{wins}[/]"
                wr_str = f"[bold]{wr_str}[/]"

            table.add_row(rank, name, wins, games, wr_str, player_type)
