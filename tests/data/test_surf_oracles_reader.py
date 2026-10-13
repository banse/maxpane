"""Detached selected-only oracle reads, fake clients and deterministic clocks."""
import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from maxpane_dashboard.data.surf_cache import SurfCache, SLOT_SURF_ORACLES, TIER_SURF_ORACLES
from maxpane_dashboard.data.surf_oracles_reader import OraclesReader
from maxpane_dashboard.data.surf_oracles import coerce_snapshot
from maxpane_dashboard.data.surf_swarm_client import SwarmClient


@pytest.fixture
def setup(tmp_path):
    raw = json.loads(Path('tests/fixtures/surf/oracles/captured.json').read_text())
    clock = SimpleNamespace(now=raw['read_ts'])
    cache = SurfCache(path=str(tmp_path / 'cache.json'), clock=lambda: clock.now)
    class Client:
        def __init__(self): self.calls = []
        async def fetch_oracle_requests(self, *, limit):
            self.calls.append(('list', limit)); return raw['requests']
        async def fetch_oracle_detail(self, identity):
            self.calls.append(('detail', identity)); return raw['details'].get(identity)
        async def close(self): pass
    client = Client()
    return OraclesReader(client, cache, clock=lambda: clock.now), client, cache, clock, raw


@pytest.mark.asyncio
async def test_single_flight_list_budget_selected_only_and_getter_no_io(setup):
    reader, client, cache, clock, raw = setup
    assert reader.project()['rows'] is None
    task = reader.offer(); assert reader.offer() is task
    await task
    data = reader.project()
    assert client.calls == [('list', 100), ('detail', raw['requests'][0]['id'])]
    assert data['state'] == 'ok' and data['detail_state'] == 'ok'
    assert data['selected_id'] == data['detail']['id'] == raw['requests'][0]['id']
    assert data['partial']
    assert reader.offer() is None
    clock.now += 60
    await reader.offer()
    assert client.calls[-1] == ('list', 100)  # terminal detail retained
    before = list(client.calls)
    reader.project(); reader.project()
    assert client.calls == before


@pytest.mark.asyncio
async def test_empty_and_failed_lists_are_distinct_and_retry_backoff(setup):
    reader, client, cache, clock, raw = setup
    raw['requests'] = []
    await reader.offer()
    assert reader.project()['rows'] == [] and reader.project()['state'] == 'ok'
    assert client.calls == [('list', 100)]
    prior = copy.deepcopy(cache.get_last_good(SLOT_SURF_ORACLES))
    raw['requests'] = None; clock.now += 60
    await reader.offer()
    assert cache.get_last_good(SLOT_SURF_ORACLES) == prior
    assert reader.project()['state'] == 'stale'
    assert reader.project()['read_ts'] == raw['read_ts']
    clock.now += 119; assert reader.offer() is None
    clock.now += 1; await reader.offer()
    assert cache.last_failure_ts(TIER_SURF_ORACLES) == clock.now


@pytest.mark.asyncio
async def test_request_without_job_stays_listed_but_detail_is_unavailable(setup):
    reader, client, cache, clock, raw = setup
    identity = raw['requests'][0]['id']
    raw['requests'] = [dict(raw['requests'][0], jobId=None)]
    await reader.offer()
    data = reader.project()
    assert data['state'] == 'ok' and data['rows'][0]['id'] == identity
    assert data['rows'][0]['job_id'] is None and data['selected_id'] == identity
    assert client.calls == [('list', 100)]
    assert data['detail'] is None and data['detail_read_ts'] is None
    assert data['detail_state'] == 'unavailable'


@pytest.mark.asyncio
async def test_selection_race_drains_latest_without_cross_request_display(setup):
    reader, client, cache, clock, raw = setup
    first, second, third = list(raw['details'])[:3]
    entered, release = asyncio.Event(), asyncio.Event()
    fetch = client.fetch_oracle_detail
    async def hanging(identity):
        if identity == first:
            entered.set(); await release.wait()
        return await fetch(identity)
    client.fetch_oracle_detail = hanging
    task = reader.offer(); await entered.wait()
    reader.select(second); assert reader.offer() is task
    reader.select(third); assert reader.offer() is task
    assert reader.project()['selected_id'] == third
    assert reader.project()['detail'] is None
    release.set(); await task
    data = reader.project()
    assert data['detail']['id'] == data['selected_id'] == third
    assert data['detail_state'] == 'ok'
    assert [value for kind, value in client.calls if kind == 'detail'] == [first, third]


@pytest.mark.asyncio
async def test_detail_failure_preserves_old_timestamp_and_is_per_request(setup):
    reader, client, cache, clock, raw = setup
    first, second = list(raw['details'])[:2]
    raw['details'][first]['status'] = raw['requests'][0]['status'] = 'assessing'
    await reader.offer()
    old = reader.project()['detail']
    clock.now += 120; raw['details'][first] = None
    await reader.offer()
    assert reader.project()['detail'] == old
    assert reader.project()['detail_state'] == 'stale'
    assert reader.project()['detail_read_ts'] == raw['read_ts']
    reader.select(second); await reader.offer()
    assert reader.project()['detail']['id'] == second
    assert reader.project()['detail_state'] == 'ok'  # mismatch retained as live source status
    reader.select(first); assert reader.offer() is None
    clock.now += 120; await reader.offer()
    assert reader.project()['detail_state'] == 'stale'


@pytest.mark.asyncio
async def test_terminal_invalidated_by_row_status_or_updated_timestamp(setup):
    reader, client, cache, clock, raw = setup
    await reader.offer()
    first = raw['requests'][0]
    first['status'] = 'disagreed'; raw['details'][first['id']]['status'] = 'disagreed'
    clock.now += 60; await reader.offer()
    assert reader.project()['detail']['status'] == 'disagreed'
    assert len([c for c in client.calls if c[0] == 'detail']) == 2
    first['updatedAt'] = first['createdAt']
    clock.now += 60; await reader.offer()
    assert len([c for c in client.calls if c[0] == 'detail']) == 3


@pytest.mark.asyncio
async def test_expired_terminal_retains_stale_disk_evidence_until_replaced(setup):
    reader, client, cache, clock, raw = setup
    await reader.offer()
    before = reader.project()
    clock.now += 86401
    raw['details'][before['selected_id']] = None
    await reader.offer()
    after = reader.project()
    assert after['detail'] == before['detail'] and after['detail_state'] == 'stale'
    assert after['detail_read_ts'] == before['detail_read_ts']
    cold = SurfCache(path=cache.path, clock=lambda: clock.now)
    cold.load(slot_coercers={SLOT_SURF_ORACLES: lambda v: coerce_snapshot(v, now=clock.now)})
    restored = OraclesReader(client, cold, clock=lambda: clock.now)
    restored.select(before['selected_id'])
    assert restored.project()['detail'] == before['detail']
    assert restored.project()['detail_state'] == 'stale'


@pytest.mark.asyncio
async def test_slow_source_reads_keep_start_clock_and_explicit_staleness(setup):
    reader, client, cache, clock, raw = setup
    first = raw['requests'][0]['id']
    raw['details'][first]['status'] = raw['requests'][0]['status'] = 'assessing'
    fetch = client.fetch_oracle_detail
    async def slow(identity):
        clock.now += 121
        return await fetch(identity)
    client.fetch_oracle_detail = slow
    await reader.offer()
    data = reader.project()
    assert data['read_ts'] == data['detail_read_ts'] == raw['read_ts']
    assert data['state'] == data['detail_state'] == 'stale'


@pytest.mark.asyncio
async def test_manager_inactive_does_not_offer_and_deactivation_cancels(setup):
    from maxpane_dashboard.data.surf_manager import SurfManager
    reader, client, cache, clock, raw = setup
    class Quiet:
        async def close(self): pass
    manager = SurfManager(client=Quiet(), pool4_client=Quiet(), npm_client=Quiet(),
                          swarm_client=client, cache=cache, clock=lambda: clock.now)
    manager.set_oracle_request(raw['requests'][0]['id'])
    assert manager._oracles_reader.task is None and client.calls == []
    manager.get_oracles_snapshot()
    assert client.calls == []
    entered = asyncio.Event()
    async def hanging(*, limit):
        entered.set(); await asyncio.Event().wait()
    client.fetch_oracle_requests = hanging
    manager.set_oracles_active(True)
    await manager.fetch_and_compute(); await entered.wait()
    task = manager._oracles_reader.task
    manager.set_oracles_active(False)
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled() and cache.get_last_good(SLOT_SURF_ORACLES) is None
    await manager.close()


@pytest.mark.asyncio
async def test_cancel_and_close_never_publish_inflight_detail(setup):
    reader, client, cache, clock, raw = setup
    entered = asyncio.Event()
    async def hanging(identity):
        entered.set(); await asyncio.Event().wait()
    client.fetch_oracle_detail = hanging
    task = reader.offer(); await entered.wait(); await reader.close()
    assert task.cancelled()
    assert cache.get_last_good(SLOT_SURF_ORACLES).payload['details'] == {}
    assert reader.project()['detail_read_ts'] is None


@pytest.mark.asyncio
async def test_lru_eight_details_and_disk_validation(setup):
    reader, client, cache, clock, raw = setup
    base = copy.deepcopy(raw['detail'])
    raw['requests'] = []
    for i in range(10):
        identity = f'00000000-0000-4000-8000-{i:012d}'
        body = dict(base, id=identity)
        raw['details'][identity] = body; raw['requests'].append(body)
    await reader.offer()
    for row in raw['requests'][1:]:
        clock.now += 1; reader.select(row['id']); await reader.offer()
    details = cache.get_last_good(SLOT_SURF_ORACLES).payload['details']
    assert len(details) == 8
    assert raw['requests'][0]['id'] not in details
    cold = SurfCache(path=cache.path, clock=lambda: clock.now)
    cold.load(); assert cold.get_last_good(SLOT_SURF_ORACLES) is None
    cold.load(slot_coercers={SLOT_SURF_ORACLES: lambda v: coerce_snapshot(v, now=clock.now)})
    assert cold.get_last_good(SLOT_SURF_ORACLES) == cache.get_last_good(SLOT_SURF_ORACLES)


@pytest.mark.asyncio
async def test_manager_active_path_detached_selection_immediate_and_cancel(setup):
    from maxpane_dashboard.data.surf_manager import SurfManager
    reader, client, cache, clock, raw = setup
    class Quiet:
        async def close(self): pass
    manager = SurfManager(client=Quiet(), pool4_client=Quiet(), npm_client=Quiet(),
                          swarm_client=client, cache=cache, clock=lambda: clock.now)
    manager._offer_full = lambda _: pytest.fail('unrelated collection in oracle mode')
    manager.set_oracles_active(True)
    assert manager._oracles_reader.task is None
    initial = await manager.fetch_and_compute()
    assert initial['surf_oracles']['rows'] is None
    await manager._oracles_reader.task
    assert manager.get_oracles_snapshot()['rows']
    second = list(raw['details'])[1]
    manager.set_oracle_request(second)
    await manager._oracles_reader.task
    assert manager.get_oracles_snapshot()['detail']['id'] == second
    manager.set_oracles_active(False)
    await manager.close()


@pytest.mark.asyncio
async def test_full_detail_endpoint_validates_uuid_and_preserves_filtered_route():
    identity = '00000000-0000-4000-8000-000000000001'
    seen = []
    def handler(request):
        seen.append(str(request.url)); return httpx.Response(200, json={'id': identity})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SwarmClient(http_client=http, hosts=('https://one.test',), inter_call_delay=0)
        assert await client.fetch_oracle_detail('../bad') is None
        assert seen == []
        assert await client.fetch_oracle_detail(identity) == {'id': identity}
        assert await client.fetch_oracle_request(identity, 'a' * 64) == {'id': identity}
    assert seen == ['https://one.test/oracle/requests/' + identity,
                    'https://one.test/oracle/requests/' + identity + '?members=' + 'a' * 64]
