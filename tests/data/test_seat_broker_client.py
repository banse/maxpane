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
# ==== Task 6.15: host readers ===============================================================================

from maxpane_dashboard.data.seat_broker_client import DockerUnitReader, FixtureUnitReader, SystemdUnitReader  # noqa: E402


def test_systemd_unit_reader_merges_show_and_cgroup(tmp_path):
    cgroup_root = tmp_path / "cgroup" / "system.slice"
    (cgroup_root / "imd-worker.service").mkdir(parents=True)
    for name in ("memory.current", "memory.peak", "memory.max", "cpu.max"):
        (cgroup_root / "imd-worker.service" / name).write_bytes((CLI / "cgroup" / name).read_bytes())
    runner = RecordingRunner({("systemctl", "show"): (0, (CLI / "systemctl_show.txt").read_text())})
    reader = SystemdUnitReader(run=runner, cgroup_root=cgroup_root, home=str(tmp_path))
    unit = reader.read_unit()
    assert unit["activeState"] == "active" and unit["memoryCurrentB"] == 116146176 and unit["memoryPeakB"] == 188592128
    argv, kw = runner.calls[0]
    assert argv[:4] == ["systemctl", "show", "imd-worker.service", "--timestamp=utc"] and argv[4] == "-p"
    assert argv[5].split(",") == ["ActiveState", "SubState", "MainPID", "NRestarts", "ActiveEnterTimestamp", "ExecMainStartTimestamp",
                                  "UnitFileState", "Restart", "RestartUSec", "MemoryMax", "CPUQuotaPerSecUSec", "TasksMax",
                                  "TasksCurrent", "KillMode", "TimeoutStopUSec", "ExecStart"]
    assert kw["timeout"] == 5
    assert SystemdUnitReader(run=RecordingRunner({("systemctl", "show"): timeout_for(["systemctl"], 5)})).read_unit() is None
    host = reader.read_host()
    assert set(host) == {"hostname", "load1", "memAvailMiB", "diskFreeGiB", "journal"} and host["diskFreeGiB"] is not None


def test_docker_unit_reader_has_25s_timeouts_and_a_5_minute_breaker():
    clock = Clock()
    inspect_body = (CLI / "docker_inspect.json").read_text()
    runner = RecordingRunner({("docker", "inspect"): (0, inspect_body), ("docker", "stats"): (0, (CLI / "docker_stats.txt").read_text())})
    reader = DockerUnitReader("imd-worker", run=runner, now=clock)
    unit = reader.read_unit()
    assert unit["running"] is True and unit["memoryCurrentB"] == int(130.8 * 1024 ** 2) and unit["gracefulStopPossible"] is False
    assert unit["activeState"] == "active" and unit["sinceUtc"] == "2026-09-25T11:45:54Z" and unit["restarts"] == 0   # the §7 block
    assert "reason" not in unit
    assert all(kw["timeout"] == 25 for _, kw in runner.calls)
    assert runner.calls[1][0] == ["docker", "stats", "--no-stream", "--format", "{{json .}}", "imd-worker"]
    # inspect times out (fill4 §1: 2 of 3 cycles on 09-26): stats still answers; inspect skipped for 5 min
    runner.script[("docker", "inspect")] = timeout_for(["docker", "inspect"], 25)
    unit = reader.read_unit()
    assert unit["memoryCurrentB"] == int(130.8 * 1024 ** 2) and "running" not in unit  # per-field, never 0 (fill4 §5)
    assert unit["reason"] == "inspect timed out 25 s"                                    # the partial block names its gap
    calls_before = len(runner.calls)
    clock.advance(60)
    partial = reader.read_unit()
    assert [a[:2] for a, _ in runner.calls[calls_before:]] == [["docker", "stats"]]   # breaker open: no inspect attempt
    assert partial["reason"].startswith("inspect skipped: breaker open until ")
    clock.advance(300)
    runner.script[("docker", "inspect")] = (0, inspect_body)
    full = reader.read_unit()
    assert full["running"] is True and "reason" not in full
    both_down = DockerUnitReader(run=RecordingRunner({("docker",): timeout_for(["docker"], 25)}))
    assert both_down.read_unit() is None


def test_fixture_unit_reader_reads_either_host_shape(tmp_path):
    systemd_case = tmp_path / "systemd" / "unit"
    systemd_case.mkdir(parents=True)
    (systemd_case / "systemctl_show.txt").write_text((CLI / "systemctl_show.txt").read_text())
    (systemd_case / "cgroup").mkdir()
    (systemd_case / "cgroup" / "memory.peak").write_text("188592128\n")
    unit = FixtureUnitReader(tmp_path / "systemd").read_unit()
    assert unit["activeState"] == "active" and unit["memoryPeakB"] == 188592128
    docker_case = tmp_path / "docker" / "unit"
    docker_case.mkdir(parents=True)
    (docker_case / "docker_inspect.json").write_text((CLI / "docker_inspect.json").read_text())
    (docker_case / "docker_stats.txt").write_text((CLI / "docker_stats.txt").read_text())
    unit = FixtureUnitReader(tmp_path / "docker").read_unit()
    assert unit["running"] is True and unit["pids"] == 11 and unit["activeState"] == "active" and unit["restarts"] == 0
    assert FixtureUnitReader(tmp_path / "empty").read_unit() is None
    assert FixtureUnitReader(tmp_path / "empty").read_host()["hostname"] == "fixture"
# ==== Task 6.16: LocalDockerBroker ==========================================================================

from maxpane_dashboard.data.seat_broker_client import CONTAINER_TIMEOUTS, LocalDockerBroker  # noqa: E402


def _container_procs():
    return [{"pid": pid, "ppid": ppid, "pgid": pgid, "uid": 1000, "start_ticks": pid * 100,
             "cgroup": "0::/", "age_s": 5400} for pid, ppid, pgid in ((1, 0, 1), (412, 0, 412), (418, 412, 412))]


def _docker_script(tail_ok: bool = True) -> dict:
    inspect_body = (CLI / "docker_inspect.json").read_text()

    def exec_answer(argv, kw):
        inner = argv[argv.index("imd-worker") + 1:]
        if inner[:1] == ["timeout"]:
            inner = inner[6:]
        if inner == ["imd", "whoami"]:
            return subprocess.CompletedProcess(argv, 0, (PUBLIC_KEY + "\n").encode(), b"")
        if inner == ["imd", "status"]:
            return subprocess.CompletedProcess(argv, 0, (BUILD / "imd_status_seat420.txt").read_bytes(), b"")
        if inner == ["imd", "skills"]:
            return subprocess.CompletedProcess(argv, 0, (BUILD / "imd_skills.txt").read_bytes(), b"")
        if inner == ["imd", "tools"]:
            return subprocess.CompletedProcess(argv, 0, (BUILD / "imd_tools_none.txt").read_bytes(), b"")
        if inner == ["imd", "doctor"]:
            return subprocess.CompletedProcess(argv, 1, (BUILD / "imd_doctor.txt").read_bytes(), b"")
        if inner[:2] == ["imd", "skills"]:
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if "--proc-snapshot" in inner:
            return subprocess.CompletedProcess(argv, 0, json.dumps(_container_procs()).encode(), b"")
        if inner[:1] == ["python3"]:
            script = kw.get("input") or b""
            if b"--config" in b" ".join(a.encode() for a in inner):
                payload = {"server": "https://api.imd.fun", "deviceKey": PUBLIC_KEY, "wallet": "0x887b", "tokenId": 420,
                           "maxConcurrency": 1, "skillsOptOut": [], "inference": None, "tools": []}
                return subprocess.CompletedProcess(argv, 0, json.dumps(payload).encode(), b"")
            return subprocess.CompletedProcess(argv, 0, json.dumps({"sessions": [], "skipped": {"oversize": 0}, "stdin_bytes": len(script)}).encode(), b"")
        if inner[:1] == ["ls"]:
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if inner[:1] == ["ps"]:
            return subprocess.CompletedProcess(argv, 0, (CLI / "docker_ps_orphan.txt").read_bytes(), b"")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    return {("docker", "inspect"): (0, inspect_body), ("docker", "exec"): exec_answer,
            ("docker", "restart"): (0, ""), ("docker", "stop"): (0, ""), ("docker", "start"): (0, "")}


def _local(tmp_path, *, tail=None, offline=True, clock=None, script=None):
    clock = clock or Clock()
    lines = list(tail) if tail is not None else idle_window(clock())
    runner = RecordingRunner(_docker_script())
    runner.script.update(script or {})
    broker = LocalDockerBroker("imd-worker", run=runner, audit_path=tmp_path / "seat_audit.jsonl", now=clock, offline=offline,
                               tail_lines=lambda: lines, seat=420)
    return broker, runner, lines, clock


def test_every_docker_exec_of_imd_python_node_is_wrapped_in_container_timeout(tmp_path, monkeypatch):
    # spec §4.2: killing the docker exec client does not stop the exec'd process -> coreutils timeout INSIDE the container
    monkeypatch.setattr(client, "broker_script", lambda name: b"# " + name.encode())
    broker, runner, _lines, _clock = _local(tmp_path)
    for verb, args in (("status", {}), ("skills", {}), ("whoami", {}), ("tools", {}), ("seat", {}),
                       ("sessions", {"since": 0.0, "runtime": "claude"})):
        broker.read(verb, args)
    for verb in ("doctor", "skills-set"):
        plan = broker.plan(verb, {"skill_id": "oracle-assess", "on": False} if verb == "skills-set" else {})
        broker.apply(plan.plan_id, plan.plan_id[:4])
        broker._threads[plan.plan_id].join(timeout=5)
    execs = [argv for argv, _ in runner.calls if argv[:2] == ["docker", "exec"]]
    runtime_execs = [a for a in execs if any(tok in ("imd", "python3", "node") for tok in a)]
    assert len(runtime_execs) >= 8, "status, skills, whoami, tools, seat(+whoami), sessions, doctor, skills-set"
    for argv in execs:
        inner = argv[4:]
        first = inner[0] if inner else None
        if first == "timeout":
            assert inner[1:5] == ["-s", "TERM", "-k", inner[4]] and inner[5].isdigit()
            assert inner[6] in ("imd", "python3", "node")
            kind = inner[7] if inner[6] == "imd" else ("seat" if "--config" in inner else "sessions")
            if inner[6:9] == ["imd", "skills", "remove"] or inner[6:9] == ["imd", "skills", "add"]:
                kind = "skills-set"
            assert (int(inner[4]), int(inner[5])) == CONTAINER_TIMEOUTS[kind], inner
        else:
            assert first not in ("imd", "python3", "node"), argv           # coreutils (ls/find/stat/ps/kill) may run bare
    for argv, kw in runner.calls:        # the host-side belt: 25 s, or grace + secs + 5 above a wrapped exec's in-container limit
        wrapped = argv[:2] == ["docker", "exec"] and argv[4:5] == ["timeout"]
        assert kw["timeout"] == (int(argv[8]) + int(argv[9]) + 5 if wrapped else 25), argv
    # `docker exec -i` never reads the TUI's terminal: a script travels as input=, everything else gets stdin=DEVNULL
    assert all(kw.get("input") is not None or kw.get("stdin") is subprocess.DEVNULL for a, kw in runner.calls if a[:2] == ["docker", "exec"])
    doctor = next(a for a in execs if a[-2:] == ["imd", "doctor"])
    assert doctor[4:10] == ["timeout", "-s", "TERM", "-k", "10", "120"]


def test_force_disabled_when_not_graceful(tmp_path):
    # spec §4.2 / §16 #8: gracefulStopPossible is false on the Mac (StopTimeout null, no init) -> --force ALWAYS force_disabled
    running = idle_window(NOW)[:-1] + [hb(NOW - 11, "1 task running"), msg(NOW - 42, "accepted implement 0c1f9727 — src/ (max 60 turns)")]
    broker, runner, _lines, _clock = _local(tmp_path, tail=running)
    with pytest.raises(BrokerError) as exc:
        broker.plan("restart", {"force_node8": "0c1f9727"})
    assert exc.value.code == "force_disabled" and exc.value.detail["graceful_stop_possible"] is False
    with pytest.raises(BrokerError) as exc:
        broker.plan("restart")
    assert exc.value.code == "gate_blocked" and exc.value.detail["reason"].startswith("task running 0c1f9727")
    assert runner.argvs("docker", "restart") == []
    # drain-restart is a plain confirm to arm (spec §11): the running task is exactly what it waits out
    drain = broker.plan("drain-restart")
    assert drain.preconditions["lifecycle_open"] is True
    assert broker.apply(drain.plan_id, drain.plan_id[:4]).outcome == "armed" and runner.argvs("docker", "restart") == []
    with pytest.raises(BrokerError) as exc:
        broker.plan("drain-restart")
    assert exc.value.code == "drain_already_armed"
    # even a graceful-looking inspect does not enable force here: the rule is the broker's, not the inspect's
    recreated = json.loads((CLI / "docker_inspect.json").read_text())
    recreated[0]["HostConfig"].update(StopTimeout=45, Init=True)
    broker2, _r, _l, _c = _local(tmp_path / "b", tail=running, script={("docker", "inspect"): (0, json.dumps(recreated))})
    with pytest.raises(BrokerError) as exc:
        broker2.plan("restart", {"force_node8": "0c1f9727"})
    assert exc.value.code == "force_disabled"


def test_local_docker_plan_apply_verify_over_the_tail(tmp_path):
    broker, runner, lines, clock = _local(tmp_path)
    assert broker.kind == "docker" and broker.trust() == "container" and broker.reachable() is True
    assert broker.read("ping")["drain"] is None and broker.read("ping")["drain_armed"] is False
    plan = broker.plan("restart")
    assert plan.argv == ["docker", "restart", "-t", "30", "imd-worker"] and plan.inverse == {"verb": "stop", "args": {}}
    assert plan.preconditions["plane"]["mode"] == "local-only" and plan.preconditions["graceful_stop_possible"] is False
    assert plan.preconditions["unit_active"] is True and plan.preconditions["outbox_files"] == 0
    with pytest.raises(BrokerError) as exc:
        broker.apply(plan.plan_id, plan.plan_id[:4])
    assert exc.value.code == "local_only_ack_required"                                 # offline=True -> typed ack
    plan = broker.plan("restart")
    result = broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")
    assert result.outcome == "applied" and runner.argvs("docker", "restart") == [["docker", "restart", "-t", "30", "imd-worker"]]
    with pytest.raises(BrokerError) as exc:
        broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")
    assert exc.value.code == "plan_spent"
    lines.extend([msg(clock() + 0.5, "shutting down"), msg(clock() + 1.4, "runtimes: claude Claude Code 2.1.282 (using claude)")])
    clock.advance(3)
    verify = broker.verify(plan.plan_id)
    assert verify.verified is True and str(verify.connected).startswith("pending")
    lines.append(msg(clock() + 1, "admitted (session 1a2b3c4d)"))
    clock.advance(2)
    assert broker.verify(plan.plan_id).connected is True
    stop = broker.plan("stop")
    assert stop.argv == ["docker", "stop", "-t", "30", "imd-worker"]
    start = broker.plan("start")
    assert start.argv == ["docker", "start", "imd-worker"]
    with pytest.raises(BrokerError) as exc:
        broker.plan("enable-boot")
    assert exc.value.code == "bad_verb"                                                 # n/a: unless-stopped


def test_local_docker_gate_fails_closed_on_inspect_timeout_and_unreadable_outbox(tmp_path):
    broker, runner, _lines, _clock = _local(tmp_path, script={("docker", "inspect"): timeout_for(["docker", "inspect"], 25)})
    with pytest.raises(BrokerError) as exc:
        broker.plan("restart")
    assert exc.value.code == "gate_unknown(unit)"                                      # spec §11 (e), fill4 §1
    assert broker.read("gate")["unknown"] == "unit"
    broker2, _r, _l, _c = _local(tmp_path / "b")

    def ls_fails(argv, kw):
        return subprocess.CompletedProcess(argv, 2, b"", b"Permission denied")

    def exec_answer(argv, kw):
        inner = argv[argv.index("imd-worker") + 1:]
        return ls_fails(argv, kw) if inner[:1] == ["ls"] else _docker_script()[("docker", "exec")](argv, kw)

    broker2._run.script[("docker", "exec")] = exec_answer
    with pytest.raises(BrokerError) as exc:
        broker2.plan("restart")
    assert exc.value.code == "gate_unknown(outbox)"


def test_local_docker_breaker_opens_for_five_minutes_after_a_timeout(tmp_path):
    clock = Clock()
    broker, runner, _lines, _clock = _local(tmp_path, clock=clock, script={("docker", "inspect"): timeout_for(["docker", "inspect"], 25)})
    assert broker.read("gate")["unit_active"] is None
    inspects = len(runner.argvs("docker", "inspect"))
    clock.advance(60)
    broker.read("gate")
    assert len(runner.argvs("docker", "inspect")) == inspects                          # breaker open: not retried
    clock.advance(300)
    runner.script[("docker", "inspect")] = (0, (CLI / "docker_inspect.json").read_text())
    assert broker.read("gate")["unit_active"] is True


def test_local_docker_audit_is_0600_and_orphans_kill_inside_the_container(tmp_path):
    broker, runner, _lines, _clock = _local(tmp_path)
    broker.plan("start")
    mode = stat.S_IMODE(os.stat(tmp_path / "seat_audit.jsonl").st_mode)
    assert mode == 0o600 and broker.read("audit-tail", {"n": 1})["lines"][0]["phase"] == "plan"
    candidates = broker.read("orphans")["candidates"]
    assert [c["pid"] for c in candidates] == [412, 418]
    plan = broker.plan("kill-orphans", {"pids": [412, 418]})
    assert plan.preconditions["kill_mode_by_pgid"] == {"412": "group"} and plan.preconditions["trust"] == "container"
    broker.apply(plan.plan_id, plan.plan_id[:4])
    kills = [a for a in runner.argvs("docker", "exec") if "kill" in a]
    assert kills == [["docker", "exec", "-i", "imd-worker", "kill", "-TERM", "--", "-412"]]


def test_local_docker_seat_projection_is_canary_checked_and_container_tagged(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "broker_script", lambda name: b"# " + name.encode())
    broker, runner, _lines, _clock = _local(tmp_path)
    data = broker.read("seat")
    assert data["deviceKey"] == PUBLIC_KEY and data["tokenId"] == 420
    projection = [a for a in runner.argvs("docker", "exec") if "--config" in a][0]
    assert projection[4:10] == ["timeout", "-s", "TERM", "-k", "5", "20"] and projection[10:12] == ["python3", "-"]
    kw = [k for a, k in runner.calls if a == projection][0]
    assert kw["input"] == b"# projection"                                            # the script travels on stdin, never in argv
    status = broker.read("status")
    assert status["unit"] is None and parse_imd_status(status["lines"])["tokenId"] == 420
    assert broker.trust() == "container"                                             # every CLI-fed Mac value is container-reported


def test_local_docker_reads_its_own_tail_and_its_seat(tmp_path, monkeypatch):
    # WP8 may build LocalDockerBroker without tail_lines or seat: the gate then reads `docker logs --tail 200 --timestamps`
    # itself (spec §5.1 trusted form, §11 (a) "the tail (Mac)") and the standing URL takes tokenId from the projection
    from tests.broker._harness import stamp
    monkeypatch.setattr(client, "broker_script", lambda name: b"# " + name.encode())
    clock = Clock()
    logs = "".join(f"{text[:23]}456789Z {text}\n" for _epoch, text in idle_window(clock()))
    runner = RecordingRunner(_docker_script())
    runner.script[("docker", "logs")] = (0, logs)
    urls: list[str] = []

    def standing(url, *, timeout_s=8):
        urls.append(url)
        return {"running_count": 0, "at": stamp(clock() - 0.4)}

    monkeypatch.setattr(client._gate_mod, "fetch_standing_running", standing)
    broker = LocalDockerBroker("imd-worker", run=runner, audit_path=tmp_path / "seat_audit.jsonl", now=clock, offline=False)
    plan = broker.plan("restart")
    assert plan.preconditions["idle_beats"] >= 4 and plan.preconditions["plane"]["mode"] == "plane+local"
    assert urls == ["https://api.imd.fun/seats/420/standing"]
    assert runner.argvs("docker", "logs")[0] == ["docker", "logs", "--tail", "200", "--timestamps", "imd-worker"]


def test_local_docker_drain_rearms_and_fires_through_the_fresh_gate(tmp_path):
    # spec §11 drain-restart, Mac column: the same loop over the tail, in-process -- it dies with the TUI
    broker, runner, lines, clock = _local(tmp_path)
    plan = broker.plan("drain-restart")
    assert "dies with the TUI" in plan.warning
    assert broker.apply(plan.plan_id, plan.plan_id[:4]).outcome == "armed" and broker.read("ping")["drain_armed"] is True
    for _ in (1, 2):
        clock.advance(30)
        lines.append(hb(clock() - 5))
        broker.tick()
    clock.advance(30)
    lines.append(hb(clock() - 5, "1 task running"))
    assert "drain_rearmed" in broker.tick()
    lines.append(msg(clock() - 0.5, "submitted implement for 4cf722c7"))
    events: list[str] = []
    for _ in range(4):
        clock.advance(30)
        lines.append(hb(clock() - 5))
        events = broker.tick()
    assert "drain_fire" in events and runner.argvs("docker", "restart") == [["docker", "restart", "-t", "30", "imd-worker"]]
    phases = [ln["phase"] for ln in broker.read("audit-tail", {"n": 50})["lines"] if ln["phase"] != "plan"]
    assert phases == ["drain_armed", "drain_rearmed", "drain_fire", "apply"] and broker.read("ping")["drain_armed"] is False
    lines.extend([msg(clock() + 0.5, "shutting down"), msg(clock() + 1.4, "runtimes: claude Claude Code 2.1.282 (using claude)")])
    clock.advance(3)
    broker.tick()                                                                    # the fired restart gets its verify line
    phases = [ln["phase"] for ln in broker.read("audit-tail", {"n": 50})["lines"] if ln["phase"] != "plan"]
    assert phases == ["drain_armed", "drain_rearmed", "drain_fire", "apply", "verify"]


def test_local_docker_kill_orphans_sigkills_after_grace(tmp_path):
    # spec §11 kill-orphans, Mac column: `kill -TERM -<pgid>` inside the container, SIGKILL after 10 s if still listed
    broker, runner, _lines, clock = _local(tmp_path)
    plan = broker.plan("kill-orphans", {"pids": [412, 418]})
    broker.apply(plan.plan_id, plan.plan_id[:4])
    assert broker.verify(plan.plan_id).verified is None                             # answered (contract §C.16), not yet decided
    assert broker.tick(clock() + 5) == []
    assert broker.tick(clock() + 11) == ["sigkill"]                                  # the ps listing still shows pgid 412
    kills = [a for a in runner.argvs("docker", "exec") if "kill" in a]
    assert kills == [["docker", "exec", "-i", "imd-worker", "kill", "-TERM", "--", "-412"],
                     ["docker", "exec", "-i", "imd-worker", "kill", "-KILL", "--", "-412"]]
    assert broker.verify(plan.plan_id).verified is None                             # SIGKILLed on that tick: decided on the next
    assert broker.tick(clock() + 30) == []                                           # one follow-up per kill, never repeated
    verdict = broker.verify(plan.plan_id)                                            # the ps listing STILL shows pgid 412
    assert verdict.verified is False and verdict.reason == "still listed after SIGKILL: pgid 412"


def test_local_docker_drain_arm_and_cancel_answer_verify(tmp_path):
    # WP8's CONTROL polls verify after every apply (contract §C.16): the Mac answers an arm and a cancel at once, like the root
    broker, runner, _lines, _clock = _local(tmp_path)
    plan = broker.plan("drain-restart")
    assert broker.apply(plan.plan_id, plan.plan_id[:4]).outcome == "armed"
    verdict = broker.verify(plan.plan_id)
    assert verdict.verified is True and verdict.reason is None
    assert verdict.verify_lines == ["drain armed · 0/4 idle beats · expires 18:13 UTC"]                # NOW 14:13:20 + 4 h
    cancel = broker.plan("cancel-drain")
    assert broker.apply(cancel.plan_id, cancel.plan_id[:4]).outcome == "cancelled"
    verdict = broker.verify(cancel.plan_id)
    assert verdict.verified is True and verdict.verify_lines == ["drain cleared · nothing restarted"]
    assert runner.argvs("docker", "restart") == []


def test_local_docker_audits_every_refusal_each_verify_flip_and_read_counts(tmp_path):
    # spec §11: "Every plan, apply, verify and refusal appends an audit line" -- the Mac keeps the same audit
    broker, _runner, lines, clock = _local(tmp_path)
    with pytest.raises(BrokerError):
        broker.call("restart", {"offline": "yes"})                                   # bad_args
    with pytest.raises(BrokerError):
        broker.plan("enable-boot")                                                    # bad_verb (n/a on docker)
    plan = broker.plan("restart")
    with pytest.raises(BrokerError):
        broker.apply(plan.plan_id, "zzzz")                                            # bad_confirm (the plan is consumed)
    with pytest.raises(BrokerError):
        broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")     # plan_spent
    plan = broker.plan("restart")
    with pytest.raises(BrokerError):
        broker.apply(plan.plan_id, plan.plan_id[:4])                                  # local_only_ack_required
    plan = broker.plan("restart")
    broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack="local-only")
    lines.extend([msg(clock() + 0.5, "shutting down"), msg(clock() + 1.4, "runtimes: claude Claude Code 2.1.282 (using claude)")])
    clock.advance(3)
    assert broker.verify(plan.plan_id).verified is True
    broker.verify(plan.plan_id)                                                       # no change -> no second verify line
    audit = [json.loads(ln) for ln in (tmp_path / "seat_audit.jsonl").read_text().splitlines()]
    assert [ln["outcome"] for ln in audit if ln["phase"] == "refused"] == [
        "bad_args", "bad_verb", "bad_confirm", "plan_spent", "local_only_ack_required"]
    verifies = [ln for ln in audit if ln["phase"] == "verify"]
    assert len(verifies) == 1 and verifies[0]["verified"] is True and verifies[0]["plan_id"] == plan.plan_id
    assert audit[0]["args"] == {"names": ["offline"]}                                 # names, never values
    broker.tick(clock() + 3601)                                                       # reads: hourly counts only (deviation 16)
    last = json.loads((tmp_path / "seat_audit.jsonl").read_text().splitlines()[-1])
    assert last["phase"] == "reads" and last["args"] == {"counts": {"verify": 2}}


def test_local_docker_breaker_is_per_verb(tmp_path):
    # spec §12.2 "a 5-min breaker per verb after a timeout": a hung `imd status` must not blind gate step (d)
    broker, runner, _lines, _clock = _local(tmp_path)
    answer = runner.script[("docker", "exec")]

    def status_hangs(argv, kw):
        if argv[-2:] == ["imd", "status"]:
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        return answer(argv, kw)

    runner.script[("docker", "exec")] = status_hangs
    with pytest.raises(BrokerError) as exc:
        broker.read("status")
    assert exc.value.code == "timeout" and exc.value.detail["family"] == "status"
    assert broker.read("outbox") == {"files": 0} and broker.read("gate")["unknown"] is None
    calls = len(runner.calls)
    with pytest.raises(BrokerError) as exc:
        broker.read("status")                                                          # this verb's breaker is open for 5 min
    assert "breaker_until" in exc.value.detail and len(runner.calls) == calls


@pytest.mark.parametrize("phase", ["plan", "term"])
@pytest.mark.parametrize("drift", ["start_ticks", "cgroup", "uid", "new_member"])
def test_local_kill_rechecks_exact_identity_and_whole_group(tmp_path, phase, drift):
    broker, runner, _lines, clock = _local(tmp_path)
    plan = broker.plan("kill-orphans", {"pids": [412, 418]})
    if phase == "term":
        broker.apply(plan.plan_id, plan.plan_id[:4])
    procs = _container_procs()
    if drift == "new_member":
        procs.append(dict(procs[1], pid=500, uid=0))
    else:
        procs[1][drift] = {"start_ticks": 41201, "cgroup": "0::/changed", "uid": 0}[drift]
    answer = runner.script[("docker", "exec")]
    def changed(argv, kw):
        if "--proc-snapshot" in argv:
            return subprocess.CompletedProcess(argv, 0, json.dumps(procs).encode(), b"")
        return answer(argv, kw)
    runner.script[("docker", "exec")] = changed
    before = len(runner.calls)
    if phase == "plan":
        broker.apply(plan.plan_id, plan.plan_id[:4])
    else:
        broker.tick(clock() + 11)
    signals = [a for a, _kw in runner.calls[before:] if "kill" in a]
    assert not any("-412" in a for a in signals), signals
    if drift != "new_member":
        assert not any(a[-1] == "412" for a in signals), signals
    snapshots = [(a, kw) for a, kw in runner.calls if "--proc-snapshot" in a]
    assert snapshots and all(a[4:10] == ["timeout", "-s", "TERM", "-k", "5", "20"] for a, _ in snapshots)
    assert all(kw["timeout"] == 30 and kw.get("input") for _, kw in snapshots)


@pytest.mark.parametrize("failure", ["timeout", "rc", "invalid"])
def test_local_kill_refuses_unavailable_snapshot(tmp_path, failure):
    broker, runner, _lines, clock = _local(tmp_path)
    plan = broker.plan("kill-orphans", {"pids": [412, 418]})
    answer = runner.script[("docker", "exec")]
    def unavailable(argv, kw):
        if "--proc-snapshot" in argv:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            return subprocess.CompletedProcess(argv, 1 if failure == "rc" else 0, b"{}", b"")
        return answer(argv, kw)
    runner.script[("docker", "exec")] = unavailable
    with pytest.raises(BrokerError):
        broker.apply(plan.plan_id, plan.plan_id[:4])
    assert not [a for a, _ in runner.calls if "kill" in a]


def test_local_doctor_cooldown_is_rechecked_at_apply(tmp_path):
    broker, runner, _, _ = _local(tmp_path)
    first, second = [broker.plan('doctor') for _ in range(2)]
    broker.apply(first.plan_id, first.plan_id[:4])
    broker._threads[first.plan_id].join(timeout=5)
    try:
        with pytest.raises(BrokerError) as error:
            broker.apply(second.plan_id, second.plan_id[:4])
        assert error.value.code == 'doctor_too_soon'
    finally:
        if second.plan_id in broker._threads:
            broker._threads[second.plan_id].join(timeout=5)
    assert len([a for a, _ in runner.calls if a[-2:] == ['imd', 'doctor']]) == 1

@pytest.mark.parametrize('failure', ['construct', 'start'])
def test_local_transient_thread_failure_finishes_watch_and_releases_lock(tmp_path, monkeypatch, failure):
    broker, *_ = _local(tmp_path)
    plan = broker.plan('doctor')
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic thread exhaustion')
    with monkeypatch.context() as patch:
        if failure == 'construct':
            patch.setattr(threading, 'Thread', fail)
        else:
            patch.setattr(threading.Thread, 'start', fail)
        with pytest.raises(BrokerError) as exc:
            broker.apply(plan.plan_id, plan.plan_id[:4])
    assert exc.value.code == 'internal'
    assert not broker._lock.locked() and broker._in_flight is None
    watch = broker._watches[plan.plan_id]
    assert watch.done and watch.verified is False and watch.reason == 'thread start failed'
    assert plan.plan_id not in broker._threads
    assert broker.plan('doctor').verb == 'doctor'
    start = broker.plan('start')
    assert broker.apply(start.plan_id, start.plan_id[:4]).outcome == 'applied'


def test_local_sessions_redacts_all_nested_metadata(tmp_path):
    body = {'sessions': [{'path': '/ordinary/session.jsonl', 'model': 'sk-review_SYNTHETIC_fragment',
                         'tokens': {'input': 234, 'output': 56},
                         'sideModel': [{'model': 'sk-ant-review_SYNTHETIC_fragment', 'tokens': 7}],
                         'quota': {'nested': ['\x1b[31mquota\x00']}}]}
    broker, *_ = _local(tmp_path, script={('docker', 'exec'): (0, json.dumps(body))})
    clean = broker.read('sessions', {'runtime': 'claude', 'since': 0})['sessions'][0]
    assert clean['model'] == 'sk-[redacted]'
    assert clean['sideModel'] == [{'model': 'sk-ant-[redacted]', 'tokens': 7}]
    assert clean['quota'] == {'nested': ['␛[31mquota']}
    assert clean['tokens'] == body['sessions'][0]['tokens'] and clean['path'] == '/ordinary/session.jsonl'


@pytest.mark.parametrize('verb', ['restart', 'stop'])
def test_local_gate_requires_fresh_complete_lifecycle_history(tmp_path, verb):
    clock = Clock()
    live = [hb(clock() - age) for age in (120, 90, 60, 30)]
    history = [msg(clock() - 7 * 86400, 'submitted implement for 0c1f9727')] + live
    def logs(argv, kw):
        return subprocess.CompletedProcess(argv, 0, '\n'.join('docker-stamp ' + text for _, text in history).encode(), b'')
    broker, runner, lines, _ = _local(tmp_path, tail=live, clock=clock, script={('docker', 'logs'): logs})
    plan = broker.plan(verb)
    assert plan.preconditions['lifecycle_open'] is False
    assert any(argv[argv.index('--tail') + 1] == '10000' for argv in runner.argvs('docker', 'logs'))
    # The stale-segment trap must never authorize a write using the older terminal.
    history[:] = history[:1]
    with pytest.raises(BrokerError) as exc:
        broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack='local-only')
    assert exc.value.code == 'gate_unknown(lifecycle)' and not runner.argvs('docker', verb)
    history.extend(live + [msg(clock() - 1, 'accepted question deadbeef')])
    with pytest.raises(BrokerError) as exc:
        broker.plan(verb)
    assert exc.value.code == 'gate_blocked'
    history.append(msg(clock(), 'answered deadbeef with 1 citation(s)'))
    plan = broker.plan(verb)
    assert broker.apply(plan.plan_id, plan.plan_id[:4], local_only_ack='local-only').outcome == 'applied'


def test_local_drain_missing_lifecycle_never_fires(tmp_path):
    clock = Clock()
    broker, runner, lines, _ = _local(tmp_path, tail=[hb(clock() - age) for age in (120, 90, 60, 30)], clock=clock,
                                    script={('docker', 'logs'): (0, '')})
    plan = broker.plan('drain-restart')
    broker.apply(plan.plan_id, plan.plan_id[:4])
    for offset in (1, 2, 3, 4): lines.append(hb(clock() + offset))
    clock.advance(31)
    assert 'drain_rearmed' in broker.tick()
    assert broker._drain.armed is not None and not runner.argvs('docker', 'restart')


@pytest.mark.parametrize("failure", [None, "first", "history", "stale"])
def test_mac_empty_history_requires_two_successful_current_reads(tmp_path, failure):
    clock = Clock()
    live = [hb(clock() - age) for age in (120, 90, 60, 30)]
    def logs(argv, kw):
        limit = argv[argv.index("--tail") + 1]
        if failure == ("first" if limit == "200" else "history"):
            return subprocess.CompletedProcess(argv, 1, b"", b"unreadable")
        rows = live[:1] if failure == "stale" and limit == "10000" else live
        return subprocess.CompletedProcess(argv, 0, "\n".join("docker-stamp " + t for _, t in rows).encode(), b"")
    runner = RecordingRunner(_docker_script())
    runner.script[("docker", "logs")] = logs
    broker = LocalDockerBroker("imd-worker", run=runner, audit_path=tmp_path / "audit.jsonl", now=clock, offline=True, seat=420)
    result = broker.read("gate")
    if failure is None:
        assert result["safe"] and result["lifecycle_open"] is False
    else:
        assert result["unknown"] == "lifecycle" and not result["safe"]
