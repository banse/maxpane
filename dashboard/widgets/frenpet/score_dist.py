"""Score distribution histogram for FrenPet General View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

# Ordered tier labels matching calculate_score_distribution output.
_TIERS = ["0-10K", "10-50K", "50-100K", "100-200K", "200-500K", "500K+"]
_MAX_BAR_WIDTH = 25


class ScoreDistribution(Vertical):
    """Horizontal bar chart of score distribution using a DataTable."""

    DEFAULT_CSS = """
    ScoreDistribution > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    ScoreDistribution > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SCORE DISTRIBUTION")
        yield DataTable(id="dist-table")

    def on_mount(self) -> None:
        table = self.query_one("#dist-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_column("Tier", width=10)
        table.add_column("Bar", width=_MAX_BAR_WIDTH + 2)
        table.add_column("Count", width=8)
        # Show loading state
        table.add_row("Loading...", "", "--")

    def update_data(self, distribution: dict) -> None:
        """Render horizontal bar chart from distribution dict."""
        table = self.query_one("#dist-table", DataTable)
        table.clear()

        if not distribution:
            table.add_row("No data", "", "--")
            return

        max_count = max(distribution.values()) if distribution.values() else 1
        max_count = max(max_count, 1)  # avoid division by zero

        for tier in _TIERS:
            count = distribution.get(tier, 0)
            bar_len = int((count / max_count) * _MAX_BAR_WIDTH)
            bar_len = max(bar_len, 1) if count > 0 else 0
            bar_fill = "\u2588" * bar_len
            bar = f"[green]{bar_fill}[/]" if bar_len > 0 else ""

            table.add_row(tier, bar, f"{count:>6,}")
