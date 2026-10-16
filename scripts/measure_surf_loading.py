"""Bounded actual-manager probe, using an isolated cache; never fabricates paint.

    .venv/bin/python scripts/measure_surf_loading.py --size 149x45 \
        --max-requests 80 --deadline 90 --output /tmp/maxpane-surf-loading.json

A cold run and a warm replay share one temporary cache. Each run has its own
attempt/deadline budget. A 429 stops the pair. No raw response bodies are saved.
"""
from __future__ import annotations

import argparse
from contextvars import ContextVar
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class Measurement:
    def __init__(self, *, max_requests=80, deadline=90, clock=time.monotonic):
        self.clock, self.started = clock, clock()
        self.max_requests, self.deadline = max_requests, deadline
        self.events, self.attempts, self.reason = [], 0, None
        self.stopped = asyncio.Event()
        self._restores = []
        self._logical = ContextVar('surf_measure_logical', default=None)
        self._logical_attempts = {}
        self.accepting_requests = True

    def event(self, kind, **fields):
        self.events.append(dict(kind=kind, ms=round((self.clock()-self.started)*1000, 3), **fields))

    def stop(self, reason):
        self.reason = self.reason or reason
        self.stopped.set()

    def instrument_http(self, client):
        original = client.send
        async def send(request, **kwargs):
            if not self.accepting_requests:
                raise asyncio.CancelledError
            if self.reason or self.attempts >= self.max_requests:
                self.stop(self.reason or 'request_budget')
                raise asyncio.CancelledError
            self.attempts += 1
            attempt = self.attempts
            logical = self._logical.get()
            ordinal = self._logical_attempts.get(logical, 0) + 1
            self._logical_attempts[logical] = ordinal
            self.event('request_start', attempt=attempt, logical=logical,
                       logical_attempt=ordinal if logical is not None else None,
                       route=str(request.url), method=request.method)
            try:
                response = await original(request, **kwargs)
                await response.aread()
                self.event('request_end', attempt=attempt, status=response.status_code, bytes=len(response.content))
                if response.status_code == 429:
                    self.stop('http_429')
                    raise asyncio.CancelledError
                return response
            except BaseException as exc:
                self.event('request_exit', attempt=attempt, error=type(exc).__name__)
                raise
        self._restores.append((client, 'send', original))
        client.send = send

    def instrument_async(self, owner, name):
        original = getattr(owner, name)
        async def call(*args, **kwargs):
            logical = len(self.events)
            token = self._logical.set(logical)
            self.event('logical_start', logical=logical, method=name, identity=str(args[0]) if args else None)
            try:
                return await original(*args, **kwargs)
            finally:
                self.event('logical_end', logical=logical, method=name)
                self._logical.reset(token)
        self._restores.append((owner, name, original))
        setattr(owner, name, call)

    def instrument_manager(self, manager):
        original = manager.cache.store_last_good
        def store(slot, payload, **kwargs):
            result = original(slot, payload, **kwargs)
            self.event('slot_publish', slot=slot)
            return result
        self._restores.append((manager.cache, 'store_last_good', original))
        manager.cache.store_last_good = store
        original_project = manager.get_hub_snapshot
        def project():
            data = original_project()
            self.projection(data)
            return data
        self._restores.append((manager, 'get_hub_snapshot', original_project))
        manager.get_hub_snapshot = project
        for owner, names in ((manager.client, ('fetch_market', 'fetch_chain_state')),
                             (manager.swarm_client, ('fetch_job', 'fetch_seat'))):
            for name in names:
                self.instrument_async(owner, name)
        # Only descend through this manager's local data objects and containers.
        seen = set()
        def visit(value):
            if id(value) in seen:
                return
            seen.add(id(value))
            if isinstance(value, httpx.AsyncClient):
                self.instrument_http(value)
            elif isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif type(value).__module__.startswith('maxpane_dashboard.data'):
                for child in vars(value).values():
                    visit(child)
        visit(manager)
        # These retained factories may create transports after initial setup.
        # Wrap each returned owner before the caller can start its first read.
        for name in ('_launch_rpc_client', 'swarm_tokens_manager', 'portfolio_manager'):
            original_factory = getattr(manager, name)
            def factory(*args, _factory=original_factory, **kwargs):
                owner = _factory(*args, **kwargs)
                visit(owner)
                return owner
            self._restores.append((manager, name, original_factory))
            setattr(manager, name, factory)

    def projection(self, data):
        if not any(e['kind'] == 'first_useful_snapshot' for e in self.events) and (
                data.get('eth_usd') is not None or data.get('swarm_seat_work_rows')
                or (data.get('surfboard_overview') or {}).get('jobs') is not None):
            self.event('first_useful_snapshot')

    def summary(self):
        def first(kind):
            return next((e['ms'] for e in self.events if e['kind'] == kind), None)
        return dict(attempts=self.attempts, censored=self.reason is not None, reason=self.reason,
                    elapsed_ms=round((self.clock()-self.started)*1000, 3),
                    first_useful_snapshot_ms=first('first_useful_snapshot'), first_paint_ms=first('paint'))

    async def run(self, operation, close):
        task, stop = asyncio.create_task(operation), asyncio.create_task(self.stopped.wait())
        try:
            done, _ = await asyncio.wait((task, stop), timeout=self.deadline, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                self.stop('deadline')
            elif task in done and not self.reason:
                await task
        finally:
            task.cancel()
            stop.cancel()
            await asyncio.gather(task, stop, return_exceptions=True)
            self.accepting_requests = False
            await close()
            for owner, name, original in reversed(self._restores):
                setattr(owner, name, original)
        return dict(self.summary(), events=self.events)


def summarize_samples(samples):
    values = [sample['elapsed_ms'] for sample in samples if not sample['censored']]
    return dict(n=len(samples), complete_n=len(values), censored_n=len(samples)-len(values),
                median_ms=statistics.median(values) if values else None,
                range_ms=[min(values), max(values)] if values else None)


async def probe(args):
    from maxpane_dashboard.data.surf_manager import SurfManager
    samples = []
    with tempfile.TemporaryDirectory(prefix='maxpane-surf-loading-') as folder:
        for scenario in ('cold', 'warm'):
            manager = SurfManager(cache_path=Path(folder)/'surf.json')
            trace = Measurement(max_requests=args.max_requests, deadline=args.deadline)
            trace.instrument_manager(manager)
            selected = None
            async def collect():
                nonlocal selected
                trace.projection(await manager.fetch_and_compute())
                board = manager._swarm_board_task
                if board is not None:
                    await asyncio.shield(board)
                data = manager.get_hub_snapshot()
                rows = data.get('swarm_board_rows') or data.get('swarm_leaderboard_rows') or []
                selected = next((row.get('token_id') for row in rows
                                 if row.get('token_id') is not None and (row.get('attempts') or row.get('accepted'))), None)
                if selected is None:
                    trace.stop('no_record_seat')
                    return
                manager.set_seat(selected)
                manager.set_agent_active(True)
                await manager._pool_swarm_seat(selected, manager._clock())
                data = manager.get_hub_snapshot()
                trace.projection(data)
                if not data.get('swarm_seat_work_rows'):
                    trace.stop('record_unavailable')
            sample = await trace.run(collect(), manager.close)
            samples.append(dict(sample, scenario=scenario, selected_seat=selected, size=args.size))
            if sample['reason'] == 'http_429':
                break
    return dict(samples=samples, summary=summarize_samples(samples), paint='not measured: manager-only probe')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', default='149x45')
    parser.add_argument('--max-requests', type=int, default=80)
    parser.add_argument('--deadline', type=float, default=90)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 80 or not 0 < args.deadline <= 90:
        parser.error('limits must be 1..80 attempts and >0..90 seconds')
    result = asyncio.run(probe(args))
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
