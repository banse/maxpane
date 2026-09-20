"""Leaderboard table showing top bakeries.

On ``widgets/panels.py`` since Branch 8 WP-B: a
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`, which owns the
title, its blank row, the column set-up and the per-row guard (one bakery
the formatter cannot read is one missing line, not an empty board).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maxpane_dashboard.analytics.leaderboard import format_cookies, format_gap
from maxpane_dashboard.analytics.production import format_rate
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE, TableLeaderboard

if TYPE_CHECKING:
    from maxpane_dashboard.data.models import BakerySummary

#: ``tx_count`` is the effective cookie count scaled by this.
_COOKIE_SCALE = 10_000


class Leaderboard(TableLeaderboard):
    """Leaderboard panel with DataTable of top bakeries."""

    TITLE = "LEADERBOARD"
    TABLE_ID = "leaderboard-table"
    COLUMNS = (
        ("#", 4),
        ("Bakery", 24),
        ("Cookies", 10),
        ("Δ/hr", 12),
        ("Gap", 8),
    )
    EMPTY_ROW = ("--", "No data", "--", "--", "--")
    #: The row for "the bakeries fetch failed", distinct from an empty board
    #: (follow-up #35). Painted through :meth:`render_table`'s *footer* -- the
    #: one row the base lands with no ``No data`` above it.
    UNAVAILABLE_ROW = ("--", UNAVAILABLE, "--", "--", "--")

    # Geometry only: the title's colour and blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    Leaderboard > DataTable {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._production_rates: dict = {}
        self._leader_cookies: float | None = None

    def update_data(
        self,
        bakeries: list[BakerySummary] | None,
        production_rates: dict[str, float],
        prize_pool_usd: float,
    ) -> None:
        """Clear and repopulate the leaderboard table with live data.

        *bakeries* is ``None`` when the client could not read the board;
        that paints :attr:`UNAVAILABLE_ROW`, not the ``No data`` an empty
        board earns (follow-up #35).
        """
        self._production_rates = (
            production_rates if isinstance(production_rates, dict) else {}
        )
        self._leader_cookies = None
        if bakeries is None:
            self.render_table([], footer=self.UNAVAILABLE_ROW)
            return
        if bakeries:
            try:
                self._leader_cookies = int(bakeries[0].tx_count) / _COOKIE_SCALE
            except Exception:
                # Every row's gap is measured against this; a leader whose
                # count cannot be read leaves the column saying so.
                self._leader_cookies = None
        self.render_table(bakeries)

    def build_row(self, index: int, bakery) -> tuple:
        cookies = int(bakery.tx_count) / _COOKIE_SCALE
        rate = self._production_rates.get(bakery.name, 0.0)

        cookies_str = format_cookies(cookies)
        rate_str = format_rate(rate)
        gap_str = (
            format_gap(cookies, self._leader_cookies)
            if self._leader_cookies is not None else "--"
        )

        # Player-chosen name: escape before it reaches markup rendering.
        safe_name = safe_markup(bakery.name)

        # Highlight the leader row
        if index == 0:
            name_str = f"[bold]{safe_name}[/]"
            cookies_str = f"[bold]{cookies_str}[/]"
            rate_str = f"[green]{rate_str}[/]"
        else:
            name_str = safe_name

        return (str(index + 1), name_str, cookies_str, rate_str, gap_str)
