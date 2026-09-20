"""Two-row sparkline widget for the TTT dashboard.

Renders two parallel ASCII sparklines sharing a single time axis:

* **BURNS** -- cumulative burn count over the last 168 hours (orange).
* **24H VOLUME $** -- total 24h USD volume across all tokens, sampled hourly (cyan).

Each input is a list of ``(unix_timestamp, value)`` tuples (or 2-element
lists -- some serializers degrade tuples to lists).  When a series has
fewer than 2 samples we render ``"waiting for data..."`` instead of an
empty bar, so the user sees the dashboard is alive but the series isn't
ready yet.

The title, its blank row, the label column, the sparkline loop and the
waiting line are
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel`'s (Branch 7,
WP-B); the numbers below are this panel's own -- a 12-cell label column,
no trend arrow, the waiting line kept beside its label so the reader can
tell which of the two series is not ready, and ``MIN_POINTS = 2``,
because a single sample would be drawn as a flat baseline and a flat
baseline reads as a run of zeroes that never happened.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.panels import SparklinePanel

#: The ``unit`` tag :meth:`TTTSparkline.fmt_value` switches on. The two
#: series are not the same kind of number -- one counts NFTs, the other
#: is money -- and the hook is handed the unit precisely so one override
#: can tell them apart without a second widget.
_BURNS = "burns"
_USD = "usd"


def _fmt_volume_usd(value: float) -> str:
    """Format USD volume with K/M/B suffix.

    **Not** ``sparkline_common.fmt_compact``, which is the base's default:
    this renders two decimals and a leading ``$`` (``$1.23M``) where
    ``fmt_compact`` renders one and none (``1.2M``). Both are on screen
    beside a price, so the digits are a pixel, and this branch moves none.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "--"
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.2f}K"
    return f"${v:.0f}"


class TTTSparkline(SparklinePanel):
    """Two stacked sparklines: cumulative burns + 24h volume."""

    TITLE = "TRENDS (7d)"

    LINE_IDS = ("ttt-spark-burns", "ttt-spark-volume")

    #: ``24H VOLUME $`` is 12 cells, so both sparklines start in the same
    #: column.
    LABEL_WIDTH = 12

    #: No trend arrow: this panel never drew one, and the arrow brings a
    #: leading space that would be a ragged cell at the end of the row.
    SHOW_ARROW = False

    EMPTY_TEXT = "[dim]waiting for data...[/]"

    EMPTY_KEEPS_LABEL = True

    MIN_POINTS = 2

    def fmt_value(self, value, unit: str) -> str:
        """Burns are a grouped count; volume is money with a ``$`` and 2 dp."""
        if unit == _USD:
            return _fmt_volume_usd(value)
        return fmt_int(value)

    def update_data(
        self,
        burns_history: list[tuple[float, float]] | None = None,
        volume_history: list[tuple[float, float]] | None = None,
        **_kwargs,  # tolerate stale floor_history kwarg from screen until B3 lands
    ) -> None:
        """Refresh both rows.

        ``*_history`` may be ``None``, an empty list, or a list of
        ``(ts, value)`` tuples / 2-element lists.  Anything shorter than
        2 points renders the ``waiting for data...`` placeholder.
        """
        self.render_series([
            ("BURNS", burns_history, "#ffa500", _BURNS),
            ("24H VOLUME $", volume_history, "cyan", _USD),
        ])
