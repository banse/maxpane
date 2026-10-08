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
