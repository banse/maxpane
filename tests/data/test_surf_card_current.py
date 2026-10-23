"""Bounded BOARDROOM current-node reads; fixtures only, no hidden-board hydration."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from maxpane_dashboard.data.surf_swarm_client import JobDetailRead


@pytest.mark.parametrize('status,expected', [
    ('executing', 1), ('completed', 0), ('paused', 0), ('blocked', 0),
    ('future-state', None),
])
async def test_workflow_summary_uses_same_lifecycle_as_detail_board(status, expected):
    captured = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    row = dict(captured['workflows'][0], status=status)
    client = SimpleNamespace(fetch_workflows=AsyncMock(return_value=[row]))
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: captured['read_ts'], swarm_client=client))
    await reader._work()
    assert reader.workflows == expected
    client.fetch_workflows.assert_awaited_once_with(limit=100)


@pytest.fixture
def setup():
    raw = json.loads(Path('tests/fixtures/surf/work/boardroom_current.json').read_text())
    clock = SimpleNamespace(now=raw['read_ts'])
    client = SimpleNamespace(_monotonic=lambda: clock.now,
        fetch_jobs=AsyncMock(return_value=raw['jobs']))
    async def detail(identity, *, fresh_after=None):
        assert fresh_after == clock.now
        payload = next((x for x in raw['details'] if x['id'] == identity), None)
        return JobDetailRead(deepcopy(payload), clock.now if payload else None, clock.now, None, False)
    client.read_job_detail = AsyncMock(side_effect=detail)
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: clock.now, swarm_client=client))
    source = dict(state='ok', read_ts=clock.now,
                  payload=dict(overview=dict(job_states=dict(executing=raw['executing']))))
    return reader, raw, source, clock, client


async def test_current_nodes_complete_snapshot_counts_only_working_nodes(setup):
    reader, raw, source, clock, client = setup
    await reader._current()
    facts = reader.current_work(source)
    assert facts['state'] == 'ok'
    assert facts['node_counts'] == {'adapt': 1, 'audit': 1, 'build': 2}
    assert facts['oracle_agents'] == 0
    assert facts['jobs_loaded'] == raw['executing']
    assert facts['read_ts'] == clock.now
    client.fetch_jobs.assert_awaited_once_with(limit=100)
    assert client.read_job_detail.await_count == raw['executing']


@pytest.mark.parametrize('failure', ['missing', 'mismatch', 'old_overview', 'old_nodes', 'failed', 'malformed'])
async def test_current_nodes_refuse_unproven_or_old_coverage(setup, failure):
    reader, raw, source, clock, client = setup
    if failure == 'missing': raw['details'].pop()
    if failure == 'mismatch': source['payload']['overview']['job_states']['executing'] += 1
    if failure == 'malformed': raw['details'][0]['nodes'][0]['key'] = ''
    await reader._current()
    if failure == 'old_overview': source['read_ts'] -= 61
    if failure == 'old_nodes': clock.now += 61; source['read_ts'] = clock.now
    if failure == 'failed':
        client.fetch_jobs.return_value = None
        await reader._current()
    facts = reader.current_work(source)
    assert facts['node_counts'] is None
    assert facts['oracle_agents'] is None
    assert facts['state'] != 'ok'


async def test_current_nodes_deduplicate_identical_jobs_and_revalidate_previous_active(setup):
    reader, raw, source, clock, client = setup
    raw['jobs'].insert(0, deepcopy(raw['jobs'][0]))
    raw['jobs'].pop()
    await reader._current()
    assert reader.current_work(source)['node_counts'] == {'adapt': 1, 'audit': 1, 'build': 2}


async def test_failed_older_job_detail_remains_eligible_for_next_refresh(setup):
    reader, raw, source, clock, client = setup
    await reader._current()
    client.fetch_jobs.return_value = []
    missing = raw['details'].pop()
    await reader._current()
    assert reader.current_work(source)['node_counts'] is None
    raw['details'].append(missing)
    await reader._current()
    assert reader.current_work(source)['node_counts'] == {'adapt': 1, 'audit': 1, 'build': 2}
    client.fetch_jobs.return_value = []
    client.read_job_detail.reset_mock()
    await reader._current()
    assert client.read_job_detail.await_count == raw['executing']
    assert reader.current_work(source)['node_counts'] == {'adapt': 1, 'audit': 1, 'build': 2}


async def test_oracle_competitive_latest_seat_is_not_a_live_panel_count(setup):
    reader, raw, source, clock, client = setup
    node = raw['details'][0]['nodes'][0]
    node.update(key='oracle_assess', state='working', seat=dict(tokenId='74'),
                live=dict(seat=dict(tokenId='7'), state='accepted'))
    await reader._current()
    facts = reader.current_work(source)
    assert facts['node_counts']['oracle'] == 1
    assert facts['oracle_agents'] is None
    assert 'live panel' in facts['reason']


async def test_unclassified_job_cannot_prove_zero_oracle_agents(setup):
    reader, raw, source, clock, client = setup
    raw['details'][0].pop('template')
    await reader._current()
    facts = reader.current_work(source)
    assert facts['node_counts'] == {'adapt': 1, 'audit': 1, 'build': 2}
    assert facts['oracle_agents'] is None


async def test_current_nodes_are_bounded_and_cancellation_propagates(setup):
    reader, raw, source, clock, client = setup
    raw['jobs'][:] = [dict(id=f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}', state='executing') for i in range(25)]
    await reader._current()
    assert client.read_job_detail.await_count == 24
    assert reader.current_work(source)['node_counts'] is None
    client.fetch_jobs.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await reader._guard(reader._current, 'current')


async def test_current_node_retention_is_bounded_when_new_jobs_arrive(setup):
    reader, raw, source, clock, client = setup
    await reader._current()
    old = set(reader.current_jobs)
    raw['jobs'][:] = [dict(id=f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}', state='executing') for i in range(25)]
    raw['details'].extend(dict(job, nodes=[], template='shape:chain') for job in raw['jobs'])
    client.read_job_detail.reset_mock()
    await reader._current()
    assert client.read_job_detail.await_count == 24
    assert len(reader.current_jobs) == 24
    assert old <= reader.current_jobs.keys()


async def test_current_nodes_single_flight_and_thirty_second_offer(setup):
    reader, raw, source, clock, client = setup
    for method in ('_work', '_pool', '_feed', '_market'):
        setattr(reader, method, AsyncMock())
    reader.offer()
    first = reader.tasks['current']
    reader.offer(force=True)
    assert reader.tasks['current'] is first
    await reader.wait_pending()
    reader.offer()
    assert reader.tasks['current'] is first
    clock.now += 30
    reader.offer()
    assert reader.tasks['current'] is not first
    await reader.wait_pending()


async def test_current_refresh_retains_fresh_cached_counts_while_pending(setup):
    reader, raw, source, clock, client = setup
    await reader._current()
    before = reader.current_work(source)
    entered = asyncio.Event()
    async def pending(**_):
        entered.set()
        await asyncio.Event().wait()
    client.fetch_jobs.side_effect = pending
    task = asyncio.create_task(reader._current())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert reader.current_work(source) == before
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
