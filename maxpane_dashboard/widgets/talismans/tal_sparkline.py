"""Two-row sparkline widget for the Talismans dashboard.

Renders two parallel ASCII sparklines:

* **MYTHIC COUNT**     -- Mythic talisman count over time (violet).
* **DAILY OPERATIONS** -- operation count sampled per day (cyan).

Each input is a list of ``[ts, value]`` lists (or 2-element tuples --
some serializers degrade tuples to lists).  When a series has fewer than
2 samples we render ``"waiting for data..."`` instead of an empty bar, so
the user sees the dashboard is alive but the series isn't ready yet.

The title, its blank row, the label column, the sparkline loop and the
waiting line are
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel`'s (Branch 7,
WP-B); this module states the four numbers that are its own -- a 16-cell
label column, no trend arrow, the waiting line kept **beside its label**
(``EMPTY_KEEPS_LABEL``: with two stacked series the reader has to be able
to tell *which* one is not ready), and ``MIN_POINTS = 2``, because
``build_sparkline_from_points`` draws a single sample as a flat baseline
and a flat baseline is a run of zeroes that never happened.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.panels import SparklinePanel


class TalismansSparkline(SparklinePanel):
    """Two stacked sparklines: Mythic count + daily operations."""

    TITLE = "TRENDS"

    LINE_IDS = ("tal-spark-mythic", "tal-spark-ops")

    #: Both labels are 16 cells wide (``DAILY OPERATIONS``), so the two
    #: sparklines start in the same column.
    LABEL_WIDTH = 16

    #: No trend arrow: this panel never drew one, and the arrow brings a
    #: leading space that would be a ragged cell at the end of the row.
    SHOW_ARROW = False

    EMPTY_TEXT = "[dim]waiting for data...[/]"

    EMPTY_KEEPS_LABEL = True

    MIN_POINTS = 2

    def fmt_value(self, value, unit: str) -> str:
        """A grouped integer, not ``fmt_compact``.

        Both series are counts of whole things -- Mythics and operations --
        and both sit in the low thousands, where ``fmt_compact`` would print
        ``1.5K`` for a number the panel has room to show exactly. This is
        the hoisted ``fmt.fmt_int``: the copy it replaces (``_fmt_count``)
        was one of six identical ones.
        """
        return fmt_int(value)

    def update_data(
        self,
        mythic_history=None,
        operations_history=None,
        **_kwargs,
    ) -> None:
        """Refresh both rows.

        ``*_history`` may be ``None``, an empty list, or a list of
        ``[ts, value]`` lists / tuples.  Anything shorter than 2 points
        renders the ``waiting for data...`` placeholder.
        """
        self.render_series([
            ("MYTHIC COUNT", mythic_history, "#8a6fd6", ""),
            ("DAILY OPERATIONS", operations_history, "cyan", ""),
        ])
