"""Recent activity and workflow checkpoint sharing; fixture-only reads."""
import asyncio
import copy
from types import SimpleNamespace

import pytest

from maxpane_dashboard.data import surf_work_catalogue as catalogue
from maxpane_dashboard.data.surf_cache import SLOT_SURF_WORK, TIER_SURF_WORK
from maxpane_dashboard.data.surf_manager import SurfManager
from tests.data.test_surf_work_reader import setup, incremental_setup, project_setup, optional_jobs


def completed_jobs(raw, now, count=25):
    identities = optional_jobs(raw, count)
    for row in raw['jobs'] + raw['details']:
        row.update(state='completed', createdAt=catalogue._iso(now - 172800),
                   updatedAt=catalogue._iso(now - 10))
    return identities


async def test_recently_completed_old_jobs_are_retained_and_hydrated_in_bounded_rotation(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    identities = completed_jobs(raw, clock.now)
    await reader.offer()
    first = reader.project()
    assert first['jobs_loaded'] == 25
    assert first['summary']['jobs'] == 0
    assert first['details_loaded'] == 24
    assert [identity for kind, identity in client.calls if kind == 'detail'] == identities[:24]
    clock.now += 31
    await reader.offer()
    assert reader.project()['details_loaded'] == 25
    assert [identity for kind, identity in client.calls if kind == 'detail'] == identities
    assert len(cache.get_last_good(SLOT_SURF_WORK).payload['catalogue']['jobs']['rows']) == 25


async def test_cold_baseline_catches_recent_activity_beyond_creation_scan_stop(incremental_setup):
    reader, client, _, clock, raw, requests = incremental_setup
    base = raw['jobs'][0]
    raw.update(workflows=[], details=[], executing_count=0)
    raw['jobs'] = [dict(base, id=f'00000000-0000-0000-0000-{i:012d}', state='completed',
                        createdAt=catalogue._iso(clock.now - 90000 - i),
                        updatedAt=catalogue._iso(clock.now - 89900 - i)) for i in range(101)]
    recent = dict(base, id='11111111-1111-4111-8111-111111111111', state='completed',
                  createdAt=catalogue._iso(clock.now - 500000), updatedAt=catalogue._iso(clock.now - 50))
    raw['jobs'].append(recent)
    async def overview():
        return {'counts': {'jobs': 102, 'jobStates': {'completed': 102}}}
    client.fetch_overview = overview
    await reader.offer()
    assert {row['id'] for row in reader.project()['jobs']} == {recent['id']}
    assert any(kind == 'jobs' and query['since'] is not None for kind, query in requests)
    assert not any(query['before'] for kind, query in requests if kind == 'jobs')


async def test_work_and_swarm_reuse_one_cold_workflow_baseline_in_both_directions(incremental_setup):
    reader, _, cache, clock, _, requests = incremental_setup
    manager = SimpleNamespace(_work_reader=reader, cache=cache, _clock=lambda: clock.now)
    await SurfManager._refresh_workflow_catalogue(manager, clock.now)
    await reader.offer()
    assert len([kind for kind, _ in requests if kind == 'workflows']) == 1
    initial = copy.deepcopy(cache.workflow_catalogue)
    clock.now += 31
    requests.clear()
    await reader.offer()
    rows, complete, stamp = await SurfManager._refresh_workflow_catalogue(manager, clock.now)
    flow_calls = [query for kind, query in requests if kind == 'workflows']
    assert len(flow_calls) == 1 and flow_calls[0]['since'] is not None
    assert complete and stamp == clock.now and rows
    assert cache.workflow_catalogue['full_ts'] == initial['full_ts']


async def test_shared_workflow_read_does_not_overlap_and_failure_keeps_checkpoint(incremental_setup):
    reader, client, cache, clock, _, requests = incremental_setup
    manager = SimpleNamespace(_work_reader=reader, cache=cache, _clock=lambda: clock.now)
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.fetch_workflows
    async def held(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)
    client.fetch_workflows = held
    first = asyncio.create_task(SurfManager._refresh_workflow_catalogue(manager, clock.now))
    await asyncio.wait_for(entered.wait(), 1)
    second = reader.offer()
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    assert len([kind for kind, _ in requests if kind == 'workflows']) == 1
    before = copy.deepcopy(cache.workflow_catalogue)
    clock.now += 31
    async def failed(**_):
        return None
    client.fetch_workflows = failed
    await reader.offer()
    assert cache.workflow_catalogue == before
    assert cache.last_failure_ts(TIER_SURF_WORK) == clock.now


async def test_legacy_workflow_checkpoint_is_shared_without_rebuilding(incremental_setup):
    reader, _, cache, clock, _, requests = incremental_setup
    await reader.offer()
    cache.workflow_catalogue = None
    requests.clear()
    manager = SimpleNamespace(_work_reader=reader, cache=cache, _clock=lambda: clock.now)
    rows, complete, stamp = await SurfManager._refresh_workflow_catalogue(manager, clock.now)
    assert rows and complete and stamp == clock.now
    assert not requests
    assert cache.workflow_catalogue == cache.get_last_good(SLOT_SURF_WORK).payload['catalogue']['workflows']


async def test_completed_listing_does_not_reopen_from_older_optional_detail(incremental_setup):
    reader, _, _, clock, raw, _ = incremental_setup
    completed_jobs(raw, clock.now, count=1)
    raw['details'][0].update(state='executing', updatedAt=catalogue._iso(clock.now - 20))
    await reader.offer()
    assert reader.project()['jobs'][0]['state'] == 'completed'
    assert reader.project()['jobs'][0]['nodes'] is None
    assert reader.project()['summary']['jobs'] == 0


async def test_completed_details_publish_before_history_scan_with_one_offer_budget(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    completed_jobs(raw, clock.now, count=101)
    for index, row in enumerate(raw['jobs']):
        row['createdAt'] = catalogue._iso(clock.now - index - 100)
        row['updatedAt'] = row['createdAt']
    raw['details'] = [dict(row, nodes=raw['details'][0]['nodes']) for row in raw['jobs']]
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.fetch_jobs
    async def held(**kwargs):
        if kwargs.get('before'):
            entered.set()
            await release.wait()
        return await original(**kwargs)
    client.fetch_jobs = held
    task = reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        visible = cache.get_last_good(SLOT_SURF_WORK).payload
        assert visible['details_loaded'] == 24
        assert any(row['nodes'] for row in visible['jobs'])
        release.set()
        await task
        assert len([identity for kind, identity in client.calls if kind == 'detail']) == 24
    finally:
        release.set()
        await reader.close()


async def test_active_project_context_does_not_hold_recent_completed_details(project_setup):
    reader, client, cache, clock, raw = project_setup
    active = raw['jobs'][0]
    active['createdAt'] = raw['details'][0]['createdAt'] = catalogue._iso(clock.now - 1)
    active['updatedAt'] = raw['details'][0]['updatedAt'] = catalogue._iso(clock.now - 1)
    completed = [dict(active, id=f'00000000-0000-0000-0000-{i:012d}', state='completed',
                      project=None, workflow=None, createdAt=catalogue._iso(clock.now - 100 - i),
                      updatedAt=catalogue._iso(clock.now - 100 - i)) for i in range(101)]
    raw['jobs'] += completed
    raw['details'] += completed
    identities = {row['id'] for row in completed}
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.fetch_jobs
    async def held(**kwargs):
        if kwargs.get('before'):
            entered.set()
            await release.wait()
        return await original(**kwargs)
    client.fetch_jobs = held
    task = reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        visible = cache.get_last_good(SLOT_SURF_WORK).payload
        assert visible['projects'] == []  # grouping still waits for authoritative context
        assert sum(row['nodes'] is not None for row in visible['jobs'] if row['id'] in identities) == 24
        release.set()
        await task
        assert reader.project()['projects']
        assert len([identity for kind, identity in client.calls if kind == 'detail' and identity in identities]) == 24
    finally:
        release.set()
        await reader.close()


@pytest.mark.parametrize('age', [10, 90000])
@pytest.mark.parametrize('status', ['frontend', 'blocked', 'paused'])
async def test_workflow_stage_without_listing_still_loads_details(incremental_setup, age, status):
    reader, _, _, clock, raw, _ = incremental_setup
    detail = dict(raw['details'][0], state='completed', project=None, workflow=None)
    flow = dict(raw['workflows'][0], status=status, contractsJobId=detail['id'],
                frontendJobId=None, createdAt=catalogue._iso(clock.now - age),
                updatedAt=catalogue._iso(clock.now - age))
    raw.update(jobs=[], workflows=[flow], details=[detail], executing_count=0)
    await reader.offer()
    assert reader.project()['details_loaded'] == 1
    assert reader.project()['jobs'][0]['nodes']
    assert reader.project()['summary']['jobs'] == 0


@pytest.mark.parametrize('status', ['frontend', 'blocked'])
async def test_old_stopped_workflow_enrichment_follows_recent_jobs(incremental_setup, status):
    reader, client, _, clock, raw, _ = incremental_setup
    flow = raw['workflows'][0]
    identities = completed_jobs(raw, clock.now)
    stage = dict(raw['details'][0], id='33333333-3333-4333-8333-333333333333')
    raw['details'].append(stage)
    raw['workflows'] = [dict(flow, status=status, contractsJobId=stage['id'], frontendJobId=None,
                            createdAt=catalogue._iso(clock.now - 90000),
                            updatedAt=catalogue._iso(clock.now - 90000))]
    await reader.offer()
    reads = [identity for kind, identity in client.calls if kind == 'detail']
    assert len(reads) == 24
    assert reads[0] == (stage['id'] if status == 'frontend' else identities[0])
    assert (stage['id'] in reads) is (status == 'frontend')
    clock.now += 31
    await reader.offer()
    assert any(row['id'] == stage['id'] and row['nodes'] for row in reader.project()['jobs'])


@pytest.mark.parametrize('change', ['none', 'revision', 'link'])
async def test_unlisted_workflow_stage_survives_pending_project_and_invalidates_on_change(project_setup, change):
    reader, client, cache, clock, raw = project_setup
    original_ts = clock.now
    stage = dict(raw['details'][0], id='33333333-3333-4333-8333-333333333333',
                 state='completed', project=None, workflow=None)
    raw['details'].append(stage)
    flow = dict(id='44444444-4444-4444-8444-444444444444', status='frontend',
                contractsJobId=stage['id'], frontendJobId=None,
                createdAt=catalogue._iso(clock.now - 90000), updatedAt=catalogue._iso(clock.now - 90000))
    raw['workflows'] = [flow]
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.fetch_job
    historical = raw['details'][1]['id']
    async def held(identity):
        if identity == historical:
            entered.set()
            await release.wait()
        return await original(identity)
    client.fetch_job = held
    task = reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        visible = cache.get_last_good(SLOT_SURF_WORK).payload
        assert visible['projects'] == []
        assert next(row for row in visible['jobs'] if row['id'] == stage['id'])['nodes']
        release.set()
        await task
        final = cache.get_last_good(SLOT_SURF_WORK).payload
        assert next(row for row in final['jobs'] if row['id'] == stage['id'])['nodes']
        assert final['optional_details'][stage['id']]['read_ts'] == original_ts
        assert reader.project()['summary']['jobs'] == 1
        assert reader.project()['summary']['blocked'] == 0
        clock.now += 31
        raw['details'].remove(stage)  # A failed optional refresh cannot invent a new observation.
        if change != 'none':
            flow['updatedAt'] = catalogue._iso(clock.now - 1)
        if change == 'link':
            flow['contractsJobId'] = '55555555-5555-4555-8555-555555555555'
        await reader.offer()
        saved = cache.get_last_good(SLOT_SURF_WORK).payload
        if change == 'none':
            assert saved['optional_details'][stage['id']]['read_ts'] == original_ts
            assert next(row for row in saved['jobs'] if row['id'] == stage['id'])['nodes']
        else:
            assert stage['id'] not in saved['optional_details']
            assert not any(row['id'] == stage['id'] and row['nodes'] for row in saved['jobs'])
        assert reader.project()['summary']['jobs'] == 1
    finally:
        release.set()
        await reader.close()
