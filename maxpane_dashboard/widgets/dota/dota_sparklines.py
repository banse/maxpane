"""Sparkline charts for Defense of the Agents dashboard."""

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


def _fmt_value(value: float) -> str:
    """Format a numeric frontline value for display."""
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}"


class DOTASparklines(Vertical):
    """ASCII sparkline charts for lane frontline positions."""

    DEFAULT_CSS = """
    DOTASparklines > .dota-chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    DOTASparklines > .dota-chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LANE FRONTLINES", classes="dota-chart-title")
        yield Static("", classes="dota-chart-line", id="dota-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="dota-chart-line", id="dota-chart-line-0")
        yield Static("", classes="dota-chart-line", id="dota-chart-line-1")
        yield Static("", classes="dota-chart-line", id="dota-chart-line-2")

    def update_data(
        self,
        top_frontline_history: list[tuple[float, float]] | None = None,
        mid_frontline_history: list[tuple[float, float]] | None = None,
        bot_frontline_history: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for Top, Mid, and Bot lane frontlines."""
        series = [
            ("Top Lane ", top_frontline_history, "green"),
            ("Mid Lane ", mid_frontline_history, "cyan"),
            ("Bot Lane ", bot_frontline_history, "yellow"),
        ]

        line_ids = ["dota-chart-line-0", "dota-chart-line-1", "dota-chart-line-2"]

        for i, (label, points, color) in enumerate(series):
            widget = self.query_one(f"#{line_ids[i]}", Static)

            if not points or len(points) < 1:
                widget.update("")
                continue

            sparkline = _build_sparkline(points)
            current = points[-1][1] if points else 0.0
            current_str = _fmt_value(current)
            arrow = _trend_arrow(points)

            widget.update(
                f"  [dim]{label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )
