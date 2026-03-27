"""Volume comparison bars for Base Terminal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from dashboard.analytics.base_tokens import format_volume
from dashboard.data.base_models import BaseToken

_MAX_BAR_WIDTH = 20
_MAX_TOKENS = 5


class VolumeBars(Vertical):
    """Panel showing horizontal volume bars relative to highest volume."""

    DEFAULT_CSS = """
    VolumeBars > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    VolumeBars > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("VOLUME LEADERS")
        yield DataTable(id="vol-table")

    def on_mount(self) -> None:
        table = self.query_one("#vol-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Token", width=8)
        table.add_column("Bar", width=_MAX_BAR_WIDTH + 2)
        table.add_column("Volume", width=10)
        # Show loading state
        table.add_row("Loading...", "", "--")

    def update_data(self, volume_leaders: list[BaseToken]) -> None:
        """Update the volume bars display."""
        table = self.query_one("#vol-table", DataTable)
        table.clear()

        display = volume_leaders[:_MAX_TOKENS]
        if not display:
            table.add_row("No data", "", "--")
            return

        max_vol = display[0].volume_24h if display else 0

        for token in display:
            vol = token.volume_24h
            symbol = token.symbol[:8]

            if max_vol > 0:
                bar_len = max(1, int(vol / max_vol * _MAX_BAR_WIDTH))
            else:
                bar_len = 1

            bar_fill = "\u2588" * bar_len
            bar = f"[cyan]{bar_fill}[/]"
            vol_str = format_volume(vol)

            table.add_row(symbol, bar, vol_str)
