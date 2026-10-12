"""Protocol cards retain the existing producer's units, route and observation."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_protocol_hero as hero
from maxpane_dashboard.data.surf_models import (
    POOL4_COUNTER_STATES, SURF_PROTOCOL_HERO_FIELDS, SURF_PROTOCOL_HERO_STATES,
)


@pytest.fixture
def snapshot():
    return dict(now=1000, sources={
        'pool4': dict(state='ok', read_ts=900),
        'market': dict(state='stale', read_ts=700),
        'stakers': dict(state='unavailable', read_ts=None),
    }, data=dict(
        pool4_total_burned=33000, pool4_total_rewarded=5800, pool4_total_fee_token=3700,
        pool4_inventory_cap=120, pool4_tokens_in_pool=123, pool4_cap_headroom=-3,
        pool4_reward_path='via-distributor', pool4_bps_denominator=10000,
        pool4_distributor_staking_bps=3000, pool4_distributor_nodes_bps=2000,
        pool4_distributor_bonding_bps=5000,
        pool4_unsettled_burn=11, pool4_unsettled_stakers=19,
        pool4_backlog_imd=21, pool4_drippable=7, pool4_drip_per_day=12,
        pool4_counter_state='reconciled', pool4_split_drift_bps=-0.25,
    ))


def test_contract_mapping_preserves_whole_reward_leg_signed_values_and_clock(snapshot):
    before = deepcopy(snapshot)
    result = hero.project(**snapshot)
    assert tuple(result) == tuple(SURF_PROTOCOL_HERO_FIELDS)
    for section, fields in SURF_PROTOCOL_HERO_FIELDS.items():
        assert tuple(result[section]) == fields
        assert result[section]['state'] in SURF_PROTOCOL_HERO_STATES
    metadata = dict(state='ok', read_ts=900)
    assert result == dict(
        totals=dict(metadata, burned=33000, rewarded=5800, fees=3700),
        inventory=dict(metadata, cap=120, reserve=123, headroom=-3),
        split=dict(metadata, path='via-distributor', staking_pct=30, nodes_pct=20, bonding_pct=50),
        unsettled=dict(metadata, burn=11, rewards=19),
        delivery=dict(metadata, queued=21, ready=7, per_day=12),
        checks=dict(metadata, counters='reconciled', drift_bps=-0.25, path='via-distributor'),
    )
    assert snapshot == before


def test_cold_contract_is_all_unknown():
    result = hero.project(data={}, sources={}, now=1000)
    for section, fields in SURF_PROTOCOL_HERO_FIELDS.items():
        assert tuple(result[section]) == fields
        assert result[section]['state'] == 'unavailable'
        assert all(value is None for key, value in result[section].items() if key != 'state')


def test_zero_is_known_and_does_not_need_other_sources(snapshot):
    snapshot['sources'].pop('market')
    snapshot['sources'].pop('stakers')
    for key, value in snapshot['data'].items():
        if type(value) in (int, float) and key != 'pool4_bps_denominator':
            snapshot['data'][key] = 0
    result = hero.project(**snapshot)
    assert all(card['state'] == 'ok' for card in result.values())
    assert result['totals']['burned'] == result['inventory']['headroom'] == 0
    assert result['split']['staking_pct'] == result['delivery']['ready'] == 0
    assert result['checks']['drift_bps'] == 0


@pytest.mark.parametrize('state', ['partial', 'stale', 'unavailable'])
def test_source_state_and_old_clock_survive_partial_facts(snapshot, state):
    snapshot['sources']['pool4'] = dict(state=state, read_ts=700)
    snapshot['data']['pool4_total_fee_token'] = None
    result = hero.project(**snapshot)
    assert all(card['state'] == state and card['read_ts'] == 700 for card in result.values())
    assert result['totals']['burned'] == (None if state == 'unavailable' else 33000)
    if state == 'unavailable':
        assert all(value is None for card in result.values() for key, value in card.items()
                   if key not in ('state', 'read_ts'))


@pytest.mark.parametrize('stamp', [None, 0, -1, True, float('inf'), float('nan'), 1001])
def test_missing_invalid_or_future_source_clock_invalidates_values(snapshot, stamp):
    snapshot['sources']['pool4']['read_ts'] = stamp
    for card in hero.project(**snapshot).values():
        assert card['state'] == 'unavailable' and card['read_ts'] is None
        assert all(value is None for key, value in card.items() if key != 'state')


@pytest.mark.parametrize('bad', [None, True, '12', float('nan'), float('inf'), -1])
def test_invalid_amount_preserves_valid_neighbors(snapshot, bad):
    snapshot['data']['pool4_total_rewarded'] = bad
    snapshot['data']['pool4_unsettled_burn'] = bad
    snapshot['data']['pool4_drippable'] = bad
    result = hero.project(**snapshot)
    assert result['totals'] == dict(state='partial', read_ts=900, burned=33000, rewarded=None, fees=3700)
    assert result['unsettled'] == dict(state='partial', read_ts=900, burn=None, rewards=19)
    assert result['delivery'] == dict(state='partial', read_ts=900, queued=21, ready=None, per_day=12)


def test_missing_all_facts_is_unavailable_despite_fresh_read(snapshot):
    snapshot['data'] = {}
    assert all(card['state'] == 'unavailable' and card['read_ts'] == 900
               for card in hero.project(**snapshot).values())


@pytest.mark.parametrize('bad', [True, '0', float('nan'), float('inf'), 10**1000])
def test_signed_values_reject_invalid_numbers_without_recomputing(snapshot, bad):
    snapshot['data']['pool4_cap_headroom'] = bad
    snapshot['data']['pool4_split_drift_bps'] = bad
    result = hero.project(**snapshot)
    assert result['inventory'] == dict(state='partial', read_ts=900, cap=120, reserve=123, headroom=None)
    assert result['checks'] == dict(state='partial', read_ts=900,
                                    counters='reconciled', drift_bps=None, path='via-distributor')


def test_unknown_source_status_never_makes_known_facts_live(snapshot):
    snapshot['sources']['pool4']['state'] = 'healthy'
    for card in hero.project(**snapshot).values():
        assert card['state'] == 'unavailable' and card['read_ts'] == 900
        assert all(value is None for key, value in card.items() if key not in ('state', 'read_ts'))


@pytest.mark.parametrize('state', ['ok', 'partial', 'stale'])
def test_direct_route_is_complete_without_distributor_subdivision(snapshot, state):
    snapshot['sources']['pool4']['state'] = state
    snapshot['data']['pool4_reward_path'] = 'direct'
    assert hero.project(**snapshot)['split'] == dict(
        state=state, read_ts=900, path='direct', staking_pct=None, nodes_pct=None, bonding_pct=None)


@pytest.mark.parametrize('path', [None, 'other', True, {}, []])
def test_unknown_route_never_infers_distributor_from_address_or_percentages(snapshot, path):
    snapshot['data']['pool4_reward_path'] = path
    snapshot['data']['pool4_distributor_addr'] = '0x' + 'a' * 40
    result = hero.project(**snapshot)
    assert result['split'] == dict(state='unavailable', read_ts=900, path=None,
                                   staking_pct=None, nodes_pct=None, bonding_pct=None)
    assert result['checks']['path'] is None and result['checks']['state'] == 'partial'


@pytest.mark.parametrize('denominator', [None, 0, -1, True, 10000.0, float('inf'), 10**1000])
def test_bad_denominator_retains_route_but_suppresses_percentages(snapshot, denominator):
    snapshot['data']['pool4_bps_denominator'] = denominator
    assert hero.project(**snapshot)['split'] == dict(state='partial', read_ts=900,
        path='via-distributor', staking_pct=None, nodes_pct=None, bonding_pct=None)


@pytest.mark.parametrize('share', [None, -1, 10001, True, 30.0, float('nan')])
def test_bad_share_does_not_erase_valid_subdivisions(snapshot, share):
    snapshot['data']['pool4_distributor_nodes_bps'] = share
    assert hero.project(**snapshot)['split'] == dict(state='partial', read_ts=900,
        path='via-distributor', staking_pct=30, nodes_pct=None, bonding_pct=50)


@pytest.mark.parametrize('counter', [*POOL4_COUNTER_STATES, None, 'ok', True, {}])
def test_checks_only_publish_explicit_counter_vocabulary(snapshot, counter):
    snapshot['data']['pool4_counter_state'] = counter
    expected = counter if counter in POOL4_COUNTER_STATES else None
    result = hero.project(**snapshot)['checks']
    assert result['counters'] == expected and result['drift_bps'] == -0.25
    assert result['state'] == ('ok' if expected is not None else 'partial')
