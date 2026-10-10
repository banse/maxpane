"""SURF owns Portfolio and its borrowed market lifetime exactly once."""
from tests.data.test_surf_manager_launches import manager, LaunchSwarm


async def test_retained_portfolio_keeps_session_wallet_and_closes_before_shared_market(tmp_path, monkeypatch):
    import httpx
    import maxpane_dashboard.data.portfolio_manager as module
    async def refuse(*args, **kwargs):
        raise AssertionError('network used by ownership test')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)
    closed = []
    class Market:
        async def close(self):
            closed.append('market')
    class Portfolio:
        def __init__(self, market, wallet, *, clock):
            self.market, self.wallet, self.clock = market, wallet, clock
        async def close(self):
            closed.append('portfolio')
    monkeypatch.setattr(module, 'PortfolioManager', Portfolio)
    surf = manager(tmp_path, LaunchSwarm())
    market = surf._swarm_tokens_manager = Market()
    first = surf.portfolio_manager('startup')
    first.wallet = 'explicit session choice'
    assert surf.portfolio_manager('startup') is first
    assert first.wallet == 'explicit session choice' and first.market is market
    await surf.close()
    await surf.close()
    assert closed == ['portfolio', 'market']
