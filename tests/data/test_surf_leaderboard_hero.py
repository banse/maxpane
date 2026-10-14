"""LEADERBOARD card facts retain canonical records and independent source clocks."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_leaderboard_hero as hero
from maxpane_dashboard.data.surf_models import SURF_LEADERBOARD_HERO_FIELDS, SURF_LEADERBOARD_HERO_STATES


def test_frozen_board_refresh_contract():
    assert SURF_LEADERBOARD_HERO_FIELDS == {
        'top': ('state', 'read_ts', 'token_id', 'accepted', 'rank', 'empty', 'percent'),
        'recorded': ('state', 'read_ts', 'seats', 'attempts', 'online', 'online_state', 'online_read_ts'),
        'rate': ('state', 'read_ts', 'accepted', 'attempts', 'percent'),
        'launches': ('state', 'read_ts', 'seats', 'claude', 'codex', 'jobs', 'runtime_known', 'runtime_state', 'runtime_read_ts',
                     'percent', 'total_seats', 'records_state', 'records_read_ts'),
        'workers': ('state', 'read_ts', 'live', 'working', 'capacity', 'runtime', 'runtime_percent',
                    'runtime_count', 'runtime_total', 'runtime_known'),
        'effort': ('state', 'read_ts', 'tokens', 'turns', 'hours', 'wall_clock_ms'),
    }
    assert {'pending', 'failed'} <= set(SURF_LEADERBOARD_HERO_STATES)


@pytest.fixture
def snapshot():
    return dict(now=1000, sources={
        'records': dict(state='ok', read_ts=900),
        'workers': dict(state='ok', read_ts=980, payload=dict(count=3, malformed_tokens=[],
            workers=[dict(token_id=7, runtimes=['claude']), dict(token_id=7, runtimes=['codex']),
                     dict(token_id=999, runtimes=['claude'])])),
        'contributors': dict(state='ok', read_ts=800),
    }, data=dict(swarm_board_rows=[
        dict(rank=2, token_id=7, accepted=10, attempts=20),
        dict(rank=1, token_id=527, accepted=40, attempts=60),
    ], swarm_board_summary=dict(seats=2, accepted=50, attempts=80,
        rejected=20, failed=5, pending=5, live=3, working=2, capacity=9,
        receipts=96, turns=120, wall_clock_ms=9_000_000,
        input_tokens=12_000, output_tokens=3_000, cached_input_tokens=10_000,
        receipt_seats=999, receipt_accepted=888, receipt_attempts=777),
        swarm_launch_contribution=dict(summary=dict(state='ok', read_ts=700, seats=2,
            claude=1, codex=1, jobs=3, runtime_known=1, runtime_state='ok', runtime_read_ts=980,
            percent=100, total_seats=2, records_state='ok', records_read_ts=900))))


def test_literal_contract_canonical_rank_counts_hours_and_independent_clocks(snapshot):
    before = deepcopy(snapshot)
    result = hero.project(**snapshot)
    expected = dict(
        top=dict(state='ok', read_ts=900, token_id=527, accepted=40, rank=1, empty=False, percent=40 / 60 * 100),
        recorded=dict(state='ok', read_ts=900, seats=2, attempts=80, online=1, online_state='ok', online_read_ts=980),
        rate=dict(state='ok', read_ts=900, accepted=50, attempts=80, percent=62.5),
        launches=snapshot['data']['swarm_launch_contribution']['summary'],
        workers=dict(state='ok', read_ts=980, live=3, working=2, capacity=9, runtime='claude',
                     runtime_percent=100, runtime_count=2, runtime_total=2, runtime_known=2),
        effort=dict(state='ok', read_ts=800, tokens=15_000, turns=120, hours=2.5, wall_clock_ms=9_000_000),
    )
    assert result == expected
    assert tuple(result) == tuple(SURF_LEADERBOARD_HERO_FIELDS)
    for section, fields in SURF_LEADERBOARD_HERO_FIELDS.items():
        assert tuple(result[section]) == fields
        assert result[section]['state'] in SURF_LEADERBOARD_HERO_STATES
    assert snapshot == before
    snapshot['data']['swarm_board_rows'].reverse()
    assert hero.project(**snapshot) == expected
    result['launches']['jobs'] = 100
    assert snapshot['data']['swarm_launch_contribution']['summary']['jobs'] == 3


def test_cold_unknown_and_proven_empty_are_distinct(snapshot):
    cold = hero.project(data={}, sources={}, now=1000)
    assert all(card['state'] == 'unavailable' for card in cold.values())
    assert all(value is None for card in cold.values() for key, value in card.items()
               if key not in ('state', 'online_state', 'runtime_state', 'records_state'))
    snapshot['data']['swarm_board_rows'] = []
    snapshot['data']['swarm_board_summary'] = dict.fromkeys(snapshot['data']['swarm_board_summary'], 0)
    snapshot['sources']['workers']['payload'].update(count=0, workers=[])
    empty = hero.project(**snapshot)
    assert empty['top'] == dict(state='ok', read_ts=900, token_id=None, accepted=None, rank=None, empty=True, percent=None)
    assert empty['recorded'] == dict(state='ok', read_ts=900, seats=0, attempts=0,
                                    online=0, online_state='ok', online_read_ts=980)
    assert empty['rate'] == dict(state='ok', read_ts=900, accepted=0, attempts=0, percent=None)
    assert empty['workers'] == dict(state='ok', read_ts=980, live=0, working=0, capacity=0,
        runtime=None, runtime_percent=None, runtime_count=None, runtime_total=0, runtime_known=0)
    assert empty['effort'] == dict(state='ok', read_ts=800, tokens=0, turns=0, hours=0, wall_clock_ms=0)
    snapshot['sources']['records']['state'] = 'stale'
    dated = hero.project(**snapshot)
    assert dated['top'] == dict(empty['top'], state='stale')
    assert dated['rate'] == dict(empty['rate'], state='stale')
    snapshot['data']['swarm_board_rows'] = None
    assert hero.project(**snapshot)['top']['empty'] is None


@pytest.mark.parametrize('accepted,attempts,percent', [(0, 80, 0), (0, 0, None), (40, 60, 40 / 60 * 100)])
def test_top_and_rate_share_percentage_semantics(snapshot, accepted, attempts, percent):
    snapshot['data']['swarm_board_summary'].update(accepted=accepted, attempts=attempts)
    snapshot['data']['swarm_board_rows'][1].update(accepted=accepted, attempts=attempts)
    result = hero.project(**snapshot)
    assert result['top']['percent'] == result['rate']['percent'] == percent
    assert result['top']['state'] == result['rate']['state'] == 'ok'


def test_records_outage_preserves_other_sources_and_worker_marker(snapshot):
    before = hero.project(**snapshot)
    snapshot['sources']['records']['state'] = 'unavailable'
    result = hero.project(**snapshot)
    for section in ('top', 'recorded', 'rate'):
        assert result[section]['state'] == 'unavailable'
    assert result['recorded']['online'] is None
    assert result['recorded']['online_state'] == 'ok'
    assert result['recorded']['online_read_ts'] == 980
    for section in ('launches', 'workers', 'effort'):
        assert result[section] == before[section]


def test_worker_outage_preserves_records_and_effort(snapshot):
    before = hero.project(**snapshot)
    snapshot['sources']['workers']['state'] = 'unavailable'
    result = hero.project(**snapshot)
    assert result['recorded'] == dict(before['recorded'], online=None, online_state='unavailable')
    assert result['workers'] == dict(state='unavailable', read_ts=980, live=None, working=None, capacity=None,
        runtime=None, runtime_percent=None, runtime_count=None, runtime_total=None, runtime_known=None)
    for section in ('top', 'rate', 'effort', 'launches'):
        assert result[section] == before[section]


def test_stale_values_keep_their_actual_source_clock(snapshot):
    for source in snapshot['sources'].values():
        source['state'] = 'stale'
    result = hero.project(**snapshot)
    assert result['top']['accepted'] == 40 and result['top']['read_ts'] == 900
    assert result['recorded']['online'] == 1 and result['recorded']['online_state'] == 'stale'
    assert result['workers']['live'] == 3 and result['workers']['read_ts'] == 980
    assert result['effort']['hours'] == 2.5 and result['effort']['read_ts'] == 800
    assert result['launches']['state'] == 'ok'


@pytest.mark.parametrize('bad', [None, True, -1, '8', 0.5, float('nan'), float('inf')])
def test_invalid_fields_preserve_only_valid_neighbors(snapshot, bad):
    summary = snapshot['data']['swarm_board_summary']
    summary.update(accepted=bad, capacity=bad, wall_clock_ms=bad, input_tokens=bad)
    result = hero.project(**snapshot)
    assert result['rate'] == dict(state='partial', read_ts=900, accepted=None, attempts=80, percent=None)
    assert result['workers'] == dict(state='partial', read_ts=980, live=3, working=2, capacity=None,
        runtime='claude', runtime_percent=100, runtime_count=2, runtime_total=2, runtime_known=2)
    assert result['effort'] == dict(state='partial', read_ts=800, tokens=None, turns=120, hours=None, wall_clock_ms=None)
    assert result['top']['state'] == result['recorded']['state'] == 'ok'


@pytest.mark.parametrize('missing', ['input_tokens', 'output_tokens'])
def test_tokens_require_both_sources_and_never_add_cached_tokens(snapshot, missing):
    snapshot['data']['swarm_board_summary'][missing] = None
    result = hero.project(**snapshot)['effort']
    assert result['tokens'] is None and result['hours'] == 2.5
    snapshot['sources']['contributors']['state'] = 'unavailable'
    assert hero.project(**snapshot)['effort'] == dict(state='unavailable', read_ts=800,
        tokens=None, turns=None, hours=None, wall_clock_ms=None)


def test_wall_clock_preserves_exact_large_integer(snapshot):
    milliseconds = 2**53 + 1
    snapshot['data']['swarm_board_summary']['wall_clock_ms'] = milliseconds
    result = hero.project(**snapshot)['effort']
    assert type(result['wall_clock_ms']) is int and result['wall_clock_ms'] == milliseconds
    assert result['hours'] == milliseconds / 3_600_000


def test_impossible_acceptance_counts_never_publish_a_percentage(snapshot):
    snapshot['data']['swarm_board_summary'].update(accepted=81, attempts=80)
    snapshot['data']['swarm_board_rows'][1].update(accepted=61, attempts=60)
    result = hero.project(**snapshot)
    assert result['rate'] == dict(state='partial', read_ts=900, accepted=None, attempts=80, percent=None)
    assert result['top'] == dict(state='partial', read_ts=900, token_id=527, accepted=None, rank=1, empty=False, percent=None)


@pytest.mark.parametrize('rows', [[], None, [{}], [True],
    [dict(rank=True, token_id=527, accepted=40)],
    [dict(rank=1, token_id=True, accepted=40)],
    [dict(rank=1, token_id=527, accepted=40), dict(rank=1, token_id=7, accepted=10)]])
def test_partial_or_malformed_records_never_invent_top_or_prove_empty(snapshot, rows):
    snapshot['sources']['records']['state'] = 'partial'
    snapshot['data']['swarm_board_rows'] = rows
    assert hero.project(**snapshot)['top'] == dict(
        state='unavailable', read_ts=900, token_id=None, accepted=None, rank=None, empty=None, percent=None)


@pytest.mark.parametrize('state', ['partial', 'stale'])
def test_incomplete_roster_keeps_served_live_but_hides_partial_slot_sums(snapshot, state):
    snapshot['sources']['workers'].update(state=state, partial=True)
    result = hero.project(**snapshot)
    assert result['workers'] == dict(state=state, read_ts=980, live=3, working=None, capacity=None,
        runtime=None, runtime_percent=None, runtime_count=None, runtime_total=None, runtime_known=2)
    assert result['recorded']['online'] is None
    assert result['recorded']['online_state'] == state
    assert result['recorded']['state'] == 'ok'


@pytest.mark.parametrize('stamp', [None, 0, -1, True, float('nan'), float('inf'), 1001])
def test_bad_source_clock_cannot_publish_values(snapshot, stamp):
    snapshot['sources']['records']['read_ts'] = stamp
    result = hero.project(**snapshot)
    for name in ('top', 'recorded', 'rate'):
        assert result[name]['state'] == 'unavailable' and result[name]['read_ts'] is None
    assert result['workers']['state'] == result['effort']['state'] == 'ok'
    assert result['recorded']['online'] is None


@pytest.fixture
def launch_snapshot():
    return dict(state='ok', read_ts=700, jobs=4, rows=[dict(token_id=7), dict(token_id=527),
        dict(token_id=80), dict(token_id=90)])


def test_launch_runtime_families_deduplicate_seats_and_disclose_coverage(launch_snapshot):
    workers = dict(count=5, malformed_tokens=[], workers=[
        dict(token_id=7, runtimes=['claude', 'codex']), dict(token_id=7, runtimes=['claude']),
        dict(token_id=527, runtimes=['codex']), dict(token_id=80, runtimes=None),
        dict(token_id=999, runtimes=['claude'])])
    before = deepcopy((launch_snapshot, workers))
    assert hero.launch_facts(launch_snapshot, workers, dict(state='stale', read_ts=980)) == dict(
        state='ok', read_ts=700, seats=4, claude=1, codex=2, jobs=4, runtime_known=2,
        runtime_state='stale', runtime_read_ts=980,
        percent=None, total_seats=None, records_state='unavailable', records_read_ts=None)
    assert (launch_snapshot, workers) == before


@pytest.mark.parametrize('workers,source,expected_state', [
    (None, dict(state='unavailable', read_ts=None), 'unavailable'),
    (dict(count=1, malformed_tokens=[], workers=[]), dict(state='ok', read_ts=980), 'partial'),
    (dict(count=0, malformed_tokens=[7], workers=[]), dict(state='stale', read_ts=980), 'stale'),
])
def test_missing_or_partial_runtime_roster_cannot_invent_family_totals(launch_snapshot, workers, source, expected_state):
    result = hero.launch_facts(launch_snapshot, workers, source)
    assert result == dict(state='ok', read_ts=700, seats=4, claude=None, codex=None, jobs=4,
        runtime_known=None, runtime_state=expected_state, runtime_read_ts=source['read_ts'],
        percent=None, total_seats=None, records_state='unavailable', records_read_ts=None)


@pytest.mark.parametrize('state', ['pending', 'failed'])
def test_launch_initial_read_unknown_and_retained_complete_facts(launch_snapshot, state):
    source = dict(state='ok', read_ts=980)
    workers = dict(count=0, malformed_tokens=[], workers=[])
    initial = hero.launch_facts(dict(state=state, rows=None, jobs=None, read_ts=None), workers, source)
    assert initial == dict(state=state, read_ts=None, seats=None, claude=None, codex=None,
        jobs=None, runtime_known=None, runtime_state='ok', runtime_read_ts=980,
        percent=None, total_seats=None, records_state='unavailable', records_read_ts=None)
    launch_snapshot['state'] = 'pending' if state == 'pending' else 'stale'
    retained = hero.launch_facts(launch_snapshot, workers, source)
    assert retained['state'] == launch_snapshot['state']
    assert retained['seats'] == retained['jobs'] == 4 and retained['read_ts'] == 700
    assert retained['claude'] == retained['codex'] == retained['runtime_known'] == 0


def test_launch_known_empty_and_legacy_unknown_jobs(launch_snapshot):
    workers = dict(count=0, workers=[], malformed_tokens=[])
    source = dict(state='ok', read_ts=980)
    empty = hero.launch_facts(dict(state='ok', rows=[], read_ts=700, jobs=0), workers, source)
    assert empty == dict(state='ok', read_ts=700, seats=0, claude=0, codex=0, jobs=0,
        runtime_known=0, runtime_state='ok', runtime_read_ts=980,
        percent=None, total_seats=None, records_state='unavailable', records_read_ts=None)
    launch_snapshot['jobs'] = None
    legacy = hero.launch_facts(launch_snapshot, workers, source)
    assert legacy['jobs'] is None and legacy['seats'] == 4 and legacy['state'] == 'partial'


@pytest.mark.parametrize('state', ['ok', 'stale'])
@pytest.mark.parametrize('count,expected', [(8, 50), (4, 100), (3, None), (0, None)])
def test_launch_share_uses_independent_complete_recorded_denominator(launch_snapshot, state, count, expected):
    records = dict(state=state, read_ts=810, payload=dict(count=count))
    result = hero.launch_facts(launch_snapshot, None, dict(state='unavailable', read_ts=None), records)
    assert result['percent'] == expected and result['total_seats'] == count
    assert result['records_state'] == state and result['records_read_ts'] == 810
    assert result['state'] == 'ok' and result['read_ts'] == 700
    assert result['seats'] == result['jobs'] == 4


@pytest.mark.parametrize('state,payload,partial', [
    ('unavailable', dict(count=8), False), ('partial', dict(count=8), False),
    ('ok', None, False), ('ok', dict(count=8), True),
    ('stale', dict(count=None), False), ('ok', dict(count=True), False),
    ('ok', dict(count=-1), False), ('ok', dict(count=0.5), False),
])
def test_unread_or_partial_denominator_never_erases_launch_facts(launch_snapshot, state, payload, partial):
    records = dict(state=state, read_ts=810, payload=payload, partial=partial)
    result = hero.launch_facts(launch_snapshot, None, dict(state='unavailable', read_ts=None), records)
    assert result['percent'] is result['total_seats'] is None
    assert result['records_state'] == state and result['records_read_ts'] == 810
    assert result['state'] == 'ok' and result['seats'] == result['jobs'] == 4


@pytest.mark.parametrize('rows,state,expected', [([], 'ok', 0), (None, 'pending', None), (None, 'failed', None)])
def test_zero_launch_seats_and_unknown_initial_read_are_distinct(rows, state, expected):
    result = hero.launch_facts(dict(rows=rows, state=state, jobs=0 if rows == [] else None, read_ts=700),
        None, dict(state='unavailable', read_ts=None), dict(state='ok', read_ts=810, payload=dict(count=8)))
    assert result['percent'] == expected and result['total_seats'] == 8
    assert result['state'] == state


def test_duplicate_launch_rows_count_seats_once_for_percentage(launch_snapshot):
    launch_snapshot['rows'].append(dict(token_id=7))
    result = hero.launch_facts(launch_snapshot, None, dict(state='unavailable', read_ts=None),
        dict(state='ok', read_ts=810, payload=dict(count=8)))
    assert result['seats'] == 4 and result['percent'] == 50


def test_workers_runtime_counts_seats_once_per_family_and_lexical_ties(snapshot):
    slot = snapshot['sources']['workers']['payload']
    slot.update(count=5, workers=[dict(token_id=7, runtimes=['codex', 'claude', 'codex']),
        dict(token_id=7, runtimes=['codex']), dict(token_id=527, runtimes=['codex']),
        dict(token_id=90, runtimes=['claude']), dict(token_id=80, runtimes=['other'])])
    result = hero.project(**snapshot)['workers']
    assert result == dict(state='ok', read_ts=980, live=3, working=2, capacity=9,
        runtime='claude', runtime_percent=50, runtime_count=2, runtime_total=4, runtime_known=4)
    slot['workers'].reverse()
    assert hero.project(**snapshot)['workers'] == result
    slot['workers'][-1]['runtimes'] = ['codex']
    result = hero.project(**snapshot)['workers']
    assert result['runtime'] == 'codex' and result['runtime_percent'] == 50
    assert result['runtime_count'] == 2 and result['runtime_total'] == 4


@pytest.mark.parametrize('missing', [None, [], [''], ['   '], ['\t\n'], ['codex', ''], ['claude', ' ']])
def test_missing_runtime_metadata_hides_leader_and_keeps_seat_coverage(snapshot, missing):
    slot = snapshot['sources']['workers']['payload']
    slot['workers'][0]['runtimes'] = missing  # same seat's second worker reports codex
    result = hero.project(**snapshot)['workers']
    assert result == dict(state='ok', read_ts=980, live=3, working=2, capacity=9,
        runtime=None, runtime_percent=None, runtime_count=None, runtime_total=2, runtime_known=1)
    assert hero.project(**snapshot)['top']['state'] == 'ok'


@pytest.mark.parametrize('kind', ['count', 'malformed'])
def test_incomplete_roster_keeps_observed_runtime_coverage_without_claiming_total(snapshot, kind):
    slot = snapshot['sources']['workers']['payload']
    if kind == 'count':
        slot['count'] = 4
    else:
        slot['malformed_tokens'] = [7]
    result = hero.project(**snapshot)['workers']
    assert result['runtime'] is result['runtime_percent'] is result['runtime_count'] is result['runtime_total'] is None
    assert result['runtime_known'] == (2 if kind == 'count' else 1)
    assert result['live'] == 3


def test_stale_complete_workers_preserve_runtime_leader_and_source_clock(snapshot):
    snapshot['sources']['workers']['state'] = 'stale'
    result = hero.project(**snapshot)['workers']
    assert result['runtime'] == 'claude' and result['runtime_percent'] == 100
    assert result['state'] == 'stale' and result['read_ts'] == 980
