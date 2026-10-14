"""Actual BOARD title clicks and background-source visibility; no network."""
from unittest.mock import Mock
import pytest

from textual.screen import Screen
from textual.widgets import DataTable

from maxpane_dashboard.screens.surf import SurfScreen
from maxpane_dashboard.widgets.surf.swarm_leaderboard import SurfSwarmLeaderboard
from tests.screens.test_surf_screen import (
    _FakeManager, _ThemedHarness, _frozen_payload, _region_text,
)


async def test_launch_tab_click_schedules_progress_preserves_rows_and_opens_seat(monkeypatch):
    manager = _FakeManager(_frozen_payload(swarm_board_rows=[
        {"token_id": 401, "rank": 1, "accepted": 55, "runtime": "claude"}]))
    manager.set_launch_contribution_active = Mock()
    manager.offer_launch_contribution = Mock()
    manager.get_launch_contribution_snapshot = Mock(return_value={
        "state": "pending", "rows": None, "read_ts": None,
        "loaded": 6, "total": 317, "detail": "loading 6/317 production launches"})
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    monkeypatch.setattr(screen, "select_seat", Mock())
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("b")
        await pilot.pause()
        widget = screen.query_one(SurfSwarmLeaderboard)
        title = widget.query_one(".panel-title")
        title_text = _region_text(pilot.app, title)
        await pilot.click(title, offset=(title_text.index("launch contribution"), 0))
        await pilot.pause()
        assert widget._view_mode == "launches"
        manager.set_launch_contribution_active.assert_called_with(True)
        screen._tick_launch_contribution()
        await pilot.pause()
        assert "loading 6/317" in _region_text(pilot.app, widget)
        assert screen._launch_contribution_timer is not None
        manager.get_launch_contribution_snapshot.return_value = {
            "state": "ok", "rows": [{"token_id": 401, "rank": 1, "jobs": 4, "launches": 3}],
            "read_ts": 1_790_000_000., "loaded": 317, "total": 317,
            "detail": "all 317 production launches"}
        screen._tick_launch_contribution()
        await pilot.pause()
        assert "claude" in _region_text(pilot.app, widget)
        widget.query_one(DataTable).focus()
        await pilot.press("enter")
        screen.select_seat.assert_called_once_with(401)
        await pilot.app.push_screen(Screen())
        await pilot.pause()
        manager.set_launch_contribution_active.assert_called_with(False)
        assert screen._launch_contribution_timer is None
        pilot.app.pop_screen()
        await pilot.pause()
        manager.set_launch_contribution_active.assert_called_with(True)
        title_text = _region_text(pilot.app, title)
        await pilot.click(title, offset=(title_text.index("recorded seats"), 0))
        await pilot.pause()
        assert widget._view_mode == "recorded"
        manager.set_launch_contribution_active.assert_called_with(False)
        assert "55" in _region_text(pilot.app, widget)


@pytest.mark.parametrize("size", [(143, 35), (149, 45), (225, 61)])
async def test_launch_tab_fits_board_pin_and_wider_sizes(size):
    manager = _FakeManager(_frozen_payload(swarm_launch_contribution={
        "state": "ok", "rows": [{"rank": 1, "token_id": 401, "jobs": 13, "launches": 12}],
        "read_ts": 1_790_000_000., "loaded": 317, "total": 317,
        "detail": "317 live production launches · all history"}))
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    async with _ThemedHarness(screen).run_test(size=size) as pilot:
        await screen._do_refresh()
        await pilot.press("b")
        screen.action_board_view("launches")
        await pilot.pause()
        widget = screen.query_one(SurfSwarmLeaderboard)
        table = widget.query_one(DataTable)
        assert tuple(str(c.label) for c in table.ordered_columns) == (
            "#▲", "seat", "jobs", "launches", "runtime", "state")
        assert table.virtual_size.width <= table.scrollable_content_region.width
        text = _region_text(pilot.app, widget)
        assert "LEADERBOARD · recorded seats · launch contribution" in text
        assert "317 live production launches · all history" in text
        assert "‹ widen" not in text
        assert widget.region.bottom <= screen.query_one("StatusBar").region.y
