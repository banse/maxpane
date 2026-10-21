"""Single-flight work reader, with fake client calls only."""
import asyncio
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from maxpane_dashboard.data.surf_cache import SurfCache, SLOT_SURF_WORK, TIER_SURF_WORK
from maxpane_dashboard.data.surf_work_reader import WorkReader
from maxpane_dashboard.data.surf_swarm_client import JobDetailRead, SwarmClient


@pytest.fixture
def setup(tmp_path):
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    clock = SimpleNamespace(now=raw['read_ts'], mono=1000.0)
    cache = SurfCache(path=str(tmp_path / 'cache.json'), clock=lambda: clock.now)

    class Client:
        calls = []
        _monotonic = staticmethod(lambda: clock.mono)
        async def fetch_jobs(self, *, limit, before=None):
            self.calls.append(('jobs', before or limit))
            return raw.get('next_jobs') if before else raw['jobs']
        async def fetch_workflows(self, *, limit, before=None):
            self.calls.append(('workflows', limit)); return raw['workflows']
        async def fetch_overview(self):
            return {'counts': {'jobStates': {'executing': raw.get('executing_count', sum(j.get('state') == 'executing' for j in raw['jobs']))}}}
        async def fetch_workflow(self, identity):
            self.calls.append(('workflow', identity)); return raw.get('workflow_details', {}).get(identity)
        async def fetch_job(self, identity):
            self.calls.append(('detail', identity))
            return next((d for d in raw['details'] if d['id'] == identity), None)
        async def read_job_detail(self, identity, *, fresh_after=None):
            payload = await self.fetch_job(identity)
            return JobDetailRead(copy.deepcopy(payload), clock.now if payload else None,
                                 clock.mono, None, False)

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
    assert sum(call[0] == 'detail' for call in client.calls) == 30
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


@pytest.fixture
def project_setup(setup):
    reader, client, cache, clock, raw = setup
    active = copy.deepcopy(raw['details'][0])
    old = copy.deepcopy(raw['details'][1])
    old['state'] = 'blocked'
    old['createdAt'] = '2020-01-01T00:00:00.000Z'
    old['nodes'][0]['state'] = 'failed'
    project = dict(id=old['id'], versions=[
        dict(jobId=old['id'], state='blocked', objective='Earlier attempt', workflowId=None),
        dict(jobId=active['id'], state='executing', objective='Current attempt', workflowId=None)])
    active['project'] = copy.deepcopy(project)
    old['project'] = copy.deepcopy(project)
    raw.update(jobs=[copy.deepcopy(active)], workflows=[], details=[active, old])
    return setup


@pytest.mark.asyncio
async def test_complete_project_reads_old_blocked_versions_and_all_steps(project_setup):
    reader, client, _, _, raw = project_setup
    await reader.offer()
    data = reader.project()
    project = data['projects'][0]
    assert project['id'] == raw['details'][1]['id']
    assert project['job_ids'] == [raw['details'][1]['id'], raw['details'][0]['id']]
    assert project['active_job_ids'] == [raw['details'][0]['id']]
    assert project['workflow_ids'] == []
    old = next(j for j in data['jobs'] if j['id'] == raw['details'][1]['id'])
    assert [n['state'] for n in old['nodes']] == ['failed', 'accepted', 'accepted', 'accepted', 'accepted']
    assert data['summary'] == dict(jobs=1, workflows=0, seats=1, build=1, review=0, blocked=0)
    assert not data['partial']
    assert len([c for c in client.calls if c[0] == 'detail']) == 2


@pytest.mark.asyncio
async def test_shared_project_and_nested_workflow_are_read_once(project_setup):
    reader, client, _, _, raw = project_setup
    active, old = raw['details']
    old['state'] = 'executing'
    old['project']['versions'][0]['state'] = 'executing'
    active['project'] = copy.deepcopy(old['project'])
    raw['jobs'].append(copy.deepcopy(old))
    flow_id = '08854072-c20d-4147-b9fd-c0d48956c55c'
    for job in raw['details']:
        job['workflow'] = dict(id=flow_id)
        for version in job['project']['versions']: version['workflowId'] = flow_id
    raw['workflow_details'] = {flow_id: dict(id=flow_id, status='frontend',
        contracts={'id': old['id']}, frontend={'id': active['id']})}
    await reader.offer()
    data = reader.project()
    assert len(data['projects']) == 1 and len(data['workflows']) == 1
    assert len(data['projects'][0]['active_job_ids']) == 2
    assert data['projects'][0]['workflow_ids'] == [flow_id]
    assert data['summary']['workflows'] == 1
    assert len([c for c in client.calls if c[0] == 'detail']) == 2
    assert len([c for c in client.calls if c[0] == 'workflow']) == 1


@pytest.mark.asyncio
async def test_active_discovery_beyond_first_hundred_and_prior_revalidation(project_setup):
    reader, client, cache, clock, raw = project_setup
    active = copy.deepcopy(raw['jobs'][0])
    recent = [dict(active, id=f'00000000-0000-0000-0000-{n:012d}', state='completed') for n in range(100)]
    recent[-1]['createdAt'] = '2026-10-12T00:00:00.000Z'
    raw['jobs'] = recent
    raw['next_jobs'] = [active]
    raw['executing_count'] = 1
    await reader.offer()
    assert reader.project()['summary']['jobs'] == 1
    assert ('jobs', recent[-1]['createdAt']) in client.calls
    clock.now += 60
    raw['next_jobs'] = []
    raw['executing_count'] = 0
    raw['details'][0]['state'] = 'completed'
    client.calls.clear()
    await reader.offer()
    data = reader.project()
    assert ('detail', active['id']) in client.calls
    assert data['summary']['jobs'] == 0 and data['projects'] == []
    assert cache.get_last_good(SLOT_SURF_WORK).payload['active_scan_complete']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['missing_count', 'failed_page', 'repeated_page'])
async def test_incomplete_discovery_never_claims_zero_activity(project_setup, failure):
    reader, client, _, _, raw = project_setup
    base = raw['jobs'][0]
    raw['jobs'] = [dict(base, id=f'00000000-0000-0000-0000-{n:012d}', state='completed') for n in range(100)]
    raw['executing_count'] = None if failure == 'missing_count' else 1
    raw['next_jobs'] = raw['jobs'] if failure == 'repeated_page' else None
    await reader.offer()
    data = reader.project()
    assert data['partial'] and data['state'] == 'ok'
    assert all(data['summary'][key] is None for key in ('jobs', 'seats', 'build', 'review'))
    assert len([c for c in client.calls if c[0] == 'jobs']) <= 2


@pytest.mark.asyncio
async def test_missing_historical_executing_metadata_is_not_current_activity(project_setup):
    reader, _, _, _, raw = project_setup
    raw['details'][0]['project']['versions'][0]['state'] = 'executing'
    old_id = raw['details'].pop()['id']
    await reader.offer()
    data = reader.project()
    old = next(j for j in data['jobs'] if j['id'] == old_id)
    assert old['state'] == 'executing' and old['nodes'] is None
    assert old['detail_state'] == 'unavailable'
    assert data['summary']['jobs'] == 1 and data['summary']['build'] == 1
    assert data['partial'] and old_id in data['projects'][0]['job_ids']


@pytest.mark.asyncio
@pytest.mark.parametrize('corruption', ['foreign_id', 'missing_seed', 'duplicate', 'malformed', 'foreign_project'])
async def test_untrusted_project_membership_is_rejected(project_setup, corruption):
    reader, _, _, _, raw = project_setup
    active, old = raw['details']
    if corruption == 'foreign_id': active['id'] = old['id']
    if corruption == 'missing_seed': active['project']['versions'].pop()
    if corruption == 'duplicate': active['project']['versions'].append(active['project']['versions'][0])
    if corruption == 'malformed': active['project']['versions'] = 'bad'
    if corruption == 'foreign_project': old['project']['id'] = active['id']
    await reader.offer()
    data = reader.project()
    assert data['partial']
    if corruption == 'foreign_project':
        assert next(j for j in data['jobs'] if j['id'] == old['id'])['nodes'] is None
    else:
        assert data['projects'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['job', 'workflow'])
async def test_context_busy_keeps_prior_snapshot(project_setup, stage):
    reader, client, cache, clock, raw = project_setup
    await reader.offer()
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    clock.now += 60
    if stage == 'job': raw['details'][1] = {'id': raw['details'][1]['id'], 'error': 'busy'}
    else:
        flow_id = '08854072-c20d-4147-b9fd-c0d48956c55c'
        raw['details'][0]['workflow'] = {'id': flow_id}
        raw['workflow_details'] = {flow_id: {'error': 'busy'}}
    await reader.offer()
    assert cache.get_last_good(SLOT_SURF_WORK) == before
    assert reader.project()['state'] == 'stale'


@pytest.mark.asyncio
async def test_active_context_exceeds_optional_budget_with_explicit_hard_cap(project_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work as work
    reader, client, _, _, raw = project_setup
    active = raw['details'][0]
    versions = [dict(active, id=f'00000000-0000-0000-0000-{n:012d}', state='completed', project=None) for n in range(30)]
    active['project']['versions'] = [dict(jobId=j['id'], state=j['state']) for j in versions + [active]]
    raw['details'] += versions
    await reader.offer()
    assert reader.project()['details_loaded'] == 31
    assert not reader.project()['partial']
    monkeypatch.setattr(work, 'CONTEXT_DETAIL_LIMIT', 4)
    reader.clock = lambda: raw['read_ts'] + 60
    client.calls.clear()
    await reader.offer()
    data = reader.project()
    assert len([c for c in client.calls if c[0] == 'detail']) == 4
    assert data['partial'] and data['details_expected'] == 31


@pytest.mark.asyncio
async def test_workflow_without_project_loads_old_peer_without_inflating_blocked(project_setup):
    reader, _, _, _, raw = project_setup
    active, old = raw['details']
    active['project'] = None
    flow_id = '08854072-c20d-4147-b9fd-c0d48956c55c'
    active['workflow'] = old['workflow'] = {'id': flow_id}
    raw['workflow_details'] = {flow_id: dict(id=flow_id, status='frontend',
        contracts={'id': old['id']}, frontend={'id': active['id']})}
    await reader.offer()
    data = reader.project()
    assert data['projects'] == [] and len(data['jobs']) == 2
    assert data['summary']['jobs'] == 1 and data['summary']['blocked'] == 0
    assert not data['partial']


@pytest.mark.asyncio
@pytest.mark.parametrize('corruption', ['identity', 'membership', 'duplicate', 'malformed', 'peer_workflow', 'peer_identity'])
async def test_direct_workflow_identity_and_peer_membership_are_validated(project_setup, corruption):
    reader, _, _, _, raw = project_setup
    active, old = raw['details']
    flow_id = '08854072-c20d-4147-b9fd-c0d48956c55c'
    active['workflow'] = old['workflow'] = {'id': flow_id}
    flow = dict(id=flow_id, status='frontend', contracts={'id': old['id']}, frontend={'id': active['id']})
    raw['workflow_details'] = {flow_id: flow}
    if corruption == 'identity': flow['id'] = old['id']
    if corruption == 'membership': flow['frontend'] = None
    if corruption == 'duplicate': flow['contracts'] = flow['frontend']
    if corruption == 'malformed': flow['contracts'] = ['bad']
    if corruption == 'peer_workflow': old['workflow'] = None
    if corruption == 'peer_identity': old['id'] = active['id']
    await reader.offer()
    data = reader.project()
    assert data['partial'] and data['summary']['jobs'] == 1
    if corruption.startswith('peer_'):
        old_row = next(j for j in data['jobs'] if j['id'] != active['id'])
        assert old_row['nodes'] is None
    else:
        assert data['workflows'] == []


@pytest.mark.asyncio
async def test_rejected_historical_project_cannot_recursively_expand(project_setup):
    reader, client, _, _, raw = project_setup
    old = raw['details'][1]
    extra_id = '00000000-0000-0000-0000-000000000999'
    old['project']['versions'].append(dict(jobId=extra_id, state='executing'))
    old['parentJobId'] = old['id']
    await reader.offer()
    data = reader.project()
    assert ('detail', extra_id) not in client.calls
    assert data['partial'] and data['summary']['jobs'] == 1
    assert next(j for j in data['jobs'] if j['id'] == old['id'])['nodes'] is None


@pytest.mark.asyncio
async def test_cancellation_mid_context_does_not_publish(project_setup):
    reader, client, cache, clock, raw = project_setup
    await reader.offer()
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    clock.now += 60
    old_id = raw['details'][1]['id']
    fetch, entered = client.fetch_job, asyncio.Event()
    async def hanging(identity):
        if identity != old_id: return await fetch(identity)
        entered.set(); await asyncio.Event().wait()
    client.fetch_job = hanging
    task = reader.offer()
    await entered.wait()
    await reader.close()
    assert task.cancelled()
    assert cache.get_last_good(SLOT_SURF_WORK) == before
    assert cache.last_failure_ts(TIER_SURF_WORK) is None


@pytest.mark.asyncio
async def test_scan_cap_and_workflow_cap_publish_partial(project_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work as work
    reader, _, _, _, raw = project_setup
    active = raw['jobs'][0]
    raw['jobs'] = [dict(active, id=f'00000000-0000-0000-0000-{n:012d}', state='completed') for n in range(100)]
    raw['executing_count'] = 1
    monkeypatch.setattr(work, 'SCAN_PAGES', 0)
    await reader.offer()
    assert reader.project()['partial'] and reader.project()['summary']['jobs'] is None
    reader.clock = lambda: raw['read_ts'] + 60
    raw['jobs'] = [active]
    raw['details'][0]['workflow'] = {'id': '08854072-c20d-4147-b9fd-c0d48956c55c'}
    monkeypatch.setattr(work, 'WORKFLOW_DETAIL_LIMIT', 0)
    await reader.offer()
    assert reader.project()['partial'] and reader.project()['summary']['jobs'] == 1


@pytest.mark.asyncio
async def test_persisted_project_scopes_and_coverage_are_validated(project_setup):
    from maxpane_dashboard.data import surf_work as work
    reader, _, cache, clock, _ = project_setup
    await reader.offer()
    slot = cache.get_last_good(SLOT_SURF_WORK).payload
    assert work.coerce_snapshot(slot, now=clock.now) == slot
    for mutate in (
        lambda s: s['projects'].append(s['projects'][0]),
        lambda s: s['projects'][0]['job_ids'].append('bad'),
        lambda s: s['projects'][0]['active_job_ids'].append(s['projects'][0]['job_ids'][0]),
        lambda s: s['current_job_ids'].append(s['projects'][0]['job_ids'][0]),
        lambda s: s.update(details_expected=0),
        lambda s: s.update(active_scan_complete='yes'),
        lambda s: s.update(context_job_ids=[]),
    ):
        changed = copy.deepcopy(slot); mutate(changed)
        assert work.coerce_snapshot(changed, now=clock.now) is None
    cold = SurfCache(path=cache.path, clock=lambda: clock.now)
    cold.load(slot_coercers={SLOT_SURF_WORK: lambda v: work.coerce_snapshot(v, now=clock.now)})
    assert cold.get_last_good(SLOT_SURF_WORK).payload == slot


@pytest.mark.asyncio
async def test_malformed_initial_row_cannot_prove_empty_active_population(project_setup):
    reader, _, _, _, raw = project_setup
    raw['jobs'] = [dict(raw['jobs'][0], state='completed'), {'id': False}]
    raw['executing_count'] = 0
    await reader.offer()
    assert reader.project()['partial']
    assert reader.project()['summary']['jobs'] is None


@pytest.mark.asyncio
async def test_scan_page_bound_includes_initial_page(project_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work as work
    reader, client, _, _, raw = project_setup
    raw['jobs'] = [dict(raw['jobs'][0], id=f'00000000-0000-0000-0000-{n:012d}', state='completed') for n in range(100)]
    raw['executing_count'] = 1
    monkeypatch.setattr(work, 'SCAN_PAGES', 1)
    await reader.offer()
    assert len([c for c in client.calls if c[0] == 'jobs']) == 1
    assert reader.project()['partial']


@pytest.mark.asyncio
async def test_malformed_historical_versions_cannot_supply_step_evidence(project_setup):
    reader, _, _, _, raw = project_setup
    raw['details'][1]['project']['versions'] = 'not a list'
    await reader.offer()
    data = reader.project()
    assert data['partial']
    assert next(j for j in data['jobs'] if j['id'] == raw['details'][1]['id'])['nodes'] is None


@pytest.mark.asyncio
async def test_captured_project_versions_have_exact_public_contract(setup):
    from maxpane_dashboard.data.surf_models import SURF_WORK_FIELDS, SURF_WORK_PROJECT_FIELDS
    reader, _, _, clock, raw = setup
    capture = json.loads(Path('tests/fixtures/surf/work/project_context.json').read_text())
    job = capture['active_detail']
    clock.now = capture['read_ts']
    raw.update(jobs=[job], details=[job], workflows=[])
    await reader.offer()
    data = reader.project()
    assert set(data) == set(SURF_WORK_FIELDS)
    assert len(data['projects']) == 1
    project = data['projects'][0]
    assert set(project) == set(SURF_WORK_PROJECT_FIELDS)
    assert project['job_ids'] == [version['jobId'] for version in job['project']['versions']]
    assert project['active_job_ids'] == [job['id']]
    assert project['workflow_ids'] == []
    assert len(data['jobs']) == 3 and data['details_loaded'] == 1
    assert data['summary']['jobs'] == 1 and data['partial']
    assert 'context_job_ids' not in data and 'active_scan_complete' not in data


@pytest.mark.asyncio
async def test_revalidated_prior_job_does_not_hide_other_active_jobs_on_cursor_page(project_setup):
    reader, client, cache, clock, raw = project_setup
    await reader.offer()
    prior = copy.deepcopy(raw['details'][0])
    fresh = dict(copy.deepcopy(prior), id='00000000-0000-0000-0000-000000999999',
                 project=None, createdAt='2026-10-11T00:00:00.000Z')
    prior['createdAt'] = '2026-10-10T00:00:00.000Z'
    raw['jobs'] = [dict(prior, id=f'00000000-0000-0000-0000-{n:012d}', state='completed',
                        createdAt='2026-10-12T00:00:00.000Z') for n in range(100)]
    raw['next_jobs'] = [fresh, prior]
    raw['executing_count'] = 2
    raw['details'].append(fresh)
    clock.now += 60
    client.calls.clear()
    await reader.offer()
    data = reader.project()
    assert data['summary']['jobs'] == 2
    assert client.calls.count(('detail', prior['id'])) == 1
    assert client.calls.count(('detail', fresh['id'])) == 1
    identities = [job['id'] for job in data['jobs']]
    assert fresh['id'] in identities and len(identities) == len(set(identities))
    assert data['jobs_loaded'] == 2 and data['details_loaded'] == 3  # older completed head rows expire
    assert not data['partial']
    assert cache.get_last_good(SLOT_SURF_WORK).payload['active_scan_complete']


@pytest.fixture
async def shared_setup(project_setup):
    """Real shared memo and discovery; only the HTTP transport is replaced."""
    _, _, cache, clock, raw = project_setup
    calls = []
    gates = {}

    async def handler(request):
        clock.mono += 1
        path = request.url.path
        calls.append((path, clock.mono))
        if path == '/jobs':
            if request.url.params.get('before') and gates.get('prime_before_page'):
                # Another consumer refreshes during the later discovery HTTP read.
                await client.read_job_detail(gates.pop('prime_before_page'), fresh_after=clock.mono)
                clock.mono += 1
                calls.append(('page_completed', clock.mono))
            payload = raw['next_jobs'] if request.url.params.get('before') else raw['jobs']
            return httpx.Response(200, json={'jobs': payload})
        if path == '/workflows':
            return httpx.Response(200, json={'workflows': raw['workflows']})
        if path == '/swarm':
            if 'discovery' in gates: gates['discovery'].set()
            return httpx.Response(200, json={'counts': {'jobStates': {'executing': raw.get('executing_count', 1)}}})
        if path.startswith('/jobs/'):
            identity = path.rsplit('/', 1)[1]
            payload = copy.deepcopy(next((j for j in raw['details'] if j['id'] == identity), None))
            if gates.get('identity') == identity:
                gates['identity'] = None
                gates['entered'].set()
                await gates['release'].wait()
            return httpx.Response(200, json=payload)
        if path.startswith('/workflows/'):
            identity = path.rsplit('/', 1)[1]
            return httpx.Response(200, json=raw.get('workflow_details', {}).get(identity))
        pytest.fail(f'unexpected request: {request.url}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with SwarmClient(http_client=http, base_url='https://swarm.invalid',
                               inter_call_delay=0, clock=lambda: clock.now,
                               monotonic=lambda: clock.mono) as client:
            yield WorkReader(client, cache, clock=lambda: clock.now), client, cache, clock, raw, calls, gates


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['terminal_cache', 'changed_project', 'old_flight', 'later_page',
                                      'prior_active', 'prior_active_later_page'])
async def test_work_discovery_revalidates_active_detail_before_atomic_publish(shared_setup, scenario):
    reader, client, cache, clock, raw, calls, gates = shared_setup
    active, historical = raw['details']
    identity = active['id']
    original = copy.deepcopy(active)
    if scenario == 'terminal_cache':
        active['state'] = 'completed'
    if scenario in ('prior_active', 'prior_active_later_page'):
        await reader.offer()
        clock.now += 60
        raw['jobs'] = []
        active['state'] = 'completed'
        raw['executing_count'] = 0
    elif scenario == 'old_flight':
        await client.read_job_detail(identity)
        clock.mono += 31  # Expire active TTL, preserving matching discovery hints.
        gates.update(identity=identity, entered=asyncio.Event(), release=asyncio.Event(),
                     discovery=asyncio.Event())
        old_flight = asyncio.create_task(client.read_job_detail(identity))
        await gates['entered'].wait()
    else:
        await client.read_job_detail(identity)
    active.update(original)
    if scenario == 'prior_active': active['state'] = 'completed'
    # Changing project versions need not change the job's updatedAt/state.
    missing = '00000000-0000-0000-0000-000000000999'
    active['project']['versions'].append(dict(jobId=missing, state='completed'))
    if scenario in ('later_page', 'prior_active_later_page'):
        if scenario == 'later_page': gates['prime_before_page'] = identity
        else: raw['executing_count'] = 2  # Keep scanning beyond the previously active ID.
        raw['jobs'] = [dict(original, id=f'00000000-0000-0000-0000-{n:012d}', state='completed')
                       for n in range(100)]
        raw['jobs'][-1]['createdAt'] = '2026-10-12T00:00:00.000Z'
        raw['next_jobs'] = [copy.deepcopy(original)]
    clock.mono += 1
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    task = reader.offer()
    if scenario == 'old_flight':
        await gates['discovery'].wait()
        assert cache.get_last_good(SLOT_SURF_WORK) == before
        gates['release'].set()
        await old_flight
    await task
    data = reader.project()
    if scenario == 'prior_active':
        assert data['summary']['jobs'] == 0
        assert data['projects'] == []
    else:
        assert data['summary']['jobs'] == 1
        assert missing in data['projects'][0]['job_ids']
        assert data['partial']  # The new version is explicitly missing.
    discovery = max(stamp for path, stamp in calls if path in ('/jobs', '/workflows', '/swarm', 'page_completed'))
    assert max(stamp for path, stamp in calls if path == '/jobs/' + identity) > discovery
    assert sum(path == '/jobs/' + identity for path, _ in calls) == (
        3 if scenario in ('old_flight', 'later_page', 'prior_active_later_page') else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['complete', 'foreign_member', 'missing_version', 'cancel'])
async def test_full_context_and_cancellation_survive_shared_details(shared_setup, case):
    reader, client, cache, clock, raw, calls, gates = shared_setup
    active, historical = raw['details']
    prototype = active['nodes'][0]
    active['nodes'] = [dict(copy.deepcopy(prototype), key=f'step-{n}',
                            state='working' if n == 0 else 'accepted',
                            dependsOn=[] if n == 0 else [f'step-{n - 1}']) for n in range(40)]
    if case == 'foreign_member': historical['project']['id'] = active['id']
    missing = '00000000-0000-0000-0000-000000000999'
    if case == 'missing_version':
        active['project']['versions'].append(dict(jobId=missing, state='completed'))
    original_read = await client.read_job_detail(historical['id'])
    historical_updated = datetime.fromisoformat(historical['updatedAt']).timestamp()
    await reader.offer()
    data = reader.project()
    current = next(j for j in data['jobs'] if j['id'] == active['id'])
    assert len(current['nodes']) == 40
    assert current['nodes'][-1]['depends_on'] == ['step-38']
    assert data['summary']['jobs'] == 1
    old_row = next(j for j in data['jobs'] if j['id'] == historical['id'])
    if case == 'foreign_member':
        assert old_row['nodes'] is None and data['partial']
    else:
        assert old_row['updated_ts'] == historical_updated
        assert old_row['id'] not in cache.get_last_good(SLOT_SURF_WORK).payload['current_job_ids']
        assert data['partial'] == (case == 'missing_version')
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    clock.now += 60
    if case == 'cancel':
        final = dict(copy.deepcopy(historical), id=missing, project=None, state='completed')
        raw['details'].append(final)
        active['project']['versions'].append(dict(jobId=missing, state='completed'))
        gates.update(identity=missing, entered=asyncio.Event(), release=asyncio.Event())
        task = reader.offer()
        await gates['entered'].wait()  # Final required context detail, before atomic publish.
        assert cache.get_last_good(SLOT_SURF_WORK) == before
        reader.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
        assert cache.get_last_good(SLOT_SURF_WORK) == before
        assert cache.last_failure_ts(TIER_SURF_WORK) is None
    else:
        await reader.offer()
        assert reader.project()['summary']['jobs'] == 1
        assert reader.project()['read_ts'] == clock.now
    retained = await client.read_job_detail(historical['id'])
    assert retained.from_cache and retained.observed_at == original_read.observed_at
    assert retained.observed_at < clock.now
    assert sum(path == '/jobs/' + historical['id'] for path, _ in calls) == 1


@pytest.mark.asyncio
async def test_later_discovery_revalidation_cap_cannot_authorize_stale_context(shared_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work as work
    reader, _, _, clock, raw, _, _ = shared_setup
    await reader.offer()
    active = raw['details'][0]
    raw['jobs'] = [dict(active, id=f'00000000-0000-0000-0000-{n:012d}', state='completed')
                   for n in range(100)]
    raw['jobs'][-1]['createdAt'] = '2026-10-12T00:00:00.000Z'
    raw['next_jobs'] = [copy.deepcopy(active)]
    raw['executing_count'] = 2
    monkeypatch.setattr(work, 'CONTEXT_DETAIL_LIMIT', 1)
    clock.now += 60
    await reader.offer()
    data = reader.project()
    assert data['projects'] == []
    assert next(j for j in data['jobs'] if j['id'] == active['id'])['nodes'] is None
    assert data['partial'] and data['summary']['build'] is None


@pytest.mark.asyncio
async def test_jobs_scan_retains_24h_history_after_active_hint_is_satisfied(setup):
    reader, client, _, clock, raw = setup
    def iso(stamp):
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace('+00:00', 'Z')
    base = raw['jobs'][0]
    raw['jobs'] = [dict(base, id=f'00000000-0000-0000-0000-{n:012d}', state='completed',
                       createdAt=iso(clock.now - n)) for n in range(100)]
    recent = dict(base, id='00000000-0000-0000-0000-000000000100', state='completed', createdAt=iso(clock.now - 86400))
    old = dict(recent, id='00000000-0000-0000-0000-000000000101', createdAt=iso(clock.now - 86401))
    raw.update(next_jobs=[recent, old], workflows=[], executing_count=0)
    await reader.offer()
    data = reader.project()
    assert data['jobs_loaded'] == 101
    assert recent['id'] in {job['id'] for job in data['jobs']}
    assert old['id'] not in {job['id'] for job in data['jobs']}
    assert data['summary']['jobs'] == 0 and not data['partial']
    assert len([call for call in client.calls if call[0] == 'jobs']) == 2


@pytest.mark.asyncio
async def test_workflow_catalogue_pages_past_old_cap_and_resumes_budget(setup, monkeypatch):
    from maxpane_dashboard.data import surf_work as work
    reader, client, cache, clock, raw = setup
    base = raw['workflows'][0]
    flows = [dict(base, id=f'11111111-1111-4111-8111-{n:012d}', status='completed',
                  contractsJobId=None, frontendJobId=None,
                  createdAt=datetime.fromtimestamp(clock.now - n * 86400, timezone.utc).isoformat().replace('+00:00', 'Z'))
             for n in range(250)]
    calls = []
    async def pages(*, limit, before=None):
        calls.append(before)
        start = next((i + 1 for i, flow in enumerate(flows) if flow['createdAt'] == before), 0)
        return copy.deepcopy(flows[start:start + limit])
    client.fetch_workflows = pages
    raw.update(jobs=[], workflows=[], executing_count=0)
    monkeypatch.setattr(work, 'WORKFLOW_PAGES_PER_READ', 1)
    for expected in (100, 200, 250):
        await reader.offer()
        data = reader.project()
        assert data['workflows_loaded'] == expected
        assert data['partial'] == (expected < 250)
        clock.now += 60
    assert calls == [None, flows[99]['createdAt'], flows[199]['createdAt']]
    assert work.coerce_snapshot(cache.get_last_good(SLOT_SURF_WORK).payload, now=clock.now) is not None


@pytest.mark.asyncio
async def test_mixed_workflow_page_retains_valid_rows_as_partial(setup):
    reader, _, _, _, raw = setup
    valid = dict(raw['workflows'][0], status='completed', contractsJobId=None, frontendJobId=None)
    raw.update(jobs=[], workflows=[valid, None], executing_count=0)
    await reader.offer()
    data = reader.project()
    assert data['state'] == 'ok' and data['partial']
    assert [row['id'] for row in data['workflows']] == [valid['id']]


@pytest.mark.asyncio
async def test_interrupted_workflow_catalogue_retains_rows_clock_and_context_scope(setup):
    from maxpane_dashboard.data import surf_work as work
    reader, client, cache, clock, raw = setup
    base = dict(raw['workflows'][0], contractsJobId=None, frontendJobId=None)
    historical = dict(base, id='22222222-2222-4222-8222-222222222222', status='blocked')
    prior = work.snapshot([], [base, historical], {}, read_ts=clock.now - 60,
                          expected_ids=[], context_workflow_ids=[historical['id']])
    assert work.coerce_snapshot(prior, now=clock.now) is not None
    cache.store_last_good(SLOT_SURF_WORK, prior, ts=clock.now - 60)
    flows = [dict(base, id=f'11111111-1111-4111-8111-{n:012d}', status='completed',
                  createdAt=datetime.fromtimestamp(clock.now - n * 86400, timezone.utc).isoformat().replace('+00:00', 'Z'))
             for n in range(100)]
    calls = []
    second_page = None
    async def pages(*, limit, before=None):
        calls.append(before)
        return copy.deepcopy(second_page if before else flows)
    client.fetch_workflows = pages
    raw.update(jobs=[], workflows=[], executing_count=0)
    await reader.offer()
    retained = cache.get_last_good(SLOT_SURF_WORK).payload
    assert len(retained['workflows']) == 102 and retained['partial']
    assert retained['read_ts'] == prior['read_ts']
    assert base['id'] in retained['current_workflow_ids']
    assert historical['id'] not in retained['current_workflow_ids']
    assert reader.project()['summary']['jobs'] == 0
    assert work.coerce_snapshot(retained, now=clock.now) is not None
    clock.now += 60
    second_page = []
    await reader.offer()
    complete = cache.get_last_good(SLOT_SURF_WORK).payload
    assert len(complete['workflows']) == 100 and not complete['partial']
    assert base['id'] not in complete['current_workflow_ids']
    assert calls == [None, flows[-1]['createdAt'], flows[-1]['createdAt']]


@pytest.mark.asyncio
async def test_failed_later_history_page_retains_entire_previous_snapshot(setup):
    reader, _, cache, clock, raw = setup
    base = dict(raw['jobs'][0], state='completed')
    raw['jobs'] = [dict(base, id=f'00000000-0000-0000-0000-{n:012d}',
                       createdAt=datetime.fromtimestamp(clock.now - n, timezone.utc).isoformat().replace('+00:00', 'Z'))
                   for n in range(100)]
    raw.update(next_jobs=[dict(base, id='00000000-0000-0000-0000-000000000100')],
               workflows=[], executing_count=0)
    await reader.offer()
    before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
    assert before.payload['jobs_loaded'] == 101
    clock.now += 60
    raw['next_jobs'] = None
    await reader.offer()
    assert cache.get_last_good(SLOT_SURF_WORK) == before
    assert cache.last_failure_ts(TIER_SURF_WORK) == clock.now
    assert reader.project()['state'] == 'stale'


@pytest.mark.asyncio
@pytest.mark.parametrize('full_head', [False, True])
@pytest.mark.parametrize('population', ['missing', 'valid', 'inconsistent'])
async def test_older_open_jobs_survive_cutoff_and_do_not_require_details(setup, full_head, population):
    reader, client, _, clock, raw = setup
    base = raw['jobs'][0]
    def old_job(index, state):
        return dict(base, id=f'00000000-0000-0000-0000-{index:012d}', state=state,
                    createdAt=datetime.fromtimestamp(clock.now - 86401 - index, timezone.utc).isoformat().replace('+00:00', 'Z'))
    tail = [old_job(100, 'blocked'), old_job(101, 'queued'), old_job(102, 'completed')]
    raw.update(jobs=[old_job(n, 'completed') for n in range(100)] if full_head else tail,
               next_jobs=tail, workflows=[], executing_count=0)
    if population != 'missing':
        async def overview():
            total = 103 if full_head else 3
            return {'counts': {'jobs': total - (population == 'inconsistent'),
                               'jobStates': {'executing': 0, 'blocked': 1, 'queued': 1, 'completed': total - 2}}}
        client.fetch_overview = overview
    await reader.offer()
    data = reader.project()
    assert {job['id'] for job in data['jobs']} == {job['id'] for job in tail[:2]}
    assert data['summary']['jobs'] == 0 and data['summary']['blocked'] == 1
    assert not data['partial']
    assert not any(call[0] == 'detail' for call in client.calls)
    assert len([call for call in client.calls if call[0] == 'jobs']) == (2 if full_head else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('warm', [False, True])
async def test_capped_older_open_scan_is_partial_or_retains_previous_snapshot(setup, monkeypatch, warm):
    from maxpane_dashboard.data import surf_work as work
    reader, _, cache, clock, raw = setup
    before = None
    if warm:
        await reader.offer()
        before = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK))
        clock.now += 60
    base = raw['jobs'][0]
    raw.update(jobs=[dict(base, id=f'00000000-0000-0000-0000-{n:012d}', state='completed',
                          createdAt=datetime.fromtimestamp(clock.now - 86401 - n, timezone.utc).isoformat().replace('+00:00', 'Z'))
                     for n in range(100)], workflows=[], executing_count=0)
    monkeypatch.setattr(work, 'SCAN_PAGES', 1)
    await reader.offer()
    if warm:
        assert cache.get_last_good(SLOT_SURF_WORK) == before
        assert reader.project()['state'] == 'stale'
    else:
        assert reader.project()['partial']
        assert not cache.get_last_good(SLOT_SURF_WORK).payload['active_scan_complete']


@pytest.mark.asyncio
@pytest.mark.parametrize('total', [1000, 999, True, '1000'])
async def test_open_population_shortcut_requires_matching_validated_total(setup, total):
    reader, client, _, clock, raw = setup
    base = raw['jobs'][0]
    raw.update(jobs=[dict(base, id=f'00000000-0000-0000-0000-{n:012d}',
                         state='blocked' if n == 0 else 'completed',
                         createdAt=datetime.fromtimestamp(clock.now - 86401 - n, timezone.utc).isoformat().replace('+00:00', 'Z'))
                    for n in range(100)], next_jobs=[], workflows=[], executing_count=0)
    async def overview():
        return {'counts': {'jobs': total, 'jobStates': {'executing': 0, 'blocked': 1, 'completed': 999}}}
    client.fetch_overview = overview
    await reader.offer()
    assert not reader.project()['partial']
    assert reader.project()['summary']['blocked'] == 1
    assert len([call for call in client.calls if call[0] == 'jobs']) == (1 if type(total) is int and total == 1000 else 2)


@pytest.mark.asyncio
async def test_recent_blocked_diagnostics_remain_bounded_while_old_rows_only_list(setup):
    reader, client, _, clock, raw = setup
    recent = dict(raw['details'][0], state='blocked',
                  createdAt=datetime.fromtimestamp(clock.now, timezone.utc).isoformat().replace('+00:00', 'Z'))
    old = dict(recent, id='00000000-0000-0000-0000-000000000100',
               createdAt=datetime.fromtimestamp(clock.now - 86401, timezone.utc).isoformat().replace('+00:00', 'Z'))
    raw.update(jobs=[recent, old], details=[recent], workflows=[], executing_count=0)
    await reader.offer()
    assert [call for call in client.calls if call[0] == 'detail'] == [('detail', recent['id'])]
    assert reader.project()['summary']['blocked'] == 2
    assert not reader.project()['partial']
