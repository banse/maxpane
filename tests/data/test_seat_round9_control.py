"""Round9 control publication and bounded display contract."""
import copy
import json

from maxpane_dashboard.data import seat_models as models
from maxpane_dashboard.data.seat_broker_client import FakeBroker
from tests.data.test_seat_manager import _manager, Clock
from tests.data.test_seat_models import _round9_document


def test_control_display_projects_bounded_plain_parts_and_complete_plan():
    doc=_round9_document()
    command='systemctl restart imd-worker.service '+('safe-target-'*35)
    warning='a task assigned in the ~1–5 s between the gate reads and systemctl may be reported as a failed run; 3 consecutive failed runs pause the seat 15 min (never measured: 16/16 historical restarts were idle)'
    doc['control'].update(status='verified ✓ · connected: pending\n'+('doctor-output '*40),
        statusParts=[{'text':'verified ✓','colour':'green','secret':'discard'},{'text':' · connected: pending','colour':'yellow'},
                     {'text':'[red]literal[/] eyJuYW1lIjoiYWJjZGVmZ2hpaiJ9 $2','colour':'link=https://evil.invalid'}],
        plan={'planId':'7f3a','command':command,'warning':warning,'preconditions':'idle_beats 9/4 · plane plane+local running0 standing_age_s0.4 · outbox_files0 · unit_activeTrue',
              'inverse':'stop','verification':'shutting down → runtimes: within30s · connected when admitted (reported separately)','secret':'discard'})
    shaped=models.shape_dashboard_document(doc)
    assert shaped['control']['plan']['command']==command
    assert shaped['control']['plan']['warning']==warning
    assert 'standing_age_s0.4' in shaped['control']['plan']['preconditions']
    assert shaped['control']['plan']['inverse']=='stop'
    assert 'reported separately' in shaped['control']['plan']['verification']
    assert len(shaped['control']['status'])>160
    parts=shaped['control']['statusParts']
    assert all(set(row)=={'text','colour'} for row in parts)
    assert parts[0]['colour']=='green' and parts[1]['colour']=='yellow' and parts[2]['colour']==''
    assert '[red]literal[/]' in parts[2]['text'] and '$' not in parts[2]['text'] and 'eyJ' not in parts[2]['text']
    assert models.validate_status_document(shaped) is None
    flat=models.fold_status_document(shaped)
    assert flat['seat_control_status_parts']==parts
    assert flat['seat_control_plan']==shaped['control']['plan']


def test_control_status_has_combined_text_and_row_caps_with_worst_document():
    doc=_round9_document()
    doc['control'].update(status='x'*100_000,statusParts=[{'text':'y'*100_000,'colour':'red'} for _ in range(100)],
        plan={name:'z'*100_000 for name in ('command','warning','preconditions','inverse','verification')})
    shaped=models.shape_dashboard_document(doc)
    assert len(shaped['control']['status'])==4096 and shaped['control']['status'].endswith('…')
    assert len(shaped['control']['statusParts'])<=32
    assert sum(len(row['text']) for row in shaped['control']['statusParts'])<=4096
    assert set(shaped['control']['plan'])==set(models.SEAT_BLOCK_KEYS['seat_control_plan'])
    assert [len(shaped['control']['plan'][k]) for k in ('command','warning','preconditions','inverse','verification')]==[1024,1024,1024,160,512]
    assert len(json.dumps(shaped,ensure_ascii=False,indent=2).encode())<models.MAX_DOCUMENT_BYTES
    assert models.validate_status_document(shaped) is None
    doc['control']['statusParts']=[{'text':'z','colour':'dim'} for _ in range(100)]
    assert len(models.shape_dashboard_document(doc)['control']['statusParts'])==32


async def test_fast_control_reads_twenty_audit_lines_independent_of_slow_journal(tmp_path):
    clock=Clock(); calls=[]; phase=['plan']
    def read(verb,args):
        calls.append((verb,args))
        if verb=='ping': return {'ok':True,'data':{'in_flight':{'verb':'restart','plan_id':'7f3a','since':'2026-09-26T03:40:12Z'}}}
        if verb=='gate': return {'ok':True,'data':{'safe':phase[0]=='verify','idle_beats':9,'idle_beats_required':4,'plane':{'mode':'plane+local','running':0},'outbox_files':0,'unit_active':True}}
        if verb=='audit-tail': return {'ok':True,'data':{'lines':[{'seq':i,'verb':'restart','phase':phase[0]} for i in range(20)]}}
        return {'ok':True,'data':{}}
    broker=FakeBroker({v:(lambda args,v=v:read(v,args)) for v in ('ping','gate','audit-tail','work-stat','outbox','orphans')})
    class Unit:
        journal_reads=0
        def read_unit(self): return {}
        def read_host(self): return {}
        def read_journal(self): self.journal_reads+=1; return {'journal':None,'reason':'fixture journal unavailable'}
    unit=Unit(); m=_manager(tmp_path,broker=broker,unit_reader=unit,now=clock,offline=True)
    try:
        await m.fetch_and_compute(); await m.settle()
        for item in ('plan','apply','verify'):
            phase[0]=item; clock.advance(5)
            await m.fetch_and_compute(); await m.settle()
            flat=await m.fetch_and_compute()
            assert len(flat['seat_control_last_audit'])==20
            assert flat['seat_control_last_audit'][-1]['phase']==item
            assert flat['seat_control_gate']['safe']==(item=='verify')
        assert unit.journal_reads==1
        assert all(args=={'n':20} for verb,args in calls if verb=='audit-tail')
        assert len([v for v,a in calls if v=='audit-tail'])>=4
    finally:
        await m.close()


async def test_manager_control_flow_survives_document_fold_and_cost_metrics_use_days(tmp_path,monkeypatch):
    m=_manager(tmp_path,offline=True)
    try:
        m.update_control_flow({'plan':{'planId':'7f3a','verb':'skills-set','command':'imd skills remove oracle-assess','warning':'restart required'},
            'status':'verified ✓ · connected: pending','statusParts':[{'text':'verified ✓','colour':'green'},{'text':' · connected: pending','colour':'yellow'}],'mode':'done'})
        flat=await m.fetch_and_compute()
        assert flat['seat_control_plan']['command']=='imd skills remove oracle-assess'
        assert [p['colour'] for p in flat['seat_control_status_parts']]==['green','yellow']
        assert models.validate_status_document(m.document()) is None
        monkeypatch.setattr(m._ledger,'days',lambda n:[{'dayUtc':'2026-09-25','tokens':{'output':100}},{'dayUtc':'2026-09-26','tokens':{'output':300}}])
        cost=m._cost_block(m._clock())
        assert cost['outputTokens']['today']==300
        assert cost['outputTokens']['sevenDays']==400
        assert cost['outputTokens']['averagePerDay']==200
        assert cost['outputTokens']['days']==2
    finally:
        await m.close()


async def test_full_broker_plan_reaches_real_manager_document_fold_and_panels(tmp_path):
    from tests.screens.test_seat_control import _A, _broker, _painted, _screen_text, PLAN
    manager = _manager(tmp_path, broker=_broker(), offline=True)
    try:
        async with _A(manager).run_test(size=(180,70)) as pilot:
            await _painted(pilot)
            screen = pilot.app.screen
            await screen.flow._plan_verb('restart', {})
            await _painted(pilot)
            plan = manager.document()['control']['plan']
            assert plan['command'] == ' '.join(PLAN['plan']['argv'])
            assert plan['warning'] == PLAN['plan']['warning']
            assert 'standing_age_s 0.4' in plan['preconditions']
            assert 'last_lifecycle_line:' in plan['preconditions']
            assert plan['inverse'] == 'stop'
            assert 'within 30 s' in plan['verification'] and 'reported separately' in plan['verification']
            text = _screen_text(pilot)
            for expected in ('systemctl restart imd-worker.service', 'idle_beats 9/4', 'standing_age_s 0.4',
                             'last_lifecycle_line:', 'inverse: stop', 'within 30 s', 'reported separately'):
                assert expected in text
            assert '3 consecutive failed runs pause the seat 15 min' in text
    finally:
        await manager.close()


async def test_fast_control_phase_facts_reach_gate_audit_and_hero_in_one_panel_refresh(tmp_path):
    from tests.screens.test_seat_control import _A, _painted
    from tests.screens.test_surf_screen import _region_text
    from maxpane_dashboard.widgets.seat import SeatGate, SeatAudit

    phase = ['plan', 4]
    def read(verb, _args):
        name, idle = phase
        if verb == 'ping':
            return {'ok':True, 'data':{'in_flight':
                    {'verb':'restart','plan_id':'7f3a','since':'2026-09-26T03:40:12Z'} if name == 'apply' else None}}
        if verb == 'gate':
            return {'ok':True, 'data':{'safe':name != 'apply','reason':'working' if name == 'apply' else None,
                    'idle_beats':idle,'idle_beats_required':4,'plane':{'mode':'plane+local','running':0},
                    'last_lifecycle_line':f'2026-09-26T03:40:12Z {name} restart','outbox_files':0,'unit_active':True}}
        return {'ok':True, 'data':{'lines':[{'seq':idle,'ts':'2026-09-26T03:40:12Z','verb':'restart',
                'phase':name,'outcome':name,'verified':True if name == 'verify' else None,'connected':'pending' if name == 'verify' else None}]}}

    broker = FakeBroker({verb:(lambda args, verb=verb:read(verb,args)) for verb in ('ping','gate','audit-tail')})
    manager = _manager(tmp_path, broker=broker, offline=True)
    try:
        async with _A(manager).run_test(size=(220,70)) as pilot:
            await _painted(pilot)
            screen = pilot.app.screen
            screen._refresh_timer.stop()
            await manager.settle()
            for name, idle, mode in [('plan',4,'planned'), ('apply',5,'applying'), ('verify',6,'done')]:
                phase[:] = [name,idle]
                manager.update_control_flow({'mode':mode,'plan':{'planId':'7f3a','verb':'restart'}})
                # Detached reads settle before the next ordinary display cycle.
                await manager._tier_control()
                await screen._do_refresh()
                await _painted(pilot)
                gate = _region_text(pilot.app, screen.query_one(SeatGate))
                audit = _region_text(pilot.app, screen.query_one(SeatAudit))
                hero = _region_text(pilot.app, screen.query_one('#seat-hero-control'))
                assert f'idle beats: {idle} of 4' in gate and f'{name} restart' in gate
                assert f'restart {name} {name}' in audit
                assert f'idle {idle}' in hero
                if name == 'verify':
                    assert manager.document()['control']['inFlight'] is None
                    assert 'in flight' not in hero and 'CONTROL ⚠' not in hero
                    assert 'verified True' in audit and 'connected pending' in audit
                elif name == 'apply':
                    assert 'in flight' in hero and 'CONTROL ⚠' in hero
                else:
                    # A merely planned operation has not acquired the broker's apply lock.
                    assert 'in flight' not in hero and 'CONTROL ⚠' not in hero
    finally:
        await manager.close()
