"""Single-flight work reader, with fake client calls only."""
import asyncio
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maxpane_dashboard.data.surf_cache import SurfCache, SLOT_SURF_WORK, TIER_SURF_WORK
from maxpane_dashboard.data.surf_work_reader import WorkReader


@pytest.fixture
def setup(tmp_path):
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    clock = SimpleNamespace(now=raw['read_ts'])
    cache = SurfCache(path=str(tmp_path / 'cache.json'), clock=lambda: clock.now)

    class Client:
        calls = []
        async def fetch_jobs(self, *, limit):
            self.calls.append(('jobs', limit)); return raw['jobs']
        async def fetch_workflows(self, *, limit):
            self.calls.append(('workflows', limit)); return raw['workflows']
        async def fetch_job(self, identity):
            self.calls.append(('detail', identity))
            return next((d for d in raw['details'] if d['id'] == identity), None)

    client = Client()
    reader = WorkReader(client, cache, clock=lambda: clock.now)
    return reader, client, cache, clock, raw


@pytest.mark.asyncio
async def test_bounded_single_flight_and_ttl(setup):
    reader, client, cache, clock, raw = setup
    task = reader.offer()
    assert reader.offer() is task
    await task
    assert client.calls[:2] == [('jobs', 100), ('workflows', 100)]
    assert client.calls[2][1] == raw['jobs'][0]['id']
    assert reader.project()['summary']['jobs'] == 2
    assert reader.project()['partial']
    assert reader.offer() is None
    clock.now += 60
    assert reader.offer() is not None
    await reader.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['list', 'detail'])
async def test_failure_retains_entire_prior_snapshot_and_stops_fanout(setup, stage):
    reader, client, cache, clock, raw = setup
    await reader.offer()
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    clock.now += 60; client.calls.clear()
    if stage == 'list':
        async def failed(*, limit): client.calls.append(('failed', limit)); return None
        client.fetch_jobs = failed
    else:
        async def busy(identity): client.calls.append(('busy', identity)); return {'error': 'busy'}
        client.fetch_job = busy
    await reader.offer()
    assert cache.get_last_good(SLOT_SURF_WORK) == before
    assert reader.project()['state'] == 'stale'
    assert len(client.calls) == (1 if stage == 'list' else 3)
    clock.now += 119
    assert reader.offer() is None
    clock.now += 1
    assert reader.offer() is not None
    await reader.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['jobs', 'workflows'])
@pytest.mark.parametrize('warm', [False, True])
async def test_nonempty_all_malformed_page_is_failed_read(setup, route, warm):
    reader, client, cache, clock, raw = setup
    if warm:
        await reader.offer()
        clock.now += 60
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    client.calls.clear()
    raw[route] = [{'id': False}, {'id': 'not-a-uuid'}]
    await reader.offer()
    assert cache.get_last_good(SLOT_SURF_WORK) == before
    assert not any(call[0] == 'detail' for call in client.calls)
    data = reader.project()
    assert data['state'] == ('stale' if warm else 'unavailable')
    assert data['summary']['jobs'] == (2 if warm else None)
    assert cache.last_failure_ts(TIER_SURF_WORK) == clock.now


@pytest.mark.asyncio
async def test_detail_budget_deduplicates_and_marks_missing(setup):
    reader, client, cache, clock, raw = setup
    raw['jobs'] = [dict(raw['jobs'][0], id=f'00000000-0000-0000-0000-{n:012d}') for n in range(30)]
    raw['workflows'] = []
    await reader.offer()
    assert sum(call[0] == 'detail' for call in client.calls) == 24
    data = reader.project()
    assert data['details_expected'] == 30 and data['details_loaded'] == 0
    assert data['partial'] and data['summary']['build'] is None


@pytest.mark.asyncio
async def test_cancellation_does_not_publish_partial_or_failure(setup):
    reader, client, cache, clock, raw = setup
    entered = asyncio.Event()
    async def hanging(identity):
        entered.set(); await asyncio.Event().wait()
    client.fetch_job = hanging
    task = reader.offer()
    await entered.wait()
    reader.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert cache.get_last_good(SLOT_SURF_WORK) is None
    assert cache.last_failure_ts(TIER_SURF_WORK) is None
    assert task.cancelled()


@pytest.mark.asyncio
async def test_persisted_snapshot_restores_but_refuses_unvalidated_slot(setup, tmp_path):
    reader, client, cache, clock, raw = setup
    await reader.offer()
    cache.save()
    cold = SurfCache(path=cache.path, clock=lambda: clock.now)
    cold.load()
    assert cold.get_last_good(SLOT_SURF_WORK) is None
    from maxpane_dashboard.data.surf_work import coerce_snapshot
    cold.load(slot_coercers={SLOT_SURF_WORK: lambda v: coerce_snapshot(v, now=clock.now)})
    assert cold.get_last_good(SLOT_SURF_WORK) == cache.get_last_good(SLOT_SURF_WORK)


@pytest.mark.asyncio
async def test_manager_visibility_has_no_io_and_leaving_cancels(setup, tmp_path):
    from maxpane_dashboard.data.surf_manager import SurfManager
    reader, client, cache, clock, raw = setup
    entered = asyncio.Event()
    class QuietClient:
        async def close(self): pass
    async def hanging(*, limit):
        entered.set(); await asyncio.Event().wait()
    client.fetch_jobs = hanging
    client.close = QuietClient().close
    manager = SurfManager(client=QuietClient(), swarm_client=client, pool4_client=QuietClient(),
                          npm_client=QuietClient(), cache=cache, clock=lambda: clock.now)
    manager._offer_full = lambda _: pytest.fail('WIP must not await unrelated pipelines')
    manager.set_work_active(True)
    assert not entered.is_set() and manager._work_reader.task is None
    data = await manager.fetch_and_compute()
    assert data['surf_work']['state'] == 'unavailable'
    await entered.wait()
    task = manager._work_reader.task
    manager.set_work_active(False)
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert cache.get_last_good(SLOT_SURF_WORK) is None
    await manager.close()


@pytest.mark.asyncio
async def test_manager_inactive_never_offers_work(setup):
    from maxpane_dashboard.data.surf_manager import SurfManager
    reader, client, cache, clock, raw = setup
    class QuietClient:
        async def close(self): pass
    manager = SurfManager(client=QuietClient(), swarm_client=client, pool4_client=QuietClient(),
                          npm_client=QuietClient(), cache=cache, clock=lambda: clock.now)
    manager._offer_full = lambda _: None
    async def seat(*args): pass
    manager._offer_swarm_seat = seat
    manager._spawn_runtime_latest = lambda *args: None
    await manager.fetch_and_compute()
    assert manager._work_reader.task is None
    await manager.close()


@pytest.mark.asyncio
async def test_read_clock_starts_before_slow_collection(setup):
    reader, client, cache, clock, raw = setup
    started = clock.now
    fetch = client.fetch_job
    async def slow(identity):
        clock.now = started + 180
        result = await fetch(identity)
        if result:
            result["updatedAt"] = datetime.fromtimestamp(int(clock.now), timezone.utc).isoformat()
        return result
    client.fetch_job = slow
    await reader.offer()
    data = reader.project()
    assert data['read_ts'] == started
    assert data['jobs'][0]['updated_ts'] == int(clock.now)
    assert data['state'] == 'stale'
    assert data['summary']['jobs'] == 2
    assert reader.offer() is None  # refresh TTL starts at completion
