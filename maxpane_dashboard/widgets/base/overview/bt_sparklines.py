"""Trend sparklines for the Base Trading Overview view.

Three stacked series -- 24h volume, ETH price and hourly trade count -- on
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel` (Branch 8, WP-A),
whose loop replaces the copy's own ``_build_sparkline`` / ``_format_value``
/ ``_trend_arrow`` (one of the eight older sparkline copies
``widgets/sparkline_common`` listed as not yet converged). The numbers
below are this panel's own: a 10-cell label column, a **20-cell** bar
where the shared default is 22 (the panel is laid out for it), the trend
arrow kept, the ``waiting for data...`` line beside its label, and a value
cell that keeps the copy's ``$`` prefix and ``/h`` suffix.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SparklinePanel

#: The ``unit`` tags :meth:`BTSparklines.fmt_value` switches on. Volume and
#: price are dollars; trades are a rate per hour. The hook is handed the
#: unit so one override can tell them apart.
_USD = "usd"
_PER_HOUR = "per_hour"


def _fmt_magnitude(value: float) -> str:
    """K/M/B at one decimal, else grouped with none -- the copy's spelling.

    **Not** ``sparkline_common.fmt_compact``, which is the base's default:
    below a thousand that renders one decimal (``950.0``) where this panel
    shows ``950``, and every trade-count sample the manager records sits in
    that range. The digits are a pixel, and this branch moves none.
    """
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


class BTSparklines(SparklinePanel):
    """Sparkline charts showing volume, ETH price, and trade count trends."""

    TITLE = "TRENDS"

    LINE_IDS = ("bto-chart-line-0", "bto-chart-line-1", "bto-chart-line-2")

    #: ``Volume`` / ``ETH`` / ``Trades`` padded to ten, so the three bars
    #: start in the same column.
    LABEL_WIDTH = 10

    #: The copy drew a 20-cell bar; the shared default is 22.
    SPARK_WIDTH = 20

    #: Stated rather than inherited so the panel's knobs read in one place;
    #: this panel always drew its arrow.
    SHOW_ARROW = True

    EMPTY_TEXT = "[dim]waiting for data...[/]"

    EMPTY_KEEPS_LABEL = True

    def fmt_value(self, value, unit: str) -> str:
        """``$1.2M`` for dollars, ``950/h`` for the trade rate."""
        if unit == _USD:
            return f"${_fmt_magnitude(value)}"
        if unit == _PER_HOUR:
            return f"{_fmt_magnitude(value)}/h"
        return _fmt_magnitude(value)

    def update_data(
        self,
        volume_history: list | None = None,
        eth_price_history: list | None = None,
        trade_count_history: list | None = None,
    ) -> None:
        """Render sparklines for volume, ETH price, and trade count."""
        self.render_series([
            ("Volume", volume_history, "cyan", _USD),
            ("ETH", eth_price_history, "green", _USD),
            ("Trades", trade_count_history, "yellow", _PER_HOUR),
        ])
