"""Runtime-auth-degraded composite rule (spec §10; contract §C.9) -- pure, clock injected.

The 401 shapes are driven through the real Codex summariser so that the mutation "key the rule on
``== ""`` only" (which lives where ``last_agent_message`` is read) reddens here too (proof 20).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from imd_dashd import summarise_codex
from maxpane_dashboard.analytics import seat_auth as sa

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "tests" / "fixtures" / "seat" / "sessions"
WORK = "/home/imd-worker/.identitymd/work"
T_4145 = 1790379900.0  # 2026-09-25T23:45:00Z, inside the 09-25 pause (paused until 23:53)
T_2355 = 1790380552.0  # 2026-09-25T23:55:52Z, the lingering `1 task running · paused until 23:53` line (fill1 §5)


def _rollout(tmp_path: Path, kind: str) -> dict:
    """rollout_401.jsonl with its token_count/task_complete rewritten to one shape, summarised by the real summariser."""
    lines = (SESSIONS / "rollout_401.jsonl").read_text(encoding="utf-8").splitlines()
    head = [line for line in lines if '"token_count"' not in line and '"task_complete"' not in line]
    usage = {"total_token_usage": {"input_tokens": 24000, "cached_input_tokens": 12288, "output_tokens": 160}}
    info = usage if kind in ("C", "D", "E") else None
    complete = {"type": "task_complete", "turn_id": "turn-1", "duration_ms": 31101, "time_to_first_token_ms": None,
                "last_agent_message": {"A": "", "B": None, "C": None, "D": "[removed]", "E": ""}[kind]}
    if kind in ("B", "C"):
        complete["error"] = {"message": "unexpected status 401 Unauthorized: Incorrect API key provided: sk-svcac********"}
    path = tmp_path / f"rollout-2026-09-25T23-36-05-{kind}.jsonl"
    path.write_text("\n".join(head + [
        json.dumps({"timestamp": "2026-09-25T23:36:05.690Z", "type": "event_msg", "payload": {"type": "token_count", "info": info}}),
        json.dumps({"timestamp": "2026-09-25T23:36:36.314Z", "type": "event_msg", "payload": complete}),
    ]) + "\n", encoding="utf-8")
    return summarise_codex.summarise_file(str(path), work_root=WORK, now=0.0)


def _state(**overrides) -> dict:
    kwargs = {"paused_hint": None, "newest_transcript": None, "newest_rollout": None, "recent_rows": [],
              "credential_mtime_utc": None, "now": T_4145}
    kwargs.update(overrides)
    return sa.auth_state(**kwargs)


@pytest.mark.parametrize("kind", ["A", "B", "C"])
def test_auth_degraded_on_both_401_shapes(tmp_path, kind):
    # spec §14 mutation proof 20: A = cost §4 reading ("" + info null), B = vps §4 reading (null + error.message),
    # C = null + error with a usage report -- all three are the failure signature
    state = _state(newest_rollout=_rollout(tmp_path, kind))
    assert state["degraded"] is True and state["reasons"] == ["codex failure signature"]
    assert state["sinceUtc"] == "2026-09-25T23:36:36Z"


@pytest.mark.parametrize("kind", ["D", "E"])
def test_healthy_or_half_shapes_are_not_the_signature(tmp_path, kind):
    # D = a normal completion; E = an empty final message but a usage report and no error -- neither is an auth failure
    assert _state(newest_rollout=_rollout(tmp_path, kind)) == {"degraded": False, "reasons": [], "sinceUtc": None}


def test_committed_401_fixture_is_degraded(tmp_path):
    # whichever reading the owner-captured rollout_401.jsonl turns out to record, the rule trips on it
    path = tmp_path / "rollout-2026-09-25T23-36-05-0401.jsonl"
    path.write_bytes((SESSIONS / "rollout_401.jsonl").read_bytes())
    state = _state(newest_rollout=summarise_codex.summarise_file(str(path), work_root=WORK, now=0.0))
    assert state["degraded"] is True and "codex failure signature" in state["reasons"]


def test_codex_failure_signature_truth_table():
    f = sa.codex_failure_signature
    assert f(last_agent_message_empty=True, token_count_info_missing=True, task_complete_error_present=False)
    assert f(last_agent_message_empty=True, token_count_info_missing=False, task_complete_error_present=True)
    assert not f(last_agent_message_empty=True, token_count_info_missing=False, task_complete_error_present=False)
    assert not f(last_agent_message_empty=False, token_count_info_missing=True, task_complete_error_present=True)


def test_paused_hint_counts_only_while_the_pause_is_ahead():
    # spec §10 rule 1 + header Review Focus 3: the suffix lingers after `until` (fill1 §5) and must not degrade then
    hint = {"until": "23:53", "failedRuns": 3, "reason": "unexpected status 401 Unauthorized", "seenUtc": "2026-09-25T23:41:22.577Z"}
    active = _state(paused_hint=hint)
    assert active == {"degraded": True, "reasons": ["paused after 3 failed runs"], "sinceUtc": "2026-09-25T23:41:22Z"}
    lingering = dict(hint, seenUtc="2026-09-25T23:55:52.000Z")
    assert _state(paused_hint=lingering, now=T_2355 + 8)["degraded"] is False
    assert _state(paused_hint=hint, now=T_4145 + 3600)["degraded"] is False  # a stale hint (> 330 s) is history
    assert sa.pause_hint_active({"until": "00:10", "seenUtc": "2026-09-25T23:58:00Z"}, now=1790380800.0)  # 00:00 next day: wraps midnight
    assert not sa.pause_hint_active({"until": "25:99"}, now=T_4145) and not sa.pause_hint_active(None, now=T_4145)


def test_claude_api_error_statuses():
    # spec §10 rule 2: newest transcript api_error 401/403 -> degraded; 429 -> "rate limited"; 5xx is not auth
    def transcript(*statuses):
        return {"apiErrors": [{"status": s, "message": "m", "atUtc": "2026-09-24T03:52:10.500Z"} for s in statuses]}

    assert _state(newest_transcript=transcript(401, 401))["reasons"] == ["api_error 401"]
    assert _state(newest_transcript=transcript(403))["reasons"] == ["api_error 403"]
    assert _state(newest_transcript=transcript(429))["reasons"] == ["rate limited"]
    assert _state(newest_transcript=transcript(500))["degraded"] is False
    assert _state(newest_transcript=transcript(401))["sinceUtc"] == "2026-09-24T03:52:10Z"


def test_fast_fail_streak_and_pre_agent_failures():
    # spec §10 rule 4: >= 2 consecutive finished rows < 40 s with zero tokens; the open row neither starts nor breaks it
    zero = {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}
    open_row = {"acceptedUtc": "2026-09-25T23:39:00.000Z", "durationS": None, "submittedUtc": None, "tokens": None}
    fast = [{"acceptedUtc": f"2026-09-25T23:3{m}:05.000Z", "durationS": 31.1, "submittedUtc": "x", "tokens": zero}
            for m in (8, 7, 6)]
    normal = {"acceptedUtc": "2026-09-25T23:00:00.000Z", "durationS": 24.8, "submittedUtc": "x",
              "tokens": {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0}}
    state = _state(recent_rows=[open_row, *fast, normal])
    assert state["reasons"] == ["3 tasks < 40 s with zero tokens"] and state["sinceUtc"] == "2026-09-25T23:36:05Z"
    assert _state(recent_rows=[fast[0], normal, fast[1]])["degraded"] is False
    pre_agent = [{"acceptedUtc": "2026-09-24T05:00:0%d.000Z" % i, "durationS": 0.4, "submittedUtc": "x", "tokens": None,
                  "preAgentFailure": True} for i in (2, 1)]
    assert _state(recent_rows=pre_agent)["reasons"] == ["pre-agent failures"]
    slow_zero = [dict(fast[0], durationS=45.0), fast[1]]
    assert _state(recent_rows=slow_zero)["degraded"] is False


def test_credential_refresh_within_the_hour():
    # spec §10 rule 5: auth.json mtime 23:38:43 (codex rewrote its credentials) -> `token refreshed HH:MM (not read)`
    mtime = "2026-09-25T23:38:43Z"
    hhmm = time.strftime("%H:%M", time.localtime(1790379523.0))
    assert _state(credential_mtime_utc=mtime)["reasons"] == [f"token refreshed {hhmm} (not read)"]
    assert _state(credential_mtime_utc=mtime, now=1790379523.0 + 3601)["degraded"] is False
    assert _state(credential_mtime_utc=None)["degraded"] is False


def test_401_wave_end_to_end(tmp_path):
    # fill1 §6 / cost §4: the 09-25 wave trips every local signal at once; sinceUtc is the earliest trigger
    rollout = _rollout(tmp_path, "B")
    zero = {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}
    rows = [{"acceptedUtc": a, "durationS": 31.1, "submittedUtc": "x", "tokens": zero}
            for a in ("2026-09-25T23:38:14.000Z", "2026-09-25T23:37:24.000Z", "2026-09-25T23:36:03.000Z")]
    hint = {"until": "23:53", "failedRuns": 3, "reason": "401", "seenUtc": "2026-09-25T23:41:22.577Z"}
    state = _state(paused_hint=hint, newest_rollout=rollout, recent_rows=rows, credential_mtime_utc="2026-09-25T23:38:43Z")
    assert state["degraded"] is True and state["reasons"][:3] == [
        "paused after 3 failed runs", "codex failure signature", "3 tasks < 40 s with zero tokens"]
    assert state["reasons"][3].startswith("token refreshed ") and state["sinceUtc"] == "2026-09-25T23:36:03Z"


def test_module_is_pure():
    import ast

    tree = ast.parse(Path(sa.__file__).read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not names & {"textual", "subprocess", "socket", "httpx", "maxpane_dashboard"}
