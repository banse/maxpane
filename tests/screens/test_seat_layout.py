"""Six-body foundation geometry, measured in WP4; full content certification is WP6.

All assertions inspect composited strips. Tables/logs scroll internally; no ledger
width exception survives the move to its full-width SEAT body. Boundary sets and
one-cell tightness guard the measured foundation pins, bounded by 134 × 50.
"""
from __future__ import annotations
import asyncio
import copy
import sys
import pytest
from rich.text import Text
from textual.widgets import DataTable, RichLog
from maxpane_dashboard.screens.seat import (
    BODY_IDS, DASHBOARDS, SCROLL_CONTAINERS, KEY_HINTS, SEAT_BODY_PINS,
    SEAT_FULL_LAYOUT_COLUMNS, SEAT_FULL_LAYOUT_ROWS, TALLER_HINT, SeatScreen,
)
from maxpane_dashboard.screens.surf import TALLER_HINT as SURF_TALLER_HINT
from maxpane_dashboard.widgets.seat import (
    SeatNow, SeatJob, SeatLog, SeatMachine, SeatCost, SeatOutputTokens, SeatLedgerTable,
    SeatConfig, SeatSkills, SeatRecords, SeatNodes, SeatControl, SeatGate, SeatAudit, SeatHero,
)
from maxpane_dashboard.widgets.seat.ledger import COMPACT_WIDTH, FULL_WIDTH, TIGHT_WIDTH
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.address_sweep.builders import _seat_app, _seat_payload
from tests.screens._sweeps import boundary_set
from tests.screens.test_surf_screen import _css_clipped_lines, _region_text, _screen_text, _status_bar_whole

#: Independent restatement of measure()'s healthy/worst/unattributed results.
MEASURED_BODY_PINS = {'SEAT': (132,40), 'LIVE': (132,30), 'CONFIG & SKILLS': (132,22),
                      'RECORDS': (132,20), 'NODES': (132,20), 'CONTROL': (132,26)}
MEASURED_SEAT_COLUMNS = 132
MEASURED_SEAT_ROWS = 40
MEASURED_LEDGER_CLEARS = 126
_BODY_WIDGETS = {
    'SEAT': (SeatMachine, SeatCost, SeatOutputTokens, SeatLedgerTable),
    'LIVE': (SeatNow, SeatJob, SeatLog), 'CONFIG & SKILLS': (SeatConfig, SeatSkills),
    'RECORDS': (SeatRecords,), 'NODES': (SeatNodes,), 'CONTROL': (SeatControl, SeatGate, SeatAudit),
}
_COLUMN_SWEEP_HEIGHT = 60
_ROW_SWEEP_WIDTH = 150
_THRESHOLDS = (MEASURED_LEDGER_CLEARS, 107, 132)
_ROW_THRESHOLDS = (20, 22, 26, 30, 40)

def worst_payload() -> dict:
    """WP4 foundation worst: long NOW/log, 50 skills, 400 records, node/JOB/audit data."""
    flat = _seat_payload()
    base = flat["seat_tasks_rows"][0]
    flat["seat_tasks_rows"] = [dict(copy.deepcopy(base), key=f"7/{i:08x}/2026-09-26T03:{i % 60:02d}:00.000Z", nodeId8=f"{i:08x}",
                                    turns=1234, tokens={"input": 9_999_999, "output": 999_999, "cached": 99_999_999, "cacheWrite": 0},
                                    verdictLagS=86_399, outcome=("accepted", "rejected", "failed", "pending")[i % 4],
                                    failureReason="local_build_failed" if i % 4 == 2 else None, repair=i % 5 == 0, resent=i % 7 == 0, sessionFiles=3)
                               for i in range(20)]
    flat["seat_tasks_window"] = dict(flat["seat_tasks_window"], rows=291)
    flat["seat_current"] = {"nodeId8": "0c1f9727", "jobId": base["jobId"], "role": "integrate", "kind": "code", "phase": "repairing", "startedUtc": "2026-09-26T03:39:30Z",
                            "elapsedS": 3599, "maxTurns": 120, "model": "gpt-6-astra", "tierDerived": "premium", "lastMessage": "x" * 400,
                            "lastMessageUtc": "2026-09-26T03:40:10Z", "planeSince": "2026-09-26T03:39:27Z", "objective": "o" * 200, "nodeKey": "build_contract_project"}
    flat["seat_daemon_running"] = 1
    flat["seat_daemon_work"] = "1 task running"
    flat["seat_skills_rows"] = [{"id": f"skill-with-a-long-name-{i:02d}", "on": i % 3 != 0, "needs": "network" if i % 4 == 0 else ("tool:forge" if i % 5 == 0 else None)} for i in range(50)]
    flat["seat_skills_offered"] = 50
    flat["seat_skills_on"] = 33
    orphan = {"pid": 64861, "pgid": 64861, "uid": 1000, "cgroup": "user-0.slice/session-147.scope", "ageS": 127000, "rssB": 130000000, "cmd": "codex exec --json",
              "pgidMembers": [{"pid": 64855, "uid": 0, "cgroup": "user-0.slice/session-147.scope", "cmd": "runuser"}]}
    flat["seat_machine_orphans"] = [dict(orphan, pid=orphan["pid"] + i) for i in range(3)]
    flat["seat_release_available"] = "0.1.0+5c1d2e3f"
    flat["seat_auth_degraded"] = True
    flat["seat_auth_reasons"] = ["paused after 3 failed runs", "api_error 401", "token refreshed 23:38 (not read)"]
    flat["seat_auth_credential_file_mtime_utc"] = "2026-09-25T23:38:43Z"
    flat["seat_hero_state"] = "amber"
    flat["seat_today_tasks"], flat["seat_today_stored"], flat["seat_today_not_stored"] = 999, 998, 1
    flat["seat_standing_attempts"], flat["seat_standing_accepted"] = 99_999, 88_888
    flat["seat_log_lines"] = [{"seq": i, "ts": f"2026-09-26T03:{i % 60:02d}:00.000Z", "kind": "phase", "invocation": None, "cursor": None,
                               "text": f"2026-09-26T03:{i % 60:02d}:00.000Z   working: " + "w" * 160} for i in range(1, 41)]
    flat["seat_log_seq"] = 40
    flat["seat_jobs"] = [dict(key='current-job', jobId=base['jobId'], nodeId8='0c1f9727', nodeKey='question', role='oracle')]
    flat["seat_current_jobs"] = flat["seat_jobs"]
    flat["seat_records_rows"] = [dict(key=f'record-{i}', jobId=base['jobId'], nodeKey='question',
                                     workStatus='pending', submittedUtc=base.get('submittedUtc')) for i in range(400)]
    flat["seat_nodes_all_rows"] = [dict(nodeKey=f'question-{i}', role='oracle', attempts=999) for i in range(30)]
    flat["seat_nodes_week_rows"] = flat["seat_nodes_all_rows"]
    flat["seat_control_last_audit"] = [dict(ts='2026-10-03T17:00:00Z', verb='restart', phase='verify', outcome='verified') for i in range(20)]
    return flat


def unattributed_payload() -> dict:
    flat = worst_payload()
    flat.update(seat_current=None, seat_daemon_running=3)
    return flat


PAYLOADS = {"healthy": _seat_payload, "worst": worst_payload, "unattributed": unattributed_payload}


def _inspect(app, dashboard):
    screen = app.screen
    widgets = {cls.__name__: screen.query_one(cls) for cls in _BODY_WIDGETS[dashboard]}
    hero = screen.query_one(SeatHero)
    marked = {name for name, w in widgets.items() if '‹' in _region_text(app, w)}
    hidden = {name: w.query_one(DataTable).max_scroll_x for name, w in widgets.items() if list(w.query(DataTable))}
    clipped = [(name, line) for name, w in widgets.items() for line in _css_clipped_lines(app, w)]
    clipped += [('SeatHero', line) for line in _css_clipped_lines(app, hero)]
    overflow, child_overflow = [], []
    for name, panel in widgets.items():
        p, c = panel.region, panel.parent.region
        if p.x < c.x or p.right > c.right:
            overflow.append(name)
        for child in panel.children:
            if child.display and child.region.height and child.region.bottom > p.bottom:
                child_overflow.append((name, child.id))
    scroll = any(screen.query_one('#' + id).show_vertical_scrollbar for id in SCROLL_CONTAINERS[dashboard])
    bar = screen.query_one(StatusBar)
    lines = _screen_text(app).splitlines()
    phrase = Text.from_markup(KEY_HINTS[dashboard]).plain
    return dict(marked=marked, hero_marked='‹' in _region_text(app, hero), hero_cut='…' in _region_text(app, hero),
                hidden=hidden, clipped=clipped, overflow=overflow, child_overflow=child_overflow,
                taller=TALLER_HINT in lines[0], scroll=scroll,
                status_whole=phrase in lines[bar.region.y] and _status_bar_whole(app),
                ledger_tier=screen.query_one(SeatLedgerTable)._tier,
                heights={name: w.region.height for name,w in widgets.items()})

async def _render(payload, size, dashboard='LIVE'):
    async with _seat_app(payload).run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        pilot.app.screen.select_dashboard(dashboard)
        await pilot.pause()
        await pilot.pause()
        return _inspect(pilot.app, dashboard)

def _assert_whole(r, where):
    assert r['status_whole'], (where, 'status bar cropped')
    assert not r['marked'], (where, r['marked'])
    assert not r['hero_marked'] and not r['hero_cut'], (where, 'hero cut')
    assert not r['clipped'], (where, 'CSS-clipped', r['clipped'])
    assert not any(r['hidden'].values()), (where, 'hidden table columns', r['hidden'])
    assert not r['overflow'], (where, 'panel overflow', r['overflow'])

def _width_loss(r):
    return r['marked'] or r['hero_marked'] or r['hero_cut'] or r['clipped'] or any(r['hidden'].values()) or not r['status_whole']

@pytest.mark.parametrize('dashboard', DASHBOARDS)
@pytest.mark.parametrize('payload_name', PAYLOADS)
async def test_the_body_is_whole_from_its_pinned_width(dashboard, payload_name):
    async with _seat_app(PAYLOADS[payload_name]()).run_test(size=(150,60)) as pilot:
        await pilot.app.screen._do_refresh()
        pilot.app.screen.select_dashboard(dashboard)
        for width in boundary_set(SEAT_BODY_PINS[dashboard][0], 100, 150, *_THRESHOLDS):
            await pilot.resize_terminal(width, _COLUMN_SWEEP_HEIGHT)
            await pilot.pause()
            r = _inspect(pilot.app, dashboard)
            assert not r['overflow'], (dashboard, width, r)
            if width >= SEAT_BODY_PINS[dashboard][0]:
                _assert_whole(r, (dashboard, payload_name, width))
            else:
                assert _width_loss(r), (dashboard, payload_name, width, 'unadvertised width loss')

@pytest.mark.parametrize('dashboard', DASHBOARDS)
async def test_the_column_pin_is_not_loose(dashboard):
    below = await _render(worst_payload(), (SEAT_BODY_PINS[dashboard][0]-1,60), dashboard)
    assert _width_loss(below), (dashboard, 'whole one column below its pin')

@pytest.mark.parametrize('width', [MEASURED_LEDGER_CLEARS-1,MEASURED_LEDGER_CLEARS,MEASURED_LEDGER_CLEARS+1])
async def test_the_ledger_clears_where_its_block_says(width):
    r = await _render(_seat_payload(), (width,60), 'SEAT')
    assert ('SeatLedgerTable' not in r['marked'] and r['ledger_tier']=='full') == (width>=MEASURED_LEDGER_CLEARS), r

@pytest.mark.parametrize('dashboard', DASHBOARDS)
@pytest.mark.parametrize('payload_name', PAYLOADS)
async def test_the_body_is_whole_from_its_pinned_height(dashboard, payload_name):
    async with _seat_app(PAYLOADS[payload_name]()).run_test(size=(134,60)) as pilot:
        await pilot.app.screen._do_refresh()
        pilot.app.screen.select_dashboard(dashboard)
        for rows in boundary_set(SEAT_BODY_PINS[dashboard][1], 16, 60, *_ROW_THRESHOLDS):
            await pilot.resize_terminal(SEAT_BODY_PINS[dashboard][0], rows)
            await pilot.pause()
            r = _inspect(pilot.app, dashboard)
            where = dashboard,payload_name,rows
            if rows >= SEAT_BODY_PINS[dashboard][1]:
                assert not r['taller'] and not r['scroll'], (where,r)
                assert not r['child_overflow'], (where,r['child_overflow'])
            else:
                assert r['taller'] == r['scroll'], (where,r)
            assert all(h>=3 for h in r['heights'].values()), (where,r)

@pytest.mark.parametrize('dashboard', DASHBOARDS)
async def test_the_row_pin_is_not_loose(dashboard):
    width, height = SEAT_BODY_PINS[dashboard]
    below = await _render(worst_payload(), (width,height-1), dashboard)
    assert below['scroll'] and below['taller'], (dashboard, 'whole one row below its pin')

def test_the_pins_are_the_measured_numbers():
    assert SEAT_FULL_LAYOUT_COLUMNS == MEASURED_SEAT_COLUMNS <= 134
    assert SEAT_FULL_LAYOUT_ROWS == MEASURED_SEAT_ROWS <= 50
    assert SEAT_BODY_PINS == MEASURED_BODY_PINS
    assert MEASURED_LEDGER_CLEARS <= SEAT_FULL_LAYOUT_COLUMNS
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH

def test_the_taller_hint_is_the_repo_spelling():
    assert TALLER_HINT == SURF_TALLER_HINT == '‹ taller'
    assert SeatScreen.KEY_HINTS == KEY_HINTS

async def measure():
    out = {}
    for payload_name, build in PAYLOADS.items():
        async with _seat_app(build()).run_test(size=(150,60)) as pilot:
            await pilot.app.screen._do_refresh()
            for dashboard in DASHBOARDS:
                pilot.app.screen.select_dashboard(dashboard)
                width_onset = None
                failure = None
                for width in range(134,99,-1):
                    await pilot.resize_terminal(width,60)
                    await pilot.pause()
                    r = _inspect(pilot.app,dashboard)
                    try:
                        _assert_whole(r, (dashboard,width))
                    except AssertionError as e:
                        failure = str(e)
                        break
                    width_onset = width
                height_onset = None
                for height in range(50,15,-1):
                    await pilot.resize_terminal(134,height)
                    await pilot.pause()
                    r = _inspect(pilot.app,dashboard)
                    if r['scroll'] or r['taller'] or r['child_overflow']:
                        break
                    height_onset = height
                out[payload_name + '/' + dashboard] = dict(columns=width_onset,rows=height_onset,width_failure=failure)
                print(payload_name,dashboard,out[payload_name+'/'+dashboard],file=sys.__stdout__,flush=True)
    ledger = None
    async with _seat_app(_seat_payload()).run_test(size=(134,60)) as pilot:
        await pilot.app.screen._do_refresh()
        pilot.app.screen.select_dashboard('SEAT')
        for width in range(134,99,-1):
            await pilot.resize_terminal(width,60)
            await pilot.pause()
            r = _inspect(pilot.app,'SEAT')
            if 'SeatLedgerTable' in r['marked'] or r['ledger_tier'] != 'full':
                break
            ledger = width
    out['ledger_clears'] = ledger
    return out

if __name__ == '__main__':
    print(asyncio.run(measure()))

@pytest.mark.parametrize("defer_auto_scroll", [False, True])
async def test_long_raw_log_rows_have_a_scrollbar_and_remain_accessible(monkeypatch, defer_auto_scroll) -> None:
    payload = worst_payload()
    payload["seat_log_lines"][-1]["text"] += " END-SCROLLBACK"
    auto_scroll_complete = asyncio.Event()
    original_scroll_end = RichLog.scroll_end

    def observed_scroll_end(log, **kwargs):
        if "immediate" in kwargs:
            return original_scroll_end(log, **kwargs)  # RichLog.write's vertical scroll
        # SeatLog schedules this after refresh; Textual itself defers it once more.
        # Observe the actual completion, including an extra frame of ordering pressure.
        kwargs["on_complete"] = auto_scroll_complete.set
        if defer_auto_scroll:
            log.call_after_refresh(original_scroll_end, log, **kwargs)
        else:
            original_scroll_end(log, **kwargs)

    monkeypatch.setattr(RichLog, "scroll_end", observed_scroll_end)
    async with _seat_app(payload).run_test(size=(SEAT_FULL_LAYOUT_COLUMNS, SEAT_FULL_LAYOUT_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await asyncio.wait_for(auto_scroll_complete.wait(), 3)
        panel = pilot.app.screen.query_one(SeatLog)
        log = panel.query_one(RichLog)
        assert log.max_scroll_x > 0 and log.show_horizontal_scrollbar
        assert "END-SCROLLBACK" in log.lines[-1].text
        log.scroll_to(x=log.max_scroll_x, animate=False, immediate=True)

        async def wait_for_visible_end():
            while "END-SCROLLBACK" not in _region_text(pilot.app, panel):
                painted = asyncio.Event()
                panel.call_after_refresh(painted.set)
                panel.refresh()
                await painted.wait()
        await asyncio.wait_for(wait_for_visible_end(), 3)
        assert log.scroll_x == log.max_scroll_x
        assert "END-SCROLLBACK" in _region_text(pilot.app, panel)

        # A newly delivered row must preserve the user's horizontal viewport.
        previous_x = log.scroll_x
        auto_scroll_complete.clear()
        event = dict(payload["seat_log_lines"][-1])
        event["seq"] += 1
        panel.update_data(seat_log_lines=[event], seat_log_seq=event["seq"])
        await asyncio.wait_for(auto_scroll_complete.wait(), 3)
        assert log.scroll_x == previous_x
        assert "END-SCROLLBACK" in _region_text(pilot.app, panel)


async def test_unattributed_running_is_visible_in_now_and_live_at_the_pin():
    app = _seat_app(unattributed_payload())
    async with app.run_test(size=(SEAT_FULL_LAYOUT_COLUMNS, SEAT_FULL_LAYOUT_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        assert '⚙ 3 tasks running' in _region_text(pilot.app, screen.query_one(SeatNow))
        assert '⚙ 3 tasks running' in _region_text(pilot.app, screen.query_one(SeatHero))
        widget = screen.query_one('#seat-now-task')
        rows = _screen_text(pilot.app).splitlines()
        y = widget.region.y
        x = rows[y].index('3 tasks running')
        style = screen.get_style_at(x, y)
        assert style.color.get_truecolor(pilot.app.ansi_theme) == pilot.app.ansi_theme.ansi_colors[3]
