"""Published reader snapshots drive local paints without UI acquisition timers."""
import asyncio
import threading

from textual.app import App
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.reader import ReaderRuntime
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen


class Board(DashboardScreen):
    GAME_NAME = 'local-snapshot'
    REFRESH_WORKER_NAME = 'local-snapshot-paint'

    def __init__(self, handle):
        super().__init__(handle)
        self.paints = asyncio.Queue()

    def compose(self):
        yield Static('pending', id='value')

    def _update_title(self, data):
        if data.get('value'):
            self.query_one('#value', Static).update(data['value'])
            self.call_after_refresh(self.paints.put_nowait, data['value'])


class Harness(App):
    def __init__(self, handle):
        super().__init__()
        self.board = Board(handle)

    def on_mount(self):
        self.push_screen(self.board)


async def test_reader_publications_paint_without_ui_fetch_or_payload_copy():
    copies = []
    ui_thread = threading.get_ident()

    class Payload(dict):
        def __deepcopy__(self, memo):
            copies.append(threading.get_ident())
            assert threading.get_ident() != ui_thread, 'payload copied on UI'
            return Payload(self)

    class Manager:
        value = 0

        async def fetch_and_compute(self):
            self.value += 1
            return Payload(value=f'snapshot {self.value}')

        async def close(self):
            pass

    runtime = ReaderRuntime(poll_interval=60)
    handle = runtime.register('board', Manager)
    app = Harness(handle)
    try:
        async with app.run_test(size=(149, 45)):
            assert await asyncio.wait_for(app.board.paints.get(), 3) == 'snapshot 1'
            assert app.board._refresh_timer is None
            handle.request_refresh()
            while await asyncio.wait_for(app.board.paints.get(), 3) != 'snapshot 2':
                pass
            # Painting a new revision must not request snapshot 3.
            before = await handle.invoke('__getattribute__', 'value')
            app.board._tick_loading()
            await app.workers.wait_for_complete()
            assert await handle.invoke('__getattribute__', 'value') == before == 2
            assert copies and set(copies) != {ui_thread}
    finally:
        await runtime.close()


async def test_reopen_uses_local_snapshot_while_reader_refresh_is_blocked():
    release = threading.Event()
    loop = asyncio.get_running_loop()
    blocked = asyncio.Event()

    class Manager:
        calls = 0

        async def fetch_and_compute(self):
            self.calls += 1
            if self.calls > 1:
                loop.call_soon_threadsafe(blocked.set)
                assert release.wait(5), 'reader was never released'
            return {'value': f'published {self.calls}'}

        async def close(self):
            pass

    runtime = ReaderRuntime(poll_interval=60)
    handle = runtime.register('board', Manager)
    app = Harness(handle)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            assert await asyncio.wait_for(app.board.paints.get(), 3) == 'published 1'
            await app.push_screen(Screen())
            app.pop_screen()
            await asyncio.wait_for(blocked.wait(), 3)
            await pilot.pause()
            assert 'published 1' in '\n'.join(s.text for s in app.board._compositor.render_strips())
            assert handle.is_loading()
            release.set()
    finally:
        release.set()
        await runtime.close()


async def test_nft_local_filters_work_before_first_reader_publication():
    from maxpane_dashboard.screens.surf_nft import SurfNftScreen
    from tests.screens.test_reader_responsiveness import BlockedRead, LocalManager

    gate = BlockedRead('constructor')
    runtime = ReaderRuntime()
    handle = runtime.register('nft', lambda: LocalManager(gate))
    app = Harness(handle)
    app.board = SurfNftScreen(handle)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            await asyncio.wait_for(gate.entered.wait(), 3)
            assert handle.get_snapshot() is None
            app.board.action_stage()
            app.board.action_chain()
            app.board.action_sort()
            await pilot.pause()
            assert app._exception is None
            gate.release.set()
    finally:
        gate.release.set()
        await runtime.close()
