"""Real serve-loop admission under blocked readers, driven by events and a monotonic clock."""
import json
import queue
import socket
import subprocess
import threading
from contextlib import contextmanager

import pytest

from tests.broker._harness import Clock, call, hb, make_broker
from maxpane_dashboard.data.seat_broker_client import PING_TIMEOUT_S


class Conn:
    def __init__(self, verb, args=None, before_read=lambda: None):
        self.raw = json.dumps({'v': 1, 'verb': verb, 'args': args or {}}).encode() + b'\n'
        self.before_read = before_read
        self.done = threading.Event()
        self.response = None
    def settimeout(self, value): pass
    def recv(self, limit):
        self.before_read()
        raw, self.raw = self.raw, b''
        return raw
    def sendall(self, raw):
        self.response = json.loads(raw)
        self.done.set()
    def close(self): pass


@contextmanager
def serving(broker):
    incoming = queue.Queue()
    class Listener:
        def settimeout(self, value): pass
        def accept(self):
            item = incoming.get(timeout=4)
            if item == 'tick': raise socket.timeout()
            if item is None: raise OSError('finished')
            return item, None
    thread = threading.Thread(target=broker.serve_forever, args=(Listener(),))
    thread.start()
    try:
        yield incoming
    finally:
        incoming.put(None)
        thread.join(4)
        assert not thread.is_alive()


def apply_conn(plan, **kwargs):
    return Conn('apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4], 'local_only_ack': 'local-only'}, **kwargs)


@pytest.mark.parametrize('next_verb', ['apply', 'ping'])
def test_slow_read_does_not_queue_apply_or_ping(tmp_path, next_verb):
    broker, runner, *_ = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, 'restart', {'offline': True})['plan']
    started, release = threading.Event(), threading.Event()
    def slow(argv, kw):
        started.set()
        assert release.wait(3)
        return subprocess.CompletedProcess(argv, 0, b'ok', b'')
    runner.script[('systemd-run',)] = slow
    next_conn = apply_conn(plan) if next_verb == 'apply' else Conn('ping')
    with serving(broker) as incoming:
        incoming.put(Conn('status'))
        assert started.wait(1)
        try:
            incoming.put(next_conn)
            assert next_conn.done.wait(PING_TIMEOUT_S), 'slow read must not queue another request'
            assert next_conn.response['ok']
        finally:
            release.set()
    assert mono() < 5


def test_apply_accept_deadline_precedes_plan_consumption(tmp_path):
    broker, runner, _journal, _clock, audit = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, 'restart', {'offline': True})['plan']
    conn = apply_conn(plan, before_read=lambda: mono.advance(6))
    with serving(broker) as incoming:
        incoming.put(conn)
        assert conn.done.wait(1)
    assert conn.response['error'] == 'apply_late'
    assert conn.response['detail'] == {'waited_s': 6, 'plan_spent': False}
    assert not broker._plans.peek(plan['plan_id']).spent
    assert not runner.argvs('systemctl', 'restart')
    assert 'apply_late' in audit.path.read_text()


def test_slow_gate_inside_apply_cannot_mutate_after_client_timeout(tmp_path):
    broker, runner, journal, _clock, audit = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, 'restart', {'offline': True})['plan']
    def slow(argv, kw):
        if '--grep' in argv:
            mono.advance(21)
        return journal(argv, kw)
    runner.script[('journalctl',)] = slow
    conn = apply_conn(plan)
    with serving(broker) as incoming:
        incoming.put(conn)
        assert conn.done.wait(1)
    assert conn.response['error'] == 'apply_late'
    assert conn.response['detail'] == {'waited_s': 21, 'plan_spent': True}
    assert broker._plans.peek(plan['plan_id']).spent
    assert not runner.argvs('systemctl', 'restart')
    assert 'apply_late' in audit.path.read_text()


def test_armed_drain_tick_does_not_block_ping(tmp_path):
    broker, runner, journal, clock, _audit = make_broker(tmp_path)
    plan = call(broker, 'drain-restart', {'offline': True})['plan']
    assert call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})['ok']
    clock.advance(31)
    started, release = threading.Event(), threading.Event()
    def slow(argv, kw):
        started.set()
        assert release.wait(3)
        return journal(argv, kw)
    runner.script[('journalctl',)] = slow
    conn = Conn('ping')
    with serving(broker) as incoming:
        incoming.put('tick')
        assert started.wait(1)
        try:
            incoming.put(conn)
            assert conn.done.wait(PING_TIMEOUT_S), 'housekeeping must not delay ping'
            assert conn.response['ok']
        finally:
            release.set()


def test_transient_worker_rechecks_deadline_at_actual_start(tmp_path, monkeypatch):
    from imd_dashd import imd_dashd as mod
    broker, runner, *_ = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "doctor")["plan"]
    original = threading.Thread
    def delayed_thread(*args, **kwargs):
        if kwargs.get("name", "").startswith("imd-dashd-doctor-"):
            target = kwargs["target"]
            def delayed():
                mono.advance(6)
                target()
            kwargs["target"] = delayed
        return original(*args, **kwargs)
    monkeypatch.setattr(mod.threading, "Thread", delayed_thread)
    conn = apply_conn(plan)
    with serving(broker) as incoming:
        incoming.put(conn)
        assert conn.done.wait(1)
    broker._threads[plan["plan_id"]].join(1)
    verify = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert verify["verified"] is False and "apply_late" in verify["reason"]
    assert '"plan_spent": true' in verify["reason"]
    assert not runner.argvs("systemd-run") and not broker._lock.locked()


@pytest.mark.parametrize("group", [False, True])
def test_orphan_signal_rechecks_deadline_after_process_snapshot(tmp_path, monkeypatch, group):
    from imd_dashd import imd_dashd as mod
    from tests.broker.test_imd_dashd import _orphan_broker
    from tests.broker._harness import write_fake_proc
    broker, runner, _clock, _audit, spec = _orphan_broker(tmp_path)
    if group:
        spec["procs"] = [p for p in spec["procs"] if p["pid"] != 64861]
        for proc in spec["procs"]:
            if proc["pgid"] == 64861:
                proc["pgid"] = 64862
        write_fake_proc(tmp_path / "proc", spec)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "kill-orphans", {"pids": [64885]})["plan"]
    assert set(plan["preconditions"]["kill_mode_by_pgid"].values()) == {"group" if group else "individual"}
    original = mod.signal_procs
    def slow(*args, **kwargs):
        rows = original(*args, **kwargs)
        mono.advance(6)
        return rows
    monkeypatch.setattr(mod, "signal_procs", slow)
    conn = apply_conn(plan)
    with serving(broker) as incoming:
        incoming.put(conn)
        assert conn.done.wait(1)
    assert conn.response["error"] == "apply_late"
    assert conn.response["detail"]["plan_spent"] is True
    assert conn.response["detail"]["partial"] is False
    assert conn.response["detail"]["killed"] == []
    assert not runner.argvs("kill")


def test_children_never_execute_under_state_lock(tmp_path):
    broker, runner, *_ = make_broker(tmp_path)
    calls = []
    def checked(argv, **kwargs):
        assert not broker._state_lock._is_owned(), argv
        calls.append(argv)
        return runner(argv, **kwargs)
    broker._run = checked
    for verb in ("status", "skills", "sessions", "whoami", "gate"):
        args = {"since": 0, "runtime": "codex"} if verb == "sessions" else {}
        call(broker, verb, args)
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    broker.tick()
    assert calls


@pytest.mark.parametrize("entry", ["accept", "dispatch"])
def test_in_flight_snapshot_survives_concurrent_finisher(tmp_path, entry):
    import dis
    import sys
    from imd_dashd.imd_dashd import Broker
    broker, *_ = make_broker(tmp_path)
    broker._in_flight = {"verb": "doctor", "plan_id": "a" * 16, "since": "2026-09-27T00:00:00Z"}
    release, cleared = threading.Event(), threading.Event()
    def finish_write():
        assert release.wait(2)
        broker._in_flight = None
        cleared.set()
    finisher = threading.Thread(target=finish_write)
    code = Broker._in_flight_detail.__code__
    reads = [i.offset for i in dis.get_instructions(code) if i.opname == "LOAD_ATTR" and i.argval == "_in_flight"]
    def trace(frame, event, _arg):
        if frame.f_code is code:
            frame.f_trace_opcodes = True
            if event == "opcode" and frame.f_lasti == reads[-1]:
                release.set()
                assert cleared.wait(2)
        return trace
    previous = sys.gettrace()
    finisher.start()
    try:
        sys.settrace(trace)
        if entry == "dispatch":
            assert call(broker, "ping")["ok"]
        else:
            conn = Conn("ping")
            class Listener:
                sent = False
                def settimeout(self, _value): pass
                def accept(self):
                    if self.sent: raise OSError("finished")
                    self.sent = True
                    return conn, None
            broker.serve_forever(Listener())
            assert conn.response["ok"]
    finally:
        sys.settrace(previous)
        release.set()
        finisher.join(2)
        assert not finisher.is_alive()
