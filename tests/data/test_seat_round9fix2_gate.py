"""Gate recovery deadlines, using fixture brokers and an injected clock only."""

import asyncio
import threading

import pytest

from maxpane_dashboard.data.seat_broker_client import BrokerError, FakeBroker
from tests.data.test_seat_manager import Clock, _manager


def gate_broker(clock, calls, answer):
    def read(args):
        calls.append((clock(), args))
        return answer(args)
    return FakeBroker({'gate': read, 'audit-tail': {'lines': []}})


def good_gate(args):
    return {'safe': True, 'plane': {'mode': 'local-only' if args['offline'] else 'plane+local'}}


@pytest.mark.parametrize('failure', ['exception', 'nonmapping'])
@pytest.mark.parametrize('slow', [0, 12, 75])
async def test_failed_gate_retries_five_seconds_after_failure(tmp_path, failure, slow):
    clock = Clock(); calls = []; first = [True]
    def answer(args):
        if first[0]:
            first[0] = False
            clock.advance(slow)
            if failure == 'exception':
                raise BrokerError('transport')
            return []
        return good_gate(args)
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, answer), offline=True)
    m.select_dashboard('LIVE')
    try:
        await m._tier_control()
        failed_at = clock()
        assert m._gate_due_at == failed_at + 5
        for elapsed in (0, 1, 3.99):
            clock.now = failed_at + elapsed
            await m._tier_control()
            assert len(calls) == 1
        clock.now = failed_at + 5
        await m._tier_control()
        assert len(calls) == 2
    finally:
        await m.close()


async def test_active_flow_failure_uses_its_shorter_poll_interval(tmp_path):
    clock = Clock(); calls = []
    def answer(_):
        clock.advance(10)
        raise RuntimeError('fixture read failed')
    m = _manager(tmp_path, now=clock, poll_interval=3,
                 broker=gate_broker(clock, calls, answer), offline=True)
    try:
        m.update_control_flow({'mode': 'planned', 'plan': {'planId': 'fixture'}})
        await m._tier_control()
        assert m._gate_due_at == clock() + 3
        clock.advance(2.99); await m._tier_control(); assert len(calls) == 1
        clock.advance(.01); await m._tier_control(); assert len(calls) == 2
    finally:
        await m.close()


@pytest.mark.parametrize('reply', ['success', 'plane_unavailable', 'broker_busy'])
async def test_success_or_broker_busy_keeps_normal_live_cadence(tmp_path, reply):
    clock = Clock(); calls = []
    def answer(args):
        if reply == 'broker_busy':
            raise BrokerError('busy')
        if reply == 'plane_unavailable':
            return {'safe': False, 'plane': {'mode': 'plane-unavailable', 'running': None}}
        return good_gate(args)
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, answer))
    m.select_dashboard('LIVE')
    try:
        start = clock()
        await m._tier_control()
        for elapsed in (5, 15, 59.99):
            clock.now = start + elapsed
            await m._tier_control()
            assert len(calls) == 1
        clock.now = start + 60
        await m._tier_control()
        assert len(calls) == 2
        if reply == 'plane_unavailable':
            assert m._control_block()['gate']['planeMode'] == 'plane-unavailable'
    finally:
        await m.close()


async def test_unreachable_broker_does_not_consume_gate_deadline(tmp_path):
    clock = Clock(); broker = FakeBroker(reachable=False)
    m = _manager(tmp_path, now=clock, broker=broker)
    try:
        m._gate_due_at = clock() - 1
        due = m._gate_due_at
        await m._tier_control()
        assert m._gate_due_at == due and m._gate_last_read_at is None
        assert not any(verb == 'gate' for verb, _ in broker.calls)
    finally:
        await m.close()


@pytest.mark.parametrize('trigger', ['phase', 'event'])
async def test_failed_gate_preserves_deadline_arriving_inflight(tmp_path, trigger):
    clock = Clock(); calls = []; entered = threading.Event(); release = threading.Event()
    def answer(args):
        if len(calls) == 1:
            entered.set()
            assert release.wait(10), 'fixture read was not released'
            raise BrokerError('transport')
        return good_gate(args)
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, answer), offline=True)
    task = asyncio.create_task(m._tier_control())
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        if trigger == 'phase':
            m.update_control_flow({'mode': 'planned', 'plan': {'planId': 'fixture'}})
        else:
            clock.advance(1); m._apply_bumps(['accepted']); clock.advance(5)
        deadline = m._gate_due_at
        release.set(); await task
        assert m._gate_due_at == deadline
        await m._tier_control()
        assert len(calls) == 2
    finally:
        release.set(); await task; await m.close()


async def test_busy_gate_reads_at_pause_end_and_each_extension(tmp_path):
    clock = Clock(start=30); calls = []
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, good_gate))
    m.select_dashboard('LIVE')
    try:
        m._api._pauses['seat'] = 40
        await m._tier_control()
        assert m._gate_due_at == 40
        assert m._control_block()['gate']['planeReason'] == 'busy'
        clock.now = 39.99; await m._tier_control(); assert len(calls) == 1
        m._api._pauses['seat'] = 55
        clock.now = 40; await m._tier_control()
        assert len(calls) == 2 and m._gate_due_at == 55
        clock.now = 54.99; await m._tier_control(); assert len(calls) == 2
        clock.now = 55; await m._tier_control()
        assert len(calls) == 3 and m._gate_due_at == 115
        assert [args['offline'] for _, args in calls] == [True, True, False]
        assert m._control_block()['gate']['planeReason'] is None
        for elapsed in (1, 5, 59):
            clock.now = 55 + elapsed
            await m._tier_control()
            assert len(calls) == 3
    finally:
        await m.close()


async def test_busy_gate_landing_uses_current_extended_pause(tmp_path):
    clock = Clock(start=30); calls = []
    def answer(args):
        m._api._pauses['seat'] = 50
        return good_gate(args)
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, answer))
    try:
        m._api._pauses['seat'] = 40
        await m._tier_control()
        assert m._gate_due_at == 50
    finally:
        await m.close()


async def test_busy_gate_landing_after_pause_expired_refreshes_next_cycle(tmp_path):
    clock = Clock(start=30); calls = []
    def answer(args):
        if len(calls) == 1:
            clock.advance(15)
        return good_gate(args)
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, answer))
    try:
        m._api._pauses['seat'] = 40
        await m._tier_control()
        assert clock() == 45 and m._gate_due_at == 40
        await m._tier_control()
        assert [args['offline'] for _, args in calls] == [True, False]
        assert m._control_block()['gate']['planeReason'] is None
    finally:
        await m.close()


async def test_failed_pause_recovery_waits_five_seconds_despite_last_good_busy(tmp_path):
    clock = Clock(start=30); calls = []
    def answer(args):
        if len(calls) == 2:
            raise BrokerError('transport')
        return good_gate(args)
    m = _manager(tmp_path, now=clock, broker=gate_broker(clock, calls, answer))
    m.select_dashboard('LIVE')
    try:
        m._api._pauses['seat'] = 40
        await m._tier_control()
        clock.now = 40; await m._tier_control()
        assert len(calls) == 2 and m._gate_due_at == 45
        assert m._control_block()['gate']['planeReason'] == 'busy'
        for at in (40, 41, 44.99):
            clock.now = at; await m._tier_control(); assert len(calls) == 2
        clock.now = 45; await m._tier_control()
        assert len(calls) == 3
        assert m._control_block()['gate']['planeReason'] is None
    finally:
        await m.close()
