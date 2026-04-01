"""FrenPet Overview widgets (Bakery-style layout)."""

from maxpane_dashboard.widgets.frenpet.overview.fp_hero_metrics import FPHeroBox, FPOverviewHero
from maxpane_dashboard.widgets.frenpet.overview.fp_overview_leaderboard import FPOverviewLeaderboard
from maxpane_dashboard.widgets.frenpet.overview.fp_score_trends import FPScoreTrends
from maxpane_dashboard.widgets.frenpet.overview.fp_game_signals import FPGameSignals
from maxpane_dashboard.widgets.frenpet.overview.fp_battle_activity import FPBattleActivity
from maxpane_dashboard.widgets.frenpet.overview.fp_best_plays import FPBestPlays

__all__ = [
    "FPHeroBox",
    "FPOverviewHero",
    "FPOverviewLeaderboard",
    "FPScoreTrends",
    "FPGameSignals",
    "FPBattleActivity",
    "FPBestPlays",
]
