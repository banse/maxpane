"""Tests for ``maxpane_dashboard.analytics.surf_swarm_signals`` (swarm v2 plan, WP3).

Pure rollups: no network, no clock, no fixtures -- every input below is a
hand-typed list whose answer was worked out by hand *before* the function
existed, so a pin here cannot have been derived from the code it checks.
The module is the one the ``s`` and ``a`` bodies' widgets will import, so
its purity is asserted mechanically (an AST walk of its own imports), not
by its docstring.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from maxpane_dashboard.analytics import surf_swarm_signals as sig


# ---------------------------------------------------------------------------
# duration_stats
# ---------------------------------------------------------------------------


def test_duration_stats_pins_median_p90_max_on_a_hand_list():
    # Ten samples 10..100. Median = (50 + 60) / 2 = 55. Nearest-rank p90 on
    # n = 10: sorted[ceil(0.9 * 10) - 1] = sorted[8] = 90 (int(0.9 * 10) = 9
    # would pick 100, the max -- the wrong rank). Max = 100.
    out = sig.duration_stats([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert out == {"dur_median_s": 55, "dur_p90_s": 90, "dur_max_s": 100}


def test_duration_stats_is_order_independent():
    shuffled = [70, 10, 100, 40, 90, 20, 60, 30, 80, 50]
    assert sig.duration_stats(shuffled) == {
        "dur_median_s": 55, "dur_p90_s": 90, "dur_max_s": 100,
    }


def test_duration_stats_p90_is_nearest_rank_not_interpolated():
    # n = 5: ceil(4.5) - 1 = 4 -> sorted[4] = 500, the largest sample.
    out = sig.duration_stats([100, 200, 300, 400, 500])
    assert out["dur_p90_s"] == 500
    assert out["dur_median_s"] == 300


@pytest.mark.parametrize("samples", [[], [5]])
def test_duration_stats_is_all_none_under_two_samples(samples):
    assert sig.duration_stats(samples) == {
        "dur_median_s": None, "dur_p90_s": None, "dur_max_s": None,
    }


def test_duration_stats_keys_are_exactly_the_contract_three():
    assert tuple(sig.duration_stats([1, 2])) == (
        "dur_median_s", "dur_p90_s", "dur_max_s",
    )


# ---------------------------------------------------------------------------
# state_rollup / count_by
# ---------------------------------------------------------------------------


def test_state_rollup_orders_by_count_desc_then_name():
    states = ["executing", "completed", "blocked", "completed", "executing",
              "completed", "quarantined"]
    assert sig.state_rollup(states) == [
        {"state": "completed", "count": 3},
        {"state": "executing", "count": 2},
        {"state": "blocked", "count": 1},
        {"state": "quarantined", "count": 1},
    ]


def test_state_rollup_keeps_a_state_the_vocabulary_has_never_seen():
    rows = sig.state_rollup(["quarantined"])
    assert rows == [{"state": "quarantined", "count": 1}]


def test_state_rollup_skips_non_strings_and_empty_strings():
    assert sig.state_rollup([None, 7, "", "blocked", ["x"]]) == [
        {"state": "blocked", "count": 1},
    ]


def test_state_rollup_of_nothing_is_an_empty_list():
    assert sig.state_rollup([]) == []
    assert sig.state_rollup(iter(())) == []


def test_count_by_drops_none_by_default():
    rows = sig.count_by(["a", None, "b", "a", None], "reason")
    assert rows == [{"reason": "a", "count": 2}, {"reason": "b", "count": 1}]


def test_count_by_keeps_none_only_when_asked():
    rows = sig.count_by(["a", None, "b", "a", None], "reason", keep_none=True)
    assert rows == [
        {"reason": "a", "count": 2},
        {"reason": None, "count": 2},
        {"reason": "b", "count": 1},
    ]


def test_count_by_names_the_field_it_was_given():
    rows = sig.count_by([1, 11155111, 1], "chain_id")
    assert rows == [{"chain_id": 1, "count": 2}, {"chain_id": 11155111, "count": 1}]
    assert all(tuple(r) == ("chain_id", "count") for r in rows)


def test_count_by_orders_desc_count_then_value_across_mixed_types():
    # Ties break on the stringified value so ints and strs can share a list
    # without a TypeError.
    rows = sig.count_by([1, "b", "a", 1, "b"], "k")
    assert rows == [
        {"k": 1, "count": 2}, {"k": "b", "count": 2}, {"k": "a", "count": 1},
    ]


# ---------------------------------------------------------------------------
# skill_summary / launch_summary
# ---------------------------------------------------------------------------


def _skill(role, judge, requires):
    return {"skill_id": "x", "version": 1, "role": role, "kind": "code",
            "tier": None, "judge": judge, "checks": None, "requires": requires}


def test_skill_summary_counts_total_by_role_by_judge_and_requires():
    rows = [
        _skill("review", "verifier-rerun", []),
        _skill("implement", "verifier-rerun", ["defi-native"]),
        _skill("implement", None, ["a", "b"]),
        _skill("reference", None, []),
    ]
    out = sig.skill_summary(rows)
    assert out == {
        "total": 4,
        "by_role": [
            {"role": "implement", "count": 2},
            {"role": "reference", "count": 1},
            {"role": "review", "count": 1},
        ],
        "by_judge": [{"judge": "verifier-rerun", "count": 2}],
        "requires_count": 2,
    }


def test_skill_summary_of_no_rows_is_zeros_not_none():
    assert sig.skill_summary([]) == {
        "total": 0, "by_role": [], "by_judge": [], "requires_count": 0,
    }


def _launch(status, kind, chain):
    return {"launch_number": 1, "kind": kind, "status": status, "chain_id": chain,
            "repo_url": None, "commit": None, "parked_reason": None,
            "artifact_count": 0, "created_ts": None, "updated_ts": None,
            "artifacts": []}


def test_launch_summary_rolls_up_status_kind_and_chain():
    rows = [
        _launch("live", "evm_project", 11155111),
        _launch("live", "evm_project", 1),
        _launch("parked", "evm_project", 11155111),
        _launch("abandoned", "site", None),
    ]
    out = sig.launch_summary(rows)
    assert out["by_status"] == [
        {"status": "live", "count": 2},
        {"status": "abandoned", "count": 1},
        {"status": "parked", "count": 1},
    ]
    assert out["by_kind"] == [
        {"kind": "evm_project", "count": 3}, {"kind": "site", "count": 1},
    ]
    # by_chain is keyed chain_id; a None chain is a failed read, not a chain.
    assert out["by_chain"] == [
        {"chain_id": 11155111, "count": 2}, {"chain_id": 1, "count": 1},
    ]
    assert tuple(out) == ("by_status", "by_kind", "by_chain")


# ---------------------------------------------------------------------------
# completed_within (plan R-A) / seen_since_ts
# ---------------------------------------------------------------------------

_DAY = 86_400


def _seen(*entries):
    return {f"job-{i}": e for i, e in enumerate(entries)}


def test_completed_within_is_none_not_zero_while_accumulating():
    # Oldest created 10 h ago: the window (24 h) has not been observed yet.
    now = 1_000_000.0
    seen = _seen(
        {"created_ts": now - 10 * 3600, "updated_ts": now - 9 * 3600,
         "state": "completed", "template": "t", "nodes": []},
        {"created_ts": now - 2 * 3600, "updated_ts": now - 3600,
         "state": "completed", "template": "t", "nodes": []},
    )
    count, since = sig.completed_within(seen, now, _DAY)
    assert since == now - 10 * 3600
    assert count is None
    assert count != 0  # R-A: never a confident zero during accumulation


def test_completed_within_is_none_none_on_an_empty_seen_map():
    assert sig.completed_within({}, 1_000.0, _DAY) == (None, None)
    assert sig.completed_within(None, 1_000.0, _DAY) == (None, None)


def test_completed_within_counts_once_the_window_has_been_observed():
    now = 1_000_000.0
    seen = _seen(
        # completed 30 h ago -- outside the window, but it makes the map old enough
        {"created_ts": now - 31 * 3600, "updated_ts": now - 30 * 3600,
         "state": "completed", "template": "t", "nodes": []},
        {"created_ts": now - 5 * 3600, "updated_ts": now - 4 * 3600,
         "state": "completed", "template": "t", "nodes": []},
        {"created_ts": now - 3 * 3600, "updated_ts": now - 2 * 3600,
         "state": "completed", "template": "t", "nodes": []},
        {"created_ts": now - 3 * 3600, "updated_ts": now - 2 * 3600,
         "state": "executing", "template": "t", "nodes": []},
    )
    count, since = sig.completed_within(seen, now, _DAY)
    assert since == now - 31 * 3600
    assert count == 2


def test_completed_within_can_report_a_real_zero_after_the_window():
    now = 1_000_000.0
    seen = _seen(
        {"created_ts": now - 40 * 3600, "updated_ts": now - 39 * 3600,
         "state": "completed", "template": "t", "nodes": []},
    )
    assert sig.completed_within(seen, now, _DAY) == (0, now - 40 * 3600)


def test_completed_within_exactly_at_the_window_edge_counts():
    now = 1_000_000.0
    seen = _seen(
        {"created_ts": now - _DAY, "updated_ts": now - _DAY,
         "state": "completed", "template": "t", "nodes": []},
    )
    # now - since == window_s is *not* "< window_s": the window has been seen.
    assert sig.completed_within(seen, now, _DAY) == (1, now - _DAY)


def test_completed_within_skips_entries_that_are_not_mappings():
    now = 1_000_000.0
    seen = {"a": "garbage", "b": None, "c": {"created_ts": now - 2 * _DAY,
                                              "updated_ts": now - 60,
                                              "state": "completed",
                                              "template": None, "nodes": []}}
    assert sig.completed_within(seen, now, _DAY) == (1, now - 2 * _DAY)


def test_seen_since_ts_is_the_oldest_created_ts():
    seen = _seen({"created_ts": 30.0}, {"created_ts": 10.0}, {"created_ts": None},
                 {"created_ts": "not a number"})
    assert sig.seen_since_ts(seen) == 10.0
    assert sig.seen_since_ts({}) is None
    assert sig.seen_since_ts("not a mapping") is None


# ---------------------------------------------------------------------------
# seat_summary retired (AGENT-seats WP5): the seat's counters are the lifetime
# /seats record, folded by data/surf_swarm.seat_summary_from_seat.
# ---------------------------------------------------------------------------


def test_the_window_based_seat_summary_is_gone():
    assert not hasattr(sig, "seat_summary")
    assert "seat_summary" not in sig.__all__


# ---------------------------------------------------------------------------
# purity
# ---------------------------------------------------------------------------


def _imported_names(module) -> list[str]:
    tree = ast.parse(inspect.getsource(module))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.append(base)
            names += [f"{base}.{a.name}" if base else a.name for a in node.names]
    return names


def test_module_is_pure_stdlib_and_clockless():
    """Widgets will import this module (WP5's ``_PURE_ANALYTICS_ALLOWED``).

    Nothing from ``maxpane_dashboard`` (so no transitive path to ``data/``
    and its ``httpx``), no Textual, no ``time`` (the clock is injected as
    ``now_ts``).
    """
    imported = _imported_names(sig)
    assert imported, "the walk found no imports -- it proved nothing"
    for name in imported:
        for banned in ("maxpane_dashboard", "httpx", "aiohttp", "textual", "time"):
            assert not name.startswith(banned), (name, banned)
            assert not name.startswith(f"{banned}."), (name, banned)


@pytest.mark.parametrize('status', ['pending', 'failed', 'rejected', 'cancelled', 'blocked', 'quarantined', None])
def test_record_state_and_open_window_keep_every_noncompleted_state(status):
    row = {'work_status': status, 'job_state': None if status is None else 'completed'}
    assert sig.record_state(row) == status
    assert sig.record_window([row], 40, True) == [row]


@pytest.mark.parametrize('status', ['accepted', None])
def test_record_state_falls_back_to_job_state(status):
    row = {'work_status': status, 'job_state': 'completed'}
    assert sig.record_state(row) == 'completed'
    assert sig.record_window([row], 40, True) == []
    assert sig.record_window([row], 40, False) == [row]


def test_record_window_filters_before_limiting_and_keeps_source_order():
    completed = [{'work_status': 'accepted', 'job_state': 'completed'} for _ in range(50)]
    failed = [{'work_status': 'failed', 'id': i} for i in range(90)]
    rows = completed + failed
    assert sig.record_window(rows, 80, True) == failed[:80]
    assert sig.record_window(rows, 80, False) == rows[:80]
    assert len(rows) == 140


@pytest.mark.parametrize(('cap', 'expected'), [(-1, 40), (0, 40), (39, 40), (60, 60), (400, 400), (401, 400)])
def test_record_window_clamps_to_retained_cache(cap, expected):
    rows = [{'work_status': None} for _ in range(500)]
    assert len(sig.record_window(rows, cap, False)) == expected
