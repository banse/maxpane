"""VERDICTS -- the selected seat's counters as a signals panel (plan A1, WP6a).

Composited assertions only; the summary dict is the manager's
``swarm_seat_summary`` shape. Unwired until WP7, so the per-class contract
checks are imposed here against ``SWARM_WIDGET_SIGNATURES``.
"""

from __future__ import annotations

import inspect

from textual.app import App

from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.swarm_seat_verdicts import (
    NO_FEEDBACK_LINE,
    NO_SEAT_LINE,
    ROW_IDS,
    SurfSwarmSeatVerdicts,
)
from tests.widgets.surf_compositing import composite_lines

LAST = 1_789_000_000.0
FIRST = 1_788_990_000.0
SUMMARY = {
    "nodes": 7, "jobs": 6, "accepted": 7, "rejected": 0, "revisions": 0,
    "mean_score": 1.0, "scored": 17, "working_now": False,
    "first_seen_ts": FIRST, "last_active_ts": LAST,
    "roles": [{"role": "implement", "count": 5}, {"role": "review", "count": 2}],
    "rejection_codes": [],
}
AS_OF = "04:06"
SIZE = (60, 16)


async def _verdicts(**kwargs):
    kwargs.setdefault("swarm_seat_summary", SUMMARY)
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmSeatVerdicts, SIZE, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_frozen_signature_in_order():
    sig = inspect.signature(SurfSwarmSeatVerdicts.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SWARM_WIDGET_SIGNATURES["SurfSwarmSeatVerdicts"]
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatVerdicts, SIZE))
    assert "unavailable" in bare and "Loading" not in bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatVerdicts, SIZE,
        **{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmSeatVerdicts"]},
    ))
    assert none.count("unavailable") >= 7, none


# -- rows -------------------------------------------------------------------------


async def test_real_zeros_render_as_zero_not_unavailable():
    lines = await _verdicts()
    rejected = _row_with(lines, "rejected")
    assert " 0" in rejected and "unavailable" not in rejected and "○" in rejected
    revisions = _row_with(lines, "revisions")
    assert " 0" in revisions and "○" in revisions
    accepted = _row_with(lines, "accepted")
    assert " 7" in accepted and "●" in accepted


async def test_the_score_row_distinguishes_no_feedback_from_a_score():
    scored = _row_with(await _verdicts(), "score")
    assert "1.0" in scored and "17 scored" in scored
    none = _row_with(await _verdicts(swarm_seat_summary=dict(SUMMARY, mean_score=None, scored=0)),
                     "score")
    assert NO_FEEDBACK_LINE in none and "0.0" not in none


async def test_working_and_the_two_stamps():
    lines = await _verdicts()
    assert "no" in _row_with(lines, "working") and "○" in _row_with(lines, "working")
    assert hhmm(FIRST) in _row_with(lines, "first seen")
    assert hhmm(LAST) in _row_with(lines, "last active")
    yes = _row_with(await _verdicts(swarm_seat_summary=dict(SUMMARY, working_now=True)), "working")
    assert "yes" in yes and "●" in yes


async def test_the_role_block_lists_roles_with_counts():
    row = _row_with(await _verdicts(), "by role")
    assert "implement 5" in row and "review 2" in row


async def test_the_rejection_code_block_says_none_for_an_empty_list():
    row = _row_with(await _verdicts(), "rejection codes")
    assert "none" in row
    coded = dict(SUMMARY, rejection_codes=[{"code": "tests_failed", "count": 2},
                                           {"code": "lint", "count": 1}])
    row = _row_with(await _verdicts(swarm_seat_summary=coded), "rejection codes")
    assert "tests_failed 2" in row and "lint 1" in row


async def test_a_hostile_rejection_code_renders_literally():
    coded = dict(SUMMARY, rejection_codes=[{"code": "[/x]", "count": 1}])
    row = _row_with(await _verdicts(swarm_seat_summary=coded), "rejection codes")
    assert "[/x] 1" in row
    themed = dict(SUMMARY, roles=[{"role": "[$success]", "count": 1}])
    row = _row_with(await _verdicts(swarm_seat_summary=themed), "by role")
    assert "[$success] 1" in row


async def test_a_summary_missing_under_a_marker_is_no_seat_not_unavailable():
    """CLAUDE.md: a real negative needs a value distinct from "could not look"."""
    swept = "\n".join(await _verdicts(swarm_seat_summary=None))
    assert NO_SEAT_LINE in swept and "unavailable" not in swept
    unread = "\n".join(await _verdicts(swarm_seat_summary=None, swarm_seat_as_of_hhmm=None))
    assert "unavailable" in unread and NO_SEAT_LINE not in unread


async def test_the_title_carries_the_marker():
    text = "\n".join(await _verdicts())
    assert "VERDICTS" in text and f"as of {AS_OF}" in text
    bare = "\n".join(await _verdicts(swarm_seat_as_of_hhmm=""))
    assert "as of" not in bare


async def test_the_loading_seed_lands_on_the_first_row_only():
    class _A(App):
        def compose(self):
            yield SurfSwarmSeatVerdicts()

    async with _A().run_test(size=SIZE) as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        loading = [y for y, r in enumerate(rows) if "Loading" in r]
        assert len(loading) == 1
        title_y = next(y for y, r in enumerate(rows) if "VERDICTS" in r)
        assert loading[0] == title_y + 2, rows[: loading[0] + 1]
        assert len(ROW_IDS) == 7


async def test_a_malformed_counter_lands_on_its_own_row_only():
    lines = await _verdicts(swarm_seat_summary=dict(SUMMARY, accepted="lots"))
    assert "--" in _row_with(lines, "accepted")
    assert " 0" in _row_with(lines, "rejected")
