"""``analytics/surf_record_filter``: RECORD's read window, its ``f`` filter and its unknowns.

``docs/surf_record_filter_spec.md``. The window tests moved here with
``record_selected`` / ``record_window`` from ``test_surf_swarm_signals.py``.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from maxpane_dashboard.analytics import surf_record_filter as rf
from maxpane_dashboard.analytics.range_filters import FilterValidationError
from maxpane_dashboard.analytics.surf_record_filter import (
    MATCH,
    NO,
    NOT_READ,
    UNAVAILABLE,
    RecordFilter,
    parse_record_filter,
    record_base_match,
    record_filter_choices,
    record_read_match,
    record_readable,
    record_selected,
    record_view,
    record_window,
)

JOB = "ad7bebb8-fd1a-4268-b831-1c253a85ae4c"
HASH = "ab" * 32
NOW = 1_790_000_000.0


def _row(**over) -> dict:
    row = {
        "job_id": JOB, "submission_hash": HASH, "node_key": "oracle_assess",
        "work_status": "accepted", "job_state": "completed",
        "submitted_ts": NOW - 3_600, "accepted_ts": NOW - 7_200,
        "answer_state": "read", "model": "claude-opus-4-1", "took_s": 330, "output_tokens": 1_500,
        "panel_state": "agreed",
    }
    row.update(over)
    return row


# -- the window (moved from test_surf_swarm_signals.py) ----------------------


@pytest.mark.parametrize("status", ["pending", "failed", "rejected", "cancelled", "blocked", "quarantined", None])
def test_record_state_and_open_window_keep_every_noncompleted_state(status):
    row = {"work_status": status, "job_state": None if status is None else "completed"}
    assert record_window([row], 40, True) == [row]


@pytest.mark.parametrize("status", ["accepted", None])
def test_an_accepted_row_takes_its_job_state(status):
    row = {"work_status": status, "job_state": "completed"}
    assert record_window([row], 40, True) == []
    assert record_window([row], 40, False) == [row]


def test_record_window_filters_before_limiting_and_keeps_source_order():
    completed = [{"work_status": "accepted", "job_state": "completed"} for _ in range(50)]
    failed = [{"work_status": "failed", "id": i} for i in range(90)]
    rows = completed + failed
    assert record_window(rows, 80, True) == failed[:80]
    assert record_window(rows, 80, False) == rows[:80]


@pytest.mark.parametrize(("cap", "expected"), [(-1, 40), (0, 40), (39, 40), (60, 60), (400, 400), (401, 400), (True, 40), ("80", 40)])
def test_record_window_clamps_to_retained_cache(cap, expected):
    rows = [{"work_status": None} for _ in range(500)]
    assert len(record_window(rows, cap, False)) == expected


@pytest.mark.parametrize("rows", [None, "abc", {"work_status": "failed"}])
@pytest.mark.parametrize("open_only", [False, True])
def test_record_window_rejects_non_sequences(rows, open_only):
    assert record_window(rows, 40, open_only) == []


@pytest.mark.parametrize("open_only", [False, True])
@pytest.mark.parametrize("container", [list, tuple])
def test_record_window_skips_malformed_items(open_only, container):
    row = {"work_status": "failed"}
    assert record_window(container([row, "bad", 3, None]), 40, open_only) == [row]


def test_record_selected_accepts_mappings_without_clamping():
    failed = MappingProxyType({"work_status": "failed"})
    completed = {"work_status": "accepted", "job_state": "completed"}
    rows = (completed, "bad", *([failed] * 405))
    assert record_selected(rows, True) == [failed] * 405
    assert record_selected(rows, False) == [completed] + [failed] * 405


# -- the base filter shapes the read window ----------------------------------


def test_the_window_is_base_filtered_before_the_cap():
    """The manager reads only inside ``record_window``: a NODE filter must move
    matching rows from past the cap into it, or they would never be read."""
    review = [_row(node_key="adversarial_review", job_id=f"{i:08x}-0000-4000-8000-000000000000") for i in range(60)]
    oracle = [_row(job_id=f"{i:08x}-1111-4000-8000-000000000000") for i in range(30)]
    spec = RecordFilter(nodes=frozenset({"oracle_assess"}))
    assert record_window(review + oracle, 40, False, spec) == oracle
    assert record_window(review + oracle, 40, False) == review[:40]


def test_read_groups_never_shape_the_window():
    rows = [_row(answer_state="not_read", model=None) for _ in range(50)]
    spec = RecordFilter(models=frozenset({"claude-opus-4-1"}))
    assert len(record_window(rows, 40, False, spec)) == 40


@pytest.mark.parametrize(
    ("spec", "row", "expected"),
    [
        (RecordFilter(nodes=frozenset({"oracle_assess"})), _row(), True),
        (RecordFilter(nodes=frozenset({"build_contract_project"})), _row(), False),
        (RecordFilter(nodes=frozenset({"oracle_assess"})), _row(node_key=["oracle_assess"]), False),
        (RecordFilter(states=frozenset({"failed"})), _row(work_status="failed"), True),
        (RecordFilter(states=frozenset({"completed"})), _row(work_status="failed"), False),
        (RecordFilter(states=frozenset({"completed"})), _row(), True),
        (RecordFilter(since_ts=NOW - 3_600), _row(), True),
        (RecordFilter(since_ts=NOW - 3_599), _row(), False),
        (RecordFilter(since_ts=NOW - 7_200), _row(submitted_ts=None), True),
        (RecordFilter(since_ts=NOW - 7_199), _row(submitted_ts=None), False),
        (RecordFilter(since_ts=0), _row(submitted_ts=None, accepted_ts=None), False),
        (RecordFilter(since_ts=0), _row(submitted_ts=True, accepted_ts=None), False),
        (RecordFilter(since_ts=0), _row(submitted_ts=float("nan")), False),
        (None, _row(node_key=None), True),
    ],
)
def test_base_match(spec, row, expected):
    assert record_base_match(row, spec) is expected


# -- parse ------------------------------------------------------------------


def test_parse_turns_when_into_a_fixed_since():
    spec = parse_record_filter({"when": "7d", "nodes": ["oracle_assess"]}, now_ts=NOW)
    assert spec.when == "7d" and spec.since_ts == NOW - 7 * 86_400
    assert spec.nodes == frozenset({"oracle_assess"})
    assert parse_record_filter({"when": "any"}, now_ts=NOW).since_ts is None


def test_an_empty_filter_is_no_filter():
    spec = parse_record_filter({"took_min": "", "nodes": frozenset(), "panel": "any"}, now_ts=NOW)
    assert spec == RecordFilter() and not spec.active


def test_parse_reads_ranges_with_the_list_rules():
    spec = parse_record_filter({"took_min": "1.5", "took_max": "10", "tok_min": "0", "tok_max": "2000"}, now_ts=NOW)
    assert (spec.took_min, spec.took_max, spec.tok_min, spec.tok_max) == (1.5, 10.0, 0, 2000)
    assert spec.reads_active and not spec.base_active


@pytest.mark.parametrize(
    ("values", "field", "message"),
    [
        ({"took_min": "5", "took_max": "2"}, "took_min", "took_min must not exceed took_max"),
        ({"tok_min": "1.5"}, "tok_min", "tok_min must be a non-negative number"),
        ({"tok_max": "-1"}, "tok_max", "tok_max must be a non-negative number"),
        ({"when": "1y"}, "when", "invalid when"),
        ({"panel": 3}, "panel", "invalid panel"),
        ({"answer": "maybe"}, "answer", "invalid answer"),
        ({"nodes": "oracle_assess"}, "nodes", "invalid nodes"),
        ({"models": [None]}, "models", "invalid models"),
        ({"states": 5}, "states", "invalid states"),
    ],
)
def test_parse_names_the_invalid_field(values, field, message):
    with pytest.raises(FilterValidationError) as raised:
        parse_record_filter(values, now_ts=NOW)
    assert (raised.value.field, str(raised.value)) == (field, message)


@pytest.mark.parametrize("now_ts", [None, float("nan"), True])
def test_when_without_a_usable_clock_is_refused(now_ts):
    with pytest.raises(FilterValidationError):
        parse_record_filter({"when": "24h"}, now_ts=now_ts)


# -- readable ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("job", "key"),
    [
        (JOB, HASH),
        (JOB, HASH.upper()),
        (JOB.upper(), HASH),
        (JOB + "\n", HASH),
        (JOB.replace("-", ""), HASH),
        (JOB, HASH[:-1]),
        (JOB, "0x" + HASH[2:]),
        (JOB, HASH + "\n"),
        (None, HASH),
        (JOB, None),
        (JOB, 12),
        ("{" + JOB + "}", HASH),
    ],
)
def test_readable_agrees_with_the_data_layers_read_rule(job, key):
    """Bound to what the seat cycle schedules (``answer_jobs_due`` /
    ``oracle_rows_due``), which analytics may not import."""
    from maxpane_dashboard.data.surf_swarm import _hex64
    from maxpane_dashboard.data.surf_swarm_client import parse_job_id

    expected = parse_job_id(job) is not None and _hex64(key) is not None
    assert record_readable({"job_id": job, "submission_hash": key}) is expected


# -- the read-dependent groups ----------------------------------------------


@pytest.mark.parametrize(
    ("spec", "over", "expected"),
    [
        # MODEL / TOOK / TOK compare a served submission's facts.
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {}, MATCH),
        (RecordFilter(models=frozenset({"gpt-5-codex"})), {}, NO),
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"answer_state": "no_reply"}, MATCH),
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"model": None}, NO),
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"answer_state": "not_read"}, NOT_READ),
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"answer_state": "unavailable"}, UNAVAILABLE),
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"answer_state": "not_served"}, NO),
        # a row no read can reach is final, whatever its state says
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"answer_state": "not_read", "submission_hash": None}, NO),
        (RecordFilter(models=frozenset({"claude-opus-4-1"})), {"answer_state": "unavailable", "job_id": "x"}, NO),
        # TOOK: the whole minutes the column shows (330 s is ``5m``)
        (RecordFilter(took_min=5), {}, MATCH),
        (RecordFilter(took_max=5), {}, MATCH),
        (RecordFilter(took_min=5.5), {}, NO),
        (RecordFilter(took_max=4.9), {}, NO),
        (RecordFilter(took_min=0), {"took_s": None}, NO),
        (RecordFilter(took_min=0), {"took_s": -3}, NO),
        (RecordFilter(took_min=0), {"took_s": True}, NO),
        (RecordFilter(tok_min=1_500, tok_max=1_500), {}, MATCH),
        (RecordFilter(tok_min=1_501), {}, NO),
        (RecordFilter(tok_max=10), {"output_tokens": 1.0}, NO),
        # ANSWER: the state the answer column shows
        (RecordFilter(answer="replied"), {}, MATCH),
        (RecordFilter(answer="no_reply"), {"answer_state": "no_reply"}, MATCH),
        (RecordFilter(answer="replied"), {"answer_state": "not_served"}, NO),
        (RecordFilter(answer="replied"), {"answer_state": "not_read"}, NOT_READ),
        (RecordFilter(answer="replied"), {"answer_state": "unavailable"}, UNAVAILABLE),
        (RecordFilter(answer="unavailable"), {"answer_state": "unavailable"}, MATCH),
        (RecordFilter(answer="unavailable"), {"answer_state": "unavailable", "submission_hash": "x"}, MATCH),
        (RecordFilter(answer="unavailable"), {"answer_state": "not_read"}, NOT_READ),
        (RecordFilter(answer="replied"), {"answer_state": "not_read", "job_id": None}, NO),
        # PANEL: oracle rows only
        (RecordFilter(panel="agreed"), {}, MATCH),
        (RecordFilter(panel="outvoted"), {}, NO),
        (RecordFilter(panel="no_quorum"), {"panel_state": "no_quorum_in"}, MATCH),
        (RecordFilter(panel="no_quorum"), {"panel_state": "no_quorum_out"}, MATCH),
        (RecordFilter(panel="agreed"), {"panel_state": "not_read"}, NOT_READ),
        (RecordFilter(panel="agreed"), {"panel_state": "unavailable"}, UNAVAILABLE),
        (RecordFilter(panel="unavailable"), {"panel_state": "unavailable"}, MATCH),
        (RecordFilter(panel="agreed"), {"panel_state": "not_read", "submission_hash": None}, NO),
        (RecordFilter(panel="agreed"), {"node_key": "adversarial_review", "panel_state": "not_oracle"}, NO),
        (RecordFilter(panel="off_panel"), {"node_key": "adversarial_review", "panel_state": "not_oracle"}, NO),
        # AND across groups: any ``no`` decides, then not-read beats unavailable
        (RecordFilter(answer="replied", panel="outvoted"), {"answer_state": "not_read"}, NO),
        (RecordFilter(answer="replied", panel="agreed"), {"answer_state": "unavailable", "panel_state": "not_read"}, NOT_READ),
        (RecordFilter(answer="replied", panel="agreed"), {"answer_state": "unavailable"}, UNAVAILABLE),
        (RecordFilter(models=frozenset({"claude-opus-4-1"}), took_min=1, tok_max=2_000, answer="replied", panel="agreed"), {}, MATCH),
        # base-only and no filter: nothing to judge
        (RecordFilter(nodes=frozenset({"x"})), {"answer_state": "not_read"}, MATCH),
        (None, {"answer_state": "not_read"}, MATCH),
    ],
)
def test_read_match(spec, over, expected):
    assert record_read_match(_row(**over), spec) == expected


def test_view_counts_unknowns_and_never_shows_or_drops_them():
    rows = [
        _row(),                                            # match
        _row(answer_state="not_read"),                     # not read yet
        _row(answer_state="unavailable"),                  # unavailable
        _row(model="gpt-5-codex"),                         # no
        _row(node_key="adversarial_review"),               # outside the base filter
    ] + [_row() for _ in range(50)]
    spec = RecordFilter(nodes=frozenset({"oracle_assess"}), models=frozenset({"claude-opus-4-1"}))
    view = record_view(rows, 40, False, spec)
    assert view.rows[0] is rows[0] and len(view.rows) == 37
    assert (view.not_read, view.unavailable, view.older) == (1, 1, 14)


def test_view_without_a_filter_is_the_window():
    rows = [_row(answer_state="not_read") for _ in range(45)]
    view = record_view(rows, 40, False)
    assert list(view.rows) == rows[:40] and (view.older, view.not_read, view.unavailable) == (5, 0, 0)


@pytest.mark.parametrize("rows", [None, "abc", {"a": 1}])
def test_view_of_nothing(rows):
    assert record_view(rows, 40, False, RecordFilter(answer="replied")) == rf.RecordView((), 0, 0, 0)


# -- choices ----------------------------------------------------------------


def test_choices_are_the_seats_own_most_frequent_first():
    """Three oracle rows to two review rows: frequency, not the alphabet, leads."""
    rows = [
        _row(),
        _row(),
        _row(node_key="adversarial_review", work_status="failed", model="gpt-5-codex"),
        _row(node_key="adversarial_review", answer_state="not_read", model="ignored"),
        _row(model=None),
        "bad",
        _row(node_key=None, job_state=None, work_status=None, answer_state="no_reply", model="claude-opus-4-1"),
    ]
    choices = record_filter_choices(rows)
    assert choices["nodes"] == ("oracle_assess", "adversarial_review")
    assert choices["states"] == ("completed", "failed")
    assert choices["models"] == ("claude-opus-4-1", "gpt-5-codex")


def test_choices_keep_what_the_stored_filter_selects():
    spec = RecordFilter(nodes=frozenset({"gone_node"}), models=frozenset({"old-model"}), states=frozenset({"quarantined"}))
    choices = record_filter_choices([_row()], spec)
    assert choices["nodes"] == ("oracle_assess", "gone_node")
    assert choices["states"] == ("completed", "quarantined")
    assert choices["models"] == ("claude-opus-4-1", "old-model")


@pytest.mark.parametrize("rows", [None, "abc", {"a": 1}])
def test_choices_of_nothing(rows):
    assert record_filter_choices(rows) == {"nodes": (), "states": (), "models": ()}


def test_the_vocabularies_match_the_data_layer():
    """PANEL / ANSWER words select states the fold actually writes.

    Both directions: a renamed state would leave its dropdown word matching
    nothing (a false ``0 match``), a new one would be unselectable.
    ``not_read`` is the unknown verdict and ``not_oracle`` PANEL's ``no``.
    """
    from maxpane_dashboard.data.surf_models import (
        SWARM_ANSWER_STATES,
        SWARM_ORACLE_NODE_KEYS,
        SWARM_PANEL_STATES,
    )

    assert rf._ORACLE_NODE_KEYS == SWARM_ORACLE_NODE_KEYS
    answer_states = {state for states in rf.ANSWER_STATES.values() for state in states}
    assert answer_states | {"not_read"} == set(SWARM_ANSWER_STATES)
    panel_states = {state for states in rf.PANEL_STATES.values() for state in states}
    assert panel_states | {"not_oracle", "not_read"} == set(SWARM_PANEL_STATES)
