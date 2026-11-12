"""Bounded independent reads, retained failures and identity-safe card joins."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from tests.data.test_surf_agent_work import complete_history

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
    data, meta = sources.project(r.capture(NOW), complete_history(seat()), now=NOW)
    assert data['_agent_earnings'] == dict(earned=1, worked_on=1, earned_24h=1, worked_on_24h=1, worked_recent=True, wallet_total=1)
    assert data['_agent_nodes'] == dict(oracle=0, launches=1, other=0, known_jobs=1, total_jobs=1, launches_total=1, oracle_total=0, research=0, research_total=0)
    assert meta['earnings']['read_ts'] == meta['agent_work']['read_ts'] == NOW
    await r.read(seat(), NOW+1)
    assert earnings.fetch.await_count == swarm.fetch_job.await_count == 1
    other_seat = dict(seat(), work=[])
    data, _ = sources.project(r.capture(NOW), complete_history(other_seat), now=NOW)
    assert data['_agent_earnings']['earned'] == 0
    assert data['_agent_earnings']['worked_on'] == 0
    assert data['_agent_earnings']['earned_24h'] == 0
    assert data['_agent_earnings']['worked_on_24h'] == 0
    data, meta = sources.project(r.capture(NOW), complete_history(seat('0x'+'9'*40)), now=NOW)
    assert data['_agent_earnings'] == {} and meta['earnings']['state'] == 'unavailable'


@pytest.mark.parametrize('accepted_work', [None, [], [dict(jobId=JOB, nodeKey='build', status='accepted')]])
def test_wallet_total_counts_distinct_production_assets_independently_of_seat_work(accepted_work):
    row = earned()[0]
    rows = [row, dict(row), dict(row, chain_id=8453, builder=False),
            dict(row, chain_id=4663, builder=False, claimed=None),
            dict(row, token_address='0x'+'2'*40, builder=False),
            *[dict(row, chain_id=chain) for chain in (11155111, 84532, 46630, 999999)]]
    capture = dict(earnings={OWNER: dict(read_ts=NOW, rows=rows)})
    raw = dict(seat(), work=accepted_work)
    data, _ = sources.project(capture, complete_history(raw), now=NOW)
    assert data['_agent_earnings']['wallet_total'] == 4
    assert data['_agent_earnings']['earned'] == (None if accepted_work is None else 0 if not accepted_work else 5)
    assert sources.project(capture, complete_history(seat('0x'+'9'*40)), now=NOW)[0]['_agent_earnings'] == {}
    capture['earnings'][OWNER]['rows'] = []
    assert sources.project(capture, complete_history(raw), now=NOW)[0]['_agent_earnings']['wallet_total'] == 0


async def test_membership_reads_failed_attempt_jobs_without_reclassifying_nodes(reader):
    r, _, swarm = reader
    raw = dict(seat(), work=[dict(jobId=JOB, nodeKey='build', status='failed')])
    await r.read(raw, NOW)
    swarm.fetch_job.assert_awaited_once_with(JOB)
    capture = r.capture(NOW)
    assert capture['work'][JOB]['launched'] is True
    assert sources.project(capture, complete_history(raw), now=NOW)[0]['_agent_nodes']['launches'] == 0


async def test_failed_refresh_keeps_values_and_clocks_and_backoff(reader):
    r, earnings, swarm = reader
    await r.read(seat(), NOW)
    earnings.fetch.return_value = None
    swarm.fetch_job.return_value = None
    await r.read(seat(), NOW+601)
    data, meta = sources.project(r.capture(NOW+601), complete_history(seat()), now=NOW+601)
    assert data['_agent_earnings']['earned'] == 1 and data['_agent_nodes']['launches'] == 1
    assert meta['earnings'] == dict(read_ts=NOW, state='failed')
    assert meta['agent_work'] == dict(read_ts=NOW, state='stale')
    await r.read(seat(), NOW+602)
    assert earnings.fetch.await_count == 2
    earnings.fetch.return_value = earned()
    r.clock = lambda: NOW+721
    await r.read(seat(), NOW+721)
    assert sources.project(r.capture(NOW+721), complete_history(seat()), now=NOW+721)[1]['earnings']['state'] == 'ok'


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
    assert sources.project(frozen, complete_history(seat()), now=NOW)[1]['earnings']['state'] == 'pending'
    assert sources.project(frozen, complete_history(seat('0x'+'9'*40)), now=NOW)[1]['earnings']['state'] == 'unavailable'
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sources.project(r.capture(NOW), complete_history(seat()), now=NOW)[1]['earnings']['state'] == ('stale' if cached else 'unavailable')
    assert sources.project(frozen, complete_history(seat()), now=NOW)[1]['earnings']['state'] == 'pending'


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
    data, _ = sources.project(capture, complete_history(raw), now=NOW)
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
        data, _ = sources.project(capture, complete_history(seat(owner)), now=NOW)
        assert data['_agent_earnings']['earned'] == 1
        assert data['_agent_earnings']['earned_24h'] == 1
    other_seat = dict(seat(new_owner), work=[])
    data, _ = sources.project(capture, complete_history(other_seat), now=NOW)
    assert data['_agent_earnings']['earned'] == data['_agent_earnings']['earned_24h'] == 0


async def test_unread_failed_jobs_do_not_starve_later_membership_reads(reader):
    r, _, swarm = reader
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(65)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='audit_math', status='accepted') for job in jobs])
    swarm.fetch_job.return_value = None
    await r.read(raw, NOW)
    assert len(swarm.fetch_job.await_args_list) == 24
    for tick in (120, 240):
        await r.read(raw, NOW+tick)
    assert jobs[-1] in [call.args[0] for call in swarm.fetch_job.await_args_list]


async def test_membership_resumes_seat_history_with_bounded_reads_and_concurrency(reader):
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
    assert swarm.fetch_job.await_count == 24
    data, meta = sources.project(r.capture(NOW), complete_history(raw), now=NOW)
    assert data['_agent_nodes']['launches_total'] is None
    await r.read(raw, NOW+1)
    assert swarm.fetch_job.await_count == 48
    await r.read(raw, NOW+2)
    data, meta = sources.project(r.capture(NOW), complete_history(raw), now=NOW)
    assert data['_agent_nodes'] == dict(oracle=0, launches=53, other=0, known_jobs=53, total_jobs=53, launches_total=53, oracle_total=0, research=0, research_total=0)
    assert meta['agent_work'] == dict(state='ok', read_ts=NOW)
    assert peak == 4 and live == 0
    await r.read(raw, NOW+1)
    assert swarm.fetch_job.await_count == 53


async def test_workflow_and_contract_followups_share_the_membership_read_budget(reader, monkeypatch):
    r, _, swarm = reader
    monkeypatch.setattr(sources, 'WORK_REQUEST_BUDGET', 3)
    fixture = swarm.fetch_job.return_value
    workflow = '11111111-1111-4111-8111-111111111111'
    contract = '22222222-2222-4222-8222-222222222222'
    monkeypatch.setattr(sources.work, 'membership_point', lambda *args: {'shipped': None})
    monkeypatch.setattr(sources.work, 'workflow_contract', lambda *args: contract)
    # No valid derived membership is needed: admission of nested reads is the invariant.
    swarm.fetch_job.return_value = dict(fixture, workflow={'id': workflow})
    raw = dict(seat(), work=[dict(jobId=f'{index:08x}-034f-47b3-b204-318734811863',
                                  nodeKey='build', status='accepted') for index in range(10)])
    await r.read(raw, NOW)
    assert swarm.read_job_detail.await_count + swarm.fetch_workflow.await_count <= 3


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
        assert hero['earnings']['wallet_total'] == 1
        assert hero['earnings']['earned_24h'] == hero['earnings']['worked_on_24h'] == 1
        assert 'claimed' not in hero['earnings']
        assert hero['nodes']['launches'] == 1
        manager.set_seat(7)
        assert manager._project_hub()['surf_agent_hero']['earnings']['earned'] is None
        assert manager._project_hub()['surf_agent_hero']['earnings']['wallet_total'] is None
        manager.save_cache()
        loaded = SurfCache(path=manager._cache_path, clock=lambda: NOW)
        loaded.load(slot_coercers={SLOT_AGENT_EARNINGS: lambda value: sources.coerce_earnings(value, NOW),
                                  SLOT_AGENT_WORK: lambda value: sources.work.coerce_points(value, NOW)})
        assert loaded.get_last_good(SLOT_AGENT_EARNINGS).payload[OWNER]['rows'] == earned()
        assert loaded.get_last_good(SLOT_AGENT_WORK).payload[JOB]['launched'] is True
    finally:
        await manager.close()
    earnings.close.assert_awaited_once()


WORKFLOW = '64edd9c0-a8f0-4720-ab70-7ca6b38d97fa'
FRONTEND = '22624be0-d2da-400e-91c4-51dac0a9a7f5'


def workflow_evidence():
    fixture = Path('tests/fixtures/surf/agent_work')
    contract = json.loads((fixture / (JOB + '.json')).read_text())
    frontend = json.loads((fixture / (FRONTEND + '.json')).read_text())
    contract['workflow'] = frontend['workflow'] = dict(id=WORKFLOW, status='completed')
    workflow = dict(id=WORKFLOW, status='completed', contracts=dict(id=JOB),
                    frontend=dict(id=FRONTEND), launch={key: contract['launch'][key] for key in ('id', 'status')})
    return contract, frontend, workflow


@pytest.mark.parametrize('chain,expected', [(1, 1), (8453, 1), (11155111, 0)])
async def test_frontend_contribution_follows_exact_workflow_without_changing_record_membership(reader, chain, expected):
    r, _, swarm = reader
    contract, frontend, workflow = workflow_evidence()
    contract['launch']['chainId'] = chain
    swarm.fetch_job.side_effect = lambda job: {JOB: contract, FRONTEND: frontend}[job]
    swarm.fetch_workflow.return_value = workflow
    raw = dict(seat(), work=[dict(jobId=FRONTEND, nodeKey='build', status='accepted'),
                            dict(jobId=FRONTEND, nodeKey='review', status='accepted')])
    await r.read(raw, NOW)
    captured = r.capture(NOW)
    assert captured['work'][FRONTEND] == dict(read_ts=NOW, launched=False, shipped=True, chain_id=chain, family="launch")
    assert sources.project(captured, complete_history(raw), now=NOW)[0]['_agent_nodes']['launches'] == expected
    assert sources.work.record_rows([dict(job_id=FRONTEND, node_key='build')], captured['work'], now=NOW)[0]['launch_state'] == 'not_launched'
    swarm.fetch_workflow.assert_awaited_once_with(WORKFLOW)
    assert [call.args[0] for call in swarm.fetch_job.await_args_list] == [FRONTEND, JOB]
    await r.read(raw, NOW + 1)
    assert swarm.fetch_workflow.await_count == 1


@pytest.mark.parametrize('failure', ['workflow', 'contracts', 'wrong_workflow', 'wrong_frontend', 'wrong_contract_workflow', 'wrong_launch'])
async def test_incomplete_frontend_links_never_claim_zero_and_preserve_previous_facts(reader, failure):
    r, _, swarm = reader
    contract, frontend, workflow = workflow_evidence()
    swarm.fetch_job.side_effect = lambda job: {JOB: contract, FRONTEND: frontend}[job]
    swarm.fetch_workflow.return_value = workflow
    raw = dict(seat(), work=[dict(jobId=FRONTEND, nodeKey='build', status='accepted')])
    # No prior successful read: failed evidence must remain unknown.
    if failure == 'workflow': swarm.fetch_workflow.return_value = None
    if failure == 'contracts': swarm.fetch_job.side_effect = lambda job: frontend if job == FRONTEND else None
    if failure == 'wrong_workflow': workflow['id'] = JOB
    if failure == 'wrong_frontend': workflow['frontend']['id'] = JOB
    if failure == 'wrong_contract_workflow': contract['workflow'] = dict(id=FRONTEND)
    if failure == 'wrong_launch': workflow['launch']['id'] = FRONTEND
    await r.read(raw, NOW)
    assert sources.project(r.capture(NOW), complete_history(raw), now=NOW)[0]['_agent_nodes']['launches'] is None
    assert FRONTEND in r.work_failed
    # A later failed refresh retains an older, independently verified positive.
    r.cache.store_last_good(sources.SLOT_AGENT_WORK,
                            {FRONTEND: dict(read_ts=NOW-601, launched=False, shipped=True, chain_id=1)}, ts=NOW-601)
    await r.read(raw, NOW)
    captured = r.capture(NOW)
    assert captured['work'][FRONTEND]['read_ts'] == NOW-601
    assert sources.project(captured, complete_history(raw), now=NOW)[0]['_agent_nodes']['launches'] == 1


async def test_workflow_without_a_launched_contract_is_a_verified_negative(reader):
    r, _, swarm = reader
    contract, frontend, workflow = workflow_evidence()
    contract['launch'].update(id=None, status=None)
    workflow['launch'] = None
    swarm.fetch_job.side_effect = lambda job: {JOB: contract, FRONTEND: frontend}[job]
    swarm.fetch_workflow.return_value = workflow
    raw = dict(seat(), work=[dict(jobId=FRONTEND, nodeKey='build', status='accepted')])
    await r.read(raw, NOW)
    assert sources.project(r.capture(NOW), complete_history(raw), now=NOW)[0]['_agent_nodes']['launches'] == 0


async def test_legacy_membership_is_refreshed_immediately(reader):
    r, _, swarm = reader
    r.cache.store_last_good(sources.SLOT_AGENT_WORK, {JOB: dict(read_ts=NOW, launched=True)}, ts=NOW)
    assert sources.project(r.capture(NOW), complete_history(seat()), now=NOW)[0]['_agent_nodes']['launches'] is None
    await r.read(seat(), NOW)
    assert sources.project(r.capture(NOW), complete_history(seat()), now=NOW)[0]['_agent_nodes']['launches'] == 1
    swarm.fetch_job.assert_awaited_once_with(JOB)


def test_unknown_oracle_network_marks_membership_partial_independently_of_launch_coverage():
    raw = dict(seat(), work=seat()['work'] + [dict(jobId=FRONTEND, nodeKey='oracle_assess', status='accepted')])
    capture = dict(work={JOB: dict(read_ts=NOW, launched=True, shipped=True, chain_id=1, family="launch")})
    data, meta = sources.project(capture, complete_history(raw), now=NOW)
    assert data['_agent_nodes']['launches'] == 1 and data['_agent_nodes']['oracle'] is None
    assert meta['agent_work']['state'] == 'partial'
    capture['oracle_chains'] = {FRONTEND: 1}
    data, meta = sources.project(capture, complete_history(raw), now=NOW)
    assert data['_agent_nodes']['oracle'] == 1 and meta['agent_work']['state'] == 'ok'


async def test_cancellation_in_workflow_read_does_not_write_partial_membership(reader):
    r, _, swarm = reader
    _, frontend, _ = workflow_evidence()
    swarm.fetch_job.return_value = frontend
    entered, release = asyncio.Event(), asyncio.Event()
    async def hold(identity):
        entered.set()
        await release.wait()
    swarm.fetch_workflow.side_effect = hold
    raw = dict(seat(), work=[dict(jobId=FRONTEND, nodeKey='build', status='accepted')])
    task = asyncio.create_task(r.read(raw, NOW))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert r.capture(NOW)['work'] == {}


async def test_first_membership_batch_prioritizes_accepted_jobs_before_record_only_attempts(reader):
    r, _, swarm = reader
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(69)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='build', status='failed' if index < 10 else 'accepted')
                            for index, job in enumerate(jobs)])
    fixture = swarm.fetch_job.return_value
    swarm.fetch_job.side_effect = lambda job: dict(fixture, id=job)
    await r.read(raw, NOW)
    got = sources.project(r.capture(NOW), complete_history(raw), now=NOW)[0]['_agent_nodes']
    assert got['known_jobs'] == 24 and got['total_jobs'] == 59
    assert got['launches'] is None  # incomplete membership cannot certify the total
    reads = [call.args[0] for call in swarm.fetch_job.await_args_list]
    assert reads == jobs[10:34]


async def test_visible_record_priority_is_bounded_and_other_jobs_keep_their_turn(reader, monkeypatch):
    r, _, swarm = reader
    monkeypatch.setattr(sources, 'WORK_REQUEST_BUDGET', 2)
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(6)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='build', status='accepted') for job in jobs])
    swarm.fetch_job.return_value = None
    await r.read(raw, NOW, priority_jobs=[jobs[-1]])
    assert [call.args[0] for call in swarm.fetch_job.await_args_list] == [jobs[-1], jobs[0]]
    await r.read(raw, NOW, priority_jobs=[jobs[-1]])
    assert [call.args[0] for call in swarm.fetch_job.await_args_list][2:] == jobs[1:3]


async def test_membership_deadline_cancels_pending_reads_but_keeps_completed_points(reader, monkeypatch):
    r, _, swarm = reader
    monkeypatch.setattr(sources, 'WORK_SECONDS', .02)
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(6)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='build', status='accepted') for job in jobs])
    fixture = swarm.fetch_job.return_value
    active = set()
    async def fetch(job):
        active.add(job)
        try:
            if job != jobs[0]:
                await asyncio.Event().wait()
            return dict(fixture, id=job)
        finally:
            active.remove(job)
    swarm.fetch_job.side_effect = fetch
    await asyncio.wait_for(r.read(raw, NOW), 1)
    assert not active
    assert list(r.capture(NOW)['work']) == [jobs[0]]
    assert len(swarm.fetch_job.await_args_list) == 4


async def test_frontend_membership_clock_never_refreshes_older_contract_evidence(reader):
    r, _, swarm = reader
    contract, frontend, workflow = workflow_evidence()
    swarm.fetch_workflow.return_value = workflow
    async def detail(job):
        payload, stamp = (frontend, NOW) if job == FRONTEND else (contract, NOW-100)
        return JobDetailRead(payload, stamp, NOW, None, False)
    swarm.read_job_detail.side_effect = detail
    raw = dict(seat(), work=[dict(jobId=FRONTEND, nodeKey='build', status='accepted')])
    await r.read(raw, NOW)
    captured = r.capture(NOW)
    assert captured['work'][FRONTEND]['read_ts'] == NOW-100
    assert sources.project(captured, complete_history(raw), now=NOW)[1]['agent_work']['read_ts'] == NOW-100


def test_capture_uses_validated_frozen_oracle_chains_without_borrowing_seat_registration_chain(reader):
    r, _, _ = reader
    raw = dict(seat(), chainId=1,
               work=[dict(jobId=FRONTEND, nodeKey='oracle_assess', status='accepted')])
    index = dict(jobs={FRONTEND: WORKFLOW}, newest='2026-10-14T10:00:00Z',
                 oldest='2026-10-14T10:00:00Z', complete=True, chains={FRONTEND: 11155111})
    r.cache.store_last_good(sources.SLOT_SWARM_ORACLE_INDEX, index, ts=NOW)
    frozen = r.capture(NOW)
    assert sources.project(frozen, complete_history(raw), now=NOW)[0]['_agent_nodes']['oracle'] == 0
    index['chains'][FRONTEND] = 1
    assert frozen['oracle_chains'][FRONTEND] == 11155111
    index['chains'][FRONTEND] = True
    r.cache.store_last_good(sources.SLOT_SWARM_ORACLE_INDEX, index, ts=NOW)
    assert sources.project(r.capture(NOW), complete_history(raw), now=NOW)[0]['_agent_nodes']['oracle'] is None


def test_total_job_membership_clock_includes_failed_only_launch_jobs():
    other = '6a7439e9-e9aa-469b-bdb5-633bd6c7f423'
    raw = dict(seat(), work=seat()['work'] + [dict(jobId=other, nodeKey='build', status='failed')])
    points = {job: dict(read_ts=stamp, launched=True, shipped=True, chain_id=1)
              for job, stamp in ((JOB, NOW), (other, NOW-601))}
    capture = dict(work=points, work_failed=set(), oracle_chains={})
    data, meta = sources.project(capture, complete_history(raw), now=NOW)
    assert data['_agent_nodes']['launches_total'] == 2
    assert meta['agent_work'] == dict(state='stale', read_ts=NOW-601)
    del points[other]
    data, meta = sources.project(capture, complete_history(raw), now=NOW)
    assert data['_agent_nodes']['launches'] == 1 and data['_agent_nodes']['launches_total'] is None
    assert meta['agent_work'] == dict(state='partial', read_ts=NOW)


def test_complete_oracle_history_excludes_unlinked_old_attempts_and_keeps_capture_frozen(reader):
    r, _, _ = reader
    raw = dict(seat(), work=[
        dict(jobId=JOB, nodeKey='oracle_assess', status='accepted', submittedAt='2026-10-13T10:00:00Z'),
        dict(jobId=FRONTEND, nodeKey='oracle_assess', status='pending', submittedAt='2026-09-23T19:34:56Z'),
        dict(jobId=FRONTEND, nodeKey='oracle_assess', status='pending', submittedAt='2026-09-23T17:09:17Z')])
    index = dict(jobs={JOB: WORKFLOW}, newest='2026-10-14T10:00:00Z',
                 oldest='2026-09-19T03:18:11Z', complete=True, chains={JOB: 1})
    r.cache.store_last_good(sources.SLOT_SWARM_ORACLE_INDEX, index, ts=NOW)
    frozen = r.capture(NOW)
    index['complete'] = False
    got = sources.project(frozen, complete_history(raw), now=NOW)[0]['_agent_nodes']
    assert got['oracle'] == got['oracle_total'] == 1
    assert got['launches_total'] == 0
    assert sources.oracle_absent(raw, frozen['oracle_index']) == {FRONTEND}


@pytest.mark.parametrize('change', ['incomplete', 'newer', 'missing_time', 'duplicate_newer',
                                  'duplicate_missing_time', 'duplicate_nonoracle_newer',
                                  'ambiguous', 'unknown_chain'])
def test_incomplete_or_conflicting_oracle_evidence_cannot_be_excluded(reader, change):
    r, _, _ = reader
    attempt = dict(jobId=FRONTEND, nodeKey='oracle_assess', status='pending',
                   submittedAt='2026-09-23T19:34:56Z')
    raw = dict(seat(), work=[dict(jobId=JOB, nodeKey='oracle_assess', status='accepted'), attempt])
    index = dict(jobs={JOB: WORKFLOW}, newest='2026-10-14T10:00:00Z',
                 oldest='2026-09-19T03:18:11Z', complete=True, chains={JOB: 1})
    if change == 'incomplete': index['complete'] = False
    if change == 'newer': attempt['submittedAt'] = '2026-10-15T10:00:00Z'
    if change == 'missing_time': attempt['submittedAt'] = None
    if change.startswith('duplicate_'):
        raw['work'].append(dict(attempt,
            nodeKey='build' if change == 'duplicate_nonoracle_newer' else 'oracle_assess',
            submittedAt=(None if change.endswith('missing_time') else '2026-10-15T10:00:00Z')))
    if change == 'ambiguous': index['jobs'][FRONTEND] = None
    if change == 'unknown_chain': index['jobs'][FRONTEND] = FRONTEND
    r.cache.store_last_good(sources.SLOT_SWARM_ORACLE_INDEX, index, ts=NOW)
    frozen = r.capture(NOW)
    assert sources.oracle_absent(raw, frozen['oracle_index']) == set()
    got = sources.project(frozen, complete_history(raw), now=NOW)[0]['_agent_nodes']
    assert got['oracle'] == 1 and got['oracle_total'] is None


async def test_restart_reads_missing_history_before_rechecking_visible_cached_jobs(reader, monkeypatch):
    r, _, swarm = reader
    monkeypatch.setattr(sources, 'WORK_REQUEST_BUDGET', 1)
    raw = dict(seat(), work=seat()['work'] + [dict(jobId=FRONTEND, nodeKey='build', status='pending')])
    r.cache.store_last_good(sources.SLOT_AGENT_WORK,
        {JOB: dict(read_ts=NOW-601, launched=True, shipped=True, chain_id=1)}, ts=NOW-601)
    fixture = swarm.fetch_job.return_value
    swarm.fetch_job.side_effect = lambda job: dict(fixture, id=job)
    await r._work(raw, NOW, priority_jobs=[JOB])
    swarm.fetch_job.assert_awaited_once_with(FRONTEND)
    got = sources.project(r.capture(NOW), complete_history(raw), now=NOW)[0]['_agent_nodes']
    assert got['launches'] == 1 and got['launches_total'] == 2


async def test_unread_launch_retry_precedes_stale_known_jobs_after_a_failed_offer(reader, monkeypatch):
    r, _, swarm = reader
    monkeypatch.setattr(sources, 'WORK_REQUEST_BUDGET', 1)
    raw = dict(seat(), work=seat()['work'] + [dict(jobId=FRONTEND, nodeKey='build', status='pending')])
    r.cache.store_last_good(sources.SLOT_AGENT_WORK,
        {JOB: dict(read_ts=NOW-601, launched=True, shipped=True, chain_id=1)}, ts=NOW-601)
    fixture = swarm.fetch_job.return_value
    swarm.fetch_job.return_value = None
    await r._work(raw, NOW)
    swarm.fetch_job.return_value = dict(fixture, id=FRONTEND)
    await r._work(raw, NOW)
    assert [call.args[0] for call in swarm.fetch_job.await_args_list] == [FRONTEND, FRONTEND]
    assert sources.project(r.capture(NOW), complete_history(raw), now=NOW)[0]['_agent_nodes']['launches_total'] == 2


async def test_persistent_missing_jobs_cannot_starve_known_refresh_or_purpose_backfill(reader):
    r, _, swarm = reader
    jobs = [f'{index:08x}-034f-47b3-b204-318734811863' for index in range(24)]
    raw = dict(seat(), work=[dict(jobId=job, nodeKey='build', status='accepted') for job in [*jobs, JOB]])
    r.cache.store_last_good(sources.SLOT_AGENT_WORK,
        {JOB: dict(read_ts=NOW-601, launched=True, shipped=True, chain_id=1)}, ts=NOW-601)
    fixture = swarm.fetch_job.return_value
    swarm.fetch_job.side_effect = lambda job: fixture if job == JOB else None
    for _ in range(3):
        before = swarm.fetch_job.await_count
        await r._work(raw, NOW)
        assert swarm.fetch_job.await_count - before <= sources.WORK_REQUEST_BUDGET
    assert JOB in [call.args[0] for call in swarm.fetch_job.await_args_list]
    assert r.capture(NOW)['work'][JOB]['family'] == 'launch'
