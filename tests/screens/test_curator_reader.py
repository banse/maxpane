"""CURATOR's local list queries obey the reader boundary and UI generations."""
import asyncio
import threading

import pytest

from textual.widgets import Input

from maxpane_dashboard.data.curator_list_filters import empty_filter_values, parse_filter_values
from maxpane_dashboard.data.curator_manager import FilteredListResult
from maxpane_dashboard.data.reader import ReaderRuntime
from maxpane_dashboard.screens.curator import CuratorScreen, CuratorListFilterEditor, CuratorRawList
from tests.screens.test_curator_screen import _FakeManager, _ThemedHarness, _list_payload, _screen_text


def filter_spec(points):
    return parse_filter_values({**empty_filter_values(), 'points_min': str(points)})


class BlockedFilters(_FakeManager):
    def __init__(self, payload, loop):
        super().__init__(payload)
        self.loop = loop
        self.started = asyncio.Event()
        self.release = threading.Event()
        self.expired = False
        self.threads = []
        self.filter_calls = 0

    def filtered_list_rows(self, *_args, **_kwargs):
        self.filter_calls += 1
        self.threads.append(threading.get_ident())
        if self.filter_calls == 1:
            self.loop.call_soon_threadsafe(self.started.set)
            self.expired |= not self.release.wait(5)
        rows = [dict(self._payload['leaderboard_rows'][0],
                     name='old-filter.eth' if self.filter_calls == 1 else 'current-filter.eth')]
        return FilteredListResult(rows, True, None)


async def test_blocked_filter_keeps_editor_responsive_and_discards_superseded_result(tmp_path, monkeypatch):
    payload = _list_payload(3)
    backend = BlockedFilters(payload, asyncio.get_running_loop())
    runtime = ReaderRuntime()
    handle = runtime.register('curator', lambda: backend)
    screen = CuratorScreen(handle, export_dir=tmp_path)
    # Isolate user-triggered list queries from periodic dashboard refresh.
    monkeypatch.setattr(screen, 'start_refresh', lambda: None)
    screen._list_source_pending = False
    screen._title_data = payload
    stored = []
    completed = asyncio.Event()
    original_store = screen._store_filter_result
    def store(spec, result):
        stored.append(spec)
        original_store(spec, result)
        completed.set()
    monkeypatch.setattr(screen, '_store_filter_result', store)
    app = _ThemedHarness(screen)
    old, current = filter_spec(1), filter_spec(2)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            try:
                screen._apply_filter(old)
                await asyncio.wait_for(backend.started.wait(), 2)
                assert backend.threads == [runtime.thread.ident]
                await pilot.press('f')
                editor = screen.query_one(CuratorListFilterEditor)
                assert screen._filter_editor_open
                editor.query_one('#filter-points-min', Input).value = '7'
                await pilot.pause()
                assert editor.query_one('#filter-points-min', Input).value == '7'
                assert not backend.expired and not backend.release.is_set()

                screen._apply_filter(current)
                screen._filter_editor_open = False
                screen._show_list_view()
                backend.release.set()
                await asyncio.wait_for(completed.wait(), 2)
                await pilot.pause()
                assert stored and all(spec == current for spec in stored)
                assert backend.threads == [runtime.thread.ident, runtime.thread.ident]
                assert 'current-filter.eth' in _screen_text(app)
                assert 'old-filter.eth' not in _screen_text(app)
            finally:
                backend.release.set()
    finally:
        backend.release.set()
        await runtime.close()


async def test_local_export_load_never_blocks_ui_and_cannot_paint_after_leaving(tmp_path, monkeypatch):
    from textual.screen import Screen
    from maxpane_dashboard.data.curator_list_source import ExportListResult
    from maxpane_dashboard.screens import curator as module

    payload = _list_payload(3)
    runtime = ReaderRuntime()
    handle = runtime.register('curator', lambda: _FakeManager(payload))
    screen = CuratorScreen(handle, export_dir=tmp_path)
    monkeypatch.setattr(screen, 'start_refresh', lambda: None)
    screen._list_source_pending = False
    screen._title_data = payload
    entered, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    expired, threads, applied = [], [], []
    def load(*_args, **_kwargs):
        threads.append(threading.get_ident())
        loop.call_soon_threadsafe(entered.set)
        expired.append(not release.wait(5))
        loop.call_soon_threadsafe(finished.set)
        return ExportListResult(payload['leaderboard_rows'], False, None, None, None)
    monkeypatch.setattr(module, 'load_export_list', load)
    monkeypatch.setattr(screen, '_apply_list_source', lambda *_args: applied.append(True))
    app = _ThemedHarness(screen)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            try:
                screen._load_selected_list_source()
                await asyncio.wait_for(entered.wait(), 2)
                assert threads[0] != threading.get_ident()
                await pilot.press('f')
                assert screen._filter_editor_open
                await app.push_screen(Screen())
                release.set()
                await asyncio.wait_for(finished.wait(), 2)
                await pilot.pause()
                assert expired == [False]
                assert applied == []
            finally:
                release.set()
    finally:
        release.set()
        await runtime.close()


@pytest.mark.parametrize('cached_failure', [False, True])
async def test_export_and_cached_names_read_the_manager_only_on_reader(tmp_path, monkeypatch, cached_failure):
    class NamesManager(_FakeManager):
        def __init__(self, payload):
            super().__init__(payload)
            self.owner_calls = []
        def full_list_rows(self, *, cleaned):
            self.owner_calls.append(('full', threading.get_ident()))
            return super().full_list_rows(cleaned=cleaned)
        def cached_list_rows_with_ens(self, rows):
            self.owner_calls.append(('cached', threading.get_ident()))
            if cached_failure:
                raise RuntimeError('cached names temporarily unavailable')
            return [dict(row, name='reader-name.eth') for row in rows]

    payload = _list_payload(3)
    for row in payload['leaderboard_rows']:
        row['name'] = 'saved.eth'
    backend = NamesManager(payload)
    runtime = ReaderRuntime()
    handle = runtime.register('curator', lambda: backend)
    screen = CuratorScreen(handle, export_dir=tmp_path)
    monkeypatch.setattr(screen, 'start_refresh', lambda: None)
    screen._list_source_pending = False
    screen._title_data = payload
    app = _ThemedHarness(screen)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            screen._dispatch(CuratorRawList, payload)
            await screen._export_and_reload_list(False, CuratorRawList, 'raw', 0)
            await pilot.pause()
            assert [name for name, _thread in backend.owner_calls] == ['full', 'cached']
            assert all(thread == runtime.thread.ident for _name, thread in backend.owner_calls)
            assert ('saved.eth' if cached_failure else 'reader-name.eth') in _screen_text(app)
            assert screen.query_one(CuratorRawList)._payload['complete']
            assert (tmp_path / 'curator_raw_list.json').exists()
    finally:
        await runtime.close()
