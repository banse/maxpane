"""Detached K8 cadence from captured receipts/state, never network."""
import copy
import uuid
import pytest
from maxpane_dashboard.analytics import surf_launch_checks as lc, surf_launch_liquidity as ll
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_FACTS, TIER_SWARM_LAUNCHES
from tests.analytics.test_surf_launch_liquidity import live_fixture
from tests.analytics.test_surf_launch_checks import checked
from tests.data.test_surf_manager_launches import manager, LaunchSwarm, NOW


def seed(m, count=1, *, pool=True):
    row,inputs,answers,decimals=live_fixture(737)
    _,facts,checks=checked()
    points={}
    for i in range(count):
        r=copy.deepcopy(row); r.update(id=str(uuid.UUID(int=i+1)),launchNumber=737+i)
        p=copy.deepcopy(facts); p.update(row=r, checks=copy.deepcopy(checks), detail_version=[r['status'],r['updatedAt']])
        if pool: p['pool_inputs']=copy.deepcopy(inputs)
        points[r['id']]=p
    m.swarm_client.rows=[p['row'] for p in points.values()]
    m.cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS,sw.coerce_launch_facts_slot({'launches':points,'sites':{}}),ts=NOW-1)
    return inputs,answers,decimals


def responder(m,answers,decimals):
    batches=[]; fail=set()
    async def fetch(calls):
        batches.append(copy.deepcopy(calls)); out=[]; word=0
        for method,params in calls:
            if params[0]['data']=='0x313ce567':
                value='0x'+decimals[params[0]['to']].to_bytes(32,'big').hex()
            else:
                value=answers[word%3]; word+=1
            out.append(None if len(out) in fail else value)
        return out
    m.client.fetch_launch_pool_state=fetch
    return batches,fail


@pytest.mark.asyncio
async def test_liquidity_cap_cadence_oldest_first_and_last_good(tmp_path):
    m=manager(tmp_path); _,answers,decimals=seed(m,12)
    batches,fail=responder(m,answers,decimals)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        points=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        read=[p for p in points.values() if p.get('liquidity',{}).get('read_ts')==NOW]
        assert len(read)==10
        assert sum(p[1][0]['data'].startswith('0x1e2eaeaf') for p in batches[0])==30
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+61)
        assert sum(p[1][0]['data'].startswith('0x1e2eaeaf') for p in batches[1])==6
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+299)
        assert len(batches)==2
        fail.add(0)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+300)
        points=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        old=[p for p in points.values() if p.get('liquidity',{}).get('read_ts')==NOW]
        assert len(old)==1 and old[0]['liquidity']['lock']=='locked'
        assert old[0]['liquidity_attempt_ts']==NOW+300
        assert all(params[0]['data']!='0x313ce567' for _,params in batches[-1])
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+361)
        assert len(batches)==4 and len(batches[-1])==6, 'failed first pool backs off; the next two get their turn'
        rows=m._swarm_launch_keys()['swarm_launch_rows']
        assert all(r['checks']['K8']==r['liquidity'] for r in rows)
        assert all(r['verdict']['state']=='swarm' for r in rows)
    finally: await m.close()


@pytest.mark.asyncio
async def test_legacy_pool_bootstrap_is_bounded_and_decimals_retry_independently(tmp_path):
    m=manager(tmp_path); _,answers,decimals=seed(m,12,pool=False)
    batches,fail=responder(m,answers,decimals); fail.add(31) # second decimal in first ten-pool batch
    original=m.client.fetch_launch_receipts; requests=[]
    async def receipts(hashes): requests.append(hashes); return await original(hashes)
    m.client.fetch_launch_receipts=receipts
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        points=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        assert sum('pool_inputs' in p for p in points.values())==10
        assert all(not p.get('liquidity') for p in points.values()), 'missing token decimals cannot fabricate token amounts'
        assert all(len(p.get('pool_decimals',{}))==1 for p in points.values() if 'pool_inputs' in p)
        fail.clear()
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+61)
        assert len(requests)==2 and sum('pool_inputs' in p for p in m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'].values())==12
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+301)
        assert len(requests)==2
        decimal_calls=[params[0]['to'] for _,params in batches[-1] if params[0]['data']=='0x313ce567']
        assert len(decimal_calls)==1, 'the successful sibling decimal is never reread'
    finally: await m.close()


@pytest.mark.asyncio
async def test_robinhood_pool_uses_chain_client_and_no_pool_never_reads(tmp_path):
    from tests.data.test_surf_manager_launches import RPC
    m=manager(tmp_path); seed(m)
    points=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
    old=next(iter(points.values()))
    row,pool,answers,decimals=live_fixture(791)
    old.update(row=row,pool_inputs=pool,detail_version=[row['status'],row['updatedAt']])
    m.swarm_client.rows=[row]
    m.cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS,sw.coerce_launch_facts_slot({'launches':{row['id']:old},'sites':{}}),ts=NOW-1)
    batches,_=responder(m,answers,decimals)
    rh=RPC(); rh.fetch_launch_pool_state=m.client.fetch_launch_pool_state
    m._launch_rpc_clients[4663]=rh
    async def forbidden(*_): raise AssertionError('RH storage routed to Ethereum')
    m.client.fetch_launch_pool_state=forbidden
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        shown=m._swarm_launch_keys()['swarm_launch_rows'][0]
        assert shown['liquidity']['paired_amount']==pytest.approx(.10126446,rel=1e-6)
        assert batches[0][0][1][0]['to']==pool['emitter']
        point=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
        point['pool_inputs']={'state':'na'}
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+301)
        assert len(batches)==1 and m._swarm_launch_keys()['swarm_launch_rows'][0]['liquidity']['state']=='na'
    finally: await m.close()


@pytest.mark.parametrize('failed_evidence', [None, {}], ids=['failed-batch', 'missing-receipt'])
async def test_legacy_bootstrap_is_not_starved_by_another_launch_on_same_chain(tmp_path, failed_evidence):
    m = manager(tmp_path)
    _, answers, decimals = seed(m, pool=False)
    legacy = m.swarm_client.rows[0]
    pending, _, _ = checked(747)
    m.swarm_client.rows.append(pending)
    legacy_hashes = {a['txHash'] for a in legacy['artifacts']}
    pending_hashes = {a['txHash'] for a in pending['artifacts']}
    original = m.client.fetch_launch_evidence
    requests = []
    batches, _ = responder(m, answers, decimals)

    async def evidence(hashes, addresses):
        requests.append(set(hashes))
        if set(hashes) == pending_hashes:
            return copy.deepcopy(failed_evidence)
        return await original(hashes, addresses)

    m.client.fetch_launch_evidence = evidence
    original_receipts = m.client.fetch_launch_receipts
    async def receipts(hashes):
        requests.append(set(hashes))
        return await original_receipts(hashes)
    m.client.fetch_launch_receipts = receipts
    try:
        for delta in (0, 61, 299, 300, 602):
            before = len(requests)
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + delta)
            # The unread launch is attempted once, never duplicated by K8.
            # The settled launch still gets its own one-time receipt bootstrap.
            assert requests[before:] == [pending_hashes] + ([legacy_hashes] if delta == 0 else [])
            points = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
            assert points[pending['id']]['pool_attempt_ts'] == NOW + delta
            assert 'pool_inputs' not in points[pending['id']]
            result = points[legacy['id']]['liquidity']
            assert result['paired_amount'] == pytest.approx(4726.591141)
            assert result['read_ts'] == NOW + (delta if delta >= 300 else 0)
            shown = next(row for row in m._swarm_launch_keys()['swarm_launch_rows']
                         if row['launch_id'] == legacy['id'])
            assert shown['pool_fee'] == 12500 and shown['checks']['K8'] == result
        assert len(batches) == 3, 'market reads retain their independent 300-second cadence'
    finally:
        await m.close()


@pytest.mark.parametrize('status,state', [('parked','na'), ('abandoned','na'), ('admitted','unknown')])
async def test_no_artifacts_liquidity_distinguishes_parked_from_admitted(tmp_path, status, state):
    m = manager(tmp_path)
    seed(m)
    points = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
    point = next(iter(points.values()))
    point.pop('pool_inputs')
    point['row'].update(status=status, artifacts=[])
    point['detail_version'] = [status, point['row']['updatedAt']]
    m.swarm_client.rows = [point['row']]
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['liquidity'] == ll.empty_liquidity(state)
    finally:
        await m.close()


async def test_native_eth_pool_775_reads_no_zero_address_decimals_and_returns_k8(tmp_path):
    m = manager(tmp_path)
    seed(m)
    point = next(iter(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'].values()))
    row, pool, answers, decimals = live_fixture(775)
    point.update(row=row, pool_inputs=pool, detail_version=[row['status'],row['updatedAt']])
    m.swarm_client.rows = [row]
    m.cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS, sw.coerce_launch_facts_slot({'launches':{row['id']:point},'sites':{}}), ts=NOW-1)
    decimals.pop(lc.ZERO)
    batches, _ = responder(m, answers, decimals)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        calls = [params[0]['to'] for _,params in batches[0] if params[0]['data'] == '0x313ce567']
        assert calls == [pool['currency1']] and lc.ZERO not in calls
        shown = m._swarm_launch_keys()['swarm_launch_rows'][0]['liquidity']
        assert shown['paired_symbol'] == 'ETH' and shown['paired_amount'] == pytest.approx(14.2330796)
        assert shown['read_ts'] == NOW and shown['state'] == 'info'
    finally:
        await m.close()


async def test_fifteen_due_pools_choose_ten_distinct_oldest_result_timestamps(tmp_path):
    m = manager(tmp_path)
    _, answers, decimals = seed(m, 15)
    points = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
    for i, point in enumerate(points.values()):
        point['liquidity'] = dict(ll.empty_liquidity(), read_ts=NOW - 600 + i)
    expected = set(list(points)[:10])
    batches, _ = responder(m, answers, decimals)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        refreshed = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        assert {key for key,p in refreshed.items() if p['liquidity']['read_ts'] == NOW} == expected
        assert len(batches) == 1 and len(batches[0]) == 32
    finally:
        await m.close()


@pytest.mark.parametrize('kind', ['initialize', 'modify'])
async def test_ambiguous_receipts_persist_unknown_without_repeat_bootstrap(tmp_path, kind):
    from tests.analytics.test_surf_launch_liquidity import ambiguous_receipts
    m = manager(tmp_path)
    seed(m, pool=False)
    _, receipts = ambiguous_receipts(kind)
    calls = []
    async def fetch_receipts(hashes):
        calls.append(hashes)
        return copy.deepcopy(receipts)
    async def forbidden(*args):
        raise AssertionError('settled K8 bootstrap needs receipts only')
    m.client.fetch_launch_receipts = fetch_receipts
    m.client.fetch_launch_evidence = forbidden
    try:
        for delta in (0, 301, 602):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + delta)
            point = next(iter(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'].values()))
            assert point['pool_inputs'] == {'state':'ambiguous'}
            assert m._swarm_launch_keys()['swarm_launch_rows'][0]['liquidity'] == ll.empty_liquidity()
            assert point['pool_fee'] == (12500 if kind == 'modify' else None)
        assert len(calls) == 1
    finally:
        await m.close()


@pytest.mark.parametrize('failure', ['missing', 'malformed'])
async def test_incomplete_or_malformed_receipts_retry_after_bootstrap_backoff(tmp_path, failure):
    from tests.analytics.test_surf_launch_liquidity import pool_fixture
    m = manager(tmp_path)
    seed(m, pool=False)
    _, receipts = pool_fixture(737)
    if failure == 'missing':
        receipts = {}
    else:
        log = next(log for log in next(iter(receipts.values()))['logs'] if log['topics'][0] == ll.MODIFY_TOPIC)
        log['data'] = '0x01'
    calls = []
    async def fetch(hashes):
        calls.append(hashes)
        return copy.deepcopy(receipts)
    m.client.fetch_launch_receipts = fetch
    try:
        for delta in (0, 61, 299, 300):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + delta)
            point = next(iter(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'].values()))
            assert 'pool_inputs' not in point
            assert m._swarm_launch_keys()['swarm_launch_rows'][0]['liquidity'] == ll.empty_liquidity()
            assert len(calls) == (2 if delta == 300 else 1)
    finally:
        await m.close()
