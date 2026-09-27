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


# ---- Task 4.7: per-file formulas: dedup, multi-file, side model, api_error, max turns ---------


def test_claude_tokens_equal_api_after_dedup(tmp_path):
    # spec §10 fixture pair / mutation proof 3: f7b20ce4 (job 48e53e33) dedup 5 / 10 / 1,267 / 149,963 = API; per-line 7 / 1,629
    path = _place(tmp_path, "transcript_f7b20ce4.jsonl", f"{TASK}{F7_JOB}-{F7_NODE}")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assistant = [r for r in lines if r["type"] == "assistant"]
    assert len(assistant) == 7 and sum(r["message"]["usage"]["output_tokens"] for r in assistant) == 1629  # per-line
    s = scl.summarise_file(str(path), now=0.0)
    assert s["turns"] == 5 and s["turnsDefinition"] == "user_lines"
    assert s["tokens"] == {"input": 10, "output": 1267, "cached": 149963, "cacheWrite": 0}
    main = next(r for r in lines if r["type"] == "cost-state")["modelUsage"]["claude-sonnet-5"]  # the cross-check
    assert (main["inputTokens"], main["outputTokens"], main["cacheReadInputTokens"] + main["cacheCreationInputTokens"]) == (10, 1267, 149963)


def test_claude_session_metadata(tmp_path):
    # spec §10 table: model/effort from message.model + top-level effort; turn-1 context; wall = cost-state.totalDuration
    path = _place(tmp_path, "transcript_f7b20ce4.jsonl", f"{TASK}{F7_JOB}-{F7_NODE}")
    s = scl.summarise_file(str(path), now=0.0)
    assert (s["kind"], s["jobId"], s["nodeId"], s["runtime"]) == ("task", F7_JOB, F7_NODE, "claude")
    assert (s["model"], s["effort"], s["turn1Context"]) == ("claude-sonnet-5", "low", 20245)
    assert s["wallMs"] == 16663  # the transcript span is 14,640 ms; cost-state.totalDuration is the tighter bound
    assert s["startedUtc"] == "2026-09-26T01:10:02.100Z" and s["endedUtc"] == "2026-09-26T01:10:16.850Z"
    assert s["cwd"] == f"/home/imd/.identitymd/work/{F7_JOB}/{F7_NODE}" and s["slug"] == f"{TASK}{F7_JOB}-{F7_NODE}"
    assert s["ttftMs"] is None and s["quota"] is None and s["sideModel"] is None and s["apiErrors"] == []
    assert (s["lastAgentMessageEmpty"], s["tokenCountInfoMissing"], s["taskCompleteErrorPresent"]) == (None, None, None)
    assert (s["maxTurnsReached"], s["maxTurns"], s["skippedOversize"], s["error"]) == (False, None, 0, None)
    assert tuple(s) == scl.SESSION_KEYS


def test_multi_attempt_files_summarise_separately(tmp_path):
    # fill3 §2 hunt_d: two files in one node dir -- 58 user lines / 73,695 out (+ an api_error) and 8 / 1,263
    slug = f"{TASK}{HUNT_JOB}-{HUNT_NODE}"
    a = scl.summarise_file(str(_place(tmp_path, "transcript_multi_attempt/a.jsonl", slug, "a.jsonl")), now=0.0)
    b = scl.summarise_file(str(_place(tmp_path, "transcript_multi_attempt/b.jsonl", slug, "b.jsonl")), now=0.0)
    assert (a["turns"], a["tokens"]["output"], b["turns"], b["tokens"]["output"]) == (58, 73695, 8, 1263)
    assert (a["jobId"], a["nodeId"]) == (b["jobId"], b["nodeId"]) == (HUNT_JOB, HUNT_NODE)
    assert [e["status"] for e in a["apiErrors"]] == [500] and b["apiErrors"] == []
    assert (a["model"], a["effort"], a["wallMs"], b["wallMs"]) == ("claude-fable-5-1", "high", 1202379, 17540)


def test_side_model_is_separate_never_added(tmp_path):
    # spec §5.4 / fill3 §2: cost-state.modelUsage["claude-haiku-4-5-*"] is SDK side spend absent from the API usage
    s = scl.summarise_file(str(_place(tmp_path, "transcript_cost_state_haiku.jsonl",
                                      f"{TASK}3195fa42-8d6e-4f2a-b1c3-5d7e9f1a3b5c-2a4c6e80-1b3d-4f5a-8c7e-9d1f3b5a7c9e")), now=0.0)
    assert s["sideModel"] == {"model": "claude-haiku-4-5-20251001", "input": 31415, "output": 273}
    assert s["tokens"] == {"input": 14, "output": 1459, "cached": 225811, "cacheWrite": 0}  # main model only
    assert "USD" not in json.dumps(s) and "0.114" not in json.dumps(s)  # totalCostUSD / costUSD never read (§10)


def test_api_error_401_is_reported_with_status(tmp_path):
    # cost §1: `system` subtype api_error, error.status 401 "OAuth access token has been revoked.", retried
    s = scl.summarise_file(str(_place(tmp_path, "transcript_api_error_401.jsonl",
                                      f"{TASK}1f3e5a7c-9b1d-4e3f-a5c7-e9b1d3f5a7c9-8c6a4e20-7d5b-4c3a-9e1f-2b4d6f8a0c1e")), now=0.0)
    assert [(e["status"], e["message"], e["atUtc"]) for e in s["apiErrors"]] == [
        (401, "401 OAuth access token has been revoked.", "2026-09-24T03:52:10.500Z"),
        (401, "401 OAuth access token has been revoked.", "2026-09-24T03:52:12.600Z")]
    assert s["tokens"] == {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0} and s["turns"] == 1 and s["model"] is None


def test_max_turns_attachment_is_read(tmp_path):
    # cost §0.5: max_turns_reached {52, 53} on the main run, then {7, 8} on the repair pass of the same task
    s = scl.summarise_file(str(_place(tmp_path, "transcript_max_turns.jsonl",
                                      f"{TASK}5b7d9f1a-3c5e-4a7b-9d1f-3e5a7c9b1d3f-ce645231-9a7b-4c5d-8e3f-1a2b3c4d5e6f")), now=0.0)
    assert (s["maxTurnsReached"], s["maxTurns"]) == (True, 52)


def test_synthetic_model_is_an_error_not_a_model(tmp_path):
    # cost §1: a `<synthetic>` assistant message is a client-side error ("API Error: 400 ..."), never the task's model
    slug = f"{TASK}{F7_JOB}-{F7_NODE}"
    path = _place(tmp_path, "transcript_f7b20ce4.jsonl", slug)
    synthetic = {"type": "assistant", "timestamp": "2026-09-22T17:19:00.000Z", "message": {
        "id": "msg_synthetic", "model": "<synthetic>", "content": [
            {"type": "text", "text": "API Error: 400 Claude Code 2.1.278 does not support this model"}],
        "usage": {"input_tokens": 0, "output_tokens": 0}}}
    with open(path, "a", encoding="utf-8") as fh:
        for _ in range(3):
            fh.write(json.dumps(synthetic) + "\n")
    s = scl.summarise_file(str(path), now=0.0)
    assert s["model"] == "claude-sonnet-5" and [e["status"] for e in s["apiErrors"]] == [400, 400, 400]
    assert s["tokens"]["output"] == 1267
