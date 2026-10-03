"""COST (spec §8 COST, §10 no-currency rule; contract §C.15): tokens, never dollars.

``test_cost_panel_has_no_currency`` is spec §14 mutation proof 11 and is **unconditional**:
it greps every composited strip of the panel for ``$`` on the healthy payload and on a
hostile one whose third-party strings carry ``$``; no flag exempts it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES, fold_status_document
from maxpane_dashboard.widgets.panels import SignalsPanelBase, SparklinePanel
from maxpane_dashboard.widgets.seat.cost import SeatCost, tokens_word
from maxpane_dashboard.widgets.seat import SeatOutputTokens
from tests.widgets.test_seat_hero import composite_lines

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
SIGNATURE = SEAT_WIDGET_SIGNATURES["SeatCost"]
WIDE = (200, 20)
HALF = (71, 20)


def _payload(**overrides) -> dict:
    flat = fold_status_document(json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8")))
    payload = {key: copy.deepcopy(flat[key]) for key in SIGNATURE}
    payload.update(overrides)
    return payload


def _source(payload: dict, name: str, **fields) -> dict:
    payload["seat_sources"] = copy.deepcopy(payload["seat_sources"])
    payload["seat_sources"][name].update(fields)
    return payload


async def _cost(size=WIDE, **payload):
    return await composite_lines(SeatCost, size, css_path=CSS_PATH, region_only=True, **payload)


def _row(rows, label) -> str:
    """The signal row labelled *label* (``  ● 7 d        tasks …``); rows 0–1 are the title and its blank, and the
    title ``COST · 7 d · as of …`` itself contains `` 7 d ``, so the search starts at row 2."""
    return next(line for line in rows[2:] if f" {label} " in line).strip()


def test_rows_and_the_nested_strip_are_the_contract_s():
    assert SeatCost.ROWS == (("seat-cost-window", "7 d"), ("seat-cost-tokens", "tokens"), ("seat-cost-bucket-1", None), ("seat-cost-bucket-2", None),
                             ("seat-cost-bucket-3", None), ("seat-cost-side", "side model"), ("seat-cost-quota", "quota"), None, ("seat-cost-footer", None))
    assert SeatCost.TITLE == "COST" and SeatCost.LABEL_WIDTH == 10 and SeatCost.DIM_LABEL is True
    assert issubclass(SeatCost, SignalsPanelBase) and issubclass(SeatOutputTokens, SparklinePanel)
    assert SeatOutputTokens.TITLE == "OUTPUT TOKENS / DAY · 14 d" and SeatOutputTokens.LINE_IDS == ("seat-output-tokens-series",)
    assert SeatOutputTokens.LABEL_WIDTH == 8 and SeatOutputTokens.SHOW_ARROW is False and SeatOutputTokens.MIN_POINTS == 2
    assert SeatOutputTokens.EMPTY_TEXT == "no token data yet"
    assert hasattr(SeatOutputTokens, "update_data"), "PANELS independently drives OUTPUT TOKENS"


def test_tokens_word_is_k_and_m_lower_case_never_a_currency():
    assert tokens_word(812) == "812" and tokens_word(96000) == "96 k" and tokens_word(2100000) == "2.1 M" and tokens_word(24000000) == "24.0 M"
    assert tokens_word(None) == "--" and tokens_word(-1) == "--"


async def test_healthy_values_at_a_wide_terminal():
    rows = await _cost(**_payload())
    assert rows[0].strip().startswith("COST · 7 d · as of ")
    assert _row(rows, "7 d").endswith("tasks 118 · excluded 2 doctor 1 manual · turns 341 (api definition)")
    assert _row(rows, "tokens").endswith("in 2.1 M · out 96 k · cached 24.0 M")
    text = "\n".join(rows)
    assert "luna 6/medium ~economy/standard · 118 tasks · p50 3 turns · out 96 k · cached 24.0 M · in 2.1 M · wall 24.8/86.9 s · TTFT 2.5 s · ctx 24 k · max-turn 0 · auth 3" in text
    assert _row(rows, "side model").endswith("n/a (codex)")
    assert "codex weekly 45 % ▮▮▯▯▯ · resets " in _row(rows, "quota") and "· sampled " in _row(rows, "quota")
    assert "sessions from 09-22 · 0 rows expired · 0 oversize skipped · tokens, not currency · definitions: turns = agent messages · input = uncached · output incl. reasoning" in text
    spark = await composite_lines(SeatOutputTokens, (100, 6), css_path=CSS_PATH, region_only=True, **_payload())
    assert "OUTPUT TOKENS / DAY" in "\n".join(spark) and any(c in "\n".join(spark) for c in "▁█"), "the independent sparkline painted blocks"


async def test_claude_wordings_side_model_and_quota():
    rows = await _cost(**_payload(seat_host_runtime="claude",
                                  seat_cost_side_model={"model": "claude-haiku-4-5-20251001", "input": 1742707, "output": 22480, "tasks": 23},
                                  seat_quota={"provider": "claude", "window": None, "usedPercent": None, "resetsAtUtc": None, "sampledAtUtc": None,
                                              "planType": None, "reason": "not observable locally"}))
    assert _row(rows, "side model").endswith("haiku 4.5: 1.7 M in / 22 k out (SDK, not in api usage)")
    assert _row(rows, "quota").endswith("claude quota: not observable locally")


async def test_degraded_sessions_keep_the_ledger_counts_and_say_why():
    rows = await _cost(**_source(_payload(seat_cost_tokens=None, seat_cost_buckets=None), "sessions", ok=False, reason="summariser timeout"))
    assert _row(rows, "tokens").endswith("tokens unavailable (sessions: summariser timeout)")
    assert "tasks 118" in _row(rows, "7 d")


async def test_the_strip_waits_for_two_points():
    rows = await composite_lines(SeatOutputTokens, (100, 6), css_path=CSS_PATH, region_only=True,
                                 seat_cost_series={"outputTokensPerDay": [["2026-09-26", 14000]]})
    assert "no token data yet" in "\n".join(rows)


async def test_cost_panel_has_no_currency():
    # spec §14 mutation proof 11 -- UNCONDITIONAL: no flag, no payload, no string may put a $ on a strip
    for payload in (
        _payload(),
        _payload(seat_host_runtime="claude", seat_cost_buckets=[dict(_payload()["seat_cost_buckets"][0], model="claude-$-4", effort="$igh", tierDerived="$")],
                 seat_cost_side_model={"model": "$haiku", "input": 1, "output": 2, "tasks": 3},
                 seat_quota={"provider": "claude", "window": None, "usedPercent": None, "resetsAtUtc": None, "sampledAtUtc": None, "planType": "$pro", "reason": "$0.07 estimate"},
                 seat_cost_depth={"ledgerFromUtc": "2026-09-22T12:00:00Z", "sessionsFromUtc": "$", "expiredRows": 0, "skipped": {"oversize": 0}}),
        {k: None for k in SIGNATURE},
    ):
        for size in (WIDE, HALF, (40, 20)):
            rows = await _cost(size, **payload)
            assert "$" not in "\n".join(rows), (size, [r for r in rows if "$" in r])


async def test_half_width_shows_short_forms_without_wrapping():
    rows = await _cost(HALF, **_payload())
    assert all(len(line) <= HALF[0] for line in rows) and "‹" not in rows[0]
    assert "tokens, not currency" in "\n".join(rows)


async def test_no_args_renders_without_raising():
    rows = await _cost(**{k: None for k in SIGNATURE})
    assert rows[0].strip() == "COST" and "unavailable" in "\n".join(rows)
