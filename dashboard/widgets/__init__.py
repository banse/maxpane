"""Dashboard widget components."""

from dashboard.widgets.hero_metrics import HeroMetrics
from dashboard.widgets.leaderboard import Leaderboard
from dashboard.widgets.cookie_chart import CookieChart
from dashboard.widgets.activity_feed import ActivityFeed
from dashboard.widgets.signals_panel import SignalsPanel
from dashboard.widgets.ev_table import EVTable
from dashboard.widgets.status_bar import StatusBar

__all__ = [
    "HeroMetrics",
    "Leaderboard",
    "CookieChart",
    "ActivityFeed",
    "SignalsPanel",
    "EVTable",
    "StatusBar",
]
