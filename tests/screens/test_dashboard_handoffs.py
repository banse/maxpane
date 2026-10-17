"""Navigation must transfer read ownership before a retired screen unmounts."""
import asyncio
import pytest
from textual.app import App
from textual.widgets import Static
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.screens.swarm_token_detail import SwarmTokenScreen
from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.data.test_detail_lifecycle import Market
from tests.screens.test_dashboard_lifecycle import Provider, Board, Harness

@pytest.mark.asyncio
async def test_separate_screen_drains_old_scope_before_new_fetch():
    first, second = Provider(), Provider()
    app = Harness(first)
    async with app.run_test(size=(149,45)) as pilot:
        await asyncio.wait_for(first.started.get(),2)
        first.finalize.clear()
        board2 = Board(second)
        try:
            await app.push_screen(board2)
            await asyncio.wait_for(first.cancelled.wait(),2)
            await pilot.pause()
            assert second.reads == [], 'new board started while old request finalizer is blocked'
        finally:
            first.finalize.set()
            first.release.set()
            second.release.set()
            await asyncio.gather(*(worker.wait() for worker in app.workers), return_exceptions=True)

class Overview(Market):
    def __init__(self):
        super().__init__()
        self.active = None
        self.reads = []
    def set_active_view(self, view):
        super().set_active_view(view)
        self.active=view
    def get_snapshot(self):
        return {}
    async def fetch_and_compute(self):
        self.reads.append(self.active)
        return {}
class OverviewScreen(DashboardScreen):
    GAME_NAME='swarm-tokens'
    def compose(self):
        yield Static('overview')
        yield StatusBar()
class ReturnApp(App):
    def __init__(self, manager):
        super().__init__()
        self.board=OverviewScreen(manager)
    def on_mount(self):
        self.push_screen(self.board)
@pytest.mark.asyncio
async def test_token_close_cannot_deactivate_resumed_overview():
    market=Overview()
    app=ReturnApp(market)
    async with app.run_test(size=(149,45)) as pilot:
        await app.workers.wait_for_complete()
        detail=SwarmTokenDetailManager(market,market.token)
        await app.push_screen(SwarmTokenScreen(detail))
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.pop_screen()
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert market.active == 'swarm-tokens', market.views


async def test_completed_screen_worker_still_drains_detached_manager_reads():
    class Detached(Provider):
        task = None

        async def fetch_and_compute(self):
            self.task = asyncio.create_task(super().fetch_and_compute())
            return self.get_snapshot()

        def set_active_view(self, view):
            super().set_active_view(view)
            if view is None and self.task is not None:
                self.task.cancel()

        async def drain_reads(self):
            if self.task is not None and self.scope is None:
                await asyncio.gather(self.task, return_exceptions=True)

    first, second = Detached(), Provider()
    app = Harness(first)
    async with app.run_test(size=(149, 45)) as pilot:
        await asyncio.wait_for(first.started.get(), 2)
        await app.workers.wait_for_complete()
        first.finalize.clear()
        try:
            await app.push_screen(Board(second))
            await asyncio.wait_for(first.cancelled.wait(), 2)
            await pilot.pause()
            assert not second.reads
            assert 'retained 42' in '\n'.join(s.text for s in app.screen._compositor.render_strips())
            first.finalize.set()
            assert await asyncio.wait_for(second.started.get(), 2) == 'a'
        finally:
            first.finalize.set()
            first.release.set()
            second.release.set()
            await app.workers.wait_for_complete()


async def test_native_board_timer_cannot_offer_before_navigation_barrier():
    from unittest.mock import Mock
    from maxpane_dashboard.screens.surf import SurfScreen
    from tests.screens.test_surf_screen import _FakeManager, _frozen_payload

    first = Provider()
    manager = _FakeManager(_frozen_payload())
    manager.set_launch_contribution_active = Mock()
    manager.offer_launch_contribution = Mock()
    manager.get_launch_contribution_snapshot = Mock(return_value={})
    screen = SurfScreen(manager)
    screen._mode = 'board'
    app = Harness(first)
    async with app.run_test(size=(149, 45)) as pilot:
        await asyncio.wait_for(first.started.get(), 2)
        first.finalize.clear()
        try:
            await app.push_screen(screen)
            await asyncio.wait_for(first.cancelled.wait(), 2)
            await pilot.pause()
            screen._tick_launch_contribution()
            manager.offer_launch_contribution.assert_not_called()
            first.finalize.set()
            await screen._refresh_worker.wait()
            screen._tick_launch_contribution()
            manager.offer_launch_contribution.assert_called()
        finally:
            first.finalize.set()
            first.release.set()
            await asyncio.gather(*(w._task for w in app.workers if w._task), return_exceptions=True)
