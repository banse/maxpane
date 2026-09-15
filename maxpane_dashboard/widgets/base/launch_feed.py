"""Live launch feed DataTable for the Base Terminal Launch Radar."""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.base_tokens import format_change, format_price, format_volume
from maxpane_dashboard.widgets.address import address_text

#: Display budget for the token symbol label, excluding the icon -- the same
#: 10-cell window the deleted ``symbol[:10]`` slice produced. No layout pin
#: covers this standalone widget (task-5 brief: "No layout pin exists for
#: base"), so the "Token" column is grown by ICON_COLS (PRD §5 recipe step
#: 6.2): 12 -> 14, keeping the 2-cell gutter the column already carried
#: beyond the 10-cell label.
_TOKEN_COLS = 10


def _format_age(timestamp: float | int | None) -> str:
    """Format a unix timestamp as relative age: '2m ago', '1h 12m', etc."""
    if timestamp is None:
        return "--"
    try:
        delta = int(time.time() - float(timestamp))
    except (ValueError, TypeError):
        return "--"

    if delta < 0:
        return "just now"
    if delta < 60:
        return f"{delta}s ago"
    minutes = delta // 60
    hours = minutes // 60
    if hours == 0:
        return f"{minutes}m ago" if minutes <= 5 else f"{minutes}m"
    remaining_m = minutes % 60
    if remaining_m == 0:
        return f"{hours}h"
    return f"{hours}h {remaining_m}m"


class LaunchFeed(Vertical):
    """DataTable showing live new token launches on Base chain."""

    DEFAULT_CSS = """
    LaunchFeed > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    LaunchFeed > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LIVE LAUNCHES", classes="launch-feed-title")
        table = DataTable(id="launch-feed-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#launch-feed-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("Age", width=8)
        table.add_column("Token", width=14)
        table.add_column("Deployer", width=10)
        table.add_column("Price", width=12)
        table.add_column("5m", width=10)
        table.add_column("Vol", width=10)
        # Show loading state
        table.add_row("--", "Loading...", "--", "--", "--", "--")

    def update_data(self, launches: list) -> None:
        """Clear and repopulate the table with live launch data.

        Each launch dict is expected to have:
            timestamp, symbol, deployer, price_usd, price_change_5m, volume.
        """
        table = self.query_one("#launch-feed-table", DataTable)
        table.clear()

        if not launches:
            table.add_row("--", "No launches", "--", "--", "--", "--")
            return

        for launch in launches:
            ts = launch.get("timestamp")
            age_str = _format_age(ts)

            symbol = launch.get("symbol", "???")
            if not symbol.startswith("$"):
                symbol = f"${symbol}"

            deployer = launch.get("deployer", "--")[:10]
            price = launch.get("price_usd", 0)
            price_str = format_price(price) if price else "--"
            change_5m = launch.get("price_change_5m")
            change_str = format_change(change_5m)

            volume = launch.get("volume", 0)
            vol_str = format_volume(volume) if volume else "--"

            # HOT marker if 5m > +100%
            is_up = change_5m is not None and change_5m > 0
            token_cell = address_text(
                launch.get("address"), label=symbol, width=_TOKEN_COLS,
                style="bold" if is_up else "",
            )
            if change_5m is not None and change_5m > 100:
                hot = Text()
                hot.append_text(token_cell)
                hot.append(" ")
                hot.append(" HOT ", style="red reverse")
                token_cell = hot

            table.add_row(age_str, token_cell, deployer, price_str, change_str, vol_str)
