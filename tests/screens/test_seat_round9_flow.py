"""Cross-dashboard write flow: key ownership, stale plans and its independent timer."""
import asyncio
import copy
import threading

import pytest
from textual.widgets import DataTable, Input

from maxpane_dashboard.screens.seat_task_detail import SeatTaskDetail
from maxpane_dashboard.widgets.seat import SeatSkills
from tests.screens.test_seat_control import _A, _Manager, _broker, _painted, _type, _calls, _screen_text, DOC, PLAN, PLAN_ID, APPLIED, _verify_sequence


async def test_dashboard_switch_drops_confirm_and_never_applies_its_plan():
    broker=_broker()
    manager=_Manager(copy.deepcopy(DOC),broker)
    async with _A(manager).run_test(size=(170,55)) as pilot:
        await _painted(pilot); await pilot.press('r'); await _painted(pilot)
        screen=pilot.app.screen
        assert manager.plan_open
        await pilot.click('#seat-hero-seat'); await _painted(pilot)
        screen.flow.submit(PLAN_ID[:4]); await _painted(pilot)
        assert not _calls(broker,'apply')
        assert screen.selected_dashboard=='SEAT' and not screen.prompt_open
        assert not manager.plan_open
        await pilot.press('6'); await _painted(pilot)
        assert 'plan 7f3a dropped — not applied' in _screen_text(pilot)


async def test_late_plan_after_leaving_its_dashboard_opens_no_prompt():
    entered=asyncio.Event(); release=threading.Event(); loop=asyncio.get_running_loop()
    def hold(_args):
        loop.call_soon_threadsafe(entered.set); release.wait(5); return PLAN
    broker=_broker(restart=hold)
    manager=_Manager(copy.deepcopy(DOC),broker)
    try:
        async with _A(manager).run_test(size=(170,55)) as pilot:
            await _painted(pilot); await pilot.press('r'); await asyncio.wait_for(entered.wait(),2)
            screen=pilot.app.screen
            await pilot.press('1'); release.set(); await _painted(pilot)
            assert screen.selected_dashboard=='SEAT' and not screen.prompt_open
            assert not manager.plan_open
            await pilot.press('6'); await _painted(pilot)
            assert 'dropped — not applied' in _screen_text(pilot)
            assert not _calls(broker,'apply')
    finally:
        release.set()


async def test_confirm_owns_digits_verbs_tab_q_t_focus_and_real_enter():
    from maxpane_dashboard.seat_cli import SeatApp
    broker=_broker(); manager=_Manager(copy.deepcopy(DOC),broker)
    async with SeatApp(manager, theme="textual-dark").run_test(size=(170,55)) as pilot:
        await _painted(pilot)
        await pilot.press('6','r'); await _painted(pilot)
        screen=pilot.app.screen; theme=pilot.app.theme
        field=screen.query_one(Input)
        screen.query_one('#seat-audit-log').focus()
        await pilot.press('1','r','d','c','tab','q','t'); await _painted(pilot)
        assert field.value=='1rdcqt'
        assert screen.selected_dashboard=='CONTROL' and pilot.app.theme==theme
        assert len(_calls(broker,'restart'))==1 and not _calls(broker,'drain-restart')
        field.value=PLAN_ID[:4]
        await pilot.press('enter'); await _painted(pilot)
        assert len(_calls(broker,'apply'))==1
        assert not manager.plan_open


async def test_actual_detail_popup_does_not_pause_timer_driven_verdict():
    popup_open = threading.Event()
    verdict_returned = asyncio.Event()
    loop = asyncio.get_running_loop()

    def verify(_args):
        verified = True if popup_open.is_set() else None
        if verified:
            loop.call_soon_threadsafe(verdict_returned.set)
        return {'ok': True, 'data': {'verified': verified, 'connected': 'pending',
                                    'elapsed_s': 1, 'verify_lines': []}}

    broker = _broker(verify=verify)
    doc = copy.deepcopy(DOC)
    doc['jobs'] = [dict(key='cached-attempt', jobId='b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70',
                        nodeKey='tests', submittedUtc='2026-09-26T03:40:00Z', reply='cached detail')]
    manager = _Manager(doc, broker)
    async with _A(manager).run_test(size=(170,55)) as pilot:
        await _painted(pilot); await pilot.press('r'); await _painted(pilot)
        screen=pilot.app.screen
        await _type(pilot,PLAN_ID[:4])
        assert screen.flow.mode=='verifying'
        await pilot.press('2', 'enter')
        await _painted(pilot)
        assert isinstance(pilot.app.screen,SeatTaskDetail)
        assert 'cached detail' in _screen_text(pilot)
        calls_before_popup = len(_calls(broker, 'verify'))
        assert not verdict_returned.is_set() and screen.flow.mode == 'verifying'
        popup_open.set()
        await asyncio.wait_for(verdict_returned.wait(), 3)
        await _painted(pilot)
        assert isinstance(pilot.app.screen, SeatTaskDetail)
        assert screen.flow.mode=='done' and len(_calls(broker,'verify'))>=2
        assert len(_calls(broker, 'verify')) > calls_before_popup
        assert not manager.plan_open
        await pilot.press('escape', '6'); await _painted(pilot)
        assert 'verified ✓' in _screen_text(pilot)


async def test_skill_toggle_after_refresh_resize_and_hidden_update_uses_same_id():
    doc=copy.deepcopy(DOC)
    doc['seat']['skills']['rows']=[dict(id=f'skill-{i:02d}',on=True,needs=None) for i in range(50)]
    broker=_broker(); manager=_Manager(doc,broker)
    async with _A(manager).run_test(size=(134,30)) as pilot:
        await _painted(pilot); await pilot.press('3','tab'); await _painted(pilot)
        screen=pilot.app.screen; panel=screen.query_one(SeatSkills); table=panel.query_one(DataTable)
        table.move_cursor(row=22); await _painted(pilot)
        doc['seat']['skills']['rows'].insert(0,dict(id='new-skill',on=False,needs=None))
        await screen._do_refresh(); await _painted(pilot)
        await pilot.resize_terminal(110,30); await _painted(pilot)
        await pilot.press('2')
        doc['seat']['skills']['rows'].insert(0,dict(id='another-new',on=False,needs=None))
        await screen._do_refresh()
        await pilot.press('3','tab'); await _painted(pilot)
        await pilot.press('space'); await _painted(pilot)
        assert _calls(broker,'skills-set')==[{'skill_id':'skill-22','on':False}]
        assert panel.selected_row()['id']=='skill-22'


@pytest.mark.parametrize('exit_kind',['escape','switch','expiry','error','verdict'])
async def test_manager_plan_open_is_false_on_every_flow_exit(exit_kind):
    broker=_broker(apply={'ok':False,'error':{'code':'busy'}}) if exit_kind=='error' else _broker()
    manager=_Manager(copy.deepcopy(DOC),broker)
    async with _A(manager).run_test(size=(170,55)) as pilot:
        await _painted(pilot); await pilot.press('r'); await _painted(pilot)
        screen=pilot.app.screen
        assert manager.plan_open
        if exit_kind=='escape': await pilot.press('escape')
        elif exit_kind=='switch': await pilot.click('#seat-hero-seat')
        else:
            if exit_kind=='expiry': screen.flow._now=lambda:screen.flow._plan_started+61
            await _type(pilot,PLAN_ID[:4])
        await _painted(pilot)
        assert not manager.plan_open


async def test_config_read_only_setting_names_its_actual_change_procedure():
    from maxpane_dashboard.widgets.seat import SeatConfig
    manager = _Manager(copy.deepcopy(DOC), _broker())
    async with _A(manager).run_test(size=(170,55)) as pilot:
        await _painted(pilot)
        await pilot.press('3'); await _painted(pilot)
        screen = pilot.app.screen
        panel = screen.query_one(SeatConfig)
        table = panel.query_one(DataTable)
        table.move_cursor(row=next(i for i,r in enumerate(panel._seat_rows) if r['setting']=='capacity'))
        await pilot.press('space'); await _painted(pilot)
        assert 'capacity is the --concurrency start flag' in screen.flow._status.plain
        assert 'runbook §4c' in screen.flow._status.plain
        assert not screen.flow._plan


@pytest.mark.parametrize('verified', [True, False])
async def test_skill_restart_required_waits_for_verified_toggle(verified):
    from tests.screens.test_seat_control import _manual_control
    plan = copy.deepcopy(PLAN)
    plan['plan'].update(verb='skills-set', restart_required_after=True)
    broker = _broker(**{'skills-set':plan, 'verify':_verify_sequence((None,None,None),(verified,None,None))})
    manager = _Manager(copy.deepcopy(DOC), broker)
    async with _A(manager).run_test(size=(170,55)) as pilot:
        flow = await _manual_control(pilot)
        await flow._plan_verb('skills-set', {'skill_id':'oracle-assess','on':False})
        await flow._apply(PLAN_ID[:4])
        assert not manager.restart_required_calls
        await flow._poll_verify()
        assert not manager.restart_required_calls
        await flow._poll_verify()
        assert manager.restart_required_calls == ([True] if verified else [])


async def test_container_boot_is_read_only_in_config_and_control():
    from maxpane_dashboard.widgets.seat import SeatConfig
    doc = copy.deepcopy(DOC)
    doc['host']['kind'] = 'docker'
    doc['unit']['restartPolicy'] = 'unless-stopped'
    broker = _broker()
    async with _A(_Manager(doc,broker)).run_test(size=(180,55)) as pilot:
        await _painted(pilot)
        assert 'boot — container restart policy · read-only' in _screen_text(pilot)
        await pilot.press('b'); await _painted(pilot)
        assert not _calls(broker,'enable-boot') and not _calls(broker,'disable-boot')
        await pilot.press('3'); await _painted(pilot)
        screen = pilot.app.screen
        panel = screen.query_one(SeatConfig)
        panel.query_one(DataTable).move_cursor(row=next(i for i,r in enumerate(panel._seat_rows) if r['setting']=='boot'))
        await pilot.press('space'); await _painted(pilot)
        assert 'unless-stopped' in _screen_text(pilot)
        assert 'CONFIG (container)' in _screen_text(pilot)
        assert not _calls(broker,'enable-boot') and not _calls(broker,'disable-boot')
