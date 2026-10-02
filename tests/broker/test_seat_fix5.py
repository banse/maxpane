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
