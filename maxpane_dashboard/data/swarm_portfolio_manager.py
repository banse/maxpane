"""Wallet-scoped public scans with single-flight reads and independent seat clocks."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import time

from maxpane_dashboard.data.swarm_portfolio_client import SwarmPortfolioClient, address, normalize_result
from maxpane_dashboard.data.swarm_portfolio_models import empty_snapshot


class SwarmPortfolioManager:
    is_mock = False

    def __init__(self, wallet=None, *, client=None, clock=time.time):
        self.client = client or SwarmPortfolioClient()
        self._owns_client, self._clock = client is None, clock
        self._wallet, self._generation, self._task = None, 0, None
        self._view = 'portfolio'
        self._retired, self._closed, self._fresh = set(), False, False
        self._seat_attempt, self._error_count = None, 0
        self._snapshot = empty_snapshot()
        self.set_wallet(wallet)

    def set_wallet(self, wallet):
        wallet = address(wallet)
        if wallet == self._wallet: return False
        self._cancel_reads()
        self._wallet = wallet
        self._fresh, self._seat_attempt = False, None
        self._snapshot = empty_snapshot(wallet)
        return True

    def _cancel_reads(self):
        self._generation += 1
        if self._task and not self._task.done():
            self._task.cancel()
            self._retired.add(self._task)
            self._task.add_done_callback(self._retired.discard)
        self._task = None

    def set_active_view(self, view):
        """Release the screen's reads without discarding its last observations."""
        if view == self._view:
            return
        self._cancel_reads()
        self._view = view
        if view is not None and self._snapshot['seats'] is None:
            self._seat_attempt = None

    async def drain_reads(self):
        tasks = tuple(self._retired)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self._retired.difference_update(tasks)

    @property
    def wallet(self):
        return self._wallet

    def request_refresh(self):
        self._fresh = True

    def get_snapshot(self):
        result = deepcopy(self._snapshot)
        if result['as_of'] is not None and self._clock() - result['as_of'] > 600:
            if result['state'] != 'loading': result['state'] = 'stale'
        if result['seats_as_of'] is not None and self._clock() - result['seats_as_of'] > 120:
            result['seats_state'] = 'stale'
        return result

    async def fetch_and_compute(self):
        if self._closed or self._view is None or self._wallet is None: return self.get_snapshot()
        if self._task is None or self._task.done():
            fresh, self._fresh = self._fresh, False
            self._task = asyncio.create_task(self._read(self._generation, self._wallet, fresh))
        try:
            await asyncio.shield(self._task)
        except asyncio.CancelledError:
            if not self._closed: raise
        return self.get_snapshot()

    async def _read(self, generation, wallet, fresh):
        stamp = self._clock()
        seats_due = self._seat_attempt is None or stamp - self._seat_attempt >= 60
        if seats_due: self._seat_attempt = stamp
        reads = [self.client.read(wallet, fresh=fresh)]
        if seats_due: reads.append(self.client.read_seats(wallet))
        responses = await asyncio.gather(*reads, return_exceptions=True)
        if generation != self._generation or wallet != self._wallet or self._closed: return
        body = responses[0]
        previous = self._snapshot
        result = None
        if isinstance(body, dict) and body.get('state') == 'done':
            result = normalize_result(body.get('result'), wallet, now=self._clock())
        if result is not None:
            for key in ('seats', 'seats_as_of', 'seats_state'): result[key] = previous[key]
            self._snapshot = result
            self._error_count = 0
        else:
            running = isinstance(body, dict) and body.get('state') == 'running'
            self._snapshot['state'] = 'loading' if running else 'stale' if previous['as_of'] is not None else 'unavailable'
            self._snapshot['error'] = None if running else 'Portfolio scan did not return a valid snapshot'
            if isinstance(body, dict) and isinstance(body.get('error'), str):
                self._snapshot['error'] = body['error'][:500]
            self._error_count += not running
        if seats_due:
            seats = responses[1]
            if isinstance(seats, list):
                self._snapshot.update(seats=seats, seats_as_of=stamp, seats_state='ok')
            else:
                self._snapshot['seats_state'] = 'stale' if self._snapshot['seats_as_of'] is not None else 'unavailable'

    async def close(self):
        self._closed = True
        self._cancel_reads()
        await self.drain_reads()
        if self._owns_client: await self.client.close()
