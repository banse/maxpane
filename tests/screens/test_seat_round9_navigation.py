"""Round 9 navigation, render and key ownership regressions (WP4)."""
import copy

import pytest
from textual.widgets import DataTable
from textual.color import Color

from maxpane_dashboard.screens.seat import SeatScreen, title_line
from maxpane_dashboard.widgets.seat import SeatHero, SeatLog, SeatLedgerTable
from tests.address_sweep.builders import _seat_app, _seat_payload

NAMES = ('SEAT', 'LIVE', 'CONFIG & SKILLS', 'RECORDS', 'NODES', 'CONTROL')
IDS = ('seat', 'live', 'config', 'records', 'nodes', 'control')


def strips(screen):
    return [''.join(seg.text for seg in strip) for strip in screen._compositor.render_strips()]


def color(screen, widget, *, label=False):
    x = widget.region.x + (widget.region.width // 2 if label else 0)
    y = widget.region.y + (1 if label else 0)
    return screen.get_style_at(x, y).color


async def test_six_keys_and_clicks_select_exactly_one_success_border():
    app = _seat_app()
    seen = []
    app._screen._data_manager.select_dashboard = seen.append
    async with app.run_test(size=(170, 50)) as pilot:
        screen = app.screen
        await pilot.pause()
        assert screen.selected_dashboard == 'LIVE'
        cards = list(screen.query(SeatHero).first().children)
        success = Color.parse(app.get_css_variables()["success"]).rich_color
        assert color(screen, cards[1]) == success
        for click in (False, True):
            for index, name in enumerate(NAMES):
                if click:
                    await pilot.click(f'#seat-hero-{IDS[index]}')
                else:
                    await pilot.press(str(index + 1))
                await pilot.pause()
                assert screen.selected_dashboard == name
                assert [color(screen, c) == success for c in cards] == [i == index for i in range(6)]
                assert sum(screen.query_one(f'#seat-body-{i}').display for i in IDS) == 1
                assert app.focused is not None and app.focused.is_on_screen
                assert seen[-1] == name
        await pilot.press('escape')
        await pilot.pause()
        assert screen.selected_dashboard == 'LIVE'


async def test_selection_border_and_health_label_are_independent():
    flat = _seat_payload()
    app = _seat_app(flat)
    async with app.run_test(size=(170, 50)) as pilot:
        screen = app.screen
        await pilot.pause()
        cards = list(screen.query_one(SeatHero).children)
        borders = [color(screen, c) for c in cards]
        flat['seat_hero_state'] = 'red'
        flat['seat_hero_reasons'] = ['tail died']
        await screen._do_refresh()
        await pilot.pause()
        assert [color(screen, c) for c in cards] == borders
        labels = [color(screen, c, label=True) for c in cards]
        assert 'LIVE ⚠' in '\n'.join(strips(screen))
        await pilot.press('3')
        await pilot.pause()
        assert [color(screen, c, label=True) for c in cards] == labels
        assert '⚠ tail died' in strips(screen)[0]


async def test_hidden_log_emitted_line_is_visible_once_after_live():
    flat = _seat_payload()
    app = _seat_app(flat)
    async with app.run_test(size=(170, 50)) as pilot:
        screen = app.screen
        await pilot.pause()
        await pilot.press('1')
        flat['seat_log_lines'] = [dict(seq=99, kind='phase', text='UNIQUE HIDDEN LOG LINE', ts='2026-10-03T17:00:00Z')]
        flat['seat_log_seq'] = 99
        await screen._do_refresh()
        flat['seat_log_lines'] = []
        await screen._do_refresh()
        await pilot.press('2')
        await pilot.pause()
        assert '\n'.join(strips(screen)).count('UNIQUE HIDDEN LOG LINE') == 1
        assert screen.query_one(SeatLog).last_seq == 99


async def test_live_refresh_and_control_keys_never_open_plan_elsewhere(monkeypatch):
    app = _seat_app()
    plans = []
    # The control dispatch is the seam the shared WP5 flow will own.
    monkeypatch.setattr(SeatScreen, '_request_control', lambda self, verb: plans.append(verb), raising=False)
    async with app.run_test(size=(170, 50)) as pilot:
        screen = app.screen
        await pilot.pause()
        # Count key-driven refreshes only, independent of the five-second cadence.
        screen._refresh_timer.pause()
        refreshes = []
        monkeypatch.setattr(screen, 'start_refresh', lambda: refreshes.append(True))
        for key in ('2', '1', '3', '4', '5'):
            await pilot.press(key, 'r', 'd', 's', 'S', 'b', 'o', 'D', 'x')
        await pilot.pause()
        assert len(refreshes) == 5
        assert plans == []
        await pilot.press('6', 'r', 'd', 's', 'S', 'b', 'o', 'D', 'x')
        await pilot.pause()
        assert plans == ['restart', 'drain-restart', 'stop', 'start', 'enable-boot', 'kill-orphans', 'doctor', 'cancel-drain']


async def test_ledger_refresh_insert_preserves_row_and_scroll():
    flat = _seat_payload()
    base = flat['seat_tasks_rows'][0]
    flat['seat_tasks_rows'] = [dict(base, key=f'row-{i}', nodeId8=f'{i:08d}') for i in range(20)]
    app = _seat_app(flat)
    async with app.run_test(size=(134, 40)) as pilot:
        screen = app.screen
        await pilot.pause()
        await pilot.press('1')
        await pilot.pause()
        panel = screen.query_one(SeatLedgerTable)
        table = panel.query_one(DataTable)
        table.move_cursor(row=12)
        await pilot.pause()
        table.scroll_to(y=8, animate=False, force=True)
        await pilot.pause()
        selected = panel.selected_row()['key']
        top = table.scroll_y
        flat['seat_tasks_rows'].insert(0, dict(base, key='new-row', nodeId8='99999999'))
        await screen._do_refresh()
        await pilot.pause()
        assert panel.selected_row()['key'] == selected
        assert table.scroll_y == top + 1
        assert '00000012' in '\n'.join(strips(screen))
        await pilot.resize_terminal(100, 40)
        await pilot.pause()
        assert panel.selected_row()['key'] == selected
        assert table.scroll_y == top + 1
        await pilot.press('2', '1')
        await pilot.pause()
        assert panel.selected_row()['key'] == selected
        assert table.scroll_y == top + 1
        y = table.region.y + table.header_height + table.cursor_row - int(table.scroll_y)
        assert screen.get_style_at(table.region.x + 2, y).bgcolor == table.get_component_rich_style('datatable--cursor').bgcolor


def test_alert_precedes_taller_and_offline():
    line = title_line(dict(seat_hero_state='red', seat_hero_reasons=['tail died', 'unit inactive'], seat_offline=True), row_hint=True)
    assert line.index('⚠ tail died') < line.index('‹ taller') < line.index('offline')
    assert 'unit inactive' not in line


@pytest.mark.parametrize('index', range(6))
async def test_hidden_updated_then_shown_matches_visible_updated_strips(index):
    payload = _seat_payload()
    payload['seat_skills_rows'] = [dict(id=f'skill-{i}', on=True, needs='network') for i in range(50)]
    payload['seat_nodes_all_rows'] = [dict(nodeKey='oracle', role='question', attempts=12)]
    payload['seat_records_rows'] = [dict(key='record-1', jobId='b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70', nodeKey='oracle', workStatus='pending')]
    async def render(hidden):
        app = _seat_app(copy.deepcopy(payload))
        async with app.run_test(size=(134, 50)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.select_dashboard(NAMES[(index + 1) % 6] if hidden else NAMES[index])
            await pilot.pause()
            await screen._do_refresh()
            screen.select_dashboard(NAMES[index])
            await pilot.pause()
            await pilot.pause()
            return strips(screen)
    assert await render(True) == await render(False)


async def test_every_body_registers_all_scrolling_containers_and_missing_body_fails(monkeypatch):
    from textual.containers import Vertical, VerticalScroll
    from maxpane_dashboard.screens import seat as module
    async with _seat_app().run_test(size=(134, 50)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        def check():
            for name, body_id in module.BODY_IDS.items():
                registered = module.SCROLL_CONTAINERS[name]
                assert registered
                root = screen.query_one(f'#{body_id}')
                scrolling = [w.id for w in (root, *root.query(Vertical)) if w.styles.overflow_y == 'auto']
                assert set(scrolling) <= set(registered)
        check()
        monkeypatch.setitem(module.SCROLL_CONTAINERS, 'NODES', ())
        with pytest.raises(AssertionError):
            check()


async def test_status_hints_change_immediately_and_control_never_promises_refresh():
    async with _seat_app().run_test(size=(134, 50)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await pilot.press('6')
        await pilot.pause()
        line = strips(screen)[-1]
        assert 'r restart' in line and 'r refresh' not in line
        assert 'PEPEPANE' in line and 'poll' in line
        await pilot.press('2')
        await pilot.pause()
        assert 'h beats' in strips(screen)[-1]


async def test_prompt_input_owns_keys_and_reclaims_focus(monkeypatch):
    from textual.widgets import Input
    submitted = []
    monkeypatch.setattr(SeatScreen, 'on_input_submitted', lambda self, event: submitted.append(event.value), raising=False)
    async with _seat_app().run_test(size=(134, 50)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen.select_dashboard('CONTROL')
        screen.prompt_open = True
        screen.query_one('#seat-confirm-strip').display = True
        field = screen.query_one('#seat-confirm-input', Input)
        field.focus()
        await pilot.pause()
        await pilot.press('1', 'r', 'd', 'c', 'tab', 'space')
        await pilot.pause()
        assert field.value == '1rdc '
        assert screen.selected_dashboard == 'CONTROL'
        screen.query_one('#seat-audit-log').focus()
        await pilot.press('2', 'enter')
        await pilot.pause()
        assert screen.selected_dashboard == 'CONTROL'
        assert submitted == ['1rdc 2']
        assert pilot.app.focused is field
        await pilot.press('escape')
        await pilot.pause()
        assert not screen.prompt_open and screen.selected_dashboard == 'CONTROL'


async def test_initial_record_window_hint_matches_visible_all_filter():
    app = _seat_app()
    seen = []
    app._screen._data_manager.set_record_window = lambda limit, *, open_only: seen.append((limit, open_only))
    async with app.run_test(size=(134, 50)) as pilot:
        await pilot.pause()
        assert seen[0] == (40, False)
        await pilot.press('4', 'f', 'm')
        await pilot.pause()
        assert seen[-2:] == [(40, True), (60, True)]


async def test_clicking_hero_drops_prompt_despite_input_focus_retention():
    from textual.widgets import Input
    async with _seat_app().run_test(size=(134, 50)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen.prompt_open = True
        screen.query_one('#seat-confirm-strip').display = True
        screen.query_one('#seat-confirm-input', Input).focus()
        await pilot.pause()
        await pilot.click('#seat-hero-config')
        await pilot.pause()
        assert screen.selected_dashboard == 'CONFIG & SKILLS'
        assert not screen.prompt_open
        assert pilot.app.focused is screen.query_one('#seat-config-table')


async def test_real_seat_app_quit_and_theme_keys_belong_to_prompt_input():
    from textual.widgets import Input
    from maxpane_dashboard.seat_cli import SeatApp
    from tests.address_sweep.builders import _PayloadManager
    app = SeatApp(_PayloadManager(_seat_payload()))
    async with app.run_test(size=(134,50)) as pilot:
        await pilot.pause()
        screen = app.screen
        theme = app.theme
        screen.prompt_open = True
        screen.query_one('#seat-confirm-strip').display = True
        field = screen.query_one('#seat-confirm-input', Input)
        field.focus()
        await pilot.pause()
        await pilot.press('q','t','h','n','f','m','w','S','D','x')
        await pilot.pause()
        assert field.value == 'qthnfmwSDx'
        assert app.screen is screen and app.theme == theme


@pytest.mark.parametrize('null_ledger_key', [True, False])
async def test_next_job_cycles_running_jobs_without_ledger_keys(null_ledger_key):
    from maxpane_dashboard.widgets.seat import SeatJob
    flat = _seat_payload()
    jobs = [dict(jobId='job-a', nodeId8='running-a', nodeKey='question', role='oracle'),
            dict(jobId='job-b', nodeId8='running-b', nodeKey='question', role='oracle')]
    if null_ledger_key:
        for job in jobs:
            job['key'] = None
    flat['seat_current_jobs'] = jobs
    flat['seat_jobs'] = list(jobs)
    async with _seat_app(flat).run_test(size=(132,40)) as pilot:
        await pilot.pause()
        panel = pilot.app.screen.query_one(SeatJob)
        assert panel.selected_row()['jobId'] == 'job-a'
        assert 'running-a' in '\n'.join(strips(pilot.app.screen))
        await pilot.press('n')
        await pilot.pause()
        assert panel.selected_row()['jobId'] == 'job-b'
        assert 'running-b' in '\n'.join(strips(pilot.app.screen))
        assert 'running-a' not in '\n'.join(strips(pilot.app.screen))
        flat['seat_jobs'].reverse()
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        assert panel.selected_row()['jobId'] == 'job-b'
        await pilot.press('n')
        await pilot.pause()
        assert panel.selected_row()['jobId'] == 'job-a'
        assert 'running-a' in '\n'.join(strips(pilot.app.screen))
