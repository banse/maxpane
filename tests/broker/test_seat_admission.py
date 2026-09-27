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
    assert conn.response['detail'] == {'waited_s': 6, 'plan_spent': False, 'hint': 'plan remains available; retry promptly or use pepepane --offline'}
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
    assert conn.response['detail'] == {'waited_s': 21, 'plan_spent': True, 'hint': 'plan afresh; use pepepane --offline if plane reads are slow'}
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


@pytest.mark.parametrize("elapsed,timeout", [(5.5, False), (12, True)])
def test_apply_slow_standing_still_queues_restart_within_exec_budget(tmp_path, elapsed, timeout):
    from tests.broker._harness import standing_child
    broker, runner, *_ = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "restart")["plan"]
    def standing(argv, kw):
        mono.advance(elapsed)
        if timeout:
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        return standing_child(0, broker._now())
    runner.script[(broker._python, "-I", broker._broker_dir + "/gate.py")] = standing
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], "local_only_ack": "local-only"})
    assert result["ok"], result
    assert runner.argvs("systemctl", "restart") == [["systemctl", "restart", "--no-block", "imd-worker.service"]]
    assert mono() < 20


def test_systemctl_apply_deadline_fits_client_and_stop_waits_for_inactive(tmp_path):
    from imd_dashd.imd_dashd import APPLY_EXEC_DEADLINE_S, SYSTEMCTL_TIMEOUT_S
    from maxpane_dashboard.data.seat_broker_client import CLIENT_TIMEOUT_S
    from tests.broker._harness import msg
    assert APPLY_EXEC_DEADLINE_S + SYSTEMCTL_TIMEOUT_S + 2 <= CLIENT_TIMEOUT_S
    broker, runner, journal, clock, _ = make_broker(tmp_path)
    plan = call(broker, "stop")["plan"]
    assert call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["ok"]
    journal.add(msg(clock(), "shutting down"))
    runner.script[("systemctl", "is-active", "imd-worker.service")] = subprocess.CompletedProcess([], 3, b"deactivating\n", b"")
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is None
    runner.script[("systemctl", "is-active", "imd-worker.service")] = subprocess.CompletedProcess([], 3, b"inactive\n", b"")
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is True


@pytest.mark.parametrize("kind", ["bad_confirm", "local_only_ack_required", "systemctl_failure"])
def test_consumed_refusals_leave_terminal_verification(tmp_path, kind):
    broker, runner, *_ = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": True})["plan"]
    args = {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], "local_only_ack": "local-only"}
    if kind == "bad_confirm": args["confirm"] = "xxxx"
    if kind == "local_only_ack_required": args.pop("local_only_ack")
    if kind == "systemctl_failure": runner.script[("systemctl", "restart")] = subprocess.CompletedProcess([], 1, b"", b"")
    response = call(broker, "apply", args)
    assert not response["ok"]
    watch = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert watch["verified"] is False and response["error"] in watch["reason"]


def test_gate_reads_are_ordered_and_capped_to_remaining_execution_budget(tmp_path):
    from tests.broker._harness import msg, standing_child
    broker, runner, journal, *_ = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "restart")["plan"]
    seen = []
    def timed(argv, **kwargs):
        remaining = max(0.5, 15 - mono())
        assert kwargs["timeout"] <= remaining
        seen.append(argv)
        if "--standing" in argv:
            mono.advance(12)
            journal.add(msg(broker._now(), "accepted question deadbeef"))
            return standing_child(0, broker._now())
        return runner(argv, **kwargs)
    broker._run = timed
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert result["error"] == "gate_blocked"
    assert "--standing" in seen[0] and seen[1][0] == "ls" and seen[2][:2] == ["systemctl", "is-active"]
    assert "--grep" in seen[-1] and not runner.argvs("systemctl", "restart")
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is False


def test_slow_gate_and_queue_command_reply_before_client_timeout(tmp_path):
    from maxpane_dashboard.data.seat_broker_client import CLIENT_TIMEOUT_S
    broker, runner, *_ = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "restart")["plan"]
    def bounded(argv, **kwargs):
        if argv[:2] == ["systemctl", "restart"]:
            assert kwargs["timeout"] == 3 and "--no-block" in argv
            mono.advance(kwargs["timeout"])
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        mono.advance(min(2.5, kwargs["timeout"]))
        return runner(argv, **kwargs)
    broker._run = bounded
    conn = apply_conn(plan)
    with serving(broker) as incoming:
        incoming.put(conn)
        assert conn.done.wait(1)
    assert conn.response["error"] == "timeout"
    assert mono() < CLIENT_TIMEOUT_S
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is None


@pytest.mark.parametrize("verb,args", [("verify", None), ("gate", {}), ("audit-tail", {"n": 5}), ("orphans", {}), ("outbox", {})])
def test_slow_transient_read_does_not_block_root_or_worker_reads(tmp_path, verb, args):
    broker, runner, *_ = make_broker(tmp_path)
    plan = call(broker, "restart")["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    started, release = threading.Event(), threading.Event()
    def slow(argv, kw):
        started.set()
        assert release.wait(3)
        return subprocess.CompletedProcess(argv, 0, b"ok", b"")
    runner.script[("systemd-run",)] = slow
    conn = Conn(verb, args if args is not None else {"plan_id": plan["plan_id"]})
    with serving(broker) as incoming:
        incoming.put(Conn("status"))
        assert started.wait(1)
        try:
            incoming.put(conn)
            assert conn.done.wait(PING_TIMEOUT_S)
            assert conn.response["ok"]
        finally:
            release.set()


def test_serialized_read_set_pins_root_bypass_and_dynamic_projection(tmp_path):
    from imd_dashd import verbs
    broker, *_ = make_broker(tmp_path)
    bypass = set(verbs.READ_VERBS) & set(verbs.ROOT_VERBS)
    assert bypass == {"ping", "orphans", "gate", "verify", "audit-tail"}
    assert all(not broker._needs_read_lock(verb) for verb in bypass)
    assert all(not broker._needs_read_lock(verb) for verb in ("outbox", "work-stat", "hints-stat", "auth-mtime"))
    assert all(broker._needs_read_lock(verb) for verb in set(verbs.READ_VERBS) & set(verbs.TRANSIENT_VERBS))
    broker._seat = None
    assert broker._needs_read_lock("seat") and broker._needs_read_lock("gate")



def test_eof_check_is_immediate_for_live_timeout_socket_and_half_close():
    from imd_dashd.imd_dashd import connection_alive
    left, right = socket.socketpair()
    try:
        left.settimeout(5)
        result, done = [], threading.Event()
        def inspect():
            result.append(connection_alive(left))
            done.set()
        thread = threading.Thread(target=inspect)
        thread.start()
        assert done.wait(0.5), "MSG_PEEK must not inherit the five-second polling wait"
        thread.join()
        assert result == [True] and left.gettimeout() == 5
        right.sendall(b"x")
        assert connection_alive(left) and left.recv(1) == b"x"
        right.shutdown(socket.SHUT_WR)
        assert connection_alive(left) is False
        assert connection_alive(Conn("ping")) is True
    finally:
        left.close()
        right.close()


def test_serialized_read_queue_reserves_control_slots_and_reaps_abandoned_waiters(tmp_path):
    from imd_dashd.imd_dashd import MAX_CONNECTIONS, MAX_SERIALIZED_READS, connection_alive
    assert MAX_CONNECTIONS == 10 and MAX_SERIALIZED_READS == 4
    broker, runner, *_ = make_broker(tmp_path)
    plan = call(broker, "restart")["plan"]
    started, release = threading.Event(), threading.Event()
    entered = queue.Queue()
    gone = queue.Queue()
    original_handle = broker.handle
    def handle(request, **kwargs):
        if kwargs.get("_conn") is not None and isinstance(kwargs["_conn"], socket.socket):
            entered.put(kwargs["_conn"])
        return original_handle(request, **kwargs)
    broker.handle = handle
    def alive(conn):
        value = connection_alive(conn)
        if not value:
            gone.put(conn)
        return value
    broker._connection_alive = alive
    def slow(argv, kw):
        started.set()
        assert release.wait(4)
        return subprocess.CompletedProcess(argv, 0, b"ok", b"")
    runner.script[("systemd-run",)] = slow
    clients = []
    with serving(broker) as incoming:
        incoming.put(Conn("status"))
        assert started.wait(1)
        try:
            for _ in range(6):
                client, server = socket.socketpair()
                clients.append(client)
                client.sendall(b'{"v":1,"verb":"status","args":{}}\n')
                incoming.put(server)
                assert entered.get(timeout=1) is server
            # The first three wait; subsequent reads are refused promptly, while six slots remain for control.
            for client in clients[3:]:
                client.settimeout(1)
                response = json.loads(client.recv(65536))
                assert response["error"] == "busy" and response["detail"] == {"reason": "read queue full"}
            for client in clients:
                client.close()
            for _ in range(3):
                gone.get(timeout=1)
            for conn in (Conn("ping"), apply_conn(plan), Conn("verify", {"plan_id": plan["plan_id"]})):
                incoming.put(conn)
                assert conn.done.wait(PING_TIMEOUT_S) and conn.response["ok"]
            # The slow child remains blocked: no waiter is allowed to start another child after EOF.
            assert len(runner.argvs("systemd-run")) == 1
        finally:
            for client in clients: client.close()
            release.set()


def test_slow_sender_does_not_block_accept_loop(tmp_path):
    broker, *_ = make_broker(tmp_path)
    blocked, release = threading.Event(), threading.Event()
    def slow_send():
        blocked.set()
        assert release.wait(2)
    with serving(broker) as incoming:
        incoming.put(Conn("ping", before_read=slow_send))
        assert blocked.wait(1)
        try:
            ping = Conn("ping")
            incoming.put(ping)
            assert ping.done.wait(PING_TIMEOUT_S) and ping.response["ok"]
        finally:
            release.set()


def test_bounded_apply_does_not_retry_unresolved_seat_identity(tmp_path):
    broker, runner, *_ = make_broker(tmp_path)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "restart")["plan"]
    broker._seat = None
    broker._whoami_key = None
    def slow_identity(argv, kw):
        mono.advance(35)
        return subprocess.CompletedProcess(argv, 1, b"", b"")
    runner.script[("systemd-run",)] = slow_identity
    response = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], "local_only_ack": "local-only"})
    assert response["ok"] and response["result"]["preconditions"]["plane"]["mode"] == "local-only"
    assert not runner.argvs("systemd-run") and mono() < 20
