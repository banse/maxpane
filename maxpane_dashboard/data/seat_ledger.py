"""The seat's durable work ledger: sqlite (WAL) rows keyed ``(seat, node8, acceptedAt)`` (spec §5.6).

The daemon persists no run history and logs a failed run exactly like a success, so this file
is the fork's answer to retention (journald ≈53–115 d, Docker log = container lifetime): one
row per ``accepted`` line, closed by ``submitted``/``answered``/a fuzz outcome, **stored** only
when ``submission stored`` follows before the next accept, joined to the control plane's
verdict by ``submissionHash.startswith(hash12)``.

Ingest is idempotent by key (replaying the same lines yields the same rows) and drives the
in-memory ``LedgerState`` detector the manager folds into the status document. Nothing here
imports Textual, subprocess or the network; every third-party string passes ``redact()`` before
it is written.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from maxpane_dashboard.analytics.seat_redact import redact, redact_agent_sentence
from maxpane_dashboard.data import seat_log_grammar as g
from maxpane_dashboard.data.seat_log_grammar import LogLine, parse_ts
from maxpane_dashboard.data.seat_models import SEAT_BLOCK_KEYS, SEAT_ROW_KEYS

LEDGER_FILE = "seat_ledger.sqlite"  #: under ~/.maxpane; WAL; busy_timeout
LEDGER_SCHEMA_VERSION = 1
LEDGER_BUSY_TIMEOUT_MS = 5000
PRE_AGENT_FAILURE_S = 1.0  #: accept→submit < 1 s with no `working:` line = pre-agent failure (spec §5.1)
RESEARCH_JOIN_S = 2.0  #: a research session joins the `accepted question` within ~2 s (spec §5.4, §10)
IDLE_WINDOW_S = 180  #: == analytics.seat_signals.IDLE_WINDOW_S (spec §9); mirrored, not imported (WP7 writes that module)
CONNECTION_WINDOW_S = 86400  #: disconnects24h / reconnects24h of the §7 daemon block
REASONS_PER_CYCLE = 2  #: == data.seat_api.MAX_REASONS_PER_CYCLE (spec §6); mirrored, not imported (WP5 writes that module)
TRANSCRIPT_RETENTION_DAYS = 30  #: Claude cleanupPeriodDays default (fill8 §4): unjoined older rows read "transcript expired" (spec §5.4)
WORK_DIR_JOIN_S = 300.0  #: a work dir's mtime ≈ its accept time (spec §5.2); attach_work_dirs joins within this window

META_KEYS = (
    "schema_version", "ledger_since_utc", "grammar_version", "sessions_watermark_mtime", "api_backfill_done_utc", "seat",
    "sessions_skipped_oversize",  #: cumulative summariser oversize skips (the --since watermark counts each file once)
)

Json = Union[None, bool, int, float, str, list, dict]
Clock = Callable[[], float]
#: tier_for(runtime, model, effort, at, *, seat=None) -> str | None  (analytics.seat_tiers, injected by WP7)
TierLookup = Callable[..., Optional[str]]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    key TEXT PRIMARY KEY, seat INTEGER, node8 TEXT NOT NULL, node_id TEXT, job_id TEXT, role TEXT, kind TEXT,
    accepted_utc TEXT NOT NULL, submitted_utc TEXT, stored_utc TEXT, hash12 TEXT, duration_s REAL,
    agent_ran INTEGER, pre_agent_failure INTEGER, cancelled TEXT, lease_closed INTEGER, repair INTEGER, resent INTEGER,
    interrupted_by_restart INTEGER, max_turns INTEGER, runtime TEXT, model TEXT, effort TEXT, tier_derived TEXT,
    turns INTEGER, turns_definition TEXT, tokens_input INTEGER, tokens_output INTEGER, tokens_cached INTEGER,
    tokens_cache_write INTEGER, side_model_json TEXT, ttft_ms INTEGER, wall_ms INTEGER, turn1_context INTEGER,
    max_turns_reached INTEGER, api_errors_json TEXT, session_files INTEGER, tokens_reason TEXT,
    outcome TEXT, outcome_as_of_utc TEXT, accepted_at_api TEXT, verdict_lag_s INTEGER, failure_reason TEXT,
    failure_class TEXT, node_key TEXT, objective TEXT, source_row TEXT, source_outcome TEXT, source_reason TEXT,
    phases_json TEXT, last_message TEXT, last_message_utc TEXT, work_dir_abnormal INTEGER, updated_utc TEXT
);
CREATE INDEX IF NOT EXISTS tasks_accepted ON tasks(accepted_utc);
CREATE INDEX IF NOT EXISTS tasks_hash12 ON tasks(hash12);
CREATE INDEX IF NOT EXISTS tasks_job ON tasks(job_id);
CREATE TABLE IF NOT EXISTS sessions (
    path TEXT PRIMARY KEY, task_key TEXT, runtime TEXT, cwd TEXT, kind TEXT, started_utc TEXT, mtime REAL,
    model TEXT, effort TEXT, turns INTEGER, tokens_input INTEGER, tokens_output INTEGER, tokens_cached INTEGER,
    tokens_cache_write INTEGER, side_model_json TEXT, ttft_ms INTEGER, wall_ms INTEGER, turn1_context INTEGER,
    max_turns_reached INTEGER, api_errors_json TEXT, quota_json TEXT, bytes INTEGER, skipped_oversize INTEGER, error TEXT
);
CREATE TABLE IF NOT EXISTS days (
    day_utc TEXT PRIMARY KEY, tasks INTEGER, stored INTEGER, not_stored INTEGER, accepted INTEGER, rejected INTEGER,
    failed INTEGER, pending INTEGER, tokens_input INTEGER, tokens_output INTEGER, tokens_cached INTEGER,
    tokens_cache_write INTEGER, turns INTEGER, p50_s REAL, longest_s REAL, verdict_lag_p50_s REAL,
    source_json TEXT, updated_utc TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_ROW_SELECT = "SELECT * FROM tasks"


def task_key(seat: int | None, node8: str, accepted_utc: str) -> str:
    return f"{seat if seat is not None else '-'}/{node8}/{accepted_utc}"


class LedgerSchemaMismatch(RuntimeError):
    """The file on disk was written by a different ``LEDGER_SCHEMA_VERSION``."""


@dataclass
class LedgerState:
    """The detector state ``drain()`` feeds (in-memory; the open row is restored from sqlite on open)."""

    idle_beats: int = 0
    last_heartbeat: LogLine | None = None
    heartbeats_recent: list[tuple[float, str]] = field(default_factory=list)  # (epoch, "idle"|"running"|"disconnected")
    consecutive_disconnected: int = 0
    disconnects_24h: int = 0
    reconnects_24h: int = 0
    last_admitted_utc: str | None = None
    paused_hint: dict | None = None  # {"until","failedRuns","reason","seenUtc"}
    fleet_online: int | None = None
    fleet_enrolled: int | None = None
    fleet_seen_utc: str | None = None
    daemon_version: str | None = None
    release_available: str | None = None
    build_mismatch: bool = False
    invocation: str | None = None
    submitted_since_start: int | None = None
    open_key: str | None = None
    current: dict | None = None  # SEAT_BLOCK_KEYS["seat_current"] shape while a row is open
    last_lifecycle: LogLine | None = None
    # (invented) bookkeeping the state machine needs; not folded into the document directly
    paused_local_utc: str | None = None  # RATE_LIMITED: `…; pausing new work for five minutes`
    runtimes: str | None = None  # the `<list>` group of the newest RUNTIMES line
    last_ts: str | None = None  # newest daemon stamp ingested
    last_accept_ts: str | None = None  # newest ACCEPTED_* stamp (the `stored before the next accept` rule)
    connection_events: list[tuple[float, str]] = field(default_factory=list)  # (epoch, "disconnect"|"admitted")
    pending_boundary: bool = False  # an invocation change already counted the restart the RUNTIMES line will announce


@dataclass(frozen=True)
class IngestResult:
    lines: int
    opened: int
    closed: int
    stored: int
    restarts: int
    unknown: int
    events: tuple[str, ...]  # "submitted" | "stored" | "accepted" | "restart" for the manager's event-driven bumps


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_api_timestamp(text: object) -> float | None:
    """Epoch from an API stamp: ISO ``Z`` (``submittedAt``) or Postgres text ``2026-09-26 03:11:29.985+00`` (``acceptedAt``)."""
    if not isinstance(text, str) or not text:
        return None
    candidate = text.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    elif candidate.endswith("+00"):
        candidate = candidate[:-3] + "+00:00"
    candidate = candidate.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _dumps(value: object) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: object) -> Json:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


class SeatLedger:
    """sqlite-backed ledger; one instance per manager, single-threaded asyncio use."""

    def __init__(self, path: str | Path, *, seat: int | None, now: Clock | None = None,
                 tier_lookup: TierLookup | None = None) -> None:
        self._path = Path(path)
        self._seat = seat
        self._now: Clock = now or time.time
        self._tier_lookup = tier_lookup
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(f"PRAGMA busy_timeout={LEDGER_BUSY_TIMEOUT_MS}")
        self._conn.executescript(SCHEMA_SQL)
        self._state = LedgerState()
        self._init_meta()
        self._load_state()

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        self._conn.close()

    @property
    def state(self) -> LedgerState:
        return self._state

    def _init_meta(self) -> None:
        version = self.meta_get("schema_version")
        if version is None:
            self.meta_set("schema_version", LEDGER_SCHEMA_VERSION)
        elif version != LEDGER_SCHEMA_VERSION:
            self._conn.close()
            raise LedgerSchemaMismatch(f"{self._path}: schema_version {version!r} != {LEDGER_SCHEMA_VERSION}")
        if self.meta_get("ledger_since_utc") is None:
            self.meta_set("ledger_since_utc", _iso(self._now()))
        self.meta_set("grammar_version", g.GRAMMAR_VERSION)
        self.meta_set("seat", self._seat)

    def _load_state(self) -> None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE submitted_utc IS NULL AND cancelled IS NULL AND source_row = 'local' "
            "AND COALESCE(interrupted_by_restart, 0) = 0 AND COALESCE(phases_json, '') NOT LIKE '%\"failed\"%' "
            "ORDER BY accepted_utc DESC LIMIT 1"
        ).fetchone()
        if row is not None:
            self._state.open_key = row["key"]
            self._state.last_accept_ts = row["accepted_utc"]
            self._state.current = self._current_from_row(row)
        newest = self._conn.execute("SELECT MAX(accepted_utc) AS ts FROM tasks WHERE source_row = 'local'").fetchone()
        if newest is not None and newest["ts"]:
            self._state.last_ts = newest["ts"]

    # ------------------------------------------------------------------ meta
    def meta_get(self, key: str) -> Json | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else _loads(row["value"])

    def meta_set(self, key: str, value: Json) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    # ------------------------------------------------------------------ ingest (Appendix B state machine)
    def ingest(self, lines: Iterable[LogLine]) -> IngestResult:
        n = opened = closed = stored = restarts = unknown = 0
        events: list[str] = []
        with self._conn:
            cur = self._conn.cursor()
            for line in lines:
                n += 1
                if line.kind == g.KIND_UNKNOWN:
                    unknown += 1
                if line.ts:
                    if self._state.invocation is not None and line.invocation is not None \
                            and line.invocation != self._state.invocation:
                        self._restart_boundary(cur, line)
                        restarts += 1
                        events.append("restart")
                        self._state.pending_boundary = True
                    if line.invocation is not None:
                        self._state.invocation = line.invocation
                    if self._state.last_ts is None or line.ts > self._state.last_ts:
                        self._state.last_ts = line.ts
                kind = line.kind
                if kind in g.ACCEPTED_KINDS:
                    if self._accept(cur, line):
                        opened += 1
                    events.append("accepted")
                elif kind == g.KIND_MODEL_LINE:
                    self._model(cur, line, line.fields.get("rt"), line.fields.get("model"))
                elif kind == g.KIND_MODEL_REFUSE:
                    self._model(cur, line, line.fields.get("rt"), None)
                elif kind == g.KIND_PHASE:
                    self._phase(cur, line)
                elif kind in (g.KIND_SUBMITTED, g.KIND_ANSWERED, g.KIND_FUZZ_OUTCOME):
                    if self._close(cur, line):
                        closed += 1
                    events.append("submitted")
                elif kind == g.KIND_STORED:
                    if self._stored(cur, line):
                        stored += 1
                    events.append("stored")
                elif kind == g.KIND_CANCELLED:
                    self._cancelled(cur, line)
                elif kind == g.KIND_SERVER_ERROR:
                    if line.fields.get("code") == "unknown_lease":
                        self._lease_closed(cur, line)
                elif kind == g.KIND_RESENDING:
                    self._resending(cur, line)
                elif kind == g.KIND_LOCAL_FAIL:
                    self._local_fail(cur, line)
                elif kind == g.KIND_RATE_LIMITED:
                    self._state.paused_local_utc = line.ts
                elif kind == g.KIND_HEARTBEAT:
                    self._heartbeat(line)
                elif kind == g.KIND_ADMITTED:
                    self._state.last_admitted_utc = line.ts
                    self._connection_event(line, "admitted")
                elif kind in (g.KIND_SERVER_CLOSED, g.KIND_WS_RESPONSE, g.KIND_WS_SOCKET, g.KIND_RECONNECTING):
                    # every loss prints `reconnecting in`; a silent drop prints nothing else (captured 2026-09-26 02:45)
                    self._connection_event(line, "disconnect")
                elif kind == g.KIND_RUNTIMES:
                    self._state.runtimes = line.fields.get("list")
                    if self._state.pending_boundary:
                        self._state.pending_boundary = False
                    else:
                        self._restart_boundary(cur, line)
                        restarts += 1
                        events.append("restart")
                elif kind == g.KIND_RELEASE_OK:
                    self._state.daemon_version = line.fields.get("version")
                    self._state.release_available = None
                elif kind == g.KIND_RELEASE_AVAIL:
                    self._state.daemon_version = line.fields.get("installed")
                    self._state.release_available = line.fields.get("available")
                elif kind == g.KIND_UPDATED:
                    self._state.daemon_version = line.fields.get("to")
                    self._state.release_available = None
                elif kind == g.KIND_BUILD_SKEW:
                    self._state.build_mismatch = True
                if kind in g.ACCEPTED_KINDS or kind in g.TERMINAL_KINDS:
                    self._state.last_lifecycle = line
        self._recount_beats()
        return IngestResult(lines=n, opened=opened, closed=closed, stored=stored, restarts=restarts,
                            unknown=unknown, events=tuple(events))

    # --- per-kind handlers ---------------------------------------------------------------
    def _accept(self, cur: sqlite3.Cursor, line: LogLine) -> bool:
        f = line.fields
        node8 = f["node8"] or ""
        if line.kind == g.KIND_ACCEPTED_RESEARCH:
            role, kind = "question", "research"
        elif line.kind == g.KIND_ACCEPTED_FUZZ:
            role, kind = "campaign", "fuzz"
        else:
            role, kind = f.get("role"), "code"
        key = task_key(self._seat, node8, line.ts)
        if self._state.open_key not in (None, key):
            # capacity is 1: a new accept while a row is open leaves that row unclosed (leaseClosed unknown)
            self._state.open_key = None
        exists = cur.execute("SELECT 1 FROM tasks WHERE key = ?", (key,)).fetchone() is not None
        max_turns = int(f["max_turns"]) if f.get("max_turns") else None
        cur.execute(
            "INSERT INTO tasks(key, seat, node8, role, kind, accepted_utc, max_turns, agent_ran, pre_agent_failure, "
            "lease_closed, repair, resent, interrupted_by_restart, source_row, source_outcome, source_reason, "
            "phases_json, updated_utc) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 'local', 'none', 'none', '[]', ?) "
            "ON CONFLICT(key) DO UPDATE SET role = excluded.role, kind = excluded.kind, max_turns = excluded.max_turns, "
            "updated_utc = excluded.updated_utc",
            (key, self._seat, node8, role, kind, line.ts, max_turns, _iso(self._now())),
        )
        self._state.open_key = key
        self._state.last_accept_ts = line.ts
        self._state.current = self._current_from_row(self._row(cur, key))
        return not exists


    def _open(self, cur: sqlite3.Cursor) -> sqlite3.Row | None:
        return None if self._state.open_key is None else self._row(cur, self._state.open_key)


    def _model(self, cur: sqlite3.Cursor, line: LogLine, runtime: str | None, model: str | None) -> None:
        row = self._open(cur)
        if row is None:
            return
        tier = None
        if self._tier_lookup is not None:
            tier = self._tier_lookup(runtime, model, None, line.ts, seat=self._seat)
        phases = list(_loads(row["phases_json"]) or [])
        if "working" not in phases:
            phases.append("working")
        cur.execute(
            "UPDATE tasks SET agent_ran = 1, runtime = ?, model = ?, tier_derived = ?, phases_json = ?, updated_utc = ? "
            "WHERE key = ?",
            (runtime, model, tier, _dumps(phases), _iso(self._now()), row["key"]),
        )
        self._state.current = self._current_from_row(self._row(cur, row["key"]))


    def _phase(self, cur: sqlite3.Cursor, line: LogLine) -> None:
        row = self._open(cur)
        if row is None:
            return
        phase = line.fields.get("phase") or ""
        phases = list(_loads(row["phases_json"]) or [])
        if phase not in phases:
            phases.append(phase)
        repair = 1 if (phase == "repairing" or row["repair"]) else 0
        if phase == "working":
            message = redact_agent_sentence(line.fields.get("msg") or "")
            cur.execute(
                "UPDATE tasks SET phases_json = ?, repair = ?, last_message = ?, last_message_utc = ?, updated_utc = ? "
                "WHERE key = ?",
                (_dumps(phases), repair, message, line.ts, _iso(self._now()), row["key"]),
            )
        else:
            cur.execute(
                "UPDATE tasks SET phases_json = ?, repair = ?, updated_utc = ? WHERE key = ?",
                (_dumps(phases), repair, _iso(self._now()), row["key"]),
            )
        self._state.current = self._current_from_row(self._row(cur, row["key"]))
        if self._state.current is not None:
            self._state.current["phase"] = phase


    def _close(self, cur: sqlite3.Cursor, line: LogLine) -> bool:
        node8 = line.fields.get("node8")
        row = None
        if node8:
            row = cur.execute(
                "SELECT * FROM tasks WHERE node8 = ? AND seat IS ? AND submitted_utc IS NULL AND source_row = 'local' "
                "AND accepted_utc <= ? ORDER BY accepted_utc DESC LIMIT 1",
                (node8, self._seat, line.ts),
            ).fetchone()
        if row is None and node8 is None:  # fuzz outcome lines carry no node8: the open row
            row = self._open(cur)
        if row is None:
            return False
        accepted = parse_ts(row["accepted_utc"])
        submitted = parse_ts(line.ts)
        duration = None if accepted is None or submitted is None else max(0.0, submitted - accepted)
        pre_agent = 1 if (not row["agent_ran"] and duration is not None and duration < PRE_AGENT_FAILURE_S) else 0
        cur.execute(
            "UPDATE tasks SET submitted_utc = ?, duration_s = ?, pre_agent_failure = ?, updated_utc = ? WHERE key = ?",
            (line.ts, duration, pre_agent, _iso(self._now()), row["key"]),
        )
        if self._state.open_key == row["key"]:
            self._state.open_key = None
            self._state.current = None
        return True


    def _stored(self, cur: sqlite3.Cursor, line: LogLine) -> bool:
        hash12 = line.fields.get("hash12")
        already = cur.execute("SELECT key FROM tasks WHERE hash12 = ? AND seat IS ?", (hash12, self._seat)).fetchone()
        if already is not None:
            return False  # replay
        row = cur.execute(
            "SELECT * FROM tasks WHERE seat IS ? AND source_row = 'local' AND submitted_utc IS NOT NULL "
            "AND stored_utc IS NULL AND COALESCE(lease_closed, 0) = 0 AND submitted_utc <= ? AND submitted_utc >= ? "
            "ORDER BY submitted_utc DESC LIMIT 1",
            (self._seat, line.ts, self._state.last_accept_ts or ""),
        ).fetchone()
        if row is None:
            return False  # a stored line after the next accept never resurrects an older row (spec §5.1 ledger rules)
        cur.execute(
            "UPDATE tasks SET stored_utc = ?, hash12 = ?, updated_utc = ? WHERE key = ?",
            (line.ts, hash12, _iso(self._now()), row["key"]),
        )
        return True


    def _cancelled(self, cur: sqlite3.Cursor, line: LogLine) -> None:
        # the line carries the LEASE id, which appears nowhere else: attach by time, never by prefix (fill6 §6)
        row = self._open(cur)
        if row is None:
            return
        cur.execute(
            "UPDATE tasks SET cancelled = ?, updated_utc = ? WHERE key = ?",
            (line.fields.get("reason"), _iso(self._now()), row["key"]),
        )
        self._state.current = self._current_from_row(self._row(cur, row["key"]))


    def _lease_closed(self, cur: sqlite3.Cursor, line: LogLine) -> None:
        row = cur.execute(
            "SELECT * FROM tasks WHERE seat IS ? AND source_row = 'local' AND submitted_utc IS NOT NULL "
            "AND stored_utc IS NULL AND submitted_utc <= ? ORDER BY submitted_utc DESC LIMIT 1",
            (self._seat, line.ts),
        ).fetchone()
        if row is None:
            return
        cur.execute("UPDATE tasks SET lease_closed = 1, updated_utc = ? WHERE key = ?", (_iso(self._now()), row["key"]))


    def _resending(self, cur: sqlite3.Cursor, line: LogLine) -> None:
        cur.execute(
            "UPDATE tasks SET resent = 1, updated_utc = ? WHERE seat IS ? AND source_row = 'local' "
            "AND submitted_utc IS NOT NULL AND stored_utc IS NULL AND COALESCE(lease_closed, 0) = 0 AND submitted_utc <= ?",
            (_iso(self._now()), self._seat, line.ts),
        )


    def _local_fail(self, cur: sqlite3.Cursor, line: LogLine) -> None:
        row = self._open(cur)
        if row is None:
            return
        phases = list(_loads(row["phases_json"]) or [])
        phases.append("failed")  # spec §5.1 localFailure == "failed" in row["phases"] (contract C.6 decision; no column)
        cur.execute(
            "UPDATE tasks SET phases_json = ?, last_message = ?, last_message_utc = ?, updated_utc = ? WHERE key = ?",
            (_dumps(phases), redact_agent_sentence(line.fields.get("msg") or ""), line.ts, _iso(self._now()), row["key"]),
        )
        self._state.open_key = None
        self._state.current = None

    def _restart_boundary(self, cur: sqlite3.Cursor, line: LogLine) -> None:
        if self._state.open_key is not None:
            cur.execute(
                "UPDATE tasks SET interrupted_by_restart = 1, updated_utc = ? WHERE key = ?",
                (_iso(self._now()), self._state.open_key),
            )
        self._state.open_key = None
        self._state.current = None
        self._state.submitted_since_start = None
        self._state.build_mismatch = False
        self._state.release_available = None
        self._state.paused_hint = None


    def _heartbeat(self, line: LogLine) -> None:
        f = line.fields
        epoch = parse_ts(line.ts)
        self._state.last_heartbeat = line
        if f.get("state") == "disconnected":
            state = "disconnected"
        elif f.get("work") == "idle":
            state = "idle"
        else:
            state = "running"
        if epoch is not None:
            self._state.heartbeats_recent.append((epoch, state))
        if f.get("submitted") is not None:
            self._state.submitted_since_start = int(f["submitted"])
        if f.get("online") is not None:
            self._state.fleet_online = int(f["online"])
            self._state.fleet_enrolled = int(f["enrolled"]) if f.get("enrolled") is not None else None
            self._state.fleet_seen_utc = line.ts
        if f.get("until") is not None:
            self._state.paused_hint = {
                "until": f["until"],
                "failedRuns": int(f["failed"]) if f.get("failed") else None,
                "reason": redact_agent_sentence(f.get("reason") or "") or None,
                "seenUtc": line.ts,
            }
        else:
            self._state.paused_hint = None


    def _connection_event(self, line: LogLine, kind: str) -> None:
        epoch = parse_ts(line.ts)
        if epoch is None:
            return
        events = self._state.connection_events
        if kind == "disconnect" and events and events[-1][1] == "disconnect":
            return  # one loss = one event, however many retries print
        events.append((epoch, kind))


    def _recount_beats(self) -> None:
        now = self._now()
        st = self._state
        st.heartbeats_recent = [(t, s) for (t, s) in st.heartbeats_recent if t >= now - IDLE_WINDOW_S]
        idle = 0
        for _, s in reversed(st.heartbeats_recent):
            if s != "idle":
                break
            idle += 1
        st.idle_beats = idle
        disconnected = 0
        for _, s in reversed(st.heartbeats_recent):
            if s != "disconnected":
                break
            disconnected += 1
        st.consecutive_disconnected = disconnected
        st.connection_events = [(t, k) for (t, k) in st.connection_events if t >= now - CONNECTION_WINDOW_S]
        st.disconnects_24h = sum(1 for _, k in st.connection_events if k == "disconnect")
        st.reconnects_24h = sum(1 for _, k in st.connection_events if k == "admitted")
        if st.current is not None and st.open_key is not None:
            accepted = parse_ts(st.current.get("startedUtc") or "")
            st.current["elapsedS"] = None if accepted is None else max(0, int(now - accepted))

    # ------------------------------------------------------------------ rows
    def _row(self, cur: sqlite3.Cursor, key: str) -> sqlite3.Row:
        return cur.execute("SELECT * FROM tasks WHERE key = ?", (key,)).fetchone()

    def _current_from_row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        current = {k: None for k in SEAT_BLOCK_KEYS["seat_current"]}
        phases = _loads(row["phases_json"]) or []
        current.update({
            "nodeId8": row["node8"], "jobId": row["job_id"], "role": row["role"], "kind": row["kind"],
            "phase": phases[-1] if phases else None, "startedUtc": row["accepted_utc"], "elapsedS": None,
            "maxTurns": row["max_turns"], "model": row["model"], "tierDerived": row["tier_derived"],
            "lastMessage": row["last_message"], "lastMessageUtc": row["last_message_utc"],
            "planeSince": None, "objective": row["objective"], "nodeKey": row["node_key"],
        })
        return current

    @staticmethod
    def _tokens(row: sqlite3.Row) -> dict | None:
        values = (row["tokens_input"], row["tokens_output"], row["tokens_cached"], row["tokens_cache_write"])
        if all(v is None for v in values):
            return None
        return {"input": values[0], "output": values[1], "cached": values[2], "cacheWrite": values[3]}

    def _to_row_dict(self, row: sqlite3.Row) -> dict:
        api_only = row["source_row"] == "api"
        out = {k: None for k in SEAT_ROW_KEYS["seat_tasks_rows"]}
        out.update({
            "key": row["key"], "nodeId8": None if api_only else row["node8"], "nodeId": row["node_id"],
            "jobId": row["job_id"], "role": row["role"], "kind": row["kind"], "acceptedUtc": row["accepted_utc"],
            "submittedUtc": row["submitted_utc"], "storedUtc": row["stored_utc"], "hash12": row["hash12"],
            "durationS": row["duration_s"], "agentRan": bool(row["agent_ran"]) if row["agent_ran"] is not None else None,
            "preAgentFailure": bool(row["pre_agent_failure"]) if row["pre_agent_failure"] is not None else None,
            "cancelled": row["cancelled"], "leaseClosed": bool(row["lease_closed"]) if row["lease_closed"] is not None else None,
            "repair": bool(row["repair"]) if row["repair"] is not None else None,
            "resent": bool(row["resent"]) if row["resent"] is not None else None,
            "interruptedByRestart": bool(row["interrupted_by_restart"]) if row["interrupted_by_restart"] is not None else None,
            "runtime": row["runtime"], "model": row["model"], "effort": row["effort"], "tierDerived": row["tier_derived"],
            "turns": row["turns"], "turnsDefinition": row["turns_definition"], "tokens": self._tokens(row),
            "sideModelTokens": _loads(row["side_model_json"]), "ttftMs": row["ttft_ms"], "wallMs": row["wall_ms"],
            "turn1Context": row["turn1_context"],
            "maxTurnsReached": bool(row["max_turns_reached"]) if row["max_turns_reached"] is not None else None,
            "apiErrors": _loads(row["api_errors_json"]) or [], "sessionFiles": row["session_files"],
            "tokensReason": row["tokens_reason"], "outcome": row["outcome"], "outcomeAsOfUtc": row["outcome_as_of_utc"],
            "acceptedAtApi": row["accepted_at_api"], "verdictLagS": row["verdict_lag_s"],
            "failureReason": row["failure_reason"], "failureClass": row["failure_class"], "nodeKey": row["node_key"],
            "objective": row["objective"],
            "source": {"row": row["source_row"], "outcome": row["source_outcome"], "reason": row["source_reason"]},
            "phases": _loads(row["phases_json"]) or [], "lastMessage": row["last_message"],
            "lastMessageUtc": row["last_message_utc"],
            "workDirAbnormal": bool(row["work_dir_abnormal"]) if row["work_dir_abnormal"] is not None else None,
            "maxTurns": row["max_turns"],
        })
        return out

    def rows(self, *, limit: int = 60) -> list[dict]:
        rows = self._conn.execute(f"{_ROW_SELECT} ORDER BY accepted_utc DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_row_dict(r) for r in rows]

    def open_row(self) -> dict | None:
        if self._state.open_key is None:
            return None
        row = self._conn.execute("SELECT * FROM tasks WHERE key = ?", (self._state.open_key,)).fetchone()
        return None if row is None else self._to_row_dict(row)

    def counts(self) -> dict:
        row = self._conn.execute("SELECT COUNT(*) AS n, MIN(accepted_utc) AS since FROM tasks").fetchone()
        return {"rows": row["n"], "sinceUtc": row["since"]}


    # ------------------------------------------------------------------ API joins
    def attach_work(self, work: list[dict], *, as_of_utc: str) -> int:
        """Join ``/seats/<id>?work=N`` rows by ``submissionHash.startswith(hash12)``; a null hash never joins."""
        joined = 0
        with self._conn:
            for item in work:
                if not isinstance(item, dict):
                    continue
                full_hash = item.get("submissionHash")
                if not isinstance(full_hash, str) or len(full_hash) < 12:
                    continue
                hash12 = full_hash[:12]
                candidates = self._conn.execute(
                    "SELECT key, stored_utc FROM tasks WHERE hash12 = ? AND seat IS ?", (hash12, self._seat)
                ).fetchall()
                if not candidates:
                    continue
                submitted_epoch = _parse_api_timestamp(item.get("submittedAt"))
                if len(candidates) > 1 and submitted_epoch is not None:
                    def distance(c: sqlite3.Row) -> tuple[int, float]:
                        stored = parse_ts(c["stored_utc"] or "")
                        if stored is None:
                            return (2, 0.0)
                        return (0 if stored <= submitted_epoch else 1, abs(submitted_epoch - stored))
                    candidates = sorted(candidates, key=distance)
                target = candidates[0]
                status = item.get("status")
                outcome = status if status in ("accepted", "rejected", "failed", "pending") else "unknown"
                accepted_at_api = item.get("acceptedAt") if isinstance(item.get("acceptedAt"), str) else None
                lag = None
                if outcome == "accepted":
                    stored_epoch = parse_ts(target["stored_utc"] or "")
                    verdict_epoch = _parse_api_timestamp(accepted_at_api)
                    if stored_epoch is not None and verdict_epoch is not None:
                        lag = int(verdict_epoch - stored_epoch)
                self._conn.execute(
                    "UPDATE tasks SET outcome = ?, outcome_as_of_utc = ?, accepted_at_api = ?, verdict_lag_s = ?, "
                    "job_id = COALESCE(?, job_id), node_key = COALESCE(?, node_key), objective = COALESCE(?, objective), "
                    "source_outcome = 'api', updated_utc = ? WHERE key = ?",
                    (outcome, as_of_utc, accepted_at_api, lag,
                     item.get("jobId") if isinstance(item.get("jobId"), str) else None,
                     redact(item.get("nodeKey")) if isinstance(item.get("nodeKey"), str) else None,
                     redact_agent_sentence(item.get("objective")) if isinstance(item.get("objective"), str) else None,
                     _iso(self._now()), target["key"]),
                )
                joined += 1
        return joined

    def attach_work_dirs(self, entries: list[dict]) -> int:
        """Join ``work-stat`` ``newest`` entries ``{jobId, nodeId, mtimeUtc, abnormal}`` to local rows (spec §5.2, §8 LEDGER detail).

        The dir name carries the full ids and its mtime ≈ the accept time, so an entry joins the row of ``nodeId[:8]``
        whose ``accepted_utc`` is nearest the mtime within ``WORK_DIR_JOIN_S`` (node8 repeats across attempts); it sets
        ``work_dir_abnormal`` and fills a missing ``node_id``/``job_id``. Entries without a usable id or stamp are skipped.
        """
        joined = 0
        with self._conn:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                node_id, job_id = entry.get("nodeId"), entry.get("jobId")
                mtime = _parse_api_timestamp(entry.get("mtimeUtc"))
                if not isinstance(node_id, str) or len(node_id) < 8 or mtime is None:
                    continue
                best: tuple[float, str] | None = None
                for row in self._conn.execute(
                    "SELECT key, accepted_utc FROM tasks WHERE node8 = ? AND seat IS ? AND source_row = 'local'",
                    (node_id[:8], self._seat),
                ).fetchall():
                    accepted = parse_ts(row["accepted_utc"])
                    if accepted is None:
                        continue
                    delta = abs(mtime - accepted)
                    if delta <= WORK_DIR_JOIN_S and (best is None or delta < best[0]):
                        best = (delta, row["key"])
                if best is None:
                    continue
                abnormal = entry.get("abnormal")
                self._conn.execute(
                    "UPDATE tasks SET work_dir_abnormal = ?, node_id = COALESCE(node_id, ?), job_id = COALESCE(job_id, ?), "
                    "updated_utc = ? WHERE key = ?",
                    (int(abnormal) if isinstance(abnormal, bool) else None, node_id,
                     job_id if isinstance(job_id, str) else None, _iso(self._now()), best[1]),
                )
                joined += 1
        return joined

    def attach_reason(self, job_id: str, *, reason: str, failure_class: str | None, source: str,
                      at: str | None = None) -> int:
        """Set the failure reason (enum word only, never a summary) on this seat's failed rows of ``job_id``."""
        rows = self._conn.execute(
            "SELECT key, stored_utc FROM tasks WHERE job_id = ? AND seat IS ? AND outcome = 'failed'", (job_id, self._seat)
        ).fetchall()
        if not rows:
            return 0
        at_epoch = _parse_api_timestamp(at)
        if at_epoch is not None and len(rows) > 1:
            rows = sorted(rows, key=lambda r: abs((parse_ts(r["stored_utc"] or "") or 0.0) - at_epoch))[:1]
        with self._conn:
            for row in rows:
                self._conn.execute(
                    "UPDATE tasks SET failure_reason = ?, failure_class = ?, source_reason = ?, updated_utc = ? WHERE key = ?",
                    (redact(reason), redact(failure_class) if failure_class else None, source, _iso(self._now()), row["key"]),
                )
        return len(rows)

    def failed_rows_needing_reason(self, *, older_than_utc: str, limit: int = REASONS_PER_CYCLE) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE outcome = 'failed' AND failure_reason IS NULL AND job_id IS NOT NULL "
            "AND stored_utc IS NOT NULL AND stored_utc < ? ORDER BY stored_utc DESC LIMIT ?",
            (older_than_utc, limit),
        ).fetchall()
        return [self._to_row_dict(r) for r in rows]

    def seed_api_rows(self, work: list[dict], *, seat: int) -> int:
        """History rows from ``/seats/<id>?work=1000``: ``source_row='api'``; never overwrites a local row."""
        inserted = 0
        with self._conn:
            for item in work:
                if not isinstance(item, dict):
                    continue
                full_hash = item.get("submissionHash")
                if not isinstance(full_hash, str) or len(full_hash) < 12:
                    continue
                hash12 = full_hash[:12]
                if self._conn.execute("SELECT 1 FROM tasks WHERE hash12 = ? AND seat IS ?", (hash12, seat)).fetchone():
                    continue
                submitted_at = item.get("submittedAt") if isinstance(item.get("submittedAt"), str) else None
                if submitted_at is None:
                    continue
                status = item.get("status")
                outcome = status if status in ("accepted", "rejected", "failed", "pending") else "unknown"
                key = task_key(seat, hash12[:8], submitted_at)
                accepted_at_api = item.get("acceptedAt") if isinstance(item.get("acceptedAt"), str) else None
                lag = None
                if outcome == "accepted":
                    s, v = _parse_api_timestamp(submitted_at), _parse_api_timestamp(accepted_at_api)
                    if s is not None and v is not None:
                        lag = int(v - s)
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO tasks(key, seat, node8, job_id, role, kind, accepted_utc, submitted_utc, "
                    "stored_utc, hash12, outcome, outcome_as_of_utc, accepted_at_api, verdict_lag_s, node_key, objective, "
                    "source_row, source_outcome, source_reason, phases_json, updated_utc) "
                    "VALUES (?, ?, ?, ?, ?, 'code', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'api', 'api', 'none', '[]', ?)",
                    (key, seat, hash12[:8], item.get("jobId") if isinstance(item.get("jobId"), str) else None,
                     redact(item.get("role")) if isinstance(item.get("role"), str) else None,
                     submitted_at, submitted_at, submitted_at, hash12, outcome, _iso(self._now()), accepted_at_api, lag,
                     redact(item.get("nodeKey")) if isinstance(item.get("nodeKey"), str) else None,
                     redact_agent_sentence(item.get("objective")) if isinstance(item.get("objective"), str) else None,
                     _iso(self._now())),
                )
                if cur.rowcount == 1:
                    inserted += 1
        return inserted


    # ------------------------------------------------------------------ sessions
    def attach_sessions(self, sessions: list[dict], *, runtime: str) -> int:
        """Join summariser output (contract C.8 ``SESSION_KEYS``) to rows; doctor/manual/unknown are stored unattached."""
        attached = 0
        with self._conn:
            for s in sessions:
                if not isinstance(s, dict) or not isinstance(s.get("path"), str):
                    continue
                key = self._task_key_for_session(s)
                tokens = s.get("tokens") if isinstance(s.get("tokens"), dict) else {}
                self._conn.execute(
                    "INSERT INTO sessions(path, task_key, runtime, cwd, kind, started_utc, mtime, model, effort, turns, "
                    "tokens_input, tokens_output, tokens_cached, tokens_cache_write, side_model_json, ttft_ms, wall_ms, "
                    "turn1_context, max_turns_reached, api_errors_json, quota_json, bytes, skipped_oversize, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(path) DO UPDATE SET task_key = excluded.task_key, kind = excluded.kind, mtime = excluded.mtime, "
                    "model = excluded.model, effort = excluded.effort, turns = excluded.turns, tokens_input = excluded.tokens_input, "
                    "tokens_output = excluded.tokens_output, tokens_cached = excluded.tokens_cached, "
                    "tokens_cache_write = excluded.tokens_cache_write, side_model_json = excluded.side_model_json, "
                    "ttft_ms = excluded.ttft_ms, wall_ms = excluded.wall_ms, turn1_context = excluded.turn1_context, "
                    "max_turns_reached = excluded.max_turns_reached, api_errors_json = excluded.api_errors_json, "
                    "quota_json = excluded.quota_json, bytes = excluded.bytes, skipped_oversize = excluded.skipped_oversize, "
                    "error = excluded.error",
                    (s["path"], key, s.get("runtime") or runtime, s.get("cwd") or s.get("slug"), s.get("kind"),
                     s.get("startedUtc"), s.get("mtime"), s.get("model"), s.get("effort"), s.get("turns"),
                     tokens.get("input"), tokens.get("output"), tokens.get("cached"), tokens.get("cacheWrite"),
                     _dumps(s.get("sideModel")), s.get("ttftMs"), s.get("wallMs"), s.get("turn1Context"),
                     1 if s.get("maxTurnsReached") else 0 if s.get("maxTurnsReached") is not None else None,
                     _dumps([{"status": e.get("status"), "message": redact(e.get("message")), "atUtc": e.get("atUtc")}
                             for e in (s.get("apiErrors") or []) if isinstance(e, dict)]),
                     _dumps(s.get("quota")), s.get("bytes"), s.get("skippedOversize"), s.get("error")),
                )
                if key is not None:
                    self._aggregate_sessions(key, runtime)
                    attached += 1
        return attached

    def _task_key_for_session(self, s: dict) -> str | None:
        kind = s.get("kind")
        if kind not in ("task", "research"):
            return None  # doctor / manual / unknown are excluded from cost (spec §10)
        started = _parse_api_timestamp(s.get("startedUtc"))
        if kind == "research":
            if started is None:
                return None
            rows = self._conn.execute(
                "SELECT key, accepted_utc FROM tasks WHERE kind = 'research' AND seat IS ? AND source_row = 'local'",
                (self._seat,),
            ).fetchall()
            best = None
            for row in rows:
                accepted = parse_ts(row["accepted_utc"])
                if accepted is None:
                    continue
                delta = abs(started - accepted)
                if delta <= RESEARCH_JOIN_S and (best is None or delta < best[0]):
                    best = (delta, row["key"])
            return None if best is None else best[1]
        node_id = s.get("nodeId")
        job_id = s.get("jobId")
        if not isinstance(node_id, str) or len(node_id) < 8:
            return None
        rows = self._conn.execute(
            "SELECT key, accepted_utc, submitted_utc FROM tasks WHERE node8 = ? AND seat IS ? AND source_row = 'local' "
            "ORDER BY accepted_utc",
            (node_id[:8], self._seat),
        ).fetchall()
        if not rows:
            return None
        mtime = s.get("mtime")
        anchor = started if started is not None else (float(mtime) if isinstance(mtime, (int, float)) else None)
        chosen = rows[-1]
        if anchor is not None:
            # multi-attempt nodes share one cwd: pick the attempt whose accept precedes the session start most closely
            preceding = [r for r in rows if (parse_ts(r["accepted_utc"]) or float("inf")) <= anchor + RESEARCH_JOIN_S]
            if preceding:
                chosen = preceding[-1]
        self._conn.execute(
            "UPDATE tasks SET node_id = ?, job_id = COALESCE(job_id, ?), updated_utc = ? WHERE key = ?",
            (node_id, job_id if isinstance(job_id, str) else None, _iso(self._now()), chosen["key"]),
        )
        return chosen["key"]

    def _aggregate_sessions(self, key: str, runtime: str) -> None:
        """Per attempt: tokens additive across files, turns NOT (max), sessionFiles = N (fill3 §2)."""
        rows = self._conn.execute("SELECT * FROM sessions WHERE task_key = ? ORDER BY mtime", (key,)).fetchall()
        if not rows:
            return
        # The stored session's own runtime wins over the caller's: WP7's first sessions cycle passes a guess ("codex") before
        # `imd status` has named the runtime, while the Mac broker always answers with Claude transcripts (spec §10 turns definition).
        runtime = rows[-1]["runtime"] or runtime

        def total(column: str) -> int | None:
            values = [r[column] for r in rows if r[column] is not None]
            return sum(values) if values else None

        turns = [r["turns"] for r in rows if r["turns"] is not None]
        ttft = [r["ttft_ms"] for r in rows if r["ttft_ms"] is not None]
        walls = [r["wall_ms"] for r in rows if r["wall_ms"] is not None]
        t1 = [r["turn1_context"] for r in rows if r["turn1_context"] is not None]
        newest = rows[-1]
        errors: list = []
        for r in rows:
            errors.extend(_loads(r["api_errors_json"]) or [])
        side: dict | None = None
        for r in rows:
            sm = _loads(r["side_model_json"])
            if isinstance(sm, dict):
                if side is None:
                    side = {"model": sm.get("model"), "input": 0, "output": 0}
                side["input"] += int(sm.get("input") or 0)
                side["output"] += int(sm.get("output") or 0)
        tier = None
        if self._tier_lookup is not None:
            accepted = self._conn.execute("SELECT accepted_utc FROM tasks WHERE key = ?", (key,)).fetchone()
            tier = self._tier_lookup(runtime, newest["model"], newest["effort"],
                                     accepted["accepted_utc"] if accepted else None, seat=self._seat)
        self._conn.execute(
            "UPDATE tasks SET runtime = COALESCE(runtime, ?), model = COALESCE(?, model), effort = ?, tier_derived = COALESCE(?, tier_derived), "
            "turns = ?, turns_definition = ?, tokens_input = ?, tokens_output = ?, tokens_cached = ?, tokens_cache_write = ?, "
            "side_model_json = ?, ttft_ms = ?, wall_ms = ?, turn1_context = ?, max_turns_reached = ?, api_errors_json = ?, "
            "session_files = ?, tokens_reason = NULL, updated_utc = ? WHERE key = ?",
            (runtime, newest["model"], newest["effort"], tier,
             max(turns) if turns else None, "agent_messages" if runtime == "codex" else "user_lines",
             total("tokens_input"), total("tokens_output"), total("tokens_cached"), total("tokens_cache_write"),
             _dumps(side), min(ttft) if ttft else None, sum(walls) if walls else None, t1[0] if t1 else None,
             1 if any(r["max_turns_reached"] for r in rows) else 0, _dumps(errors), len(rows), _iso(self._now()), key),
        )

    def unattached_sessions(self, *, since_utc: str) -> list[dict]:
        """Doctor/manual/unknown summaries stored with task_key NULL, for ``seat_cost.summarise(sessions=...)`` (spec §7 ``cost.excluded``)."""
        rows = self._conn.execute(
            "SELECT kind, started_utc FROM sessions WHERE task_key IS NULL AND kind IN ('doctor', 'manual', 'unknown') "
            "AND started_utc IS NOT NULL AND started_utc >= ? ORDER BY started_utc",
            (since_utc,),
        ).fetchall()
        return [{"kind": r["kind"], "startedUtc": r["started_utc"]} for r in rows]

    def mark_expired_transcripts(self, *, runtime: str, now_utc: str, days: int = TRANSCRIPT_RETENTION_DAYS) -> int:
        """Spec §5.4 Claude retention: local rows no transcript joined within ``days`` read ``tokens_reason = 'transcript expired'``.

        Claude Code sweeps transcripts older than ``cleanupPeriodDays`` (30); codex never deletes rollouts, so it returns 0
        there. Pre-agent failures (no agent ran, no transcript ever existed) and fuzz campaigns (tokens null by construction)
        are never marked; a session that joins later clears the reason (``_aggregate_sessions`` sets it NULL).
        """
        if runtime != "claude":
            return 0
        now_epoch = _parse_api_timestamp(now_utc)
        if now_epoch is None:
            return 0
        with self._conn:
            cur = self._conn.execute(
                "UPDATE tasks SET tokens_reason = 'transcript expired', updated_utc = ? WHERE seat IS ? AND source_row = 'local' "
                "AND tokens_input IS NULL AND tokens_reason IS NULL AND COALESCE(pre_agent_failure, 0) = 0 "
                "AND COALESCE(kind, '') != 'fuzz' AND accepted_utc < ?",
                (_iso(self._now()), self._seat, _iso(now_epoch - days * 86400)),
            )
        return cur.rowcount


    # ------------------------------------------------------------------ day rollups
    def _day_rows(self, day_utc: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM tasks WHERE substr(accepted_utc, 1, 10) = ? ORDER BY accepted_utc", (day_utc,)
        ).fetchall()

    def _summarise_day(self, day_utc: str) -> dict:
        rows = self._day_rows(day_utc)
        stored = [r for r in rows if r["stored_utc"]]
        durations = [r["duration_s"] for r in rows if r["duration_s"] is not None]
        lags = [r["verdict_lag_s"] for r in rows if r["verdict_lag_s"] is not None]
        counts = {o: sum(1 for r in rows if r["outcome"] == o) for o in ("accepted", "rejected", "failed", "pending")}
        sources = {r["source_row"] for r in rows}

        def total(column: str) -> int | None:
            values = [r[column] for r in rows if r[column] is not None]
            return sum(values) if values else None

        return {
            "dayUtc": day_utc, "tasks": len(rows), "stored": len(stored), "notStored": len(rows) - len(stored),
            "accepted": counts["accepted"], "rejected": counts["rejected"], "failed": counts["failed"],
            "pending": counts["pending"], "tokens": {"input": total("tokens_input"), "output": total("tokens_output"),
                                                     "cached": total("tokens_cached"), "cacheWrite": total("tokens_cache_write")},
            "turns": total("turns"), "p50S": _median(durations), "longestS": max(durations) if durations else None,
            "verdictLagP50S": _median(lags),
            "verdictsAsOfUtc": max((r["outcome_as_of_utc"] for r in rows if r["outcome_as_of_utc"]), default=None),
            "source": {"tasks": ("mixed" if len(sources) > 1 else next(iter(sources))) if sources else None,
                       "verdicts": "api" if any(r["outcome"] for r in rows) else None,
                       "tokens": "sessions" if any(r["tokens_output"] is not None for r in rows) else None},
        }

    def rollup_day(self, day_utc: str, *, now_utc: str) -> dict:
        summary = self._summarise_day(day_utc)
        with self._conn:
            self._conn.execute(
                "INSERT INTO days(day_utc, tasks, stored, not_stored, accepted, rejected, failed, pending, tokens_input, "
                "tokens_output, tokens_cached, tokens_cache_write, turns, p50_s, longest_s, verdict_lag_p50_s, source_json, "
                "updated_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(day_utc) DO UPDATE SET tasks = excluded.tasks, stored = excluded.stored, "
                "not_stored = excluded.not_stored, accepted = excluded.accepted, rejected = excluded.rejected, "
                "failed = excluded.failed, pending = excluded.pending, tokens_input = excluded.tokens_input, "
                "tokens_output = excluded.tokens_output, tokens_cached = excluded.tokens_cached, "
                "tokens_cache_write = excluded.tokens_cache_write, turns = excluded.turns, p50_s = excluded.p50_s, "
                "longest_s = excluded.longest_s, verdict_lag_p50_s = excluded.verdict_lag_p50_s, "
                "source_json = excluded.source_json, updated_utc = excluded.updated_utc",
                (day_utc, summary["tasks"], summary["stored"], summary["notStored"], summary["accepted"],
                 summary["rejected"], summary["failed"], summary["pending"], summary["tokens"]["input"],
                 summary["tokens"]["output"], summary["tokens"]["cached"], summary["tokens"]["cacheWrite"],
                 summary["turns"], summary["p50S"], summary["longestS"], summary["verdictLagP50S"],
                 _dumps(summary["source"]), now_utc),
            )
        return {**summary, "updatedUtc": now_utc}

    def days(self, n: int = 14) -> list[dict]:
        """The newest ``n`` rolled-up days, oldest first (the series order ``seat_cost.series_from_days`` wants)."""
        rows = self._conn.execute("SELECT * FROM days ORDER BY day_utc DESC LIMIT ?", (n,)).fetchall()
        out = []
        for r in reversed(rows):
            out.append({
                "dayUtc": r["day_utc"], "tasks": r["tasks"], "stored": r["stored"], "notStored": r["not_stored"],
                "accepted": r["accepted"], "rejected": r["rejected"], "failed": r["failed"], "pending": r["pending"],
                "tokens": {"input": r["tokens_input"], "output": r["tokens_output"], "cached": r["tokens_cached"],
                           "cacheWrite": r["tokens_cache_write"]},
                "turns": r["turns"], "p50S": r["p50_s"], "longestS": r["longest_s"], "verdictLagP50S": r["verdict_lag_p50_s"],
                "source": _loads(r["source_json"]), "updatedUtc": r["updated_utc"],
            })
        return out

    def today(self, day_utc: str) -> dict:
        """The §7 ``today`` block minus ``divergence`` (WP7 adds that from the plane), computed live from ``tasks``.

        ``p50S``/``longestS``/``verdictLagP50S`` are whole seconds, as spec §7 prints them (``"p50S": 28``) and as WP7's
        fallback ``seat_signals.rollup_today`` rounds them; ``rollup_day``/``days`` keep the REAL column values.
        """
        s = self._summarise_day(day_utc)

        def whole(value: float | None) -> int | None:
            return None if value is None else int(round(value))

        return {
            "dayUtc": s["dayUtc"], "tasks": s["tasks"], "stored": s["stored"], "notStored": s["notStored"],
            "p50S": whole(s["p50S"]), "longestS": whole(s["longestS"]), "accepted": s["accepted"], "rejected": s["rejected"],
            "failed": s["failed"], "pending": s["pending"], "verdictLagP50S": whole(s["verdictLagP50S"]),
            "verdictsAsOfUtc": s["verdictsAsOfUtc"],
        }


__all__ = [
    "LEDGER_FILE", "LEDGER_SCHEMA_VERSION", "LEDGER_BUSY_TIMEOUT_MS", "PRE_AGENT_FAILURE_S", "RESEARCH_JOIN_S",
    "IDLE_WINDOW_S", "CONNECTION_WINDOW_S", "REASONS_PER_CYCLE", "TRANSCRIPT_RETENTION_DAYS", "WORK_DIR_JOIN_S",
    "META_KEYS", "SCHEMA_SQL", "Json", "Clock",
    "TierLookup", "task_key", "LedgerSchemaMismatch", "LedgerState", "IngestResult", "SeatLedger",
]
