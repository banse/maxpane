"""Base Trading Overview widgets (Bakery-style layout)."""

# Legacy overview panel (kept for disabled views)
from maxpane_dashboard.widgets.base.overview._legacy_overview import OverviewPanel

# New overview widgets
from maxpane_dashboard.widgets.base.overview.bt_hero_metrics import BTHeroBox, BTOverviewHero
from maxpane_dashboard.widgets.base.overview.bt_overview_leaderboard import BTOverviewLeaderboard
from maxpane_dashboard.widgets.base.overview.bt_sparklines import BTSparklines
from maxpane_dashboard.widgets.base.overview.bt_signals import BTSignals
from maxpane_dashboard.widgets.base.overview.bt_activity_feed import BTActivityFeed
from maxpane_dashboard.widgets.base.overview.bt_best_plays import BTBestPlays

__all__ = [
    "OverviewPanel",
    "BTHeroBox",
    "BTOverviewHero",
    "BTOverviewLeaderboard",
    "BTSparklines",
    "BTSignals",
    "BTActivityFeed",
    "BTBestPlays",
]
