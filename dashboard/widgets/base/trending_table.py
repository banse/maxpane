"""Trending tokens DataTable for the Base Terminal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.base_tokens import (
    format_change,
    format_market_cap,
    format_price,
    format_volume,
)
from dashboard.data.base_models import BaseToken


class TrendingTable(Vertical):
    """DataTable showing up to 20 trending tokens on Base chain."""

    DEFAULT_CSS = """
    TrendingTable > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TrendingTable > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDING TOKENS")
        table = DataTable(id="bt-tokens-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#bt-tokens-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Token", width=12)
        table.add_column("Price", width=14)
        table.add_column("5m", width=10)
        table.add_column("1h", width=10)
        table.add_column("24h", width=10)
        table.add_column("Volume", width=10)
        table.add_column("MCap", width=10)
        table.add_column("Liq", width=10)
        # Show loading state
        table.add_row("--", "Loading...", "--", "--", "--", "--", "--", "--", "--")

    def update_data(self, tokens: list[BaseToken]) -> None:
        """Clear and repopulate the table with live token data."""
        table = self.query_one("#bt-tokens-table", DataTable)
        table.clear()

        if not tokens:
            table.add_row("--", "No data", "--", "--", "--", "--", "--", "--", "--")
            return

        for idx, token in enumerate(tokens[:20], start=1):
            price_str = format_price(token.price_usd)
            change_5m = format_change(token.price_change_5m)
            change_1h = format_change(token.price_change_1h)
            change_24h = format_change(token.price_change_24h)
            vol_str = format_volume(token.volume_24h)
            mcap_str = format_market_cap(token.market_cap)
            liq_str = format_market_cap(token.liquidity)

            symbol = token.symbol[:10]

            # Highlight top 3
            if idx <= 3:
                symbol = f"[bold]{symbol}[/]"
                price_str = f"[bold]{price_str}[/]"

            table.add_row(
                str(idx),
                symbol,
                price_str,
                change_5m,
                change_1h,
                change_24h,
                vol_str,
                mcap_str,
                liq_str,
            )
