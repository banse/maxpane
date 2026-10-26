import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_wallet_client import SurfWalletClient
from maxpane_dashboard.data.surf_wallet_manager import SurfWalletManager

FIXTURE = json.loads((Path(__file__).parents[1] / 'fixtures/surf/wallet/public_orders.json').read_text())
WALLET = FIXTURE['orders']['payer']
OTHER = '0x' + '9' * 40


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('network access forbidden')
    monkeypatch.setattr('socket.create_connection', refuse)
    monkeypatch.setattr('httpx.AsyncClient.send', AsyncMock(side_effect=refuse))


class Swarm:
    def __init__(self):
        self.calls = []
        self.payload = deepcopy(FIXTURE['orders'])
        self.close = AsyncMock()

    async def _get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if path.startswith('/requests/paid-by/'):
            return deepcopy(self.payload)
        if path == '/schedules':
            return {'count': 0, 'schedules': []}
        raise AssertionError(path)

    async def fetch_job(self, identity):
        if identity == FIXTURE['job']['id']:
            return deepcopy(FIXTURE['job'])
        return dict(id=identity, state='completed', objective='A public request', project={'id':identity}, site=None)

    async def fetch_launch(self, identity):
        assert identity == FIXTURE['launch']['id']
        return deepcopy(FIXTURE['launch'])


async def test_public_client_validates_payer_and_never_reads_authenticated_order_route():
    swarm = Swarm()
    client = SurfWalletClient(swarm)
    assert len(await client.orders(WALLET)) == 5
    assert await client.orders('../token') is None
    swarm.payload['payer'] = OTHER
    assert await client.orders(WALLET) is None
    assert all(path.startswith('/requests/paid-by/') for path, _ in swarm.calls)


async def test_cold_snapshot_then_complete_first_load_without_detail_selection(tmp_path):
    swarm = Swarm()
    seen = []
    async def enrich(orders, candidates, **kwargs):
        seen.extend(deepcopy(candidates))
        for candidate in candidates:
            if candidate['kind'] != 'SITE':
                candidate['deployment']['confirmed'] = True
        return orders, candidates, ['Payments need receipt evidence']
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, evidence=SimpleNamespace(enrich=enrich),
                                cache_path=tmp_path/'wallet.json', clock=lambda: 1793059200.)
    assert manager.get_snapshot()['wallet_snapshot']['orders'] is None
    await manager.fetch_and_compute()
    await manager.wait_pending()
    result = manager.get_snapshot()['wallet_snapshot']
    assert len(result['orders']) == 5 and len(seen) == 1
    assert seen[0]['address'] == FIXTURE['launch']['artifacts'][0]['address'].lower()
    assert seen[0]['deployment']['tx_hash'] == FIXTURE['launch']['artifacts'][0]['txHash']
    assert seen[0]['deployment']['expected_runtime_hash'] == '0x' + FIXTURE['launch']['attestation']['contracts'][0]['deployedCodeHash']
    assert all(row['payer'] == WALLET for row in result['orders'])
    assert len(result['artifacts']) == 1 and result['payment_totals'] is None
    assert result['sources']['orders']['observed_at'] == 1793059200.
    await manager.close()
    swarm.close.assert_not_awaited()


async def test_failed_orders_retain_values_and_timestamp_and_back_off(tmp_path):
    swarm = Swarm()
    now = SimpleNamespace(value=1793059200.)
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json', clock=lambda: now.value)
    await manager.fetch_and_compute(); await manager.wait_pending()
    first = manager.get_snapshot()['wallet_snapshot']
    now.value += 31
    swarm.payload = None
    await manager.fetch_and_compute(); await manager.wait_pending()
    result = manager.get_snapshot()['wallet_snapshot']
    assert result['orders'] == first['orders']
    assert result['sources']['orders']['observed_at'] == first['sources']['orders']['observed_at']
    assert result['sources']['orders']['state'] == 'unavailable'
    calls = len(swarm.calls)
    now.value += 31
    await manager.fetch_and_compute(); await manager.wait_pending()
    assert len(swarm.calls) == calls
    await manager.close()


async def test_late_old_wallet_reply_cannot_repopulate_new_wallet(tmp_path):
    swarm = Swarm()
    entered, release = asyncio.Event(), asyncio.Event()
    original = swarm._get
    async def slow(path, **kwargs):
        if path.endswith(WALLET):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return deepcopy(FIXTURE['orders'])
        if path.endswith(OTHER):
            return {'payer': OTHER, 'count': 0, 'orders': []}
        return await original(path, **kwargs)
    swarm._get = slow
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json')
    await manager.fetch_and_compute(); await entered.wait()
    assert manager.set_wallet(OTHER)
    assert manager.get_snapshot()['wallet_snapshot']['orders'] is None
    release.set()
    await manager.drain_reads()
    await manager.fetch_and_compute(); await manager.wait_pending()
    assert manager.get_snapshot()['wallet_snapshot']['wallet'] == OTHER
    assert manager.get_snapshot()['wallet_snapshot']['orders'] == []
    await manager.close()


async def test_confirmed_catalogue_is_retained_when_latest_order_window_moves(tmp_path):
    swarm = Swarm()
    async def enrich(orders, candidates, **kwargs):
        for candidate in candidates:
            candidate['deployment']['confirmed'] = True
        return orders, candidates, []
    now = SimpleNamespace(value=1793059200.)
    path = tmp_path/'wallet.json'
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, evidence=SimpleNamespace(enrich=enrich),
                                cache_path=path, clock=lambda: now.value)
    await manager.fetch_and_compute(); await manager.wait_pending()
    assert len(manager.get_snapshot()['wallet_snapshot']['artifacts']) == 1
    swarm.payload = {'payer': WALLET, 'count': 0, 'orders': []}
    now.value += 31
    await manager.fetch_and_compute(); await manager.wait_pending()
    assert len(manager.get_snapshot()['wallet_snapshot']['artifacts']) == 1
    await manager.close()
    restored = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=path)
    assert len(restored.get_snapshot()['wallet_snapshot']['artifacts']) == 1
    assert restored.set_wallet(OTHER)
    assert restored.get_snapshot()['wallet_snapshot']['artifacts'] is None
    await restored.close()


async def test_api_overview_publishes_while_evidence_is_still_pending(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    async def enrich(orders, candidates, **kwargs):
        entered.set()
        await release.wait()
        return orders, [], []
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, evidence=SimpleNamespace(enrich=enrich), cache_path=tmp_path/'w.json')
    await asyncio.wait_for(manager.fetch_and_compute(), .1)
    await asyncio.wait_for(entered.wait(), .1)
    assert len(manager.get_snapshot()['wallet_snapshot']['orders']) == 5
    assert manager.is_loading()
    release.set()
    await manager.wait_pending()
    await manager.close()


async def test_unverified_deployments_are_not_promoted_and_site_versions_share_project(tmp_path):
    swarm = Swarm()
    original = swarm.fetch_job
    project = FIXTURE['job']['id']
    versions = [row['result']['jobId'] for row in swarm.payload['orders']]
    async def job(identity):
        result = await original(identity)
        result.update(project={'id': project, 'versions': [{'jobId': i} for i in versions]},
                      site={'url': 'https://example.test/site', 'label': 'public-site'})
        return result
    swarm.fetch_job = job
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json')
    await manager.fetch_and_compute(); await manager.wait_pending()
    assets = manager.get_snapshot()['wallet_snapshot']['artifacts']
    assert len(assets) == 1 and assets[0]['kind'] == 'SITE'
    assert assets[0]['project'] == project and assets[0]['version'] == 5
    assert assets[0]['linked_id'] is None and assets[0]['binding_checked'] is False
    await manager.close()


async def test_schedule_pages_validate_payer_and_retain_partial_page():
    from uuid import UUID
    first = [dict(id=str(UUID(int=i+1)), owner=WALLET, createdAt='2026-10-01T00:00:00Z') for i in range(100)]
    calls = []
    async def get(path, **kwargs):
        calls.append((path, kwargs))
        return {'schedules': first} if len(calls) == 1 else {'schedules': [dict(first[0], owner=OTHER)]}
    rows, complete = await SurfWalletClient(SimpleNamespace(_get=get)).schedules(WALLET)
    assert len(rows) == 100 and complete is False
    assert calls[1][1]['params']['before'] == first[-1]['createdAt']
    assert all(path == '/schedules' for path, _ in calls)


async def test_invalid_cache_and_wallet_are_ignored(tmp_path):
    path = tmp_path/'w.json'
    path.write_text(json.dumps({WALLET: {'wallet': OTHER, 'orders': []}}))
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, cache_path=path)
    assert manager.get_snapshot()['wallet_snapshot']['orders'] is None
    assert manager.set_wallet('../../secrets') is False
    assert manager.get_snapshot()['wallet_snapshot']['wallet'] == WALLET
    await manager.close()


async def test_failed_enrichment_retains_prior_payment_proofs_and_source_time(tmp_path):
    now = SimpleNamespace(value=1793059200.)
    fail = False
    async def enrich(orders, candidates, **kwargs):
        if fail:
            raise RuntimeError('evidence temporarily unavailable')
        for row in orders:
            row['payments'] = [dict(chain_id=1, asset='0x'+'a'*40, symbol='IMD', decimals=18,
                                    amount='.1', tx_hash=row['tx_hash'], observed_at=now.value)]
        return orders, [], []
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, evidence=SimpleNamespace(enrich=enrich),
                                cache_path=tmp_path/'w.json', clock=lambda: now.value)
    await manager.fetch_and_compute(); await manager.wait_pending()
    first = manager.get_snapshot()['wallet_snapshot']
    fail = True
    now.value += 31
    await manager.fetch_and_compute(); await manager.wait_pending()
    result = manager.get_snapshot()['wallet_snapshot']
    assert result['orders'][0]['payments'] == first['orders'][0]['payments']
    assert result['sources']['details']['observed_at'] == first['sources']['details']['observed_at']
    await manager.close()


async def test_runtime_change_invalidates_usage_without_erasing_deployment_history(tmp_path):
    invalidated = False
    now = SimpleNamespace(value=1793059200.)
    async def enrich(orders, candidates, **kwargs):
        for candidate in candidates:
            candidate['deployment']['confirmed'] = not invalidated
            candidate['evidence_invalidated'] = invalidated
            candidate['usage'] = None if invalidated else dict(count=4, complete=True, observed_at=now.value)
        return orders, candidates, []
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, evidence=SimpleNamespace(enrich=enrich),
                                cache_path=tmp_path/'w.json', clock=lambda: now.value)
    await manager.fetch_and_compute(); await manager.wait_pending()
    assert manager.get_snapshot()['wallet_snapshot']['artifacts'][0]['usage']['count'] == 4
    invalidated = True
    now.value += 31
    await manager.fetch_and_compute(); await manager.wait_pending()
    artifact = manager.get_snapshot()['wallet_snapshot']['artifacts'][0]
    assert artifact['usage'] is None and artifact['evidence_invalidated'] is True
    assert artifact['deployment']['confirmed'] is True  # Historical confirmed deployment.
    await manager.close()


async def test_leaving_view_cancels_evidence_and_drains_without_closing_transport(tmp_path):
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def enrich(orders, candidates, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    swarm = Swarm()
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, evidence=SimpleNamespace(enrich=enrich), cache_path=tmp_path/'w.json')
    await manager.fetch_and_compute(); await entered.wait()
    manager.set_active_view(None)
    await asyncio.wait_for(manager.drain_reads(), .1)
    assert cancelled.is_set() and not manager.is_loading()
    await manager.fetch_and_compute()
    assert not manager.is_loading()
    await manager.close()
    swarm.close.assert_not_awaited()


async def test_unknown_result_kind_is_not_followed_as_a_job(tmp_path):
    swarm = Swarm()
    swarm.payload['orders'] = [dict(swarm.payload['orders'][0], result=dict(kind='unknown', jobId=FIXTURE['job']['id']))]
    swarm.fetch_job = AsyncMock(side_effect=AssertionError('Unknown result must not authorize a job join'))
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json')
    await manager.fetch_and_compute(); await manager.wait_pending()
    row = manager.get_snapshot()['wallet_snapshot']['orders'][0]
    assert row['job_id'] is None and row['outcome'] == 'admitted'
    swarm.fetch_job.assert_not_called()
    await manager.close()


async def test_detail_budget_eventually_reads_tail_of_full_order_window(tmp_path):
    from uuid import UUID
    swarm = Swarm()
    template = swarm.payload['orders'][0]
    swarm.payload['orders'] = [dict(template, orderId=str(UUID(int=1000+i)),
        result=dict(kind='job', jobId=str(UUID(int=10000+i)))) for i in range(100)]
    seen = set()
    original = swarm.fetch_job
    async def job(identity):
        seen.add(identity)
        return await original(identity)
    swarm.fetch_job = job
    now = SimpleNamespace(value=1793059200.)
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json', clock=lambda: now.value)
    for _ in range(3):
        await manager.fetch_and_compute(); await manager.wait_pending()
        now.value += 61
    assert len(seen) == 100
    assert manager.get_snapshot()['wallet_snapshot']['sources']['orders']['truncated'] is True
    await manager.close()


async def test_detail_budget_completes_dependent_launch_reads_for_full_window(tmp_path):
    from uuid import UUID
    swarm = Swarm()
    template = swarm.payload['orders'][0]
    jobs = [str(UUID(int=10000+i)) for i in range(100)]
    launches = [str(UUID(int=20000+i)) for i in range(100)]
    swarm.payload['orders'] = [dict(template, orderId=str(UUID(int=1000+i)), action='launch.open',
        result=dict(kind='job', jobId=identity)) for i, identity in enumerate(jobs)]
    seen = set()
    async def job(identity):
        return dict(id=identity, state='completed', launch={'id': launches[jobs.index(identity)]})
    async def launch(identity):
        seen.add(identity)
        return dict(id=identity, status='live', chainId=1, artifacts=[])
    swarm.fetch_job, swarm.fetch_launch = job, launch
    now = SimpleNamespace(value=1793059200.)
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json', clock=lambda: now.value)
    for _ in range(5):
        await manager.fetch_and_compute(); await manager.wait_pending()
        now.value += 61
    assert seen == set(launches)
    assert all(row['outcome'] == 'live' for row in manager.get_snapshot()['wallet_snapshot']['orders'])
    await manager.close()


async def test_paid_oracle_group_counts_once_without_invented_child_reads(tmp_path):
    from maxpane_dashboard.analytics.surf_wallet import summary
    swarm = Swarm()
    swarm.payload['orders'] = [dict(swarm.payload['orders'][0], action='oracle.group',
        result={'kind': 'group', 'requestIds': [FIXTURE['job']['id']]})]
    swarm.fetch_job = AsyncMock(side_effect=AssertionError('No explicit supported result join'))
    manager = SurfWalletManager(swarm=swarm, wallet=WALLET, cache_path=tmp_path/'w.json', clock=lambda: 1793059200.)
    await manager.fetch_and_compute(); await manager.wait_pending()
    result = manager.get_snapshot()['wallet_snapshot']
    assert len(result['orders']) == 1 and result['orders'][0]['action'] == 'oracle.group'
    assert summary(result, 1793059200.)['counts']['ORACLES'] == 1
    assert result['orders'][0]['job_id'] is None
    swarm.fetch_job.assert_not_called()
    await manager.close()


async def test_schedule_cursor_resumes_after_budget_and_is_isolated_per_wallet():
    from datetime import datetime, timedelta, timezone
    from uuid import UUID
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    records = [dict(id=str(UUID(int=i+1)), owner=WALLET,
                    createdAt=(start-timedelta(seconds=i)).isoformat().replace('+00:00', 'Z')) for i in range(450)]
    calls = []
    async def get(path, *, params):
        assert path == '/schedules'
        calls.append(dict(params))
        values = records if params['owner'] == WALLET else []
        return {'schedules': [r for r in values if not params.get('before') or r['createdAt'] < params['before']][:100]}
    client = SurfWalletClient(SimpleNamespace(_get=get))
    first, complete = await client.schedules(WALLET)
    assert len(first) == 400 and complete is False
    assert await client.schedules(OTHER) == ([], True)
    second, complete = await client.schedules(WALLET)
    assert len(second) == 450 and complete is True
    assert calls[-1]['before'] == records[399]['createdAt']
    await client.schedules(WALLET)
    assert 'before' not in calls[-4]  # Completed passes restart from the head.


@pytest.mark.parametrize(('path', 'bad'), [
    (('artifacts', 0, 'usage'), 'malformed'),
    (('artifacts', 0, 'usage', 'count'), []),
    (('artifacts', 0, 'usage', 'actors'), {}),
    (('artifacts', 0, 'usage', 'complete'), 'yes'),
    (('artifacts', 0, 'usage', 'rule'), []),
    (('artifacts', 0, 'linked_id'), []),
    (('artifacts', 0, 'deployment'), []),
    (('sources', 'orders'), 'malformed'),
    (('sources', 'orders', 'observed_at'), float('nan')),
    (('sources', 'orders', 'complete'), 'yes'),
    (('orders', 0, 'payments'), {}),
    (('orders', 0, 'payments', 0), 'malformed'),
    (('orders', 0, 'payments', 0, 'amount'), []),
    (('orders', 0, 'payments', 0, 'decimals'), 300),
    (('payment_totals', 0), 'malformed'),
    (('payment_totals', 0, 'paid'), 'NaN'),
    (('sources', 'orders', 'observed_at'), 10**400),
    (('artifacts', 0, 'usage_state'), {}),
    (('artifacts', 0, 'usage_state'), 'unknown-state'),
    (('artifacts', 0, 'usage_state'), 'unsupported'),
])
async def test_nested_malformed_cache_rejects_entire_wallet(tmp_path, path, bad):
    from maxpane_dashboard.analytics.surf_wallet import payment_totals
    from maxpane_dashboard.data.surf_wallet_manager import _record
    from maxpane_dashboard.data.surf_wallet_models import empty_snapshot
    snapshot = empty_snapshot(WALLET)
    order = _record(FIXTURE['orders']['orders'][0], WALLET)
    order['payments'] = [dict(chain_id=1, asset='0x'+'a'*40, symbol='IMD', decimals=18,
                              amount='0.1', tx_hash=order['tx_hash'], observed_at=1793059200.)]
    snapshot.update(orders=[order], schedules=[], as_of=1793059200., payment_totals=payment_totals([order]),
        artifacts=[dict(id='1:'+'0x'+'a'*40, kind='CONTRACT', address='0x'+'a'*40, chain_id=1,
                        deployment={'confirmed': True}, linked_id=None,
                        usage=dict(count=1, actors=1, complete=True, rule='rule'))],
        sources={'orders': dict(state='ok', observed_at=1793059200., complete=True)})
    assert SurfWalletManager._valid(snapshot, WALLET)
    target = snapshot
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    cache = tmp_path/'w.json'
    cache.write_text(json.dumps({WALLET: snapshot}))
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, cache_path=cache)
    assert manager.get_snapshot()['wallet_snapshot']['orders'] is None
    await manager.close()


@pytest.mark.parametrize('population', ['orders', 'artifacts', 'schedules'])
async def test_duplicate_cached_id_rejects_wallet_before_paint(tmp_path, population):
    from maxpane_dashboard.data.surf_wallet_manager import _record
    from maxpane_dashboard.data.surf_wallet_models import empty_snapshot
    snapshot = empty_snapshot(WALLET)
    record = _record(FIXTURE['orders']['orders'][0], WALLET)
    snapshot.update(orders=[record], artifacts=[dict(id='site:'+FIXTURE['job']['id'], kind='SITE')],
                    schedules=[dict(id=FIXTURE['job']['id'], owner=WALLET)], as_of=record['timestamp'])
    assert SurfWalletManager._valid(snapshot, WALLET)
    snapshot[population].append(deepcopy(snapshot[population][0]))
    cache = tmp_path/'w.json'
    cache.write_text(json.dumps({WALLET: snapshot}))
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, cache_path=cache)
    assert manager.get_snapshot()['wallet_snapshot'] == empty_snapshot(WALLET)
    await manager.close()


@pytest.mark.parametrize('legacy_marker', [False, True])
async def test_failed_usage_read_retains_same_runtime_observation_and_clock(tmp_path, legacy_marker):
    now = SimpleNamespace(value=1793059200.)
    observed = dict(count=4, actors=2, unit='refreshes', complete=True, observed_at=now.value, rule='reviewed')
    fail = False
    async def enrich(orders, candidates, **kwargs):
        for candidate in candidates:
            candidate['deployment'].update(confirmed=True, runtime_hash=candidate['deployment']['expected_runtime_hash'])
            candidate['usage'] = None if fail else deepcopy(observed)
            candidate.update(evidence_state='ok', evidence_observed_at=now.value)
            if not legacy_marker:
                candidate['usage_state'] = 'unavailable' if fail else 'ok'
        return orders, candidates, []
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, evidence=SimpleNamespace(enrich=enrich),
                                cache_path=tmp_path/'w.json', clock=lambda: now.value)
    await manager.fetch_and_compute(); await manager.wait_pending()
    fail = True
    now.value += 31
    await manager.fetch_and_compute(); await manager.wait_pending()
    result = manager.get_snapshot()['wallet_snapshot']
    artifact = result['artifacts'][0]
    assert artifact['usage'] == observed
    assert artifact['usage_state'] == 'unavailable'
    assert result['sources']['usage']['state'] == 'partial'
    assert result['sources']['usage']['observed_at'] == observed['observed_at']
    assert result['sources']['chain']['observed_at'] == now.value
    await manager.close()


@pytest.mark.parametrize(('state', 'changed_runtime'), [('unsupported', False), ('invalidated', False), ('unavailable', True)])
async def test_usage_is_cleared_for_unsupported_rule_or_different_runtime(tmp_path, state, changed_runtime):
    now = SimpleNamespace(value=1793059200.)
    fail = False
    async def enrich(orders, candidates, **kwargs):
        for candidate in candidates:
            candidate['deployment'].update(confirmed=True,
                runtime_hash='0x'+'9'*64 if fail and changed_runtime else candidate['deployment']['expected_runtime_hash'])
            candidate['usage'] = None if fail else dict(count=4, complete=True, observed_at=now.value)
            candidate['usage_state'] = state if fail else 'ok'
        return orders, candidates, []
    manager = SurfWalletManager(swarm=Swarm(), wallet=WALLET, evidence=SimpleNamespace(enrich=enrich),
                                cache_path=tmp_path/'w.json', clock=lambda: now.value)
    await manager.fetch_and_compute(); await manager.wait_pending()
    fail = True
    now.value += 31
    await manager.fetch_and_compute(); await manager.wait_pending()
    result = manager.get_snapshot()['wallet_snapshot']
    assert result['artifacts'][0]['usage'] is None
    assert result['sources']['usage']['observed_at'] is None
    await manager.close()
