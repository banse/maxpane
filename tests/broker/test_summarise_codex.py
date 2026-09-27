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


# ---- Task 4.2: per-file API-equal formulas ---------------------------------------------------


def _copy(tmp_path: Path, fixture: str, rel: str = "2026/09/26/rollout-2026-09-26T02-33-41-0199f3a2.jsonl",
          mtime: float = 1790390044.0) -> Path:
    """Place a fixture where codex-cli keeps rollouts (``sessions/YYYY/MM/DD/rollout-*.jsonl``) with a fixed mtime."""
    dst = tmp_path / "sessions" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SESSIONS / fixture, dst)
    os.utime(dst, (mtime, mtime))
    return dst


def _write(tmp_path: Path, lines: list[str], rel: str, mtime: float = 1790390044.0) -> Path:
    dst = tmp_path / "sessions" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(dst, (mtime, mtime))
    return dst


def test_codex_turns_are_agent_messages(tmp_path):
    # spec §10 fixture pair / mutation proof 4: job 15bb693b node 4b9b896f -- 3 AgentMessage items vs 5 token_usage_records
    path = _copy(tmp_path, "rollout_task.jsonl")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert sum(1 for r in records if r["type"] == "token_usage_record") == 5  # the writer's definition would say 5
    session = sc.summarise_file(str(path), work_root=WORK, now=0.0)
    assert session["turns"] == 3 and session["turnsDefinition"] == "agent_messages"


def test_codex_tokens_are_api_equal(tmp_path):
    # spec §10: last total_token_usage 110,792 in / 92,928 cached / 812 out -> API 17,864 / 92,928 / 812
    path = _copy(tmp_path, "rollout_task.jsonl")
    s = sc.summarise_file(str(path), work_root=WORK, now=0.0)
    assert s["tokens"] == {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0}
    assert (s["kind"], s["jobId"], s["nodeId"]) == ("task", JOB, NODE)
    assert (s["model"], s["effort"]) == ("gpt-6-luna", "medium")
    assert (s["ttftMs"], s["wallMs"], s["turn1Context"]) == (1807, 22400, 24000)
    assert (s["startedUtc"], s["endedUtc"]) == ("2026-09-26T02:33:41.905Z", "2026-09-26T02:34:04.310Z")
    assert s["apiErrors"] == [] and s["skippedOversize"] == 0 and s["error"] is None
    assert tuple(s) == sc.SESSION_KEYS and s["slug"] is None and s["runtime"] == "codex"
    assert s["mtime"] == 1790390044.0 and s["bytes"] == path.stat().st_size and s["path"] == str(path)
    assert s["sideModel"] is None and s["maxTurnsReached"] is None and s["maxTurns"] is None


def test_codex_quota_is_the_newest_rate_limits_sample(tmp_path):
    # spec §10 quota gauge / cost §0.3: newest primary{used_percent, window_minutes, resets_at} + plan_type, stamped
    s = sc.summarise_file(str(_copy(tmp_path, "rollout_task.jsonl")), work_root=WORK, now=0.0)
    assert s["quota"] == {"usedPercent": 45.0, "windowMinutes": 10080, "resetsAtUtc": "2026-09-28T21:50:11Z",
                          "planType": "pro", "sampledAtUtc": "2026-09-26T02:33:59Z"}


def test_codex_turn_type_is_case_normalised(tmp_path):
    # fill3 §3: rollout items are CamelCase (AgentMessage); the exec stream says agent_message -- both count
    text = (SESSIONS / "rollout_task.jsonl").read_text(encoding="utf-8").replace('"type":"AgentMessage"', '"type":"agent_message"')
    path = _write(tmp_path, text.splitlines(), "2026/09/26/rollout-2026-09-26T02-33-41-lower.jsonl")
    assert sc.summarise_file(str(path), work_root=WORK, now=0.0)["turns"] == 3


def test_unreadable_and_non_regular_files_return_none(tmp_path):
    target = _copy(tmp_path, "rollout_task.jsonl")
    link = target.parent / "rollout-2026-09-26T02-40-00-link.jsonl"
    link.symlink_to(target)
    assert sc.summarise_file(str(tmp_path / "missing.jsonl"), work_root=WORK, now=0.0) is None
    assert sc.summarise_file(str(link), work_root=WORK, now=0.0) is None  # a task could plant a link to config.json
    assert sc.summarise_file(str(target.parent), work_root=WORK, now=0.0) is None
