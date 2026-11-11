"""Launch and report counts use verified job identities, never global subtraction."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from maxpane_dashboard.data.surf_swarm_client import JobDetailRead
from maxpane_dashboard.data.surfboard import cards


@pytest.fixture
def setup():
    raw = json.loads(Path('tests/fixtures/surf/work/boardroom_job_categories.json').read_text())
    jobs = {row['label']: deepcopy(row['job']) for row in raw['rows']}
    now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc).timestamp()
    client = SimpleNamespace(_monotonic=lambda: now, fetch_jobs=AsyncMock())
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: now, swarm_client=client))
    source = dict(state='ok', read_ts=now, payload=dict(overview=dict(job_states={})))

    async def load(labels):
        chosen = [dict(jobs[label], state='executing') for label in labels]
        client.fetch_jobs.return_value = chosen
        client.read_job_detail = AsyncMock(side_effect=lambda key, **kw:
            JobDetailRead(next(row for row in chosen if row['id'] == key), now, now, None, False))
        source['payload']['overview']['job_states']['executing'] = len(chosen)
        await reader._current()
        return reader.current_work(source)

    return reader, jobs, source, client, now, load


async def test_reports_and_oracles_are_research_while_site_is_not_a_launch(setup):
    reader, jobs, source, client, now, load = setup
    facts = await load(['goal', 'goal-old', 'oracle', 'site'])
    groups = facts['job_groups']
    assert groups['launch']['count'] == 0
    assert groups['research']['count'] == 3
    assert reader.work_snapshot(source)['summary']['jobs'] == 0
    assert groups['launch']['agents'] == 0
    assert groups['research']['agents'] is None  # no complete standing read yet


@pytest.mark.parametrize('label,category', [('goal','research'), ('report','research'),
    ('oracle','research'), ('launch-contracts','launch'), ('launch-project','launch'),
    ('workflow-frontend','launch')])
async def test_explicit_job_families_and_terminal_exclusion(setup, label, category):
    reader, jobs, source, client, now, load = setup
    facts = await load([label])
    assert facts['job_groups'][category]['count'] == 1
    row = dict(jobs[label], state='completed')
    client.fetch_jobs.return_value = [row]
    client.read_job_detail.return_value = JobDetailRead(row, now, now, None, False)
    client.read_job_detail.side_effect = None
    source['payload']['overview']['job_states']['executing'] = 0
    await reader._current()
    assert reader.current_work(source)['job_groups'][category]['count'] == 0


@pytest.mark.parametrize('failure', ['missing_job', 'unclassified', 'failed_detail', 'stale_overview'])
async def test_incomplete_category_coverage_cannot_prove_zero_launches(setup, failure):
    reader, jobs, source, client, now, load = setup
    await load(['goal'])
    if failure == 'missing_job': source['payload']['overview']['job_states']['executing'] = 2
    if failure == 'unclassified': reader.current_jobs[jobs['goal']['id']]['family'] = None
    if failure == 'failed_detail': reader.current_failed = True
    if failure == 'stale_overview': source['read_ts'] -= 61
    groups = reader.current_work(source)['job_groups']
    assert groups['launch']['count'] is None
    assert groups['research']['count'] is None
    assert reader.work_snapshot(source)['summary']['jobs'] is None


@pytest.mark.parametrize('mixed', [False, True])
async def test_complete_standings_scope_and_deduplicate_each_category(setup, mixed):
    reader, jobs, source, client, now, load = setup
    await load(['goal', 'oracle', 'launch-contracts', 'site'])
    # Synthetic response bodies live in the fixture; mutations stay explicit.
    scenario = json.loads(Path('tests/fixtures/surf/work/boardroom_job_categories.json').read_text())['assignment_scenario']
    standings = scenario['standings']
    if mixed:
        standings['7']['standing']['running'] += deepcopy(standings['9']['standing']['running'])
        standings['7']['standing']['working'] += 1
    client.fetch_overview = AsyncMock(return_value=scenario['roster'])
    client.fetch_seat_standing = AsyncMock(side_effect=lambda token: deepcopy(standings[str(token)]))
    await reader._research_agents([dict(job_id=jobs['oracle']['id'])])
    facts = reader.current_work(source)
    assert facts['job_groups']['research']['agents'] == 2
    assert facts['job_groups']['launch']['agents'] == 1 + mixed
    data = dict(surf_work=reader.work_snapshot(source), surfboard_overview=dict(working_seats=4))
    rows = {r['key']:r for r in cards(data, {}, now=now, current_work=facts)}
    assert (rows['work']['primary'],rows['work']['secondary']) == ('1',f'{1 + mixed} working')
    assert (rows['oracles']['primary'],rows['oracles']['secondary']) == ('2','2 agents')
    assert rows['board']['secondary'] == '4 working'
    client.fetch_overview.return_value = None
    await reader._research_agents([dict(job_id=jobs['oracle']['id'])])
    assert reader.current_work(source)['job_groups']['research']['agents'] is None


async def test_launch_agents_are_read_even_without_oracle_requests(setup):
    reader, jobs, source, client, now, load = setup
    await load(['launch-contracts'])
    client.fetch_oracle_requests = AsyncMock(return_value=[])
    reader._research_agents = AsyncMock(return_value=(0, now))
    await reader._research()
    reader._research_agents.assert_awaited_once_with([])


async def test_a_job_created_after_standing_observation_cannot_inherit_zero_agents(setup):
    reader, jobs, source, client, now, load = setup
    await load(['goal'])
    reader.current_jobs[jobs['goal']['id']]['created_ts'] = now - 5
    reader._busy_assignments = ({7:{jobs['oracle']['id']}}, now - 10)
    assert reader.current_work(source)['job_groups']['research']['agents'] is None
    reader._busy_assignments = ({7:{jobs['oracle']['id']}}, now)
    assert reader.current_work(source)['job_groups']['research']['agents'] == 0


async def test_category_counts_and_status_are_painted_on_the_cards(setup):
    from tests.widgets.test_surfboard_rack import RackApp, SurfboardCard, card_strips
    reader, jobs, source, client, now, load = setup
    facts = await load(['goal', 'goal-old', 'oracle', 'site'])
    data = dict(surf_work=reader.work_snapshot(source))
    rows = {r['key']:r for r in cards(data, {}, now=now, current_work=facts)}
    async with RackApp().run_test(size=(149,45)) as pilot:
        for key, caption in [('work','0 working'), ('oracles','0 agents')]:
            card = pilot.app.query_one('#surfboard-card-' + key, SurfboardCard)
            card.set_data(rows[key])
            await pilot.pause()
            painted = '\n'.join(s.text for s in card_strips(pilot.app, card))
            assert caption in painted
        assert rows['work']['primary'] == '0' and rows['work']['status'] == 'idle'
        assert rows['oracles']['primary'] == '3' and rows['oracles']['status'] == 'assessing'
