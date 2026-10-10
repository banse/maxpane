"""Offline portfolio workflows and native composited output."""
import httpx
import pytest
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Input, Select

from maxpane_dashboard.demos.portfolio import PortfolioDemo
from maxpane_dashboard.screens.portfolio import PortfolioScreen
from maxpane_dashboard.screens.wallet_input import WalletInputScreen
from maxpane_dashboard.widgets.portfolio import PortfolioTable


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError('portfolio mock attempted network access')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)


async def test_option_one_shows_native_panels_and_claim_only_tokens():
    app = PortfolioDemo()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(app)
        for label in ('HELD VALUE', 'CLAIMABLE', 'IMD AGENTS', 'P/L',
                      'MARKET ACTIVITY', 'MOVERS / 24H', 'PORTFOLIO', 'MOCK DATA',
                      'TIDE', 'KITE', 'FOAM', 'MESH', 'PAIRED LP', 'PRICE 24H'):
            assert label in text
        assert 'LAUNCH LIQUIDITY' not in text
        assert '+$200' in text and '+6.1% · unrealized' in text
        rows = app.screen.snapshot['tokens']
        foam = next(row for row in rows if row['symbol'] == 'FOAM')
        assert foam['held_quantity'] == 0 and foam['claimable_quantity'] > 0
        assert app.screen.query_one(DataTable).row_count == len(rows)
        assert any(char in text for char in '▂▃▄▅▆▇█')
        assert '30s poll' not in text


async def test_no_wallet_prompt_persists_and_repaints_selected_address(monkeypatch, tmp_path):
    import maxpane_dashboard.config as config
    monkeypatch.setattr(config, '_CONFIG_DIR', tmp_path)
    monkeypatch.setattr(config, '_CONFIG_FILE', tmp_path / 'config.toml')
    monkeypatch.delenv('MAXPANE_WALLET', raising=False)
    wallet = '0x' + 'ab' * 20
    app = PortfolioDemo(wallet=None)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert 'Set a wallet' in painted(app)
        assert app.screen.snapshot['tokens'] == []
        await pilot.press('w')
        assert isinstance(app.screen, WalletInputScreen)
        app.screen.query_one(Input).value = wallet
        await pilot.press('enter')
        await pilot.pause()
        assert isinstance(app.screen, PortfolioScreen)
        assert app.screen.snapshot['wallet'] == wallet
        assert config.get_wallet() == wallet
        assert '⧉' in painted(app) and 'MOCK DATA' in painted(app)
        await pilot.press('w', 'escape')
        assert app.screen.snapshot['wallet'] == wallet


async def test_filter_population_drives_every_panel_and_cancel_preserves_draft_boundary():
    app = PortfolioDemo()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        screen = app.screen
        initial = len(screen.snapshot['tokens'])
        await pilot.press('f')
        screen.query_one('#filter-chain', Select).value = 'base'
        assert len(screen.snapshot['tokens']) == initial
        await pilot.press('escape')
        assert screen.chain == 'all'
        await pilot.press('f')
        screen.query_one('#filter-assets', Select).value = 'claimable'
        await pilot.click('#filter-apply')
        await pilot.pause()
        rows = screen.snapshot['tokens']
        assert rows and all(row['claimable_quantity'] > 0 for row in rows)
        ids = {row['id'] for row in rows}
        for key in ('claimable', 'gainers', 'losers'):
            assert all(row['id'] in ids for row in screen.snapshot[key])
        assert all(row['token_id'] in ids for row in screen.snapshot['activity'])
        await pilot.press('/')
        screen.query_one('#filter-query', Input).value = 'absent token'
        await pilot.click('#filter-apply')
        await pilot.pause()
        assert 'No matching tokens' in painted(app)
        assert screen.snapshot['metrics']['held_value'] == 0


async def test_selection_refresh_and_cached_detail_include_position_and_claim():
    app = PortfolioDemo()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        screen = app.screen
        panel = screen.query_one(PortfolioTable)
        table = panel.query_one(DataTable)
        index = next(i for i, row in enumerate(screen.snapshot['tokens']) if row['symbol'] == 'TIDE')
        table.move_cursor(row=index)
        table.focus()
        await pilot.pause()
        selected = panel.selected_token()['id']
        await pilot.press('o', 'r')
        await pilot.pause()
        assert panel.selected_token()['id'] == selected
        await pilot.press('enter')
        await pilot.pause()
        for label in ('YOUR POSITION', 'CLAIM STATUS', 'MARKET', 'LAUNCH POSITION', 'MOCK DATA'):
            assert label in painted(app)
        await pilot.press('escape')
        assert app.screen is screen


async def test_small_terminal_keeps_fields_reachable_and_editor_fits():
    app = PortfolioDemo()
    async with app.run_test(size=(100, 28)) as pilot:
        await pilot.pause()
        assert '‹ widen' in painted(app) and '‹ taller' in painted(app)
        viewport = app.screen.query_one('#st-viewport', VerticalScroll)
        viewport.scroll_to(x=viewport.max_scroll_x, y=viewport.max_scroll_y, animate=False)
        await pilot.pause()
        assert 'PRICE 24H' in painted(app)
        await pilot.press('/')
        await pilot.pause()
        assert app.screen.query_one('#filter-query', Input).has_focus
        await pilot.press('w', 'f', 'c', 'o', 'r', 'q')
        assert app.screen.query_one('#filter-query', Input).value == 'wfcorq'
        assert app.screen.assets == 'all' and app.screen.chain == 'all'


async def test_hub_card_opens_mock_and_returns_with_wallet_choice(monkeypatch):
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.widgets.surfboard import SurfboardRack
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    monkeypatch.setattr('maxpane_dashboard.config.get_wallet', lambda: '')
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        rack = hub.query_one(SurfboardRack)
        rack.query_one('#surfboard-card-portfolio').action_activate()
        await pilot.pause()
        assert isinstance(app.screen, PortfolioScreen)
        assert app.screen._data_manager.is_mock
        assert 'Set a wallet' in painted(app)
        await pilot.press('escape')
        assert app.screen is hub and isinstance(app.screen, SurfboardScreen)


@pytest.mark.guard
def test_portfolio_css_matches_its_application_block():
    from pathlib import Path
    css = Path('maxpane_dashboard/themes/minimal.tcss').read_text()
    block = css.split('/* PORTFOLIO mock screen */', 1)[1]
    assert ' '.join(block.split()) == ' '.join(PortfolioScreen.DEFAULT_CSS.split())


async def test_wallet_change_discards_late_snapshot_and_refreshes_new_identity():
    import asyncio
    from copy import deepcopy
    from maxpane_dashboard.data.portfolio_demo import DemoPortfolioManager
    class DelayedManager(DemoPortfolioManager):
        def __init__(self):
            super().__init__('sample')
            self.entered, self.release, self.done = asyncio.Event(), asyncio.Event(), asyncio.Event()
            self.hold = False

        async def fetch_and_compute(self):
            raw = deepcopy(await super().fetch_and_compute())
            if self.hold:
                self.hold = False
                self.entered.set()
                await self.release.wait()
            else:
                self.done.set()
            return raw

    app = PortfolioDemo()
    manager = app.manager = DelayedManager()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        screen = app.screen
        published = []
        original_title = screen._update_title
        def observe(data):
            published.append(data['wallet'])
            original_title(data)
        screen._update_title = observe
        manager.hold = True
        screen.action_refresh()
        await asyncio.wait_for(manager.entered.wait(), 2)
        manager.done.clear()
        wallet = '0x' + 'cd' * 20
        screen._wallet_entered(wallet)
        assert screen.query_one(PortfolioTable).selected_token() is None
        manager.release.set()
        await asyncio.wait_for(manager.done.wait(), 2)
        await pilot.pause()
        assert screen.snapshot['wallet'] == wallet
        assert published and set(published) == {wallet}


@pytest.mark.sweep
@pytest.mark.parametrize('axis,delta', [('width', -1), ('width', 0), ('width', 1),
                                     ('height', -1), ('height', 0), ('height', 1)])
async def test_measured_portfolio_boundary_preserves_columns_and_advertises_scroll(axis, delta):
    from maxpane_dashboard.screens.portfolio import PORTFOLIO_FULL_LAYOUT_COLUMNS, PORTFOLIO_FULL_LAYOUT_ROWS
    width = PORTFOLIO_FULL_LAYOUT_COLUMNS + (delta if axis == 'width' else 0)
    height = PORTFOLIO_FULL_LAYOUT_ROWS + (delta if axis == 'height' else 0)
    app = PortfolioDemo(wallet='0x' + 'ab' * 20)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        viewport = app.screen.query_one('#st-viewport', VerticalScroll)
        cut = viewport.show_horizontal_scrollbar or viewport.show_vertical_scrollbar
        assert cut == (delta < 0)
        text = painted(app)
        assert ('‹ widen' in text) == viewport.show_horizontal_scrollbar
        assert ('‹ taller' in text) == viewport.show_vertical_scrollbar
        assert not app.screen.query_one(DataTable).show_horizontal_scrollbar
        if not cut:
            for word in ('CLAIMABLE', 'MARKET ACTIVITY', 'MOVERS / 24H', 'PAIRED LP', 'PRICE 24H', '⧉'):
                assert word in text
            assert app.screen.query_one(PortfolioTable).region.bottom <= viewport.region.bottom


async def test_long_portfolio_keeps_all_rows_and_unpriced_stale_claims_visible():
    from copy import deepcopy
    from maxpane_dashboard.data.portfolio_demo import demo_snapshot
    raw = demo_snapshot('sample')
    foam = next(row for row in raw['tokens'] if row['symbol'] == 'FOAM')
    foam['claim_read_state'] = 'stale'
    mesh = next(row for row in raw['tokens'] if row['symbol'] == 'MESH')
    mesh['price_usd'] = None
    for index in range(40):
        row = deepcopy(raw['tokens'][0])
        row.update(id=f'eth:extra-{index}', launch_id=500 + index, symbol=f'EX{index:02}',
                   claimable_quantity=0, claim_state='none')
        raw['tokens'].append(row)
    app = PortfolioDemo()
    async def snapshot():
        return deepcopy(raw)
    app.manager.fetch_and_compute = snapshot
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert app.screen.query_one(DataTable).row_count == 44
        assert 'stale' in painted(app)
        rows = app.screen.snapshot['tokens']
        assert next(row for row in rows if row['symbol'] == 'MESH')['held_usd'] is None
        assert next(row for row in rows if row['symbol'] == 'FOAM')['claimable_usd'] is None
        assert app.screen.snapshot['metrics']['claimable_known'] < app.screen.snapshot['metrics']['claimable_total']
        await pilot.press('ctrl+end')
        await pilot.pause()
        assert app.screen.query_one(PortfolioTable).selected_token()['id'] == rows[-1]['id']
