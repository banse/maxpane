"""SHIPPED RECENTLY mixes proven shipments without turning them into a table."""
from copy import deepcopy

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
from tests.surf_launch_fixtures import launch_row
from tests.widgets.surf_compositing import composite_lines


def site(name='weir', timestamp=1900, **overrides):
    row = dict(label=name, ens_name=f'{name}.sites.imd.fun', status='named',
               named_ts=timestamp, superseded_by=None)
    row.update(overrides)
    return row


def token(name='EHS', timestamp=1800, **overrides):
    row = launch_row(ticker=name, updated_ts=timestamp, created_ts=timestamp - 120 if timestamp is not None else None)
    row.update(overrides)
    return row


async def test_mixed_shipments_plain_aligned_and_newest_first():
    contract = token(kind='evm_contracts', timestamp=1700)
    contract['artifacts'] = [dict(contract['artifacts'][0], name='PvPPad', role='contract')]
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
    async with Probe().run_test(size=(46, 12)) as pilot:
        panel = pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=[contract, token()], swarm_site_rows=[site()],
                         swarm_launches_as_of_hhmm='17:18', as_of=2000)
        await pilot.pause()
        assert not panel.query(DataTable)
        lines = [s.text.rstrip() for s in pilot.app.screen._compositor.render_strips()]
        assert 'SHIPPED RECENTLY · as of 17:18' in lines[0]
        assert lines[1] == ''
        assert 'weir' in lines[2] and '$EHS' in lines[3] and 'PvPPad' in lines[4]
        assert lines[2].index('site') == lines[3].index('token') == lines[4].index('contract')
        assert '1m' in lines[2] and '~3m' in lines[3] and '~5m' in lines[4]


@pytest.mark.parametrize('launches,sites,expected', [(None, None, ''),
    ([], [], 'no shipped items yet'), ([], None, 'partial'), (None, [site()], 'partial')])
async def test_sources_distinguish_unavailable_empty_and_partial(launches, sites, expected):
    lines = await composite_lines(SurfSwarmLatestLaunches, (46, 12),
        swarm_launch_rows=launches, swarm_site_rows=sites, as_of=2000)
    assert expected in '\n'.join(lines)


def test_signature_includes_the_second_source():
    from maxpane_dashboard.data.surf_models import SWARM_LATEST_LAUNCHES_SIGNATURE
    assert SWARM_LATEST_LAUNCHES_SIGNATURE == (
        'swarm_launch_rows', 'swarm_site_rows', 'swarm_launches_as_of_hhmm', 'as_of')


def test_shipments_filter_dedupe_and_cap_after_mixing():
    from maxpane_dashboard.widgets.surf.swarm_latest import shipped_items
    valid = token()
    contract = token(kind='evm_contracts', timestamp=1850)
    a = dict(contract['artifacts'][0], name='Alpha', role='contract', address='0x'+'1'*40)
    b = dict(a, name='Beta', address='0x'+'2'*40)
    contract['artifacts'] = [a, b, a, dict(a, name='Bad', address='invalid')]
    launches = [valid, deepcopy(valid), token('TESTNET', production=False),
                token('PARKED', status='parked'), token('EMPTY', artifacts=[]), contract]
    sites = [site('newest', 1950), site('weir', 1900), site('old', 1600),
             site('replaced', 2000, superseded_by='new'), site('failed', 2000, status='failed')]
    items = shipped_items(launches, sites)
    assert [item['name'] for item in items] == ['newest', 'weir', 'Alpha', 'Beta', '$EHS', 'old']
    assert [item['kind'] for item in items] == ['site', 'site', 'contract', 'contract', 'token', 'site']


def test_site_unknown_time_stays_last_and_known_testnet_join_is_excluded():
    from maxpane_dashboard.widgets.surf.swarm_latest import shipped_items
    launches = [token(production=False, chain_id=11155111)]
    sites = [site('unknown', None), site('testnet', 2200, launch_number=737), site('known', 100)]
    items = shipped_items(launches, sites)
    assert [item['name'] for item in items] == ['known', 'unknown']


def test_missing_launch_time_and_names_have_honest_fallbacks():
    from maxpane_dashboard.widgets.surf.swarm_latest import shipped_items
    row = token(None, timestamp=None, token_name=None, created_ts=None)
    item = shipped_items([row], [])[0]
    assert item['name'] == '#737'
    assert item['timestamp'] is None
    row.update(token_name='Identity', created_ts=10)
    item = shipped_items([row], [])[0]
    assert item['name'] == 'Identity' and item['timestamp'] == 10
    assert 'request time' in item['timing']


@pytest.mark.parametrize('opening', ['click', 'enter'])
async def test_launch_selection_and_x_snapshot_are_immutable(opening):
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    from maxpane_dashboard.widgets.surf.swarm_latest import ShippedRow
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
        def on_surf_swarm_latest_launches_selected(self, event):
            self.push_screen(LaunchDetailScreen(event.row))
    row = token('[red]X')
    async with Probe().run_test(size=(46, 30)) as pilot:
        panel = pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=[row], swarm_site_rows=[site()], as_of=2000)
        await pilot.pause()
        assert panel.top_row()['ticker'] == '[red]X'
        panel.top_row()['ticker'] = 'cannot change stored row'
        row['ticker'] = 'changed'
        widget = panel.query_one('#shipped-row-1', ShippedRow)
        if opening == 'click':
            await pilot.click(widget, offset=(2, 0))
        else:
            widget.focus()
            await pilot.press('enter')
        await pilot.pause()
        assert isinstance(pilot.app.screen, LaunchDetailScreen)
        assert pilot.app.screen.row['ticker'] == '[red]X'
        assert pilot.app.screen.row['as_of'] == 2000


@pytest.mark.parametrize('width', [20, 28, 46])
async def test_literal_hostile_names_and_cjk_stay_on_one_row(width):
    from rich.cells import cell_len
    row = token('[red]漢字\x1b\n\u202eLONGTICKER')
    lines = await composite_lines(SurfSwarmLatestLaunches, (width, 12),
        swarm_launch_rows=[row], swarm_site_rows=[site('hello.sites.imd.fun')], as_of=2000)
    assert 'hello' in lines[2] and '.sites.imd.fun' not in '\n'.join(lines)
    assert '$[red]' in lines[3]
    assert '\x1b' not in '\n'.join(lines) and '\u202e' not in '\n'.join(lines)
    assert not lines[4].strip()
    assert all(cell_len(line) <= width for line in lines)


async def test_hover_discloses_proxy_times_and_missing_source():
    from maxpane_dashboard.widgets.surf.swarm_latest import ShippedRow
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
    async with Probe().run_test(size=(46, 12)) as pilot:
        panel = pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=[token()], swarm_site_rows=None, as_of=2000)
        await pilot.pause()
        hover = panel.query_one(ShippedRow).tooltip.plain
        assert 'API update time' in hover and 'approximate' in hover
        assert 'partial' in hover and 'partial' in panel.tooltip.plain and 'unavailable' not in hover


async def test_actual_styles_links_and_padding_are_composited():
    from rich.color import Color
    from maxpane_dashboard.app import MaxPaneApp
    from maxpane_dashboard.themes import THEMES
    from tests.widgets.address_probe import icon_targets, link_targets
    class Probe(App):
        CSS_PATH = MaxPaneApp.CSS_PATH
        def __init__(self):
            super().__init__()
            self.register_theme(THEMES['matrix'])
            self.theme = 'matrix'
        def compose(self): yield SurfSwarmLatestLaunches()
    async with Probe().run_test(size=(46, 12)) as pilot:
        panel = pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=[token()], swarm_site_rows=[site()], as_of=2000)
        await pilot.pause()
        lines = [s.text for s in pilot.app.screen._compositor.render_strips()]
        for y, name in ((2, 'weir'), (3, '$EHS')):
            assert lines[y][0] == lines[y][-1] == ' '
            name_style = pilot.app.screen.get_style_at(lines[y].index(name), y)
            assert name_style.color == Color.parse(pilot.app.get_css_variables()['foreground'])
            assert not name_style.dim
            age_style = pilot.app.screen.get_style_at(lines[y].index('m'), y)
            age_rgb = age_style.color.get_truecolor()
            assert age_rgb.red == age_rgb.green == age_rgb.blue
            assert age_style.color != name_style.color
        assert any(link[3:5] == ('site', 'weir') for link in link_targets(pilot.app))
        assert icon_targets(pilot.app)[0][2] == next(a['address'] for a in token()['artifacts'] if a['role'] == 'token')


@pytest.mark.parametrize('change', [dict(production=False), dict(status='parked'),
    dict(artifacts=[]), dict(artifacts=[dict(role='token', address='bad')]),
    dict(artifacts=[dict(role='token', address='0x'+'0'*40)]),
    dict(artifacts=[dict(role='helper', address='0x'+'1'*40)])])
def test_only_production_live_deployed_token_is_a_shipment(change):
    from maxpane_dashboard.widgets.surf.swarm_latest import shipped_items
    assert shipped_items([token(**change)], []) == []


@pytest.mark.parametrize("size", [(149, 45), (141, 38)])
async def test_seven_newest_items_fit_the_board_top_row(size):
    from tests.screens.test_surf_screen import _frozen_payload, _surf_app, _region_text
    from tests.screens.test_surf_swarm_screen import _open
    from maxpane_dashboard.widgets.surf.swarm_latest import ShippedRow
    payload = _frozen_payload(swarm_launch_rows=[token(timestamp=1899)],
        swarm_site_rows=[site(f's{i}', 1900+i) for i in range(8)], as_of=2000)
    async with _surf_app(payload).run_test(size=size) as pilot:
        screen = await _open(pilot)
        panel = screen.query_one(SurfSwarmLatestLaunches)
        rows = list(panel.query(ShippedRow))
        assert len(rows) == 7
        assert [item['name'] for item in panel._payload['rows']] == [f's{i}' for i in range(7, 0, -1)]
        painted = _region_text(pilot.app, panel)
        assert all(f's{i}' in painted for i in range(7, 0, -1))
        assert 's0' not in painted and '$EHS' not in painted
        assert panel.parent.region.contains_region(rows[-1].region)


async def test_refresh_removes_previous_items_and_x_tracks_request_order():
    from maxpane_dashboard.widgets.surf.swarm_latest import ShippedRow
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
    async with Probe().run_test(size=(46, 12)) as pilot:
        panel = pilot.app.query_one(SurfSwarmLatestLaunches)
        older = token('older', 1900, created_ts=1000)
        newer = token('newer', 1800, created_ts=1500, launch_number=999)
        newer['artifacts'] = [dict(a, address='0x'+'3'*40) for a in newer['artifacts']]
        panel.update_data(swarm_launch_rows=[older, newer], swarm_site_rows=[], as_of=2000)
        await pilot.pause()
        assert '$older' in str(panel.query_one('#shipped-row-0').render())
        assert panel.top_row()['launch_number'] == 999
        panel.update_data(swarm_launch_rows=[], swarm_site_rows=[], as_of=2100)
        await pilot.pause()
        lines = [s.text for s in pilot.app.screen._compositor.render_strips()]
        assert not any('$older' in line or '$newer' in line for line in lines)
        assert all(not row.display for row in panel.query(ShippedRow))
        assert panel.top_row() is None


def test_published_site_on_abandoned_mainnet_is_not_a_testnet_site():
    from maxpane_dashboard.widgets.surf.swarm_latest import shipped_items
    launches = [token(production=False, status='abandoned', chain_id=1)]
    assert [item['name'] for item in shipped_items(launches, [site(launch_number=737)])] == ['weir']
