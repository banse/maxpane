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
