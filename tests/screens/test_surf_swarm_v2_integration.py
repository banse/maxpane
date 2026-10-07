"""Offline v2 mounting, popup routing, and SITES/status separation."""
from copy import deepcopy
import json

import pytest
from textual.widgets import DataTable
from textual.containers import VerticalScroll

from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
from maxpane_dashboard.widgets.surf import SurfSwarmLaunches, SurfSwarmSites, SurfSwarmThroughput
from tests.screens.test_surf_screen import _frozen_payload, _screen_text, _surf_app
from tests.screens.test_surf_swarm_screen import _open
from tests.screens.test_surf_swarm_layout import _production_swarm_payload
from tests.surf_launch_fixtures import launch_row


@pytest.mark.parametrize('opening', ['x', 'enter', 'click', 'launches'])
async def test_latest_routes_snapshot_popup_without_reads(opening):
    rows = [launch_row(737, created_ts=1000), launch_row(747, created_ts=900)]
    original = deepcopy(rows)
    async with _surf_app(_frozen_payload(swarm_launch_rows=rows, as_of=2000)).run_test(size=(150, 46)) as pilot:
        screen = await _open(pilot)
        assert not list(screen.query(SurfSwarmThroughput))
        latest = screen.query_one(SurfSwarmLatestLaunches)
        table = (screen.query_one(SurfSwarmLaunches) if opening == 'launches' else latest).query_one(DataTable)
        table.focus()
        reads = screen._data_manager.calls
        if opening == 'click':
            await pilot.click(table, offset=(2, 0))
        else:
            await pilot.press('enter' if opening in ('enter', 'launches') else 'x')
        await pilot.pause()
        assert isinstance(pilot.app.screen, LaunchDetailScreen)
        assert ('#747' if opening == 'launches' else '#737') in _screen_text(pilot.app)
        assert pilot.app.screen.row['as_of'] == 2000
        assert rows == original
        assert screen._data_manager.calls == reads


@pytest.mark.parametrize('rows', [None, [], [launch_row(production=False)]])
async def test_x_without_production_launch_is_noop(rows):
    async with _surf_app(_frozen_payload(swarm_launch_rows=rows)).run_test(size=(129, 35)) as pilot:
        screen = await _open(pilot)
        await pilot.press('x')
        await pilot.pause()
        assert pilot.app.screen is screen


@pytest.mark.parametrize('width', [90, 91, 111, 112, 129, 143, 150, 155, 156, 157, 170, 171])
async def test_launches_liquidity_at_owner_widths(width):
    from tests.widgets.test_surf_swarm_liquidity import liquid_row
    payload = _production_swarm_payload()
    payload['swarm_launch_rows'] = [liquid_row()]
    async with _surf_app(payload).run_test(size=(width, 46)) as pilot:
        screen = await _open(pilot)
        launches = screen.query_one(SurfSwarmLaunches)
        shown = 'liq' in launches._keys
        assert shown == (width >= 91)
        assert '4.7K IMD' in _screen_text(pilot.app) if shown else '4.7K IMD' not in _screen_text(pilot.app)


@pytest.mark.parametrize('size', [(129, 35), (130, 36), (143, 35), (150, 46), (200, 48)])
async def test_sites_has_blank_composited_row_above_status(size):
    async with _surf_app(_production_swarm_payload()).run_test(size=size) as pilot:
        screen = await _open(pilot)
        sites = screen.query_one(SurfSwarmSites)
        lines = _screen_text(pilot.app).splitlines()
        assert sites.region.bottom <= size[1]-2
        assert lines[size[1]-2].strip() == ''
        assert 'q quit' in lines[size[1]-1]
        assert '‹ taller' not in lines[0]


@pytest.mark.parametrize('withdrawn', [False, True], ids=['locked', 'withdrawn'])
async def test_receipt_to_manager_snapshot_to_liquidity_popup(tmp_path, withdrawn):
    """Exercise the data/render seam without installing a precomputed K8 result."""
    from tests.analytics.test_surf_launch_liquidity import FIX
    from tests.data.test_surf_manager_launches import manager, LaunchSwarm, NOW
    from tests.analytics.test_surf_launch_checks import fixture
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES

    swarm = LaunchSwarm()
    swarm.rows = [fixture('launch_737')]
    manager_ = manager(tmp_path, swarm)
    requests = json.loads((FIX / 'v9/MANIFEST.json').read_text())['files']['rpc_737_pool_state']['request']
    replies = {item['id']: item['result'] for item in json.loads((FIX / 'v9/rpc_737_pool_state.json').read_text())}
    calls_seen = []
    fail = False

    async def state(calls):
        calls_seen.append(deepcopy(calls))
        # Match complete calldata and destinations to the independent capture.
        values = {(request['method'], json.dumps(request['params'], sort_keys=True)): replies[request['id']]
                  for request in requests}
        return [None if fail else values[method, json.dumps(params, sort_keys=True)] for method, params in calls]

    manager_.client.fetch_launch_pool_state = state
    try:
        await manager_._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        if withdrawn:
            replies[2] = '0x' + (int(replies[2], 16) // 2).to_bytes(32, 'big').hex()
            await manager_._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 300)
        last_good = NOW + (300 if withdrawn else 0)
        fail = True
        await manager_._pool_swarm_launches({TIER_SWARM_LAUNCHES}, last_good + 600)
        keys = manager_._swarm_launch_keys()
        row = keys['swarm_launch_rows'][0]
        assert row['liquidity']['read_ts'] == last_good
        assert row['liquidity']['paired_amount'] == pytest.approx(4726.591141 / (2 if withdrawn else 1))
        assert row['checks']['K8'] == row['liquidity']
        assert row['verdict']['state'] == 'swarm'
        assert len(calls_seen) == (3 if withdrawn else 2)
    finally:
        await manager_.close()

    async with _surf_app(_frozen_payload(**keys, as_of=last_good + 600)).run_test(size=(200, 48)) as pilot:
        screen = await _open(pilot)
        screen.query_one(SurfSwarmLaunches).query_one(DataTable).show_cursor = False
        await pilot.pause()
        strips = screen._compositor.render_strips()
        assert ('withdrawn' if withdrawn else '4.7K IMD') in _screen_text(pilot.app)
        assert '✓ swarm' in _screen_text(pilot.app)
        if withdrawn:
            segments = [segment for strip in strips for segment in strip if 'withdrawn' in segment.text]
            assert segments and all(segment.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[1] for segment in segments)
        await pilot.press('x')
        await pilot.pause()
        assert isinstance(pilot.app.screen, LaunchDetailScreen)
        scroll = pilot.app.screen.query_one(VerticalScroll)
        seen = ''
        while True:
            seen += '\n' + _screen_text(pilot.app)
            if scroll.scroll_y >= scroll.max_scroll_y:
                break
            scroll.scroll_relative(y=15, animate=False)
            await pilot.pause()
        for word in ('pool liquidity: paired amount, range, lock', '1.25%', 'in range', '10m ago',
                     'withdrawn 50%' if withdrawn else 'never withdrawn',
                     '50% of active liquidity' if withdrawn else '100% of active liquidity'):
            assert word in seen, (word, seen)


async def test_liquidity_visibility_is_monotonic_from_91_through_220():
    from tests.widgets.test_surf_swarm_liquidity import liquid_row
    payload = _production_swarm_payload()
    payload['swarm_launch_rows'] = [liquid_row()]
    async with _surf_app(payload).run_test(size=(60, 46)) as pilot:
        screen = await _open(pilot)
        launches = screen.query_one(SurfSwarmLaunches)
        first_seen = None
        for width in range(60, 221):
            await pilot.resize_terminal(width, 46)
            await pilot.pause()
            lines = _screen_text(pilot.app).splitlines()
            region = launches.region
            header = next((line for line in lines[region.y:region.bottom]
                           if 'ticker' in line and 'verdict' in line), '')
            shown = 'liq' in launches._keys
            assert ('liq' in header) == shown, (width, header, launches._keys)
            if shown and first_seen is None:
                first_seen = width
            if first_seen is not None:
                assert shown, (width, first_seen, launches._tier)
                assert '4.7K IMD' in '\n'.join(lines[region.y:region.bottom]), width
        assert first_seen == 91


@pytest.mark.parametrize('kind', ['initialize', 'modify'])
async def test_ambiguous_manager_pool_paints_dash_in_liquidity_cell(tmp_path, kind):
    from tests.analytics.test_surf_launch_liquidity import ambiguous_receipts
    from tests.data.test_surf_manager_liquidity import manager, seed, NOW
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES
    manager_ = manager(tmp_path)
    seed(manager_, pool=False)
    _, receipts = ambiguous_receipts(kind)
    async def fetch(hashes): return deepcopy(receipts)
    manager_.client.fetch_launch_receipts = fetch
    try:
        await manager_._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        keys = manager_._swarm_launch_keys()
        assert keys['swarm_launch_rows'][0]['liquidity']['state'] == 'na'
    finally:
        await manager_.close()
    async with _surf_app(_frozen_payload(**keys)).run_test(size=(150, 46)) as pilot:
        screen = await _open(pilot)
        panel = screen.query_one(SurfSwarmLaunches)
        table = panel.query_one(DataTable)
        index = panel._keys.index('liq')
        x = table.content_region.x + sum(c.get_render_width(table) for c in table.ordered_columns[:index])
        width = table.ordered_columns[index].get_render_width(table)
        y = table.content_region.y + table.header_height
        cell = screen._compositor.render_strips()[y].crop(x, x + width).text.strip()
        assert cell == '--'
