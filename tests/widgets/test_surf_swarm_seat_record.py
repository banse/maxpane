"""RECORD -- the selected seat's nodes, newest first (swarm v2 plan A1, WP6a).

Composited assertions only; the hand rows are bound to
``SURF_ROW_KEYS["swarm_seat_node_rows"]``. Unwired until WP7, so the per-class
contract checks are imposed here against ``SWARM_WIDGET_SIGNATURES``.
"""

from __future__ import annotations

import inspect

from rich.color import Color

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.swarm_roster import SeatTableBase
from maxpane_dashboard.widgets.surf.swarm_seat_record import (
    COMPACT_WIDTH,
    DETAIL_MIN_COLS,
    EMPTY_LINE,
    FULL_WIDTH,
    JOB_COLS,
    TIGHT_WIDTH,
    SurfSwarmSeatRecord,
)
from tests.widgets.surf_compositing import composite_lines

JOB = "ad7bebb8-fd1a-4268-b831-1c253a85ae4c"
AT = 1_789_000_000.0
AT_OLDER = 1_788_990_000.0

NODE = {
    "job_id": JOB, "template": "skill:build-contract-project",
    "node_key": "build_contract_project", "role": "implement", "state": "accepted",
    "attempt": 1, "revisions": 0, "verdict_status": "accepted", "rejection_code": None,
    "failed_checks": [], "detail": "all checks passed", "at_ts": AT,
}
REJECTED = {
    "job_id": "71cd53fa-0000-4000-8000-000000000000", "template": "skill:oracle-assess",
    "node_key": "review_oracle", "role": "review", "state": "failed",
    "attempt": 2, "revisions": 1, "verdict_status": "rejected", "rejection_code": "tests_failed",
    "failed_checks": ["lint", "unit"], "detail": "two checks failed", "at_ts": AT_OLDER,
}
SEEN = {
    "job_id": "9dbfeb65-0000-4000-8000-000000000000", "template": "t",
    "node_key": None, "role": "integrate", "state": "accepted",
    "attempt": None, "revisions": 3, "verdict_status": "accepted", "rejection_code": None,
    "failed_checks": [], "detail": None, "at_ts": AT_OLDER - 60,
}
ROWS = [NODE, REJECTED, SEEN]
AS_OF = "04:06"
SIZE = (140, 12)


def test_the_hand_rows_carry_exactly_the_frozen_shape():
    for row in ROWS:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_node_rows"]


async def _record(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_node_rows", ROWS)
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmSeatRecord, size, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_frozen_signature_in_order():
    sig = inspect.signature(SurfSwarmSeatRecord.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SWARM_WIDGET_SIGNATURES["SurfSwarmSeatRecord"]
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatRecord, SIZE))
    assert "unavailable" in bare and "Loading" not in bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatRecord, SIZE,
        **{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmSeatRecord"]},
    ))
    assert "unavailable" in none


# -- rows -------------------------------------------------------------------------


async def test_a_detail_node_renders_every_column():
    lines = await _record()
    row = _row_with(lines, "build_contract_project")
    assert hhmm(AT) in row and JOB[:JOB_COLS] in row and JOB[JOB_COLS:JOB_COLS + 4] not in row
    assert "implement" in row and "accepted" in row and "all checks passed" in row
    assert " 1 " in row  # try
    assert "RECORD" in "\n".join(lines) and f"as of {AS_OF}" in "\n".join(lines)


async def test_the_folds_order_is_kept():
    lines = await _record()
    y_new = next(i for i, l in enumerate(lines) if "build_contract_project" in l)
    y_old = next(i for i, l in enumerate(lines) if "review_oracle" in l)
    assert y_new < y_old


async def test_a_rejected_node_names_its_code_and_failed_checks():
    row = _row_with(await _record(), "review_oracle")
    assert "rejected · tests_failed" in row
    assert "two checks failed ✗ lint, unit" in row
    assert "failed" in row


async def test_a_seen_slot_node_invents_nothing():
    """No key, no attempt, no detail: three dashes, never a guessed value."""
    row = _row_with(await _record(), "integrate")
    assert row.count("--") >= 3
    assert "?" not in row.replace("??:??", "")
    assert "accepted" in row and " 3 " in row  # rev, from the slot


async def test_the_state_word_is_coloured_on_the_raw_word():
    from textual.app import App

    class _A(App):
        def compose(self):
            yield SurfSwarmSeatRecord()

    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(
            swarm_seat_node_rows=[dict(NODE, state="working"), REJECTED],
            swarm_seat_as_of_hhmm=AS_OF,
        )
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        y_w = next(i for i, r in enumerate(rows) if "working" in r)
        y_f = next(i for i, r in enumerate(rows) if "review_oracle" in r)
        x_w = rows[y_w].index("working")
        x_f = rows[y_f].index("failed")
        # A DataTable cell's ``[green]`` reaches the screen as the app's ANSI
        # theme's green (a hex), so compare truecolor through that theme.
        theme = pilot.app.ansi_theme
        working = pilot.app.screen.get_style_at(x_w, y_w).color.get_truecolor(theme)
        failed = pilot.app.screen.get_style_at(x_f, y_f).color.get_truecolor(theme)
        assert working == Color.parse("green").get_truecolor(theme)
        assert failed == Color.parse("red").get_truecolor(theme)


async def test_none_and_empty_differ():
    empty = "\n".join(await _record(swarm_seat_node_rows=[]))
    assert EMPTY_LINE in empty and "unavailable" not in empty
    unread = "\n".join(await _record(swarm_seat_node_rows=None))
    assert "unavailable" in unread and EMPTY_LINE not in unread


async def test_a_hostile_detail_and_failed_check_render_stripped_and_never_raise():
    hostile = dict(REJECTED, detail="[/x]PWNED detail", failed_checks=["[/x]CHECK", "unit"])
    lines = await _record(swarm_seat_node_rows=[hostile], region_only=True)
    text = "\n".join(lines)
    assert "PWNED detail" in text and "CHECK, unit" in text
    assert "[" not in text and "]" not in text


async def test_a_theme_token_in_a_detail_does_not_raise():
    hostile = dict(NODE, detail="[$success] fine", rejection_code="[$error]")
    text = "\n".join(await _record(swarm_seat_node_rows=[hostile]))
    assert "build_contract_project" in text


async def test_a_long_detail_is_clipped_and_the_title_says_widen():
    detail = "x" * 63
    lines = await _record((120, 12), swarm_seat_node_rows=[dict(NODE, detail=detail)])
    text = "\n".join(lines)
    assert detail not in text and "xxxx…" in text
    assert "‹" in text
    # At SIZE the detail column has room for REJECTED's 30-cell line.
    short = "\n".join(await _record(SIZE))
    assert "two checks failed ✗ lint, unit" in short
    assert "‹" not in short, "a detail that fits raises no hint"


async def test_a_non_dict_row_is_skipped_and_the_rest_render():
    text = "\n".join(await _record(swarm_seat_node_rows=[NODE, "garbage", REJECTED]))
    assert "build_contract_project" in text and "review_oracle" in text


async def test_rows_past_the_cap_are_not_drawn():
    rows = [dict(NODE, node_key=f"node_{i:02d}") for i in range(45)]
    lines = await _record((140, 60), swarm_seat_node_rows=rows)
    painted = [l for l in lines if "node_" in l]
    assert len(painted) == SurfSwarmSeatRecord.ROW_CAP == 40


# -- tiers -------------------------------------------------------------------------


def test_the_tier_thresholds_descend_and_detail_has_a_floor():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert DETAIL_MIN_COLS >= len("all checks passed")


async def test_one_below_full_sheds_try_and_rev_and_says_widen():
    gutter = SeatTableBase.GUTTER_COLS
    # At the full pin the detail column sits at its 17-cell floor, so the row
    # carries a detail that fits it -- a clipped detail is its own hint.
    row = dict(REJECTED, detail="two failed", failed_checks=[])
    full_lines = await _record((FULL_WIDTH + gutter, 12), swarm_seat_node_rows=[row])
    compact_lines = await _record((FULL_WIDTH + gutter - 1, 12), swarm_seat_node_rows=[row])
    full, compact = "\n".join(full_lines), "\n".join(compact_lines)
    # The header line, not the body: ``review_oracle`` contains ``rev``.
    full_header = _row_with(full_lines, "when").split()
    compact_header = _row_with(compact_lines, "when").split()
    assert "try" in full_header and "rev" in full_header and "‹" not in full
    assert "try" not in compact_header and "rev" not in compact_header and "‹" in compact
    assert "two failed" in compact, "compact keeps the detail"


async def test_one_below_compact_sheds_the_detail():
    gutter = SeatTableBase.GUTTER_COLS
    tight = "\n".join(await _record((COMPACT_WIDTH + gutter - 1, 12), swarm_seat_node_rows=[REJECTED]))
    assert "two checks" not in tight and "detail" not in tight
    assert "rejected" in tight and "review_oracle" in tight and "‹" in tight
