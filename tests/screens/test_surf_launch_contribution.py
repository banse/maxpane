"""Actual BOARD title clicks and background-source visibility; no network."""
from unittest.mock import Mock
import pytest

from textual.screen import Screen
from textual.widgets import DataTable

from maxpane_dashboard.screens.surf import SurfScreen, SURF_BOARD_FULL_LAYOUT_COLUMNS
from maxpane_dashboard.widgets.surf.swarm_leaderboard import SurfSwarmLeaderboard
from maxpane_dashboard.widgets.surf.swarm_fleet import SurfSwarmFleet
from maxpane_dashboard.widgets.surf.swarm_board_hero import SurfSwarmBoardHero
from tests.screens._sweeps import boundary_set
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
        "loaded": 6, "total": 317, "detail": "loading 6/317 production launches",
        "summary": {"state":"pending","seats":None,"jobs":None}})
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    monkeypatch.setattr(screen, "select_seat", Mock())
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("b")
        await pilot.pause()
        manager.set_launch_contribution_active.assert_called_with(True)
        assert screen._board_view == 'recorded'
        screen._tick_launch_contribution()
        await pilot.pause()
        launches_card = screen.query_one(SurfSwarmBoardHero).query_one('#hero-launches')
        assert 'loading' in _region_text(pilot.app, launches_card)
        widget = screen.query_one(SurfSwarmLeaderboard)
        title = widget.query_one(".panel-title")
        title_text = _region_text(pilot.app, title)
        await pilot.click(title, offset=(title_text.index("launch contributors"), 0))
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
            "detail": "all 317 production launches",
            "summary": {"state":"ok","read_ts":1_790_000_000.,"seats":1,"jobs":4,
                        "claude":1,"codex":0,"runtime_known":1,
                        "runtime_state":"ok","runtime_read_ts":1_790_000_001.,
                        "percent":25.,"total_seats":4,"records_state":"ok",
                        "records_read_ts":1_790_000_002.}}
        screen._tick_launch_contribution()
        await pilot.pause()
        assert "claude" in _region_text(pilot.app, widget)
        assert '25%' in _region_text(pilot.app, launches_card)
        assert '1 of 4 recorded seats' in launches_card.tooltip.plain
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
        manager.set_launch_contribution_active.assert_called_with(True)
        assert "55" in _region_text(pilot.app, widget)


async def test_launch_columns_show_current_model_and_job_split_at_owner_size():
    manager = _FakeManager(_frozen_payload(swarm_board_rows=[
        {"token_id": 401, "rank": 1, "runtime": "claude", "live_state": "working", "working": 2}],
        swarm_launch_contribution={
            "state": "ok", "rows": [{"rank": 1, "token_id": 401, "jobs": 13, "launches": 12,
                "build_jobs": 4, "review_jobs": 10, "advertised_models": [
                    {"model": "claude-fable-5-1", "effort": "high"},
                    {"model": "gpt-6-astra", "effort": "xhigh"}]}],
            "read_ts": 1_790_000_000., "loaded": 317, "total": 317,
            "detail": "317 live production launches · all history"}))
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    async with _ThemedHarness(screen).run_test(size=(149, 45)) as pilot:
        await screen._do_refresh()
        await pilot.press("b")
        screen.action_board_view("launches")
        await pilot.pause()
        widget = screen.query_one(SurfSwarmLeaderboard)
        text = _region_text(pilot.app, widget)
        for word in ("model", "effort", "build/review", "fable 5.1 +1", "high", "4 / 10", "claude", "working 2"):
            assert word in text
        table = widget.query_one(DataTable)
        assert table.virtual_size.width <= table.scrollable_content_region.width
        assert screen.query_one(SurfSwarmFleet).size.width > 37
        assert table.scrollable_content_region.width - table.virtual_size.width <= 2
        assert "‹ widen" not in text


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
            "#▲", "seat", "jobs", "launches", "build/review", "model", "effort", "runtime", "state")
        assert table.virtual_size.width <= table.scrollable_content_region.width
        text = _region_text(pilot.app, widget)
        assert "LEADERBOARD · recorded seats · launch contributors" in text
        assert "317 live production launches · all history" in text
        assert "‹ widen" not in text
        assert widget.region.bottom <= screen.query_one("StatusBar").region.y


@pytest.mark.sweep
@pytest.mark.parametrize("width",boundary_set(SURF_BOARD_FULL_LAYOUT_COLUMNS,60,225,72,129,142,149))
async def test_launch_column_tiers_keep_geometry_without_widen_hint(width):
    # Measured in the real BOARD with a scrolling table: tight stops clipping
    # at 72, compact begins at 129, and all nine columns arrive at 142.
    launches=[dict(rank=i+1,token_id=i+1,jobs=13,launches=12,build_jobs=4,review_jobs=10,
                   advertised_models=[dict(model='claude-fable-5-1',effort='high'),
                                      dict(model='gpt-6-astra',effort='xhigh')]) for i in range(40)]
    workers=[dict(rank=i+1,token_id=i+1,runtime='claude',live_state='working',working=2)
             for i in range(40)]
    manager=_FakeManager(_frozen_payload(swarm_board_rows=workers,swarm_launch_contribution={
        "state":"ok","rows":launches,"read_ts":1_790_000_000.,"loaded":318,"total":318,
        "detail":"318 live production launches · all history"}))
    screen=SurfScreen(manager,poll_interval=30,name='surf')
    async with _ThemedHarness(screen).run_test(size=(width,45)) as pilot:
        await screen._do_refresh()
        await pilot.press('b')
        screen.action_board_view('launches')
        await pilot.pause()
        widget=screen.query_one(SurfSwarmLeaderboard)
        table=widget.query_one(DataTable)
        assert table.show_vertical_scrollbar
        clipped=table.virtual_size.width>table.scrollable_content_region.width
        title=_region_text(pilot.app,widget.query_one('.panel-title'))
        all_keys=('rank','seat','jobs','launches','build_review','model','effort','runtime','state')
        assert '‹' not in title and 'widen' not in title
        if width>=142:
            assert widget._keys==all_keys and not clipped
            text=_region_text(pilot.app,widget)
            for word in ('build/review','model','effort','fable 5.1 +1','high','4 / 10','claude','working 2'):
                assert word in text
        elif width>=129:
            assert widget._keys==tuple(key for key in all_keys if key!='runtime')
        else:
            assert widget._keys==('rank','seat','jobs','launches')
        assert clipped==(width<72)
        if width == SURF_BOARD_FULL_LAYOUT_COLUMNS:
            assert widget._keys == all_keys and not clipped
        elif width == SURF_BOARD_FULL_LAYOUT_COLUMNS - 1:
            assert widget._keys != all_keys


@pytest.mark.parametrize('count',[10_000,100_000])
async def test_launch_role_counts_keep_every_digit_at_board_pin(count):
    manager=_FakeManager(_frozen_payload(swarm_launch_contribution={
        'state':'ok','rows':[dict(rank=1,token_id=7,jobs=count,launches=10_000,
            build_jobs=count,review_jobs=count,advertised_models=[])],
        'read_ts':1_790_000_000.,'loaded':10_000,'total':10_000,
        'detail':'all production launches'}))
    screen=SurfScreen(manager,poll_interval=30,name='surf')
    async with _ThemedHarness(screen).run_test(size=(143,35)) as pilot:
        await screen._do_refresh()
        await pilot.press('b')
        screen.action_board_view('launches');await pilot.pause()
        widget=screen.query_one(SurfSwarmLeaderboard)
        row=next(line for line in _region_text(pilot.app,widget).splitlines() if '#7 ' in line)
        assert f'{count}/{count}' in row.replace(' ','')
        assert '…' not in row and '‹' not in _region_text(pilot.app,widget)
        table=widget.query_one(DataTable)
        assert table.virtual_size.width<=table.scrollable_content_region.width
