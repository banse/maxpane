"""The ``s`` SWARM body and the ``a`` AGENT body: modes, keys, bodies, hero swap.

Swarm v2 (WP7, 2026-09-21): the 2026-09-16 body (THE FIELD, QUEUE, JUST
SHIPPED, the score-table THROUGHPUT) is gone; ``s`` shows the hero over
CAPABILITY | THROUGHPUT, IN FLIGHT | LAUNCHES and SITES, and the new ``a``
shows the seat hero over ROSTER | VERDICTS, RECORD and FEEDBACK. Geometry is
``test_surf_swarm_layout.py``'s; this file is composition and behaviour.

Everything asserted against **composited output** (``_compositor.render_strips()``),
joined per row and then by newline: a string that never reaches a pixel passes
a naive test while being invisible to the user. No network: the harness is
``test_surf_screen``'s own ``_FakeManager`` over a committed/frozen payload.
"""

from __future__ import annotations

import pytest
from textual.widgets import DataTable

from maxpane_dashboard.screens.surf import (
    AGENT_BODY_ID, LAUNCHPAD_BODY_ID, MODE_AGENT, MODE_SWARM, POOL4_BODY_ID,
    POOL4_USER_BODY_ID, SWARM_BODY_ID, SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfSwarmAgentHero, SurfSwarmCapability, SurfSwarmHero, SurfSwarmInFlight,
    SurfSwarmLaunches, SurfSwarmRoster, SurfSwarmSeatFeedback,
    SurfSwarmSeatRecord, SurfSwarmSeatVerdicts, SurfSwarmSites,
    SurfSwarmThroughput,
)
from tests.screens.test_surf_screen import (
    _FakeManager, _frozen_payload, _region_text, _screen_text, _surf_app,
    _ThemedHarness,
)

_SIZE = (150, 45)
_S_PANELS = (SurfSwarmCapability, SurfSwarmThroughput, SurfSwarmInFlight,
             SurfSwarmLaunches, SurfSwarmSites)
_A_PANELS = (SurfSwarmRoster, SurfSwarmSeatVerdicts, SurfSwarmSeatRecord,
             SurfSwarmSeatFeedback)
_BODIES = {"s": (SWARM_BODY_ID, _S_PANELS, SurfSwarmHero),
           "a": (AGENT_BODY_ID, _A_PANELS, SurfSwarmAgentHero)}


async def _open(pilot, key="s"):
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press(key)
    await pilot.pause()
    await pilot.pause()
    return pilot.app.screen


@pytest.mark.parametrize("key,mode", [("s", MODE_SWARM), ("a", MODE_AGENT)])
async def test_the_key_opens_its_body_and_escape_backs_out(key, mode):
    body_id = _BODIES[key][0]
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, key)
        assert screen._mode == mode
        assert screen.query_one(f"#{body_id}").display is True
        await pilot.press("escape")
        await pilot.pause()
        assert screen.query_one(f"#{body_id}").display is False
        assert screen.query_one("#middle-row").display is True


@pytest.mark.parametrize("key", ["s", "a"])
async def test_pressing_the_key_twice_returns_to_the_dashboard(key):
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, key)
        await pilot.press(key)
        await pilot.pause()
        assert screen.query_one("#middle-row").display is True
        assert screen.query_one(f"#{_BODIES[key][0]}").display is False


async def test_s_and_a_switch_directly_from_every_other_body():
    bodies = ("#middle-row", f"#{LAUNCHPAD_BODY_ID}", f"#{POOL4_BODY_ID}",
              f"#{POOL4_USER_BODY_ID}", f"#{SWARM_BODY_ID}", f"#{AGENT_BODY_ID}")
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = pilot.app.screen
        for key, expected in (("l", f"#{LAUNCHPAD_BODY_ID}"),
                              ("s", f"#{SWARM_BODY_ID}"),
                              ("a", f"#{AGENT_BODY_ID}"),
                              ("s", f"#{SWARM_BODY_ID}"),
                              ("4", f"#{POOL4_USER_BODY_ID}"),
                              ("a", f"#{AGENT_BODY_ID}"),
                              ("e", f"#{POOL4_BODY_ID}"),
                              ("s", f"#{SWARM_BODY_ID}")):
            await pilot.press(key)
            await pilot.pause()
            showing = [b for b in bodies if screen.query_one(b).display]
            assert showing == [expected], (key, showing)


@pytest.mark.parametrize("key", ["s", "a"])
async def test_exactly_one_hero_shows_in_each_swarm_body(key):
    """Two swarm heroes are composed once each; ``_SURF_HERO_MODES``
    enumerates the modes that get ``SurfHero``, so neither body paints two."""
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, key)
        shown = [h for h in screen.query(".surf-hero") if h.display]
        assert len(shown) == 1
        assert isinstance(shown[0], _BODIES[key][2])


@pytest.mark.parametrize(
    "key,cls",
    [(k, c) for k, (_id, panels, _h) in _BODIES.items() for c in panels],
    ids=[c.__name__ for _k, (_id, panels, _h) in _BODIES.items() for c in panels],
)
async def test_every_swarm_panel_reaches_the_compositor(key, cls):
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, key)
        body = screen.query_one(f"#{_BODIES[key][0]}")
        found = list(body.query(cls))
        assert len(found) == 1, f"{cls.__name__}: {len(found)} instances"
        assert found[0].region.width > 0 and found[0].region.height > 0


@pytest.mark.parametrize(
    "key,cls",
    [(k, c) for k, (_id, panels, _h) in _BODIES.items() for c in panels],
    ids=[c.__name__ for _k, (_id, panels, _h) in _BODIES.items() for c in panels],
)
async def test_every_swarm_panel_paints_a_blank_row_under_its_title(key, cls):
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, key)
        panel = next(iter(screen.query_one(f"#{_BODIES[key][0]}").query(cls)))
        rows = _region_text(pilot.app, panel).split("\n")

    assert rows[0].strip(), f"{cls.__name__} has no title row"
    assert not rows[1].strip(), f"{cls.__name__} has no blank row under its title"
    assert rows[2].strip(), f"{cls.__name__} has no content row"


async def test_the_key_hint_names_the_swarm_and_the_agent():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        await pilot.pause()
        text = _screen_text(pilot.app)
        assert "s swarm" in text and "a agent" in text
    assert SurfScreen.KEY_HINTS == "[dim]l launchpad · 4 pool4 · s swarm · a agent[/]"


async def test_the_bindings_gained_a_and_nothing_else():
    assert {b.key for b in SurfScreen.BINDINGS} == {"r", "l", "e", "4", "s", "a", "escape"}
    assert hasattr(SurfScreen, "action_toggle_swarm")
    assert hasattr(SurfScreen, "action_toggle_agent")


# -- the roster picker ---------------------------------------------------------


class _SeatManager(_FakeManager):
    """A fake with the one seam the picker needs: ``select_seat`` records."""

    def __init__(self, payload=None) -> None:
        super().__init__(payload)
        self.selected: list = []

    def select_seat(self, token) -> None:
        self.selected.append(token)


def _seat_app(payload=None):
    manager = _SeatManager(payload)
    return _ThemedHarness(SurfScreen(manager, poll_interval=30, name="surf")), manager


async def test_enter_on_a_roster_row_selects_that_seat_and_refreshes():
    """``DataTable.RowSelected`` -> ``manager.select_seat(token)`` ->
    ``start_refresh``. The frozen payload's roster is 1548 then 1601; the
    cursor sits on the selected row (1548, index 0) after the first
    dispatch, so the second row is a genuine move."""
    app, manager = _seat_app()
    async with app.run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "a")
        calls_before = manager.calls
        roster = screen.query_one(SurfSwarmRoster)
        table = roster.query_one(f"#{SurfSwarmRoster.TABLE_ID}", DataTable)
        assert table.cursor_row == 0, "the cursor should start on the selected seat"
        table.focus()
        table.move_cursor(row=1, animate=False)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert manager.selected == [1601]
        assert manager.calls > calls_before, "a selection has to refresh the seat keys"


async def test_a_row_selected_from_another_table_picks_no_seat():
    """The handler is scoped to the roster's own table id."""
    app, manager = _seat_app()
    async with app.run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "s")
        launches = screen.query_one(SurfSwarmLaunches).query_one(DataTable)
        screen.post_message(DataTable.RowSelected(launches, 0, None))
        await pilot.pause()
        await pilot.pause()
        assert manager.selected == []


async def test_a_manager_without_the_seam_makes_enter_a_no_op():
    """No ``select_seat`` -> no selection, never a crash (test doubles, older
    managers)."""
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "a")
        table = screen.query_one(SurfSwarmRoster).query_one(DataTable)
        table.focus()
        table.move_cursor(row=1, animate=False)
        await pilot.press("enter")
        await pilot.pause()
        assert screen._mode == MODE_AGENT
        assert not pilot.app._exit


async def test_the_cursor_follows_the_manager_selection_after_a_refresh():
    """``_place_roster_cursor``: the manager's ``swarm_seat_selected`` is the
    truth; the cursor is moved onto its row after every dispatch."""
    payload = _frozen_payload(
        swarm_seat_selected={"token_id": 1601, "agent_id": "51044", "selected_by": "cursor"},
    )
    async with _surf_app(payload).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "a")
        roster = screen.query_one(SurfSwarmRoster)
        table = roster.query_one(DataTable)
        assert roster.selected_row_index == 1
        assert table.cursor_row == 1
