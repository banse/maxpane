"""Attempt identity and unknown verdicts through the real compositor."""
import pytest
from maxpane_dashboard.data.seat_models import fold_status_document
from maxpane_dashboard.widgets.seat import SeatJob
from tests.address_sweep.builders import _seat_app, _seat_payload
from tests.screens.test_seat_round9_navigation import strips

JOB = 'job-a'


def jobs_payload(current, jobs):
    shaped = fold_status_document(dict(currentJobs=current, jobs=jobs))
    return {name: shaped[name] for name in ('seat_current_jobs', 'seat_jobs')}


async def test_running_plane_never_rejoins_old_finished_node_on_refresh():
    live = dict(jobId=JOB, nodeKey='tests', startedUtc='2026-10-03T10:00:01Z', phase='working', objective='live question')
    old = dict(key='old', jobId=JOB, nodeId8='aaaa1111', nodeKey='tests', acceptedUtc='2026-10-03T09:00:03Z',
               submittedUtc='2026-10-03T09:01:00Z', outcome='failed', failureReason='old failure', objective='old question', usage={'turns': 99})
    flat = _seat_payload()
    flat.update(jobs_payload([live], [old]))
    async with _seat_app(flat).run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        panel = pilot.app.screen.query_one(SeatJob)
        assert 'live question' in '\n'.join(strips(pilot.app.screen))
        assert 'old failure' not in '\n'.join(strips(pilot.app.screen))
        selected = panel._selected_key
        newer = dict(live, startedUtc='2026-10-03T10:00:40Z', objective='newer question')
        panel.update_data(**jobs_payload([newer, live], [old]))
        await pilot.pause()
        assert panel._selected_key == selected
        assert 'live question' in '\n'.join(strips(pilot.app.screen))
        assert 'newer question' not in '\n'.join(strips(pilot.app.screen))


async def test_widget_ambiguous_cached_attempts_keep_plane_question():
    live = dict(jobId=JOB, nodeKey='tests', startedUtc='2026-10-03T10:00:20Z', objective='plane question')
    cached = [dict(key=node, jobId=JOB, nodeId8=node, nodeKey='tests', acceptedUtc='2026-10-03T10:00:22Z', objective='cached ' + node)
              for node in ('aaaa1111', 'bbbb2222')]
    flat = _seat_payload()
    other = dict(jobId=JOB, nodeKey='contracts', startedUtc='2026-10-03T10:00:01Z', objective='other plane')
    flat.update(jobs_payload([live, other], cached))
    async with _seat_app(flat).run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        text = '\n'.join(strips(pilot.app.screen))
        assert 'plane question' in text and 'cached aaaa1111' not in text


@pytest.mark.parametrize('working', [False, True])
async def test_submitted_unknown_verdict_is_dim_question_mark_only_when_finished(working):
    row = dict(key='unknown', jobId=JOB, nodeKey='tests', submittedUtc=None if working else '2026-10-03T10:00:30Z',
               outcome=None, objective='question', reply='reply', structuralCheck={'evaluation': 'structural'})
    flat = _seat_payload()
    flat.update(jobs_payload([row] if working else [], [row]))
    async with _seat_app(flat).run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        region = screen.query_one('#seat-job-content').region
        rows = [line[region.x:region.right] if region.y <= y < region.bottom else ''
                for y, line in enumerate(strips(screen))]
        verdict = [(y, line) for y, line in enumerate(rows) if line.strip() == '?']
        assert bool(verdict) is (not working)
        check_y, check_line = next((y, line) for y, line in enumerate(rows) if 'check: structural' in line)
        if not working:
            y, line = verdict[0]
            assert y + 1 == check_y
            assert screen.get_style_at(region.x + line.index('?'), y).color == screen.get_style_at(region.x + check_line.index('check:'), check_y).color
        await pilot.resize_terminal(131, 30)
        scroll = screen.query_one('#seat-job-scroll')
        scroll.scroll_to(y=scroll.max_scroll_y, animate=False, immediate=True)
        await pilot.pause()
        region = screen.query_one('#seat-job-content').region
        painted = [line[region.x:region.right].strip() for line in strips(screen)]
        assert ('?' in painted) is (not working)
        assert any('check: structural' in line for line in painted)


@pytest.mark.parametrize('state,warning', [('activating', False), ('reloading', False), ('inactive', True), ('failed', True), ('deactivating', True)])
async def test_seat_label_uses_alive_states(state, warning):
    flat = _seat_payload()
    flat.update(seat_unit_active_state=state, seat_unit_boot_enabled=True)
    async with _seat_app(flat).run_test(size=(131, 40)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        hero = screen.query_one('#seat-hero-seat')
        label_y = hero.region.y + 1
        line = strips(screen)[label_y][hero.region.x:hero.region.right]
        assert ('SEAT ⚠' in line) is warning
        color = screen.get_style_at(hero.region.x + line.index('SEAT'), label_y).color.get_truecolor(pilot.app.ansi_theme)
        assert (color == pilot.app.ansi_theme.ansi_colors[1]) is warning


async def test_selection_keeps_attempt_when_cache_arrives_at_window_upper_edge():
    current = [dict(jobId=JOB, nodeKey=node, startedUtc=f'2026-10-03T10:00:{second:02d}Z', objective=node + ' plane')
               for node, second in [('contracts', 1), ('tests', 20)]]
    flat = _seat_payload()
    flat.update(jobs_payload(current, []))
    async with _seat_app(flat).run_test(size=(180, 40)) as pilot:
        await pilot.pause()
        panel = pilot.app.screen.query_one(SeatJob)
        assert panel.selected_row()['nodeKey'] == 'tests'
        cached = [dict(key=node, jobId=JOB, nodeKey=node, nodeId8=str(index) * 8,
                       acceptedUtc=f'2026-10-03T10:00:{second + 8:02d}Z', objective=node + ' cached')
                  for index, (node, second) in enumerate([('contracts', 1), ('tests', 20)], 1)]
        newer = dict(jobId=JOB, nodeKey='new-node', startedUtc='2026-10-03T10:00:40Z', objective='new plane')
        panel.update_data(**jobs_payload([newer, *reversed(current)], cached))
        await pilot.pause()
        assert panel.selected_row()['key'] == 'tests'
        assert 'tests cached' in '\n'.join(strips(pilot.app.screen))


@pytest.mark.parametrize('state', ['activating', 'reloading'])
async def test_starting_seat_keeps_boot_disabled_amber_rule(state):
    flat = _seat_payload()
    flat.update(seat_unit_active_state=state, seat_unit_boot_enabled=False)
    async with _seat_app(flat).run_test(size=(131, 40)) as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        hero = screen.query_one('#seat-hero-seat')
        y = hero.region.y + 1
        line = strips(screen)[y][hero.region.x:hero.region.right]
        assert 'SEAT ⚠' in line
        color = screen.get_style_at(hero.region.x + line.index('SEAT'), y).color.get_truecolor(pilot.app.ansi_theme)
        assert color == pilot.app.ansi_theme.ansi_colors[3]
