"""Sparkline charts for Onchain Monsters dashboard.

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


class OCMSparklines(Vertical):
    """ASCII sparkline charts for Onchain Monsters metrics."""

    DEFAULT_CSS = """
    OCMSparklines > .chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OCMSparklines > .chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDS", classes="chart-title")
        yield Static("", classes="chart-line", id="ocm-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="chart-line", id="ocm-chart-line-0")
        yield Static("", classes="chart-line", id="ocm-chart-line-1")
        yield Static("", classes="chart-line", id="ocm-chart-line-2")

    def update_data(
        self,
        supply_history: list[tuple[float, float]] | None = None,
        staked_history: list[tuple[float, float]] | None = None,
        ocmd_supply_history: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for Supply, Staked, and $OCMD."""
        series = [
            ("Supply  ", supply_history, "green", ""),
            ("Staked  ", staked_history, "cyan", ""),
            ("$OCMD   ", ocmd_supply_history, "yellow", ""),
        ]

        line_ids = ["ocm-chart-line-0", "ocm-chart-line-1", "ocm-chart-line-2"]

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
