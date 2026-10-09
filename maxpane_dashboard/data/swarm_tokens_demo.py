"""Deterministic, entirely offline data for the SWARM TOKENS design preview.

These are invented market values, not evidence about the named launches. There
are no contract addresses, remote clients, persisted caches, or wallet access.
"""

MOCK_NOW = 1_791_572_400.0

# ID, symbol, name, chain, age hours, price, 24h change, 24h volume,
# buys, sells, paired amount, paired asset, LP state.
_TOKENS = (
    (1175, 'SC', 'Swarm Coin', 'eth', 48, .00420, 24.8, 82100, 412, 208, 788, 'IMD', 'two-sided'),
    (1170, 'MEAT', 'Meat Market', 'eth', 72, .00118, 12.4, 46300, 236, 184, 2.84, 'ETH', 'two-sided'),
    (737, 'ZTO', 'Zero to One', 'eth', 168, .00860, -3.2, 31400, 142, 198, 4727, 'IMD', 'two-sided'),
    (1168, 'TESTER', 'Test Flight', 'base', 120, .00034, 8.6, 14800, 94, 72, 128, 'IMD', 'two-sided'),
    (996, 'FROG', 'Swarm Frog', 'rh', 288, .00210, -10.6, 6200, 38, 82, 420, 'IMD', 'two-sided'),
    (1178, 'CLAUS', 'Claus', 'eth', 4/60, None, None, 0, 0, 0, 0, 'ETH', 'one-token'),
    (1177, 'NOVA', 'Nova', 'base', 28/60, None, None, 0, 0, 0, 0, 'IMD', 'one-token'),
    (1176, 'ORB', 'Orbit', 'rh', 2, None, None, None, None, None, None, 'IMD', 'unknown'),
    (902, 'VOID', 'Void', 'eth', 360, None, None, None, None, None, 0, 'IMD', 'withdrawn'),
    (1159, 'BEAM', 'Beam', 'base', 144, .00612, 6.3, 10800, 82, 44, .85, 'ETH', 'two-sided'),
    (1154, 'TIDE', 'Tide Pool', 'rh', 192, .00081, -6.5, 5400, 29, 67, 219, 'IMD', 'two-sided'),
    (1148, 'BYTE', 'Byte Coin', 'eth', 216, .00345, 3.1, 9700, 58, 51, 184, 'IMD', 'two-sided'),
    (1141, 'ECHO', 'Echo', 'base', 240, .00105, 0, 1800, 19, 19, .18, 'ETH', 'two-sided'),
    (1134, 'ROOT', 'Root', 'rh', 264, .00062, -1.8, 2100, 12, 18, 72, 'IMD', 'two-sided'),
    (1128, 'MINT', 'Mint', 'eth', 312, .00009, 4.2, 750, 8, 6, 0, 'IMD', 'one-token'),
    (1118, 'GLINT', 'Glint', 'base', 336, .00273, 18.2, 7300, 74, 31, 530, 'IMD', 'one-quote'),
    (1104, 'DRIFT', 'Drift', 'rh', 384, .00048, -12.8, 3200, 14, 48, 116, 'IMD', 'one-quote'),
    (1089, 'LOOP', 'Loop', 'eth', 408, .00014, None, 0, 0, 0, 0, 'ETH', 'one-token'),
    (1067, 'PULSE', 'Pulse', 'base', 432, .00431, 2.7, 4200, 37, 23, .62, 'ETH', 'two-sided'),
    (1044, 'LENS', 'Lens', 'rh', 456, None, None, None, None, None, None, 'IMD', 'unknown'),
    (1021, 'DUST', 'Dust', 'eth', 480, None, None, 0, 0, 0, 0, 'IMD', 'withdrawn'),
    (987, 'SPARK', 'Spark', 'base', 504, .00025, -4.1, 940, 6, 11, 0, 'IMD', 'one-token'),
    (961, 'WAVE', 'Wave', 'rh', 528, .00167, 5.6, 3850, 33, 21, 167, 'IMD', 'two-sided'),
    (943, 'DORM', 'Dormant', 'eth', 552, None, None, None, None, None, None, 'ETH', 'unknown'),
)


def _token(row: tuple) -> dict:
    (launch, symbol, name, chain, age, price, change, volume,
     buys, sells, paired, asset, state) = row
    history = None
    if price is not None and change is not None:
        start = price / (1 + change / 100)
        # Explicit synthetic samples: preserve endpoints, vary the intermediate path.
        history = [round(start + (price-start)*i/23 +
                         (0 if i in (0, 23) else ((i % 4)-1.5)*price*.015), 9)
                   for i in range(24)]
    mcap = price * 100_000_000 if price is not None else None
    return {
        'id': f'{chain}:{launch}', 'launch_id': launch, 'symbol': symbol,
        'name': name, 'chain': chain, 'launched_at': MOCK_NOW-age*3600,
        'price_usd': price, 'change_24h': change, 'mcap_usd': mcap,
        'volume_24h': volume, 'buys_24h': buys, 'sells_24h': sells,
        'paired_amount': paired, 'paired_symbol': asset, 'lp_state': state,
        'sparkline': history, 'verdict': 'swarm', 'status': 'live',
        'fdv_usd': mcap, 'fee_pct': 1.25 if asset == 'IMD' else .3,
    }


def demo_snapshot() -> dict:
    """A fresh JSON-compatible snapshot, with a fixed clock and no side effects."""
    activities = (
        ('eth:1175', 0, 'BUY', 42.6, 'IMD'),
        ('eth:1170', 1, 'SELL', .12, 'ETH'),
        ('eth:1178', 4, 'LAUNCH', None, ''),
        ('base:1168', 5, 'LP ADD', 18, 'IMD'),
        ('eth:737', 6, 'BUY', 66.8, 'IMD'),
        ('eth:902', 8, 'LP READ', None, ''),
        ('base:1177', 28, 'LAUNCH', None, ''),
        ('rh:1176', 120, 'LAUNCH', None, ''),
    )
    return {
        'tokens': [_token(row) for row in _TOKENS],
        'activity': [
            {'id': f'demo:{index}', 'token_id': token, 'ts': MOCK_NOW-minutes*60,
             'kind': kind, 'amount': amount, 'asset': asset}
            for index, (token, minutes, kind, amount, asset) in enumerate(activities)
        ],
        'as_of': MOCK_NOW, 'is_mock': True,
    }


class DemoSwarmTokensManager:
    """Dashboard lifecycle adapter; fetching only reconstructs the mock snapshot."""

    _error_count = 0

    async def fetch_and_compute(self) -> dict:
        return demo_snapshot()

    async def close(self) -> None:
        pass
