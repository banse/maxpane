"""Sparkline charts for Cat Town dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 22


def _build_sparkline(points: list[tuple[float, float]], width: int = _SPARK_WIDTH) -> str:
    """Convert time-series points into a sparkline string."""
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


def _trend_arrow(points: list[tuple[float, float]]) -> str:
    """Return a colored trend arrow based on the last two points."""
    if len(points) >= 2 and points[-1][1] > points[-2][1]:
        return "[green]\u25b2[/]"
    elif len(points) >= 2 and points[-1][1] < points[-2][1]:
        return "[red]\u25bc[/]"
    return "[dim]\u25cf[/]"


def _fmt_value(value: float, unit: str = "") -> str:
    """Format a numeric value for display."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{unit}"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K{unit}"
    elif value >= 1:
        return f"{value:.1f}{unit}"
    return f"{value:.0f}{unit}"


class CTSparklines(Vertical):
    """ASCII sparkline charts for Cat Town metrics."""

    DEFAULT_CSS = """
    CTSparklines > .chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CTSparklines > .chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("CAT TOWN TRENDS", classes="chart-title")
        yield Static("", classes="chart-line", id="ct-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="chart-line", id="ct-chart-line-0")
        yield Static("", classes="chart-line", id="ct-chart-line-1")
        yield Static("", classes="chart-line", id="ct-chart-line-2")

    def update_data(
        self,
        prize_pool_history: list[tuple[float, float]] | None = None,
        leader_weight_history: list[tuple[float, float]] | None = None,
        raffle_tickets_history: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for Prize Pool, Leader Weight, and Raffle Tickets."""
        series = [
            ("Prize Pl", prize_pool_history, "yellow", ""),
            ("Leader  ", leader_weight_history, "green", "kg"),
            ("Raffle  ", raffle_tickets_history, "cyan", " tix"),
        ]

        line_ids = ["ct-chart-line-0", "ct-chart-line-1", "ct-chart-line-2"]

        for i, (label, points, color, unit) in enumerate(series):
            widget = self.query_one(f"#{line_ids[i]}", Static)

            if not points or len(points) < 1:
                widget.update("")
                continue

            sparkline = _build_sparkline(points)
            current = points[-1][1] if points else 0.0
            current_str = _fmt_value(current, unit)
            arrow = _trend_arrow(points)

            widget.update(
                f"  [dim]{label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )
