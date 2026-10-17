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
    async def inspect(_candidate, progress, *, budget):
        calls.append('chain')
        budget.consume(http=1, rpc=1)
        return SimpleNamespace(progress={'started_at': now.value}, evidence=None,
                               children=[], complete=False)
    manager.discovery.advance = discovery
    manager.inspector.advance = inspect
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert calls[:3] == ['page', 'chain', 'details']
        assert identity in manager.state['progress']
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
