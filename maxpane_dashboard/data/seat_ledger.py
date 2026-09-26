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
                if line.ts and (self._state.last_ts is None or line.ts > self._state.last_ts):
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
                if kind in g.ACCEPTED_KINDS or kind in g.TERMINAL_KINDS:
                    self._state.last_lifecycle = line
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


__all__ = [
    "LEDGER_FILE", "LEDGER_SCHEMA_VERSION", "LEDGER_BUSY_TIMEOUT_MS", "PRE_AGENT_FAILURE_S", "RESEARCH_JOIN_S",
    "IDLE_WINDOW_S", "CONNECTION_WINDOW_S", "REASONS_PER_CYCLE", "TRANSCRIPT_RETENTION_DAYS", "WORK_DIR_JOIN_S",
    "META_KEYS", "SCHEMA_SQL", "Json", "Clock",
    "TierLookup", "task_key", "LedgerSchemaMismatch", "LedgerState", "IngestResult", "SeatLedger",
]
