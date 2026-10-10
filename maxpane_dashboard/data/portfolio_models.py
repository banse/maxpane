"""Primitive contracts for live PORTFOLIO and its isolated offline preview.

Amounts are whole-token quantities. Ready claims exclude locked and already
claimed allocations. Unknown measurements remain None; zero is a known read.
Optional claim detail keys are locked_quantity, unlock_at and claim_reason.
"""

from maxpane_dashboard.data.swarm_tokens_models import (
    ACTIVITY_KEYS, TOKEN_KEYS as MARKET_TOKEN_KEYS, LIVE_TOKEN_KEYS as MARKET_LIVE_TOKEN_KEYS,
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

# Live sources keep their own successful clocks; evaluation time is not freshness.
# Existing mock tuples stay stable so no synthetic field can become a live default.
BALANCE_KEYS = ('balance_raw', 'decimals', 'held_quantity', 'balance_state',
                'balance_read_at', 'balance_block')
LIVE_TOKEN_KEYS = MARKET_LIVE_TOKEN_KEYS + TOKEN_KEYS[len(MARKET_TOKEN_KEYS):] + (
    'balance_raw', 'decimals', 'balance_read_at', 'balance_block',
    'claim_read_at', 'claim_reason', 'locked_quantity', 'claimed_quantity', 'unlock_at',
    'basis_state', 'basis_read_at', 'basis_reason', 'basis_quantity', 'basis_source',
)
LIVE_SNAPSHOT_KEYS = SNAPSHOT_KEYS + ('wallet_generation', 'sources')
LIVE_PROJECTION_KEYS = PROJECTION_KEYS + ('wallet_generation', 'sources')
LIVE_METRIC_KEYS = METRIC_KEYS + ('held_partial', 'claimable_partial', 'agents_state', 'agents_as_of')

# Client read boundaries (managers own retries, generation guards and last-good).
# read_balances(wallet, tokens) -> {token_id: {BALANCE_KEYS}}
# fetch_claims(wallet) -> {allocations: list|None, agents: list|None, sources: dict}
# Each allocation carries chain_id/token_address/launch_uuid, allocation_id,
# claimable_quantity, locked_quantity, claimed_quantity, claim_state,
# claim_read_state/read_at, unlock_at and claim_reason. Verified source evidence
# decides readiness; allocation presence alone never proves an unclaimed reward.
# A source dict has state, as_of, complete and optional checked/total/reason.
# basis_state='unavailable' and held_cost_usd=None until provenance is established.
# Live token unlock_at is Unix seconds or None; the manager normalizes client ISO timestamps.
