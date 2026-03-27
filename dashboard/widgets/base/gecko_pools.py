"""GeckoTerminal trending pools panel for Base Terminal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.base_tokens import format_change, format_volume
from dashboard.data.base_models import TrendingPool

_MAX_POOLS = 5


class GeckoPools(Vertical):
    """DataTable showing trending pools from GeckoTerminal."""

    DEFAULT_CSS = """
    GeckoPools > .gecko-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GeckoPools > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDING POOLS (GeckoTerminal)", classes="gecko-title")
        table = DataTable(id="gecko-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#gecko-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Pool", width=16)
        table.add_column("Volume", width=10)
        table.add_column("24h Change", width=10)

    def update_data(self, pools: list[TrendingPool]) -> None:
        """Update the trending pools display."""
        table = self.query_one("#gecko-table", DataTable)
        table.clear()

        display = pools[:_MAX_POOLS]

        if not display:
            table.add_row("No data", "--", "--")
            return

        for pool in display:
            pair = f"{pool.token_symbol}/WETH"
            pair_str = pair[:16]
            vol_str = format_volume(pool.volume_24h)
            change_str = format_change(pool.price_change_24h)

            table.add_row(
                f"[bold]{pair_str}[/]",
                vol_str,
                change_str,
            )
