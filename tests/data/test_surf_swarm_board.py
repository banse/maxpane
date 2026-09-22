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


@pytest.mark.parametrize('field', list(_COUNTERS.values()))
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
    for key in ('seats', 'attempts', 'accepted', 'rejected', 'pending', 'receipts', 'tokens_per_completed_job'):
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
    for key in ('attempts', 'accepted', 'rejected', 'pending'):
        assert summary[key] == sum(row[key] for row in contributors['contributors'])
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
def test_malformed_worker_is_dropped_not_falsely_idle(workers, field, value):
    row = copy.deepcopy(workers['workers'][0]); row[field] = value
    assert sw.normalize_workers({'workers': [row]})['workers'] == []


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
        corrupt = copy.deepcopy(slot); corrupt[name][0]['device_key'] = None
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
