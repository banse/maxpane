"""Oracle folds: raw captures and adversarial identities, never network reads."""
import copy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_models import SWARM_ORACLE_CACHE_FIELDS, SWARM_ORACLE_NODE_KEYS
from tests.surf_swarm_fixtures import SWARM_ORACLE_DETAIL_IDS, swarm_oracle_details

ROOT = Path(__file__).parents[1] / 'fixtures/surf/swarm/oracle'
SEAT = json.loads((ROOT / 'seat_420.json').read_bytes())
DETAILS = swarm_oracle_details()
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
    assert value['quorum'] == detail['quorum']


def test_blocked_null_members_is_a_closed_blocked_panel():
    detail = next(copy.deepcopy(d) for d in DETAILS if d['status']=='blocked' and d['members'] is None)
    row = dict(ROWS[0],job_id=detail['jobId'])
    value = point(detail,row)
    assert value['quorum']==detail['quorum'] and value['terminal'] and not value['on_panel']
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
    assert due==rows[2:]
    due=sw.oracle_rows_due(rows,slot,now_ts=1120,due_s=120)
    assert due==rows[2:]+rows[1:2]
    assert sw.oracle_rows_due([dict(row,node_key='build'),dict(row,submission_hash='bad')],{},now_ts=1000,due_s=120)==[]


def test_request_matching_rejects_duplicate_job_and_requires_complete_coverage():
    detail, row = captured()
    request = {k: detail[k] for k in ('id', 'jobId', 'createdAt')}
    index = dict(jobs={}, newest='2026-09-24T00:00:00Z', oldest=request['createdAt'], complete=False)
    sw.add_oracle_index_page(index, [request, request])
    assert sw.match_requests(index, [row]) == ({row['job_id']: detail['id']}, set(), set())
    other = dict(row, job_id='00000000-0000-4000-8000-000000000002')
    assert sw.match_requests(index, [other])[2] == set()
    index['complete'] = True
    assert sw.match_requests(index, [other])[2] == {other['job_id']}
    assert sw.match_requests(index, [dict(other, submitted_ts=sw.oracle_cursor_ts(index['newest']) + 1)])[2] == set()
    sw.add_oracle_index_page(index, [dict(request, id='00000000-0000-4000-8000-000000000001')])
    assert sw.match_requests(index, [row]) == ({}, {row['job_id']}, set())


@pytest.mark.parametrize('change', [
    {'jobs': {'bad': None}}, {'complete': 1}, {'extra': 1},
    {'newest': '2026-09-23T19:00:00+00:00'}, {'oldest': '2099-01-01T00:00:00Z'},
    {'jobs': {}}, {'newest': None},
])
def test_hostile_index_is_rejected_whole(change):
    detail, row = captured()
    index = dict(jobs={row['job_id']: detail['id']}, newest='2026-09-24T00:00:00Z',
                 oldest=detail['createdAt'], complete=True)
    assert sw.coerce_oracle_index(index) == index
    assert sw.coerce_oracle_index(dict(index, **change)) is None


def test_complete_captured_list_index_finds_242_jobs_and_only_one_absence():
    pages = [json.loads((ROOT / f'list_{i}.json').read_bytes())['requests'] for i in (1, 2, 3)]
    index = sw.empty_oracle_index()
    for page in pages:
        assert sw.oracle_index_page(page) is not None
        sw.add_oracle_index_page(index, page)
    stamps = [r['createdAt'] for page in pages for r in page]
    index.update(newest=max(stamps, key=sw.oracle_cursor_ts),
                 oldest=min(stamps, key=sw.oracle_cursor_ts), complete=True)
    rows = [r for r in sw.seat_work_rows(json.loads((ROOT / 'seat_420.json').read_bytes()))
            if r['node_key'] in SWARM_ORACLE_NODE_KEYS]
    matched, ambiguous, negative = sw.match_requests(index, rows)
    assert not ambiguous
    assert sum(r['job_id'] in matched for r in rows) == 242
    assert sum(r['job_id'] in negative for r in rows) == 1
    slot = {r['job_id']: {r['submission_hash']: sw.oracle_empty_point('off_panel', now_ts=1000)}
            for r in rows if r['job_id'] in negative}
    enriched = sw.enrich_panel_rows(rows, slot, SWARM_ORACLE_NODE_KEYS)
    assert sum(r['panel_state'] == 'off_panel' for r in enriched) == 1
    assert sum(r['panel_state'] == 'not_read' for r in enriched) == 242
    # Every retained detail selected by the list is joined by hash, never by job alone.
    from tests.surf_swarm_fixtures import swarm_oracle_details
    retained = {d['id']: d for d in swarm_oracle_details()}
    checked = 0
    for row in rows:
        detail = retained.get(matched.get(row['job_id']))
        if detail is None:
            continue
        value = point(detail, row)
        member = any(m['submissionHash'] == row['submission_hash'] for m in detail.get('members') or [])
        assert value['on_panel'] is member
        if not member:
            expected = detail['status'] if detail['status'] in ('blocked', 'assessing') else 'off_panel'
            assert enrich(row, value)['panel_state'] == expected
        checked += 1
    assert checked > 40


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


def test_committed_details_are_exactly_the_listed_ids_and_the_manifest_agrees():
    on_disk = {p.stem[len('request_'):] for p in ROOT.glob('request_*.json')}
    assert on_disk == set(SWARM_ORACLE_DETAIL_IDS)
    files = json.loads((ROOT / 'MANIFEST.json').read_bytes())['files']
    listed = {name[len('request_'):] for name, entry in files.items()
              if name.startswith('request_') and entry.get('committed', True)}
    assert listed == on_disk


@pytest.mark.parametrize('kind', ['bool', 'uint256', 'address[]'])
def test_member_answer_facts_use_request_type_and_exact_hash(kind):
    detail, member = next((copy.deepcopy(d), m) for d in DETAILS if d['answerType'] == kind
                          for m in d.get('members') or [] if m.get('ok') is True)
    row = dict(ROWS[0], job_id=detail['jobId'], submission_hash=member['submissionHash'])
    value = point(detail, row)
    raw = member['answer']['answer']
    expected = ('true' if raw else 'false') if kind == 'bool' else ' '.join(raw) if kind == 'address[]' else raw
    assert value['seat_answer'] == expected
    assert value['question'] == ' '.join(detail['question'].split())
    assert value['chain_id'] == detail['chainId']
    assert value['member_ok'] is True and value['notes']
    assert value['quorum'] == detail['quorum']
    joined = enrich(row, value)
    assert joined['oracle_seat_answer'] == expected and joined['oracle_member_ok'] is True
    detail['members'][0]['answer']['answerType'] = 'irrelevant'
    assert point(detail, row)['seat_answer'] == expected


@pytest.mark.parametrize('kind,raw', [('bool', 1), ('uint256', '1'*79), ('uint256', 12),
                                      ('address[]', ['bad']), ('address[]', ['0x'+'1'*40]*21)])
def test_invalid_member_values_preserve_membership_with_no_guessed_value(kind, raw):
    detail, row = captured()
    member = next(m for m in detail['members'] if m['submissionHash'] == row['submission_hash'])
    detail['answerType'] = kind; member['answer']['answer'] = raw
    value = point(detail, row)
    assert value['seat_answer'] is None and value['on_panel'] and value['member_ok'] is True
    assert enrich(row, value)['oracle_member_ok'] is True


@pytest.mark.parametrize('status', ['refused', 'failed'])
def test_unknown_status_with_null_agreement_preserves_member_answer(status):
    detail, row = captured(); detail.update(status=status, agreement=None)
    value = point(detail, row)
    assert value and not value['terminal'] and value['notes']
    assert enrich(row, value)['panel_state'] == 'unavailable'
    assert enrich(row, value)['oracle_member_ok'] is True


@pytest.mark.parametrize('status', ['attested', 'disagreed'])
@pytest.mark.parametrize('agreement', [None, [], 'invalid'])
def test_known_final_without_agreement_is_a_failed_read(status, agreement):
    detail, row = captured()
    detail.update(status=status, agreement=agreement)
    assert point(detail, row) is None
    failed = sw.oracle_empty_point(None, now_ts=1000)
    assert not failed['terminal']
    assert enrich(row, failed)['panel_state'] == 'unavailable'


@pytest.mark.parametrize('status', ['', '  '])
def test_empty_or_whitespace_status_is_a_failed_read(status):
    detail, row = captured()
    detail['status'] = status
    assert point(detail, row) is None


def test_member_failure_and_normalized_paragraphs():
    detail, row = captured()
    member = next(m for m in detail['members'] if m['submissionHash'] == row['submission_hash'])
    member.update(ok=False, reason=' Invalid   input\x00 ')
    member['answer']['notes'] = ' first   line\n\nsecond\x00 [/x] '
    value = point(detail, row)
    assert value['member_ok'] is False and value['member_reason'] == 'Invalid input'
    assert value['notes'] == 'first line\n\nsecond [/x]'
    member['submissionHash'] = 'f'*64
    value = point(detail, row)
    assert not value['on_panel']
    assert all(value[k] is None for k in ('question','chain_id','member_ok','member_reason','seat_answer','notes'))


@pytest.mark.parametrize('text,trim_reason', [('x', False), ('界', False), ('😀', False), ('"\\', False), ('😀', True)])
def test_maximal_member_point_fits_actual_json_byte_budget(text, trim_reason):
    detail, row = captured()
    member = next(m for m in detail['members'] if m['submissionHash'] == row['submission_hash'])
    detail.update(question=text*1000, answerType='address[]')
    member.update(reason=text*200)
    member['answer'].update(answer=['0x'+'1'*40]*20, notes=text*4001)
    if trim_reason:
        detail['answerType'] = 'x'*4500
        member['answer']['answer'] = 'preserved value'
    value = point(detail, row)
    assert len(json.dumps(value).encode()) <= 6000
    assert value['seat_answer'] == ('preserved value' if trim_reason else ' '.join(['0x'+'1'*40]*20))
    assert len(value['notes'] or '') <= 4000
    assert sw.coerce_oracle_slot({row['job_id']: {row['submission_hash']: value}})
    if trim_reason:
        assert value['question'] is None and value['notes'] is None
        assert 0 < len(value['member_reason']) < 200


def hex_cut_case(mode):
    detail, row = captured()
    member = next(m for m in detail['members'] if m['submissionHash'] == row['submission_hash'])
    raw_hash = '0x' + 'ab'*32
    member['answer']['notes'] = ('x'*3957 if mode == 'cap' else 'Evidence') + ' ' + raw_hash
    if mode == 'bytes':
        detail['answerType'] = ''
        member['answer']['answer'] = 'value'
        member['reason'] = None
        detail['question'] = None
        probe = point(detail, row)
        probe['notes'] = 'Evidence ' + raw_hash[:42]
        # Force the byte-bound prefix to end at a false 42-character address.
        detail['answerType'] = 'x'*(6000 - len(json.dumps(probe).encode()))
    return detail, row


@pytest.mark.parametrize('mode', ['cap', 'bytes'])
def test_hex_run_cut_never_becomes_a_fake_address_and_roundtrips(mode):
    detail, row = hex_cut_case(mode)
    value = point(detail, row)
    assert value['notes'] == ('x'*3957 if mode == 'cap' else 'Evidence')
    slot = {row['job_id']: {row['submission_hash']: value}}
    assert sw.coerce_oracle_slot(slot) == slot


@pytest.mark.parametrize('cut', [1, 2, 3, 42, 65])
def test_any_cut_inside_hex_drops_the_entire_run(cut):
    raw_hash = '0x' + 'ab'*32
    assert sw._oracle_text('Evidence ' + raw_hash, len('Evidence ') + cut) == 'Evidence'
    assert sw._oracle_text('Evidence ' + raw_hash, 200) == 'Evidence ' + raw_hash


@pytest.mark.parametrize('changes', [dict(notes='x'*4001), dict(notes='bad\x00'), dict(chain_id=True),
    dict(member_ok=1), dict(question='q'*1001), dict(member_reason='r'*201),
    dict(notes='😀'*4000), dict(on_panel=False), dict(answer_type='bool', seat_answer='yes')])
def test_new_member_fields_drop_only_hostile_point(changes):
    detail, row = captured(); value = point(detail, row)
    bad = dict(value, **changes)
    assert sw.coerce_oracle_slot({row['job_id']: {row['submission_hash']: value, 'f'*64: bad}}) == {
        row['job_id']: {row['submission_hash']: value}}
    old = {k:v for k,v in value.items() if k not in ('question','chain_id','member_ok','member_reason','seat_answer','notes')}
    assert sw.coerce_oracle_slot({row['job_id']: {row['submission_hash']: old}}) == {}


def test_filtered_body_never_joins_a_different_member_hash():
    detail = json.loads((ROOT / 'filtered/hit.json').read_bytes())
    member = detail['members'][0]
    row = dict(ROWS[0], job_id=detail['jobId'], submission_hash=member['submissionHash'])
    assert point(detail, row)['on_panel'] is True
    member['submissionHash'] = 'f'*64
    value = point(detail, row)
    assert value['on_panel'] is False and value['seat_answer'] is None
    assert enrich(row, value)['oracle_member_ok'] is None
