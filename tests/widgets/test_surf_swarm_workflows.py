"""WORKFLOWS (``widgets/surf/swarm_workflows.py``), SWARM WORKFLOWS WP4.

Unmounted and unexported until WP5 (spec §6: an exported widget must be
mounted). Every assertion is against composited output; styles are read off
the compositor (``get_style_at``) and links through
``tests/widgets/address_probe``. The captured page is folded through
``data/surf_swarm.workflow_rows`` -- the producer the screen will hand it --
so the rows are the served text, brackets and all.
"""

from __future__ import annotations

import inspect
import re
import time

from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WORKFLOW_LIMIT
from maxpane_dashboard.data.surf_swarm import workflow_rows
from maxpane_dashboard.widgets.address import COPY_GLYPH
from maxpane_dashboard.widgets.surf.swarm_workflows import (
    COMPACT_WIDTH,
    FULL_WIDTH,
    TEXT_MIN_COLS,
    TIGHT_WIDTH,
    SurfSwarmWorkflows,
)
from tests.surf_swarm_fixtures import swarm_capture_v6
from tests.widgets.address_probe import icon_targets, link_targets
from tests.widgets.surf_compositing import composite_lines

ROW_KEYS = SURF_ROW_KEYS["swarm_workflow_rows"]
GUTTER = SurfSwarmWorkflows.GUTTER_COLS

#: Hand-typed until WP5 flips ``SWARM_WIDGET_SIGNATURES`` from CAPABILITY to
#: this widget (spec §2 "Screen"); WP5's contract tests bind the two then.
SIG = ("swarm_workflow_rows", "swarm_scores_as_of_hhmm")

SIZE = (140, 24)
AS_OF = "04:06"
JOB = "86c76df1-724d-4c85-8e59-7379fe6ff012"
JOB2 = "71bacc5a-0000-4000-8000-000000000001"

#: The spec's stylesheet block for the panel (§2 "Screen"), so a tier is
#: measured on the geometry the screen will give it: ``padding: 0 1`` takes
#: two cells off the panel before its own budget is read.
SPEC_CSS = "SurfSwarmWorkflows { width: 1fr; height: 1fr; min-height: 8; padding: 0 1; }"
SPEC_PADDING = 2


def _row(**over) -> dict:
    """One row in the frozen ``swarm_workflow_rows`` shape (capture values)."""
    row = dict(
        workflow_id="wf-1", status="completed", contracts_job_id=JOB, frontend_job_id=JOB2,
        objective="A tip jar on Sepolia. Contract TipJar: anyone can send ETH.",
        failure="", created_ts=1_790_880_570.224, updated_ts=1_790_880_600.0,
        waiting_for_hosting=False,
    )
    row.update(over)
    return row


def _captured() -> list[dict]:
    return workflow_rows(swarm_capture_v6("workflows_limit12")["workflows"])


async def _workflows(size=SIZE, **kwargs) -> str:
    return "\n".join(await composite_lines(SurfSwarmWorkflows, size, **kwargs))


def _data_lines(text: str) -> list[str]:
    """The table's rows: below the header, above the footer, non-blank."""
    lines = text.split("\n")
    header = next(i for i, line in enumerate(lines) if "status" in line and "contracts" in line)
    return [line for line in lines[header + 1:] if line.strip() and "newest" not in line]


class _Probe(App):
    def compose(self):
        yield SurfSwarmWorkflows()


class _Spec(App):
    CSS = SPEC_CSS

    def compose(self):
        yield SurfSwarmWorkflows()


def _strip_rows(app) -> list[str]:
    return ["".join(seg.text for seg in strip) for strip in app.screen._compositor.render_strips()]


# -- the contract ----------------------------------------------------------------------


def test_the_row_cap_agrees_with_the_data_layers_page_limit():
    """The widget restates the producer's limit; this binds the copy."""
    assert SurfSwarmWorkflows.ROW_CAP == SWARM_WORKFLOW_LIMIT == 12


def test_the_hand_row_is_the_frozen_shape():
    assert set(_row()) == set(ROW_KEYS) and len(_row()) == len(ROW_KEYS)


def test_update_data_names_exactly_the_spec_signature_and_takes_kwargs():
    params = list(inspect.signature(SurfSwarmWorkflows.update_data).parameters.values())
    named = [p.name for p in params if p.kind is not p.VAR_KEYWORD and p.name != "self"]
    assert tuple(named) == SIG
    assert any(p.kind is p.VAR_KEYWORD for p in params)


def test_the_columns_are_the_specs_and_the_row_tuples_agree():
    assert SurfSwarmWorkflows.COLUMN_SPECS == (
        ("when", "when", 11),
        ("status", "status", 9),
        ("contracts", "contracts", 9),
        ("frontend", "frontend", 8),
        ("text", "objective / failure", TEXT_MIN_COLS),
    )
    assert TEXT_MIN_COLS == 20
    width = len(SurfSwarmWorkflows.COLUMNS)
    assert len(SurfSwarmWorkflows.EMPTY_ROW) == width == 5
    assert len(SurfSwarmWorkflows.LOADING_ROW) == width
    assert SurfSwarmWorkflows.EMPTY_LINE is None
    assert SurfSwarmWorkflows.TITLE == "WORKFLOWS"
    assert SurfSwarmWorkflows.TABLE_ID == "surf-swarm-workflows-table"
    assert SurfSwarmWorkflows.CURSOR_TYPE == "row"


# -- the captured page -------------------------------------------------------------------


async def test_the_captured_page_renders_twelve_rows_and_the_first_reads_as_by_hand():
    rows = _captured()
    assert len(rows) == 12
    text = await _workflows(swarm_workflow_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert len(lines) == 12, lines
    # Row one of the capture, read off the JSON by hand: blocked, created
    # 1791015415.724, contracts job 86c76df1-…, no frontend job, and a
    # failure whose own words carry square brackets.
    first = lines[0]
    when = time.strftime("%m-%d %H:%M", time.localtime(1_791_015_415))
    assert first.lstrip().startswith(when), first
    assert re.search(r"\bblocked\b", first), first
    assert "86c76df1" in first and "86c76df1-" not in first, first
    assert "—" in first, first
    assert ("protected_invariants: invariants-7848f0989d32: "
            "[FAIL: project constructor failed] setUp()") in first, first
    assert "The launch token" not in first, first
    # A completed row shows its objective's first sentence instead.
    sixth = lines[5]
    assert "A tip jar on Sepolia." in sixth and "Contract TipJar" not in sixth, sixth
    assert "WORKFLOWS · as of 04:06" in text, text
    assert "newest 12 · 8 blocked · 4 completed" in text, text


async def test_the_job_cells_link_their_jobs_on_the_imd_explorer_without_an_icon():
    async with _Probe().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmWorkflows).update_data(
            swarm_workflow_rows=[_row()], swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        urls = {url for *_rest, url in link_targets(pilot.app) if url}
        icons = icon_targets(pilot.app)
    assert urls == {f"https://explorer.imd.fun/jobs/{JOB}", f"https://explorer.imd.fun/jobs/{JOB2}"}, urls
    assert icons == [], icons


# -- the text cell -----------------------------------------------------------------------


async def test_a_failure_renders_literally_and_in_red_while_the_row_is_not_completed():
    """``sanitize_cell`` would delete ``[FAIL: …]`` -- the failure's own words.
    Row 0 is the focused table's cursor row, so the probed row sits below it."""
    failure = "[FAIL: project constructor failed] setUp() (gas: 0)"
    rows = [_row(workflow_id="cursor", objective="Cursor row."),
            _row(status="blocked", failure=failure, objective="Hidden objective.")]
    async with _Probe().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmWorkflows).update_data(
            swarm_workflow_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        lines = _strip_rows(pilot.app)
        y = next(i for i, line in enumerate(lines) if "[FAIL:" in line)
        style = pilot.app.screen.get_style_at(lines[y].index("[FAIL:"), y)
        red = pilot.app.ansi_theme.ansi_colors[1]
        assert style.color is not None and style.color.get_truecolor() == red, style
    assert failure in lines[y], lines[y]
    assert "Hidden objective" not in "\n".join(lines)


async def test_a_completed_row_shows_its_objective_even_with_a_failure_string():
    rows = [_row(status="completed", failure="stale failure text", objective="Shipped it. More.")]
    lines = _data_lines(await _workflows(swarm_workflow_rows=rows))
    assert "Shipped it." in lines[0] and "stale failure" not in lines[0], lines


async def test_a_blank_failure_falls_back_to_the_objective():
    for failure in ("", "   \n ", None):
        rows = [_row(status="blocked", failure=failure, objective="Build the thing. Then more.")]
        lines = _data_lines(await _workflows(swarm_workflow_rows=rows))
        assert "Build the thing." in lines[0] and "Then more" not in lines[0], (failure, lines)


async def test_a_markup_shaped_objective_renders_literally():
    rows = [_row(objective="Ship [/x] and [b]bold[/b] [$error] now. Second sentence.")]
    lines = _data_lines(await _workflows(swarm_workflow_rows=rows))
    assert "Ship [/x] and [b]bold[/b] [$error] now." in lines[0], lines
    assert "Second sentence" not in lines[0], lines


async def test_the_first_sentence_is_cut_at_a_dot_before_whitespace_or_the_end():
    cases = {
        "One. Two.": "One.",
        "Ends at the end.": "Ends at the end.",
        "No full stop at all": "No full stop at all",
        "Spread over\nthree\tlines. Rest": "Spread over three lines.",
        # A dot inside a token is not an ending: a URL, a version number.
        "Host it at https://pv.pad/app.js for v1.2 users. Rest": "Host it at https://pv.pad/app.js for v1.2 users.",
        # Documented limit: an abbreviation's dot is followed by a space, so
        # the rule (spec §2, "a `.` followed by whitespace") cuts there.
        "Use a vault, e.g. a 7-day lock. Rest": "Use a vault, e.g.",
    }
    for objective, shown in cases.items():
        lines = _data_lines(await _workflows(swarm_workflow_rows=[_row(objective=objective)]))
        cell = lines[0].split(JOB2[:8], 1)[1].strip()
        assert cell == shown, (objective, cell)


async def test_a_clipped_text_shows_its_ellipsis_and_does_not_light_widen():
    """Only a shed column lights ``‹ widen`` (IN FLIGHT's objective precedent)."""
    rows = [_row(status="blocked", failure="x" * 300)]
    text = await _workflows((FULL_WIDTH + GUTTER, 20), swarm_workflow_rows=rows,
                            swarm_scores_as_of_hhmm=AS_OF)
    line = _data_lines(text)[0]
    assert line.rstrip().endswith("x…"), line
    assert "‹" not in text, text


# -- None, [], all-None, the cap -------------------------------------------------------------


async def test_none_is_a_yellow_unavailable_with_no_footer():
    """The word is the table's only row, which is the cursor row; the
    cursor's own colour is Textual's, so it is switched off to read the cell's."""
    for kwargs in ({}, {"swarm_workflow_rows": None, "swarm_scores_as_of_hhmm": None}):
        async with _Probe().run_test(size=SIZE) as pilot:
            pilot.app.query_one(SurfSwarmWorkflows).update_data(**kwargs)
            pilot.app.query_one(DataTable).show_cursor = False
            await pilot.pause()
            lines = _strip_rows(pilot.app)
            text = "\n".join(lines)
            assert "unavailable" in text and "no workflows" not in text, text
            assert "newest" not in text and "No data" not in text, text
            y = next(i for i, line in enumerate(lines) if "unavailable" in line)
            style = pilot.app.screen.get_style_at(lines[y].index("unavailable"), y)
            assert style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[3], style


async def test_an_empty_list_says_no_workflows_with_no_footer():
    text = await _workflows(swarm_workflow_rows=[], swarm_scores_as_of_hhmm=AS_OF)
    assert "no workflows" in text and "unavailable" not in text, text
    assert "newest" not in text and "No data" not in text, text


async def test_an_all_none_row_renders_dashes_without_raising():
    row = {key: None for key in ROW_KEYS}
    lines = _data_lines(await _workflows(swarm_workflow_rows=[row], swarm_scores_as_of_hhmm=AS_OF))
    assert len(lines) == 1, lines
    cells = lines[0].split()
    assert cells == ["--", "--", "--", "—", "--"], cells


async def test_the_thirteenth_row_is_not_shown():
    rows = [_row(objective=f"Workflow number {n:02d}.") for n in range(13, 0, -1)]
    text = await _workflows((SIZE[0], 30), swarm_workflow_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    lines = _data_lines(text)
    assert len(lines) == 12, lines
    assert "Workflow number 13." in lines[0] and "Workflow number 02." in lines[-1], lines
    assert "Workflow number 01." not in text, text
    assert "newest 12 · 12 completed" in text, text


# -- status colours ----------------------------------------------------------------------------


async def test_status_is_escaped_and_coloured_on_the_raw_word():
    rows = [_row(workflow_id="cursor", status="completed", objective="Cursor row."),
            _row(status="completed", objective="Green row."),
            _row(status="blocked", failure="", objective="Red row."),
            _row(status="cancelled", objective="Dim row."),
            _row(status="executing", objective="Yellow row."),
            _row(status="[/x]completed", objective="Hostile row.")]
    async with _Probe().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmWorkflows).update_data(
            swarm_workflow_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        lines = _strip_rows(pilot.app)
        theme = pilot.app.ansi_theme.ansi_colors

        def colour(marker: str, word: str):
            y = next(i for i, line in enumerate(lines) if marker in line)
            return pilot.app.screen.get_style_at(lines[y].index(word), y).color, y

        green, _ = colour("Green row.", "completed")
        red, _ = colour("Red row.", "blocked")
        yellow, _ = colour("Yellow row.", "executing")
        hostile, _ = colour("Hostile row.", "completed")
        dim, y_dim = colour("Dim row.", "cancelled")
        plain = pilot.app.screen.get_style_at(lines[y_dim].index("Dim row."), y_dim).color
        assert green.get_truecolor() == theme[2], green
        assert red.get_truecolor() == theme[1], red
        assert yellow.get_truecolor() == theme[3], yellow
        # The colour is looked up on the raw word: ``[/x]completed`` is not
        # ``completed``, so it is an unknown status (yellow), shown stripped.
        assert hostile.get_truecolor() == theme[3], hostile
        assert dim != plain and dim.get_truecolor() not in (theme[1], theme[2], theme[3]), (dim, plain)
    assert "[/x]" not in "\n".join(lines)


# -- footer ---------------------------------------------------------------------------------------


async def test_the_footer_counts_the_rows_it_was_handed_by_count_then_word():
    statuses = ["cancelled", "completed", "blocked", "completed", "executing",
                "blocked", "cancelled", "completed"]
    rows = [_row(status=s, failure="") for s in statuses]
    text = await _workflows(swarm_workflow_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
    # 3 completed, then the 2/2 tie broken by word (blocked < cancelled), then 1.
    assert "newest 8 · 3 completed · 2 blocked · 2 cancelled · 1 executing" in text, text


# -- tiers ------------------------------------------------------------------------------------


def test_the_tier_widths_are_the_specs_columns_plus_the_tables_padding():
    """``table_cols``: each column's width plus two cells of ``DataTable``
    padding, the text column at its 20-cell floor."""
    assert FULL_WIDTH == (11 + 9 + 9 + 8 + 20) + 5 * 2 == 67
    assert COMPACT_WIDTH == (11 + 9 + 9 + 20) + 4 * 2 == 57
    assert TIGHT_WIDTH == (9 + 9 + 20) + 3 * 2 == 44
    assert SurfSwarmWorkflows.LADDER.steps == (
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH))


async def _measure(outer: int):
    """``(columns, max_scroll_x, text)`` at *outer* cells under the spec's CSS."""
    async with _Spec().run_test(size=(outer, 20)) as pilot:
        widget = pilot.app.query_one(SurfSwarmWorkflows)
        widget.update_data(swarm_workflow_rows=_captured(), swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        table = pilot.app.query_one(DataTable)
        keys = [column.label.plain for column in table.columns.values()]
        return keys, table.max_scroll_x, "\n".join(_strip_rows(pilot.app))


async def test_each_tier_shows_its_columns_whole_at_its_own_threshold_under_the_spec_css():
    """The ladder measured in a harness with the spec's stylesheet block: at
    each threshold the table needs no horizontal scroll, every header it
    keeps is whole, and one cell less drops to the next tier. WP5 certifies
    the pin in situ."""
    full = FULL_WIDTH + GUTTER + SPEC_PADDING
    compact = COMPACT_WIDTH + GUTTER + SPEC_PADDING
    tight = TIGHT_WIDTH + GUTTER + SPEC_PADDING

    keys, scroll, text = await _measure(full)
    assert keys == ["when", "status", "contracts", "frontend", "objective / failure"], keys
    assert scroll == 0
    assert re.search(r"when\s+status\s+contracts\s+frontend\s+objective / failure", text), text
    assert "‹" not in text, text

    keys, scroll, text = await _measure(full - 1)
    assert keys == ["when", "status", "contracts", "objective / failure"], keys
    assert scroll == 0 and "‹" in text, text

    keys, scroll, text = await _measure(compact)
    assert keys == ["when", "status", "contracts", "objective / failure"], keys
    assert scroll == 0
    assert re.search(r"when\s+status\s+contracts\s+objective / failure", text), text

    keys, scroll, text = await _measure(compact - 1)
    assert keys == ["status", "contracts", "objective / failure"], keys
    assert scroll == 0 and "‹" in text, text

    keys, scroll, text = await _measure(tight)
    assert keys == ["status", "contracts", "objective / failure"], keys
    assert scroll == 0
    assert re.search(r"status\s+contracts\s+objective / failure", text), text
    assert "newest 12" in text


async def test_the_text_column_takes_every_spare_cell():
    failure = "y" * 60
    rows = [_row(status="blocked", failure=failure)]
    narrow = await _workflows((FULL_WIDTH + GUTTER, 20), swarm_workflow_rows=rows)
    wide = await _workflows((FULL_WIDTH + GUTTER + 40, 20), swarm_workflow_rows=rows)
    assert failure not in narrow and "y…" in narrow, narrow
    assert failure in wide and "…" not in _data_lines(wide)[0], wide


# -- title ----------------------------------------------------------------------------------


async def test_the_title_carries_the_marker_only_when_it_is_real():
    text = await _workflows(swarm_workflow_rows=[_row()], swarm_scores_as_of_hhmm=AS_OF)
    assert "WORKFLOWS · as of 04:06" in text, text
    for as_of in (None, ""):
        text = await _workflows(swarm_workflow_rows=[_row()], swarm_scores_as_of_hhmm=as_of)
        assert "as of" not in text and "WORKFLOWS" in text, text


# -- an address inside the text: its copy icon, and no link (review I1) -------------------------

#: The 100-row capture's one failure that names a whole address (row 45).
C0DE = "0x000000000000000000000000000000000000c0de"
#: The same capture's abbreviated form (row 4): not an address, so no icon.
ABBREVIATED = "0x5167d0...3281"
#: The fixed columns at the full tier: ``table_cols([11, 9, 9, 8])`` + the
#: text column's own padding + the panel's gutter, so a terminal this much
#: wider than *n* gives the text column exactly *n* cells (bare harness).
_FIXED_COLS = (11 + 9 + 9 + 8) + 4 * 2 + 2 + GUTTER


def _failure_row(needle: str) -> dict:
    rows = workflow_rows(swarm_capture_v6("workflows_100")["workflows"])
    return next(row for row in rows if needle in (row["failure"] or ""))


async def _address_probe(rows, size):
    """``(screen rows, icons, links)`` read off the compositor."""
    async with _Probe().run_test(size=size) as pilot:
        pilot.app.query_one(SurfSwarmWorkflows).update_data(
            swarm_workflow_rows=rows, swarm_scores_as_of_hhmm=AS_OF)
        await pilot.pause()
        return _strip_rows(pilot.app), icon_targets(pilot.app), link_targets(pilot.app)


async def test_a_whole_address_in_a_failure_gets_its_copy_icon_and_no_link():
    """CLAUDE.md: every displayed 0x address carries a copy icon, and an
    unknown chain gets no link, never a guessed one -- a workflow carries no
    chain id, so ``link_prose`` runs with ``explorer=None``."""
    failure = f"names {C0DE} as the hook"
    rows = [_row(status="blocked", failure=failure, frontend_job_id=None)]
    lines, icons, links = await _address_probe(rows, SIZE)
    y = next(i for i, line in enumerate(lines) if C0DE in line)
    assert f"names {C0DE} {COPY_GLYPH} as the hook" in lines[y], lines[y]
    assert [(iy, copied) for _x, iy, copied in icons] == [(y, C0DE)], icons
    # The address's cells and its icon carry no link; the only links left on
    # screen are the contracts job's, on the IMD explorer.
    start = lines[y].index(C0DE)
    on_address = [t for t in links if t[1] == y and start <= t[0] <= start + len(C0DE) + 1]
    assert on_address == [], on_address
    assert {url for *_r, url in links if url} == {f"https://explorer.imd.fun/jobs/{JOB}"}, links


async def test_an_address_and_icon_that_cannot_fit_are_dropped_whole_before_the_ellipsis():
    """The unit is never bisected: no ``0x`` fragment, no orphaned icon, and
    still no ``‹ widen`` for a clipped text."""
    failure = f"names {C0DE} as the hook"
    rows = [_row(status="blocked", failure=failure, frontend_job_id=None)]
    lines, icons, _links = await _address_probe(rows, (FULL_WIDTH + GUTTER, 20))
    text = "\n".join(lines)
    row = next(line for line in lines if "names" in line)
    assert row.rstrip().endswith("names…"), row
    assert "0x" not in text and COPY_GLYPH not in text and icons == [], text
    assert "‹" not in text, text


async def test_the_captured_failure_naming_an_address_shows_it_whole_with_its_icon():
    row = _failure_row(C0DE)
    assert row["status"] == "blocked"
    # The address, a space and the icon, then one cell for the cut's ``…``.
    shown_to = row["failure"].index(C0DE) + len(C0DE) + 2
    lines, icons, links = await _address_probe([row], (_FIXED_COLS + shown_to + 1, 20))
    y = next(i for i, line in enumerate(lines) if C0DE in line)
    assert f'names {C0DE} {COPY_GLYPH}' in lines[y], lines[y]
    assert lines[y].rstrip().endswith(f"{COPY_GLYPH}…"), lines[y]
    assert [copied for _x, _y, copied in icons] == [C0DE], icons
    assert not [t for t in links if t[1] == y and t[3] == "address"], links


async def test_the_abbreviated_form_is_not_an_address_and_gets_no_icon():
    row = _failure_row(ABBREVIATED)
    width = _FIXED_COLS + len(row["failure"]) + 10
    lines, icons, _links = await _address_probe([row], (width, 20))
    assert any(f"operator {ABBREVIATED};" in line for line in lines), lines
    assert icons == [] and COPY_GLYPH not in "\n".join(lines), icons
