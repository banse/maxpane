"""The reader owns I/O and mutable managers; UI access stays local."""
import asyncio
from concurrent.futures import Future
import threading

import pytest

from maxpane_dashboard.data.reader import ReaderRuntime


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.001)


class Manager:
    def __init__(self, calls):
        self.calls = calls
        self.value = {'rows': [{'value': 1}]}
        self.view = None
        self.closed = False
        self.record('construct')

    def record(self, operation):
        self.calls.append((operation, threading.get_ident()))

    def set_active_view(self, view):
        self.record('set')
        self.view = view

    async def fetch_and_compute(self):
        self.record('fetch')
        return self.value

    def get_snapshot(self):
        self.record('project')
        return self.value

    def is_loading(self, view=None):
        return False

    def current_view(self):
        return self.view

    async def close(self):
        self.record('close')
        self.closed = True


async def test_factory_fetch_projection_and_close_have_one_reader_owner():
    calls, created = [], []
    runtime = ReaderRuntime()
    def factory():
        manager = Manager(calls)
        created.append(manager)
        return manager
    handle = runtime.register('one', factory)
    assert not calls and handle.get_snapshot() is None
    try:
        handle.set_active_view('one')
        await handle.fetch_and_compute()
        await eventually(lambda: handle.get_snapshot() is not None and not handle.is_loading())
        assert handle.get_snapshot()['rows'][0]['value'] == 1
        assert sum(name == 'fetch' for name, _ in calls) == 1
        handle.get_snapshot()['rows'][0]['value'] = 99
        assert created[0].value['rows'][0]['value'] == 1
    finally:
        await runtime.close()
    assert created[0].closed
    assert len({thread for _, thread in calls}) == 1
    assert calls[0][1] != threading.get_ident()
    assert not runtime.thread.is_alive()


async def test_blocking_constructor_does_not_block_local_reads_or_commands():
    entered, release = threading.Event(), threading.Event()
    def factory():
        entered.set()
        release.wait(3)
        return Manager([])
    runtime = ReaderRuntime()
    handle = runtime.register('one', factory)
    try:
        handle.set_active_view('one')
        await eventually(entered.is_set)
        assert handle.get_snapshot() is None
        assert handle.is_loading()
        handle.set_active_view(None)
        assert not handle.is_loading()
        release.set()
        await handle.drain_reads()
        assert handle.get_snapshot() is None
    finally:
        release.set()
        await runtime.close()


async def test_first_fetch_publishes_persisted_snapshot_before_network_completes():
    started, release = threading.Event(), threading.Event()
    calls = []
    class Persisted(Manager):
        async def fetch_and_compute(self):
            self.record('fetch')
            started.set()
            while not release.is_set():
                await asyncio.sleep(.001)
            self.value = {'rows': [{'value': 2}], 'observed_at': 200}
            return self.value
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Persisted(calls))
    try:
        handle.set_active_view('dashboard')
        await eventually(started.is_set)
        assert handle.get_snapshot() == {'rows': [{'value': 1}]}
        assert handle.is_loading()
        release.set()
        await eventually(lambda: not handle.is_loading())
        assert handle.get_snapshot()['observed_at'] == 200
        assert sum(name == 'fetch' for name, _ in calls) == 1
    finally:
        release.set()
        await runtime.close()


async def test_detached_completion_during_fetch_is_published_without_next_poll():
    calls = []
    class Completed(Manager):
        async def fetch_and_compute(self):
            self.record('fetch')
            captured = self.value
            async def enrichment():
                self.value = {'rows': [{'value': 2}], 'observed_at': 100}
            await asyncio.create_task(enrichment())
            return captured
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Completed(calls))
    try:
        handle.set_active_view('dashboard')
        await eventually(lambda: not handle.is_loading())
        assert handle.get_snapshot() == {'rows': [{'value': 2}], 'observed_at': 100}
        assert sum(name == 'fetch' for name, _ in calls) == 1
    finally:
        await runtime.close()


@pytest.mark.parametrize('projection', ['raises', 'empty'])
async def test_snapshot_failure_does_not_prevent_fetch_or_discard_fetched_value(projection):
    class BrokenProjection(Manager):
        def get_snapshot(self):
            if projection == 'raises':
                raise ValueError('invalid persisted slot')
            return None
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: BrokenProjection([]))
    try:
        handle.set_active_view('dashboard')
        await eventually(lambda: not handle.is_loading())
        assert handle.get_snapshot() == {'rows': [{'value': 1}]}
    finally:
        await runtime.close()


async def test_reader_polls_without_ui_requests_and_stops_when_hidden():
    calls = []
    runtime = ReaderRuntime(poll_interval=.03)
    handle = runtime.register('one', lambda: Manager(calls))
    try:
        handle.set_active_view('one')
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) >= 2)
        handle.set_active_view(None)
        await handle.drain_reads()
        count = sum(n == 'fetch' for n, _ in calls)
        # Reader barrier after multiple scheduling turns, with a real due time.
        await asyncio.sleep(.08)
        assert sum(n == 'fetch' for n, _ in calls) == count
    finally:
        await runtime.close()


async def test_old_scope_cannot_publish_after_cancellation_and_reopen_is_cached():
    started = threading.Event()
    class Slow(Manager):
        async def fetch_and_compute(self):
            view = self.view
            if view == 'a':
                started.set()
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    return {'view': 'old a'}
            return {'view': view}
        get_snapshot = None
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Slow([]))
    try:
        handle.set_active_view('a')
        await eventually(started.is_set)
        handle.set_active_view('b')
        await eventually(lambda: (handle.get_snapshot() or {}).get('view') == 'b')
        handle.set_active_view(None)
        await handle.drain_reads()
        handle.set_active_view('b')
        assert handle.get_snapshot() == {'view': 'b'}
        assert handle.is_loading()
    finally:
        await runtime.close()


async def test_detached_reads_publish_completion_and_special_getters_locally():
    finish = threading.Event()
    class Detached(Manager):
        async def fetch_and_compute(self):
            self.task = asyncio.create_task(self.read())
            return {'surf_oracles': {'count': 0}}
        async def read(self):
            while not finish.is_set():
                await asyncio.sleep(.001)
            self.value = {'surf_oracles': {'count': 7}, 'nft_readme': {'text': 'ready'}}
        def is_loading(self, view=None):
            return hasattr(self, 'task') and not self.task.done()
        def clean_routed_eth(self):
            self.record('clean')
            return 12
        def get_launch_contribution_snapshot(self):
            self.record('launch')
            return {'count': 8}
    calls = []
    runtime = ReaderRuntime(publish_interval=.03)
    handle = runtime.register('one', lambda: Detached(calls))
    try:
        handle.set_active_view('board')
        await eventually(lambda: handle.revision > 0)
        finish.set()
        await eventually(lambda: handle.get_oracles_snapshot() == {'count': 7})
        assert handle.get_readme() == {'text': 'ready'}
        assert handle.get_launch_contribution_snapshot() == {'count': 8}
        assert handle.clean_routed_eth() == 12
        before = list(calls)
        handle.get_readme(); handle.get_oracles_snapshot(); handle.get_hub_snapshot()
        assert before == calls
    finally:
        finish.set()
        await runtime.close()


async def test_async_queries_and_child_factories_keep_real_shared_manager_on_reader():
    calls = []
    class Parent(Manager):
        def nft_manager(self):
            self.record('child')
            self.child = Manager(calls)
            return self.child
        def query(self, rows):
            self.record('query')
            rows[0]['changed'] = True
            return rows
        async def close(self):
            await self.child.close()
            await super().close()
    runtime = ReaderRuntime()
    parent = runtime.register('parent', lambda: Parent(calls))
    child = parent.nft_manager()
    assert parent.nft_manager() is child and not calls
    try:
        child.set_active_view('NFT EXPLORER')
        await eventually(lambda: child.get_snapshot() is not None)
        rows = [{}]
        assert await parent.invoke('query', rows) == [{'changed': True}]
        assert rows == [{}]
    finally:
        await runtime.close()
    assert len([name for name, _ in calls if name == 'close']) == 2
    assert {thread for _, thread in calls} != {threading.get_ident()}


async def test_wallet_change_hides_other_wallet_snapshot_and_updates_metadata_immediately():
    class Wallet(Manager):
        wallet = 'first'
        def set_wallet(self, value):
            self.wallet = value
        async def fetch_and_compute(self):
            return {'wallet': self.wallet}
        get_snapshot = None
    runtime = ReaderRuntime()
    handle = runtime.register('wallet', lambda: Wallet([]), {'wallet': 'first'})
    try:
        handle.set_active_view('portfolio')
        await eventually(lambda: handle.get_snapshot() == {'wallet': 'first'})
        assert handle.set_wallet('second')
        assert handle.wallet == 'second'
        assert handle.get_snapshot() is None
        assert not handle.set_wallet('second')
        await eventually(lambda: handle.get_snapshot() == {'wallet': 'second'})
    finally:
        await runtime.close()


async def test_ui_generation_rejects_result_before_reader_can_process_switch():
    entered, release, next_read = threading.Event(), threading.Event(), threading.Event()
    class Blocked(Manager):
        get_snapshot = None
        async def fetch_and_compute(self):
            if self.view == 'a':
                entered.set()
                release.wait(3)
                return {'view': 'a'}
            next_read.set()
            await asyncio.sleep(60)
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Blocked([]))
    try:
        handle.set_active_view('a')
        await eventually(entered.is_set)
        handle.set_active_view('b')
        release.set()
        await eventually(next_read.is_set)
        assert handle.get_snapshot() is None
    finally:
        release.set()
        await runtime.close()


async def test_scope_change_cancels_query_and_preserves_async_cancellation():
    entered = threading.Event()
    class Query(Manager):
        async def lookup(self):
            entered.set()
            await asyncio.sleep(60)
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Query([]))
    try:
        handle.set_active_view('one')
        await eventually(lambda: handle.get_snapshot() is not None)
        task = asyncio.create_task(handle.invoke('lookup'))
        await eventually(entered.is_set)
        assert handle.is_loading()
        handle.set_active_view(None)
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not handle.is_loading()
    finally:
        await runtime.close()


async def test_failed_refresh_retains_local_data_and_closes_only_constructed_managers():
    class Failing(Manager):
        async def fetch_and_compute(self):
            if hasattr(self, 'fetched'):
                raise OSError('offline')
            self.fetched = True
            return self.value
    calls = []
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Failing(calls))
    runtime.register('never', lambda: pytest.fail('inactive manager was constructed'))
    try:
        handle.set_active_view('one')
        await eventually(lambda: handle.get_snapshot() is not None)
        handle.request_refresh()
        await eventually(lambda: handle._error_count == 1)
        assert handle.get_snapshot()['rows'][0]['value'] == 1
        assert not handle.is_loading()
    finally:
        await runtime.close()
    assert [name for name, _ in calls].count('close') == 1


async def test_new_handle_waits_for_previous_handle_cancellation_cleanup():
    started, cleaning, release, second = (threading.Event() for _ in range(4))
    class First(Manager):
        async def fetch_and_compute(self):
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                cleaning.set()
                while not release.is_set():
                    await asyncio.sleep(.001)
    class Second(Manager):
        async def fetch_and_compute(self):
            second.set()
            return self.value
        def barrier(self):
            return None
    runtime = ReaderRuntime()
    a = runtime.register('a', lambda: First([]))
    b = runtime.register('b', lambda: Second([]))
    try:
        a.set_active_view('a')
        await eventually(started.is_set)
        a.set_active_view(None)
        b.set_active_view('b')
        await eventually(cleaning.is_set)
        await b.invoke('barrier')
        assert not second.is_set()
        assert b.get_snapshot() == {'rows': [{'value': 1}]}
        assert b.is_loading()
        release.set()
        await eventually(second.is_set)
    finally:
        release.set()
        await runtime.close()


async def test_constructor_failure_can_retry_and_explicit_close_is_not_repeated():
    attempts, calls = [], []
    def factory():
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError('temporary cache failure')
        return Manager(calls)
    runtime = ReaderRuntime()
    handle = runtime.register('one', factory)
    try:
        handle.set_active_view('one')
        await eventually(lambda: handle._error_count == 1)
        handle.request_refresh()
        await eventually(lambda: handle.get_snapshot() is not None)
        assert await handle.invoke('current_view') == 'one'
        await handle.close()
    finally:
        await runtime.close()
    assert [name for name, _ in calls].count('close') == 1
    await handle.close()  # selected detail unmount follows application close


@pytest.mark.parametrize('selection', ['select', 'set_oracle_request'])
async def test_selection_retains_catalogue_and_hides_only_old_detail(selection):
    entered, release = threading.Event(), threading.Event()
    class Catalogue(Manager):
        def __init__(self):
            super().__init__([])
            self.value = {'nft_rows': [{'id': 'first'}], 'nft_readme': {'identity': 'first'},
                          'surf_oracles': {'rows': [{'id': 'first'}], 'selected_id': 'first',
                                           'detail': {'value': 'old'}}}
        def select(self, value):
            entered.set()
            release.wait(3)
        set_oracle_request = select
    runtime = ReaderRuntime()
    handle = runtime.register('one', Catalogue)
    try:
        handle.set_active_view('NFT EXPLORER' if selection == 'select' else 'oracles')
        await eventually(lambda: handle.get_snapshot() is not None)
        getattr(handle, selection)('second')
        await eventually(entered.is_set)
        assert handle.get_snapshot()['nft_rows'] == [{'id': 'first'}]
        if selection == 'select':
            assert handle.get_readme() is None
            assert handle.get_snapshot()['nft_readme'] is None
        else:
            assert handle.get_oracles_snapshot()['selected_id'] == 'second'
            assert handle.get_oracles_snapshot()['detail'] is None
    finally:
        release.set()
        await runtime.close()


async def test_query_cancelled_before_reader_coroutine_starts_settles_ui_waiter():
    entered, release, queried = (threading.Event() for _ in range(3))
    class Query(Manager):
        async def lookup(self):
            queried.set()
            return 'must not execute'
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Query([]))
    query = None
    def block():
        entered.set()
        release.wait(3)
    try:
        handle.set_active_view('a')
        await eventually(lambda: handle.get_snapshot() is not None)
        runtime._submit(block)
        await eventually(entered.is_set)
        query = asyncio.create_task(handle.invoke('lookup'))
        await asyncio.sleep(0)  # enqueue invoke before the scope change
        handle.set_active_view('b')
        release.set()
        await runtime.close()
        assert not queried.is_set()
        assert query.done() and query.cancelled()
        assert handle._query_count == 0
    finally:
        release.set()
        if query is not None and not query.done():
            query.cancel()
            with pytest.raises(asyncio.CancelledError):
                await query
        await runtime.close()


async def test_idle_board_offers_do_not_repeat_full_snapshot_projection():
    projected, offers, loading_checks = [], [], []
    class Board(Manager):
        def get_snapshot(self):
            projected.append(True)
            return self.value
        def offer_launch_contribution(self):
            offers.append(True)
        def get_launch_contribution_snapshot(self):
            return {'count': 0}
        def is_loading(self, view=None):
            loading_checks.append(True)
            return False
    runtime = ReaderRuntime(publish_interval=.01)
    handle = runtime.register('board', lambda: Board([]))
    try:
        handle.set_active_view('board')
        await eventually(lambda: handle.get_snapshot() is not None)
        initial = len(projected)
        for number in range(1, 4):
            checks = len(loading_checks)
            handle.offer_launch_contribution()
            await eventually(lambda: len(offers) == number)
            # Observe monitor passes without an invoke query that would itself
            # invalidate the retained projection or a fixed readiness sleep.
            await eventually(lambda: len(loading_checks) >= checks + 2)
        assert not handle.is_loading()
        assert len(projected) == initial
    finally:
        await runtime.close()


@pytest.mark.parametrize('fast', [False, True])
async def test_board_offer_publishes_completed_work_even_between_monitor_ticks(fast):
    started, release = threading.Event(), threading.Event()
    class Board(Manager):
        def __init__(self):
            super().__init__([])
            self.completed = 0
            self.pending = None
        def offer_launch_contribution(self):
            self.pending = asyncio.create_task(self.read())
        async def read(self):
            started.set()
            if not fast:
                while not release.is_set():
                    await asyncio.sleep(.001)
            self.completed += 1
        def is_loading(self, view=None):
            return self.pending is not None and not self.pending.done()
        def get_launch_contribution_snapshot(self):
            return {'count': self.completed}
    runtime = ReaderRuntime(publish_interval=.2)
    handle = runtime.register('board', lambda: Board())
    try:
        handle.set_active_view('board')
        await eventually(lambda: handle.get_snapshot() is not None)
        handle.offer_launch_contribution()
        await eventually(started.is_set)
        if not fast:
            await eventually(handle.is_loading)
            release.set()
        await eventually(lambda: handle.get_launch_contribution_snapshot() == {'count': 1})
        await eventually(lambda: not handle.is_loading())
    finally:
        release.set()
        await runtime.close()


async def test_synchronous_board_offer_publishes_only_changed_contribution_snapshot():
    projected = []
    class Board(Manager):
        completed = 0
        def get_snapshot(self):
            projected.append(True)
            return self.value
        def offer_launch_contribution(self):
            self.completed += 1
        def get_launch_contribution_snapshot(self):
            return {'count': self.completed}
    runtime = ReaderRuntime(publish_interval=.01)
    handle = runtime.register('board', lambda: Board([]))
    try:
        handle.set_active_view('board')
        await eventually(lambda: handle.get_launch_contribution_snapshot() == {'count': 0})
        initial, revision = len(projected), handle.revision
        handle.offer_launch_contribution()
        await eventually(lambda: handle.get_launch_contribution_snapshot() == {'count': 1})
        assert handle.revision > revision
        assert len(projected) == initial
        assert not handle.is_loading()
    finally:
        await runtime.close()


async def reader_turn(runtime, callback):
    """Observe an explicit reader turn, without sleeping to assert an absence."""
    future = Future()
    def run():
        try:
            future.set_result(callback())
        except BaseException as exc:
            future.set_exception(exc)
    runtime._submit(run)
    return await asyncio.wrap_future(future)


async def test_refresh_burst_while_reader_cpu_blocked_does_not_queue_a_followup():
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Blocked(Manager):
        async def fetch_and_compute(self):
            self.record('fetch')
            entered.set()
            assert release.wait(3)
            return self.value
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Blocked(calls))
    try:
        handle.set_active_view('one')
        await eventually(entered.is_set)
        for _ in range(20):
            handle.request_refresh()
        release.set()
        await reader_turn(runtime, lambda: None)
        await reader_turn(runtime, lambda: None)  # run any admitted coroutine
        assert sum(name == 'fetch' for name, _ in calls) == 1
        assert not handle.is_loading()
        handle.request_refresh()  # a fresh request after completion still works
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) == 2)
    finally:
        release.set()
        await runtime.close()


@pytest.mark.parametrize('detached', [False, True])
async def test_busy_cycles_discard_elapsed_ticks_and_publish_without_catchup(detached):
    now, calls = [100.0], []
    started, finish = threading.Event(), threading.Event()
    class Held(Manager):
        task = None
        async def read(self):
            started.set()
            while not finish.is_set():
                await asyncio.sleep(.001)
            self.value = {'rows': [{'value': 7}]}
            return self.value
        async def fetch_and_compute(self):
            self.record('fetch')
            if detached:
                self.task = asyncio.create_task(self.read())
                return self.value
            return await self.read()
        def is_loading(self, view=None):
            return self.task is not None and not self.task.done()
    runtime = ReaderRuntime(clock=lambda: now[0])
    handle = runtime.register('one', lambda: Held(calls))
    try:
        handle.set_active_view('one')
        await eventually(started.is_set)
        now[0] = 165  # miss the 130 and 160 deadlines while still reading
        await reader_turn(runtime, runtime._poll)
        await reader_turn(runtime, lambda: runtime._request('one', handle._generation))
        await reader_turn(runtime, lambda: None)
        assert sum(n == 'fetch' for n, _ in calls) == 1
        assert handle.is_loading()
        if detached:
            assert handle.get_snapshot() == {'rows': [{'value': 1}]}
        finish.set()
        await eventually(lambda: not handle.is_loading())
        assert handle.get_snapshot() == {'rows': [{'value': 7}]}
        await reader_turn(runtime, runtime._poll)
        assert sum(n == 'fetch' for n, _ in calls) == 1
        now[0] = 189
        await reader_turn(runtime, runtime._poll)
        assert sum(n == 'fetch' for n, _ in calls) == 1
        now[0] = 190
        await reader_turn(runtime, runtime._poll)
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) == 2)
    finally:
        finish.set()
        await runtime.close()


async def test_offer_only_manager_refreshes_independent_sources_while_busy():
    now, calls = [100.0], []
    class Offers(Manager):
        def reader_offer_only(self, view):
            return view == 'one'
        def is_loading(self, view=None):
            return True  # an optional source remains in flight
    runtime = ReaderRuntime(clock=lambda: now[0])
    handle = runtime.register('one', lambda: Offers(calls))
    try:
        handle.set_active_view('one')
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) == 1)
        await reader_turn(runtime, lambda: None)
        now[0] = 165
        await reader_turn(runtime, runtime._poll)
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) == 2)
        await reader_turn(runtime, runtime._poll)
        assert sum(n == 'fetch' for n, _ in calls) == 2  # no catch-up burst
        assert handle.is_loading()
        handle.set_active_view(None)
        now[0] = 225
        await reader_turn(runtime, runtime._poll)
        assert sum(n == 'fetch' for n, _ in calls) == 2
    finally:
        await runtime.close()


async def test_offer_only_return_reuses_current_snapshot_after_initial_publication():
    calls = []
    class Offers(Manager):
        def reader_offer_only(self, view):
            return True
        async def fetch_and_compute(self):
            self.record('fetch')
            self.value = {'rows': [{'value': 8}]}
            return self.get_snapshot()
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Offers(calls))
    try:
        handle.set_active_view('one')
        await eventually(lambda: handle.get_snapshot() == {'rows': [{'value': 8}]} and not handle.is_loading())
        assert sum(n == 'project' for n, _ in calls) == 2
    finally:
        await runtime.close()


@pytest.mark.parametrize('fails', [False, True])
async def test_cpu_blocked_completion_or_error_skips_missed_poll_deadlines(fails):
    now, calls = [100.0], []
    class Slow(Manager):
        async def fetch_and_compute(self):
            self.record('fetch')
            now[0] = max(now[0], 165)  # synchronous work prevents monitor ticks
            if fails:
                raise OSError('read failed after a long projection')
            return self.value
    runtime = ReaderRuntime(clock=lambda: now[0])
    handle = runtime.register('one', lambda: Slow(calls))
    try:
        handle.set_active_view('one')
        await eventually(lambda: bool(calls) and not handle.is_loading())
        await reader_turn(runtime, runtime._poll)
        await reader_turn(runtime, lambda: None)
        assert sum(n == 'fetch' for n, _ in calls) == 1
        now[0] = 190
        await reader_turn(runtime, runtime._poll)
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) == 2)
    finally:
        await runtime.close()


async def test_detached_final_projection_skips_deadlines_crossed_while_publishing():
    now, calls = [100.0], []
    class Projection(Manager):
        busy = True
        def is_loading(self, view=None):
            return self.busy
        def get_snapshot(self):
            now[0] = 165
            return {'rows': [{'value': 7}]}
    runtime = ReaderRuntime(clock=lambda: now[0])
    handle = runtime.register('one', lambda: Projection(calls))
    try:
        handle.set_active_view('one')
        await eventually(lambda: handle.get_snapshot() is not None)
        def complete():
            runtime.get_manager('one').busy = False
            runtime._poll()
        await reader_turn(runtime, complete)
        await reader_turn(runtime, lambda: None)
        assert handle.get_snapshot() == {'rows': [{'value': 7}]}
        assert not handle.is_loading()
        assert sum(n == 'fetch' for n, _ in calls) == 1
        now[0] = 190
        await reader_turn(runtime, runtime._poll)
        await eventually(lambda: sum(n == 'fetch' for n, _ in calls) == 2)
    finally:
        await runtime.close()


async def test_activation_bootstrap_runs_catalogue_despite_setter_started_readme():
    calls, started, finish = [], threading.Event(), threading.Event()
    class Catalogue(Manager):
        def set_active_view(self, view):
            super().set_active_view(view)
            if view:
                self.task = asyncio.create_task(self.readme())
        async def readme(self):
            started.set()
            while not finish.is_set():
                await asyncio.sleep(.001)
        def is_loading(self, view=None):
            return hasattr(self, 'task') and not self.task.done()
    runtime = ReaderRuntime()
    handle = runtime.register('one', lambda: Catalogue(calls))
    try:
        handle.set_active_view('NFT EXPLORER')
        await handle.fetch_and_compute()
        await eventually(started.is_set)
        await eventually(lambda: handle.get_snapshot() is not None)
        assert sum(n == 'fetch' for n, _ in calls) == 1
        assert handle.is_loading()
        finish.set()
        await eventually(lambda: not handle.is_loading())
    finally:
        finish.set()
        await runtime.close()

async def test_wallet_child_factory_is_retained_on_reader_and_seeded_explicitly():
    calls, parents = [], []
    class Wallet(Manager):
        def __init__(self, wallet):
            super().__init__(calls); self.wallet=wallet
        def set_wallet(self, address): self.wallet=address
        def get_snapshot(self): return {'wallet_snapshot':{'wallet':self.wallet}}
        async def fetch_and_compute(self): return self.get_snapshot()
    class Parent(Manager):
        def wallet_manager(self, wallet=None):
            self.record('wallet child'); self.child=Wallet(wallet); return self.child
        async def close(self):
            await self.child.close(); await super().close()
    def factory():
        value=Parent(calls); parents.append(value); return value
    runtime=ReaderRuntime(); parent=runtime.register('parent',factory)
    child=parent.wallet_manager('first')
    assert parent.wallet_manager('ignored') is child and not calls
    try:
        child.set_active_view('wallet')
        await eventually(lambda: child.get_snapshot()=={'wallet_snapshot':{'wallet':'first'}})
        assert child.wallet=='first'
        assert child.set_wallet('second') and child.get_snapshot() is None
        await eventually(lambda: child.get_snapshot()=={'wallet_snapshot':{'wallet':'second'}})
        assert parents[0].child.wallet=='second'
    finally:
        await runtime.close()
    assert sum(name=='wallet child' for name,_ in calls)==1
    assert sum(name=='close' for name,_ in calls)==2
    assert len({thread for _,thread in calls})==1
