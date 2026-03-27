"""Leaderboard table showing top bakeries."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.leaderboard import format_cookies, format_gap
from dashboard.analytics.production import format_rate
from dashboard.data.models import BakerySummary


class Leaderboard(Vertical):
    """Leaderboard panel with DataTable of top bakeries."""

    DEFAULT_CSS = """
    Leaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    Leaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LEADERBOARD")
        table = DataTable(id="leaderboard-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Bakery", width=24)
        table.add_column("Cookies", width=10)
        table.add_column("\u0394/hr", width=12)
        table.add_column("Gap", width=8)

    def update_data(
        self,
        bakeries: list[BakerySummary],
        production_rates: dict[str, float],
        prize_pool_usd: float,
    ) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        table = self.query_one("#leaderboard-table", DataTable)
        table.clear()

        if not bakeries:
            table.add_row("--", "No data", "--", "--", "--")
            return

        cookie_scale = 10_000
        leader_cookies = int(bakeries[0].tx_count) / cookie_scale

        for idx, bakery in enumerate(bakeries[:10], start=1):
            cookies = int(bakery.tx_count) / cookie_scale
            rate = production_rates.get(bakery.name, 0.0)

            cookies_str = format_cookies(cookies)
            rate_str = format_rate(rate)
            gap_str = format_gap(cookies, leader_cookies)

            # Highlight the leader row
            if idx == 1:
                name_str = f"[bold]{bakery.name}[/]"
                cookies_str = f"[bold]{cookies_str}[/]"
                rate_str = f"[green]{rate_str}[/]"
            else:
                name_str = bakery.name

            table.add_row(
                str(idx),
                name_str,
                cookies_str,
                rate_str,
                gap_str,
            )
