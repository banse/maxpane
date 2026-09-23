"""BOARD folds over committed v3 captures; all derived truths recomputed here.

No clock or transport: source timestamps come from the frozen payloads. Shapes
created below only reshape those captures to exercise unavailable and malformed data.
"""
from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_models import (
    SURF_ROW_KEYS, SWARM_BOARD_SUMMARY_FIELDS, SWARM_FLEET_FIELDS,
    SWARM_SEAT_CONTRIB_FIELDS, SWARM_SEAT_LIVE_FIELDS,
)
from tests.surf_swarm_fixtures import swarm_capture_v3


def _iso(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


@pytest.fixture
def contributors():
    return swarm_capture_v3('contributors')


@pytest.fixture
def workers():
    return swarm_capture_v3('workers')


_COUNTERS = {
    'attempts': 'attempts', 'accepted': 'accepted', 'rejected': 'rejected',
    'pending': 'pending', 'turns': 'turns', 'wall_clock_ms': 'wallClockMs',
    'input_tokens': 'inputTokens', 'output_tokens': 'outputTokens',
    'cached_input_tokens': 'cachedInputTokens',
}


def test_device_counters_aggregate_by_token_before_ranking(contributors, workers):
    rows = sw.board_rows(contributors, workers)
    expected = {}
    for device in contributors['contributors']:
        token = int(device['tokenId'])
        seat = expected.setdefault(token, {'devices': 0, **dict.fromkeys(_COUNTERS, 0)})
        seat['devices'] += 1
        for key, source in _COUNTERS.items():
            seat[key] += int(device[source])
    order = sorted(expected, key=lambda token: (
        -expected[token]['accepted'],
        -(expected[token]['accepted'] / expected[token]['attempts']) if expected[token]['attempts'] else 1,
        token,
    ))
    assert [row['token_id'] for row in rows] == order
    for rank, row in enumerate(rows, 1):
        assert tuple(row) == SURF_ROW_KEYS['swarm_board_rows']
        source = expected[row['token_id']]
        assert row['rank'] == rank
        for key in ('devices', 'attempts', 'accepted', 'rejected', 'pending', 'turns'):
            assert row[key] == source[key]
        assert row['wall_clock_s'] == source['wall_clock_ms'] / 1000
        assert row['accept_rate'] == (source['accepted'] / source['attempts'] if source['attempts'] else None)
    duplicate = next(row for row in rows if row['token_id'] == 1089)
    devices = [row for row in contributors['contributors'] if row['tokenId'] == '1089']
    assert len(devices) > 1
    assert duplicate['attempts'] == sum(row['attempts'] for row in devices)
    normalized = sw.normalize_contributors(contributors)
    for row, original in zip(normalized['contributors'], contributors['contributors']):
        for key, source in _COUNTERS.items():
            assert row[key] == int(original[source])


@pytest.mark.parametrize('bad', ['12.5', '-1', True, False, 12.5, -1, '+12', ' 12', '12 ', '١٢', '', None])
def test_strict_decimal_counter_parser_never_coerces_garbage(bad):
    assert sw._served_token(bad) is None


@pytest.mark.parametrize('field', ['attempts', 'accepted', 'rejected', 'pending', 'turns', 'wallClockMs'])
@pytest.mark.parametrize('bad', ['12.5', '-1', True, None])
def test_any_malformed_required_contributor_counter_drops_its_row(contributors, field, bad):
    source = copy.deepcopy(contributors['contributors'][0])
    source[field] = bad
    assert sw.board_rows({'contributors': [source]}, None) == []


@pytest.mark.parametrize('good', [0, 12, '0', '12', '0012'])
def test_strict_decimal_counter_parser_accepts_nonnegative_ascii_integers(good):
    assert sw._served_token(good) == int(good)


@pytest.mark.parametrize('source', [None, {}, {'contributors': None}, {'contributors': {}}, {'contributors': 'bad'}])
def test_missing_contributors_is_unread_not_an_empty_board(source, workers):
    assert sw.board_rows(source, workers) is None
    assert sw.seat_contrib(source, 420) is None
    summary = sw.board_summary(source, workers)
    for key in ('seats', 'attempts', 'accepted', 'rejected', 'pending', 'devices', 'turns',
                'wall_clock_ms', 'input_tokens', 'output_tokens', 'receipts', 'tokens_per_completed_job'):
        assert summary[key] is None
    assert summary['live'] == workers['count']


@pytest.mark.parametrize('source', [None, {}, {'workers': None}, {'workers': {}}, {'workers': 'bad'}])
def test_offline_and_unavailable_remain_distinct(contributors, source):
    unread = sw.board_rows(contributors, source)
    offline = sw.board_rows(contributors, {'count': 0, 'workers': []})
    assert unread and offline
    assert all(row['live_state'] is None and row['runtime'] is None for row in unread)
    assert all(row['live_state'] == 'offline' and row['runtime'] == 'offline' for row in offline)
    assert sw.seat_live(source, 420) is None
    assert sw.seat_live({'workers': []}, 420)['live'] is False
    assert sw.fleet(source) is None


def test_served_empty_sources_are_real_zeros_and_not_listed():
    contributors = {'contributors': [], 'receipts': 0, 'tokensPerCompletedJob': 0}
    workers = {'workers': [], 'count': 0}
    summary = sw.board_summary(contributors, workers)
    assert tuple(summary) == SWARM_BOARD_SUMMARY_FIELDS
    assert all(value == 0 for value in summary.values())
    assert sw.board_rows(contributors, workers) == []
    absent = sw.seat_contrib(contributors, 420)
    assert tuple(absent) == SWARM_SEAT_CONTRIB_FIELDS
    assert absent['listed'] is False
    assert all(value is None for key, value in absent.items() if key != 'listed')
    assert sw.seat_contrib(None, 420) is None
    assert sw.fleet(workers)['paused'] == []


def test_board_summary_keeps_both_sources_and_served_totals(contributors, workers):
    summary = sw.board_summary(contributors, workers)
    assert tuple(summary) == SWARM_BOARD_SUMMARY_FIELDS
    assert summary['seats'] == len({row['tokenId'] for row in contributors['contributors']})
    for key in ('attempts', 'accepted', 'rejected', 'pending', 'turns'):
        assert summary[key] == sum(row[key] for row in contributors['contributors'])
    for key, served in (('wall_clock_ms', 'wallClockMs'), ('input_tokens', 'inputTokens'),
                        ('output_tokens', 'outputTokens')):
        assert summary[key] == sum(int(row[served]) for row in contributors['contributors'])
    assert summary['devices'] == len(contributors['contributors'])
    assert summary['live'] == workers['count']
    assert summary['paused'] == len({row['seat']['tokenId'] for row in workers['workers'] if row['paused']})
    assert summary['capacity'] == sum(row['maxConcurrency'] for row in workers['workers'])
    assert summary['working'] == sum(row['working'] for row in workers['workers'])
    assert summary['receipts'] == contributors['receipts']
    assert summary['tokens_per_completed_job'] == contributors['tokensPerCompletedJob']
    modified = dict(workers, count=999)
    assert sw.board_summary(contributors, modified)['live'] == 999
    assert sw.board_summary(contributors, dict(workers, count=True))['live'] is None
    assert sw.board_summary(None, None) == dict.fromkeys(SWARM_BOARD_SUMMARY_FIELDS)


def test_contributor_token_sums_are_unknown_when_one_row_does_not_serve_them(contributors):
    """inputTokens/outputTokens are optional per row: one unserved row makes
    that sum unknown, never a smaller number; the required counters still sum."""
    source = copy.deepcopy(contributors)
    del source['contributors'][0]['inputTokens']
    summary = sw.board_summary(source, None)
    assert summary['input_tokens'] is None
    assert summary['output_tokens'] == sum(int(r['outputTokens']) for r in source['contributors'])
    assert summary['turns'] == sum(r['turns'] for r in source['contributors'])


def test_a_malformed_contributor_leaves_every_contributor_sum_unknown(contributors):
    source = copy.deepcopy(contributors)
    source['contributors'][0]['turns'] = '-1'
    summary = sw.board_summary(source, None)
    for key in ('attempts', 'accepted', 'rejected', 'pending', 'devices', 'turns',
                'wall_clock_ms', 'input_tokens', 'output_tokens'):
        assert summary[key] is None, key
    assert summary['seats'] == len({r['tokenId'] for r in source['contributors']})


def test_fleet_mixes_and_heartbeats_are_derived_from_each_worker(workers):
    result = sw.fleet(workers)
    assert tuple(result) == SWARM_FLEET_FIELDS
    sources = workers['workers']
    for key, values in {
        'daemons': [row['daemonVersion'] for row in sources],
        'os': [row['platform']['os'] for row in sources],
        'profiles': ['+'.join(sorted(set(row['profiles']))) or 'none' for row in sources],
        'concurrency': [str(row['maxConcurrency']) for row in sources],
    }.items():
        counts = Counter(values)
        assert result[key] == [{'value': key, 'count': count} for key, count in sorted(counts.items(), key=lambda p: (-p[1], p[0]))]
    runtime_counts = Counter()
    for row in sources:
        names = {runtime['id'] for runtime in row['runtimes']}
        bucket = 'both' if names == {'codex', 'claude'} else '+'.join(sorted(names)) or 'none'
        runtime_counts[bucket] += 1
    assert result['runtimes'] == [{'value': key, 'count': count} for key, count in sorted(runtime_counts.items(), key=lambda p: (-p[1], p[0]))]
    stamps = [_iso(row['lastHeartbeatAt']) for row in sources]
    assert result['heartbeat_oldest_ts'] == min(stamps)
    assert result['heartbeat_newest_ts'] == max(stamps)


def test_paused_until_and_failures_are_the_same_device_fact(workers):
    paused = [row for row in workers['workers'] if row['paused']]
    assert paused
    expected = sorted([
        {'token_id': int(row['seat']['tokenId']), 'until_ts': _iso(row['paused']['until']),
         'failures': row['paused']['consecutiveFailures']} for row in paused
    ], key=lambda row: (row['until_ts'], row['token_id']))
    assert sw.fleet(workers)['paused'] == expected
    for row in paused:
        live = sw.seat_live(workers, int(row['seat']['tokenId']))
        assert live['paused_until_ts'] == _iso(row['paused']['until'])
        assert live['failures'] == row['paused']['consecutiveFailures']


def test_multidevice_live_state_priority_and_pause_tie_pairing(contributors, workers):
    base = copy.deepcopy(workers['workers'][0])
    token = int(contributors['contributors'][0]['tokenId'])
    base['seat']['tokenId'] = str(token)
    first = dict(base, deviceKey='z', working=0, maxConcurrency=2,
                 paused={'until': '2026-09-22T02:10:00Z', 'consecutiveFailures': 9})
    earliest = dict(base, deviceKey='b', working=0, maxConcurrency=3,
                    paused={'until': '2026-09-22T02:00:00Z', 'consecutiveFailures': 4})
    tied = dict(earliest, deviceKey='a', paused={'until': '2026-09-22T02:00:00Z', 'consecutiveFailures': 2})
    idle = dict(base, deviceKey='idle', working=0, maxConcurrency=1, paused=None)
    fleet = {'workers': [first, earliest, tied, idle], 'count': 4}
    live = sw.seat_live(fleet, token)
    assert live['working'] == 0 and live['max_concurrency'] == 9 and live['devices'] == 4
    assert live['paused_until_ts'] == _iso(tied['paused']['until'])
    assert live['failures'] == tied['paused']['consecutiveFailures']
    row = next(row for row in sw.board_rows(contributors, fleet) if row['token_id'] == token)
    assert row['live_state'] == 'paused'
    fleet['workers'].append(dict(base, deviceKey='working', working=2, maxConcurrency=5, paused=None))
    row = next(row for row in sw.board_rows(contributors, fleet) if row['token_id'] == token)
    assert row['live_state'] == 'working' and row['working'] == 2
    assert sw.seat_live(fleet, token)['max_concurrency'] == 14
    assert sw.fleet({'workers': [idle]})['paused'] == []
    row = next(row for row in sw.board_rows(contributors, {'workers': [idle]}) if row['token_id'] == token)
    assert row['live_state'] == 'idle'


def test_selected_contrib_rank_uses_aggregated_board_and_stays_separate_from_seats(contributors):
    rows = sw.board_rows(contributors, None)
    seat = swarm_capture_v3('seat_420_with_contributors')
    selected = sw.seat_contrib(contributors, int(seat['tokenId']))
    assert tuple(selected) == SWARM_SEAT_CONTRIB_FIELDS
    row = next(row for row in rows if row['token_id'] == int(seat['tokenId']))
    assert selected == {'listed': True, **{key: row[key] for key in (
        'attempts', 'accepted', 'rejected', 'pending', 'turns', 'wall_clock_s', 'rank')}, 'ranked_of': len(rows)}
    assert selected['accepted'] != seat['accepted']
    assert sw.seat_contrib({'contributors': []}, int(seat['tokenId']))['listed'] is False
    assert sw.seat_contrib(None, int(seat['tokenId'])) is None


def test_optional_worker_metadata_preserves_missing_empty_and_union(workers):
    row = copy.deepcopy(workers['workers'][0]); token = int(row['seat']['tokenId'])
    result = sw.seat_live({'workers': [row]}, token)
    assert tuple(result) == SWARM_SEAT_LIVE_FIELDS
    assert result['skills'] == len(set(row['skills']))
    assert result['profiles'] == sorted(set(row['profiles']))
    assert result['platform'] == f"{row['platform']['os']} {row['platform']['arch']}"
    second = copy.deepcopy(row); second.update(deviceKey='second', skills=['extra'], profiles=['extra'])
    result = sw.seat_live({'workers': [row, second]}, token)
    assert result['skills'] == len(set(row['skills']) | {'extra'})
    assert result['profiles'] == sorted(set(row['profiles']) | {'extra'})
    for key in ('skills', 'profiles', 'platform'):
        row.pop(key)
    result = sw.seat_live({'workers': [row]}, token)
    assert result['skills'] is result['profiles'] is result['platform'] is None
    result = sw.seat_live({'workers': [dict(row, skills=[], profiles=[])]}, token)
    assert result['skills'] == 0 and result['profiles'] == []


@pytest.mark.parametrize('field,value', [('working', True), ('maxConcurrency', '-1'), ('paused', {}), ('paused', {'until': 'bad', 'consecutiveFailures': 3}), ('paused', {'until': '2026-09-22T02:00:00Z', 'consecutiveFailures': True}), ('seat', {'tokenId': False}), ('deviceKey', '')])
def test_worker_field_defects_do_not_erase_a_valid_token(workers, field, value):
    row = copy.deepcopy(workers['workers'][0]); row[field] = value
    normalized = sw.normalize_workers({'workers': [row]})['workers']
    if field == 'seat':
        assert normalized == []
    else:
        assert len(normalized) == 1
        assert sw.seat_live({'workers': [row]}, int(row['seat']['tokenId']))['live'] is True


def test_huge_wall_clock_integer_degrades_only_float_conversion(contributors):
    row = copy.deepcopy(contributors['contributors'][0]); row['wallClockMs'] = 10 ** 500
    result = sw.board_rows({'contributors': [row]}, None)[0]
    assert result['wall_clock_s'] is None
    assert result['attempts'] == row['attempts']
    row['wallClockMs'] = '9' * 5000
    assert sw.board_rows({'contributors': [row]}, None) == []


def test_normalized_slot_roundtrips_validate_without_reparsing(contributors, workers):
    for name, raw, normalize, coerce in (
        ('contributors', contributors, sw.normalize_contributors, sw.coerce_contributors_slot),
        ('workers', workers, sw.normalize_workers, sw.coerce_workers_slot),
    ):
        slot = normalize(raw)
        assert coerce(slot) == slot
        corrupt = copy.deepcopy(slot); corrupt[name][0]['token_id'] = str(corrupt[name][0]['token_id'])
        assert coerce(corrupt) is None
        corrupt = copy.deepcopy(slot); corrupt[name][0]['device_key'] = 123
        assert coerce(corrupt) is None
        assert coerce({name: 'bad'}) is None


@pytest.mark.parametrize('name', ['contributors', 'workers'])
def test_normalized_slots_refuse_every_field_with_a_wrong_type(name):
    normalize = getattr(sw, f'normalize_{name}')
    coerce = getattr(sw, f'coerce_{name}_slot')
    slot = normalize(swarm_capture_v3(name))
    for key in slot:
        corrupt = copy.deepcopy(slot); corrupt[key] = {'not': 'a valid field'}
        assert coerce(corrupt) is None, key
    for key in slot[name][0]:
        corrupt = copy.deepcopy(slot); corrupt[name][0][key] = {'not': 'a valid field'}
        assert coerce(corrupt) is None, key
    for key in slot[name][0]:
        corrupt = copy.deepcopy(slot); del corrupt[name][0][key]
        assert coerce(corrupt) is None, key


def test_normalized_slot_rejects_nonfinite_timestamps_and_mismatched_pause_pair(workers):
    slot = sw.normalize_workers(workers)
    for bad in (float('nan'), float('inf'), True, '123'):
        corrupt = copy.deepcopy(slot); corrupt['workers'][0]['heartbeat_ts'] = bad
        assert sw.coerce_workers_slot(corrupt) is None
    corrupt = copy.deepcopy(slot)
    corrupt['workers'][0].update(paused_until_ts=123.0, failures=None)
    assert sw.coerce_workers_slot(corrupt) is None


def test_inflight_note_prefers_dispatch_and_falls_back_to_failure():
    job = swarm_capture_v3('job_5a4dfb13_dispatch_note')
    details = {job['id']: job}
    expected_node = next(node for node in job['nodes'] if node.get('dispatchNote'))
    expected_node['failureReason'] = 'secondary reason'
    row = sw.inflight_rows([job], details, now_ts=_iso(job['updatedAt']))[0]
    assert row['note'] == expected_node['dispatchNote'] and row['note_kind'] == 'dispatch'
    expected_node['dispatchNote'] = None
    row = sw.inflight_rows([job], details, now_ts=_iso(job['updatedAt']))[0]
    assert row['note'] == 'secondary reason' and row['note_kind'] == 'failure'
    expected_node['failureReason'] = None
    row = sw.inflight_rows([job], details, now_ts=_iso(job['updatedAt']))[0]
    assert row['note'] is row['note_kind'] is None
    blocked = swarm_capture_v3('job_0ed3e9f8_blocked')
    assert sw.inflight_rows([blocked], {blocked['id']: blocked}, now_ts=0) == []


def test_huge_inconsistent_acceptance_counter_cannot_overflow_the_rate(contributors):
    row = copy.deepcopy(contributors['contributors'][0])
    row.update(attempts=1, accepted=10 ** 500)
    result = sw.board_rows({'contributors': [row]}, None)[0]
    assert result['accept_rate'] is None
    assert result['accepted'] == row['accepted']


@pytest.mark.parametrize('field,value', [('tokenId', True), ('tokenId', '١٢'), ('tokenId', '-1'), ('deviceKey', ''), ('deviceKey', None)])
def test_malformed_contributor_identity_is_dropped(contributors, field, value):
    row = copy.deepcopy(contributors['contributors'][0]); row[field] = value
    assert sw.board_rows({'contributors': [row]}, None) == []


@pytest.mark.parametrize('field', ['runtimes', 'profiles', 'skills'])
def test_normalized_worker_lists_refuse_bad_members(workers, field):
    slot = sw.normalize_workers(workers)
    slot['workers'][0][field] = ['valid', 123]
    assert sw.coerce_workers_slot(slot) is None


# §9 I1: malformed fields never fabricate offline / not-listed identities.

@pytest.mark.parametrize('optional', ['inputTokens', 'outputTokens', 'cachedInputTokens'])
def test_i1_optional_token_counter_keeps_v3_seat420_listed(contributors, workers, optional):
    original_seats = {int(row['tokenId']) for row in contributors['contributors']}
    for row in contributors['contributors']:
        if row['tokenId'] == '420':
            row[optional] = None
    slot = sw.normalize_contributors(contributors)
    normalized = next(row for row in slot['contributors'] if row['token_id'] == 420)
    field = next(key for key, source in _COUNTERS.items() if source == optional)
    assert normalized[field] is None
    assert slot['malformed_tokens'] == []
    assert sw.seat_contrib(contributors, 420)['listed'] is True
    assert any(row['token_id'] == 420 for row in sw.board_rows(contributors, workers))
    assert sw.board_summary(contributors, workers)['seats'] == len(original_seats)


def test_i1_missing_pause_keeps_v3_worker420_live_but_not_idle(contributors, workers):
    row = next(row for row in workers['workers'] if row['seat']['tokenId'] == '420')
    row.pop('paused')
    assert sw.seat_live(workers, 420)['live'] is True
    selected = next(row for row in sw.board_rows(contributors, workers) if row['token_id'] == 420)
    assert selected['live_state'] is None
    assert selected['runtime'] != 'offline'
    assert sw.board_summary(contributors, workers)['live'] == workers['count']
    normalized = next(row for row in sw.normalize_workers(workers)['workers'] if row['token_id'] == 420)
    assert normalized['pause_known'] is False
    assert normalized['paused_until_ts'] is normalized['failures'] is None


@pytest.mark.parametrize('source', ['contributors', 'workers'])
@pytest.mark.parametrize('bad', [True, -1, 'not-a-token', '١٢', None])
def test_i1_bad_token_ids_still_drop_without_made_up_malformed_identity(source, bad):
    payload = swarm_capture_v3(source)
    row = copy.deepcopy(payload[source][0])
    (row['seat'] if source == 'workers' else row)['tokenId'] = bad
    normalized = getattr(sw, f'normalize_{source}')({source: [row]})
    assert normalized[source] == []
    assert normalized['malformed_tokens'] == []


@pytest.mark.parametrize('field', ['attempts', 'accepted', 'rejected', 'pending', 'turns', 'wallClockMs', 'deviceKey'])
def test_i1_incomplete_token_suppresses_valid_sibling_and_full_source_totals(contributors, workers, field):
    original_seats = {int(row['tokenId']) for row in contributors['contributors']}
    original = next(row for row in contributors['contributors'] if row['tokenId'] == '420')
    invalid = copy.deepcopy(original); invalid['deviceKey'] = 'another-device'; invalid[field] = None
    contributors['contributors'].append(invalid)
    slot = sw.normalize_contributors(contributors)
    assert slot['malformed_tokens'] == [420]
    assert sw.seat_contrib(contributors, 420) is None
    rows = sw.board_rows(contributors, workers)
    assert rows and all(row['token_id'] != 420 for row in rows)
    assert all(row['rank'] is None for row in rows)
    summary = sw.board_summary(contributors, workers)
    assert summary['seats'] == len(original_seats)
    assert all(summary[key] is None for key in ('attempts', 'accepted', 'rejected', 'pending'))
    assert summary['receipts'] == contributors['receipts']
    assert summary['tokens_per_completed_job'] == contributors['tokensPerCompletedJob']
    good = rows[0]['token_id']
    selected = sw.seat_contrib(contributors, good)
    assert selected['listed'] is True and selected['rank'] is None
    assert selected['ranked_of'] == len(original_seats)
    assert selected['accepted'] == rows[0]['accepted']


def test_i1_unknown_worker_counts_are_not_partial_totals_or_none_mix_buckets(workers, contributors):
    original = copy.deepcopy(next(row for row in workers['workers'] if row['seat']['tokenId'] == '420'))
    original.update(working=2, maxConcurrency=3, paused=None)
    unknown = copy.deepcopy(original)
    unknown.update(deviceKey=None, working=None, maxConcurrency=None)
    unknown.pop('paused')
    workers['workers'] = [original, unknown]
    live = sw.seat_live(workers, 420)
    assert live['live'] is True and live['devices'] == 2
    assert live['working'] is live['max_concurrency'] is None
    summary = sw.board_summary(contributors, workers)
    assert summary['working'] is summary['capacity'] is None
    assert sw.fleet(workers)['concurrency'] == [{'value': '3', 'count': 1}]
    row = next(row for row in sw.board_rows(contributors, workers) if row['token_id'] == 420)
    assert row['live_state'] == 'working' and row['working'] is None
    original['working'] = 0
    original['paused'] = {'until': '2026-09-22T02:00:00Z', 'consecutiveFailures': 3}
    row = next(row for row in sw.board_rows(contributors, workers) if row['token_id'] == 420)
    assert row['live_state'] == 'paused'
    original['paused'] = None
    row = next(row for row in sw.board_rows(contributors, workers) if row['token_id'] == 420)
    assert row['live_state'] is None


@pytest.mark.parametrize('source', ['workers', 'contributors'])
@pytest.mark.parametrize('bad', [None, {}, [True], [-1], ['420'], [420, 420], [421, 420]])
def test_i1_malformed_tokens_metadata_is_strict(source, bad):
    slot = getattr(sw, f'normalize_{source}')(swarm_capture_v3(source))
    slot['malformed_tokens'] = bad
    assert getattr(sw, f'coerce_{source}_slot')(slot) is None


@pytest.mark.parametrize('source', ['workers', 'contributors'])
def test_i1_old_slots_lacking_lost_identity_metadata_are_refused(source):
    slot = getattr(sw, f'normalize_{source}')(swarm_capture_v3(source))
    slot.pop('malformed_tokens')
    assert getattr(sw, f'coerce_{source}_slot')(slot) is None


@pytest.mark.parametrize('bad', [None, 0, 1, 'true'])
def test_i1_pause_known_is_a_strict_internal_boolean(workers, bad):
    slot = sw.normalize_workers(workers)
    slot['workers'][0]['pause_known'] = bad
    assert sw.coerce_workers_slot(slot) is None


def test_i1_unknown_pause_cannot_persist_a_conflicting_known_pair(workers):
    slot = sw.normalize_workers(workers)
    row = next(row for row in slot['workers'] if row['paused_until_ts'] is not None)
    row['pause_known'] = False
    assert sw.coerce_workers_slot(slot) is None
    slot = sw.normalize_workers(workers)
    del slot['workers'][0]['pause_known']
    assert sw.coerce_workers_slot(slot) is None
