"""``imd_dashd/audit.py`` -- one line per phase, seq monotonic, fixed field set (spec §11 audit line, §13)."""
from __future__ import annotations

import json
import os
import stat

import pytest

from imd_dashd.audit import AUDIT_FIELDS, PHASES, Audit


def test_append_fills_ts_and_seq_and_the_fixed_field_set(tmp_path):
    # spec §11: {"ts","seq","peer_uid","verb","phase","plan_id","args","preconditions","outcome","verified","connected","cursor_before","cursor_after"}
    audit = Audit(tmp_path / "audit.jsonl", now=lambda: 1_790_000_000.0)
    seq = audit.append(peer_uid=1001, verb="restart", phase="plan", plan_id="7f3a9c1e2b4d6081",
                       args={"offline": False}, preconditions={"idle_beats": 9}, outcome="planned")
    assert seq == 1 and audit.seq == 1
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert tuple(record) == AUDIT_FIELDS
    assert record["ts"] == "2026-09-21T14:13:20Z" and record["seq"] == 1
    assert record["verified"] is None and record["cursor_after"] is None


def test_seq_is_monotonic_across_reopen(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = Audit(path, now=lambda: 1.0)
    first.append(verb="restart", phase="plan")
    first.append(verb="restart", phase="apply", outcome="applied")
    second = Audit(path, now=lambda: 2.0)         # a socket-activated broker restarts often (spec §12.1)
    assert second.seq == 2
    assert second.append(verb="restart", phase="verify", verified=True) == 3


def test_unknown_field_and_unknown_phase_raise(tmp_path):
    audit = Audit(tmp_path / "a.jsonl", now=lambda: 1.0)
    with pytest.raises(TypeError):
        audit.append(verb="restart", phase="plan", config_body="{...}")     # spec §13: never file bodies
    with pytest.raises(TypeError):
        audit.append(verb="restart", phase="plan", seq=99)                  # seq is the log's, not the caller's
    with pytest.raises(ValueError):
        audit.append(verb="restart", phase="reboot")
    assert not (tmp_path / "a.jsonl").exists()


def test_tail_returns_newest_n_oldest_first_and_skips_corrupt_lines(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = Audit(path, now=lambda: 1.0)
    for i in range(5):
        audit.append(verb="restart", phase="plan", plan_id=f"{i:016x}")
    with path.open("a") as fh:
        fh.write("{not json\n")
    tail = audit.tail(3)
    assert [r["plan_id"] for r in tail] == ["0000000000000002", "0000000000000003", "0000000000000004"]
    assert audit.tail(0) == [] and Audit(tmp_path / "missing.jsonl").tail(5) == []


def test_file_is_created_0600(tmp_path):
    # spec §11: Mac ~/.maxpane/seat_audit.jsonl 0600; VPS LogsDirectory 0700
    audit = Audit(tmp_path / "audit.jsonl", now=lambda: 1.0)
    audit.append(verb="ping", phase="refused", outcome="peer_refused")
    mode = stat.S_IMODE(os.stat(tmp_path / "audit.jsonl").st_mode)
    assert mode == 0o600


def test_phases_are_the_spec_list():
    # the spec's audit phases, plus "reads": read verbs are "audited as counts only" (spec §11; deviation 16)
    assert PHASES == ("plan", "apply", "verify", "refused", "canary", "drain_armed", "drain_rearmed", "drain_fire",
                      "drain_cancelled", "drain_expired", "drain_lost", "reads")


def test_audit_redacts_every_string_at_the_write_boundary(tmp_path):
    audit = Audit(tmp_path / 'audit.jsonl')
    secret = 'sk-testSyntheticKey0123456789'
    audit.append(verb='apply', phase='refused', outcome='bad_args', args={'names': [secret, '\x1b[31mname']})
    text = audit.path.read_text()
    assert secret not in text and '\\u001b' not in text
    assert audit.tail(1)[0]['args']['names'] == ['sk-[redacted]', '␛[31mname']
