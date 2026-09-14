"""Token leaderboard table for the Base Trading Overview view."""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.address import address_text

#: Display budget for the token name/symbol label, excluding the icon. This
#: column had no pre-existing slice (it relied on DataTable's own silent,
#: non-cell_len truncation), so the label width is picked to leave the same
#: 2-cell gutter as the package's other token columns once grown; no layout
#: pin governs this dead-code duplicate (task-5 brief: "No layout pin exists
#: for base"): col 14 -> 16 (PRD §5 recipe step 6.2).
_TOKEN_COLS = 12


def _strip_non_ascii(text: str) -> str:
    """Remove non-ASCII characters from text for alignment."""
    return re.sub(r"[^\x20-\x7E]", "", text)


def _format_usd(value: float) -> str:
    """Format a USD value with K/M/B suffix."""
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.2f}"


def _format_price(price: float) -> str:
    """Format a token price with appropriate precision."""
    if price >= 1.0:
        return f"${price:,.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    elif price >= 0.0001:
        return f"${price:.6f}"
    return f"${price:.8f}"


class BTOverviewLeaderboard(Vertical):
    """Leaderboard panel with DataTable of top tokens by volume."""

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
        yield Static("LEADERBOARD", classes="bto-lb-title")
        table = DataTable(id="bto-lb-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#bto-lb-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Token", width=16)
        table.add_column("Price", width=12)
        table.add_column("24h %", width=10)
        table.add_column("Volume", width=14)
        table.add_column("Liquidity", width=14)

    def update_data(self, tokens: list) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        table = self.query_one("#bto-lb-table", DataTable)
        table.clear()

        if not tokens:
            table.add_row("--", "No data", "--", "--", "--", "--")
            return

        # Sort by volume_24h descending, take top 10
        sorted_tokens = sorted(
            tokens,
            key=lambda t: float(t.get("volume_24h", 0) if isinstance(t, dict) else getattr(t, "volume_24h", 0)),
            reverse=True,
        )[:10]

        for idx, token in enumerate(sorted_tokens, start=1):
            if isinstance(token, dict):
                name = token.get("symbol", token.get("name", "?"))
                address = token.get("address")
                price = float(token.get("price_usd", 0))
                change = float(token.get("price_change_24h", 0))
                volume = float(token.get("volume_24h", 0))
                liquidity = float(token.get("liquidity_usd", 0))
            else:
                name = getattr(token, "symbol", getattr(token, "name", "?"))
                address = getattr(token, "address", None)
                price = float(getattr(token, "price_usd", 0))
                change = float(getattr(token, "price_change_24h", 0))
                volume = float(getattr(token, "volume_24h", 0))
                liquidity = float(getattr(token, "liquidity_usd", 0))

            name = _strip_non_ascii(name)
            price_str = _format_price(price)
            vol_str = _format_usd(volume)
            liq_str = _format_usd(liquidity)

            # Color 24h% green/red
            change_color = "green" if change >= 0 else "red"
            change_sign = "+" if change >= 0 else ""
            change_str = f"[{change_color}]{change_sign}{change:.1f}%[/]"

            # Bold the #1 row
            is_top = idx == 1
            name_cell = address_text(
                address, label=name or None, width=_TOKEN_COLS, style="bold" if is_top else "",
            )
            if is_top:
                price_str = f"[bold]{price_str}[/]"

            table.add_row(
                str(idx),
                name_cell,
                price_str,
                change_str,
                vol_str,
                liq_str,
            )
