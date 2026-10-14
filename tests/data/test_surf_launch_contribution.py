"""All-history launch contribution must not rank a partially read fleet."""
import asyncio
import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from maxpane_dashboard.data.surf_cache import SurfCache, SLOT_SWARM_LAUNCH_CONTRIBUTION
from maxpane_dashboard.data.surf_launch_contribution import LaunchContributionReader

NOW = 1_800_000_000.0
FIXTURE = Path('tests/fixtures/surf/launch_contribution/captured.json')


class Client:
    def __init__(self, raw):
        self.raw = raw
        self.calls = []
        self.wait = None

    async def read(self, kind, identity):
        self.calls.append((kind, identity))
        if self.wait is not None:
            await self.wait.wait()
        value = self.raw[kind].get(identity)
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    async def fetch_launch_jobs(self, identity):
        return await self.read('launches', identity)

    async def fetch_job(self, identity):
        return await self.read('jobs', identity)

    async def fetch_workflow(self, identity):
        return await self.read('workflows', identity)


@pytest.fixture
def setup(tmp_path):
    raw = json.loads(FIXTURE.read_text())
    clock = [NOW]
    cache = SurfCache(str(tmp_path / 'cache.json'), clock=lambda: clock[0])
    client = Client(raw)
    reader = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    return reader, client, raw, cache, clock


async def batch(reader, raw, **kwargs):
    reader.offer(raw['catalogue'], read_ts=NOW, complete=True, **kwargs)
    if reader.task is not None:
        await reader.task
    return reader.project()


@pytest.mark.asyncio
async def test_real_launches_include_verified_frontend_and_count_jobs_once(setup):
    reader, client, raw, cache, _ = setup
    before = copy.deepcopy(raw)
    result = await batch(reader, raw)
    assert result['state'] == 'ok' and result['loaded'] == result['total'] == 2
    rows = {row['token_id']: row for row in result['rows']}
    assert rows[401]['jobs'] == rows[402]['jobs'] == 1
    assert rows[401]['launches'] == rows[402]['launches'] == 1
    assert 717 in rows and 863 in rows
    assert sorted(row['rank'] for row in result['rows']) == list(range(1, len(rows) + 1))
    assert raw == before
    assert not any(word in json.dumps(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
                   for word in ('objective', 'deviceKey', 'wallet', 'brief'))
    reader.offer(raw['catalogue'], complete=True, read_ts=NOW)
    assert reader.task is None or reader.task.done()
    assert len(client.calls) == 6  # two launches, three jobs, one workflow


@pytest.mark.asyncio
async def test_deduplicates_seat_nodes_and_job_across_launches_excludes_oracle(setup):
    reader, client, raw, _, _ = setup
    first, second = raw['catalogue']
    job = raw['launches'][first['id']]['jobs'][0]['id']
    raw['launches'][second['id']]['jobs'] = [{'id': job}]
    raw['jobs'][job]['nodes'] = [
        {'key': 'build', 'state': 'accepted', 'seat': {'tokenId': '7'}},
        {'key': 'review', 'state': 'accepted', 'seat': {'tokenId': '7'}},
        {'key': 'oracle_assess', 'state': 'accepted', 'seat': {'tokenId': '8'}},
        {'key': 'failed', 'state': 'failed', 'seat': {'tokenId': '9'}},
        {'key': 'pending', 'state': 'working', 'seat': {'tokenId': '10'}},
    ]
    result = await batch(reader, raw)
    assert result['rows'] == [{'rank': 1, 'token_id': 7, 'jobs': 1, 'launches': 2}]
    assert client.calls.count(('jobs', job)) == 1


@pytest.mark.asyncio
async def test_testnet_and_parked_excluded_before_any_detail_read(setup):
    reader, client, raw, _, _ = setup
    raw['catalogue'][0]['chainId'] = 11155111
    raw['catalogue'][1]['status'] = 'parked'
    result = await batch(reader, raw)
    assert result['state'] == 'ok' and result['rows'] == [] and result['total'] == 0
    assert client.calls == []


@pytest.mark.asyncio
async def test_first_loading_no_provisional_ranking_and_cancel_is_not_failure(setup):
    reader, client, raw, _, _ = setup
    client.wait = asyncio.Event()
    reader.offer(raw['catalogue'], complete=True, read_ts=NOW)
    assert reader.project()['state'] == 'pending' and reader.project()['rows'] is None
    task = reader.task
    reader.cancel()
    await reader.close()
    assert task is not None and task.done()
    assert reader.project()['state'] not in ('failed', 'stale')
    client.wait = None
    assert (await batch(reader, raw))['state'] == 'ok'


@pytest.mark.asyncio
async def test_partial_catalogue_can_warm_facts_but_cannot_publish_all_history(setup):
    reader, client, raw, _, _ = setup
    reader.offer(raw['catalogue'], complete=False, read_ts=NOW)
    if reader.task is not None:
        await reader.task
    result = reader.project()
    assert result['state'] == 'pending' and result['rows'] is None
    assert result['loaded'] == 2
    calls = len(client.calls)
    assert (await batch(reader, raw))['state'] == 'ok'
    assert len(client.calls) == calls


@pytest.mark.asyncio
async def test_initial_catalogue_pending_without_timestamp_is_loading(setup):
    reader, client, _, _, _ = setup
    assert reader.project()['state'] == 'pending'
    assert reader.project()['detail'] == 'loading launch catalogue'
    assert reader.project()['rows'] is None
    reader.offer([], complete=False, read_ts=None)
    assert reader.project()['state'] == 'pending'
    assert reader.project()['rows'] is None and reader.project()['total'] is None
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [None, {'error': 'busy'}, RuntimeError('read failed')])
async def test_failed_read_stops_fanout_and_backoff_then_retries(setup, failure):
    reader, client, raw, _, clock = setup
    identity = raw['catalogue'][0]['id']
    good = raw['launches'][identity]
    raw['launches'][identity] = failure
    result = await batch(reader, raw)
    assert result['state'] == 'failed' and result['rows'] is None
    assert len(client.calls) == 1
    raw['launches'][identity] = good
    clock[0] += 119
    await batch(reader, raw)
    assert len(client.calls) == 1
    clock[0] += 1
    assert (await batch(reader, raw))['state'] == 'ok'


@pytest.mark.asyncio
async def test_last_complete_ranking_survives_refresh_failure_and_restart(setup):
    reader, client, raw, cache, clock = setup
    good = await batch(reader, raw)
    raw['catalogue'][0]['updatedAt'] = '2026-10-14T23:00:00.000Z'
    raw['launches'][raw['catalogue'][0]['id']] = None
    clock[0] += 1
    failed = await batch(reader, raw)
    assert failed['state'] == 'stale' and failed['rows'] == good['rows']
    assert failed['read_ts'] == good['read_ts']
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert restored.project()['rows'] == good['rows']
    assert restored.project()['state'] == 'pending'


@pytest.mark.asyncio
async def test_catalogue_failure_is_not_empty_and_newer_catalogue_wins_in_flight(setup):
    reader, client, raw, _, _ = setup
    good = await batch(reader, raw)
    reader.offer([], complete=False, failed=True, read_ts=None)
    assert reader.project()['rows'] == good['rows']
    assert reader.project()['state'] == 'stale'
    client.wait = asyncio.Event()
    raw['catalogue'][0]['updatedAt'] = '2026-10-14T23:00:00.000Z'
    reader.offer(raw['catalogue'], complete=True, read_ts=NOW)
    reader.offer([], complete=True, read_ts=NOW)
    client.wait.set()
    if reader.task is not None:
        await reader.task
    assert reader.project()['rows'] == [] and reader.project()['state'] == 'ok'


@pytest.mark.asyncio
@pytest.mark.parametrize('target,change', [
    ('launch', {'id': str(UUID(int=500))}), ('launch', {'chainId': True}),
    ('launch', {'status': 'parked'}), ('launch', {'jobs': [{'id': 'bad'}]}),
    ('job', {'id': str(UUID(int=500))}), ('job', {'nodes': None}),
    ('job', {'nodes': [{'key': 'build', 'state': 'accepted', 'seat': {'tokenId': True}}]}),
    ('workflow', {'id': str(UUID(int=500))}),
    ('workflow', {'launch': {'id': str(UUID(int=500)), 'status': 'live'}}),
    ('workflow', {'contracts': {'id': str(UUID(int=500))}}),
    ('workflow', {'frontend': {}}),
])
async def test_malformed_or_mismatched_evidence_never_becomes_zero(setup, target, change):
    reader, _, raw, _, _ = setup
    if target == 'launch':
        obj = raw['launches'][raw['catalogue'][0]['id']]
    elif target == 'job':
        obj = next(iter(raw['jobs'].values()))
    else:
        obj = next(iter(raw['workflows'].values()))
    obj.update(change)
    result = await batch(reader, raw)
    assert result['rows'] is None and result['state'] == 'failed'


@pytest.mark.asyncio
async def test_terminal_facts_refresh_and_frontend_changes_do_not_use_old_seats(setup):
    reader, client, raw, _, clock = setup
    good = await batch(reader, raw)
    frontend = next(iter(raw['workflows'].values()))['frontend']['id']
    raw['jobs'][frontend]['nodes'][0]['seat']['tokenId'] = '1988'
    clock[0] += 1801
    result = await batch(reader, raw)
    assert result['state'] == 'ok'
    assert 401 in {row['token_id'] for row in good['rows']}
    assert 1988 in {row['token_id'] for row in result['rows']}
    assert client.calls.count(('jobs', frontend)) == 2


@pytest.mark.asyncio
async def test_bad_cached_fact_is_refetched_without_dropping_valid_siblings(setup):
    reader, client, raw, cache, clock = setup
    await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    job = next(iter(raw['jobs']))
    payload['jobs'][job]['seats'] = [True]
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    client.calls.clear()
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert (await batch(restored, raw))['state'] == 'ok'
    assert client.calls == [('jobs', job)]


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, [], {'snapshot': {'read_ts': NOW, 'rows': [{'rank': True}]}},
                                {'launches': {'bad': {'read_ts': float('nan')}}}])
async def test_malformed_cache_is_not_a_ranking(setup, bad):
    reader, client, raw, cache, clock = setup
    if bad is not None:
        cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, bad, ts=NOW)
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert restored.project()['rows'] is None
    assert (await batch(restored, raw))['state'] == 'ok'


@pytest.mark.asyncio
async def test_bounded_batches_continue_without_provisional_rows(setup):
    reader, client, raw, _, _ = setup
    source = raw['catalogue'][0]
    launch = raw['launches'][source['id']]
    raw['catalogue'] = []
    for index in range(8):
        identity = str(UUID(int=index + 1))
        raw['catalogue'].append(dict(source, id=identity))
        raw['launches'][identity] = dict(launch, id=identity)
    first = await batch(reader, raw)
    assert first['state'] == 'pending' and first['rows'] is None
    assert 0 < first['loaded'] < 8
    second = await batch(reader, raw)
    assert second['state'] == 'ok' and second['loaded'] == 8
    assert all(row['launches'] == 8 and row['jobs'] == 1 for row in second['rows'])


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, NOW + 1, 10**1000])
async def test_invalid_source_clock_never_certifies_history(setup, value):
    reader, client, raw, _, _ = setup
    reader.offer(raw['catalogue'], complete=True, read_ts=value)
    assert reader.project()['state'] == 'failed' and reader.project()['rows'] is None
    assert client.calls == []


@pytest.mark.asyncio
async def test_duplicate_catalogue_and_duplicate_job_ids_are_not_complete(setup):
    reader, client, raw, _, _ = setup
    reader.offer(raw['catalogue'] * 2, complete=True, read_ts=NOW)
    assert reader.project()['state'] == 'failed' and client.calls == []
    launch = raw['launches'][raw['catalogue'][0]['id']]
    launch['jobs'] *= 2
    assert (await batch(reader, raw))['state'] == 'failed'
