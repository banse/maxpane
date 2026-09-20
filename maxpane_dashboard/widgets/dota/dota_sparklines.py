"""Sparkline charts for Defense of the Agents dashboard.

The sparkline primitives come from
``maxpane_dashboard/widgets/sparkline_common.py``.  This module used to
carry its own pre-hardening copies, which raised ``TypeError`` on a
``None`` entry or a ``None`` value in a cached history (MEDI-36); the
render loop itself is
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel`'s since Branch 7.

**The value formatter stays here.** Unlike ocm's and cattown's it is *not*
``sparkline_common.fmt_compact`` in disguise: a lane frontline is a
position between the two bases, so it has no K/M/B magnitudes at all and
switches on ``abs >= 100`` to drop its decimal place. ``fmt_compact`` would
print ``1.0K`` where this panel shows ``950``, and every frontline the game
serves is in the range where the two disagree.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SparklinePanel


def _fmt_frontline(value: float) -> str:
    """Format a numeric frontline value for display."""
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.1f}"


class DOTASparklines(SparklinePanel):
    """ASCII sparkline charts for lane frontline positions."""

    TITLE = "LANE FRONTLINES"

    LINE_IDS = ("dota-chart-line-0", "dota-chart-line-1", "dota-chart-line-2")

    #: The labels below are nine cells wide, one more than the default.
    LABEL_WIDTH = 9

    def fmt_value(self, value, unit: str) -> str:
        """A frontline position, not a magnitude (see the module docstring)."""
        return _fmt_frontline(value)

    def update_data(
        self,
        top_frontline_history: list[tuple[float, float]] | None = None,
        mid_frontline_history: list[tuple[float, float]] | None = None,
        bot_frontline_history: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for Top, Mid, and Bot lane frontlines."""
        self.render_series([
            ("Top Lane ", top_frontline_history, "green", ""),
            ("Mid Lane ", mid_frontline_history, "cyan", ""),
            ("Bot Lane ", bot_frontline_history, "yellow", ""),
        ])
