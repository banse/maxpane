"""WORK body routing, source dispatch and keyboard behavior; no network."""
from unittest.mock import Mock

from textual.screen import Screen
from textual.widgets import Input

from maxpane_dashboard.screens.surf import SurfScreen
from tests.screens.test_surf_screen import (
    _FakeManager, _ThemedHarness, _frozen_payload, _screen_text,
)


async def test_work_mode_switches_hero_body_and_source_eligibility(monkeypatch):
    manager = _FakeManager(_frozen_payload())
    manager.set_work_active = Mock()
    screen = SurfScreen(manager)
    monkeypatch.setattr(screen, "start_refresh", Mock())
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("w")
        assert screen._mode == "work"
        assert screen.query_one("SurfWorkBody").display
        assert screen.query_one("SurfWorkHero").display
        assert not screen.query_one("SurfSwarmRackHero").display
        assert "WORK IN PROGRESS" in _screen_text(pilot.app)
        manager.set_work_active.assert_called_with(True)
        await pilot.app.push_screen(Screen())
        await pilot.pause()
        manager.set_work_active.assert_called_with(False)
        pilot.app.pop_screen()
        await pilot.pause()
        manager.set_work_active.assert_called_with(True)
        await pilot.press("w")
        assert screen._mode == "dashboard"
        manager.set_work_active.assert_called_with(False)


async def test_work_find_escape_and_filter_do_not_open_agent_filter(monkeypatch):
    screen = SurfScreen(_FakeManager(_frozen_payload()))
    monkeypatch.setattr(screen, "start_refresh", Mock())
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("w", "/")
        assert isinstance(screen.focused, Input)
        await pilot.press("w", "o", "r", "k", "f", "l", "o", "w")
        assert screen.focused.value == "workflow"
        await pilot.press("escape")
        assert screen._mode == "work"
        assert not isinstance(screen.focused, Input)
        await pilot.press("f")
        assert not screen._record_filter_open
        await pilot.press("escape")
        assert screen._mode == "dashboard"


async def test_work_native_route_returns_to_boardroom(monkeypatch):
    screen = SurfScreen(_FakeManager(_frozen_payload()))
    monkeypatch.setattr(screen, "start_refresh", Mock())
    screen.open_mode("work", return_context="surfboard")
    app = _ThemedHarness(screen)
    app.return_to_surfboard = Mock()
    async with app.run_test(size=(149, 45)) as pilot:
        assert screen._mode == "work"
        await pilot.press("escape")
        app.return_to_surfboard.assert_called_once()


async def test_boardroom_work_shortcut_uses_retained_surf_route():
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.screens.surfboard import SurfboardScreen

    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.press("w")
        assert isinstance(app.screen, SurfScreen)
        assert app.screen._mode == "work"
        await pilot.press("escape")
        assert isinstance(app.screen, SurfboardScreen)
