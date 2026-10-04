"""Ledger tests for ``data/seat_ledger.py`` (spec §5.1 ledger rules, §5.6, §9, §10, Appendix B; contract C.6)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from maxpane_dashboard.analytics.seat_redact import SK_RE
from maxpane_dashboard.data import seat_log_grammar as g
from maxpane_dashboard.data.seat_ledger import (
    LEDGER_BUSY_TIMEOUT_MS,
    LEDGER_SCHEMA_VERSION,
    META_KEYS,
    IngestResult,
    LedgerSchemaMismatch,
    LedgerState,
    SeatLedger,
    task_key,
)
from maxpane_dashboard.data.seat_models import SEAT_BLOCK_KEYS, SEAT_ROW_KEYS

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "seat" / "grammar"
T0 = 1_790_000_000.0  # 2026-09-21T14:13:20Z — an injected clock; per-test clocks sit just after a slice's last stamp


def _lines(name: str, *, invocation: str | None = None) -> list[g.LogLine]:
    return [g.classify(line, invocation=invocation, seq=i)
            for i, line in enumerate((FIXTURES / name).read_text(encoding="utf-8").splitlines())]


def _classify(lines: list[str], *, invocation: str | None = None) -> list[g.LogLine]:
    return [g.classify(line, invocation=invocation, seq=i) for i, line in enumerate(lines)]


def _ledger(tmp_path: Path, *, seat: int | None = 7, now: float = T0, tier_lookup=None) -> SeatLedger:
    return SeatLedger(tmp_path / "seat_ledger.sqlite", seat=seat, now=lambda: now, tier_lookup=tier_lookup)


def _by_node(ledger: SeatLedger, node8: str) -> list[dict]:
    return sorted((r for r in ledger.rows(limit=500) if r["nodeId8"] == node8), key=lambda r: r["acceptedUtc"])

class TestSchema:
    def test_ledger_busy_timeout_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Spec §5.6: WAL + busy_timeout so a `--once` run and the TUI can share the file.

        Python's ``sqlite3.connect`` defaults to ``timeout=5.0`` (= busy_timeout 5000 ms), which would mask a
        missing PRAGMA; the driver timeout is forced to 0 here so only the ledger's own PRAGMA can yield 5000.
        """
        real_connect = sqlite3.connect

        def zero_timeout_connect(database, *args, **kwargs):
            kwargs["timeout"] = 0.0
            return real_connect(database, *args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", zero_timeout_connect)
        ledger = _ledger(tmp_path)
        assert ledger._conn.execute("PRAGMA busy_timeout").fetchone()[0] == LEDGER_BUSY_TIMEOUT_MS == 5000
        assert ledger._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        ledger.close()

    def test_tables_and_columns_match_the_contract(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path)
        names = {r[0] for r in ledger._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"tasks", "sessions", "days", "meta"} <= names
        task_cols = [r[1] for r in ledger._conn.execute("PRAGMA table_info(tasks)")]
        assert task_cols[:8] == ["key", "seat", "node8", "node_id", "job_id", "role", "kind", "accepted_utc"]
        assert task_cols[53] == "updated_utc" and task_cols[54:] == ["job_state", "launch_json", "submission_hash", "work_status", "text_expired", "api_merged"]
        assert [r[1] for r in ledger._conn.execute("PRAGMA table_info(days)")][:3] == ["day_utc", "tasks", "stored"]
        indexes = {r[0] for r in ledger._conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"tasks_accepted", "tasks_hash12", "tasks_job"} <= indexes
        ledger.close()

    def test_meta_keys_and_schema_version(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path)
        assert META_KEYS == ("schema_version", "ledger_since_utc", "grammar_version", "sessions_watermark_mtime",
                             "api_backfill_done_utc", "seat", "sessions_skipped_oversize")
        assert ledger.meta_get("schema_version") == LEDGER_SCHEMA_VERSION == 1
        assert ledger.meta_get("grammar_version") == g.GRAMMAR_VERSION and ledger.meta_get("seat") == 7
        assert ledger.meta_get("ledger_since_utc") == "2026-09-21T14:13:20Z"
        ledger.meta_set("sessions_watermark_mtime", 1790000123.5)
        assert ledger.meta_get("sessions_watermark_mtime") == 1790000123.5
        assert ledger.meta_get("api_backfill_done_utc") is None
        assert ledger.meta_get("sessions_skipped_oversize") is None  # WP7 accumulates it; a fresh ledger holds none
        ledger.close()
        with sqlite3.connect(tmp_path / "seat_ledger.sqlite") as conn:
            conn.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
        with pytest.raises(LedgerSchemaMismatch):
            _ledger(tmp_path)

    def test_task_key(self) -> None:
        assert task_key(7, "0c1f9727", "2026-09-26T01:52:44.909Z") == "7/0c1f9727/2026-09-26T01:52:44.909Z"
        assert task_key(None, "0c1f9727", "2026-09-26T01:52:44.909Z") == "-/0c1f9727/2026-09-26T01:52:44.909Z"


# ---------------------------------------------------------------------------------------- Task 2.7
class TestStateMachine:
    def test_rows_carry_exactly_the_contract_keys(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path, now=1790457000.0)
        ledger.ingest(_lines("research_question.txt"))
        (row,) = ledger.rows()
        assert set(row) == set(SEAT_ROW_KEYS["seat_tasks_rows"])
        assert row["kind"] == "research" and row["role"] == "question" and row["hash12"] == "3f166c0de71b"
        assert row["source"] == {"row": "local", "outcome": "none", "reason": "none"}
        assert isinstance(ledger.ingest([]), IngestResult) and isinstance(ledger.state, LedgerState)
        ledger.close()

    def test_full_lifecycle_row(self, tmp_path: Path) -> None:
        """Appendix B: accept opens, model line proves the agent ran, submitted closes, stored sets hash12."""
        ledger = _ledger(tmp_path, now=1790380000.0)
        result = ledger.ingest(_lines("heartbeat_lingering_pause.txt"))
        assert (result.opened, result.closed, result.stored, result.restarts, result.unknown) == (3, 2, 2, 0, 0)
        assert result.events.count("accepted") == 3 and result.events.count("stored") == 2
        first = _by_node(ledger, "2fc3b00f")[0]
        assert first["acceptedUtc"] == "2026-09-25T23:54:11.178Z" and first["submittedUtc"] == "2026-09-25T23:54:37.418Z"
        assert first["storedUtc"] == "2026-09-25T23:54:37.499Z" and first["hash12"] == "54f724419d3a"
        assert first["agentRan"] is True and first["preAgentFailure"] is False and first["model"] == "gpt-6-luna"
        assert first["runtime"] == "codex" and first["phases"] == ["preparing", "working", "checking", "bundling", "uploading"]
        assert first["lastMessage"].startswith("Created [artifacts/answer.json]") and 26 < first["durationS"] < 27
        assert first["outcome"] is None  # verdicts exist only at the API (spec §2)
        # the third accept (5501ac4d) is still open
        open_row = ledger.open_row()
        assert open_row is not None and open_row["nodeId8"] == "5501ac4d" and open_row["submittedUtc"] is None
        assert ledger.state.current["nodeId8"] == "5501ac4d" and ledger.state.current["phase"] == "working"
        assert set(ledger.state.current) == set(SEAT_BLOCK_KEYS["seat_current"])
        assert ledger.state.last_lifecycle.kind == g.KIND_ACCEPTED_CODE
        ledger.close()

    def test_same_node_on_two_seats_are_two_rows(self, tmp_path: Path) -> None:
        """fill6 §2: 4cf722c7 was accepted on the VPS 17:08:39 and on the Mac 17:08:52 — the key carries the seat."""
        vps = SeatLedger(tmp_path / "vps.sqlite", seat=7, now=lambda: 1790230000.0)
        mac = SeatLedger(tmp_path / "mac.sqlite", seat=420, now=lambda: 1790230000.0)
        vps.ingest(_classify(["2026-09-23T17:08:39.905Z accepted implement 4cf722c7 — artifacts/answer.json (max 60 turns)"]))
        mac.ingest(_classify(["2026-09-23T17:08:52.171Z accepted implement 4cf722c7 — artifacts/answer.json (max 60 turns)"]))
        assert vps.rows()[0]["key"] == "7/4cf722c7/2026-09-23T17:08:39.905Z"
        assert mac.rows()[0]["key"] == "420/4cf722c7/2026-09-23T17:08:52.171Z"
        vps.close(); mac.close()

    def test_pre_agent_failure_needs_no_working_line_and_under_one_second(self, tmp_path: Path) -> None:
        """Spec §5.1: sub-second accept→submit with no `working:` line = pre-agent failure, 0 tokens (six measured)."""
        ledger = _ledger(tmp_path, now=1790391000.0)
        ledger.ingest(_lines("fast_fail_no_working.txt"))
        rows = ledger.rows()
        assert len(rows) == 6 and all(r["preAgentFailure"] is True and r["agentRan"] is False for r in rows)
        assert all(r["durationS"] < 1.0 for r in rows) and all(r["hash12"] for r in rows)
        # the Mac one was stored through a re-send after a socket drop
        (mac,) = _by_node(ledger, "8eac278c")
        assert mac["resent"] is True and mac["hash12"] == "3538ff5d2068"
        ledger.close()

    def test_repair_yields_one_submission_and_sets_repair(self, tmp_path: Path) -> None:
        """Spec §5.1: `repairing:` → one more `bundling:` then exactly ONE submitted (3/3 on the Mac)."""
        ledger = _ledger(tmp_path, now=1790220000.0)
        result = ledger.ingest(_lines("repair_once.txt"))
        assert (result.opened, result.closed, result.stored) == (3, 3, 3)
        rows = ledger.rows()
        assert all(r["repair"] is True for r in rows) and all("repairing" in r["phases"] for r in rows)
        (tests_row,) = [r for r in rows if r["role"] == "tests"]
        assert tests_row["nodeId8"] == "e78e1517" and tests_row["model"] == "claude-fable-5-1" and tests_row["runtime"] == "claude"
        ledger.close()

    def test_resend_yields_exactly_one_stored(self, tmp_path: Path) -> None:
        """Spec §5.1: a re-send yields exactly one `stored` (2/2); the row is flagged `resent`."""
        ledger = _ledger(tmp_path, now=1790391000.0)
        ledger.ingest(_classify([
            "2026-09-22T17:20:00.000Z accepted implement 4a2a12e5 — artifacts/answer.json (max 60 turns)",
            "2026-09-22T17:20:01.000Z   working: running claude on claude-sonnet-5",
        ]) + _lines("resend.txt"))
        (row,) = _by_node(ledger, "4a2a12e5")
        assert row["resent"] is True and row["hash12"] == "7f11d6b7f9d0" and row["storedUtc"] == "2026-09-22T17:21:24.252Z"
        assert ledger.counts()["rows"] == 2  # 4a2a12e5 + 8eac278c, one stored line each
        ledger.close()

    def test_research_row_closes_on_answered(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path, now=1790457000.0)
        ledger.ingest(_lines("research_question.txt"))
        (row,) = ledger.rows()
        assert (row["kind"], row["role"], row["submittedUtc"], row["hash12"]) == (
            "research", "question", "2026-09-25T18:09:56.031Z", "3f166c0de71b")
        assert row["agentRan"] is False and row["preAgentFailure"] is False  # 61 s: no `working:` line is normal for research
        ledger.close()

    def test_fuzz_row_closes_on_outcome_with_zero_tokens_by_construction(self, tmp_path: Path) -> None:
        """Spec §5.1 / fill6 §3: a campaign prints only accept + outcome; tokens stay null (never 0)."""
        ledger = _ledger(tmp_path)
        ledger.ingest(_classify([
            "2026-09-24T04:24:01.000Z accepted campaign cb1949ef — test/Harness.t.sol (256 runs)",
            "2026-09-24T04:26:10.000Z campaign could not run: the harness did not build",
        ]))
        (row,) = ledger.rows()
        assert (row["kind"], row["role"], row["submittedUtc"]) == ("fuzz", "campaign", "2026-09-24T04:26:10.000Z")
        assert row["tokens"] is None and row["preAgentFailure"] is False
        ledger.close()

    def test_model_refuse_marks_agent_ran_with_default_model(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path)
        ledger.ingest(_classify([
            "2026-09-26T01:00:00.000Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)",
            "2026-09-26T01:00:00.500Z   working: codex refused model gpt-6-astra; running on its default model instead",
        ]))
        row = ledger.open_row()
        assert row["agentRan"] is True and row["model"] is None and row["runtime"] == "codex"
        ledger.close()

    def test_tier_lookup_is_injected(self, tmp_path: Path) -> None:
        """Contract C.6: `tier_lookup(runtime, model, effort, at, *, seat)` is injected; None until WP4/WP7 wire it."""
        calls: list[tuple] = []

        def lookup(runtime, model, effort, at, *, seat=None):
            calls.append((runtime, model, effort, at, seat))
            return "economy/standard"

        ledger = _ledger(tmp_path, tier_lookup=lookup)
        ledger.ingest(_classify([
            "2026-09-26T01:00:00.000Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)",
            "2026-09-26T01:00:00.500Z   working: running codex on gpt-6-luna",
        ]))
        assert ledger.open_row()["tierDerived"] == "economy/standard"
        assert calls == [("codex", "gpt-6-luna", None, "2026-09-26T01:00:00.500Z", 7)]
        plain = SeatLedger(tmp_path / "plain.sqlite", seat=7, now=lambda: T0)
        plain.ingest(_classify(["2026-09-26T01:00:00.000Z accepted implement 0c1f9727 — a (max 60 turns)",
                                "2026-09-26T01:00:00.500Z   working: running codex on gpt-6-luna"]))
        assert plain.open_row()["tierDerived"] is None
        ledger.close(); plain.close()

    def test_agent_sentence_is_redacted_before_persisting(self, tmp_path: Path) -> None:
        """Spec §13: redact before every sqlite write (masked key fragment, OSC payload, whitespace collapse)."""
        ledger = _ledger(tmp_path)
        ledger.ingest(_classify([
            "2026-09-26T01:00:00.000Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)",
            "2026-09-26T01:00:00.500Z   working: running codex on gpt-6-luna",
            "2026-09-26T01:00:05.000Z   working: the key was sk-svcac******** and \x1b]52;c;AAAA\x07   then " + "x" * 90,
        ]))
        message = ledger.open_row()["lastMessage"]
        assert message.startswith("the key was sk-[redacted] and \u241b]52;c;AAAA then xxx")
        assert SK_RE.search(message) is None and "\x07" not in message and "  " not in message and len(message) <= 160
        dump = "\n".join(str(tuple(r)) for r in ledger._conn.execute("SELECT * FROM tasks"))
        assert SK_RE.search(dump) is None
        ledger.close()


def test_double_accept_keeps_every_row(tmp_path: Path) -> None:
    """Mutation proof 1 (spec §14): key by (seat, node8, acceptedAt) — node8 repeats up to 3× (fill6 §2)."""
    ledger = _ledger(tmp_path, now=1790230000.0)
    ledger.ingest(_lines("double_accept.txt"))
    assert ledger.counts()["rows"] == 6
    assert len(_by_node(ledger, "4cf722c7")) == 3 and len(_by_node(ledger, "3aa1c610")) == 3
    hashes = {r["hash12"] for r in ledger.rows()}
    assert hashes == {"5be358c456eb", "4e3eef449076", "50596a6ec16e", "cee9e3163b14", "f7ef8612dee7", "5b83f0929a19"}
    keys = {r["key"] for r in ledger.rows()}
    assert "7/4cf722c7/2026-09-23T17:08:39.905Z" in keys and "7/4cf722c7/2026-09-24T05:36:49.988Z" in keys
    ledger.close()


def test_lease_closed_is_not_an_attempt(tmp_path: Path) -> None:
    """Mutation proof 5 (spec §14): `submitted` without `stored` = lease-closed, never an attempt (fill6 §2)."""
    ledger = _ledger(tmp_path, now=1790391000.0)
    ledger.ingest(_lines("cancel_lease_closed.txt"))
    (row,) = _by_node(ledger, "b6d17f8d")
    assert row["submittedUtc"] == "2026-09-26T02:48:19.156Z"
    assert row["storedUtc"] is None and row["hash12"] is None and row["leaseClosed"] is True
    # the NEXT task's stored line attaches to the next task, never to the lease-closed row
    (nxt,) = _by_node(ledger, "f3230435")
    assert nxt["hash12"] == "d9bebae54a7d" and nxt["leaseClosed"] is False
    ledger.close()


def test_cancel_attaches_to_open_row_not_by_prefix(tmp_path: Path) -> None:
    """Mutation proof 6 (spec §14): `cancelled <lease8>` names the LEASE — attach by time, never by id match.

    The real captured slice has no node8 matching the lease id (16a4df90); an id-matching
    implementation attaches nowhere and leaves the open row untouched.
    """
    ledger = _ledger(tmp_path, now=1790391000.0)
    ledger.ingest(_lines("cancel_lease_closed.txt"))
    (open_at_that_instant,) = _by_node(ledger, "b6d17f8d")
    assert _by_node(ledger, "16a4df90") == []
    assert open_at_that_instant["cancelled"] == "superseded"
    ledger.close()


# ---------------------------------------------------------------------------------------- Task 2.8
class TestRestartBoundaries:
    def test_runtimes_line_is_a_restart_boundary(self, tmp_path: Path) -> None:
        """Appendix B: RUNTIMES closes an open row as interruptedByRestart and resets submittedSinceStart."""
        ledger = _ledger(tmp_path, now=1790337000.0)
        ledger.ingest(_classify(["2026-09-25T11:45:20.000Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)"]))
        result = ledger.ingest(_lines("restart_boundary.txt"))
        assert result.restarts == 1 and "restart" in result.events
        (row,) = ledger.rows()
        assert row["interruptedByRestart"] is True and row["submittedUtc"] is None and ledger.open_row() is None
        st = ledger.state
        assert st.submitted_since_start == 0 and st.daemon_version == "0.1.0+5bfa8261" and st.runtimes == "codex codex-cli 0.157.0"
        assert st.last_admitted_utc == "2026-09-25T11:45:41.968Z" and st.fleet_online == 362
        ledger.close()

    def test_state_is_restored_from_sqlite_on_reopen(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path, now=1790391000.0)
        ledger.ingest(_lines("open_accept_after_idle.txt"))
        ledger.close()
        reopened = _ledger(tmp_path, now=1790391000.0)
        assert reopened.open_row()["nodeId8"] == "0c1f9727" and reopened.state.current["nodeId8"] == "0c1f9727"
        reopened.close()


def test_invocation_change_is_a_restart_boundary(tmp_path: Path) -> None:
    """Header Review Focus 1: a crash-restart without the `runtimes:` banner in the window — the journald
    `_SYSTEMD_INVOCATION_ID` change alone closes the open row `interruptedByRestart` and resets the counter."""
    ledger = _ledger(tmp_path, now=1790337000.0)
    ledger.ingest(_classify([
        "2026-09-25T11:44:59.469Z alive 15h6m · idle · 108 submitted · fleet 362 online, 370 enrolled",
        "2026-09-25T11:45:20.000Z accepted implement 0c1f9727 — artifacts/answer.json (max 60 turns)",
    ], invocation="aaaa"))
    assert ledger.state.submitted_since_start == 108
    result = ledger.ingest(_classify([
        "2026-09-25T11:46:11.851Z alive 0m · idle · 0 submitted · fleet 362 online, 370 enrolled",
    ], invocation="bbbb"))
    assert result.restarts == 1 and result.events == ("restart",)
    (row,) = ledger.rows()
    assert row["interruptedByRestart"] is True and ledger.open_row() is None
    assert ledger.state.invocation == "bbbb" and ledger.state.submitted_since_start == 0
    # a later `runtimes:` line of the same start does not count a second restart
    again = ledger.ingest(_classify(["2026-09-25T11:46:12.000Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)"], invocation="bbbb"))
    assert again.restarts == 0
    ledger.close()


class TestDetectorState:
    def test_idle_beats_count_only_recent_consecutive_idle_heartbeats(self, tmp_path: Path) -> None:
        """Spec §9 / §11 gate (a): idle beats = consecutive `idle` among heartbeats newer than now − 3 min."""
        now = g.parse_ts("2026-09-26T03:24:05.000Z")
        ledger = _ledger(tmp_path, now=now)
        ledger.ingest(_lines("open_accept_after_idle.txt"))
        st = ledger.state
        assert st.idle_beats == 4 and st.last_heartbeat.ts == "2026-09-26T03:23:45.104Z"
        assert ledger.open_row() is not None and st.last_lifecycle.kind in g.ACCEPTED_KINDS  # gate (c) must refuse
        assert st.current["elapsedS"] == 4
        # a frozen tail cannot vouch "idle": with the clock 10 min later the beats age out
        stale = SeatLedger(tmp_path / "stale.sqlite", seat=7, now=lambda: now + 600)
        stale.ingest(_lines("open_accept_after_idle.txt"))
        assert stale.state.idle_beats == 0 and stale.state.heartbeats_recent == []
        ledger.close(); stale.close()

    def test_disconnected_beats_and_connection_counters(self, tmp_path: Path) -> None:
        """Spec §6 rule 3: two consecutive `disconnected` beats; a redeploy wave is one loss + one admitted."""
        now = g.parse_ts("2026-09-26T02:46:00.000Z")
        ledger = _ledger(tmp_path, now=now)
        ledger.ingest(_lines("redeploy_wave.txt"))
        st = ledger.state
        assert st.consecutive_disconnected == 0 and st.last_admitted_utc == "2026-09-26T02:45:26.585Z"
        assert st.disconnects_24h == 1 and st.reconnects_24h == 1  # the 09-24 window is older than 24 h
        assert (st.fleet_online, st.fleet_enrolled) == (406, 417)
        mid = SeatLedger(tmp_path / "mid.sqlite", seat=7, now=lambda: g.parse_ts("2026-09-24T22:23:00.000Z"))
        mid.ingest(_lines("redeploy_wave.txt")[:12])
        assert mid.state.consecutive_disconnected == 3 and mid.state.disconnects_24h == 1 and mid.state.reconnects_24h == 0
        # a SILENT drop (captured 2026-09-26 02:45, seat #7): no `server closed:`/502/socket line, only `reconnecting` -> still one loss
        silent = SeatLedger(tmp_path / "silent.sqlite", seat=7, now=lambda: g.parse_ts("2026-09-26T02:46:00.000Z"))
        silent.ingest(_classify([
            "2026-09-26T02:44:55.471Z alive 14h59m · idle · 80 submitted · fleet 402 online, 417 enrolled",
            "2026-09-26T02:45:23.814Z reconnecting in 1.7s",
            "2026-09-26T02:45:25.485Z disconnected 14h59m · idle · 80 submitted · fleet 6 online, 417 enrolled",
            "2026-09-26T02:45:25.706Z connected to api.imd.fun",
            "2026-09-26T02:45:26.585Z admitted (session 94f3d61f)",
        ]))
        assert silent.state.disconnects_24h == 1 and silent.state.reconnects_24h == 1
        assert silent.state.last_admitted_utc == "2026-09-26T02:45:26.585Z"
        ledger.close(); mid.close(); silent.close()

    def test_paused_hint_and_fleet_from_heartbeats(self, tmp_path: Path) -> None:
        """Spec §5.1: pausedHint carries until/failedRuns/reason (redacted); fleet is null when the clause is absent."""
        now = g.parse_ts("2026-09-25T23:56:30.000Z")
        ledger = _ledger(tmp_path, now=now)
        ledger.ingest(_lines("heartbeat_lingering_pause.txt")[:16])
        hint = ledger.state.paused_hint
        assert hint["until"] == "23:53" and hint["failedRuns"] == 3 and hint["seenUtc"] == "2026-09-25T23:55:52.556Z"
        assert "sk-[redacted]" in hint["reason"] and SK_RE.search(hint["reason"]) is None
        ledger.ingest(_lines("heartbeat_lingering_pause.txt")[16:])
        assert ledger.state.paused_hint is None  # the newest beat carries no suffix
        assert ledger.state.submitted_since_start == 17
        nofleet = SeatLedger(tmp_path / "nofleet.sqlite", seat=7, now=lambda: g.parse_ts("2026-09-25T15:13:25.000Z"))
        nofleet.ingest(_lines("heartbeat_no_fleet.txt")[:8])
        assert nofleet.state.fleet_online == 320 and nofleet.state.fleet_seen_utc == "2026-09-25T15:12:44.631Z"
        assert nofleet.state.last_heartbeat.fields["online"] is None
        ledger.close(); nofleet.close()

    def test_release_available_and_build_mismatch(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path)
        ledger.ingest(_classify([
            "2026-09-23T19:56:32.045Z 0.1.0+79f4f4d5 installed; 0.1.0+61d04d62 is available; when idle, stop the worker and run `imd update`, or start with --auto-update so it happens by itself",
            "2026-09-23T19:56:33.000Z build mismatch: control plane 0.1.0+aa634633",
        ]))
        st = ledger.state
        assert (st.daemon_version, st.release_available, st.build_mismatch) == ("0.1.0+79f4f4d5", "0.1.0+61d04d62", True)
        ledger.ingest(_classify(["2026-09-23T19:58:33.000Z runtimes: codex codex-cli 0.157.0 (using codex, as asked)",
                                 "2026-09-23T19:58:33.300Z release 0.1.0+61d04d62, the latest"]))
        assert (st.daemon_version, st.release_available, st.build_mismatch) == ("0.1.0+61d04d62", None, False)
        ledger.close()


# ---------------------------------------------------------------------------------------- Task 2.9
WORK_ROWS = [
    {"jobId": "6c296b69-8c22-435c-a2c2-56ab1660bb4e", "objective": "Compare floors", "jobState": "completed",
     "nodeKey": "oracle_assess", "role": "implement", "status": "accepted",
     "submissionHash": "f7ef8612dee7a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a",
     "submittedAt": "2026-09-23T19:35:16.822Z", "acceptedAt": "2026-09-23 19:52:36.822+00"},
    {"jobId": "9f1c2d3e-0000-4000-8000-000000000001", "objective": "x", "jobState": "blocked",
     "nodeKey": "oracle_assess", "role": "implement", "status": "failed",
     "submissionHash": "5b83f0929a19ffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "submittedAt": "2026-09-24T05:36:50.343Z", "acceptedAt": None},
    {"jobId": "9f1c2d3e-0000-4000-8000-000000000002", "objective": "pending research", "jobState": "open",
     "nodeKey": "hunt_d", "role": "tests", "status": "pending", "submissionHash": None,
     "submittedAt": "2026-09-24T05:36:50.343Z", "acceptedAt": None},
    {"jobId": "9f1c2d3e-0000-4000-8000-000000000003", "status": "rejected", "submissionHash": 12345,
     "submittedAt": "2026-09-24T05:36:50.343Z"},
    {"jobId": "9f1c2d3e-0000-4000-8000-000000000004", "status": "accepted",
     "submissionHash": "000000000000ffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "submittedAt": "2026-09-24T05:36:50.343Z", "acceptedAt": "2026-09-24 05:40:00+00"},
]


class TestApiJoins:
    def test_attach_work_joins_by_hash12_prefix(self, tmp_path: Path) -> None:
        """Spec §6: verdict per row by `submissionHash.startswith(hash12)`; verdict lag from Postgres-text acceptedAt."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        joined = ledger.attach_work(WORK_ROWS, as_of_utc="2026-09-26T03:40:09Z")
        assert joined == 3  # two local joins plus the newly retained plane-only attempt
        accepted = [r for r in _by_node(ledger, "4cf722c7") if r["hash12"] == "f7ef8612dee7"][0]
        assert accepted["outcome"] == "accepted" and accepted["outcomeAsOfUtc"] == "2026-09-26T03:40:09Z"
        assert accepted["jobId"] == "6c296b69-8c22-435c-a2c2-56ab1660bb4e" and accepted["nodeKey"] == "oracle_assess"
        assert accepted["acceptedAtApi"] == "2026-09-23 19:52:36.822+00" and accepted["verdictLagS"] == 1040
        assert accepted["source"] == {"row": "local", "outcome": "api", "reason": "none"}
        failed = [r for r in _by_node(ledger, "4cf722c7") if r["hash12"] == "5b83f0929a19"][0]
        assert failed["outcome"] == "failed" and failed["verdictLagS"] is None and failed["failureReason"] is None
        untouched = [r for r in ledger.rows() if r["hash12"] == "cee9e3163b14"][0]
        assert untouched["outcome"] is None
        ledger.close()

    def test_duplicate_hash12_prefers_the_stored_row_nearest_before_submitted_at(self, tmp_path: Path) -> None:
        """Header Review Focus 4: two rows with one hash12 → the row whose storedUtc is nearest before submittedAt."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_classify([
            "2026-09-24T05:00:00.000Z accepted implement aaaa1111 — a (max 60 turns)",
            "2026-09-24T05:00:10.000Z submitted implement for aaaa1111",
            "2026-09-24T05:00:11.000Z submission stored (000000000000) — awaiting verdict",
        ]))
        ledger._conn.execute("INSERT INTO tasks(key, seat, node8, accepted_utc, submitted_utc, stored_utc, hash12, source_row) "
                             "VALUES ('7/bbbb2222/2026-09-24T05:30:00.000Z', 7, 'bbbb2222', '2026-09-24T05:30:00.000Z', "
                             "'2026-09-24T05:30:10.000Z', '2026-09-24T05:30:11.000Z', '000000000000', 'local')")
        ledger._conn.commit()
        assert ledger.attach_work([WORK_ROWS[4]], as_of_utc="2026-09-26T03:40:09Z") == 1
        joined = [r for r in ledger.rows() if r["outcome"] == "accepted"]
        assert len(joined) == 1 and joined[0]["nodeId8"] == "bbbb2222"
        ledger.close()

    def test_attach_reason_and_failed_rows_needing_reason(self, tmp_path: Path) -> None:
        """Spec §6: reasons are the enum word only; ≤2 failed rows older than the standing window per cycle."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        ledger.attach_work(WORK_ROWS, as_of_utc="2026-09-26T03:40:09Z")
        needing = ledger.failed_rows_needing_reason(older_than_utc="2026-09-25T03:40:09Z")
        assert [r["jobId"] for r in needing] == ["9f1c2d3e-0000-4000-8000-000000000001"]
        assert ledger.failed_rows_needing_reason(older_than_utc="2026-09-24T00:00:00Z") == []
        updated = ledger.attach_reason("9f1c2d3e-0000-4000-8000-000000000001", reason="runtime_error",
                                       failure_class="machine", source="submissions")
        assert updated == 1
        (row,) = [r for r in ledger.rows() if r["outcome"] == "failed"]
        assert (row["failureReason"], row["failureClass"], row["source"]["reason"]) == ("runtime_error", "machine", "submissions")
        assert ledger.failed_rows_needing_reason(older_than_utc="2026-09-25T03:40:09Z") == []
        assert ledger.attach_reason("no-such-job", reason="internal_error", failure_class=None, source="standing") == 0
        ledger.close()

    def test_seed_api_rows_never_overwrites_a_local_row(self, tmp_path: Path) -> None:
        """Spec §5.6 / §16 #15: history rows are flagged `source.row == "api"`; a hash the ledger holds is skipped."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        inserted = ledger.seed_api_rows(WORK_ROWS + [
            {"jobId": "9f1c2d3e-0000-4000-8000-000000000009", "role": "implement", "status": "accepted", "nodeKey": "oracle_assess",
             "objective": "older than the log", "submissionHash": "abcdef012345ffffffffffffffffffffffffffffffffffffffffffffffffffff",
             "submittedAt": "2026-09-20T18:00:00.000Z", "acceptedAt": "2026-09-20 18:17:20+00"},
        ], seat=7)
        assert inserted == 2  # WORK_ROWS[4] (unknown hash) and the pre-log row; f7ef…/5b83… exist locally; null/int hashes skipped
        api_rows = [r for r in ledger.rows(limit=100) if r["source"]["row"] == "api"]
        assert len(api_rows) == 2 and all(r["nodeId8"] is None and r["hash12"] for r in api_rows)
        old = [r for r in api_rows if r["hash12"] == "abcdef012345"][0]
        assert old["acceptedUtc"] == "2026-09-20T18:00:00.000Z" and old["outcome"] == "accepted" and old["verdictLagS"] == 1040
        local = [r for r in _by_node(ledger, "4cf722c7") if r["hash12"] == "f7ef8612dee7"][0]
        assert local["source"]["row"] == "local" and local["acceptedUtc"] == "2026-09-23T19:34:26.693Z"
        assert ledger.seed_api_rows(WORK_ROWS, seat=7) == 0  # idempotent
        ledger.close()


def test_null_submission_hash_never_joins(tmp_path: Path) -> None:
    """Header Review Focus 4: a `null` or non-string `submissionHash` is skipped — `str.startswith(None)` would raise
    inside the tick; the rows stay `unknown` (None) and counters are validated elsewhere."""
    ledger = _ledger(tmp_path, now=1790230000.0)
    ledger.ingest(_lines("double_accept.txt"))
    joined = ledger.attach_work([WORK_ROWS[2], WORK_ROWS[3], {"status": "accepted"}, "not a dict"],
                                as_of_utc="2026-09-26T03:40:09Z")
    assert joined == 0 and all(r["outcome"] is None for r in ledger.rows())
    ledger.close()


class TestWorkDirs:
    def test_work_dirs_attach_ids_and_the_abnormal_flag(self, tmp_path: Path) -> None:
        """Spec §5.2 work-stat / §8 LEDGER detail: the dir name gives the full ids; mtime ≈ accept picks the attempt."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        node = "4cf722c7-101e-473b-a153-3315d3673a83"
        job = "6c296b69-8c22-435c-a2c2-56ab1660bb4e"
        joined = ledger.attach_work_dirs([
            {"jobId": job, "nodeId": node, "mtimeUtc": "2026-09-23T19:34:27Z", "abnormal": True},
            {"jobId": job, "nodeId": node, "mtimeUtc": "2026-09-24T05:36:50Z", "abnormal": False},
            {"jobId": "x", "nodeId": "ffffffff-0000-4000-8000-000000000000", "mtimeUtc": "2026-09-23T19:34:27Z", "abnormal": True},
            {"jobId": "y", "nodeId": node, "mtimeUtc": "2026-09-23T12:00:00Z", "abnormal": True},  # no accept within 300 s
            {"jobId": "z", "nodeId": None, "mtimeUtc": None, "abnormal": True},
            "not a dict",
        ])
        assert joined == 2
        by_accept = {r["acceptedUtc"]: r for r in _by_node(ledger, "4cf722c7")}
        flagged = by_accept["2026-09-23T19:34:26.693Z"]
        assert flagged["workDirAbnormal"] is True and flagged["nodeId"] == node and flagged["jobId"] == job
        assert by_accept["2026-09-24T05:36:49.988Z"]["workDirAbnormal"] is False
        assert by_accept["2026-09-23T17:08:39.905Z"]["workDirAbnormal"] is None and by_accept["2026-09-23T17:08:39.905Z"]["nodeId"] is None
        ledger.close()


# ---------------------------------------------------------------------------------------- Task 2.10
CODEX_SESSION = {
    "path": "/home/imd-worker/.codex/sessions/2026/09/23/rollout-2026-09-23T19-34-27-uuid.jsonl", "runtime": "codex",
    "cwd": "/home/imd-worker/.identitymd/work/6c296b69-8c22-435c-a2c2-56ab1660bb4e/4cf722c7-101e-473b-a153-3315d3673a83",
    "slug": None, "kind": "task", "jobId": "6c296b69-8c22-435c-a2c2-56ab1660bb4e",
    "nodeId": "4cf722c7-101e-473b-a153-3315d3673a83", "startedUtc": "2026-09-23T19:34:27.500Z",
    "endedUtc": "2026-09-23T19:35:15.900Z", "mtime": 1790364915.9, "bytes": 200000, "model": "gpt-5.6-luna", "effort": "medium",
    "turns": 3, "turnsDefinition": "agent_messages", "tokens": {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0},
    "sideModel": None, "ttftMs": 1807, "wallMs": 22400, "turn1Context": 24000, "maxTurnsReached": False, "maxTurns": 60,
    "apiErrors": [], "lastAgentMessageEmpty": False, "tokenCountInfoMissing": False, "taskCompleteErrorPresent": False,
    "quota": {"usedPercent": 45.0, "windowMinutes": 10080, "resetsAtUtc": "2026-09-28T21:50:11Z", "planType": "pro",
              "sampledAtUtc": "2026-09-23T19:35:15Z"}, "skippedOversize": 0, "error": None,
}


class TestSessions:
    def test_attach_sessions_joins_a_task_by_node_and_time(self, tmp_path: Path) -> None:
        """Spec §10 fixture pair: Codex 15bb693b-style 17,864 / 92,928 / 812, turns 3 — attached to the matching attempt."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        assert ledger.attach_sessions([CODEX_SESSION], runtime="codex") == 1
        row = [r for r in _by_node(ledger, "4cf722c7") if r["acceptedUtc"] == "2026-09-23T19:34:26.693Z"][0]
        assert row["tokens"] == {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0}
        assert (row["turns"], row["turnsDefinition"], row["effort"], row["sessionFiles"]) == (3, "agent_messages", "medium", 1)
        assert row["nodeId"] == "4cf722c7-101e-473b-a153-3315d3673a83" and row["jobId"] == "6c296b69-8c22-435c-a2c2-56ab1660bb4e"
        assert (row["ttftMs"], row["wallMs"], row["turn1Context"], row["maxTurnsReached"]) == (1807, 22400, 24000, False)
        others = [r for r in _by_node(ledger, "4cf722c7") if r["acceptedUtc"] != "2026-09-23T19:34:26.693Z"]
        assert all(r["tokens"] is None for r in others)
        ledger.close()

    def test_multi_file_attempt_adds_tokens_but_not_turns(self, tmp_path: Path) -> None:
        """Spec §10 / fill3 §2: 7b9c907d hunt_d — tokens additive across files (73,695 + 1,263), turns not (61 ≠ 58 + 8)."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_classify(["2026-09-24T03:50:34.996Z accepted tests e78e1517 — test/fren-review/hunt_d (max 60 turns)",
                                 "2026-09-24T04:13:46.135Z submitted tests for e78e1517"]))
        a = dict(CODEX_SESSION, path="/x/a.jsonl", nodeId="e78e1517-0000-4000-8000-000000000000", startedUtc="2026-09-24T03:52:33.000Z",
                 mtime=1790306000.0, tokens={"input": 70000, "output": 3695, "cached": 0, "cacheWrite": 0}, turns=58)
        b = dict(CODEX_SESSION, path="/x/b.jsonl", nodeId="e78e1517-0000-4000-8000-000000000000", startedUtc="2026-09-24T04:05:00.000Z",
                 mtime=1790307000.0, tokens={"input": 1000, "output": 263, "cached": 0, "cacheWrite": 0}, turns=8)
        assert ledger.attach_sessions([a, b], runtime="codex") == 2
        (row,) = ledger.rows()
        assert row["tokens"]["input"] + row["tokens"]["output"] == 74958 and row["turns"] == 58 and row["sessionFiles"] == 2
        ledger.close()

    def test_research_session_joins_within_two_seconds_and_probes_are_excluded(self, tmp_path: Path) -> None:
        """Spec §10: research joins by cwd == work root + start within RESEARCH_JOIN_S; doctor/manual never attach."""
        ledger = _ledger(tmp_path, now=1790457000.0)
        ledger.ingest(_lines("research_question.txt"))
        research = dict(CODEX_SESSION, path="/r.jsonl", kind="research", jobId=None, nodeId=None,
                        cwd="/home/imd-worker/.identitymd/work", startedUtc="2026-09-25T18:08:55.948Z", model="gpt-5.6-luna",
                        tokens={"input": 24568, "output": 2835, "cached": 45056, "cacheWrite": 0}, turns=2)
        doctor = dict(CODEX_SESSION, path="/d.jsonl", kind="doctor", jobId=None, nodeId=None, startedUtc="2026-09-25T18:08:56.000Z")
        manual = dict(CODEX_SESSION, path="/m.jsonl", kind="manual", jobId=None, nodeId=None, startedUtc="2026-09-25T18:08:56.000Z")
        late = dict(research, path="/late.jsonl", startedUtc="2026-09-25T18:09:10.000Z")
        assert ledger.attach_sessions([research, doctor, manual, late], runtime="codex") == 1
        (row,) = ledger.rows()
        assert row["tokens"] == {"input": 24568, "output": 2835, "cached": 45056, "cacheWrite": 0} and row["sessionFiles"] == 1
        stored = {r[0]: r[1] for r in ledger._conn.execute("SELECT path, task_key FROM sessions")}
        assert stored["/r.jsonl"] == row["key"] and stored["/d.jsonl"] is None and stored["/m.jsonl"] is None and stored["/late.jsonl"] is None
        # the late research session stays unattached too, but only doctor/manual/unknown are cost exclusions (spec §7)
        assert sorted(s["kind"] for s in ledger.unattached_sessions(since_utc="2026-09-25T00:00:00Z")) == ["doctor", "manual"]
        ledger.close()

    def test_api_error_messages_are_redacted_when_stored(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        session = dict(CODEX_SESSION, apiErrors=[{"status": 401, "message": "401 Unauthorized: Incorrect API key provided: sk-svcac********",
                                                  "atUtc": "2026-09-23T19:34:30.000Z"}])
        ledger.attach_sessions([session], runtime="codex")
        row = [r for r in _by_node(ledger, "4cf722c7") if r["acceptedUtc"] == "2026-09-23T19:34:26.693Z"][0]
        assert row["apiErrors"][0]["status"] == 401 and "sk-[redacted]" in row["apiErrors"][0]["message"]
        assert SK_RE.search(str(row["apiErrors"])) is None
        ledger.close()

    def test_unattached_sessions_feed_cost_exclusions(self, tmp_path: Path) -> None:
        """Spec §7 ``cost.excluded`` / §8 COST ``excluded 2 doctor``: the task_key-NULL summaries are read back for seat_cost."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.attach_sessions([{"path": "/r/d.jsonl", "kind": "doctor", "startedUtc": "2026-09-23T10:00:00.000Z"},
                                {"path": "/r/m.jsonl", "kind": "manual", "startedUtc": "2026-09-23T11:00:00.000Z"},
                                {"path": "/r/o.jsonl", "kind": "doctor", "startedUtc": "2026-09-01T11:00:00.000Z"}], runtime="codex")
        assert ledger.unattached_sessions(since_utc="2026-09-19T00:00:00Z") == [
            {"kind": "doctor", "startedUtc": "2026-09-23T10:00:00.000Z"}, {"kind": "manual", "startedUtc": "2026-09-23T11:00:00.000Z"}]
        ledger.close()

    def test_unjoined_claude_rows_older_than_30_days_are_marked_expired(self, tmp_path: Path) -> None:
        """Spec §5.4 Claude retention: a row no transcript joined within 30 days reads ``tokens: null``, reason ``transcript expired``."""
        ledger = _ledger(tmp_path, seat=420, now=1790391000.0)
        ledger.ingest(_classify([
            "2026-08-26T10:00:00.000Z accepted implement aaaa1111 — a (max 60 turns)",
            "2026-08-26T10:00:01.000Z   working: running claude on claude-sonnet-5",
            "2026-08-26T10:01:00.000Z submitted implement for aaaa1111",
            "2026-08-26T10:01:00.100Z submission stored (aaaa11110000) — awaiting verdict",
            "2026-08-26T11:00:00.000Z accepted implement bbbb2222 — a (max 60 turns)",
            "2026-08-26T11:00:00.400Z submitted implement for bbbb2222",
            "2026-08-26T11:00:00.500Z submission stored (bbbb22220000) — awaiting verdict",
            "2026-08-28T10:00:00.000Z accepted implement cccc3333 — a (max 60 turns)",
            "2026-08-28T10:00:01.000Z   working: running claude on claude-sonnet-5",
            "2026-08-28T10:01:00.000Z submitted implement for cccc3333",
            "2026-08-28T10:01:00.100Z submission stored (cccc33330000) — awaiting verdict",
        ]))
        now_utc = "2026-09-26T12:00:00Z"
        assert ledger.mark_expired_transcripts(runtime="codex", now_utc=now_utc) == 0  # codex rollouts are never deleted
        assert ledger.mark_expired_transcripts(runtime="claude", now_utc=now_utc) == 1
        reasons = {r["nodeId8"]: (r["tokens"], r["tokensReason"], r["preAgentFailure"]) for r in ledger.rows()}
        assert reasons == {"aaaa1111": (None, "transcript expired", False),  # 31 days old, never joined
                           "bbbb2222": (None, None, True),  # pre-agent failure: no transcript ever existed
                           "cccc3333": (None, None, False)}  # 29 days old: still inside the window
        assert ledger.mark_expired_transcripts(runtime="claude", now_utc=now_utc) == 0  # idempotent
        # a transcript that still joins (the summariser caught it before the sweep) clears the reason
        late = dict(CODEX_SESSION, path="/c/aaaa.jsonl", runtime="claude", nodeId="aaaa1111-0000-4000-8000-000000000000",
                    jobId=None, startedUtc="2026-08-26T10:00:01.500Z")
        assert ledger.attach_sessions([late], runtime="claude") == 1
        (row,) = _by_node(ledger, "aaaa1111")
        assert row["tokensReason"] is None and row["tokens"]["output"] == 812
        ledger.close()

    def test_the_sessions_own_runtime_wins_over_the_callers_guess(self, tmp_path: Path) -> None:
        """Spec §10 ``turnsDefinition``: WP7's first sessions cycle passes ``runtime="codex"`` before ``imd status`` names the
        runtime, and the Mac broker answers with Claude transcripts anyway; the stored session's ``runtime`` decides the turns
        definition and the effort re-derivation, so a Claude row never reads ``agent_messages``."""
        calls: list[tuple] = []

        def lookup(runtime, model, effort, at, *, seat=None):
            calls.append((runtime, model, effort))
            return f"{runtime}/{effort}" if str(model).startswith(runtime) else None  # like tier_for: codex never knows a claude model

        ledger = _ledger(tmp_path, seat=420, now=1790391000.0, tier_lookup=lookup)
        ledger.ingest(_classify([
            "2026-09-26T01:00:00.000Z accepted implement dddd4444 — a (max 60 turns)",
            "2026-09-26T01:00:01.000Z   working: running claude on claude-sonnet-5",
            "2026-09-26T01:05:00.000Z submitted implement for dddd4444",
        ]))
        assert _by_node(ledger, "dddd4444")[0]["tierDerived"] == "claude/None"  # accept-time tier, derived without the effort
        claude = dict(CODEX_SESSION, path="/home/imd/.claude/projects/-home-imd--identitymd-work-x/dddd.jsonl", runtime="claude",
                      nodeId="dddd4444-0000-4000-8000-000000000000", jobId=None, startedUtc="2026-09-26T01:00:01.500Z",
                      model="claude-sonnet-5", effort="high", turnsDefinition="user_lines", quota=None)
        assert ledger.attach_sessions([claude], runtime="codex") == 1  # the caller's guess is wrong
        (row,) = _by_node(ledger, "dddd4444")
        assert (row["turnsDefinition"], row["effort"], row["tierDerived"]) == ("user_lines", "high", "claude/high")
        assert calls[-1] == ("claude", "claude-sonnet-5", "high")
        ledger.close()


# ---------------------------------------------------------------------------------------- Task 2.11
class TestRollups:
    def test_rollup_day_and_days_and_today(self, tmp_path: Path) -> None:
        """Spec §5.6: per-day counts with source per figure live in the sqlite `days` table (not a SeriesCache)."""
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        ledger.attach_work(WORK_ROWS, as_of_utc="2026-09-26T03:40:09Z")
        ledger.attach_sessions([CODEX_SESSION], runtime="codex")
        day = ledger.rollup_day("2026-09-23", now_utc="2026-09-26T03:41:00Z")
        assert (day["tasks"], day["stored"], day["notStored"], day["accepted"], day["failed"], day["pending"]) == (2, 2, 0, 1, 0, 0)
        assert day["tokens"]["output"] == 812 and day["turns"] == 3 and day["verdictLagP50S"] == 1040
        assert day["longestS"] > day["p50S"] > 0 and day["updatedUtc"] == "2026-09-26T03:41:00Z"
        assert day["source"] == {"tasks": "local", "verdicts": "api", "tokens": "sessions"}
        ledger.rollup_day("2026-09-22", now_utc="2026-09-26T03:41:00Z")
        ledger.rollup_day("2026-09-24", now_utc="2026-09-26T03:41:00Z")
        days = ledger.days(n=14)
        assert [d["dayUtc"] for d in days] == ["2026-09-22", "2026-09-23", "2026-09-24"]  # oldest first
        assert days[0]["tasks"] == 3 and days[2]["failed"] == 1 and days[0]["tokens"]["output"] is None
        assert [d["dayUtc"] for d in ledger.days(n=2)] == ["2026-09-23", "2026-09-24"]
        today = ledger.today("2026-09-24")
        assert set(today) == {"dayUtc", "tasks", "stored", "notStored", "p50S", "longestS", "accepted", "rejected", "failed",
                              "pending", "verdictLagP50S", "verdictsAsOfUtc"}
        assert (today["tasks"], today["failed"], today["verdictsAsOfUtc"]) == (2, 1, "2026-09-26T03:40:09Z")
        assert all(today[k] is None or type(today[k]) is int for k in ("p50S", "longestS", "verdictLagP50S"))  # spec §7 whole seconds
        assert ledger.today("2026-09-30")["tasks"] == 0 and ledger.today("2026-09-30")["p50S"] is None
        ledger.close()

    def test_rollup_day_is_an_upsert(self, tmp_path: Path) -> None:
        ledger = _ledger(tmp_path, now=1790230000.0)
        ledger.ingest(_lines("double_accept.txt"))
        ledger.rollup_day("2026-09-23", now_utc="2026-09-26T03:41:00Z")
        ledger.rollup_day("2026-09-23", now_utc="2026-09-26T03:46:00Z")
        assert ledger._conn.execute("SELECT COUNT(*) FROM days").fetchone()[0] == 1
        assert ledger.days()[0]["updatedUtc"] == "2026-09-26T03:46:00Z"
        ledger.close()

    def test_lease_closed_row_is_not_stored_today(self, tmp_path: Path) -> None:
        """Mutation proof 5 (day half): the lease-closed b6d17f8d counts as a task, not as stored."""
        ledger = _ledger(tmp_path, now=1790391000.0)
        ledger.ingest(_lines("cancel_lease_closed.txt"))
        today = ledger.today("2026-09-26")
        assert (today["tasks"], today["stored"], today["notStored"]) == (3, 1, 2)
        assert type(today["p50S"]) is int and type(today["longestS"]) is int
        ledger.close()


# ---------------------------------------------------------------------------------------- Task 2.12
class TestCorpus:
    def test_replaying_500_lines_twice_is_idempotent(self, tmp_path: Path) -> None:
        """Spec §9 Watermarks: ledger rows are idempotent upserts — replaying the same lines yields identical rows."""
        source = (FIXTURES / "journal7d.txt")
        if not source.exists():
            pytest.skip("journal7d.txt not captured yet (Task 2.12, owner-run)")
        raw = source.read_text(encoding="utf-8").splitlines()[6000:6500]
        ledger = _ledger(tmp_path, now=1790391000.0)
        first = ledger.ingest(g.classify(line, seq=i) for i, line in enumerate(raw))
        snapshot = [tuple(r) for r in ledger._conn.execute("SELECT * FROM tasks ORDER BY key")]
        # a re-attached tail (cursor lost, `--since` fallback) re-delivers the same lines with new seq numbers
        second = ledger.ingest(g.classify(line, seq=10_000 + i) for i, line in enumerate(raw))
        replay = [tuple(r) for r in ledger._conn.execute("SELECT * FROM tasks ORDER BY key")]
        assert first.opened == 5 and second.opened == 0 and second.stored == 0  # lines 6000–6500 hold five accepts
        assert len(snapshot) == len(replay) == ledger.counts()["rows"]
        assert [s[:-1] for s in snapshot] == [r[:-1] for r in replay]  # every column but updated_utc identical
        ledger.close()


def test_corpus_ledger_counts(tmp_path: Path) -> None:
    """Spec §14 grammar corpus through the ledger: 277 VPS rows (276 implement + 1 research), all stored;
    292 Mac rows all stored, 3 repairs, 2 re-sends; 5 + 1 pre-agent failures."""
    for name, seat, rows, pre_agent, repairs, resent in (("journal7d.txt", 7, 277, 5, 0, 0), ("docker420.log", 420, 292, 1, 3, 2)):
        path = FIXTURES / name
        if not path.exists():
            pytest.skip(f"{name} not captured yet (Task 2.12, owner-run)")
        docker = name.endswith(".log")
        lines = [g.classify(g.strip_docker_prefix(l) if docker else l, seq=i)
                 for i, l in enumerate(path.read_text(encoding="utf-8").splitlines())]
        ledger = SeatLedger(tmp_path / f"{seat}.sqlite", seat=seat, now=lambda: 1790391000.0)
        result = ledger.ingest(lines)
        all_rows = ledger.rows(limit=1000)
        assert len(all_rows) == rows == result.opened and result.stored == rows
        assert all(r["storedUtc"] and r["hash12"] for r in all_rows) and ledger.open_row() is None
        assert sum(1 for r in all_rows if r["preAgentFailure"]) == pre_agent
        assert sum(1 for r in all_rows if r["repair"]) == repairs and sum(1 for r in all_rows if r["resent"]) == resent
        assert result.restarts == (9 if seat == 7 else 8)  # every `runtimes:` banner incl. the first start
        assert not any(r["interruptedByRestart"] for r in all_rows)  # 16/16 restarts were idle (fill1 §0)
        ledger.close()


def test_attach_sessions_sanitizes_every_string_before_sqlite(tmp_path):
    import json
    from maxpane_dashboard.data.seat_ledger import SeatLedger
    secret = 'sk-review_SYNTHETIC_fragment'
    session = {'path': '/ordinary/session.jsonl', 'runtime': 'codex', 'kind': 'manual',
               'cwd': '/ordinary/work', 'model': secret, 'effort': '\x1b[31mhigh\x00',
               'tokens': {'input': 123, 'output': 45, 'cached': 67, 'cacheWrite': 89},
               'sideModel': [{'model': secret, 'input': 12}], 'quota': {secret: [secret]},
               'apiErrors': [{'message': secret, 'atUtc': secret, 'status': 401}], 'error': secret}
    ledger = SeatLedger(tmp_path / 'sanitized.sqlite', seat=7)
    try:
        ledger.attach_sessions([session], runtime='codex')
        row = dict(ledger._conn.execute('SELECT * FROM sessions').fetchone())
        assert secret not in json.dumps(row) and '\\u001b' not in json.dumps(row) and '\\u0000' not in json.dumps(row)
        assert row['model'] == 'sk-[redacted]' and row['effort'] == '␛[31mhigh'
        assert row['path'] == session['path'] and row['cwd'] == session['cwd']
        assert [row['tokens_' + k] for k in ('input', 'output', 'cached', 'cache_write')] == [123, 45, 67, 89]
        assert session['model'] == secret  # caller's data is not mutated
    finally:
        ledger.close()


@pytest.mark.parametrize("fixture", ["local_fail_empty.txt", "local_fail_stripped.txt"])
def test_empty_local_failure_closes_the_ledger_row(tmp_path, fixture):
    ledger = _ledger(tmp_path)
    try:
        lines = _lines(fixture)
        assert lines[-1].kind == g.KIND_LOCAL_FAIL
        assert lines[-1].fields["msg"] in (None, "")
        ledger.ingest(lines)
        assert ledger.open_row() is None
        assert ledger.state.last_lifecycle.kind == g.KIND_LOCAL_FAIL
    finally:
        ledger.close()
