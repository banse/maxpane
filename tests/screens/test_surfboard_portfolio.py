"""Boardroom portfolio navigation does not steal text input or replace WIP."""
import sys
from types import SimpleNamespace

from textual.screen import Screen

from tests.screens.test_surfboard_layout import HubHarness
from tests.surfboard_fixtures import hub_payload


async def test_portfolio_shortcut_opens_retained_view_and_preserves_terminal_input(monkeypatch):
    class Portfolio(Screen):
        def __init__(self, manager, *, view_state):
            super().__init__()
            self.manager, self.view_state = manager, view_state

    monkeypatch.setitem(sys.modules, 'maxpane_dashboard.screens.swarm_portfolio',
                        SimpleNamespace(SwarmPortfolioScreen=Portfolio))
    app = HubHarness(hub_payload())
    retained = object()
    calls = []

    def portfolio_manager(wallet):
        calls.append(wallet)
        return retained

    app.hub._data_manager.swarm_portfolio_manager = portfolio_manager
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        painted = '\n'.join(strip.text for strip in app.screen._compositor.render_strips())
        assert 'o portfolio' in painted
        await pilot.press('o')
        assert isinstance(app.screen, Portfolio)
        assert app.screen.manager is retained
        app.screen.view_state['query'] = 'keep selection'
        app.pop_screen()
        await pilot.pause()
        await pilot.press('o')
        assert app.screen.view_state['query'] == 'keep selection'
        app.pop_screen()
        await pilot.pause()
        app.hub.action_command_input()
        await pilot.press('o')
        assert app.screen is app.hub
        assert len(calls) == 2
