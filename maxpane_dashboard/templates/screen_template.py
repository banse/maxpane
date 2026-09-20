"""BakeryScreen -- RugPull Bakery game dashboard as a Textual Screen.

Copy-source for a new dashboard screen. Copy it, rename the class, set
``GAME_NAME`` / ``REFRESH_WORKER_NAME``, list your panels in ``PANELS`` and
write ``compose``. Everything else -- the constructor, the resume/suspend
lifecycle, the guarded refresh and the whole fetch-to-widget dispatch -- lives
in :class:`~maxpane_dashboard.screens.dashboard_screen.DashboardScreen` and
must not be copied back in. A screen that hand-writes a
``try: self.query_one(W).update_data(...) except`` block per panel is the
pattern Branch 5 removed (151 of them across 14 screens); a copy of that shape
here would put it straight back into dashboard number fifteen.

Read ``screens/ocm.py`` for a migrated screen and ``screens/dashboard_screen.py``
for the contract.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.hero_metrics import HeroMetrics
from maxpane_dashboard.widgets.leaderboard import Leaderboard
from maxpane_dashboard.widgets.cookie_chart import CookieChart
from maxpane_dashboard.widgets.activity_feed import ActivityFeed
from maxpane_dashboard.widgets.signals_panel import SignalsPanel
from maxpane_dashboard.widgets.ev_table import EVTable
from maxpane_dashboard.widgets.status_bar import StatusBar


def _cookie_chart(data: dict) -> dict:
    """An adapter for a panel whose keyword is not the payload's key.

    ``keys(...)`` covers the dominant shape -- keyword and payload key are the
    same word. Anything else (a rename, or a value computed from several keys)
    is a plain module-level function taking ``data`` and returning the keyword
    arguments, exactly like this one.
    """
    return {"histories": data.get("chart_histories")}


class BakeryScreen(DashboardScreen):
    """RugPull Bakery game dashboard."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "rugpull bakery"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "bakery-refresh"

    #: The dispatch, as data: one row per panel, in update order. Each adapter
    #: maps the manager's flat payload to that widget's ``update_data`` keyword
    #: arguments; ``keys(...)`` is the plain ``data.get`` shape, and a key that
    #: needs a fallback names it (``recommendation=""``). The status bar is not
    #: a row -- the base always updates it last.
    PANELS = (
        (
            HeroMetrics,
            keys(
                "prize_pool_eth",
                "prize_pool_usd",
                "hours_remaining",
                "season_id",
                "season_active",
                "leader_name",
                "leader_cookies",
                "leader_rate",
            ),
        ),
        (Leaderboard, keys("bakeries", "production_rates", "prize_pool_usd")),
        (CookieChart, _cookie_chart),
        (ActivityFeed, keys("events")),
        (
            SignalsPanel,
            keys("late_join_ev", "gap_analysis", "dominance", "recommendation"),
        ),
        (EVTable, keys("boost_rankings", "attack_rankings")),
    )

    def compose(self) -> ComposeResult:
        # Title bar
        yield Static(
            "RugPull Bakery · Season ?",
            id="title-bar",
        )

        # Hero metrics row
        yield HeroMetrics()

        # Middle row: leaderboard (left) | cookie chart + signals (right)
        with Horizontal(id="middle-row"):
            yield Leaderboard()
            with Vertical(id="right-col"):
                yield CookieChart()
                yield SignalsPanel()

        # Dashed separator
        yield Static(
            "─" * 300,
            id="separator",
        )

        # Bottom row: activity feed (left) | EV table (right)
        with Horizontal(id="bottom-row"):
            yield ActivityFeed()
            yield EVTable()

        # Status bar
        yield StatusBar()

    def _update_title(self, data: dict) -> None:
        """Hook: the one thing this screen shows outside a panel.

        The base calls it with the fetched payload and contains anything it
        raises, so there is no ``try`` to copy here.
        """
        self.query_one("#title-bar", Static).update(
            f"RugPull Bakery · Season {data.get('season_id')}"
        )
