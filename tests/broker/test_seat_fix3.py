"""Third-round regressions use scripted local sources only."""
import json
import subprocess

import pytest

from imd_dashd import imd_dashd as root
from tests.broker._harness import Clock, Journal, audit_lines, call, hb, make_broker, msg, standing_child
from tests.data.test_seat_broker_client import _local


def apply(broker, plan, **extra):
    return call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], **extra})


@pytest.mark.parametrize("drain", [False, True])
def test_root_plane_age_is_fixed_at_standing_completion(tmp_path, drain):
    broker, runner, journal, clock, audit = make_broker(tmp_path)
    broker._monotonic = clock
    def slow_journal(argv, kw):
        clock.advance(1.1 if "--grep" in argv else 1.0)
        return journal(argv, kw)
    runner.script[("journalctl",)] = slow_journal
    plan = call(broker, "drain-restart" if drain else "restart")["plan"]
    assert plan["preconditions"]["plane"]["mode"] == "plane+local"
    assert plan["preconditions"]["plane"]["standing_age_s"] == 0.4
    assert apply(broker, plan)["ok"]
    if drain:
        for offset in (1, 2, 3, 4): journal.add(hb(clock() + offset))
        clock.advance(5)
        broker.tick()
    assert runner.argvs("systemctl", "restart")
    applied = [r for r in audit_lines(audit) if r["phase"] == "apply"][-1]
    assert applied["preconditions"]["plane"]["standing_age_s"] == 0.4
    assert applied["preconditions"]["newest_heartbeat_age_s"] >= 2.1


@pytest.mark.parametrize("drain", [False, True])
def test_mac_slow_outbox_preserves_fresh_plane_read(tmp_path, drain):
    broker, runner, lines, clock = _local(tmp_path, offline=False)
    broker._standing = lambda: {"running_count": 0, "at": root.iso_utc(clock())}
    def outbox():
        clock.advance(3)
        return 0
    broker._outbox_files = outbox
    plan = broker.plan("drain-restart" if drain else "restart")
    assert plan.preconditions["plane"]["mode"] == "plane+local"
    assert plan.preconditions["plane"]["standing_age_s"] == 0
    assert broker.apply(plan.plan_id, plan.plan_id[:4]).outcome in ("armed", "applied")
    if drain:
        for _ in range(4):
            clock.advance(30)
            lines.append(hb(clock() - 1))
            broker.tick()
    assert runner.argvs("docker", "restart")


def test_mac_accept_after_standing_is_seen_before_apply(tmp_path):
    from maxpane_dashboard.data.seat_broker_client import BrokerError
    broker, runner, lines, clock = _local(tmp_path, offline=False)
    armed = [False]
    def standing():
        armed[0] = True
        return {"running_count": 0, "at": root.iso_utc(clock())}
    broker._standing = standing
    plan = broker.plan("restart")
    broker._injected_tail = None
    armed[0] = False
    def tail(argv, kw):
        newest = lines + ([msg(clock() - 1, "accepted question deadbeef")] if armed[0] else [])
        return subprocess.CompletedProcess(argv, 0, "\n".join("2026-09-26T00:00:00Z " + text for _, text in newest).encode(), b"")
    runner.script[("docker", "logs")] = tail
    with pytest.raises(BrokerError) as exc:
        broker.apply(plan.plan_id, plan.plan_id[:4])
    assert exc.value.code == "gate_blocked" and "task running" in exc.value.detail["reason"]
    assert not runner.argvs("docker", "restart")


OBJECTIVES = ["\u200b", "\u202e", "fix\u2028the parser", "fix\x85parser", "fix\x1cparser", "a\x0bb", "fix the parser", "\x07"]


@pytest.mark.parametrize("objective", OBJECTIVES)
def test_raw_root_lifecycle_blocks_apply_drain_and_redacts_output(tmp_path, objective):
    from imd_dashd.redact import redact
    broker, runner, journal, clock, _ = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": True})["plan"]
    drain = call(broker, "drain-restart", {"offline": True})["plan"]
    accepted = msg(clock() - 5, f"accepted implement 0c1f9727 — {objective} (max 40 turns)")
    journal.add(accepted)
    original = journal
    def read(argv, kw):
        done = original(argv, kw)
        if objective == "\x07" and "--grep" in argv:
            done.stdout = json.dumps({"MESSAGE": list(accepted[1].encode()), "__REALTIME_TIMESTAMP": str(int(accepted[0]*1e6))}).encode()
        return done
    runner.script[("journalctl",)] = read
    response = apply(broker, plan, local_only_ack="local-only")
    assert response["error"] == "gate_blocked"
    assert response["detail"]["preconditions"]["last_lifecycle_line"] == redact(accepted[1])
    assert call(broker, "gate", {"offline": True})["data"]["last_lifecycle_line"] == redact(accepted[1])
    preview = call(broker, "restart", {"offline": True, "force_node8": "0c1f9727"})["plan"]
    assert preview["preconditions"]["last_lifecycle_line"] == redact(accepted[1])
    assert apply(broker, drain)["ok"]
    for i in (1, 2, 3, 4): journal.add(hb(clock() + i))
    clock.advance(5)
    broker.tick()
    assert not runner.argvs("systemctl", "restart")
    assert broker._drain.armed is not None
    broker._drain.cancel()
    if objective == "\u200b":
        assert apply(broker, preview, force_node8="0c1f9727")["ok"]
        assert runner.argvs("systemctl", "restart")


@pytest.mark.parametrize("objective", OBJECTIVES[:-1])
def test_raw_mac_lifecycle_blocks_apply_and_drain(tmp_path, objective):
    from imd_dashd.redact import redact
    from maxpane_dashboard.data.seat_broker_client import BrokerError
    broker, runner, lines, clock = _local(tmp_path)
    plan = broker.plan("restart")
    drain = broker.plan("drain-restart")
    accepted = msg(clock() - 5, f"accepted implement 0c1f9727 — {objective} (max 40 turns)")
    lines.append(accepted)
    broker._injected_tail = None
    def logs(argv, kw):
        return subprocess.CompletedProcess(argv, 0, "\n".join("2026-09-26T00:00:00Z " + text for _, text in lines).encode(), b"")
    runner.script[("docker", "logs")] = logs
    gate = broker._gate()
    assert gate.lifecycle_open is True and "task running" in gate.reason
    assert broker.read("gate")["last_lifecycle_line"] == redact(accepted[1])
    with pytest.raises(BrokerError) as exc:
        broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")
    assert exc.value.code == "gate_blocked"
    assert broker.apply(drain.plan_id, drain.plan_id[:4]).outcome == "armed"
    for _ in range(4):
        clock.advance(30)
        lines.append(hb(clock() - 1))
        broker.tick()
    assert broker._drain.armed is not None and not runner.argvs("docker", "restart")


@pytest.mark.parametrize("rc,out,err,ok", [
    (1, b"", b"", True), (1, b"-- No entries --\n", b"", True),
    (1, b"-- cursor: s=0;i=1;b=0;m=0;t=0;x=0\n", b"", True),
    (1, b"-- cursor: x\n", b"warning", False), (2, b"", b"", False),
    (1, '{"MESSAGE":"x"}\n-- cursor: …\n'.encode(), b"", False),
    (0, b'{"MESSAGE":"x"}\n', b"warning", False),
    (0, b"", b"", False), (0, b"-- cursor: x\n", b"", False), (0, b"-- No entries --\n", b"", False),
    (0, b'{"MESSAGE":[255]}\n', b"", False),
    (0, '{"MESSAGE":"fix\u2028the parser"}\r\n'.encode(), b"", True),
    (0, b'{"MESSAGE":[65,7,66]}\n', b"", True),
])
def test_lifecycle_outcome_direct_table(rc, out, err, ok):
    records, succeeded = root.lifecycle_read_outcome(rc, out, err)
    assert succeeded is ok
    assert bool(records) is (ok and rc == 0)


def test_lifecycle_query_preserves_long_fields_before_filter():
    argv = root.lifecycle_journal_argv()
    assert argv.index("--all") < argv.index("--grep")


def test_lifecycle_unclassifiable_records_fail_closed(tmp_path):
    broker, runner, journal, _, _ = make_broker(tmp_path)
    def read(argv, kw):
        if "--grep" in argv:
            return subprocess.CompletedProcess(argv, 0, b'{"MESSAGE":"not a lifecycle"}\n', b"")
        return journal(argv, kw)
    runner.script[("journalctl",)] = read
    assert call(broker, "restart", {"offline": True})["error"] == "gate_unknown(lifecycle)"


def test_window_replaces_bad_heartbeat_byte_but_lifecycle_stays_strict(tmp_path):
    broker, runner, journal, clock, _ = make_broker(tmp_path)
    badbeat = hb(clock() - 2)[1] + " · paused until 23:53 after 3 failed runs: "
    records = [{"MESSAGE": text, "__REALTIME_TIMESTAMP": str(int(epoch*1e6))} for epoch, text in journal.lines]
    records.append({"MESSAGE": list(badbeat.encode()) + [255] + list(" — run imd doctor".encode()), "__REALTIME_TIMESTAMP": str(int((clock()-2)*1e6))})
    window = "\n".join(json.dumps(row) for row in records).encode()
    def read(argv, kw):
        if "--grep" in argv:
            line = msg(clock()-1, "accepted implement 0c1f9727 — ")[1]
            payload = {"MESSAGE": list(line.encode()) + [255] + list(b" (max 40 turns)")}
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload).encode(), b"")
        return subprocess.CompletedProcess(argv, 0, window, b"")
    runner.script[("journalctl",)] = read
    lines, _, succeeded = broker._journal_read()
    assert succeeded and "\ufffd" in lines[-1][1]
    gate, _, _ = broker._gate(offline=True)
    assert gate.idle_beats >= 4 and gate.unknown == "lifecycle"


def test_long_terminal_is_classified(tmp_path):
    broker, _, journal, clock, _ = make_broker(tmp_path)
    journal.add(msg(clock()-1, "task failed: " + "a" * 4100))
    gate, _, _ = broker._gate(offline=True)
    assert gate.safe and gate.lifecycle_open is False


def test_root_literal_unicode_separator_fixture_is_one_record(tmp_path):
    from pathlib import Path
    payload = Path('tests/fixtures/seat/logs/unicode-lifecycle-root.jsonl').read_bytes()
    broker, runner, *_ = make_broker(tmp_path)
    runner.script[("journalctl",)] = subprocess.CompletedProcess([], 0, payload, b"")
    lines, _, succeeded = broker._journal_read(lifecycle_only=True)
    assert succeeded and len(lines) == 1 and "fix\u2028the parser" in lines[0][1]
    assert root.ACCEPTED_RE.match(lines[0][1])


def test_second_drain_apply_cannot_change_original_online_gate(tmp_path):
    broker, runner, journal, clock, audit = make_broker(tmp_path)
    online = call(broker, "drain-restart")["plan"]
    offline = call(broker, "drain-restart", {"offline": True})["plan"]
    assert apply(broker, online)["ok"]
    refused = apply(broker, offline)
    assert refused["error"] == "drain_already_armed"
    assert "cancel-drain" in refused["detail"]["hint"]
    assert broker._drain_offline is False and broker._drain.armed.plan_id == online["plan_id"]
    assert audit_lines(audit)[-1]["plan_id"] == offline["plan_id"]
    assert call(broker, "verify", {"plan_id": offline["plan_id"]})["data"]["verified"] is False
    broker._standing = lambda *args: None
    for i in (1, 2, 3, 4): journal.add(hb(clock()+i))
    clock.advance(5)
    broker.tick()
    assert not runner.argvs("systemctl", "restart") and broker._drain.armed.plan_id == online["plan_id"]


@pytest.mark.parametrize("mac", [False, True])
def test_consumed_unexpected_exception_completes_watch_and_audits_id(tmp_path, mac):
    if mac:
        broker, runner, _, _ = _local(tmp_path)
        plan = broker.plan("restart")
        plan_id = plan.plan_id
        broker._gate = lambda: (_ for _ in ()).throw(RuntimeError("synthetic"))
        result = broker._apply({"plan_id": plan_id, "confirm": plan_id[:4], "local_only_ack": "local-only"})
        watch = broker.verify(plan_id)
        assert watch.verified is False and "RuntimeError" in watch.reason
        records = broker.read("audit-tail", {"n": 50})["lines"]
    else:
        broker, _, _, _, audit = make_broker(tmp_path)
        plan = call(broker, "restart")["plan"]
        plan_id = plan["plan_id"]
        broker._dispatch_apply = lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic"))
        result = apply(broker, plan)
        watch = call(broker, "verify", {"plan_id": plan_id})["data"]
        assert watch["verified"] is False and "RuntimeError" in watch["reason"]
        records = audit_lines(audit)
    assert result["error"] == "internal"
    assert any(r["plan_id"] == plan_id and r["phase"] == "refused" and r["outcome"] == "internal: RuntimeError" for r in records)


@pytest.mark.parametrize("failure", ["snapshot", "signal"])
def test_mac_partial_kill_retains_completed_targets_and_audit(tmp_path, failure):
    from maxpane_dashboard.data.seat_broker_client import BrokerError
    from tests.data.test_seat_broker_client import _container_procs
    broker, runner, _, _ = _local(tmp_path)
    rows = _container_procs()
    rows += [dict(rows[1], pid=512, pgid=512, start_ticks=51200)]
    broker._process_snapshot = lambda: rows
    original_read = broker._read
    broker._read = lambda verb, args: {"candidates": rows[1:]} if verb == "orphans" else original_read(verb, args)
    plan = broker.plan("kill-orphans", {"pids": [412, 418, 512]})
    original_exec = broker._exec
    kills = []
    def execute(argv, **kw):
        if argv[0] == "kill":
            kills.append(argv)
            if failure == "signal" and len(kills) == 2:
                raise BrokerError("timeout", {"reason": "synthetic signal timeout"})
        return original_exec(argv, **kw)
    broker._exec = execute
    def snapshot():
        if failure == "snapshot" and kills:
            raise BrokerError("unreadable", {"what": "process snapshot"})
        return rows
    broker._process_snapshot = snapshot
    result = broker._apply({"plan_id": plan.plan_id, "confirm": plan.plan_id[:4]})
    assert not result["ok"] and result["detail"]["partial"] is True
    assert result["detail"]["killed"] == [{"mode": "group", "pgid": 412, "pids": [412, 418]}]
    assert result["detail"]["skipped"][0]["pid"] == 512
    watch = broker._watches[plan.plan_id]
    assert watch.targets == [("pgid", 412)] and watch.verified is None
    assert broker._pending_kills[0][1:] == ("pgid", 412)
    assert any(r["plan_id"] == plan.plan_id and r["outcome"] == "partial" for r in broker.read("audit-tail", {"n": 50})["lines"])
