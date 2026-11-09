from copy import deepcopy
import json
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable, Input

from maxpane_dashboard.screens.swarm_portfolio import (
    SwarmPortfolioScreen, SWARM_PORTFOLIO_FULL_LAYOUT_COLUMNS, SWARM_PORTFOLIO_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.widgets.portfolio.overview import SwarmPortfolioOverview
from maxpane_dashboard.widgets.portfolio.inspector import SwarmPortfolioInspector
from tests.widgets.test_swarm_portfolio import portfolio_snapshot, painted
from tests.screens._sweeps import boundary_set


class Manager:
    def __init__(self):
        self.snapshot = portfolio_snapshot()
        self.refresh_requests = 0

    def get_snapshot(self):
        return deepcopy(self.snapshot)

    async def fetch_and_compute(self):
        return self.get_snapshot()

    def request_refresh(self):
        self.refresh_requests += 1

    def set_wallet(self, wallet):
        self.snapshot = dict(wallet=wallet, state='loading', as_of=None, assets=None)
        return True


class PortfolioApp(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'

    def __init__(self):
        super().__init__()
        from maxpane_dashboard.themes import THEMES
        self.register_theme(THEMES['matrix'])
        self.theme = 'matrix'
        self.manager = Manager()
        self.view_state = {}

    def on_mount(self):
        self.push_screen(SwarmPortfolioScreen(self.manager, view_state=self.view_state))


async def test_holdings_enter_opens_native_popup_and_escape_preserves_selection():
    async with PortfolioApp().run_test(size=(149, 45)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        table = screen.query_one('#pf-holdings-table', DataTable)
        table.focus()
        await pilot.press('enter')
        assert isinstance(pilot.app.screen, SwarmPortfolioInspector)
        await pilot.press('escape')
        assert pilot.app.screen is screen
        assert table.cursor_row == 0
        assert screen.query_one(SwarmPortfolioOverview).selected_id.endswith('34' * 20)


async def test_search_is_local_and_wallet_change_clears_previous_positions():
    async with PortfolioApp().run_test(size=(149, 45)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.press('slash')
        search = screen.query_one('#pf-search', Input)
        assert search.has_focus
        search.value = 'does-not-match'
        await pilot.pause()
        assert screen.query_one('#pf-holdings-table', DataTable).row_count == 1
        assert 'ALPHA' not in painted(pilot.app)
        assert pilot.app.manager.refresh_requests == 0
        screen._wallet_entered('0x' + '78' * 20)
        await pilot.pause()
        assert 'ALPHA' not in painted(pilot.app)
        assert screen.query_one('#hero-pf-total').data.digits == ''


async def test_second_holding_survives_refresh_and_modal_return():
    app = PortfolioApp()
    other = deepcopy(app.manager.snapshot['assets'][0])
    other.update(id='1:0x' + '90' * 20, token_address='0x' + '90' * 20,
                 symbol='BETA', total_usd=100, wallet_usd=100)
    app.manager.snapshot['assets'].append(other)
    async with app.run_test(size=(149,45)) as pilot:
        screen = app.screen
        await screen._do_refresh()
        table = screen.query_one('#pf-holdings-table', DataTable)
        table.focus()
        await pilot.press('down')
        assert screen.query_one(SwarmPortfolioOverview).selected_id == other['id']
        await screen._do_refresh()
        await pilot.pause()
        assert table.cursor_row == 1
        assert screen.query_one(SwarmPortfolioOverview).selected_id == other['id']
        await pilot.press('enter')
        assert app.screen.row['id'] == other['id']
        await pilot.press('escape')
        assert table.cursor_row == 1


def layout_snapshot(kind):
    if kind == 'live_capture':
        from maxpane_dashboard.data.swarm_portfolio_client import normalize_result
        raw = json.loads((Path(__file__).parents[1] / 'fixtures/portfolio_scan/captured.json').read_text())
        return normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    snapshot = portfolio_snapshot()
    if kind in ('loading','empty'):
        for key in ('assets','positions','rewards','nfts','standings','utilities','seats'):
            snapshot[key] = None if kind == 'loading' else []
        snapshot.update(state='loading' if kind == 'loading' else 'ok', as_of=None if kind == 'loading' else snapshot['as_of'])
    if kind == 'extreme':
        snapshot['assets'][0].update(symbol='非常に長い[/x] token', name='large value',
                                     wallet_quantity=1e30, wallet_usd=1e30, total_usd=1e30)
        snapshot['assets'] = [dict(snapshot['assets'][0], id=f'{i}:token') for i in range(20)]
        snapshot['rewards'] *= 20
        snapshot['standings'] = [dict(chain_id=1, contract_address='0x'+'ab'*20,
            name='Long eligibility contract', fields=[dict(name='threshold',value='x'*200)])] * 20
    return snapshot


@pytest.mark.guard
def test_portfolio_screen_css_agrees_with_the_production_theme():
    css = PortfolioApp.CSS_PATH.read_text()
    block = css.split('/* SWARM Portfolio */',1)[1].split('/* END SWARM Portfolio */',1)[0]
    assert ' '.join(block.split()) == ' '.join(SwarmPortfolioScreen.DEFAULT_CSS.split())


@pytest.mark.sweep
@pytest.mark.parametrize('kind', ['representative','live_capture','extreme','loading','empty'])
async def test_measured_portfolio_width_is_the_first_whole_viewport(kind):
    app = PortfolioApp()
    app.manager.snapshot = layout_snapshot(kind)
    async with app.run_test(size=(160,50)) as pilot:
        for width in boundary_set(SWARM_PORTFOLIO_FULL_LAYOUT_COLUMNS,120,160):
            await pilot.resize_terminal(width,50)
            await pilot.pause()
            body = app.screen.query_one(SwarmPortfolioOverview)
            whole = body.max_scroll_x == 0
            assert whole == (width >= SWARM_PORTFOLIO_FULL_LAYOUT_COLUMNS)
            title = app.screen._compositor.render_strips()[0].text
            assert ('‹ widen' in title) == (not whole)
            heroes = list(body.query_one('#pf-heroes').children)
            assert all(card.region.height == 9 for card in heroes)
            assert all(table.virtual_size.width <= table.scrollable_content_region.width for table in body.query(DataTable))
            if whole:
                assert heroes[-1].region.right <= body.scrollable_content_region.right
                line = app.screen._compositor.render_strips()[heroes[0].region.y].text
                assert line.count('╮') == 6
                for label in ('SOURCE','JOINED','TOKEN IDS','SEATS & ELIGIBILITY'):
                    assert label in painted(app)


@pytest.mark.sweep
@pytest.mark.parametrize('kind', ['representative','live_capture','extreme','loading','empty'])
async def test_measured_portfolio_height_is_the_first_whole_viewport(kind):
    app = PortfolioApp()
    app.manager.snapshot = layout_snapshot(kind)
    async with app.run_test(size=(160,50)) as pilot:
        for height in boundary_set(SWARM_PORTFOLIO_FULL_LAYOUT_ROWS,24,50):
            await pilot.resize_terminal(160,height)
            await pilot.pause()
            body = app.screen.query_one(SwarmPortfolioOverview)
            whole = body.max_scroll_y == 0
            assert whole == (height >= SWARM_PORTFOLIO_FULL_LAYOUT_ROWS)
            title = app.screen._compositor.render_strips()[0].text
            assert ('‹ taller' in title) == (not whole)
            assert body.query_one('#pf-panels').region.height == 25
            assert body.query_one('#pf-nfts-table').region.height == 4
            if whole:
                assert body.query_one('#pf-panels').region.bottom <= body.scrollable_content_region.bottom
                assert 'NFT INVENTORY' in painted(app) and 'SEATS & ELIGIBILITY' in painted(app)


async def test_both_boundaries_and_smaller_terminal_keep_all_corners_reachable():
    app = PortfolioApp()
    width, height = SWARM_PORTFOLIO_FULL_LAYOUT_COLUMNS, SWARM_PORTFOLIO_FULL_LAYOUT_ROWS
    async with app.run_test(size=(width,height)) as pilot:
        await pilot.pause()
        body = app.screen.query_one(SwarmPortfolioOverview)
        assert body.max_scroll_x == body.max_scroll_y == 0
        await pilot.resize_terminal(80,24)
        await pilot.pause()
        assert '‹ widen' in painted(app) and '‹ taller' in painted(app)
        assert 'TOTAL VALUE' in painted(app)
        body.scroll_to(x=body.max_scroll_x,y=0,animate=False)
        await pilot.pause()
        assert 'SEATS' in painted(app)
        body.scroll_to(x=0,y=body.max_scroll_y,animate=False)
        await pilot.pause()
        assert 'NFT INVENTORY' in painted(app)
        body.scroll_to(x=body.max_scroll_x,y=body.max_scroll_y,animate=False)
        await pilot.pause()
        assert 'SEATS & ELIGIBILITY' in painted(app)
        await pilot.resize_terminal(width,height)
        await pilot.pause()
        assert body.max_scroll_x == body.max_scroll_y == 0


@pytest.mark.parametrize('panel,collection', [('rewards','rewards'),('stakes','positions'),('utilities','utilities'),('nfts','nfts')])
async def test_each_panel_keeps_its_selected_record_across_popup_return_and_reordering(panel,collection):
    app = PortfolioApp()
    row = dict(asset_id=app.manager.snapshot['assets'][0]['id'],chain_id=1,
               contract_address='0x'+'ab'*20,token_address='0x'+'34'*20,name='Position',symbol='ALPHA',
               quantity=3,value_usd=25,status='ready',kind='Stake',role='takes',joined=True,count=2,token_ids=['7','9'])
    if collection == 'nfts':
        row.pop('asset_id')
    app.manager.snapshot[collection] = [dict(row,id='first'),dict(row,id='second')]
    async with app.run_test(size=(149,45)) as pilot:
        screen = app.screen
        await screen._do_refresh()
        table = screen.query_one('#pf-'+panel+'-table',DataTable)
        table.focus()
        await pilot.press('down','enter','escape')
        await screen._do_refresh()
        await pilot.pause()
        assert table.has_focus and table.cursor_row == 1
        app.manager.snapshot[collection].reverse()
        await screen._do_refresh()
        await pilot.pause()
        assert table.cursor_row == 0
