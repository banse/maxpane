"""One reader event loop owns managers; UI handles only see local data copies.

Factories, HTTP clients, cache writes, projections and cancellation stay on the
reader thread. Publishing swaps a prepared copy under a short lock; no UI read
waits for a factory, a projection, a file, or a network request.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass, field
import inspect
import logging
import threading
import time

logger = logging.getLogger(__name__)
_UNSET = object()


@dataclass
class _Entry:
    handle: 'ReaderHandle'
    factory: object
    owns_manager: bool
    manager: object = None
    task: object = None
    generation: int = 0
    view: str | None = None
    value: object = None
    next_read: float = 0
    last_publish: float = 0
    busy: bool = False
    closed: bool = False
    retired: list = field(default_factory=list)
    calls: set = field(default_factory=set)
    pending_commands: list = field(default_factory=list)


class ReaderRuntime:
    """Lazy application-owned thread, shared by every dashboard manager."""

    def __init__(self, poll_interval=30, publish_interval=1.0, *, clock=time.monotonic):
        if poll_interval <= 0 or publish_interval <= 0:
            raise ValueError('reader intervals must be positive')
        self.poll_interval, self.publish_interval = poll_interval, publish_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._entries, self._pending = {}, []
        self._loop = self._thread = None
        self._closing = False
        self._calls = set()
        self._retirements = set()
        self._close_future = None

    @property
    def thread(self):
        return self._thread

    @property
    def closing(self):
        with self._lock:
            return self._closing

    def register(self, key, factory, metadata=None, *, owns_manager=True):
        with self._lock:
            if self._closing:
                raise RuntimeError('reader is closed')
            if key not in self._entries:
                handle = ReaderHandle(self, key, metadata or {})
                self._entries[key] = _Entry(handle, factory, owns_manager)
            return self._entries[key].handle

    def _submit(self, callback, *args, closing=False):
        with self._lock:
            if self._closing and not closing:
                return False
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name='maxpane-reader', daemon=True)
                self._thread.start()
            if self._loop is None:
                self._pending.append((callback, args))
            else:
                self._loop.call_soon_threadsafe(callback, *args)
        return True

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
            pending, self._pending = self._pending, []
        for callback, args in pending:
            loop.call_soon(callback, *args)
        monitor = loop.create_task(self._monitor())
        try:
            loop.run_forever()
        finally:
            monitor.cancel()
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def get_manager(self, key):
        """Resolve a dependency inside a reader-side factory, never from UI."""
        if threading.current_thread() is not self._thread:
            raise RuntimeError('managers belong to the reader thread')
        entry = self._entries[key]
        if entry.closed:
            raise RuntimeError('manager is closed')
        if entry.manager is None:
            entry.manager = entry.factory()
            pending, entry.pending_commands = entry.pending_commands, []
            for method, args, kwargs in pending:
                self._apply_command(entry.manager, method, args, kwargs)
        return entry.manager

    @staticmethod
    def _apply_command(manager, method, args, kwargs):
        operation = getattr(manager, method, None)
        if callable(operation):
            operation(*deepcopy(args), **deepcopy(kwargs))
        elif method == 'set_wallet':
            manager._wallet_address = args[0]

    def _command(self, key, method, args, kwargs, generation, view):
        entry = self._entries[key]
        try:
            changed = generation != entry.generation
            previous_view = entry.view
            if changed:
                if entry.task is not None:
                    entry.task.cancel()
                    entry.retired.append(entry.task)
                    entry.task = None
                for task in entry.calls:
                    task.cancel()
                    entry.retired.append(task)
                entry.generation, entry.view, entry.value = generation, view, None
            manager = self.get_manager(key)
            self._apply_command(manager, method, args, kwargs)
            if changed and previous_view is not None:
                retirement = asyncio.create_task(self._retire(entry))
                self._retirements.add(retirement)
                retirement.add_done_callback(self._retirements.discard)
            if entry.view is not None and not self._closing:
                if changed:
                    # Activation may already have started a selected README.
                    # The new scope still needs its catalogue bootstrap.
                    self._start_refresh(entry, bootstrap=True)
                elif method == 'offer_launch_contribution':
                    # A one-second eligibility offer is often a no-op. Publish
                    # just its small result, without rebuilding the full board.
                    # Observe new tasks before yielding so even an immediate
                    # completion still gets the monitor's final publication.
                    busy = self._manager_loading(entry) or (
                        entry.task is not None and not entry.task.done())
                    entry.busy |= busy
                    getter = getattr(manager, 'get_launch_contribution_snapshot', None)
                    if callable(getter):
                        entry.handle._publish_extra(generation,
                            'get_launch_contribution_snapshot', deepcopy(getter()), busy)
                else:
                    entry.last_publish = 0
        except Exception:
            logger.exception('Reader command %s.%s failed', key, method)
            if entry.manager is None:
                entry.pending_commands.append((method, args, kwargs))
            entry.next_read = self._clock() + self.poll_interval
            entry.handle._finish_error(generation)

    def _request(self, key, generation):
        entry = self._entries[key]
        if generation == entry.generation and entry.view is not None:
            self._start_refresh(entry)

    def _start_refresh(self, entry, *, bootstrap=False):
        if self._closing or entry.view is None or entry.task is not None and not entry.task.done():
            return
        if not bootstrap and self._manager_loading(entry):
            return
        entry.next_read = self._clock() + self.poll_interval
        entry.handle._mark_loading(entry.generation, True)
        entry.task = asyncio.create_task(self._refresh(entry, entry.generation))

    def _skip_elapsed_polls(self, entry):
        """Keep the cadence, but never replay ticks missed during a read."""
        now = self._clock()
        if entry.next_read <= now:
            entry.next_read += (int((now - entry.next_read) / self.poll_interval) + 1) * self.poll_interval

    async def _refresh(self, entry, generation):
        try:
            manager = self.get_manager(entry.handle.key)
            # UI navigation never waits for this barrier. Only acquisition in
            # the newly visible scope waits for all earlier readers to drain.
            await self._drain_retirements()
            await self._drain(entry)
            drain = getattr(manager, 'drain_reads', None)
            if callable(drain):
                await drain()
            if generation != entry.generation or entry.view is None:
                return
            method = 'fetch_hub_snapshot' if entry.view == 'surfboard' and callable(
                getattr(manager, 'fetch_hub_snapshot', None)) else 'fetch_and_compute'
            result = await getattr(manager, method)()
            if generation != entry.generation or entry.view is None:
                return
            entry.value = result
            self._publish(entry, generation, busy=self._manager_loading(entry), payload=result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Reader refresh %s failed', entry.handle.key)
            entry.handle._finish_error(generation)
        finally:
            if generation == entry.generation:
                entry.task = None
                self._skip_elapsed_polls(entry)

    async def _drain(self, entry):
        retired = tuple(entry.retired)
        if retired:
            await asyncio.gather(*retired, return_exceptions=True)
            entry.retired = [task for task in entry.retired if task not in retired]

    async def _retire(self, entry):
        await self._drain(entry)
        drain = getattr(entry.manager, 'drain_reads', None)
        if callable(drain):
            await drain()

    async def _drain_retirements(self):
        # A later rapid switch may cancel this waiter, never the cleanup it
        # waits for; otherwise old HTTP work can escape into the next scope.
        if self._retirements:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._retirements)))

    def _manager_loading(self, entry):
        loading = getattr(entry.manager, 'is_loading', None)
        try:
            return bool(loading(entry.view)) if callable(loading) else False
        except Exception:
            logger.exception('Reader loading state %s failed', entry.handle.key)
            return False

    def _publish(self, entry, generation, *, busy, payload=_UNSET):
        manager = entry.manager
        if payload is _UNSET:
            getter = getattr(manager, 'get_snapshot', None)
            payload = getter() if callable(getter) else entry.value
        extras = {}
        if isinstance(payload, dict):
            extras['get_oracles_snapshot'] = payload.get('surf_oracles')
            extras['get_readme'] = payload.get('nft_readme')
        getters = ['clean_routed_eth']
        if entry.view == 'board':
            getters.append('get_launch_contribution_snapshot')
        if entry.view == 'oracles' and extras.get('get_oracles_snapshot') is None:
            getters.append('get_oracles_snapshot')
        if entry.view == 'NFT EXPLORER' and extras.get('get_readme') is None:
            getters.append('get_readme')
        for name in getters:
            method = getattr(manager, name, None)
            if callable(method):
                extras[name] = method()
        metadata = {name: getattr(manager, name) for name in
                    ('wallet', '_wallet_address', '_error_count', 'is_mock') if hasattr(manager, name)}
        seats = getattr(manager, 'get_hub_seats', None)
        if callable(seats):
            metadata['hub_seats'] = seats()
        # One memo keeps auxiliary views into a payload from being copied twice.
        payload, extras = deepcopy((payload, extras))
        entry.handle._publish(generation, payload, extras, metadata, busy)
        entry.last_publish, entry.busy = self._clock(), busy

    async def _monitor(self):
        while True:
            await asyncio.sleep(min(.1, self.publish_interval, self.poll_interval))
            self._poll()

    def _poll(self):
        with self._lock:
            entries = list(self._entries.values())
        for entry in entries:
            if entry.view is None or entry.closed or self._closing:
                continue
            now = self._clock()
            if entry.manager is None:
                if now >= entry.next_read:
                    self._start_refresh(entry)
                continue
            if entry.task is not None and not entry.task.done():
                self._skip_elapsed_polls(entry)
                continue
            busy = self._manager_loading(entry)
            if busy or entry.busy or not entry.last_publish:
                if not busy or not entry.last_publish or now - entry.last_publish >= self.publish_interval:
                    try:
                        self._publish(entry, entry.generation, busy=busy)
                    except Exception:
                        logger.exception('Reader projection %s failed', entry.handle.key)
                self._skip_elapsed_polls(entry)
            if self._clock() >= entry.next_read:
                self._start_refresh(entry)

    def _begin_invoke(self, future, key, method, args, kwargs):
        entry = self._entries[key]
        async def call():
            try:
                if method == 'close' and entry.closed:
                    future.set_result(None)
                    return
                manager = self.get_manager(key)
                operation = getattr(manager, method, None)
                if method in ('drain_reads', 'close'):
                    await self._drain_retirements()
                    await self._drain(entry)
                if method == 'drain_reads' and not callable(operation):
                    result = None
                else:
                    result = operation(*deepcopy(args), **deepcopy(kwargs))
                    if inspect.isawaitable(result):
                        result = await result
                if method == 'close':
                    entry.closed = True
                if not future.done():
                    future.set_result(deepcopy(result))
                if method != 'drain_reads':
                    entry.last_publish = 0
            except BaseException as exc:
                if not future.done():
                    if isinstance(exc, asyncio.CancelledError):
                        future.cancel()
                    else:
                        future.set_exception(exc)
        task = asyncio.create_task(call())
        # Cancelling a task before its first step never enters call()'s except
        # block. Settle its cross-thread waiter in that case as well.
        task.add_done_callback(lambda done: future.cancel() if done.cancelled() else None)
        self._calls.add(task)
        task.add_done_callback(self._calls.discard)
        if method != 'drain_reads':
            entry.calls.add(task)
            task.add_done_callback(entry.calls.discard)
        def cancel(done):
            if done.cancelled() and not task.done() and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(task.cancel)
        future.add_done_callback(cancel)

    async def invoke(self, key, method, *args, **kwargs):
        future = Future()
        if not self._submit(self._begin_invoke, future, key, method, args, kwargs):
            raise RuntimeError('reader is closed')
        return await asyncio.wrap_future(future)

    async def close(self):
        with self._lock:
            if self._close_future is None:
                self._close_future = Future()
                self._closing = True
                first = True
            else:
                first = False
            future, thread = self._close_future, self._thread
        if first:
            if thread is None:
                future.set_result(None)
            else:
                self._submit(lambda: asyncio.create_task(self._shutdown(future)), closing=True)
        await asyncio.shield(asyncio.wrap_future(future))
        if thread is not None:
            await asyncio.to_thread(thread.join)

    async def _shutdown(self, future):
        try:
            entries = list(self._entries.values())
            tasks = set(self._calls)
            tasks.update(self._retirements)
            for entry in entries:
                if entry.task is not None:
                    tasks.add(entry.task)
                tasks.update(entry.retired)
                if entry.manager is not None and not entry.closed:
                    setter = getattr(entry.manager, 'set_active_view', None)
                    if callable(setter):
                        try:
                            setter(None)
                        except Exception:
                            logger.exception('Reader stop %s failed', entry.handle.key)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for entry in reversed(entries):
                if entry.manager is not None and entry.owns_manager and not entry.closed:
                    try:
                        await entry.manager.close()
                        entry.closed = True
                    except Exception:
                        logger.exception('Reader close %s failed', entry.handle.key)
            future.set_result(None)
        except BaseException as exc:
            future.set_exception(exc)
        finally:
            self._loop.stop()


class ReaderHandle:
    """Small UI-side command port and reader-published local value store."""

    _COMMANDS = frozenset(('set_agent_active', 'set_swarm_active', 'set_work_active',
        'set_oracles_active', 'set_launch_contribution_active', 'set_hub_active',
        'offer_launch_contribution'))
    _QUERIES = frozenset(('execute_hub_command', 'resolve_nft_collection_name',
                         'label_list_rows_with_ens'))

    def __init__(self, runtime, key, metadata):
        self.runtime, self.key = runtime, key
        self._lock = threading.Lock()
        self._metadata = dict(metadata)
        self._view, self._generation, self._revision = None, 0, 0
        self._identity = {}
        self._commands = {}
        self._snapshots = {}
        self._payload, self._extras = None, {}
        self._loading = False
        self._query_count = 0
        self._child_serial = 0

    @property
    def revision(self):
        with self._lock:
            return self._revision

    def get_snapshot(self):
        with self._lock:
            return self._payload

    get_hub_snapshot = get_snapshot

    def _extra(self, name):
        with self._lock:
            return self._extras.get(name)

    def get_oracles_snapshot(self):
        return self._extra('get_oracles_snapshot') or {}

    def get_launch_contribution_snapshot(self, **kwargs):
        return self._extra('get_launch_contribution_snapshot') or {}

    def get_readme(self):
        return self._extra('get_readme')

    def clean_routed_eth(self):
        return self._extra('clean_routed_eth')

    def get_hub_seats(self):
        with self._lock:
            return self._metadata.get('hub_seats', (None, None, None, None))

    def is_loading(self, view=None):
        with self._lock:
            return self._view is not None and (self._loading or self._query_count > 0)

    def _scope(self):
        return self._view, tuple(sorted((key, repr(value)) for key, value in self._identity.items()))

    def _send(self, method, *args, identity=False, **kwargs):
        with self._lock:
            selection = method in ('select', 'set_oracle_request')
            previous_payload, previous_extras = self._payload, self._extras
            if method == 'set_active_view':
                if self._view == args[0]:
                    return
                self._view = args[0]
            elif identity:
                value = (args, kwargs)
                default = ((None,), {}) if selection else None
                if self._identity.get(method, default) == value:
                    return
                self._identity[method] = value
            elif method.startswith('set_'):
                value = (args, kwargs)
                if self._commands.get(method) == value:
                    return
                self._commands[method] = value
            if method == 'set_active_view' or identity:
                self._generation += 1
                self._payload, self._extras = self._snapshots.get(self._scope(), (None, {}))
                if selection and previous_payload is not None:
                    # Row selection keeps its catalogue on screen. Only the
                    # selected detail loses its previous identity immediately.
                    self._payload, self._extras = dict(previous_payload), dict(previous_extras)
                    if method == 'select':
                        self._payload['nft_readme'] = self._extras['get_readme'] = None
                    else:
                        detail = dict(previous_payload.get('surf_oracles') or {})
                        detail.update(selected_id=args[0], detail=None,
                                      detail_state='loading', detail_read_ts=None)
                        self._payload['surf_oracles'] = self._extras['get_oracles_snapshot'] = detail
                self._revision += 1
                self._loading = self._view is not None
            generation, view = self._generation, self._view
        self.runtime._submit(self.runtime._command, self.key, method, args, kwargs, generation, view)

    def set_active_view(self, view):
        self._send('set_active_view', view)

    def set_wallet(self, wallet):
        wallet = wallet or None
        with self._lock:
            old = self._metadata.get('wallet', self._metadata.get('_wallet_address'))
            if old == wallet:
                return False
            self._metadata['wallet'] = self._metadata['_wallet_address'] = wallet
        self._send('set_wallet', wallet, identity=True)
        return True

    def set_seat(self, seat):
        self._send('set_seat', seat, identity=True)

    def set_hub_seats(self, seats):
        with self._lock:
            self._metadata['hub_seats'] = tuple(seats)
        self._send('set_hub_seats', tuple(seats), identity=True)

    def set_record_view(self, *args, **kwargs):
        self._send('set_record_view', *args, identity=True, **kwargs)

    def set_oracle_request(self, value):
        self._send('set_oracle_request', value, identity=True)

    def select(self, value):
        self._send('select', value, identity=True)

    def request_refresh(self):
        with self._lock:
            # Coalesce before crossing threads: the reader may be CPU-bound
            # and unable to reject queued callbacks until after it completes.
            if self._view is None or self._loading:
                return
            generation = self._generation
            self._loading = True
        self.runtime._submit(self.runtime._request, self.key, generation)

    async def fetch_and_compute(self):
        self.request_refresh()
        return self.get_snapshot() or {}

    fetch_hub_snapshot = fetch_and_compute

    async def invoke(self, method, *args, **kwargs):
        with self._lock:
            self._query_count += method != 'drain_reads'
        try:
            return await self.runtime.invoke(self.key, method, *args, **kwargs)
        finally:
            with self._lock:
                self._query_count -= method != 'drain_reads'

    async def drain_reads(self):
        return await self.invoke('drain_reads')

    def _publish(self, generation, payload, extras, metadata, busy):
        # The potentially large comparison belongs to the reader. UI access
        # only takes the lock for a reference swap/read, never for this walk.
        with self._lock:
            prior_payload, prior_extras = self._payload, self._extras
        changed = payload != prior_payload or extras != prior_extras
        with self._lock:
            if generation != self._generation or self._view is None:
                return
            if changed:
                self._payload, self._extras = payload, extras
                self._snapshots[self._scope()] = payload, extras
                while len(self._snapshots) > 16:
                    self._snapshots.pop(next(iter(self._snapshots)))
                self._revision += 1
            self._metadata.update(metadata)
            self._loading = busy

    def _mark_loading(self, generation, busy):
        with self._lock:
            if generation == self._generation:
                self._loading = busy

    def _publish_extra(self, generation, name, value, busy):
        with self._lock:
            previous = self._extras.get(name)
        changed = value != previous
        with self._lock:
            if generation != self._generation or self._view is None:
                return
            if changed:
                self._extras = dict(self._extras, **{name: value})
                self._snapshots[self._scope()] = self._payload, self._extras
                self._revision += 1
            self._loading = busy

    def _finish_error(self, generation):
        with self._lock:
            if generation == self._generation:
                self._loading = False
                self._metadata['_error_count'] = self._metadata.get('_error_count', 0) + 1

    def _child(self, method, *args, metadata=None):
        key = f'{self.key}/{method}'
        return self.runtime.register(key,
            lambda: getattr(self.runtime.get_manager(self.key), method)(*args),
            metadata, owns_manager=False)

    def nft_manager(self):
        return self._child('nft_manager')

    def swarm_tokens_manager(self):
        return self._child('swarm_tokens_manager')

    def portfolio_manager(self, wallet=None):
        return self._child('portfolio_manager', wallet, metadata={'wallet': wallet})

    def token_detail_manager(self, token):
        from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager
        # A selected detail owns its own lifecycle, while borrowing the real
        # overview and client already owned by the reader.
        with self._lock:
            self._child_serial += 1
            key = f'{self.key}/token/{self._child_serial}'
        return self.runtime.register(key,
            lambda: SwarmTokenDetailManager(self.runtime.get_manager(self.key), deepcopy(token)))

    async def close(self):
        if self.runtime.closing:
            return
        self.set_active_view(None)
        try:
            await self.invoke('close')
        except RuntimeError:
            if not self.runtime.closing:
                raise

    def __getattr__(self, name):
        if name in self._COMMANDS:
            return lambda *args, **kwargs: self._send(name, *args, **kwargs)
        if name in self._QUERIES:
            return lambda *args, **kwargs: self.invoke(name, *args, **kwargs)
        if name in ('wallet', '_wallet_address', '_error_count', 'is_mock'):
            with self._lock:
                return self._metadata.get(name, False if name == 'is_mock' else 0 if name == '_error_count' else None)
        raise AttributeError(name)
