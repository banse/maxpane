"""Foreground publication and reader lifetime; no network."""
import asyncio
import copy
from datetime import datetime, timezone

from maxpane_dashboard.data.surf_cache import SLOT_SURF_WORK, TIER_SURF_WORK
from tests.data.test_surf_work_reader import setup, incremental_setup, optional_jobs, project_setup


async def test_expired_catalogue_publishes_delta_before_reconciliation(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    await reader.offer()
    old = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK).payload)
    clock.now += 601
    raw['jobs'][0]['updatedAt'] = datetime.fromtimestamp(clock.now, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    entered = asyncio.Event()
    fetch = client.fetch_jobs
    async def hanging(**kwargs):
        if not kwargs.get('since'):
            entered.set()
            await asyncio.Event().wait()
        return await fetch(**kwargs)
    client.fetch_jobs = hanging
    reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        current = cache.get_last_good(SLOT_SURF_WORK).payload
        assert current['catalogue']['jobs']['watermark'] > old['catalogue']['jobs']['watermark']
        assert current['catalogue']['jobs']['full_ts'] == old['catalogue']['jobs']['full_ts']
        assert reader.offer() is reader.task
    finally:
        await reader.close()


async def test_optional_fanout_is_bounded_and_cancelled_with_reader(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    optional_jobs(raw)
    entered = asyncio.Event()
    active = set()
    total = []
    async def hanging(identity, *, fresh_after=None):
        active.add(identity); total.append(identity)
        if len(active) == 4:
            entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            active.remove(identity)
    client.read_job_detail = hanging
    task = reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert cache.get_last_good(SLOT_SURF_WORK) is not None
        clock.now += 30
        assert reader.offer() is task
    finally:
        await reader.close()
    assert len(total) == 4 and not active
    assert cache.last_failure_ts(TIER_SURF_WORK) is None
    assert cache.get_last_good(SLOT_SURF_WORK).payload['optional_cursor'] is None


async def test_optional_time_budget_preserves_foreground(incremental_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work_reader
    reader, client, cache, clock, raw, _ = incremental_setup
    optional_jobs(raw)
    monkeypatch.setattr(surf_work_reader, 'OPTIONAL_SECONDS', 0)
    async def hanging(identity, *, fresh_after=None):
        await asyncio.Event().wait()
    client.read_job_detail = hanging
    await asyncio.wait_for(reader.offer(), 1)
    assert reader.project()['summary']['jobs'] == 0
    assert cache.last_failure_ts(TIER_SURF_WORK) is None
    assert cache.get_last_good(SLOT_SURF_WORK).payload['optional_cursor'] is None


async def test_complete_population_witness_can_omit_zero_state(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    optional_jobs(raw, count=1)
    async def overview():
        return {'counts': {'jobs': 1, 'jobStates': {'blocked': 1}}}
    client.fetch_overview = overview
    await reader.offer()
    assert reader.project()['summary']['jobs'] == 0
    assert cache.get_last_good(SLOT_SURF_WORK).payload['active_scan_complete']


async def test_resumed_workflow_scan_catches_updates_to_earlier_pages(incremental_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work
    reader, client, cache, clock, raw, requests = incremental_setup
    monkeypatch.setattr(surf_work, 'WORKFLOW_PAGES_PER_READ', 1)
    start = clock.now
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    prototype = raw['workflows'][0]
    raw.update(jobs=[], details=[], executing_count=0,
        workflows=[dict(prototype, id=f'00000000-0000-0000-0000-{n:012d}',
            createdAt=stamp(start - 500 - n), updatedAt=stamp(start - 500 - n)) for n in range(101)])
    await reader.offer()
    assert not cache.get_last_good(SLOT_SURF_WORK).payload['workflow_scan_complete']
    clock.now += 400
    raw['workflows'][0].update(objective='changed during pagination', updatedAt=stamp(start + 50))
    raw['workflows'][-1]['updatedAt'] = stamp(start + 390)
    requests.clear()
    await reader.offer()
    saved = cache.get_last_good(SLOT_SURF_WORK).payload
    assert saved['workflow_scan_complete']
    assert saved['workflows'][0]['objective'] == 'changed during pagination'
    assert any(kind == 'workflows' and query['since'] == stamp(start - 300) for kind, query in requests)
    assert saved['catalogue']['workflows']['full_ts'] == clock.now


async def test_fresh_active_job_publishes_before_old_project_versions(project_setup):
    reader, client, cache, clock, raw = project_setup
    entered = asyncio.Event()
    fetch = client.fetch_job
    async def hanging(identity):
        if identity == raw['details'][1]['id']:
            entered.set()
            await asyncio.Event().wait()
        return await fetch(identity)
    client.fetch_job = hanging
    reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        saved = cache.get_last_good(SLOT_SURF_WORK)
        assert saved is not None
        assert saved.payload['partial']
        assert saved.payload['projects'] == []
        assert reader.project()['summary']['jobs'] == 1
    finally:
        await reader.close()


async def test_malformed_reconcile_keeps_all_committed_rows(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    raw['jobs'] = [dict(row, state='completed') for row in raw['jobs']]
    raw.update(details=[], workflows=[], executing_count=0)
    await reader.offer()
    old = cache.get_last_good(SLOT_SURF_WORK).payload
    clock.now += 601
    fetch = client.fetch_jobs
    async def malformed(**kwargs):
        return await fetch(**kwargs) if kwargs.get('since') else [raw['jobs'][0], {'id': False}]
    client.fetch_jobs = malformed
    await reader.offer()
    saved = cache.get_last_good(SLOT_SURF_WORK).payload
    assert {row['id'] for row in saved['jobs']} == {row['id'] for row in old['jobs']}
    assert cache.last_failure_ts(TIER_SURF_WORK) == clock.now


async def test_optional_mixed_failure_timeout_retains_same_version_evidence(incremental_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work_reader
    reader, client, cache, clock, raw, _ = incremental_setup
    identities = optional_jobs(raw, 2)
    await reader.offer()
    old = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK).payload)
    clock.now += 121
    monkeypatch.setattr(surf_work_reader, 'OPTIONAL_SECONDS', .01)
    async def hanging(identity, *, fresh_after=None):
        if identity == identities[0]:
            return None
        await asyncio.Event().wait()
    client.read_job_detail = hanging
    await reader.offer()
    saved = cache.get_last_good(SLOT_SURF_WORK).payload
    assert saved['details_loaded'] == 2
    assert saved['optional_details'] == old['optional_details']
    assert saved['optional_cursor'] == old['optional_cursor']
    assert cache.last_failure_ts(TIER_SURF_WORK) is None


async def test_full_scan_includes_hidden_creation_boundary_ties(incremental_setup, monkeypatch):
    from maxpane_dashboard.data import surf_work
    reader, client, cache, clock, raw, _ = incremental_setup
    monkeypatch.setattr(surf_work, 'PAGE_LIMIT', 2)
    prototype = raw['jobs'][0]
    raw.update(workflows=[], details=[], executing_count=0,
        jobs=[dict(prototype, id=f'00000000-0000-0000-0000-{n+1:012d}', state='blocked',
             createdAt=datetime.fromtimestamp(clock.now - age, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
             updatedAt=datetime.fromtimestamp(clock.now - 1, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
             for n, age in enumerate((10, 20, 20))])
    await reader.offer()
    saved = cache.get_last_good(SLOT_SURF_WORK).payload
    assert len(saved['catalogue']['jobs']['rows']) == 3
    assert reader.project()['summary']['blocked'] == 3


async def test_full_workflow_scan_includes_hidden_boundary_tie(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    prototype = raw['workflows'][0]
    raw.update(jobs=[], details=[], executing_count=0,
        workflows=[dict(prototype, id=f'00000000-0000-0000-0000-{n+1:012d}',
            createdAt=datetime.fromtimestamp(clock.now - min(n + 1, 100), timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            updatedAt=datetime.fromtimestamp(clock.now - 1, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
            for n in range(101)])
    await reader.offer()
    saved = cache.get_last_good(SLOT_SURF_WORK).payload
    assert saved['workflow_scan_complete']
    assert len(saved['catalogue']['workflows']['rows']) == 101


async def test_legacy_cache_publishes_current_before_history(incremental_setup):
    reader, client, cache, clock, raw, _ = incremental_setup
    await reader.offer()
    old = copy.deepcopy(cache.get_last_good(SLOT_SURF_WORK).payload)
    old.pop('catalogue')
    cache.store_last_good(SLOT_SURF_WORK, old, ts=clock.now)
    clock.now += 30
    active = raw['jobs'][0]
    raw['jobs'] = [active] + [dict(active, id=f'00000000-0000-0000-0000-{n:012d}', state='completed',
        createdAt=datetime.fromtimestamp(clock.now - 1500 - n, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
        for n in range(99)]
    raw.update(workflows=[], executing_count=2)
    entered = asyncio.Event()
    fetch = client.fetch_jobs
    async def hanging(**kwargs):
        if kwargs.get('before'):
            entered.set()
            await asyncio.Event().wait()
        return await fetch(**kwargs)
    client.fetch_jobs = hanging
    reader.offer()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        current = cache.get_last_good(SLOT_SURF_WORK)
        assert current.ts == clock.now
        assert current.payload['partial']
        assert reader.project()['summary']['jobs'] == 2
        assert {j['id'] for j in old['jobs']} <= {j['id'] for j in current.payload['jobs']}
    finally:
        await reader.close()
