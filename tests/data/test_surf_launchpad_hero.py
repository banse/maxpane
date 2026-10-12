"""LAUNCHPAD cards preserve getter facts, observed history and bounded USD volume."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_launchpad_hero as hero
from maxpane_dashboard.data.surf_models import SURF_LAUNCHPAD_HERO_FIELDS, SURF_LAUNCHPAD_HERO_STATES


@pytest.fixture
def snapshot():
    return dict(now=18020, sources={
        'launchpad': dict(state='ok', read_ts=18005),
        'market': dict(state='ok', read_ts=18015),
    }, launchpad=dict(volume_2h=dict(state='ok', points_wei=[i * 10**18 for i in range(8)],
        read_ts=18010, head_ts=18000, until=18000, known=25, total=25)), data=dict(
        launchpad_coin_count=25, launchpad_launch_count=25, launchpad_new_24h=2,
        launchpad_swap_count=800, launchpad_trader_count=60, launchpad_creator_count=12,
        launchpad_creator_eth_owed=.002, burn_accrued=250, burn_staged=120,
        burn_bridgeable=119, burn_ready=True, launchpad_burned_total=15000,
        eth_usd=2000, pool4_total_burned=99999, burned_total=77777,
        launchpad_coins=[dict(imd_burned=1)], burn_min_bridge=999999,
    ))


def test_literal_contract_existing_units_volume_sum_and_source_clocks(snapshot):
    before = deepcopy(snapshot)
    result = hero.project(**snapshot)
    metadata = dict(state='ok', read_ts=18005)
    expected = dict(
        coins=dict(metadata, count=25, new_24h=2, swept=25),
        flow=dict(metadata, swaps=800, traders=60, creators=12),
        volume=dict(metadata, usd=56000, points=[i * 2000 for i in range(8)], until=18000,
                    known=25, total=25, quote=2000, quote_read_ts=18015, volume_read_ts=18010),
        fees=dict(metadata, eth=.002),
        queue=dict(metadata, accrued=250, staged=120, sendable=119, ready=True),
        burned=dict(metadata, imd=15000),
    )
    assert result == expected
    assert tuple(result) == tuple(SURF_LAUNCHPAD_HERO_FIELDS)
    for section, fields in SURF_LAUNCHPAD_HERO_FIELDS.items():
        assert tuple(result[section]) == tuple(expected[section]) == fields
        assert result[section]['state'] in SURF_LAUNCHPAD_HERO_STATES
    assert snapshot == before


def test_cold_unknown_and_complete_quiet_zero_are_distinct(snapshot):
    result = hero.project(data={}, launchpad={}, sources={}, now=18020)
    assert all(card['state'] == 'unavailable' for card in result.values())
    assert all(value is None for card in result.values() for key, value in card.items() if key != 'state')
    for key in ('launchpad_coin_count', 'launchpad_launch_count', 'launchpad_new_24h',
                'launchpad_swap_count', 'launchpad_trader_count', 'launchpad_creator_count',
                'launchpad_creator_eth_owed', 'burn_accrued', 'burn_staged',
                'burn_bridgeable', 'launchpad_burned_total'):
        snapshot['data'][key] = 0
    snapshot['data']['burn_ready'] = False
    snapshot['launchpad']['volume_2h'].update(points_wei=[0] * 8, known=0, total=0)
    result = hero.project(**snapshot)
    assert all(card['state'] == 'ok' for card in result.values())
    assert result['volume']['usd'] == 0 and result['volume']['points'] == [0] * 8
    assert result['fees']['eth'] == result['burned']['imd'] == 0
    assert result['queue']['ready'] is False


@pytest.mark.parametrize('count,swept', [(25, 24), (24, 25), (None, 25), (25, None), (True, 25)])
def test_population_coverage_only_qualifies_event_history(snapshot, count, swept):
    snapshot['data'].update(launchpad_coin_count=count, launchpad_launch_count=swept)
    result = hero.project(**snapshot)
    assert all(result[name]['state'] == 'partial' for name in ('coins', 'flow', 'burned'))
    assert result['flow']['swaps'] == 800 and result['burned']['imd'] == 15000
    assert all(result[name]['state'] == 'ok' for name in ('fees', 'queue', 'volume'))


def test_incomplete_volume_keeps_coverage_without_partial_sum_or_chart(snapshot):
    snapshot['launchpad']['volume_2h'].update(state='partial', points_wei=None, known=24)
    result = hero.project(**snapshot)
    assert result['volume']['state'] == 'partial'
    assert result['volume']['usd'] is result['volume']['points'] is None
    assert (result['volume']['known'], result['volume']['total']) == (24, 25)
    assert result['volume']['until'] == 18000 and result['volume']['volume_read_ts'] == 18010
    assert result['coins']['state'] == result['fees']['state'] == 'ok'


@pytest.mark.parametrize('state,stamp', [('unavailable', None), ('stale', 18015), ('ok', 17900)])
def test_market_outage_or_old_quote_cannot_mint_usd_or_degrade_getters(snapshot, state, stamp):
    snapshot['sources']['market'] = dict(state=state, read_ts=stamp)
    result = hero.project(**snapshot)
    assert result['volume']['state'] == 'unavailable'
    assert result['volume']['usd'] is result['volume']['points'] is None
    assert result['volume']['until'] == 18000 and result['volume']['volume_read_ts'] == 18010
    assert all(result[name]['state'] == 'ok' for name in ('coins', 'flow', 'fees', 'queue', 'burned'))


def test_stale_launchpad_retains_values_and_stale_takes_precedence_over_coverage(snapshot):
    snapshot['sources']['launchpad']['state'] = 'stale'
    snapshot['data']['launchpad_launch_count'] = 24
    result = hero.project(**snapshot)
    assert all(card['state'] == 'stale' for card in result.values())
    assert result['volume']['usd'] == 56000 and result['volume']['read_ts'] == 18005
    assert result['burned']['imd'] == 15000


def test_volume_keeps_its_own_old_clock_and_window_after_slot_refresh(snapshot):
    snapshot['now'] = 18901
    snapshot['sources']['launchpad']['read_ts'] = 18900
    snapshot['sources']['market']['read_ts'] = 18900
    result = hero.project(**snapshot)
    assert result['volume']['state'] == 'stale'
    assert result['volume']['usd'] == 56000
    assert result['volume']['read_ts'] == result['volume']['volume_read_ts'] == 18010
    assert result['volume']['until'] == 18000 and result['fees']['state'] == 'ok'


def test_captured_sources_override_later_global_failure_and_keep_oldest_quote_clock(snapshot):
    snapshot['data']['degraded'] = ['pad']
    snapshot['sources']['market']['read_ts'] = 17950
    volume = hero.project(**snapshot)['volume']
    assert volume['state'] == 'ok' and volume['usd'] == 56000
    assert volume['read_ts'] == volume['quote_read_ts'] == 17950


@pytest.mark.parametrize('quote', [None, 0, True, float('nan'), float('inf'), pytest.param(10**1000, id='overflow')])
def test_invalid_quote_never_converts_volume(snapshot, quote):
    snapshot['data']['eth_usd'] = quote
    volume = hero.project(**snapshot)['volume']
    assert volume['state'] == 'unavailable' and volume['usd'] is volume['points'] is volume['quote'] is None
    assert volume['known'] == volume['total'] == 25


def test_nonfinite_coverage_never_certifies_a_volume_snapshot(snapshot):
    snapshot['launchpad']['volume_2h'].update(known=10**1000, total=10**1000)
    volume = hero.project(**snapshot)['volume']
    assert volume['state'] == 'unavailable' and volume['known'] is volume['total'] is None
    assert volume['usd'] is volume['points'] is None


@pytest.mark.parametrize('bad', [None, True, -1, '1', float('nan'), float('inf'), pytest.param(10**1000, id='overflow')])
def test_invalid_numbers_leave_only_valid_neighbors(snapshot, bad):
    snapshot['data'].update(launchpad_swap_count=bad, launchpad_creator_eth_owed=bad,
                            burn_staged=bad, launchpad_burned_total=bad)
    result = hero.project(**snapshot)
    assert result['flow'] == dict(state='partial', read_ts=18005, swaps=None, traders=60, creators=12)
    assert result['fees'] == dict(state='unavailable', read_ts=18005, eth=None)
    assert result['queue'] == dict(state='partial', read_ts=18005, accrued=250, staged=None, sendable=119, ready=True)
    assert result['burned'] == dict(state='unavailable', read_ts=18005, imd=None)


@pytest.mark.parametrize('ready', [None, 0, 1, 'yes', [], False, True])
def test_readiness_is_strict_tristate_never_reinferred_from_amounts(snapshot, ready):
    snapshot['data']['burn_ready'] = ready
    queue = hero.project(**snapshot)['queue']
    assert queue['ready'] is (ready if type(ready) is bool else None)
    assert queue['state'] == ('ok' if type(ready) is bool else 'partial')
    assert queue['sendable'] == 119


@pytest.mark.parametrize('stamp', [None, 0, -1, True, float('nan'), float('inf'), 18021])
def test_invalid_launchpad_clock_invalidates_cached_volume_and_getters(snapshot, stamp):
    snapshot['sources']['launchpad']['read_ts'] = stamp
    result = hero.project(**snapshot)
    assert all(card['state'] == 'unavailable' for card in result.values())
    assert result['volume']['usd'] is result['volume']['points'] is None
    assert result['fees']['eth'] is result['queue']['ready'] is None


@pytest.mark.parametrize('changes', [dict(known=True), dict(total=-1), dict(read_ts=18021),
    dict(points_wei=[0] * 7), dict(points_wei=[-1] * 8), dict(points_wei=[True] * 8)])
def test_invalid_volume_snapshot_has_no_total_or_chart(snapshot, changes):
    snapshot['launchpad']['volume_2h'].update(changes)
    result = hero.project(**snapshot)['volume']
    assert result['state'] == 'unavailable' and result['usd'] is result['points'] is None


def test_sum_overflow_does_not_publish_infinite_usd(snapshot):
    snapshot['data']['eth_usd'] = 1e308
    snapshot['launchpad']['volume_2h']['points_wei'] = [10**18] * 8
    volume = hero.project(**snapshot)['volume']
    assert volume['usd'] is None and volume['state'] != 'ok'
