"""BakeryScreen -- RugPull Bakery game dashboard as a Textual Screen.

One transcription note. This is the only screen whose hand-written dispatch read
its payload by **subscript** rather than ``data.get`` -- every panel, all
twenty-one keys from ``data["prize_pool_eth"]`` through ``data["poll_interval"]``,
not just ``data["bakeries"]`` -- so a key the manager had not produced raised
``KeyError`` before that panel was touched and the panel kept its last render. ``keys(...)`` reads with ``data.get``
instead, so such a panel now receives an explicit ``None``. That is not a
behaviour change against the real manager:
:meth:`maxpane_dashboard.data.manager.DataManager.fetch_and_compute` builds its
payload as one dict literal in which every key below is always present, so the
two reads are the same read. It is only visible under a hand-built partial
payload, and there the composited render is identical at 170 columns and at the
layout pin (measured before and after on the address sweep's own bakery payload,
which carries none of ``chart_histories`` / ``late_join_ev`` / ``boost_rankings``).
Keeping the subscript would have cost more than it bought: an adapter that raises
on a partial payload cannot be read by
``test_every_panel_row_names_a_mounted_widget_and_its_update_data_keywords``,
which would leave bakery the one dashboard with no enforcement at all -- the
exact hole this branch exists to close.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from maxpane_dashboard.analytics.ev import CATALOG_SOURCE_LIVE
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.hero_metrics import HeroMetrics
from maxpane_dashboard.widgets.leaderboard import Leaderboard
from maxpane_dashboard.widgets.cookie_chart import CookieChart
from maxpane_dashboard.widgets.activity_feed import ActivityFeed
from maxpane_dashboard.widgets.signals_panel import SignalsPanel
from maxpane_dashboard.widgets.ev_table import EVTable
from maxpane_dashboard.widgets.status_bar import StatusBar


def _cookie_chart(data: dict) -> dict:
    """The one panel whose keyword is not its payload key."""
    return {"histories": data.get("chart_histories")}


def _ev_table(data: dict) -> dict:
    """Two required rankings plus the catalog source, which has a fallback."""
    return {
        "boost_rankings": data.get("boost_rankings"),
        "attack_rankings": data.get("attack_rankings"),
        "catalog_source": data.get("ev_catalog_source", CATALOG_SOURCE_LIVE),
    }


class BakeryScreen(DashboardScreen):
    """RugPull Bakery game dashboard."""

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "rugpull bakery"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "bakery-refresh"

    #: Transcribed from the six hand-written dispatch blocks, in the same
    #: order (see the module docstring on the one read that changed shape);
    #: the status bar is updated by the base.
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
        (EVTable, _ev_table),
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
        title = self.query_one("#title-bar", Static)
        title.update(
            f"RugPull Bakery · Season {data['season_id']}"
        )
