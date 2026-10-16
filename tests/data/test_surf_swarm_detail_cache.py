"""Real SwarmClient/HTTP transport tests; every response is an offline fixture."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.surf_swarm_client import SwarmClient

ROOT = Path(__file__).parents[1] / 'fixtures/surf/detail_cache'
CASES = json.loads((ROOT / 'cases.json').read_text())
JOB = CASES['active']['id']


class Clock:
    def __init__(self):
        self.wall = 1000.0
        self.mono = 0.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


async def turn():
    """Yield to already queued coroutines without a timer or wall-clock wait."""
    ready = asyncio.Event()
    asyncio.get_running_loop().call_soon(ready.set)
    await ready.wait()


@asynccontextmanager
async def client_for(handler, clock=None, **kwargs):
    clock = clock or Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SwarmClient(http_client=http, hosts=kwargs.pop('hosts', ('https://one.test',)),
                             inter_call_delay=0, clock=lambda: clock.wall,
                             monotonic=lambda: clock.mono, **kwargs)
        try:
            yield client
        finally:
            await client.close()


def response(request, body='active', status=200):
    assert request.method == 'GET'
    assert request.url.path == '/jobs/' + JOB
    assert not request.url.params
    return httpx.Response(status, json=CASES[body])


async def test_shared_detail_is_one_request_and_independent_copies():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    clock = Clock()

    async def handler(request):
        calls.append(request)
        entered.set()
        await release.wait()
        clock.advance(2)
        return response(request)

    async with client_for(handler, clock) as client:
        tasks = [asyncio.create_task(client.read_job_detail(JOB)) for _ in range(5)]
        await entered.wait()
        await turn()
        release.set()
        reads = await asyncio.gather(*tasks)
        assert len(calls) == 1
        assert all(r.payload == CASES['active'] and r.observed_at == 1002 and
                   r.started_mono == 0 and r.revision == '2026-10-17T10:00:00.000Z'
                   and not r.from_cache for r in reads)
        reads[0].payload['nodes'][0]['id'] = 'tampered'
        assert reads[1].payload == CASES['active']
        clock.advance(1)
        cached = await client.read_job_detail(JOB)
        assert cached.payload == CASES['active'] and cached.from_cache
        assert cached.observed_at == 1002 and len(calls) == 1
        with pytest.raises(FrozenInstanceError):
            cached.observed_at = 0


@pytest.mark.parametrize('kind,ttl', [('active', 30), ('terminal', 600), ('busy', 15)])
async def test_ttl_and_negative_backoff_preserve_observed_at(kind, ttl):
    clock, calls = Clock(), []
    clock.wall = 0  # Zero is a genuine observation, never an absence sentinel.
    def handler(request):
        calls.append(request)
        return response(request, kind, 503 if kind == 'busy' else 200)
    async with client_for(handler, clock) as client:
        first = await client.read_job_detail(JOB)
        clock.advance(ttl - 0.01)
        clock.wall = -500  # A wallclock correction never extends monotonic TTL.
        cached = await client.read_job_detail(JOB)
        assert cached.from_cache and cached.observed_at == first.observed_at
        assert len(calls) == 1
        clock.advance(0.01)
        reread = await client.read_job_detail(JOB)
        assert not reread.from_cache and len(calls) == 2
        if kind == 'busy':
            assert first.observed_at is None and reread.observed_at is None
            first.payload['error'] = 'changed'
            assert cached.payload == {'error': 'busy'}


async def test_detail_limits_keep_complete_large_payload():
    entered, release = asyncio.Event(), asyncio.Event()
    oversized = json.loads((ROOT / 'oversized.json').read_text())
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.url.path == '/jobs/' + JOB
        entered.set()
        await release.wait()
        return httpx.Response(200, json=oversized)
    async with client_for(handler) as client:
        tasks = [asyncio.create_task(client.read_job_detail(JOB)) for _ in range(5)]
        await entered.wait()
        await turn()
        release.set()
        reads = await asyncio.gather(*tasks)
        assert all(r.payload == oversized for r in reads) and len(calls) == 1
        first = reads[0]
        assert first.payload == oversized and len(first.payload['nodes']) == 45
        assert len(first.payload['edges']) == 44
        second = await client.read_job_detail(JOB)
        assert second.payload == oversized and not second.from_cache
        assert len(calls) == 2


async def test_waiter_cancel_keeps_shared_read():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(request):
        calls.append(request)
        entered.set()
        await release.wait()
        return response(request)
    async with client_for(handler) as client:
        first = asyncio.create_task(client.fetch_job(JOB))
        second = asyncio.create_task(client.fetch_job(JOB))
        await entered.wait()
        await turn()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await second == CASES['active']
        assert len(calls) == 1


async def test_last_waiter_cancel_and_reopen_drain_old_flight():
    entered, cancelled, drain = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await drain.wait()
                raise
        return response(request)
    async with client_for(handler) as client:
        first = asyncio.create_task(client.fetch_job(JOB))
        await entered.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await cancelled.wait()
        reopened = asyncio.create_task(client.fetch_job(JOB))
        await turn()
        assert len(calls) == 1
        drain.set()
        assert await reopened == CASES['active'] and len(calls) == 2


@pytest.mark.parametrize('owned', [False, True])
async def test_close_cancels_and_awaits_owned_flights(owned):
    entered, cancelled, drain = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def handler(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await drain.wait()
            raise
    async with client_for(handler) as client:
        client._owns_client = owned
        reader = asyncio.create_task(client.fetch_job(JOB))
        await entered.wait()
        closing = asyncio.create_task(client.close())
        await cancelled.wait()
        assert not client._client.is_closed and not closing.done()
        drain.set()
        await closing
        with pytest.raises(asyncio.CancelledError):
            await reader
        assert client._client.is_closed is owned


async def test_detail_parallelism_never_exceeds_eight():
    eight, release = asyncio.Event(), asyncio.Event()
    active = maximum = 0
    async def handler(request):
        nonlocal active, maximum
        assert request.url.path.startswith('/jobs/')
        active += 1
        maximum = max(maximum, active)
        if active == 8:
            eight.set()
        await release.wait()
        active -= 1
        return httpx.Response(200, json=dict(CASES['active'], id=request.url.path[6:]))
    async with client_for(handler) as client:
        tasks = [asyncio.create_task(client.fetch_job(f'job-{n}')) for n in range(12)]
        await eight.wait()
        await turn()
        assert maximum == 8
        release.set()
        assert all(await asyncio.gather(*tasks))
        assert maximum == 8


async def test_fresh_after_revalidates_older_flight_once():
    clock = Clock()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            await release.wait()
        return response(request, 'active' if len(calls) == 1 else 'changed')
    async with client_for(handler, clock) as client:
        old = asyncio.create_task(client.read_job_detail(JOB))
        await entered.wait()
        clock.advance(1)
        fresh = [asyncio.create_task(client.read_job_detail(JOB, fresh_after=1)) for _ in range(5)]
        await turn()
        release.set()
        first = await old
        reads = await asyncio.gather(*fresh)
        assert first.started_mono == 0 and first.payload == CASES['active']
        assert len(calls) == 2
        assert all(r.started_mono == 1 and r.payload == CASES['changed'] for r in reads)


@pytest.mark.parametrize('changed', ['state', 'revision'])
async def test_changed_list_state_or_revision_invalidates_detail(changed):
    clock, calls = Clock(), []
    change = dict(CASES['active'])
    change['state' if changed == 'state' else 'updatedAt'] = CASES['changed'][
        'state' if changed == 'state' else 'updatedAt']
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/jobs':
            return httpx.Response(200, json={'jobs': [change if len(calls) == 2 else CASES['changed']]})
        return response(request, 'active' if len(calls) == 1 else 'changed')
    async with client_for(handler, clock) as client:
        await client.read_job_detail(JOB)
        await client.fetch_jobs()
        assert (await client.read_job_detail(JOB)).payload == CASES['changed']
        assert calls == ['/jobs/' + JOB, '/jobs', '/jobs/' + JOB]
        await client.fetch_jobs()
        assert (await client.read_job_detail(JOB)).from_cache


async def test_dirty_epoch_rejects_late_old_response():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(request):
        if request.url.path == '/jobs':
            return httpx.Response(200, json={'jobs': [CASES['changed']]})
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            await release.wait()
            return response(request)
        return response(request, 'changed')
    async with client_for(handler) as client:
        old = asyncio.create_task(client.read_job_detail(JOB))
        await entered.wait()
        await client.fetch_jobs()
        fresh = asyncio.create_task(client.read_job_detail(JOB))
        await turn()
        release.set()
        reads = await asyncio.gather(old, fresh)
        assert all(r.payload == CASES['changed'] for r in reads)
        assert len(calls) == 2


@pytest.mark.parametrize('outcome', ['busy', 'invalid', 'foreign', 'network'])
async def test_negative_retry_never_returns_last_good_as_fresh(outcome):
    clock, calls = Clock(), []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return response(request)
        if outcome == 'network':
            raise httpx.ConnectError('offline', request=request)
        return response(request, outcome, 503 if outcome == 'busy' else 200)
    async with client_for(handler, clock) as client:
        good = await client.read_job_detail(JOB)
        clock.advance(30)
        error = await client.read_job_detail(JOB)
        assert error.payload == ({'error': 'busy'} if outcome == 'busy' else None)
        assert error.observed_at is None and good.observed_at == 1000
        retained = client._detail_memo[JOB].last_good
        assert retained.payload == CASES['active'] and retained.observed_at == 1000
        clock.advance(14)
        assert (await client.read_job_detail(JOB)).from_cache
        assert len(calls) == 2
        clock.advance(1)
        assert (await client.read_job_detail(JOB)).observed_at is None
        assert len(calls) == 3


async def test_response_job_id_mismatch_is_not_cached():
    calls = []
    def handler(request):
        calls.append(request)
        return response(request, 'foreign' if len(calls) == 1 else 'active')
    clock = Clock()
    async with client_for(handler, clock) as client:
        assert (await client.read_job_detail(JOB)).payload is None
        clock.advance(15)
        assert (await client.read_job_detail(JOB)).payload == CASES['active']
        assert len(calls) == 2


@pytest.mark.parametrize('negative', [False, True])
async def test_lru_retains_400_entries_and_touch_protects_oldest(negative):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=CASES['invalid'][1] if negative else
                              dict(CASES['terminal'], id=request.url.path[6:]))
    async with client_for(handler) as client:
        for index in range(400):
            await client.fetch_job(f'job-{index}')
        await client.fetch_job('job-0')
        await client.fetch_job('job-400')
        await client.fetch_job('job-0')
        assert len(calls) == 401
        await client.fetch_job('job-1')
        assert len(calls) == 402


async def test_client_scope_never_reuses_other_instance_or_changed_host(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.host)
        return response(request)
    async with client_for(handler) as first, client_for(handler) as second:
        await first.fetch_job(JOB)
        await second.fetch_job(JOB)
        first._hosts = ('https://two.test',)
        assert not (await first.read_job_detail(JOB)).from_cache
        assert calls == ['one.test', 'one.test', 'two.test']
        monkeypatch.setattr('maxpane_dashboard.data.surf_swarm_client._DETAIL_API_VERSION', 'jobs-v2')
        assert not (await first.read_job_detail(JOB)).from_cache
        assert calls == ['one.test', 'one.test', 'two.test', 'two.test']


async def test_last_cancelled_waiter_leaves_no_registered_flight():
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def handler(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    async with client_for(handler) as client:
        reader = asyncio.create_task(client.fetch_job(JOB))
        await entered.wait()
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        await cancelled.wait()
        await turn()
        assert client._detail_flights == {}
        assert client._detail_epochs == {}


async def test_byte_budget_evicts_complete_entries_before_400_limit():
    medium = json.loads((ROOT / 'bounded.json').read_text())
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path.startswith('/jobs/')
        return httpx.Response(200, json=dict(medium, id=request.url.path[6:]))
    async with client_for(handler) as client:
        for index in range(64):
            read = await client.read_job_detail(f'job-{index}')
            assert read.payload == dict(medium, id=f'job-{index}')
        assert (await client.read_job_detail('job-63')).from_cache
        assert len(calls) == 64
        assert not (await client.read_job_detail('job-0')).from_cache
        assert len(calls) == 65
        assert sum(entry.size for entry in client._detail_memo.values()) <= 16 * 1024 * 1024


@pytest.mark.parametrize('bad', [True, False, '0', float('nan'), float('inf')])
async def test_invalid_freshness_never_sends_request(bad):
    def handler(request):
        raise AssertionError(f'unexpected request: {request.url}')
    async with client_for(handler) as client:
        assert (await client.read_job_detail(JOB, fresh_after=bad)).payload is None


async def test_zero_freshness_reuses_zero_start_and_pacing_uses_real_start():
    clock, paced, release = Clock(), asyncio.Event(), asyncio.Event()
    calls = []
    async def sleep(delay):
        paced.set()
        await release.wait()
    def handler(request):
        calls.append(request)
        return response(request)
    async with client_for(handler, clock, sleep=sleep) as client:
        old = asyncio.create_task(client.read_job_detail(JOB))
        await paced.wait()
        clock.advance(1)
        fresh = asyncio.create_task(client.read_job_detail(JOB, fresh_after=1))
        await turn()
        release.set()
        a, b = await asyncio.gather(old, fresh)
        assert a.started_mono == b.started_mono == 1 and len(calls) == 1
        assert (await client.read_job_detail(JOB, fresh_after=0)).from_cache


async def test_bad_or_absent_list_metadata_does_not_invalidate():
    clock, calls = Clock(), []
    invalid = json.loads((ROOT / 'cases.json').read_text())['invalid_metadata']
    def handler(request):
        calls.append(request)
        if request.url.path == '/jobs':
            return httpx.Response(200, json=invalid)
        return response(request)
    async with client_for(handler, clock) as client:
        await client.read_job_detail(JOB)
        await client.fetch_jobs()
        assert (await client.read_job_detail(JOB)).from_cache
        assert len(calls) == 2


async def test_changed_scope_rejects_late_response_even_if_transport_ignores_cancel():
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(request):
        calls.append(request.url.host)
        if request.url.host == 'one.test':
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
                return response(request)
        return response(request, 'changed')
    async with client_for(handler) as client:
        old = asyncio.create_task(client.read_job_detail(JOB))
        await entered.wait()
        client._hosts = ('https://two.test',)
        fresh = asyncio.create_task(client.read_job_detail(JOB))
        await cancelled.wait()
        assert (await client.read_job_detail(JOB)).payload == CASES['changed']
        release.set()
        a, b = await asyncio.gather(old, fresh)
        assert a.payload == b.payload == CASES['changed']
        assert calls == ['one.test', 'two.test']


async def test_host_order_and_normalized_names_share_same_deployment_scope():
    calls = []
    def handler(request):
        calls.append(request.url.host)
        return response(request)
    async with client_for(handler, hosts=('https://ONE.test/', 'https://two.test')) as client:
        await client.read_job_detail(JOB)
        client._hosts = ('https://two.test', 'https://one.test')
        assert (await client.read_job_detail(JOB)).from_cache
        assert calls == ['one.test']


@pytest.mark.parametrize('owned', [False, True])
async def test_close_drains_retiring_scope_flight_before_http_shutdown(owned):
    entered, cancelled, drain = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cleanup_finished = asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request.url.host)
        assert request.url.host == 'one.test'
        try:
            entered.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await drain.wait()
            return response(request)
        finally:
            cleanup_finished.set()

    async with client_for(handler) as client:
        client._owns_client = owned
        original = asyncio.create_task(client.read_job_detail(JOB))
        await entered.wait()
        client._hosts = ('https://two.test',)
        scope_change = asyncio.create_task(client.read_job_detail(JOB))
        await cancelled.wait()
        closing = asyncio.create_task(client.close())
        await turn()
        try:
            assert not closing.done(), 'close must await the retired scope flight'
            assert not client._client.is_closed
            assert not cleanup_finished.is_set()
        finally:
            drain.set()
            await asyncio.gather(original, scope_change, closing)
        assert cleanup_finished.is_set()
        assert client._client.is_closed is owned
        assert calls == ['one.test']
        assert original.result().payload is None and scope_change.result().payload is None
