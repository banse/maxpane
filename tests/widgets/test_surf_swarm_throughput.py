"""THROUGHPUT -- the swarm signals panel on ``panels.SignalsPanelBase`` (WP5, on screen since WP7).

The panel reads the plan §1.3 dict **only**; the hand dict below is that shape.
Every assertion is against composited output.
"""

from __future__ import annotations

import inspect

from textual.app import App

from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.swarm_throughput import (
    ACCUMULATING_WORD,
    CANCELS_ID,
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
