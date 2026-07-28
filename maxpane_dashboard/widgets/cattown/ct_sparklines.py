"""Sparkline charts for Cat Town dashboard.

The sparkline primitives come from
``maxpane_dashboard/widgets/sparkline_common.py``.  This module used to
carry its own pre-hardening copies, which raised ``TypeError`` on a
``None`` entry or a ``None`` value in a cached history (MEDI-36).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline_from_points as _build_sparkline,
    coerce_points as _coerce_points,
    trend_arrow as _trend_arrow,
)


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

            points = _coerce_points(points)
            if not points:
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
