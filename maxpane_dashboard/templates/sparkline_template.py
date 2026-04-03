"""Sparkline chart template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and per-metric lines.
Each line shows: label, sparkline using block chars, current value,
and a trend arrow.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_score_trends.py
  - maxpane_dashboard/widgets/cattown/ct_sparklines.py
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 22


def _build_sparkline(points: list[tuple[float, float]], width: int = _SPARK_WIDTH) -> str:
    """Convert time-series points ``(timestamp, value)`` into a sparkline string.

    The Y axis is scaled relative to the series min/max range so
    short-range movements are still visible.
    """
    if len(points) < 2:
        return _SPARK_CHARS[0] * width

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

    # Pad to width if fewer samples
    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])

    return "".join(chars)


def _trend_arrow(points: list[tuple[float, float]]) -> str:
    """Return a colored trend arrow based on the last two points."""
    if len(points) >= 2 and points[-1][1] > points[-2][1]:
        return "[green]\u25b2[/]"
    elif len(points) >= 2 and points[-1][1] < points[-2][1]:
        return "[red]\u25bc[/]"
    return "[dim]\u25cf[/]"


def _fmt_value(value: float, unit: str = "") -> str:
    """Format a numeric value with K/M/B suffix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B{unit}"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{unit}"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K{unit}"
    elif value >= 1:
        return f"{value:.1f}{unit}"
    return f"{value:.0f}{unit}"


class GameSparklines(Vertical):
    """ASCII sparkline charts for game metrics.

    Rename for your game, e.g. ``CTSparklines``, ``DOTASparklines``.
    Adjust compose() widget IDs and update_data() parameters.
    """

    DEFAULT_CSS = """
    GameSparklines > .chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameSparklines > .chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDS", classes="chart-title")
        yield Static("", classes="chart-line", id="game-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="chart-line", id="game-chart-line-0")
        yield Static("", classes="chart-line", id="game-chart-line-1")
        yield Static("", classes="chart-line", id="game-chart-line-2")

    def update_data(
        self,
        series_0: list[tuple[float, float]] | None = None,
        series_1: list[tuple[float, float]] | None = None,
        series_2: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for up to three time-series.

        Each series is a list of ``(timestamp, value)`` tuples.
        Adapt the series names and labels to your game.
        """
        series = [
            ("Metric 1", series_0, "green", ""),
            ("Metric 2", series_1, "cyan", ""),
            ("Metric 3", series_2, "yellow", ""),
        ]

        line_ids = ["game-chart-line-0", "game-chart-line-1", "game-chart-line-2"]

        for i, (label, points, color, unit) in enumerate(series):
            widget = self.query_one(f"#{line_ids[i]}", Static)

            if not points or len(points) < 1:
                widget.update("")
                continue

            sparkline = _build_sparkline(points)
            current = points[-1][1] if points else 0.0
            current_str = _fmt_value(current, unit)
            arrow = _trend_arrow(points)

            padded_label = label[:8].ljust(8)
            widget.update(
                f"  [dim]{padded_label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )
