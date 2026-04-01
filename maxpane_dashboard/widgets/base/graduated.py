"""Graduated tokens panel for the Base Terminal Launch Radar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.base_tokens import format_change, format_price


class GraduatedTokens(Vertical):
    """DataTable showing recently graduated tokens (Clanker champagne threshold)."""

    DEFAULT_CSS = """
    GraduatedTokens > .graduated-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GraduatedTokens > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("GRADUATED \U0001f37e", classes="graduated-title")
        table = DataTable(id="graduated-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#graduated-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Token", width=12)
        table.add_column("Price", width=14)
        table.add_column("Change", width=10)

    def update_data(self, graduated: list) -> None:
        """Update the graduated tokens display.

        Each entry is expected to have:
            symbol, price_usd, price_change_5m (or price_change).
        """
        table = self.query_one("#graduated-table", DataTable)
        table.clear()

        if not graduated:
            table.add_row("No launches", "--", "--")
            return

        for token in graduated:
            symbol = token.get("symbol", "???")
            if not symbol.startswith("$"):
                symbol = f"${symbol}"
            symbol = symbol[:10]

            price = token.get("price_usd", 0)
            price_str = format_price(price) if price else "--"

            change = token.get("price_change_5m") or token.get("price_change")
            change_str = format_change(change)

            table.add_row(
                f"[bold]{symbol}[/]",
                price_str,
                change_str,
            )
