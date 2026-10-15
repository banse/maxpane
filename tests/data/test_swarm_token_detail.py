"""Selected-token enrichment: fixture-only authoritative joins and owned tasks."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager
from maxpane_dashboard.data.swarm_token_detail_models import (
    ARTIFACT_KEYS, CONTRIBUTOR_KEYS, LAUNCH_KEYS, SNAPSHOT_KEYS, SOURCE_KEYS, SOURCE_NAMES,
)

FIXTURES = Path(__file__).parents[1] / 'fixtures/surf'


def evidence():
    """Connect existing captured jobs to captured Slabs for an offline join graph."""
    launch = json.loads((FIXTURES / 'swarm/v9/launch_791.json').read_text())
    graph = json.loads((FIXTURES / 'launch_contribution/captured.json').read_text())
    jobs = graph['jobs']
    original = '2ff472e8-1453-414f-81ab-eb2702dbeece'
    contract = launch['jobs'][0]['id']
    jobs[contract] = jobs.pop(original)
    jobs[contract]['id'] = contract
    workflow = next(iter(graph['workflows'].values()))
    workflow['contracts']['id'] = contract
    workflow['launch']['id'] = launch['id']
    frontend = workflow['frontend']['id']
    sites = [dict(jobId=frontend, label='slabs', ensName='slabs.sites.imd.fun',
                  status='named', supersededBy=None, namedAt='2026-10-12T20:11:00Z')]
    return launch, jobs, graph['workflows'], sites


class Client:
    def __init__(self):
        self.launch, self.jobs, self.workflows, self.sites = evidence()
        self.calls = []
        self.closed = False

    async def fetch_launch_jobs(self, identity):
        self.calls.append(('launch', identity))
        return deepcopy(self.launch)

    async def fetch_job(self, identity):
        self.calls.append(('job', identity))
        return deepcopy(self.jobs.get(identity))

    async def fetch_workflow(self, identity):
        self.calls.append(('workflow', identity))
        return deepcopy(self.workflows.get(identity))

    async def fetch_sites(self):
        self.calls.append(('sites', None))
        return deepcopy(self.sites)

    async def close(self):
        self.closed = True


class Overview:
    is_mock = False

    def __init__(self, client=None):
        self.client = client or Client()
        launch = self.client.launch
        contract = next(a['address'] for a in launch['artifacts'] if a['role'] == 'token')
        self.token = dict(id=f"4663:{contract}", chain_id=4663, token_address=contract,
                          launch_uuid=launch['id'], launch_id=791, symbol='SLABS', name='Slabs',
                          market_state='ok', market_read_at=1000, price_usd=1.25,
                          history_state='ok', history_read_at=1000, sparkline=[1, 2, 3],
                          liquidity_state='ok', liquidity_read_at=1000, paired_amount=12,
                          verdict='swarm', status='live')
        self.selected_calls = []
        self.closed = False

    async def fetch_selected_token(self, identity, *, launch_uuid=None):
        self.selected_calls.append((identity, launch_uuid))
        return deepcopy(self.token)

    async def close(self):
        self.closed = True


async def ready(manager):
    await manager.fetch_and_compute()
    await manager.wait_pending()
    return await manager.fetch_and_compute()


async def test_seed_is_immediate_then_authoritative_jobs_sites_and_contract():
    overview = Overview()
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    seed = await manager.fetch_and_compute()
    assert seed['token']['price_usd'] == 1.25
    assert seed['contributors'] is None
    assert seed['sources']['contributors']['state'] == 'pending'
    await manager.wait_pending()
    result = await manager.fetch_and_compute()
    assert tuple(result) == SNAPSHOT_KEYS
    assert tuple(result['launch']) == LAUNCH_KEYS
    assert tuple(result['sources']) == SOURCE_NAMES
    assert all(tuple(row) == SOURCE_KEYS for row in result['sources'].values())
    assert result['launch']['number'] == 791
    assert result['launch']['objective'].startswith('A custom token: Slabs')
    assert result['launch']['site_label'] == 'slabs'
    assert len(result['contributors']) == 10
    assert {row['stage'] for row in result['contributors']} == {'contracts', 'frontend'}
    assert {row['role'] for row in result['contributors']} == {'build', 'review', 'integrate', 'tests'}
    assert all(tuple(row) == CONTRIBUTOR_KEYS for row in result['contributors'])
    assert all(tuple(row) == ARTIFACT_KEYS for row in result['artifacts'])
    assert {row['kind'] for row in result['artifacts']} == {'token', 'contract', 'site'}
    assert all(row['state'] == 'ok' for row in result['sources'].values())
    assert overview.selected_calls[0] == (overview.token['id'], overview.token['launch_uuid'])
    await manager.close()
    assert not overview.closed and not overview.client.closed


@pytest.mark.parametrize('change', ['id', 'chain', 'token'])
async def test_launch_identity_mismatch_never_fetches_jobs(change):
    overview = Overview()
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    if change == 'id':
        overview.client.launch['id'] = '00000000-0000-0000-0000-000000000000'
    elif change == 'chain':
        overview.client.launch['chainId'] = 1
    else:
        overview.client.launch['artifacts'] = []
    result = await ready(manager)
    assert result['launch'] is None and result['contributors'] is None
    assert result['sources']['launch']['state'] == 'unavailable'
    assert not any(kind == 'job' for kind, _ in overview.client.calls)
    await manager.close()


async def test_workflow_mismatch_keeps_contract_seats_partial_and_excludes_frontend_site():
    overview = Overview()
    workflow = next(iter(overview.client.workflows.values()))
    workflow['launch']['id'] = '00000000-0000-0000-0000-000000000000'
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    result = await ready(manager)
    assert len(result['contributors']) == 8
    assert result['sources']['contributors']['state'] == 'partial'
    assert result['sources']['artifacts']['state'] == 'partial'
    assert result['launch']['site_label'] is None
    assert all(row['stage'] == 'contracts' for row in result['contributors'])
    await manager.close()


async def test_partial_coverage_survives_age_and_failure_until_complete_refresh():
    overview, now = Overview(), [1000]
    workflow = next(iter(overview.client.workflows.values()))
    workflow['launch']['id'] = '00000000-0000-0000-0000-000000000000'
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: now[0])
    original = await ready(manager)
    assert original['sources']['contributors']['partial'] is True
    launch = overview.client.launch
    overview.client.launch = None
    now[0] += manager.TTL
    aged = await manager.fetch_and_compute()
    await manager.wait_pending()
    failed = await manager.fetch_and_compute()
    for result in (aged, failed):
        assert result['contributors'] == original['contributors']
        assert result['sources']['contributors'] == dict(state='stale', read_ts=1000, partial=True)
        assert result['sources']['artifacts']['partial'] is True
    overview.client.launch = launch
    workflow['launch']['id'] = launch['id']
    now[0] += manager.TTL
    recovered = await ready(manager)
    assert len(recovered['contributors']) == 10
    assert recovered['sources']['contributors'] == dict(state='ok', read_ts=now[0], partial=False)
    await manager.close()


async def test_only_accepted_nonoracle_seats_deduplicate_per_role_and_job():
    overview = Overview()
    job = overview.client.jobs[overview.client.launch['jobs'][0]['id']]
    original = job['nodes'][0]
    job['nodes'] += [dict(original, key='duplicate_review'),
                     dict(original, key='oracle_assess', seat={'tokenId': '9999'}),
                     dict(original, key='rejected_review', state='rejected', seat={'tokenId': '9998'})]
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    result = await ready(manager)
    assert len(result['contributors']) == 10
    assert all(row['seat'] not in (9999, 9998) for row in result['contributors'])
    await manager.close()


async def test_missing_job_is_unknown_not_zero_and_failure_retains_original_source_clock():
    overview, now = Overview(), [1000]
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: now[0])
    original = await ready(manager)
    overview.client.jobs = {}
    now[0] += manager.TTL
    pending = await manager.fetch_and_compute()
    assert pending['sources']['contributors']['state'] == 'stale'
    await manager.wait_pending()
    retained = await manager.fetch_and_compute()
    assert retained['contributors'] == original['contributors']
    assert retained['sources']['contributors'] == {'state': 'stale', 'read_ts': 1000, 'partial': False}
    assert retained['sources']['launch']['state'] == 'ok'
    await manager.close()
    cold = SwarmTokenDetailManager(overview, overview.token, clock=lambda: now[0])
    result = await ready(cold)
    assert result['contributors'] is None
    assert result['sources']['contributors']['state'] == 'unavailable'
    await cold.close()


async def test_disappeared_or_different_selected_identity_retains_stale_token():
    overview = Overview()
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    overview.token = dict(overview.token, id='1:another', price_usd=999)
    result = await manager.fetch_and_compute()
    assert result['token']['price_usd'] == 1.25
    assert result['token']['market_state'] == 'stale'
    assert result['token']['history_state'] == 'stale'
    await manager.close()


async def test_mock_never_constructs_a_network_client_or_invents_an_artifact():
    manager = SwarmTokenDetailManager(SimpleNamespace(is_mock=True),
                                     {'id': 'demo', 'symbol': 'DEMO'}, clock=lambda: 1000)
    result = await ready(manager)
    assert result['is_mock'] is True
    assert result['contributors'] is None and result['artifacts'] is None
    assert all(value['state'] == 'unavailable' for value in result['sources'].values())
    await manager.close()


async def test_close_cancels_owned_pending_read_and_does_not_close_borrowed_client():
    overview = Overview()
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked(_):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    overview.client.fetch_launch_jobs = blocked
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    await manager.fetch_and_compute()
    await started.wait()
    await asyncio.wait_for(manager.close(), .2)
    assert cancelled.is_set()
    assert not overview.client.closed and not overview.closed
    await manager.fetch_and_compute()
    assert len(overview.selected_calls) == 1


async def test_overview_selected_seam_only_enriches_identity_without_changing_overview_mode():
    from maxpane_dashboard.data.surf_swarm import launch_rows
    from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
    from tests.data.test_swarm_tokens_live import Market, Pages, Source, rows

    class SelectedMarket(Market):
        def __init__(self):
            self.calls = []

        async def fetch_markets(self, tokens):
            self.calls.append([token['id'] for token in tokens])
            return {}

    source, market = Source(launch_rows(rows())), SelectedMarket()
    manager = SwarmTokensManager(source, client=Pages(), market=market, clock=lambda: 1000)
    manager._catalogue, manager._complete = rows(), True
    manager._cat_as_of = manager._cat_attempt = 1000
    candidates = manager._tokens(source.data, 1000)
    selected = candidates[-1]
    result = await manager.fetch_selected_token(selected['id'], launch_uuid=selected['launch_uuid'])
    assert result['id'] == selected['id']
    await manager.wait_pending()
    assert market.calls == [[selected['id']]]
    assert manager._portfolio_active is False
    assert await manager.fetch_selected_token('missing') is None
    assert await manager.fetch_selected_token(selected['id'], launch_uuid='different') is None
    assert market.calls == [[selected['id']]]
    await manager.close()


@pytest.mark.parametrize('jobs,expected,state', [([], [], 'ok'), (None, None, 'unavailable')])
async def test_empty_jobs_differ_from_unread_jobs(jobs, expected, state):
    overview = Overview()
    overview.client.launch['jobs'] = jobs
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    result = await ready(manager)
    assert result['contributors'] == expected
    assert result['sources']['contributors']['state'] == state
    await manager.close()


async def test_site_name_is_not_a_join_and_superseded_site_is_excluded():
    overview = Overview()
    site = overview.client.sites[0]
    overview.client.sites = [dict(site, jobId=str(UUID(int=999))),
                             dict(site, supersededBy='replacement'),
                             dict(site, status='failed')]
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    result = await ready(manager)
    assert not any(row['kind'] == 'site' for row in result['artifacts'])
    assert result['launch']['site_ens_name'] is None
    await manager.close()


async def test_sites_failure_retains_artifacts_but_does_not_stale_launch_or_contributors():
    overview, now = Overview(), [1000]
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: now[0])
    original = await ready(manager)
    overview.client.sites = None
    now[0] += manager.TTL
    result = await ready(manager)
    assert result['artifacts'] == original['artifacts']
    assert result['sources']['artifacts'] == {'state': 'stale', 'read_ts': 1000, 'partial': False}
    assert result['sources']['launch'] == {'state': 'ok', 'read_ts': now[0], 'partial': False}
    assert result['sources']['contributors'] == {'state': 'ok', 'read_ts': now[0], 'partial': False}
    await manager.close()


async def test_job_fanout_is_bounded_and_truncated_evidence_is_partial():
    overview = Overview()
    source_job = deepcopy(overview.client.jobs[overview.client.launch['jobs'][0]['id']])
    identities = [str(UUID(int=index + 1)) for index in range(16)]
    overview.client.launch['jobs'] = [{'id': identity} for identity in identities]
    entered, release = asyncio.Event(), asyncio.Event()
    active, maximum, calls = 0, 0, []

    async def job(identity):
        nonlocal active, maximum
        calls.append(identity)
        active += 1
        maximum = max(maximum, active)
        if active == SwarmTokenDetailManager.CONCURRENCY:
            entered.set()
        try:
            await release.wait()
            return dict(source_job, id=identity, workflow=None)
        finally:
            active -= 1

    overview.client.fetch_job = job
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    await manager.fetch_and_compute()
    await entered.wait()
    assert maximum == manager.CONCURRENCY
    release.set()
    await manager.wait_pending()
    result = await manager.fetch_and_compute()
    assert len(calls) == manager.MAX_JOBS
    assert maximum == manager.CONCURRENCY
    assert result['sources']['contributors']['state'] == 'partial'
    assert {row['job_id'] for row in result['contributors']} == set(identities[:manager.MAX_JOBS])
    await manager.close()


async def test_launch_artifacts_are_bounded_with_partial_coverage():
    overview = Overview()
    overview.client.launch['artifacts'] += [dict(role='helper', name=f'Helper {index}',
                                                 address=f'0x{index + 1:040x}') for index in range(130)]
    overview.client.sites = []
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    result = await ready(manager)
    assert len(result['artifacts']) == manager.MAX_ARTIFACTS
    assert result['sources']['artifacts']['state'] == 'partial'
    await manager.close()
