"""IN FLIGHT -- the swarm v2 snapshot feed on ``panels.RichLogFeed`` (WP5).

Rows are the manager's ``swarm_inflight_rows`` dicts, built by hand here
and bound to the frozen shape ``SURF_ROW_KEYS["swarm_inflight_rows"]`` by
:func:`test_the_hand_rows_are_the_frozen_row_shape`, so a drifted shape
reddens here rather than on screen. Every assertion is against composited
output.

The log's own width is the panel's minus its ``padding: 0 1`` and the
``RichLog``'s one-cell scrollbar (``overflow-y: scroll`` in Textual's own
``RichLog`` CSS, ``scrollbar-size: 1 1`` in the panel's); the tier tests
pin that derivation (:data:`CHROME_COLS`) rather than assume it, so a
chrome change reads as a measurement here instead of a silent tier shift.
"""

from __future__ import annotations

import inspect
import logging

from textual.app import App
from textual.widgets import RichLog

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.rowfit import WIDEN_HINT
from maxpane_dashboard.widgets.surf.swarm_inflight import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    LOG_ID,
    MIN_OBJECTIVE_COLS,
    TIGHT_WIDTH,
    SurfSwarmInFlight,
)
from tests.widgets.surf_compositing import composite_lines


def _row(**over) -> dict:
    row = {
        "job_id": "a1b2c3",
        "template": "skill:oracle-assess",
        "objective": "Assess the oracle feed for the pool4 market",
        "created_ts": 1_758_000_000.0,
        "age_s": 720.0,
        "node_key": "implement_contract",
        "node_role": "implement",
        "node_state": "working",
        "agent_token": 1548,
        "agent_id": 50971,
        "revisions": 0,
        "note": None, "note_kind": None,
    }
    row.update(over)
    return row


ROWS = [
    _row(),
    _row(job_id="d4e5f6", template="skill:launch-site", objective="Publish the roll site",
         age_s=45.0, node_role="review", node_state="waiting", agent_token=7, revisions=1),
]

#: Panel padding (2) + the log's one-cell scrollbar (1).
CHROME_COLS = 3

#: Wide enough for the ``full`` tier with the corpus objective whole.
SIZE = (FULL_WIDTH + 48 + CHROME_COLS, 12)


def test_the_hand_rows_are_the_frozen_row_shape():
    expected = SURF_ROW_KEYS["swarm_inflight_rows"]
    for row in ROWS:
        assert tuple(row) == expected, (tuple(row), expected)


async def _lines(size=SIZE, **kwargs) -> list[str]:
    return await composite_lines(SurfSwarmInFlight, size, **kwargs)


async def _text(size=SIZE, **kwargs) -> str:
    return "\n".join(await _lines(size, **kwargs))


# -- contract ---------------------------------------------------------------


def test_update_data_takes_exactly_the_frozen_keys_in_order():
    expected = SWARM_WIDGET_SIGNATURES["SurfSwarmInFlight"]
    params = inspect.signature(SurfSwarmInFlight.update_data).parameters
    named = tuple(
        name for name, p in params.items()
        if name != "self" and p.kind is not p.VAR_KEYWORD
    )
    assert named == expected
    assert set(named) == set(expected)
    assert any(p.kind is p.VAR_KEYWORD for p in params.values())


async def test_no_args_renders_unavailable():
    text = await _text()
    assert "unavailable" in text, text
    assert "Loading" not in text


async def test_every_key_none_renders_unavailable():
    text = await _text(**{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmInFlight"]})
    assert "unavailable" in text, text


# -- None vs [] (snapshot) ----------------------------------------------------


async def test_none_is_unavailable_and_an_empty_list_is_nothing_executing():
    unread = await _text(swarm_inflight_rows=None, swarm_as_of_hhmm="12:34")
    empty = await _text(swarm_inflight_rows=[], swarm_as_of_hhmm="12:34")
    assert "unavailable" in unread and "nothing executing" not in unread, unread
    assert "nothing executing" in empty and "unavailable" not in empty, empty
    assert EMPTY_LINE.count("nothing executing") == 1


async def test_the_unavailable_line_is_written_once_over_nothing():
    lines = await _lines(swarm_inflight_rows=None)
    body = [l for l in lines if l.strip()]
    assert sum("unavailable" in l for l in body) == 1, lines
    assert len(body) == 2, lines  # title + the one line


async def test_an_uniterable_rows_value_is_unavailable_not_a_crash():
    text = await _text(swarm_inflight_rows=7)
    assert "unavailable" in text, text


# -- rows -------------------------------------------------------------------


async def test_a_row_carries_age_template_seat_role_state_and_objective():
    lines = await _lines(swarm_inflight_rows=ROWS, swarm_as_of_hhmm="12:34")
    first = next(l for l in lines if "oracle-assess" in l)
    assert "12m" in first, first
    assert "skill:oracle-assess" in first, first
    assert "IDMD #1548" in first, first
    assert "implement·working" in first, first
    assert "Assess the oracle feed for the pool4 market" in first, first
    # Column order: age, template, seat, role·state, objective.
    order = [first.index(w) for w in ("12m", "skill:oracle", "IDMD #1548", "implement·working", "Assess")]
    assert order == sorted(order), first


async def test_newest_first_is_the_folds_order_and_is_not_re_sorted():
    lines = await _lines(swarm_inflight_rows=ROWS)
    y_first = next(i for i, l in enumerate(lines) if "oracle-assess" in l)
    y_second = next(i for i, l in enumerate(lines) if "launch-site" in l)
    assert y_first < y_second, lines
    lines = await _lines(swarm_inflight_rows=list(reversed(ROWS)))
    y_first = next(i for i, l in enumerate(lines) if "oracle-assess" in l)
    y_second = next(i for i, l in enumerate(lines) if "launch-site" in l)
    assert y_second < y_first, lines


async def test_the_seat_cell_is_a_dash_when_the_token_is_none():
    text = await _text(swarm_inflight_rows=[_row(agent_token=None)])
    assert "IDMD #" not in text, text
    line = next(l for l in text.splitlines() if "oracle-assess" in l)
    assert "--" in line, line


async def test_a_non_int_token_is_not_dressed_as_a_seat():
    text = await _text(swarm_inflight_rows=[_row(agent_token="1548"), _row(agent_token=True)])
    assert "IDMD #" not in text, text


async def test_a_missing_field_is_a_dash_never_a_crash():
    row = _row()
    del row["node_role"], row["age_s"]
    lines = await _lines(swarm_inflight_rows=[row])
    line = next(l for l in lines if "oracle-assess" in l)
    assert "--·working" in line, line
    assert line.lstrip().startswith("--"), line


async def test_a_second_poll_with_an_empty_set_repaints_to_nothing_executing():
    """Snapshot: every poll is the whole state; ``[]`` after rows wipes them."""

    class _A(App):
        def compose(self):
            yield SurfSwarmInFlight()

    async with _A().run_test(size=SIZE) as pilot:
        panel = pilot.app.query_one(SurfSwarmInFlight)
        panel.update_data(swarm_inflight_rows=ROWS, swarm_as_of_hhmm="12:34")
        await pilot.pause()
        panel.update_data(swarm_inflight_rows=[], swarm_as_of_hhmm="12:35")
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
    assert "oracle-assess" not in text, text
    assert "nothing executing" in text, text


async def test_a_second_poll_with_a_different_set_repaints():
    class _A(App):
        def compose(self):
            yield SurfSwarmInFlight()

    async with _A().run_test(size=SIZE) as pilot:
        panel = pilot.app.query_one(SurfSwarmInFlight)
        panel.update_data(swarm_inflight_rows=ROWS)
        await pilot.pause()
        panel.update_data(swarm_inflight_rows=[_row(job_id="zz", template="skill:new-one")])
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
    assert "oracle-assess" not in text and "launch-site" not in text, text
    assert "skill:new-one" in text, text


async def test_a_non_dict_entry_is_skipped_and_logged_and_the_rest_render(caplog):
    with caplog.at_level(logging.WARNING, logger="maxpane_dashboard.widgets.surf.swarm_inflight"):
        lines = await _lines(swarm_inflight_rows=[ROWS[0], "garbage", None, ROWS[1]])
    assert any("oracle-assess" in l for l in lines)
    assert any("launch-site" in l for l in lines)
    body = [l for l in lines if l.strip() and "IN FLIGHT" not in l]
    assert len(body) == 2, lines
    assert any("SurfSwarmInFlight" in r.getMessage() for r in caplog.records), caplog.records


async def test_a_hostile_objective_renders_literally():
    text = await _text(swarm_inflight_rows=[_row(objective="close [/x] the loop")])
    assert "close [/x] the loop" in text, text
    assert "unavailable" not in text


async def test_a_theme_token_in_an_objective_does_not_raise_and_renders_literally():
    text = await _text(swarm_inflight_rows=[_row(objective="[$success] ship it", template="[$warning]")])
    assert "[$success] ship it" in text, text
    assert "[$warning]" in text, text


async def test_an_objective_is_clipped_never_wrapped():
    long = "word " * 80
    lines = await _lines(swarm_inflight_rows=[_row(objective=long)])
    body = [l for l in lines if l.strip() and "IN FLIGHT" not in l]
    assert len(body) == 1, lines
    assert "…" in body[0] and body[0].rstrip().endswith("--"), body


async def test_a_newline_in_an_objective_is_flattened_to_one_row():
    lines = await _lines(swarm_inflight_rows=[_row(objective="first\nsecond\nthird")])
    body = [l for l in lines if l.strip() and "IN FLIGHT" not in l]
    assert len(body) == 1, lines
    assert "first second third" in body[0], body


# -- title ------------------------------------------------------------------


async def test_the_title_carries_the_marker_only_when_it_is_real():
    marked = await _lines(swarm_inflight_rows=ROWS, swarm_as_of_hhmm="12:34")
    assert "IN FLIGHT · as of 12:34" in marked[0], marked[0]
    for absent in (None, ""):
        bare = await _lines(swarm_inflight_rows=ROWS, swarm_as_of_hhmm=absent)
        assert bare[0].strip() == "IN FLIGHT", bare[0]


async def test_the_network_word_is_accepted_and_never_painted():
    text = await _text(swarm_inflight_rows=ROWS, swarm_network="MAINNET")
    assert "MAINNET" not in text, text


async def test_a_blank_row_separates_the_title_from_the_log():
    lines = await _lines(swarm_inflight_rows=ROWS)
    assert "IN FLIGHT" in lines[0]
    assert lines[1].strip() == "", lines[:3]
    assert "oracle-assess" in lines[2], lines[:3]


# -- tiers --------------------------------------------------------------------


async def _at_log_width(log_width: int, rows=ROWS):
    """Mount so the log is exactly *log_width* cells; pin that it is."""

    class _A(App):
        def compose(self):
            yield SurfSwarmInFlight()

    size = (log_width + CHROME_COLS, 12)
    async with _A().run_test(size=size) as pilot:
        panel = pilot.app.query_one(SurfSwarmInFlight)
        panel.update_data(swarm_inflight_rows=rows, swarm_as_of_hhmm="12:34")
        await pilot.pause()
        log = pilot.app.query_one(f"#{LOG_ID}", RichLog)
        assert log.scrollable_content_region.width == log_width, (
            log.scrollable_content_region.width, log_width,
        )
        strips = pilot.app.screen._compositor.render_strips()
        return ["".join(seg.text for seg in strip).rstrip() for strip in strips]


def test_the_tiers_are_ordered_and_the_tight_floor_keeps_the_objective_readable():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert MIN_OBJECTIVE_COLS == 20


async def test_at_the_full_width_every_cell_shows_and_no_hint_lights():
    lines = await _at_log_width(FULL_WIDTH)
    first = next(l for l in lines if "oracle-assess" in l)
    assert "IDMD #1548" in first and "implement·working" in first, first
    assert WIDEN_HINT not in lines[0], lines[0]
    assert "‹" not in lines[0], lines[0]


async def test_one_below_full_sheds_role_state_and_lights_the_hint():
    lines = await _at_log_width(FULL_WIDTH - 1)
    first = next(l for l in lines if "oracle-assess" in l)
    assert "implement" not in first and "working" not in first, first
    assert "IDMD #1548" in first, first
    assert "Assess the oracle" in first, first
    assert "‹" in lines[0], lines[0]


async def test_one_below_compact_sheds_the_seat_too_and_keeps_the_objective():
    lines = await _at_log_width(COMPACT_WIDTH - 1)
    first = next(l for l in lines if "oracle-assess" in l)
    assert "IDMD" not in first, first
    assert "implement" not in first, first
    assert "Assess the oracle" in first, first
    assert "‹" in lines[0], lines[0]


async def test_at_the_tight_floor_the_objective_still_has_twenty_cells():
    lines = await _at_log_width(TIGHT_WIDTH)
    first = next(l for l in lines if "oracle-assess" in l)
    objective_cell = first.rsplit("  ",1)[0].split("skill:oracle-assess", 1)[1].strip()
    assert len(objective_cell) == MIN_OBJECTIVE_COLS, (objective_cell, first)
    assert objective_cell.endswith("…"), objective_cell


async def test_the_hint_stays_dark_when_nothing_was_shed_because_nothing_rendered():
    lines = await _at_log_width(COMPACT_WIDTH - 1, rows=[])
    assert "‹" not in lines[0], lines[0]
    assert "nothing executing" in "\n".join(lines)

async def test_note_is_last_sanitized_and_clipped_with_an_explicit_marker():
    text=await _text(size=(130,12),swarm_inflight_rows=[_row(objective='objective',note='[/x]dispatch '+('x'*300),note_kind='dispatch')])
    line=next(line for line in text.splitlines() if 'oracle-assess' in line)
    assert 'dispatch' in line and line.index('objective')<line.index('dispatch')
    assert '[/x]' not in line and '…' in line and '‹' in text.splitlines()[0]

async def test_failure_note_is_rendered_and_none_is_a_dash():
    text=await _text(size=(200,12),swarm_inflight_rows=[_row(note='failure details',note_kind='failure')])
    assert 'failure details' in text
    plain=await _text(size=(200,12),swarm_inflight_rows=[_row(note=None,note_kind=None)])
    assert next(line for line in plain.splitlines() if 'oracle-assess' in line).rstrip().endswith('--')

async def test_a_fitting_literal_note_ellipsis_does_not_claim_loss():
    lines=await _lines(size=(180,12),swarm_inflight_rows=[_row(note='waiting…',note_kind='dispatch')])
    assert 'waiting…' in '\n'.join(lines) and '‹' not in lines[0]
