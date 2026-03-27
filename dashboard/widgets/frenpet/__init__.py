"""FrenPet widgets for General, Wallet, and Pet views."""

from dashboard.widgets.frenpet.action_queue import ActionQueue
from dashboard.widgets.frenpet.aggregate_stats import AggregateStats
from dashboard.widgets.frenpet.alerts import AlertsPanel
from dashboard.widgets.frenpet.battle_feed import BattleFeed
from dashboard.widgets.frenpet.battle_log import BattleLog
from dashboard.widgets.frenpet.game_stats import GameStats
from dashboard.widgets.frenpet.logo import FrenPetLogo
from dashboard.widgets.frenpet.market_conditions import MarketConditions
from dashboard.widgets.frenpet.next_actions import NextActions
from dashboard.widgets.frenpet.pet_card import PetCard
from dashboard.widgets.frenpet.pet_signals import PetSignals
from dashboard.widgets.frenpet.pet_stats import PetStats
from dashboard.widgets.frenpet.pets_in_context import PetsInContext
from dashboard.widgets.frenpet.population import Population
from dashboard.widgets.frenpet.score_dist import ScoreDistribution
from dashboard.widgets.frenpet.score_trend import ScoreTrend
from dashboard.widgets.frenpet.sniper_queue import SniperQueue
from dashboard.widgets.frenpet.target_landscape import TargetLandscape
from dashboard.widgets.frenpet.top_leaderboard import TopLeaderboard
from dashboard.widgets.frenpet.training_status import TrainingStatus
from dashboard.widgets.frenpet.wallet_activity import WalletActivity

__all__ = [
    "ActionQueue",
    "AggregateStats",
    "AlertsPanel",
    "BattleFeed",
    "BattleLog",
    "FrenPetLogo",
    "GameStats",
    "MarketConditions",
    "NextActions",
    "PetCard",
    "PetSignals",
    "PetStats",
    "PetsInContext",
    "Population",
    "ScoreDistribution",
    "ScoreTrend",
    "SniperQueue",
    "TargetLandscape",
    "TopLeaderboard",
    "TrainingStatus",
    "WalletActivity",
]
