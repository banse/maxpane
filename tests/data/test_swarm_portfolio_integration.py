"""The new portfolio borrows SURF lifetime, while keeping its session wallet."""
import sys
from types import SimpleNamespace

from tests.data.test_surf_manager_launches import manager, LaunchSwarm


async def test_scan_portfolio_is_retained_without_replacing_its_wallet(tmp_path, monkeypatch):
    closed = []

    class Portfolio:
        def __init__(self, wallet=None, *, clock):
            self.wallet, self.clock = wallet, clock

        async def close(self):
            closed.append(self.wallet)

    monkeypatch.setitem(sys.modules, 'maxpane_dashboard.data.swarm_portfolio_manager',
                        SimpleNamespace(SwarmPortfolioManager=Portfolio))
    surf = manager(tmp_path, LaunchSwarm())
    portfolio = surf.swarm_portfolio_manager('initial')
    portfolio.wallet = 'session selection'
    assert surf.swarm_portfolio_manager('initial') is portfolio
    assert portfolio.wallet == 'session selection'
    assert getattr(surf, '_portfolio_manager', None) is None
    await surf.close()
    await surf.close()
    assert closed == ['session selection']
