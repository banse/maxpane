"""Bounded independent reads, retained failures and identity-safe card joins."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surf_agent_card_sources as sources
from maxpane_dashboard.data.surf_cache import SurfCache

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
    return sources.AgentCardSources(cache, earnings, swarm, clock=lambda: NOW), earnings, swarm


async def test_success_clocks_distinct_assets_and_selected_seat_join(reader):
    r, earnings, swarm = reader
    await r.read(seat(), NOW)
    data, meta = sources.project(r.capture(NOW), seat(), now=NOW)
    assert data['_agent_earnings'] == dict(earned=1, worked_on=1, claimed=1, worked_recent=True)
    assert data['_agent_nodes'] == dict(oracle=0, launches=1, other=0, known_jobs=1, total_jobs=1)
    assert meta['earnings']['read_ts'] == meta['agent_work']['read_ts'] == NOW
    await r.read(seat(), NOW+1)
    assert earnings.fetch.await_count == swarm.fetch_job.await_count == 1
    other_seat = dict(seat(), work=[])
    data, _ = sources.project(r.capture(NOW), other_seat, now=NOW)
    assert data['_agent_earnings']['earned'] == 1
    assert data['_agent_earnings']['worked_on'] == 0
    data, meta = sources.project(r.capture(NOW), seat('0x'+'9'*40), now=NOW)
    assert data['_agent_earnings'] == {} and meta['earnings']['state'] == 'unavailable'


async def test_failed_refresh_keeps_values_and_clocks_and_backoff(reader):
    r, earnings, swarm = reader
    await r.read(seat(), NOW)
    earnings.fetch.return_value = None
    swarm.fetch_job.return_value = None
    await r.read(seat(), NOW+601)
    data, meta = sources.project(r.capture(NOW+601), seat(), now=NOW+601)
    assert data['_agent_earnings']['earned'] == 1 and data['_agent_nodes']['launches'] == 1
    assert meta['earnings'] == dict(read_ts=NOW, state='stale')
    assert meta['agent_work'] == dict(read_ts=NOW, state='stale')
    await r.read(seat(), NOW+602)
    assert earnings.fetch.await_count == 2


async def test_pending_is_actual_owner_read_and_cancellation_clears_it(reader):
    r, earnings, _ = reader
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
    assert sources.project(r.capture(NOW), seat(), now=NOW)[1]['earnings']['state'] == 'unavailable'
    assert sources.project(frozen, seat(), now=NOW)[1]['earnings']['state'] == 'pending'


def test_cache_validation_is_per_owner_and_never_treats_invalid_rows_as_empty():
    valid = dict(read_ts=NOW, rows=earned())
    raw = {OWNER: valid, None: valid, 'bad': valid, '0x'+'2'*40: dict(valid, rows=[{}]),
           '0x'+'3'*40: dict(valid, read_ts=NOW+1)}
    assert sources.coerce_earnings(raw, NOW) == {OWNER: valid}
    assert sources.coerce_earnings({OWNER: dict(valid, rows=[])}, NOW)[OWNER]['rows'] == []


def test_unknown_accepted_job_identity_does_not_claim_zero_worked_on():
    capture = dict(earnings={OWNER: dict(read_ts=NOW, rows=earned())})
    raw = dict(seat(), work=[dict(nodeKey='audit_math', status='accepted', jobId=None)])
    data, _ = sources.project(capture, raw, now=NOW)
    assert data['_agent_earnings']['earned'] == 1
    assert data['_agent_earnings']['worked_on'] is None
    assert data['_agent_earnings']['worked_recent'] is None


async def test_unread_failed_jobs_do_not_starve_later_membership_reads(reader):
    r, _, swarm = reader
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(13)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='audit_math', status='accepted') for job in jobs])
    swarm.fetch_job.return_value = None
    await r.read(raw, NOW)
    assert len(swarm.fetch_job.await_args_list) == 12
    await r.read(raw, NOW+120)
    assert jobs[-1] in [call.args[0] for call in swarm.fetch_job.await_args_list]


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
