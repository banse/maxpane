"""Base chain view widgets."""

from maxpane_dashboard.widgets.base.fee_claims import FeeClaims
from maxpane_dashboard.widgets.base.fee_leaderboard import FeeLeaderboard
from maxpane_dashboard.widgets.base.fee_stats import FeeStats
from maxpane_dashboard.widgets.base.gecko_pools import GeckoPools
from maxpane_dashboard.widgets.base.graduated import GraduatedTokens
from maxpane_dashboard.widgets.base.launch_feed import LaunchFeed
from maxpane_dashboard.widgets.base.launch_stats import LaunchStats
from maxpane_dashboard.widgets.base.pool_info import PoolInfo
from maxpane_dashboard.widgets.base.price_sparklines import PriceSparklines
from maxpane_dashboard.widgets.base.token_chart import TokenChart
from maxpane_dashboard.widgets.base.token_price import TokenPrice
from maxpane_dashboard.widgets.base.token_signals import TokenSignals
from maxpane_dashboard.widgets.base.top_movers import TopMovers
from maxpane_dashboard.widgets.base.trade_feed import TradeFeed
from maxpane_dashboard.widgets.base.trending_table import TrendingTable
from maxpane_dashboard.widgets.base.overview import OverviewPanel
from maxpane_dashboard.widgets.base.volume_bars import VolumeBars
from maxpane_dashboard.widgets.base.volume_sparklines import VolumeSparklines

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
