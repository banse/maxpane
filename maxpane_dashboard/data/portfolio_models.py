"""Primitive contract for the offline PORTFOLIO preview.

Amounts are whole-token quantities. Ready claims exclude locked and already
claimed allocations. Unknown measurements remain None; zero is a known read.
Optional claim detail keys are locked_quantity, unlock_at and claim_reason.
"""

from maxpane_dashboard.data.swarm_tokens_models import (
    ACTIVITY_KEYS, TOKEN_KEYS as MARKET_TOKEN_KEYS,
)

TOKEN_KEYS = MARKET_TOKEN_KEYS + (
    'held_quantity', 'claimable_quantity', 'claim_state',
    'balance_state', 'claim_read_state', 'held_cost_usd',
)
SNAPSHOT_KEYS = ('tokens', 'activity', 'as_of', 'is_mock', 'wallet', 'agents')
METRIC_KEYS = (
    'total', 'held_value', 'held_known', 'held_total',
    'claimable_value', 'claimable_known', 'claimable_total',
    'agents_total', 'agents_online',
    'liquidity_imd', 'liquidity_eth', 'liquidity_partial',
    'pnl_usd', 'pnl_percent',
)
PROJECTION_KEYS = (
    'wallet', 'tokens', 'metrics', 'claimable', 'gainers', 'losers',
    'activity', 'agents', 'as_of', 'is_mock',
)
WIDGET_SIGNATURES = {
    'PortfolioHero': ('metrics',),
    'PortfolioTable': ('tokens', 'as_of'),
    'ClaimableTokens': ('claimable',),
    'BestPlays': ('gainers', 'losers'),
    'TokenActivity': ('activity', 'tokens'),
}
