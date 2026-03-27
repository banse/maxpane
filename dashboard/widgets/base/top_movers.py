"""Top gainers and losers panel for Base Terminal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.base_tokens import format_market_cap
from dashboard.data.base_models import BaseToken


class TopMovers(Vertical):
    """DataTable showing top gainers and losers."""

    DEFAULT_CSS = """
    TopMovers > .movers-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TopMovers > DataTable {
        height: 1fr;
    }
    """

    _MAX_EACH = 3

    def compose(self) -> ComposeResult:
        yield Static("TOP MOVERS", classes="movers-title")
        table = DataTable(id="movers-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#movers-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Dir", width=3)
        table.add_column("Token", width=10)
        table.add_column("Change", width=8)
        table.add_column("Status", width=10)

    def update_data(
        self,
        gainers: list[BaseToken],
        losers: list[BaseToken],
    ) -> None:
        """Update the movers display with gainers and losers."""
        table = self.query_one("#movers-table", DataTable)
        table.clear()

        top_gainers = gainers[: self._MAX_EACH]
        top_losers = losers[: self._MAX_EACH]

        if not top_gainers and not top_losers:
            table.add_row("--", "No data", "--", "--")
            return

        for token in top_gainers:
            change = token.price_change_24h
            pct = f"+{change:.0f}%" if change is not None else "+?%"
            mcap = format_market_cap(token.market_cap)
            symbol = token.symbol[:10]
            table.add_row(
                "[green]\u25b2[/]",
                f"[bold]{symbol}[/]",
                f"[green]{pct}[/]",
                f"[dim]{mcap}[/]",
            )

        for token in top_losers:
            change = token.price_change_24h
            pct = f"{change:.0f}%" if change is not None else "-?%"
            mcap = format_market_cap(token.market_cap)
            symbol = token.symbol[:10]
            table.add_row(
                "[red]\u25bc[/]",
                f"[bold]{symbol}[/]",
                f"[red]{pct}[/]",
                f"[dim]{mcap}[/]",
            )
