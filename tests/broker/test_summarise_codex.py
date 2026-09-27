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


# ---- Task 4.3: research, doctor, manual and the 401 failure shapes ---------------------------


def test_clean_run_has_no_failure_flags(tmp_path):
    # spec §10 failure signature inputs: a normal completion reports all three flags False and no apiErrors
    s = sc.summarise_file(str(_copy(tmp_path, "rollout_task.jsonl")), work_root=WORK, now=0.0)
    assert (s["lastAgentMessageEmpty"], s["tokenCountInfoMissing"], s["taskCompleteErrorPresent"]) == (False, False, False)
    assert s["apiErrors"] == []


def test_research_rollout_is_the_work_root(tmp_path):
    # fill6 §2/§6: cwd = work root, no model passed (wrapper gpt-5.6-luna), 69,624 / 45,056 / 2,835, 0.9 s after the accept
    s = sc.summarise_file(str(_copy(tmp_path, "rollout_research_workroot.jsonl")), work_root=WORK, now=0.0)
    assert (s["kind"], s["jobId"], s["nodeId"]) == ("research", None, None)
    assert s["tokens"] == {"input": 24568, "output": 2835, "cached": 45056, "cacheWrite": 0}
    assert (s["model"], s["turns"], s["startedUtc"]) == ("gpt-5.6-luna", 2, "2026-09-25T18:08:55.921Z")


def test_doctor_and_manual_rollouts_are_labelled(tmp_path):
    # spec §10 exclusions: work/doctor-* (11 rollouts), /tmp (7), /home/imd-worker (2) -- labelled, never tasks
    assert sc.summarise_file(str(_copy(tmp_path, "rollout_doctor.jsonl")), work_root=WORK, now=0.0)["kind"] == "doctor"
    text = (SESSIONS / "rollout_task.jsonl").read_text(encoding="utf-8")
    for n, cwd in enumerate(("/tmp", "/home/imd-worker")):
        swapped = text.replace(f"{WORK}/{JOB}/{NODE}", cwd)
        path = _write(tmp_path, swapped.splitlines(), f"2026/09/22/rollout-2026-09-22T12-0{n}-00-manual.jsonl")
        s = sc.summarise_file(str(path), work_root=WORK, now=0.0)
        assert (s["kind"], s["jobId"]) == ("manual", None)


def test_committed_401_rollout_trips_the_failure_fields(tmp_path):
    # spec §10: whichever of the two readings the committed rollout_401.jsonl records, it matches the signature
    s = sc.summarise_file(str(_copy(tmp_path, "rollout_401.jsonl", "2026/09/25/rollout-2026-09-25T23-36-05-0401.jsonl")),
                          work_root=WORK, now=0.0)
    assert s["kind"] == "task" and sc.UUID_RE.fullmatch(s["jobId"] or "") and sc.UUID_RE.fullmatch(s["nodeId"] or "")
    assert s["lastAgentMessageEmpty"] is True
    assert s["tokenCountInfoMissing"] is True or s["taskCompleteErrorPresent"] is True


def _shape(kind: str) -> list[str]:
    """The 401 rollout with its token_count and task_complete lines rewritten to one reading (spec §10)."""
    lines = (SESSIONS / "rollout_401.jsonl").read_text(encoding="utf-8").splitlines()
    head = [line for line in lines if '"token_count"' not in line and '"task_complete"' not in line]
    info = None if kind in ("A", "B") else {"total_token_usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}}
    complete = {"type": "task_complete", "turn_id": "turn-1", "duration_ms": 31101, "time_to_first_token_ms": None,
                "last_agent_message": "" if kind == "A" else None}
    if kind in ("B", "C"):
        complete["error"] = {"message": "unexpected status 401 Unauthorized: Incorrect API key provided: sk-svcac********, "
                                        "url: https://chatgpt.com/backend-api/codex/responses"}
    return head + [
        json.dumps({"timestamp": "2026-09-25T23:36:05.690Z", "type": "event_msg", "payload": {"type": "token_count", "info": info}}),
        json.dumps({"timestamp": "2026-09-25T23:36:36.314Z", "type": "event_msg", "payload": complete}),
    ]


@pytest.mark.parametrize("kind, flags, status", [
    ("A", (True, True, False), None),  # cost §4: last_agent_message "" + token_count.info null, no error event
    ("B", (True, True, True), 401),  # vps §4: last_agent_message null + task_complete.error.message
    ("C", (True, False, True), 401),  # null + error with a usage report present: the error clause alone
])
def test_both_401_shapes_set_the_signature_fields(tmp_path, kind, flags, status):
    path = _write(tmp_path, _shape(kind), f"2026/09/25/rollout-2026-09-25T23-36-05-{kind}.jsonl")
    s = sc.summarise_file(str(path), work_root=WORK, now=0.0)
    assert (s["lastAgentMessageEmpty"], s["tokenCountInfoMissing"], s["taskCompleteErrorPresent"]) == flags
    assert [e["status"] for e in s["apiErrors"]] == ([status] if status else [])
    assert s["tokens"] == {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}


def test_api_error_message_is_raw_for_the_caller_to_redact(tmp_path):
    # contract §C.8: the summariser passes apiErrors[].message on unredacted; the broker redacts it (spec §13)
    from maxpane_dashboard.analytics.seat_redact import SK_RE, redact

    s = sc.summarise_file(str(_write(tmp_path, _shape("B"), "2026/09/25/rollout-2026-09-25T23-36-05-raw.jsonl")),
                          work_root=WORK, now=0.0)
    message = s["apiErrors"][0]["message"]
    assert "sk-svcac********" in message and s["apiErrors"][0]["atUtc"] == "2026-09-25T23:36:36.314Z"
    assert SK_RE.search(redact(message)) is None and "sk-[redacted]" in redact(message)
