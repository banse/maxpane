"""The real Textual UI stays usable during synchronous reader-side work.

No network, private cache, or sleep-based readiness: a thread event holds the
reader and observable screen/animation events prove that the UI still runs.
"""
import asyncio
import threading

import pytest
from textual.app import App
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.reader import ReaderRuntime
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.status_bar import StatusBar


class BlockedRead:
    def __init__(self, stage):
        self.stage = stage
        self.loop = asyncio.get_running_loop()
        self.entered = asyncio.Event()
        self.release = threading.Event()
        self.thread = None
        self.expired = False

    def block(self, stage):
        if stage != self.stage:
            return
        self.thread = threading.get_ident()
        self.loop.call_soon_threadsafe(self.entered.set)
        # A broken implementation running on the UI thread must fail rather
        # than hang pytest forever. Expiry is never accepted as a release.
        self.expired |= not self.release.wait(timeout=5)


class LocalManager:
    def __init__(self, gate):
        gate.block('constructor')
        self.gate = gate
        self.value = 'retained local data'
        self.view = None

    def set_active_view(self, view):
        self.view = view

    def get_snapshot(self):
        return {'value': self.value}

    async def fetch_and_compute(self):
        self.gate.block('compute')
        self.save_cache()
        self.value = 'reader completed'
        return self.get_snapshot()

    def save_cache(self):
        self.gate.block('save')

    async def close(self):
        pass


class ObservedStatusBar(StatusBar):
    def __init__(self):
        super().__init__()
        self.frames = asyncio.Queue()

    def _tick_loading(self):
        previous = self._loading_frame
        super()._tick_loading()
        if previous != self._loading_frame:
            self.frames.put_nowait(self._loading_frame)


class NavigationTarget(Screen):
    def compose(self):
        yield Static('Navigation remains responsive')


class ResponsiveBoard(DashboardScreen):
    GAME_NAME = 'reader-probe'
    REFRESH_WORKER_NAME = 'reader-probe-refresh'
    BINDINGS = [Binding('v', 'local_change', show=False),
                Binding('n', 'navigate', show=False)]

    def __init__(self, handle):
        super().__init__(handle)
        self.local_changed = asyncio.Event()

    def compose(self):
        yield Static('Waiting for reader', id='value')
        yield Static('', id='local-change')
        yield ObservedStatusBar()

    def _update_title(self, data):
        self.query_one('#value', Static).update(data.get('value', 'Waiting for reader'))

    def action_local_change(self):
        self.query_one('#local-change', Static).update('Local key handled')
        self.call_after_refresh(self.local_changed.set)

    def action_navigate(self):
        self.app.push_screen(NavigationTarget())


class ResponsiveApp(App):
    def __init__(self, handle):
        super().__init__()
        self.board = ResponsiveBoard(handle)

    def on_mount(self):
        self.push_screen(self.board)


def painted(screen):
    return '\n'.join(strip.text for strip in screen._compositor.render_strips())


@pytest.mark.parametrize('stage', ['constructor', 'compute', 'save'])
async def test_reader_blockage_preserves_animation_local_keys_and_navigation(stage):
    gate = BlockedRead(stage)
    runtime = ReaderRuntime(poll_interval=30, publish_interval=1.0)
    handle = runtime.register('reader-probe', lambda: LocalManager(gate))
    app = ResponsiveApp(handle)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            try:
                await asyncio.wait_for(gate.entered.wait(), timeout=2)
                assert gate.thread != threading.get_ident(), stage
                bar = app.board.query_one(ObservedStatusBar)
                first = await asyncio.wait_for(bar.frames.get(), timeout=2)
                second = await asyncio.wait_for(bar.frames.get(), timeout=2)
                assert first != second
                assert 'loading' in painted(app.board)
                assert not gate.release.is_set() and not gate.expired

                await pilot.press('v')
                await asyncio.wait_for(app.board.local_changed.wait(), timeout=2)
                assert 'Local key handled' in painted(app.board)

                await pilot.press('n')
                await pilot.pause()
                assert isinstance(app.screen, NavigationTarget)
                assert 'Navigation remains responsive' in painted(app.screen)
                assert not gate.release.is_set() and not gate.expired
            finally:
                gate.release.set()
    finally:
        gate.release.set()
        await runtime.close()
