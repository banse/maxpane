"""``data/seat_broker_client.py`` -- brokers, host readers and text parsers (spec §4.2, §5.3, §5.5, §11, §12.2).

No real socket path, docker or file under ~/.maxpane: sockets are ``socket.socketpair()`` against a real
``Broker`` on a thread, docker is a ``RecordingRunner``, the audit lives on ``tmp_path``.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import threading
from pathlib import Path

import pytest

from imd_dashd import verbs as broker_verbs
from maxpane_dashboard.data import seat_broker_client as client
from maxpane_dashboard.data.seat_broker_client import (
    CLIENT_TIMEOUT_S, ApplyResult, BrokerError, FakeBroker, Plan, UnixSocketBroker, VerifyResult,
)
from tests.broker._harness import NOW, PUBLIC_KEY, Clock, hb, idle_window, make_broker, msg
from tests.broker._recorder import RecordingRunner, timeout_for

CLI = Path(__file__).resolve().parents[1] / "fixtures" / "seat" / "cli"
BUILD = CLI / "5bfa8261"


def _lines(name: str) -> list[str]:
    return (BUILD / name).read_text(encoding="utf-8").splitlines()


# ==== Task 6.13: enum copy, wire dataclasses, UnixSocketBroker, FakeBroker ==================================


def test_client_enum_equals_the_broker_enum():
    # the TUI carries copies (the VPS wheel has no imd_dashd); they must never drift from imd_dashd/verbs.py
    assert client.READ_VERBS == broker_verbs.READ_VERBS and client.WRITE_VERBS == broker_verbs.WRITE_VERBS
    assert client.GATED_VERBS == broker_verbs.GATED_VERBS and client.TRANSIENT_VERBS == broker_verbs.TRANSIENT_VERBS
    assert client.SKILL_ID_RE.pattern == broker_verbs.SKILL_ID_RE.pattern and client.LOCAL_ONLY_ACK == broker_verbs.LOCAL_ONLY_ACK
    assert client.APPLY_VERB == broker_verbs.APPLY_VERB and client.PROTOCOL_VERSION == broker_verbs.PROTOCOL_VERSION
    assert CLIENT_TIMEOUT_S == 20.0


def test_wire_dataclasses_parse_the_spec_shapes():
    plan = Plan.from_wire({"plan_id": "7f3a9c1e2b4d6081", "verb": "restart", "argv": ["systemctl", "restart", "imd-worker.service"],
                           "expires_at": "2026-09-26T03:41:12Z", "single_use": True, "preconditions": {"idle_beats": 9},
                           "warning": "w", "inverse": {"verb": "stop", "args": {}}, "verify": {"within_s": 30},
                           "restart_required_after": False})
    assert plan.plan_id == "7f3a9c1e2b4d6081" and plan.inverse == {"verb": "stop", "args": {}} and plan.raw["warning"] == "w"
    result = ApplyResult.from_wire({"outcome": "applied", "exit_code": 0, "cursor_before": "s=1;i=2", "audit_seq": 1287, "preconditions": {}})
    assert result.outcome == "applied" and result.audit_seq == 1287
    verify = VerifyResult.from_wire({"verified": True, "connected": "pending (reconnecting since 03:40:31)", "verify_lines": ["a"],
                                     "cursor_after": "s=1;i=9", "elapsed_s": 4.1, "audit_seq": 1288})
    assert verify.verified is True and verify.connected.startswith("pending") and verify.reason is None


# -- UnixSocketBroker over socketpair


def _served(broker):
    def connect(path: str, timeout_s: float) -> socket.socket:
        ours, theirs = socket.socketpair()
        threading.Thread(target=broker.serve_connection, args=(theirs,), daemon=True).start()
        return ours
    return connect


def test_unix_socket_broker_round_trips_plan_apply_verify(tmp_path):
    broker, runner, journal, clock, _audit = make_broker(tmp_path)
    unix = UnixSocketBroker("/run/imd-dash/broker.sock", offline=False, connect=_served(broker))
    assert unix.kind == "unix" and unix.trust() == "host" and unix.reachable() is True
    assert unix.read("ping")["version"] == "imd-dashd 0.1.0"
    plan = unix.plan("restart")
    assert isinstance(plan, Plan) and plan.argv == ["systemctl", "restart", "imd-worker.service"]
    assert plan.preconditions["plane"]["mode"] == "plane+local"                      # offline=False travelled in args
    result = unix.apply(plan.plan_id, plan.plan_id[:4])
    assert result.outcome == "applied" and runner.argvs("systemctl", "restart") == [["systemctl", "restart", "imd-worker.service"]]
    journal.add(msg(clock() + 0.3, "shutting down"), msg(clock() + 0.6, "runtimes: codex codex-cli 0.157.0 (using codex)"))
    clock.advance(2)
    verify = unix.verify(plan.plan_id)
    assert verify.verified is True and str(verify.connected).startswith("pending")
    with pytest.raises(BrokerError) as exc:
        unix.apply(plan.plan_id, plan.plan_id[:4])
    assert exc.value.code == "plan_spent" and exc.value.detail == {"plan_id": plan.plan_id}


def test_unix_socket_broker_offline_marks_every_gated_plan_local_only(tmp_path):
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    unix = UnixSocketBroker(connect=_served(broker), offline=True)
    plan = unix.plan("restart")
    assert plan.preconditions["plane"]["mode"] == "local-only" and runner.argvs("python3", "-I") == []
    with pytest.raises(BrokerError) as exc:
        unix.apply(plan.plan_id, plan.plan_id[:4])
    assert exc.value.code == "local_only_ack_required"
    plan = unix.plan("restart")
    assert unix.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only").outcome == "applied"


def test_unix_socket_broker_transport_failures_are_broker_errors():
    def refuse(path, timeout_s):
        raise ConnectionRefusedError()

    unix = UnixSocketBroker("/run/imd-dash/broker.sock", connect=refuse)
    assert unix.reachable() is False
    with pytest.raises(BrokerError) as exc:
        unix.read("ping")
    assert exc.value.code == "unreachable" and exc.value.detail["path"] == "/run/imd-dash/broker.sock"

    def half_open(path, timeout_s):
        ours, theirs = socket.socketpair()
        theirs.close()
        return ours

    with pytest.raises(BrokerError) as exc:
        UnixSocketBroker(connect=half_open).read("ping")
    assert exc.value.code in ("transport", "bad_response")


# -- FakeBroker


def test_fake_broker_records_calls_and_serves_fixtures(tmp_path):
    fake = FakeBroker({"status": {"ok": True, "data": {"lines": ["token 7"], "rc": 0, "unit": None}},
                       "restart": lambda args: {"ok": True, "plan": {"plan_id": "0" * 16, "verb": "restart", "argv": [], "expires_at": "",
                                                                     "single_use": True, "preconditions": {"offline": args["offline"]},
                                                                     "warning": "", "inverse": None, "verify": {}, "restart_required_after": False}}},
                      offline=True, trust="container")
    assert fake.read("status")["lines"] == ["token 7"] and fake.trust() == "container" and fake.kind == "fake"
    assert fake.plan("restart").preconditions == {"offline": True}                  # offline injected into the plan args
    assert fake.calls == [("status", {}), ("restart", {"offline": True})]
    assert fake.reachable() is True
    with pytest.raises(BrokerError) as exc:
        fake.read("whoami")
    assert exc.value.code == "no_fixture"
    case = tmp_path / "case"
    (case / "broker").mkdir(parents=True)
    (case / "broker" / "outbox.json").write_text(json.dumps({"ok": True, "data": {"files": 0}}))
    (case / "broker" / "seat.json").write_text(json.dumps({"ok": False, "error": "projection_refused", "detail": {"canary": "key_name"}}))
    fixture = FakeBroker(fixture_dir=case)
    assert fixture.read("outbox") == {"files": 0}
    with pytest.raises(BrokerError) as exc:
        fixture.read("seat")
    assert exc.value.code == "projection_refused" and exc.value.detail == {"canary": "key_name"}
    assert FakeBroker(reachable=False).reachable() is False
    # WP7 fixtures hold bare read payloads, WP8 scripts hold whole wire responses: both are valid (deviation 13)
    bare = FakeBroker({"ping": {"pid": 4242, "drain_armed": False}, "outbox": lambda args: {"files": 2}, "restart": {"plan_id": "x"}})
    assert bare.read("ping") == {"pid": 4242, "drain_armed": False} and bare.read("outbox") == {"files": 2}
    assert bare.reachable() is True
    with pytest.raises(BrokerError) as exc:
        bare.plan("restart")                                                          # a write verb needs the whole response
    assert exc.value.code == "bad_response"
    (case / "broker" / "tools.json").write_text(json.dumps({"lines": [], "rc": 0, "unit": None}))
    assert fixture.read("tools") == {"lines": [], "rc": 0, "unit": None}
