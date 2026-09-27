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
import select
import signal
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from imd_dashd import verbs
from imd_dashd.audit import Audit, iso_utc
from imd_dashd.child_unit import RUNTIME_MAX_S, Runner, read_ip_address_deny, run_inprocess, run_transient, unit_name
from imd_dashd.drain import Drain, DrainState
from imd_dashd.gate import ACCEPTED_RE, HEARTBEAT_RE, TERMINAL_RE, GateResult, evaluate, parse_iso
from imd_dashd.redact import find_secret, redact, redact_agent_sentence, redact_tree
from imd_dashd.process_snapshot import snapshot as process_snapshot

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
SYSTEMCTL_TIMEOUT_S = 3
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


APPLY_START_BUDGET_S = 5.0  # admission, transient starts and initial orphan signals
APPLY_EXEC_DEADLINE_S = 15.0  # systemctl enqueue after bounded fresh gate reads
MAX_CONNECTIONS = 10
MAX_SERIALIZED_READS = 4


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
    accepted_monotonic: float | None = None  # None only for broker-owned drain fires
    kill_snapshot: dict = field(default_factory=dict)  # internal identity evidence, never wire data


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


@dataclass
class VerifyWatch:
    """Per applied plan: what the journal said after ``cursor_before`` (spec §11 protocol bullet 4).

    ``verified`` and ``connected`` are two facts and never share one verdict: restart success is
    ``shutting down`` followed by ``runtimes:`` within VERIFY_WITHIN_S; ``connected`` is ``admitted (session``.
    """
    plan_id: str
    verb: str
    kind: str                      # "restart" | "start" | "stop" | "enabled" | "disabled" | "transient" | "kill" | "none"
    cursor_before: str | None
    started: float
    verified: bool | None = None
    connected: bool | str | None = None
    reason: str | None = None
    lines: list[str] = field(default_factory=list)
    cursor_after: str | None = None
    shutting_down_at: float | None = None
    runtimes_at: float | None = None
    reconnecting_since: float | None = None
    unit_state: str | None = None
    done: bool = False              # transient: the thread finished
    rc: int | None = None
    targets: list[tuple[str, int]] = field(default_factory=list)   # kill: ("pid" | "pgid", id) each SIGTERM went to

    def update(self, lines: Sequence[tuple[float, str]], now: float, *, unit_active: bool | None = None,
               unit_enabled: bool | None = None, unit_state: str | None = None) -> None:
        for epoch, text in lines:
            short = _short_line(text)
            if short not in self.lines:
                self.lines.append(short)
            body = text.split(" ", 1)[1] if " " in text else text
            if body == "shutting down" and self.shutting_down_at is None:
                self.shutting_down_at = epoch
            elif body.startswith("runtimes: ") and self.runtimes_at is None and (
                    self.kind != "restart" or self.shutting_down_at is not None):
                self.runtimes_at = epoch
            elif body.startswith("admitted (session "):
                self.connected = True
            elif (body.startswith("reconnecting in ") or body.startswith("connected to ")) and self.connected is not True:
                self.reconnecting_since = self.reconnecting_since or epoch
        if self.connected is not True and self.lines:
            since = self.reconnecting_since or self.shutting_down_at or self.runtimes_at or self.started
            self.connected = "pending (reconnecting since " + time.strftime("%H:%M:%S", time.gmtime(since)) + ")"
        if self.kind == "restart":
            if self.shutting_down_at is not None and self.runtimes_at is not None:
                self.verified = self.runtimes_at - self.shutting_down_at <= VERIFY_WITHIN_S
                if not self.verified:
                    self.reason = f"runtimes: {self.runtimes_at - self.shutting_down_at:.1f} s after shutting down (> {VERIFY_WITHIN_S} s)"
            elif self.shutting_down_at is None and now - self.started > VERIFY_WITHIN_S:
                self.verified, self.reason = False, f"no shutting down within {VERIFY_WITHIN_S} s"
            elif self.shutting_down_at is not None and now - self.shutting_down_at > VERIFY_WITHIN_S:
                self.verified, self.reason = False, f"no runtimes: within {VERIFY_WITHIN_S} s of shutting down"
        elif self.kind == "start":
            if self.runtimes_at is not None:
                self.verified = True
            elif now - self.started > VERIFY_WITHIN_S:
                self.verified, self.reason = False, f"no runtimes: within {VERIFY_WITHIN_S} s"
        elif self.kind == "stop":
            self.connected = None                                  # a stopped daemon has no connection to report
            if unit_state is not None:
                self.unit_state = unit_state
            elif unit_active is not None:  # in-process Mac compatibility
                self.unit_state = "active" if unit_active else "inactive"
            if self.shutting_down_at is not None and self.unit_state in ("inactive", "failed"):
                self.verified = True
            elif now - self.started > VERIFY_WITHIN_S:
                self.verified, self.reason = False, "no shutting down + ActiveState=inactive within 30 s"
        elif self.kind in ("enabled", "disabled"):
            self.connected = None
            if unit_enabled is not None:
                self.verified = unit_enabled is (self.kind == "enabled")
                if not self.verified:
                    self.reason = f"systemctl is-enabled says {'enabled' if unit_enabled else 'disabled'}"

    def to_dict(self, now: float, audit_seq: int | None) -> dict:
        return {"verified": self.verified, "connected": self.connected, "verify_lines": list(self.lines),
                "cursor_after": self.cursor_after, "elapsed_s": round(now - self.started, 1), "audit_seq": audit_seq,
                "reason": self.reason}


def _short_line(text: str) -> str:
    """``2026-09-26T03:40:31.101Z shutting down`` -> ``03:40:31.101Z shutting down`` (spec §11 example)."""
    text = redact(text)
    if len(text) > 24 and text[10] == "T" and text[23] == "Z":
        return text[11:]
    return text


def _drain_verify_line(drain: dict, required: object) -> str:
    """The ``verify`` line of an armed drain (a ``kind="none"`` watch: arming has nothing to wait for)."""
    return f"drain armed · {drain['idleBeats']}/{required} idle beats · expires {drain['expiresAtUtc'][11:16]} UTC"

# ---------------------------------------------------------------- /proc reading (orphans)


def read_procs(proc_root: str, *, now: float, clk_tck: int = 100) -> list[dict]:
    """Every process under *proc_root* as ``{pid, ppid, pgid, uid, cgroup, start_ticks, age_s, rss_b, cmd}``.

    Pure over the directory tree so a ``tmp_path`` fake ``/proc`` drives every test (contract §E).
    """
    btime = 0.0
    try:
        with open(os.path.join(proc_root, "stat"), "rb") as fh:
            for raw in fh:
                if raw.startswith(b"btime "):
                    btime = float(raw.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    procs: list[dict] = []
    try:
        names = os.listdir(proc_root)
    except OSError:
        return procs
    for name in names:
        if not name.isdigit():
            continue
        base = os.path.join(proc_root, name)
        try:
            with open(os.path.join(base, "stat"), "rb") as fh:
                stat_line = fh.read().decode("utf-8", "replace")
            with open(os.path.join(base, "status"), "rb") as fh:
                status = fh.read().decode("utf-8", "replace")
            with open(os.path.join(base, "cgroup"), "rb") as fh:
                cgroup_line = fh.read().decode("utf-8", "replace").strip()
            with open(os.path.join(base, "cmdline"), "rb") as fh:
                cmdline = fh.read()
        except OSError:
            continue
        try:
            rest = stat_line.rsplit(")", 1)[1].split()           # fields 3.. after "(comm)"
            ppid, pgid = int(rest[1]), int(rest[2])
            start_ticks = int(rest[19])                          # field 22
            rss_pages = int(rest[21])                            # field 24
        except (IndexError, ValueError):
            continue
        uid = None
        for line in status.splitlines():
            if line.startswith("Uid:"):
                try:
                    uid = int(line.split()[1])
                except (IndexError, ValueError):
                    uid = None
        if uid is None:
            continue
        cgroup = cgroup_line.split(":", 2)[-1].lstrip("/") if cgroup_line else ""
        cmd = redact_agent_sentence(cmdline.replace(b"\x00", b" ").decode("utf-8", "replace"))[:80]
        procs.append({"pid": int(name), "ppid": ppid, "pgid": pgid, "uid": uid, "cgroup": cgroup,
                      "start_ticks": start_ticks, "age_s": max(0.0, now - (btime + start_ticks / clk_tck)),
                      "rss_b": rss_pages * 4096, "cmd": cmd})
    procs.sort(key=lambda p: p["pid"])
    return procs


def _in_worker_unit(cgroup: str) -> bool:
    return (not cgroup or any(cgroup == root or cgroup.startswith(root + "/") for root in ORPHAN_EXCLUDED_CGROUPS)
            or cgroup.startswith(ORPHAN_EXCLUDED_CGROUP_PREFIX))


def select_orphans(procs: Sequence[dict], *, worker_uid: int = WORKER_UID, min_age_s: float = ORPHAN_MIN_AGE_S) -> list[dict]:
    """Candidates (spec §11 kill-orphans): uid-1000, outside the unit and every ``imd-dash-*`` scope, older than 1 h."""
    out: list[dict] = []
    for proc in procs:
        if proc["uid"] != worker_uid or _in_worker_unit(proc["cgroup"]) or proc["age_s"] <= min_age_s:
            continue
        members = [{"pid": m["pid"], "uid": m["uid"], "cgroup": m["cgroup"], "cmd": m["cmd"]}
                   for m in procs if m["pgid"] == proc["pgid"] and m["pid"] != proc["pid"]]
        out.append({"pid": proc["pid"], "pgid": proc["pgid"], "uid": proc["uid"], "cgroup": proc["cgroup"],
                    "ageS": int(proc["age_s"]), "rssB": proc["rss_b"], "cmd": proc["cmd"], "pgidMembers": members})
    return out


def group_kill_allowed(procs: Sequence[dict], pgid: int, *, worker_uid: int = WORKER_UID) -> bool:
    """Group kill only when EVERY pgid member is outside the unit and is uid-1000 or a direct ``runuser``/``sh -c``
    ancestor of a uid-1000 member (spec §11; mutation proof 34)."""
    members = [p for p in procs if p["pgid"] == pgid]
    if not members:
        return False
    worker_pids = {p["pid"] for p in members if p["uid"] == worker_uid}
    worker_ppids = {p["ppid"] for p in members if p["uid"] == worker_uid}
    for member in members:
        if _in_worker_unit(member["cgroup"]):
            return False
        if member["pid"] in worker_pids:
            continue
        cmd = member["cmd"]
        is_wrapper = cmd.startswith("runuser ") or cmd.startswith("sh -c ") or cmd.startswith("bash -c ") or cmd.startswith("/bin/sh -c ")
        if member["pid"] in worker_ppids and is_wrapper:
            continue
        return False
    return True


def _proc_identity(proc: dict) -> tuple:
    return tuple(proc[key] for key in ("uid", "pgid", "ppid", "cgroup", "start_ticks"))


def _same_process(proc: dict | None, snapshot: dict, *, worker_uid: int) -> bool:
    return (proc is not None and proc["uid"] == worker_uid and not _in_worker_unit(proc["cgroup"])
            and snapshot.get(proc["pid"]) == _proc_identity(proc))


def _same_group(procs: Sequence[dict], pgid: int, snapshot: dict, *, worker_uid: int) -> bool:
    members = [p for p in procs if p["pgid"] == pgid]
    return (bool(members) and all(snapshot.get(p["pid"]) == _proc_identity(p) for p in members)
            and group_kill_allowed(procs, pgid, worker_uid=worker_uid))


def signal_procs(proc_root: str, *, now: float) -> list[dict] | None:
    """A partial /proc read cannot prove whole-group safety or that a target exited."""
    try:
        metadata = process_snapshot(Path(proc_root), now=now)
        procs = read_procs(proc_root, now=now)
        expected = {p["pid"]: (p["uid"], p["pgid"], p["ppid"], p["cgroup"].split(":", 2)[-1].lstrip("/"), p["start_ticks"])
                    for p in metadata}
        if expected != {p["pid"]: _proc_identity(p) for p in procs}:
            return None
        return procs
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def _decide_kill_watch(watch: VerifyWatch, *, pids: set[int], pgids: set[int]) -> None:
    """The ``kill-orphans`` verify (plan ``verified_when: ["pids gone"]``) over a listing taken after every target's
    SIGKILL follow-up: verified when no target -- a pid, or the whole pgid of a group kill -- is listed; the survivors
    are named otherwise. Shared with ``LocalDockerBroker``, which passes the container's ``ps`` listing."""
    survivors = [f"{kind} {ident}" for kind, ident in watch.targets if ident in (pgids if kind == "pgid" else pids)]
    gone = [f"{kind} {ident}" for kind, ident in watch.targets if f"{kind} {ident}" not in survivors]
    watch.verified = not survivors
    watch.reason = None if not survivors else "still listed after SIGKILL: " + ", ".join(survivors)
    watch.lines = ["pids gone: " + ", ".join(gone)] if gone else []

# ---------------------------------------------------------------- the broker


def connection_alive(conn: socket.socket | None) -> bool:
    """Nonblocking EOF check without altering the request socket's timeout.

    UnixSocketBroker sends a newline and never half-closes; SHUT_WR therefore means abandonment.
    Test connection objects without fileno are treated as alive.
    """
    if conn is None or not hasattr(conn, "fileno"):
        return True
    try:
        readable, _, _ = select.select([conn], [], [], 0)
        return not readable or conn.recv(1, socket.MSG_PEEK) != b""
    except (OSError, ValueError):
        return False


def systemctl_argv(verb: str, unit: str = WORKER_UNIT) -> list[str]:
    """Keep the verb first for both recorder prefix matching and readable previews."""
    return ["systemctl", verb, *(["--no-block"] if verb in ("start", "restart", "stop") else []), unit]


def lifecycle_journal_argv(unit: str = WORKER_UNIT, *, pattern: str | None = None) -> list[str]:
    """Exact filtered history query shared with the owner-run VPS compatibility probe."""
    if pattern is None:
        pattern = re.sub(r"\(\?P<[^>]+>", "(?:", f"(?:{ACCEPTED_RE.pattern}|{TERMINAL_RE.pattern})")
    return ["journalctl", "-u", unit, "-o", "json", "--no-pager",
            "--grep", pattern, "--lines", "1", "--case-sensitive=yes"]


def lifecycle_read_outcome(returncode: int, stdout: bytes | str, stderr: bytes | str) -> tuple[list[dict], bool]:
    """Measured JSON grep outcomes, shared by the broker and owner-run probe.

    Empty exit 1 is a successful no-match; diagnostics or malformed/mixed records fail closed.
    """
    if stderr or returncode not in (0, 1):
        return [], False
    try:
        text = stdout.decode("utf-8") if isinstance(stdout, bytes) else stdout
        records = []
        for raw in text.splitlines():
            if not raw.strip() or raw.strip() == "-- No entries --" or raw.startswith("-- cursor: "):
                continue
            record = json.loads(raw)
            if not isinstance(record, dict):
                return [], False
            message = record.get("MESSAGE")
            if isinstance(message, list):
                if not all(type(b) is int and 0 <= b < 256 for b in message):
                    return [], False
                message = bytes(message).decode("utf-8")
            if not isinstance(message, str):
                return [], False
            records.append({**record, "MESSAGE": message})
        succeeded = bool(records) if returncode == 0 else not records
        return (records if succeeded else []), succeeded
    except (UnicodeDecodeError, ValueError, TypeError):
        return [], False


class Broker:
    def __init__(self, *, run: Runner = subprocess.run, popen: Callable = subprocess.Popen,
                 peer_uid_of: Callable[[socket.socket], int], allowed_uid: int, audit: Audit, now: Clock = time.time,
                 seat: int | None, monotonic: Clock = time.monotonic, worker_home: str = "/home/imd-worker", socket_path: str = SOCKET_PATH,
                 standing_url: str = STANDING_URL, proc_root: str = "/proc", unit: str = WORKER_UNIT,
                 broker_dir: str = BROKER_DIR, python: str = PYTHON, worker_uid: int = WORKER_UID,
                 connection_alive_of: Callable = connection_alive) -> None:
        self._run = run
        self._popen = popen                     # reserved for a journal follower; the v1 drain polls on the tick
        self._peer_uid_of = peer_uid_of
        self._allowed_uid = allowed_uid
        self._audit = audit
        self._now = now
        self._monotonic = monotonic
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
        self._state_lock = threading.RLock()
        self._read_lock = threading.Lock()
        self._read_slots = threading.BoundedSemaphore(MAX_SERIALIZED_READS)
        self._connection_alive = connection_alive_of
        self._counts_lock = threading.Lock()
        self._audit_lock = threading.Lock()
        self._in_flight: dict | None = None
        self._drain = Drain(now=now)
        self._drain_offline = False
        self._drain_seen: set[str] = set()
        self._drain_fired: set[str] = set()      #: synthetic plan ids of drain-fired restarts still awaiting their verify line
        self._pending_kills: list[tuple[float, str, int]] = []
        self._kill_snapshots: dict[tuple[str, int], dict] = {}
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
        with self._audit_lock:
            self._seq += 1
            return self._seq

    def _log(self, **fields) -> int:
        try:
            with self._audit_lock:
                return self._audit.append(**fields)
        except (OSError, TypeError, ValueError):
            return -1

    def _in_flight_detail(self) -> dict | None:
        snapshot = self._in_flight
        return None if snapshot is None else dict(snapshot)

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

    def _journal(self, *, since_s: int | None = None, after_cursor: str | None = None, lifecycle_only: bool = False, deadline: float | None = None) -> tuple[list[tuple[float, str]], str | None]:
        lines, cursor, _succeeded = self._journal_read(since_s=since_s, after_cursor=after_cursor, lifecycle_only=lifecycle_only, deadline=deadline)
        return lines, cursor

    def _journal_read(self, *, since_s: int | None = None, after_cursor: str | None = None,
                      lifecycle_only: bool = False, deadline: float | None = None) -> tuple[list[tuple[float, str]], str | None, bool]:
        argv = ["journalctl", "-u", self._unit, "-o", "json", "--no-pager", "--show-cursor"]
        if lifecycle_only:
            # Filter inside journald before limiting output: history may predate idle heartbeats by days.
            argv = lifecycle_journal_argv(self._unit)
        elif after_cursor:
            argv += ["--after-cursor", after_cursor]
        else:
            argv += ["--since", f"-{since_s or JOURNAL_WINDOW_S}s"]
        try:
            done = self._run(argv, capture_output=True, timeout=self._read_timeout(INPROCESS_TIMEOUT_S["gate"], deadline))
        except (subprocess.TimeoutExpired, OSError):
            return [], None, False
        try:
            stdout = done.stdout.decode("utf-8") if lifecycle_only and isinstance(done.stdout, bytes) else _text(done.stdout)
        except UnicodeDecodeError:
            return [], None, False
        if lifecycle_only:
            records, succeeded = lifecycle_read_outcome(done.returncode, done.stdout, done.stderr)
            if not succeeded:
                return [], None, False
            if not records:
                return [], None, True
        elif done.returncode != 0:
            return [], None, False
        lines: list[tuple[float, str]] = []
        cursor: str | None = None
        parse_failed = False
        for raw in stdout.splitlines():
            if not raw.strip() or raw.strip() == "-- No entries --":
                continue
            if raw.startswith("-- cursor: "):
                cursor = raw[len("-- cursor: "):].strip()
                continue
            try:
                record = json.loads(raw)
            except ValueError:
                parse_failed = True
                continue
            if not isinstance(record, dict):
                parse_failed = True
                continue
            message = record.get("MESSAGE")
            if isinstance(message, list):
                if lifecycle_only and not all(type(b) is int and 0 <= b < 256 for b in message):
                    parse_failed = True
                    continue
                try:
                    message = bytes(b for b in message if isinstance(b, int) and 0 <= b < 256).decode(
                        "utf-8", "strict" if lifecycle_only else "replace")
                except UnicodeDecodeError:
                    parse_failed = True
                    continue
            if not isinstance(message, str):
                parse_failed = True
                continue
            try:
                epoch = int(record.get("__REALTIME_TIMESTAMP")) / 1_000_000
            except (TypeError, ValueError):
                epoch = parse_iso(message[:24]) or 0.0
            lines.append((epoch, redact(message)))
        return lines, cursor, (not lifecycle_only or not parse_failed) and bool(
            lines or cursor or not stdout.strip() or stdout.strip() == "-- No entries --")

    def _read_timeout(self, usual: float, deadline: float | None) -> float:
        return usual if deadline is None else min(usual, max(0.5, deadline - self._monotonic()))

    def _unit_state(self, deadline: float | None = None) -> str | None:
        try:
            done = self._run(["systemctl", "is-active", self._unit], capture_output=True, timeout=self._read_timeout(5, deadline))
        except (subprocess.TimeoutExpired, OSError):
            return None
        state = _text(done.stdout).strip()
        if not state:
            return None
        return state

    def _unit_active(self, deadline: float | None = None) -> bool | None:
        state = self._unit_state(deadline)
        return None if state is None else state == "active"

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

    def _outbox_files(self, deadline: float | None = None) -> int | None:
        result = run_inprocess(["ls", "-1A", f"{self._home}/.identitymd/outbox"], run=self._run,
                               timeout_s=self._read_timeout(INPROCESS_TIMEOUT_S["outbox"], deadline))
        if result.timed_out or result.rc != 0:
            return None
        return len([ln for ln in _text(result.stdout).splitlines() if ln.strip()])

    def _standing(self, offline: bool, deadline: float | None = None) -> dict | None:
        # Plans resolve dynamic identity; apply must not start an unbounded whoami transient.
        if offline or (deadline is not None and self._seat is None):
            return None
        url = self._standing_url_for_seat()
        if url is None:
            return None
        result = run_inprocess([self._python, "-I", os.path.join(self._broker_dir, "gate.py"), "--standing", url],
                               run=self._run, timeout_s=self._read_timeout(INPROCESS_TIMEOUT_S["gate"], deadline))
        if result.timed_out or result.rc != 0:
            return None
        try:
            body = json.loads(_text(result.stdout))
        except ValueError:
            return None
        if not isinstance(body, dict) or "running_count" not in body:
            return None
        return body

    def _gate(self, *, offline: bool, deadline: float | None = None) -> tuple[GateResult, list[tuple[float, str]], str | None]:
        standing = self._standing(offline, deadline)
        outbox = self._outbox_files(deadline)
        active = self._unit_active(deadline)
        lines, cursor = self._journal(deadline=deadline)
        lifecycle, _, lifecycle_ok = self._journal_read(lifecycle_only=True, deadline=deadline)
        lines = sorted(set(lines + lifecycle))
        result = evaluate(journal_lines=lines, standing=standing, offline=offline,
                          outbox_files=outbox, unit_active=active,
                          graceful_stop_possible=self.graceful_stop_possible, now=self._now(),
                          lifecycle_read_succeeded=lifecycle_ok)
        return result, lines, cursor

    # ------------------------------------------------------------ transport

    def serve_connection(self, conn: socket.socket) -> None:
        self._serve_connection(conn, _accepted_at=self._monotonic())

    def _serve_connection(self, conn: socket.socket, *, _arrival_busy: dict | None = None, _accepted_at: float | None = None) -> None:
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
                    if _arrival_busy is not None and verb not in verbs.READ_VERBS:
                        self._log(peer_uid=peer, verb=verb, phase="refused", outcome="busy")
                        response = verbs.err("busy", _arrival_busy)
                    else:
                        response = self.handle({"v": verbs.PROTOCOL_VERSION, "verb": verb, "args": args}, peer_uid=peer, _accepted_at=_accepted_at, _conn=conn)
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

    def handle(self, request: dict, *, peer_uid: int, _accepted_at: float | None = None, _conn: socket.socket | None = None) -> dict:
        # Read serialization never delays writes or ping; state sections contain no children.
        accepted_at = self._monotonic() if _accepted_at is None else _accepted_at
        verb = request.get("verb") if isinstance(request, dict) else None
        busy = self._in_flight_detail()
        if peer_uid == self._allowed_uid and busy is not None and verb in (*verbs.WRITE_VERBS, verbs.APPLY_VERB):
            self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="busy")
            return verbs.err("busy", busy)
        if peer_uid == self._allowed_uid and self._needs_read_lock(verb):
            if not self._read_slots.acquire(blocking=False):
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="busy")
                return verbs.err("busy", {"reason": "read queue full"})
            locked = False
            try:
                while self._connection_alive(_conn):
                    locked = self._read_lock.acquire(timeout=0.5)
                    if locked:
                        if not self._connection_alive(_conn):
                            break
                        return self._handle(request, peer_uid=peer_uid, accepted_at=accepted_at)
                return verbs.err("busy", {"reason": "client disconnected"})
            finally:
                if locked:
                    self._read_lock.release()
                self._read_slots.release()
        return self._handle(request, peer_uid=peer_uid, accepted_at=accepted_at)

    def _needs_read_lock(self, verb: object) -> bool:
        if verb not in verbs.READ_VERBS:
            return False
        return (verb in verbs.TRANSIENT_VERBS or
                (self._whoami_key is None and (verb == "seat" or (verb == "gate" and self._seat is None))))

    def _handle(self, request: dict, *, peer_uid: int, accepted_at: float) -> dict:
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
                return self._apply(args, peer_uid, accepted_at)
            return self._plan(verb, args, peer_uid)
        except Exception as exc:                                   # noqa: BLE001 -- the socket loop must survive anything
            self._log(peer_uid=peer_uid, verb=None, phase="refused", outcome=f"internal: {exc.__class__.__name__}")
            return verbs.err("internal", {"reason": exc.__class__.__name__})

    # ------------------------------------------------------------ read verbs

    def _read(self, verb: str, args: dict, peer_uid: int) -> dict:
        with self._counts_lock:
            self._read_counts[verb] = self._read_counts.get(verb, 0) + 1       # audited as counts only (spec §11)
        if verb == "ping":
            drain = self._drain.armed
            return verbs.ok(data={"pid": os.getpid(), "version": VERSION, "uptime_s": round(self._now() - self._started, 1),
                                  "drain_armed": drain is not None, "in_flight": self._in_flight_detail(),
                                  "posture_ok": self.ip_address_deny is not None,
                                  "drain": None if drain is None else drain.to_dict()})
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
        kind = find_secret(payload, allowed_hex64_paths=frozenset({"deviceKey"}))
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
        return verbs.ok(data=redact_tree(body))

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

    def _busy(self) -> dict | None:
        if self._in_flight is not None:
            return verbs.err("busy", self._in_flight_detail())
        return None

    def _armed_drain_refusal(self, verb: str, peer_uid: int, plan_id: str | None = None) -> dict | None:
        if verb in ("restart", "stop") and self._drain.armed is not None:
            self._log(peer_uid=peer_uid, verb=verb, phase="refused", plan_id=plan_id, outcome="drain_already_armed")
            return verbs.err("drain_already_armed", {"hint": "cancel-drain before a manual restart or stop"})
        return None

    def _plan(self, verb: str, args: dict, peer_uid: int) -> dict:
        refusal = self._armed_drain_refusal(verb, peer_uid)
        if refusal is not None:
            return refusal
        busy = self._busy()
        if busy is not None:
            self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="busy", args={"names": sorted(args)})
            return busy
        offline = bool(args.get("offline", False))
        force_node8 = args.get("force_node8")
        preconditions: dict = {}
        argv: list[str]
        verify: dict = {"verified_when": [], "within_s": VERIFY_WITHIN_S, "connected_when": None, "reported_separately": True}
        inverse: dict | None = None
        restart_required_after = False
        warning = WARNING
        if verb in verbs.GATED_VERBS:
            gate, _lines, _cursor = self._gate(offline=offline)
            preconditions = _preconditions(gate)
            if verb != "drain-restart":                # spec §11: drain-restart = plain confirm to arm; G runs at fire time
                refusal = self._gate_refusal(gate, force_node8, verb, peer_uid, preconditions)
                if refusal is not None:
                    return refusal
            if verb == "restart":
                argv = systemctl_argv("restart", self._unit)
                verify = {"verified_when": ["shutting down", "runtimes:"], "within_s": VERIFY_WITHIN_S,
                          "connected_when": "admitted (session", "reported_separately": True}
                inverse = {"verb": "stop", "args": {}}
            elif verb == "stop":
                argv = systemctl_argv("stop", self._unit)
                verify = {"verified_when": ["shutting down", "ActiveState=inactive"], "within_s": VERIFY_WITHIN_S,
                          "connected_when": None, "reported_separately": True}
                inverse = {"verb": "start", "args": {}}
            else:  # drain-restart
                argv = systemctl_argv("restart", self._unit)
                verify = {"verified_when": ["shutting down", "runtimes:"], "within_s": VERIFY_WITHIN_S,
                          "connected_when": "admitted (session", "reported_separately": True}
                inverse = {"verb": "cancel-drain", "args": {}}
                if self._drain.armed is not None:
                    self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="drain_already_armed")
                    return verbs.err("drain_already_armed", self._drain.armed.to_dict())
                warning = ("arms a broker-side wait for 4 consecutive idle heartbeats; the same fresh gate runs at fire time; "
                           "expires after 4 h; survives TUI exit; a broker restart drops it") + " · " + WARNING
        elif verb == "start":
            argv = systemctl_argv("start", self._unit)
            preconditions = {"unit_active": self._unit_active()}
            verify = {"verified_when": ["runtimes:"], "within_s": VERIFY_WITHIN_S, "connected_when": "admitted (session",
                      "reported_separately": True}
            inverse = {"verb": "stop", "args": {}}
            warning = "starts the seat; it will accept work as soon as it is admitted"
        elif verb in ("enable-boot", "disable-boot"):
            argv = ["systemctl", "enable" if verb == "enable-boot" else "disable", self._unit]
            preconditions = {"boot_enabled": self._unit_enabled()}
            verify = {"verified_when": ["systemctl is-enabled"], "within_s": VERIFY_WITHIN_S, "connected_when": None,
                      "reported_separately": True}
            inverse = {"verb": verbs.INVERSE[verb], "args": {}}
            warning = "no technical risk; changes only what happens at the next boot"
        elif verb == "cancel-drain":
            if self._drain.armed is None:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="drain_not_armed")
                return verbs.err("drain_not_armed")
            argv = []
            preconditions = {"drain": self._drain.armed.to_dict()}
            warning = "clears the armed drain; nothing is restarted"
        elif verb == "skills-set":
            skill_id = args["skill_id"]
            if not verbs.SKILL_ID_RE.fullmatch(skill_id):
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="bad_skill_id",
                          args={"skill_id": "<refused>", "on": bool(args["on"])})
                return verbs.err("bad_skill_id")
            if self._skills_listing is None:
                self._transient_read("skills")
            if self._skills_listing is not None and skill_id not in self._skills_listing:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="skill_not_listed", args={"skill_id": skill_id})
                return verbs.err("skill_not_listed", {"skill_id": skill_id})
            if self.ip_address_deny is None:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="child_posture_unavailable", args={"skill_id": skill_id})
                return verbs.err("child_posture_unavailable", {"verb": verb})
            argv = ["imd", "skills", "add" if args["on"] else "remove", skill_id]
            preconditions = {"skill_id": skill_id, "on": bool(args["on"]), "listed": self._skills_listing is not None}
            verify = {"verified_when": ["imd skills re-listed"], "within_s": RUNTIME_MAX_S["skills-set"], "connected_when": None,
                      "reported_separately": True}
            inverse = {"verb": "skills-set", "args": {"skill_id": skill_id, "on": not args["on"]}}
            restart_required_after = True
            warning = "skillsOptOut is read once at daemon start: the change applies after a (drained) restart"
        elif verb == "doctor":
            now = self._now()
            if self._last_doctor is not None and now - self._last_doctor < DOCTOR_MIN_INTERVAL_S:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="doctor_too_soon")
                return verbs.err("doctor_too_soon", {"next_allowed_at": iso_utc(self._last_doctor + DOCTOR_MIN_INTERVAL_S)})
            if self.ip_address_deny is None:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="child_posture_unavailable")
                return verbs.err("child_posture_unavailable", {"verb": verb})
            argv = ["imd", "doctor"]
            preconditions = {"last_doctor_utc": None if self._last_doctor is None else iso_utc(self._last_doctor),
                             "runtime_max_s": RUNTIME_MAX_S["doctor"]}
            verify = {"verified_when": ["exit 0"], "within_s": RUNTIME_MAX_S["doctor"], "connected_when": None,
                      "reported_separately": True}
            warning = "spends one runtime turn and quota; leaves a work/doctor-* transcript; excluded from cost by cwd"
        elif verb == "kill-orphans":
            procs = signal_procs(self._proc_root, now=self._now())
            if procs is None:
                self._log(verb=verb, phase="refused", outcome="process snapshot unavailable")
                return verbs.err("unreadable", {"what": "process snapshot"})
            candidates = {c["pid"]: c for c in select_orphans(procs, worker_uid=self._worker_uid)}
            pids = [int(p) for p in args["pids"]]
            if any(p not in candidates for p in pids):
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="bad_args", args={"pids": pids})
                return verbs.err("bad_args", {"reason": "every pid must be a current orphan candidate", "pids": pids})
            plan_rows = [candidates[p] for p in pids]
            mode = {}
            for pgid in sorted({candidates[p]["pgid"] for p in pids}):
                mode[str(pgid)] = "group" if group_kill_allowed(procs, pgid, worker_uid=self._worker_uid) else "individual"
            argv = ["kill", "-TERM"]
            preconditions = {"candidates": plan_rows, "kill_mode_by_pgid": mode, "min_age_s": ORPHAN_MIN_AGE_S,
                             "sigkill_after_s": KILL_GRACE_S}
            verify = {"verified_when": ["pids gone"], "within_s": KILL_GRACE_S, "connected_when": None, "reported_separately": True}
            warning = "kills the listed processes with SIGTERM (SIGKILL after 10 s); pgid members are listed in preconditions"
        else:
            return verbs.err("bad_verb", {"verb": verb})

        with self._state_lock:
            plan = self._plans.create(verb, args, argv, preconditions, inverse, verify, force_node8=force_node8)
        if verb == "kill-orphans":
            plan.kill_snapshot = {p["pid"]: _proc_identity(p) for p in procs}
        seq = self._log(peer_uid=peer_uid, verb=verb, phase="plan", plan_id=plan.plan_id,
                        args={k: ("<node8>" if k == "force_node8" and v else v) for k, v in args.items()},
                        preconditions=preconditions, outcome="planned")
        return verbs.ok(plan={"plan_id": plan.plan_id, "verb": verb, "argv": argv, "expires_at": iso_utc(plan.expires),
                              "single_use": True, "preconditions": preconditions, "warning": warning, "inverse": inverse,
                              "verify": verify, "restart_required_after": restart_required_after, "audit_seq": seq})

    def _gate_refusal(self, gate: GateResult, force_node8: object, verb: str, peer_uid: int, preconditions: dict) -> dict | None:
        """The plan-time and apply-time refusal for a gated verb; ``None`` when the gate lets it through."""
        if gate.unknown is not None:
            code = f"gate_unknown({gate.unknown})"
            self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome=code, preconditions=preconditions)
            return verbs.err(code, {"reason": gate.reason, "preconditions": preconditions})
        if force_node8:
            if gate.graceful_stop_possible is not True:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="force_disabled", preconditions=preconditions)
                return verbs.err("force_disabled", {"graceful_stop_possible": gate.graceful_stop_possible})
            running = _running_node8(gate)
            if running is None or force_node8 != running:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="force_node8_mismatch", preconditions=preconditions)
                return verbs.err("force_node8_mismatch", {"running": running})
            # (a)-(c) bypassed; (d) and (e) never
            if gate.outbox_files != 0:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="gate_blocked", preconditions=preconditions)
                return verbs.err("gate_blocked", {"reason": f"outbox {gate.outbox_files} file(s)", "preconditions": preconditions})
            if gate.unit_active is not True:
                self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="gate_blocked", preconditions=preconditions)
                return verbs.err("gate_blocked", {"reason": "unit inactive", "preconditions": preconditions})
            return None
        if not gate.safe:
            self._log(peer_uid=peer_uid, verb=verb, phase="refused", outcome="gate_blocked", preconditions=preconditions)
            return verbs.err("gate_blocked", {"reason": gate.reason, "preconditions": preconditions})
        return None

    # ------------------------------------------------------------ write verbs: apply

    def _late_apply(self, accepted_at: float | None, peer_uid: int, *, plan_spent: bool, plan_id: str | None = None, budget: float = APPLY_START_BUDGET_S) -> dict | None:
        if accepted_at is None:  # drain fires have no waiting client
            return None
        waited = max(0.0, self._monotonic() - accepted_at)
        if waited <= budget:
            return None
        detail = {"waited_s": round(waited, 3), "plan_spent": plan_spent,
                  "hint": "plan afresh; use pepepane --offline if plane reads are slow" if plan_spent else "plan remains available; retry promptly or use pepepane --offline"}
        self._log(peer_uid=peer_uid, verb="apply", phase="refused", plan_id=plan_id,
                  outcome="apply_late", args=detail)
        return verbs.err("apply_late", detail)

    def _apply(self, args: dict, peer_uid: int, accepted_at: float) -> dict:
        plan_id = str(args["plan_id"])
        if not verbs.PLAN_ID_RE.fullmatch(plan_id):
            self._log(peer_uid=peer_uid, verb="apply", phase="refused", outcome="unknown_plan")
            return verbs.err("unknown_plan")
        if not self._lock.acquire(blocking=False):
            self._log(peer_uid=peer_uid, verb="apply", phase="refused", plan_id=plan_id, outcome="busy")
            return verbs.err("busy", self._in_flight_detail() or {})
        release = True
        try:
            now = self._now()
            refusal = self._late_apply(accepted_at, peer_uid, plan_spent=False, plan_id=plan_id)
            if refusal is not None:
                return refusal
            try:
                with self._state_lock:
                    plan = self._plans.consume(plan_id, now)
                    plan.accepted_monotonic = accepted_at
                    self._watches[plan_id] = VerifyWatch(plan_id=plan_id, verb=plan.verb, kind="none",
                                                        cursor_before=None, started=now)
            except PlanError as exc:
                self._log(peer_uid=peer_uid, verb="apply", phase="refused", plan_id=plan_id, outcome=exc.code)
                return verbs.err(exc.code, exc.detail)
            try:
                result = self._dispatch_apply(plan, args, peer_uid, now)
            except (OSError, ValueError) as exc:
                result = verbs.err("internal", {"reason": type(exc).__name__})
            uncertain = result.get("error") == "timeout" and result.get("detail", {}).get("outcome") == "timeout"
            if not result.get("ok") and not result.get("detail", {}).get("partial") and not uncertain:
                with self._state_lock:
                    watch = self._watches[plan_id]
                    watch.kind, watch.done, watch.verified = "none", True, False
                    watch.reason = result["error"] + ": " + json.dumps(result.get("detail", {}), sort_keys=True)
            if plan.verb in ("skills-set", "doctor") and result.get("ok"):
                release = False  # successful worker start transfers cleanup
            return result
        finally:
            if release:
                self._in_flight = None
                self._lock.release()

    def _dispatch_apply(self, plan: Plan, args: dict, peer_uid: int, now: float) -> dict:
        plan_id = plan.plan_id
        if args["confirm"] != plan_id[:4]:
            self._log(peer_uid=peer_uid, verb=plan.verb, phase="refused", plan_id=plan_id, outcome="bad_confirm")
            return verbs.err("bad_confirm")
        self._in_flight = {"verb": plan.verb, "plan_id": plan_id, "since": iso_utc(now)}
        if plan.verb in verbs.GATED_VERBS:
            return self._apply_gated(plan, args, peer_uid)
        if plan.verb in ("start", "enable-boot", "disable-boot"):
            return self._apply_systemctl(plan, peer_uid)
        if plan.verb == "cancel-drain":
            event = self._drain.cancel()
            # WP8's CONTROL polls verify after every apply (contract §C.16): nothing to wait for, verified at once
            self._watches[plan_id] = VerifyWatch(plan_id=plan_id, verb=plan.verb, kind="none", cursor_before=None,
                                                 started=now, verified=True, lines=["drain cleared · nothing restarted"])
            seq = self._log(peer_uid=peer_uid, verb=plan.verb, phase=event, plan_id=plan_id, outcome="cancelled")
            return verbs.ok(result={"outcome": "cancelled", "exit_code": 0, "cursor_before": None, "audit_seq": seq,
                                    "preconditions": plan.preconditions})
        if (plan.verb == "doctor" and self._last_doctor is not None
                and now - self._last_doctor < DOCTOR_MIN_INTERVAL_S):
            self._log(peer_uid=peer_uid, verb="doctor", phase="refused", plan_id=plan_id, outcome="doctor_too_soon")
            return verbs.err("doctor_too_soon")
        if plan.verb in ("skills-set", "doctor"):
            result = self._apply_transient(plan, peer_uid)
            return result
        if plan.verb == "kill-orphans":
            return self._apply_kill(plan, peer_uid)
        return verbs.err("internal", {"reason": "unhandled verb"})

    def _apply_gated(self, plan: Plan, args: dict, peer_uid: int) -> dict:
        refusal = self._armed_drain_refusal(plan.verb, peer_uid, plan.plan_id)
        if refusal is not None:
            return refusal
        offline = bool(plan.args.get("offline", False))
        force_node8 = args.get("force_node8")
        if plan.force_node8 and force_node8 != plan.force_node8:
            self._log(peer_uid=peer_uid, verb=plan.verb, phase="refused", plan_id=plan.plan_id, outcome="force_node8_mismatch")
            return verbs.err("force_node8_mismatch", {"reason": "type the running node8 at plan AND apply"})
        if plan.verb == "drain-restart":
            self._drain_offline = offline
            event = self._drain.arm(plan.plan_id)
            # arming is verified at once (a kind="none" watch, so verify never answers unknown_plan to WP8's CONTROL);
            # the restart the drain fires later is verified under its own synthetic plan id (Task 6.12 `_fire_drain`)
            self._watches[plan.plan_id] = VerifyWatch(
                plan_id=plan.plan_id, verb=plan.verb, kind="none", cursor_before=None, started=self._now(), verified=True,
                lines=[_drain_verify_line(self._drain.armed.to_dict(), plan.preconditions.get("idle_beats_required"))])
            seq = self._log(peer_uid=peer_uid, verb=plan.verb, phase=event, plan_id=plan.plan_id,
                            preconditions=plan.preconditions, outcome="armed")
            return verbs.ok(result={"outcome": "armed", "exit_code": None, "cursor_before": None, "audit_seq": seq,
                                    "preconditions": plan.preconditions, "drain": self._drain.armed.to_dict()})
        gate, _lines, cursor_before = self._gate(offline=offline, deadline=None if plan.accepted_monotonic is None else plan.accepted_monotonic + APPLY_EXEC_DEADLINE_S)           # FRESH at apply (spec §11 (a)-(e))
        preconditions = _preconditions(gate)
        refusal = self._gate_refusal(gate, plan.force_node8, plan.verb, peer_uid, preconditions)
        if refusal is not None:
            return refusal
        if gate.plane["mode"] == "local-only" and not plan.force_node8 and args.get("local_only_ack") != verbs.LOCAL_ONLY_ACK:
            self._log(peer_uid=peer_uid, verb=plan.verb, phase="refused", plan_id=plan.plan_id,
                      outcome="local_only_ack_required", preconditions=preconditions)
            return verbs.err("local_only_ack_required", {"plane": gate.plane, "ack": verbs.LOCAL_ONLY_ACK})
        return self._exec_systemctl(plan, preconditions, cursor_before, peer_uid)

    def _apply_systemctl(self, plan: Plan, peer_uid: int) -> dict:
        _lines, cursor_before = self._journal(since_s=60, deadline=None if plan.accepted_monotonic is None else plan.accepted_monotonic + APPLY_EXEC_DEADLINE_S)
        return self._exec_systemctl(plan, plan.preconditions, cursor_before, peer_uid)

    def _exec_systemctl(self, plan: Plan, preconditions: dict, cursor_before: str | None, peer_uid: int) -> dict:
        refusal = self._late_apply(plan.accepted_monotonic, peer_uid, plan_spent=True, plan_id=plan.plan_id, budget=APPLY_EXEC_DEADLINE_S)
        if refusal is not None:
            return refusal
        started = self._now()  # evidence may arrive before the queue command returns
        try:
            done = self._run(list(plan.argv), capture_output=True, timeout=SYSTEMCTL_TIMEOUT_S)
            exit_code: int | None = done.returncode
        except subprocess.TimeoutExpired:
            exit_code = None
        except OSError:
            exit_code = -1
        kind = {"restart": "restart", "drain-restart": "restart", "stop": "stop", "start": "start",
                "enable-boot": "enabled", "disable-boot": "disabled"}[plan.verb]
        watch = VerifyWatch(plan_id=plan.plan_id, verb=plan.verb, kind=kind, cursor_before=cursor_before, started=started)
        self._watches[plan.plan_id] = watch
        outcome = "applied" if exit_code == 0 else ("timeout" if exit_code is None else f"exit {exit_code}")
        seq = self._log(peer_uid=peer_uid, verb=plan.verb, phase="apply", plan_id=plan.plan_id, preconditions=preconditions,
                        outcome=outcome, cursor_before=cursor_before)
        if exit_code != 0:
            code = "timeout" if exit_code is None else "internal"
            detail = {"outcome": outcome, "exit_code": exit_code, "audit_seq": seq}
            if exit_code is not None:  # a timeout may follow successful job acceptance
                watch.kind, watch.done, watch.verified = "none", True, False
                watch.reason = code + ": " + json.dumps(detail, sort_keys=True)
            return verbs.err(code, detail)
        return verbs.ok(result={"outcome": "applied", "exit_code": exit_code, "cursor_before": cursor_before, "audit_seq": seq,
                                "preconditions": preconditions})

    def _apply_transient(self, plan: Plan, peer_uid: int) -> dict:
        verb = plan.verb
        seq_no = self._next_seq()
        watch = VerifyWatch(plan_id=plan.plan_id, verb=verb, kind="transient", cursor_before=None, started=self._now())
        self._watches[plan.plan_id] = watch
        previous_doctor = self._last_doctor
        if verb == "doctor":
            self._last_doctor = self._now()

        def worker() -> None:
            try:
                def guarded_run(argv, *, timeout, **kwargs):
                    if argv[0] == "systemd-run":
                        refusal = self._late_apply(plan.accepted_monotonic, peer_uid, plan_spent=True, plan_id=plan.plan_id)
                        if refusal is not None:
                            raise PlanError("apply_late", refusal["detail"])
                    return self._run(argv, timeout=timeout, **kwargs)
                result = run_transient(verb, seq_no, plan.argv, run=guarded_run, ip_address_deny=self.ip_address_deny or "")
                watch.lines = [_CURRENCY_FIGURE_RE.sub("", redact(ln)) for ln in _text(result.stdout).splitlines() if ln.strip()]
                watch.rc = result.rc
                watch.verified = (result.rc == 0) and not result.timed_out
                watch.reason = "timed out (unit killed)" if result.timed_out else (None if result.rc == 0 else f"exit {result.rc}")
                if verb == "skills-set" and watch.verified:
                    self._skills_listing = None                     # the re-listing below refreshes it
                    listing = self._transient_read("skills")        # spec §11 skills row: verify by re-listing
                    rows = [ln.split() for ln in (listing.get("data") or {}).get("lines", [])] if listing.get("ok") else []
                    row = next((r for r in rows if len(r) > 1 and r[0] in ("on", "off") and r[1] == plan.args["skill_id"]), None)
                    watch.verified = row is not None and (row[0] == "on") is bool(plan.args["on"])
                    if not watch.verified:
                        watch.reason = "re-listing disagrees"
            except PlanError as exc:
                self._last_doctor = previous_doctor
                watch.verified, watch.reason = False, f"{exc.code}: {json.dumps(exc.detail, sort_keys=True)}"
            except OSError as exc:
                watch.verified, watch.reason = False, exc.__class__.__name__
            finally:
                watch.done = True
                self._log(peer_uid=peer_uid, verb=verb, phase="verify", plan_id=plan.plan_id, outcome="finished",
                          verified=watch.verified)
                self._in_flight = None
                self._lock.release()

        seq = self._log(peer_uid=peer_uid, verb=verb, phase="apply", plan_id=plan.plan_id, preconditions=plan.preconditions,
                        outcome="started", args={"unit": unit_name(verb, seq_no)})
        try:
            thread = threading.Thread(target=worker, name=f"imd-dashd-{verb}-{seq_no}", daemon=True)
            self._threads[plan.plan_id] = thread
            thread.start()
        except Exception:  # constructor/start failure: no worker owns cleanup yet
            self._threads.pop(plan.plan_id, None)
            self._last_doctor = previous_doctor  # no child ran: preserve the preceding cooldown
            watch.done, watch.verified, watch.reason = True, False, "thread start failed"
            self._log(peer_uid=peer_uid, verb=plan.verb, phase="verify", plan_id=plan.plan_id,
                      outcome="thread start failed", verified=False)
            return verbs.err("internal", {"reason": "thread start failed"})
        return verbs.ok(result={"outcome": "started", "exit_code": None, "cursor_before": None, "audit_seq": seq,
                                "preconditions": plan.preconditions, "unit": unit_name(verb, seq_no)})

    def _initial_signal(self, argv: list[str]) -> dict | None:
        try:
            done = self._run(argv, capture_output=True, timeout=5)
        except subprocess.TimeoutExpired:
            return verbs.err("timeout", {"reason": "orphan signal command timed out", "outcome": "timeout"})
        except OSError as exc:
            return verbs.err("internal", {"reason": type(exc).__name__})
        if done.returncode != 0:
            return verbs.err("internal", {"reason": "orphan signal command failed", "exit_code": done.returncode})
        return None

    def _apply_kill(self, plan: Plan, peer_uid: int) -> dict:
        now = self._now()
        rows = plan.preconditions["candidates"]
        killed: list[dict] = []
        skipped: list[dict] = []
        by_pgid: dict[int, list[dict]] = {}
        for row in rows:
            by_pgid.setdefault(row["pgid"], []).append(row)
        for pgid, members in by_pgid.items():
            checked = signal_procs(self._proc_root, now=self._now())
            if checked is None:
                self._log(verb="kill-orphans", phase="refused", outcome="process snapshot unavailable")
                return self._finish_kill(plan, peer_uid, now, killed, skipped,
                                         verbs.err("unreadable", {"what": "process snapshot"}))
            procs = {p["pid"]: p for p in checked}
            if (_same_group(list(procs.values()), pgid, plan.kill_snapshot, worker_uid=self._worker_uid)
                    and all(_same_process(procs.get(r["pid"]), plan.kill_snapshot, worker_uid=self._worker_uid) for r in members)):
                refusal = self._late_apply(plan.accepted_monotonic, peer_uid, plan_spent=True, plan_id=plan.plan_id)
                if refusal is not None:
                    return self._finish_kill(plan, peer_uid, now, killed, skipped, refusal)
                refusal = self._initial_signal(["kill", "-TERM", "--", f"-{pgid}"])
                if refusal is not None:
                    return self._finish_kill(plan, peer_uid, now, killed, skipped, refusal)
                self._pending_kills.append((now + KILL_GRACE_S, "pgid", pgid))
                self._kill_snapshots[("pgid", pgid)] = dict(plan.kill_snapshot)
                killed.append({"mode": "group", "pgid": pgid, "pids": [m["pid"] for m in members]})
                continue
            for row in members:
                checked = signal_procs(self._proc_root, now=self._now())
                if checked is None:
                    self._log(verb="kill-orphans", phase="refused", outcome="process snapshot unavailable")
                    return self._finish_kill(plan, peer_uid, now, killed, skipped,
                                             verbs.err("unreadable", {"what": "process snapshot"}))
                procs = {p["pid"]: p for p in checked}
                live = procs.get(row["pid"])
                # re-check cgroup and start time (pid reuse) before each individual kill (spec §11)
                if not _same_process(live, plan.kill_snapshot, worker_uid=self._worker_uid):
                    skipped.append({"pid": row["pid"], "reason": "changed since plan"})
                    continue
                refusal = self._late_apply(plan.accepted_monotonic, peer_uid, plan_spent=True, plan_id=plan.plan_id)
                if refusal is not None:
                    return self._finish_kill(plan, peer_uid, now, killed, skipped, refusal)
                refusal = self._initial_signal(["kill", "-TERM", str(row["pid"])])
                if refusal is not None:
                    return self._finish_kill(plan, peer_uid, now, killed, skipped, refusal)
                self._pending_kills.append((now + KILL_GRACE_S, "pid", row["pid"]))
                self._kill_snapshots[("pid", row["pid"])] = dict(plan.kill_snapshot)
                killed.append({"mode": "individual", "pid": row["pid"]})
        return self._finish_kill(plan, peer_uid, now, killed, skipped)

    def _finish_kill(self, plan: Plan, peer_uid: int, now: float, killed: list[dict], skipped: list[dict],
                     refusal: dict | None = None) -> dict:
        """Retain the audit and completion watch for exactly the targets already signalled."""
        if refusal is not None:
            accounted = {pid for item in killed for pid in (item["pids"] if item["mode"] == "group" else [item["pid"]])}
            accounted.update(item["pid"] for item in skipped)
            skipped.extend({"pid": row["pid"], "reason": refusal["error"]}
                           for row in plan.preconditions["candidates"] if row["pid"] not in accounted)
        if refusal is not None and not killed:
            self._log(peer_uid=peer_uid, verb=plan.verb, phase="refused", plan_id=plan.plan_id,
                      outcome=refusal["error"], args={"killed": [], "skipped": skipped})
            return verbs.err(refusal["error"], {**refusal.get("detail", {}), "plan_spent": True,
                                                 "partial": False, "killed": [], "skipped": skipped})
        # the plan's verify ("pids gone"): tick() decides it once every target's SIGKILL follow-up has run
        targets = [("pgid", k["pgid"]) if k["mode"] == "group" else ("pid", k["pid"]) for k in killed]
        self._watches[plan.plan_id] = VerifyWatch(
            plan_id=plan.plan_id, verb="kill-orphans", kind="kill", cursor_before=None, started=now, targets=targets,
            verified=None if targets else True,
            lines=[] if targets else [f"nothing killed · {len(skipped)} pid(s) changed since plan"])
        seq = self._log(peer_uid=peer_uid, verb="kill-orphans", phase="apply", plan_id=plan.plan_id,
                        preconditions={"pids": [r["pid"] for r in plan.preconditions["candidates"]], "kill_mode_by_pgid": plan.preconditions["kill_mode_by_pgid"]},
                        outcome="partial" if refusal is not None else ("applied" if killed else "nothing to kill"),
                        args={"killed": killed})
        if refusal is not None:
            return verbs.err(refusal["error"], {**refusal.get("detail", {}), "plan_spent": True, "partial": True,
                                                 "killed": killed, "skipped": skipped, "audit_seq": seq})
        return verbs.ok(result={"outcome": "applied", "exit_code": 0, "cursor_before": None, "audit_seq": seq,
                                "preconditions": plan.preconditions, "killed": killed, "skipped": skipped})

    def _resolve_kill_watches(self, now: float, sigkilled: set[tuple[str, int]]) -> None:
        """Decide each open ``kill-orphans`` watch whose targets have no SIGKILL follow-up still queued. A target that
        needed the SIGKILL on this very tick is decided on the next one, so a process still being reaped is not
        reported as a survivor. Writes one ``verify`` audit line per decision (spec §11)."""
        queued = {(kind, ident) for _deadline, kind, ident in self._pending_kills}
        ready = [w for w in list(self._watches.values()) if w.kind == "kill" and w.verified is None
                 and not any(t in queued or t in sigkilled for t in w.targets)]
        if not ready:
            return
        procs = signal_procs(self._proc_root, now=now)
        if procs is None:
            for watch in ready:
                watch.verified, watch.reason = False, "process snapshot unavailable"
                self._log(verb=watch.verb, phase="verify", plan_id=watch.plan_id, outcome=watch.reason, verified=False)
            return
        pids, pgids = {p["pid"] for p in procs}, {p["pgid"] for p in procs}
        for watch in ready:
            _decide_kill_watch(watch, pids=pids, pgids=pgids)
            self._log(verb=watch.verb, phase="verify", plan_id=watch.plan_id,
                      outcome="verified" if watch.verified else "not verified", verified=watch.verified)

    # ------------------------------------------------------------ verify

    def _verify(self, plan_id: str) -> dict:
        watch = self._watches.get(plan_id)
        if watch is None:
            return verbs.err("unknown_plan", {"plan_id": plan_id})
        now = self._now()
        if watch.kind == "transient":
            if not watch.done:
                return verbs.ok(data={"verified": None, "connected": None, "verify_lines": [], "cursor_after": None,
                                      "elapsed_s": round(now - watch.started, 1), "audit_seq": None, "reason": None})
            return verbs.ok(data={"verified": watch.verified, "connected": None, "verify_lines": list(watch.lines),
                                  "cursor_after": None, "elapsed_s": round(now - watch.started, 1), "audit_seq": None,
                                  "reason": watch.reason, "rc": watch.rc})
        if watch.kind in ("none", "kill"):          # decided at apply (drain arm, cancel-drain) or by tick() (kill-orphans)
            return verbs.ok(data=watch.to_dict(now, None))
        lines: list[tuple[float, str]] = []
        cursor_after = None
        if watch.cursor_before:
            lines, cursor_after = self._journal(after_cursor=watch.cursor_before)
        else:
            lines, _cursor = self._journal(since_s=int(now - watch.started) + 5)
            lines = [(e, t) for e, t in lines if e >= watch.started - 1]
        unit_state = self._unit_state() if watch.kind == "stop" else None
        unit_enabled = self._unit_enabled() if watch.kind in ("enabled", "disabled") else None
        with self._state_lock:
            if cursor_after:
                watch.cursor_after = cursor_after
            previously = (watch.verified, watch.connected)
            watch.update(lines, now, unit_state=unit_state, unit_enabled=unit_enabled)
            seq = None
            if (watch.verified, watch.connected) != previously:
                seq = self._log(verb=watch.verb, phase="verify", plan_id=plan_id, outcome="verified" if watch.verified else
                                ("pending" if watch.verified is None else "not verified"), verified=watch.verified,
                                connected=watch.connected, cursor_before=watch.cursor_before, cursor_after=watch.cursor_after)
            return verbs.ok(data=watch.to_dict(now, seq))

    # ------------------------------------------------------------ housekeeping

    def _flush_read_counts(self, now: float, *, force: bool = False) -> None:
        """Read verbs are audited as counts only (spec §11): one line per READ_COUNT_FLUSH_S, and at exit."""
        with self._counts_lock:
            if not self._read_counts or (not force and now - self._reads_flushed_at < READ_COUNT_FLUSH_S):
                return
            counts, self._read_counts = self._read_counts, {}
            self._reads_flushed_at = now
        self._log(verb=None, phase="reads", outcome="counts", args={"counts": counts})

    def tick(self, now: float | None = None) -> list[str]:
        return self._tick(now)

    def _tick(self, now: float | None = None) -> list[str]:
        """Drain beats, plan/watch expiry, SIGKILL follow-ups. Returns the audit events it wrote (tests read them)."""
        now = self._now() if now is None else now
        events: list[str] = []
        self._flush_read_counts(now)
        with self._state_lock:
            self._plans.purge(now)
        for fired in list(self._drain_fired):              # the drain's own restart gets its verify line (spec §11 audit column)
            data = self._verify(fired).get("data") or {}
            if data.get("verified") is not None or fired not in self._watches:
                self._drain_fired.discard(fired)
        for plan_id in [k for k, w in list(self._watches.items()) if now - w.started > VERIFY_WATCH_S and not (w.kind == "transient" and not w.done)]:
            del self._watches[plan_id]
        armed = self._drain.armed
        if armed is not None:
            lines, _cursor = self._journal(since_s=TICK_S * 2 + 5)
            # Read outside every state/write lock. A cancelled/replaced drain cannot
            # consume this old snapshot, and an active apply never queues behind it.
            if self._lock.acquire(blocking=False):
                try:
                    if self._drain.armed is armed:
                        event = self._drain.tick(now)
                        if event:
                            events.append(event)
                            self._log(verb="drain-restart", phase=event, outcome="expired")
                        else:
                            for epoch, text in lines:
                                match = HEARTBEAT_RE.match(text)
                                if not match or epoch <= self._last_tick:
                                    continue
                                key = f"{epoch}:{text}"
                                if key in self._drain_seen:
                                    continue
                                self._drain_seen.add(key)
                                armed_before = self._drain.armed
                                event = self._drain.on_heartbeat("idle" if match.group("work") == "idle" else "running", epoch)
                                if event:
                                    events.append(event)
                                    if event == "drain_fire":
                                        self._fire_drain(events, armed_before, lock_held=True)
                                    else:
                                        self._log(verb="drain-restart", phase=event, outcome=event)
                                if self._drain.armed is None:
                                    break
                            if len(self._drain_seen) > 2000:
                                self._drain_seen = set(list(self._drain_seen)[-500:])
                finally:
                    self._lock.release()
        still: list[tuple[float, str, int]] = []
        sigkilled: set[tuple[str, int]] = set()
        with self._state_lock:
            pending, self._pending_kills = self._pending_kills, []
        for deadline, kind, ident in pending:
            if now < deadline:
                still.append((deadline, kind, ident))
                continue
            procs = signal_procs(self._proc_root, now=now)
            if procs is None:
                self._kill_snapshots.pop((kind, ident), None)
                self._log(verb="kill-orphans", phase="refused", outcome="process snapshot unavailable before SIGKILL")
                continue
            alive = any(p["pgid"] == ident for p in procs) if kind == "pgid" else any(p["pid"] == ident for p in procs)
            snapshot = self._kill_snapshots.pop((kind, ident), {})
            safe = (_same_group(procs, ident, snapshot, worker_uid=self._worker_uid) if kind == "pgid" else
                    _same_process(next((p for p in procs if p["pid"] == ident), None), snapshot, worker_uid=self._worker_uid))
            if alive and not safe:
                self._log(verb="kill-orphans", phase="refused", outcome="identity changed before SIGKILL",
                          args={"kind": kind, "id": ident})
            if alive and safe:
                argv = ["kill", "-KILL", "--", f"-{ident}"] if kind == "pgid" else ["kill", "-KILL", str(ident)]
                try:
                    self._run(argv, capture_output=True, timeout=5)
                except (subprocess.TimeoutExpired, OSError):
                    pass
                events.append("sigkill")
                sigkilled.add((kind, ident))
        with self._state_lock:
            self._pending_kills.extend(still)
        self._resolve_kill_watches(now, sigkilled)         # the kill-orphans verify: "pids gone" (or the survivors named)
        self._last_tick = now
        return events

    def _fire_drain(self, events: list[str], armed_before: DrainState, *, lock_held: bool = False) -> None:
        if not lock_held and not self._lock.acquire(blocking=False):
            self._drain.restore(armed_before)    # keep waiting (same drain, same deadline): something else is in flight
            return
        plan_id = secrets.token_hex(8)
        self._in_flight = {"verb": "drain-restart", "plan_id": plan_id, "since": iso_utc(self._now())}
        try:
            gate, _lines, cursor_before = self._gate(offline=self._drain_offline)
            preconditions = _preconditions(gate)
            if gate.unknown is not None or not gate.safe or (gate.plane["mode"] == "local-only" and not self._drain_offline):
                self._drain.restore(armed_before)  # re-arm the SAME drain from zero beats; DRAIN_MAX_S still caps it (spec §11)
                self._log(verb="drain-restart", phase="drain_rearmed", plan_id=armed_before.plan_id, preconditions=preconditions,
                          outcome=gate.reason or f"plane {gate.plane['mode']}")
                events.append("drain_rearmed")
                return
            plan = Plan(plan_id=plan_id, verb="drain-restart", args={"offline": self._drain_offline},
                        argv=systemctl_argv("restart", self._unit), created=self._now(), expires=self._now(),
                        preconditions=preconditions, inverse=None, verify={}, force_node8=None, spent=True)
            self._in_flight = {"verb": "drain-restart", "plan_id": plan.plan_id, "since": iso_utc(self._now())}
            self._log(verb="drain-restart", phase="drain_fire", plan_id=plan.plan_id, preconditions=preconditions, outcome="firing")
            self._exec_systemctl(plan, preconditions, cursor_before, peer_uid=0)
            self._drain_fired.add(plan.plan_id)          # tick() writes its verify line once the journal decides
        finally:
            self._in_flight = None
            if not lock_held:
                self._lock.release()

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
        """Bounded admission stays responsive while one serialized operation writes.

        Ten connections and one housekeeping thread at most. Decoded transient reads
        occupy at most four slots; control/root reads have six reserved slots.
        Busy is captured at accept and checked again at dispatch so a concurrent
        apply cannot become a delayed write after the first one exits.
        """
        listener.settimeout(1.0)
        slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        connections: list[threading.Thread] = []
        tick_thread = None

        def serve(conn, busy, accepted_at):
            try:
                self._serve_connection(conn, _arrival_busy=busy, _accepted_at=accepted_at)
            finally:
                slots.release()

        try:
            while not self.stop_requested:
                try:
                    conn, _addr = listener.accept()
                    accepted_at = self._monotonic()
                except socket.timeout:
                    conn = None
                except OSError:
                    break
                connections = [thread for thread in connections if thread.is_alive()]
                if conn is not None:
                    busy = self._in_flight_detail()
                    if slots.acquire(blocking=False):
                        try:
                            thread = threading.Thread(target=serve, args=(conn, busy, accepted_at), name="imd-dash-request")
                            thread.start()
                        except (RuntimeError, OSError):
                            slots.release()
                            conn.close()
                        else:
                            connections.append(thread)
                    else:
                        conn.close()  # overload is refused, never queued for a later write
                now = self._now()
                if now - self._last_tick >= TICK_S and (tick_thread is None or not tick_thread.is_alive()):
                    try:
                        tick_thread = threading.Thread(target=self.tick, args=(now,), name="imd-dash-tick")
                        tick_thread.start()
                    except (RuntimeError, OSError):
                        tick_thread = None
                if self.idle_exit_due(now):
                    break
        finally:
            for thread in connections:
                thread.join()
            if tick_thread is not None:
                tick_thread.join()


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


def _preconditions(gate: GateResult) -> dict:
    return {"idle_beats": gate.idle_beats, "idle_beats_required": gate.idle_beats_required,
            "newest_heartbeat_age_s": gate.newest_heartbeat_age_s, "plane": dict(gate.plane),
            "last_lifecycle_line": gate.last_lifecycle_line, "lifecycle_open": gate.lifecycle_open,
            "outbox_files": gate.outbox_files, "unit_active": gate.unit_active,
            "graceful_stop_possible": gate.graceful_stop_possible}


def _running_node8(gate: GateResult) -> str | None:
    if not gate.lifecycle_open or not gate.last_lifecycle_line:
        return None
    match = ACCEPTED_RE.match(gate.last_lifecycle_line)
    if not match:
        return None
    return match.group("node8") or match.group("node8_q") or match.group("node8_c")

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


__all__ = ["AUDIT_PATH", "BROKER_DIR", "BROKER_IDLE_EXIT_S", "Broker", "DOCTOR_MIN_INTERVAL_S", "INPROCESS_TIMEOUT_S",
           "KILL_GRACE_S", "ORPHAN_EXCLUDED_CGROUPS", "ORPHAN_EXCLUDED_CGROUP_PREFIX", "ORPHAN_MIN_AGE_S", "PLAN_TTL_S",
           "Plan", "PlanError", "PlanStore", "SOCKET_PATH", "STANDING_URL", "VERIFY_WATCH_S", "VERIFY_WITHIN_S", "VERSION",
           "VerifyWatch", "WARNING", "group_kill_allowed", "listener_from_systemd", "main", "parse_work_listing", "peer_uid",
           "read_procs", "select_orphans"]

if __name__ == "__main__":
    raise SystemExit(main())
