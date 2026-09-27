"""imd-dashd -- the root broker behind ``/run/imd-dash/broker.sock`` (spec §4.1, §11, §12.1; contract C.11).

One JSON line in, one out. Every request is checked in this order: peer uid (``SO_PEERCRED``) ==
``imd-dash``; verb in the fixed enum; args typed. Read verbs run as dropped children (in-process
``imd-worker`` or a transient unit); write verbs are plan -> apply -> verify with single-use plan ids,
one write in flight (``busy``), the idle gate re-read fresh at apply, ``apply`` returning when the
command exits, and ``verify`` as a separate read verb. Everything is audited. Root code only:
stdlib, no ``maxpane_dashboard`` import, Python 3.11 syntax (``/usr/bin/python3 -I``).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # python3 -I: no script dir

import argparse
import json
import re
import secrets
import signal
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from imd_dashd import verbs
from imd_dashd.audit import Audit, iso_utc
from imd_dashd.child_unit import RUNTIME_MAX_S, Runner, read_ip_address_deny, run_inprocess, run_transient, unit_name
from imd_dashd.drain import Drain, DrainState
from imd_dashd.gate import ACCEPTED_RE, HEARTBEAT_RE, GateResult, evaluate, parse_iso
from imd_dashd.redact import find_secret, redact, redact_agent_sentence

Clock = Callable[[], float]

VERSION = "imd-dashd 0.1.0"
PLAN_TTL_S = 60
VERIFY_WITHIN_S = 30           #: `shutting down` -> `runtimes:` within 30 s = verified (fill1 §1: +0.3 s on 8/8)
VERIFY_WATCH_S = 120           #: the post-apply journal watch is kept this long
BROKER_IDLE_EXIT_S = 600
DOCTOR_MIN_INTERVAL_S = 600
ORPHAN_MIN_AGE_S = 3600
KILL_GRACE_S = 10              #: SIGTERM then SIGKILL after 10 s
ORPHAN_EXCLUDED_CGROUPS = ("system.slice/imd-worker.service",)
ORPHAN_EXCLUDED_CGROUP_PREFIX = "system.slice/imd-dash-"
SOCKET_PATH = "/run/imd-dash/broker.sock"
AUDIT_PATH = "/var/log/imd-dash/audit.jsonl"
STANDING_URL = "https://api.imd.fun/seats/{seat}/standing"
WORKER_UNIT = "imd-worker.service"
WORKER_UID = 1000
PYTHON = "/usr/bin/python3"
BROKER_DIR = os.path.dirname(os.path.abspath(__file__))   #: where gate.py / projection.py / summarise_*.py live
JOURNAL_WINDOW_S = 1800        #: the journal slice every gate read and plan preview scans (30 min: ~60 heartbeats)
TICK_S = 30                    #: the serve loop's housekeeping cadence (drain beats, expiry, kill follow-ups)
INPROCESS_TIMEOUT_S = {"seat": 10, "outbox": 5, "work-stat": 20, "hints-stat": 5, "auth-mtime": 5, "orphans": 5,
                       "audit-tail": 5, "verify": 5, "ping": 1, "gate": 12}
SYSTEMCTL_TIMEOUT_S = 20
WARNING = ("a task assigned in the ~1–5 s between the gate's fresh reads and systemctl may be reported as a failed run; "
           "3 consecutive failed runs pause the seat 15 min (never measured: 16/16 historical restarts were idle)")
READ_COUNT_FLUSH_S = 3600      #: read verbs are audited as counts only: one `reads` line per hour and at exit (spec §11)
#: a list-price figure in `imd doctor` output (`· $0.114`, `($0.114 estimated)`); spec §10 "no currency", §5.3 doctor row
_CURRENCY_FIGURE_RE = re.compile(r"\s*(?:·\s*)?\(?\$\s*\d[\d,]*(?:\.\d+)?(?:\s*estimated)?\)?")
RUNTIME_PATHS = {
    "codex": {"sessions": ".codex/sessions", "hints": ".codex/AGENTS.md", "auth": ".codex/auth.json"},
    "claude": {"sessions": ".claude/projects", "hints": "CLAUDE.md", "auth": ".claude/.credentials.json"},
}
SO_PEERCRED = getattr(socket, "SO_PEERCRED", 17)         # Linux value; macOS lacks the constant (tests inject peer_uid_of)


class PlanError(Exception):
    def __init__(self, code: str, detail: dict | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail or {}


@dataclass
class Plan:
    plan_id: str
    verb: str
    args: dict
    argv: list[str]
    created: float
    expires: float
    preconditions: dict
    inverse: dict | None
    verify: dict
    force_node8: str | None
    spent: bool = False


class PlanStore:
    """Single-use plan ids with a TTL (spec §11 protocol bullets 1-2)."""

    def __init__(self, *, now: Clock, ttl_s: float = PLAN_TTL_S) -> None:
        self._now = now
        self._ttl = ttl_s
        self._plans: dict[str, Plan] = {}

    def create(self, verb: str, args: dict, argv: list[str], preconditions: dict, inverse: dict | None, verify: dict,
               force_node8: str | None = None) -> Plan:
        created = self._now()
        plan = Plan(plan_id=secrets.token_hex(8), verb=verb, args=dict(args), argv=list(argv), created=created,
                    expires=created + self._ttl, preconditions=preconditions, inverse=inverse, verify=verify,
                    force_node8=force_node8)
        self._plans[plan.plan_id] = plan
        return plan

    def peek(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def consume(self, plan_id: str, now: float) -> Plan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise PlanError("unknown_plan")
        if plan.spent:
            raise PlanError("plan_spent", {"plan_id": plan_id})
        if now > plan.expires:
            raise PlanError("plan_expired", {"plan_id": plan_id, "expired_at": iso_utc(plan.expires)})
        plan.spent = True
        return plan

    def purge(self, now: float) -> None:
        for plan_id in [k for k, p in self._plans.items() if p.spent or now > p.expires + PLAN_TTL_S]:
            del self._plans[plan_id]


# ---------------------------------------------------------------- /proc reading (orphans)


# ---------------------------------------------------------------- the broker


class Broker:
    def __init__(self, *, run: Runner = subprocess.run, popen: Callable = subprocess.Popen,
                 peer_uid_of: Callable[[socket.socket], int], allowed_uid: int, audit: Audit, now: Clock = time.time,
                 seat: int | None, worker_home: str = "/home/imd-worker", socket_path: str = SOCKET_PATH,
                 standing_url: str = STANDING_URL, proc_root: str = "/proc", unit: str = WORKER_UNIT,
                 broker_dir: str = BROKER_DIR, python: str = PYTHON, worker_uid: int = WORKER_UID) -> None:
        self._run = run
        self._popen = popen                     # reserved for a journal follower; the v1 drain polls on the tick
        self._peer_uid_of = peer_uid_of
        self._allowed_uid = allowed_uid
        self._audit = audit
        self._now = now
        self._seat = seat
        self._home = worker_home.rstrip("/")
        self._socket_path = socket_path
        self._standing_url = standing_url
        self._proc_root = proc_root
        self._unit = unit
        self._broker_dir = broker_dir
        self._python = python
        self._worker_uid = worker_uid
        self._started = now()
        self._last_activity = self._started
        self._seq = 0
        self._plans = PlanStore(now=now)
        self._watches: dict[str, VerifyWatch] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._in_flight: dict | None = None
        self._drain = Drain(now=now)
        self._drain_offline = False
        self._drain_seen: set[str] = set()
        self._drain_fired: set[str] = set()      #: synthetic plan ids of drain-fired restarts still awaiting their verify line
        self._pending_kills: list[tuple[float, str, int]] = []
        self._whoami_key: str | None = None
        self._skills_listing: set[str] | None = None
        self._last_doctor: float | None = None
        self._last_tick = self._started
        self._read_counts: dict[str, int] = {}
        self._reads_flushed_at = self._started
        self.ip_address_deny: str | None = read_ip_address_deny(run=run)
        self.graceful_stop_possible: bool | None = self._read_graceful()
        self.stop_requested = False

    # ------------------------------------------------------------ helpers

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _log(self, **fields) -> int:
        try:
            return self._audit.append(**fields)
        except (OSError, TypeError, ValueError):
            return -1

    def _in_flight_detail(self) -> dict | None:
        return None if self._in_flight is None else dict(self._in_flight)

    def _standing_url_for_seat(self) -> str | None:
        if self._seat is None:                                   # no --seat in ExecStart: take tokenId from the canary-checked projection
            answer = self._seat_projection(self._allowed_uid)
            token = answer.get("data", {}).get("tokenId") if answer.get("ok") else None
            if isinstance(token, int) and not isinstance(token, bool) and token > 0:
                self._seat = token
        return None if self._seat is None else self._standing_url.format(seat=self._seat)

    def _read_graceful(self) -> bool | None:
        try:
            done = self._run(["systemctl", "show", self._unit, "-p", "KillMode", "-p", "TimeoutStopUSec"],
                             capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if done.returncode != 0:
            return None
        props = dict(line.split("=", 1) for line in _text(done.stdout).splitlines() if "=" in line)
        kill_mode = props.get("KillMode")
        stop_s = _usec_to_s(props.get("TimeoutStopUSec"))
        if kill_mode is None or stop_s is None:
            return None
        return kill_mode == "control-group" and stop_s >= 30

    # ------------------------------------------------------------ journal / unit / outbox reads (root)

    def _journal(self, *, since_s: int | None = None, after_cursor: str | None = None) -> tuple[list[tuple[float, str]], str | None]:
        argv = ["journalctl", "-u", self._unit, "-o", "json", "--no-pager", "--show-cursor"]
        if after_cursor:
            argv += ["--after-cursor", after_cursor]
        else:
            argv += ["--since", f"-{since_s or JOURNAL_WINDOW_S}s"]
        try:
            done = self._run(argv, capture_output=True, timeout=INPROCESS_TIMEOUT_S["gate"])
        except (subprocess.TimeoutExpired, OSError):
            return [], None
        lines: list[tuple[float, str]] = []
        cursor: str | None = None
        for raw in _text(done.stdout).splitlines():
            if raw.startswith("-- cursor: "):
                cursor = raw[len("-- cursor: "):].strip()
                continue
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get("MESSAGE")
            if isinstance(message, list):
                message = bytes(b for b in message if isinstance(b, int) and 0 <= b < 256).decode("utf-8", "replace")
            if not isinstance(message, str):
                continue
            try:
                epoch = int(record.get("__REALTIME_TIMESTAMP")) / 1_000_000
            except (TypeError, ValueError):
                epoch = parse_iso(message[:24]) or 0.0
            lines.append((epoch, redact(message)))
        return lines, cursor

    def _unit_active(self) -> bool | None:
        try:
            done = self._run(["systemctl", "is-active", self._unit], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            return None
        state = _text(done.stdout).strip()
        if not state:
            return None
        return state == "active"

    def _unit_enabled(self) -> bool | None:
        try:
            done = self._run(["systemctl", "is-enabled", self._unit], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            return None
        state = _text(done.stdout).strip()
        if state in ("enabled", "enabled-runtime", "static", "alias", "indirect"):
            return True
        if state in ("disabled", "masked", "masked-runtime"):
            return False
        return None

    def _outbox_files(self) -> int | None:
        result = run_inprocess(["ls", "-1A", f"{self._home}/.identitymd/outbox"], run=self._run,
                               timeout_s=INPROCESS_TIMEOUT_S["outbox"])
        if result.timed_out or result.rc != 0:
            return None
        return len([ln for ln in _text(result.stdout).splitlines() if ln.strip()])

    def _standing(self, offline: bool) -> dict | None:
        url = self._standing_url_for_seat()
        if offline or url is None:
            return None
        result = run_inprocess([self._python, "-I", os.path.join(self._broker_dir, "gate.py"), "--standing", url],
                               run=self._run, timeout_s=INPROCESS_TIMEOUT_S["gate"])
        if result.timed_out or result.rc != 0:
            return None
        try:
            body = json.loads(_text(result.stdout))
        except ValueError:
            return None
        if not isinstance(body, dict) or "running_count" not in body:
            return None
        return body

    def _gate(self, *, offline: bool) -> tuple[GateResult, list[tuple[float, str]], str | None]:
        lines, cursor = self._journal()
        result = evaluate(journal_lines=lines, standing=self._standing(offline), offline=offline,
                          outbox_files=self._outbox_files(), unit_active=self._unit_active(),
                          graceful_stop_possible=self.graceful_stop_possible, now=self._now())
        return result, lines, cursor

    # ------------------------------------------------------------ transport

    def serve_connection(self, conn: socket.socket) -> None:
        """One JSON line in, one out, close (spec §11 protocol)."""
        response: dict
        peer = -1
        try:
            try:
                peer = int(self._peer_uid_of(conn))
            except (OSError, ValueError, TypeError):
                peer = -1
            if peer != self._allowed_uid:
                self._log(peer_uid=peer, verb=None, phase="refused", outcome="peer_refused")
                response = verbs.err("peer_refused", {"peer_uid": peer})
            else:
                conn.settimeout(5.0)
                raw = _read_line(conn, verbs.MAX_REQUEST_BYTES)
                try:
                    verb, args = verbs.decode_request(raw)
                except ValueError as exc:
                    self._log(peer_uid=peer, verb=None, phase="refused", outcome=f"bad_request: {exc}")
                    response = verbs.err("bad_request", {"reason": str(exc)})
                else:
                    response = self.handle({"v": verbs.PROTOCOL_VERSION, "verb": verb, "args": args}, peer_uid=peer)
        except (OSError, ValueError) as exc:
            response = verbs.err("internal", {"reason": exc.__class__.__name__})
        try:
            conn.sendall((json.dumps(response, separators=(",", ":"), ensure_ascii=True, default=str) + "\n").encode("utf-8"))
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def handle(self, request: dict, *, peer_uid: int) -> dict:
        """The whole verb dispatch; never raises."""
        self._last_activity = self._now()
        if peer_uid != self._allowed_uid:
            self._log(peer_uid=peer_uid, verb=None, phase="refused", outcome="peer_refused")
            return verbs.err("peer_refused", {"peer_uid": peer_uid})
        try:
            verb = request.get("verb") if isinstance(request, dict) else None
            args = request.get("args", {}) if isinstance(request, dict) else {}
            if not isinstance(verb, str) or not isinstance(args, dict):
                return verbs.err("bad_request")
            code = verbs.validate_args(verb, args)
            if code is not None:
                self._log(peer_uid=peer_uid, verb=verb if verb in verbs.ALL_VERBS else None, phase="refused",
                          outcome=code, args={"names": sorted(args)})
                return verbs.err(code, {"verb": verb} if code == "bad_verb" else {"arg_names": sorted(args)})
            if verb in verbs.READ_VERBS:
                return self._read(verb, args, peer_uid)
            if verb == verbs.APPLY_VERB:
                return self._apply(args, peer_uid)
            return self._plan(verb, args, peer_uid)
        except Exception as exc:                                   # noqa: BLE001 -- the socket loop must survive anything
            self._log(peer_uid=peer_uid, verb=None, phase="refused", outcome=f"internal: {exc.__class__.__name__}")
            return verbs.err("internal", {"reason": exc.__class__.__name__})

    # ------------------------------------------------------------ read verbs

    def _read(self, verb: str, args: dict, peer_uid: int) -> dict:
        self._read_counts[verb] = self._read_counts.get(verb, 0) + 1       # audited as counts only (spec §11)
        if verb == "ping":
            return verbs.ok(data={"pid": os.getpid(), "version": VERSION, "uptime_s": round(self._now() - self._started, 1),
                                  "drain_armed": self._drain.armed is not None, "in_flight": self._in_flight_detail(),
                                  "posture_ok": self.ip_address_deny is not None,
                                  "drain": None if self._drain.armed is None else self._drain.armed.to_dict()})
        if verb == "audit-tail":
            return verbs.ok(data={"lines": self._audit.tail(max(1, min(int(args["n"]), 200)))})
        if verb == "gate":
            result, _lines, _cursor = self._gate(offline=bool(args.get("offline", False)))
            return verbs.ok(data=result.to_dict())
        if verb == "verify":
            return self._verify(str(args["plan_id"]))
        if verb == "orphans":
            procs = read_procs(self._proc_root, now=self._now())
            return verbs.ok(data={"candidates": select_orphans(procs, worker_uid=self._worker_uid)})
        if verb == "outbox":
            count = self._outbox_files()
            if count is None:
                return verbs.err("unreadable", {"what": "outbox"})
            return verbs.ok(data={"files": count})
        if verb == "work-stat":
            return self._work_stat()
        if verb == "hints-stat":
            return self._stat_verb("hints", with_sha=True)
        if verb == "auth-mtime":
            return self._stat_verb("auth", with_sha=False)
        if verb == "seat":
            return self._seat_projection(peer_uid)
        if verb == "sessions":
            return self._sessions(args)
        if verb in verbs.TRANSIENT_VERBS:
            return self._transient_read(verb)
        return verbs.err("bad_verb", {"verb": verb})

    def _transient(self, verb: str, argv: Sequence[str]):
        if self.ip_address_deny is None:
            return None
        return run_transient(verb, self._next_seq(), argv, run=self._run, ip_address_deny=self.ip_address_deny)

    def _transient_read(self, verb: str) -> dict:
        result = self._transient(verb, ["imd", verb])
        if result is None:
            return verbs.err("child_posture_unavailable", {"verb": verb})
        if result.timed_out:
            return verbs.err("timeout", {"verb": verb, "unit": result.unit})
        # whoami prints the public key: redact with the allowed field so the hex64 rule keeps it (spec §13 canary (3))
        lines = [redact(ln, "deviceKey" if verb == "whoami" else None) for ln in _text(result.stdout).splitlines() if ln.strip()]
        if verb == "whoami":
            key = next((ln.strip() for ln in lines if len(ln.strip()) == 64 and all(c in "0123456789abcdef" for c in ln.strip())), None)
            if key is None:
                return verbs.err("whoami_unavailable", {"rc": result.rc})
            self._whoami_key = key
            return verbs.ok(data={"deviceKey": key})
        if verb == "skills":
            self._skills_listing = {ln.split()[1] for ln in lines if ln.split()[:1] in (["on"], ["off"]) and len(ln.split()) > 1}
        return verbs.ok(data={"lines": lines, "rc": result.rc, "unit": result.unit})

    def _seat_projection(self, peer_uid: int) -> dict:
        if self._whoami_key is None:
            answer = self._transient_read("whoami")
            if not answer.get("ok"):
                if answer.get("error") == "child_posture_unavailable":
                    return answer
                return verbs.err("whoami_unavailable", answer.get("detail", {}))
        result = run_inprocess([self._python, "-I", os.path.join(self._broker_dir, "projection.py"),
                                "--config", f"{self._home}/.identitymd/config.json", "--tools", f"{self._home}/.identitymd/tools.json"],
                               run=self._run, timeout_s=INPROCESS_TIMEOUT_S["seat"])
        if result.timed_out:
            return verbs.err("timeout", {"verb": "seat"})
        try:
            payload = json.loads(_text(result.stdout))
        except ValueError:
            payload = None
        if result.rc == 3 or (isinstance(payload, dict) and payload.get("error") == "unknown_keys"):
            return self._canary_refused("unknown_keys", peer_uid)
        if result.rc != 0 or not isinstance(payload, dict):
            return verbs.err("unreadable", {"what": "config projection", "rc": result.rc})
        kind = find_secret(payload, allowed_hex64_fields=frozenset({"deviceKey"}))
        if kind is not None:
            return self._canary_refused(kind, peer_uid)
        if payload.get("deviceKey") != self._whoami_key:
            return self._canary_refused("devicekey_mismatch", peer_uid)
        return verbs.ok(data=payload)

    def _canary_refused(self, kind: str, peer_uid: int) -> dict:
        self._log(peer_uid=peer_uid, verb="seat", phase="canary", outcome=f"canary: {kind}")
        return verbs.err("projection_refused", {"canary": kind})

    def _sessions(self, args: dict) -> dict:
        runtime = str(args["runtime"])
        if runtime not in RUNTIME_PATHS:
            return verbs.err("bad_args", {"runtime": runtime})
        script = os.path.join(self._broker_dir, f"summarise_{runtime}.py")
        argv = [self._python, "-I", script, "--root", f"{self._home}/{RUNTIME_PATHS[runtime]['sessions']}",
                "--since", repr(float(args["since"]))]
        if runtime == "codex":
            argv += ["--work-root", f"{self._home}/.identitymd/work"]
        result = self._transient("sessions", argv)
        if result is None:
            return verbs.err("child_posture_unavailable", {"verb": "sessions"})
        if result.timed_out:
            return verbs.err("timeout", {"verb": "sessions", "unit": result.unit})
        try:
            body = json.loads(_text(result.stdout))
        except ValueError:
            return verbs.err("unreadable", {"what": "summariser output", "rc": result.rc})
        if isinstance(body, dict):
            for session in body.get("sessions", []) or []:
                if isinstance(session, dict):
                    for error in session.get("apiErrors", []) or []:
                        if isinstance(error, dict) and "message" in error:
                            error["message"] = redact(error["message"])
        return verbs.ok(data=body)

    def _work_stat(self) -> dict:
        root = f"{self._home}/.identitymd/work"
        listing = run_inprocess(["find", root, "-mindepth", "1", "-maxdepth", "4", "-printf", "%y\t%T@\t%P\n"],
                                run=self._run, timeout_s=INPROCESS_TIMEOUT_S["work-stat"])
        if listing.timed_out or listing.rc != 0:
            return verbs.err("unreadable", {"what": "work"})
        usage = run_inprocess(["du", "-sb", root], run=self._run, timeout_s=INPROCESS_TIMEOUT_S["work-stat"])
        total: int | None = None
        if not usage.timed_out and usage.rc == 0:
            try:
                total = int(_text(usage.stdout).split()[0])
            except (IndexError, ValueError):
                total = None
        return verbs.ok(data=parse_work_listing(_text(listing.stdout), total_bytes=total))

    def _stat_verb(self, what: str, *, with_sha: bool) -> dict:
        for runtime in ("codex", "claude"):
            path = f"{self._home}/{RUNTIME_PATHS[runtime][what]}"
            result = run_inprocess(["stat", "-c", "%s %Y", path], run=self._run, timeout_s=INPROCESS_TIMEOUT_S[f"{what}-stat" if what == "hints" else "auth-mtime"])
            if result.timed_out or result.rc != 0:
                continue
            try:
                size, mtime = _text(result.stdout).split()
                data = {"path": path, "mtimeUtc": iso_utc(int(mtime))}
            except ValueError:
                continue
            if not with_sha:
                return verbs.ok(data=data)
            digest = run_inprocess(["sha256sum", path], run=self._run, timeout_s=INPROCESS_TIMEOUT_S["hints-stat"])
            sha8 = _text(digest.stdout).split()[0][:8] if (not digest.timed_out and digest.rc == 0 and _text(digest.stdout).split()) else None
            data.update({"bytes": int(size), "sha8": sha8})
            return verbs.ok(data=data)
        return verbs.err("unreadable", {"what": what})

    # ------------------------------------------------------------ write verbs: plan

    # ------------------------------------------------------------ write verbs: apply

    # ------------------------------------------------------------ verify

    # ------------------------------------------------------------ housekeeping

    def _flush_read_counts(self, now: float, *, force: bool = False) -> None:
        """Read verbs are audited as counts only (spec §11): one line per READ_COUNT_FLUSH_S, and at exit."""
        if not self._read_counts or (not force and now - self._reads_flushed_at < READ_COUNT_FLUSH_S):
            return
        self._log(verb=None, phase="reads", outcome="counts", args={"counts": dict(self._read_counts)})
        self._read_counts = {}
        self._reads_flushed_at = now

    def tick(self, now: float | None = None) -> list[str]:
        """Plan and watch expiry (Task 6.12 adds drain beats and the SIGKILL follow-ups). Returns the audit events it wrote."""
        now = self._now() if now is None else now
        events: list[str] = []
        self._flush_read_counts(now)
        self._plans.purge(now)
        for plan_id in [k for k, w in self._watches.items() if now - w.started > VERIFY_WATCH_S and not (w.kind == "transient" and not w.done)]:
            del self._watches[plan_id]
        self._last_tick = now
        return events

    def idle_exit_due(self, now: float | None = None) -> bool:
        now = self._now() if now is None else now
        return (now - self._last_activity > BROKER_IDLE_EXIT_S and self._drain.armed is None and self._in_flight is None
                and not self._pending_kills)

    def shutdown(self) -> None:
        self._flush_read_counts(self._now(), force=True)
        event = self._drain.lose()
        if event:
            self._log(verb="drain-restart", phase=event, outcome="broker stopping")
        self.stop_requested = True

    def serve_forever(self, listener: socket.socket) -> None:
        listener.settimeout(1.0)
        while not self.stop_requested:
            try:
                conn, _addr = listener.accept()
            except socket.timeout:
                conn = None
            except OSError:
                break
            if conn is not None:
                self.serve_connection(conn)
            now = self._now()
            if now - self._last_tick >= TICK_S:
                self.tick(now)
            if self.idle_exit_due(now):
                break


# ---------------------------------------------------------------- pure helpers


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return "" if value is None else str(value)


def _usec_to_s(value: str | None) -> float | None:
    if not value or value == "infinity":
        return None
    total = 0.0
    for part in value.split():
        for suffix, factor in (("ms", 0.001), ("us", 0.000001), ("min", 60.0), ("s", 1.0), ("h", 3600.0), ("d", 86400.0)):
            if part.endswith(suffix) and part[:-len(suffix)].replace(".", "", 1).isdigit():
                total += float(part[:-len(suffix)]) * factor
                break
        else:
            return None
    return total


def parse_work_listing(text: str, *, total_bytes: int | None) -> dict:
    """``find -printf "%y\\t%T@\\t%P\\n"`` (depth 1-4 under work/) -> the work-stat data shape (contract C.11)."""
    nodes: dict[tuple[str, str], dict] = {}
    for raw in text.splitlines():
        parts = raw.split("\t", 2)
        if len(parts) != 3:
            continue
        kind, mtime_text, rel = parts
        segments = rel.split("/")
        if len(segments) < 2:
            continue
        key = (segments[0], segments[1])
        entry = nodes.setdefault(key, {"jobId": segments[0], "nodeId": segments[1], "mtime": 0.0, "abnormal": False})
        if len(segments) == 2 and kind == "d":
            try:
                entry["mtime"] = float(mtime_text)
            except ValueError:
                entry["mtime"] = 0.0
        # the disk signature of an abnormally ended lease: `.imd/reads` or anything under `artifacts/` still
        # present after the run (a normal run empties both -- spec §5.2, vps §6.3)
        if len(segments) == 4 and ((segments[2] == ".imd" and segments[3] == "reads") or segments[2] == "artifacts"):
            entry["abnormal"] = True
    rows = sorted(nodes.values(), key=lambda r: r["mtime"], reverse=True)
    newest = [{"jobId": r["jobId"], "nodeId": r["nodeId"], "mtimeUtc": iso_utc(r["mtime"]) if r["mtime"] else None,
               "abnormal": r["abnormal"]} for r in rows[:20]]
    return {"count": len(rows), "bytes": total_bytes, "abnormal": sum(1 for r in rows if r["abnormal"]), "newest": newest}

def _read_line(conn: socket.socket, limit: int) -> bytes:
    chunks = bytearray()
    while len(chunks) <= limit:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks += chunk
        if b"\n" in chunk:
            break
    return bytes(chunks.split(b"\n", 1)[0]) + b"\n"


def peer_uid(conn: socket.socket) -> int:
    """The connecting uid via ``SO_PEERCRED`` (struct ucred: pid, uid, gid)."""
    creds = conn.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", creds)
    return uid


def listener_from_systemd() -> socket.socket | None:
    """``LISTEN_FDS == 1`` (and ``LISTEN_PID`` is us) -> fd 3; else ``None`` (main binds the path itself)."""
    if os.environ.get("LISTEN_FDS") != "1":
        return None
    listen_pid = os.environ.get("LISTEN_PID")
    if listen_pid and listen_pid != str(os.getpid()):
        return None
    return socket.socket(fileno=3, family=socket.AF_UNIX, type=socket.SOCK_STREAM)


def _allowed_uid(name: str) -> int:
    import pwd
    return pwd.getpwnam(name).pw_uid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="imd-dashd")
    parser.add_argument("--socket", default=SOCKET_PATH)
    parser.add_argument("--audit", default=AUDIT_PATH)
    parser.add_argument("--seat", type=int, default=None)
    parser.add_argument("--allowed-uid", type=int, default=None)
    parser.add_argument("--allowed-user", default="imd-dash")
    parser.add_argument("--worker-home", default="/home/imd-worker")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    allowed_uid = args.allowed_uid if args.allowed_uid is not None else _allowed_uid(args.allowed_user)
    audit = Audit(args.audit)
    broker = Broker(peer_uid_of=peer_uid, allowed_uid=allowed_uid, audit=audit, seat=args.seat, worker_home=args.worker_home,
                    socket_path=args.socket)
    listener = listener_from_systemd()
    if listener is None:
        try:
            os.unlink(args.socket)
        except OSError:
            pass
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(args.socket)
        os.chmod(args.socket, 0o660)
        listener.listen(8)
    signal.signal(signal.SIGTERM, lambda *_: broker.shutdown())
    signal.signal(signal.SIGINT, lambda *_: broker.shutdown())
    broker.serve_forever(listener)
    broker.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
