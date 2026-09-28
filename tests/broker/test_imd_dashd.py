"""``imd_dashd/imd_dashd.py`` -- the root broker end to end over ``socket.socketpair()`` and a scripted host.

Spec §11 protocol (single-use plans, one write in flight, apply returns on exit, verify separate), §4.1
trust boundaries (peer uid, posture), §13 audit contents. Mutation proofs 10, 25, 26, 27, 32, 33, 34 plus
``test_verify_times_out_to_false_not_null``, ``test_child_posture_unavailable_refuses_runtime_verbs``,
``test_plan_expires_after_60s`` and the stdlib/compileall guards. Sections are appended task by task
(6.8 transport, 6.9 reads, 6.10 plan/apply, 6.11 verify + transient verbs, 6.12 orphans + drain, 6.17 guards).
"""
from __future__ import annotations

import json
import os
import socket
import struct
import shutil
import subprocess
from pathlib import Path

import pytest

from imd_dashd import imd_dashd as broker_mod
from imd_dashd.imd_dashd import (
    BROKER_IDLE_EXIT_S, DOCTOR_MIN_INTERVAL_S, KILL_GRACE_S, PLAN_TTL_S, READ_COUNT_FLUSH_S, VERIFY_WITHIN_S, VERSION, PlanError,
    PlanStore, listener_from_systemd, peer_uid,
)
from tests.broker._harness import (
    DASH_UID, IP_DENY, NOW, PRIVATE_KEY, PUBLIC_KEY, PYTHON, Clock, Journal, audit_lines, call, hb, idle_window, make_broker,
    msg, projection_child, transient, write_fake_proc,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat" / "broker"


# ==== Task 6.8: transport, peer check, plan store ============================================================


def test_broker_rejects_foreign_peer(tmp_path):
    # mutation proof 10: SO_PEERCRED uid != imd-dash -> peer_refused, audited, no child spawned
    broker, runner, _journal, _clock, audit = make_broker(tmp_path)
    before = len(runner.calls)
    response = call(broker, "ping", peer_uid=1000)                      # the worker uid
    assert response == {"ok": False, "error": "peer_refused", "detail": {"peer_uid": 1000}}
    assert call(broker, "restart", {"offline": False}, peer_uid=0)["error"] == "peer_refused"   # even root
    assert len(runner.calls) == before
    assert audit_lines(audit)[-1]["phase"] == "refused" and audit_lines(audit)[-1]["outcome"] == "peer_refused"
    # and over a real socketpair, the uid the kernel reports decides -- the line is never even read
    broker._peer_uid_of = lambda conn: 1000
    ours, theirs = socket.socketpair()
    ours.sendall(b'{"v":1,"verb":"ping","args":{}}\n')
    broker.serve_connection(theirs)
    assert json.loads(ours.recv(4096))["error"] == "peer_refused"
    ours.close()


def test_serve_connection_round_trip_over_socketpair(tmp_path):
    broker, _runner, _journal, _clock, _audit = make_broker(tmp_path)
    ours, theirs = socket.socketpair()
    ours.sendall(b'{"v":1,"verb":"ping","args":{}}\n')
    broker.serve_connection(theirs)
    raw = ours.recv(65536)
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    data = json.loads(raw)["data"]
    assert data["version"] == VERSION == "imd-dashd 0.1.0"
    # contract §C.11 ping shape plus the additive "drain" dict (deviation 13: WP7 renders control.drain from it)
    assert set(data) == {"pid", "version", "uptime_s", "drain_armed", "in_flight", "posture_ok", "drain"}
    assert data["posture_ok"] is True and data["in_flight"] is None and data["drain_armed"] is False and data["drain"] is None
    # a malformed line is bad_request, never a crash
    ours2, theirs2 = socket.socketpair()
    ours2.sendall(b"garbage\n")
    broker.serve_connection(theirs2)
    assert json.loads(ours2.recv(4096))["error"] == "bad_request"


def test_bad_verb_and_bad_args_are_refused_and_audited_by_name_only(tmp_path):
    broker, _runner, _journal, _clock, audit = make_broker(tmp_path)
    assert call(broker, "tier-set", {"model": "x"})["error"] == "bad_verb"          # spec §11: not a verb
    assert call(broker, "restart", {"offline": "yes"})["error"] == "bad_args"
    assert call(broker, "audit-tail", {})["error"] == "bad_args"
    lines = audit_lines(audit)
    assert [ln["outcome"] for ln in lines[-3:]] == ["bad_verb", "bad_args", "bad_args"]
    assert lines[-2]["args"] == {"names": ["offline"]}                              # names, never values


def test_peer_uid_unpacks_the_ucred_struct_and_listener_reads_listen_fds(monkeypatch):
    class Conn:
        def getsockopt(self, level, opt, size):
            assert level == socket.SOL_SOCKET and size == struct.calcsize("3i")
            return struct.pack("3i", 4242, 1001, 1001)

    assert peer_uid(Conn()) == 1001
    monkeypatch.delenv("LISTEN_FDS", raising=False)
    assert listener_from_systemd() is None
    monkeypatch.setenv("LISTEN_FDS", "2")
    assert listener_from_systemd() is None
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("LISTEN_PID", str(os.getpid() + 1))
    assert listener_from_systemd() is None                                          # not our pid


def test_plan_store_ids_are_single_use_and_expire():
    # spec §11: random 16-hex plan ids, valid PLAN_TTL_S = 60, consumed exactly once
    assert PLAN_TTL_S == 60
    store = PlanStore(now=lambda: NOW)
    created = store.create("restart", {}, ["systemctl", "restart", "--no-block", "imd-worker.service"], {}, None, {})
    assert len(created.plan_id) == 16 and int(created.plan_id, 16) >= 0 and created.expires == NOW + 60
    assert store.peek(created.plan_id) is created
    store.consume(created.plan_id, NOW + 1)
    with pytest.raises(PlanError) as exc:
        store.consume(created.plan_id, NOW + 2)
    assert exc.value.code == "plan_spent"
    with pytest.raises(PlanError) as exc:
        store.consume("0000000000000000", NOW)
    assert exc.value.code == "unknown_plan"
    late = store.create("stop", {}, [], {}, None, {})
    with pytest.raises(PlanError) as exc:
        store.consume(late.plan_id, NOW + 61)
    assert exc.value.code == "plan_expired" and exc.value.detail["expired_at"] == "2026-09-21T14:14:20Z"
    store.purge(NOW + 200)
    assert store.peek(created.plan_id) is None and store.peek(late.plan_id) is None


def test_idle_exit_and_shutdown_without_a_drain(tmp_path):
    # spec §12.1: the broker exits after BROKER_IDLE_EXIT_S unless a drain is armed or a write is in flight
    broker, _runner, _journal, clock, _audit = make_broker(tmp_path)
    assert BROKER_IDLE_EXIT_S == 600
    assert broker.idle_exit_due(clock() + 599) is False and broker.idle_exit_due(clock() + 601) is True
    call(broker, "ping")
    assert broker.idle_exit_due(clock() + 601) is True                              # ping at NOW; still idle 601 s later
    broker.shutdown()
    assert broker.stop_requested is True


def test_read_verbs_are_audited_as_counts_only(tmp_path):
    # spec §11 "Read verbs (no gating; audited as counts only)": one hourly counts line, never a line per read (deviation 16)
    broker, _runner, _journal, clock, audit = make_broker(tmp_path)
    for _ in range(3):
        call(broker, "outbox")
    for _ in range(2):
        call(broker, "ping")
    assert READ_COUNT_FLUSH_S == 3600
    broker.tick(clock() + 1800)
    assert not audit.path.exists()                                                   # no line per read, none before the hour
    broker.tick(clock() + 3601)
    lines = audit_lines(audit)
    assert len(lines) == 1 and lines[0]["phase"] == "reads" and lines[0]["verb"] is None and lines[0]["outcome"] == "counts"
    assert lines[0]["args"] == {"counts": {"outbox": 3, "ping": 2}}                  # counts only, never arg values
    broker.tick(clock() + 7300)
    assert len(audit_lines(audit)) == 1                                              # nothing read since: no empty line
    call(broker, "ping")
    broker.shutdown()                                                                # idle exit / SIGTERM flushes the rest
    assert audit_lines(audit)[-1]["args"] == {"counts": {"ping": 1}}
# ==== Task 6.9: read verbs ================================================================================


from imd_dashd.child_unit import CHILD_ENV, transient_argv  # noqa: E402


def test_child_posture_unavailable_refuses_runtime_verbs(tmp_path):
    # spec §4.1b: if IPAddressDeny cannot be read, runtime-executing verbs are refused, in-process reads still work
    broker, runner, _journal, _clock, _audit = make_broker(
        tmp_path, script={("systemctl", "show", "imd-worker.service", "-p", "IPAddressDeny", "--value"): (1, "")})
    assert broker.ip_address_deny is None and call(broker, "ping")["data"]["posture_ok"] is False
    for verb, args in (("status", {}), ("whoami", {}), ("skills", {}), ("tools", {}), ("seat", {}),
                       ("sessions", {"since": 0.0, "runtime": "codex"})):
        assert call(broker, verb, args)["error"] == "child_posture_unavailable", verb
    assert runner.argvs("systemd-run") == []
    assert call(broker, "outbox") == {"ok": True, "data": {"files": 0}}


def test_status_read_runs_a_transient_unit_with_the_worker_posture(tmp_path):
    text = "config  /home/imd-worker/.identitymd/config.json\nserver  https://api.imd.fun\ntoken   7\n"
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, script={("systemd-run",): lambda argv, kw: transient(text)})
    data = call(broker, "status")["data"]
    assert data == {"lines": text.splitlines(), "rc": 0, "unit": "imd-dash-status-1"}
    (argv, kw), = [(a, k) for a, k in runner.calls if a and a[0] == "systemd-run"]
    assert argv == transient_argv("status", 1, ["imd", "status"], ip_address_deny=IP_DENY, runtime_max_s=30)
    assert kw["timeout"] == 45 and "env" not in kw                                  # env travels as --setenv, not to systemd-run


def test_seat_projection_passes_the_canary_and_whoami_is_cached(tmp_path):
    from imd_dashd.projection import project
    payload = project(json.loads((FIXTURES / "projection_ok.json").read_text()), None)
    broker_dir = broker_mod.BROKER_DIR
    broker, runner, _journal, _clock, _audit = make_broker(
        tmp_path, script={(PYTHON, "-I", os.path.join(broker_dir, "projection.py")): lambda argv, kw: projection_child(payload)})
    data = call(broker, "seat")["data"]
    assert data["deviceKey"] == PUBLIC_KEY and data["tokenId"] == 7 and PRIVATE_KEY not in json.dumps(data)
    call(broker, "seat")
    assert len([a for a in runner.argvs("systemd-run") if a[-1] == "whoami"]) == 1  # once per broker life
    projections = [(a, k) for a, k in runner.calls if a[:2] == [PYTHON, "-I"] and a[2].endswith("projection.py")]
    assert len(projections) == 2                                                     # the projection itself is not cached
    argv, kw = projections[0]
    assert argv[3:] == ["--config", "/home/imd-worker/.identitymd/config.json", "--tools", "/home/imd-worker/.identitymd/tools.json"]
    assert kw["user"] == "imd-worker" and kw["env"] == CHILD_ENV and kw["timeout"] == 10


def test_outbox_unreadable_is_an_error_not_zero(tmp_path):
    broker, _runner, _journal, _clock, _audit = make_broker(tmp_path, script={("ls", "-1A"): (2, "")})
    assert call(broker, "outbox") == {"ok": False, "error": "unreadable", "detail": {"what": "outbox"}}
    # one unacknowledged submit frame (fixture broker/outbox_pending.json): the broker counts names, never reads bodies
    lease = json.loads((FIXTURES / "outbox_pending.json").read_text())["leaseId"]
    broker2, _r, _j, _c, _a = make_broker(tmp_path / "b", script={("ls", "-1A"): (0, f"{lease}.json\n")})
    assert call(broker2, "outbox")["data"] == {"files": 1}


def test_work_stat_parses_the_find_listing(tmp_path):
    fixture = json.loads((FIXTURES / "work_stat.json").read_text())
    broker, runner, _journal, _clock, _audit = make_broker(
        tmp_path, script={("find",): (0, fixture["find_listing"]), ("du", "-sb"): (0, f"{fixture['du_bytes']}\t/home/imd-worker/.identitymd/work\n")})
    assert call(broker, "work-stat")["data"] == fixture["expected"]
    find_argv = runner.argvs("find")[0]
    assert find_argv == ["find", "/home/imd-worker/.identitymd/work", "-mindepth", "1", "-maxdepth", "4", "-printf", "%y\t%T@\t%P\n"]
    assert [k["user"] for a, k in runner.calls if a[0] in ("find", "du")] == ["imd-worker", "imd-worker"]


def test_sessions_runs_the_summariser_as_a_transient_unit_and_redacts_messages(tmp_path):
    body = {"sessions": [{"path": "x", "apiErrors": [{"status": 401, "message": "Incorrect API key provided: sk-svcac1234abcd", "atUtc": "t"}]}],
            "skipped": {"oversize": 0}}
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, script={("systemd-run",): lambda argv, kw: transient(json.dumps(body))})
    data = call(broker, "sessions", {"since": 1790000000.5, "runtime": "codex"})["data"]
    assert data["sessions"][0]["apiErrors"][0]["message"] == "Incorrect API key provided: sk-[redacted]"
    argv = runner.argvs("systemd-run")[0]
    assert argv[argv.index("--") + 1:] == [PYTHON, "-I", os.path.join(broker_mod.BROKER_DIR, "summarise_codex.py"), "--root",
                                          "/home/imd-worker/.codex/sessions", "--since", "1790000000.5", "--work-root",
                                          "/home/imd-worker/.identitymd/work"]
    assert "-p" in argv and "RuntimeMaxSec=60" in argv


def test_hints_stat_and_auth_mtime_never_open_the_credential_file(tmp_path):
    broker, runner, _journal, _clock, _audit = make_broker(
        tmp_path, script={("stat", "-c"): (0, "1791 1790400000\n"), ("sha256sum",): (0, "3f2a9b8c7d6e5f40 /home/imd-worker/.codex/AGENTS.md\n")})
    hints = call(broker, "hints-stat")["data"]
    assert hints == {"path": "/home/imd-worker/.codex/AGENTS.md", "mtimeUtc": "2026-09-26T05:20:00Z", "bytes": 1791, "sha8": "3f2a9b8c"}
    auth = call(broker, "auth-mtime")["data"]
    assert auth == {"path": "/home/imd-worker/.codex/auth.json", "mtimeUtc": "2026-09-26T05:20:00Z"}
    auth_calls = [a for a, _ in runner.calls if "/home/imd-worker/.codex/auth.json" in a]
    assert auth_calls == [["stat", "-c", "%s %Y", "/home/imd-worker/.codex/auth.json"]]    # stat only, never cat/sha256sum


def test_gate_read_is_a_preview_with_the_gate_result_shape(tmp_path):
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    data = call(broker, "gate", {"offline": False})["data"]
    assert data["safe"] is True and data["plane"]["mode"] == "plane+local" and data["outbox_files"] == 0
    assert runner.argvs(PYTHON, "-I") and runner.argvs("ls", "-1A") and runner.argvs("systemctl", "is-active")
    assert call(broker, "gate", {"offline": True})["data"]["plane"]["mode"] == "local-only"


def test_standing_url_falls_back_to_the_projection_token(tmp_path):
    # WP9's imd-dashd.service runs the broker without --seat: the seat id comes from the canary-checked projection,
    # so the plane half of the gate (spec §11 (b)) is read in production instead of every gate being local-only
    from imd_dashd.projection import project
    payload = project(json.loads((FIXTURES / "projection_ok.json").read_text()), None)
    child = (PYTHON, "-I", os.path.join(broker_mod.BROKER_DIR, "projection.py"))
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, seat=None, script={child: lambda argv, kw: projection_child(payload)})
    assert call(broker, "gate", {"offline": False})["data"]["plane"]["mode"] == "plane+local"
    standing = [a for a in runner.argvs(PYTHON, "-I") if a[2].endswith("gate.py")]
    assert standing[-1][-1] == "https://api.imd.fun/seats/7/standing"
    call(broker, "gate", {"offline": False})
    assert len([a for a in runner.argvs(PYTHON, "-I") if a[2].endswith("projection.py")]) == 1       # learned once
# ==== Task 6.10: plan -> apply for restart, stop, start, enable/disable, cancel-drain ==========================


def test_plan_id_is_single_use(tmp_path):
    # mutation proof 25: a consumed plan id cannot be applied twice
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    assert len(plan["plan_id"]) == 16 and plan["single_use"] is True
    first = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert first["ok"] and first["result"]["outcome"] == "applied"
    second = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert second == {"ok": False, "error": "plan_spent", "detail": {"plan_id": plan["plan_id"]}}
    assert len(runner.argvs("systemctl", "restart")) == 1


def test_plan_expires_after_60s(tmp_path):
    # spec §11: plan ids are valid 60 s; an injected clock at 61 s -> plan_expired
    broker, runner, journal, clock, _audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    assert plan["expires_at"] == "2026-09-21T14:14:20Z"                              # NOW + 60
    clock.advance(61)
    late = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert late["error"] == "plan_expired" and late["detail"]["plan_id"] == plan["plan_id"]
    assert runner.argvs("systemctl", "restart") == []
    journal.add(*[hb(clock() - age) for age in (100, 70, 40, 10)])                  # the seat kept idling meanwhile
    plan = call(broker, "restart", {"offline": False})["plan"]
    clock.advance(60)                                                                # exactly the TTL still applies
    journal.add(hb(clock() - 40), hb(clock() - 10))
    assert call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["ok"]


def test_bad_confirm_and_unknown_plan(tmp_path):
    broker, _runner, _journal, _clock, _audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    assert call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": "zzzz"})["error"] == "bad_confirm"
    assert call(broker, "apply", {"plan_id": "0123456789abcdef", "confirm": "0123"})["error"] == "unknown_plan"
    assert call(broker, "apply", {"plan_id": "not-a-plan", "confirm": "not-"})["error"] == "unknown_plan"


def test_second_write_while_in_flight_is_refused(tmp_path):
    # mutation proof 26: while systemctl runs, any other plan/apply of a write verb -> busy {verb, plan_id, since}
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    other = call(broker, "stop", {"offline": False})["plan"]
    seen: list[dict] = []

    def slow_restart(argv, kw):
        seen.append(call(broker, "restart", {"offline": False}))                     # a second TUI plans …
        seen.append(call(broker, "apply", {"plan_id": other["plan_id"], "confirm": other["plan_id"][:4]}))   # … or applies
        seen.append(call(broker, "ping"))                                            # reads are never blocked
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    runner.script[("systemctl", "restart")] = slow_restart
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert result["ok"] and result["result"]["outcome"] == "applied"
    assert seen[0]["error"] == "busy" and seen[1]["error"] == "busy"
    assert seen[0]["detail"] == {"verb": "restart", "plan_id": plan["plan_id"], "since": "2026-09-21T14:13:20Z"}
    assert seen[2]["ok"] and seen[2]["data"]["in_flight"] == seen[0]["detail"]
    assert len(runner.argvs("systemctl", "restart")) == 1
    assert call(broker, "ping")["data"]["in_flight"] is None                         # released on exit


def test_apply_returns_before_verify_completes(tmp_path):
    # mutation proof 27: apply returns when systemctl exits -- it never waits for `admitted` or even `runtimes:`
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    calls_before = len(runner.calls)
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    assert set(result) == {"outcome", "exit_code", "cursor_before", "audit_seq", "preconditions"}
    assert result["outcome"] == "applied" and result["exit_code"] == 0 and result["cursor_before"].startswith("s=")
    assert "verified" not in result and "connected" not in result
    during_apply = [argv for argv, _ in runner.calls[calls_before:]]
    assert not any("--after-cursor" in argv for argv in during_apply)              # no post-apply journal wait inside apply
    assert during_apply[-1] == ["systemctl", "restart", "--no-block", "imd-worker.service"]      # systemctl is the LAST thing apply does


def test_restart_plan_has_the_spec_shape(tmp_path):
    broker, _runner, _journal, _clock, audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    assert plan["verb"] == "restart" and plan["argv"] == ["systemctl", "restart", "--no-block", "imd-worker.service"]
    assert set(plan["preconditions"]) == {"idle_beats", "idle_beats_required", "newest_heartbeat_age_s", "plane",
                                          "last_lifecycle_line", "lifecycle_open", "outbox_files", "unit_active",
                                          "graceful_stop_possible"}
    assert plan["preconditions"]["plane"] == {"mode": "plane+local", "running": 0, "as_of": "2026-09-21T14:13:19.600Z", "standing_age_s": 0.4}
    assert plan["preconditions"]["idle_beats"] == 6 and plan["preconditions"]["outbox_files"] == 0
    assert plan["preconditions"]["last_lifecycle_line"].endswith("submitted implement for 0c1f9727")
    assert plan["inverse"] == {"verb": "stop", "args": {}}
    assert plan["verify"] == {"verified_when": ["shutting down", "runtimes:"], "within_s": 30, "connected_when": "admitted (session",
                              "reported_separately": True}
    assert plan["warning"].startswith("a task assigned in the ~1–5 s") and plan["restart_required_after"] is False
    assert audit_lines(audit)[-1]["phase"] == "plan" and audit_lines(audit)[-1]["preconditions"] == plan["preconditions"]


def test_plan_restart_is_refused_while_a_task_runs(tmp_path):
    journal = Journal(idle_window(NOW)[:-1] + [hb(NOW - 11, "1 task running")])
    broker, runner, _journal, _clock, audit = make_broker(tmp_path, journal=journal)
    refused = call(broker, "restart", {"offline": False})
    assert refused["error"] == "gate_blocked" and refused["detail"]["reason"].startswith("task running")
    assert runner.argvs("systemctl", "restart") == []
    assert audit_lines(audit)[-1]["outcome"] == "gate_blocked"


def test_apply_re_reads_the_gate_fresh(tmp_path):
    # spec §11: "apply re-reads everything fresh -- cached preconditions are not a gate"
    broker, runner, journal, clock, _audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    clock.advance(3)
    journal.add(msg(clock() - 1, "accepted implement 3aa1c610 — src/ (max 60 turns)"))     # assigned between plan and apply
    refused = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert refused["error"] == "gate_blocked" and refused["detail"]["reason"] == "task running 3aa1c610 · 0:01"
    assert runner.argvs("systemctl", "restart") == []
    assert len(runner.argvs(PYTHON, "-I")) == 2                                      # one standing read at plan, one FRESH at apply


def test_force_requires_the_running_node8_twice_and_a_graceful_unit(tmp_path):
    journal = Journal(idle_window(NOW)[:-1] + [hb(NOW - 11, "1 task running"),
                                              msg(NOW - 42, "accepted implement 0c1f9727 — src/ (max 60 turns)")])
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, journal=journal)
    assert call(broker, "restart", {"offline": False, "force_node8": "deadbeef"})["error"] == "force_node8_mismatch"
    plan = call(broker, "restart", {"offline": False, "force_node8": "0c1f9727"})["plan"]
    assert plan["preconditions"]["lifecycle_open"] is True                            # (a)-(c) bypassed, shown honestly
    assert call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["error"] == "force_node8_mismatch"
    plan = call(broker, "restart", {"offline": False, "force_node8": "0c1f9727"})["plan"]
    applied = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4], "force_node8": "0c1f9727"})
    assert applied["ok"] and len(runner.argvs("systemctl", "restart")) == 1
    # force never bypasses (d): a pending outbox still blocks
    runner.script[("ls", "-1A")] = (0, "16a4df90-5555-4555-8555-555555555555.json\n")
    assert call(broker, "restart", {"offline": False, "force_node8": "0c1f9727"})["error"] == "gate_blocked"
    # and force is disabled when the unit cannot stop gracefully
    ungraceful, _r, _j, _c, _a = make_broker(tmp_path / "b", journal=journal,
                                              script={("systemctl", "show", "imd-worker.service", "-p", "KillMode"): (0, "KillMode=process\nTimeoutStopUSec=10s\n")})
    assert ungraceful.graceful_stop_possible is False
    assert call(ungraceful, "restart", {"offline": False, "force_node8": "0c1f9727"})["error"] == "force_disabled"


def test_start_enable_disable_plans_and_apply(tmp_path):
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    for verb, argv, inverse in (("start", ["systemctl", "start", "--no-block", "imd-worker.service"], "stop"),
                                ("enable-boot", ["systemctl", "enable", "imd-worker.service"], "disable-boot"),
                                ("disable-boot", ["systemctl", "disable", "imd-worker.service"], "enable-boot")):
        plan = call(broker, verb, {})["plan"]
        assert plan["argv"] == argv and plan["inverse"]["verb"] == inverse
        result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
        assert result["outcome"] == "applied" and runner.argvs(*argv[:2]) == [argv]


def test_cancel_drain_without_a_drain_is_refused(tmp_path):
    broker, _runner, _journal, _clock, _audit = make_broker(tmp_path)
    assert call(broker, "cancel-drain", {})["error"] == "drain_not_armed"


def test_drain_restart_can_be_armed_while_a_task_runs(tmp_path):
    # spec §11 drain-restart row: "plain confirm to arm; G at fire time" -- waiting out a running task is the point
    journal = Journal(idle_window(NOW)[:-1] + [hb(NOW - 11, "1 task running"),
                                              msg(NOW - 42, "accepted implement 0c1f9727 — src/ (max 60 turns)")])
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, journal=journal)
    planned = call(broker, "drain-restart", {"offline": False})
    assert planned["ok"] is True and planned["plan"]["preconditions"]["lifecycle_open"] is True     # the preview, not a gate
    plan = planned["plan"]
    applied = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert applied["result"]["outcome"] == "armed" and runner.argvs("systemctl", "restart") == []
    assert call(broker, "restart", {"offline": False})["error"] == "drain_already_armed"  # cancel first
# ==== Task 6.11: verify, doctor, skills-set ====================================================================


def _applied_restart(tmp_path, journal=None):
    broker, runner, journal, clock, audit = make_broker(tmp_path, journal=journal)
    plan = call(broker, "restart", {"offline": False})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    return broker, runner, journal, clock, audit, plan["plan_id"]


def test_restart_verified_without_admitted(tmp_path):
    # mutation proof 32: `shutting down` -> `runtimes:` +0.3 s = verified; `admitted` is a separate fact
    broker, _runner, journal, clock, audit, plan_id = _applied_restart(tmp_path)
    clock.advance(1)
    journal.add(msg(clock() - 0.6, "shutting down"),
                msg(clock() - 0.3, "runtimes: codex codex-cli 0.157.0 (using codex, as asked)"),
                msg(clock() - 0.2, "connected to api.imd.fun"))
    clock.advance(3)
    data = call(broker, "verify", {"plan_id": plan_id})["data"]
    assert data["verified"] is True
    assert isinstance(data["connected"], str) and data["connected"].startswith("pending (reconnecting since ")
    assert data["verify_lines"][0].endswith("Z shutting down") and "runtimes: codex" in data["verify_lines"][1]
    assert data["cursor_after"].startswith("s=") and data["elapsed_s"] == 4.0 and data["reason"] is None
    # `admitted` arrives 70 s later (a redeploy wave, fill5 §7) -> connected flips, verified never changed
    clock.advance(70)
    journal.add(msg(clock() - 1, "admitted (session 1a2b3c4d)"))
    data = call(broker, "verify", {"plan_id": plan_id})["data"]
    assert data["verified"] is True and data["connected"] is True
    phases = [(ln["phase"], ln["verified"], ln["connected"]) for ln in audit_lines(audit) if ln["phase"] == "verify"]
    assert phases[0][1] is True and str(phases[0][2]).startswith("pending") and phases[-1][2] is True


def test_verify_times_out_to_false_not_null(tmp_path):
    # header Review Focus 5: nothing for 30 s after apply -> verified False with a reason, never null forever
    broker, _runner, _journal, clock, _audit, plan_id = _applied_restart(tmp_path)
    assert VERIFY_WITHIN_S == 30
    clock.advance(29)
    assert call(broker, "verify", {"plan_id": plan_id})["data"]["verified"] is None
    clock.advance(2)
    data = call(broker, "verify", {"plan_id": plan_id})["data"]
    assert data["verified"] is False and data["reason"] == "no shutting down within 30 s"
    assert call(broker, "ping")["data"]["in_flight"] is None                         # the write lock was released at apply
    assert call(broker, "verify", {"plan_id": "0123456789abcdef"})["error"] == "unknown_plan"


def test_verify_late_runtimes_is_false_and_stop_needs_inactive(tmp_path):
    broker, runner, journal, clock, _audit, plan_id = _applied_restart(tmp_path)
    journal.add(msg(clock() + 1, "shutting down"), msg(clock() + 35, "runtimes: codex codex-cli 0.157.0 (using codex)"))
    clock.advance(40)
    data = call(broker, "verify", {"plan_id": plan_id})["data"]
    assert data["verified"] is False and data["reason"].startswith("runtimes: 34.0 s after shutting down")
    # stop: `shutting down` + ActiveState=inactive
    plan = call(broker, "stop", {"offline": False})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    journal.add(msg(clock() + 1, "shutting down"))
    clock.advance(2)
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is None   # still active
    runner.script[("systemctl", "is-active", "imd-worker.service")] = (3, "inactive\n")
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is True and data["connected"] is None


def test_enable_boot_verify_uses_is_enabled(tmp_path):
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    plan = call(broker, "enable-boot", {})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False and data["reason"] == "systemctl is-enabled says disabled"   # the scripted host still says disabled
    runner.script[("systemctl", "is-enabled", "imd-worker.service")] = (0, "enabled\n")
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is True


def _wait(broker, plan_id):
    broker._threads[plan_id].join(timeout=5)
    assert not broker._threads[plan_id].is_alive()


def test_doctor_apply_returns_started_and_verify_carries_redacted_output(tmp_path):
    lines = "imd doctor · daemon 0.1.0+5bfa8261\n✓ codex run answered in 2.3s ($0.114 estimated)\n✗ memory 3.7 GB\n"
    broker, runner, _journal, clock, _audit = make_broker(tmp_path, script={("systemd-run",): lambda argv, kw: transient(lines, rc=1)})
    plan = call(broker, "doctor", {})["plan"]
    assert plan["argv"] == ["imd", "doctor"] and plan["inverse"] is None
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    assert result["outcome"] == "started" and result["unit"] == "imd-dash-doctor-1"
    _wait(broker, plan["plan_id"])
    (argv, kw), = [(a, k) for a, k in runner.calls if a and a[0] == "systemd-run"]
    assert argv == transient_argv("doctor", 1, ["imd", "doctor"], ip_address_deny=IP_DENY, runtime_max_s=120)
    assert kw["timeout"] == 135
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False and data["reason"] == "exit 1"
    assert "$" not in "".join(data["verify_lines"]) and any("memory 3.7 GB" in ln for ln in data["verify_lines"])
    assert "0.114" not in "".join(data["verify_lines"])                              # the figure itself goes, not just the `$`
    assert call(broker, "ping")["data"]["in_flight"] is None
    # spec §11: never on a timer; >= 10 min apart
    assert DOCTOR_MIN_INTERVAL_S == 600
    assert call(broker, "doctor", {})["error"] == "doctor_too_soon"
    clock.advance(601)
    assert call(broker, "doctor", {})["ok"]


def test_doctor_and_skills_set_need_the_child_posture(tmp_path):
    broker, runner, _journal, _clock, _audit = make_broker(
        tmp_path, script={("systemctl", "show", "imd-worker.service", "-p", "IPAddressDeny", "--value"): (1, "")})
    assert call(broker, "doctor", {})["error"] == "child_posture_unavailable"
    assert call(broker, "skills-set", {"skill_id": "oracle-assess", "on": False})["error"] == "child_posture_unavailable"
    assert runner.argvs("systemd-run") == []
    assert call(broker, "restart", {"offline": False})["ok"]                          # systemctl needs no runtime child


def test_bad_skill_id_is_refused_and_not_echoed(tmp_path):
    # mutation proof 33: a skill_id with a space or `;` never reaches argv, and the audit never echoes it
    broker, runner, _journal, _clock, audit = make_broker(tmp_path)
    for bad in ("oracle assess", "oracle;rm -rf /", "../etc", "Oracle-Assess"):
        assert call(broker, "skills-set", {"skill_id": bad, "on": False}) == {"ok": False, "error": "bad_skill_id", "detail": {}}
    assert runner.argvs("systemd-run") == []
    text = (tmp_path / "audit.jsonl").read_text()
    assert "oracle assess" not in text and "rm -rf" not in text and "../etc" not in text
    assert audit_lines(audit)[-1]["args"] == {"skill_id": "<refused>", "on": False}
    assert audit_lines(audit)[-1]["outcome"] == "bad_skill_id"


def test_skills_set_is_a_transient_add_or_remove_and_marks_restart_required(tmp_path):
    host = {"listing": "31 skills offered, 31 on here.\non oracle-assess — needs network\non implement-component — needs network\n"}

    def children(argv, kw):
        if argv[-1] == "skills":
            return transient(host["listing"])
        if argv[-2:] == ["remove", "oracle-assess"]:                    # the scripted daemon honours the remove only
            host["listing"] = host["listing"].replace("31 on here.\non oracle-assess", "30 on here.\noff oracle-assess")
        return transient("")

    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, script={("systemd-run",): children})
    assert call(broker, "skills-set", {"skill_id": "not-offered", "on": False})["error"] == "skill_not_listed"
    plan = call(broker, "skills-set", {"skill_id": "oracle-assess", "on": False})["plan"]
    assert plan["argv"] == ["imd", "skills", "remove", "oracle-assess"] and plan["restart_required_after"] is True
    assert plan["inverse"] == {"verb": "skills-set", "args": {"skill_id": "oracle-assess", "on": True}}
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    assert result["outcome"] == "started"
    _wait(broker, plan["plan_id"])
    unit_argv = next(a for a in runner.argvs("systemd-run") if a[-4:] == ["imd", "skills", "remove", "oracle-assess"])
    assert "--unit=imd-dash-skills-set-2" in unit_argv
    assert runner.argvs("systemd-run")[-1][-2:] == ["imd", "skills"]                 # spec §11 skills row: verify by re-listing
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is True    # the re-listing says `off`
    plan = call(broker, "skills-set", {"skill_id": "oracle-assess", "on": True})["plan"]
    assert plan["argv"] == ["imd", "skills", "add", "oracle-assess"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    _wait(broker, plan["plan_id"])
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False and data["reason"] == "re-listing disagrees"    # exit 0, but the listing still says off
# ==== Task 6.12: orphans, kill-orphans, drain-restart, audit contents =========================================


from imd_dashd.imd_dashd import read_procs, select_orphans  # noqa: E402


def _orphan_broker(tmp_path):
    spec = json.loads((FIXTURES / "procs_orphan.json").read_text())
    write_fake_proc(tmp_path / "proc", spec)
    broker, runner, journal, clock, audit = make_broker(tmp_path, clock=Clock(spec["now"]))
    return broker, runner, clock, audit, spec


def test_orphans_lists_candidates_with_every_pgid_member(tmp_path):
    broker, _runner, _clock, _audit, spec = _orphan_broker(tmp_path)
    procs = read_procs(str(tmp_path / "proc"), now=spec["now"])
    assert {p["pid"] for p in procs} == {p["pid"] for p in spec["procs"]}
    candidates = call(broker, "orphans")["data"]["candidates"]
    assert [c["pid"] for c in candidates] == [64876, 64877, 64884, 64885]           # uid 1000, outside the unit, > 1 h
    row = next(c for c in candidates if c["pid"] == 64877)
    assert set(row) == {"pid", "pgid", "uid", "cgroup", "ageS", "rssB", "cmd", "pgidMembers"}
    assert row["pgid"] == 64861 and row["ageS"] == 35 * 3600 and row["rssB"] == 16845 * 4096
    assert row["cgroup"] == "user.slice/user-0.slice/session-147.scope" and len(row["cmd"]) <= 80
    assert {m["pid"] for m in row["pgidMembers"]} == {64861, 64862, 64876, 64884, 64885}
    assert {m["uid"] for m in row["pgidMembers"] if m["pid"] in (64861, 64862)} == {0}
    # excluded: MainPID and its task child (unit cgroup), the imd-dash transient scope, the 10-minute probe
    assert select_orphans(procs, worker_uid=1000, min_age_s=3600) == candidates
    assert call(broker, "kill-orphans", {"pids": [98600]})["error"] == "bad_args"    # a live unit task is never a candidate


def test_kill_orphans_kills_individually_when_pgid_is_mixed(tmp_path):
    # mutation proof 34: pgid 64861 has a root `bash -c` that is no direct ancestor of a uid-1000 member -> never `kill -- -64861`
    broker, runner, clock, audit, _spec = _orphan_broker(tmp_path)
    plan = call(broker, "kill-orphans", {"pids": [64876, 64877, 64884, 64885]})["plan"]
    assert plan["preconditions"]["kill_mode_by_pgid"] == {"64861": "individual"}
    assert len(plan["preconditions"]["candidates"]) == 4 and plan["inverse"] is None
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    kills = runner.argvs("kill")
    assert kills == [["kill", "-TERM", "64876"], ["kill", "-TERM", "64877"], ["kill", "-TERM", "64884"], ["kill", "-TERM", "64885"]]
    assert ["kill", "-TERM", "--", "-64861"] not in kills
    assert result["outcome"] == "applied" and [k["mode"] for k in result["killed"]] == ["individual"] * 4
    assert audit_lines(audit)[-1]["preconditions"]["pids"] == [64876, 64877, 64884, 64885]
    # SIGKILL follows on the tick after KILL_GRACE_S for anything still alive (the fake /proc still lists them)
    assert KILL_GRACE_S == 10
    assert broker.tick(clock() + 5) == []
    events = broker.tick(clock() + 11)
    assert events == ["sigkill"] * 4 and runner.argvs("kill", "-KILL") == [["kill", "-KILL", str(p)] for p in (64876, 64877, 64884, 64885)]


def test_kill_orphans_group_kills_a_clean_pgid(tmp_path):
    spec = json.loads((FIXTURES / "procs_orphan.json").read_text())
    spec["procs"] = [p for p in spec["procs"] if p["pid"] != 64861]                 # drop the root bash -c: runuser leads
    for p in spec["procs"]:
        if p["pgid"] == 64861:
            p["pgid"] = 64862
    write_fake_proc(tmp_path / "proc", spec)
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path, clock=Clock(spec["now"]))
    plan = call(broker, "kill-orphans", {"pids": [64876, 64877, 64884, 64885]})["plan"]
    assert plan["preconditions"]["kill_mode_by_pgid"] == {"64862": "group"}
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    assert runner.argvs("kill") == [["kill", "-TERM", "--", "-64862"]]
    assert result["killed"] == [{"mode": "group", "pgid": 64862, "pids": [64876, 64877, 64884, 64885]}]


def test_kill_orphans_skips_a_pid_whose_cgroup_or_start_changed(tmp_path):
    broker, runner, _clock, _audit, spec = _orphan_broker(tmp_path)
    plan = call(broker, "kill-orphans", {"pids": [64885]})["plan"]
    # pid reuse between plan and apply: 64885 is now a fresh process (start time moved)
    for p in spec["procs"]:
        if p["pid"] == 64885:
            p["start_ticks"] += 35 * 3600 * 100 - 100
    write_fake_proc(tmp_path / "proc", spec)
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    assert result["killed"] == [] and result["skipped"] == [{"pid": 64885, "reason": "changed since plan"}]
    assert runner.argvs("kill") == []


def test_drain_restart_arms_rearms_and_fires_through_the_fresh_gate(tmp_path):
    broker, runner, journal, clock, audit = make_broker(tmp_path)
    plan = call(broker, "drain-restart", {"offline": False})["plan"]
    assert plan["inverse"] == {"verb": "cancel-drain", "args": {}}
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]
    assert result["outcome"] == "armed" and set(result["drain"]) == {"armedAtUtc", "idleBeats", "rearmed", "expiresAtUtc"}
    ping = call(broker, "ping")["data"]
    assert ping["drain_armed"] is True and ping["drain"] == result["drain"]          # the SEAT_BLOCK_KEYS["seat_control_drain"] dict
    assert call(broker, "restart", {"offline": False})["error"] == "drain_already_armed"
    assert call(broker, "drain-restart", {"offline": False})["error"] == "drain_already_armed"
    # two idle beats, then work: re-armed
    for _ in (1, 2):
        clock.advance(30)
        journal.add(hb(clock() - 1))
        broker.tick(clock())
    clock.advance(30)
    journal.add(hb(clock() - 1, "1 task running"))
    assert "drain_rearmed" in broker.tick(clock())
    # four idle beats -> fire -> fresh gate -> systemctl restart
    journal.add(msg(clock() - 0.5, "submitted implement for 4cf722c7"))
    events: list[str] = []
    for _ in range(4):
        clock.advance(30)
        journal.add(hb(clock() - 1))
        events = broker.tick(clock())
    assert "drain_fire" in events and runner.argvs("systemctl", "restart") == [["systemctl", "restart", "--no-block", "imd-worker.service"]]
    phases = [ln["phase"] for ln in audit_lines(audit)]
    assert phases.count("drain_armed") == 1 and phases.count("drain_rearmed") == 1 and phases.count("drain_fire") == 1
    assert phases[-1] == "apply" and call(broker, "ping")["data"]["drain_armed"] is False
    assert call(broker, "ping")["data"]["drain"] is None
    # the fired restart gets its verify line on a later tick (spec §11 drain row audit: "arm, each re-arm, fire, verify")
    clock.advance(1)
    journal.add(msg(clock() - 0.6, "shutting down"), msg(clock() - 0.3, "runtimes: codex codex-cli 0.157.0 (using codex, as asked)"))
    broker.tick(clock())
    lines = audit_lines(audit)
    assert [ln["phase"] for ln in lines][-3:] == ["drain_fire", "apply", "verify"] and lines[-1]["verified"] is True
    assert lines[-1]["plan_id"] == lines[-2]["plan_id"] == lines[-3]["plan_id"]


def test_refused_drain_fire_keeps_the_original_deadline(tmp_path):
    # spec §11 drain row: DRAIN_MAX_S caps the whole wait -- a fire refused by the fresh gate re-arms the SAME drain
    broker, runner, journal, clock, _audit = make_broker(tmp_path)
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    armed = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]["drain"]
    runner.script[("ls", "-1A")] = (0, "16a4df90-5555-4555-8555-555555555555.json\n")    # an unacked submit frame blocks (d)
    events: list[str] = []
    for _ in range(4):
        clock.advance(30)
        journal.add(hb(clock() - 1))
        events += broker.tick(clock())
    assert events == ["drain_fire", "drain_rearmed"] and runner.argvs("systemctl", "restart") == []
    again = call(broker, "ping")["data"]["drain"]
    assert again["armedAtUtc"] == armed["armedAtUtc"] and again["expiresAtUtc"] == armed["expiresAtUtc"] and again["rearmed"] == 1
    assert broker._drain.armed.plan_id == plan["plan_id"]
    assert broker.tick(NOW + 14400 + 1) == ["drain_expired"]


def test_drain_suspends_idle_exit_and_is_cancelled_or_lost(tmp_path):
    broker, _runner, _journal, clock, audit = make_broker(tmp_path)
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert broker.idle_exit_due(clock() + BROKER_IDLE_EXIT_S + 1) is False           # spec §11: idle-exit suspended while armed
    cancel = call(broker, "cancel-drain", {})["plan"]
    result = call(broker, "apply", {"plan_id": cancel["plan_id"], "confirm": cancel["plan_id"][:4]})["result"]
    assert result["outcome"] == "cancelled" and call(broker, "ping")["data"]["drain_armed"] is False
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    broker.shutdown()
    assert audit_lines(audit)[-1]["phase"] == "drain_lost" and broker.stop_requested is True


def test_drain_expires_after_four_hours(tmp_path):
    broker, _runner, _journal, clock, audit = make_broker(tmp_path)
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert broker.tick(clock() + 14400 + 1) == ["drain_expired"]
    assert audit_lines(audit)[-1]["phase"] == "drain_expired"


def test_audit_has_one_line_per_phase_with_cursors_and_no_secrets(tmp_path):
    broker, _runner, journal, clock, audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    journal.add(msg(clock() + 0.3, "shutting down"), msg(clock() + 0.6, "runtimes: codex codex-cli 0.157.0 (using codex, as asked)"))
    clock.advance(4)
    call(broker, "verify", {"plan_id": plan["plan_id"]})
    lines = [ln for ln in audit_lines(audit) if ln["plan_id"] == plan["plan_id"]]
    assert [ln["phase"] for ln in lines] == ["plan", "apply", "verify"]
    assert lines[1]["cursor_before"].startswith("s=") and lines[2]["cursor_after"].startswith("s=")
    assert lines[1]["preconditions"]["outbox_files"] == 0 and lines[1]["peer_uid"] == DASH_UID
    text = (tmp_path / "audit.jsonl").read_text()
    assert PUBLIC_KEY not in text and PRIVATE_KEY not in text
    tail = call(broker, "audit-tail", {"n": 2})["data"]["lines"]
    assert [ln["phase"] for ln in tail] == ["apply", "verify"]


def test_drain_arm_and_cancel_answer_verify_at_once(tmp_path):
    # WP8's CONTROL polls verify after EVERY apply (contract §C.16): an arm and a cancel are verified at once, never unknown_plan
    broker, runner, _journal, _clock, _audit = make_broker(tmp_path)
    plan = call(broker, "drain-restart", {"offline": True})["plan"]
    assert call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})["result"]["outcome"] == "armed"
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is True and data["reason"] is None and data["connected"] is None
    assert data["verify_lines"] == ["drain armed · 0/4 idle beats · expires 18:13 UTC"]              # NOW 14:13:20 + 4 h
    cancel = call(broker, "cancel-drain", {})["plan"]
    applied = call(broker, "apply", {"plan_id": cancel["plan_id"], "confirm": cancel["plan_id"][:4]})
    assert applied["result"]["outcome"] == "cancelled"
    data = call(broker, "verify", {"plan_id": cancel["plan_id"]})["data"]
    assert data["verified"] is True and data["verify_lines"] == ["drain cleared · nothing restarted"]
    assert runner.argvs("systemctl", "restart") == []


def test_kill_orphans_verify_decides_pids_gone_after_the_sigkill_follow_up(tmp_path):
    # the plan promises verify {"verified_when": ["pids gone"]}; WP8's CONTROL polls it after the apply (contract §C.16)
    broker, runner, clock, audit, _spec = _orphan_broker(tmp_path)
    plan = call(broker, "kill-orphans", {"pids": [64876, 64877]})["plan"]
    assert plan["verify"]["verified_when"] == ["pids gone"]
    call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    pending = call(broker, "verify", {"plan_id": plan["plan_id"]})
    assert pending["ok"] is True and pending["data"]["verified"] is None                        # never unknown_plan
    shutil.rmtree(tmp_path / "proc" / "64876")                                             # 64876 exits on SIGTERM; 64877 not
    assert broker.tick(clock() + 11) == ["sigkill"] and runner.argvs("kill", "-KILL") == [["kill", "-KILL", "64877"]]
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is None     # SIGKILLed this tick: decided next
    broker.tick(clock() + 41)                                                                   # the fake /proc still lists 64877
    data = call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is False and data["reason"] == "still listed after SIGKILL: pid 64877"
    assert data["verify_lines"] == ["pids gone: pid 64876"]
    last = audit_lines(audit)[-1]
    assert last["phase"] == "verify" and last["plan_id"] == plan["plan_id"] and last["verified"] is False
    # a target gone on SIGTERM alone is decided on the follow-up tick itself
    broker2, runner2, clock2, _audit2, _spec2 = _orphan_broker(tmp_path / "b")
    plan = call(broker2, "kill-orphans", {"pids": [64884]})["plan"]
    call(broker2, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    shutil.rmtree(tmp_path / "b" / "proc" / "64884")
    assert broker2.tick(clock2() + 11) == [] and runner2.argvs("kill", "-KILL") == []
    data = call(broker2, "verify", {"plan_id": plan["plan_id"]})["data"]
    assert data["verified"] is True and data["reason"] is None and data["verify_lines"] == ["pids gone: pid 64884"]


@pytest.mark.parametrize('change', ['start_ticks', 'cgroup', 'uid'])
def test_kill_rechecks_exact_identity_before_term_and_kill(tmp_path, change):
    broker, runner, clock, _audit, spec = _orphan_broker(tmp_path)
    plan = call(broker, 'kill-orphans', {'pids': [64885]})['plan']
    target = next(p for p in spec['procs'] if p['pid'] == 64885)
    original = dict(target)
    target[change] = {'start_ticks': target['start_ticks'] + 1,
                      'cgroup': 'system.slice/imd-worker.service/child', 'uid': 0}[change]
    write_fake_proc(tmp_path / 'proc', spec)
    result = call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})['result']
    assert result['killed'] == [] and runner.argvs('kill') == []
    target.update(original)
    write_fake_proc(tmp_path / 'proc', spec)
    plan = call(broker, 'kill-orphans', {'pids': [64885]})['plan']
    call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
    target[change] = {'start_ticks': target['start_ticks'] + 1,
                      'cgroup': 'system.slice/imd-worker.service/child', 'uid': 0}[change]
    write_fake_proc(tmp_path / 'proc', spec)
    broker.tick(clock() + 11)
    assert runner.argvs('kill', '-KILL') == []


@pytest.mark.parametrize('phase', ['plan', 'term'])
@pytest.mark.parametrize('change', ['new_member', 'start_ticks', 'cgroup'])
def test_group_kill_rechecks_all_members_against_plan(tmp_path, phase, change):
    spec = json.loads((FIXTURES / 'procs_orphan.json').read_text())
    spec['procs'] = [p for p in spec['procs'] if p['pid'] != 64861]
    for p in spec['procs']:
        if p['pgid'] == 64861:
            p['pgid'] = 64862
    write_fake_proc(tmp_path / 'proc', spec)
    broker, runner, _journal, clock, _audit = make_broker(tmp_path, clock=Clock(spec['now']))
    plan = call(broker, 'kill-orphans', {'pids': [64876, 64877, 64884, 64885]})['plan']
    if phase == 'term':
        call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
    target = next(p for p in spec['procs'] if p['pid'] == 64885)
    if change == 'new_member':
        spec['procs'].append({**target, 'pid': 64999})
    elif change == 'start_ticks':
        target['start_ticks'] += 1
    else:
        target['cgroup'] = 'system.slice/imd-worker.service/child'
    write_fake_proc(tmp_path / 'proc', spec)
    if phase == 'plan':
        call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
        assert ['kill', '-TERM', '--', '-64862'] not in runner.argvs('kill')
        assert ['kill', '-TERM', '64999'] not in runner.argvs('kill')
    else:
        broker.tick(clock() + 11)
        assert runner.argvs('kill', '-KILL') == []


def test_doctor_cooldown_is_rechecked_at_apply(tmp_path):
    broker, runner, _, _, audit = make_broker(tmp_path, script={("systemd-run",): lambda a, k: transient('ok')})
    plans = [call(broker, 'doctor', {})['plan'] for _ in range(2)]
    first, second = plans
    assert call(broker, 'apply', {'plan_id': first['plan_id'], 'confirm': first['plan_id'][:4]})['ok']
    _wait(broker, first['plan_id'])
    result = call(broker, 'apply', {'plan_id': second['plan_id'], 'confirm': second['plan_id'][:4]})
    if result.get('ok'):
        _wait(broker, second['plan_id'])
    assert result['error'] == 'doctor_too_soon'
    assert len(runner.argvs('systemd-run')) == 1
    assert audit_lines(audit)[-1]['phase'] == 'refused'


def test_transient_oserror_is_a_decided_failure_and_releases_lock(tmp_path):
    broker, _, _, _, _ = make_broker(tmp_path, script={("systemd-run",): OSError('synthetic runner unavailable')})
    plan = call(broker, 'doctor', {})['plan']
    call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
    _wait(broker, plan['plan_id'])
    verdict = call(broker, 'verify', {'plan_id': plan['plan_id']})['data']
    assert verdict['verified'] is False and verdict['reason'] == 'OSError'
    assert call(broker, 'ping')['data']['in_flight'] is None


@pytest.mark.parametrize('phase', ['plan', 'term'])
def test_root_kill_refuses_incomplete_process_snapshot(tmp_path, phase):
    broker, runner, _, clock, audit = make_broker(tmp_path)
    spec = json.loads((FIXTURES / 'procs_orphan.json').read_text())
    write_fake_proc(Path(broker._proc_root), spec)
    pids = [p['pid'] for p in spec['procs'] if p['pgid'] == 64861 and p['uid'] == 1000]
    plan = call(broker, 'kill-orphans', {'pids': pids})['plan']
    if phase == 'term':
        assert call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})['ok']
    # A group member is unreadable, not known to have exited: never omit it and signal the remaining group.
    unreadable = next(p for p in spec['procs'] if p['pgid'] == 64861)
    (Path(broker._proc_root) / str(unreadable['pid']) / 'stat').unlink()
    before = len(runner.calls)
    if phase == 'plan':
        result = call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
        assert result.get('error') == 'unreadable'
    else:
        broker.tick(clock() + 11)
        assert call(broker, 'verify', {'plan_id': plan['plan_id']})['data']['verified'] is False
    assert not [a for a, _ in runner.calls[before:] if a[:1] == ['kill']]
# ==== Task 6.17: guards -- stdlib-only root code, timeouts everywhere, 3.11 byte-compile ======================

import ast  # noqa: E402
import sys  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
IMD_DASHD_DIR = REPO / "imd_dashd"
CLIENT_FILE = REPO / "maxpane_dashboard" / "data" / "seat_broker_client.py"
RUNNER_NAMES = {"run", "_run", "Popen", "popen", "_popen"}


def _calls_missing_timeout(path: Path) -> list[str]:
    """Every call to subprocess.run/Popen or an injected Runner (`run(...)`, `self._run(...)`) must pass timeout= and a list argv."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                problems.append(f"{path.name}:{node.lineno} shell=True")
        if name not in RUNNER_NAMES:
            continue
        if not any(kw.arg == "timeout" for kw in node.keywords):
            problems.append(f"{path.name}:{node.lineno} {name}() without timeout=")
        if node.args and isinstance(node.args[0], (ast.Constant, ast.JoinedStr)):
            problems.append(f"{path.name}:{node.lineno} {name}() with a string argv")
    return problems


@pytest.mark.guard
def test_imd_dashd_imports_nothing_from_maxpane():
    # spec §4.1 trust boundary (3), §15: root code is stdlib only and imports nothing from maxpane_dashboard
    files = sorted(IMD_DASHD_DIR.glob("*.py"))
    assert {f.name for f in files} >= {"__init__.py", "imd_dashd.py", "verbs.py", "gate.py", "drain.py", "child_unit.py",
                                        "projection.py", "audit.py", "redact.py"}
    # `compression` is stdlib from Python 3.14 only; WP4's summarise_codex.py imports it once, inside a try/except
    # ImportError, and WP4's `test_zstd_import_is_guarded` pins that guard (ast.walk also sees imports inside try).
    stdlib = set(sys.stdlib_module_names) | {"compression"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                assert top != "maxpane_dashboard", f"{path.name} imports {name}"
                assert top == "imd_dashd" or top in stdlib, f"{path.name} imports non-stdlib {name}"
        assert _calls_missing_timeout(path) == [], path.name
        assert "\ntype " not in path.read_text(encoding="utf-8"), f"{path.name}: `type` statement needs 3.12"


@pytest.mark.guard
def test_imd_dashd_byte_compiles_and_the_client_has_timeouts():
    # spec §5.4 interpreter floor: Python 3.11 syntax (the CI venv is 3.11; the VPS is 3.14, the container 3.11.2).
    # compile() under this interpreter is the byte-compile check without writing __pycache__ into the tree.
    assert sys.version_info[:2] >= (3, 11)
    for path in sorted(IMD_DASHD_DIR.glob("*.py")):
        compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True)
    assert _calls_missing_timeout(CLIENT_FILE) == []
    assert "shell=True" not in CLIENT_FILE.read_text(encoding="utf-8")

@pytest.mark.parametrize('failure', ['construct', 'start'])
def test_transient_thread_failure_finishes_watch_and_releases_lock(tmp_path, monkeypatch, failure):
    import threading
    broker, *_ = make_broker(tmp_path)
    plan = call(broker, 'doctor')['plan']
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic thread exhaustion')
    with monkeypatch.context() as patch:
        if failure == 'construct':
            patch.setattr(threading, 'Thread', fail)
        else:
            patch.setattr(threading.Thread, 'start', fail)
        result = call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
    assert result['error'] == 'internal'
    assert not broker._lock.locked() and broker._in_flight is None
    watch = broker._watches[plan['plan_id']]
    assert watch.done and watch.verified is False and 'internal' in watch.reason and 'thread start failed' in watch.reason
    assert plan['plan_id'] not in broker._threads
    # No child was started: failure must not burn the doctor cooldown.
    assert call(broker, 'doctor')['ok']
    start = call(broker, 'start')['plan']
    assert call(broker, 'apply', {'plan_id': start['plan_id'], 'confirm': start['plan_id'][:4]})['ok']


def test_sessions_redacts_actual_summary_metadata_recursively(tmp_path):
    from imd_dashd.summarise_codex import summarise_file
    synthetic = 'sk-review_SYNTHETIC_fragment'
    fixture = Path('tests/fixtures/seat/sessions/rollout_task.jsonl')
    records = [json.loads(line) for line in fixture.read_text().splitlines()]
    for rec in records:
        if rec.get('type') == 'turn_context':
            rec['payload']['model'] = synthetic
    rollout = tmp_path / 'rollout-synthetic.jsonl'
    rollout.write_text('\n'.join(json.dumps(r) for r in records))
    session = summarise_file(str(rollout), work_root='/home/imd-worker/.identitymd/work', now=0)
    session['quota'] = {synthetic: [synthetic, '\x1b[31mquota\x00']}
    broker, runner, *_ = make_broker(tmp_path)
    runner.script[('systemd-run',)] = (0, json.dumps({'sessions': [session]}))
    clean = call(broker, 'sessions', {'runtime': 'codex', 'since': 0})['data']['sessions'][0]
    assert clean['model'] == 'sk-[redacted]'
    assert clean['quota'] == {'sk-[redacted]': ['sk-[redacted]', '␛[31mquota']}
    assert clean['tokens'] == session['tokens'] and clean['path'] == session['path']


@pytest.mark.parametrize('drain', [False, True])
def test_serving_loop_refuses_arrivals_during_write_and_drain(tmp_path, drain):
    import queue
    import threading
    import socket
    broker, runner, journal, clock, audit = make_broker(tmp_path)
    plans = [call(broker, 'restart')['plan'] for _ in range(2)]
    if drain:
        armed = call(broker, 'drain-restart', {'offline': True})['plan']
        assert call(broker, 'apply', {'plan_id': armed['plan_id'], 'confirm': armed['plan_id'][:4]})['ok']
        # Each post-arm heartbeat is consumed by the production scheduler's tick.
        for offset in (1, 2, 3, 4):
            journal.add(hb(clock() + offset))
        clock.advance(31)
    class Conn:
        def __init__(self, verb, args):
            self.raw = json.dumps({'v': 1, 'verb': verb, 'args': args}).encode() + b'\n'
            self.response = None
            self.done = threading.Event()
        def settimeout(self, timeout): pass
        def recv(self, limit):
            raw, self.raw = self.raw, b''
            return raw
        def sendall(self, raw):
            self.response = json.loads(raw)
            self.done.set()
        def close(self): pass
    incoming = queue.Queue()
    class Listener:
        def settimeout(self, timeout): pass
        def accept(self):
            item = incoming.get(timeout=4)
            if item == 'tick': raise socket.timeout()
            if item is None: raise OSError('finished')
            return item, None
    second = Conn('apply', {'plan_id': plans[1]['plan_id'], 'confirm': plans[1]['plan_id'][:4]})
    preview = Conn('restart', {})
    observations = []
    def restart(argv, kw):
        incoming.put(second)
        incoming.put(preview)
        try:
            observations.append(second.done.wait(2) and preview.done.wait(2))
        finally:
            incoming.put(None)
        return subprocess.CompletedProcess(argv, 0, b'', b'')
    runner.script[('systemctl', 'restart')] = restart
    first = Conn('apply', {'plan_id': plans[0]['plan_id'], 'confirm': plans[0]['plan_id'][:4]})
    incoming.put('tick' if drain else first)
    broker.serve_forever(Listener())
    assert observations == [True], 'admission must respond while the write still holds the lock'
    assert len(runner.argvs('systemctl', 'restart')) == 1
    for conn in (second, preview):
        assert conn.response['error'] == 'busy'
        assert conn.response['detail']['verb'] == ('drain-restart' if drain else 'restart')
        assert conn.response['detail']['plan_id'] and conn.response['detail']['since']
    assert not broker._lock.locked()
    # Rejected apply did not consume the previously issued single-use plan.
    assert not broker._plans._plans[plans[1]['plan_id']].spent
    records = audit_lines(audit)
    assert [r['seq'] for r in records] == list(range(1, len(records) + 1))


def test_serving_loop_bounds_connections_without_queueing_overload(tmp_path):
    import threading
    broker, *_ = make_broker(tmp_path)
    release = threading.Event()
    class Conn:
        def __init__(self):
            self.reading = threading.Event()
            self.sent = False
            self.closed = False
        def settimeout(self, timeout): assert timeout == 5.0
        def recv(self, limit):
            self.reading.set()
            assert release.wait(2)
            return b'{"v":1,"verb":"ping","args":{}}\n'
        def sendall(self, raw): self.sent = True
        def close(self):
            self.closed = True
            if self is connections[-1]: release.set()
    from imd_dashd.imd_dashd import MAX_CONNECTIONS
    connections = [Conn() for _ in range(MAX_CONNECTIONS + 1)]
    class Listener:
        i = 0
        def settimeout(self, timeout): pass
        def accept(self):
            if self.i == len(connections): raise OSError('finished')
            if self.i: assert connections[self.i - 1].reading.wait(2)
            conn = connections[self.i]
            self.i += 1
            return conn, None
    try:
        broker.serve_forever(Listener())
    finally:
        release.set()
    assert all(c.sent and c.closed for c in connections[:-1])
    assert connections[-1].closed and not connections[-1].sent and not connections[-1].reading.is_set()


@pytest.mark.parametrize('verb', ['restart', 'stop'])
def test_gate_requires_history_and_refetches_latest_lifecycle_at_apply(tmp_path, verb):
    clock = Clock()
    journal = Journal([hb(clock() - age) for age in (120, 90, 60, 30)])
    broker, runner, *_ = make_broker(tmp_path, clock=clock, journal=journal)
    assert call(broker, verb, {'offline': True})['plan']['preconditions']['lifecycle_open'] is False
    journal.add(msg(clock() - 7 * 86400, 'submitted implement for 0c1f9727'))
    plan = call(broker, verb, {'offline': True})['plan']
    assert plan['preconditions']['lifecycle_open'] is False
    journal.add(msg(clock() - 1, 'accepted question deadbeef'))
    result = call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4], 'local_only_ack': 'local-only'})
    assert result['error'] == 'gate_blocked' and not runner.argvs('systemctl', verb)
    journal.add(msg(clock(), 'answered deadbeef with 1 citation(s)'))
    plan = call(broker, verb, {'offline': True})['plan']
    assert call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4], 'local_only_ack': 'local-only'})['ok']
    history_calls = [argv for argv in runner.argvs('journalctl') if '--grep' in argv]
    assert history_calls and all('--since' not in argv and argv[argv.index('--lines') + 1] == '1' for argv in history_calls)


def test_drain_successful_empty_lifecycle_can_restart(tmp_path):
    clock = Clock()
    journal = Journal([hb(clock() - age) for age in (120, 90, 60, 30)])
    broker, runner, *_ = make_broker(tmp_path, clock=clock, journal=journal)
    plan = call(broker, 'drain-restart', {'offline': True})['plan']
    assert call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})['ok']
    for offset in (1, 2, 3, 4): journal.add(hb(clock() + offset))
    clock.advance(31)
    assert 'drain_fire' in broker.tick()
    assert broker._drain.armed is None and runner.argvs('systemctl', 'restart')


@pytest.mark.parametrize("rc,out,err", [
    (1, b"-- No entries --\n", b""),
    (1, b"-- No entries --\n", b"PCRE2 unavailable"),
    (2, b"-- No entries --\n", b""),
    (1, b"", b""),
    (1, b"-- cursor: s=0;i=1;b=0;m=0;t=0;x=0\n", b""),
    (1, b"-- cursor: x\n", b"Hint: failed"),
    (0, b"", b""),
    (0, b"-- cursor: x\n", b""),
    (0, b"-- No entries --\n", b""),
    (1, b'{"MESSAGE":"x"}\n-- No entries --\n', b""),
    (0, b"garbage", b""),
    (0, b"", b"PCRE2 unavailable"),
])
def test_lifecycle_no_match_accepts_measured_json_forms_only(tmp_path, rc, out, err):
    journal = Journal([hb(NOW - age) for age in (120, 90, 60, 30)])
    def read(argv, kw):
        if "--grep" in argv:
            return subprocess.CompletedProcess(argv, rc, out, err)
        return journal(argv, kw)
    broker, *_ = make_broker(tmp_path, journal=journal, script={("journalctl",): read})
    result = call(broker, "restart", {"offline": True})
    if rc == 1 and not err and (not out or out.startswith(b"-- cursor: ") or out == b"-- No entries --\n"):
        assert result["ok"] and result["plan"]["preconditions"]["lifecycle_open"] is False
    else:
        assert result["error"] == "gate_unknown(lifecycle)"


@pytest.mark.parametrize("verb", ["restart", "stop"])
def test_armed_drain_refuses_manual_plan_and_preexisting_apply(tmp_path, verb):
    broker, runner, _journal, _clock, audit = make_broker(tmp_path)
    earlier = call(broker, verb)["plan"]
    drain = call(broker, "drain-restart", {"offline": True})["plan"]
    assert call(broker, "apply", {"plan_id": drain["plan_id"], "confirm": drain["plan_id"][:4]})["ok"]
    preview = call(broker, verb)
    apply = call(broker, "apply", {"plan_id": earlier["plan_id"], "confirm": earlier["plan_id"][:4]})
    for result in (preview, apply):
        assert result["error"] == "drain_already_armed"
        assert "cancel-drain" in result["detail"]["hint"]
    assert not runner.argvs("systemctl", verb)
    refused = [r for r in audit_lines(audit) if r["outcome"] == "drain_already_armed"]
    assert len(refused) == 2
    assert refused[0]["plan_id"] is None
    assert refused[-1]["plan_id"] == earlier["plan_id"]


def test_malformed_plan_id_is_audited_without_echoing_it(tmp_path):
    broker, _runner, _journal, _clock, audit = make_broker(tmp_path)
    secret = "malformed-private-marker"
    assert call(broker, "apply", {"plan_id": secret, "confirm": "bad"})["error"] == "unknown_plan"
    records = audit_lines(audit)
    assert records[-1]["phase"] == "refused" and records[-1]["outcome"] == "unknown_plan"
    assert secret not in audit.path.read_text()


@pytest.mark.parametrize("failure", [OSError("unreadable"), subprocess.TimeoutExpired("journalctl", 12)])
def test_lifecycle_history_failure_does_not_become_empty_success(tmp_path, failure):
    broker, runner, journal, *_ = make_broker(tmp_path)
    def read(argv, kw):
        if "--grep" in argv:
            raise failure
        return journal(argv, kw)
    runner.script[("journalctl",)] = read
    assert call(broker, "restart", {"offline": True})["error"] == "gate_unknown(lifecycle)"


def test_lifecycle_journal_argv_is_the_broker_history_command(tmp_path):
    from imd_dashd.imd_dashd import lifecycle_journal_argv
    broker, runner, *_ = make_broker(tmp_path)
    call(broker, "gate")
    assert lifecycle_journal_argv() in runner.argvs("journalctl")
    assert lifecycle_journal_argv(pattern="(?!)")[-5:] == ["--grep", "(?!)", "--lines", "1", "--case-sensitive=yes"]


@pytest.mark.parametrize("as_list", [False, True])
def test_projection_canary_refuses_nested_device_key(tmp_path, as_list):
    from imd_dashd.projection import project
    source = json.loads((FIXTURES / "projection_nested_device_key.json").read_text())
    nested = source["inference"]["deviceKey"]
    if as_list:
        source["inference"] = [source["inference"]]
    payload = project(source, None)
    child = (PYTHON, "-I", os.path.join(broker_mod.BROKER_DIR, "projection.py"))
    broker, _runner, _journal, _clock, audit = make_broker(
        tmp_path, script={child: lambda argv, kw: projection_child(payload)})
    response = call(broker, "seat")
    assert response == {"ok": False, "error": "projection_refused", "detail": {"canary": "hex64"}}
    assert audit_lines(audit)[-1]["outcome"] == "canary: hex64"
    assert nested not in json.dumps(audit_lines(audit)) and PUBLIC_KEY not in json.dumps(audit_lines(audit))


@pytest.mark.parametrize("bad_record", ['{"MESSAGE":', '{"MESSAGE": null}', '[]', '{"MESSAGE": ["bad"]}', '{"MESSAGE": [255]}', '{"MESSAGE": [true]}'])
@pytest.mark.parametrize("mixed", [False, True])
def test_unreadable_lifecycle_with_cursor_refuses_plan_and_apply(tmp_path, bad_record, mixed):
    broker, runner, journal, clock, _audit = make_broker(tmp_path)
    prior = call(broker, "restart", {"offline": True})["plan"]
    valid = json.dumps({"MESSAGE": msg(clock() - 300, "submitted implement for 0c1f9727")[1]})
    def lifecycle(argv, kw):
        if "--grep" in argv:
            rows = ([valid] if mixed else []) + [bad_record, "-- cursor: s=deadbeef;i=8"]
            return subprocess.CompletedProcess(argv, 0, "\n".join(rows).encode(), b"")
        return journal(argv, kw)
    runner.script[("journalctl",)] = lifecycle
    preview = call(broker, "restart", {"offline": True})
    applied = call(broker, "apply", {"plan_id": prior["plan_id"], "confirm": prior["plan_id"][:4], "local_only_ack": "local-only"})
    assert preview.get("error") == "gate_unknown(lifecycle)"
    assert applied.get("error") == "gate_unknown(lifecycle)"
    assert not runner.argvs("systemctl", "restart")


@pytest.mark.parametrize("failure", ["deadline", "snapshot", "exception", "timeout", "nonzero"])
@pytest.mark.parametrize("group", [False, True])
def test_partial_orphan_apply_retains_actual_audit_and_verification(tmp_path, monkeypatch, failure, group):
    broker, runner, clock, audit, spec = _orphan_broker(tmp_path)
    if group:
        # Two independent clean orphan groups, so the second group's fresh read can fail.
        spec["procs"] = [p for p in spec["procs"] if p["pid"] in (64876, 64877)]
        for proc in spec["procs"]:
            proc["pgid"] = proc["pid"]
        # The initial helper already wrote a /proc tree; remove only this test's fake entries.
        for child in (tmp_path / "proc").iterdir():
            if child.is_dir(): shutil.rmtree(child)
        write_fake_proc(tmp_path / "proc", spec)
    mono = Clock(0)
    broker._monotonic = mono
    plan = call(broker, "kill-orphans", {"pids": [64876, 64877]})["plan"]
    assert set(plan["preconditions"]["kill_mode_by_pgid"].values()) == {"group" if group else "individual"}
    original = broker_mod.signal_procs
    def snapshot(*args, **kwargs):
        if failure == "snapshot" and runner.argvs("kill", "-TERM"):
            return None
        mono.advance(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(broker_mod, "signal_procs", snapshot)
    def first_kill(argv, kw):
        if failure in ("exception", "timeout", "nonzero") and len(runner.argvs("kill", "-TERM")) == 2:
            if failure == "exception": raise OSError("synthetic kill failure")
            if failure == "timeout": raise subprocess.TimeoutExpired(argv, 5)
            return subprocess.CompletedProcess(argv, 1, b"", b"")
        if failure in ("deadline", "snapshot"):
            mono.advance(5 if group else 4)
        return subprocess.CompletedProcess(argv, 0, b"", b"")
    runner.script[("kill", "-TERM")] = first_kill
    response = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert response["error"] == {"deadline": "apply_late", "snapshot": "unreadable", "exception": "internal", "timeout": "timeout", "nonzero": "internal"}[failure]
    expected = {"mode": "group", "pgid": 64876, "pids": [64876]} if group else {"mode": "individual", "pid": 64876}
    assert response["detail"]["partial"] is True and response["detail"]["killed"] == [expected]
    applied = [r for r in audit_lines(audit) if r["phase"] == "apply" and r["plan_id"] == plan["plan_id"]]
    assert len(applied) == 1 and applied[0]["outcome"] == "partial"
    assert applied[0]["args"]["killed"] == [expected]
    watch = broker._watches[plan["plan_id"]]
    assert watch.targets == [("pgid" if group else "pid", 64876)]
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is None
    assert len(runner.argvs("kill", "-TERM")) == (2 if failure in ("exception", "timeout", "nonzero") else 1)
    assert [row["pid"] for row in response["detail"]["skipped"]] == [64877]
    assert len(broker._pending_kills) == 1
    # Finish only the already-signalled subset, preserving the normal identity-checked completion.
    monkeypatch.setattr(broker_mod, "signal_procs", original)
    assert broker.tick(clock() + 11) == ["sigkill"]
    assert runner.argvs("kill", "-KILL") == ([["kill", "-KILL", "--", "-64876"]] if group else [["kill", "-KILL", "64876"]])
    shutil.rmtree(tmp_path / "proc" / "64876")
    broker.tick(clock() + 12)
    assert call(broker, "verify", {"plan_id": plan["plan_id"]})["data"]["verified"] is True


def test_ordinary_journal_still_preserves_readable_records_amid_bad_ones(tmp_path):
    broker, runner, _journal, clock, _audit = make_broker(tmp_path)
    text = msg(clock(), "submitted implement for 0c1f9727")[1]
    output = '{"MESSAGE":\n' + json.dumps({"MESSAGE": list(text.encode())}) + "\n-- cursor: s=ok;i=1\n"
    runner.script[("journalctl",)] = (0, output)
    lines, cursor = broker._journal()
    assert lines == [(clock(), text)] and cursor == "s=ok;i=1"


def test_no_signal_snapshot_refusal_is_explicitly_not_partial(tmp_path, monkeypatch):
    broker, runner, _clock, _audit, _spec = _orphan_broker(tmp_path)
    plan = call(broker, "kill-orphans", {"pids": [64876]})["plan"]
    monkeypatch.setattr(broker_mod, "signal_procs", lambda *args, **kwargs: None)
    result = call(broker, "apply", {"plan_id": plan["plan_id"], "confirm": plan["plan_id"][:4]})
    assert result["error"] == "unreadable"
    assert result["detail"]["partial"] is False and result["detail"]["killed"] == []
    assert not runner.argvs("kill") and not broker._pending_kills


def test_lifecycle_argv_preserves_diagnostic_stderr_and_omits_cursor():
    from imd_dashd.imd_dashd import lifecycle_journal_argv
    argv = lifecycle_journal_argv()
    assert not {"--show-cursor", "-q", "--quiet"}.intersection(argv)


def test_nonpartial_orphan_timeout_does_not_leave_unresolvable_none_watch(tmp_path):
    broker, runner, clock, _audit, _spec = _orphan_broker(tmp_path)
    plan = call(broker, 'kill-orphans', {'pids': [64876]})['plan']
    def timed_out(argv, kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
    runner.script[('kill', '-TERM')] = timed_out
    response = call(broker, 'apply', {'plan_id': plan['plan_id'], 'confirm': plan['plan_id'][:4]})
    assert response['error'] == 'timeout' and response['detail']['partial'] is False
    assert broker._pending_kills == []
    clock.advance(31)
    broker.tick()
    result = call(broker, 'verify', {'plan_id': plan['plan_id']})['data']
    assert result['verified'] is False, result
    assert 'timeout' in result['reason']
