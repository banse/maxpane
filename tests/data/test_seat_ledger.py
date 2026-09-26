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
