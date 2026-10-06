import asyncio
import copy
import pytest
from tests.analytics.test_surf_launch_checks import fixture, evidence
from tests.data.test_surf_manager import FakeClock, FakeSurfClient
from tests.data.test_surf_manager_pool4 import FakePool4Client
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data import surf_swarm as sw
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
        assert m._swarm_launch_events(keys['swarm_launch_rows']) is None
        m.swarm_client.fail=set(); m.swarm_client.rows=[]
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+602)
        retained = m._swarm_launch_keys()
        assert len([r for r in retained['swarm_launch_rows'] if r['production']]) == 9
        assert sum(r['count'] for r in retained['swarm_launch_summary']['by_status']) == 9
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
        assert first['swarm_launch_rows'] is None
        # The worker may still be hashing; completion never changes this snapshot.
        await m._swarm_launches_task
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


def test_v8_signal_reading_uses_passed_snapshot_and_publishes_chain(tmp_path):
    from tests.surf_launch_fixtures import launch_event
    from maxpane_dashboard.analytics.surf_signals import build_signals
    m=manager(tmp_path)
    event=launch_event(chain_id=8453)
    envelope={'events':[event], 'ts':NOW}
    reading=m._readings({},None,{},[],swarm_launch_events=envelope)
    assert reading['swarm_launch_events'] is envelope
    _, baseline=build_signals({}, {'swarm_launch_events':{'events':[], 'ts':NOW}}, NOW)
    m.cache.set_baselines(baseline,now=NOW)
    result=m._signal_keys(reading,NOW+10)
    assert result['sig_swarm_chain_id']==8453
    assert result['sig_swarm_launch']['launch_id']==event['launch_id']
    assert result['swarm_launch_fired'][0]['launch_id']==event['launch_id']
    assert result['sig_swarm_state']=='fired'


@pytest.mark.asyncio
async def test_site_match_is_detached_memoized_and_refresh_reuses_launch_rows(tmp_path, monkeypatch):
    import threading
    from maxpane_dashboard.analytics import surf_launch_sites as ls
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SCORES
    m = manager(tmp_path)
    original = ls.match_sites
    matches = []
    loop_thread = threading.get_ident()
    def match(*args):
        matches.append(threading.get_ident())
        return original(*args)
    monkeypatch.setattr(ls, 'match_sites', match)
    try:
        await m.fetch_and_compute()
        if m._swarm_launches_task:
            await m._swarm_launches_task
        assert len(matches) == 1
        assert matches[0] != loop_thread
        keys = m._swarm_launch_keys()
        assert len(matches) == 1
        snapshot = copy.deepcopy(keys)
        monkeypatch.setattr(m, '_swarm_launch_keys', lambda: pytest.fail('event rebuilt launch rows'))
        m._swarm_launch_events(keys['swarm_launch_rows'])
        assert keys == snapshot
        # Route failures leave timestamps and facts unchanged: cached links stay reusable.
        m.swarm_client.fail = {'launches', 'sites', 'policies'}
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        assert len(matches) == 1
        m.cache.store_last_good(SLOT_SWARM_SCORES, {'workflows': fixture('workflows_100')['workflows'], 'workflows_ts': NOW+1}, ts=NOW+1)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+1)
        assert len(matches) == 2
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_site_links_invalidate_on_new_facts_with_unchanged_failed_route_clock(tmp_path, monkeypatch):
    from maxpane_dashboard.analytics import surf_launch_sites as ls
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    original_detail = swarm.fetch_launch
    async def unavailable(_):
        return None
    swarm.fetch_launch = unavailable
    m = manager(tmp_path, swarm)
    calls = []
    original_match = ls.match_sites
    def match(*args):
        calls.append(copy.deepcopy(args[1]))
        return original_match(*args)
    monkeypatch.setattr(ls, 'match_sites', match)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        before = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert len(calls) == 1
        assert not next(iter(calls[0].values())).get('detail_version')
        swarm.fetch_launch = original_detail
        swarm.fail = {'launches'}
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61)
        after = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert len(calls) == 2
        assert after['launches_ts'] == before['launches_ts']
        assert after['site_links_inputs'] != before['site_links_inputs']
        assert next(iter(calls[1].values()))['ticker'] == 'ZTO'
    finally:
        await m.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('version', [None, 999])
async def test_unknown_policy_version_is_refreshed_once_and_persisted(tmp_path, version):
    swarm = LaunchSwarm(); row = fixture('launch_737'); row['policyVersion'] = version; swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    try:
        for i in range(3):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61*i)
        assert swarm.calls.count('policies') == 1
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload['policies_refreshed_for'] == {row['id']: version}
        m.cache.save(); m.cache.load()
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+183)
        assert swarm.calls.count('policies') == 1
    finally: await m.close()


@pytest.mark.asyncio
async def test_checks_are_threaded_and_persisted_failure_does_not_refresh_policies(tmp_path, monkeypatch):
    import threading
    from maxpane_dashboard.analytics import surf_launch_checks as lc
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    m = manager(tmp_path, swarm)
    calls = []; original = lc.check_launch; loop = threading.get_ident()
    def check(*args, **kwargs):
        calls.append(threading.get_ident())
        return original(*args, **kwargs)
    monkeypatch.setattr(lc, 'check_launch', check)
    original_rpc = m.client.fetch_launch_evidence
    async def wrong(*args):
        out = await original_rpc(*args)
        for tx in out['transactions'].values(): tx['from'] = '0x'+'1'*40
        out['codes'] = {}  # keep K3 pending while K2 is permanently failed
        return out
    m.client.fetch_launch_evidence = wrong
    m.cache.store_last_good(SLOT_SWARM_LAUNCHES, {'policies': fixture('launch_policies')['policies'], 'policies_ts': NOW}, ts=NOW)
    try:
        for i in range(3):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61*i)
        assert swarm.calls.count('policies') == 1
        assert len(calls) == 4  # initial + refreshed policy, then two pending retries
        assert all(thread != loop for thread in calls)
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K2']['state'] == 'fail'
    finally: await m.close()


@pytest.mark.asyncio
async def test_failed_details_rotate_without_starving_lower_numbers(tmp_path):
    swarm = LaunchSwarm()
    swarm.rows = [row for row in swarm.rows if row['launchNumber'] in (754, 751, 747, 741, 737, 734)]
    original = swarm.fetch_launch
    async def detail(key):
        row = next(row for row in swarm.rows if row['id'] == key)
        if row['launchNumber'] == 741:
            swarm.calls.append(('detail', key))
            return {**fixture('launch_737'), **row}
        return await original(key)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    try:
        for i in range(4):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61*i)
            if i == 1:
                reached = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
                assert {p['row']['launchNumber'] for p in reached.values() if p.get('detail_version')} >= {737, 741}
        facts = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        assert {p['row']['launchNumber'] for p in facts.values() if p.get('detail_version')} >= {737, 741}
        failed = [p for p in facts.values() if p['row']['launchNumber'] in (754,751)]
        assert all(p['detail_failed_ts'] > NOW for p in failed)
        m.cache.save(); m.cache.load()
        assert all('detail_failed_ts' in p for p in m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'].values() if p['row']['launchNumber'] in (754,751))
        recovered = next(row for row in swarm.rows if row['launchNumber'] == 754)
        async def recover(key): return {**fixture('launch_737'), **recovered} if key == recovered['id'] else await detail(key)
        swarm.fetch_launch = recover
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+244)
        assert 'detail_failed_ts' not in m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][recovered['id']]
    finally: await m.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failed_route', ['sites', 'policies'])
async def test_other_route_failure_does_not_back_off_launches(tmp_path, failed_route):
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        swarm.fail = {failed_route}
        failed, fetched = [], []
        m.cache.mark_failed = lambda tier, now: failed.append(tier)
        m.cache.mark_fetched = lambda tier, now: fetched.append(tier)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+1801)
        assert failed == [] and fetched == [TIER_SWARM_LAUNCHES]
        slot = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert slot[failed_route+'_ts'] == NOW and slot['launches_ts'] == NOW+1801
    finally: await m.close()


@pytest.mark.asyncio
async def test_malformed_site_project_is_read_once_and_none_persisted(tmp_path):
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    sites = fixture('sites')['sites']; site = next(s for s in sites if s['label'] == 'zto')
    async def fetch_sites(): return [site]
    async def job(key):
        swarm.calls.append(('site_job', key))
        return {**fixture('job_zto_site'), 'project': ['bad']}
    swarm.fetch_sites = fetch_sites; swarm.fetch_job = job
    m = manager(tmp_path, swarm)
    try:
        for i in range(2): await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61*i)
        assert swarm.calls.count(('site_job', site['jobId'])) == 1
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['sites'][site['id']] is None
        m.cache.save(); m.cache.load()
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['sites'][site['id']] is None
    finally: await m.close()


@pytest.mark.asyncio
async def test_site_created_gate_cadence_and_newest_link(tmp_path):
    from uuid import UUID
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    sites = fixture('sites')['sites']; zto = next(s for s in sites if s['label'] == 'zto'); adam = next(s for s in sites if s['label'] == 'adam')
    adam['createdAt'] = '2020-01-01T00:00:00Z'
    newer = {**zto, 'id': str(UUID(int=100)), 'label': 'new-zto', 'createdAt': '2026-10-06T01:00:00Z'}
    async def fetch_sites(): swarm.calls.append('sites'); return [adam, newer, zto]
    swarm.fetch_sites = fetch_sites
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61)
        assert ('site_job', adam['jobId']) not in swarm.calls
        assert swarm.calls.count('sites') == 1
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['site_label'] == 'new-zto'
    finally: await m.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('explode', [False, True])
async def test_fix2_bad_workflow_match_preserves_tier_and_links(tmp_path, monkeypatch, caplog, explode):
    import logging
    from maxpane_dashboard.analytics import surf_launch_sites as ls
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SCORES
    swarm=LaunchSwarm(); swarm.rows=[fixture('launch_737')]
    async def sites(): return [s for s in fixture('sites')['sites'] if s['label']=='zto']
    swarm.fetch_sites=sites
    m=manager(tmp_path,swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        before=copy.deepcopy(m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload['site_links'])
        assert before
        m.cache.store_last_good(SLOT_SWARM_SCORES, {'workflows':fixture('workflows_100')['workflows'] + [{'frontendJobId':[1], 'contractsJobId':{}}], 'workflows_ts':NOW+1}, ts=NOW+1)
        if explode:
            def broken(*args): raise RuntimeError('synthetic matcher failure')
            monkeypatch.setattr(ls, 'match_sites', broken)
        with caplog.at_level(logging.WARNING):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+61)
        assert m._swarm_launch_read_ok is True
        after=m.cache.get_last_good(SLOT_SWARM_LAUNCHES)
        assert after.ts == NOW+61 and after.payload['site_links'] == before
        assert m._swarm_launch_events(m._swarm_launch_keys()['swarm_launch_rows']) is not None
        assert len([x for x in swarm.calls if isinstance(x,tuple) and x[0]=='detail']) == 1
        if explode:
            assert len([r for r in caplog.records if 'site match failed' in r.message]) == 1
    finally: await m.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['hook', 'renamed', 'policy_outage'])
async def test_fix2_legacy_cached_checks_rejudged_without_rereading_detail(tmp_path, case):
    from maxpane_dashboard.analytics import surf_launch_checks as lc
    swarm=LaunchSwarm(); row=fixture('launch_737')
    if case in ('hook','policy_outage'): row.update(kind='univ4_hook', policyVersion=19)
    swarm.rows=[row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch=detail
    m=manager(tmp_path,swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW)
        entry=m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS)
        point=entry.payload['launches'][row['id']]
        if case == 'renamed':
            for artifact in row['artifacts']: artifact['name'] += '_renamed'
            point['row']=copy.deepcopy(row)
        point['checks']['K2']['state']='fail' if case != 'renamed' else 'pass'
        point['checks']['K3']['state']='pass'
        for key in ('K2','K3'): point['checks'][key]['evidence'].pop('rule_version')
        # A vacuous legacy K3 verdict retained only na contracts.
        if case == 'renamed':
            for contract in point['checks']['K3']['evidence']['contracts']:
                contract.update(state='na', reason='not deployed by this launch')
        cached=m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        for policy in cached['policies']: policy.pop('kind')
        cached.pop('policies_schema', None)
        # The old algorithm already tried a policy refresh for this version.
        cached['policies_refreshed_for']={row['id']:row['policyVersion']}
        m.cache.save()
    finally: await m.close()
    swarm.calls=[]
    if case=='policy_outage': swarm.fail={'policies'}
    restored=manager(tmp_path,swarm)
    try:
        await restored._pool_swarm_launches({TIER_SWARM_LAUNCHES},NOW+61)
        actual=restored._swarm_launch_keys()['swarm_launch_rows'][0]
        assert not [c for c in swarm.calls if isinstance(c,tuple) and c[0]=='detail']
        assert swarm.calls.count('policies')==1
        if case=='renamed':
            assert actual['checks']['K3']['state']=='unknown'
            assert actual['verdict']['state']!='swarm'
        else:
            assert actual['checks']['K2']['state']==('unknown' if case=='policy_outage' else 'pass')
        assert actual['checks']['K3']['evidence']['contracts'][0]['state']==('na' if case=='renamed' else 'pass')
    finally: await restored.close()


@pytest.mark.asyncio
async def test_fix2_identical_successful_reads_reuse_site_match(tmp_path, monkeypatch):
    from maxpane_dashboard.analytics import surf_launch_sites as ls
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    async def sites(): return [s for s in fixture('sites')['sites'] if s['label']=='zto']
    swarm.fetch_sites = sites
    m = manager(tmp_path, swarm); calls = []; original = ls.match_sites
    def match(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(ls, 'match_sites', match)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        before = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+301)
        after = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert after['launches_ts'] > before['launches_ts']
        assert after['sites_ts'] > before['sites_ts']
        assert len(calls) == 1
        assert after['site_links_inputs'] == before['site_links_inputs']
        assert next(iter(after['site_links'].values()))['trusted'] is True
        facts = copy.deepcopy(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload)
        facts['launches'][swarm.rows[0]['id']]['requester'] = '0x'+'1'*40
        m.cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS, facts, ts=NOW+301)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+362)
        changed = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert len(calls) == 2
        assert next(iter(changed['site_links'].values()))['trusted'] is False
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_fix3_coverage_rpc_once_then_backoff_and_facts_change(tmp_path):
    swarm = LaunchSwarm()
    row = fixture('launch_737')
    for artifact in row['artifacts']:
        if artifact['role'] == 'token': artifact['name'] += '_renamed'
    swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    calls = []
    original = m.client.fetch_launch_evidence
    async def counted(hashes, addresses):
        calls.append((list(hashes), list(addresses)))
        return await original(hashes, addresses)
    m.client.fetch_launch_evidence = counted
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        assert len(calls) == 1 and calls[0][0]
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K3']['state'] == 'unknown'
        for cycle in range(1, 6):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + cycle * 60)
        assert len(calls) == 1
        m.cache.save(); m.cache.load(slot_coercers={SLOT_SWARM_LAUNCH_FACTS: sw.coerce_launch_facts_slot})
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 1799)
        assert len(calls) == 1
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 1800)
        assert len(calls) == 2
        row['updatedAt'] = '2026-10-06T01:00:00Z'
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 1860)
        assert len(calls) == 3
    finally: await m.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('unresolved', ['K2', 'K6'])
async def test_fix3_coverage_backoff_keeps_other_rpc_checks_live(tmp_path, unresolved):
    swarm = LaunchSwarm(); row = fixture('launch_737')
    row.update(kind='univ4_hook', policyVersion=19)
    swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        point = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
        assert point['checks']['K3']['state'] == 'unknown'
        point['checks'][unresolved]['state'] = 'unknown'
        calls = []; original = m.client.fetch_launch_evidence
        async def counted(hashes, addresses):
            calls.append((list(hashes), list(addresses)))
            return await original(hashes, addresses)
        m.client.fetch_launch_evidence = counted
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 60)
        assert len(calls) == 1 and calls[0][0] and not calls[0][1]
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks'][unresolved]['state'] != 'unknown'
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_old_shared_hook_unknown_settles_on_first_cycle(tmp_path, monkeypatch):
    from maxpane_dashboard.analytics import surf_launch_checks as lc
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_747')]
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        point = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][swarm.rows[0]['id']]
        point['checks']['K3']['state'] = 'unknown'
        point['checks']['K3']['evidence']['unmatched_artifacts'] = ['PoolInitializationGuard']
        point.pop('k3_retry_ts', None)  # the pre-G2 cache has no retry timestamp
        m.cache.save(); m.cache.load(slot_coercers={SLOT_SWARM_LAUNCH_FACTS: sw.coerce_launch_facts_slot})
        def forbidden(*_): raise AssertionError('terminal token creation evidence was hashed again')
        monkeypatch.setattr(lc, 'creation_match', forbidden)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 60)
        actual = m._swarm_launch_keys()['swarm_launch_rows'][0]
        assert actual['checks']['K3']['state'] == 'pass_immutables'
        assert actual['checks']['K3']['evidence']['unmatched_artifacts'] == []
        assert actual['verdict']['state'] == 'swarm'
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_unresolved_contract_still_retries_rpc(tmp_path):
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    m = manager(tmp_path, swarm)
    calls = []; original = m.client.fetch_launch_evidence
    async def unavailable(hashes, addresses):
        calls.append((list(hashes), list(addresses)))
        rpc = await original(hashes, addresses)
        if len(calls) == 1: rpc['codes'] = {}
        return rpc
    m.client.fetch_launch_evidence = unavailable
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K3']['state'] == 'unknown'
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 60)
        assert len(calls) == 2 and calls[-1][1]
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K3']['state'] == 'pass'
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_future_coverage_retry_timestamp_does_not_stall(tmp_path):
    swarm = LaunchSwarm(); row = fixture('launch_737')
    for artifact in row['artifacts']:
        if artifact['role'] == 'token': artifact['name'] += '_renamed'
    swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    calls = []; original = m.client.fetch_launch_evidence
    async def counted(hashes, addresses):
        calls.append((list(hashes), list(addresses)))
        return await original(hashes, addresses)
    m.client.fetch_launch_evidence = counted
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        point = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
        point['k3_retry_ts'] = NOW + 1000000
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + 60)
        assert len(calls) == 2
        actual = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
        assert actual['k3_retry_ts'] == NOW + 60
        assert actual['checks']['K3']['state'] == 'unknown'
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_live_kindless_policies_keep_ttl_and_schema_across_restart(tmp_path):
    swarm = LaunchSwarm(); row = fixture('launch_737'); row['kind'] = None; swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    original = swarm.fetch_launch_policies
    async def policies():
        values = await original()
        for policy in values: policy.pop('kind', None)
        return values
    swarm.fetch_launch_policies = policies
    m = manager(tmp_path, swarm)
    try:
        for cycle in range(6):
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW + cycle*61)
        assert swarm.calls.count('policies') == 1
        m.cache.save()
    finally: await m.close()
    m = SurfManager(clock=FakeClock(NOW+400), cache_path=str(tmp_path/'cache.json'), client=RPC(), pool4_client=FakePool4Client(), swarm_client=swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+400)
        assert swarm.calls.count('policies') == 1
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_foreign_kind_version_forces_manager_policy_refresh(tmp_path):
    swarm = LaunchSwarm(); row = fixture('launch_737'); row.update(kind='univ4_hook', policyVersion=27); swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    try:
        m.cache.store_last_good(SLOT_SWARM_LAUNCHES, {'policies':fixture('launch_policies')['policies'], 'policies_ts':NOW, 'policies_schema':1}, ts=NOW)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61)
        assert swarm.calls.count('policies') == 1
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K2']['state'] == 'unknown'
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_failed_match_retries_unchanged_inputs_and_dedupes_until_success(tmp_path, monkeypatch, caplog):
    import logging
    from maxpane_dashboard.analytics import surf_launch_sites as ls
    swarm = LaunchSwarm(); swarm.rows = [fixture('launch_737')]
    async def sites(): return [s for s in fixture('sites')['sites'] if s['label']=='zto']
    swarm.fetch_sites = sites
    original = ls.match_sites; calls = []; failure = [RuntimeError]
    def match(*args):
        calls.append(ls.site_match_key(*args))
        if failure[0]: raise failure[0]('synthetic failure')
        return original(*args)
    monkeypatch.setattr(ls, 'match_sites', match)
    m = manager(tmp_path, swarm)
    try:
        with caplog.at_level(logging.WARNING):
            for cycle in range(3): await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+cycle*61)
            assert len(calls) == 3 and len(set(calls)) == 1
            logs = lambda: [r for r in caplog.records if 'site match failed' in r.message]
            assert len(logs()) == 1
            failure[0] = ValueError
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+183)
            assert len(logs()) == 2
            failure[0] = RuntimeError
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+244)
            assert len(logs()) == 2
            failure[0] = None
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+305)
            assert m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload['site_links_inputs']
            m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload['site_links_inputs'] = None
            failure[0] = RuntimeError
            await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+366)
            assert len(logs()) == 3
    finally: await m.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [False, True])
async def test_fix3_legacy_policy_migration_runs_once_without_erasing_last_good(tmp_path, failed):
    swarm = LaunchSwarm(); row = fixture('launch_737'); row['kind'] = None; swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    old = fixture('launch_policies')['policies']
    for policy in old: policy.pop('kind', None)
    async def policies():
        swarm.calls.append('policies')
        return None if failed else copy.deepcopy(old)
    swarm.fetch_launch_policies = policies
    m = manager(tmp_path, swarm)
    try:
        m.cache.store_last_good(SLOT_SWARM_LAUNCHES, {'policies':old, 'policies_ts':NOW}, ts=NOW)
        for cycle in range(1, 7): await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+cycle*61)
        assert swarm.calls.count('policies') == 1
        slot = m.cache.get_last_good(SLOT_SWARM_LAUNCHES).payload
        assert slot['policies'] and slot['policies_schema'] == 1
        assert slot['policies_ts'] == (NOW if failed else NOW+61)
        assert m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']['K2']['state'] == 'pass'
    finally: await m.close()


@pytest.mark.asyncio
async def test_fix3_cached_pooled_checks_rejudged_once_preserving_k3(tmp_path):
    swarm = LaunchSwarm(); row = fixture('launch_737'); row['kind'] = None; swarm.rows = [row]
    async def detail(_): return copy.deepcopy(row)
    swarm.fetch_launch = detail
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        point = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
        k3 = copy.deepcopy(point['checks']['K3'])
        point['checks']['K2']['state'] = 'fail'
        point['checks']['K2']['evidence']['rule_version'] = 2
        point['checks']['K6']['evidence'].update(owner_is_factory=True, rule_version=2)
        m.cache.save()
    finally: await m.close()
    m = manager(tmp_path, swarm); calls = []
    original = m.client.fetch_launch_evidence
    async def rpc(hashes, addresses):
        calls.append((hashes, addresses)); return await original(hashes, addresses)
    m.client.fetch_launch_evidence = rpc
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61)
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+122)
        checks = m._swarm_launch_keys()['swarm_launch_rows'][0]['checks']
        assert checks['K2']['state'] == 'pass' and checks['K6']['evidence']['owner_is_factory'] is False
        assert checks['K3'] == k3
        assert len(calls) == 1 and calls[0][1] == []
    finally: await m.close()


@pytest.mark.asyncio
async def test_initialize_fee_and_liquidity_contract_reach_snapshot(tmp_path):
    m = manager(tmp_path)
    m.swarm_client.rows = [fixture('launch_737'), next(r for r in fixture('launches_100')['launches'] if r['chainId'] == 11155111)]
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        rows = m._swarm_launch_keys()['swarm_launch_rows']
        production = next(r for r in rows if r['production'])
        sepolia = next(r for r in rows if not r['production'])
        assert production['pool_fee'] == 12500
        assert production['liquidity']['state'] == 'unknown'
        assert production['checks']['K8'] == production['liquidity']
        assert sepolia['liquidity'] is None
        m.cache.save()
        restored = manager(tmp_path)
        try:
            row = next(r for r in restored._swarm_launch_keys()['swarm_launch_rows'] if r['production'])
            assert row['pool_fee'] == 12500
        finally:
            await restored.close()
    finally:
        await m.close()
