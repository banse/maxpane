"""The AGENT body's hero: SEAT · NODES · JOBS · ACC / REJ · REVISIONS · SCORE · STATUS.

Composited assertions only; the payload dicts are the manager's
``swarm_seat_selected`` / ``swarm_seat_summary`` shapes (plan A1). The
per-class contract checks are imposed here against the frozen
``SWARM_WIDGET_SIGNATURES`` export.

**Composited under the real stylesheet, at the real pins** (WP7). The hero
states no geometry of its own (``rules/widgets.md``: ``HeroBoxBase`` leaves
every dimension to ``minimal.tcss``), so a bare ``App`` would render six
unbordered, unpadded boxes and prove nothing about what fits. The harness
loads ``maxpane_dashboard.app.CSS_PATH`` and renders at the AGENT body's own
column pin and at the app-wide ``FULL_LAYOUT_COLUMNS`` -- the two widths the
plan's one-line ``IDMD #1548 · agent 50971 · most active`` (25 cells) does
**not** fit, which is why SEAT is three lines (module docstring).
"""

from __future__ import annotations

import inspect

import pytest
from textual.app import App

from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.screens.surf import SURF_AGENT_FULL_LAYOUT_COLUMNS
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.swarm_agent_hero import (
    BOX_IDS,
    NO_SEAT_LINE,
    SurfSwarmAgentHero,
    SurfSwarmAgentHeroBox,
)
from tests.widgets.surf_compositing import composite_lines

LAST = 1_789_000_000.0
FIRST = 1_788_990_000.0

SELECTED = {"token_id": 1548, "agent_id": "50971", "selected_by": "env"}
SUMMARY = {
    "nodes": 7, "jobs": 6, "accepted": 7, "rejected": 0, "revisions": 0,
    "mean_score": 1.0, "scored": 17, "working_now": False,
    "first_seen_ts": FIRST, "last_active_ts": LAST,
    "roles": [{"role": "implement", "count": 5}, {"role": "review", "count": 2}],
    "rejection_codes": [],
}
AS_OF = "04:06"
#: The AGENT body's own column pin: six bordered boxes with a 1-cell margin
#: and ``padding: 0 1`` leave ~16 content cells each there -- SEAT's widest
#: line (``agent 50971``, 11; ``IDMD #1548``, 10) fits, the plan's 25-cell
#: one-liner does not. Every ``_box_text`` below renders here by default.
SIZE = (SURF_AGENT_FULL_LAYOUT_COLUMNS, 9)
#: The two widths the hero has to be whole at: its body's pin and the app's.
PINS = (SURF_AGENT_FULL_LAYOUT_COLUMNS, FULL_LAYOUT_COLUMNS)


class _Themed(App):
    """The real stylesheet: ``SurfSwarmAgentHeroBox``'s geometry lives there."""

    CSS_PATH = CSS_PATH

    def compose(self):
        yield SurfSwarmAgentHero()


async def _hero(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_selected", SELECTED)
    kwargs.setdefault("swarm_seat_summary", SUMMARY)
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return "\n".join(await composite_lines(SurfSwarmAgentHero, size, css_path=CSS_PATH, **kwargs))


async def _box_text(box_id, size=SIZE, **kwargs):
    """The composited text of one box's own region (the boxes share rows)."""
    merged = {"swarm_seat_selected": SELECTED, "swarm_seat_summary": SUMMARY,
              "swarm_seat_as_of_hhmm": AS_OF, **kwargs}

    async with _Themed().run_test(size=size) as pilot:
        hero = pilot.app.query_one(SurfSwarmAgentHero)
        hero.update_data(**merged)
        await pilot.pause()
        box = pilot.app.query_one(f"#{box_id}")
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        region = box.region
        sliced = [
            rows[y][region.x: region.x + region.width]
            for y in range(max(region.y, 0), min(region.y + region.height, len(rows)))
        ]
        return "\n".join(row.rstrip() for row in sliced)


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_frozen_signature_in_order():
    sig = inspect.signature(SurfSwarmAgentHero.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SWARM_WIDGET_SIGNATURES["SurfSwarmAgentHero"]
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = await composite_lines(SurfSwarmAgentHero, SIZE)
    assert "unavailable" in "\n".join(bare) and "Loading" not in "\n".join(bare)
    none = await composite_lines(
        SurfSwarmAgentHero, SIZE,
        **{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmAgentHero"]},
    )
    assert "unavailable" in "\n".join(none)


def test_the_box_class_is_its_own_type_selector():
    assert SurfSwarmAgentHero.BOX_CLASS is SurfSwarmAgentHeroBox
    assert len(BOX_IDS) == 6 == len(SurfSwarmAgentHero.BOXES)


# -- SEAT ------------------------------------------------------------------------


@pytest.mark.parametrize("width", PINS)
async def test_the_seat_box_names_token_and_agent_whole_at_both_pins(width):
    """Three lines, none of them clipped: the plan's one-line form is 25
    cells and the box has ~16 content cells at the AGENT pin, ~17 at 143."""
    text = await _box_text(BOX_IDS["seat"], size=(width, 9))
    assert "SEAT" in text and "IDMD #1548" in text and "agent 50971" in text
    assert "…" not in text, (width, text)


@pytest.mark.parametrize("width", PINS)
async def test_the_three_selected_by_phrasings(width):
    env = await _box_text(BOX_IDS["seat"], size=(width, 9),
                          swarm_seat_selected=dict(SELECTED, selected_by="env"))
    assert "env" in env and "…" not in env
    cursor = await _box_text(BOX_IDS["seat"], size=(width, 9),
                             swarm_seat_selected=dict(SELECTED, selected_by="cursor"))
    assert "selected" in cursor and "MAXPANE" not in cursor and "…" not in cursor
    most = await _box_text(BOX_IDS["seat"], size=(width, 9),
                           swarm_seat_selected=dict(SELECTED, selected_by="most_active"))
    assert "most active" in most and "…" not in most


async def test_the_hero_row_is_seven_lines_under_the_stylesheet():
    """SEAT's three lines under the label and its blank row need a 7-tall
    box (border included); ``minimal.tcss`` says so and this is where it
    is read back off the compositor rather than off the file."""
    async with _Themed().run_test(size=SIZE) as pilot:
        hero = pilot.app.query_one(SurfSwarmAgentHero)
        hero.update_data(swarm_seat_selected=SELECTED, swarm_seat_summary=SUMMARY,
                         swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        assert hero.region.height == 7
        assert all(box.region.height == 7 for box in pilot.app.query(SurfSwarmAgentHeroBox))


async def test_no_selection_is_two_different_facts():
    """No sweep at all is ``unavailable``; a sweep that found no seat says so."""
    unread = await _box_text(BOX_IDS["seat"], swarm_seat_selected=None, swarm_seat_summary=None,
                             swarm_seat_as_of_hhmm=None)
    assert "unavailable" in unread and NO_SEAT_LINE not in unread
    swept = await _box_text(BOX_IDS["seat"], swarm_seat_selected=None, swarm_seat_summary=None,
                            swarm_seat_as_of_hhmm=AS_OF)
    assert NO_SEAT_LINE in swept and "unavailable" not in swept


async def test_a_hostile_agent_id_renders_literally():
    text = await _box_text(BOX_IDS["seat"], swarm_seat_selected=dict(SELECTED, agent_id="[/x]"))
    assert "agent [/x]" in text


async def test_a_theme_token_in_an_agent_id_does_not_raise():
    text = await _box_text(BOX_IDS["seat"], swarm_seat_selected=dict(SELECTED, agent_id="[$success]"))
    # ``agent [$success]`` is 16 cells and fits the box at the pin: the token
    # is *shown*, brackets and all (a parsed theme token vanishes or raises).
    assert "agent [$success]" in text


# -- the counters -----------------------------------------------------------------


async def test_the_counter_boxes_carry_their_numbers_and_zeros_are_real():
    nodes = await _box_text(BOX_IDS["nodes"])
    assert "NODES · JOBS" in nodes and "7 · 6" in nodes
    verdicts = await _box_text(BOX_IDS["verdicts"])
    # ``ACC / REJ``, not ``ACCEPTED / REJECTED`` (19 cells): the label has to
    # fit the ~16-cell box at the AGENT pin without an ellipsis of its own.
    assert "ACC / REJ" in verdicts and "7 / 0" in verdicts and "…" not in verdicts
    revisions = await _box_text(BOX_IDS["revisions"])
    assert "REVISIONS" in revisions
    body_lines = [line.strip("│ ") for line in revisions.splitlines()]
    assert "0" in body_lines
    assert "unavailable" not in verdicts + revisions


async def test_a_missing_summary_under_a_marker_is_an_empty_not_a_failure():
    """The sweep ran and found no seat: the counters have nothing to say, which
    is not the same claim as ``unavailable`` (CLAUDE.md: never a false
    degradation). With no marker at all they *are* unavailable.
    """
    swept = await _box_text(BOX_IDS["nodes"], swarm_seat_selected=None, swarm_seat_summary=None)
    assert "unavailable" not in swept and "—" in swept
    unread = await _box_text(BOX_IDS["nodes"], swarm_seat_selected=None, swarm_seat_summary=None,
                             swarm_seat_as_of_hhmm=None)
    assert "unavailable" in unread


# -- SCORE ------------------------------------------------------------------------


async def test_the_score_box_distinguishes_no_feedback_from_zero():
    scored = await _box_text(BOX_IDS["score"])
    assert "1.0 (17 scored)" in scored
    none = await _box_text(BOX_IDS["score"], swarm_seat_summary=dict(SUMMARY, mean_score=None, scored=0))
    assert "— (0 scored)" in none and "0.0" not in none
    zero = await _box_text(BOX_IDS["score"], swarm_seat_summary=dict(SUMMARY, mean_score=0.0, scored=3))
    assert "0.0 (3 scored)" in zero


# -- STATUS -----------------------------------------------------------------------


async def test_the_status_box_says_working_or_idle_with_the_last_stamp():
    idle = await _box_text(BOX_IDS["status"])
    assert "idle ○" in idle and f"last {hhmm(LAST)}" in idle
    working = await _box_text(BOX_IDS["status"], swarm_seat_summary=dict(SUMMARY, working_now=True))
    assert "working ●" in working


async def test_a_malformed_summary_field_lands_on_unavailable_not_a_crash():
    text = await _box_text(BOX_IDS["nodes"], swarm_seat_summary=dict(SUMMARY, nodes="many"))
    assert "-- · 6" in text
    whole = await _hero(swarm_seat_summary="garbage")
    assert "unavailable" in whole
