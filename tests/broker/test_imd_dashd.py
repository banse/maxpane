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
    created = store.create("restart", {}, ["systemctl", "restart", "imd-worker.service"], {}, None, {})
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
    assert during_apply[-1] == ["systemctl", "restart", "imd-worker.service"]      # systemctl is the LAST thing apply does


def test_restart_plan_has_the_spec_shape(tmp_path):
    broker, _runner, _journal, _clock, audit = make_broker(tmp_path)
    plan = call(broker, "restart", {"offline": False})["plan"]
    assert plan["verb"] == "restart" and plan["argv"] == ["systemctl", "restart", "imd-worker.service"]
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
    for verb, argv, inverse in (("start", ["systemctl", "start", "imd-worker.service"], "stop"),
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
    assert call(broker, "restart", {"offline": False})["error"] == "gate_blocked"                 # restart itself stays gated
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
