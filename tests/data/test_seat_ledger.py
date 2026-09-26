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
        assert task_cols[-1] == "updated_utc" and len(task_cols) == 54
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
    (nxt,) = _by_node(ledger, "5e0c3a11")
    assert nxt["hash12"] == "9d0e5f6a7b8c" and nxt["leaseClosed"] is False
    ledger.close()


def test_cancel_attaches_to_open_row_not_by_prefix(tmp_path: Path) -> None:
    """Mutation proof 6 (spec §14): `cancelled <lease8>` names the LEASE — attach by time, never by id match.

    The slice carries a decoy row whose node8 equals the lease id (16a4df90); an id-matching
    implementation attaches the cancel there and leaves the open row untouched.
    """
    ledger = _ledger(tmp_path, now=1790391000.0)
    ledger.ingest(_lines("cancel_lease_closed.txt"))
    (open_at_that_instant,) = _by_node(ledger, "b6d17f8d")
    (decoy,) = _by_node(ledger, "16a4df90")
    assert open_at_that_instant["cancelled"] == "superseded"
    assert decoy["cancelled"] is None and decoy["hash12"] == "0a1b2c3d4e5f"
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
        assert st.consecutive_disconnected == 0 and st.last_admitted_utc == "2026-09-26T02:45:26.180Z"
        assert st.disconnects_24h == 1 and st.reconnects_24h == 1  # the 09-24 window is older than 24 h
        assert (st.fleet_online, st.fleet_enrolled) == (398, 417)
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
