import json
from pathlib import Path
import pytest
from maxpane_dashboard.data import surfboard as hub

ROOT=Path(__file__).parents[1]/'fixtures/surf/swarm/hub'
def capture(name):return json.loads((ROOT/(name+'.json')).read_text())

@pytest.mark.parametrize('name',['bad_partition','duplicate_records','missing_records','malformed_records'])
def test_outcome_snapshot_rejected_whole(name):
    assert hub.normalize_records(capture(name)) is None

def test_canonical_summary_acceptance_and_integer_ranking():
    records=hub.normalize_records(capture('records'))
    outcome=hub.seat_outcome(records,420)
    assert outcome['accepted']==3253 and outcome['attempts']==3392
    assert outcome['rank']==1 and outcome['ranked_of']==2
    assert hub.seat_outcome(records,1836)['attempts']==1
    assert hub.seat_outcome(records,0)['listed'] is False
    assert hub.normalize_records(capture('empty_records'))=={'count':0,'seats':[]}

def test_overview_bad_seat_outcomes_do_not_contaminate_network_facts():
    value=hub.normalize_overview(capture('overview'))
    assert value['overview']['agents_online']==864
    assert value['overview']['jobs_24h']==1134
    assert 'seats' not in value
    assert len(value['events'])==6
    assert [x['timestamp'] for x in value['events']]==sorted(x['timestamp'] for x in value['events'])

def test_hourly_missing_bucket_unknown_and_real_zero():
    assert hub.normalize_hourly(capture('hourly'))['points'][-1]==30326
    bad=capture('hourly');bad['accepted'].pop()
    assert hub.normalize_hourly(bad) is None

def test_source_validation_rechecks_payload_not_only_hash():
    raw=hub.normalize_records(capture('records'))
    value=hub.source_envelope(raw,100)
    assert hub.coerce_source(value,'records',now=101)==value
    value['payload']['seats'][0]['accepted']=999999
    assert hub.coerce_source(value,'records',now=101) is None

@pytest.mark.parametrize('field,value',[('attempts',-1),('accepted',1.0),('rejected',True),('failed',float('nan')),('pending',None)])
def test_every_outcome_counter_is_a_strict_nonnegative_integer(field,value):
    raw=capture('records');raw['seats'][0][field]=value
    assert hub.normalize_records(raw) is None


def test_duplicate_normalized_ids_and_count_mismatch_reject_whole_snapshot():
    raw=capture('records');raw['seats'][1]['tokenId']='001836'
    assert hub.normalize_records(raw) is None
    raw=capture('records');raw['count']=1
    assert hub.normalize_records(raw) is None


def test_equal_accepted_uses_exact_integer_fraction_then_token():
    raw={'count':3,'seats':[
        {'tokenId':3,'attempts':10**18+1,'accepted':1,'rejected':10**18,'failed':0,'pending':0},
        {'tokenId':2,'attempts':10**18,'accepted':1,'rejected':10**18-1,'failed':0,'pending':0},
        {'tokenId':1,'attempts':10**18,'accepted':1,'rejected':10**18-1,'failed':0,'pending':0}]}
    assert [r['token_id'] for r in hub.normalize_records(raw)['seats']]==[1,2,3]


def test_canonical_board_survives_missing_effort_and_presence():
    records=hub.normalize_records(capture('records'))
    rows,summary=hub.canonical_board(records,None,None)
    assert summary['accepted']==3254 and summary['attempts']==3393
    assert summary['receipt_accepted'] is None and summary['live'] is None
    assert rows[0]['failed']==21 and rows[0]['turns'] is None


def test_recorded_zero_population_is_a_real_empty():
    rows,summary=hub.canonical_board(hub.normalize_records(capture('empty_records')),None,None)
    assert rows==[] and summary['seats']==summary['attempts']==summary['accepted']==0


def test_fleet_work_duration_uses_all_contributors_not_just_ranked_seats():
    from tests.surf_swarm_fixtures import swarm_board_payload
    data = swarm_board_payload()  # 101 contributor devices, only two ranked seats
    card = next(c for c in hub.cards(data, {}, now=100) if c['key'] == 'board')
    assert card['meter_kind'] == 'duration'
    assert card['numerator'] == 1614366561
    assert card['denominator'] is None
    assert card['fleet_summary']['state'] == 'unavailable'
    assert 'contributors read' in card['detail']


@pytest.mark.parametrize('value,expected', [(0, 0), (None, None), (-1, None), (True, None), (float('nan'), None)])
def test_fleet_work_duration_keeps_unknown_distinct_from_zero(value, expected):
    card = next(c for c in hub.cards({'swarm_board_summary': {'wall_clock_ms': value}}, {}, now=100)
                if c['key'] == 'board')
    assert card['numerator'] == expected


def test_rack_meters_use_real_denominators_uncapped_population_and_split():
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
    data={f'sig_{name}_state':'ok' for name in SIGNAL_NAMES}
    data[f'sig_{SIGNAL_NAMES[0]}_state']='fired'
    data.update(swarm_seat_selected={'token_id':420},swarm_seat_outcome=hub.seat_outcome(hub.normalize_records(capture('records')),420),
                swarm_board_summary={'seats':2,'attempts':3393,'accepted':3254},
                pool4_vault_assets=20,pool4_total_supply=100,pool4_total_burned=2,pool4_total_rewarded=3,pool4_total_fee_token=5)
    cards={c['key']:c for c in hub.cards(data,{},now=100)}
    assert (cards['announce']['numerator'],cards['announce']['denominator'])==(1,len(SIGNAL_NAMES))
    assert (cards['agent']['numerator'],cards['agent']['denominator'])==(None,86400)
    assert (cards['board']['numerator'],cards['board']['denominator'])==(None,None)
    assert cards['oracles']['numerator'] is cards['oracles']['denominator'] is None
    assert cards['oracles']['points'] is None
    assert cards['pool4']['share_price'] is None
    assert cards['pool4']['numerator'] is cards['pool4']['denominator'] is None
    assert 'protocol' not in cards
    assert cards['surf-nft']['primary'] == '—'
    assert not {c['key'] for c in cards.values() if c['status']=='planned'}
    assert 'portfolio' not in cards and cards['work']['status']=='unavailable'
    assert 'earnings' not in cards


def test_unknown_detector_prevents_a_false_zero_bar():
    cards=hub.cards({}, {}, now=100)
    assert cards[0]['numerator'] is cards[0]['denominator'] is None


@pytest.mark.parametrize('state,partial,rows,primary,secondary,status,meter', [
    ('unavailable', False, None, '—', 'in progress', 'unavailable', 'unavailable'),
    ('ok', False, [], '0', 'in progress', 'idle', 'ok'),
    ('ok', False, ['assessing', 'attested', 'mismatch'], '1', 'in progress', 'assessing', 'ok'),
    ('ok', True, ['assessing'] * 7 + ['attested'] * 86 + ['blocked'] * 7,
     '7', 'in progress', 'assessing', 'partial'),
    ('stale', True, ['assessing', 'attested'], '1', 'in progress', 'stale', 'stale'),
])
def test_oracle_card_counts_only_loaded_rows_and_retains_source_state(
        state, partial, rows, primary, secondary, status, meter):
    snapshot = dict(state=state, partial=partial, read_ts=900 if rows is not None else None,
                    rows=[dict(status=s, chain_id=1 if i % 2 == 0 else 8453) for i, s in enumerate(rows)] if rows is not None else None)
    cards = {row['key']: row for row in hub.cards(dict(surf_oracles=snapshot), {}, now=1000)}
    row = cards['oracles']
    assert 'launchpad' not in cards
    assert row['title'] == 'ORACLES' and row['destination'] == 'oracles'
    assert (row['primary'], row['secondary'], row['status']) == (primary, secondary, status)
    assert row['meter_kind'] == 'oracles' and row['meter_state'] == meter
    assert row['numerator'] == (min(len(rows), 2) if rows is not None else None)
    assert row['denominator'] == (len(rows) if rows is not None else None)
    assert 'newest 100' in row['detail']
    assert 'stale' not in row['detail'] and 'unavailable' not in row['detail']
    if meter == 'partial':
        assert 'partial' in row['detail']
    if rows is not None:
        assert f'read {hub.hhmm(900)}' in row['detail']
        for name in set(rows):
            assert f'{rows.count(name)} {name}' in row['detail']


@pytest.mark.parametrize('chain_ids,expected', [
    ([1, 1, 8453], 2), ([4663], 1), ([], 0), ([1, None], None),
    ([1, True], None), ([1, '8453'], None), ([1, 0], None),
])
def test_oracle_card_counts_distinct_known_chains(chain_ids, expected):
    snapshot = dict(state='ok', partial=False, rows=[
        dict(status='assessing', chain_id=chain) for chain in chain_ids])
    card = next(row for row in hub.cards(dict(surf_oracles=snapshot), {}, now=1000)
                if row['key'] == 'oracles')
    assert card['numerator'] == expected


@pytest.mark.parametrize('jobs,workflows,status,subtitle', [
    (5, 1, 'active', '1 workflow'), (0, 0, 'idle', '0 workflows'),
    (12, 3, 'active', '3 workflows'),
])
def test_work_card_projects_loaded_counts(jobs, workflows, status, subtitle):
    summary = dict(jobs=jobs, workflows=workflows, seats=9, build=5, review=4, blocked=11)
    source = dict(state='ok', read_ts=90, summary=summary, partial=True,
                  jobs_loaded=100, workflows_loaded=100, details_loaded=24, details_expected=42)
    cards = hub.cards({'surf_work': source}, {}, now=100)
    row = next(c for c in cards if c['key']=='work')
    assert (row['title'], row['destination'], row['meter_kind']) == ('WORK IN PROGRESS', 'work', 'work')
    assert (row['primary'], row['secondary'], row['status'], row['meter_state']) == (str(jobs), subtitle, status, 'ok')
    assert row['work_summary'] == summary
    assert all(c['work_summary'] is None for c in cards if c['key']!='work')
    assert '100 jobs' in row['detail'] and '100 workflows' in row['detail']
    assert '24/42 details' in row['detail'] and 'partial' in row['detail']
    assert f'read {hub.hhmm(90)}' in row['detail'] and 'Enter to open' in row['detail']


def test_work_card_preserves_stale_and_unknown_counts_without_false_zero():
    summary = dict(jobs=5, workflows=1, seats=None, build=None, review=None, blocked=11)
    stale = dict(state='stale', read_ts=90, summary=summary, partial=True,
                 jobs_loaded=100, workflows_loaded=100, details_loaded=24, details_expected=42)
    row = next(c for c in hub.cards({'surf_work': stale}, {}, now=300) if c['key']=='work')
    assert (row['primary'], row['secondary'], row['status'], row['meter_state']) == ('5', '1 workflow', 'stale', 'stale')
    assert row['work_summary']['build'] is row['work_summary']['review'] is None
    unknown = next(c for c in hub.cards({}, {}, now=300) if c['key']=='work')
    assert (unknown['primary'], unknown['secondary'], unknown['status'], unknown['meter_state']) == ('—', '— workflows', 'unavailable', 'unavailable')
    assert all(value is None for value in unknown['work_summary'].values())


@pytest.mark.parametrize('kind,age,expected', [
    ('self', 0, True), ('self', 86399, True), ('self', 86400, False),
    ('self', -1, False), ('answer', 0, False), ('reply', 0, False), ('failed', 0, False),
])
def test_latest_announcement_controls_freshness_not_replies(kind, age, expected):
    old = dict(kind='self', ts=1000, tx_hash='0x'+'a'*64, text='Original announcement')
    new = dict(kind=kind, ts=100000-age, tx_hash='0x'+'b'*64, text='Latest announcement')
    row = hub.cards({}, {}, now=100000, announce_items=[old, new])[0]
    assert row['title'] == 'SURFBOARD'
    assert row['primary'] == ('Latest announcement' if kind=='self' and age>=0 else 'Original announcement')
    assert (row['status']=='active') == expected
    assert row['secondary'] == ('1 new reply' if kind in ('reply','answer') and 0<=age<86400 else '0 new replies')


@pytest.mark.parametrize('items,footer', [
    (None,'unavailable'), ([], '0 new replies'),
    ([dict(kind='self',ts=99999,tx_hash='0x'+'a'*64)],'0 new replies'),
    ([dict(kind=kind,ts=99999,tx_hash='0x'+char*64)
      for kind,char in [('self','a'),('reply','b'),('answer','c')]],'2 new replies'),
    ([dict(kind=kind,ts=ts,tx_hash='0x'+char*64) for kind,ts,char in [
        ('answer',99999,'a'),('answer',99999,'A'),('reply',13601,'b'),
        ('reply',13600,'c'),('reply',100001,'d'),('action',99999,'e'),
        ('failed',99999,'f'),('fund',99999,'1')]],'2 new replies'),
    ([None,dict(kind='reply',ts=True,tx_hash='0x'+'a'*64),
      dict(kind='reply',ts=99999,tx_hash='bad')],'0 new replies'),
])
def test_announce_card_counts_unique_replies_and_answers_in_last_day(items,footer):
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
    data={f'sig_{name}_state':'fired' if i<5 else 'ok' for i,name in enumerate(SIGNAL_NAMES)}
    row=hub.cards(data,{},now=100000,announce_items=items)[0]
    assert row['primary']=='—' and row['secondary']==footer
    assert row['numerator']==5 and row['denominator']==len(SIGNAL_NAMES)
    assert '24h' in row['detail'] and 'cached' in row['detail']
    assert row['status']!='active'


def test_fleet_ignores_canonical_rank_and_selected_seat():
    records=hub.normalize_records(capture('records'))
    rows, summary=hub.canonical_board(records,None,None)
    data=dict(swarm_board_rows=list(reversed(rows)),swarm_board_summary=summary,
              swarm_seat_selected={'token_id':1836},swarm_seat_outcome=hub.seat_outcome(records,1836))
    before = fleet_card(fleet_workers(), data=data)
    assert before['title'] == 'FLEET' and before['destination'] == 'board'
    assert 'accepted jobs' not in before['detail'] and 'top #' not in before['detail']
    for missing in (None, []):
        data['swarm_board_rows'] = missing
        assert fleet_card(fleet_workers(), data=data) == before


@pytest.mark.parametrize('summary,primary,secondary,status', [
    ({}, '—', '—', 'unavailable'),
    (dict(deployed=0, building=0, mint_open=0), '0', '0 building', 'active'),
    (dict(deployed=20, building=3, mint_open=15, partial=True), '20', '3 building', 'active'),
    (dict(deployed=True, building=-1, mint_open=None), '—', '—', 'unavailable'),
])
def test_nft_card_keeps_unknown_zero_and_partial_counts_separate(summary, primary, secondary, status):
    rows = hub.cards({}, {}, now=100, nft_catalogue=summary)
    row = next(c for c in rows if c['key'] == 'surf-nft')
    assert (row['primary'], row['secondary'], row['status']) == (primary, secondary, status)
    assert row['destination'] == 'surf-nft'
    assert row['nft_summary'] == summary
    assert all(c['key'] != 'protocol' for c in rows)
    if summary.get('partial'):
        assert 'partial catalog' in row['detail']


@pytest.mark.parametrize('state,working,capacity,slots,status', [
    ('working', 2, 3, '2 of 3 slots', 'working'),
    ('idle', 0, 3, '0 of 3 slots', 'idle'),
    ('offline', 0, 0, 'offline', 'offline'),
    ('paused', 0, 3, '0 of 3 slots', 'idle'),
    ('paused', 1, 3, '1 of 3 slots', 'working'),
    ('working', 0, 3, '0 of 3 slots', 'idle'),
    ('working', None, 3, '— of 3 slots', 'unavailable'),
    ('working', True, 3, '— of 3 slots', 'unavailable'),
    ('working', 1, None, '1 of — slots', 'working'),
    ('working', 9, 3, '9 working', 'working'),
    (None, None, None, '— of — slots', 'unavailable'),
])
def test_agent_card_uses_the_selected_seat_live_slots(state, working, capacity, slots, status):
    from tests.data.test_surfboard_activity import workers
    outcome = hub.seat_outcome(hub.normalize_records(capture('records')), 420)
    data = dict(swarm_seat_selected={'token_id':420}, swarm_seat_outcome=outcome,
                swarm_seat_live=dict(live_state=state, working=working, max_concurrency=capacity),
                swarm_workers_as_of_hhmm='12:34')
    observed = hub.work_activity.observe(None, workers() if state == 'offline' else workers(working), now=200)
    cards = hub.cards(data, {'records':dict(state='stale', read_ts=100)}, now=200, activity=observed)
    agent = next(card for card in cards if card['key']=='agent')
    assert agent['primary']=='IDMD #420' and agent['secondary']==slots
    assert agent['status']==status
    assert (agent['numerator'],agent['denominator'])==(86400 if status == 'working' else None,86400)
    assert '95.9% accepted' in agent['detail'] and 'records read '+hub.hhmm(100) in agent['detail']
    assert 'stale' not in agent['detail'] and 'unavailable' not in agent['detail']
    assert 'workers' in agent['detail'] and '12:34' in agent['detail']


@pytest.mark.parametrize('price,expected', [(7.963529, 7.963529), (0,0), (None,None), (False,None), (-1,None), (float('inf'),None)])
def test_pool4_share_rate_uses_protocol_value_with_explicit_unknown(price,expected):
    row=next(c for c in hub.cards({'pool4_share_price':price},{},now=100) if c['key']=='pool4')
    assert row['share_price']==expected
    assert row['numerator'] is row['denominator'] is None
    assert (f'1 sIMD = {expected:,.6f} IMD' if expected is not None else '1 sIMD = — IMD') in row['detail']

@pytest.mark.parametrize('value',[1e300,-1e300,float('inf'),True])
def test_unrepresentable_timestamps_are_rejected_and_format_safely(value):
    assert hub.timestamp(value) is None
    assert hub.hhmm(value)=='—'
    raw=capture('hourly');raw['until']=value
    assert hub.normalize_hourly(raw) is None


def test_corrupt_persisted_hourly_timestamp_is_rejected_even_with_matching_hash():
    payload=hub.normalize_hourly(capture('hourly'));payload['until']=1e300
    source=hub.source_envelope(payload,100)
    assert hub.coerce_source(source,'hourly',now=101) is None


def test_swarm_stale_hourly_retains_chart_and_discloses_both_read_clocks():
    sources={'overview':{'state':'ok','read_ts':200},'hourly':{'state':'stale','read_ts':100}}
    data={'surfboard_overview':{'agents_online':1,'working_now':0},'surfboard_hourly':{'points':[1]*8,'until':99}}
    card=next(c for c in hub.cards(data,sources,now=200) if c['key']=='swarm')
    assert card['status']=='stale' and card['points']==[1]*8
    assert 'overview read '+hub.hhmm(200) in card['detail']
    assert 'hourly · read '+hub.hhmm(100) in card['detail']
    assert 'stale' not in card['detail']


def test_degraded_pool4_never_labels_retained_numbers_active():
    data={'pool4_price_usd':2.0,'pool4_trailing_return_pct':3.0,'pool4_share_price':7.963529,'pool4_vault_assets':20,'pool4_total_supply':100,'degraded':['p4']}
    cards={c['key']:c for c in hub.cards(data,{},now=100)}
    assert cards['pool4']['status']=='stale'
    assert cards['pool4']['share_price']==7.963529


def test_overview_inference_tokens_uses_captured_network_count():
    raw = capture('overview')
    raw.update(capture('footer_counts'))
    assert hub.normalize_overview(raw)['overview']['inference_tokens'] == 189121393249


@pytest.mark.parametrize('value,expected', [(0, 0), (True, None), (-1, None), (1.5, None), ('123', None), (None, None)])
def test_inference_tokens_is_optional_strict_nonnegative_integer(value, expected):
    raw = capture('overview')
    raw['counts']['inferenceTokens'] = value
    assert hub.normalize_overview(raw)['overview']['inference_tokens'] == expected
    del raw['counts']['inferenceTokens']
    assert hub.normalize_overview(raw)['overview']['inference_tokens'] is None


@pytest.mark.parametrize('value', [True, -1, 1.5, '123'])
def test_restored_inference_tokens_rejects_invalid_values_even_with_matching_hash(value):
    payload = hub.normalize_overview(capture('overview'))
    payload['overview']['inference_tokens'] = value
    assert hub.coerce_source(hub.source_envelope(payload, 1000), 'overview', now=1001) is None


def test_legacy_overview_cache_load_preserves_data_and_source_clocks(tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    payload = hub.normalize_overview(capture('overview'))
    payload['overview'].pop('inference_tokens')
    old = hub.source_envelope(payload, 1000, provider_ts=990)
    old = hub.source_envelope(None, 1001, prior=old)
    path = tmp_path / 'legacy.json'
    cache = SurfCache(path=path, clock=lambda: 1002)
    cache.store_last_good(hub.SOURCE_SLOTS['overview'], old, ts=1001)
    cache.save()
    loaded = SurfCache(path=path, clock=lambda: 1002)
    loaded.load(slot_coercers={hub.SOURCE_SLOTS['overview']: lambda value: hub.coerce_source(value, 'overview', now=1002)})
    source = loaded.get_last_good(hub.SOURCE_SLOTS['overview']).payload
    assert source['payload'] == dict(payload, overview=dict(payload['overview'], inference_tokens=None))
    assert source['version'] == hub.version(source['payload']) != old['version']
    assert {k: v for k, v in source.items() if k not in ('payload', 'version')} == {
        'read_ts': 1000, 'provider_ts': 990, 'attempt_ts': 1001, 'state': 'stale',
    }
    assert hub.coerce_source(source, 'overview', now=1002) == source
    assert 'inference_tokens' not in old['payload']['overview']


@pytest.mark.parametrize('damage', ['tampered_hash', 'boolean_counter', 'missing_counter', 'bad_event_hash'])
def test_legacy_overview_cache_does_not_bless_tampered_or_malformed_data(damage):
    payload = hub.normalize_overview(capture('overview'))
    payload['overview'].pop('inference_tokens')
    old = hub.source_envelope(payload, 1000)
    if damage == 'tampered_hash':
        payload['overview']['agents_online'] += 1
    elif damage == 'boolean_counter':
        payload['overview']['agents_online'] = True
        old['version'] = hub.version(payload)
    elif damage == 'missing_counter':
        payload['overview'].pop('jobs')
        old['version'] = hub.version(payload)
    else:
        payload['events'][0]['objective'] = 'tampered'
        old['version'] = hub.version(payload)
    assert hub.coerce_source(old, 'overview', now=1001) is None


def test_current_overview_with_unknown_inference_count_roundtrips():
    raw = capture('overview')
    raw['counts'].pop('inferenceTokens')
    payload = hub.normalize_overview(raw)
    assert payload['overview']['inference_tokens'] is None
    source = hub.source_envelope(payload, 1000)
    assert hub.coerce_source(source, 'overview', now=1001) == source


def test_event_details_cover_all_seven_reference_kinds_without_invented_history():
    raw = capture('event_parity')
    events = {e['kind']: e for e in hub.normalize_overview(raw)['events']}
    assert set(events) == {'job', 'node', 'done', 'review', 'site', 'launch', 'agent'}
    assert events['job']['state'] == 'posted'
    assert events['job']['details'] == events['node']['details'] == {}
    assert events['done']['details'] == {'steps': 1}
    assert events['review']['details'] == {'scores': 3, 'accepted': 2}
    assert events['launch']['details'] == {'token': 'Slabs', 'launch_number': 791, 'chain_id': 4663}
    site = next(e for e in raw['events'] if e['kind'] == 'site')
    assert events['site']['details'] == {'ens_name': site['ensName'], 'cid': site['cid']}
    agent = events['agent']
    assert agent['details'] == {
        'seat_accepted': 662, 'seat_failed': 16,
        'last_work': hub.timestamp('2026-10-08T21:27:07.886Z'),
        'owner': raw['owners'][str(agent['token_id'])], 'owner_seats': len(raw['owners']),
    }
    payload = hub.normalize_overview(raw)
    source = hub.source_envelope(payload, 1000)
    assert hub.coerce_source(source, 'overview', now=1001) == source


def test_captured_failure_details_preserve_reason_and_zero_steps():
    raw = capture('event_parity')
    raw['events'] = capture('event_failures')
    events = hub.normalize_overview(raw)['events']
    assert [e['kind'] for e in events] == ['node', 'done']
    assert events[0]['state'] == 'failed'
    assert events[0]['details'] == {'reason': 'launch.json is not a valid launch manifest: pool.initialPrice: Invalid input: expected string, received undefined'}
    assert events[1]['details'] == {'steps': 0, 'failure': 'node build_contract_project: analysis_failed'}


@pytest.mark.parametrize('state', ['running', 'assigned', 'executing'])
def test_node_state_is_preserved_for_view_mapping(state):
    raw = capture('event_parity')
    raw['events'] = [dict(next(e for e in raw['events'] if e['kind'] == 'node'), state=state)]
    assert hub.normalize_overview(raw)['events'][0]['state'] == state


def test_metadata_changes_preserve_event_identity_but_update_source_version():
    raw = capture('event_parity')
    before = hub.normalize_overview(raw)
    next(e for e in raw['events'] if e['kind'] == 'launch')['token'] = 'Updated label'
    raw['seats']['961']['accepted'] += 1
    after = hub.normalize_overview(raw)
    assert [e['key'] for e in before['events']] == [e['key'] for e in after['events']]
    assert hub.version(before) != hub.version(after)
    for e in after['events']:
        assert e['key'] == hub.version({k: v for k, v in e.items() if k not in ('key', 'details')})


@pytest.mark.parametrize('reverse_input', [False, True])
def test_equal_timestamp_events_retain_reversed_api_order(reverse_input):
    raw = capture('event_parity')
    done = next(e for e in raw['events'] if e['kind'] == 'done')
    node = dict(next(e for e in raw['events'] if e['kind'] == 'node'), at=done['at'], state='accepted')
    raw['events'] = [done, node]
    if reverse_input:
        raw['events'].reverse()
    assert [e['kind'] for e in hub.normalize_overview(raw)['events']] == [e['kind'] for e in reversed(raw['events'])]


def test_agent_history_is_sparse_and_owner_holdings_are_case_insensitive():
    raw = capture('event_parity')
    agent = next(e for e in raw['events'] if e['kind'] == 'agent')
    raw['events'] = [agent]
    raw['seats'] = {'961': {'accepted': 0, 'failed': True, 'last': 'bad'}}
    owner = raw['owners']['961']
    owners = [None] * 962
    owners[961], owners[5], owners[6] = owner, '0x' + owner[2:].upper(), 'invalid'
    raw['owners'] = owners
    assert hub.normalize_overview(raw)['events'][0]['details'] == {'seat_accepted': 0, 'owner': owner, 'owner_seats': 2}
    del raw['seats']; del raw['owners']
    assert hub.normalize_overview(raw)['events'][0]['details'] == {}


@pytest.mark.parametrize('field,value', [('token', 1), ('ensName', True), ('cid', []), ('failure', None), ('reason', {}), ('launchNumber', True), ('chainId', -1), ('steps', 1.2), ('scores', '3'), ('accepted', float('inf'))])
def test_invalid_optional_event_details_are_omitted_at_live_boundary(field, value):
    raw = capture('event_parity')
    raw['events'] = [dict(kind='job', at=raw['events'][0]['at'], **{field: value})]
    assert hub.normalize_overview(raw)['events'][0]['details'] == {}


@pytest.mark.parametrize('details', [None, [], {'unknown': 'x'}, {'token': 1}, {'ens_name': True}, {'cid': None}, {'launch_number': True}, {'chain_id': -1}, {'steps': 1.1}, {'scores': '1'}, {'accepted': None}, {'seat_accepted': True}, {'seat_failed': -1}, {'owner_seats': False}, {'owner': 2}, {'last_work': '2026-10-09T00:00:00Z'}, {'last_work': 1e300}])
def test_persisted_event_details_reject_bad_shapes_even_with_matching_source_hash(details):
    payload = hub.normalize_overview(capture('event_parity'))
    payload['events'][0]['details'] = details
    assert hub.coerce_source(hub.source_envelope(payload, 1000), 'overview', now=1001) is None


def test_persisted_event_detail_nonfinite_value_is_rejected():
    source = hub.source_envelope(hub.normalize_overview(capture('event_parity')), 1000)
    source['payload']['events'][0]['details'] = {'last_work': float('nan')}
    assert hub.coerce_source(source, 'overview', now=1001) is None


@pytest.mark.parametrize('owner', ['invalid', '0x1234', '0x' + 'z' * 40])
def test_persisted_event_owner_must_be_valid_address(owner):
    payload = hub.normalize_overview(capture('event_parity'))
    payload['events'][0]['details'] = {'owner': owner}
    assert hub.coerce_source(hub.source_envelope(payload, 1000), 'overview', now=1001) is None


@pytest.mark.parametrize('without_tokens', [False, True])
def test_legacy_event_details_migrate_without_losing_identity_or_clocks(without_tokens):
    payload = hub.normalize_overview(capture('event_parity'))
    for row in payload['events']:
        row.pop('details', None)
    if without_tokens:
        payload['overview'].pop('inference_tokens')
    source = hub.source_envelope(payload, 1000, provider_ts=990)
    source = hub.source_envelope(None, 1001, prior=source)
    upgraded = hub.coerce_source(source, 'overview', now=1002)
    assert upgraded is not None
    assert upgraded['payload']['events'] == [dict(row, details={}) for row in payload['events']]
    assert upgraded['payload']['overview']['inference_tokens'] == (None if without_tokens else capture('event_parity')['counts']['inferenceTokens'])
    assert {k: v for k, v in upgraded.items() if k not in ('payload', 'version')} == {k: v for k, v in source.items() if k not in ('payload', 'version')}
    assert upgraded['version'] == hub.version(upgraded['payload'])
    assert hub.coerce_source(upgraded, 'overview', now=1002) == upgraded


@pytest.mark.parametrize('damage', ['envelope_hash', 'event_hash', 'invalid_present_details'])
def test_legacy_event_migration_does_not_bless_corruption(damage):
    payload = hub.normalize_overview(capture('event_parity'))
    for row in payload['events']:
        row.pop('details', None)
    source = hub.source_envelope(payload, 1000)
    if damage == 'envelope_hash':
        payload['overview']['jobs'] += 1
    elif damage == 'event_hash':
        payload['events'][0]['objective'] = 'tampered'
        source['version'] = hub.version(payload)
    else:
        payload['events'][0]['details'] = None
        source['version'] = hub.version(payload)
    assert hub.coerce_source(source, 'overview', now=1001) is None


@pytest.mark.parametrize('total,expected', [(0, '0 new'), (23, '23 new'), (None, 'unavailable')])
@pytest.mark.parametrize('state', ['ok', 'partial', 'stale'])
def test_tokens_card_new_count_uses_24h_catalogue_not_one_hour_events(total, expected, state):
    data = dict(as_of=10000, swarm_launch_fired=[dict(ts=10000, number=1210)])
    row = next(r for r in hub.cards(data, {}, now=10000,
        tokens_catalogue=dict(count=116, state=state, as_of=9900,
                             ranking=dict(total=total, state=state))) if r['key']=='swarm-tokens')
    assert (row['title'], row['primary'], row['secondary']) == (
        'TOKENS', '≥116' if state == 'partial' else '116', expected)
    assert row['destination'] == 'swarm-tokens'
    assert (row['status'] == 'active') == (total is not None and total > 0)
    assert 'last 24h' in row['detail'] and 'launch news 1h' not in row['detail']


@pytest.mark.parametrize('catalogue,primary', [
    (None, 'unavailable'), ({'count': 0, 'state': 'ok', 'as_of': 9900}, '0'),
    ({'count': 116, 'state': 'partial', 'as_of': 9900}, '≥116'),
    ({'count': 116, 'state': 'stale', 'as_of': 9900}, '116'),
])
def test_tokens_card_preserves_unknown_partial_and_stale_catalogue(catalogue, primary):
    row = next(r for r in hub.cards({}, {}, now=10000, tokens_catalogue=catalogue) if r['key']=='swarm-tokens')
    assert row['primary'] == primary
    assert row['secondary'] == 'unavailable'
    assert row['status'] != 'active'
    assert row['destination'] == 'swarm-tokens'
    assert 'catalogue read '+hub.hhmm((catalogue or {}).get('as_of')) in row['detail']
    assert 'stale' not in row['detail'] and 'unavailable' not in row['detail']


@pytest.mark.parametrize('ranked', [None, [], [dict(id='eth:token', age_s=7200,
    symbol='SFPT', chain='eth', volume_usd=12500, price_direction='up')]])
def test_tokens_card_carries_ranking_and_keeps_count_in_detail(ranked):
    ranking = dict(rows=ranked, newest=dict(id='eth:new', age_s=120,
        symbol='NEW', chain='eth'), state='ok', read_ts=9900, known=1, total=1)
    cards = hub.cards({}, {}, now=10000, tokens_catalogue=dict(
        count=116, state='ok', as_of=9900, ranking=ranking))
    row = next(r for r in cards if r['key'] == 'swarm-tokens')
    assert row['token_ranking'] == ranking
    assert '116 tokens' in row['detail']
    assert all(r['token_ranking'] is None for r in cards if r['key'] != 'swarm-tokens')
    assert row['points'] is None and row['meter_kind'] == 'sparkline'
    assert row['meter_state'] == 'unavailable'


@pytest.mark.parametrize('direction,status', [('up','active'),('down','falling'),
    ('flat','idle'),(None,'idle')])
@pytest.mark.parametrize('change', [2.3, -2.3, 0, None, float('nan')])
def test_pool4_price_digits_follow_consecutive_reads_not_24h_change(direction, status, change):
    row = next(c for c in hub.cards(dict(pool4_price_usd=8.77, imd_price_usd=9.99,
        imd_change_24h_pct=change), {}, now=100, pool4_price_direction=direction) if c['key']=='pool4')
    assert (row['primary'], row['secondary'], row['status']) == ('8.77', 'USD', status)
    assert row['destination'] == 'pool4_user'
    assert '24h' in row['detail']


def test_nft_card_clock_and_count_do_not_depend_on_protocol_values():
    summary = dict(deployed=20, building=3, mint_open=15, partial=True, observed_at=50)
    def card(data, now):
        return next(c for c in hub.cards(data, {}, now=now, nft_catalogue=summary) if c['key']=='surf-nft')
    assert card({}, 100) == card(dict(pool4_total_burned=999, burn_ready=True), 200)
    assert 'read '+hub.hhmm(50) in card({}, 100)['detail']


def test_pool4_missing_price_never_shows_zero_or_green():
    row=next(c for c in hub.cards(dict(imd_change_24h_pct=2.3),{},now=100) if c['key']=='pool4')
    assert (row['primary'],row['secondary'],row['status']) == ('unavailable','USD','unavailable')


def test_fleet_duration_is_independent_of_selected_and_top_agent_activity():
    from maxpane_dashboard.data import surfboard_activity as activity
    from tests.data.test_surfboard_activity import workers
    data = dict(swarm_seat_selected={'token_id': 1836}, swarm_board_summary={'wall_clock_ms': 1614366561},
                swarm_board_rows=[dict(rank=1, token_id=420, accepted=3253)])
    observed = activity.observe(None, workers(1), now=100)
    rows = {c['key']: c for c in hub.cards(data, {}, now=100, activity=observed)}
    assert rows['board']['meter_state'] == 'unavailable'
    assert rows['board']['numerator'] == 1614366561 and rows['board']['denominator'] is None
    assert rows['agent']['meter_state'] == 'idle' and rows['agent']['numerator'] is None
    observed = activity.observe(observed, workers(0), now=200)
    observed = activity.observe(observed, workers(0), now=43400)
    rows = {c['key']: c for c in hub.cards(data, {}, now=43400, activity=observed)}
    assert rows['board']['numerator'] == 1614366561
    assert 'observed stop' not in rows['board']['detail'] and 'contributors read' in rows['board']['detail']
    rows = {c['key']: c for c in hub.cards(data, {}, now=43701, activity=observed)}
    assert rows['board']['meter_state'] == 'unavailable' and rows['board']['numerator'] == 1614366561


@pytest.mark.parametrize('selected_busy, top_busy', [(True, False), (False, True)])
def test_agent_activity_colors_do_not_govern_fleet(selected_busy, top_busy):
    from tests.data.test_surfboard_activity import workers
    read = workers(int(selected_busy), token=1836)
    read['workers'] += workers(int(top_busy), token=420)['workers']
    read['count'] = 2
    observed = hub.work_activity.observe(None, read, now=100)
    # Contradictory legacy states cannot override fresh positive/zero work.
    data = dict(swarm_seat_selected={'token_id':1836},
                swarm_seat_live={'live_state':'working'},
                swarm_board_rows=[dict(rank=1, token_id=420, accepted=3253, live_state='working')])
    rows = {c['key']: c for c in hub.cards(data, {}, now=100, activity=observed, workers=fleet_workers(),
               worker_source=dict(state='ok', read_ts=100))}
    assert rows['agent']['status'] == ('working' if selected_busy else 'idle')
    assert rows['agent']['meter_state'] == ('busy' if selected_busy else 'idle')
    assert rows['board']['status'] == 'idle' and rows['board']['meter_state'] == 'ok'


@pytest.mark.parametrize('selected_offline', [False, True])
def test_offline_identity_for_selected_seat_does_not_govern_fleet(selected_offline):
    from tests.data.test_surfboard_activity import workers
    observed = hub.work_activity.observe(None, workers(0, token=420 if selected_offline else 1836), now=100)
    data = dict(swarm_seat_selected={'token_id':1836},
                swarm_seat_live={'live_state':'offline' if selected_offline else 'idle'},
                swarm_board_rows=[dict(rank=1, token_id=420, accepted=3253,
                                       live_state='idle' if selected_offline else 'offline')])
    rows = {c['key']: c for c in hub.cards(data, {}, now=100, activity=observed, workers=fleet_workers(),
               worker_source=dict(state='ok', read_ts=100))}
    assert rows['agent']['status'] == rows['agent']['meter_state'] == ('offline' if selected_offline else 'idle')
    assert rows['board']['status'] == 'idle' and rows['board']['meter_state'] == 'ok'


def test_fresh_offline_changes_display_without_rewriting_activity_history():
    from copy import deepcopy
    from tests.data.test_surfboard_activity import workers
    observed = hub.work_activity.observe(None, workers(1), now=100)
    observed = hub.work_activity.observe(observed, workers(), now=200)
    before = deepcopy(observed)
    data = dict(swarm_seat_selected={'token_id':420},
                swarm_seat_live={'live_state':'offline'},
                swarm_board_rows=[dict(rank=1, token_id=420, accepted=3253, live_state='offline')])
    row = next(c for c in hub.cards(data, {}, now=300, activity=observed) if c['key'] == 'agent')
    assert row['meter_state'] == row['status'] == 'offline'
    assert (row['numerator'], row['denominator']) == (86300, 86400)
    assert 'activity offline' in row['detail'] and 'workers read '+hub.hhmm(200) in row['detail']
    assert 'observed stop '+hub.hhmm(200) in row['detail']
    assert observed == before


@pytest.mark.parametrize('failure, expected', [
    ('stale', 'stale'), ('failed', 'stale'), ('incomplete', 'unavailable'),
    ('unknown', 'unavailable'), ('missing', 'unavailable'),
])
def test_uncertain_activity_never_certifies_offline_for_agent(failure, expected):
    from tests.data.test_surfboard_activity import workers
    observed = hub.work_activity.observe(None, workers(), now=100)
    now = 401 if failure == 'stale' else 200
    if failure == 'failed':
        observed = hub.work_activity.observe(observed, None, now=now)
    elif failure == 'incomplete':
        partial = workers()
        partial['count'] = 1
        observed = hub.work_activity.observe(observed, partial, now=now)
    elif failure == 'unknown':
        observed = hub.work_activity.observe(observed, workers(None), now=now)
    elif failure == 'missing':
        observed = None
    data = dict(swarm_seat_selected={'token_id':420},
                swarm_seat_live={'live_state':'offline'},
                swarm_board_rows=[dict(rank=1, token_id=420, accepted=3253, live_state='offline')])
    rows = {c['key']: c for c in hub.cards(data, {}, now=now, activity=observed)}
    assert rows['agent']['status'] == rows['agent']['meter_state'] == expected
    assert rows['agent']['numerator'] is None
    assert rows['board']['status'] == 'unavailable'


def test_token_ranking_projection_discloses_coverage_and_source_clock():
    ranking = dict(rows=[dict(id='eth:token', age_s=7200, symbol='SFPT', chain='eth',
                             volume_usd=12500, price_direction='up')],
                   newest=None, state='partial', read_ts=90, known=8, total=10)
    source = dict(count=10, state='ok', as_of=100, ranking=ranking,
        volume=dict(points=[1]*8, state='ok', known=10, total=10, as_of=100))
    row = next(c for c in hub.cards({}, {}, now=100, tokens_catalogue=source) if c['key']=='swarm-tokens')
    assert row['token_ranking'] == ranking
    assert row['meter_kind'] == 'sparkline' and row['points'] == [1]*8
    assert row['meter_state'] == 'ok'
    assert 'USD' in row['detail'] and '8/10' in row['detail']
    assert 'partial' in row['detail'] and f'read {hub.hhmm(90)}' in row['detail']
    assert '12,500' in row['detail']
    assert 'all swarm tokens' in row['detail'] and '10/10' in row['detail']


def launchpad_volume_snapshot(**changes):
    return dict(dict(state='ok', points_wei=[i * 10**18 for i in range(8)],
                     read_ts=18010, head_ts=18000, until=18000, known=25, total=25), **changes)


def launchpad_volume_projection(snapshot=None, *, now=18020, price=2000, market=None, launch_state='ok'):
    points, state, detail = hub._launchpad_volume(
        dict(eth_usd=price), dict(volume_2h=snapshot), {
            'quote': market if market is not None else dict(state='ok', read_ts=now),
            'launchpad': dict(state=launch_state, read_ts=now)}, now)
    return dict(points=points, meter_state=state, detail=detail)


def test_launchpad_volume_uses_quote_clock_independently_of_pool_market():
    points, state, detail = hub._launchpad_volume(
        dict(eth_usd=2000), dict(volume_2h=launchpad_volume_snapshot()),
        dict(quote=dict(state='ok', read_ts=18010), market=dict(state='stale', read_ts=100),
             launchpad=dict(state='ok', read_ts=18000)), 18020)
    assert points == [i * 2000 for i in range(8)] and state == 'ok'
    assert 'quote read '+hub.hhmm(18010) in detail


def test_launchpad_volume_projects_eight_usd_buckets_and_retains_source_window():
    snapshot = launchpad_volume_snapshot()
    row = launchpad_volume_projection(snapshot)
    assert row['meter_state'] == 'ok'
    assert row['points'] == [i * 2000 for i in range(8)]
    for text in ('USD', '15m', 'current ETH/USD', '25/25', hub.hhmm(18000)):
        assert text in row['detail']
    assert snapshot == launchpad_volume_snapshot()


@pytest.mark.parametrize('snapshot,now,launch_state', [
    (launchpad_volume_snapshot(), 18611, 'ok'),
    (launchpad_volume_snapshot(), 18901, 'ok'),
    (launchpad_volume_snapshot(read_ts=18895, head_ts=18890), 18901, 'ok'),
    (launchpad_volume_snapshot(read_ts=18620), 18620, 'ok'),
    (launchpad_volume_snapshot(), 18020, 'stale'),
])
def test_launchpad_volume_stays_stale_after_expiry_new_slot_clock_or_failed_read(snapshot, now, launch_state):
    row = launchpad_volume_projection(snapshot, now=now, launch_state=launch_state)
    assert row['points'] == [i * 2000 for i in range(8)]
    assert row['meter_state'] == 'stale'


@pytest.mark.parametrize('price,market', [
    (None, None), (True, None), (0, None), (-2, None), (float('inf'), None),
    (float('nan'), None), (2000, {}), (2000, dict(state='unavailable', read_ts=None)),
    (2000, dict(state='stale', read_ts=18020)), (2000, dict(state='ok', read_ts=17900)),
    (2000, dict(state='ok', read_ts=18030)), (1e308, None),
])
def test_launchpad_volume_requires_fresh_positive_finite_usd_quote(price, market):
    row = launchpad_volume_projection(launchpad_volume_snapshot(), price=price, market=market)
    assert row['points'] is None and row['meter_state'] == 'unavailable'


@pytest.mark.parametrize('snapshot,state', [
    (None, 'unavailable'), ({}, 'unavailable'),
    (launchpad_volume_snapshot(points_wei=[True] * 8), 'unavailable'),
    (launchpad_volume_snapshot(points_wei=[-1] * 8), 'unavailable'),
    (launchpad_volume_snapshot(points_wei=[0] * 7), 'unavailable'),
    (launchpad_volume_snapshot(read_ts=19000), 'unavailable'),
    (launchpad_volume_snapshot(state='partial', points_wei=None, known=24), 'partial'),
])
def test_launchpad_volume_unknown_is_never_a_zero_chart(snapshot, state):
    row = launchpad_volume_projection(snapshot)
    assert row['points'] is None and row['meter_state'] == state


def test_launchpad_volume_complete_empty_intervals_are_real_zero():
    row = launchpad_volume_projection(launchpad_volume_snapshot(points_wei=[0] * 8))
    assert row['points'] == [0] * 8 and row['meter_state'] == 'ok'


def fleet_workers():
    """Three distinct seats, five devices; repeated IDs/pairs cannot earn extra votes."""
    from maxpane_dashboard.data.surf_swarm import normalize_workers
    pairs = [('model-a', 'low'), ('model-a', 'high'), ('model-b', 'medium'),
             ('model-b', 'medium'), ('model-b', 'medium')]
    rows = [dict(seat=dict(tokenId=token), deviceKey=str(i),
                 runtimes=[dict(id=runtime) for runtime in runtimes],
                 daemonVersion=daemon)
            for i, (token, runtimes, daemon) in enumerate([
                (7, ['codex', 'codex'], '0.1.2+first'),
                (7, ['codex'], '0.1.2+second'),
                (7, ['claude'], '0.1.2+third'),
                (8, ['claude'], '0.1.1+same'),
                (9, ['claude'], '0.1.1+same')])]
    workers = normalize_workers(dict(count=len(rows), workers=rows))
    for row, (model, effort) in zip(workers['workers'], pairs):
        row['advertised_models'] = [dict(model=model, effort=effort)] * 2
    return workers


def fleet_card(workers, *, state='ok', data=None, partial=False):
    return next(card for card in hub.cards(data or {}, {}, now=1000, workers=workers,
        worker_source=dict(state=state, read_ts=900, partial=partial)) if card['key'] == 'board')


def test_fleet_runtime_shares_use_distinct_online_seats_and_deduplicate_devices():
    from copy import deepcopy
    workers = fleet_workers()
    before = deepcopy(workers)
    card = fleet_card(workers)
    facts = card['fleet_summary']
    assert facts == dict(codex_percent=pytest.approx(100/3), claude_percent=100, daemon='0.1.2',
        model='model-b', effort='medium', online=3, runtime_known=3, state='ok', read_ts=900)
    assert card['destination'] == 'board' and card['title'] == 'FLEET'
    assert card['status'] == 'idle'
    assert all(text in card['detail'] for text in ('3/3', 'online seats', 'both', 'advertised', '0.1.2+first'))
    assert workers == before


def test_fleet_daemon_aggregates_builds_before_ranking_and_model_keeps_effort_pairs():
    workers = fleet_workers()
    # Combined model-a wins 3:2, but no one model-a/effort pair beats model-b/medium.
    workers['workers'][2]['advertised_models'] = [dict(model='model-a', effort='medium')]
    workers['workers'][0]['advertised_models'] *= 20  # advertisements within a device deduplicate
    facts = fleet_card(workers)['fleet_summary']
    assert facts['daemon'] == '0.1.2'
    assert (facts['model'], facts['effort']) == ('model-b', 'medium')
    # Known absence contributes no vote, and a tie is lexical, independent of row order.
    workers['workers'][0]['advertised_models'] = []
    workers['workers'][2]['advertised_models'] = [dict(model='model-a', effort='high')]
    workers['workers'].reverse()
    facts = fleet_card(workers)['fleet_summary']
    assert (facts['model'], facts['effort']) == ('model-a', 'high')


@pytest.mark.parametrize('daemon', [None, '', '  ', '+build'])
def test_fleet_missing_daemon_cannot_claim_fleet_majority(daemon):
    workers = fleet_workers()
    workers['workers'][0]['daemon'] = daemon
    facts = fleet_card(workers)['fleet_summary']
    assert facts['daemon'] is None
    assert facts['claude_percent'] == 100 and facts['model'] == 'model-b'


@pytest.mark.parametrize('missing', [None, [], [''], ['  '], ['codex', '']])
def test_fleet_missing_runtime_on_any_device_keeps_denominator_but_no_percentage(missing):
    workers = fleet_workers()
    workers['workers'][0]['runtimes'] = missing
    facts = fleet_card(workers)['fleet_summary']
    assert facts['online'] == 3 and facts['runtime_known'] == 2
    assert facts['codex_percent'] is facts['claude_percent'] is None
    assert facts['model'] == 'model-b' and facts['daemon'] == '0.1.2'


@pytest.mark.parametrize('mode', ['missing', 'partial', 'count', 'malformed', 'unavailable'])
def test_fleet_unproven_roster_does_not_claim_share_daemon_or_model(mode):
    workers = fleet_workers()
    if mode == 'count': workers['count'] += 1
    if mode == 'malformed': workers['malformed_tokens'] = [7]
    card = fleet_card(None if mode == 'missing' else workers,
        state='unavailable' if mode == 'unavailable' else 'ok', partial=mode == 'partial',
        data=dict(swarm_board_summary=dict(wall_clock_ms=90000000), swarm_contributors_as_of_hhmm='00:12'))
    facts = card['fleet_summary']
    assert all(facts[key] is None for key in ('online', 'codex_percent', 'claude_percent', 'daemon', 'model', 'effort'))
    assert facts['read_ts'] == 900
    assert facts['state'] == ('unavailable' if mode in ('missing', 'unavailable') else 'partial')
    assert card['numerator'] == 90000000 and 'contributors read 00:12' in card['detail']


def test_fleet_empty_roster_known_zero_and_stale_source_retains_exact_facts():
    workers = fleet_workers()
    facts = fleet_card(workers)['fleet_summary']
    assert fleet_card(workers, state='stale')['fleet_summary'] == dict(facts, state='stale')
    workers.update(count=0, workers=[])
    empty = fleet_card(workers)['fleet_summary']
    assert empty == dict(codex_percent=None, claude_percent=None, daemon=None, model=None,
                        effort=None, online=0, runtime_known=0, state='ok', read_ts=900)
    assert all(card['fleet_summary'] is None for card in hub.cards({}, {}, now=1000) if card['key'] != 'board')


@pytest.mark.parametrize('state,points', [('ok', [0]*8), ('partial', [1, None, 2, 3, 4, 5, 6, 7]),
                                         ('stale', None), ('unavailable', None)])
def test_token_volume_projection_is_independent_of_recent_launch_ranking(state, points):
    volume = dict(points=points, state=state, known=20, total=178, as_of=9000, until=7200)
    catalogue = dict(count=178, state='ok', as_of=9900, volume=volume,
                     ranking=dict(rows=[], total=0, known=0, state='ok'))
    row = next(c for c in hub.cards({}, {}, now=10000, tokens_catalogue=catalogue)
               if c['key'] == 'swarm-tokens')
    assert row['secondary'] == '0 new'
    assert row['meter_kind'] == 'sparkline' and row['meter_state'] == state
    assert row['points'] == points
    assert 'all swarm tokens' in row['detail'] and '20/178' in row['detail']
    assert 'read '+hub.hhmm(9000) in row['detail']
    assert 'stale' not in row['detail'] and 'unavailable' not in row['detail']
    if state == 'partial':
        assert 'partial' in row['detail']


def test_card_details_omit_source_warnings_but_keep_internal_state():
    from maxpane_dashboard.data.surfboard import cards
    rows = cards({}, {}, now=1_800_000_000)
    assert any(row['status'] == 'unavailable' for row in rows)
    for row in rows:
        assert 'unavailable' not in row['detail']
        assert 'stale' not in row['detail']


def test_agent_card_hides_stale_activity_in_tooltip(monkeypatch):
    from maxpane_dashboard.data import surfboard
    monkeypatch.setattr(surfboard.work_activity, 'project', lambda *args, **kwargs:
                        dict(state='stale', remaining=None, as_of=1000, stopped_ts=None))
    rows = surfboard.cards({}, {}, now=2000, agent_seats=[{'token_id': 3}])
    agent = next(row for row in rows if row.get('token_id') == 3)
    assert agent['meter_state'] == 'stale'
    assert 'stale' not in agent['detail']
