"""Primitive read-only scan contract; amounts are token units and estimated USD.

The upstream scanner quotes combined chain/token exposure once, then apportions
value to wallet/stake/reward rows. No field is an executable or net-of-gas quote.
"""
CHAINS = (1, 8453, 4663)
BUCKETS = ('wallet', 'staked', 'ready', 'locked', 'pending', 'unknown_reward')
SNAPSHOT_KEYS = ('wallet', 'state', 'as_of', 'assets', 'positions', 'rewards', 'nfts',
                 'standings', 'utilities', 'chains', 'coverage', 'error',
                 'seats', 'seats_as_of', 'seats_state')
WIDGET_SIGNATURES = {'SwarmPortfolioOverview': ('snapshot',)}


def empty_snapshot(wallet=None):
    result = dict.fromkeys(SNAPSHOT_KEYS)
    result.update(wallet=wallet, state='empty' if wallet is None else 'loading',
                  chains=[], coverage={}, seats_state='unavailable')
    return result
