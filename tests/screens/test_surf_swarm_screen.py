"""The ``s`` SWARM body and the ``a`` AGENT body: modes, keys, bodies, hero swap.

Swarm v2 (WP7, 2026-09-21): the 2026-09-16 body (THE FIELD, QUEUE, JUST
SHIPPED, the score-table THROUGHPUT) is gone; ``s`` shows the hero over
CAPABILITY | THROUGHPUT, IN FLIGHT | LAUNCHES and SITES, and the new ``a``
shows the seat hero over ROSTER | SEAT RECORD, RECORD and FEEDBACK. Geometry is
``test_surf_swarm_layout.py``'s; this file is composition and behaviour.

The AGENT body reads the seat's lifetime ``/seats`` record since WP5 of
``docs/surf_agent_seats_plan.md`` (the contract flip). The seat tests below
that need the manager's real seat tier drive a real ``SurfManager`` over the
network-dead doubles of ``tests/data/test_surf_manager_swarm.py`` -- never a
payload hand-shaped to look like one.

Everything asserted against **composited output** (``_compositor.render_strips()``),
joined per row and then by newline: a string that never reaches a pixel passes
a naive test while being invisible to the user. No network: the harness is
``test_surf_screen``'s own ``_FakeManager`` over a committed/frozen payload.
"""

from __future__ import annotations

import pytest
from textual.widgets import DataTable

from maxpane_dashboard.screens.surf import (
    AGENT_BODY_ID, BOARD_BODY_ID, LAUNCHPAD_BODY_ID, MODE_AGENT, MODE_SWARM, MODE_BOARD, POOL4_BODY_ID,
    POOL4_USER_BODY_ID, SWARM_BODY_ID, SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfSwarmAgentHero, SurfSwarmBoardHero, SurfSwarmLeaderboard, SurfSwarmFleet, SurfSwarmCapability, SurfSwarmHero, SurfSwarmInFlight,
    SurfSwarmLaunches, SurfSwarmSeatNodes,
    SurfSwarmSeatRecord, SurfSwarmSeatVerdicts, SurfSwarmSites,
    SurfSwarmThroughput,
)
from maxpane_dashboard.data import surf_swarm as sw
from tests.data.test_surf_manager_swarm import _FakeSwarm, _seated, _settle
from tests.screens.test_surf_screen import (
    _FakeManager, _frozen_payload, _region_text, _screen_text, _surf_app,
    _ThemedHarness,
)
from tests.surf_swarm_fixtures import swarm_seat_capture

_SIZE = (150, 45)
_S_PANELS = (SurfSwarmCapability, SurfSwarmThroughput, SurfSwarmInFlight,
             SurfSwarmLaunches, SurfSwarmSites)
_A_PANELS = (SurfSwarmSeatVerdicts, SurfSwarmSeatNodes, SurfSwarmSeatRecord)
_BODIES = {"s": (SWARM_BODY_ID, _S_PANELS, SurfSwarmHero),
           "a": (AGENT_BODY_ID, _A_PANELS, SurfSwarmAgentHero),
           "b": (BOARD_BODY_ID, (SurfSwarmLeaderboard,SurfSwarmFleet), SurfSwarmBoardHero)}


async def _open(pilot, key="s"):
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press(key)
    await pilot.pause()
    await pilot.pause()
    return pilot.app.screen


@pytest.mark.parametrize("key,mode", [("s", MODE_SWARM), ("a", MODE_AGENT), ("b", MODE_BOARD)])
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


@pytest.mark.parametrize("key", ["s", "a", "b"])
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


@pytest.mark.parametrize("key", ["s", "a", "b"])
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


async def test_every_agent_hero_title_sits_on_the_same_row():
    """Owner, 2026-09-21: bodies of one to three lines were centred, so ACCEPTED
    and COLLAB sat a row below SEAT, REVIEWED, SCORE and STATUS. Every box's
    title is its first row inside the border."""
    from maxpane_dashboard.widgets.surf.swarm_agent_hero import SurfSwarmAgentHeroBox

    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "a")
        boxes = list(screen.query_one(SurfSwarmAgentHero).query(SurfSwarmAgentHeroBox))
        firsts = [_region_text(pilot.app, b).split("\n")[1].strip(" │") for b in boxes]
        heights = {len(str(b.render()).split("\n")) for b in boxes}

    assert len(heights) > 1, "every body has the same height: nothing to align"
    assert firsts == ["SEAT", "ACCEPTED", "ACCEPT RATE", "REVIEWED", "COLLAB", "STATUS · workers as of 04:02"], firsts


async def test_the_key_hint_names_the_swarm_and_the_agent():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        await pilot.pause()
        text = _screen_text(pilot.app)
        assert "s swm" in text and "a agt" in text
    assert SurfScreen.KEY_HINTS == "[dim]l launchpad · 4 pl4 · s swm · a agt · b brd[/]"


async def test_the_bindings_include_board_agent_and_seat_selection():
    assert {b.key for b in SurfScreen.BINDINGS} == {"r", "l", "e", "4", "s", "a", "b", "i", "escape"}
    assert hasattr(SurfScreen, "action_toggle_swarm")
    assert hasattr(SurfScreen, "action_toggle_agent")


async def test_retired_roster_selection_is_gone():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "a")
        assert all(table.cursor_type == "none" for table in screen.query_one(f"#{AGENT_BODY_ID}").query(DataTable))
        text = _region_text(pilot.app,screen.query_one(f"#{AGENT_BODY_ID}"))
        assert "BY NODE" in text and "TEAMMATES" in text
        assert "ROSTER" not in text and "FEEDBACK" not in text


def _record_needles(seat: dict) -> list[str]:
    """Strings only seat *seat*'s ``/seats`` record puts on the AGENT body."""
    summary = sw.seat_summary_from_seat(seat)
    work = sw.seat_work_rows(seat)
    needles = [f"{summary['accepted']} of {summary['attempts']}", summary["owner"][:6]]
    needles += [row["job_id"][:8] for row in work[:3]]
    return needles


async def test_a_switch_pending_composite_shows_no_number_of_the_old_seat(tmp_path):
    """Plan §5, the screen column: A's slot is present and B is selected.
    Not one of A's record strings reaches the composited AGENT body -- and
    each of them does reach it while A is the selected seat, so the needles
    can match (a control, not an assumption)."""
    manager, before = await _seated(tmp_path, _FakeSwarm())
    assert before["swarm_seat_selected"]["token_id"] == 0
    manager.set_seat(420)
    pending = await manager.fetch_and_compute()
    await manager.close()
    assert pending["swarm_seat_state"] == "pending"
    needles = _record_needles(swarm_seat_capture("seat_0"))
    for payload, should_show in ((before, True), (pending, False)):
        async with _surf_app(payload).run_test(size=(170, 60)) as pilot:
            screen = await _open(pilot, "a")
            body = screen.query_one(f"#{AGENT_BODY_ID}")
            text = _region_text(pilot.app, body)
            hero = _region_text(pilot.app, screen.query_one(SurfSwarmAgentHero))
            shown = [n for n in needles if n in text or n in hero]
            if should_show:
                assert shown == needles, sorted(set(needles) - set(shown))
            else:
                assert shown == [], shown
                assert "IDMD #420" in hero and "Loading" in hero
                assert "IDMD #0" not in hero


# -- the seat prompt (`i`) ----------------------------------------------------
#
# Drives the real `SeatInputScreen` through the pilot. `save_seat` is
# monkeypatched in every test -- it writes `~/.maxpane/config.toml` -- and
# `save_wallet` raises: the prompt subclasses the wallet prompt, and Textual
# runs a message handler on every class in the MRO.


class _SavedSeatManager(_FakeManager):
    """Records the saved-seat changes through ``set_seat``."""

    def __init__(self, payload=None) -> None:
        super().__init__(payload)
        self.saved: list = []

    def set_seat(self, token) -> None:
        self.saved.append(token)


@pytest.fixture()
def saved_seats(monkeypatch) -> list:
    saved: list = []
    monkeypatch.setattr("maxpane_dashboard.screens.seat_input.save_seat", saved.append)
    monkeypatch.setattr("maxpane_dashboard.screens.seat_input.get_seat", lambda: 1548)

    def _no_wallet(_address):
        raise AssertionError("the seat prompt must never save a wallet")

    monkeypatch.setattr("maxpane_dashboard.screens.wallet_input.save_wallet", _no_wallet)
    return saved


def _prompt_app():
    manager = _SavedSeatManager()
    return _ThemedHarness(SurfScreen(manager, poll_interval=30, name="surf")), manager


async def _type(pilot, text: str) -> None:
    from textual.widgets import Input
    field = pilot.app.screen.query_one("#wi-input", Input)
    field.value = ""
    await pilot.press(*text)
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


async def test_i_opens_the_seat_prompt_prefilled_with_the_saved_seat(saved_seats):
    from textual.widgets import Input
    from maxpane_dashboard.screens.seat_input import SeatInputScreen
    app, _ = _prompt_app()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot, "i")
        assert isinstance(app.screen, SeatInputScreen)
        assert app.screen.query_one("#wi-input", Input).value == "1548"
        text = _screen_text(app.screen)
        assert "IDENTITY.MD SEAT" in text and "Identity.md NFT id" in text
        assert "config.toml" in text, "the durable write is disclosed before it happens"


async def test_a_typed_seat_is_saved_set_and_opens_the_agent_body(saved_seats):
    """From the dashboard body: the reader asked about a seat, so they land
    on the body that is about one, and the seat keys refresh now."""
    app, manager = _prompt_app()
    async with app.run_test(size=_SIZE) as pilot:
        screen = app.screen
        await _open(pilot, "i")
        calls_before = manager.calls
        await _type(pilot, "#463")
        assert saved_seats == [463]
        assert manager.saved == [463]
        assert app.screen is screen and screen._mode == MODE_AGENT
        assert manager.calls > calls_before, "a new seat has to refresh the seat keys"


class _NeverPairedManager(_SavedSeatManager):
    """``set_seat`` makes the next payload the one the real manager serves for
    a token ``/seats`` answers 404 ``unknown_seat`` for (plan §5)."""

    def set_seat(self, token) -> None:
        super().set_seat(token)
        self._payload = dict(
            self._payload,
            swarm_seat_selected={"token_id": token, "agent_id": None, "selected_by": "saved"},
            swarm_seat_state="unknown_seat", swarm_seat_summary=None,
            swarm_seat_work_rows=[], swarm_seat_node_rows=[], swarm_seat_teammates=[],
            swarm_seat_as_of_hhmm="13:50",
        )


async def test_a_saved_seat_never_paired_says_so_and_never_not_seen(saved_seats):
    """Decision D1 replaces change A's ``#N not seen`` fallback: an unknown
    saved seat is shown as itself, ``never paired`` -- a real negative --
    and no other seat's record stands in for it."""
    manager = _NeverPairedManager()
    app = _ThemedHarness(SurfScreen(manager, poll_interval=30, name="surf"))
    async with app.run_test(size=_SIZE) as pilot:
        screen = app.screen
        await _open(pilot, "i")
        await _type(pilot, "#9999")
        assert manager.saved == [9999] and screen._mode == MODE_AGENT
        await screen._do_refresh()
        await pilot.pause()
        hero = _region_text(app, screen.query_one(SurfSwarmAgentHero))
        body = _region_text(app, screen.query_one(f"#{AGENT_BODY_ID}"))
        assert "IDMD #9999" in hero and "never paired" in hero
        for panel in (SurfSwarmSeatVerdicts, SurfSwarmSeatRecord, SurfSwarmSeatNodes):
            assert "never paired" in _region_text(app, screen.query_one(panel)), panel.__name__
        assert "not seen" not in hero + body
        assert "IDMD #1548" not in hero


async def _real_client_answer_for_the_404_capture(token: int):
    """What the real ``SwarmClient.fetch_seat`` returns for the committed
    ``unknown_seat_404.json`` body -- read through an injected
    ``httpx.MockTransport``, so the network is never reached."""
    import httpx
    from maxpane_dashboard.data.surf_swarm_client import SwarmClient

    body = swarm_seat_capture("unknown_seat_404")

    async def _no_sleep(_s: float) -> None:
        return None

    client = SwarmClient(
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(404, json=body))
        ),
        sleep=_no_sleep,
    )
    try:
        return await client.fetch_seat(token)
    finally:
        await client.close()


async def test_a_never_paired_seat_reaches_the_screen_through_a_real_manager(tmp_path):
    """The never-paired chain end to end, where the test above hand-shapes
    the payload: the real client's answer to the committed 404 capture ->
    a real ``SurfManager``'s seat tier with the seat saved -> the composited
    AGENT body. Final-review fix wave, 2026-09-21."""
    answer = await _real_client_answer_for_the_404_capture(9999)
    manager, payload = await _seated(
        tmp_path, _FakeSwarm(seats={9999: answer}), seat=9999,
    )
    assert manager.swarm_client.seat_calls == [9999]
    assert payload["swarm_seat_state"] == "unknown_seat"
    app = _ThemedHarness(SurfScreen(manager, poll_interval=3600, name="surf"))
    async with app.run_test(size=_SIZE) as pilot:
        screen = await _open(pilot, "a")
        await _settle(manager)
        hero = _region_text(app, screen.query_one(SurfSwarmAgentHero))
        body = _region_text(app, screen.query_one(f"#{AGENT_BODY_ID}"))
        assert "IDMD #9999" in hero and "never paired" in hero
        for panel in (SurfSwarmSeatVerdicts, SurfSwarmSeatRecord, SurfSwarmSeatNodes):
            assert "never paired" in _region_text(app, screen.query_one(panel)), panel.__name__
        assert "not seen" not in hero + body
        assert "Loading" not in hero
    await manager.close()


async def test_an_invalid_seat_is_refused_on_the_prompt(saved_seats):
    from maxpane_dashboard.screens.seat_input import SeatInputScreen
    app, manager = _prompt_app()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot, "i")
        await _type(pilot, "#")
        assert isinstance(app.screen, SeatInputScreen)
        assert "Invalid seat" in _screen_text(app.screen)
        assert saved_seats == [] and manager.saved == []


async def test_escape_leaves_the_seat_and_the_body_alone(saved_seats):
    app, manager = _prompt_app()
    async with app.run_test(size=_SIZE) as pilot:
        from maxpane_dashboard.screens.seat_input import SeatInputScreen
        screen = await _open(pilot, "s")
        await pilot.press("i")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, SeatInputScreen)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.pause()
        assert app.screen is screen and screen._mode == MODE_SWARM
        assert saved_seats == [] and manager.saved == []


async def test_a_manager_without_set_seat_still_saves_and_never_crashes(saved_seats):
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = pilot.app.screen
        await _open(pilot, "i")
        await _type(pilot, "463")
        assert saved_seats == [463]
        assert pilot.app.screen is screen and screen._mode == MODE_AGENT
        assert not pilot.app._exit


async def test_board_opens_its_own_hero_and_toggles_back():
    from maxpane_dashboard.widgets.surf import SurfSwarmBoardHero
    async with _surf_app(_frozen_payload()).run_test(size=(150,45)) as pilot:
        screen=await _open(pilot,'b')
        assert screen._mode=='board'
        assert [type(w) for w in screen.query('.surf-hero') if w.display]==[SurfSwarmBoardHero]
        await pilot.press('b');await pilot.pause()
        assert screen.query_one('#middle-row').display
        await pilot.press('b','escape');await pilot.pause()
        assert screen.query_one('#middle-row').display

async def test_board_enter_persists_using_shared_writer_and_opens_agent(monkeypatch):
    from maxpane_dashboard import config
    from maxpane_dashboard.widgets.surf import SurfSwarmLeaderboard
    from maxpane_dashboard.data import surf_swarm as fold
    from tests.surf_swarm_fixtures import swarm_capture_v3
    rows=fold.board_rows(swarm_capture_v3('contributors'),swarm_capture_v3('workers'))
    writes=[]
    monkeypatch.setattr(config,'save_seat',lambda token:writes.append(token))
    data=_frozen_payload(swarm_board_rows=rows)
    async with _surf_app(data).run_test(size=(150,45)) as pilot:
        screen=await _open(pilot,'b')
        selected=[]
        screen._data_manager.set_seat=lambda token:selected.append(token)
        table=screen.query_one(SurfSwarmLeaderboard).query_one(DataTable)
        table.focus();table.move_cursor(row=1)
        await pilot.press('enter');await pilot.pause()
        assert writes==selected==[rows[1]['token_id']]
        assert screen._mode==MODE_AGENT


@pytest.mark.parametrize("state", ["pending", None])
async def test_selected_seat_keeps_worker_and_contributor_groups_when_seats_is_unread(state):
    from tests.screens.test_surf_swarm_layout import _v3_agent_payload
    payload=_v3_agent_payload("pending" if state else "seats-unavailable")
    async with _surf_app(payload).run_test(size=(170,60)) as pilot:
        screen=await _open(pilot,"a")
        hero=_region_text(pilot.app,screen.query_one(SurfSwarmAgentHero))
        seat=_region_text(pilot.app,screen.query_one(SurfSwarmSeatVerdicts))
    assert "IDMD #420" in hero and "working 0 of 1" in hero
    assert "accepted unavailable" in hero
    assert "contributors 207 att · 189 acc · 2 rej · 16 pend" in seat
    assert "skills" not in seat and "linux arm64" not in seat
    assert "as of 03:01" in seat and "workers as of 04:02" not in seat
    assert "workers as of 04:02" in hero
    assert "⧉" not in seat and "attempts 201" not in seat

async def test_captured_executing_note_is_visible_and_honestly_cut_at_swarm_pin():
    from tests.screens.test_surf_swarm_layout import _v3_swarm_payload
    from maxpane_dashboard.screens.surf import SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS
    payload=_v3_swarm_payload()
    assert len(payload['swarm_inflight_rows'])==1
    assert payload['swarm_inflight_rows'][0]['job_id'].startswith('5a4dfb13')
    async with _surf_app(payload).run_test(size=(SURF_SWARM_FULL_LAYOUT_COLUMNS,SURF_SWARM_FULL_LAYOUT_ROWS)) as pilot:
        screen=await _open(pilot,'s')
        text=_region_text(pilot.app,screen.query_one(SurfSwarmInFlight))
    assert 'no online' in text and '…' in text and '‹' in text.splitlines()[0]
