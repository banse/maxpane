"""NFT orchestration stays passive on navigation and drains owned work."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_nft_manager import SurfNftManager


class Cache:
    def __init__(self, state=None):
        self.state = state or {'records': None, 'discovery': {}, 'evidence': {},
                               'progress': {}, 'child_candidates': {}}
        self.saves = 0

    def load(self):
        return deepcopy(self.state)

    def save(self, state, **_kw):
        self.state = deepcopy(state)
        self.saves += 1
        return True


@pytest.fixture
def setup(monkeypatch):
    now = SimpleNamespace(value=1000.)
    client = SimpleNamespace(close=AsyncMock())
    swarm = SimpleNamespace(close=AsyncMock())
    cache = Cache()
    manager = SurfNftManager(swarm=swarm, client=client, cache=cache,
                            clock=lambda: now.value, monotonic=lambda: now.value)
    entered, release = asyncio.Event(), asyncio.Event()
    async def advance(state, **_kw):
        entered.set()
        await release.wait()
        return SimpleNamespace(state={'raw': {}, 'sources': {'launches': {'head_at': now.value},
                                   'jobs': {'head_at': now.value}}, 'observed_at': now.value},
                               candidates={}, job_facts={}, coverage={'complete': True})
    manager.discovery.advance = AsyncMock(side_effect=advance)
    return manager, now, entered, release, client, swarm, cache


async def test_cold_fetch_returns_before_blocked_read_and_passive_snapshot_starts_nothing(setup):
    manager, now, entered, release, client, swarm, cache = setup
    try:
        initial = manager.get_snapshot()
        assert initial['nft_rows'] is None
        assert not manager.is_loading()
        await manager.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        first = manager._task
        for _ in range(10):
            manager.select(None)
            manager.get_snapshot()
            manager.catalogue_summary()
        assert manager._task is first
        assert manager.discovery.advance.await_count == 1
        now.value += 5
        release.set()
        await manager.wait_pending()
        assert not manager.is_loading()
        assert manager.get_snapshot()['nft_rows'] == []
        assert cache.state['discovery']['observed_at'] == 1005
        manager.get_snapshot()
        assert cache.state['discovery']['observed_at'] == 1005
    finally:
        await manager.close()


async def test_repeated_offers_join_and_close_does_not_close_borrowed_clients(setup):
    manager, now, entered, release, client, swarm, cache = setup
    await manager.fetch_and_compute()
    await asyncio.wait_for(entered.wait(), 1)
    original = manager._task
    for _ in range(4):
        manager.offer_hub()
        await manager.fetch_and_compute()
    assert manager._task is original
    await manager.close()
    assert original.done()
    assert not manager.is_loading()
    client.close.assert_not_awaited()
    swarm.close.assert_not_awaited()
    manager.offer_hub()
    assert manager._task is original


async def test_failure_retains_last_good_inventory_and_original_clock(setup):
    manager, now, entered, release, client, swarm, cache = setup
    release.set()
    await manager.fetch_and_compute()
    await manager.wait_pending()
    previous = manager.get_snapshot()
    now.value += 300
    manager.discovery.advance = AsyncMock(side_effect=ValueError('invalid source'))
    await manager.fetch_and_compute()
    await manager.wait_pending()
    assert manager.get_snapshot()['nft_rows'] == previous['nft_rows']
    assert manager.state['discovery']['observed_at'] == 1000
    await manager.close()


async def test_owned_client_closed_after_tasks_drain(monkeypatch, tmp_path):
    client = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr('maxpane_dashboard.data.surf_nft_manager.SurfNftClient', lambda **_kw: client)
    manager = SurfNftManager(swarm=SimpleNamespace(), cache_path=tmp_path / 'nft.json',
                            clock=lambda: 1000, monotonic=lambda: 1000)
    await manager.close()
    client.close.assert_awaited_once()


async def test_boardroom_discovery_also_advances_one_launch_detail(setup):
    manager, now, entered, release, *_ = setup
    release.set()
    try:
        await manager._cycle(proof_only=True)
        limits = manager.discovery.advance.await_args_list[0].kwargs
        assert limits['page_limit'] == 1
        assert limits['launch_limit'] == 1
        assert limits['detail_limit'] == 1  # Bounded job-to-launch relationship needed for proof discovery.
        assert manager.last_budget.http_attempts <= 12
    finally:
        await manager.close()


def test_manager_retains_hidden_identity_for_screen_projection_and_card_totals(setup):
    import json
    from pathlib import Path
    from maxpane_dashboard.analytics.surf_nft import normalize_record, project_snapshot
    manager, *_ = setup
    source = json.loads((Path(__file__).parents[1]/'fixtures/surf/nft/projection.json').read_text())['records'][0]
    hidden = normalize_record(source)
    hidden.update(name='Same Collection')
    hidden['stats']['totalMinted'] = 10
    hidden['deployment'].update(deployer='0x'+'ab'*20,
        request_job_ids=['20000000-0000-4000-8000-000000000001'])
    representative = deepcopy(hidden)
    representative.update(id='1:0x'+'f'*40, contract='0x'+'f'*40)
    representative['stats']['totalMinted'] = 20
    manager.state['records'] = [hidden,representative]
    original = deepcopy(manager.state['records'])
    delivered = manager.get_snapshot()
    assert manager.catalogue_summary()['deployed'] == 1
    assert len(delivered['nft_rows']) == 2  # Reader retains identities for local screen filters.
    rendered = project_snapshot(delivered, filters={'search':hidden['contract']})
    assert rendered['nft_selected']['id'] == hidden['id']
    assert [row['id']for row in rendered['nft_rows']] == [hidden['id']]
    manager.select(hidden['id'])
    assert manager.get_snapshot()['nft_selected']['id'] == hidden['id']
    delivered['nft_rows'][0]['stats']['totalMinted'] = 999
    assert manager.state['records'] == original


async def test_legacy_proof_refresh_adds_origin_without_renewing_detail_clock(setup):
    manager, *_ = setup
    identity = '1:0x'+'a'*40
    candidate = {'chainId':1, 'address':identity[2:], 'artifact':{}, 'launch':{}}
    previous = dict(chainId=1, address=identity[2:], checkedAt=900., codeHash='0x'+'b'*64,
                    deploymentConfirmed=True, codePresent=True, standard='ERC-721',
                    deployment={'timestamp':800.}, stats={'totalMinted':10})
    previous['_proof_revision'] = manager._proof_revision(candidate, previous)
    manager.state['evidence'][identity] = deepcopy(previous)
    assert manager._proof_changed(identity, candidate)
    assert not manager._proof_current(identity, candidate)
    fresh = dict(previous, checkedAt=1000., proofOnly=True,
                 deployment={'timestamp':800., 'deployer':'0x'+'c'*40})
    manager.inspector.advance = AsyncMock(return_value=SimpleNamespace(
        evidence=fresh, progress=None, complete=True, children=[]))
    from maxpane_dashboard.data.surf_nft_client import Budget
    try:
        await manager._inspect(identity, candidate, Budget(), proof_only=True)
        result = manager.state['evidence'][identity]
        assert result['deployment']['deployer'] == '0x'+'c'*40
        assert result['checkedAt'] == 900.
        assert result['stats'] == {'totalMinted':10}
        assert manager._proof_current(identity, candidate)
    finally:
        await manager.close()


def test_projection_origin_uses_direct_launch_jobs_not_transitive_links(setup, monkeypatch):
    import maxpane_dashboard.data.surf_nft_manager as module
    manager, *_ = setup
    import json
    from pathlib import Path
    row = json.loads((Path(__file__).parents[1]/'fixtures/surf/nft/projection.json').read_text())['records'][0]
    identity = row['id']
    direct = '20000000-0000-4000-8000-000000000001'
    indirect = '30000000-0000-4000-8000-000000000001'
    row['jobs'] = [{'id':direct},{'id':indirect}]
    manager.state['discovery'] = dict(observed_at=900., raw={})
    manager._candidates = lambda:{identity:{'launch':{'jobs':[{'id':direct}]}}}
    monkeypatch.setattr(module, 'project_catalog', lambda *_a,**_k:{'collections':[row],'coverage':{'complete':False}})
    manager._publish()
    assert manager.state['records'][0]['deployment']['request_job_ids'] == [direct]


async def test_new_head_collection_reaches_snapshot_through_real_discovery_and_chain_reader(tmp_path):
    """Bounded offline wire replay covers API head -> receipt proof -> published row."""
    import httpx
    from maxpane_dashboard.data.surf_nft_client import SurfNftClient
    from maxpane_dashboard.data.surf_swarm_client import SwarmClient
    from tests.data.test_surf_nft_discovery import FIXTURE
    from tests.data.test_surf_rpc_budget_r2_nft import Wire, ADDRESS, TX, NOW
    launch = deepcopy(FIXTURE['launch'])
    launch['artifacts'] = [dict(launch['artifacts'][0], name='NewCollectionNFT', address=ADDRESS, txHash=TX)]
    launch['jobs'] = []
    wire = Wire()
    def handler(request):
        if request.method == 'POST':
            return wire(request)
        path = request.url.path
        if path == '/launches':
            value = {'launches':[launch]}
        elif path.startswith('/launches/'):
            value = launch
        elif path == '/publications':
            value = {'items':[], 'count':0, 'totalPages':0}
        elif path in ('/jobs','/workflows','/sites'):
            value = {path[1:]:[]}
        else:
            value = {}
        return httpx.Response(200, json=value)
    now = [NOW]
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = SurfNftClient(http_client=http, inter_call_delay=0, clock=lambda:now[0], monotonic=lambda:1.)
    swarm = SwarmClient(http_client=http, inter_call_delay=0, clock=lambda:now[0], monotonic=lambda:1.)
    manager = SurfNftManager(client=client, swarm=swarm, cache_path=tmp_path/'nft.json',
                             clock=lambda:now[0], monotonic=lambda:1.)
    try:
        assert manager.get_snapshot()['nft_rows'] is None
        for _ in range(4):
            await manager._cycle(proof_only=True)
            assert manager.last_budget.http_attempts <= 12
            if manager.get_snapshot()['nft_rows']:
                break
            now[0] += 30
        rows = manager.get_snapshot()['nft_rows']
        assert [(row['id'],row['name'])for row in rows] == [(f'1:{ADDRESS}', 'NewCollectionNFT')]
        assert rows[0]['deployment']['receiptSuccess'] is True
        assert rows[0]['sources']['chain']['observed_at'] >= NOW
        assert manager._error_count == 0
    finally:
        await manager.close()
        await http.aclose()


async def test_workflow_registry_crosses_large_backlog_and_cache_reopen_with_wire_budget(tmp_path):
    """Captured public relationship graph; synthetic pinned chain wire, never live I/O."""
    import httpx
    from maxpane_dashboard.data.surf_nft_cache import SurfNftCache
    from maxpane_dashboard.data.surf_nft_client import SurfNftClient
    from maxpane_dashboard.data.surf_nft_discovery import empty_discovery_state
    from maxpane_dashboard.data.surf_swarm_client import SwarmClient
    from tests.data.test_surf_nft_discovery import SWORN
    from tests.data.test_surf_rpc_budget_r2_nft import Wire
    from tests.data.test_surf_nft_chain import word
    now = [1792716000.]
    launch = deepcopy(SWORN['launch'])
    target = next(a for a in launch['artifacts'] if a['name']=='Registry')
    identity = '1:'+target['address']
    job = deepcopy(SWORN['job'])
    for version in job['project']['versions']:
        version['objective'] = 'Repeated earlier workflow requirements. ' * 180
    generic = [dict(id=f'90000000-0000-4000-8000-{i:012d}', chainId=1,
        launchNumber=3000+i, status='live', artifacts=[dict(name='Token', address='0x'+f'{i+1:040x}')])
        for i in range(400)]
    sources = {row['id']:row for row in generic+[launch]}
    class RegistryWire(Wire):
        def value(self, method, params):
            if method=='eth_blockNumber': return hex(target['blockNumber']+100)
            if method=='eth_getTransactionReceipt':
                return dict(status='0x1', transactionHash=params[0], blockNumber=hex(target['blockNumber']),
                            contractAddress=None, **{'from':'0x'+'ab'*20})
            if method=='eth_call' and params[0]['to'] != target['address']:
                return word(0)
            return super().value(method, params)
    wire = RegistryWire(); reads=[]
    def handler(request):
        reads.append(str(request.url))
        if request.method=='POST': return wire(request)
        path=request.url.path
        if path.startswith('/launches/'): value=sources[path.rsplit('/',1)[-1]]
        elif path==f"/jobs/{job['id']}": value=job
        elif path.startswith('/jobs/'):
            value=dict(id=path.rsplit('/',1)[-1], objective='Unrelated work')
        else: raise AssertionError(f'Unexpected wire read: {request.url}')
        return httpx.Response(200,json=value)
    http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client=SurfNftClient(http_client=http,clock=lambda:now[0],monotonic=lambda:1.,inter_call_delay=0)
    swarm=SwarmClient(http_client=http,clock=lambda:now[0],monotonic=lambda:1.,inter_call_delay=0)
    state=empty_discovery_state(); state['observed_at']=now[0]
    for source in state['sources'].values(): source.update(head_at=now[0],terminal=True)
    state['raw'].update(launches=generic+[dict(launch,jobs=[])], workflows=[SWORN['workflow']])
    state['pending_launches']={row['id']:dict(retry_at=0.,revision=None) for row in generic+[launch]}
    state['pending_jobs']={row['id']:dict(retry_at=0.,revision=None) for row in generic}
    state['pending_jobs'][job['id']]=dict(retry_at=0.,revision=None)
    cache=SurfNftCache(path=tmp_path/'nft.json',clock=lambda:now[0]); cache.save(dict(discovery=state))
    snapshots=[]
    try:
        for _ in range(6):
            manager=SurfNftManager(client=client,swarm=swarm,cache=cache,
                clock=lambda:now[0],monotonic=lambda:1.)
            await manager._cycle(proof_only=True)
            assert manager.last_budget.http_attempts<=12 and manager.last_budget.rpc_calls<=96
            snapshots.append(manager.get_snapshot())
            assert manager._error_count==0
            await manager.close()  # Real atomic cache round-trip between every bounded cycle.
            if any(row['id']==identity for row in snapshots[-1]['nft_rows'] or []): break
            now[0]+=30
        rows=snapshots[-1]['nft_rows'] or []
        record=next(row for row in rows if row['id']==identity)
        assert record['standard']=='ERC-721'
        assert record['deployment']['receiptSuccess'] is True
        assert any(f"/jobs/{job['id']}" in url for url in reads)
        assert any(f"/launches/{launch['id']}" in url for url in reads)
        assert any('90000000-' in url for url in reads)  # Generic lane also progresses.
    finally:
        await http.aclose()


async def test_bounded_cycles_resume_pinned_inspection_and_publish_real_catalog(tmp_path):
    from tests.data.test_surf_nft_chain import AsyncReads, ADDRESS, TX
    from maxpane_dashboard.data.surf_nft_cache import SurfNftCache
    now = SimpleNamespace(value=1792200000.)
    client = AsyncReads()
    manager = SurfNftManager(swarm=SimpleNamespace(), client=client,
        cache_path=tmp_path / 'nft.json', clock=lambda: now.value, monotonic=lambda: 10.)
    launch_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    artifact = dict(address=ADDRESS, name='Observed NFT', txHash=TX, blockNumber=144)
    launch = dict(id=launch_id, chainId=1, launchNumber=1, status='live', artifacts=[artifact], jobs=[])
    raw = dict(launches=[launch], launchDetails={launch_id: launch}, jobDetails={},
               workflows=[], publications=[], sites={'sites': []}, coverage={'complete': False})
    async def advance(state, **_kw):
        return SimpleNamespace(state=dict(raw=deepcopy(raw), sources={}, observed_at=1792200000.),
                               candidates={}, job_facts={}, coverage={'complete': False})
    manager.discovery.advance = advance
    identity = f'1:{ADDRESS}'
    manager.select(identity)
    try:
        # Selected work gets only six sends, but resumes rather than restarts.
        previous = 0
        for cycle in range(20):
            await manager.fetch_and_compute()
            await manager.wait_pending()
            assert manager.last_budget.http_attempts <= 24
            stage = manager.state['progress'].get(identity)
            if stage is None:
                break
            assert stage['completed_operations'] > previous
            previous = stage['completed_operations']
            now.value += 30
        assert identity in manager.state['evidence']
        assert identity not in manager.state['progress']
        assert [r['id'] for r in manager.get_snapshot()['nft_rows']] == [identity]
        assert len(client.sent) == len(set(client.sent))
        loaded = SurfNftCache(path=tmp_path / 'nft.json', clock=lambda: now.value).load()
        assert loaded['evidence'][identity]['readTimestamp'] == manager.state['evidence'][identity]['readTimestamp']
        assert loaded['records'][0]['contract'] == ADDRESS
    finally:
        await manager.close()


async def test_selection_change_during_read_does_not_relabel_late_result(setup):
    manager, now, entered, release, client, swarm, cache = setup
    a, b = ('1:0x' + char * 40 for char in 'ab')
    candidate = {'chainId': 1, 'address': '0x'+'a'*40, 'artifact': {}, 'launch': {}}
    manager._candidates = lambda: {a: candidate}
    release.set()
    started, finish = asyncio.Event(), asyncio.Event()
    async def inspect(_candidate, progress, *, budget):
        started.set()
        await finish.wait()
        return SimpleNamespace(progress={}, children=[], complete=True,
            evidence={'chainId': 1, 'address': '0x'+'a'*40, 'checkedAt': 1000,
                      'standard': None, 'detectionStatus': 'unsupported'})
    manager.inspector.advance = inspect
    manager._publish = lambda: None
    manager.select(a)
    try:
        await manager.fetch_and_compute()
        await asyncio.wait_for(started.wait(), 1)
        manager.select(b)
        finish.set()
        await manager.wait_pending()
        assert a in manager.state['evidence']
        assert b not in manager.state['evidence']
        assert manager._selected == b
    finally:
        await manager.close()


async def test_cold_unselected_chain_work_precedes_slow_job_backfill(setup):
    manager, now, entered, release, client, swarm, cache = setup
    identity = '1:0x' + 'a' * 40
    candidate = {'chainId': 1, 'address': '0x'+'a'*40, 'artifact': {}, 'launch': {}}
    manager._candidates = lambda: {identity: candidate}
    calls = []
    async def discovery(state, *, budget, detail_limit, **_kw):
        calls.append('details' if detail_limit else 'page')
        if detail_limit:
            now.value += 16  # Time-consuming job response exhausts cycle deadline.
        return SimpleNamespace(state={}, coverage={'complete': False})
    async def inspect(_candidate, progress, *, budget, proof_only=False):
        calls.append('chain')
        budget.consume(http=1, rpc=1)
        return SimpleNamespace(progress={'started_at': now.value, 'completed_operations':
                                         (progress or {}).get('completed_operations', 0) + 1}, evidence=None,
                               children=[], complete=False)
    manager.discovery.advance = discovery
    manager.inspector.advance = inspect
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert calls[0:2] == ['page', 'chain']
        assert calls[-1] == 'details'
        assert identity in manager.state['progress']
    finally:
        await manager.close()


async def test_selected_enrichment_and_slow_backfill_do_not_starve_other_collections(setup):
    manager, now, entered, release, client, swarm, cache = setup
    candidates = {f'1:0x{char * 40}': {'chainId': 1, 'address': '0x' + char * 40}
                  for char in 'abc'}
    manager._candidates = lambda: candidates
    selected = next(iter(candidates))
    manager.select(selected)
    seen = set()

    async def discovery(state, *, budget, detail_limit, **_kw):
        if detail_limit:
            now.value += 16  # Slow job details used to consume the whole deadline.
        return SimpleNamespace(state={}, coverage={'complete': False})

    async def inspect(candidate, progress, *, budget, proof_only=False):
        identity = f"1:{candidate['address']}"
        seen.add(identity)
        budget.consume(http=1, rpc=1)
        return SimpleNamespace(progress={'started_at': now.value, 'completed_operations':
                                         (progress or {}).get('completed_operations', 0) + 1}, children=[],
            complete=identity != selected,
            evidence={'chainId': 1, 'address': candidate['address'],
                      'checkedAt': now.value, 'detectionStatus': 'unsupported'})

    manager.discovery.advance = discovery
    manager.inspector.advance = inspect
    manager._publish = lambda: None
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert seen == set(candidates)
        assert manager.last_budget.http_attempts <= 24
    finally:
        await manager.close()


def test_first_proofs_precede_known_collection_details(setup, monkeypatch):
    manager, *_ = setup
    selected, known, unseen, ordinary = [f'1:0x{char * 40}' for char in 'abcd']
    candidates = dict.fromkeys((selected, known, unseen, ordinary), {})
    monkeypatch.setattr('maxpane_dashboard.data.surf_nft_manager.RULES', {known: {}, unseen: {}})
    manager.state['progress'][known] = {'started_at': 1000.}
    manager.state['evidence'][known] = {'checkedAt': 1000., 'standard': 'ERC-721', 'proofOnly': True}
    manager.select(selected)
    assert [key for key, _ in manager._pending(candidates)] == [selected, unseen, known, ordinary]


def test_unseen_nft_launches_precede_generic_contracts_without_excluding_them(setup):
    manager, now, *_ = setup
    generic, older, newer = [f'1:0x{char * 40}' for char in 'abc']
    candidates = {
        generic: {'launch': {'launchNumber': 50, 'jobs': [{'objective': 'Deploy an ERC20 token'}]}},
        older: {'launch': {'launchNumber': 10, 'jobs': [{'objective': 'Build an ERC-721 collection'}]}},
        newer: {'launch': {'launchNumber': 20, 'jobs': [{'objective': 'Build an ERC-1155 collection'}]}},
    }
    assert manager._focus(candidates, probe=True) == newer
    assert [key for key, _ in manager._pending(candidates)] == [newer, older, generic]
    # A description changes priority, never establishes that a contract is an NFT.
    assert manager.get_snapshot()['nft_rows'] is None
    for key in (older, newer):
        manager.state['evidence'][key] = dict(checkedAt=now.value, detectionStatus='unsupported')
    assert manager._focus(candidates, probe=True) == generic


def test_linked_nft_priority_and_generic_turn_survive_manager_reopen(tmp_path):
    from maxpane_dashboard.data.surf_nft_cache import SurfNftCache
    cache = SurfNftCache(path=tmp_path/'nft.json', clock=lambda:1000.)
    generic = '1:0x'+'1'*40
    priority = ['1:0x'+f'{i:040x}' for i in range(2, 8)]
    candidates = {generic:dict(launch={'launchNumber':1}, artifact={'name':'Registry'})}
    candidates.update({key:dict(launch={'launchNumber':100+i}, artifact={'name':'Registry'},
                                nft_intent=True) for i,key in enumerate(priority)})
    chosen = []
    for _ in range(4):
        manager = SurfNftManager(swarm=object(), client=object(), cache=cache, clock=lambda:1000.)
        identity = manager._focus(candidates, probe=True)
        chosen.append(identity)
        manager.state['evidence'][identity] = dict(chainId=1, address=identity[2:],
            detectionStatus='unsupported', checkedAt=1000.)
        cache.save(manager.state)
    assert chosen[0] == priority[-1]
    assert chosen[3] == generic
    assert len(set(chosen)) == 4


def test_probe_resumes_unexpired_stage_after_reopen_before_newer_candidates(setup):
    manager, now, *_ = setup
    previous, newer = ['1:0x'+c*40 for c in 'ab']
    candidates = {previous:dict(launch={'launchNumber':1}),
                  newer:dict(launch={'launchNumber':2}, nft_intent=True)}
    manager.state['progress'][previous] = dict(started_at=now.value-30, completed_operations=3)
    assert manager._focus(candidates, probe=True) == previous


async def test_new_verified_metadata_gets_bounded_slice_without_resetting_factory_focus(setup):
    from maxpane_dashboard.data.surf_nft_rules.children import FACTORIES
    manager, now, _, _, client, swarm, cache = setup
    factory = f"{FACTORIES[0]['chainId']}:{FACTORIES[0]['factory']}"
    address = '0x'+'9'*40; identity='1:'+address
    launch=dict(id='20000000-0000-4000-8000-000000000001', chainId=1, launchNumber=2404,
                status='live', artifacts=[dict(address=address, name='Registry')], jobs=[])
    candidates={factory:dict(chainId=1,address=factory[2:],launch={},launchIds=[],jobIds=[],artifact={}), identity:dict(
        chainId=1,address=address,artifact=launch['artifacts'][0],launch=launch,launchIds=[launch['id']],jobIds=[])}
    manager._candidates=lambda:candidates
    manager.state['discovery']=dict(observed_at=now.value,raw=dict(launches=[launch],coverage={'complete':False}))
    manager._discover=AsyncMock()
    manager._inspection_focus[False]=(factory,now.value-30)
    manager.state['progress'][factory]=dict(started_at=now.value-30,completed_operations=10)
    manager.state['evidence'][identity]=dict(chainId=1,address=address,standard='ERC-721',
        proofOnly=True,deploymentConfirmed=True,codePresent=True,receiptSuccess=True,
        checkedAt=now.value-10,deployment={},reads={})
    manager.state['progress'][identity]=dict(started_at=now.value-10,completed_operations=10)
    seen=[]
    async def inspect(candidate,progress,*,budget,proof_only=False):
        key=f"1:{candidate['address']}";seen.append((key,budget.remaining_http))
        budget.consume(http=2,rpc=2)
        if key==factory:
            return SimpleNamespace(complete=False,children=[],evidence=None,
                progress=dict(progress,completed_operations=progress['completed_operations']+2))
        if progress['completed_operations']<12:
            return SimpleNamespace(complete=False,children=[],evidence=None,
                progress=dict(progress,completed_operations=12))
        return SimpleNamespace(complete=True,children=[],progress={},evidence=dict(
            manager.state['evidence'][identity],proofOnly=False,name='Sworn',symbol='SWORN',
            reads={'name':'Sworn','symbol':'SWORN'},checkedAt=now.value))
    manager.inspector.advance=inspect
    await manager._cycle()
    assert seen[0]==(identity,3)
    assert factory in [key for key,_ in seen]
    assert manager.state['progress'][factory]['started_at']==now.value-30
    assert manager.state['progress'][factory]['completed_operations']>10
    assert manager.state['progress'][identity]['completed_operations']==12
    # Reopen using persisted evidence/stages; the factory still receives work.
    now.value+=30
    manager=SurfNftManager(client=client,swarm=swarm,cache=cache,
        clock=lambda:now.value,monotonic=lambda:now.value)
    manager._candidates=lambda:candidates
    manager._discover=AsyncMock()
    manager.inspector.advance=inspect
    await manager._cycle()
    assert manager.state['progress'][factory]['started_at']==now.value-60
    assert manager.state['progress'][factory]['completed_operations']>=14
    record=next(row for row in manager.get_snapshot()['nft_rows'] if row['id']==identity)
    assert (record['name'],record['symbol'])==('Sworn','SWORN')
    assert manager.last_budget.http_attempts<=24


@pytest.mark.parametrize('kind', ['registry', 'constructor'])
async def test_reviewed_factory_receives_child_discovery_instead_of_proof_only(setup, kind):
    from maxpane_dashboard.data.surf_nft_rules.children import FACTORIES
    from maxpane_dashboard.data.surf_nft_rules.references import SEASONS
    manager, now, *_ = setup
    config = FACTORIES[0] if kind == 'registry' else dict(chainId=4663, factory=SEASONS['hook'])
    key = f"{config['chainId']}:{config['factory']}"
    candidate = dict(chainId=config['chainId'], address=config['factory'], launch={})
    manager._candidates = lambda: {key: candidate}
    manager.state['evidence'][key] = dict(checkedAt=now.value - 121,
        detectionStatus='unsupported', standard=None)
    seen = []
    async def discover(state, **kwargs):
        return SimpleNamespace(state={}, coverage={'complete': False})
    async def inspect(_candidate, progress, *, budget, proof_only=False):
        seen.append(proof_only)
        budget.consume(http=1, rpc=1)
        return SimpleNamespace(progress={}, children=[], complete=True,
            evidence=dict(chainId=config['chainId'], address=config['factory'],
                          checkedAt=now.value, detectionStatus='unsupported'))
    manager.discovery.advance = discover
    manager.inspector.advance = inspect
    manager._publish = lambda: None
    try:
        await manager._cycle()
        assert seen == [False]
    finally:
        await manager.close()


def test_retained_factory_scan_is_prioritized_after_restart(setup):
    from maxpane_dashboard.data.surf_nft_rules.children import FACTORIES
    manager, now, *_ = setup
    factory = f"{FACTORIES[0]['chainId']}:{FACTORIES[0]['factory']}"
    known = '1:0x' + 'a' * 40
    manager.state['evidence'] = {
        factory: dict(checkedAt=now.value, standard=None, detectionStatus='unsupported'),
        known: dict(checkedAt=900, standard='ERC-721', proofOnly=True),
    }
    manager.state['progress'][factory] = dict(started_at=now.value - 60, completed_operations=7)
    assert manager._focus({known: {}, factory: {}}) == factory


async def test_discovered_child_is_inspected_before_waiting_for_negative_probe_ttl(setup):
    manager, now, *_ = setup
    child, generic = [f'1:0x{char * 40}' for char in 'ab']
    candidate = dict(chainId=1, address=child[2:], artifact={'name': 'LoomCollection'})
    manager.state['child_candidates'][child] = candidate
    manager.state['evidence'][child] = dict(chainId=1, address=child[2:],
        checkedAt=now.value, inspectionComplete=False, factoryCreationVerified=True)
    manager._candidates = lambda: {generic: {}, child: candidate}
    seen = []
    async def discover(state, **kwargs):
        return SimpleNamespace(state={}, coverage={'complete': False})
    async def inspect(candidate, progress, *, budget, proof_only=False):
        seen.append((candidate.get('address'), proof_only))
        budget.consume(http=1, rpc=1)
        return SimpleNamespace(progress={}, children=[], complete=True,
            evidence=dict(chainId=1, address=candidate.get('address'),
                          checkedAt=now.value, detectionStatus='unsupported'))
    manager.discovery.advance = discover
    manager.inspector.advance = inspect
    manager._publish = lambda: None
    try:
        await manager._cycle()
        assert (child[2:], False) in seen
        # A completed negative still backs off; child origin alone admits no row.
        assert not manager._due(child)
        assert manager.get_snapshot()['nft_rows'] is None
    finally:
        await manager.close()


async def test_linked_job_detail_has_budget_even_with_selected_and_background_reads(setup):
    manager, now, *_ = setup
    selected, background = [f'1:0x{char * 40}' for char in 'ab']
    candidates = {key: {'chainId': 1, 'address': key[2:]} for key in (selected, background)}
    manager._candidates = lambda: candidates
    manager.select(selected)
    manager.state['evidence'][background] = dict(standard='ERC-721', proofOnly=True)
    progress = []
    async def discover(state, *, budget, page_limit, launch_limit, detail_limit, checkpoint=None):
        for _ in range(page_limit + launch_limit):
            if budget.can_admit():
                budget.consume(http=1)
        if detail_limit and budget.can_admit(http=2):
            budget.reserve_shared_job()
            progress.append('job detail read')
        return SimpleNamespace(state={}, coverage={'complete': False})
    async def inspect(_candidate, stage, *, budget, proof_only=False):
        while budget.can_admit():
            budget.consume(http=1, rpc=1)
        return SimpleNamespace(progress={'started_at': now.value,
            'completed_operations': (stage or {}).get('completed_operations', 0) + 1},
            evidence=None, children=[], complete=False)
    manager.discovery.advance = discover
    manager.inspector.advance = inspect
    manager._publish = lambda: None
    try:
        await manager._cycle()
        assert progress == ['job detail read']
        assert manager.last_budget.http_attempts + manager.last_budget.reserved_http <= 24
    finally:
        await manager.close()


async def test_background_inspection_leaves_time_for_reserved_job_detail(setup):
    manager, now, *_ = setup
    identity = '1:0x' + 'a' * 40
    manager._candidates = lambda: {identity: {'chainId': 1, 'address': identity[2:]}}
    manager.state['evidence'][identity] = dict(standard='ERC-721', proofOnly=True)
    reads = []
    async def discover(state, *, budget, detail_limit, **_kw):
        if detail_limit and budget.can_admit(http=2):
            reads.append(budget.remaining_seconds)
            budget.reserve_shared_job()
        return SimpleNamespace(state={}, coverage={'complete': False})
    async def inspect(candidate, stage, *, budget, **_kw):
        budget.consume(http=1)
        now.value += budget.remaining_seconds  # the read reaches its admitted deadline
        return SimpleNamespace(progress={'started_at': 1000., 'completed_operations': 1},
                               evidence=None, children=[], complete=False)
    manager.discovery.advance = discover
    manager.inspector.advance = inspect
    manager._publish = lambda: None
    try:
        await manager._cycle()
        assert reads and reads[0] >= 2
    finally:
        await manager.close()


@pytest.mark.parametrize('failed_method,retain', [('eth_getCode', True),
    ('eth_getTransactionReceipt', True), ('empty-code', False), ('reverted-receipt', False),
    ('partial-stage', True)])
async def test_incomplete_chain_refresh_keeps_proven_collection_and_clock(setup, failed_method, retain):
    from tests.data.test_surf_nft_chain import ADDRESS, TX, FakeRPC, Inspector
    from maxpane_dashboard.data.surf_nft_client import Budget
    manager, *_ = setup
    identity = f'1:{ADDRESS}'
    candidate = dict(chainId=1, address=ADDRESS, artifact=dict(name='Known', txHash=TX),
        launch=dict(id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', chainId=1), launchIds=[], jobIds=[])
    rpc = FakeRPC()
    good = Inspector(rpc=rpc, fetch_json=lambda _: {}).inspect_contract(1, ADDRESS, TX)
    good['checkedAt'] = 900
    manager._candidates = lambda: {identity: candidate}
    manager.state.update(discovery=dict(observed_at=900, raw={'coverage': {'complete': False}},
                                       sources={'launches': {'head_at': 900}}),
                         evidence={identity: good})
    manager._publish()
    assert manager.get_snapshot()['nft_summary']['deployed'] == 1
    def failing(chain, method, params):
        if method == failed_method:
            raise OSError('RPC read failed')
        if failed_method == 'empty-code' and method == 'eth_getCode':
            return '0x'
        if failed_method == 'reverted-receipt' and method == 'eth_getTransactionReceipt':
            return dict(rpc(chain, method, params), status='0x0')
        return rpc(chain, method, params)
    failed = Inspector(rpc=failing, fetch_json=lambda _: {}).inspect_contract(1, ADDRESS, TX)
    if failed_method == 'partial-stage':
        failed.update(proofOnly=True, inspectionComplete=False)
    assert failed['detectionStatus'] == 'confirmed'
    assert failed['deploymentConfirmed'] is (failed_method == 'partial-stage')
    manager.inspector.advance = AsyncMock(return_value=SimpleNamespace(
        evidence=failed, complete=True, progress={}, children=[]))
    try:
        await manager._inspect(identity, candidate, Budget(monotonic=lambda: 1))
        manager._publish()
        assert manager.get_snapshot()['nft_summary']['deployed'] == int(retain)
        if retain:
            assert manager.state['evidence'][identity] == good
            assert manager.get_snapshot()['nft_rows'][0]['sources']['chain']['observed_at'] == 900
    finally:
        await manager.close()


async def test_new_runtime_checkpoint_invalidates_previous_rule_interpretation(setup):
    manager, *_ = setup
    identity = '1:0x' + 'a' * 40
    previous = dict(chainId=1, address='0x' + 'a' * 40, codeHash='0x' + '1' * 64,
                    detectionStatus='confirmed', codePresent=True, receiptSuccess=True,
                    deploymentConfirmed=True, reads={'mintPrice()': 0}, checkedAt=900)
    fresh = dict(previous, codeHash='0x' + '2' * 64, proofOnly=True,
                 inspectionComplete=False, reads={}, checkedAt=1000)
    manager.state['evidence'][identity] = previous
    try:
        manager._retain_evidence(identity, fresh)
        assert manager.state['evidence'][identity] == fresh
    finally:
        await manager.close()


def seed_reviewed_collection(manager):
    from tests.data.test_surf_nft_rules import MintRulesTest
    evidence = MintRulesTest().evidence(1416, {'totalMinted': 2},
        standard='ERC-721', detectionStatus='confirmed', receiptSuccess=True,
        deploymentConfirmed=True, checkedAt=900)
    identity = f"{evidence['chainId']}:{evidence['address']}"
    candidate = dict(chainId=evidence['chainId'], address=evidence['address'],
        artifact={'name': 'Reviewed collection'}, launchIds=[], jobIds=[],
        launch=dict(id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', chainId=evidence['chainId']))
    manager._candidates = lambda: {identity: candidate}
    manager.state.update(discovery=dict(observed_at=900, raw={'coverage': {'complete': False}},
                                       sources={'launches': {'head_at': 900}}),
                         evidence={identity: evidence})
    manager._publish()
    assert manager.get_snapshot()['nft_rows'][0]['mint']['state'] == 'open'
    return identity, candidate, deepcopy(evidence)


@pytest.mark.parametrize('receipt_available', [True, False])
@pytest.mark.parametrize('record_only', [True, False])
async def test_changed_runtime_invalidates_mint_even_when_receipt_read_fails(setup, receipt_available, record_only):
    from maxpane_dashboard.data.surf_nft_client import Budget
    manager, *_ = setup
    identity, candidate, previous = seed_reviewed_collection(manager)
    if record_only:
        manager.state['evidence'].clear()
    fresh = dict(previous, codeHash='0x' + '99' * 32, reads={}, checkedAt=1000,
                 proofOnly=True, inspectionComplete=False,
                 receiptSuccess=True if receipt_available else None,
                 deploymentConfirmed=receipt_available)
    manager.inspector.advance = AsyncMock(return_value=SimpleNamespace(
        evidence=fresh, complete=False, progress={'started_at': 1000}, children=[]))
    try:
        await manager._inspect(identity, candidate, Budget(monotonic=lambda: 1))
        manager._publish()
        assert manager.state['evidence'][identity] == fresh
        snapshot = manager.get_snapshot()
        assert snapshot['nft_summary']['mint_open'] in (None, 0)
        assert snapshot['nft_summary']['idmd_free'] in (None, 0)
        for row in snapshot['nft_rows']:
            assert row['code_hash'] == fresh['codeHash']
            assert row['rule_review'].get('status') != 'matched'
    finally:
        await manager.close()


@pytest.mark.parametrize('record_only', [True, False])
async def test_parent_rediscovery_keeps_proven_child_and_enrichment_due(setup, record_only):
    from maxpane_dashboard.data.surf_nft_client import Budget
    manager, now, *_ = setup
    identity, candidate, previous = seed_reviewed_collection(manager)
    if record_only:
        manager.state['evidence'].clear()
    now.value = 1201
    parent = '1:0x' + 'b' * 40
    deferred = dict(chainId=candidate['chainId'], address=candidate['address'], warnings=[],
                    inspectionComplete=False, factoryCreationVerified=True, checkedAt=1201)
    manager.inspector.advance = AsyncMock(return_value=SimpleNamespace(
        evidence=None, complete=True, progress={},
        children=[dict(key=identity, candidate=candidate, evidence=deferred)]))
    try:
        assert manager._due(identity)
        await manager._inspect(parent, {}, Budget(monotonic=lambda: 1))
        manager._publish()
        snapshot = manager.get_snapshot()
        assert snapshot['nft_summary']['deployed'] == 1
        assert snapshot['nft_rows'][0]['mint']['state'] == 'open'
        assert snapshot['nft_rows'][0]['sources']['chain']['observed_at'] == 900
        assert manager.state['child_candidates'][identity] == candidate
        if not record_only:
            assert manager.state['evidence'][identity] == previous
        assert manager._due(identity)  # Rediscovery must not renew a ten-minute probe TTL.
    finally:
        await manager.close()


def seed_readme_rows(manager):
    from maxpane_dashboard.analytics.surf_nft import normalize_record
    rows = [normalize_record(dict(id='1:0x' + char * 40, chainId=1,
        contractAddress='0x' + char * 40, category='launched',
        repositories=[{'url': f'https://github.com/example/{name}', 'commit': char * 40}]))
        for char, name in [('a', 'one'), ('b', 'two')]]
    manager.state['records'] = rows
    return rows


def readme_result(repo, revision, *, text='README excerpt', observed_at=1000.):
    return SimpleNamespace(payload=dict(repository_url=repo, revision=revision,
        readme_url=f'{repo}/blob/{revision or "HEAD"}/README.md', text=text, state='ok'),
        observed_at=observed_at)


@pytest.mark.parametrize('invalid', [
    {'url': 'https://gitlab.com/example/one', 'commit': 'a' * 40},
    {'url': 'https://github.com/example/one', 'commit': 'broken-pin'},
])
async def test_readme_skips_invalid_repository_entries_without_downgrading_pin(setup, invalid):
    manager, _, _, _, client, *_ = setup
    rows = seed_readme_rows(manager)
    rows[0]['repositories'] = [invalid, rows[1]['repositories'][0],
                              {'url': 'https://github.com/example/three'}]
    client.readme = AsyncMock(side_effect=lambda repo, revision, **_: readme_result(repo, revision))
    try:
        manager.set_active_view('NFT EXPLORER')
        manager.select(rows[0]['id'])
        assert manager._readme_task is not None
        await manager._readme_task
        assert client.readme.await_args.args == ('https://github.com/example/two', 'b' * 40)
        assert client.readme.await_count == 1
        assert manager.get_readme()['state'] == 'ok'
        assert manager.get_readme()['identity'] == rows[0]['id']
    finally:
        await manager.close()


async def test_readme_is_selected_only_boardroom_silent_and_independent_of_catalogue(setup):
    manager, now, entered, release, client, *_ = setup
    rows = seed_readme_rows(manager)
    read_entered, read_release = asyncio.Event(), asyncio.Event()
    async def read(repo, revision, **kwargs):
        read_entered.set()
        await read_release.wait()
        return readme_result(repo, revision)
    client.readme = AsyncMock(side_effect=read)
    try:
        manager.set_active_view('BOARDROOM')
        manager.select(rows[0]['id'])
        assert manager.get_readme()['state'] == 'pending'
        client.readme.assert_not_called()
        manager.set_active_view('NFT EXPLORER')
        await asyncio.wait_for(read_entered.wait(), 1)
        assert manager.is_loading()
        await manager.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        assert manager.discovery.advance.await_count == 1
        for _ in range(10):
            manager.get_readme()
            manager.get_snapshot()
        assert client.readme.await_count == 1
        read_release.set()
        await manager._readme_task
        assert manager.get_readme()['text'] == 'README excerpt'
        assert manager.get_snapshot()['nft_readme']['identity'] == rows[0]['id']
        assert not manager._task.done()  # README appears before the chain/discovery cycle.
    finally:
        release.set()
        await manager.close()


async def test_readme_cache_reopen_failure_backoff_and_revision_isolation(setup):
    manager, now, _, _, client, *_ = setup
    rows = seed_readme_rows(manager)
    client.readme = AsyncMock(side_effect=lambda repo, revision, **_: readme_result(repo, revision))
    try:
        manager.set_active_view('NFT EXPLORER')
        manager.select(rows[0]['id'])
        await manager.wait_pending()
        original = manager.get_readme()
        manager.set_active_view('BOARDROOM')
        await manager.drain_reads()
        manager.set_active_view('NFT EXPLORER')
        assert manager.get_readme() == original and client.readme.await_count == 1
        now.value += manager.README_TTL
        client.readme.side_effect = OSError('failed read')
        manager.select(rows[0]['id'])
        assert manager.get_readme()['text'] == original['text']
        await manager.wait_pending()
        retained = manager.get_readme()
        assert retained['text'] == original['text'] and retained['observed_at'] == 1000.
        assert retained['state'] == 'unavailable'
        manager.select(rows[0]['id'])
        await manager.wait_pending()
        assert client.readme.await_count == 2
        rows[0]['repositories'][0]['commit'] = 'c' * 40
        manager.select(rows[0]['id'])
        assert manager.get_readme()['text'] is None
        await manager.wait_pending()
        assert client.readme.call_args.args[1] == 'c' * 40
        assert manager.get_readme()['observed_at'] is None
    finally:
        await manager.close()


async def test_readme_switch_cancels_drains_and_rejects_late_completion(setup):
    manager, _, _, _, client, *_ = setup
    rows = seed_readme_rows(manager)
    entered, cancelled, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen = []
    async def read(repo, revision, **_):
        seen.append(repo)
        if repo.endswith('/one'):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await finish.wait()  # Simulate a provider cleaning up after cancellation.
                return readme_result(repo, revision, text='Late old README')
        return readme_result(repo, revision, text='Selected second README')
    client.readme = AsyncMock(side_effect=read)
    try:
        manager.set_active_view('NFT EXPLORER')
        manager.select(rows[0]['id'])
        await asyncio.wait_for(entered.wait(), 1)
        old = manager._readme_task
        manager.select(rows[1]['id'])
        await asyncio.wait_for(cancelled.wait(), 1)
        assert manager.get_readme()['identity'] == rows[1]['id']
        assert manager.get_readme()['text'] is None
        assert len(seen) == 1  # New source waits until old transport has drained.
        finish.set()
        await manager.wait_pending()
        assert old.done() and manager.get_readme()['text'] == 'Selected second README'
        manager.select(rows[0]['id'])
        assert manager.get_readme()['text'] is None  # Late cancelled data was not cached.
    finally:
        finish.set()
        await manager.close()


async def test_readme_leave_and_close_cancel_owned_task_without_retry(setup):
    manager, _, _, _, client, *_ = setup
    rows = seed_readme_rows(manager)
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def read(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    client.readme = AsyncMock(side_effect=read)
    manager.set_active_view('NFT EXPLORER')
    manager.select(rows[0]['id'])
    await asyncio.wait_for(entered.wait(), 1)
    manager.set_active_view('BOARDROOM')
    await manager.drain_reads()
    assert cancelled.is_set() and not manager.is_loading()
    assert client.readme.await_count == 1
    entered.clear(); cancelled.clear()
    manager.set_active_view('NFT EXPLORER')
    await asyncio.wait_for(entered.wait(), 1)
    await manager.close()
    assert cancelled.is_set() and not manager.is_loading()


async def test_readme_leave_requests_cancellation_before_drain(setup):
    manager, _, _, _, client, *_ = setup
    rows = seed_readme_rows(manager)
    entered = asyncio.Event()
    async def read(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    client.readme = AsyncMock(side_effect=read)
    manager.set_active_view('NFT EXPLORER')
    manager.select(rows[0]['id'])
    await asyncio.wait_for(entered.wait(), 1)
    old = manager._readme_task
    try:
        manager.set_active_view('BOARDROOM')
        assert old.cancelling() > 0
        await manager.drain_reads()
        assert old.done()
    finally:
        old.cancel()
        await manager.close()


async def test_readme_invalid_pin_never_falls_back_and_cache_is_bounded(setup):
    manager, _, _, _, client, *_ = setup
    rows = seed_readme_rows(manager)
    rows[0]['repositories'][0]['commit'] = 'main'
    client.readme = AsyncMock(side_effect=lambda repo, revision, **_: readme_result(repo, revision))
    try:
        manager.set_active_view('NFT EXPLORER')
        manager.select(rows[0]['id'])
        assert manager.get_readme()['state'] == 'unavailable'
        client.readme.assert_not_called()
        for index in range(manager.README_CACHE_SIZE + 2):
            rows[0]['repositories'][0]['commit'] = f'{index:040x}'
            manager.select(rows[0]['id'])
            await manager.wait_pending()
        assert len(manager._readme_cache) == manager.README_CACHE_SIZE
    finally:
        await manager.close()


async def test_readme_publish_new_direct_launch_metadata_offers_selected_read(setup):
    manager, _, _, _, client, *_ = setup
    identity, candidate, _ = seed_reviewed_collection(manager)
    assert manager.state['records'][0]['repositories'] == []
    client.readme = AsyncMock(side_effect=lambda repo, revision, **_: readme_result(repo, revision))
    try:
        manager.set_active_view('NFT EXPLORER')
        manager.select(identity)
        assert manager.get_readme()['state'] == 'missing'
        candidate['launch'].update(sourceRepoUrl='https://github.com/example/direct', sourceCommit='d' * 40)
        manager._publish()
        await manager.wait_pending()
        assert client.readme.call_args.args == ('https://github.com/example/direct', 'd' * 40)
        assert manager.get_readme()['state'] == 'ok'
    finally:
        await manager.close()


async def test_known_incomplete_collections_finish_before_stage_expiry_despite_large_probe_queue(setup):
    """Two-provider getter fallbacks need sustained work, not 981-way rotation."""
    from maxpane_dashboard.data.surf_nft_client import BudgetExhausted
    manager, now, *_ = setup
    known = [f'1:0x{i:040x}' for i in range(1, 19)]
    probes = [f'1:0x{i:040x}' for i in range(100, 1081)]
    candidates = {key: dict(chainId=1, address=key[2:]) for key in known + probes}
    manager._candidates = lambda: candidates
    manager._publish = lambda: None
    manager.state['evidence'] = {key: dict(chainId=1, address=key[2:], standard='ERC-721',
        proofOnly=True, checkedAt=900, deploymentConfirmed=True) for key in known}
    manager.select(known[0])
    manager.discovery.advance = AsyncMock(return_value=SimpleNamespace(state={}, coverage={}))
    completed, attempted_probes, resets = [], set(), []

    async def inspect(candidate, progress, *, budget, proof_only=False):
        identity = f"1:{candidate['address']}"
        if proof_only:
            attempted_probes.add(identity)
        stage = deepcopy(progress) if progress else dict(started_at=now.value, completed_operations=0)
        if now.value - stage['started_at'] > 600:
            resets.append(identity)
            stage = dict(started_at=now.value, completed_operations=0)
        target = 8 if proof_only else 64
        try:
            while stage['completed_operations'] < target:
                budget.consume(http=2, rpc=1)
                stage['completed_operations'] += 1
        except BudgetExhausted:
            pass
        complete = stage['completed_operations'] == target
        if complete and not proof_only:
            completed.append((identity, now.value))
        evidence = dict(chainId=1, address=candidate['address'], checkedAt=now.value,
                        standard=None, detectionStatus='unsupported') if proof_only and complete else None
        if not proof_only and complete:
            evidence = dict(manager.state['evidence'][identity], proofOnly=False,
                            checkedAt=now.value, reads={'totalSupply': 7})
        return SimpleNamespace(progress=stage, evidence=evidence, children=[], complete=complete)

    manager.inspector.advance = inspect
    try:
        for _ in range(65):
            await manager.fetch_and_compute()
            await manager.wait_pending()
            assert manager.last_budget.http_attempts <= 24
            assert manager.last_budget.rpc_calls <= 256
            now.value += 30
            if len({key for key, _ in completed}) >= 3:
                break
        assert len({key for key, _ in completed}) >= 3
        assert known[0] in {key for key, _ in completed}
        assert all(stamp < 1000 + 600 for key, stamp in completed[:1])
        assert not resets  # Healthy admitted stages finish within their pinned context.
        assert attempted_probes  # Discovery does not wait for the existing catalog.
        assert len(attempted_probes) < 20  # Each probe is resumed to a terminal proof.
        assert any(not manager.state['evidence'][key].get('proofOnly') for key in known[1:])
    finally:
        await manager.close()


async def test_expired_or_stalled_background_focus_yields_to_another_collection(setup):
    manager, now, *_ = setup
    keys = [f'1:0x{i:040x}' for i in range(1, 4)]
    candidates = {key: dict(chainId=1, address=key[2:]) for key in keys}
    manager._candidates = lambda: candidates
    manager._publish = lambda: None
    manager.discovery.advance = AsyncMock(return_value=SimpleNamespace(state={}, coverage={}))
    manager.state['evidence'] = {key: dict(chainId=1, address=key[2:], standard='ERC-721',
        proofOnly=True, checkedAt=900, deploymentConfirmed=True) for key in keys}
    seen = []

    async def inspect(candidate, progress, *, budget, **_kw):
        key = f"1:{candidate['address']}"
        seen.append(key)
        budget.consume(http=1, rpc=1)
        # An archive/context failure must not hold the lane indefinitely.
        stage = dict(started_at=now.value, completed_operations=1, restart_reason='header not found')
        return SimpleNamespace(progress=stage, evidence=None, children=[], complete=False)

    manager.inspector.advance = inspect
    try:
        for _ in range(3):
            await manager.fetch_and_compute()
            await manager.wait_pending()
            now.value += 30
        assert set(seen) == set(keys)
        assert len(seen) == len(keys)  # Backoff applies even while a stage is retained.
        assert all(manager.state['evidence'][key]['checkedAt'] == 900 for key in keys)
    finally:
        await manager.close()


async def test_slow_discovery_and_selection_leave_time_for_background_enrichment(setup):
    from maxpane_dashboard.data.surf_nft_client import BudgetExhausted
    manager, now, *_ = setup
    keys = ['1:0x' + c * 40 for c in 'ab']
    candidates = {key: dict(chainId=1, address=key[2:]) for key in keys}
    manager._candidates = lambda: candidates
    manager._publish = lambda: None
    manager.state['evidence'] = {key: dict(standard='ERC-721', proofOnly=True, checkedAt=900) for key in keys}
    manager.select(keys[0])
    slices = []
    async def discovery(state, *, budget, detail_limit, **_kw):
        if not detail_limit:
            now.value += budget.remaining_seconds
            raise BudgetExhausted('slow discovery')
        return SimpleNamespace(state={}, coverage={})
    async def inspect(candidate, progress, *, budget, **_kw):
        key = f"1:{candidate['address']}"
        slices.append((key, budget.remaining_seconds))
        budget.consume(http=1, rpc=1)
        if key == keys[0]:
            now.value += budget.remaining_seconds
            # Transport pauses without losing the previously completed reads.
        return SimpleNamespace(progress=dict(started_at=1000, completed_operations=
            (progress or {}).get('completed_operations', 0) + 1), evidence=None, children=[], complete=False)
    manager.discovery.advance = discovery
    manager.inspector.advance = inspect
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert keys[1] in [key for key, _ in slices]
        assert slices[0] == (keys[0], 3)
        assert manager.last_budget.deadline_seconds == 15
        assert not manager._failed
    finally:
        await manager.close()


async def test_leaving_nft_view_cancels_inspection_and_reentry_resumes_retained_stage(setup):
    manager, now, *_ = setup
    key = '1:0x' + 'a' * 40
    manager._candidates = lambda: {key: dict(chainId=1, address=key[2:])}
    manager._publish = lambda: None
    manager.state['evidence'][key] = dict(standard='ERC-721', proofOnly=True, checkedAt=900)
    manager.state['progress'][key] = dict(started_at=1000, completed_operations=4)
    manager.discovery.advance = AsyncMock(return_value=SimpleNamespace(state={}, coverage={}))
    entered, cancelled, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen = []
    async def inspect(candidate, progress, **_kw):
        seen.append(deepcopy(progress))
        entered.set()
        try:
            await finish.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return SimpleNamespace(progress=dict(progress, completed_operations=5), evidence=None,
                               children=[], complete=False)
    manager.inspector.advance = inspect
    try:
        manager.set_active_view('NFT EXPLORER')
        await manager.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        manager.set_active_view(None)
        await manager.drain_reads()
        assert cancelled.is_set() and not manager.is_loading()
        for _ in range(3):
            manager.get_snapshot()
            await manager.fetch_and_compute()
        assert len(seen) == 1
        entered.clear()
        manager.set_active_view('NFT EXPLORER')
        await manager.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        assert seen[-1]['completed_operations'] == 4
        finish.set()
        await manager.wait_pending()
        assert manager.state['progress'][key]['completed_operations'] == 5
    finally:
        finish.set()
        await manager.close()


def test_full_stage_cache_keeps_existing_work_admissible_without_spinning_on_new_rows(setup):
    from maxpane_dashboard.data.surf_nft_cache import SurfNftCache
    manager, *_ = setup
    keys = [f'1:0x{i:040x}' for i in range(SurfNftCache.MAX_STAGES + 1)]
    manager.state['progress'] = {key: dict(started_at=1000) for key in keys[:-1]}
    manager.state['evidence'][keys[-1]] = dict(standard='ERC-721', proofOnly=True)
    assert manager._focus({keys[-1]: {}}) is None
    assert manager._focus({key: {} for key in keys}, probe=True) in keys[:-1]
