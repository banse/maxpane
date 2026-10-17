"""Bounded independent reads, retained failures and identity-safe card joins."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surf_agent_card_sources as sources
from maxpane_dashboard.data.surf_cache import SurfCache
from maxpane_dashboard.data.surf_swarm_client import JobDetailRead

NOW = 1791990000.
OWNER = '0x84f4b7424e1b0464f9c749725c1f34bed9aa8ada'
JOB = 'f708c332-034f-47b3-b204-318734811863'


def seat(owner=OWNER):
    return dict(owner=owner, work=[dict(jobId=JOB, nodeKey='audit_economics', status='accepted')])


def earned():
    return [dict(chain_id=1, token_address='0x'+'1'*40, job_id=JOB, launched_ts=NOW-60,
                 builder=True, claimed=True)]


@pytest.fixture
def reader(tmp_path):
    cache = SurfCache(path=str(tmp_path/'cache.json'), clock=lambda: NOW)
    earnings = AsyncMock()
    earnings.fetch.return_value = earned()
    swarm = AsyncMock()
    swarm.fetch_job.return_value = json.loads((Path('tests/fixtures/surf/agent_work') / (JOB+'.json')).read_text())
    reader = sources.AgentCardSources(cache, earnings, swarm, clock=lambda: NOW)
    swarm._monotonic = lambda: NOW
    async def detail(job, *, fresh_after=None):
        payload = await swarm.fetch_job(job)
        return JobDetailRead(payload, reader.clock() if payload is not None else None,
                             NOW, None, False)
    swarm.read_job_detail.side_effect = detail
    return reader, earnings, swarm


async def test_success_clocks_distinct_assets_and_selected_seat_join(reader):
    r, earnings, swarm = reader
    await r.read(seat(), NOW)
    data, meta = sources.project(r.capture(NOW), seat(), now=NOW)
    assert data['_agent_earnings'] == dict(earned=1, worked_on=1, earned_24h=1, worked_on_24h=1, worked_recent=True)
    assert data['_agent_nodes'] == dict(oracle=0, launches=1, other=0, known_jobs=1, total_jobs=1)
    assert meta['earnings']['read_ts'] == meta['agent_work']['read_ts'] == NOW
    await r.read(seat(), NOW+1)
    assert earnings.fetch.await_count == swarm.fetch_job.await_count == 1
    other_seat = dict(seat(), work=[])
    data, _ = sources.project(r.capture(NOW), other_seat, now=NOW)
    assert data['_agent_earnings']['earned'] == 0
    assert data['_agent_earnings']['worked_on'] == 0
    assert data['_agent_earnings']['earned_24h'] == 0
    assert data['_agent_earnings']['worked_on_24h'] == 0
    data, meta = sources.project(r.capture(NOW), seat('0x'+'9'*40), now=NOW)
    assert data['_agent_earnings'] == {} and meta['earnings']['state'] == 'unavailable'


async def test_membership_reads_failed_attempt_jobs_without_reclassifying_nodes(reader):
    r, _, swarm = reader
    raw = dict(seat(), work=[dict(jobId=JOB, nodeKey='build', status='failed')])
    await r.read(raw, NOW)
    swarm.fetch_job.assert_awaited_once_with(JOB)
    capture = r.capture(NOW)
    assert capture['work'][JOB]['launched'] is True
    assert sources.project(capture, raw, now=NOW)[0]['_agent_nodes']['launches'] == 0


async def test_failed_refresh_keeps_values_and_clocks_and_backoff(reader):
    r, earnings, swarm = reader
    await r.read(seat(), NOW)
    earnings.fetch.return_value = None
    swarm.fetch_job.return_value = None
    await r.read(seat(), NOW+601)
    data, meta = sources.project(r.capture(NOW+601), seat(), now=NOW+601)
    assert data['_agent_earnings']['earned'] == 1 and data['_agent_nodes']['launches'] == 1
    assert meta['earnings'] == dict(read_ts=NOW, state='failed')
    assert meta['agent_work'] == dict(read_ts=NOW, state='stale')
    await r.read(seat(), NOW+602)
    assert earnings.fetch.await_count == 2
    earnings.fetch.return_value = earned()
    r.clock = lambda: NOW+721
    await r.read(seat(), NOW+721)
    assert sources.project(r.capture(NOW+721), seat(), now=NOW+721)[1]['earnings']['state'] == 'ok'


@pytest.mark.parametrize('cached', [False, True])
async def test_pending_is_actual_owner_read_and_cancellation_clears_it(reader, cached):
    r, earnings, _ = reader
    if cached:
        r.clock = lambda: NOW-601
        await r.read(seat(), NOW-601)
        r.clock = lambda: NOW
    entered, release = asyncio.Event(), asyncio.Event()
    async def hold(owner):
        entered.set()
        await release.wait()
        return None
    earnings.fetch.side_effect = hold
    task = asyncio.create_task(r.read(seat(), NOW))
    await entered.wait()
    frozen = r.capture(NOW)
    assert sources.project(frozen, seat(), now=NOW)[1]['earnings']['state'] == 'pending'
    assert sources.project(frozen, seat('0x'+'9'*40), now=NOW)[1]['earnings']['state'] == 'unavailable'
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sources.project(r.capture(NOW), seat(), now=NOW)[1]['earnings']['state'] == ('stale' if cached else 'unavailable')
    assert sources.project(frozen, seat(), now=NOW)[1]['earnings']['state'] == 'pending'


def test_cache_validation_is_per_owner_and_never_treats_invalid_rows_as_empty():
    valid = dict(read_ts=NOW, rows=earned())
    raw = {OWNER: valid, None: valid, 'bad': valid, '0x'+'2'*40: dict(valid, rows=[{}]),
           '0x'+'3'*40: dict(valid, read_ts=NOW+1)}
    assert sources.coerce_earnings(raw, NOW) == {OWNER: valid}
    assert sources.coerce_earnings({OWNER: dict(valid, rows=[])}, NOW)[OWNER]['rows'] == []


@pytest.mark.parametrize('work', [None, [dict(nodeKey='audit_math', status='accepted', jobId=None)]])
def test_unknown_accepted_job_identity_does_not_claim_zero_earnings(work):
    capture = dict(earnings={OWNER: dict(read_ts=NOW, rows=earned())})
    raw = dict(seat(), work=work)
    data, _ = sources.project(capture, raw, now=NOW)
    assert data['_agent_earnings']['earned'] is None
    assert data['_agent_earnings']['worked_on'] is None
    assert data['_agent_earnings']['earned_24h'] is None
    assert data['_agent_earnings']['worked_on_24h'] is None
    assert data['_agent_earnings']['worked_recent'] is None


def test_owner_change_rejoins_rewards_to_the_same_seat_not_the_new_wallet_total():
    new_owner = '0x' + '9' * 40
    matched = earned()[0]
    unrelated = dict(matched, token_address='0x' + '2' * 40,
                     job_id='11111111-1111-1111-1111-111111111111')
    capture = dict(earnings={
        OWNER: dict(read_ts=NOW, rows=[matched]),
        new_owner: dict(read_ts=NOW, rows=[matched, unrelated]),
    })
    for owner in (OWNER, new_owner):
        data, _ = sources.project(capture, seat(owner), now=NOW)
        assert data['_agent_earnings']['earned'] == 1
        assert data['_agent_earnings']['earned_24h'] == 1
    other_seat = dict(seat(new_owner), work=[])
    data, _ = sources.project(capture, other_seat, now=NOW)
    assert data['_agent_earnings']['earned'] == data['_agent_earnings']['earned_24h'] == 0


async def test_unread_failed_jobs_do_not_starve_later_membership_reads(reader):
    r, _, swarm = reader
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(65)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='audit_math', status='accepted') for job in jobs])
    swarm.fetch_job.return_value = None
    await r.read(raw, NOW)
    assert len(swarm.fetch_job.await_args_list) == 64
    await r.read(raw, NOW+120)
    assert jobs[-1] in [call.args[0] for call in swarm.fetch_job.await_args_list]


async def test_first_read_completes_seat_420_sized_history_with_bounded_concurrency(reader):
    r, _, swarm = reader
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(53)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='audit_math', status='accepted') for job in jobs])
    live, peak = 0, 0
    fixture = swarm.fetch_job.return_value
    async def fetch(job):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        try:
            await asyncio.sleep(0)  # Yield without a wall-clock delay.
            return dict(fixture, id=job)
        finally:
            live -= 1
    swarm.fetch_job.side_effect = fetch
    await r.read(raw, NOW)
    data, meta = sources.project(r.capture(NOW), raw, now=NOW)
    assert data['_agent_nodes'] == dict(oracle=0, launches=53, other=0, known_jobs=53, total_jobs=53)
    assert meta['agent_work'] == dict(state='ok', read_ts=NOW)
    assert peak == 4 and live == 0
    await r.read(raw, NOW+1)
    assert swarm.fetch_job.await_count == 53


async def test_cancelled_membership_batch_stops_all_in_flight_reads(reader):
    r, _, swarm = reader
    started, release = asyncio.Event(), asyncio.Event()
    live = 0
    fixture = swarm.fetch_job.return_value
    async def fetch(job):
        nonlocal live
        live += 1
        started.set()
        try:
            await release.wait()
            return dict(fixture, id=job)
        finally:
            live -= 1
    swarm.fetch_job.side_effect = fetch
    raw = dict(seat(), work=[dict(jobId=f'{index:08x}-034f-47b3-b204-318734811863',
                                  nodeKey='audit_math', status='accepted') for index in range(10)])
    task = asyncio.create_task(r.read(raw, NOW))
    await started.wait()
    assert live == 4
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert live == 0 and swarm.fetch_job.await_count == 4
    assert r.capture(NOW)['work'] == {}


async def test_manager_selected_read_persistence_and_switch_never_borrow_other_owner(tmp_path, monkeypatch):
    from tests.data.test_surf_manager import FakeClock
    from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager, _seat_payload_of
    from maxpane_dashboard.data.surf_cache import SLOT_AGENT_EARNINGS, SLOT_AGENT_WORK
    raw = dict(_seat_payload_of(420), **seat())
    swarm = _FakeSwarm(seats={420: raw})
    swarm.fetch_job = AsyncMock(return_value=json.loads((Path('tests/fixtures/surf/agent_work') / (JOB+'.json')).read_text()))
    earnings = AsyncMock()
    earnings.fetch.return_value = earned()
    manager = _manager(tmp_path, swarm, clock=FakeClock(NOW), seat=420, earnings_client=earnings)
    for method in ('_resolve_seat_owner', '_pool_swarm_seat_rewards', '_pool_swarm_answers', '_pool_swarm_oracle', '_pool_swarm_job_details'):
        monkeypatch.setattr(manager, method, AsyncMock())
    try:
        await manager._pool_swarm_seat(420, NOW)
        earnings.fetch.assert_not_awaited()
        manager.set_agent_active(True)
        await manager._pool_swarm_seat(420, NOW)
        hero = manager._project_hub()['surf_agent_hero']
        assert hero['earnings']['earned'] == hero['earnings']['worked_on'] == 1
        assert hero['earnings']['earned_24h'] == hero['earnings']['worked_on_24h'] == 1
        assert 'claimed' not in hero['earnings']
        assert hero['nodes']['launches'] == 1
        manager.set_seat(7)
        assert manager._project_hub()['surf_agent_hero']['earnings']['earned'] is None
        manager.save_cache()
        loaded = SurfCache(path=manager._cache_path, clock=lambda: NOW)
        loaded.load(slot_coercers={SLOT_AGENT_EARNINGS: lambda value: sources.coerce_earnings(value, NOW),
                                  SLOT_AGENT_WORK: lambda value: sources.work.coerce_points(value, NOW)})
        assert loaded.get_last_good(SLOT_AGENT_EARNINGS).payload[OWNER]['rows'] == earned()
        assert loaded.get_last_good(SLOT_AGENT_WORK).payload[JOB]['launched'] is True
    finally:
        await manager.close()
    earnings.close.assert_awaited_once()
