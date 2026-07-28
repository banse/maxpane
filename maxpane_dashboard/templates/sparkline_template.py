"""Sparkline chart template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and per-metric lines.
Each line shows: label, sparkline using block chars, current value,
and a trend arrow.

**Copy the widget class, import the helpers.**  The sparkline primitives
live in ``maxpane_dashboard/widgets/sparkline_common.py`` and this template
imports them.  Keep the import when you copy this file -- do not paste the
helper bodies into your new module.  Three dashboards (ttt, talismans, fwa)
each carried a byte-identical copy of ``_coerce_points`` while three older
ones (ocm, cattown, dota) carried a pre-hardening version that crashed on a
``None`` sample, and a fix applied to any one of them reached none of the
others (MEDI-36).  One import is the whole remedy.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_score_trends.py
  - maxpane_dashboard/widgets/cattown/ct_sparklines.py
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline_from_points as _build_sparkline,
    coerce_points as _coerce_points,
    fmt_compact as _fmt_value,
    trend_arrow as _trend_arrow,
)


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

        Every series is coerced before use, so a cache that came back with
        ``None`` entries or ragged rows renders an empty line instead of
        raising inside Textual's message pump.
        """
        series = [
            ("Metric 1", series_0, "green", ""),
            ("Metric 2", series_1, "cyan", ""),
            ("Metric 3", series_2, "yellow", ""),
        ]

        line_ids = ["game-chart-line-0", "game-chart-line-1", "game-chart-line-2"]

        for i, (label, points, color, unit) in enumerate(series):
            widget = self.query_one(f"#{line_ids[i]}", Static)

            points = _coerce_points(points)
            if not points:
                widget.update("")
                continue

            sparkline = _build_sparkline(points)
            current = points[-1][1]
            current_str = _fmt_value(current, unit)
            arrow = _trend_arrow(points)

            padded_label = label[:8].ljust(8)
            widget.update(
                f"  [dim]{padded_label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )
