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
# ==== Task 6.14: text parsers over the CLI fixtures =========================================================

from maxpane_dashboard.data.seat_broker_client import (  # noqa: E402
    parse_cgroup, parse_docker_inspect, parse_docker_ps, parse_docker_stats, parse_imd_skills, parse_imd_status, parse_imd_tools,
    parse_systemctl_show, parse_whoami,
)


def test_parse_systemctl_show_yields_the_unit_block():
    unit = parse_systemctl_show((CLI / "systemctl_show.txt").read_text())
    assert unit["activeState"] == "active" and unit["subState"] == "running" and unit["mainPid"] == 98508
    assert unit["sinceUtc"] == "2026-09-25T11:45:41Z" and unit["restarts"] == 0
    assert unit["bootEnabled"] is False and unit["unitFileState"] == "disabled"     # spec §8 UNIT: `boot: disabled ⚠`
    assert unit["restartPolicy"] == "always/30s" and unit["killMode"] == "control-group" and unit["stopTimeoutS"] == 30.0
    assert unit["gracefulStopPossible"] is True                                       # spec §5.5: control-group and >= 30 s
    assert unit["memoryMaxB"] == 3221225472 and unit["cpuQuota"] == "100%" and unit["tasksMax"] == 256 and unit["tasksCurrent"] == 11
    assert unit["execStart"].startswith("{ path=/opt/imd-worker/bin/imd")
    # missing fields are None, never 0; infinity is None
    sparse = parse_systemctl_show("ActiveState=inactive\nMemoryMax=infinity\nTimeoutStopUSec=infinity\nKillMode=process\n")
    assert sparse["restarts"] is None and sparse["mainPid"] is None and sparse["memoryMaxB"] is None
    assert sparse["stopTimeoutS"] is None and sparse["gracefulStopPossible"] is None and sparse["bootEnabled"] is None
    assert parse_systemctl_show("CPUQuotaPerSecUSec=500ms\n")["cpuQuota"] == "50%"


def test_parse_docker_inspect_and_stats_and_cgroup():
    unit = parse_docker_inspect(json.loads((CLI / "docker_inspect.json").read_text()))
    assert unit["running"] is True and unit["status"] == "running" and unit["startedAt"] == "2026-09-25T11:45:54Z"
    assert unit["restartCount"] == 0 and unit["restartPolicy"] == "unless-stopped" and unit["image"] == "imd-worker:285d1984-forge"
    assert unit["stopTimeoutS"] == 10 and unit["stopTimeoutConfigured"] is False and unit["init"] is False
    assert unit["gracefulStopPossible"] is False                                      # fill1 §3: PID 1 without init, 10 s SIGKILL
    assert unit["memoryMaxB"] == 3758096384 and unit["cpuQuota"] == "6 cpus" and unit["logConfig"]["type"] == "json-file"
    # the §7 unit keys WP7's _unit_block copies (contract §C.12): hero, UNIT since/restarts, configChangedSinceStart's anchor
    assert unit["activeState"] == "active" and unit["subState"] == "running" and unit["sinceUtc"] == "2026-09-25T11:45:54Z"
    assert unit["restarts"] == 0 and unit["mainPid"] == 48213 and unit["bootEnabled"] is True
    stopped = json.loads((CLI / "docker_inspect.json").read_text())
    stopped[0]["State"].update(Running=False, Status="exited", Pid=0)
    down = parse_docker_inspect(stopped)
    assert down["activeState"] == "exited" and down["subState"] == "exited" and down["mainPid"] is None and down["running"] is False
    assert parse_docker_inspect([]) == {} and parse_docker_inspect("junk") == {}
    stats = parse_docker_stats((CLI / "docker_stats.txt").read_text().strip())
    assert stats == {"memoryCurrentB": int(130.8 * 1024 ** 2), "cpuPct": 0.0, "pids": 11}
    assert parse_docker_stats("not json") == {"memoryCurrentB": None, "cpuPct": None, "pids": None}
    cgroup = parse_cgroup(CLI / "cgroup")
    assert cgroup == {"memoryCurrentB": 116146176, "memoryPeakB": 188592128, "memoryMaxB": 3221225472, "cpuQuota": "100%"}
    assert parse_cgroup(CLI / "missing")["memoryCurrentB"] is None
    # graceful on docker: StopTimeout >= 45 or Init (spec §5.5)
    recreated = json.loads((CLI / "docker_inspect.json").read_text())
    recreated[0]["HostConfig"]["StopTimeout"] = 45
    recreated[0]["HostConfig"]["Init"] = True
    assert parse_docker_inspect(recreated)["gracefulStopPossible"] is True


def test_parse_imd_status_both_seats_and_drift():
    seat7 = parse_imd_status(_lines("imd_status_seat7.txt"), daemon_version="0.1.0+5bfa8261")
    assert seat7["tokenId"] == 7 and seat7["capacity"] == 1 and seat7["server"] == "https://api.imd.fun"
    assert seat7["deviceKey"] == PUBLIC_KEY and seat7["offers"] == ["code", "fuzz", "research"]
    assert seat7["runtime"] == {"id": "codex", "version": "codex-cli 0.157.0"} and seat7["tasksRunOn"] == "codex"
    assert seat7["eligibility"] == "eligible — this machine can receive work" and seat7["parseError"] is None
    assert [r["id"] for r in seat7["runtimes"]] == ["claude", "codex"] and seat7["runtimes"][0]["available"] is False
    seat420 = parse_imd_status(_lines("imd_status_seat420.txt"))
    assert seat420["tokenId"] == 420 and seat420["runtime"] == {"id": "claude", "version": "Claude Code 2.1.282"}
    # a redacted device line (the broker turns the hex64 into <hex64>) is None, not a bogus key
    redacted = [ln.replace(PUBLIC_KEY, "<hex64>") for ln in _lines("imd_status_seat7.txt")]
    assert parse_imd_status(redacted)["deviceKey"] is None
    drift = parse_imd_status(["Status: everything fine", "Seat: 7"], daemon_version="0.1.0+deadbeef")
    assert drift["tokenId"] is None and drift["parseError"] == "imd status format changed in 0.1.0+deadbeef"


def test_parse_imd_skills_tools_whoami():
    skills = parse_imd_skills(_lines("imd_skills.txt"))
    assert skills["offered"] == 31 and skills["on"] == 31 and len(skills["rows"]) == 31 and skills["needsNetwork"] == 7
    assert {"id": "oracle-assess", "on": True, "needs": "network"} in skills["rows"]
    assert {"id": "better-interface", "on": True, "needs": "tool:browser"} in skills["rows"]
    assert {"id": "abi-recon", "on": True, "needs": None} in skills["rows"]
    assert set(skills["rows"][0]) == {"id", "on", "needs"}
    off = parse_imd_skills(["31 skills offered, 30 on here.", "off oracle-assess — needs network"])
    assert off["on"] == 30 and off["rows"] == [{"id": "oracle-assess", "on": False, "needs": "network"}]
    assert parse_imd_tools(_lines("imd_tools_none.txt")) == []
    assert parse_imd_tools(["ready      browser — probe answered", "not ready  ipfs — set IPFS_TOKEN"]) == ["browser", "ipfs"]
    assert parse_whoami(_lines("imd_whoami.txt")) == PUBLIC_KEY
    assert parse_whoami(["not a key", ""]) is None


def test_parse_docker_ps_selects_orphans_outside_pid_1_older_than_an_hour():
    rows = parse_docker_ps((CLI / "docker_ps_orphan.txt").read_text())
    assert [r["pid"] for r in rows] == [412, 418]                                     # the hung doctor and its claude child
    assert set(rows[0]) == {"pid", "pgid", "uid", "cgroup", "ageS", "rssB", "cmd", "pgidMembers"}
    assert rows[0]["ageS"] == 5412 and rows[0]["rssB"] == 131204 * 1024 and rows[0]["cgroup"] == "container"
    assert [m["pid"] for m in rows[0]["pgidMembers"]] == [418]
    assert parse_docker_ps("garbage\n") == []


def test_cli_stand_ins_agree_with_the_broker_and_the_unit_file():
    # spec §11: the brokers exec only subcommands the measured `imd` usage lists, and `update` exists there but is
    # excluded entirely from the verb enum; spec §4.1b: transient children copy the worker unit's IPAddressDeny
    from imd_dashd.child_unit import read_ip_address_deny
    usage = (BUILD / "imd_help.txt").read_text(encoding="utf-8").splitlines()
    assert usage[0] == "unknown command: --help"                               # `imd --help` is not a flag (vps §47)
    commands = {ln.split()[0] for ln in usage[3:] if ln.startswith("  ") and ln.split()}
    assert {"whoami", "status", "skills", "tools", "doctor"} <= commands        # every imd subcommand the brokers exec
    assert "update" in commands and "update" not in broker_verbs.ALL_VERBS
    shown = (CLI / "systemctl_show_ipaddressdeny.txt").read_text(encoding="utf-8").strip()
    assert shown.startswith("IPAddressDeny=")
    copied = read_ip_address_deny(run=RecordingRunner({("systemctl", "show"): (0, shown.split("=", 1)[1] + "\n")}))
    unit_file = (CLI / "systemctl_cat.txt").read_text(encoding="utf-8").splitlines()
    declared = " ".join(ln.split("=", 1)[1] for ln in unit_file if ln.startswith("IPAddressDeny="))
    assert copied.split() == [a if "/" in a else a + "/32" for a in declared.split()]   # systemd prints bare hosts as /32
