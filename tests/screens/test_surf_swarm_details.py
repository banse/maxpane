"""SWARM v3 cached popup interactions and alarm rendering."""
import pytest
from textual.widgets import DataTable

from maxpane_dashboard.screens.surf import SurfScreen
from maxpane_dashboard.widgets.surf import SurfSwarmWorkflows
from tests.screens.test_surf_screen import _frozen_payload, _region_text, _screen_text, _surf_app
from tests.screens.test_surf_swarm_screen import _open
from tests.widgets.test_surf_swarm_workflows import _row, JOB, JOB2
from tests.widgets.address_probe import icon_targets, link_targets

ADDRESS = '0x' + 'c0' * 20


@pytest.mark.parametrize('opening', ['enter', 'click'])
async def test_workflow_popup_is_a_literal_snapshot_with_job_links(opening):
    from maxpane_dashboard.screens.swarm_detail import WorkflowDetailScreen
    row = _row(objective='First sentence. Whole objective ends here.',
               failure=f'[FAIL: contract {ADDRESS}]', waiting_for_hosting=True)
    payload = _frozen_payload(swarm_workflow_rows=[row])
    async with _surf_app(payload).run_test(size=(200, 48)) as pilot:
        screen = await _open(pilot)
        table = screen.query_one(SurfSwarmWorkflows).query_one(DataTable)
        table.focus()
        calls = screen._data_manager.calls
        if opening == 'enter':
            await pilot.press('enter')
        else:
            await pilot.click(table, offset=(2, 1))
        await pilot.pause()
        popup = pilot.app.screen
        assert isinstance(popup, WorkflowDetailScreen)
        row['objective'] = 'CHANGED AFTER OPENING'
        text = _screen_text(pilot.app)
        for word in ('STATUS', 'CREATED / UPDATED', 'CONTRACTS JOB', 'FRONTEND JOB',
                     'WAITING FOR HOSTING', 'OBJECTIVE', 'FAILURE', 'yes',
                     'Whole objective ends here.', f'[FAIL: contract {ADDRESS} ⧉]'):
            assert word in text
        assert 'CHANGED AFTER OPENING' not in text
        assert ADDRESS in {address for _, _, address in icon_targets(pilot.app)}
        targets = link_targets(pilot.app)
        assert {f'https://explorer.imd.fun/jobs/{JOB}', f'https://explorer.imd.fun/jobs/{JOB2}'} <= {v[5] for v in targets}
        assert not any(ADDRESS in str(v[5]) for v in targets)
        assert screen._data_manager.calls == calls
        await pilot.press('escape')
        await pilot.pause()
        assert pilot.app.screen is screen


async def test_throughput_popup_uses_snapshot_and_space_closes():
    from maxpane_dashboard.screens.swarm_detail import ThroughputDetailScreen
    tp = {'states': [{'state': 'executing', 'count': 7}],
          'cancel_reasons': [{'reason': '[FAIL: unavailable node]', 'count': 3}]}
    async with _surf_app(_frozen_payload(swarm_throughput=tp)).run_test(size=(200, 48)) as pilot:
        screen = await _open(pilot)
        before = screen._data_manager.calls
        await pilot.press('x')
        await pilot.pause()
        assert isinstance(pilot.app.screen, ThroughputDetailScreen)
        tp['states'][0]['state'] = 'CHANGED'
        text = _screen_text(pilot.app)
        assert 'executing' in text and '[FAIL: unavailable node]' in text
        assert 'CHANGED' not in text
        assert screen._data_manager.calls == before
        await pilot.press('space')
        await pilot.pause()
        assert pilot.app.screen is screen
        assert 'x more' in _screen_text(pilot.app)
        assert 'x less' not in _screen_text(pilot.app)


@pytest.mark.parametrize('value', [None, {}, {'states': None, 'cancel_reasons': None}])
async def test_throughput_missing_blocks_are_yellow_unavailable(value):
    async with _surf_app(_frozen_payload(swarm_throughput=value)).run_test(size=(200, 48)) as pilot:
        await _open(pilot)
        await pilot.press('x')
        await pilot.pause()
        matches = [seg for strip in pilot.app.screen._compositor.render_strips()
                   for seg in strip if 'unavailable' in seg.text]
        assert len(matches) == 2
        assert all(seg.style.color.get_truecolor(pilot.app.ansi_theme) == pilot.app.ansi_theme.ansi_colors[3]
                   for seg in matches)


@pytest.mark.parametrize('fields,alarm', [
    ({'swarm_breaker': {'tripped': True}}, '⚠ breaker open'),
    ({'swarm_services_up': {'verifier': False, 'publisher': None}}, '⚠ verifier down'),
    ({'swarm_services_up': {'verifier': False, 'publisher': False}}, '⚠ 2 services down'),
    ({'swarm_health_status': '[red]bad\x1b\nhealth state'}, '⚠ health bad health …'),
])
async def test_swarm_alarms_only_appear_in_swarm(fields, alarm):
    payload = _frozen_payload(swarm_breaker=None, swarm_services_up=None, swarm_health_status='ok')
    payload.update(fields)
    async with _surf_app(payload).run_test(size=(220, 48)) as pilot:
        screen = await _open(pilot)
        assert alarm in _region_text(pilot.app, screen.query_one('#title-bar'))
        await pilot.press('s')
        await pilot.pause()
        assert alarm not in _region_text(pilot.app, screen.query_one('#title-bar'))


async def test_swarm_layout_parks_exported_widgets_and_puts_workflows_below_launches():
    from maxpane_dashboard.data.surf_models import SWARM_PARKED_WIDGET_SIGNATURES
    from maxpane_dashboard.widgets import surf as widgets
    async with _surf_app(_frozen_payload()).run_test(size=(200, 48)) as pilot:
        screen = await _open(pilot)
        for name in SWARM_PARKED_WIDGET_SIGNATURES:
            assert not list(screen.query(getattr(widgets, name)))
        launches = screen.query_one(widgets.SurfSwarmLaunches).region
        throughput = screen.query_one(widgets.SurfSwarmThroughput).region
        workflows = screen.query_one(widgets.SurfSwarmWorkflows).region
        sites = screen.query_one(widgets.SurfSwarmSites).region
        assert launches.y == throughput.y and launches.right <= throughput.x
        assert launches.bottom <= workflows.y and workflows.bottom <= sites.y
        assert workflows.width > launches.width
        assert SurfScreen.KEY_HINTS == '[dim]x more · 4 pl4 · s swm · a agt · b brd[/]'


async def test_workflow_popup_wraps_and_scrolls_to_the_whole_failure():
    from textual.containers import VerticalScroll
    objective = ' '.join(f'word{n:03d}' for n in range(300)) + ' OBJECTIVE_END'
    failure = '[FAIL: ' + 'long failure ' * 80 + f'{ADDRESS}] FAILURE_END'
    async with _surf_app(_frozen_payload(swarm_workflow_rows=[_row(objective=objective, failure=failure)])).run_test(size=(96, 30)) as pilot:
        screen = await _open(pilot)
        screen.query_one(SurfSwarmWorkflows).query_one(DataTable).focus()
        await pilot.press('enter')
        await pilot.pause()
        popup = pilot.app.screen
        scroll = popup.query_one(VerticalScroll)
        assert scroll.max_scroll_y > 0
        seen = _screen_text(pilot.app)
        while scroll.scroll_y < scroll.max_scroll_y:
            scroll.scroll_relative(y=10, animate=False)
            await pilot.pause()
            seen += '\n' + _screen_text(pilot.app)
        assert 'OBJECTIVE_END' in seen and 'FAILURE_END' in seen
        assert '[FAIL:' in seen and ADDRESS in seen
        assert ADDRESS in {address for _, _, address in icon_targets(pilot.app)}


@pytest.mark.parametrize('health', [None, 17, {}, ''])
async def test_swarm_unread_health_is_explicit_without_reporting_a_service_down(health):
    payload = _frozen_payload(swarm_health_status=health, swarm_breaker=None,
                              swarm_services_up={'verifier': None, 'publisher': True})
    async with _surf_app(payload).run_test(size=(200, 48)) as pilot:
        screen = await _open(pilot)
        title = _region_text(pilot.app, screen.query_one('#title-bar'))
        assert 'health unavailable' in title
        assert 'down' not in title and 'breaker open' not in title
        await pilot.press('a')
        await pilot.pause()
        assert 'health unavailable' not in _region_text(pilot.app, screen.query_one('#title-bar'))


@pytest.mark.parametrize('down', [{'verifier': False, 'publisher': False, 'deployer': False}, {'publisher': False}])
async def test_compact_swarm_title_keeps_every_alarm_at_the_existing_pin(down):
    from maxpane_dashboard.screens.surf import SURF_SWARM_FULL_LAYOUT_COLUMNS, _title_line
    from maxpane_dashboard.data.surf_manager import SOURCES
    from tests.screens.test_surf_screen import _worst_case_title_payload
    from rich.text import Text
    payload = _worst_case_title_payload()
    payload.update(swarm_breaker={'tripped': True}, swarm_services_up=down,
                   swarm_health_status='abcdefghijkl')
    async with _surf_app(payload).run_test(size=(SURF_SWARM_FULL_LAYOUT_COLUMNS, 30)) as pilot:
        screen = await _open(pilot)
        title = _region_text(pilot.app, screen.query_one('#title-bar')).strip()
        assert 'IMD $0.71' in title and 'par -2.7%' in title
        assert 'as of ' in title and '‹ taller' in title and 'LP changed' in title
        assert f'⚠ {len(SOURCES)} src' in title
        assert 'breaker open' in title
        assert ('3 svc down' if len(down) > 1 else 'pub down') in title
        assert title.endswith('health abcdefghijkl')
        rendered = Text.from_markup(_title_line(payload, row_hint=True, swarm=True,
                                               columns=screen.query_one('#title-bar').content_size.width)).plain
        assert title == rendered
