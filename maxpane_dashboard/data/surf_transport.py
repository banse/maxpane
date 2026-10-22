"""Surf reader-loop host admission and refresh-local single-flight reads.

Parked dashboards do not import this policy. Default clients share admission in
their event loop; custom clocks can inject a coordinator for deterministic tests.
No task, timer or network operation runs until a visible reader asks for one.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from functools import wraps
import math
import time
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import httpx
from maxpane_dashboard.data.rpc_common import jsonrpc_payload


class HostCoolingDown(httpx.HTTPError):
    """No request was sent; rotate to an eligible alternative now."""


@dataclass
class _Host:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last: float = -math.inf
    interval: float = 0.


class HostCoordinator:
    def __init__(self, *, monotonic=time.monotonic, clock=time.time, sleep=asyncio.sleep):
        self.monotonic, self.clock, self.sleep = monotonic, clock, sleep
        self.hosts: dict[str, _Host] = {}
        self.cooldown: dict[str, float] = {}

    def cooling(self, url):
        return self.cooldown.get(urlsplit(url).hostname, 0) > self.monotonic()

    async def acquire(self, url, interval):
        host = urlsplit(url).hostname
        state = self.hosts.setdefault(host, _Host())
        state.interval = max(state.interval, interval)
        async with state.lock:
            while True:
                if self.cooling(url):
                    raise HostCoolingDown('host cooldown')
                delay = state.interval - (self.monotonic() - state.last)
                if delay <= 0:
                    break
                await self.sleep(delay)
            # A prior in-flight response may have installed a cooldown while
            # this waiter slept. Cancellation never reserves a future slot.
            state.last = self.monotonic()

    def observe(self, url, response):
        if response.status_code != 429:
            return
        retry = response.headers.get('Retry-After', '')
        try:
            seconds = float(retry)
        except ValueError:
            try:
                seconds = parsedate_to_datetime(retry).timestamp() - self.clock()
            except (ValueError, TypeError, OverflowError):
                seconds = 60.
        if not math.isfinite(seconds):
            seconds = 60.
        host = urlsplit(url).hostname
        self.cooldown[host] = max(self.cooldown.get(host, 0), self.monotonic() + max(1., seconds))


_loops = WeakKeyDictionary()
_cycle: ContextVar[dict | None] = ContextVar('surf_read_cycle', default=None)


def read_cycle(fn):
    """Share a stable context with child tasks, never a mutable global tick."""
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        if _cycle.get() is not None:
            return await fn(*args, **kwargs)
        token = _cycle.set({})
        try:
            return await fn(*args, **kwargs)
        finally:
            _cycle.reset(token)
    return wrapped


class SurfTransport:
    def __init__(self, *, delay=.12, coordinator=None):
        self.delay, self._coordinator = delay, coordinator

    @property
    def coordinator(self):
        if self._coordinator is not None:
            return self._coordinator
        loop = asyncio.get_running_loop()
        if loop not in _loops:
            _loops[loop] = HostCoordinator()
        return _loops[loop]

    async def acquire(self, url):
        await self.coordinator.acquire(url, self.delay)

    def observe(self, url, response):
        self.coordinator.observe(url, response)

    async def post(self, client, url, payload):
        await self.acquire(url)
        response = await client.post(url, json=payload)
        self.observe(url, response)
        return response

    async def prove_block(self, client, url, block, *, loader=None):
        """A fallback must serve the requested upper bound before logs count.

        A chain head obtained from another host is not that evidence. Cache
        successful or failed target-header probes only inside this refresh.
        """
        cycle = _cycle.get()
        key = ('block', url, block)
        async def probe():
            ident = f'surf-block-{block}'
            payload = jsonrpc_payload(ident, 'eth_getBlockByNumber', [hex(block), False])
            try:
                if loader is not None:
                    body = await loader(payload)
                else:
                    response = await self.post(client, url, payload)
                    response.raise_for_status()
                    body = response.json()
                result = body.get('result') if isinstance(body, dict) else None
                return (isinstance(result, dict) and not body.get('error')
                        and body.get('id') == ident and body.get('jsonrpc') == '2.0'
                        and isinstance(result.get('number'), str)
                        and int(result['number'], 16) == block)
            except (httpx.HTTPError, ValueError, TypeError):
                return False
        if cycle is None:
            return await probe()
        if key not in cycle:
            cycle[key] = asyncio.create_task(probe())
        return await cycle[key]

    async def head(self, chain, loader):
        cycle = _cycle.get()
        if cycle is None:
            return await loader()
        key = ('head', chain)
        if key not in cycle:
            cycle[key] = asyncio.create_task(loader())
        task = cycle[key]
        try:
            result = await task
        except BaseException:
            if cycle.get(key) is task:
                cycle.pop(key)
            raise
        try:
            valid = isinstance(result, str) and result.startswith('0x') and int(result, 16) >= 0
        except ValueError:
            valid = False
        if not valid and cycle.get(key) is task:
            cycle.pop(key)
        return result
