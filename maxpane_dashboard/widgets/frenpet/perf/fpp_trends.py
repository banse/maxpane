"""Performance trend sparklines for the FrenPet Performance view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 20


def _build_sparkline(values: list[float], width: int = _SPARK_WIDTH) -> str:
    """Convert a list of float values into a sparkline string."""
    if len(values) < 2:
        return "\u2581" * width

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


def _format_value(value: float, suffix: str = "") -> str:
    """Format a value with K/M/B suffix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B{suffix}"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{suffix}"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K{suffix}"
    return f"{value:,.0f}{suffix}"


def _format_pct_value(value: float) -> str:
    """Format a percentage value."""
    return f"{value:.1f}%"


def _format_velocity(value: float) -> str:
    """Format velocity as +X/hr with K/M suffix."""
    sign = "+" if value >= 0 else ""
    if abs(value) >= 1_000_000:
        return f"{sign}{value / 1_000_000:.1f}M/hr"
    if abs(value) >= 1_000:
        return f"{sign}{value / 1_000:.1f}K/hr"
    return f"{sign}{value:,.0f}/hr"


def _trend_arrow(values: list[float]) -> str:
    """Return a trend arrow based on the last two values."""
    if len(values) >= 2 and values[-1] > values[-2]:
        return "[green]\u25b2[/]"
    elif len(values) >= 2 and values[-1] < values[-2]:
        return "[red]\u25bc[/]"
    return "[dim]\u25cf[/]"


class FPPerfTrends(Vertical):
    """Performance sparklines: Score, Velocity, Win Rate."""

    DEFAULT_CSS = """
    FPPerfTrends > .fpp-chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPPerfTrends > .fpp-chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDS", classes="fpp-chart-title")
        yield Static("", classes="fpp-chart-line", id="fpp-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="fpp-chart-line", id="fpp-chart-score")
        yield Static("", classes="fpp-chart-line", id="fpp-chart-velocity")
        yield Static("", classes="fpp-chart-line", id="fpp-chart-winrate")

    def update_data(
        self,
        score_history: list[tuple[float, float]] | None = None,
        velocity_history: list[tuple[float, float]] | None = None,
        win_rate_history: list[tuple[float, float]] | None = None,
    ) -> None:
        """Render performance sparklines."""
        metrics = [
            ("fpp-chart-score", "Score", score_history or [], "score"),
            ("fpp-chart-velocity", "Velocity", velocity_history or [], "velocity"),
            ("fpp-chart-winrate", "Win Rate", win_rate_history or [], "pct"),
        ]

        colors = ["green", "cyan", "yellow"]

        for (widget_id, label, history, fmt_type), color in zip(metrics, colors):
            widget = self.query_one(f"#{widget_id}", Static)

            if not history:
                widget.update(f"  [dim]{label:<14}[/]  [dim]no data[/]")
                continue

            values = [p[1] for p in history]
            sparkline = _build_sparkline(values)
            current = values[-1] if values else 0.0

            if fmt_type == "velocity":
                current_str = _format_velocity(current)
            elif fmt_type == "pct":
                current_str = _format_pct_value(current)
            else:
                current_str = _format_value(current)

            arrow = _trend_arrow(values)

            padded_label = label[:14].ljust(14)
            padded_value = current_str.rjust(8)
            widget.update(
                f"  [dim]{padded_label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{padded_value}[/] {arrow}"
            )
