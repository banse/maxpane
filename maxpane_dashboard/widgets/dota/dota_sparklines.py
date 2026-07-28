"""Sparkline charts for Defense of the Agents dashboard.

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

            points = _coerce_points(points)
            if not points:
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
