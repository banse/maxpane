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
