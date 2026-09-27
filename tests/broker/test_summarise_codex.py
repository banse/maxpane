"""Codex rollout summariser (spec §5.4, §10; contract §C.8) -- fixtures are copied to ``tmp_path``.

Every figure asserted here is a reconciliation fact of fill3 §3 / fill6 §6 reproduced by a
synthetic-but-faithful fixture (``tests/fixtures/seat/MANIFEST.json`` labels each one).
"""

from __future__ import annotations

import ast
import io
import json
import os
import py_compile
import shutil
import sys
from pathlib import Path

import pytest

from imd_dashd import summarise_codex as sc

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "tests" / "fixtures" / "seat" / "sessions"
WORK = "/home/imd-worker/.identitymd/work"
JOB = "15bb693b-5c2e-4a51-9d3e-0f6a2b7c8d91"
NODE = "4b9b896f-2d4e-4f8a-b1c3-7e9d0a5b6c42"


# ---- Task 4.1: the bounded line reader and cwd classification -------------------------------


def test_classify_cwd_kinds():
    # spec §5.4 / fill6 §6: task (work/<job>/<node>), research (the work root), doctor, manual (exact), unknown
    assert sc.classify_cwd(f"{WORK}/{JOB}/{NODE}", work_root=WORK) == ("task", JOB, NODE)
    assert sc.classify_cwd(WORK, work_root=WORK) == ("research", None, None)
    assert sc.classify_cwd(WORK + "/", work_root=WORK) == ("research", None, None)
    assert sc.classify_cwd(f"{WORK}/doctor-Xq3v9K", work_root=WORK) == ("doctor", None, None)
    assert sc.classify_cwd("/tmp", work_root=WORK) == ("manual", None, None)
    assert sc.classify_cwd("/home/imd-worker", work_root=WORK) == ("manual", None, None)
    assert sc.classify_cwd("/tmp/probe-ws", work_root=WORK) == ("unknown", None, None)  # exact, never a prefix
    assert sc.classify_cwd(f"{WORK}/{JOB}", work_root=WORK) == ("unknown", None, None)
    assert sc.classify_cwd(f"{WORK}/not-a-uuid/{NODE}", work_root=WORK) == ("unknown", None, None)
    assert sc.classify_cwd("", work_root=WORK) == ("unknown", None, None)


def test_bounded_reader_skips_and_counts_oversize_lines():
    # spec §5.4 hostile size: a line longer than max_line is drained unparsed and counted; the rest is yielded whole
    data = b'{"a":1}\n' + b"x" * 40 + b"\n" + b'{"b":2}\n' + b"y" * 10 + b"\n" + b'{"c":3}'
    counts = {"oversize": 0}
    lines = list(sc.iter_bounded_lines(io.BytesIO(data), counts, max_line=16))
    assert lines == [b'{"a":1}\n', b'{"b":2}\n', b"y" * 10 + b"\n", b'{"c":3}']
    assert counts == {"oversize": 1}


def test_bounded_reader_keeps_a_line_of_exactly_max_line_bytes():
    counts = {"oversize": 0}
    exact = b"z" * 16 + b"\n"
    assert list(sc.iter_bounded_lines(io.BytesIO(exact), counts, max_line=16)) == [exact]
    assert counts == {"oversize": 0}


def test_bounded_reader_enforces_wall_clock_and_total():
    ticks = iter([0.0, 0.0, 10.0])
    with pytest.raises(sc._WallClock):
        list(sc.iter_bounded_lines(io.BytesIO(b"a\nb\nc\n"), {}, deadline=5.0, clock=lambda: next(ticks)))
    with pytest.raises(sc._TooBig):
        list(sc.iter_bounded_lines(io.BytesIO(b"a" * 10 + b"\n" + b"b" * 10 + b"\n"), {}, max_total=15))


def test_constants_match_the_contract():
    assert (sc.MAX_FILE_BYTES, sc.MAX_LINE_BYTES, sc.PER_FILE_WALL_S) == (64 * 1024 * 1024, 1024 * 1024, 5.0)
    assert sc.CODEX_EXCLUDED_CWDS == ("/tmp", "/home/imd-worker")
    assert sc.CODEX_PLAIN_ROLLOUT_DAYS == 7
    assert len(sc.SESSION_KEYS) == 29 and sc.SESSION_KEYS[0] == "path" and sc.SESSION_KEYS[-1] == "error"
