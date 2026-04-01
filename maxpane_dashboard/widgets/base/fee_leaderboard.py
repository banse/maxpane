"""Fee leaderboard panel for the Base Terminal Fee Monitor view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static


class FeeLeaderboard(Vertical):
    """DataTable showing ranked tokens by total fees claimed."""

    DEFAULT_CSS = """
    FeeLeaderboard > .fl-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FeeLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("FEE LEADERBOARD", classes="fl-title")
        table = DataTable(id="fl-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#fl-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Token", width=14)
        table.add_column("Total Claimed", width=12)

    def update_data(self, leaderboard: list[dict] | None) -> None:
        """Update the leaderboard display.

        Each entry dict expected keys:
            token, total_claimed_eth.
        """
        table = self.query_one("#fl-table", DataTable)
        table.clear()

        if not leaderboard:
            table.add_row("--", "No data", "--")
            return

        for idx, entry in enumerate(leaderboard[:10], start=1):
            token = entry.get("token", "???")
            total = entry.get("total_claimed_eth", 0)
            try:
                total_val = float(total)
            except (ValueError, TypeError):
                total_val = 0

            total_str = f"{total_val:.1f} ETH"

            # Bold top 3
            if idx <= 3:
                table.add_row(
                    f"[bold]{idx}[/]",
                    f"[bold]{token}[/]",
                    f"[bold]{total_str}[/]",
                )
            else:
                table.add_row(
                    str(idx),
                    token,
                    f"[dim]{total_str}[/]",
                )
