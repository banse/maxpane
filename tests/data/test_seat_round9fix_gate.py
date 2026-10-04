"""Gate cadence and independent stamps; fake clocks/transports only."""
import asyncio
import threading

import httpx
import pytest

from maxpane_dashboard.data import seat_models as models
from maxpane_dashboard.data.seat_broker_client import BrokerError, FakeBroker
from tests.data.test_seat_manager import Clock, _manager, _api


def recording_broker(clock, calls, *, failure=None, block=None):
    def read(verb, args):
        calls.append((clock(), verb, args))
        if verb == 'gate':
            if block:
                block[0].set()
                assert block[1].wait(10), 'test did not release gate read'
            if failure and failure[0]:
                raise BrokerError('transport', {})
            return {'ok': True, 'data': {'idle_beats': 9, 'idle_beats_required': 4, 'safe': True,
                    'plane': {'mode': 'local-only' if args.get('offline') else 'plane+local', 'running': 0}}}
        return {'ok': True, 'data': {'lines': []} if verb == 'audit-tail' else {}}
    return FakeBroker({verb: (lambda args, verb=verb: read(verb, args))
                       for verb in ('gate', 'ping', 'audit-tail')})


def gates(calls):
    return [(at, args) for at, verb, args in calls if verb == 'gate']


@pytest.mark.parametrize('dashboard,expected', [('LIVE', [0, 60]), ('CONTROL', [0, 15, 30, 45, 60])])
async def test_gate_clock_cadence_keeps_ping_and_audit_each_cycle(tmp_path, dashboard, expected):
    clock = Clock(); calls = []
    m = _manager(tmp_path, now=clock, broker=recording_broker(clock, calls), offline=True)
    m.select_dashboard(dashboard)
    try:
        for _ in range(13):
            await m._tier_control()
            clock.advance(5)
        assert [at - expected_start for at, _ in gates(calls) for expected_start in [1790394012.0]] == expected
        assert len([v for _, v, _ in calls if v == 'ping']) == 26
        assert [args for _, v, args in calls if v == 'audit-tail'] == [{'n': 20}] * 13
    finally:
        await m.close()


async def test_gate_own_stamp_survives_control_landing_and_failed_gate(tmp_path):
    clock = Clock(); calls = []; failure = [False]
    m = _manager(tmp_path, now=clock, broker=recording_broker(clock, calls, failure=failure), offline=True)
    try:
        await m._tier_control()
        first = m._control_block()['gate'].copy()
        assert first['asOfUtc'] == '2026-09-26T03:40:12Z'
        clock.advance(5); await m._tier_control()
        assert m._control_block()['gate'] == first
        clock.advance(55); failure[0] = True; await m._tier_control()
        assert m._control_block()['gate'] == first
    finally:
        await m.close()


def test_gate_timestamp_and_busy_reason_survive_schema_and_fold():
    from tests.data.test_seat_models import _round9_document
    doc = _round9_document()
    doc['control']['gate'] = {'asOfUtc': '2026-09-26T03:40:12Z', 'planeReason': 'busy', 'planeMode': 'local-only'}
    shaped = models.shape_dashboard_document(doc)
    assert shaped['control']['gate']['asOfUtc'] == '2026-09-26T03:40:12Z'
    assert shaped['control']['gate']['planeReason'] == 'busy'
    assert models.validate_status_document(shaped) is None
    assert models.fold_status_document(shaped)['seat_control_gate']['planeReason'] == 'busy'


@pytest.mark.parametrize('line', [
    '2026-09-26T03:40:13.000Z accepted implement 12345678 — question (max 60 turns)',
    '2026-09-26T03:40:13.000Z submitted implement for 12345678',
    '2026-09-26T03:40:13.000Z submission stored (aaaaaaaaaaaa) — awaiting verdict',
    '2026-09-26T03:40:13.000Z question failed: boom',
    '2026-09-26T03:40:13.000Z cancelled 12345678: superseded',
])
async def test_each_local_lifecycle_signal_bumps_gate_five_seconds(tmp_path, line):
    clock = Clock(); calls = []
    m = _manager(tmp_path, now=clock, broker=recording_broker(clock, calls), offline=True)
    try:
        await m._tier_control(); clock.advance(1)
        m.feed_lines([line]); m.drain()
        clock.advance(4); await m._tier_control(); assert len(gates(calls)) == 1
        clock.advance(1); await m._tier_control(); assert len(gates(calls)) == 2
    finally:
        await m.close()


async def test_flow_phase_changes_are_immediate_and_unchanged_publishes_obey_poll(tmp_path):
    clock = Clock(); calls = []
    m = _manager(tmp_path, now=clock, broker=recording_broker(clock, calls), offline=True)
    try:
        for mode in ('planned', 'applying', 'verifying', 'done'):
            m.update_control_flow({'mode': mode, 'plan': {'planId': '7f3a'}})
            await m._tier_control()
        assert len(gates(calls)) == 4
        m.update_control_flow({'mode': 'planned', 'plan': {'planId': 'other'}})
        await m._tier_control()
        for _ in range(20):
            m.update_control_flow({'mode': 'planned', 'plan': {'planId': 'other'}, 'status': 'typing'})
            await m._tier_control()
        assert len(gates(calls)) == 5
        clock.advance(4.99); await m._tier_control(); assert len(gates(calls)) == 5
        clock.advance(.01); await m._tier_control(); assert len(gates(calls)) == 6
    finally:
        await m.close()


@pytest.mark.parametrize('trigger', ['phase', 'event'])
async def test_gate_trigger_arriving_inflight_keeps_its_deadline(tmp_path, trigger):
    clock = Clock(); calls = []; entered = threading.Event(); release = threading.Event()
    m = _manager(tmp_path, now=clock, broker=recording_broker(clock, calls, block=(entered, release)), offline=True)
    task = asyncio.create_task(m._tier_control())
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        if trigger == 'phase':
            m.update_control_flow({'mode': 'planned', 'plan': {'planId': '7f3a'}})
        else:
            clock.advance(1); m._apply_bumps(['accepted']); clock.advance(5)
        release.set(); await task
        await m._tier_control()
        assert len(gates(calls)) == 2
    finally:
        release.set(); await task; await m.close()


async def test_busy_gate_args_keep_broker_online_and_carry_own_reason(tmp_path):
    clock = Clock(); calls = []
    from tests.data.test_seat_round9_cache import client
    api = client(lambda req: httpx.Response(503, json={'error': 'busy'}), clock)
    broker = recording_broker(clock, calls)
    m = _manager(tmp_path, now=clock, broker=broker, api=api)
    try:
        await api.standing(7)
        await m._tier_control()
        assert gates(calls)[0][1] == {'offline': True}
        assert broker.offline is False
        assert m._control_block()['gate']['planeReason'] == 'busy'
    finally:
        await m.close(); await api.close()


async def test_api_spawn_window_blocks_refresh_bursts_but_allows_timer_jitter(tmp_path):
    clock = Clock(); calls = []
    m = _manager(tmp_path, now=clock)
    async def record(tier): calls.append(tier)
    for tier in ('standing', 'seatwork', 'details', 'plane'):
        setattr(m, '_tier_' + tier, lambda tier=tier: record(tier))
    try:
        await m.fetch_and_compute(); await m.settle()
        assert calls == ['standing', 'seatwork', 'details', 'plane']
        for _ in range(20):
            for tier in ('standing', 'seatwork', 'details', 'plane'): m.bump(tier, 0)
            await m.fetch_and_compute(); await m.settle()
        assert len(calls) == 4
        clock.advance(3.99); await m.fetch_and_compute(); await m.settle(); assert len(calls) == 4
        clock.advance(1); await m.fetch_and_compute(); await m.settle(); assert len(calls) == 8
    finally:
        await m.close()


def test_mac_gate_offline_arg_skips_standing_but_fresh_plan_still_reads(tmp_path, monkeypatch):
    from tests.data.test_seat_broker_client import _local
    broker, _, _, _ = _local(tmp_path, offline=False)
    reads = []
    monkeypatch.setattr(broker, '_standing', lambda: reads.append('standing') or {'running': []})
    gate = broker.read('gate', {'offline': True})
    assert reads == [] and gate['plane']['mode'] == 'local-only'
    assert broker.offline is False
    broker.plan('restart')
    assert reads == ['standing']


@pytest.mark.parametrize('verb,code', [('plan', 'gate_blocked'), ('plan', 'force_node8_mismatch'),
                                      ('apply', 'gate_blocked'), ('apply', 'force_node8_mismatch')])
async def test_real_write_flow_refusal_invalidates_gate_immediately(tmp_path, verb, code):
    from tests.screens.test_seat_control import _A, _broker, _painted
    def refusal(_): raise BrokerError(code, {'reason': 'fixture refusal'})
    broker = _broker(**({'restart': refusal} if verb == 'plan' else {'apply': refusal}))
    manager = _manager(tmp_path, broker=broker, offline=True)
    try:
        async with _A(manager).run_test(size=(180, 70)) as pilot:
            await _painted(pilot); screen = pilot.app.screen
            screen._refresh_timer.stop(); await manager.settle()
            screen.flow.publish = lambda: None
            notified = []
            original = getattr(manager, 'gate_refused', lambda code: None)
            def notify(code):
                notified.append(code); original(code)
            manager.gate_refused = notify
            await screen.flow._plan_verb('restart', {})
            if verb == 'apply':
                await manager._tier_control()
                # Avoid counting the legitimate applying phase refresh as the refusal hook.
                screen.flow.publish = lambda: None
                await screen.flow._apply('local-only')
            assert notified == [code]
            before = len([v for v, _ in broker.calls if v == 'gate'])
            await manager._tier_control()
            assert len([v for v, _ in broker.calls if v == 'gate']) == before + 1
    finally:
        await manager.close()


async def test_busy_gate_paints_own_timestamp_and_local_only_plane_busy(tmp_path):
    from tests.screens.test_seat_control import _A, _painted
    from tests.screens.test_surf_screen import _region_text
    from maxpane_dashboard.widgets.seat import SeatGate
    clock = Clock(); calls = []
    broker = recording_broker(clock, calls)
    manager = _manager(tmp_path, now=clock, broker=broker, offline=True)
    try:
        async with _A(manager).run_test(size=(131, 29)) as pilot:
            await _painted(pilot); screen = pilot.app.screen
            screen._refresh_timer.stop(); await manager.settle()
            flat = await manager.fetch_and_compute()
            flat['seat_control_gate'].update(asOfUtc='2026-09-26T03:40:12Z', planeMode='local-only', planeReason='busy')
            flat['seat_as_of_hhmm']['broker'] = '23:59'
            panel = screen.query_one(SeatGate)
            panel.update_data(**flat); await _painted(pilot)
            text = _region_text(pilot.app, panel)
            from maxpane_dashboard.analytics.seat_signals import as_of_hhmm
            assert 'GATE · as of ' + as_of_hhmm('2026-09-26T03:40:12Z') in text
            assert 'local-only · plane busy' in text and 'offline' not in text and '23:59' not in text
    finally:
        await manager.close()


async def test_selecting_control_uses_last_read_plus_fifteen_seconds(tmp_path):
    clock = Clock(); calls = []
    m = _manager(tmp_path, now=clock, broker=recording_broker(clock, calls), offline=True)
    try:
        await m._tier_control(); clock.advance(10); m.select_dashboard('CONTROL')
        await m._tier_control(); assert len(gates(calls)) == 1
        clock.advance(4); await m._tier_control(); assert len(gates(calls)) == 1
        clock.advance(1); await m._tier_control(); assert len(gates(calls)) == 2
    finally:
        await m.close()


async def test_twenty_real_flow_refreshes_add_no_detail_api_reads(tmp_path):
    from tests.data.test_seat_round9_cache import Clock as CacheClock, client, manager, cycle, job_body
    clock = CacheClock(); requests = []
    def handler(req):
        requests.append(req.url.path)
        return httpx.Response(200, json=dict(job_body(), id=req.url.path.split('/')[2], state='working'))
    api = client(handler, clock); m = manager(tmp_path, api, clock)
    calls = []; m._broker = recording_broker(clock, calls); m._due_at['control'] = 0
    m._land('standing', {'running': [dict(jobId=f'{index:08x}-0000-4000-8000-000000000000',
              since=f'2026-10-03T12:00:0{index}Z') for index in range(3)]}, clock())
    try:
        await cycle(m); assert len(requests) == 2
        before = len(gates(calls))
        for _ in range(20):
            m.update_control_flow({'mode': 'planned', 'plan': {'planId': '7f3a'}})
            await cycle(m)
        assert len(requests) == 2
        assert len(gates(calls)) == before + 1
    finally:
        await m.close(); await api.close()


async def test_busy_pause_arriving_during_ping_applies_to_same_gate_read(tmp_path):
    from tests.data.test_seat_round9_cache import client
    clock = Clock(); calls = []; pings = []
    api = client(lambda req: httpx.Response(200, json={}), clock)
    def ping(_):
        pings.append(True)
        if len(pings) == 2:
            api._pauses['seat'] = clock() + 60
        return {'ok': True, 'data': {}}
    def gate(args):
        calls.append(args)
        return {'ok': True, 'data': {'plane': {'mode': 'local-only'}}}
    broker = FakeBroker({'ping': ping, 'gate': gate, 'audit-tail': {'ok': True, 'data': {'lines': []}}})
    m = _manager(tmp_path, now=clock, api=api, broker=broker)
    try:
        await m._tier_control()
        assert calls == [{'offline': True}]
        assert m._control_block()['gate']['planeReason'] == 'busy'
        assert broker.offline is False
    finally:
        await m.close(); await api.close()
