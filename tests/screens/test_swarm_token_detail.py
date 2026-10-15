"""Selected token dashboard composition and round-trip navigation, offline."""
from copy import deepcopy
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.data.swarm_tokens_demo import demo_snapshot
from maxpane_dashboard.screens.swarm_token_detail import (
    SwarmTokenScreen, SWARM_TOKEN_FULL_LAYOUT_COLUMNS, SWARM_TOKEN_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.themes import THEMES
from tests.widgets.address_probe import CopyRecorder

TOKEN_ADDRESS = '0x' + 'ab' * 20
HOOK_ADDRESS = '0x' + 'cd' * 20
JOB_ID = '663e917d-9776-4cbb-bc6d-d0905e337064'


def detail_payload():
    raw = demo_snapshot()
    token = raw['tokens'][0]
    token.update(id='1:' + TOKEN_ADDRESS, token_address=TOKEN_ADDRESS, chain_id=1,
                 token_amount=2400000, withdrawn_pct=0,
                 market_source='DexScreener', market_state='ok', history_state='ok',
                 liquidity_state='ok', market_pool='0x' + 'ef' * 20,
                 market_read_at=raw['as_of'], history_read_at=raw['as_of'],
                 liquidity_read_at=raw['as_of'])
    launch = dict(id='6d766a87-1614-4bdb-aa24-5960fef59882', number=1175,
                  chain_id=1, status='live', verdict='swarm', objective='Build a community token.',
                  recorded_ts=token['launched_at'], repo_url='https://github.com/identity-md-launches/demo',
                  site_label='demo', site_ens_name='demo.sites.imd.fun')
    contributors = [dict(seat=str(192+i), role='build' if i == 0 else 'review',
                         job_id=JOB_ID, state='accepted', stage='contracts') for i in range(12)]
    artifacts = [dict(kind=kind, name=name, address=address, chain_id=1,
                      site_label=None, site_ens_name=None) for kind, name, address in (
                      ('token', 'Swarm Coin', TOKEN_ADDRESS), ('contract', 'DemoHook', HOOK_ADDRESS))]
    artifacts.append(dict(kind='site', name='demo', address=None, chain_id=1,
                          site_label='demo', site_ens_name='demo.sites.imd.fun'))
    return dict(token=token, launch=launch, contributors=contributors, artifacts=artifacts,
                sources={name: dict(state='ok', read_ts=raw['as_of'])
                         for name in ('launch', 'contributors', 'artifacts')},
                as_of=raw['as_of'], is_mock=False)


class DetailProvider:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else detail_payload()
        self.closed = False

    async def fetch_and_compute(self):
        return deepcopy(self.payload)

    async def close(self):
        self.closed = True


class DetailApp(CopyRecorder, App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'

    def __init__(self, provider=None):
        super().__init__()
        self.provider = provider or DetailProvider()

    def on_mount(self):
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = 'matrix'
        self.push_screen(SwarmTokenScreen(self.provider))


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


async def test_approved_dashboard_fits_and_keeps_contributors_scrollable():
    from maxpane_dashboard.widgets.swarm_token_detail import (
        DetailHero, LaunchSummary, ContributorTable, MarketPanel, PositionPanel, ArtifactTable,
    )
    app = DetailApp()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(app)
        for label in ('PRICE', 'MARKET CAP', 'VOLUME', 'CONTRIBUTORS', 'POSITION',
                      'LAUNCH', 'CONTRIBUTING AGENTS', 'MARKET', 'LAUNCH POSITION', 'ARTIFACTS'):
            assert label in text
        screen = app.screen
        hero, launch, contributors, market, position, artifacts = (
            screen.query_one(kind) for kind in (DetailHero, LaunchSummary, ContributorTable,
                                               MarketPanel, PositionPanel, ArtifactTable))
        assert hero.region.height == 9
        assert launch.region.y == market.region.y
        assert contributors.region.y >= launch.region.bottom
        assert position.region.y >= market.region.bottom
        assert launch.region.right < market.region.x
        assert artifacts.region.y >= contributors.region.bottom
        assert artifacts.region.right > position.region.x
        assert contributors.query_one(DataTable).row_count == 12
        assert artifacts.region.bottom <= screen.query_one('#token-viewport').region.bottom
        assert '‹ widen' not in text and '‹ taller' not in text


async def test_token_click_opens_full_dashboard_and_escape_preserves_selection():
    from maxpane_dashboard.demos.swarm_tokens import SwarmTokensDemo
    from maxpane_dashboard.widgets.swarm_tokens import TokensTable
    app = SwarmTokensDemo()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        overview = app.screen
        table = overview.query_one(TokensTable).query_one(DataTable)
        table.move_cursor(row=2)
        selected = overview.query_one(TokensTable).selected_token()['id']
        await pilot.click(table, offset=(12, 3))
        await pilot.pause()
        assert isinstance(app.screen, SwarmTokenScreen)
        assert 'MOCK DATA' in painted(app)
        await pilot.press('escape')
        await pilot.pause()
        assert app.screen is overview
        assert overview.query_one(TokensTable).selected_token()['id'] == selected


async def test_screen_unmount_closes_only_detail_provider():
    app = DetailApp()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.press('escape')
        await pilot.pause()
        assert app.provider.closed


@pytest.mark.guard
def test_detail_css_agrees_with_application_stylesheet():
    css = (Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss').read_text()
    block = css.split('/* SWARM TOKEN detail screen */', 1)[1].split('/* SWARM TOKENS mock screen */', 1)[0]
    assert ' '.join(block.split()) == ' '.join(SwarmTokenScreen.DEFAULT_CSS.split())


@pytest.mark.sweep
@pytest.mark.parametrize('axis,delta', [('width', -1), ('width', 0), ('width', 1),
                                      ('height', -1), ('height', 0), ('height', 1)])
@pytest.mark.parametrize('degraded', [False, True])
async def test_detail_layout_boundary(axis, delta, degraded):
    from maxpane_dashboard.widgets.swarm_token_detail import DetailHero, ArtifactTable
    payload = detail_payload()
    if degraded:
        payload['launch']['objective'] = 'A long objective ' * 100
        payload['contributors'] = payload['artifacts'] = None
        payload['sources'] = {name: dict(state='unavailable', read_ts=None) for name in payload['sources']}
    width = SWARM_TOKEN_FULL_LAYOUT_COLUMNS + (delta if axis == 'width' else 0)
    height = SWARM_TOKEN_FULL_LAYOUT_ROWS + (delta if axis == 'height' else 0)
    app = DetailApp(DetailProvider(payload))
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        viewport = app.screen.query_one('#token-viewport')
        clipped = viewport.max_scroll_x > 0 or viewport.max_scroll_y > 0
        assert clipped == (delta < 0)
        text = painted(app)
        assert ('‹ widen' in text) == (viewport.max_scroll_x > 0)
        assert ('‹ taller' in text) == (viewport.max_scroll_y > 0)
        if not clipped:
            assert app.screen.query_one(DetailHero).region.right <= viewport.scrollable_content_region.right
            assert app.screen.query_one(ArtifactTable).region.bottom <= viewport.region.bottom
            for label in ('CONTRIBUTING AGENTS', 'MARKET', 'LAUNCH POSITION', 'ARTIFACTS', 'repository'):
                assert label in text
