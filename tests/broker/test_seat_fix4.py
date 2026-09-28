"""Fourth-round regressions against scripted local sources, never a live worker."""
import json
import subprocess

import pytest

from imd_dashd import imd_dashd as root
from imd_dashd import gate
from tests.broker._harness import call, make_broker, msg
from tests.data.test_seat_broker_client import _local
from maxpane_dashboard.data.seat_broker_client import BrokerError
from maxpane_dashboard.data import seat_log_grammar as grammar
from maxpane_dashboard.data.seat_ledger import SeatLedger


ACCEPTS = [
    ("accepted review deadbeef —  (max 60 turns)", "accepted_code", "review", "code", 60),
    ("accepted implement deadbeef — src/", "accepted_code_head", "implement", "code", None),
    ("accepted tests deadbeef —", "accepted_code_head", "tests", "code", None),
    ("accepted review deadbeef — ", "accepted_code_head", "review", "code", None),
    ("accepted campaign deadbeef — harness", "accepted_fuzz_head", "campaign", "fuzz", None),
    ("accepted campaign deadbeef —", "accepted_fuzz_head", "campaign", "fuzz", None),
]


def apply(broker, plan, **extra):
    return call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], **extra})


@pytest.mark.parametrize("body,kind,role,task_kind,turns", ACCEPTS)
def test_all_accept_forms_open_the_ledger(tmp_path, body, kind, role, task_kind, turns):
    line = grammar.classify(msg(1790000000, body)[1])
    assert line.kind == kind
    if turns is not None:
        assert line.fields["paths"] == "" and line.fields["max_turns"] == str(turns)
    ledger = SeatLedger(tmp_path / "ledger.sqlite", seat=7, now=lambda: 1790000005)
    try:
        result = ledger.ingest([line])
        assert result.opened == 1
        row = ledger.open_row()
        assert row["nodeId8"] == "deadbeef" and row["role"] == role and row["kind"] == task_kind
        assert ledger.rows()[0]["maxTurns"] == turns
    finally:
        ledger.close()


@pytest.mark.parametrize("body,kind,role,task_kind,turns", ACCEPTS)
def test_root_accept_forms_block_and_matching_force_works(tmp_path, body, kind, role, task_kind, turns):
    broker, runner, journal, clock, _ = make_broker(tmp_path)
    plan = call(broker, "restart")["plan"]
    journal.add(msg(clock() - 5, body))
    answer = apply(broker, plan)
    assert answer["error"] == "gate_blocked"
    assert answer["detail"]["reason"] == "task running deadbeef · 0:05"
    assert answer["detail"]["preconditions"]["lifecycle_open"] is True
    assert not runner.argvs("systemctl", "restart")
    forced = call(broker, "restart", {"force_node8": "deadbeef"})["plan"]
    assert apply(broker, forced, force_node8="deadbeef")["ok"]
    assert runner.argvs("systemctl", "restart")


@pytest.mark.parametrize("body,kind,role,task_kind,turns", ACCEPTS)
def test_mac_accept_forms_block_apply(tmp_path, body, kind, role, task_kind, turns):
    broker, runner, lines, clock = _local(tmp_path)
    plan = broker.plan("restart")
    lines.append(msg(clock() - 5, body))
    with pytest.raises(BrokerError) as caught:
        broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")
    assert caught.value.code == "gate_blocked"
    assert caught.value.detail["reason"] == "task running deadbeef · 0:05"
    assert caught.value.detail["preconditions"]["lifecycle_open"] is True
    assert not runner.argvs("docker", "restart")


@pytest.mark.parametrize("body", [
    "accepted review deadbeef — src (max 60 turns) trailing",
    "accepted campaign deadbeef — harness (20 runs) trailing",
])
def test_completed_tail_with_trailing_prose_never_becomes_a_head(body):
    text = msg(1790000000, body)[1]
    assert grammar.classify(text).kind == grammar.KIND_UNKNOWN
    assert gate.newest_lifecycle([text]) == (None, None)


@pytest.mark.parametrize("byte_count,all_fields,expect_null", [(4087, False, False), (4088, False, True), (4100, True, False)])
def test_journal_fake_filters_full_message_before_systemd_size_limit(byte_count, all_fields, expect_null):
    from tests.broker._harness import Journal, NOW
    prefix = msg(NOW, "task failed: ")[1]
    # The boundary is UTF-8 bytes, not characters.
    text = prefix + "é" * ((byte_count - len(prefix.encode())) // 2)
    text += "x" * (byte_count - len(text.encode()))
    journal = Journal([(NOW, text)])
    argv = ["journalctl", "--grep", "task failed: .+", "--lines", "1"] + (["--all"] if all_fields else [])
    result = journal(argv, {})
    assert result.returncode == 0
    message = json.loads(result.stdout)["MESSAGE"]
    assert (message is None) is expect_null
    if not expect_null:
        assert message == text


@pytest.mark.parametrize("cursor", [None, "s=deadbeef;i=0"])
def test_follower_preserves_long_terminal_and_closes_ledger(tmp_path, cursor):
    from tests.broker._harness import Journal, NOW
    from tests.data.test_seat_tail import _Proc
    from maxpane_dashboard.data.seat_tail import JournaldSource
    accepted = msg(NOW - 10, "accepted implement deadbeef — src (max 60 turns)")
    terminal = msg(NOW - 1, "task failed: " + "z" * 4100)
    journal = Journal([accepted, terminal])
    def popen(argv, **kw):
        done = journal(argv, kw)
        return _Proc(done.stdout, done.returncode)
    source = JournaldSource(cursor=cursor, since="-600s", popen=popen)
    ledger = SeatLedger(tmp_path / "ledger.sqlite", seat=7, now=lambda: NOW)
    try:
        ledger.ingest([grammar.classify(accepted[1], cursor=Journal.cursor(0), invocation="inv0001")])
        source.open()
        parsed = [grammar.classify(raw.text, cursor=raw.cursor, invocation=raw.invocation)
                  for raw in source.lines() if raw is not None]
        ledger.ingest(parsed)
        assert ledger.open_row() is None
        assert ledger.state.last_lifecycle.kind == "local_fail"
        assert ledger.state.last_lifecycle.fields["msg"] == "z" * 4100
        # The same journal without --all demonstrates the actual loss, independent of argv assertions.
        argv = [arg for arg in source.argv() if arg != "--all"]
        hidden = journal(argv, {})
        decoded = [JournaldSource._parse_record(line) for line in hidden.stdout.decode().split("\n") if line]
        assert decoded[-1].text == ""
        no_all = SeatLedger(tmp_path / "without-all.sqlite", seat=7, now=lambda: NOW)
        try:
            no_all.ingest([grammar.classify(accepted[1])])
            no_all.ingest(grammar.classify(raw.text) for raw in decoded if raw is not None)
            assert no_all.open_row()["nodeId8"] == "deadbeef"
        finally:
            no_all.close()
    finally:
        source.close()
        ledger.close()


@pytest.mark.parametrize("state,shutdown,extended", [("active", False, False), (None, False, False), ("deactivating", False, True), ("active", True, True)])
def test_stop_extended_deadline_requires_teardown_evidence(state, shutdown, extended):
    watch = root.VerifyWatch("a" * 16, "stop", "stop", None, 100, stop_within_s=100)
    watch.update([msg(105, "shutting down")] if shutdown else [], 131, unit_state=state)
    assert watch.verified is (None if extended else False)
    if extended:
        watch.update([], 201, unit_state=state)
        assert watch.verified is False and "within 100 s" in watch.reason
    else:
        assert "within 30 s" in watch.reason


@pytest.mark.parametrize("forced,late,expected", [(True, 95, True), (True, 111, False), (False, 95, False)])
def test_restart_deadline_both_verdict_and_timeout_paths(tmp_path, forced, late, expected):
    broker, runner, journal, clock, _ = make_broker(tmp_path, script={
        ("systemctl", "show", "imd-worker.service", "-p", "KillMode"): (0, "KillMode=control-group\nTimeoutStopUSec=90s\n")})
    if forced:
        journal.add(msg(clock() - 5, "accepted implement deadbeef — src"))
    args = {"force_node8": "deadbeef"} if forced else {}
    plan = call(broker, "restart", args)["plan"]
    assert plan["verify"]["within_s"] == (110 if forced else 30)
    assert apply(broker, plan, **args)["ok"]
    start = clock()
    journal.add(msg(start + 20, "shutting down"))
    clock.advance(51)
    interim = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert interim["verified"] is (None if forced else False)
    clock.advance(late - 51)
    journal.add(msg(clock(), "runtimes: codex (using codex)"))
    broker.tick()
    result = call(broker, "verify", {"plan_id": plan["plan_id"]})
    assert result["ok"] and result["data"]["verified"] is expected


def test_forced_restart_without_runtimes_reaches_verdict_before_purge(tmp_path):
    broker, _, journal, clock, _ = make_broker(tmp_path, script={
        ("systemctl", "show", "imd-worker.service", "-p", "KillMode"): (0, "KillMode=control-group\nTimeoutStopUSec=90s\n")})
    journal.add(msg(clock() - 5, "accepted implement deadbeef — src"))
    plan = call(broker, "restart", {"force_node8": "deadbeef"})["plan"]
    assert apply(broker, plan, force_node8="deadbeef")["ok"]
    start = clock()
    journal.add(msg(start + 20, "shutting down"))
    clock.advance(109)
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is None
    clock.advance(2)
    broker.tick()
    answer = call(broker, "verify", {"plan_id": plan["plan_id"]})
    assert answer["ok"] and answer["data"]["verified"] is False
    assert "within 90 s" in answer["data"]["reason"]


@pytest.mark.parametrize("forced", [False, True])
def test_plans_refresh_stop_timeout_and_graceful_capability(tmp_path, forced):
    broker, runner, journal, clock, _ = make_broker(tmp_path)
    assert broker._stop_timeout_s == 30
    runner.script[("systemctl", "show", "imd-worker.service", "-p", "KillMode")] = (0, "KillMode=control-group\nTimeoutStopUSec=90s\n")
    if forced:
        journal.add(msg(clock() - 5, "accepted review deadbeef —"))
    verb, args = ("restart", {"force_node8": "deadbeef"}) if forced else ("stop", {})
    plan = call(broker, verb, args)["plan"]
    assert plan["verify"]["within_s"] == (110 if forced else 100)
    runner.script[("systemctl", "show", "imd-worker.service", "-p", "KillMode")] = (1, "")
    refused = call(broker, verb, args)
    assert broker._stop_timeout_s is None and broker.graceful_stop_possible is None
    if forced:
        assert not refused["ok"]
    else:
        assert refused["plan"]["verify"]["within_s"] == 110


@pytest.mark.parametrize("failure", ["signal", "breaker", "snapshot"])
def test_mac_kill_timeout_marks_unknown_only_after_signal_exec(tmp_path, failure):
    from tests.data.test_seat_broker_client import _container_procs
    broker, runner, _, clock = _local(tmp_path)
    plan = broker.plan("kill-orphans", {"pids": [412, 418]})
    if failure == "breaker":
        # Permit the snapshot seam so this exercises the signal's breaker path itself.
        broker._process_snapshot = _container_procs
        broker._breaker_until["kill-orphans"] = clock() + 100
    real = runner.script[("docker", "exec")]
    def execute(argv, kw):
        if (failure == "signal" and "kill" in argv) or (failure == "snapshot" and "--proc-snapshot" in argv):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        return real(argv, kw)
    runner.script[("docker", "exec")] = execute
    answer = broker._apply({"plan_id": plan.plan_id, "confirm": plan.plan_id[:4]})
    assert answer["error"] == "timeout" and answer["detail"]["partial"] is False
    detail = answer["detail"]
    signals = [argv for argv in runner.argvs("docker", "exec") if "kill" in argv]
    if failure == "signal":
        assert len(signals) == 1
        assert detail["outcome"] == "timeout" and detail["reason"] == "orphan signal command timed out"
    else:
        assert not signals and "outcome" not in detail


@pytest.mark.parametrize("mac", [False, True])
def test_drain_refusals_share_flat_plan_and_apply_shape(tmp_path, mac):
    if mac:
        broker, _, _, _ = _local(tmp_path)
        first, second = broker.plan("drain-restart"), broker.plan("drain-restart")
        broker.apply(first.plan_id, first.plan_id[:4])
        plan_reply = broker._plan("drain-restart", {})
        apply_reply = broker._apply({"plan_id": second.plan_id, "confirm": second.plan_id[:4]})
    else:
        broker, _, _, _, _ = make_broker(tmp_path)
        first, second = call(broker, "drain-restart")["plan"], call(broker, "drain-restart")["plan"]
        apply(broker, first)
        plan_reply = call(broker, "drain-restart")
        apply_reply = apply(broker, second)
    expected = {**broker._drain.armed.to_dict(), "hint": "cancel-drain before arming another drain"}
    assert plan_reply["error"] == apply_reply["error"] == "drain_already_armed"
    assert plan_reply["detail"] == apply_reply["detail"] == expected
