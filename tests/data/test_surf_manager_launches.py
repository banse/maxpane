import asyncio
import copy
import pytest
from tests.analytics.test_surf_launch_checks import fixture, evidence
from tests.data.test_surf_manager import FakeClock, FakeSurfClient
from tests.data.test_surf_manager_pool4 import FakePool4Client
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES, SLOT_SWARM_LAUNCHES, SLOT_SWARM_LAUNCH_FACTS

NOW = 1791247200.
class LaunchSwarm:
    def __init__(self):
        self.rows = fixture('launches_100')['launches']; self.calls = []
        self.fail = set()
    async def fetch_launches(self):
        self.calls.append('launches'); return None if 'launches' in self.fail else copy.deepcopy(self.rows)
    async def fetch_sites(self):
        self.calls.append('sites'); return None if 'sites' in self.fail else fixture('sites')['sites']
    async def fetch_launch_policies(self):
        self.calls.append('policies'); return None if 'policies' in self.fail else fixture('launch_policies')['policies']
    async def fetch_launch(self, key):
        self.calls.append(('detail', key))
        return next((fixture(f'launch_{n}') for n in (734,737,747) if fixture(f'launch_{n}')['id'] == key), None)
    async def fetch_job(self, key):
        self.calls.append(('site_job',key))
        return next((fixture(name) for name in ('job_zto_site','job_adam_site') if fixture(name)['id'] == key), None)
    async def close(self): pass
class RPC(FakeSurfClient):
    async def fetch_launch_evidence(self, hashes, addresses):
        out = {'transactions':{},'receipts':{},'codes':{}}
        for n in (734,737,747):
            _, rpc = evidence(n)
            for key in out:
                out[key].update({k:v for k,v in rpc[key].items() if k in hashes or k in addresses})
        return out

def manager(tmp_path, swarm=None):
    return SurfManager(clock=FakeClock(NOW), cache_path=str(tmp_path/'cache.json'), client=RPC(), pool4_client=FakePool4Client(), swarm_client=swarm or LaunchSwarm())

@pytest.mark.asyncio
async def test_launch_cycle_budgets_clocks_last_good_and_production_history(tmp_path):
    m=manager(tmp_path)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        calls=m.swarm_client.calls
        assert len([x for x in calls if isinstance(x,tuple) and x[0]=='detail']) == 3
        assert len([x for x in calls if isinstance(x,tuple) and x[0]=='site_job']) == 3
        keys=m._swarm_launch_keys()
        assert sum(x['count'] for x in keys['swarm_launch_summary']['by_status']) == 9
        old=m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        m.swarm_client.fail={'launches'}
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+301)
        new=m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert new['launches_ts']==old['launches_ts'] and new['sites_ts']==NOW+301
        assert m._swarm_launch_events() is None
        m.swarm_client.fail=set(); m.swarm_client.rows=[]
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+602)
        assert len([r for r in m._swarm_launch_keys()['swarm_launch_rows'] if r['production']])==9
    finally: await m.close()

@pytest.mark.asyncio
async def test_details_read_once_then_on_version_change_and_unknown_retries(tmp_path):
    swarm=LaunchSwarm(); swarm.rows=[fixture('launch_737')]
    m=manager(tmp_path,swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        row=m._swarm_launch_keys()['swarm_launch_rows'][0]
        assert row['verdict']['state']=='swarm' and row['ticker']=='ZTO'
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+61)
        assert len([x for x in swarm.calls if isinstance(x,tuple) and x[0]=='detail'])==1
        swarm.rows[0]['updatedAt']='2026-10-06T01:00:00Z'
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+122)
        assert len([x for x in swarm.calls if isinstance(x,tuple) and x[0]=='detail'])==2
    finally: await m.close()

@pytest.mark.asyncio
async def test_launch_tier_detaches_and_cancels(tmp_path):
    swarm=LaunchSwarm(); gate=asyncio.Event()
    async def blocked(): await gate.wait()
    swarm.fetch_launches=blocked
    m=manager(tmp_path,swarm)
    task=m._spawn_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
    assert task is m._spawn_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
    await asyncio.sleep(0)
    await m.close()
    assert task.cancelled()

@pytest.mark.asyncio
async def test_new_policy_refresh_and_failed_refresh_cannot_convict(tmp_path):
    swarm=LaunchSwarm(); swarm.rows=[fixture('launch_737')]
    m=manager(tmp_path,swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        # Clear the check so a cached-policy mismatch must first refresh policies.
        entry=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS)
        entry.payload['launches'][swarm.rows[0]['id']]['checks']['K2']['state']='unknown'
        original=m.client.fetch_launch_evidence
        async def wrong(*args):
            out=await original(*args)
            for tx in out['transactions'].values(): tx['from']='0x'+'1'*40
            return out
        m.client.fetch_launch_evidence=wrong
        swarm.fail={'policies'}
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+1801)
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K2']['state']=='unknown'
        assert swarm.calls.count('policies')==2
        swarm.fail=set()
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+1922)
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K2']['state']=='fail'
    finally: await m.close()

@pytest.mark.asyncio
async def test_first_payload_keeps_pre_spawn_launch_snapshot(tmp_path):
    swarm=LaunchSwarm(); swarm.rows=[fixture('launch_737')]
    m=manager(tmp_path,swarm)
    try:
        first=await m.fetch_and_compute()
        # Fake core calls suspend through gather; launch read lands during them.
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCHES) is not None
        assert first['swarm_launch_rows'] is None
        second=await m.fetch_and_compute()
        assert second['swarm_launch_rows'][0]['ticker']=='ZTO'
    finally: await m.close()

@pytest.mark.asyncio
async def test_policy_version_newer_than_cache_refreshes_before_judgment(tmp_path):
    swarm=LaunchSwarm(); row=fixture('launch_737'); row['policyVersion']=99; swarm.rows=[row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch=detail
    original=swarm.fetch_launch_policies
    async def policies():
        values=await original(); newer=copy.deepcopy(values[1]); newer['version']=99
        return values+[newer]
    swarm.fetch_launch_policies=policies
    m=manager(tmp_path,swarm)
    try:
        m.cache.store_last_good(SLOT_SWARM_LAUNCHES, {'policies': fixture('launch_policies')['policies'], 'policies_ts':NOW}, ts=NOW)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+61)
        assert swarm.calls.count('policies')==1
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K2']['state']=='pass'
    finally: await m.close()
