import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.surf_nft_client import Budget, SurfNftClient
from maxpane_dashboard.data.surf_nft_discovery import (
    SurfNftDiscovery, discovery_candidates, empty_discovery_state,
)
from maxpane_dashboard.data.surf_swarm_client import SwarmClient

FIXTURE=json.loads((Path(__file__).parents[1]/'fixtures/surf/nft/discovery/public.json').read_text())
JOB=FIXTURE['job']['id']
SWORN=json.loads((Path(__file__).parents[1]/'fixtures/surf/nft/discovery/sworn_workflow.json').read_text())


def test_large_project_history_keeps_current_job_and_explicit_links():
    from maxpane_dashboard.data.surf_nft_discovery import _compact
    job = deepcopy(SWORN['job'])
    for version in job['project']['versions']:
        version['objective'] = 'Previous workflow requirements. ' * 180
    fact = _compact(job, 'jobDetails', 100.)
    assert fact is not None
    assert len(json.dumps(fact).encode()) < 32 * 1024
    assert fact['objective'] == job['objective']
    assert fact['launch']['id'] == SWORN['launch']['id']
    assert fact['workflow']['id'] == SWORN['workflow']['id']
    assert [v['jobId'] for v in fact['project']['versions']] == [v['jobId'] for v in job['project']['versions']]
    assert fact['_truncated'] is True


def test_empty_project_has_no_invented_truncation():
    from maxpane_dashboard.data.surf_nft_discovery import _compact
    fact = _compact(dict(id=JOB, objective='Current body', project={}), 'jobDetails', 100.)
    assert fact['project']=={}
    assert not fact.get('_truncated')


def test_exact_workflow_job_launch_link_prioritizes_generic_registry_only():
    state = empty_discovery_state()
    launch = deepcopy(SWORN['launch']); launch.pop('jobs')
    unrelated = dict(launch, id='10000000-0000-4000-8000-000000000099',
                     artifacts=[dict(launch['artifacts'][1], address='0x'+'9'*40)])
    state['raw'].update(launches=[launch, unrelated], workflows=[SWORN['workflow']],
                        jobDetails={SWORN['job']['id']:SWORN['job']})
    candidates = discovery_candidates(state)
    assert candidates['1:0x0da2679000ea5380d1361cc3cca7d4e8c881f766']['nft_intent'] is True
    assert not candidates['1:0x'+'9'*40].get('nft_intent')


async def test_relevant_job_precedes_fifo_backlog_but_background_gets_a_turn():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    state = empty_discovery_state()
    generic = '10000000-0000-4000-8000-000000000099'
    relevant = [f'20000000-0000-4000-8000-{i:012d}' for i in range(5)]
    state['raw']['workflows'] = [dict(SWORN['workflow'], id=identity,
        contractsJobId=identity, frontendJobId=None) for identity in relevant]
    state['pending_jobs'] = {identity:dict(retry_at=0., revision=None) for identity in [generic]+relevant}
    async def read(identity, **_kw):
        return SimpleNamespace(payload=dict(id=identity, objective='generic'), observed_at=100., revision=None, from_cache=False)
    swarm = SimpleNamespace(known_job_revision=lambda _id:None, read_job_detail=AsyncMock(side_effect=read))
    client = SimpleNamespace(can_read_shared_job=lambda:True)
    for _ in range(4):
        discovery = SurfNftDiscovery(client=client, swarm=swarm, clock=lambda:100.)
        result = await discovery.advance(state, budget=budget(), page_limit=0, launch_limit=0, detail_limit=1)
        state = json.loads(json.dumps(result.state))  # Fresh manager / persisted queue every turn.
    ids = [call.args[0] for call in swarm.read_job_detail.await_args_list]
    assert ids[0] in relevant
    assert generic in ids
    assert len(set(ids)) == 4


def setup(handler=None, monotonic=lambda: 1.):
    seen=[]
    def default(request):
        seen.append(str(request.url))
        path=request.url.path
        if handler:
            value=handler(request)
            if value is not None: return value
        if path==f'/jobs/{JOB}': body=FIXTURE['job']
        elif path==f"/jobs/{FIXTURE['continuation']['id']}": body=FIXTURE['continuation']
        elif path.startswith('/launches/'):
            body=FIXTURE['launch'] if path.endswith(FIXTURE['launch']['id']) else dict(FIXTURE['launches']['launches'][1],jobs=[])
        elif path=='/requests/capabilities': body={'chains':[1,4663]}
        else: body=FIXTURE[path[1:]]
        return httpx.Response(200,json=body)
    http=httpx.AsyncClient(transport=httpx.MockTransport(default))
    nft=SurfNftClient(http_client=http,clock=lambda:100.,monotonic=monotonic,inter_call_delay=0)
    swarm=SwarmClient(http_client=http,clock=lambda:77.,monotonic=monotonic,inter_call_delay=0)
    return SurfNftDiscovery(client=nft,swarm=swarm,clock=lambda:100.,monotonic=monotonic),seen,swarm


def budget(n=24):return Budget(http_limit=n,monotonic=lambda:1.)


async def test_head_refresh_catches_up_missing_pages_without_rewinding_history():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from maxpane_dashboard.data.surf_nft_client import Page
    old = dict(FIXTURE['launches']['launches'][0], launchNumber=100)
    new = dict(old, id='10000000-0000-4000-8000-000000000099', launchNumber=300)
    missed = dict(old, id='10000000-0000-4000-8000-000000000098', launchNumber=199)
    state = empty_discovery_state()
    state['sources']['launches'].update(head_at=1., tail_cursor=9, terminal=True,
                                        head_ids=[old['id']])
    client = SimpleNamespace(page=AsyncMock(side_effect=[
        Page([new], 200, False, 1000.), Page([missed, old], 100, False, 1001.)]))
    discovery = SurfNftDiscovery(client=client, swarm=SimpleNamespace(), clock=lambda:1001.)
    first = await discovery.advance(state, budget=budget(), page_limit=1, detail_limit=0, launch_limit=0)
    first.state['rotation'] = 0
    second = await discovery.advance(first.state, budget=budget(), page_limit=1, detail_limit=0, launch_limit=0)
    assert [call.kwargs['cursor'] for call in client.page.await_args_list] == [None, 200]
    assert {new['id'], missed['id'], old['id']} <= {r['id'] for r in second.state['raw']['launches']}
    source = second.state['sources']['launches']
    assert source['tail_cursor'] == 9 and source['terminal'] is True
    assert source['refresh_cursor'] is None
    assert source['head_ids'] == [new['id']]


def test_new_launch_summary_does_not_hide_behind_older_detail():
    state = empty_discovery_state()
    old = deepcopy(FIXTURE['launch'])
    old['updatedAt'] = '2026-10-16T10:00:00Z'
    state['raw']['launchDetails'][old['id']] = old
    fresh = deepcopy(old)
    fresh['updatedAt'] = '2026-10-16T11:00:00Z'
    fresh['artifacts'] = [dict(old['artifacts'][0], address='0x'+'9'*40)]
    discovery = SurfNftDiscovery(client=None, swarm=None, clock=lambda:1001.)
    discovery._ingest(state, 'launches', [fresh], 1001.)
    assert set(discovery_candidates(state)) == {'1:0x'+'9'*40}
    assert old['id'] in state['pending_launches']


async def test_unread_recent_launch_details_precede_periodic_old_refreshes():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from maxpane_dashboard.data.surf_nft_client import SourceRead
    state = empty_discovery_state()
    old = deepcopy(FIXTURE['launch'])
    fresh = dict(old, id='10000000-0000-4000-8000-000000000099', launchNumber=99, jobs=[])
    state['raw']['launches'] = [old, fresh]
    state['raw']['launchDetails'][old['id']] = old
    state['pending_launches'] = {row['id']:{'retry_at':0., 'revision':None} for row in (old, fresh)}
    client = SimpleNamespace(detail=AsyncMock(return_value=SourceRead(fresh, 1000.)))
    discovery = SurfNftDiscovery(client=client, swarm=SimpleNamespace(), clock=lambda:1001.)
    result = await discovery.advance(state, budget=budget(), page_limit=0, detail_limit=0, launch_limit=1)
    assert client.detail.await_args.args == ('launches', fresh['id'])
    assert fresh['id'] in result.state['raw']['launchDetails']
    assert old['id'] in result.state['pending_launches']


def test_candidate_projection_parses_each_job_once_and_refreshes_references(monkeypatch):
    from unittest.mock import Mock
    import maxpane_dashboard.data.surf_nft_rules.catalog as catalog

    ids = [f'00000000-0000-4000-8000-{i:012d}' for i in range(4)]
    commit = 'ab' * 20
    details = {
        ids[0]: {'id': ids[0], 'objective': 'Shared project'},
        ids[1]: {'id': ids[1], 'objective': f'Continue {ids[0]}',
                 'delivery': {'commit': commit}},
        ids[2]: {'id': ids[2], 'objective': 'Shared project',
                 'project': {'versions': [{'baseCommit': commit}]}},
        ids[3]: {'id': ids[3], 'objective': 'Shared project'},
    }
    raw = {'jobDetails': details, 'launches': [
        {'id': 'launch', 'chainId': 1, 'jobs': [{'id': ids[0]}],
         'artifacts': [{'address': '0x' + char * 40} for char in '12']},
    ]}
    pattern = Mock(wraps=catalog.JOB_ID)
    monkeypatch.setattr(catalog, 'JOB_ID', pattern)
    original = deepcopy(raw)
    first = discovery_candidates({'raw': raw})
    assert len(first) == 2
    assert all(candidate['jobIds'] == ids[:3] for candidate in first.values())
    assert raw == original
    assert pattern.findall.call_count == len(details)

    details[ids[1]]['objective'] = 'Shared project'
    details[ids[2]]['project']['versions'][0]['baseCommit'] = 'cd' * 20
    second = discovery_candidates({'raw': raw})
    assert all(candidate['jobIds'] == ids[:1] for candidate in second.values())
    assert pattern.findall.call_count == 2 * len(details)


@pytest.mark.parametrize('template', [[], {}])
async def test_malformed_job_template_retains_other_page_progress(template):
    def handler(request):
        if request.url.path == '/jobs':
            body = deepcopy(FIXTURE['jobs'])
            body['jobs'][0]['template'] = template
            return httpx.Response(200, json=body)
    d, seen, swarm = setup(handler)
    try:
        result = await d.advance(None, budget=budget(), page_limit=2, detail_limit=0, launch_limit=0)
        assert len(seen) == 2
        assert result.state['raw']['launches']
        assert result.state['sources']['jobs']['head_at'] == 100
        assert result.state['truncated']
    finally:
        await swarm.close()


@pytest.mark.parametrize('source,cursor', [('jobs', 'invalid'), ('launches', -1),
    ('workflows', 12), ('publications', '2'), ('search:NFT', '2026-99-99T00:00:00Z')])
async def test_invalid_saved_cursor_restarts_only_its_source(source, cursor):
    from maxpane_dashboard.data.surf_nft_discovery import SOURCES
    d, seen, swarm = setup()
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index(source)
    state['sources'][source].update(head_at=90., tail_cursor=cursor, retry_at=220.)
    state['sources']['sites'].update(head_at=80., terminal=True)
    try:
        result = await d.advance(state, budget=budget(), page_limit=1, detail_limit=0, launch_limit=0)
        assert len(seen) == 1
        assert 'before=' not in seen[0]
        assert result.state['sources'][source]['head_at'] == 100.
        assert result.state['sources'][source]['tail_cursor'] != cursor
        assert result.state['sources']['sites']['head_at'] == 80.
        assert result.state['truncated']
    finally:
        await swarm.close()


@pytest.mark.asyncio
async def test_all_artifacts_distinct_chains_without_nft_name_filter():
    d,seen,swarm=setup()
    r=await d.advance(None,budget=budget(),page_limit=1,detail_limit=0,launch_limit=0)
    assert set(r.candidates)=={'1:0x'+'1'*40,'4663:0x'+'1'*40}
    assert discovery_candidates(r.state)==r.candidates
    assert len(seen)==1
    await swarm.close()


@pytest.mark.asyncio
async def test_shared_detail_original_observation_and_project_continuation():
    d,seen,swarm=setup()
    first=await swarm.read_job_detail(JOB)
    r=await d.advance(None,budget=budget(),page_limit=1)
    assert r.job_facts[JOB]['_observed_at']==first.observed_at==77.
    assert r.job_facts[JOB]['_revision']==first.revision
    assert FIXTURE['continuation']['id'] in r.job_facts
    assert sum('/jobs/'+JOB in u for u in seen)==1
    assert r.state['raw']['jobDetails'][JOB]['project']['versions'][0]['jobId']==FIXTURE['continuation']['id']
    await swarm.close()


@pytest.mark.asyncio
async def test_budget_pause_resumes_pending_details_without_restarting_pages():
    d,seen,swarm=setup()
    r1=await d.advance(None,budget=budget(1),page_limit=1)
    assert r1.state['pending_launches']
    r2=await d.advance(r1.state,budget=budget(10),page_limit=0)
    assert len(r2.job_facts)==2
    assert sum('/launches?' in u for u in seen)==1
    assert not r2.state['pending_launches']
    await swarm.close()


@pytest.mark.asyncio
async def test_failed_page_never_advances_cursor_or_completeness():
    def handler(request):
        if request.url.path=='/launches': return httpx.Response(503)
    d,_,swarm=setup(handler)
    r=await d.advance(None,budget=budget(),page_limit=1)
    source=r.state['sources']['launches']
    assert source['tail_cursor'] is None and source['head_at'] is None
    assert not source['terminal'] and not r.coverage['complete']
    await swarm.close()


@pytest.mark.asyncio
async def test_head_refresh_keeps_independent_history_cursor():
    d,_,swarm=setup()
    d.clock=d.client.clock=lambda:400.
    state=empty_discovery_state()
    state['sources']['launches'].update(head_at=0.,tail_cursor=10,terminal=False,count=100)
    r=await d.advance(state,budget=budget(),page_limit=1,detail_limit=0,launch_limit=0)
    assert r.state['sources']['launches']['tail_cursor']==10
    await swarm.close()


@pytest.mark.asyncio
async def test_publication_total_change_and_duplicate_page_stay_partial():
    d,_,swarm=setup()
    state=empty_discovery_state(); state['rotation']=3
    state['sources']['publications'].update(head_at=90.,tail_cursor=2,provider_total=2,count=1,
                                           recent_ids=[FIXTURE['publications']['items'][0]['id']])
    r=await d.advance(state,budget=budget(),page_limit=1,detail_limit=0,launch_limit=0)
    source=r.state['sources']['publications']
    assert source['tail_cursor']==2 and not source['terminal']
    assert 'repeated_page' in source['warnings']
    assert not r.coverage['complete']
    await swarm.close()


@pytest.mark.asyncio
async def test_names_do_not_create_links_and_eviction_marks_partial():
    d,_,swarm=setup()
    state=empty_discovery_state()
    state['raw']['jobDetails']['90000000-0000-4000-8000-000000000001']={
        'id':'90000000-0000-4000-8000-000000000001','objective':'OrdinaryToken',
        'site':{'url':'https://unrelated.example','status':'published'}}
    r=await d.advance(state,budget=budget(),page_limit=1)
    candidate=next(iter(r.candidates.values()))
    assert '90000000-0000-4000-8000-000000000001' not in candidate['jobIds']
    # Corrupt/oversized persisted evidence is bounded without certifying completeness.
    r.state['raw']['publications']=[{'id':f'publication:{i}','title':'x'} for i in range(2100)]
    bounded=await d.advance(r.state,budget=budget(),page_limit=0,detail_limit=0,launch_limit=0)
    assert len(bounded.state['raw']['publications'])<=2000
    assert bounded.coverage['truncated'] and not bounded.coverage['complete']
    await swarm.close()


@pytest.mark.asyncio
async def test_nft_waiter_cancellation_does_not_cancel_work_consumer():
    entered=asyncio.Event(); release=asyncio.Event(); calls=[]
    async def handler(request):
        calls.append(request.url.path); entered.set(); await release.wait()
        return httpx.Response(200,json=FIXTURE['job'])
    http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    swarm=SwarmClient(http_client=http,inter_call_delay=0,clock=lambda:77.)
    nft=SurfNftClient(http_client=http,inter_call_delay=0)
    d=SurfNftDiscovery(client=nft,swarm=swarm)
    work=asyncio.create_task(swarm.read_job_detail(JOB))
    await entered.wait()
    state=empty_discovery_state(); state['pending_jobs'][JOB]={'retry_at':0,'revision':None}
    started=asyncio.Event()
    original=swarm.read_job_detail
    async def joined(*a,**kw): started.set(); return await original(*a,**kw)
    swarm.read_job_detail=joined
    task=asyncio.create_task(d.advance(state,budget=Budget(),page_limit=0,launch_limit=0))
    await started.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    release.set(); result=await work
    assert result.payload['id']==JOB and calls==['/jobs/'+JOB]
    await swarm.close()


@pytest.mark.asyncio
async def test_changed_list_revision_forces_new_shared_observation():
    revision='2026-10-17T13:00:00.000Z'
    newer=dict(FIXTURE['job'],updatedAt=revision,objective='NFT updated mint conditions')
    updated=False
    def handler(request):
        if request.url.path=='/jobs/'+JOB:
            return httpx.Response(200,json=newer if updated else FIXTURE['job'])
        if request.url.path=='/jobs':
            return httpx.Response(200,json={'jobs':[dict(FIXTURE['jobs']['jobs'][0],updatedAt=revision)]})
    mono=[1.]
    d,seen,swarm=setup(handler, monotonic=lambda:mono[0])
    await swarm.read_job_detail(JOB)
    updated=True
    mono[0]=2.
    state=empty_discovery_state();state['rotation']=1
    r=await d.advance(state,budget=budget(),page_limit=1,launch_limit=0,detail_limit=1)
    assert r.job_facts[JOB]['_revision']==revision
    assert sum('/jobs/'+JOB in u for u in seen)==2
    await swarm.close()


@pytest.mark.asyncio
async def test_deferred_launches_do_not_starve_later_pending_launch():
    d,_,swarm=setup()
    state=empty_discovery_state()
    for i in range(4):
        state['pending_launches'][f'70000000-0000-4000-8000-{i:012d}']={'retry_at':200.,'revision':None}
    state['pending_launches'][FIXTURE['launch']['id']]={'retry_at':0.,'revision':None}
    r=await d.advance(state,budget=budget(),page_limit=0,launch_limit=1,detail_limit=0)
    assert FIXTURE['launch']['id'] in r.state['raw']['launchDetails']
    await swarm.close()


@pytest.mark.asyncio
async def test_malformed_nested_links_never_crash_or_join_unknown_identity():
    d,_,swarm=setup()
    state=empty_discovery_state()
    malformed=deepcopy(FIXTURE['job'])
    malformed['project']['versions']=[{'jobId':['bad'],'baseCommit':{}}, {'jobId':FIXTURE['continuation']['id']}]
    malformed['launch']={'chainId':True}
    malformed['site']={'id':[],'url':{},'status':'published'}
    state['raw']['jobDetails'][JOB]=malformed
    state['raw']['publications']=[dict(FIXTURE['publications']['items'][0],versions=[{'jobId':JOB,'repoUrl':[]}])]
    state['raw']['workflows']=[dict(FIXTURE['workflows']['workflows'][0],contractsJobId={})]
    r=await d.advance(state,budget=budget(),page_limit=1,launch_limit=0,detail_limit=0)
    assert r.job_facts[JOB]['launch']['chainId'] is None
    assert r.coverage['truncated']
    await swarm.close()


@pytest.mark.asyncio
async def test_shared_cache_hit_refunds_two_host_admission_credit():
    d,_,swarm=setup()
    await swarm.read_job_detail(JOB)
    state=empty_discovery_state();state['pending_jobs'][JOB]={'retry_at':0.,'revision':None}
    b=budget(2)
    result=await d.advance(state,budget=b,page_limit=0,launch_limit=0,detail_limit=1)
    assert result.job_facts[JOB]['id']==JOB
    assert b.reserved_http==0 and b.http_attempts==0
    await swarm.close()


@pytest.mark.asyncio
async def test_head_observation_does_not_renew_unrelated_job_fact():
    d,_,swarm=setup()
    state=empty_discovery_state()
    state['raw']['jobDetails'][JOB]=dict(FIXTURE['job'],_observed_at=50.,_revision='old')
    r=await d.advance(state,budget=budget(),page_limit=1,detail_limit=0,launch_limit=0)
    assert r.state['observed_at']==100. and r.job_facts[JOB]['_observed_at']==50.
    assert not r.coverage['truncated']
    await swarm.close()


@pytest.mark.asyncio
async def test_explicit_workflow_relationship_queues_non_nft_site_job():
    d,_,swarm=setup()
    state=empty_discovery_state()
    state['raw']['jobDetails'][JOB]=dict(FIXTURE['job'],project={},_observed_at=100.)
    state['raw']['workflows']=[dict(FIXTURE['workflows']['workflows'][0],objective='Website')]
    r=await d.advance(state,budget=budget(),page_limit=0,detail_limit=0,launch_limit=0)
    assert FIXTURE['continuation']['id'] in r.state['pending_jobs']
    await swarm.close()


def test_future_fact_does_not_discard_other_observations():
    from maxpane_dashboard.data.surf_nft_discovery import validate_discovery_state
    state=empty_discovery_state(); state['observed_at']=100.
    state['raw']['jobDetails']={JOB:dict(FIXTURE['job'],_observed_at=77.),
                               FIXTURE['continuation']['id']:dict(FIXTURE['continuation'],_observed_at=101.)}
    state['pending_jobs'][JOB]={'retry_at':220.,'revision':None}
    result=validate_discovery_state(state,100.)
    assert set(result['raw']['jobDetails'])=={JOB}
    assert result['raw']['jobDetails'][JOB]['_observed_at']==77.
    assert result['pending_jobs'][JOB]['retry_at']==220.
    assert result['truncated']
