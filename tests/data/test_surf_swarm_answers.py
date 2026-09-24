"""Submission popup facts, byte budgets and hostile persisted points."""
import copy
import json
from pathlib import Path

import pytest
from maxpane_dashboard.data import surf_swarm as sw

ROOT = Path(__file__).parents[1] / 'fixtures/surf/swarm'


def capture(name):
    return json.loads((ROOT / 'submissions' / (name + '.json')).read_text())


def own(name='hunt'):
    payload = capture(name + '_submissions')
    item = next(i for i in payload['submissions'] if str(i.get('seat', {}).get('tokenId')) == '420')
    return payload, item


def point(payload, item):
    return sw.bound_answer_point(dict(sw.submission_answer(payload, payload['jobId'], item['hash'], 420),
                                     read_ts=1000.0, terminal=True))


def test_hunt_reply_facts_and_other_seats():
    payload, item = own(); value = point(payload, item)
    assert value['failure_reason'] == 'local_build_failed' and value['turns'] == 61
    assert value['reply'] == item['summary']
    assert value['others_total'] == len(value['others']) == 7
    assert sorted(r['failure_reason'] for r in value['others']) == ['path_violation'] + ['runtime_error']*6
    assert value['others'] == sorted(value['others'], key=lambda r: (r['node_key'], r['token']))
    assert all(len(r['line']) <= 200 for r in value['others'])
    job = sw.job_detail_point(capture('hunt_job'), payload['jobId'], now_ts=1000)
    assert job['state'] == 'blocked' and job['blocked_reason'] == 'node hunt_b: runtime_error'
    assert not job['terminal'] and len(job['nodes']) == 6


def test_reply_keeps_indentation_newlines_and_boxes_but_no_paths_ansi_or_fake_address():
    payload, item = own()
    item['summary'] = 'start\n\t┃ \x1b[31mred\x1b[0m /Users/alice/private/file.sol\n  done\n'
    value = point(payload, item)
    assert value['reply'] == 'start\n    ┃ red file.sol\n  done\n'
    slot = {payload['jobId']: {item['hash']: value}}
    assert sw.coerce_answers_slot(slot) == slot
    item['summary'] = 'x'*4053 + ' 0x' + 'ab'*32
    assert sw.clean_reply(item['summary']) == 'x'*4053
    assert '0x' not in point(payload, item)['reply']


@pytest.mark.parametrize('field,bad', [
    ('reply', 'bad\x00'), ('reply', '/Users/alice/private/file'), ('reply', 'x'*4097),
    ('failure_reason', 'bad code'), ('turns', True), ('cached_input_tokens', -1),
    ('failed_checks', 'x'*301), ('findings', True), ('artifacts', [{'name':'x','bytes':True}]),
    ('others', [{'node_key':'x','token':True,'outcome':'failed','failure_reason':None,'line':'x'}]),
    ('others_total', True),
])
def test_hostile_reply_field_drops_only_its_point(field,bad):
    payload,item=own(); value=point(payload,item)
    slot={payload['jobId']:{item['hash']:value,'f'*64:dict(value,**{field:bad})}}
    assert sw.coerce_answers_slot(slot)=={payload['jobId']:{item['hash']:value}}
    old={k:v for k,v in value.items()if k not in sw.SUBMISSION_FACT_FIELDS}
    assert sw.coerce_answers_slot({payload['jobId']:{item['hash']:old}})=={}


@pytest.mark.parametrize('step', ['others', 'reply', 'failed_checks', 'answer'])
def test_answer_byte_cascade_exercises_each_step(step):
    payload,item=own(); value=point(payload,item)
    value.update(reply='😀'*4096, failed_checks='😀'*300)
    for other in value['others']: other['line']='😀'*200
    if step=='others': value['reply']='x'*3000
    if step=='failed_checks': value['model']='m'*6500
    if step=='answer': value['answer']='审计发现'*700+'。'
    result=sw.bound_answer_point(copy.deepcopy(value))
    assert result and len(json.dumps(result).encode())<=8000
    if step=='others': assert any(len(r['line'])<200 for r in result['others'])
    if step=='reply': assert all(not r['line']for r in result['others']) and len(result['reply'])<4096
    if step=='failed_checks': assert result['reply'] is None and len(result['failed_checks'] or '')<300
    if step=='answer':
        assert result['reply'] is None and result['failed_checks'] is None
        assert len(result['answer']) < 2801
    assert sw.coerce_answers_slot({payload['jobId']:{item['hash']:result}})


def test_two_hashes_keep_their_own_reply_and_oracle_has_no_others():
    payload,item=own()
    sibling=copy.deepcopy(item); sibling.update(hash='f'*64,summary='Sibling\nreply')
    payload['submissions'].append(sibling)
    assert point(payload,item)['reply']==item['summary']
    assert point(payload,sibling)['reply']=='Sibling\nreply'
    item['nodeKey']='oracle_assess'
    assert point(payload,item)['others'] is None and point(payload,item)['others_total'] is None


def test_bytes32_fixture_normalizes_without_address_semantics():
    detail=json.loads((ROOT/'oracle/filtered/bytes32.json').read_text()); member=detail['members'][0]
    value=sw.oracle_point(detail,detail['jobId'],member['submissionHash'],now_ts=1000)
    assert value['seat_answer']==' '.join(member['answer']['answer'])
    assert sw.coerce_oracle_slot({detail['jobId']:{member['submissionHash']:value}})


@pytest.mark.parametrize('bad', [dict(state='x'*41),dict(blocked_reason='/Users/a/secret'),
    dict(nodes=[{'key':'x','role':'tests','state':'failed','attempt':True,'failure_reason':None}]),
    dict(terminal=True),dict(read_ts=True),dict(nodes=[{}]*17)])
def test_job_detail_coercion_drops_only_hostile_job(bad):
    detail=capture('hunt_job'); point=sw.job_detail_point(detail,detail['id'],now_ts=1000)
    sibling='00000000-0000-4000-8000-000000000000'
    assert sw.coerce_job_detail_slot({detail['id']:point,sibling:dict(point,**bad)})=={detail['id']:point}


def test_others_and_artifacts_caps_with_strict_numbers_and_old_shape_drop():
    payload,item=own()
    template=payload['submissions'][0]
    payload['submissions']=[item]+[dict(template,hash=f'{i:064x}',seat={'tokenId':str(i)})for i in range(12)]
    item['artifacts']=[{'name':'n'*100,'bytes':i}for i in range(12)]
    item['usage'].update(turns=True,cachedInputTokens=-1)
    item['verdict']={'failedChecks':['check1',{'name':'check2'}]}
    value=point(payload,item)
    assert value['others_total']==12 and len(value['others'])==8 and len(value['artifacts'])==10
    assert all(len(a['name'])==80 for a in value['artifacts'])
    assert value['turns'] is None and value['cached_input_tokens'] is None
    assert value['failed_checks']=='check1, check2'


@pytest.mark.parametrize('changes,eligible', [
    ({'node_key': 'oracle_assess', 'panel_state': 'off_panel', 'work_status': 'accepted'}, True),
    ({'oracle_member_ok': True}, False), ({'oracle_member_ok': False}, False),
    ({'answer_state': 'no_reply'}, True), ({'answer_state': 'not_read'}, False),
    ({'answer_state': 'unavailable'}, False), ({'submission_hash': 'bad'}, False),
    ({'job_id': 'bad'}, False),
])
def test_job_details_follow_submission_eligibility(changes, eligible):
    from maxpane_dashboard.widgets.surf._oracle_answer import can_open_submission
    payload, item = own()
    row = dict(job_id=payload['jobId'], submission_hash=item['hash'], node_key='hunt_d',
               work_status='accepted', answer_state='read', oracle_member_ok=None)
    row.update(changes)
    assert can_open_submission(row) is eligible
    assert sw.job_details_due([row], {}, now_ts=1000) == ([row['job_id']] if eligible else [])
    # The caller supplies the selected window; eligibility must not truncate it again.
    assert sw.job_details_due([dict(row, answer_state='not_read')]*40+[row], {}, now_ts=1000) == ([row['job_id']] if eligible else [])


@pytest.mark.parametrize('items,expected', [
    ([], ''), (['0x1', '9'*78, '0x'+'F'*64], '0x1 '+'9'*78+' 0x'+'F'*64),
    (['1']*20, ' '.join(['1']*20)), (['1']*21, None),
    (['0x'], None), (['0x'+'a'*65], None), (['9'*79], None),
    (['1\n'], None), (['-1'], None), ([1], None), ([True], None),
])
def test_non_address_arrays_require_bounded_full_string_items(items, expected):
    assert sw._seat_answer(items, 'bytes32[]') == expected


def test_completed_review_fallback_preserves_its_reply_and_usage():
    payload = json.loads((ROOT/'v4/submissions_33016bad.json').read_text())
    item = next(i for i in payload['submissions'] if str(i['seat']['tokenId']) == '420')
    value = point(payload, item)
    assert item['nodeKey'] not in sw.SWARM_ORACLE_NODE_KEYS
    assert value['state'] == 'read' and value['reply'] == sw.clean_reply(item['summary'])
    assert value['turns'] == item['usage']['turns']
    assert value['others_total'] == len(payload['submissions'])-1


@pytest.mark.parametrize('tail', ['https:/', 'https://'])
@pytest.mark.parametrize('field,cap', [('others', 200), ('reply', 4096), ('failed_checks', 300)])
def test_url_character_cuts_survive_load_unchanged(field, cap, tail):
    payload, item = own()
    text = 'x'*(cap-len(tail)-1) + ' https://example.com/path'
    if field == 'others':
        sibling = next(i for i in payload['submissions'] if i['hash'] != item['hash'])
        sibling['summary'] = text
    elif field == 'reply':
        item['summary'] = 'Done.\n' + text[6:]
    else:
        item['verdict'] = {'failedChecks': [text]}
    value = point(payload, item)
    slot = {payload['jobId']: {item['hash']: value}}
    assert sw.coerce_answers_slot(slot) == slot


@pytest.mark.parametrize('tail', ['https:/', 'https://'])
@pytest.mark.parametrize('field', ['others', 'reply', 'failed_checks'])
def test_url_byte_cuts_survive_load_unchanged(monkeypatch, field, tail):
    payload, item = own()
    value = point(payload, item)
    value.update(reply=None, failed_checks=None)
    for other in value['others']:
        other['line'] = ''
    target = value['others'][0] if field == 'others' else value
    key = 'line' if field == 'others' else field
    target[key] = 'prefix ' + tail
    limit = len(json.dumps(value).encode())
    target[key] = 'prefix https://example.com/path'
    monkeypatch.setattr(sw, 'ANSWER_POINT_BYTES', limit)
    result = sw.bound_answer_point(value)
    assert result is not None
    slot = {payload['jobId']: {item['hash']: result}}
    assert sw.coerce_answers_slot(slot) == slot


def test_mixed_job_excludes_each_oracle_sibling():
    payload, item = own()
    before = point(payload, item)
    oracle = dict(item, hash='f'*64, nodeKey='oracle_assess', seat={'tokenId': '9999'})
    payload['submissions'].append(oracle)
    value = point(payload, item)
    assert value['others'] == before['others']
    assert value['others_total'] == before['others_total'] == 7
    assert sw.submission_answer(payload, payload['jobId'], oracle['hash'], 9999)['others'] is None


def test_loader_uses_disk_encoding_for_answer_bound():
    payload, item = own()
    value = point(payload, item)
    value.update(reply='😀'*1000)
    assert len(json.dumps(value).encode()) > 8000
    assert sw.coerce_answers_slot({payload['jobId']: {item['hash']: value}}) == {}


@pytest.mark.parametrize('text,safe', [
    ('line\n    ┃ 审计', True), ('nonbreaking\u00a0space', True), ('[bold]', True),
    ('https://example.com/path', True), ('https://example.com/\x00secret', False),
    ('https://example.com/\u200bsecret', False), ('bad\x7f', False), ('bad\u200b', False),
    ('bad\ue000', False), ('bad\ud800', False), ('[label](https://example.com)', False),
    ('/Users/user/private.txt', False), ('C:\\Users\\user\\private.txt', False),
])
def test_reply_safety_preserves_unicode_and_rejects_unsafe_text(text, safe):
    assert sw._safe_reply(text) is safe


def test_plain_replies_skip_python_link_parser_at_cache_cap(monkeypatch):
    payload, item = own()
    value = point(payload, item)
    value.update(answer='Observed result.', reply='x'*4096)
    for other in value['others']:
        other['line'] = 'x'*100
    slot = {payload['jobId']: {f'{i:064x}': copy.deepcopy(value) for i in range(400)}}
    def unexpected_parse(text):
        raise AssertionError('plain prose must not run the Python Markdown parser')
    monkeypatch.setattr(sw, '_answer_link_spans', unexpected_parse)
    assert len(sw.coerce_answers_slot(slot)[payload['jobId']]) == 400


@pytest.mark.parametrize('text,safe', [
    ('https://example.com/[label](target)', False),
    ('[label https://example.com/](target)', False),
    ('https://example.com/](literal)', True),
])
def test_url_embedded_markdown_keeps_both_safety_checks(text, safe):
    assert sw._safe_reply(text) is safe
    assert sw._safe_stored_answer(text) is safe
