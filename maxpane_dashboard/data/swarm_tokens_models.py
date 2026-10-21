"""Primitive payload shared by live SWARM TOKENS and its offline preview.

``None`` means unknown; zero is a known measurement. Live price history keeps
missing hourly samples as None within the same 24-hour window. Live tokens
carry their own source clocks; snapshot as_of is only the evaluation clock.
"""

TOKEN_KEYS = (
    'id', 'launch_id', 'symbol', 'name', 'chain', 'launched_at',
    'price_usd', 'change_24h', 'mcap_usd', 'volume_24h', 'buys_24h', 'sells_24h',
    'paired_amount', 'paired_symbol', 'lp_state', 'sparkline', 'verdict',
    'status', 'fdv_usd', 'fee_pct',
)
ACTIVITY_KEYS = ('id', 'token_id', 'ts', 'kind', 'amount', 'asset')
SNAPSHOT_KEYS = ('tokens', 'activity', 'as_of', 'is_mock')
LIVE_TOKEN_KEYS = TOKEN_KEYS + (
    'token_address', 'chain_id', 'launch_uuid', 'launch_uuids', 'launch_pool',
    'market_pool', 'market_source', 'market_read_at', 'liquidity_read_at',
    'history_read_at', 'trades_read_at', 'market_state', 'history_state',
    'liquidity_state', 'trades_state', 'sparkline_timestamps',
    'token_amount', 'withdrawn_pct',
)
LIVE_SNAPSHOT_KEYS = SNAPSHOT_KEYS + ('sources',)
METRIC_KEYS = (
    'total', 'new_24h', 'two_sided', 'one_sided', 'unknown', 'other',
    'volume_24h', 'volume_known', 'volume_total',
    'liquidity_imd', 'liquidity_eth', 'liquidity_partial',
)
PROJECTION_KEYS = (
    'tokens', 'metrics', 'newly_launched', 'gainers', 'losers',
    'activity', 'as_of', 'is_mock', 'tokens_hero',
)
# Source state and successful read clock belong to each section. No I/O or
# rendering types cross this seam; live timestamps never use evaluation time.
HERO_STATES = ('ok', 'partial', 'stale', 'unavailable')
HERO_FIELDS = {
    'tokens': ('state', 'read_ts', 'tracked', 'new_24h', 'chains'),
    'volume': ('state', 'read_ts', 'amount', 'known', 'total'),
    'liquidity': ('state', 'read_ts', 'imd', 'eth', 'known', 'total', 'partial'),
    'pools': ('state', 'read_ts', 'two_sided', 'one_sided', 'unknown', 'other'),
    'momentum': ('state', 'read_ts', 'rising', 'falling', 'flat', 'known', 'total'),
    'top_volume': ('state', 'read_ts', 'rows', 'known', 'total'),
}
HERO_VOLUME_ROW_FIELDS = ('symbol', 'volume_usd')
WIDGET_SIGNATURES = {
    'TokensHero': ('tokens_hero',),
    'TokensTable': ('tokens', 'as_of'),
    'NewlyLaunched': ('newly_launched', 'as_of'),
    'BestPlays': ('gainers', 'losers'),
    'TopTraded': ('tokens',),
    'TokenActivity': ('activity', 'tokens'),
}
