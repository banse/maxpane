"""Sparkline chart widget for the Base Terminal Token Detail view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.analytics.base_tokens import format_price

# Braille-style sparkline blocks, 8 levels
_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def _make_sparkline(values: list[float], width: int = 60) -> str:
    """Build a sparkline string from a list of float values."""
    if not values:
        return "[dim]no data[/]"

    # Sample down to width if needed
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = list(values)

    lo = min(sampled)
    hi = max(sampled)
    span = hi - lo if hi != lo else 1.0

    chars = []
    for v in sampled:
        idx = int((v - lo) / span * 7)
        idx = max(0, min(7, idx))
        chars.append(_SPARK_CHARS[idx])

    return "".join(chars)


class TokenChart(Vertical):
    """Wide sparkline chart with low/high/current price labels."""

    DEFAULT_CSS = """
    TokenChart > .tc-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TokenChart > .tc-body {
        width: 100%;
        padding: 0 1;
        border: solid $panel;
        background: $surface;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("CHART", classes="tc-title")
        yield Static(
            "[dim]  no data[/]",
            id="tc-body",
            classes="tc-body",
        )

    def update_data(self, price_history: list[tuple[float, float]] | None) -> None:
        """Update the sparkline chart.

        Args:
            price_history: list of (timestamp, price) tuples, ordered by time.
        """
        body = self.query_one("#tc-body", Static)

        if not price_history:
            body.update("[dim]  no data[/]")
            return

        prices = [p for _, p in price_history]
        if not prices:
            body.update("[dim]  no data[/]")
            return

        sparkline = _make_sparkline(prices)
        lo = min(prices)
        hi = max(prices)
        current = prices[-1]

        lo_str = format_price(lo)
        hi_str = format_price(hi)
        cur_str = format_price(current)

        lines = [
            "",
            f"  {sparkline}",
            "",
            f"  Low: {lo_str}   High: {hi_str}   Now: [bold]{cur_str}[/]",
        ]
        body.update("\n".join(lines))
