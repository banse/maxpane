"""Frozen primitive payload for the mock SWARM TOKENS preview.

The market values are illustrative, never live quotes. ``None`` means unknown;
zero is a known measurement. A sparkline is 24 evenly spaced price samples over
the same 24-hour window, or None when that history is not available.
"""

TOKEN_KEYS = (
    'id', 'launch_id', 'symbol', 'name', 'chain', 'launched_at',
    'price_usd', 'change_24h', 'mcap_usd', 'volume_24h', 'buys_24h', 'sells_24h',
    'paired_amount', 'paired_symbol', 'lp_state', 'sparkline', 'verdict',
    'status', 'fdv_usd', 'fee_pct',
)
ACTIVITY_KEYS = ('id', 'token_id', 'ts', 'kind', 'amount', 'asset')
SNAPSHOT_KEYS = ('tokens', 'activity', 'as_of', 'is_mock')
METRIC_KEYS = (
    'total', 'new_24h', 'two_sided', 'one_sided', 'unknown', 'other',
    'volume_24h', 'volume_known', 'volume_total',
)
PROJECTION_KEYS = (
    'tokens', 'metrics', 'newly_launched', 'gainers', 'losers',
    'activity', 'as_of', 'is_mock',
)
WIDGET_SIGNATURES = {
    'TokensHero': ('metrics',),
    'TokensTable': ('tokens', 'as_of'),
    'NewlyLaunched': ('newly_launched', 'as_of'),
    'BestPlays': ('gainers', 'losers'),
    'TokenActivity': ('activity', 'tokens'),
}
