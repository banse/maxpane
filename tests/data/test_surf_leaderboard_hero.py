"""LEADERBOARD card facts retain canonical records and independent source clocks."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_leaderboard_hero as hero
from maxpane_dashboard.data.surf_models import SURF_LEADERBOARD_HERO_FIELDS, SURF_LEADERBOARD_HERO_STATES


@pytest.fixture
def snapshot():
    return dict(now=1000, sources={
        'records': dict(state='ok', read_ts=900),
        'workers': dict(state='ok', read_ts=980),
        'contributors': dict(state='ok', read_ts=800),
    }, data=dict(swarm_board_rows=[
        dict(rank=2, token_id=7, accepted=10, attempts=20),
        dict(rank=1, token_id=527, accepted=40, attempts=60),
    ], swarm_board_summary=dict(seats=2, accepted=50, attempts=80,
        rejected=20, failed=5, pending=5, live=3, working=2, capacity=9,
        receipts=96, turns=120, wall_clock_ms=9_000_000,
        receipt_seats=999, receipt_accepted=888, receipt_attempts=777)))


def test_literal_contract_canonical_rank_counts_hours_and_independent_clocks(snapshot):
    before = deepcopy(snapshot)
    result = hero.project(**snapshot)
    expected = dict(
        top=dict(state='ok', read_ts=900, token_id=527, accepted=40, rank=1, empty=False),
        recorded=dict(state='ok', read_ts=900, seats=2, attempts=80),
        rate=dict(state='ok', read_ts=900, accepted=50, attempts=80, percent=62.5),
        outcomes=dict(state='ok', read_ts=900, rejected=20, failed=5, pending=5),
        workers=dict(state='ok', read_ts=980, live=3, working=2, capacity=9),
        effort=dict(state='ok', read_ts=800, receipts=96, turns=120, hours=2.5),
    )
    assert result == expected
    assert tuple(result) == tuple(SURF_LEADERBOARD_HERO_FIELDS)
    for section, fields in SURF_LEADERBOARD_HERO_FIELDS.items():
        assert tuple(result[section]) == tuple(expected[section]) == fields
        assert result[section]['state'] in SURF_LEADERBOARD_HERO_STATES
    assert snapshot == before
    snapshot['data']['swarm_board_rows'].reverse()
    assert hero.project(**snapshot) == expected


def test_cold_unknown_and_proven_empty_are_distinct(snapshot):
    cold = hero.project(data={}, sources={}, now=1000)
    assert all(card['state'] == 'unavailable' for card in cold.values())
    assert all(value is None for card in cold.values() for key, value in card.items() if key != 'state')
    snapshot['data']['swarm_board_rows'] = []
    snapshot['data']['swarm_board_summary'] = dict.fromkeys(snapshot['data']['swarm_board_summary'], 0)
    empty = hero.project(**snapshot)
    assert empty['top'] == dict(state='ok', read_ts=900, token_id=None, accepted=None, rank=None, empty=True)
    assert empty['recorded'] == dict(state='ok', read_ts=900, seats=0, attempts=0)
    assert empty['rate'] == dict(state='ok', read_ts=900, accepted=0, attempts=0, percent=None)
    assert empty['workers'] == dict(state='ok', read_ts=980, live=0, working=0, capacity=0)
    assert empty['effort'] == dict(state='ok', read_ts=800, receipts=0, turns=0, hours=0)
    snapshot['sources']['records']['state'] = 'stale'
    dated = hero.project(**snapshot)
    assert dated['top'] == dict(empty['top'], state='stale')
    assert dated['rate'] == dict(empty['rate'], state='stale')
    snapshot['data']['swarm_board_rows'] = None
    assert hero.project(**snapshot)['top']['empty'] is None


def test_zero_acceptance_with_real_attempts_is_zero_percent(snapshot):
    snapshot['data']['swarm_board_summary'].update(accepted=0, attempts=80)
    assert hero.project(**snapshot)['rate'] == dict(state='ok', read_ts=900, accepted=0, attempts=80, percent=0)


@pytest.mark.parametrize('name,sections', [
    ('records', ('top', 'recorded', 'rate', 'outcomes')),
    ('workers', ('workers',)), ('contributors', ('effort',)),
])
def test_source_outages_leave_other_families_untouched(snapshot, name, sections):
    before = hero.project(**snapshot)
    snapshot['sources'][name]['state'] = 'unavailable'
    result = hero.project(**snapshot)
    for section, card in result.items():
        if section in sections:
            assert card['state'] == 'unavailable'
            assert all(value is None for key, value in card.items() if key not in ('state', 'read_ts'))
        else:
            assert card == before[section]


def test_stale_values_keep_their_actual_source_clock(snapshot):
    for source in snapshot['sources'].values():
        source['state'] = 'stale'
    result = hero.project(**snapshot)
    assert all(card['state'] == 'stale' for card in result.values())
    assert result['top']['accepted'] == 40 and result['top']['read_ts'] == 900
    assert result['workers']['live'] == 3 and result['workers']['read_ts'] == 980
    assert result['effort']['hours'] == 2.5 and result['effort']['read_ts'] == 800


@pytest.mark.parametrize('bad', [None, True, -1, '8', float('nan'), float('inf')])
def test_invalid_fields_preserve_only_valid_neighbors(snapshot, bad):
    summary = snapshot['data']['swarm_board_summary']
    summary.update(accepted=bad, failed=bad, capacity=bad, wall_clock_ms=bad)
    result = hero.project(**snapshot)
    assert result['rate'] == dict(state='partial', read_ts=900, accepted=None, attempts=80, percent=None)
    assert result['outcomes'] == dict(state='partial', read_ts=900, rejected=20, failed=None, pending=5)
    assert result['workers'] == dict(state='partial', read_ts=980, live=3, working=2, capacity=None)
    assert result['effort'] == dict(state='partial', read_ts=800, receipts=96, turns=120, hours=None)
    assert result['top']['state'] == result['recorded']['state'] == 'ok'


def test_impossible_acceptance_counts_never_publish_a_percentage(snapshot):
    snapshot['data']['swarm_board_summary'].update(accepted=81, attempts=80)
    snapshot['data']['swarm_board_rows'][1].update(accepted=61, attempts=60)
    result = hero.project(**snapshot)
    assert result['rate'] == dict(state='partial', read_ts=900, accepted=None, attempts=80, percent=None)
    assert result['top'] == dict(state='partial', read_ts=900, token_id=527, accepted=None, rank=1, empty=False)


@pytest.mark.parametrize('rows', [[], None, [{}], [True],
    [dict(rank=True, token_id=527, accepted=40)],
    [dict(rank=1, token_id=True, accepted=40)],
    [dict(rank=1, token_id=527, accepted=40), dict(rank=1, token_id=7, accepted=10)]])
def test_partial_or_malformed_records_never_invent_top_or_prove_empty(snapshot, rows):
    snapshot['sources']['records']['state'] = 'partial'
    snapshot['data']['swarm_board_rows'] = rows
    assert hero.project(**snapshot)['top'] == dict(
        state='unavailable', read_ts=900, token_id=None, accepted=None, rank=None, empty=None)


@pytest.mark.parametrize('state', ['partial', 'stale'])
def test_incomplete_roster_keeps_served_live_but_hides_partial_slot_sums(snapshot, state):
    snapshot['sources']['workers'].update(state=state, partial=True)
    assert hero.project(**snapshot)['workers'] == dict(
        state=state, read_ts=980, live=3, working=None, capacity=None)
    snapshot['data']['swarm_board_summary'].update(turns=None, wall_clock_ms=None)
    assert hero.project(**snapshot)['effort'] == dict(
        state='partial', read_ts=800, receipts=96, turns=None, hours=None)


@pytest.mark.parametrize('stamp', [None, 0, -1, True, float('nan'), float('inf'), 1001])
def test_bad_source_clock_cannot_publish_values(snapshot, stamp):
    snapshot['sources']['records']['read_ts'] = stamp
    result = hero.project(**snapshot)
    for name in ('top', 'recorded', 'rate', 'outcomes'):
        assert result[name]['state'] == 'unavailable' and result[name]['read_ts'] is None
    assert result['workers']['state'] == result['effort']['state'] == 'ok'
