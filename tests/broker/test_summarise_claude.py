"""Claude Code transcript summariser (spec §5.4, §10; contract §C.8) -- fixtures copied into slug dirs on ``tmp_path``.

Every figure asserted here is a reconciliation fact of fill3 §2 / cost §0-§1 reproduced by a
synthetic-but-faithful fixture (``tests/fixtures/seat/MANIFEST.json`` labels each one).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from imd_dashd import summarise_claude as scl

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "tests" / "fixtures" / "seat" / "sessions"
SCRIPT = REPO / "imd_dashd" / "summarise_claude.py"
TASK = "-home-imd--identitymd-work-"
F7_JOB, F7_NODE = "48e53e33-7c1d-4e2a-9b5f-3a6d8c0e1f24", "f7b20ce4-2b9a-4c6d-8e1f-5a7b9c0d2e36"
HUNT_JOB, HUNT_NODE = "7b9c907d-1e3f-4a5b-8c7d-9e1f3a5b7c9d", "6d4b2f80-5c3a-4e1d-9f7b-3a5c7e9b1d2f"


def _place(tmp_path: Path, fixture: str, slug: str, name: str = "3f0c9a52-7e1b-4d6a-8c2f-9b1e3d5a7c90.jsonl",
           mtime: float = 1790385000.0) -> Path:
    """Put a fixture where Claude Code keeps it: ``projects/<slug>/<sessionId>.jsonl``, with a fixed mtime."""
    dst = tmp_path / "projects" / slug / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SESSIONS / fixture, dst)
    os.utime(dst, (mtime, mtime))
    return dst


# ---- Task 4.6: slug classification ---------------------------------------------------------


def test_research_slug_is_not_excluded():
    # spec §5.4 / mutation proof 35: exclusions are EXACT -- a prefix match on -home-imd would swallow the research slug
    assert scl.classify_slug("-home-imd--identitymd-work") == "research"
    assert scl.classify_slug("-home-imd") == "manual"
    assert scl.classify_slug("-home-imd--identitymd-work-doctor-Ab3dE9") == "doctor"
    assert scl.classify_slug(f"{TASK}{F7_JOB}-{F7_NODE}") == "task"


def test_slug_table_matches_the_fixture():
    # tests/fixtures/seat/sessions/claude_slugs.txt: the exact-match exclusion list incl. the research slug
    rows = [line.split("\t") for line in (SESSIONS / "claude_slugs.txt").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 12
    for slug, kind in rows:
        assert scl.classify_slug(slug) == kind, slug


def test_parse_task_slug_splits_two_uuids_by_length():
    assert scl.parse_task_slug(f"{TASK}{F7_JOB}-{F7_NODE}") == (F7_JOB, F7_NODE)
    assert scl.parse_task_slug(f"{TASK}{F7_JOB}") is None
    assert scl.parse_task_slug(f"{TASK}{F7_JOB}-{F7_NODE}x") is None
    assert scl.parse_task_slug(f"{TASK}doctor-Ab3dE9") is None
    assert scl.parse_task_slug("-home-imd--identitymd-work") is None


def test_constants_match_the_contract():
    assert scl.CLAUDE_EXCLUDED_SLUGS == frozenset({"-home-imd", "-tmp", "-tmp-probe-ws", "-tmp-probe-ws2", "-tmp-probe-ws3"})
    assert scl.CLAUDE_DOCTOR_SLUG_PREFIX == "-home-imd--identitymd-work-doctor-"
    assert scl.CLAUDE_RESEARCH_SLUG == "-home-imd--identitymd-work" and scl.CLAUDE_TASK_SLUG_PREFIX == TASK
    assert (scl.MAX_FILE_BYTES, scl.MAX_LINE_BYTES, scl.PER_FILE_WALL_S) == (64 * 1024 * 1024, 1024 * 1024, 5.0)
    assert scl.SESSION_KEYS[0] == "path" and len(scl.SESSION_KEYS) == 29
