"""Native rack navigation and input integration; every manager is a local stub."""
from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GameSelectScreen
from maxpane_dashboard.screens.surf import (
    MODE_AGENT, MODE_BOARD, MODE_DASHBOARD, MODE_ORACLES, MODE_POOL4,
    MODE_POOL4_USER, MODE_SWARM, MODE_WORK, SurfScreen,
)
from tests.test_app_startup import MANAGER_ATTRS
from tests.data.test_surf_manager_surfboard import manager as work_manager

MODES = (MODE_DASHBOARD, MODE_SWARM, MODE_AGENT, MODE_BOARD,
         MODE_ORACLES, MODE_POOL4_USER, MODE_WORK)
CARD_KEYS = ("announce", "swarm", "agent", "board", "oracles", "pool4", "work")


class HubManager:
    """Shared manager double: separate full/snapshot reads and observable lookups."""
    def __init__(self):
        self._error_count = 0
        self.full_reads = 0
        self.hub_reads = 0
        self.closed = 0
        self.agent_active = False
        self.hub_active = False
        self.seat = None
        self.hub_seats = (420, None, None, None)
        self.commands = []
        self.command_entered = asyncio.Event()
        self.command_release = asyncio.Event()
        self.command_release.set()
        self.ignore_command_cancel = False
        self.command_result = {"lines": ["reply"], "intent": None, "token_id": None,
                               "url": None, "clear": False}

    async def fetch_and_compute(self):
        self.full_reads += 1
        return {}

    async def fetch_hub_snapshot(self):
        self.hub_reads += 1
        return {"surfboard_cards": [dict(key=key, destination=mode, status="live",
                                        seat_slot=0 if key == "agent" else None,
                                        token_id=self.hub_seats[0] if key == "agent" else None)
                                   for key, mode in zip(CARD_KEYS, MODES)]}

    def get_hub_seats(self):
        return self.hub_seats

    def set_hub_seats(self, seats):
        self.hub_seats = tuple(seats)

    def set_agent_active(self, active):
        self.agent_active = active

    def set_hub_active(self, active):
        self.hub_active = active

    def set_seat(self, seat):
        self.seat = seat

    async def execute_hub_command(self, command, **kwargs):
        self.commands.append(command)
        self.command_entered.set()
        try:
            await self.command_release.wait()
        except asyncio.CancelledError:
            if not self.ignore_command_cancel:
                raise
            await self.command_release.wait()
        return self.command_result

    async def close(self):
        self.closed += 1


class HubApp(MaxPaneApp):
    """Real app routing/bindings without the splash or a network prefetch."""
    def on_mount(self, event):
        event.prevent_default()
        self._launch_game(self._initial_game, first=True)


def hub_app(initial_game="surfboard"):
    app = HubApp(initial_game=initial_game)
    managers = {}
    for attr in MANAGER_ATTRS:
        manager = HubManager()
        managers[attr] = manager
        setattr(app, attr, manager)
    return app, managers


def painted(app):
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


@pytest.mark.parametrize("configured_interval", (15,30,60))
async def test_hub_terminal_polling_is_thirty_seconds(configured_interval):
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import HubPayloadManager, hub_payload
    payload=hub_payload()
    app=HubHarness(payload)
    app.hub=SurfboardScreen(HubPayloadManager(payload), poll_interval=configured_interval)
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        assert app.hub._poll_interval==30
        assert '30s poll' not in painted(app)
        assert 'q quit · m menu · tab switch' in painted(app).splitlines()[-1]


async def test_terminal_age_timer_uses_injected_elapsed_time_and_stops_when_hidden(monkeypatch):
    from types import SimpleNamespace
    from textual.screen import Screen
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import HubPayloadManager, hub_payload

    clock = SimpleNamespace(now=100.)
    payload = hub_payload()
    app = HubHarness(payload)
    app.hub = SurfboardScreen(HubPayloadManager(payload), clock=lambda: clock.now)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.hub
        first_timer = hub._age_timer
        assert first_timer is not None
        first_timer.pause()
        terminal = hub.query_one(SurfboardTerminal)
        calls = []
        monkeypatch.setattr(terminal, "update_age", calls.append, raising=False)
        clock.now += 9
        hub._tick_terminal_age()
        assert calls == [9.]
        await hub._do_refresh()
        hub._tick_terminal_age()
        assert calls[-1] == 0.
        await app.push_screen(Screen())
        await pilot.pause()
        assert hub._age_timer is None
        assert first_timer._task is None
        count = len(calls)
        clock.now += 20
        hub._tick_terminal_age()
        assert len(calls) == count
        await app.pop_screen()
        await pilot.pause()
        assert hub._age_timer is not None and hub._age_timer is not first_timer
        hub._age_timer.pause()
        clock.now += 3
        hub._tick_terminal_age()
        assert calls[-1] == 3.


def test_open_mode_validates_before_mount_without_scheduling():
    screen = SurfScreen(HubManager())
    screen.open_mode(MODE_AGENT, return_context="surfboard")
    assert screen._mode == MODE_AGENT
    assert screen.return_context == "surfboard"
    with pytest.raises(ValueError):
        screen.open_mode("not-a-body", return_context="surfboard")
    with pytest.raises(ValueError):
        screen.open_mode(MODE_AGENT, return_context="arbitrary")
    assert screen._mode == MODE_AGENT


@pytest.mark.asyncio
async def test_all_eight_routes_reuse_one_screen_and_return_to_one_rack():
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    from maxpane_dashboard.widgets.surfboard import SurfboardRack
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        assert isinstance(hub, SurfboardScreen)
        depth = len(app.screen_stack)
        installed = None
        for key, mode in zip(CARD_KEYS, MODES):
            hub.query_one(SurfboardRack).focus_card(key)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SurfScreen)
            assert app.screen._mode == mode
            assert app.screen._data_manager is managers["_surf_manager"]
            assert app._current_game == "surfboard"
            assert managers["_surf_manager"].agent_active is (mode == MODE_AGENT)
            assert not managers["_surf_manager"].hub_active
            installed = installed or app.screen
            assert app.screen is installed
            await pilot.press("escape")
            assert app.screen is hub
            assert len(app.screen_stack) == depth
            assert not managers["_surf_manager"].agent_active
            assert managers["_surf_manager"].hub_active


@pytest.mark.asyncio
async def test_body_toggle_and_editor_escape_preserve_hub_context():
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        app.open_surf_mode(MODE_AGENT)
        await pilot.pause()
        screen = app.screen
        await pilot.press("f")
        assert screen._record_filter_open
        await pilot.press("escape")
        assert app.screen is screen
        assert not screen._record_filter_open
        await pilot.press("s")
        assert screen._mode == MODE_SWARM
        await pilot.press("s")
        assert app.screen.name == "surfboard"
        assert not managers["_surf_manager"].agent_active


@pytest.mark.asyncio
async def test_explicit_entry_one_clears_context_and_preserves_native_escape():
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        app.open_surf_mode(MODE_AGENT)
        await pilot.pause()
        await pilot.press("m")
        assert isinstance(app.screen, GameSelectScreen)
        assert not managers["_surf_manager"].agent_active
        await pilot.press("1")
        screen = app.screen
        assert isinstance(screen, SurfScreen)
        assert screen.return_context is None
        await pilot.press("a", "escape")
        assert app.screen is screen
        assert screen._mode == MODE_DASHBOARD
        assert app._current_game == "surf"


@pytest.mark.asyncio
async def test_input_keeps_global_shortcuts_literal_and_escape_restores_cards():
    from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        terminal = hub.query_one(SurfboardTerminal)
        await pilot.press("slash")
        assert app.focused is terminal.command_input
        await pilot.press("q", "m", "t", "r", "slash", "1", "9")
        assert terminal.command_input.value == "qmtr/19"
        assert app.screen is hub
        assert managers["_surf_manager"].closed == 0
        await pilot.press("tab")
        assert app.screen is hub
        previous_card = hub.query_one(SurfboardRack).focused_card
        terminal.focus_input()
        await pilot.press("escape")
        assert app.screen is hub
        assert not isinstance(app.focused, Input)
        assert hub.query_one(SurfboardRack).focused_card == previous_card
        assert terminal.command_input.value == "qmtr/19"
        await pilot.press("tab")
        assert app.screen.name == "surf"
        assert app._current_game == "surf"


@pytest.mark.asyncio
async def test_command_result_after_navigation_cannot_reply_or_open_a_body(monkeypatch):
    from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
    app, managers = hub_app()
    manager = managers["_surf_manager"]
    saved = []
    monkeypatch.setattr("maxpane_dashboard.config.save_seat", saved.append)
    manager.command_release.clear()
    manager.ignore_command_cancel = True
    manager.command_result = {"lines": ["late reply"], "intent": "open_seat", "token_id": 420,
                              "url": None, "clear": False}
    async with app.run_test(size=(149, 45)) as pilot:
        hub = app.screen
        terminal = hub.query_one(SurfboardTerminal)
        await pilot.press("slash")
        terminal.command_input.value = "open #420"
        await pilot.press("enter")
        await manager.command_entered.wait()
        await pilot.press("escape", "tab")
        assert app.screen.name == "surf"
        app._current_game = "surfboard"
        app._launch_game("surfboard")
        await pilot.pause()
        manager.command_release.set()
        await pilot.pause()
        assert app.screen is hub
        assert manager.seat is None
        assert saved == []
        assert "late reply" not in painted(app)


@pytest.mark.asyncio
async def test_empty_seats_focus_input_without_navigating_and_terminal_draft_survives_visit():
    from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        rack = hub.query_one(SurfboardRack)
        terminal = hub.query_one(SurfboardTerminal)
        terminal.command_input.value = "find unchanged.eth"
        for card in rack.query(".empty"):
            card.action_activate()
            await pilot.pause()
            assert app.screen is hub
            assert card.can_focus
            assert app.focused is card.query_one(Input)
        rack.focus_card("board")
        await pilot.press("enter", "escape")
        assert app.screen is hub
        assert rack.focused_card == "board"
        assert terminal.command_input.value == "find unchanged.eth"


@pytest.mark.asyncio
async def test_agent_modal_escape_closes_prompt_before_hub(monkeypatch):
    from maxpane_dashboard.screens.seat_input import SeatInputScreen
    monkeypatch.setattr("maxpane_dashboard.screens.seat_input.get_seat", lambda: None)
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        app.open_surf_mode(MODE_AGENT)
        await pilot.press("i")
        assert isinstance(app.screen, SeatInputScreen)
        assert not managers["_surf_manager"].agent_active
        await pilot.press("escape")
        assert isinstance(app.screen, SurfScreen)
        assert managers["_surf_manager"].agent_active
        await pilot.press("escape")
        assert app.screen.name == "surfboard"


@pytest.mark.parametrize('activation', ['mouse', 'keyboard'])
async def test_agent_header_numbers_edit_only_the_clicked_slot_and_keep_boardroom(monkeypatch, activation):
    from maxpane_dashboard.screens.seat_input import SeatInputScreen
    from maxpane_dashboard.widgets.surfboard.rack import AGENT_KEYS, SurfboardCard
    saved = []
    monkeypatch.setattr('maxpane_dashboard.config.save_surfboard_seat', lambda slot, token: saved.append((slot, token)))
    app, managers = hub_app()
    manager = managers['_surf_manager']
    manager.hub_seats = (420, 7, None, 0)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        for slot, key in enumerate(AGENT_KEYS):
            replacement = 0 if slot == 0 else 100 + slot
            card = hub.query_one('#surfboard-card-' + key, SurfboardCard)
            card.set_data(dict(token_id=manager.hub_seats[slot], status='idle', primary='420', meter_state='idle'))
            await pilot.pause()
            row = hub._compositor.render_strips()[card.region.y]
            x = 0
            for segment in row:
                if segment.style and segment.style.meta.get('seat_edit') == slot:
                    break
                x += segment.cell_length
            else:
                pytest.fail('Clickable slot number missing from the card header')
            original = manager.hub_seats
            async def open_editor():
                if activation == 'mouse':
                    await pilot.click(offset=(x + slot % 3, card.region.y))
                else:
                    await pilot.press(str(slot + 1))
            await open_editor()
            await pilot.pause()
            assert isinstance(app.screen, SeatInputScreen)
            field = app.screen.query_one('#wi-input', Input)
            assert field.value == ('' if original[slot] is None else str(original[slot]))
            field.value = str(replacement)
            await pilot.press('escape')
            await pilot.pause()
            assert app.screen is hub and manager.hub_seats == original
            assert len(saved) == slot
            await open_editor()
            await pilot.pause()
            field = app.screen.query_one('#wi-input', Input)
            field.value = ''
            await pilot.press('enter')
            assert isinstance(app.screen, SeatInputScreen) and len(saved) == slot
            field.value = str(replacement)
            if slot == 2:
                def fail_save(slot, token):
                    raise OSError('read-only config')
                monkeypatch.setattr('maxpane_dashboard.config.save_surfboard_seat', fail_save)
                await pilot.press('enter')
                assert isinstance(app.screen, SeatInputScreen)
                assert manager.hub_seats == original and len(saved) == slot
                assert 'Could not save seat' in painted(app)
                monkeypatch.setattr('maxpane_dashboard.config.save_surfboard_seat', lambda slot, token: saved.append((slot, token)))
            await pilot.press('enter')
            await pilot.pause()
            assert app.screen is hub
            expected = list(original)
            expected[slot] = replacement
            assert manager.hub_seats == tuple(expected)
            assert saved == [(index, 0 if index == 0 else 100 + index) for index in range(slot + 1)]
            assert manager.seat == 0


async def test_agent_number_shortcuts_do_not_intercept_input():
    from maxpane_dashboard.screens.seat_input import SeatInputScreen
    from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        for field in (hub.query_one(SurfboardTerminal).query_one(Input),
                      hub.query_one('#surfboard-seat-2', Input)):
            field.focus()
            await pilot.press('1', '2', '3', '4')
            assert app.screen is hub
            assert field.value == '1234'
        card = hub.query_one('#surfboard-card-agent')
        await pilot.click(offset=(card.region.right - 5, card.region.y))
        assert isinstance(app.screen, SeatInputScreen)
        await pilot.press('escape')
        assert app.screen is hub


@pytest.mark.asyncio
async def test_hub_paints_while_startup_full_fetch_is_blocked():
    from maxpane_dashboard.screens.refresh_guard import PREFETCH_WORKER_NAME
    from tests.screens.test_refresh_guard import _drain
    app, managers = hub_app()
    manager = managers["_surf_manager"]
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_full():
        entered.set()
        await release.wait()
        return {}

    manager.fetch_and_compute = blocked_full
    async with app.run_test(size=(149, 45)) as pilot:
        app.run_worker(app._prefetch(manager, "surfboard"), name=PREFETCH_WORKER_NAME)
        await entered.wait()
        manager.hub_reads = 0
        app.screen.start_refresh()
        await _drain()
        assert manager.hub_reads == 1
        assert not release.is_set()
        await pilot.pause()
        assert "IMD BOARDROOM" in painted(app)
        release.set()


@pytest.mark.asyncio
async def test_command_navigation_and_url_allowlist_use_existing_routes(monkeypatch):
    from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
    app, managers = hub_app()
    manager = managers["_surf_manager"]
    opened = []
    saved = []
    monkeypatch.setattr(app, "open_url", opened.append)
    monkeypatch.setattr("maxpane_dashboard.config.save_seat", saved.append)
    job_id = "12345678-1234-1234-1234-123456789012"
    async with app.run_test(size=(149, 45)) as pilot:
        hub = app.screen
        terminal = hub.query_one(SurfboardTerminal)
        terminal.focus_input()
        manager.command_result = dict(lines=[], intent="open_url", token_id=None,
                                      url=f"https://explorer.imd.fun/jobs/{job_id}", clear=False)
        terminal.command_input.value = "open " + job_id
        await pilot.press("enter")
        assert opened == [manager.command_result["url"]]
        manager.command_result["url"] = f"https://explorer.imd.fun.evil.example/jobs/{job_id}"
        terminal.command_input.value = "open invalid"
        await pilot.press("enter")
        assert len(opened) == 1
        manager.command_result = dict(lines=[], intent="open_seat", token_id=420, url=None, clear=False)
        terminal.command_input.value = "open #420"
        await pilot.press("enter")
        assert app.screen.name == "surf"
        assert app.screen._mode == MODE_AGENT
        assert manager.seat == 420
        assert saved == [420]
        await pilot.press("escape")
        assert app.screen is hub


@pytest.mark.asyncio
async def test_work_card_mouse_route_returns_to_same_boardroom():
    from maxpane_dashboard.screens.surf import MODE_WORK
    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        assert await pilot.click('#surfboard-card-work')
        await pilot.pause()
        assert isinstance(app.screen, SurfScreen) and app.screen._mode == MODE_WORK
        assert app.screen.return_context == 'surfboard'
        await pilot.press('escape')
        await pilot.pause()
        assert app.screen is hub


async def test_work_card_loads_only_when_open_and_cancels_on_return(work_manager):
    manager, _ = work_manager
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def jobs(*, limit):
        if manager._hub_active:
            assert not manager._work_active
            return []  # Bounded card discovery does not activate the Work board.
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    manager.swarm_client.fetch_jobs.side_effect = jobs
    app, _ = hub_app()
    app._surf_manager = manager
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        manager.swarm_client.fetch_jobs.assert_awaited_once_with(limit=100)
        assert manager._work_reader.task is None
        await pilot.click('#surfboard-card-work')
        await asyncio.wait_for(entered.wait(), 2)
        await pilot.pause()
        assert app.screen._mode == MODE_WORK
        pending = manager._work_reader.task
        assert pending is not None and not pending.cancelling()
        await pilot.press('escape')
        await asyncio.wait_for(cancelled.wait(), 2)
        await pilot.pause()
        assert manager._hub_active and not manager._work_active
        assert pending.cancelled()
        entered.clear()
        await pilot.click('#surfboard-card-work')
        await asyncio.wait_for(entered.wait(), 2)
        assert manager._work_reader.task is not pending
        await pilot.press('escape')
        await pilot.press('m')
        await pilot.pause()
        assert isinstance(app.screen, GameSelectScreen)
        assert pending.cancelled()


async def test_oracles_card_click_opens_native_dashboard_and_escape_retains_card():
    from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        card = hub.query_one('#surfboard-card-oracles', SurfboardCard)
        await pilot.click(card)
        await pilot.pause()
        assert isinstance(app.screen, SurfScreen)
        assert app.screen._mode == MODE_ORACLES
        assert app.screen.return_context == 'surfboard'
        await pilot.press('escape')
        assert app.screen is hub
        assert hub.query_one('#surfboard-card-oracles') is card


async def test_loading_repaints_completed_cache_without_offering_more_reads():
    from copy import deepcopy
    from unittest.mock import AsyncMock, Mock
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload, HubPayloadManager
    from tests.widgets.test_card_loading import face
    payload = hub_payload()
    loading = deepcopy(payload)
    next(c for c in loading['surfboard_cards'] if c['key'] == 'pool4')['status'] = 'loading'
    manager = HubPayloadManager(loading)
    manager.fetch_hub_snapshot = AsyncMock(return_value=loading)
    manager.get_hub_snapshot = Mock(return_value=payload)
    app = HubHarness(loading)
    app.hub = SurfboardScreen(manager)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.hub
        hub._age_timer.pause()
        hub._refresh_timer.pause()
        card = hub.query_one('#surfboard-card-pool4')
        assert hub._loading and card.data['status'] == 'loading'
        assert 'loading' not in face(app, card) and '1 sIMD =' in face(app, card)
        offered = manager.fetch_hub_snapshot.await_count
        hub._tick_terminal_age()
        await pilot.pause()
        assert 'loading' not in face(app, card) and '1 sIMD =' in face(app, card)
        assert not hub._loading
        assert manager.get_hub_snapshot.call_count == 2  # entry cache + completed read
        assert manager.fetch_hub_snapshot.await_count == offered
        hub._tick_terminal_age()
        await pilot.pause()
        assert manager.get_hub_snapshot.call_count == 2
        hub.action_refresh()
        await pilot.pause()
        assert manager.fetch_hub_snapshot.await_count == offered + 1
