"""Selected hero facts retain their own observation clocks and coverage."""
from copy import deepcopy

import pytest

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot
from maxpane_dashboard.analytics.swarm_tokens_hero import project
from maxpane_dashboard.data.swarm_tokens_demo import demo_snapshot
from maxpane_dashboard.data.swarm_tokens_models import HERO_FIELDS, HERO_STATES, HERO_VOLUME_ROW_FIELDS

NOW = 2_000_000_000


def row(key='a', **changes):
    result = dict(demo_snapshot()['tokens'][0], id=key, symbol=key.upper(), chain='eth',
                launched_at=NOW-100, volume_24h=10, price_usd=1, change_24h=2,
                paired_amount=3, paired_symbol='IMD', lp_state='two-sided',
                market_state='ok', market_read_at=NOW-30,
                liquidity_state='ok', liquidity_read_at=NOW-60)
    result.update(changes)
    return result


def snapshot(rows, state='ok', stamp=NOW-10):
    return dict(tokens=rows, activity=[], as_of=NOW, is_mock=False,
                sources={'catalogue': {'state': state, 'as_of': stamp},
                         'markets': {'state': 'ok', 'as_of': NOW-1, 'known': 999}})


def hero(rows, **kwargs):
    raw = snapshot(rows, **kwargs)
    return project(rows, catalogue=raw['sources']['catalogue'], now=NOW)


def test_contract_and_selected_cohort_use_independent_source_clocks():
    raw = snapshot([row('a'), row('b', chain='base', volume_24h=999),
                    row('c', market_read_at=NOW-120, liquidity_read_at=NOW-150)])
    original = deepcopy(raw)
    result = project_snapshot(raw, chain='eth')['tokens_hero']
    assert tuple(result) == tuple(HERO_FIELDS)
    for key, fields in HERO_FIELDS.items():
        assert tuple(result[key]) == fields
        assert result[key]['state'] in HERO_STATES
    assert result['tokens'] == dict(state='ok', read_ts=NOW-10, tracked=2, new_24h=2, chains=1)
    assert result['volume'] == dict(state='ok', read_ts=NOW-120, amount=20, known=2, total=2)
    assert result['liquidity'] == dict(state='ok', read_ts=NOW-150, imd=6, eth=0, known=2, total=2, partial=False)
    assert result['pools'] == dict(state='ok', read_ts=NOW-150, two_sided=2, one_sided=0, unknown=0, other=0)
    assert result['momentum'] == dict(state='ok', read_ts=NOW-120, rising=2, falling=0, flat=0, known=2, total=2)
    assert all(tuple(value) == HERO_VOLUME_ROW_FIELDS for value in result['top_volume']['rows'])
    assert raw == original


@pytest.mark.parametrize('filters,expected', [({'chain': 'base'}, ['B']),
    ({'query': 'B'}, ['B']), ({'lp_state': 'one-sided'}, ['B']),
    ({'sort': 'symbol'}, ['C', 'B', 'A'])])
def test_all_filters_and_sort_share_selected_denominators(filters, expected):
    raw = snapshot([row('a', name='alpha', volume_24h=10),
                    row('b', name='beta', chain='base', lp_state='one-token', volume_24h=20),
                    row('c', name='gamma', volume_24h=30)])
    result = project_snapshot(raw, **filters)['tokens_hero']
    assert [value['symbol'] for value in result['top_volume']['rows']] == expected
    assert result['tokens']['tracked'] == result['volume']['total'] == len(expected)


def test_stale_quotes_excluded_and_all_stale_keeps_actual_clock_without_zero():
    stale = row('old', volume_24h=10000, paired_amount=10000, market_state='stale',
                liquidity_state='stale', market_read_at=NOW-300, liquidity_read_at=NOW-600)
    result = hero([row('a', volume_24h=0, change_24h=0, paired_amount=0), stale])
    assert result['volume'] == dict(state='partial', read_ts=NOW-30, amount=0, known=1, total=2)
    assert result['momentum']['flat'] == 1 and result['momentum']['rising'] == 0
    assert result['liquidity']['imd'] == 0 and result['liquidity']['eth'] is None
    assert result['liquidity']['partial'] is True
    assert result['top_volume']['rows'] == [dict(symbol='A', volume_usd=0)]
    result = hero([stale])
    assert result['volume'] == dict(state='stale', read_ts=NOW-300, amount=None, known=0, total=1)
    assert result['momentum']['rising'] is None and result['top_volume']['rows'] is None
    assert result['liquidity']['read_ts'] == NOW-600 and result['liquidity']['imd'] is None
    assert result['pools'] == dict(state='stale', read_ts=NOW-600, two_sided=None, one_sided=None, unknown=1, other=None)


def test_empty_success_unknown_catalogue_and_mock_are_distinct():
    empty = hero([])
    assert empty['volume'] == dict(state='ok', read_ts=NOW-10, amount=0, known=0, total=0)
    assert empty['liquidity']['imd'] == empty['liquidity']['eth'] == 0
    assert empty['momentum']['flat'] == 0 and empty['top_volume']['rows'] == []
    for rows in (None, [], [row()]):
        cold = hero(rows, state='unavailable', stamp=None)
        assert all(value['state'] == 'unavailable' for value in cold.values())
        assert cold['tokens']['tracked'] is cold['volume']['total'] is cold['volume']['amount'] is None
    live = row()
    for key in ('market_state', 'market_read_at', 'liquidity_state', 'liquidity_read_at'):
        live.pop(key)
    result = hero([live])
    assert result['volume']['state'] == result['liquidity']['state'] == 'unavailable'
    mock = project_snapshot(dict(tokens=[live], activity=[], as_of=NOW, is_mock=True))['tokens_hero']
    assert mock['volume']['state'] == 'ok' and mock['volume']['read_ts'] == NOW


@pytest.mark.parametrize('state', ['partial', 'stale'])
def test_uncertain_catalogue_keeps_fresh_measurement_clocks_and_partial_state(state):
    result = hero([row()], state=state, stamp=NOW-1000)
    assert result['tokens']['state'] == state and result['tokens']['read_ts'] == NOW-1000
    assert all(result[key]['state'] == 'partial' for key in HERO_FIELDS if key != 'tokens')
    assert result['volume']['read_ts'] == NOW-30 and result['liquidity']['read_ts'] == NOW-60
    assert result['liquidity']['partial'] is True


@pytest.mark.parametrize('stamp', [None, 0, -1, NOW+1, float('nan'), float('inf'), True])
def test_invalid_observation_clock_never_counts_or_uses_snapshot_clock(stamp):
    result = hero([row(market_read_at=stamp, liquidity_read_at=stamp)])
    assert result['volume']['state'] == 'unavailable' and result['volume']['read_ts'] is None
    assert result['volume']['amount'] is None and result['volume']['known'] == 0
    assert result['liquidity']['imd'] is None and result['pools']['two_sided'] is None
    assert hero([row()], stamp=stamp)['tokens']['tracked'] is None


@pytest.mark.parametrize('invalid', [-1, float('nan'), float('inf'), True, '20'])
def test_invalid_measurement_values_do_not_contribute(invalid):
    result = hero([row(volume_24h=invalid, paired_amount=invalid, price_usd=invalid)])
    assert result['volume']['amount'] is None and result['volume']['known'] == 0
    assert result['liquidity']['imd'] is None and result['liquidity']['known'] == 0
    assert result['momentum']['known'] == 0 and result['momentum']['rising'] is None


def test_assets_pool_states_momentum_and_ranking_ties_remain_reconciled():
    rows = [row('c', volume_24h=20, change_24h=0, lp_state='withdrawn'),
            row('b', volume_24h=20, change_24h=-2, lp_state='one-quote', paired_symbol='ETH'),
            row('a', volume_24h=20, change_24h=2, lp_state='one-token'),
            row('d', volume_24h=1, change_24h=float('nan'), lp_state='unknown', paired_symbol='USDC')]
    result = hero(rows)
    assert result['liquidity'] == dict(state='partial', read_ts=NOW-60, imd=6, eth=3, known=3, total=4, partial=True)
    assert result['pools'] == dict(state='partial', read_ts=NOW-60, two_sided=0, one_sided=2, unknown=1, other=1)
    assert result['momentum'] == dict(state='partial', read_ts=NOW-30, rising=1, falling=1, flat=1, known=3, total=4)
    assert result['top_volume']['rows'] == [dict(symbol=key, volume_usd=20) for key in ('A', 'B', 'C')]
    result['top_volume']['rows'][0]['symbol'] = 'changed'
    assert rows[2]['symbol'] == 'A'


def test_launch_age_boundaries_and_unread_fields_are_not_known_zero():
    result = hero([row(str(index), launched_at=value) for index, value in enumerate(
        [NOW, NOW-86399, NOW-86400, NOW+1, None, float('nan')])])
    assert result['tokens']['new_24h'] == 2
    result = hero([row('a', market_state='unsupported', liquidity_state='unknown'),
                   row('b', market_state='unindexed', liquidity_state='pending')])
    assert result['volume']['known'] == 0 and result['volume']['amount'] is None
    assert result['pools'] == dict(state='unavailable', read_ts=None, two_sided=None,
                                    one_sided=None, unknown=2, other=None)
