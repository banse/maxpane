"""Bounded BOARDROOM current-node reads; fixtures only, no hidden-board hydration."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from maxpane_dashboard.data.surf_swarm_client import JobDetailRead


@pytest.fixture
def older_active():
    raw = json.loads(Path('tests/fixtures/surf/work/boardroom_old_active.json').read_text())
    clock = SimpleNamespace(now=raw['read_ts'])
    client = SimpleNamespace(_monotonic=lambda: clock.now,
        fetch_jobs=AsyncMock(side_effect=[raw['jobs'], [raw['old_job']]]),
        fetch_oracle_requests=AsyncMock(return_value=raw['requests']))
    async def detail(identity, *, fresh_after=None):
        assert identity == raw['old_job']['id']
        return JobDetailRead(deepcopy(raw['old_job']), clock.now, clock.now, None, False)
    client.read_job_detail = AsyncMock(side_effect=detail)
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: clock.now, swarm_client=client))
    source = dict(state='ok', read_ts=clock.now,
                  payload=dict(overview=dict(job_states=dict(executing=1))))
    reader.current_work(source)
    return reader, raw, source, clock, client


async def test_current_discovers_old_submitted_job_outside_recent_page(older_active):
    reader, raw, source, clock, client = older_active
    await reader._current()
    facts = reader.current_work(source)
    assert facts['state'] == 'ok'
    assert facts['node_counts'] == {}
    assert facts['waiting_jobs'] == 1
    assert client.fetch_jobs.await_args_list[1].kwargs == dict(
        limit=500, before=raw['jobs'][-1]['createdAt'])


async def test_current_history_resumes_one_page_per_poll(older_active):
    reader, raw, source, clock, client = older_active
    boundary = datetime.fromisoformat(raw['jobs'][-1]['createdAt']).timestamp()
    tail = [dict(raw['jobs'][-1], id=f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}', state='completed',
                 createdAt=datetime.fromtimestamp(boundary - i - 1, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
            for i in range(500)]
    client.fetch_jobs.side_effect = [raw['jobs'], tail, raw['jobs'], [raw['old_job']]]
    await reader._current()
    assert reader.current_work(source)['node_counts'] is None
    assert client.fetch_jobs.await_count == 2
    await reader._current()
    assert reader.current_work(source)['waiting_jobs'] == 1
    assert client.fetch_jobs.await_args_list[-1].kwargs == dict(limit=500, before=tail[-1]['createdAt'])


async def test_terminal_research_job_does_not_block_active_history_discovery(older_active):
    reader, raw, source, clock, client = older_active
    terminal = dict(raw['old_job'], id=raw['jobs'][0]['id'], state='completed')
    client.fetch_oracle_requests.return_value = [dict(raw['requests'][0], jobId=terminal['id'])]
    async def page(*, limit, before=None):
        return raw['jobs'] if before is None else [raw['old_job']]
    async def detail(identity, *, fresh_after=None):
        payload = terminal if identity == terminal['id'] else raw['old_job']
        return JobDetailRead(payload, clock.now, clock.now, None, False)
    client.fetch_jobs.side_effect = page
    client.read_job_detail.side_effect = detail
    await reader._research()
    for _ in range(3):
        await reader._current()
    assert reader.current_work(source)['waiting_jobs'] == 1
    assert any(call.kwargs.get('before') for call in client.fetch_jobs.await_args_list)


@pytest.mark.parametrize('failure', ['failed', 'cancelled'])
async def test_discovered_job_detail_failure_does_not_skip_its_page(older_active, failure):
    reader, raw, source, clock, client = older_active
    old = raw['old_job']
    boundary = datetime.fromisoformat(old['createdAt']).timestamp()
    tail = [old] + [dict(old, id=f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}', state='completed',
                        createdAt=datetime.fromtimestamp(boundary - i - 1, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
                   for i in range(499)]
    client.fetch_jobs.side_effect = [raw['jobs'], tail, raw['jobs'], tail]
    client.read_job_detail.side_effect = [asyncio.CancelledError() if failure == 'cancelled' else
        JobDetailRead(None, None, clock.now, None, False),
        JobDetailRead(old, clock.now, clock.now, None, False)]
    if failure == 'cancelled':
        with pytest.raises(asyncio.CancelledError):
            await reader._current()
    else:
        await reader._current()
    assert reader._current_before is None
    await reader._current()
    assert reader.current_work(source)['waiting_jobs'] == 1
    assert client.fetch_jobs.await_args_list[1] == client.fetch_jobs.await_args_list[3]
    assert client.read_job_detail.await_count == 2


@pytest.mark.parametrize('failure', ['unavailable', 'nonadvancing', 'duplicate', 'malformed', 'oversized'])
async def test_current_bad_history_retries_without_claiming_complete(older_active, failure):
    reader, raw, source, clock, client = older_active
    old = raw['old_job']
    tail = {'unavailable': None, 'nonadvancing': [raw['jobs'][0]], 'duplicate': [old, old],
            'malformed': [{}], 'oversized': [old] * 501}[failure]
    client.fetch_jobs.side_effect = [raw['jobs'], tail, raw['jobs'], [old]]
    await reader._current()
    assert reader.current_work(source)['node_counts'] is None
    await reader._current()
    assert reader.current_work(source)['waiting_jobs'] == 1
    assert client.fetch_jobs.await_args_list[1] == client.fetch_jobs.await_args_list[3]


async def test_filtered_research_finds_old_request_and_seeds_job_discovery(older_active):
    reader, raw, source, clock, client = older_active
    client.fetch_jobs.side_effect = [raw['jobs'], []]  # Only the filtered request names the job.
    await reader._research()
    await reader._current()
    facts = reader.current_work(source)
    assert facts['research']['count'] == 1
    assert facts['research']['chains'] == 1
    assert facts['research']['state'] == 'ok'
    assert facts['waiting_jobs'] == 1
    client.fetch_oracle_requests.assert_awaited_once_with(limit=500, status='assessing')
    assert client.fetch_jobs.await_count == 2
    client.read_job_detail.assert_awaited_once_with(raw['old_job']['id'], fresh_after=clock.now)
    assert facts['oracle_agents'] is None
    clock.now += 61
    assert reader.current_work(source)['research']['count'] is None


@pytest.mark.parametrize('failure', ['unavailable', 'duplicate', 'wrong_status', 'full_page', 'malformed'])
async def test_research_incomplete_reads_never_prove_zero(older_active, failure):
    reader, raw, source, clock, client = older_active
    await reader._research()
    row = raw['requests'][0]
    client.fetch_oracle_requests.return_value = {
        'unavailable': None, 'duplicate': [row, row],
        'wrong_status': [dict(row, status='attested')],
        'full_page': [dict(row, id=f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}') for i in range(500)],
        'malformed': [{}],
    }[failure]
    await reader._research()
    assert reader.current_work(source)['research']['count'] is None


async def test_research_real_zero_and_cancelled_read(older_active):
    reader, raw, source, clock, client = older_active
    client.fetch_oracle_requests.return_value = []
    await reader._research()
    assert reader.current_work(source)['research']['count'] == 0
    client.fetch_oracle_requests.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await reader._guard(reader._research, 'research')
    assert reader.current_work(source)['research']['read_ts'] == clock.now


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


def workflow_pages(size):
    captured = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    now = captured['read_ts']
    rows = [dict(captured['workflows'][0], id=f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}',
                 status='completed', createdAt=datetime.fromtimestamp(now - i - 1, timezone.utc)
                 .isoformat().replace('+00:00', 'Z')) for i in range(size)]
    client = SimpleNamespace(fetch_workflows=AsyncMock())
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: now, swarm_client=client))
    return reader, client, rows, now


@pytest.mark.parametrize('tail_status,expected', [('executing', 1), ('completed', 0)])
async def test_workflow_count_includes_tail_beyond_full_first_page(tail_status, expected):
    reader, client, rows, now = workflow_pages(101)
    rows[-1]['status'] = tail_status
    client.fetch_workflows.side_effect = [rows[:100], rows[100:]]
    await reader._work()
    assert reader.workflows == expected
    assert reader.workflows_ts == now
    assert client.fetch_workflows.await_args_list[1].kwargs == {'limit': 100, 'before': rows[99]['createdAt']}


async def test_workflow_pagination_resumes_with_bounded_reads_and_keeps_last_complete_count():
    reader, client, rows, now = workflow_pages(401)
    rows[-1]['status'] = 'executing'
    client.fetch_workflows.side_effect = [rows[i:i + 100] for i in range(0, len(rows), 100)]
    reader.workflows, reader.workflows_ts = 7, now - 60
    await reader._work()
    assert client.fetch_workflows.await_count == 4
    assert (reader.workflows, reader.workflows_ts) == (7, now - 60)
    await reader._work()
    assert client.fetch_workflows.await_count == 5
    assert client.fetch_workflows.await_args.kwargs['before'] == rows[399]['createdAt']
    assert (reader.workflows, reader.workflows_ts) == (1, now)
    # A completed scan must refresh from the newest page on the next poll.
    client.fetch_workflows.side_effect = [rows[:1]]
    await reader._work()
    assert client.fetch_workflows.await_args.kwargs == {'limit': 100}
    assert reader.workflows == 0


async def test_workflow_later_page_failure_retries_cursor_without_certifying_zero():
    reader, client, rows, now = workflow_pages(101)
    client.fetch_workflows.side_effect = [rows[:100], None, rows[100:]]
    await reader._work()
    assert reader.workflows is None
    assert reader.workflows_ts is None
    await reader._work()
    assert client.fetch_workflows.await_args.kwargs['before'] == rows[99]['createdAt']
    assert (reader.workflows, reader.workflows_ts) == (0, now)


@pytest.mark.parametrize('bad_tail', ['duplicate', 'unknown', 'malformed', 'nonadvancing', 'newer_short_page'])
async def test_workflow_tail_cannot_certify_incomplete_or_unknown_count(bad_tail):
    reader, client, rows, now = workflow_pages(201)
    if bad_tail == 'duplicate': rows[100] = rows[0]
    if bad_tail == 'unknown': rows[100]['status'] = 'future-state'
    if bad_tail == 'malformed': rows[100]['id'] = 'bad-id'
    if bad_tail == 'nonadvancing': rows[199]['createdAt'] = rows[99]['createdAt']
    if bad_tail == 'newer_short_page': rows[200]['createdAt'] = rows[0]['createdAt']
    client.fetch_workflows.side_effect = [rows[:100], rows[100:200], rows[200:]]
    await reader._work()
    assert reader.workflows is None
    assert reader.workflows_ts is None


async def test_workflow_multi_poll_timestamp_describes_oldest_observation():
    reader, client, rows, now = workflow_pages(401)
    client.fetch_workflows.side_effect = [rows[i:i + 100] for i in range(0, len(rows), 100)]
    await reader._work()
    reader.manager._clock = lambda: now + 30
    await reader._work()
    assert reader.workflows == 0
    assert reader.workflows_ts == now


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


async def test_unknown_workflow_lifecycle_keeps_last_proven_count_and_timestamp():
    reader, client, rows, now = workflow_pages(101)
    reader.workflows, reader.workflows_ts = 7, now - 60
    rows[-1]['status'] = 'future-state'
    client.fetch_workflows.side_effect = [rows[:100], rows[100:]]
    await reader._work()
    assert (reader.workflows, reader.workflows_ts) == (7, now - 60)
    # An unprovable completed scan must not strand the next poll at its tail.
    client.fetch_workflows.side_effect = [rows[:1]]
    await reader._work()
    assert client.fetch_workflows.await_args.kwargs == {'limit': 100}
    assert (reader.workflows, reader.workflows_ts) == (0, now)
