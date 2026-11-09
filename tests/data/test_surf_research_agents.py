"""Research agents come from running assignments, not submitted node seats."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from maxpane_dashboard.data.surf_swarm import _ts
from maxpane_dashboard.data.surf_swarm_client import SwarmClient


@pytest.fixture
def setup():
    raw = json.loads(Path('tests/fixtures/surf/work/research_workers.json').read_text())
    now = max(_ts(p['at']) for p in raw['standings'].values())
    for row in raw['standings'].values(): row['at'] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    raw['roster']['at'] = int(now * 1000)
    client = SimpleNamespace(fetch_oracle_requests=AsyncMock(return_value=raw['requests']),
        fetch_overview=AsyncMock(side_effect=lambda: deepcopy(raw['roster'])),
        fetch_seat_standing=AsyncMock(side_effect=lambda seat: deepcopy(raw['standings'][str(seat)])))
    clock = [now]
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: clock[0], swarm_client=client))
    return reader, raw, client, clock


async def test_submitted_research_node_still_counts_its_running_seat(setup):
    reader, raw, client, clock = setup
    await reader._research()
    facts = reader.current_work({})
    assert facts['research']['count'] == 1
    assert facts['oracle_agents'] == 1
    assert 'Current node coverage incomplete' in facts['reason']
    assert {call.args[0] for call in client.fetch_seat_standing.await_args_list} == {1548, 143}
    assert client.fetch_overview.await_count == 2
    clock[0] += 61
    assert reader.current_work({})['oracle_agents'] is None


async def test_same_seat_multiple_assignments_counts_once(setup):
    reader, raw, client, clock = setup
    raw['standings']['1548']['standing']['working'] = 2
    raw['standings']['1548']['standing']['running'] *= 2
    await reader._research()
    assert reader.current_work({})['oracle_agents'] == 1


@pytest.mark.parametrize('failure', ['roster_missing','seat_identity','working','old_roster',
    'standing_missing','identity','truncated','bad_job','old_standing','roster_changed'])
async def test_incomplete_roster_never_claims_an_agent_count(setup, failure):
    reader, raw, client, clock = setup
    if failure == 'roster_missing': client.fetch_overview.side_effect = lambda: None
    if failure == 'seat_identity': raw['roster']['seats']['1548']['tokenId'] = 143
    if failure == 'working': raw['roster']['seats']['1548']['working'] = None
    if failure == 'old_roster': raw['roster']['at'] = 0
    if failure == 'standing_missing': client.fetch_seat_standing.side_effect = lambda _: None
    if failure == 'identity': raw['standings']['1548']['tokenId'] = '143'
    if failure == 'truncated': raw['standings']['1548']['standing']['running'] = []
    if failure == 'bad_job': raw['standings']['1548']['standing']['running'][0]['jobId'] = 'invalid'
    if failure == 'old_standing': raw['standings']['1548']['at'] = '2000-01-01T00:00:00Z'
    if failure == 'roster_changed':
        changed = deepcopy(raw['roster']); changed['seats']['1322']['working'] = True
        client.fetch_overview.side_effect = [raw['roster'], changed]
    await reader._research()
    assert reader.current_work({})['oracle_agents'] is None
    assert reader.current_work({})['research']['count'] == 1


async def test_large_roster_resumes_with_a_bounded_budget_and_oldest_source_clock(setup):
    reader, raw, client, clock = setup
    start = clock[0]
    raw['roster']['seats'] = {str(i):dict(raw['roster']['seats']['1548'], tokenId=i) for i in range(81)}
    raw['standings'] = {str(i):dict(deepcopy(raw['standings']['1548' if i == 80 else '143']), tokenId=str(i)) for i in range(81)}
    for round in range(3):
        raw['roster']['at'] = int(clock[0] * 1000)
        for row in raw['standings'].values(): row['at'] = datetime.fromtimestamp(clock[0], timezone.utc).isoformat()
        await reader._research()
        if round < 2:
            assert reader.current_work({})['oracle_agents'] is None
            clock[0] += 90
    assert client.fetch_seat_standing.await_count == 96
    facts = reader.current_work({})
    assert facts['oracle_agents'] == 1
    assert facts['research']['read_ts'] == start


async def test_idle_standing_overrides_older_busy_flag(setup):
    reader, raw, client, clock = setup
    raw['standings']['1548']['standing'].update(working=0, running=[])
    await reader._research()
    assert reader.current_work({})['oracle_agents'] == 0


async def test_no_active_request_is_a_real_zero_and_needs_no_worker_fanout(setup):
    reader, raw, client, clock = setup
    client.fetch_oracle_requests.return_value = []
    await reader._research()
    assert reader.current_work({})['oracle_agents'] == 0
    client.fetch_overview.assert_not_awaited()


async def test_unrelated_running_work_is_not_a_research_agent(setup):
    reader, raw, client, clock = setup
    raw['standings']['1548']['standing']['running'] = deepcopy(raw['standings']['143']['standing']['running'])
    await reader._research()
    assert reader.current_work({})['oracle_agents'] == 0


async def test_research_budget_allows_bounded_standings_without_changing_other_reads(setup, monkeypatch):
    from contextlib import asynccontextmanager
    budgets = []
    @asynccontextmanager
    async def deadline(seconds):
        budgets.append(seconds)
        yield
    monkeypatch.setattr(asyncio, 'timeout', deadline)
    await setup[0]._guard(AsyncMock(), 'research')
    await setup[0]._guard(AsyncMock(), 'current')
    assert budgets == [30, 12]


async def test_research_card_paints_count_and_uses_its_own_observation_time(setup):
    from maxpane_dashboard.data.surfboard import cards
    from maxpane_dashboard.widgets.fmt import hhmm
    from tests.widgets.test_surfboard_rack import RackApp, SurfboardCard, card_strips
    reader, raw, client, clock = setup
    await reader._research()
    facts = reader.current_work({})
    row = next(row for row in cards({}, {}, now=clock[0], current_work=facts) if row['key'] == 'oracles')
    assert 'agents read ' + hhmm(clock[0]) in row['detail']
    async with RackApp().run_test(size=(149,45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-oracles', SurfboardCard)
        card.set_data(row)
        await pilot.pause()
        painted = '\n'.join(strip.text for strip in card_strips(pilot.app, card))
        assert '1 agents' in painted and 'RESEARCH' in painted


async def test_cancelled_standing_read_cannot_retain_previous_agent_count(setup):
    reader, raw, client, clock = setup
    await reader._research()
    clock[0] += 61
    raw['roster']['at'] = int(clock[0] * 1000)
    client.fetch_seat_standing.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError): await reader._research()
    assert reader.current_work({})['oracle_agents'] is None


async def test_standing_budget_reuses_only_matching_requests_with_original_clock(setup):
    reader, raw, client, clock = setup
    await reader._research()
    original = reader.current_work({})['research']['read_ts']
    clock[0] += 30
    await reader._research()
    assert client.fetch_seat_standing.await_count == 2
    assert reader.current_work({})['oracle_agents'] == 1
    assert reader.current_work({})['research']['read_ts'] == original
    # Another request cannot inherit the cached total or bypass the standing budget.
    raw['requests'][0]['jobId'] = 'aaaaaaaa-aaaa-4aaa-8aaa-000000000001'
    await reader._research()
    assert reader.current_work({})['oracle_agents'] is None
    assert client.fetch_seat_standing.await_count == 2


async def test_failed_standing_read_does_not_retry_inside_its_budget(setup):
    reader, raw, client, clock = setup
    client.fetch_seat_standing.side_effect = lambda _: None
    await reader._research()
    clock[0] += 30
    await reader._research()
    assert client.fetch_seat_standing.await_count == 2
    assert reader.current_work({})['oracle_agents'] is None


async def test_failed_refresh_removes_that_seats_previous_assignment(setup):
    reader, raw, client, clock = setup
    await reader._research()
    clock[0] += 61
    raw['roster']['at'] = int(clock[0] * 1000)
    client.fetch_seat_standing.side_effect = lambda _: None
    await reader._research()
    assert reader.current_work({})['oracle_agents'] is None


async def test_recent_request_poll_cannot_extend_expired_agent_observations(setup):
    reader, raw, client, clock = setup
    await reader._research()
    clock[0] += 301
    reader._research_agents_next = clock[0] + 60
    await reader._research()
    assert reader.current_work({})['research']['count'] == 1
    assert reader.current_work({})['oracle_agents'] is None


async def test_standing_route_uses_validated_seat_and_skips_queue_work():
    calls = []
    response = json.loads(Path('tests/fixtures/surf/work/research_workers.json').read_text())['standings']['1548']
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: (calls.append(request) or httpx.Response(200, json=response)))) as http:
        client = SwarmClient(http_client=http, base_url='https://example.invalid', inter_call_delay=0)
        assert await client.fetch_seat_standing(1548) == response
        for value in ('1548/other', True, -1): assert await client.fetch_seat_standing(value) is None
        assert len(calls) == 1
        assert calls[0].url.path == '/seats/1548/standing'
        assert calls[0].url.params['queue'] == '0'
