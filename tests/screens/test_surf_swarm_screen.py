"""Task 10 -- the ``s`` SWARM body: mode, key, body, hero swap, CSS.

Everything asserted against **composited output** (``_compositor.render_strips()``),
joined per row and then by newline: a string that never reaches a pixel passes
a naive test while being invisible to the user. No network: the harness is
``test_surf_screen``'s own ``_FakeManager`` over a committed/frozen payload.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.screens.surf import (
    LAUNCHPAD_BODY_ID, MODE_SWARM, POOL4_BODY_ID, POOL4_USER_BODY_ID,
    SWARM_BODY_ID, SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfSwarmField, SurfSwarmHero, SurfSwarmQueue, SurfSwarmShipped,
    SurfSwarmThroughput,
)
from tests.screens.test_surf_screen import _frozen_payload, _screen_text, _surf_app

_SIZE = (150, 45)
_PANELS = (SurfSwarmField, SurfSwarmShipped, SurfSwarmQueue, SurfSwarmThroughput)


async def _open(pilot):
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press("s")
    await pilot.pause()
    await pilot.pause()
    return pilot.app.screen


async def test_s_opens_the_swarm_body_and_escape_backs_out():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        assert screen._mode == MODE_SWARM
        assert screen.query_one(f"#{SWARM_BODY_ID}").display is True
        await pilot.press("escape")
        await pilot.pause()
        assert screen.query_one(f"#{SWARM_BODY_ID}").display is False


async def test_pressing_s_twice_returns_to_the_dashboard():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        await pilot.press("s")
        await pilot.pause()
        assert screen.query_one("#middle-row").display is True


async def test_s_switches_directly_from_every_other_body():
    bodies = ("#middle-row", f"#{LAUNCHPAD_BODY_ID}", f"#{POOL4_BODY_ID}",
              f"#{POOL4_USER_BODY_ID}", f"#{SWARM_BODY_ID}")
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = pilot.app.screen
        for keys, expected in ((("l",), f"#{LAUNCHPAD_BODY_ID}"),
                               (("s",), f"#{SWARM_BODY_ID}"),
                               (("4",), f"#{POOL4_USER_BODY_ID}"),
                               (("s",), f"#{SWARM_BODY_ID}"),
                               (("e",), f"#{POOL4_BODY_ID}"),
                               (("s",), f"#{SWARM_BODY_ID}")):
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            showing = [b for b in bodies if screen.query_one(b).display]
            assert showing == [expected], (keys, showing)


async def test_exactly_one_hero_shows_in_the_swarm_body():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        shown = [h for h in screen.query(".surf-hero") if h.display]
        assert len(shown) == 1
        assert isinstance(shown[0], SurfSwarmHero)


@pytest.mark.parametrize("cls", _PANELS, ids=[c.__name__ for c in _PANELS])
async def test_every_swarm_panel_reaches_the_compositor(cls):
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        body = screen.query_one(f"#{SWARM_BODY_ID}")
        found = list(body.query(cls))
        assert len(found) == 1, f"{cls.__name__}: {len(found)} instances"
        assert found[0].region.width > 0


@pytest.mark.parametrize("cls", _PANELS, ids=[c.__name__ for c in _PANELS])
async def test_every_swarm_panel_paints_a_blank_row_under_its_title(cls):
    from tests.screens.test_surf_screen import _region_text

    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        panel = next(iter(screen.query_one(f"#{SWARM_BODY_ID}").query(cls)))
        rows = _region_text(pilot.app, panel).split("\n")

    assert rows[0].strip(), f"{cls.__name__} has no title row"
    assert not rows[1].strip(), f"{cls.__name__} has no blank row under its title"
    assert rows[2].strip(), f"{cls.__name__} has no content row"


async def test_the_key_hint_names_the_swarm():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        await pilot.pause()
        assert "s swarm" in _screen_text(pilot.app)
    assert SurfScreen.KEY_HINTS == "[dim]l launchpad · 4 pool4 · s swarm[/]"


async def test_the_bindings_gained_s_and_nothing_else():
    assert {b.key for b in SurfScreen.BINDINGS} == {"r", "l", "e", "4", "s", "escape"}
    assert hasattr(SurfScreen, "action_toggle_swarm")
