import copy
import uuid
from tests.analytics.test_surf_launch_checks import fixture, checked
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SurfCache

def test_launch_slots_drop_corrupt_entries_and_bound_raw_fields():
    row, facts, checks = checked()
    facts.update(row=row, checks=checks, detail_version=[row['status'], row['updatedAt']])
    facts['rewardSnapshot'] = 'must not persist'
    clean = sw.coerce_launch_facts_slot({'launches': {row['id']: facts, 'bad': facts}, 'sites': {}})
    assert list(clean['launches']) == [row['id']]
    assert 'rewardSnapshot' not in clean['launches'][row['id']]
    assert 'attestation' not in clean['launches'][row['id']]['row']
    corrupt = copy.deepcopy(facts); corrupt['checks']['K2']['state'] = 'safe'
    assert sw.coerce_launch_facts_slot({'launches': {row['id']: corrupt}, 'sites': {}})['launches'] == {}

def test_launch_baselines_have_500_uuid_cap_and_deep_copies():
    cache = SurfCache()
    ids = [str(uuid.UUID(int=i+1)) for i in range(600)]
    point = {'ts': 100, 'number': 737, 'ticker': 'ZTO', 'chain_id': 1, 'token_address': fixture('launch_737')['artifacts'][2]['address'], 'verdict_state': 'swarm', 'verdict_passed': 4, 'verdict_failed': None}
    cache.set_baselines({'swarm_live_seen': ids, 'swarm_launch_pending': ids, 'swarm_launch_high_water': 800, 'swarm_launch_fired': {ids[-1]: point, 'bad': point}}, now=101)
    actual = cache.get_baselines()
    assert actual['swarm_live_seen'] == ids[-500:]
    assert actual['swarm_launch_pending'] == ids[-500:]
    assert set(actual['swarm_launch_fired']) == {ids[-1]}
    actual['swarm_live_seen'].clear(); actual['swarm_launch_fired'][ids[-1]]['ticker'] = 'bad'
    assert len(cache.get_baselines()['swarm_live_seen']) == 500
    assert cache.get_baselines()['swarm_launch_fired'][ids[-1]]['ticker'] == 'ZTO'

def test_persisted_launch_facts_and_baselines_reload_bounded(tmp_path):
    row, facts, checks=checked()
    facts.update(row=row, checks=checks, detail_version=[row['status'], row['updatedAt']])
    points={}
    for i in range(600):
        point=copy.deepcopy(facts); key=str(uuid.UUID(int=i+1)); point['row'].update(id=key,launchNumber=i)
        points[key]=point
    clean=sw.coerce_launch_facts_slot({'launches':points,'sites':{}})
    assert len(clean['launches'])==500
    assert min(p['row']['launchNumber'] for p in clean['launches'].values())==100
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_FACTS
    path=str(tmp_path/'cache.json'); cache=SurfCache(path=path,clock=lambda:101)
    cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS,clean,ts=100)
    cache.set_baselines({'swarm_live_seen':list(points)},now=101); cache.save()
    restored=SurfCache(path=path,clock=lambda:101)
    restored.load(slot_coercers={SLOT_SWARM_LAUNCH_FACTS:sw.coerce_launch_facts_slot})
    assert restored.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload==clean
    assert len(restored.get_baselines()['swarm_live_seen'])==500

def test_invalid_nested_check_evidence_is_refused():
    row,facts,checks=checked(); facts.update(row=row,checks=checks,detail_version=[row['status'],row['updatedAt']])
    checks['K3']['evidence']['contracts']='not contracts'
    assert sw.coerce_launch_facts_slot({'launches':{row['id']:facts},'sites':{}})['launches']=={}

def test_route_data_without_valid_read_time_is_not_presented_as_read():
    raw={'launches':[fixture('launch_737')], 'launches_ts':float('nan'), 'sites':[], 'sites_ts':100}
    slot=sw.coerce_launches_slot(raw,now=101)
    assert slot['launches'] is None and slot['launches_ts'] is None
    assert slot['sites']==[] and slot['sites_ts']==100
