"""Dated tier derivation (spec §5.4, §10 tier table, §16 #16; contract §C.9) -- pure, no clock."""

from __future__ import annotations

from datetime import datetime

import pytest

from maxpane_dashboard.analytics import seat_tiers as st


def test_tier_table_is_dated():
    # spec §14 mutation proof 19: gpt-6-luna/medium on #7 after 09-23 19:56 -> economy/standard; the same pair is
    # plain standard on 09-23 10:00 (economy was still gpt-5.6-luna/medium) -- an undated table cannot tell them apart
    assert st.tier_for("codex", "gpt-6-luna", "medium", "2026-09-26T02:33:38.000Z", seat=7) == "economy/standard"
    assert st.tier_for("codex", "gpt-6-luna", "medium", "2026-09-23T19:56:00Z", seat=7) == "economy/standard"
    assert st.tier_for("codex", "gpt-6-luna", "medium", "2026-09-23T10:00:00Z", seat=7) == "standard"
    assert st.tier_for("codex", "gpt-5.6-luna", "medium", "2026-09-23T10:00:00Z", seat=7) == "economy"
    assert st.tier_for("codex", "gpt-5.6-luna", "medium", "2026-09-22T12:00:00Z", seat=7) == "economy/standard"
    assert st.tier_for("codex", "gpt-5.6-luna", "medium", "2026-09-26T02:33:38Z", seat=7) is None
    assert st.tier_for("codex", "gpt-6-luna", "medium", "2026-09-21T18:59:59Z", seat=7) is None  # before the tier era


def test_tier_history_rows_are_dated_sorted_and_named():
    stamps = [datetime.fromisoformat(r.since_utc.replace("Z", "+00:00")) for r in st.TIER_HISTORY]
    assert stamps == sorted(stamps)
    assert {r.since_utc[:16] for r in st.TIER_HISTORY} == {
        "2026-09-21T19:00", "2026-09-22T10:03", "2026-09-22T17:22", "2026-09-22T18:26", "2026-09-23T19:56", "2026-09-23T19:58"}
    assert all(r.tier in st.TIERS and r.model and r.effort and r.note for r in st.TIER_HISTORY)


def test_newest_generic_state_equals_the_bundle_constants():
    # fill2 §2: ECONOMY_MODELS / PREMIUM_MODELS at 5bfa8261 are what a seat without config overrides resolves to today
    for runtime in ("codex", "claude"):
        table = st.resolved_table(runtime, None, seat=None)
        for tier in ("economy", "premium"):
            assert table[tier] == st.BUNDLE_CONSTANTS["5bfa8261"][tier][runtime]


def test_claude_tiers_are_injective_on_420():
    # fill2 §6: on #420 sonnet-5/low = economy, fable-5-1/high = premium, opus-5-5/medium (no flags) = standard
    assert st.tier_for("claude", "claude-sonnet-5", "low", "2026-09-25T10:00:00Z", seat=420) == "economy"
    assert st.tier_for("claude", "claude-fable-5-1", "high", "2026-09-24T09:00:00Z", seat=420) == "premium"
    assert st.tier_for("claude", "claude-opus-5-5", "medium", "2026-09-22T17:30:00Z", seat=420) == "standard"
    assert st.tier_for("claude", "claude-opus-5", "high", "2026-09-22T12:00:00Z", seat=420) == "standard"
    assert st.tier_for("claude", "claude-opus-5", "high", "2026-09-22T17:30:00Z", seat=420) is None
    assert st.tier_for("claude", "claude-fable-5-1", "high", "2026-09-22T10:00:00Z", seat=420) is None  # before 79f4f4d5
    assert st.tier_for("codex", "gpt-6-astra", "max", "2026-09-26T02:33:38Z", seat=7) == "premium"  # isPremiumModel efforts


def test_bare_model_is_standard_and_effort_none_matches_on_model():
    # spec §5.1 / fill2 §6.4: bare `running codex` = standard on the runtime default; the log line carries no effort
    assert st.tier_for("codex", None, None, "2026-09-26T02:33:38Z", seat=7) == "standard"
    assert st.tier_for("codex", "gpt-6-luna", None, "2026-09-26T02:33:38Z", seat=7) == "economy/standard"
    assert st.tier_for("codex", "gpt-6-astra", None, "2026-09-26T02:33:38Z", seat=7) == "premium"
    assert st.tier_for("codex", None, None, "2026-09-20T12:00:00Z", seat=7) is None
    assert st.tier_for("acp", "x", "y", "2026-09-26T02:33:38Z") is None
    assert st.tier_for("codex", "gpt-6-luna", "medium", 1790390018.0, seat=7) == "economy/standard"  # epoch seconds too


def test_projection_beats_history_going_forward():
    # spec §10: the broker's inference projection (owner decision §16 #5) replaces the dated rows going forward
    inference = {"economy": {"codex": {"model": "gpt-6-sol", "effort": "low"}}, "standard": {}, "premium": None}
    at = "2026-09-26T02:33:38Z"
    assert st.tier_for("codex", "gpt-6-sol", "low", at, seat=7, inference=inference) == "economy"
    assert st.tier_for("codex", "gpt-6-luna", "medium", at, seat=7, inference=inference) == "standard"
    assert st.tier_for("codex", "gpt-6-sol", "low", "2026-09-23T10:00:00Z", seat=7, inference=inference) is None


def test_is_premium_follows_is_premium_model():
    # fill2 §2: the approved model and codex xhigh|max|ultra / claude high|xhigh|max; no effort -> model alone
    assert st.is_premium("codex", "gpt-6-astra", "xhigh") and st.is_premium("codex", "gpt-6-astra", "ultra")
    assert not st.is_premium("codex", "gpt-6-astra", "medium") and not st.is_premium("codex", "gpt-6-luna", "xhigh")
    assert st.is_premium("claude", "claude-fable-5-1", "high") and not st.is_premium("claude", "claude-fable-5-1", "medium")
    assert st.is_premium("codex", "gpt-6-astra", None) and not st.is_premium(None, "gpt-6-astra", "xhigh")


def test_tier_label_marks_every_derived_tier():
    from maxpane_dashboard.widgets.fmt import DASH

    assert st.tier_label("economy/standard") == "~economy/standard" and st.tier_label("premium") == "~premium"
    assert st.tier_label(None) == DASH == st.DASH and st.tier_label("") == DASH
    assert (st.TIER_MARK, st.TIER_SHARED) == ("~", "economy/standard")


@pytest.mark.parametrize("module_name", ["seat_tiers"])
def test_module_is_pure(module_name):
    # spec §14 purity walk (2): analytics/seat_* import no textual, subprocess, socket, httpx
    import ast
    from pathlib import Path

    source = (Path(st.__file__).parent / f"{module_name}.py").read_text(encoding="utf-8")
    names = {a.name.split(".")[0] for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)}
    assert not names & {"textual", "subprocess", "socket", "httpx", "maxpane_dashboard"}
