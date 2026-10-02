"""Install-day privilege failures: no host access, injected status and child runners."""
from __future__ import annotations

import pytest

from imd_dashd import imd_dashd as broker_mod
from imd_dashd import verbs
from tests.broker._harness import audit_lines, call, hb, make_broker


@pytest.mark.parametrize("caps,expected", [("00000000000000ef", True), ("c0", True),
                                            ("6f", False), ("80", False), ("0", False)])
def test_ping_reports_effective_uid_and_gid_capabilities(tmp_path, caps, expected):
    reads = []
    def status():
        reads.append(True)
        return f"Name:\tpython3\nCapPrm:\tffffffff\nCapEff:\t{caps}\nCapBnd:\tffffffff\n"
    broker, *_ = make_broker(tmp_path, status_reader=status)
    assert call(broker, "ping")["data"]["drop_ok"] is expected
    assert reads == [True]


@pytest.mark.parametrize("status", [None, "Name:\tpython3\n", "CapEff:\tnot-hex\n"])
def test_unknown_drop_status_is_diagnostic_and_kernel_still_decides(tmp_path, status):
    def read_status():
        if status is None:
            raise FileNotFoundError("/proc/self/status")
        return status
    broker, runner, *_ = make_broker(tmp_path, status_reader=read_status)
    assert call(broker, "ping")["data"]["drop_ok"] is None
    assert call(broker, "outbox")["data"] == {"files": 0}
    assert runner.argvs("ls", "-1A")


@pytest.mark.parametrize("verb,args", [("seat", {}), ("outbox", {}), ("work-stat", {}),
    ("hints-stat", {}), ("auth-mtime", {}), ("gate", {"offline": False}), ("gate", {"offline": True}),
    ("restart", {"offline": True}), ("stop", {"offline": False}), ("drain-restart", {"offline": True})])
def test_missing_drop_capability_refuses_before_inprocess_spawn(tmp_path, verb, args):
    broker, runner, _, _, audit = make_broker(tmp_path, status_reader=lambda: "CapEff:\t6f\n")
    reply = call(broker, verb, args)
    assert reply["error"] == "child_drop_unavailable"
    assert not any(kw.get("user") == "imd-worker" for _, kw in runner.calls)
    assert not runner.argvs("systemctl", "restart") and not runner.argvs("systemctl", "stop")
    line = audit_lines(audit)[-1]
    assert line["verb"] == verb and line["outcome"] == "child_drop_unavailable"
    assert "child_drop_unavailable" in verbs.ERRORS


@pytest.mark.parametrize("verb", ["restart", "stop", "drain-restart"])
def test_gated_apply_refuses_drop_failure_and_finalizes_consumed_plan(tmp_path, verb):
    broker, runner, _, _, audit = make_broker(tmp_path)
    plan = call(broker, verb, {"offline": True})["plan"]
    broker.drop_ok = False
    before = len(runner.calls)
    reply = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4],
                                   "local_only_ack": "local-only"})
    assert reply["error"] == "child_drop_unavailable"
    assert not any(kw.get("user") == "imd-worker" for _, kw in runner.calls[before:])
    assert not runner.argvs("systemctl", "restart") and not runner.argvs("systemctl", "stop")
    assert broker._drain.armed is None
    line = audit_lines(audit)[-1]
    assert line["verb"] == verb and line["plan_id"] == plan["plan_id"] and line["outcome"] == "child_drop_unavailable"
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is False
    assert call(broker, "ping")["data"]["in_flight"] is None and not broker._lock.locked()


@pytest.mark.parametrize("failure,outcome", [(PermissionError(1, "untrusted diagnostic"), "internal: PermissionError errno 1"),
                                            (RuntimeError("untrusted diagnostic"), "internal: RuntimeError"),
                                            (None, "child_drop_unavailable")])
def test_drain_gate_exception_rearms_same_drain_without_escaping_tick(tmp_path, monkeypatch, failure, outcome):
    broker, runner, journal, clock, audit = make_broker(tmp_path)
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    armed = broker._drain.armed
    deadline = armed.expires_at
    if failure is None:
        broker.drop_ok = False
    else:
        def broken_gate(**kw):
            raise failure
        monkeypatch.setattr(broker, "_gate", broken_gate)
    events = []
    for _ in range(4):
        clock.advance(30)
        journal.add(hb(clock() - 1))
        events += broker.tick(clock())
    assert events == ["drain_fire", "drain_rearmed"]
    assert broker._drain.armed is armed and armed.plan_id == plan["plan_id"]
    assert armed.expires_at == deadline and armed.idle_beats == 0 and armed.rearmed == 1
    assert not runner.argvs("systemctl", "restart")
    assert call(broker, "ping")["data"]["in_flight"] is None and not broker._lock.locked()
    line = audit_lines(audit)[-1]
    assert line["phase"] == "drain_rearmed" and line["outcome"] == outcome and line["plan_id"] == plan["plan_id"]
    assert "untrusted diagnostic" not in audit.path.read_text()


def test_oserror_audit_retains_validated_verb_and_errno(tmp_path):
    broker, _, _, _, audit = make_broker(tmp_path, script={("ls", "-1A"): PermissionError(1, "untrusted diagnostic")})
    assert call(broker, "outbox")["error"] == "internal"
    line = audit_lines(audit)[-1]
    assert line["verb"] == "outbox" and line["phase"] == "refused"
    assert line["outcome"] == "internal: PermissionError errno 1"
    assert "untrusted diagnostic" not in audit.path.read_text()


def test_broker_version_identifies_fix5():
    import imd_dashd
    assert broker_mod.VERSION == "imd-dashd 0.1.1"
    assert imd_dashd.__version__ == "0.1.1"


@pytest.mark.parametrize("verb", ["status", "skills", "tools", "whoami", "seat", "sessions"])
@pytest.mark.parametrize("timed_out", [False, True])
def test_failed_transient_stderr_is_separate_bounded_redacted_and_not_audited(tmp_path, verb, timed_out):
    import json
    import subprocess
    from tests.broker._harness import NOW, PRIVATE_KEY, PUBLIC_KEY, transient
    diagnostic = "lookup failed\n" + PUBLIC_KEY + "\n" + PRIVATE_KEY + "\n" + "x" * 190 + "sk-" + "a" * 60 + "\n" + "z" * 250 + "\nomitted\n"
    answer = (subprocess.TimeoutExpired("systemd-run", 45, output=b"", stderr=diagnostic.encode())
              if timed_out else transient("", rc=1, stderr=diagnostic))
    broker, _, _, _, audit = make_broker(tmp_path, script={("systemd-run",): answer})
    args = {"runtime": "codex", "since": NOW - 86400} if verb == "sessions" else {}
    reply = call(broker, verb, args)
    detail = reply["data"] if reply["ok"] else reply["detail"]
    assert detail["stderr_head"][0] == "lookup failed"
    assert len(detail["stderr_head"]) == 5 and all(len(line) <= 200 for line in detail["stderr_head"])
    assert detail.get("lines", []) == [] and broker._whoami_key is None
    assert PUBLIC_KEY not in json.dumps(reply) and PRIVATE_KEY not in json.dumps(reply) and "a" * 60 not in json.dumps(reply)
    assert "omitted" not in json.dumps(reply)
    broker.shutdown()  # even flushed read counts contain no diagnostics
    assert "lookup failed" not in audit.path.read_text()


def test_sessions_nonzero_exit_with_valid_json_is_unreadable(tmp_path):
    from tests.broker._harness import NOW, transient
    broker, *_ = make_broker(tmp_path, script={("systemd-run",): transient('{"sessions": []}', rc=1, stderr="namespace failed")})
    reply = call(broker, "sessions", {"runtime": "codex", "since": NOW - 86400})
    assert reply["error"] == "unreadable" and reply["detail"]["rc"] == 1
    assert reply["detail"]["stderr_head"] == ["namespace failed"]


@pytest.mark.parametrize("verb,args", [("doctor", {}), ("skills-set", {"skill_id": "oracle-assess", "on": False})])
@pytest.mark.parametrize("timed_out", [False, True])
def test_failed_apply_verify_has_sanitized_stderr_without_currency(tmp_path, verb, args, timed_out):
    import subprocess
    from tests.broker._harness import PRIVATE_KEY, transient
    diagnostic = "namespace failed ($0.114 estimated)\n" + PRIVATE_KEY
    answer = (subprocess.TimeoutExpired("systemd-run", 135, output=b"stdout only", stderr=diagnostic.encode())
              if timed_out else transient("stdout only", rc=1, stderr=diagnostic))
    broker, _, _, _, audit = make_broker(tmp_path, script={("systemd-run",): answer})
    broker._skills_listing = {"oracle-assess"}
    plan = call(broker, verb, args)["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    broker._threads[plan["plan_id"]].join(timeout=5)
    assert not broker._threads[plan["plan_id"]].is_alive()
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False
    assert data["verify_lines"] == ["stdout only"]
    assert data["stderr_head"][0].strip() == "namespace failed"
    assert "0.114" not in str(data) and PRIVATE_KEY not in str(data)
    assert "namespace failed" not in audit.path.read_text()


def test_successful_transient_keeps_original_reply_shape_even_with_stderr(tmp_path):
    from tests.broker._harness import transient
    broker, *_ = make_broker(tmp_path, script={("systemd-run",): transient("ok", stderr="successful warning")})
    assert set(call(broker, "status")["data"]) == {"lines", "rc", "unit"}
    plan = call(broker, "doctor")["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    broker._threads[plan["plan_id"]].join(timeout=5)
    assert "stderr_head" not in call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
