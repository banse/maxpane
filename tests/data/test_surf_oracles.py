"""Oracle dashboard extraction uses captured public data and canonical panel semantics."""
import copy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_oracles as oracle
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS


@pytest.fixture
def captured():
    return json.loads(Path('tests/fixtures/surf/oracles/captured.json').read_text())


def test_page_bound_unknown_status_and_empty(captured):
    rows, partial = oracle.decode_page(captured['requests'], now=captured['read_ts'])
    assert len(rows) == 100 and partial
    assert rows[0]['id'] == captured['requests'][0]['id']
    assert any(row['status'] == 'mismatch' for row in rows)
    assert oracle.decode_page([], now=captured['read_ts']) == ([], False)
    with pytest.raises(ValueError):
        oracle.decode_page([{'id': False}], now=captured['read_ts'])


def test_consecutive_hashes_share_wallet_but_keep_exact_cluster_and_seat(captured):
    raw = copy.deepcopy(captured['detail'])
    a, b = raw['members'][:2]
    b['wallet'] = a['wallet']
    b['answer'] = copy.deepcopy(a['answer'])
    a['tokenId'], b['tokenId'] = '12', '15'
    raw['agreement']['cluster'] = [b['submissionHash']]
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    entry = oracle.decode_detail(raw, row, read_ts=captured['read_ts'])
    detail = oracle.project_detail(entry)
    first, second = detail['members'][:2]
    assert first['panel_state'] == 'outvoted'
    assert second['panel_state'] == 'agreed'
    assert [first['seat'], second['seat']] == [12, 15]
    assert first['oracle_seat_answer'] == second['oracle_seat_answer']
    assert set(first) == set(SURF_ROW_KEYS['swarm_seat_work_rows']) | {'seat'}
    assert first['work_status'] is None and first['job_state'] is None
    assert 'wallet' not in json.dumps(entry) and 'attestation' not in json.dumps(entry)


@pytest.mark.parametrize('status,states', [('attested', ['outvoted', 'agreed']),
    ('disagreed', ['no_quorum_out', 'no_quorum_in']), ('assessing', ['assessing'] * 2),
    ('mismatch', ['unavailable'] * 2), ('new-status', ['unavailable'] * 2)])
def test_status_is_canonical_not_guessed(captured, status, states):
    raw = captured['detail']; raw['status'] = status
    raw['agreement']['cluster'] = [raw['members'][1]['submissionHash']]
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    detail = oracle.project_detail(oracle.decode_detail(raw, row, read_ts=captured['read_ts']))
    assert detail['status'] == status
    assert [m['panel_state'] for m in detail['members'][:2]] == states


@pytest.mark.parametrize('token,expected', [(None, None), ('14', 14), (0, 0),
    (True, None), ('-1', None), ('١٢', None), ('12_2', None)])
def test_member_seat_has_no_wallet_fallback(captured, token, expected):
    raw = captured['detail']; raw['members'][0]['tokenId'] = token
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    member = oracle.project_detail(oracle.decode_detail(raw, row, read_ts=captured['read_ts']))['members'][0]
    assert member['seat'] == expected


def test_captured_outcomes_and_figure_remain_exact(captured):
    for raw in captured['details'].values():
        row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
        detail = oracle.project_detail(oracle.decode_detail(raw, row, read_ts=captured['read_ts']))
        assert detail['member_count'] == len(raw['members'])
        for member in detail['members']:
            key = member['submission_hash']
            point = sw.oracle_point(raw, raw['jobId'], key, now_ts=captured['read_ts'])
            assert member['panel_figure'] == point['figure']
            assert member['oracle_member_ok'] == point['member_ok']
    raw = captured['detail']; raw.update(status='blocked', members=None, agreement=None)
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    detail = oracle.project_detail(oracle.decode_detail(raw, row, read_ts=captured['read_ts']))
    assert detail['status'] == 'blocked' and detail['members'] == [] and detail['member_count'] == 0


def test_detail_identity_conflicting_duplicates_and_member_bound(captured):
    raw = captured['detail']
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    wrong = dict(raw, id=captured['requests'][1]['id'])
    assert oracle.decode_detail(wrong, row, read_ts=captured['read_ts']) is None
    raw['members'].append(dict(raw['members'][0], ok=not raw['members'][0]['ok']))
    entry = oracle.decode_detail(raw, row, read_ts=captured['read_ts'])
    assert entry['truncated']
    assert all(m['hash'] != raw['members'][0]['submissionHash'] for m in entry['members'])
    raw['members'] = [dict(raw['members'][0], submissionHash=f'{i:064x}') for i in range(70)]
    entry = oracle.decode_detail(raw, row, read_ts=captured['read_ts'])
    assert len(entry['members']) == 64 and entry['member_count'] == 70 and entry['truncated']
    assert all(len(json.dumps(m['point']).encode()) <= 6000 for m in entry['members'])


def test_persisted_points_revalidated_independently_and_old_details_remain_stale_evidence(captured):
    now = captured['read_ts']; rows, partial = oracle.decode_page(captured['requests'], now=now)
    entry = oracle.decode_detail(captured['detail'], rows[0], read_ts=now)
    payload = dict(rows=rows, partial=partial, read_ts=now, details={rows[0]['id']: entry})
    assert oracle.coerce_snapshot(payload, now=now) == payload
    entry['members'][0]['point']['in_cluster'] = 'yes'
    clean = oracle.coerce_snapshot(payload, now=now)
    assert len(clean['details'][rows[0]['id']]['members']) == len(entry['members']) - 1
    assert clean['details'][rows[0]['id']]['truncated']
    assert oracle.coerce_snapshot(payload, now=now + 86401)['details'] == clean['details']


def test_malformed_member_does_not_discard_valid_siblings(captured):
    raw = captured['detail']; raw['members'].append(None)
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    entry = oracle.decode_detail(raw, row, read_ts=captured['read_ts'])
    assert entry is not None
    assert entry['member_count'] == len(raw['members'])
    assert len(entry['members']) == len(raw['members']) - 1 and entry['truncated']


@pytest.mark.parametrize('kind,value,expected', [('bool', False, 'false'),
    ('bool', 'false', None), ('uint256', '0', '0'), ('address[]', [], '')])
def test_false_zero_and_empty_typed_answers_remain_distinct(captured, kind, value, expected):
    raw = captured['detail']; raw['answerType'] = kind
    raw['agreement'].update(answer=False, figure='0')
    raw['members'][0]['answer']['answer'] = value
    row = oracle.decode_page([raw], now=captured['read_ts'])[0][0]
    detail = oracle.project_detail(oracle.decode_detail(raw, row, read_ts=captured['read_ts']))
    assert detail['panel_answer_bool'] is False and detail['panel_figure'] == '0'
    assert detail['members'][0]['oracle_seat_answer'] == expected
