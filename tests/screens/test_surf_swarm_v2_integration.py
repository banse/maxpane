"""Offline v2 mounting, popup routing, and SITES/status separation."""
from copy import deepcopy

import pytest
from textual.widgets import DataTable

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
