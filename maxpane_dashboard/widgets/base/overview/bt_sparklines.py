"""Trend sparklines for the Base Trading Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 20


def _build_sparkline(points: list[tuple[float, float]], width: int = _SPARK_WIDTH) -> str:
    """Convert time-series points into a sparkline string.

    Each point is ``(timestamp, value)``.
    """
    if len(points) < 2:
        return "\u2581" * width

    values = [p[1] for p in points]

    if len(values) > width:
        values = values[-width:]

    lo = min(values)
    hi = max(values)
    span = hi - lo

    chars: list[str] = []
    for v in values:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
            idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])

    return "".join(chars)


def _format_value(value: float, prefix: str = "", suffix: str = "") -> str:
    """Format a numeric value with K/M/B suffix."""
    if value >= 1_000_000_000:
        return f"{prefix}{value / 1_000_000_000:.1f}B{suffix}"
    elif value >= 1_000_000:
        return f"{prefix}{value / 1_000_000:.1f}M{suffix}"
    elif value >= 1_000:
        return f"{prefix}{value / 1_000:.1f}K{suffix}"
    return f"{prefix}{value:,.0f}{suffix}"


def _trend_arrow(points: list[tuple[float, float]]) -> str:
    """Return a colored arrow based on the last two data points."""
    if len(points) >= 2 and points[-1][1] > points[-2][1]:
        return "[green]\u25b2[/]"
    elif len(points) >= 2 and points[-1][1] < points[-2][1]:
        return "[red]\u25bc[/]"
    return "[dim]\u25cf[/]"


class BTSparklines(Vertical):
    """Sparkline charts showing volume, ETH price, and trade count trends."""

    DEFAULT_CSS = """
    BTSparklines > .bto-chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BTSparklines > .bto-chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDS", classes="bto-chart-title")
        yield Static("", classes="bto-chart-line", id="bto-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="bto-chart-line", id="bto-chart-line-0")
        yield Static("", classes="bto-chart-line", id="bto-chart-line-1")
        yield Static("", classes="bto-chart-line", id="bto-chart-line-2")

    def update_data(
        self,
        volume_history: list | None = None,
        eth_price_history: list | None = None,
        trade_count_history: list | None = None,
    ) -> None:
        """Render sparklines for volume, ETH price, and trade count."""
        series = [
            ("Volume", "cyan", volume_history or [], "$", ""),
            ("ETH", "green", eth_price_history or [], "$", ""),
            ("Trades", "yellow", trade_count_history or [], "", "/h"),
        ]

        line_ids = ["bto-chart-line-0", "bto-chart-line-1", "bto-chart-line-2"]

        for i, (label, color, points, prefix, suffix) in enumerate(series):
            widget = self.query_one(f"#{line_ids[i]}", Static)

            if not points:
                widget.update(f"  [dim]{label:<10}[/]  [dim]waiting for data...[/]")
                continue

            sparkline = _build_sparkline(points)
            current = points[-1][1] if points else 0.0
            current_str = _format_value(current, prefix=prefix, suffix=suffix)
            arrow = _trend_arrow(points)

            widget.update(
                f"  [dim]{label:<10}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )
