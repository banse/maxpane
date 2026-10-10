"""Wallet balances and ready claims have separate, honest valuations."""

from copy import deepcopy

import pytest

from maxpane_dashboard.analytics.portfolio import project_snapshot
from maxpane_dashboard.data import portfolio_models as models
from maxpane_dashboard.data.portfolio_demo import SAMPLE_WALLET, demo_snapshot


def _snapshot(*rows):
    snapshot = demo_snapshot(SAMPLE_WALLET)
    if rows:
        base = snapshot['tokens'][0]
        snapshot['tokens'] = [dict(base, id=f'eth:{index}', **row)
                              for index, row in enumerate(rows)]
    return snapshot


def test_sample_totals_reconcile_without_turning_claims_into_holdings():
    result = project_snapshot(_snapshot())
    metrics = result['metrics']
    assert tuple(result) == models.PROJECTION_KEYS
    assert tuple(metrics) == models.METRIC_KEYS
    assert metrics == dict(
        total=3, held_value=3500, held_known=3, held_total=3,
        claimable_value=400, claimable_known=2, claimable_total=2,
        agents_total=3, agents_online=2,
        liquidity_imd=120000, liquidity_eth=4.2, liquidity_partial=False,
        pnl_usd=200, pnl_percent=pytest.approx(200 / 3300 * 100),
    )
    assert [row['symbol'] for row in result['tokens']] == ['MESH', 'TIDE', 'KITE']
    assert {row['symbol'] for row in result['claimable']} == {'TIDE', 'FOAM'}
    assert [row['symbol'] for row in result['gainers']] == ['TIDE']
    assert [row['symbol'] for row in result['losers']] == ['MESH', 'KITE']
    assert result['wallet'] == SAMPLE_WALLET


def test_table_and_held_card_exclude_claim_only_and_unknown_balances():
    raw = _snapshot(
        {'held_quantity': 10, 'price_usd': 2, 'claimable_quantity': 3},
        {'held_quantity': 0, 'price_usd': 100, 'claimable_quantity': 20},
        {'held_quantity': None, 'balance_state': 'unavailable',
         'price_usd': 100, 'claimable_quantity': 30},
        {'held_quantity': 0, 'balance_state': 'stale',
         'price_usd': 100, 'claimable_quantity': 2},
    )
    result = project_snapshot(raw)
    assert [row['id'] for row in result['tokens']] == ['eth:0']
    assert result['metrics']['total'] == result['metrics']['held_total'] == 1
    assert result['metrics']['held_known'] == 1
    assert result['metrics']['held_value'] == 20
    assert len(result['claimable']) == 4
    assert result['metrics']['claimable_value'] == 5206


@pytest.mark.parametrize('filters, symbols, held, claimable, imd, eth', [
    ({'chain': 'base'}, {'KITE'}, 800, 0, 0, 2.4),
    ({'query': 'foam'}, set(), 0, 200, 0, 0),
    ({'query': '401'}, {'TIDE'}, 1000, 200, 120000, 0),
    ({'assets': 'held'}, {'TIDE', 'KITE', 'MESH'}, 3500, 200, 120000, 4.2),
    ({'assets': 'claimable'}, {'TIDE'}, 1000, 400, 120000, 0),
    ({'lp_state': 'issues'}, set(), 0, 0, 0, 0),
])
def test_all_panels_share_filters_but_agent_counts_stay_wallet_scoped(
        filters, symbols, held, claimable, imd, eth):
    result = project_snapshot(_snapshot(), **filters)
    assert {row['symbol'] for row in result['tokens']} == symbols
    ids = {row['id'] for row in result['tokens']}
    for key in ('gainers', 'losers'):
        assert all(row['id'] in ids for row in result[key])
    assert all(row['token_id'] in ids for row in result['activity'])
    metrics = result['metrics']
    assert metrics['total'] == len(symbols)
    assert metrics['held_value'] == held and metrics['claimable_value'] == claimable
    assert metrics['liquidity_imd'] == imd and metrics['liquidity_eth'] == eth
    assert metrics['agents_total'] == 3 and metrics['agents_online'] == 2


def test_unpriced_stale_and_unknown_measurements_preserve_rows_and_coverage():
    raw = _snapshot(
        {'held_quantity': 10, 'price_usd': None, 'claimable_quantity': 0, 'claim_state': 'none'},
        {'held_quantity': 20, 'price_usd': 2, 'market_state': 'stale', 'claimable_quantity': 0},
        {'held_quantity': 30, 'price_usd': 2, 'balance_state': 'stale', 'claimable_quantity': 0},
        {'held_quantity': None, 'price_usd': 2, 'balance_state': 'unavailable',
         'claimable_quantity': 5},
        {'held_quantity': 0, 'price_usd': None, 'claimable_quantity': 10},
    )
    result = project_snapshot(raw)
    assert len(result['tokens']) == 3
    by_id = {row['id']: row for row in result['tokens']}
    assert all(by_id[f'eth:{i}']['held_usd'] is None for i in range(3))
    assert by_id['eth:0']['claimable_usd'] == 0
    assert result['metrics']['held_value'] is None
    assert result['metrics']['held_known'] == 0 and result['metrics']['held_total'] == 3
    assert result['metrics']['claimable_value'] == 10
    assert result['metrics']['claimable_known'] == 1 and result['metrics']['claimable_total'] == 2
    assert all(row['id'] != 'eth:1' for row in result['gainers'])


def test_ready_claims_do_not_include_locked_claimed_or_unavailable_allocations():
    raw = _snapshot(
        {'held_quantity': 0, 'claimable_quantity': 10, 'claim_state': 'locked'},
        {'held_quantity': 0, 'claimable_quantity': 10, 'claim_state': 'claimed'},
        {'held_quantity': 0, 'claimable_quantity': None, 'claim_state': 'unavailable',
         'claim_read_state': 'unavailable'},
        {'held_quantity': 0, 'claimable_quantity': 10, 'claim_state': 'ready'},
        {'held_quantity': 2, 'claimable_quantity': 10, 'claim_state': 'locked'},
        {'held_quantity': 2, 'claimable_quantity': 10, 'claim_state': 'ready',
         'claim_read_state': 'stale'},
        {'held_quantity': 0, 'claimable_quantity': 0, 'claim_state': 'none'},
    )
    result = project_snapshot(raw)
    assert {row['id'] for row in result['tokens']} == {'eth:4', 'eth:5'}
    assert [row['id'] for row in result['claimable']] == ['eth:3', 'eth:5']
    assert result['metrics']['claimable_value'] == .1
    assert result['metrics']['claimable_known'] == 1
    assert result['metrics']['claimable_total'] == 2
    raw['agents'] = [{'id': str(i), 'online': False} for i in range(10)]
    assert project_snapshot(raw)['metrics']['claimable_value'] == .1


def test_stale_claim_only_token_remains_visible_without_current_usd_value():
    raw = _snapshot()
    raw['tokens'][2]['claim_read_state'] = 'stale'
    result = project_snapshot(raw, assets='claimable')
    assert {row['symbol'] for row in result['tokens']} == {'TIDE'}
    foam = next(row for row in result['claimable'] if row['symbol'] == 'FOAM')
    assert foam['claimable_quantity'] == 50000
    assert foam['claim_read_state'] == 'stale'
    assert foam['claimable_usd'] is None
    assert result['metrics']['claimable_value'] == 200
    assert result['metrics']['claimable_known'] == 1
    assert result['metrics']['claimable_total'] == 2
    raw['tokens'][2].update(claim_read_state='unavailable', claimable_quantity=None)
    assert {row['symbol'] for row in project_snapshot(raw)['tokens']} == {'TIDE', 'KITE', 'MESH'}


def test_duplicate_identities_and_paired_positions_are_not_summed_twice():
    raw = _snapshot()
    tide, kite, foam, mesh = raw['tokens']
    tide.update(token_address='synthetic:TIDE', chain_id=1, paired_position_id='position:A')
    mesh.update(paired_position_id='position:A', paired_symbol='IMD', paired_amount=120000)
    raw['tokens'].append(dict(tide, id='eth:duplicate', token_address='SYNTHETIC:tide'))
    raw['tokens'].append(deepcopy(kite))
    result = project_snapshot(raw)
    assert result['metrics']['total'] == 3
    assert result['metrics']['held_value'] == 3500
    assert result['metrics']['claimable_value'] == 400
    assert result['metrics']['liquidity_imd'] == 120000
    assert result['metrics']['liquidity_eth'] == 2.4
    assert result['metrics']['liquidity_partial'] is False
    raw['tokens'][-1] = dict(tide, id='base:401', chain='base', chain_id=8453)
    assert project_snapshot(raw)['metrics']['held_value'] == 4500


@pytest.mark.parametrize('sort, symbols', [
    ('value', ['MESH', 'TIDE', 'KITE']),
    ('claimable', ['TIDE', 'KITE', 'MESH']),
    ('symbol', ['KITE', 'MESH', 'TIDE']),
    ('change', ['TIDE', 'KITE', 'MESH']),
    ('newest', ['TIDE', 'KITE', 'MESH']),
    ('volume', ['TIDE', 'MESH', 'KITE']),
])
def test_supported_sorts_are_deterministic(sort, symbols):
    result = project_snapshot(_snapshot(), sort=sort)
    assert [row['symbol'] for row in result['tokens']] == symbols


def test_unknown_values_sort_last_and_partial_value_counts_only_known_positions():
    raw = _snapshot()
    raw['tokens'][0]['price_usd'] = None
    result = project_snapshot(raw)
    assert result['tokens'][-1]['symbol'] == 'TIDE'
    assert result['metrics']['held_value'] == 2500
    assert result['metrics']['held_known'] == 2 and result['metrics']['held_total'] == 3
    assert result['metrics']['claimable_value'] == 200
    assert result['metrics']['claimable_known'] == 1 and result['metrics']['claimable_total'] == 2


def test_no_wallet_unavailable_and_no_match_are_distinct_and_outputs_are_detached():
    raw = _snapshot()
    saved = deepcopy(raw)
    result = project_snapshot(raw)
    result['tokens'][0]['sparkline'][0] = -10
    result['activity'][0]['amount'] = -10
    result['agents'][0]['online'] = False
    assert raw == saved
    empty = project_snapshot(raw, query='no match')
    assert empty['metrics']['held_value'] == 0 and empty['tokens'] == []
    raw['wallet'] = None
    no_wallet = project_snapshot(raw)
    assert no_wallet['wallet'] is None
    assert no_wallet['tokens'] == no_wallet['activity'] == no_wallet['agents'] == []
    assert no_wallet['metrics']['total'] == no_wallet['metrics']['agents_total'] == 0
    raw.update(wallet=SAMPLE_WALLET, tokens=None, agents=None)
    unavailable = project_snapshot(raw)
    assert unavailable['tokens'] is unavailable['metrics'] is unavailable['claimable'] is None
    assert unavailable['agents'] is None


def test_liquidity_unknown_and_stale_are_partial_without_turning_into_zero():
    raw = _snapshot({'paired_amount': None, 'liquidity_state': 'unavailable'})
    metrics = project_snapshot(raw)['metrics']
    assert metrics['liquidity_imd'] is metrics['liquidity_eth'] is None
    assert metrics['liquidity_partial'] is True
    raw['tokens'].append(dict(raw['tokens'][0], id='base:2', chain='base',
                              paired_amount=0, paired_symbol='ETH', liquidity_state='ok'))
    metrics = project_snapshot(raw)['metrics']
    assert metrics['liquidity_imd'] is None and metrics['liquidity_eth'] == 0


def test_agents_unknown_and_duplicate_agents_have_honest_totals():
    raw = _snapshot()
    raw['agents'] = None
    metrics = project_snapshot(raw)['metrics']
    assert metrics['agents_total'] is metrics['agents_online'] is None
    raw['agents'] = [{'id': '1', 'online': True}, {'id': '1', 'online': True}]
    metrics = project_snapshot(raw)['metrics']
    assert metrics['agents_total'] == metrics['agents_online'] == 1
    raw['agents'].append({'id': '2', 'online': None})
    metrics = project_snapshot(raw)['metrics']
    assert metrics['agents_total'] == 2 and metrics['agents_online'] is None


def test_unrealized_pnl_uses_held_cost_and_filtered_population_excluding_claims():
    raw = _snapshot()
    raw['tokens'][2]['held_cost_usd'] = None  # Claim-only token needs no cost basis.
    metrics = project_snapshot(raw)['metrics']
    assert metrics['pnl_usd'] == 200
    assert metrics['pnl_percent'] == pytest.approx(200 / 3300 * 100)
    metrics = project_snapshot(raw, chain='base')['metrics']
    assert metrics['pnl_usd'] == -100
    assert metrics['pnl_percent'] == pytest.approx(-100 / 900 * 100)
    metrics = project_snapshot(raw, query='foam')['metrics']
    assert metrics['pnl_usd'] == 0 and metrics['pnl_percent'] is None


@pytest.mark.parametrize('change', [
    {'held_cost_usd': None}, {'held_cost_usd': float('nan')}, {'held_cost_usd': -1},
    {'held_quantity': None, 'balance_state': 'unavailable'},
    {'price_usd': None}, {'balance_state': 'stale'}, {'market_state': 'stale'},
])
def test_pnl_is_unknown_when_any_held_position_lacks_current_value_or_cost(change):
    raw = _snapshot()
    raw['tokens'][0].update(change)
    metrics = project_snapshot(raw)['metrics']
    assert metrics['pnl_usd'] is metrics['pnl_percent'] is None


def test_zero_cost_has_defined_dollar_pnl_but_no_infinite_percent():
    raw = _snapshot({'held_quantity': 10, 'price_usd': 2, 'held_cost_usd': 0})
    metrics = project_snapshot(raw)['metrics']
    assert metrics['pnl_usd'] == 20 and metrics['pnl_percent'] is None


def _live_snapshot():
    raw = _snapshot()
    raw.update(is_mock=False, wallet_generation=4, sources={
        name: dict(state='ok', complete=True, as_of=100) for name in ('catalogue', 'balances', 'claims', 'agents')})
    return raw


def test_live_projection_keeps_source_clocks_and_rejects_unproven_numeric_cost_basis():
    raw = _live_snapshot()
    result = project_snapshot(raw)
    assert tuple(result) == models.LIVE_PROJECTION_KEYS
    assert result['wallet_generation'] == 4 and result['sources'] == raw['sources']
    assert result['metrics']['pnl_usd'] is result['metrics']['pnl_percent'] is None
    for row in raw['tokens']:
        row.update(basis_state='ok', basis_quantity=row['held_quantity'], basis_source='verified fixture', basis_read_at=100)
    assert project_snapshot(raw)['metrics']['pnl_usd'] == 200
    raw['tokens'][0]['basis_quantity'] -= 1
    assert project_snapshot(raw)['metrics']['pnl_usd'] is None


def test_live_missing_membership_never_looks_like_a_complete_empty_wallet():
    raw = _live_snapshot()
    raw['sources']['balances'].update(state='partial', complete=False, checked=0, total=4)
    raw['sources']['claims'].update(state='pending', complete=False)
    for row in raw['tokens']:
        row.update(held_quantity=None, balance_state='pending', claimable_quantity=None,
                   claim_state='unavailable', claim_read_state='pending')
    result = project_snapshot(raw)
    assert result['tokens'] == []
    assert result['metrics']['held_value'] is None
    assert result['metrics']['claimable_value'] is None
    assert result['metrics']['held_partial'] is result['metrics']['claimable_partial'] is True
    assert result['metrics']['pnl_usd'] is None


def test_live_known_partial_sum_is_qualified_even_when_all_visible_rows_are_priced():
    raw = _live_snapshot()
    raw['sources']['balances'].update(complete=False, state='partial', checked=4, total=10)
    result = project_snapshot(raw, chain='base')
    assert result['metrics']['held_value'] == 800
    assert result['metrics']['held_partial'] is True
    assert result['metrics']['pnl_usd'] is None
    assert result['sources']['balances']['total'] == 10
    result['sources']['balances']['total'] = 0
    assert raw['sources']['balances']['total'] == 10


def test_live_stale_agents_cannot_look_like_current_online_counts():
    raw = _live_snapshot()
    raw['sources']['agents'].update(state='stale', complete=False)
    result = project_snapshot(raw)
    assert result['metrics']['agents_state'] == 'stale'
    assert result['metrics']['agents_as_of'] == 100
