"""RECORD -- the selected seat's accepted work, lifetime, newest first (plan WP4).

Composited assertions only. Rows are **folded** from the committed ``/seats``
captures by ``data/surf_swarm.seat_work_rows`` (the manager's own fold), and
every expected value is read off that fold, never hand-typed. The per-class
contract is imposed against ``SWARM_WIDGET_SIGNATURES`` (flipped in WP5, which
also removed the two transitional parameters).
"""

from __future__ import annotations

import inspect

from rich.color import Color
from textual.app import App

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.data.surf_swarm import seat_work_rows
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase
from maxpane_dashboard.widgets.surf.swarm_seat_record import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    JOB_COLS,
    OBJECTIVE_MIN_COLS,
    TIGHT_WIDTH,
    SurfSwarmSeatRecord,
)
from tests.surf_swarm_fixtures import swarm_seat_capture
from tests.widgets.surf_compositing import composite_lines

SIGNATURE = SWARM_WIDGET_SIGNATURES["SurfSwarmSeatRecord"]

ROWS_420 = seat_work_rows(swarm_seat_capture("seat_420"))
ROWS_0 = seat_work_rows(swarm_seat_capture("seat_0"))
NEWEST = ROWS_420[0]
AS_OF = "04:06"
#: Wide enough for every column at ``full`` plus ~45 cells of objective; tall
#: enough for #420's twelve rows, the header, the title and a footer.
SIZE = (130, 20)


def _job(row) -> str:
    return row["job_id"][:JOB_COLS]


def test_the_folded_rows_carry_exactly_the_frozen_shape():
    assert ROWS_420 and ROWS_0
    for row in ROWS_420 + ROWS_0:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_work_rows"]


async def _record(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_work_rows", ROWS_420)
    kwargs.setdefault("swarm_seat_state", "ok")
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmSeatRecord, size, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_signature():
    sig = inspect.signature(SurfSwarmSeatRecord.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SIGNATURE
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_a_splatted_key_outside_the_signature_is_never_painted():
    """The screen splats the whole payload; ``swarm_network`` left RECORD's
    signature in the WP5 flip and must not reach the panel through ``**_kwargs``."""
    plain = await _record()
    noisy = await _record(swarm_network="SEPOLIA")
    assert plain == noisy


# -- the four seat states stay distinct ----------------------------------------------


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatRecord, SIZE))
    assert "unavailable" in bare and "Loading" not in bare and EMPTY_LINE not in bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatRecord, SIZE, **{k: None for k in SIGNATURE},
    ))
    assert "unavailable" in none and EMPTY_LINE not in none


async def test_a_failed_read_is_unavailable_and_never_the_real_empty_sentence():
    """State ``None`` (read failed, no last-good) -- even beside ``[]`` rows."""
    for rows in (None, [], ROWS_420):
        text = "\n".join(await _record(swarm_seat_work_rows=rows, swarm_seat_state=None))
        assert "unavailable" in text, rows
        assert EMPTY_LINE not in text and _job(NEWEST) not in text


async def test_ok_with_empty_rows_is_the_real_empty_sentence():
    text = "\n".join(await _record(swarm_seat_work_rows=[]))
    assert EMPTY_LINE in text and "unavailable" not in text


async def test_ok_with_unread_rows_is_unavailable():
    text = "\n".join(await _record(swarm_seat_work_rows=None))
    assert "unavailable" in text and EMPTY_LINE not in text


async def test_unknown_seat_says_never_paired_not_the_empty_sentence():
    text = "\n".join(await _record(swarm_seat_work_rows=[], swarm_seat_state="unknown_seat"))
    assert NEVER_PAIRED_WORDS in text
    assert EMPTY_LINE not in text and "unavailable" not in text


async def test_pending_says_loading_and_paints_no_row():
    text = "\n".join(await _record(swarm_seat_state="pending"))
    assert "Loading" in text
    assert _job(NEWEST) not in text and "unavailable" not in text and EMPTY_LINE not in text


async def test_a_malformed_state_is_unavailable():
    text = "\n".join(await _record(swarm_seat_state="bogus"))
    assert "unavailable" in text and _job(NEWEST) not in text


# -- rows ---------------------------------------------------------------------------


async def test_the_defect_seat_shows_its_twelve_accepted_jobs_newest_first():
    lines = await _record()
    ys = [next(i for i, l in enumerate(lines) if _job(row) in l) for row in ROWS_420]
    assert len(ys) == len(ROWS_420) == swarm_seat_capture("seat_420")["accepted"]
    assert ys == sorted(ys), "the fold's order (newest first) is kept, never re-sorted"
    assert "older" not in "\n".join(lines), "twelve rows are under the cap"


async def test_a_work_row_renders_every_column():
    lines = await _record()
    row = _row_with(lines, _job(NEWEST))
    assert hhmm(NEWEST["accepted_ts"]) in row
    assert NEWEST["job_id"][JOB_COLS:JOB_COLS + 4] not in row
    assert NEWEST["node_key"] in row and NEWEST["role"] in row and NEWEST["job_state"] in row
    assert NEWEST["objective"][:30] in row
    text = "\n".join(lines)
    assert "RECORD" in text and f"as of {AS_OF}" in text
    header = _row_with(lines, "objective").split()
    assert header == ["when", "job", "node", "role", "state", "objective"]


async def test_the_objective_is_clipped_with_an_ellipsis_and_the_title_says_widen():
    lines = await _record()
    row = _row_with(lines, _job(NEWEST))
    assert NEWEST["objective"] not in row and row.rstrip().endswith("…")
    assert "‹" in "\n".join(lines)
    short = [dict(NEWEST, objective="build a hook")]
    text = "\n".join(await _record(swarm_seat_work_rows=short))
    assert "build a hook" in text and "‹" not in text, "an objective that fits raises no hint"


async def test_the_state_word_is_coloured_on_the_raw_word():
    class _A(App):
        def compose(self):
            yield SurfSwarmSeatRecord()

    rows = [NEWEST, dict(ROWS_420[1], job_state="failed")]
    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmSeatRecord)
        widget.update_data(swarm_seat_work_rows=rows, swarm_seat_state="ok",
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        painted = ["".join(seg.text for seg in strip) for strip in strips]
        y_c = next(i for i, r in enumerate(painted) if _job(rows[0]) in r)
        y_f = next(i for i, r in enumerate(painted) if _job(rows[1]) in r)
        x_c = painted[y_c].index("completed")
        x_f = painted[y_f].index("failed")
        theme = pilot.app.ansi_theme
        done = pilot.app.screen.get_style_at(x_c, y_c).color.get_truecolor(theme)
        failed = pilot.app.screen.get_style_at(x_f, y_f).color.get_truecolor(theme)
        assert done == Color.parse("green").get_truecolor(theme)
        assert failed == Color.parse("red").get_truecolor(theme)


async def test_a_hostile_objective_and_node_key_render_literally_and_never_raise():
    hostile = dict(NEWEST, objective="[/x]PWNED objective", node_key="[/y]NODE",
                   role="[$error]", job_state="[bold]")
    lines = await _record(swarm_seat_work_rows=[hostile], region_only=True)
    text = "\n".join(lines)
    assert "PWNED objective" in text and "NODE" in text
    assert "[" not in text and "]" not in text


async def test_a_malformed_row_field_dashes_and_a_non_dict_row_is_skipped():
    bad = dict(NEWEST, accepted_ts="yesterday", node_key=None, objective=None, job_id=7)
    lines = await _record(swarm_seat_work_rows=[bad, "garbage", ROWS_420[1]])
    row = _row_with(lines, "??:??")
    assert row.count("--") >= 3
    assert _job(ROWS_420[1]) in "\n".join(lines)


async def test_rows_past_the_cap_are_counted_as_older():
    """#0 has 26 accepted jobs; a cap-breaking list is the fold repeated."""
    rows = (ROWS_0 * 2)[: SurfSwarmSeatRecord.ROW_CAP + 5]
    lines = await _record((130, 60), swarm_seat_work_rows=rows)
    painted = [l for l in lines if "completed" in l]
    assert len(painted) == SurfSwarmSeatRecord.ROW_CAP == 40
    assert "+5 older" in "\n".join(lines)
    exact = await _record((130, 60), swarm_seat_work_rows=rows[: SurfSwarmSeatRecord.ROW_CAP])
    assert "older" not in "\n".join(exact)


# -- tiers (provisional; WP6 measures) ------------------------------------------------


def test_the_tier_thresholds_descend():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert OBJECTIVE_MIN_COLS > 0


async def test_one_below_full_sheds_role_and_says_widen():
    gutter = SwarmTableBase.GUTTER_COLS
    row = [dict(NEWEST, objective="fits")]
    full_lines = await _record((FULL_WIDTH + gutter, 12), swarm_seat_work_rows=row)
    compact_lines = await _record((FULL_WIDTH + gutter - 1, 12), swarm_seat_work_rows=row)
    full_header = _row_with(full_lines, "when").split()
    compact_header = _row_with(compact_lines, "when").split()
    assert "role" in full_header and "‹" not in "\n".join(full_lines)
    assert "role" not in compact_header and "‹" in "\n".join(compact_lines)
    assert "objective" in compact_header, "compact keeps the objective"


async def test_one_below_compact_sheds_the_objective():
    gutter = SwarmTableBase.GUTTER_COLS
    lines = await _record((COMPACT_WIDTH + gutter - 1, 12), swarm_seat_work_rows=[NEWEST])
    header = _row_with(lines, "when").split()
    assert "objective" not in header and "‹" in "\n".join(lines)
    assert NEWEST["node_key"] in "\n".join(lines)
