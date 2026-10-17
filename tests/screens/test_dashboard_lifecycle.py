"""Visible-scope ownership, immediate retained paint and cancellation barriers."""
import asyncio

from textual.app import App
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.status_bar import StatusBar


class Provider:
    def __init__(self):
        self.scope = None
        self.reads = []
        self.started = asyncio.Queue()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.finalize = asyncio.Event()
        self.finalize.set()
        self.cached = 'retained 42'

    def set_active_view(self, view):
        self.scope = view

    async def drain_reads(self):
        pass

    def get_snapshot(self):
        return {'value': self.cached}

    async def fetch_and_compute(self):
        scope = self.scope
        self.reads.append(scope)
        self.started.put_nowait(scope)
        try:
            await self.release.wait()
            self.cached = f'fresh {scope}'
            return self.get_snapshot()
        finally:
            self.cancelled.set()
            await self.finalize.wait()


class Board(DashboardScreen):
    GAME_NAME = 'board'
    REFRESH_WORKER_NAME = 'lifecycle-board'

    def __init__(self, manager):
        super().__init__(manager)
        self._mode = 'a'

    def compose(self):
        yield Static('not painted', id='value')
        yield StatusBar()

    def _update_title(self, data):
        self.query_one('#value', Static).update(data['value'])


class Harness(App):
    def __init__(self, provider):
        super().__init__()
        self.board = Board(provider)

    def on_mount(self):
        self.push_screen(self.board)


def painted(board):
    return '\n'.join(strip.text for strip in board._compositor.render_strips())


async def test_entry_paints_retained_data_while_first_request_is_blocked():
    provider = Provider()
    app = Harness(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        assert await asyncio.wait_for(provider.started.get(), 2) == 'a'
        await pilot.pause()
        assert 'retained 42' in painted(app.board)
        assert 'loading' in painted(app.board).splitlines()[-1]
        assert app.board._poll_interval == 30
        provider.release.set()
        await app.workers.wait_for_complete()


async def test_suspension_cancels_request_and_reopen_fetches_immediately():
    provider = Provider()
    app = Harness(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await asyncio.wait_for(provider.started.get(), 2)
        await app.push_screen(Screen())
        await asyncio.wait_for(provider.cancelled.wait(), 2)
        assert provider.scope is None
        assert app.board._refresh_timer is None
        assert app.board._loading_timer is None
        assert provider.reads == ['a']
        app.pop_screen()
        assert await asyncio.wait_for(provider.started.get(), 2) == 'a'
        await pilot.pause()
        assert 'retained 42' in painted(app.board)
        assert provider.reads == ['a', 'a']
        provider.release.set()
        await app.workers.wait_for_complete()


async def test_body_switch_drains_old_worker_before_starting_new_scope():
    provider = Provider()
    app = Harness(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await asyncio.wait_for(provider.started.get(), 2)
        provider.finalize.clear()
        app.board._mode = 'b'
        app.board.restart_view()
        await asyncio.wait_for(provider.cancelled.wait(), 2)
        await pilot.pause()
        assert provider.reads == ['a']
        assert app.board._refresh_in_flight
        provider.finalize.set()
        assert await asyncio.wait_for(provider.started.get(), 2) == 'b'
        assert app.board._refresh_in_flight
        await pilot.pause()
        assert 'loading' in painted(app.board).splitlines()[-1]
        provider.release.set()
        await app.workers.wait_for_complete()
        app.board._tick_loading()
        await pilot.pause()
        assert 'fresh b' in painted(app.board)
        assert 'loading' not in painted(app.board)


async def test_completed_fetch_is_replayed_when_manager_has_no_snapshot_method():
    provider = Provider()
    provider.get_snapshot = None
    async def fetch():
        provider.started.put_nowait(provider.scope)
        await provider.release.wait()
        return {'value': 'last completed 17'}
    provider.fetch_and_compute = fetch
    provider.release.set()
    app = Harness(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        await provider.started.get()
        await app.push_screen(Screen())
        provider.release.clear()
        app.board.query_one('#value', Static).update('cleared by layout')
        app.pop_screen()
        await asyncio.wait_for(provider.started.get(), 2)
        await pilot.pause()
        assert 'last completed 17' in painted(app.board)
        provider.release.set()
        await app.workers.wait_for_complete()
