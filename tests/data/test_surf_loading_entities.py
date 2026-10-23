"""Offline regressions for mutable entity evidence and selection refresh."""
import asyncio
import copy
from uuid import UUID

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_FACTS, TIER_SWARM_LAUNCHES
from tests.analytics.test_surf_launch_checks import checked
from tests.data.test_surf_manager_launches import LaunchSwarm, NOW, fixture, manager


@pytest.mark.asyncio
async def test_site_facts_refresh_mutable_job_and_keep_failed_observation(tmp_path):
    swarm = LaunchSwarm()
    swarm.rows = [fixture('launch_737')]
    site = next(s for s in fixture('sites')['sites'] if s['label'] == 'zto')
    job = fixture('job_zto_site')
    async def sites(): return [site]
    async def detail(identity):
        swarm.calls.append(('site_job', identity))
        return copy.deepcopy(job)
    swarm.fetch_sites, swarm.fetch_job = sites, detail
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        first = copy.deepcopy(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload)
        job['objective'] = 'Updated deployment ' + '0x' + 'f' * 40
        job['updatedAt'] = '2026-10-06T03:00:00Z'
        m._clock.advance(601)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
        refreshed = copy.deepcopy(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload)
        assert refreshed['sites'][site['id']]['addresses'] == ['0x' + 'f' * 40]
        assert refreshed['_site_reads'][site['id']]['read_ts'] > first['_site_reads'][site['id']]['read_ts']
        job = None
        m._clock.advance(601)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
        failed = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload
        assert failed['sites'] == refreshed['sites']
        assert failed['_site_reads'][site['id']]['read_ts'] == refreshed['_site_reads'][site['id']]['read_ts']
        m.cache.save()
        m.cache.load(slot_coercers={SLOT_SWARM_LAUNCH_FACTS: sw.coerce_launch_facts_slot})
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['_site_reads'] == failed['_site_reads']
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_failed_newest_sites_do_not_starve_fourth_site(tmp_path):
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    template = next(s for s in fixture('sites')['sites'] if s['label'] == 'zto')
    sites = [dict(template, id=str(UUID(int=i+1)), jobId=str(UUID(int=i+11))) for i in range(4)]
    async def listing(): return sites
    async def detail(identity):
        swarm.calls.append(('site_job', identity))
        return None
    swarm.fetch_sites, swarm.fetch_job = listing, detail
    m = manager(tmp_path, swarm)
    try:
        for _ in range(2):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
            m._clock.advance(61)
        assert {call[1] for call in swarm.calls if isinstance(call, tuple) and call[0] == 'site_job'} == {s['jobId'] for s in sites}
    finally:
        await m.close()


def test_selected_old_proof_survives_bounded_fact_retention_and_reload(tmp_path):
    row, facts, checks = checked()
    facts.update(row=row, checks=checks, detail_version=[row['status'], row['updatedAt']], evidence_read_ts=100)
    points = {}
    for index in range(2001):
        key = str(UUID(int=index+1))
        point = copy.deepcopy(facts)
        point['row'].update(id=key, launchNumber=index+1)
        points[key] = point
    selected = str(UUID(int=1))
    points[selected]['evidence_read_ts'] = 200
    # A failed request is an attempt, never a fresh successful observation.
    points[str(UUID(int=2))]['detail_attempt_ts'] = 999
    points[str(UUID(int=2))]['evidence_read_ts'] = 1
    cleaned = sw.coerce_launch_facts_slot({'launches': points, 'sites': {}})
    assert len(cleaned['launches']) == 2000
    assert selected in cleaned['launches']
    assert str(UUID(int=2)) not in cleaned['launches']
    from maxpane_dashboard.data.surf_cache import SurfCache
    cache = SurfCache(path=str(tmp_path / 'retained.json'), clock=lambda: 1000)
    cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS, cleaned, ts=200)
    cache.save(); cache.load(slot_coercers={SLOT_SWARM_LAUNCH_FACTS: sw.coerce_launch_facts_slot})
    assert cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][selected]['evidence_read_ts'] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['seat', 'record'])
@pytest.mark.parametrize('in_flight', [False, True])
async def test_selection_refresh_bypasses_prior_identity_poll_throttle(tmp_path, monkeypatch, change, in_flight):
    m = manager(tmp_path)
    m._active_view = 'agent'
    m.set_seat(420)
    calls = []
    entered = asyncio.Event()
    async def collect(view, now):
        calls.append((m._seat_saved, m.record_cap))
        entered.set()
        if len(calls) == 1 and in_flight:
            await asyncio.Event().wait()
    monkeypatch.setattr(m, '_collect_visible_detail', collect)
    monkeypatch.setattr(m, '_project_hub', lambda: {})
    try:
        await m._fetch_visible_detail(); await entered.wait()
        if not in_flight: await m._full_task
        m._clock.advance(1)
        if change == 'seat': m.set_seat(421)
        else: m.set_record_view(80, False)
        await m.drain_reads()
        await m._fetch_visible_detail()
        await asyncio.sleep(0)
        assert len(calls) == 2
        assert calls[-1] == ((421, 40) if change == 'seat' else (420, 80))
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_site_identity_revision_and_negative_retry_are_bounded(tmp_path):
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    site = next(s for s in fixture('sites')['sites'] if s['label'] == 'zto')
    job = dict(fixture('job_zto_site'), project=['malformed'])
    revision = ['2026-10-06T02:00:00Z']
    swarm.known_job_revision = lambda _: revision[0]
    async def sites(): return [site]
    async def detail(identity):
        swarm.calls.append(('site_job', identity))
        return copy.deepcopy(job)
    swarm.fetch_sites, swarm.fetch_job = sites, detail
    m = manager(tmp_path, swarm)
    try:
        for advance in (0, 1, 58):
            m._clock.advance(advance)
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
        assert swarm.calls.count(('site_job', site['jobId'])) == 1
        job['project'] = None
        m._clock.advance(1)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
        assert swarm.calls.count(('site_job', site['jobId'])) == 2
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['sites'][site['id']] is not None
        revision[0] = '2026-10-06T03:00:00Z'
        job['objective'] = 'Revised ' + '0x' + 'd' * 40
        m._clock.advance(1)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['sites'][site['id']]['addresses'] == ['0x' + 'd' * 40]
        site['jobId'] = str(UUID(int=9999))
        job = None
        m._clock.advance(300)  # Site route refresh discovers the changed owning job.
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, m._clock())
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['sites'][site['id']] is None
    finally:
        await m.close()


def test_site_read_metadata_rejects_malformed_identity_and_clocks():
    key = str(UUID(int=1))
    entry = dict(identity=[str(UUID(int=2)), None, None], read_ts=float('nan'), attempt_ts=True)
    raw = {'launches': {}, 'sites': {}, '_site_reads': {key: entry, 'bad': entry}}
    clean = sw.coerce_launch_facts_slot(raw)
    assert clean['_site_reads'] == {key: {'identity': entry['identity']}}
    entry['identity'][0] = None
    assert '_site_reads' not in sw.coerce_launch_facts_slot(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize('changed_field', ['job_revision', 'site_revision'])
async def test_failed_new_revision_cannot_authorize_old_site_joins(tmp_path, changed_field):
    from maxpane_dashboard.analytics import surf_launch_sites as ls
    swarm = LaunchSwarm()
    site = next(s for s in fixture('sites')['sites'] if s['label'] == 'zto')
    job = fixture('job_zto_site')
    revision = ['2026-10-06T02:00:00Z']
    swarm.known_job_revision = lambda _: revision[0]
    async def detail(identity): return copy.deepcopy(job)
    swarm.fetch_job = detail
    m = manager(tmp_path, swarm)
    facts = {'launches': {}, 'sites': {}}
    try:
        await m._refresh_site_facts({'sites': [site]}, facts, 0, m._clock())
        assert facts['sites'][site['id']]['project_jobs'] or facts['sites'][site['id']]['addresses']
        old_key = ls.site_match_key([site], {}, facts['sites'], [])
        if changed_field == 'job_revision':
            revision[0] = '2026-10-06T03:00:00Z'
        else:
            site['updatedAt'] = '2026-10-06T03:00:00Z'
        job = None
        m._clock.advance(1)
        await m._refresh_site_facts({'sites': [site]}, facts, 0, m._clock())
        point = facts['_site_reads'][site['id']]
        assert point['identity'] == [site['jobId'], site.get('updatedAt'), revision[0]]
        assert point['failed'] is True
        assert facts['sites'].get(site['id']) is None
        assert point.get('read_ts') is None
        assert ls.site_match_key([site], {}, facts['sites'], []) != old_key
    finally:
        await m.close()
