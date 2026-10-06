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
    original=m.client.fetch_launch_evidence; requests=[]
    async def evidence(hashes,addresses): requests.append((hashes,addresses)); return await original(hashes,addresses)
    m.client.fetch_launch_evidence=evidence
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
