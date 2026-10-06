import pytest
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


def test_launch_links_and_content_memo_roundtrip_and_invalid_rejected(tmp_path):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCHES
    launch = fixture('launch_737'); site = fixture('sites')['sites'][0]
    raw = {'launches': [launch], 'launches_ts': 100, 'sites': [site], 'sites_ts': 100,
           'site_links': {site['id']: {'launch_id': launch['id'], 'method': 'named', 'trusted': True}},
           'site_links_inputs': 'a'*64}
    clean = sw.coerce_launches_slot(raw, now=101)
    assert clean['site_links'] == raw['site_links']
    assert clean['site_links_inputs'] == raw['site_links_inputs']
    cache = SurfCache(path=str(tmp_path/'links.json'), clock=lambda: 101)
    cache.store_last_good(SLOT_SWARM_LAUNCHES, clean, ts=100); cache.save()
    cache.load(slot_coercers={SLOT_SWARM_LAUNCHES: lambda value: sw.coerce_launches_slot(value, now=101)})
    assert cache.get_last_good(SLOT_SWARM_LAUNCHES).payload == clean
    clean['site_links'][site['id']]['trusted'] = False
    assert raw['site_links'][site['id']]['trusted'] is True
    for field, invalid in [('site_links', {'bad': {'launch_id': launch['id'], 'method': 'named', 'trusted': True}}),
                           ('site_links', {site['id']: {'launch_id': launch['id'], 'method': 'named', 'trusted': 1}})]:
        bad = dict(raw, **{field: invalid})
        result = sw.coerce_launches_slot(bad, now=101)
        assert result['site_links'] == {} and result['site_links_inputs'] is None
    for legacy in ({'launches_ts':100,'sites_ts':100,'facts_ts':100,'workflows_ts':None}, None, 'bad', 'A'*64):
        result = sw.coerce_launches_slot(dict(raw, site_links_inputs=legacy), now=101)
        assert result['site_links'] == raw['site_links']
        assert result['site_links_inputs'] is None


def test_live_number_map_is_strict_bounded_and_not_shared(tmp_path):
    ids = [str(uuid.UUID(int=i+1)) for i in range(600)]
    cache = SurfCache(path=str(tmp_path/'numbers.json'), clock=lambda: 101)
    cache.set_baselines({'swarm_live_numbers': dict(zip(ids, range(600)))}, now=101)
    numbers = cache.get_baselines()['swarm_live_numbers']
    assert numbers == dict(zip(ids[100:], range(100, 600)))
    numbers[ids[-1]] = 0
    assert cache.get_baselines()['swarm_live_numbers'][ids[-1]] == 599
    for invalid in ([], {'bad': 737}, {ids[0]: True}, {ids[0]: -1}, {ids[0]: '737'}):
        cache.set_baselines({'swarm_live_numbers': invalid}, now=101)
        cache.save(); cache.load()
        assert cache.get_baselines()['swarm_live_numbers'] is None


def test_per_contract_progress_survives_cache_and_rejects_invalid_states(tmp_path):
    from maxpane_dashboard.analytics import surf_launch_checks as lc
    from maxpane_dashboard.data.keccak import keccak256
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_FACTS
    row, facts, checks = checked(747)
    checks['K3']['state'] = 'unknown'
    facts.update(row=row, checks=checks, detail_version=[row['status'],row['updatedAt']])
    cache = SurfCache(path=str(tmp_path/'contracts.json'), clock=lambda: 101)
    cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS, {'launches':{row['id']:facts},'sites':{}}, ts=100); cache.save()
    cache.load(slot_coercers={SLOT_SWARM_LAUNCH_FACTS: sw.coerce_launch_facts_slot})
    restored = cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
    assert restored['checks']['K3']['evidence']['contracts'][0]['state'] == 'pass_immutables'
    def forbidden(_): raise AssertionError('persisted passing contract rehashed')
    again = lc.check_launch(row, restored, [], {}, keccak=forbidden, previous=restored['checks'])
    # The persisted token match settles coverage without hashing the shared hook.
    assert again['K3']['state'] == 'pass_immutables'
    assert again['K3']['evidence']['contracts'][0]['state'] == 'pass_immutables'
    for invalid in ('safe', 3, {'state':'pass'}):
        facts['checks']['K3']['evidence']['contracts'][0]['state'] = invalid
        assert sw.coerce_launch_facts_slot({'launches':{row['id']:facts}, 'sites':{}})['launches'] == {}


def test_refresh_versions_and_failure_timestamps_are_strict_and_bounded():
    launch = fixture('launch_737'); key = launch['id']
    for version in (None, 99):
        assert sw.coerce_launches_slot({'policies_refreshed_for': {key: version}})['policies_refreshed_for'] == {key:version}
    for invalid in (True, -1, '99', {}):
        assert sw.coerce_launches_slot({'policies_refreshed_for': {key: invalid}})['policies_refreshed_for'] == {}
    ids = [str(uuid.UUID(int=i+1)) for i in range(600)]
    assert len(sw.coerce_launches_slot({'policies_refreshed_for': dict.fromkeys(ids, None)})['policies_refreshed_for']) == 500
    for stamp in (float('nan'), float('inf'), -1, True, 'now'):
        clean = sw.coerce_launch_facts_slot({'launches':{key:{'row':launch,'detail_failed_ts':stamp}}, 'sites':{}})
        assert 'detail_failed_ts' not in clean['launches'][key]


def test_fix2_policy_kind_and_unmatched_artifact_evidence_survive_cache(tmp_path):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCHES, SLOT_SWARM_LAUNCH_FACTS
    from maxpane_dashboard.analytics import surf_launch_checks as lc
    from maxpane_dashboard.data.keccak import keccak256
    row,facts,_=checked()
    row['artifacts']=[{**a,'name':a['name']+'_renamed'} for a in row['artifacts']]
    checks=lc.check_launch(row,facts,fixture('launch_policies')['policies'],{},keccak=keccak256)
    facts.update(row=row,checks=checks,detail_version=[row['status'],row['updatedAt']])
    cache=SurfCache(path=str(tmp_path/'cache.json'),clock=lambda:101)
    cache.store_last_good(SLOT_SWARM_LAUNCHES, {'policies':fixture('launch_policies')['policies'],'policies_ts':100},ts=100)
    cache.store_last_good(SLOT_SWARM_LAUNCH_FACTS, {'launches':{row['id']:facts},'sites':{}},ts=100)
    cache.save(); cache.load(slot_coercers={SLOT_SWARM_LAUNCHES:sw.coerce_launches_slot,SLOT_SWARM_LAUNCH_FACTS:sw.coerce_launch_facts_slot})
    assert {p['kind'] for p in cache.get_last_good(SLOT_SWARM_LAUNCHES).payload['policies']}=={p['kind'] for p in fixture('launch_policies')['policies']}
    persisted=cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]['checks']['K3']
    assert persisted['state']=='unknown'
    assert persisted['evidence']['unmatched_artifacts']==checks['K3']['evidence']['unmatched_artifacts']
    assert persisted['evidence']['rule_version']==2


@pytest.mark.parametrize('stamp', [True, '123', -1, 0, float('nan'), float('inf')])
def test_fix3_coverage_retry_timestamp_rejects_invalid(stamp):
    row = fixture('launch_737')
    point = {'row': row, 'k3_retry_ts': stamp}
    clean = sw.coerce_launch_facts_slot({'launches': {row['id']: point}, 'sites': {}})
    assert 'k3_retry_ts' not in clean['launches'][row['id']]
