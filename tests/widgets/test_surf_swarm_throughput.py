"""THROUGHPUT -- the swarm signals panel on ``panels.SignalsPanelBase`` (WP5, on screen since WP7).

The panel reads the plan §1.3 dict **only**; the hand dict below is that shape.
Every assertion is against composited output. The fold (``set_expanded``, the
``x more`` / ``x less`` hint, the collapsed display) is SWARM WORKFLOWS WP4,
``docs/surf_swarm_workflows_spec.md`` §1; its tests are at the end.
"""

from __future__ import annotations

import inspect

from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.swarm_throughput import (
    ACCUMULATING_WORD,
    CANCELS_ID,
    FOLD_GAP_ID,
    LESS_HINT,
    MORE_HINT,
    NO_JOBS_LINE,
    SAMPLE_FLOOR_WORD,
    STALE_WORD,
    STATES_ID,
    SurfSwarmThroughput,
)
from tests.widgets.surf_compositing import composite_lines

#: Plan §1.3, filled from the 2026-09-21 corpus facts (100 jobs, 98
#: completed / 2 executing, durations over the 10 delivered jobs).
THROUGHPUT = {
    "window_start_ts": 1_758_000_000.0,
    "window_end_ts": 1_758_000_840.0,      # 14 min later
    "window_n": 100,
    "states": [{"state": "executing", "count": 2}, {"state": "completed", "count": 98}],
    "dur_median_s": 54 * 60.0,
    "dur_p90_s": 72 * 60.0,
    "dur_max_s": 3 * 3600.0 + 5 * 60.0,
    "dur_n": 10,
    "cancel_reasons": [],
    "completed_24h": 41,
    "seen_since_ts": 1_757_900_000.0,
}

SIZE = (60, 26)


async def _lines(size=SIZE, **kwargs) -> list[str]:
    return await composite_lines(SurfSwarmThroughput, size, **kwargs)


async def _text(size=SIZE, **kwargs) -> str:
    return "\n".join(await _lines(size, **kwargs))


def _tp(**over) -> dict:
    return {**THROUGHPUT, **over}


def _without(*keys) -> dict:
    return {k: v for k, v in THROUGHPUT.items() if k not in keys}


# -- contract ---------------------------------------------------------------


def test_update_data_takes_exactly_the_frozen_keys_in_order():
    expected = SWARM_WIDGET_SIGNATURES["SurfSwarmThroughput"]
    params = inspect.signature(SurfSwarmThroughput.update_data).parameters
    named = tuple(
        name for name, p in params.items()
        if name != "self" and p.kind is not p.VAR_KEYWORD
    )
    assert named == expected
    assert set(named) == set(expected)
    assert any(p.kind is p.VAR_KEYWORD for p in params.values())


async def test_no_args_renders_every_row_unavailable_and_never_loading():
    lines = await _lines()
    assert "Loading" not in "\n".join(lines)
    # window, median, p90, max, completed 24h, states, cancel reasons
    assert sum("unavailable" in l for l in lines) == 7, lines


async def test_every_key_none_renders_unavailable():
    text = await _text(**{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmThroughput"]})
    assert text.count("unavailable") == 7, text


async def test_a_non_dict_payload_is_unavailable_not_a_crash():
    text = await _text(swarm_throughput="fast")
    assert text.count("unavailable") == 7, text


# -- window row ---------------------------------------------------------------


async def test_the_window_line_names_the_span_and_the_job_count():
    lines = await _lines(swarm_throughput=THROUGHPUT)
    assert any("over 14 min · 100 jobs" in l for l in lines), lines


async def test_the_window_line_spans_hours_when_it_must():
    lines = await _lines(swarm_throughput=_tp(window_end_ts=THROUGHPUT["window_start_ts"] + 2 * 3600 + 5 * 60))
    assert any("over 2 h 5 min · 100 jobs" in l for l in lines), lines


async def test_a_missing_window_end_says_over_dash():
    lines = await _lines(swarm_throughput=_tp(window_end_ts=None))
    assert any("over -- · 100 jobs" in l for l in lines), lines


async def test_a_zero_job_window_says_so_instead_of_a_zero():
    lines = await _lines(swarm_throughput=_tp(window_n=0))
    assert any(NO_JOBS_LINE in l for l in lines), lines
    assert not any("0 jobs" in l for l in lines), lines


async def test_the_window_row_is_the_first_body_row_and_label_less():
    lines = await _lines(swarm_throughput=THROUGHPUT)
    assert "THROUGHPUT" in lines[0]
    assert lines[1].strip() == "", lines[:3]
    assert "over 14 min" in lines[2], lines[:3]
    assert "window" not in lines[2].lower(), lines[2]


# -- duration rows ------------------------------------------------------------


async def test_the_three_duration_rows_carry_two_unit_durations():
    lines = await _lines(swarm_throughput=THROUGHPUT)
    median = next(l for l in lines if "median" in l)
    p90 = next(l for l in lines if "p90" in l)
    mx = next(l for l in lines if l.strip().endswith("3h 5m") or " max " in l)
    assert "54m" in median, median
    assert "1h 12m" in p90, p90
    assert "3h 5m" in mx, mx


async def test_each_duration_row_carries_the_sample_count():
    """``dur_n`` (WP7) beside every real duration; a dict without the field
    prints the bare duration rather than a count nobody measured."""
    lines = await _lines(swarm_throughput=THROUGHPUT)
    for label in ("median", "p90", "max"):
        row = next(l for l in lines if f" {label}" in l)
        assert "n=10" in row, row
    bare = await _lines(swarm_throughput=_without("dur_n"))
    for label in ("median", "p90", "max"):
        row = next(l for l in bare if f" {label}" in l)
        assert "n=" not in row, row


async def test_a_duration_under_the_sample_floor_says_so():
    lines = await _lines(swarm_throughput=_tp(dur_median_s=None, dur_p90_s=None, dur_max_s=None))
    for label in ("median", "p90", "max"):
        row = next(l for l in lines if f" {label}" in l)
        assert SAMPLE_FLOOR_WORD in row, row
        assert "0" not in row.split(label, 1)[1], row


async def test_a_missing_duration_key_is_a_bare_dash_not_the_floor_word():
    lines = await _lines(swarm_throughput=_without("dur_p90_s"))
    row = next(l for l in lines if " p90" in l)
    assert "--" in row and SAMPLE_FLOOR_WORD not in row, row


# -- completed 24h ------------------------------------------------------------


async def test_completed_24h_accumulates_with_its_since_clock_while_none():
    since = THROUGHPUT["seen_since_ts"]
    lines = await _lines(swarm_throughput=_tp(completed_24h=None))
    row = next(l for l in lines if "completed 24h" in l)
    assert f"{ACCUMULATING_WORD} since {hhmm(since)}" in row, row
    assert "0" not in row.split("completed 24h", 1)[1].replace(hhmm(since), ""), row


async def test_completed_24h_zero_is_a_real_zero_once_accumulated():
    lines = await _lines(swarm_throughput=_tp(completed_24h=0))
    row = next(l for l in lines if "completed 24h" in l)
    assert row.rstrip().endswith(" 0"), row
    assert ACCUMULATING_WORD not in row, row


async def test_completed_24h_shows_its_count():
    lines = await _lines(swarm_throughput=THROUGHPUT)
    row = next(l for l in lines if "completed 24h" in l)
    assert row.rstrip().endswith(" 41"), row


async def test_completed_24h_missing_key_is_a_dash():
    lines = await _lines(swarm_throughput=_without("completed_24h", "seen_since_ts"))
    row = next(l for l in lines if "completed 24h" in l)
    assert row.rstrip().endswith("--"), row
    assert ACCUMULATING_WORD not in row


# -- state rollup ---------------------------------------------------------------


async def test_states_render_one_line_each_sorted_by_count_desc():
    lines = await _lines(swarm_throughput=THROUGHPUT)
    y_completed = next(i for i, l in enumerate(lines) if "completed " in l and "98" in l)
    y_executing = next(i for i, l in enumerate(lines) if "executing" in l and " 2" in l)
    assert y_completed < y_executing, lines


async def test_a_hostile_state_word_renders_literally():
    tp = _tp(states=[{"state": "[/x]", "count": 3}, {"state": "[$error]", "count": 1}])
    text = await _text(swarm_throughput=tp)
    assert "[/x]" in text, text
    assert "[$error]" in text, text
    assert "unavailable" not in text


async def test_an_empty_state_list_says_none_and_a_none_list_is_unavailable():
    class _A(App):
        def compose(self):
            yield SurfSwarmThroughput()

    async def _states_text(states):
        async with _A().run_test(size=SIZE) as pilot:
            panel = pilot.app.query_one(SurfSwarmThroughput)
            panel.update_data(swarm_throughput=_tp(states=states))
            await pilot.pause()
            region = pilot.app.query_one(f"#{STATES_ID}").region
            strips = pilot.app.screen._compositor.render_strips()
            rows = ["".join(seg.text for seg in strip) for strip in strips]
            return "\n".join(
                rows[y][region.x: region.x + region.width]
                for y in range(region.y, region.y + region.height)
            )

    assert "none" in await _states_text([])
    assert "unavailable" in await _states_text(None)


async def test_a_malformed_state_entry_is_skipped_and_the_rest_render():
    tp = _tp(states=[{"state": "completed", "count": 98}, "junk", {"count": 1}, {"state": "x"}])
    text = await _text(swarm_throughput=tp)
    assert "completed" in text and "98" in text, text


# -- cancel reasons -------------------------------------------------------------


async def test_the_cancel_block_says_none_when_empty_and_lists_reasons_when_not():
    text = await _text(swarm_throughput=THROUGHPUT)
    block = text.split("cancel reasons", 1)[1]
    assert "none" in block.splitlines()[1] if len(block.splitlines()) > 1 else "none" in block, text
    tp = _tp(cancel_reasons=[{"reason": "needs a [/x] reviewer", "count": 4}])
    text = await _text(swarm_throughput=tp)
    assert "needs a [/x] reviewer" in text and " 4" in text, text


async def test_a_none_cancel_list_is_unavailable_and_a_long_reason_is_clipped():
    class _A(App):
        def compose(self):
            yield SurfSwarmThroughput()

    async def _cancels(cancel_reasons):
        async with _A().run_test(size=SIZE) as pilot:
            panel = pilot.app.query_one(SurfSwarmThroughput)
            panel.update_data(swarm_throughput=_tp(cancel_reasons=cancel_reasons))
            await pilot.pause()
            region = pilot.app.query_one(f"#{CANCELS_ID}").region
            strips = pilot.app.screen._compositor.render_strips()
            rows = ["".join(seg.text for seg in strip) for strip in strips]
            return [
                rows[y][region.x: region.x + region.width].rstrip()
                for y in range(region.y, region.y + region.height)
            ]

    assert any("unavailable" in l for l in await _cancels(None))
    rows = await _cancels([{"reason": "r" * 200, "count": 1}])
    reason_rows = [l for l in rows if "rrr" in l]
    assert len(reason_rows) == 1, rows
    assert "…" in reason_rows[0], reason_rows
    assert reason_rows[0].rstrip().endswith("1"), reason_rows


# -- title --------------------------------------------------------------------


async def test_the_stale_word_appears_only_when_told_true():
    for value in (None, False):
        lines = await _lines(swarm_throughput=THROUGHPUT, swarm_stale=value)
        assert STALE_WORD not in lines[0], (value, lines[0])
    lines = await _lines(swarm_throughput=THROUGHPUT, swarm_stale=True)
    assert f"· {STALE_WORD}" in lines[0], lines[0]


async def test_the_title_carries_the_marker_only_when_it_is_real():
    marked = await _lines(swarm_throughput=THROUGHPUT, swarm_as_of_hhmm="12:34", swarm_stale=True)
    assert marked[0].strip() == f"THROUGHPUT · as of 12:34 · {STALE_WORD}", marked[0]
    for absent in (None, ""):
        bare = await _lines(swarm_throughput=THROUGHPUT, swarm_as_of_hhmm=absent)
        assert bare[0].strip() == "THROUGHPUT", bare[0]


# -- seed ---------------------------------------------------------------------


async def test_the_loading_seed_lands_on_the_first_row_not_a_separator():
    class _A(App):
        def compose(self):
            yield SurfSwarmThroughput()

    async with _A().run_test(size=SIZE) as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip).rstrip() for strip in strips]
    assert "THROUGHPUT" in rows[0]
    assert rows[1] == "", rows[:4]
    assert "Loading..." in rows[2], rows[:4]
    assert rows[3] == "", rows[:4]
    assert "\n".join(rows).count("Loading") == 1, rows


# -- the fold (spec §1: ``set_expanded``, the title hint, the collapsed display) ----------

#: THROUGHPUT's SWARM geometry with the row's width fixed at the 46 cells the
#: panel renders at the pin (``max-width: 46``), and ``height: auto`` so the
#: panel's height *is* its lines -- the quantity the top row's floor binds.
_FOLD_CSS = "SurfSwarmThroughput { width: 46; height: auto; padding: 0 1; }"
_FOLD_SIZE = (60, 30)
#: Hidden when collapsed: the separator above the blocks, ``states`` + its two
#: states, ``cancel reasons`` + ``none`` -- counted off the hand dict.
_FOLDED_LINES = 1 + (1 + len(THROUGHPUT["states"])) + (1 + 1)


class _Fold(App):
    CSS = _FOLD_CSS

    def compose(self):
        yield SurfSwarmThroughput()


def _region_rows(app, widget) -> list[str]:
    strips = app.screen._compositor.render_strips()
    rows = ["".join(seg.text for seg in strip) for strip in strips]
    r = widget.region
    return [rows[y][r.x: r.x + r.width].rstrip() for y in range(r.y, r.y + r.height)]


async def _fold(*calls, size=_FOLD_SIZE, **kwargs):
    """``(height, rows, hidden ids)`` after *kwargs* then ``set_expanded`` per call."""
    async with _Fold().run_test(size=size) as pilot:
        panel = pilot.app.query_one(SurfSwarmThroughput)
        if kwargs:
            panel.update_data(**kwargs)
        for value in calls:
            panel.set_expanded(value)
        await pilot.pause()
        hidden = sorted(w.id or "?" for w in panel.query("*") if not w.display)
        return panel.region.height, _region_rows(pilot.app, panel), hidden


def test_the_hints_are_the_specs_words_and_the_same_width():
    assert (MORE_HINT, LESS_HINT) == ("x more", "x less")
    assert cell_len(MORE_HINT) == cell_len(LESS_HINT) == 6


async def test_the_widgets_own_default_is_expanded_with_no_hint():
    """Nothing changes until a screen applies its state (spec §1, WP4 → WP5):
    every block shows and the title advertises no key nobody binds yet."""
    height, rows, hidden = await _fold(swarm_throughput=THROUGHPUT, swarm_as_of_hhmm="12:34")
    assert hidden == [], hidden
    assert rows[0].strip() == "THROUGHPUT · as of 12:34", rows[0]
    assert any("cancel reasons" in r for r in rows) and any("executing" in r for r in rows), rows
    assert height == len(rows) == 9 + _FOLDED_LINES, rows


async def test_collapsing_hides_exactly_the_separator_and_the_two_blocks():
    open_h, open_rows, _ = await _fold(True, swarm_throughput=THROUGHPUT)
    shut_h, shut_rows, hidden = await _fold(False, swarm_throughput=THROUGHPUT)
    assert hidden == sorted([FOLD_GAP_ID, STATES_ID, CANCELS_ID]), hidden
    assert open_h - shut_h == _FOLDED_LINES == 6, (open_h, shut_h)
    # The collapsed body is the expanded body with its last six lines gone.
    assert shut_rows[1:] == open_rows[1:shut_h], (shut_rows, open_rows)
    dropped = open_rows[shut_h:]
    assert dropped[0] == "" and "states" in dropped[1] and "cancel reasons" in dropped[4], dropped
    assert "completed 24h" in shut_rows[-1], shut_rows


async def test_expanding_again_restores_every_line():
    first_h, first_rows, _ = await _fold(True, swarm_throughput=THROUGHPUT)
    again_h, again_rows, hidden = await _fold(False, True, swarm_throughput=THROUGHPUT)
    assert hidden == [] and again_h == first_h and again_rows == first_rows, again_rows


async def test_a_non_bool_is_ignored():
    for value in (1, 0, None, "yes", [], 1.0):
        shut_h, shut_rows, hidden = await _fold(False, value, swarm_throughput=THROUGHPUT)
        assert len(hidden) == 3 and shut_rows[0].endswith("· x more"), (value, shut_rows[0])
        _h, rows, hidden = await _fold(value, swarm_throughput=THROUGHPUT)
        assert hidden == [] and rows[0].strip() == "THROUGHPUT", (value, rows[0])


async def test_the_title_ends_with_the_hint_for_the_state_and_keeps_its_width():
    _h, shut, _ = await _fold(False, swarm_throughput=THROUGHPUT, swarm_as_of_hhmm="12:34")
    _h, opened, _ = await _fold(True, swarm_throughput=THROUGHPUT, swarm_as_of_hhmm="12:34")
    assert shut[0].strip() == f"THROUGHPUT · as of 12:34 · {MORE_HINT}", shut[0]
    assert opened[0].strip() == f"THROUGHPUT · as of 12:34 · {LESS_HINT}", opened[0]
    assert cell_len(shut[0].strip()) == cell_len(opened[0].strip())


async def test_stale_sits_before_the_hint_and_the_worst_title_is_whole_at_the_pin_width():
    """Spec §1's worst case, measured at the 46-cell panel (title room 42)."""
    for expanded, hint in ((False, MORE_HINT), (True, LESS_HINT)):
        _h, rows, _ = await _fold(expanded, swarm_throughput=THROUGHPUT,
                                  swarm_as_of_hhmm="17:45", swarm_stale=True)
        title = rows[0].strip()
        assert title == f"THROUGHPUT · as of 17:45 · {STALE_WORD} · {hint}", title
        assert cell_len(title) == 41 and "…" not in title, title


async def test_a_title_too_wide_clips_before_the_hint_and_never_the_hint():
    class _Narrow(App):
        CSS = "SurfSwarmThroughput { width: 30; height: auto; padding: 0 1; }"

        def compose(self):
            yield SurfSwarmThroughput()

    for expanded, hint in ((False, MORE_HINT), (True, LESS_HINT)):
        async with _Narrow().run_test(size=_FOLD_SIZE) as pilot:
            panel = pilot.app.query_one(SurfSwarmThroughput)
            panel.update_data(swarm_throughput=THROUGHPUT, swarm_as_of_hhmm="17:45", swarm_stale=True)
            panel.set_expanded(expanded)
            await pilot.pause()
            title = _region_rows(pilot.app, panel)[0].strip()
        # 30 cells less the panel's and the title's padding: 26 of room.
        assert title.endswith(f"… · {hint}"), title
        assert title.startswith("THROUGHPUT · as"), title
        assert cell_len(title) == 26, title


async def test_set_expanded_repaints_from_the_stored_payload_without_new_data():
    """A fixed-height panel, so no resize repaints it behind the call's back:
    ``True`` changes no line's display at all, and the title must still move."""

    class _Fixed(App):
        CSS = "SurfSwarmThroughput { width: 46; height: 24; padding: 0 1; }"

        def compose(self):
            yield SurfSwarmThroughput()

    for expanded, hint in ((True, LESS_HINT), (False, MORE_HINT)):
        async with _Fixed().run_test(size=_FOLD_SIZE) as pilot:
            panel = pilot.app.query_one(SurfSwarmThroughput)
            panel.update_data(swarm_throughput=THROUGHPUT, swarm_as_of_hhmm="12:34")
            await pilot.pause()
            height = panel.region.height
            panel.set_expanded(expanded)
            await pilot.pause()
            rows = _region_rows(pilot.app, panel)
            assert panel.region.height == height
        assert rows[0].strip() == f"THROUGHPUT · as of 12:34 · {hint}", rows[0]
        assert any("over 14 min · 100 jobs" in r for r in rows), rows
        assert "unavailable" not in "\n".join(rows), rows


async def test_set_expanded_before_any_data_keeps_the_loading_seed():
    """No payload yet: the hint is painted, the ``Loading...`` seed is not
    replaced by a false ``unavailable``."""
    height, rows, hidden = await _fold(False)
    assert rows[0].strip() == f"THROUGHPUT · {MORE_HINT}", rows[0]
    assert "Loading..." in rows[2] and "unavailable" not in "\n".join(rows), rows
    assert len(hidden) == 3, hidden


async def test_set_expanded_before_mount_composes_collapsed():
    panel = SurfSwarmThroughput()
    panel.set_expanded(False)

    class _Pre(App):
        CSS = _FOLD_CSS

        def compose(self):
            yield panel

    async with _Pre().run_test(size=_FOLD_SIZE) as pilot:
        panel.update_data(swarm_throughput=THROUGHPUT)
        await pilot.pause()
        hidden = sorted(w.id or "?" for w in panel.query("*") if not w.display)
        rows = _region_rows(pilot.app, panel)
    assert hidden == sorted([FOLD_GAP_ID, STATES_ID, CANCELS_ID]), hidden
    assert rows[0].strip() == f"THROUGHPUT · {MORE_HINT}", rows[0]
