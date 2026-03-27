"""Base chain view widgets."""

from dashboard.widgets.base.fee_claims import FeeClaims
from dashboard.widgets.base.fee_leaderboard import FeeLeaderboard
from dashboard.widgets.base.fee_stats import FeeStats
from dashboard.widgets.base.gecko_pools import GeckoPools
from dashboard.widgets.base.graduated import GraduatedTokens
from dashboard.widgets.base.launch_feed import LaunchFeed
from dashboard.widgets.base.launch_stats import LaunchStats
from dashboard.widgets.base.pool_info import PoolInfo
from dashboard.widgets.base.price_sparklines import PriceSparklines
from dashboard.widgets.base.token_chart import TokenChart
from dashboard.widgets.base.token_price import TokenPrice
from dashboard.widgets.base.token_signals import TokenSignals
from dashboard.widgets.base.top_movers import TopMovers
from dashboard.widgets.base.trade_feed import TradeFeed
from dashboard.widgets.base.trending_table import TrendingTable
from dashboard.widgets.base.overview import OverviewPanel
from dashboard.widgets.base.volume_bars import VolumeBars
from dashboard.widgets.base.volume_sparklines import VolumeSparklines

__all__ = [
    "FeeClaims",
    "FeeLeaderboard",
    "FeeStats",
    "GeckoPools",
    "GraduatedTokens",
    "LaunchFeed",
    "LaunchStats",
    "OverviewPanel",
    "PoolInfo",
    "PriceSparklines",
    "TokenChart",
    "TokenPrice",
    "TokenSignals",
    "TopMovers",
    "TradeFeed",
    "TrendingTable",
    "VolumeBars",
    "VolumeSparklines",
]
