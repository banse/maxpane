"""Oracle folds: raw captures and adversarial identities, never network reads."""
import copy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_models import SWARM_ORACLE_CACHE_FIELDS, SWARM_ORACLE_NODE_KEYS

ROOT = Path(__file__).parents[1] / 'fixtures/surf/swarm/oracle'
SEAT = json.loads((ROOT / 'seat_420.json').read_bytes())
DETAILS = [json.loads(p.read_bytes()) for p in sorted(ROOT.glob('request_*.json'))]
ROWS = sw.seat_work_rows(SEAT)


def captured(status='attested', inside=True, tolerance=False):
    for detail in DETAILS:
        if detail['status'] != status:
            continue
        agreement = detail.get('agreement') or {}
        for row in ROWS:
            members = [m for m in detail.get('members') or [] if m['submissionHash'] == row['submission_hash']]
            if not members or row['job_id'] != detail['jobId']:
                continue
            if (row['submission_hash'] in agreement.get('cluster', [])) != inside:
                continue
            if tolerance and not (detail.get('toleranceBps') == 1000 and agreement.get('figure') is not None
                                  and members[0]['answer'].get('figure') != agreement['figure']):
                continue
            return copy.deepcopy(detail), dict(row)
    raise AssertionError('missing captured case')


def point(detail, row, now=1000):
    return sw.oracle_point(detail, row['job_id'], row['submission_hash'], now_ts=now)


def enrich(row, value):
    slot = {} if value is None else {row['job_id']: {row['submission_hash']: value}}
    return sw.enrich_panel_rows([row], slot, SWARM_ORACLE_NODE_KEYS)[0]


@pytest.mark.parametrize('status,inside,state', [
    ('attested',True,'agreed'), ('attested',False,'outvoted'),
    ('disagreed',True,'no_quorum_in'), ('disagreed',False,'no_quorum_out'),
    ('assessing',False,'assessing'),
])
def test_captured_panel_outcomes(status,inside,state):
    detail, row = captured(status,inside)
    value = point(detail,row)
    assert set(value) == set(SWARM_ORACLE_CACHE_FIELDS)
    assert value['on_panel'] is True
    assert enrich(row,value)['panel_state'] == state
    assert value['terminal'] == (status != 'assessing')
    assert value['members'] == len(detail['members'])


def test_blocked_null_members_is_a_closed_blocked_panel():
    detail = next(copy.deepcopy(d) for d in DETAILS if d['status']=='blocked' and d['members'] is None)
    row = dict(ROWS[0],job_id=detail['jobId'])
    value = point(detail,row)
    assert value['members']==0 and value['terminal'] and not value['on_panel']
    assert enrich(row,value)['panel_state']=='blocked'


def test_wallet_cannot_join_another_submission():
    detail,row=captured()
    member=next(m for m in detail['members'] if m['submissionHash']==row['submission_hash'])
    wallet=member['wallet']
    value=point(detail,row)
    assert value['on_panel'] is True
    member['submissionHash']='f'*64
    assert member['wallet']==wallet
    value=point(detail,row)
    assert value['on_panel'] is False
    assert enrich(row,value)['panel_state']=='off_panel'


def test_tolerance_uses_cluster_even_when_figures_differ():
    detail,row=captured(tolerance=True)
    value=point(detail,row)
    assert value['in_cluster'] is True
    assert enrich(row,value)['panel_state']=='agreed'


def test_figure_digits_survive_without_float_conversion():
    detail,row=captured(tolerance=True)
    detail['agreement']['figure']='457162630000000001'
    value=point(detail,row)
    assert value['figure']=='457162630000000001'
    assert enrich(row,value)['panel_figure']=='457162630000000001'


@pytest.mark.parametrize('figure',[0,1.5,True,'1e20','NaN','[/x]','1'*81,'1.'+'2'*41])
def test_invalid_figures_are_absent(figure):
    detail,row=captured();detail['agreement']['figure']=figure
    assert point(detail,row)['figure'] is None


def test_duplicate_hash_conflicts_fail_but_identical_duplicates_are_safe():
    detail,row=captured();member=next(m for m in detail['members'] if m['submissionHash']==row['submission_hash'])
    detail['members'].append(copy.deepcopy(member))
    assert point(detail,row) is not None
    detail['members'][-1]['ok']=not member['ok']
    assert point(detail,row) is None


@pytest.mark.parametrize('change',[{'members':None},{'agreement':[]},{'jobId':'bad'},{'status':None}])
def test_untrusted_details_fail(change):
    detail,row=captured();detail.update(change)
    assert point(detail,row) is None


def test_malformed_cluster_fails():
    detail,row=captured()
    for cluster in (None,{},['bad'],[True]):
        detail['agreement']['cluster']=cluster
        assert point(detail,row) is None


def test_all_remaining_states_and_unrelated_rows():
    detail,row=captured()
    assert enrich(row,None)['panel_state']=='not_read'
    assert enrich(dict(row,node_key='build'),None)['panel_state']=='not_oracle'
    for status,expected in [(None,'unavailable'),('off_panel','off_panel'),('future-status','unavailable')]:
        value=sw.oracle_empty_point(status,now_ts=1000)
        assert enrich(row,value)['panel_state']==expected
    value=point(detail,row);value['status']='future-status';value['terminal']=False
    assert enrich(row,value)['panel_state']=='unavailable'


def test_hostile_slot_drops_only_bad_point():
    detail,row=captured();value=point(detail,row);job=row['job_id'];key=row['submission_hash']
    for bad in [dict(value,figure=1.5),dict(value,extra='notes'),dict(value,terminal='yes'),dict(value,read_ts=True),dict(value,agreed=True)]:
        result=sw.coerce_oracle_slot({job:{key:value,'f'*64:bad},'bad':{key:value}})
        assert result=={job:{key:value}}
    assert sw.coerce_oracle_slot(None) is None
    assert sw.coerce_oracle_slot({job:{'bad':value}})=={}


def test_due_rows_respect_window_identities_terminal_and_retry_age():
    detail,row=captured();value=point(detail,row)
    rows=[dict(row,submission_hash=f'{i:064x}') for i in range(42)]
    slot={row['job_id']:{rows[0]['submission_hash']:value,
                       rows[1]['submission_hash']:dict(value,terminal=False,status='assessing')}}
    due=sw.oracle_rows_due(rows,slot,now_ts=1119,due_s=120)
    assert due==rows[2:40]
    due=sw.oracle_rows_due(rows,slot,now_ts=1120,due_s=120)
    assert due==rows[2:40]+rows[1:2]
    assert sw.oracle_rows_due([dict(row,node_key='build'),dict(row,submission_hash='bad')],{},now_ts=1000,due_s=120)==[]


def test_request_matching_rejects_duplicate_job_and_tracks_coverage():
    detail,row=captured();request={k:detail[k] for k in ('id','jobId','createdAt')}
    matched,ambiguous,negative=sw.match_requests([request],[row])
    assert matched=={row['job_id']:detail['id']} and not ambiguous and not negative
    matched,ambiguous,negative=sw.match_requests([request,dict(request,id='00000000-0000-4000-8000-000000000001')],[row])
    assert not matched and ambiguous=={row['job_id']} and not negative
    other=dict(row,job_id='00000000-0000-4000-8000-000000000002')
    assert sw.match_requests([request],[other])[2]=={other['job_id']}
    assert sw.match_requests([], [other])[2]==set()
    assert sw.match_requests([], [other], end_of_history=True)[2]=={other['job_id']}
    assert sw.match_requests([dict(request,createdAt='2099-01-01T00:00:00Z')],[other])[2]==set()


def test_prune_bounds_each_point_and_checks_age():
    detail,row=captured();value=point(detail,row);job=row['job_id']
    slot={job:{f'{i:064x}':dict(value,read_ts=i) for i in range(5)}}
    assert set(sw.prune_oracle(slot,now_ts=5,cap=2,max_age_s=10)[job])=={f'{i:064x}' for i in (3,4)}
    assert sw.prune_oracle(slot,now_ts=10,cap=400,max_age_s=2)=={}
    assert sw.prune_oracle({job:{row['submission_hash']:value}},now_ts=999)=={}


@pytest.mark.parametrize('answer', [True, False])
def test_bool_answer_comes_from_agreement_not_numeric_figure(answer):
    detail = next(copy.deepcopy(d) for d in DETAILS if d.get('answerType') == 'bool'
                  and (d.get('agreement') or {}).get('answer') is answer
                  and (d.get('agreement') or {}).get('figure') is not None)
    member = detail['members'][0]
    row = dict(ROWS[0], job_id=detail['jobId'], submission_hash=member['submissionHash'])
    value = point(detail, row)
    assert value['answer_bool'] is answer
    assert enrich(row, value)['panel_answer_bool'] is answer
    assert value['figure'] == detail['agreement']['figure']
    for bad in (0, 1, 'true', 'false', []):
        detail['agreement']['answer'] = bad
        assert point(detail, row)['answer_bool'] is None
        bad_point = dict(value, answer_bool=bad)
        assert sw.coerce_oracle_slot({row['job_id']: {row['submission_hash']: bad_point}}) == {}
