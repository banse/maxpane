"""ROSTER -- the AGENT body's seat picker (swarm v2 plan A1, WP6a).

Composited assertions only (``rules/widgets.md``). The hand rows are bound to
``SURF_ROW_KEYS["swarm_seat_rows"]`` so a drifted shape reddens here rather
than on screen. The widget is unwired until WP7, so the per-class contract
checks the package walk would run are imposed here, bound to the frozen
``SWARM_WIDGET_SIGNATURES`` export.
"""

from __future__ import annotations

import inspect

from textual.app import App

from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS, SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.swarm_roster import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    SEAT_COLS,
    TIGHT_WIDTH,
    SurfSwarmRoster,
)
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase
from tests.widgets.surf_compositing import composite_lines

LAST_0 = 1_789_000_900.0
LAST_1548 = 1_789_000_000.0
LAST_463 = 1_789_000_500.0

SEAT_0 = {
    "token_id": 0, "agent_id": "50906", "nodes": 8, "jobs": 8,
    "roles": ["implement", "integrate", "review"],
    "accepted": 8, "rejected": 0, "revisions": 2, "mean_score": 100.0, "scored": 4,
    "working_now": False, "last_active_ts": LAST_0,
}
SEAT_1548 = {
    "token_id": 1548, "agent_id": "50971", "nodes": 7, "jobs": 6,
    "roles": ["implement", "review"],
    "accepted": 7, "rejected": 0, "revisions": 0, "mean_score": 1.0, "scored": 17,
    "working_now": False, "last_active_ts": LAST_1548,
}
SEAT_463 = {
    "token_id": 463, "agent_id": "50972", "nodes": 3, "jobs": 3,
    "roles": ["implement"],
    "accepted": 2, "rejected": 1, "revisions": 1, "mean_score": None, "scored": 0,
    "working_now": True, "last_active_ts": LAST_463,
}
ROWS = [SEAT_0, SEAT_1548, SEAT_463]

SELECTED = {"token_id": 1548, "agent_id": "50971", "selected_by": "saved"}
AS_OF = "04:06"
SIZE = (120, 14)


def test_the_hand_rows_carry_exactly_the_frozen_shape():
    for row in ROWS:
        assert tuple(row) == SURF_ROW_KEYS["swarm_seat_rows"]


async def _roster(size=SIZE, **kwargs):
    kwargs.setdefault("swarm_seat_rows", ROWS)
    kwargs.setdefault("swarm_seat_selected", SELECTED)
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmRoster, size, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


# -- the self-imposed contract (unwired until WP7) --------------------------------


def test_update_data_names_exactly_the_frozen_signature_in_order():
    params = [
        name for name, p in inspect.signature(SurfSwarmRoster.update_data).parameters.items()
        if name != "self" and p.kind is not p.VAR_KEYWORD
    ]
    assert tuple(params) == SWARM_WIDGET_SIGNATURES["SurfSwarmRoster"]
    assert any(
        p.kind is p.VAR_KEYWORD
        for p in inspect.signature(SurfSwarmRoster.update_data).parameters.values()
    )


async def test_no_args_and_all_none_render_unavailable_without_raising():
    bare = await composite_lines(SurfSwarmRoster, SIZE)
    assert "unavailable" in "\n".join(bare)
    assert "Loading" not in "\n".join(bare)
    none = await composite_lines(
        SurfSwarmRoster, SIZE,
        **{k: None for k in SWARM_WIDGET_SIGNATURES["SurfSwarmRoster"]},
    )
    assert "unavailable" in "\n".join(none)


# -- rows -------------------------------------------------------------------------


async def test_every_seat_renders_in_the_folds_order_with_its_counters():
    lines = await _roster()
    text = "\n".join(lines)
    y0 = next(i for i, l in enumerate(lines) if "IDMD #0" in l)
    y1548 = next(i for i, l in enumerate(lines) if "IDMD #1548" in l)
    y463 = next(i for i, l in enumerate(lines) if "IDMD #463" in l)
    assert y0 < y1548 < y463, "the fold's order (nodes desc) is kept, never re-sorted"
    row = _row_with(lines, "IDMD #1548")
    assert "50971" in row and "impl/rev" in row
    assert hhmm(LAST_1548) in row
    assert "1.0" in row
    assert "ROSTER" in text and f"as of {AS_OF}" in text


async def test_the_selected_row_is_marked_and_token_at_maps_it():
    class _A(App):
        def compose(self):
            yield SurfSwarmRoster()

    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmRoster)
        widget.update_data(
            swarm_seat_rows=ROWS, swarm_seat_selected=SELECTED, swarm_seat_as_of_hhmm=AS_OF,
        )
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        marked = [r for r in rows if "▸" in r]
        assert len(marked) == 1 and "IDMD #1548" in marked[0]
        assert "▸" not in _row_with(rows, "IDMD #0")
        # The marker is painted bold -- read off the compositor at the cell.
        y = rows.index(marked[0])
        x = marked[0].index("IDMD")
        assert pilot.app.screen.get_style_at(x, y).bold
        # The picker's map: row index -> token, in painted order.
        assert widget.selected_token == 1548
        assert widget.token_at(0) == 0
        assert widget.token_at(1) == 1548
        assert widget.token_at(2) == 463
        assert widget.token_at(3) is None and widget.token_at(-1) is None
        assert widget.selected_row_index == 1


async def test_a_non_dict_row_is_skipped_and_the_map_stays_aligned():
    class _A(App):
        def compose(self):
            yield SurfSwarmRoster()

    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SurfSwarmRoster)
        widget.update_data(
            swarm_seat_rows=[SEAT_0, "garbage", SEAT_463], swarm_seat_selected=None,
            swarm_seat_as_of_hhmm=AS_OF,
        )
        await pilot.pause()
        assert widget.token_at(0) == 0 and widget.token_at(1) == 463
        assert widget.token_at(2) is None
        assert widget.selected_token is None and widget.selected_row_index is None


async def test_an_empty_sweep_says_no_seat_seen_and_an_unread_one_says_unavailable():
    empty = "\n".join(await _roster(swarm_seat_rows=[], swarm_seat_selected=None))
    assert EMPTY_LINE in empty and "unavailable" not in empty
    unread = "\n".join(await _roster(swarm_seat_rows=None, swarm_seat_selected=None))
    assert "unavailable" in unread and EMPTY_LINE not in unread


async def test_a_hostile_role_word_renders_stripped_and_never_raises():
    hostile = dict(SEAT_463, roles=["[/x]PWNED", "implement"])
    lines = await _roster(swarm_seat_rows=[hostile], region_only=True)
    text = "\n".join(lines)
    assert "PWNED" in text and "impl" in text
    assert "[" not in text and "]" not in text


async def test_a_theme_token_in_an_agent_id_does_not_raise():
    hostile = dict(SEAT_463, agent_id="[$success]x")
    lines = await _roster(swarm_seat_rows=[hostile])
    assert "IDMD #463" in "\n".join(lines)


async def test_an_unknown_role_renders_whole_and_a_missing_score_dashes():
    row = dict(SEAT_463, roles=["referee"], mean_score=None)
    line = _row_with(await _roster(swarm_seat_rows=[row]), "IDMD #463")
    assert "referee" in line
    assert "--" in line


async def test_thirty_seats_render_without_a_cap():
    seats = [dict(SEAT_0, token_id=1000 + i) for i in range(30)]
    lines = await _roster((120, 40), swarm_seat_rows=seats, swarm_seat_selected=None)
    painted = [l for l in lines if "IDMD #1" in l]
    assert len(painted) == 30
    assert SurfSwarmRoster.ROW_CAP is None


async def test_a_malformed_row_field_dashes_instead_of_crashing():
    row = dict(SEAT_463, nodes="lots", last_active_ts="yesterday", roles="implement")
    line = _row_with(await _roster(swarm_seat_rows=[row]), "IDMD #463")
    assert "--" in line and "??:??" in line


# -- tiers -------------------------------------------------------------------------


def test_the_tier_thresholds_descend_and_are_row_sums():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0
    assert SEAT_COLS >= len("▸ IDMD #1548")


async def test_one_below_full_sheds_roles_and_says_widen():
    gutter = SwarmTableBase.GUTTER_COLS
    full = await _roster((FULL_WIDTH + gutter, 14))
    compact = await _roster((FULL_WIDTH + gutter - 1, 14))
    assert "impl/rev" in "\n".join(full) and "‹" not in "\n".join(full)
    assert "impl/rev" not in "\n".join(compact) and "‹" in "\n".join(compact)
    assert hhmm(LAST_1548) in "\n".join(compact), "compact keeps `last`"


async def test_one_below_compact_sheds_rev_and_last_too():
    gutter = SwarmTableBase.GUTTER_COLS
    tight = "\n".join(await _roster((COMPACT_WIDTH + gutter - 1, 14)))
    assert hhmm(LAST_1548) not in tight
    assert "IDMD #1548" in tight and "50971" in tight
    assert "‹" in tight


async def test_the_cursor_sits_on_the_selected_row_and_survives_a_resize():
    """The picker's cursor follows the manager's selection, and a repaint
    (every resize re-tiers the table: ``clear()`` + ``add_row``, which resets
    a ``DataTable`` cursor to row 0) puts it back. WP7's screen test found
    the gap: placed once by the screen, the cursor was on the selected row
    after the dispatch and on row 0 the moment the body was shown."""
    from textual.widgets import DataTable

    class _A(App):
        def compose(self):
            yield SurfSwarmRoster()

    async with _A().run_test(size=SIZE) as pilot:
        roster = pilot.app.query_one(SurfSwarmRoster)
        roster.update_data(swarm_seat_rows=ROWS, swarm_seat_selected=SELECTED,
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        table = roster.query_one(DataTable)
        assert roster.selected_row_index == 1
        assert table.cursor_row == 1
        await pilot.resize_terminal(SIZE[0] - 30, SIZE[1])
        await pilot.pause()
        await pilot.pause()
        assert table.cursor_row == 1, "the resize repaint reset the cursor"
        # A selection nothing painted carries leaves the cursor alone.
        roster.update_data(swarm_seat_rows=ROWS, swarm_seat_selected=None,
                           swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        assert roster.selected_row_index is None
