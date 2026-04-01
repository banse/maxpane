"""Trending tokens leaderboard for the Base Trading Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static


class BTOverviewLeaderboard(Vertical):
    """Leaderboard panel with DataTable of trending tokens."""

    DEFAULT_CSS = """
    BTOverviewLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BTOverviewLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDING TOKENS", classes="bto-lb-title")
        table = DataTable(id="bto-lb-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#bto-lb-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Token", width=12)
        table.add_column("Price", width=14)
        table.add_column("24h %", width=10)
        table.add_column("Volume", width=12)
        table.add_column("Mcap", width=12)

    def update_data(self, trending_tokens: list) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        table = self.query_one("#bto-lb-table", DataTable)
        table.clear()

        if not trending_tokens:
            table.add_row("--", "No data", "--", "--", "--", "--")
            return

        for idx, token in enumerate(trending_tokens[:15], start=1):
            # Support both dict and object access
            if isinstance(token, dict):
                symbol = token.get("symbol", "???")[:10]
                price = token.get("price_usd", 0)
                change = token.get("price_change_24h")
                volume = token.get("volume_24h", 0)
                mcap = token.get("market_cap", 0)
            else:
                symbol = getattr(token, "symbol", "???")[:10]
                price = getattr(token, "price_usd", 0)
                change = getattr(token, "price_change_24h", None)
                volume = getattr(token, "volume_24h", 0)
                mcap = getattr(token, "market_cap", 0)

            # Format price
            try:
                p = float(price)
                if p < 0.0001:
                    price_str = f"${p:.8f}"
                elif p < 1:
                    price_str = f"${p:.6f}"
                else:
                    price_str = f"${p:,.2f}"
            except (ValueError, TypeError):
                price_str = "..."

            # Format change
            if change is not None:
                try:
                    c = float(change)
                    if c >= 0:
                        change_str = f"[green]+{c:.1f}%[/]"
                    else:
                        change_str = f"[red]{c:.1f}%[/]"
                except (ValueError, TypeError):
                    change_str = "..."
            else:
                change_str = "[dim]--[/]"

            # Format volume
            try:
                v = float(volume)
                if v >= 1_000_000:
                    vol_str = f"${v / 1_000_000:.1f}M"
                elif v >= 1_000:
                    vol_str = f"${v / 1_000:.1f}K"
                else:
                    vol_str = f"${v:,.0f}"
            except (ValueError, TypeError):
                vol_str = "..."

            # Format market cap
            try:
                m = float(mcap)
                if m >= 1_000_000_000:
                    mcap_str = f"${m / 1_000_000_000:.1f}B"
                elif m >= 1_000_000:
                    mcap_str = f"${m / 1_000_000:.1f}M"
                elif m >= 1_000:
                    mcap_str = f"${m / 1_000:.1f}K"
                else:
                    mcap_str = f"${m:,.0f}"
            except (ValueError, TypeError):
                mcap_str = "..."

            # Highlight top 3
            if idx <= 3:
                symbol = f"[bold]{symbol}[/]"

            table.add_row(
                str(idx),
                symbol,
                price_str,
                change_str,
                vol_str,
                mcap_str,
            )
