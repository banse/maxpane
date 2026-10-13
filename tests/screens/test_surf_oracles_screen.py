"""Native oracle routing and cached selection lifecycle; no network."""
from unittest.mock import Mock

from textual.screen import Screen
from textual.widgets import Input

from maxpane_dashboard.screens.surf import SurfScreen
from tests.screens.test_surf_screen import _FakeManager, _ThemedHarness, _frozen_payload, _screen_text


async def test_oracles_mode_switches_native_body_and_source_lifecycle(monkeypatch):
    manager = _FakeManager(_frozen_payload())
    manager.set_oracles_active = Mock()
    screen = SurfScreen(manager)
    monkeypatch.setattr(screen, "start_refresh", Mock())
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("ctrl+o")
        assert screen._mode == "oracles"
        assert screen.query_one("SurfOraclesHero").display
        assert screen.query_one("SurfOraclesBody").display
        assert len([hero for hero in screen.query(".surf-hero") if hero.display]) == 1
        assert "ORACLES" in _screen_text(pilot.app)
        manager.set_oracles_active.assert_called_with(True)
        await pilot.app.push_screen(Screen())
        await pilot.pause()
        manager.set_oracles_active.assert_called_with(False)
        assert screen._oracles_timer is None
        pilot.app.pop_screen()
        await pilot.pause()
        manager.set_oracles_active.assert_called_with(True)
        await pilot.press("ctrl+o")
        assert screen._mode == "dashboard"
        manager.set_oracles_active.assert_called_with(False)
        assert screen._oracles_timer is None


async def test_oracles_find_filter_and_chain_preserve_input_typing(monkeypatch):
    screen = SurfScreen(_FakeManager(_frozen_payload()))
    monkeypatch.setattr(screen, "start_refresh", Mock())
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("ctrl+o", "/")
        assert isinstance(screen.focused, Input)
        await pilot.press(*"factors")
        assert screen.focused.value == "factors"
        await pilot.press("escape")
        assert screen._mode == "oracles"
        assert not isinstance(screen.focused, Input)
        await pilot.press("f", "c")
        assert not screen._record_filter_open
        await pilot.press("escape")
        assert screen._mode == "dashboard"


async def test_boardroom_oracles_shortcut_returns_to_boardroom():
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.screens.surfboard import SurfboardScreen

    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.press("ctrl+o")
        assert isinstance(app.screen, SurfScreen)
        assert app.screen._mode == "oracles"
        await pilot.press("escape")
        assert isinstance(app.screen, SurfboardScreen)


async def test_oracles_selection_and_answer_route_use_cached_data(monkeypatch):
    from maxpane_dashboard.screens.oracle_answer import OracleAnswerScreen
    from maxpane_dashboard.widgets.surf.oracles import SurfOraclesBody
    from scripts.surf_oracles_demo import MOCK_REQUESTS

    manager = _FakeManager(_frozen_payload())
    manager.set_oracle_request = Mock()
    manager.get_oracles_snapshot = Mock(return_value=None)
    screen = SurfScreen(manager)
    monkeypatch.setattr(screen, "start_refresh", Mock())
    screen.open_mode("oracles")
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        body = screen.query_one(SurfOraclesBody)
        identity = "00000000-0000-4000-8000-000000000001"
        body.post_message(SurfOraclesBody.RequestSelected(identity))
        await pilot.pause()
        manager.set_oracle_request.assert_called_once_with(identity)
        count = screen.start_refresh.call_count
        screen._tick_oracles()
        manager.get_oracles_snapshot.assert_called_once()
        assert screen.start_refresh.call_count == count
        row = MOCK_REQUESTS[1]["members"][0]
        body.post_message(SurfOraclesBody.AnswerSelected(row))
        await pilot.pause()
        assert isinstance(pilot.app.screen, OracleAnswerScreen)
        assert pilot.app.screen.row["submission_hash"] == row["submission_hash"]
        await pilot.press("escape")
        assert pilot.app.screen is screen
        assert screen._mode == "oracles"


def test_oracles_body_css_copies_agree():
    from tests.screens.test_surf_screen import _css_rules, _surf_stylesheet_block
    selector = "#surf-oracles-body"
    assert _css_rules(SurfScreen.DEFAULT_CSS)[selector] == _css_rules(_surf_stylesheet_block())[selector]
