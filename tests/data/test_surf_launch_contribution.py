"""All-history launch contribution must not rank a partially read fleet."""
import asyncio
import copy
import json
from pathlib import Path
from uuid import UUID
from unittest.mock import AsyncMock

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
    reader._sleep = AsyncMock()
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
    assert result['jobs'] == 3
    rows = {row['token_id']: row for row in result['rows']}
    assert rows[401]['jobs'] == rows[402]['jobs'] == 1
    assert rows[401]['launches'] == rows[402]['launches'] == 1
    assert (rows[401]['build_jobs'], rows[401]['review_jobs']) == (0, 1)
    assert (rows[402]['build_jobs'], rows[402]['review_jobs']) == (1, 0)
    assert (rows[849]['build_jobs'], rows[849]['review_jobs']) == (1, 0)
    assert (rows[1573]['build_jobs'], rows[1573]['review_jobs']) == (1, 0)
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
        {'key': 'build', 'role': 'implement', 'state': 'accepted', 'seat': {'tokenId': '7'}},
        {'key': 'tests', 'role': 'test', 'state': 'accepted', 'seat': {'tokenId': '7'}},
        {'key': 'review', 'role': 'review', 'state': 'accepted', 'seat': {'tokenId': '7'}},
        {'key': 'oracle_assess', 'state': 'accepted', 'seat': {'tokenId': '8'}},
        {'key': 'failed', 'state': 'failed', 'seat': {'tokenId': '9'}},
        {'key': 'pending', 'state': 'working', 'seat': {'tokenId': '10'}},
    ]
    result = await batch(reader, raw)
    assert result['rows'] == [{'rank': 1, 'token_id': 7, 'jobs': 1, 'launches': 2,
                              'build_jobs': 1, 'review_jobs': 1}]
    assert result['jobs'] == 1
    assert client.calls.count(('jobs', job)) == 1


@pytest.mark.asyncio
async def test_testnet_and_parked_excluded_before_any_detail_read(setup):
    reader, client, raw, _, _ = setup
    raw['catalogue'][0]['chainId'] = 11155111
    raw['catalogue'][1]['status'] = 'parked'
    result = await batch(reader, raw)
    assert result['state'] == 'ok' and result['rows'] == [] and result['total'] == 0
    assert result['jobs'] == 0
    assert client.calls == []


@pytest.mark.asyncio
async def test_first_loading_no_provisional_ranking_and_cancel_is_not_failure(setup):
    reader, client, raw, _, _ = setup
    client.wait = asyncio.Event()
    reader.offer(raw['catalogue'], complete=True, read_ts=NOW)
    assert reader.project()['state'] == 'pending' and reader.project()['rows'] is None
    assert reader.project()['jobs'] is None
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
    attempts = 1 if isinstance(failure, Exception) else 3
    assert len(client.calls) == attempts
    assert reader._sleep.await_count == attempts - 1
    raw['launches'][identity] = good
    clock[0] += 119
    await batch(reader, raw)
    assert len(client.calls) == attempts
    clock[0] += 1
    assert (await batch(reader, raw))['state'] == 'ok'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['launches', 'jobs', 'workflows'])
async def test_transient_failure_retries_same_read_without_losing_scan_progress(setup, kind):
    reader, client, raw, _, _ = setup
    original = client.read
    failures = [None, {'error': 'busy'}]
    async def flaky_read(source, identity):
        if source == kind and failures:
            client.calls.append((source, identity))
            return failures.pop(0)
        return await original(source, identity)
    async def delay(seconds):
        assert reader.project()['state'] == 'pending'
        assert reader.project()['rows'] is None
    client.read = flaky_read
    reader._sleep.side_effect = delay
    result = await batch(reader, raw)
    assert result['state'] == 'ok' and result['loaded'] == result['total'] == 2
    assert result['rows']
    assert [call.args for call in reader._sleep.await_args_list] == [(5,), (15,)]
    retried = [call for call in client.calls if call[0] == kind]
    assert retried[0] == retried[1] == retried[2]


@pytest.mark.asyncio
async def test_cancel_during_transient_retry_stops_requests_without_marking_failed(setup):
    reader, client, raw, _, _ = setup
    raw['launches'][raw['catalogue'][0]['id']] = None
    waiting = asyncio.Event()
    async def delay(seconds):
        waiting.set()
        await asyncio.Event().wait()
    reader._sleep.side_effect = delay
    reader.offer(raw['catalogue'], complete=True, read_ts=NOW)
    await asyncio.wait_for(waiting.wait(), 1)
    await reader.close()
    assert len(client.calls) == 1
    assert reader.project()['state'] == 'pending'


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
    assert failed['jobs'] == good['jobs'] == 3
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert restored.project()['rows'] == good['rows']
    assert restored.project()['jobs'] == 3
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


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [None, 'unknown', 3, ['review']])
async def test_unknown_role_keeps_ranking_and_only_hides_affected_seat_split(setup, role):
    reader, client, raw, _, _ = setup
    jobs = list(raw['jobs'].values())
    jobs[0]['nodes'][0]['role'] = role
    jobs[0]['nodes'][1]['seat']['tokenId'] = '863'  # known and unknown role on one job
    jobs[1]['nodes'][0]['seat']['tokenId'] = '863'
    result = await batch(reader, raw)
    rows = {row['token_id']: row for row in result['rows']}
    assert result['state'] == 'ok' and rows[863]['jobs'] == 2
    assert rows[863]['build_jobs'] is rows[863]['review_jobs'] is None
    assert (rows[717]['build_jobs'], rows[717]['review_jobs']) == (1, 0)
    calls = list(client.calls)
    await batch(reader, raw)
    assert client.calls == calls  # known absence is not endlessly refetched


@pytest.mark.asyncio
async def test_legacy_ranking_retained_while_role_facts_are_backfilled(setup):
    reader, client, raw, cache, clock = setup
    good = await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    for fact in payload['jobs'].values():
        fact.pop('roles')
    for row in payload['snapshot']['rows']:
        row.pop('build_jobs'); row.pop('review_jobs')
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    client.calls.clear()
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    before = restored.project()
    assert before['rows'] == [dict(row, build_jobs=None, review_jobs=None) for row in good['rows']]
    assert before['read_ts'] == good['read_ts']
    client.wait = asyncio.Event()
    restored.offer(raw['catalogue'], complete=True, read_ts=NOW)
    assert restored.project()['state'] == 'pending'
    assert restored.project()['rows'] == before['rows']
    client.wait.set()
    await restored.task
    assert restored.project()['rows'] == good['rows']
    assert sorted(client.calls) == [('jobs', identity) for identity in sorted(raw['jobs'])]


@pytest.mark.asyncio
@pytest.mark.parametrize('roles', [None, {}, {'build': [True], 'review': [], 'unknown': []},
    {'build': [99999], 'review': [], 'unknown': []},
    {'build': [717, 717], 'review': [], 'unknown': []},
    {'build': [717], 'review': [], 'unknown': [717]}])
async def test_corrupt_cached_roles_refetch_only_the_bad_job(setup, roles):
    reader, client, raw, cache, clock = setup
    await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    identity = next(iter(raw['jobs']))
    payload['jobs'][identity]['roles'] = roles
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    client.calls.clear()
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert (await batch(restored, raw))['state'] == 'ok'
    assert client.calls == [('jobs', identity)]


@pytest.mark.asyncio
@pytest.mark.parametrize('build,review', [(True, 1), (-1, 1), (2, 0), (None, 0), (0, 0)])
async def test_impossible_cached_split_cannot_be_presented_as_complete(setup, build, review):
    reader, client, raw, cache, clock = setup
    await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    payload['snapshot']['rows'][0].update(build_jobs=build, review_jobs=review)
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert restored.project()['rows'] is None
    assert (await batch(restored, raw))['state'] == 'ok'


@pytest.mark.asyncio
async def test_global_jobs_union_excludes_jobs_without_accepted_contributor_seats(setup):
    reader, _, raw, _, _ = setup
    first, second = raw['catalogue']
    shared = raw['launches'][first['id']]['jobs'][0]['id']
    unrelated = raw['launches'][second['id']]['jobs'][0]['id']
    raw['launches'][second['id']]['jobs'].append({'id': shared})
    raw['jobs'][shared]['nodes'] = [
        {'key': 'build', 'role': 'implement', 'state': 'accepted', 'seat': {'tokenId': '7'}},
        {'key': 'review', 'role': 'review', 'state': 'accepted', 'seat': {'tokenId': '8'}},
    ]
    raw['jobs'][unrelated]['nodes'] = [
        {'key': 'oracle_assess', 'state': 'accepted', 'seat': {'tokenId': '9'}},
        {'key': 'build', 'state': 'failed', 'seat': {'tokenId': '10'}},
    ]
    # This fixture's verified frontend remains a distinct contributing job.
    result = await batch(reader, raw)
    assert result['jobs'] == 2
    assert sum(row['jobs'] for row in result['rows']) == 4
    assert {row['token_id'] for row in result['rows']} == {7, 8, 401, 402}


@pytest.mark.asyncio
async def test_legacy_snapshot_retains_rows_but_jobs_unknown_until_recomputed(setup):
    reader, client, raw, cache, clock = setup
    good = await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    payload['snapshot'].pop('jobs')
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert restored.project()['rows'] == good['rows']
    assert restored.project()['jobs'] is None
    client.calls.clear()
    recomputed = await batch(restored, raw)
    assert recomputed['jobs'] == 3 and recomputed['rows'] == good['rows']
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('total', [True, -1, 0, 0.5, '3', 100001, 100, float('nan')])
async def test_invalid_or_inconsistent_persisted_global_jobs_is_not_a_snapshot(setup, total):
    reader, client, raw, cache, clock = setup
    await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    payload['snapshot']['jobs'] = total
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    restored = LaunchContributionReader(client, cache, clock=lambda: clock[0])
    assert restored.project()['rows'] is None and restored.project()['jobs'] is None
    assert (await batch(restored, raw))['jobs'] == 3


@pytest.mark.asyncio
async def test_persisted_total_cannot_be_less_than_a_seats_job_count(setup):
    reader, client, raw, cache, clock = setup
    await batch(reader, raw)
    payload = copy.deepcopy(cache.get_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION).payload)
    payload['snapshot'] = dict(read_ts=NOW, jobs=1,
        rows=[dict(rank=1, token_id=7, jobs=2, launches=1, build_jobs=2, review_jobs=0)])
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION, payload, ts=NOW)
    assert LaunchContributionReader(client, cache, clock=lambda: clock[0]).project()['rows'] is None


@pytest.mark.asyncio
async def test_empty_persisted_snapshot_cannot_claim_jobs(setup):
    _, client, _, cache, clock = setup
    cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION,
        {'snapshot': dict(read_ts=NOW, jobs=1, rows=[])}, ts=NOW)
    assert LaunchContributionReader(client, cache, clock=lambda: clock[0]).project()['rows'] is None
