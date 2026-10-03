"""Upgrade-day regressions, using only the scripted broker host."""
from tests.broker._harness import audit_lines, call, hb, make_broker


def test_drain_dispatch_exception_never_queues_a_second_restart(tmp_path):
    broker, runner, journal, clock, audit = make_broker(
        tmp_path, script={("systemctl", "restart"): RuntimeError("untrusted message")})
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    for _ in range(4):
        clock.advance(30)
        journal.add(hb(clock() - 1))
        broker.tick(clock())
    assert broker._drain.armed is None
    lines = audit_lines(audit)
    firing = next(i for i, line in enumerate(lines) if line["phase"] == "drain_fire")
    assert len(lines[firing + 1:]) == 1
    line = lines[-1]
    assert line["phase"] == "apply" and line["verb"] == "drain-restart"
    assert line["plan_id"] == lines[firing]["plan_id"] != plan["plan_id"]
    assert line["outcome"] == "internal: RuntimeError; not re-armed"
    assert "untrusted message" not in audit.path.read_text()
    for _ in range(4):
        clock.advance(30)
        journal.add(hb(clock() - 1))
        broker.tick(clock())
    assert len(runner.argvs("systemctl", "restart")) == 1
    assert not broker._lock.locked() and broker._in_flight is None


def test_doctor_failure_reason_uses_only_redacted_bounded_summary(tmp_path):
    from tests.broker._harness import PRIVATE_KEY, transient
    summary = "2 things to fix: memory, " + PRIVATE_KEY + " ($0.114 estimated), " + "x" * 250
    broker, _, _, _, audit = make_broker(tmp_path, script={("systemd-run",): transient(summary, rc=1)})
    plan = call(broker, "doctor")["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    broker._threads[plan["plan_id"]].join(timeout=5)
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False
    assert data["reason"] == "exit 1 · " + data["verify_lines"][-1][:200]
    assert len(data["reason"]) == len("exit 1 · ") + 200
    assert PRIVATE_KEY not in str(data) and "0.114" not in str(data)
    assert audit_lines(audit)[-1]["outcome"] == "finished"
    assert "things to fix" not in audit.path.read_text()
