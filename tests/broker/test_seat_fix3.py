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
