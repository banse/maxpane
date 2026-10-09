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


def test_rack_meters_use_real_denominators_uncapped_population_and_split():
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
    data={f'sig_{name}_state':'ok' for name in SIGNAL_NAMES}
    data[f'sig_{SIGNAL_NAMES[0]}_state']='fired'
    data.update(swarm_seat_selected={'token_id':420},swarm_seat_outcome=hub.seat_outcome(hub.normalize_records(capture('records')),420),
                swarm_board_summary={'seats':2,'attempts':3393,'accepted':3254},
                pool4_vault_assets=20,pool4_total_supply=100,pool4_total_burned=2,pool4_total_rewarded=3,pool4_total_fee_token=5)
    lp={'coin_count':25,'launch_count':25,'cursor':{'last_block':123,'launches':{str(i):{} for i in range(25)}},'swaps_by_coin':{str(i):1 for i in range(23)}}
    cards={c['key']:c for c in hub.cards(data,{},now=100,launchpad=lp)}
    assert (cards['announce']['numerator'],cards['announce']['denominator'])==(1,len(SIGNAL_NAMES))
    assert (cards['agent']['numerator'],cards['agent']['denominator'])==(3253,3392)
    assert (cards['board']['numerator'],cards['board']['denominator'])==(3254,3393)
    assert (cards['launchpad']['numerator'],cards['launchpad']['denominator'])==(23,25)
    assert (cards['pool4']['numerator'],cards['pool4']['denominator'])==(20,100)
    assert (cards['protocol']['numerator'],cards['protocol']['denominator'])==(2,10)
    assert cards['protocol']['status']=='experimental'
    assert {c['key'] for c in cards.values() if c['status']=='planned'}=={'swarm-tokens','portfolio','earnings'}
    lp['launch_count']=24
    assert next(c for c in hub.cards(data,{},now=100,launchpad=lp) if c['key']=='launchpad')['numerator'] is None


def test_unknown_detector_prevents_a_false_zero_bar():
    cards=hub.cards({}, {}, now=100)
    assert cards[0]['numerator'] is cards[0]['denominator'] is None


@pytest.mark.parametrize('items,footer', [
    (None,'unavailable'), ([], '0 new posts'),
    ([dict(kind='self',ts=99999,tx_hash='0x'+'a'*64)],'1 new post'),
    ([dict(kind=kind,ts=99999,tx_hash='0x'+char*64)
      for kind,char in [('self','a'),('reply','b'),('answer','c')]],'3 new posts'),
    ([dict(kind=kind,ts=ts,tx_hash='0x'+char*64) for kind,ts,char in [
        ('self',99999,'a'),('self',99999,'A'),('reply',13601,'b'),
        ('reply',13600,'c'),('self',100001,'d'),('action',99999,'e'),
        ('failed',99999,'f'),('fund',99999,'1')]],'2 new posts'),
    ([None,dict(kind='self',ts=True,tx_hash='0x'+'a'*64),
      dict(kind='self',ts=99999,tx_hash='bad')],'0 new posts'),
])
def test_announce_card_counts_unique_posts_replies_and_answers_in_last_day(items,footer):
    from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
    data={f'sig_{name}_state':'fired' if i<5 else 'ok' for i,name in enumerate(SIGNAL_NAMES)}
    row=hub.cards(data,{},now=100000,announce_items=items)[0]
    assert row['primary']=='5' and row['secondary']==footer
    assert row['numerator']==5 and row['denominator']==len(SIGNAL_NAMES)
    assert '24h' in row['detail'] and 'cached' in row['detail']
    assert hub.cards({}, {},now=100000,announce_items=[])[0]['primary']=='unavailable'


@pytest.mark.parametrize('burn,reward,primary,secondary', [
    (33279.30, 5872.82, '33,279', '5,873 rewarded'),
    (0, 0, '0', '0 rewarded'),
    (12.8, 3.2, '13', '3 rewarded'),
    (None, None, 'unavailable', 'unavailable'),
    (True, float('nan'), 'unavailable', 'unavailable'),
])
def test_protocol_card_rounds_readouts_but_keeps_exact_flow(burn, reward, primary, secondary):
    row=next(c for c in hub.cards(dict(pool4_total_burned=burn,
        pool4_total_rewarded=reward,pool4_total_fee_token=1),{},now=100) if c['key']=='protocol')
    assert (row['primary'],row['secondary'])==(primary,secondary)
    assert row['status']=='experimental'
    if type(burn) in (int,float):
        assert row['numerator']==burn
        assert row['denominator']==burn+reward+1
        assert (f'{burn:,}' if type(burn) is int else f'{burn:,.2f}')+' burned' in row['detail']
        assert (f'{reward:,}' if type(reward) is int else f'{reward:,.2f}')+' rewarded' in row['detail']


@pytest.mark.parametrize('state,working,capacity,slots,status', [
    ('working', 2, 3, '2 of 3 slots', 'working'),
    ('idle', 0, 3, '0 of 3 slots', 'idle'),
    ('offline', 0, 0, '0 of 0 slots', 'offline'),
    ('paused', 0, 3, '0 of 3 slots', 'paused'),
    ('paused', 1, 3, '1 of 3 slots', 'paused'),
    ('working', 0, 3, '0 of 3 slots', 'unavailable'),
    ('working', None, 3, '— of 3 slots', 'unavailable'),
    ('working', True, 3, '— of 3 slots', 'unavailable'),
    ('working', 1, None, '1 of — slots', 'working'),
    ('working', 9, 3, '9 working', 'working'),
    (None, None, None, '— of — slots', 'unavailable'),
])
def test_agent_card_uses_the_selected_seat_live_slots(state, working, capacity, slots, status):
    outcome = hub.seat_outcome(hub.normalize_records(capture('records')), 420)
    data = dict(swarm_seat_selected={'token_id':420}, swarm_seat_outcome=outcome,
                swarm_seat_live=dict(live_state=state, working=working, max_concurrency=capacity),
                swarm_workers_as_of_hhmm='12:34')
    cards = hub.cards(data, {'records':dict(state='stale', read_ts=100)}, now=200)
    agent = next(card for card in cards if card['key']=='agent')
    assert agent['primary']=='IDMD #420' and agent['secondary']==slots
    assert agent['status']==status
    assert (agent['numerator'],agent['denominator'])==(3253,3392)
    assert '95.9% accepted' in agent['detail'] and 'records stale' in agent['detail']
    assert 'workers' in agent['detail'] and '12:34' in agent['detail']


def test_card_zero_denominator_differs_from_invalid_boolean():
    def pool(assets,supply):
        return next(c for c in hub.cards({'pool4_vault_assets':assets,'pool4_total_supply':supply},{},now=100) if c['key']=='pool4')
    zero=pool(0,0)
    assert zero['numerator']==zero['denominator']==0 and 'no supply' in zero['detail']
    invalid=pool(False,0)
    assert invalid['numerator'] is invalid['denominator'] is None

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
    assert 'hourly stale · read '+hub.hhmm(100) in card['detail']


def test_degraded_pool4_never_labels_retained_numbers_active():
    data={'pool4_price_usd':2.0,'pool4_trailing_return_pct':3.0,'pool4_vault_assets':20,'pool4_total_supply':100,'degraded':['p4']}
    cards={c['key']:c for c in hub.cards(data,{},now=100)}
    assert cards['pool4']['status']=='stale'
    assert cards['pool4']['numerator']==20


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
