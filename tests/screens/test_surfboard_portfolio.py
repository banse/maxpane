"""Boardroom portfolio navigation does not steal text input or replace WIP."""
import sys
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


async def test_portfolio_opens_through_reader_and_reuses_its_wallet_manager():
    from maxpane_dashboard.data.reader import ReaderHandle, ReaderRuntime
    from maxpane_dashboard.screens.swarm_portfolio import SwarmPortfolioScreen
    from tests.data.test_reader import eventually
    from tests.screens.test_swarm_portfolio import Manager
    from tests.widgets.test_swarm_portfolio import WALLET, painted

    app = HubHarness(hub_payload())
    parent = app.hub._data_manager
    calls = []

    def portfolio_manager(wallet):
        calls.append((wallet, threading.get_ident()))
        return Manager()

    parent.swarm_portfolio_manager = portfolio_manager
    parent.close = AsyncMock()
    runtime = ReaderRuntime()
    app.hub._data_manager = runtime.register('surfboard', lambda: parent)
    app.hub._wallet = WALLET
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            assert calls == []
            await pilot.press('o')
            assert isinstance(app.screen, SwarmPortfolioScreen)
            child = app.screen._data_manager
            assert isinstance(child, ReaderHandle) and child.wallet == WALLET
            await eventually(lambda: child.get_snapshot() is not None)
            await app.screen._do_refresh()
            await pilot.pause()
            assert 'PORTFOLIO' in painted(app) and 'ALPHA' in painted(app)
            app.pop_screen()
            await pilot.pause()
            await pilot.press('o')
            assert isinstance(app.screen, SwarmPortfolioScreen)
            assert app.screen._data_manager is child
            assert calls == [(WALLET, runtime.thread.ident)]
            assert runtime.thread.ident != threading.get_ident()
    finally:
        await runtime.close()
