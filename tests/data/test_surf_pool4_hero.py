"""POOL4 rack facts preserve native meanings and independent source clocks."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_pool4_hero as hero
from maxpane_dashboard.data.surf_models import SURF_POOL4_HERO_FIELDS, SURF_POOL4_HERO_STATES


@pytest.fixture
def snapshot():
    return dict(now=1000, sources={
        'pool4': dict(state='ok', read_ts=990),
        'market': dict(state='ok', read_ts=980),
        'stakers': dict(state='ok', read_ts=900),
    }, data=dict(
        pool4_network='MAINNET', pool4_stakers_network='MAINNET',
        pool4_price_usd=9.4, pool4_cheaper_venue='here', pool4_venue_gap_pct=-1.2,
        pool4_share_price=7.96, pool4_trailing_return_pct=13.4, pool4_implied_apr_pct=999,
        pool4_vault_assets=1200, pool4_vault_shares=200, pool4_staker_count=17,
        pool4_backstop_state='deployed', pool4_backstop_eth=2.5,
        pool4_current_tick=68181, pool4_backstop_lower_tick=68340,
        pool4_backlog_imd=30, pool4_drip_per_day=7, pool4_backlog_days=4.2,
        imd_price_usd=888,
    ))


@pytest.mark.parametrize('network', ['SEPOLIA', None, 'BASE'])
def test_vault_does_not_merge_holders_from_another_or_unknown_chain(snapshot, network):
    snapshot['data']['pool4_stakers_network'] = network
    vault = hero.project(**snapshot)['vault']
    assert vault['imd'] == 1200 and vault['simd'] == 200
    assert vault['holders'] is None


def test_contract_native_mappings_and_independent_source_clocks(snapshot):
    original = deepcopy(snapshot)
    result = hero.project(**snapshot)
    assert tuple(result) == tuple(SURF_POOL4_HERO_FIELDS)
    for section, fields in SURF_POOL4_HERO_FIELDS.items():
        assert tuple(result[section]) == fields
        assert result[section]['state'] in SURF_POOL4_HERO_STATES
    assert result['price'] == dict(state='ok', read_ts=980, usd=9.4, venue='here', gap_pct=-1.2)
    assert result['rate'] == dict(state='ok', read_ts=990, imd=7.96)
    assert result['staking'] == dict(state='ok', read_ts=990, apr=13.4)
    assert result['vault'] == dict(state='ok', read_ts=900, imd=1200, simd=200,
                                   holders=17, holders_state='ok', holders_read_ts=900, holders_partial=False)
    assert result['bid']['state'] == 'ok' and result['bid']['read_ts'] == 990
    assert result['bid']['eth'] == 2.5 and result['bid']['status'] == 'deployed'
    assert result['bid']['distance_pct'] == pytest.approx(1.58, abs=.01)
    assert result['queue'] == dict(state='ok', read_ts=990, imd=30, per_day=7, days=4.2)
    assert snapshot == original


def test_cold_result_contains_all_unknown_facts():
    result = hero.project(data={}, sources={}, now=1000)
    for section, fields in SURF_POOL4_HERO_FIELDS.items():
        assert tuple(result[section]) == fields
        assert result[section]['state'] == 'unavailable'
        assert result[section]['read_ts'] is None
    assert result['price']['usd'] is result['bid']['status'] is result['vault']['holders'] is None
    assert result['vault']['holders_state'] == 'unavailable'


def test_price_needs_both_reads_never_falls_back_to_unrelated_dex(snapshot):
    snapshot['sources']['market'] = dict(state='unavailable', read_ts=800)
    result = hero.project(**snapshot)
    assert result['price']['state'] == 'unavailable'
    assert result['price']['usd'] is result['price']['gap_pct'] is result['price']['venue'] is None
    assert result['rate']['imd'] == 7.96 and result['rate']['state'] == 'ok'
    snapshot['sources']['market'] = dict(state='stale', read_ts=800)
    price = hero.project(**snapshot)['price']
    assert price == dict(state='stale', read_ts=800, usd=9.4, venue='here', gap_pct=-1.2)
    snapshot['data']['pool4_price_usd'] = None
    assert hero.project(**snapshot)['price']['usd'] is None
    assert hero.project(**snapshot)['price']['state'] == 'unavailable'


def test_stale_pool_read_retains_numbers_and_does_not_stale_fresh_holders(snapshot):
    snapshot['sources']['pool4'] = dict(state='stale', read_ts=700)
    result = hero.project(**snapshot)
    assert all(result[key]['state'] == 'stale' for key in result)
    assert all(result[key]['read_ts'] == 700 for key in result)
    assert result['vault']['holders_state'] == 'ok' and result['vault']['holders_read_ts'] == 900
    assert result['staking']['apr'] == 13.4


def test_vault_combines_only_contributing_sources_and_preserves_partial_values(snapshot):
    snapshot['sources']['stakers'] = dict(state='unavailable', read_ts=600)
    result = hero.project(**snapshot)['vault']
    assert result == dict(state='partial', read_ts=990, imd=1200, simd=200,
                          holders=None, holders_state='unavailable', holders_read_ts=600, holders_partial=False)
    snapshot['sources']['stakers'] = dict(state='stale', read_ts=650)
    result = hero.project(**snapshot)['vault']
    assert result['state'] == 'stale' and result['read_ts'] == 650 and result['holders'] == 17
    snapshot['data']['pool4_staker_count'] = None
    result = hero.project(**snapshot)['vault']
    assert result['state'] == 'partial' and result['read_ts'] == 990
    snapshot['sources']['pool4'] = dict(state='unavailable', read_ts=500)
    snapshot['sources']['stakers'] = dict(state='ok', read_ts=900)
    snapshot['data']['pool4_staker_count'] = 17
    result = hero.project(**snapshot)['vault']
    assert result['state'] == 'partial' and result['read_ts'] == 900
    assert result['imd'] is result['simd'] is None and result['holders'] == 17
    snapshot['data']['pool4_staker_count'] = None
    assert hero.project(**snapshot)['vault']['state'] == 'unavailable'


def test_known_zero_and_absent_band_remain_distinct_from_unread(snapshot):
    snapshot['data'].update(pool4_price_usd=0, pool4_share_price=0, pool4_trailing_return_pct=0,
        pool4_vault_assets=0, pool4_vault_shares=0, pool4_staker_count=0,
        pool4_backstop_state='none', pool4_backstop_eth=0, pool4_backlog_imd=0,
        pool4_drip_per_day=0, pool4_backlog_days=0, pool4_cheaper_venue=None)
    result = hero.project(**snapshot)
    assert result['bid'] == dict(state='ok', read_ts=990, status='none', eth=None, distance_pct=None)
    assert all(result[key]['state'] == 'ok' for key in result)
    assert result['price']['usd'] == result['rate']['imd'] == result['staking']['apr'] == 0
    assert result['vault']['holders'] == result['queue']['imd'] == 0
    snapshot['data']['pool4_backstop_state'] = None
    assert hero.project(**snapshot)['bid']['state'] == 'unavailable'


def test_deployed_bid_and_queue_missing_facts_are_partial_without_rederiving(snapshot):
    snapshot['data'].update(pool4_backstop_eth=None, pool4_backlog_days=None)
    result = hero.project(**snapshot)
    assert result['bid']['state'] == 'partial' and result['bid']['eth'] is None
    assert result['bid']['distance_pct'] == pytest.approx(1.58, abs=.01)
    assert result['queue'] == dict(state='partial', read_ts=990, imd=30, per_day=7, days=None)
    snapshot['data'].update(pool4_current_tick=None, pool4_backstop_lower_tick=None)
    assert hero.project(**snapshot)['bid']['state'] == 'partial'  # deployment itself was read
    snapshot['data'].update(pool4_backlog_imd=None, pool4_drip_per_day=None)
    assert hero.project(**snapshot)['queue']['state'] == 'unavailable'


@pytest.mark.parametrize('invalid', [True, '10', -1, float('nan'), float('inf'), 10**400])
def test_malformed_numbers_do_not_become_metrics(snapshot, invalid):
    for key in ('pool4_price_usd', 'pool4_share_price', 'pool4_trailing_return_pct',
                'pool4_vault_assets', 'pool4_vault_shares', 'pool4_backstop_eth',
                'pool4_backlog_imd', 'pool4_drip_per_day', 'pool4_backlog_days'):
        snapshot['data'][key] = invalid
    result = hero.project(**snapshot)
    assert result['price']['usd'] is result['rate']['imd'] is result['staking']['apr'] is None
    assert result['vault']['imd'] is result['vault']['simd'] is result['bid']['eth'] is None
    assert result['queue']['state'] == 'unavailable'


@pytest.mark.parametrize('stamp', [None, True, 0, -1, 1001, float('nan'), float('inf')])
def test_invalid_source_clock_never_borrows_evaluation_time(snapshot, stamp):
    snapshot['sources']['pool4']['read_ts'] = stamp
    result = hero.project(**snapshot)
    assert result['rate']['state'] == 'unavailable' and result['rate']['read_ts'] is None
    assert result['rate']['imd'] is result['price']['usd'] is None
    assert result['vault']['holders'] == 17 and result['vault']['read_ts'] == 900


@pytest.mark.parametrize('invalid', [True, 1.5, -1, '17'])
def test_holder_count_is_integer_not_coerced(snapshot, invalid):
    snapshot['data']['pool4_staker_count'] = invalid
    vault = hero.project(**snapshot)['vault']
    assert vault['holders'] is None and vault['holders_state'] == 'unavailable'
    assert vault['state'] == 'partial'


def test_signed_gap_valid_venue_allowlist_and_tick_validation(snapshot):
    snapshot['data'].update(pool4_cheaper_venue='untrusted', pool4_venue_gap_pct=-.25,
                            pool4_current_tick=float('inf'))
    result = hero.project(**snapshot)
    assert result['price']['venue'] is None and result['price']['gap_pct'] == -.25
    assert result['bid']['distance_pct'] is None and result['bid']['state'] == 'partial'
    snapshot['data'].update(pool4_venue_gap_pct=True, pool4_current_tick=True)
    result = hero.project(**snapshot)
    assert result['price']['gap_pct'] is None and result['bid']['distance_pct'] is None
    snapshot['data'].update(pool4_backstop_state='untrusted')
    assert hero.project(**snapshot)['bid']['status'] is None


def test_partial_source_provenance_remains_visible_and_in_money_band_is_zero(snapshot):
    snapshot['sources']['pool4']['state'] = 'partial'
    snapshot['data'].update(pool4_current_tick=-10, pool4_backstop_lower_tick=-20)
    result = hero.project(**snapshot)
    assert all(result[key]['state'] == 'partial' for key in result)
    assert result['bid']['distance_pct'] == 0
    assert result['vault']['holders_state'] == 'ok'
