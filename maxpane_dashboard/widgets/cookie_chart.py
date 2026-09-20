"""Cookie trend sparkline charts.

On ``widgets/panels.py`` since Branch 8 WP-B: a
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel` with the copy's
30-cell bar, drawing the top three bakeries' histories through the shared
``sparkline_common`` primitives (MEDI-36).
"""

from __future__ import annotations

from maxpane_dashboard.analytics.leaderboard import format_cookies
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE_LINE, SparklinePanel

#: Line colour per rank.
_COLORS = ("green", "cyan", "yellow")


class CookieChart(SparklinePanel):
    """Block sparkline chart showing cookie production trends."""

    TITLE = "COOKIE TRENDS (30m)"
    LINE_IDS = ("chart-line-0", "chart-line-1", "chart-line-2")
    #: The copy's ``_SPARK_WIDTH``; the right column is laid out for it.
    SPARK_WIDTH = 30

    def fmt_value(self, value, unit: str) -> str:
        """Cookie counts, as the leaderboard prints them."""
        return format_cookies(value)

    def _label_cell(self, label) -> str:
        """The base's clip-and-pad, then escaped.

        Escaping **after** the clip: a player-chosen name is clipped to eight
        characters and must reach the screen whole. Escaping first would put
        a backslash in front of any ``[`` and the clip would then cut the
        name's last character instead.
        """
        return safe_markup(super()._label_cell(label))

    def update_data(
        self,
        histories: dict[str, list[tuple[float, float]]],
    ) -> None:
        """Render sparklines for the top 3 bakeries.

        ``histories`` is a dict from the manager on every poll. Anything else
        is a read that failed and says so on the first line (MEDI-38) --
        distinct from ``{}``, a read that found nobody, which blanks all
        three.
        """
        if not isinstance(histories, dict):
            self.write(f"#{self.LINE_IDS[0]}", UNAVAILABLE_LINE)
            for line_id in self.LINE_IDS[1:]:
                self.write(f"#{line_id}", "")
            return

        names = list(histories.keys())[: len(self.LINE_IDS)]
        series = []
        for i, color in enumerate(_COLORS):
            if i < len(names):
                series.append((names[i], histories[names[i]], color, ""))
            else:
                series.append(("", [], color, ""))
        self.render_series(series)
