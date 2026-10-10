"""Fixed synthetic portfolio data; no wallet reads, clients or persistence."""

from maxpane_dashboard.data.swarm_tokens_demo import MOCK_NOW, _token

SAMPLE_WALLET = 'sample'

# The existing market fixture builder supplies the same primitive market data
# and synthetic 24-hour price samples used by the SWARM TOKENS preview.
_MARKET_ROWS = (
    (401, 'TIDE', 'Tide Pool', 'eth', 24, .01, 8.2, 84000, 412, 208,
     120000, 'IMD', 'two-sided'),
    (398, 'KITE', 'Kite', 'base', 48, .02, -1.4, 24000, 94, 108,
     2.4, 'ETH', 'two-sided'),
    (392, 'FOAM', 'Foam', 'rh', 72, .004, 3.7, 18000, 82, 44,
     80000, 'IMD', 'two-sided'),
    (387, 'MESH', 'Mesh', 'eth', 96, .17, -2.4, 32000, 142, 198,
     1.8, 'ETH', 'two-sided'),
)
_QUANTITIES = ((100000, 20000), (40000, 0), (0, 50000), (10000, 0))
# Invented remaining-position cost basis, solely for the labeled offline preview.
_HELD_COSTS = (800, 900, 0, 1600)


def demo_snapshot(wallet: str | None = None) -> dict:
    """Return detached mock data, or the unconfigured-wallet empty state.

Any supplied identity selects the same invented example. SAMPLE_WALLET lets a
standalone preview request that example without inventing an onchain address.
"""
    wallet = wallet.strip() or None if wallet is not None else None
    tokens = []
    if wallet is not None:
        for row, (held, claimable), cost in zip(_MARKET_ROWS, _QUANTITIES, _HELD_COSTS):
            tokens.append(dict(
                _token(row), held_quantity=held, claimable_quantity=claimable,
                claim_state='ready' if claimable else 'none',
                balance_state='ok', claim_read_state='ok', held_cost_usd=cost,
            ))
    activities = (
        ('eth:401', 0, 'BUY', 240), ('base:398', 3, 'SELL', 95),
        ('rh:392', 7, 'BUY', 180), ('eth:387', 11, 'SELL', 120),
    )
    return {
        'tokens': tokens,
        'activity': [
            {'id': f'portfolio-demo:{index}', 'token_id': token,
             'ts': MOCK_NOW-minutes*60, 'kind': kind, 'amount': amount, 'asset': 'USD'}
            for index, (token, minutes, kind, amount) in enumerate(activities)
        ] if wallet is not None else [],
        'as_of': MOCK_NOW, 'is_mock': True, 'wallet': wallet,
        'agents': [
            {'id': '420', 'online': True}, {'id': '77', 'online': True},
            {'id': '1548', 'online': False},
        ] if wallet is not None else [],
    }


class DemoPortfolioManager:
    """Wallet-scoped lifecycle adapter that only reconstructs local fixtures."""

    is_mock = True
    _error_count = 0

    def __init__(self, wallet: str | None = None) -> None:
        self._wallet = None
        self.set_wallet(wallet)

    @property
    def wallet(self) -> str | None:
        return self._wallet

    def set_wallet(self, address: str | None) -> bool:
        wallet = address.strip() or None if address is not None else None
        changed = wallet != self._wallet
        self._wallet = wallet
        return changed

    async def fetch_and_compute(self) -> dict:
        return demo_snapshot(self.wallet)

    async def close(self) -> None:
        pass
