"""Surf-only host admission and refresh-local head sharing; no real sleeps/I/O."""
import asyncio
from email.utils import formatdate

import httpx
import pytest

from maxpane_dashboard.data.surf_transport import (
    HostCoordinator, HostCoolingDown, SurfTransport, read_cycle,
)


class Clock:
    def __init__(self):
        self.now = 100.

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_parallel_clients_share_host_admission():
    clock = Clock()
    coordinator = HostCoordinator(monotonic=clock, clock=clock, sleep=clock.sleep)
    starts = []
    async def answer(request):
        starts.append(clock())
        return httpx.Response(200, json={'result': '0x10'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        a = SurfTransport(delay=.25, coordinator=coordinator)
        b = SurfTransport(delay=.25, coordinator=coordinator)
        await asyncio.gather(*(client.post(http, 'https://rpc.example/a', {})
                               for client in (a, b, a, b)))
    assert len(starts) == 4
    assert all(right - left >= .25 for left, right in zip(starts, starts[1:]))


@pytest.mark.asyncio
async def test_stricter_waiter_interval_is_respected_before_dispatch():
    clock = Clock()
    coordinator = HostCoordinator(monotonic=clock, clock=clock, sleep=clock.sleep)
    starts = []
    await coordinator.acquire('https://rpc.example', .25)
    async def admit(delay):
        await coordinator.acquire('https://rpc.example', delay)
        starts.append(clock())
    await asyncio.gather(admit(.25), admit(1.))
    assert starts == [101., 102.]


@pytest.mark.asyncio
@pytest.mark.parametrize('retry,seconds', [('7', 7), (formatdate(111, usegmt=True), 11),
                                         ('garbage', 60), ('nan', 60)])
async def test_429_cools_all_clients_but_not_alternatives(retry, seconds):
    clock = Clock()
    coordinator = HostCoordinator(monotonic=clock, clock=clock, sleep=clock.sleep)
    urls = []
    async def answer(request):
        urls.append(str(request.url))
        return httpx.Response(429, headers={'Retry-After': retry})
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        a, b = (SurfTransport(delay=0, coordinator=coordinator) for _ in range(2))
        await a.post(http, 'https://rpc.example/a', {})
        with pytest.raises(HostCoolingDown):
            await b.post(http, 'https://rpc.example/b', {})
        await b.post(http, 'https://alternate.example/', {})
        assert len(urls) == 2
        assert clock() == 100
        clock.now += seconds
        await b.post(http, 'https://rpc.example/b', {})
        assert len(urls) == 3


@pytest.mark.asyncio
async def test_cancelled_wait_does_not_reserve_future_slot():
    clock = Clock()
    waiting = asyncio.Event()
    async def pause(seconds):
        waiting.set()
        await asyncio.Future()
    coordinator = HostCoordinator(monotonic=clock, clock=clock, sleep=pause)
    await coordinator.acquire('https://rpc.example', .5)
    task = asyncio.create_task(coordinator.acquire('https://rpc.example', .5))
    observed = asyncio.create_task(waiting.wait())
    await asyncio.wait({task, observed}, return_when=asyncio.FIRST_COMPLETED)
    if not waiting.is_set():
        observed.cancel()
        await asyncio.gather(observed, return_exceptions=True)
        pytest.fail('second admission bypassed its host wait')
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    clock.now += .5
    await coordinator.acquire('https://rpc.example', .5)


@pytest.mark.asyncio
async def test_head_singleflight_is_per_chain_and_per_explicit_refresh():
    calls = []
    a, b = SurfTransport(delay=0), SurfTransport(delay=0)
    async def read():
        calls.append(1)
        await asyncio.sleep(0)
        return hex(100 + len(calls))
    @read_cycle
    async def refresh():
        result = await asyncio.gather(a.head(1, read), b.head(1, read))
        assert result[0] == result[1]
        await b.head(4663, read)
    await refresh()
    assert len(calls) == 2
    await refresh()
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_bad_head_is_never_cached():
    transport = SurfTransport(delay=0)
    replies = iter([None, 'bad', '0x10'])
    async def read():
        return next(replies)
    @read_cycle
    async def refresh():
        assert await transport.head(1, read) is None
        assert await transport.head(1, read) == 'bad'
        assert await transport.head(1, read) == '0x10'
    await refresh()


@pytest.mark.asyncio
async def test_block_proof_is_endpoint_specific_and_shared_within_refresh():
    calls = []
    async def answer(request):
        import json
        payload = json.loads(request.content)
        calls.append((request.url.host, payload['method']))
        height = payload['params'][0]
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': payload['id'],
                                        'result': None if request.url.host == 'lagging.example'
                                        else {'number': height}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        transport = SurfTransport(delay=0)
        @read_cycle
        async def refresh():
            assert await transport.prove_block(http, 'https://ready.example', 100)
            assert await transport.prove_block(http, 'https://ready.example', 100)
            assert not await transport.prove_block(http, 'https://lagging.example', 100)
        await refresh()
        assert len(calls) == 2
        await refresh()
        assert len(calls) == 4


@pytest.mark.asyncio
async def test_real_surf_and_launch_clients_share_429_without_retry_wait():
    import json
    from maxpane_dashboard.data.surf_client import SurfClient
    from maxpane_dashboard.data.surf_launch_base_client import SwarmBaseClient
    from maxpane_dashboard.data.surf_launch_rh_client import SwarmRobinhoodClient
    clock = Clock()
    transport = SurfTransport(delay=0, coordinator=HostCoordinator(
        monotonic=clock, clock=clock, sleep=clock.sleep))
    hosts = []
    async def answer(request):
        hosts.append(request.url.host)
        if request.url.host == 'busy.example':
            return httpx.Response(429, headers={'Retry-After': '60'})
        batch = json.loads(request.content)
        return httpx.Response(200, json=[dict(jsonrpc='2.0', id=call['id'], result='0x10')
                                        for call in batch])
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        urls = ['https://busy.example', 'https://ready.example']
        surf = SurfClient(http_client=http, state_rpc=urls[0], state_fallbacks=urls[1:],
                          inter_call_delay=0)
        surf._transport = transport
        calls = [('eth_call', [{'to': '0x' + '1' * 40, 'data': '0x18160ddd'}, 'latest'])]
        assert await surf.fetch_launch_pool_state(calls) == ['0x10']
        for cls in (SwarmBaseClient, SwarmRobinhoodClient):
            client = cls(http_client=http, rpcs=urls, transport=transport)
            assert await client.fetch_launch_pool_state(calls) == ['0x10']
    assert hosts == ['busy.example', 'ready.example', 'ready.example', 'ready.example']
    assert clock() == 100
