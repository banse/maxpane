"""COST / QUOTA blocks (spec §7, §8 COST, §10; contract §C.9) -- pure, clock injected."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from imd_dashd import summarise_claude, summarise_codex
from maxpane_dashboard.analytics import seat_cost as sc

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "tests" / "fixtures" / "seat" / "sessions"
NOW = 1790393051.8  # 2026-09-26T03:24:11.8Z
WORK = "/home/imd-worker/.identitymd/work"


# ---- Task 4.11: attempts, buckets, exclusions ------------------------------------------------


def _row(accepted: str, *, kind: str = "code", model: str = "gpt-6-luna", effort: str = "medium",
         tier: str | None = "economy/standard", turns: int | None = 3, tokens: dict | None = None, wall: int | None = 22400,
         ttft: int | None = 1807, turn1: int | None = 24000, max_turns: bool | None = False, errors: list | None = None,
         side: dict | None = None, reason: str | None = None) -> dict:
    """A ledger row (SEAT_ROW_KEYS["seat_tasks_rows"] subset) as SeatLedger.rows() returns it."""
    return {"acceptedUtc": accepted, "kind": kind, "model": model, "effort": effort, "tierDerived": tier, "turns": turns,
            "tokens": {"input": 17864, "output": 812, "cached": 92928, "cacheWrite": 0} if tokens is None else tokens,
            "wallMs": wall, "ttftMs": ttft, "turn1Context": turn1, "maxTurnsReached": max_turns, "apiErrors": errors or [],
            "sideModelTokens": side, "tokensReason": reason}


def test_percentile_is_nearest_rank():
    assert sc.percentile([], 50) is None and sc.percentile([None, None], 50) is None
    assert sc.percentile([4, 1, 3, 2], 50) == 2 and sc.percentile([4, 1, 3, 2], 90) == 4
    assert sc.percentile([24.8, 86.9, 10.0, None], 50) == 24.8 and sc.percentile([7], 90) == 7


def test_multi_file_attempt_tokens_add_and_turns_do_not(tmp_path):
    # spec §10 fixture pair / fill3 §2 hunt_d: output 73,695 + 1,263 = 74,958 (= API); turns 61 != 58 + 8 -> max, flagged x2
    slug = tmp_path / "projects" / "-home-imd--identitymd-work-7b9c907d-1e3f-4a5b-8c7d-9e1f3a5b7c9d-6d4b2f80-5c3a-4e1d-9f7b-3a5c7e9b1d2f"
    slug.mkdir(parents=True)
    sessions = []
    for name in ("a.jsonl", "b.jsonl"):
        shutil.copyfile(SESSIONS / "transcript_multi_attempt" / name, slug / name)
        sessions.append(summarise_claude.summarise_file(str(slug / name), now=0.0))
    attempt = sc.tokens_for_attempt(sessions)
    assert attempt["tokens"]["output"] == 73695 + 1263 == 74958
    assert attempt["tokens"]["input"] == sessions[0]["tokens"]["input"] + sessions[1]["tokens"]["input"]
    assert attempt["turns"] == 58 and attempt["turns"] != 58 + 8 and attempt["sessionFiles"] == 2
    assert attempt["wallMs"] == 1202379 + 17540 and attempt["turn1Context"] == sessions[0]["turn1Context"]
    assert [e["status"] for e in attempt["apiErrors"]] == [500] and attempt["turnsDefinition"] == "user_lines"
    assert (attempt["model"], attempt["effort"]) == ("claude-fable-5-1", "high")


def test_tokens_for_attempt_edges():
    assert sc.tokens_for_attempt([]) == {"tokens": None, "turns": None, "turnsDefinition": None, "sessionFiles": 0,
                                         "ttftMs": None, "wallMs": None, "turn1Context": None, "maxTurnsReached": None,
                                         "apiErrors": [], "sideModelTokens": None, "model": None, "effort": None}
    one = sc.tokens_for_attempt([{"startedUtc": "2026-09-25T14:02:10.950Z", "tokens": None, "turns": 2,
                                  "sideModel": {"model": "claude-haiku-4-5-20251001", "input": 31415, "output": 273},
                                  "maxTurnsReached": True, "ttftMs": None}])
    assert one["tokens"] is None and one["sideModelTokens"] == {"model": "claude-haiku-4-5-20251001", "input": 31415, "output": 273}
    assert one["maxTurnsReached"] is True and one["sessionFiles"] == 1


def test_doctor_runs_excluded_from_cost(tmp_path):
    # spec §14 mutation proof 14 / §10 exclusions: doctor and manual runs are counted as excluded, never as tasks or tokens
    doctor = tmp_path / "rollout-2026-09-25T11-45-43-0002.jsonl"
    shutil.copyfile(SESSIONS / "rollout_doctor.jsonl", doctor)
    os.utime(doctor, (1790336747.0, 1790336747.0))
    doctor_session = summarise_codex.summarise_file(str(doctor), work_root=WORK, now=0.0)
    assert doctor_session["kind"] == "doctor" and doctor_session["tokens"]["input"] == 11234
    rows = [_row("2026-09-26T02:33:38.000Z"), _row("2026-09-25T20:00:00.000Z"), _row("2026-09-24T09:00:00.000Z")]
    others = [doctor_session, dict(doctor_session, path="p2", startedUtc="2026-09-25T20:10:00.000Z"),
              {"kind": "manual", "startedUtc": "2026-09-22T12:03:00.000Z", "tokens": {"input": 5, "output": 5, "cached": 0, "cacheWrite": 0}},
              {"kind": "unknown", "startedUtc": "2026-09-25T01:00:00.000Z", "tokens": None},
              {"kind": "task", "startedUtc": "2026-09-25T01:00:00.000Z", "tokens": None}]  # task sessions arrive as rows, not here
    cost = sc.summarise(rows, window_days=7, now=NOW, sessions=others)
    assert cost["tasks"] == 3 and cost["excluded"] == {"doctor": 2, "manual": 2}
    assert cost["tokens"] == {"input": 3 * 17864, "output": 3 * 812, "cached": 3 * 92928, "cacheWrite": 0}
    assert cost["turns"] == 9
    rows_with_doctor_row = rows + [dict(_row("2026-09-25T11:45:43.000Z"), kind="doctor")]
    assert sc.summarise(rows_with_doctor_row, window_days=7, now=NOW)["tasks"] == 3


def test_buckets_by_model_effort_tier_in_schema_order():
    # spec §8 COST: buckets per (model, effort, ~tier) with turns p50, wall p50/p90, TTFT p50, turn-1 ctx p50, hits, auth
    rows = [_row("2026-09-26T02:33:38.000Z", turns=3, wall=22400, ttft=1807),
            _row("2026-09-26T01:00:00.000Z", turns=5, wall=86900, ttft=4134, max_turns=True),
            _row("2026-09-25T23:36:05.000Z", turns=0, wall=31101, ttft=None, turn1=None,
                 tokens={"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}, errors=[{"status": 401, "message": "x", "atUtc": None}]),
            _row("2026-09-22T12:00:00.000Z", model="gpt-5.6-luna", tier="economy", turns=4, wall=30000, ttft=2000)]
    cost = sc.summarise(rows, window_days=7, now=NOW)
    first, second = cost["buckets"]
    assert tuple(first) == sc.BUCKET_KEYS and tuple(second) == sc.BUCKET_KEYS
    assert (first["model"], first["effort"], first["tierDerived"], first["tasks"]) == ("gpt-6-luna", "medium", "economy/standard", 3)
    assert (first["turnsP50"], first["wallP50S"], first["wallP90S"], first["ttftP50Ms"]) == (3, 31.1, 86.9, 1807)
    assert (first["turn1ContextP50"], first["maxTurnsHits"], first["authErrors"]) == (24000, 1, 1)
    assert first["tokens"] == {"input": 2 * 17864, "output": 2 * 812, "cached": 2 * 92928, "cacheWrite": 0}
    assert (second["model"], second["tasks"], second["tierDerived"]) == ("gpt-5.6-luna", 1, "economy")


def test_bucket_keys_match_the_status_schema():
    # contract §C.4: every bucket dict has exactly SEAT_ROW_KEYS["seat_cost_buckets"], in that order
    from maxpane_dashboard.data.seat_models import SEAT_ROW_KEYS

    assert sc.BUCKET_KEYS == SEAT_ROW_KEYS["seat_cost_buckets"]


def test_window_and_none_never_zero():
    # spec §7: a failed read is null, never 0 -- rows without token data give tokens None; an empty window is a true 0
    old = _row("2026-09-18T00:00:00.000Z")
    assert sc.summarise([old], window_days=7, now=NOW)["tasks"] == 0
    empty = sc.summarise([], window_days=7, now=NOW)
    assert (empty["tasks"], empty["turns"], empty["tokens"], empty["buckets"], empty["sideModel"]) == (
        0, 0, {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}, [], None)
    expired = [_row("2026-09-26T01:00:00.000Z", turns=None, reason="transcript expired")]
    expired[0]["tokens"] = None
    block = sc.summarise(expired, window_days=7, now=NOW)
    assert block["tasks"] == 1 and block["tokens"] is None and block["turns"] is None
    assert block["depth"] == {"ledgerFromUtc": "2026-09-26T01:00:00.000Z", "sessionsFromUtc": None, "expiredRows": 1,
                              "skipped": {"oversize": None}}
    assert block["windowDays"] == 7


def test_side_model_is_summed_separately():
    # spec §8 COST: Claude's `side model haiku-4-5: 1.7 M in / 22 k out (SDK, not in api usage)` -- never inside tokens
    side = {"model": "claude-haiku-4-5-20251001", "input": 31415, "output": 273}
    rows = [_row("2026-09-25T14:02:11.000Z", model="claude-sonnet-5", effort="low", tier="economy", side=side,
                 tokens={"input": 14, "output": 1459, "cached": 225811, "cacheWrite": 0}),
            _row("2026-09-25T15:00:00.000Z", model="claude-sonnet-5", effort="low", tier="economy", side=dict(side, input=3000, output=49),
                 tokens={"input": 10, "output": 1267, "cached": 149963, "cacheWrite": 0})]
    cost = sc.summarise(rows, window_days=7, now=NOW)
    assert cost["sideModel"] == {"model": "claude-haiku-4-5-20251001", "input": 34415, "output": 322, "tasks": 2}
    assert cost["tokens"] == {"input": 24, "output": 2726, "cached": 375774, "cacheWrite": 0}


def test_module_is_pure():
    import ast

    source = Path(sc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not names & {"textual", "subprocess", "socket", "httpx", "maxpane_dashboard"}


# ---- Task 4.12: series, quota and the no-currency rule --------------------------------------


def test_quota_keys_match_the_status_schema():
    # contract §C.4: the quota block has exactly SEAT_BLOCK_KEYS["seat_quota"], in that order
    from maxpane_dashboard.data.seat_models import SEAT_BLOCK_KEYS

    assert sc.QUOTA_KEYS == SEAT_BLOCK_KEYS["seat_quota"]


def test_series_from_days_skips_unknown_days():
    # spec §8 COST sparkline `output tokens/day · 14 d` from the sqlite days table (oldest first)
    days = [{"dayUtc": f"2026-09-{d:02d}", "tasks": d, "accepted": d - 1, "tokens": {"output": d * 1000}} for d in range(10, 27)]
    days[-2]["tokens"] = None
    series = sc.series_from_days(days, n=14)
    assert series["tasksPerDay"][0] == ["2026-09-13", 13] and series["tasksPerDay"][-1] == ["2026-09-26", 26]
    assert len(series["tasksPerDay"]) == 14 and len(series["outputTokensPerDay"]) == 13
    assert ["2026-09-25", 25000] not in series["outputTokensPerDay"] and series["acceptedPerDay"][-1] == ["2026-09-26", 25]


def test_quota_block_codex_weekly_and_claude_unobservable():
    # spec §10 quota gauge: Codex newest weekly sample with its age; Claude "not observable locally", never fabricated
    sample = {"usedPercent": 45.0, "windowMinutes": 10080, "resetsAtUtc": "2026-09-28T21:50:11Z", "planType": "pro",
              "sampledAtUtc": "2026-09-26T02:33:59Z"}
    assert sc.quota_block(sample, runtime="codex") == {
        "provider": "codex", "window": "weekly", "usedPercent": 45.0, "resetsAtUtc": "2026-09-28T21:50:11Z",
        "sampledAtUtc": "2026-09-26T02:33:59Z", "planType": "pro", "reason": None}
    assert sc.quota_block(sample, runtime="claude") == {
        "provider": "claude", "window": None, "usedPercent": None, "resetsAtUtc": None, "sampledAtUtc": None,
        "planType": None, "reason": "not observable locally"}
    assert sc.quota_block(None, runtime="codex")["reason"] == "no rate_limits sample yet"
    assert sc.quota_block(dict(sample, windowMinutes=300), runtime="codex")["window"] == "5h"
    assert tuple(sc.quota_block(None, runtime="codex")) == sc.QUOTA_KEYS


def test_no_currency_field_in_any_cost_output(tmp_path):
    # spec §10 no-currency rule (unconditional): no `$`, no price/usd/cost field in any summariser or analytics output,
    # even when the inputs carry cost-state.totalCostUSD / costUSD
    slug = tmp_path / "projects" / "-home-imd--identitymd-work-3195fa42-8d6e-4f2a-b1c3-5d7e9f1a3b5c-2a4c6e80-1b3d-4f5a-8c7e-9d1f3b5a7c9e"
    slug.mkdir(parents=True)
    shutil.copyfile(SESSIONS / "transcript_cost_state_haiku.jsonl", slug / "s.jsonl")
    rollouts = tmp_path / "sessions" / "2026" / "09" / "26"
    rollouts.mkdir(parents=True)
    shutil.copyfile(SESSIONS / "rollout_task.jsonl", rollouts / "rollout-2026-09-26T02-33-41-0199f3a2.jsonl")
    outputs = [
        summarise_claude.summarise_dir(str(tmp_path / "projects"), since_mtime=0.0, budget_s=15.0, now=0.0),
        summarise_codex.summarise_dir(str(tmp_path / "sessions"), since_mtime=0.0, work_root=WORK, budget_s=40.0, now=0.0),
        sc.summarise([dict(_row("2026-09-26T02:33:38.000Z"), costUsd=0.07, totalCostUSD=0.114)], window_days=7, now=NOW),
        sc.quota_block({"usedPercent": 45.0, "windowMinutes": 10080}, runtime="codex"),
        sc.series_from_days([{"dayUtc": "2026-09-26", "tasks": 1, "accepted": 1, "tokens": {"output": 812}}]),
    ]
    banned = re.compile(r"usd|price|dollar|currency|cost", re.IGNORECASE)

    def keys(value):
        if isinstance(value, dict):
            for key, inner in value.items():
                yield key
                yield from keys(inner)
        elif isinstance(value, list):
            for inner in value:
                yield from keys(inner)

    for out in outputs:
        assert "$" not in json.dumps(out)
        assert not [k for k in keys(out) if banned.search(str(k))]
    assert "0.114" not in json.dumps(outputs) and "0.0069" not in json.dumps(outputs)
