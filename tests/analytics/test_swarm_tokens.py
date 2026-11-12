"""Filtering must mean the same thing in every panel of the mock market."""

from copy import deepcopy

import pytest

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot, select_tokens
from maxpane_dashboard.data.swarm_tokens_demo import MOCK_NOW, demo_snapshot
from maxpane_dashboard.data import swarm_tokens_models as models


def test_live_unavailable_is_not_empty_and_source_clocks_survive_filters():
    raw = dict(tokens=None, activity=None, as_of=MOCK_NOW, is_mock=False,
               sources={'catalogue': {'state': 'unavailable', 'as_of': None}})
    unavailable = project_snapshot(raw)
    assert unavailable['tokens'] is None and unavailable['metrics'] is None
    assert unavailable['newly_launched'] is None and unavailable['gainers'] is None
    assert unavailable['sources'] == raw['sources']
    raw.update(tokens=[], activity=[])
    assert project_snapshot(raw)['metrics']['total'] == 0
    raw['tokens'] = [dict(demo_snapshot()['tokens'][0], launched_at=None,
                          token_address='0x'+'a'*40)]
    projected = project_snapshot(raw, query='0x'+'a'*40)
    assert len(projected['tokens']) == 1
    assert projected['newly_launched'] == []
    assert projected['sources'] == raw['sources']
    projected['sources']['catalogue']['state'] = 'wrong'
    assert raw['sources']['catalogue']['state'] == 'unavailable'


def test_stale_market_quotes_remain_in_rankings_with_original_source_state():
    raw = demo_snapshot()
    raw['tokens'] = [dict(raw['tokens'][0],market_state='stale')]
    projected = project_snapshot(raw)
    assert len(projected['tokens']) == 1
    assert projected['gainers'][0]['market_state'] == 'stale'
    assert projected['losers'] == []
    assert projected['metrics']['volume_24h'] == raw['tokens'][0]['volume_24h']
    assert projected['metrics']['volume_known'] == 1


def test_paired_liquidity_totals_keep_assets_filters_zero_and_unknown_separate():
    raw = demo_snapshot()
    base = raw['tokens'][0]
    raw['tokens'] = [dict(base, id=str(i), chain=chain, paired_symbol=symbol,
                          paired_amount=amount, liquidity_state=state)
                     for i, (chain, symbol, amount, state) in enumerate([
                         ('eth','IMD',788,'ok'), ('rh','IMD',12,'ok'),
                         ('eth','ETH',2.5,'ok'), ('base','ETH',0,'ok'),
                         ('eth','USDC',900,'ok'), ('eth','IMD',999,'stale'),
                         ('eth',None,None,'unknown')])]
    metrics = project_snapshot(raw)['metrics']
    assert metrics['liquidity_imd'] == 1799 and metrics['liquidity_eth'] == 2.5
    assert metrics['liquidity_partial'] is True
    filtered = project_snapshot(raw, chain='rh')['metrics']
    assert filtered['liquidity_imd'] == 12 and filtered['liquidity_eth'] == 0
    assert filtered['liquidity_partial'] is False
    zero = project_snapshot(raw, chain='base')['metrics']
    assert zero['liquidity_eth'] == 0 and zero['liquidity_partial'] is False
    empty = project_snapshot(raw, query='no such token')['metrics']
    assert empty['liquidity_imd'] == empty['liquidity_eth'] == 0
    raw['tokens'] = [raw['tokens'][-1]]
    unknown = project_snapshot(raw)['metrics']
    assert unknown['liquidity_imd'] is unknown['liquidity_eth'] is None


def test_projection_metrics_reconcile_with_rows_and_unknown_volume():
    snapshot = demo_snapshot()
    result = project_snapshot(snapshot)
    metrics = result['metrics']
    assert tuple(result) == models.PROJECTION_KEYS
    assert tuple(metrics) == models.METRIC_KEYS
    assert metrics['total'] == 24
    assert metrics['new_24h'] == 3
    assert metrics['total'] == sum(metrics[key] for key in ('two_sided', 'one_sided', 'unknown', 'other'))
    known = [token['volume_24h'] for token in snapshot['tokens'] if token['volume_24h'] is not None]
    assert metrics['volume_known'] == len(known) < metrics['volume_total'] == 24
    assert metrics['volume_24h'] == sum(known)
    assert [token['symbol'] for token in result['newly_launched']] == ['CLAUS', 'NOVA', 'ORB']
    assert result['is_mock'] is True and result['as_of'] == MOCK_NOW
    assert project_snapshot(snapshot, query='ORB')['metrics']['volume_24h'] is None
    assert project_snapshot(snapshot, query='CLAUS')['metrics']['volume_24h'] == 0


@pytest.mark.parametrize('filters', [
    {'chain': 'base'}, {'query': 'sC'}, {'query': 'coin'}, {'query': '1178'},
    {'lp_state': 'one-sided'}, {'lp_state': 'issues'}, {'chain': 'eth', 'query': 'SC'},
])
def test_filters_apply_to_all_panels_consistently(filters):
    snapshot = demo_snapshot()
    result = project_snapshot(snapshot, **filters)
    visible = select_tokens(snapshot['tokens'], **filters)
    ids = {row['id'] for row in visible}
    assert ids, 'The fixture must exercise a nonempty filter'
    assert result['tokens'] == visible
    assert result['metrics']['total'] == len(ids)
    for panel in ('newly_launched', 'gainers', 'losers'):
        assert all(row['id'] in ids for row in result[panel])
    assert result['activity'] == sorted(
        [row for row in snapshot['activity'] if row['token_id'] in ids],
        key=lambda row: (-row['ts'], row['id']),
    )
    if 'chain' in filters:
        assert all(row['chain'] == filters['chain'] for row in visible)
    if filters.get('lp_state') == 'one-sided':
        assert {row['lp_state'] for row in visible} == {'one-token', 'one-quote'}
    if filters.get('lp_state') == 'issues':
        assert {row['lp_state'] for row in visible} == {'unknown', 'withdrawn'}


def test_sort_has_stable_id_ties_keeps_zero_and_orders_unknown_last():
    original = demo_snapshot()['tokens'][0]
    rows = [dict(original, id=key, volume_24h=volume, change_24h=change,
                 launched_at=age, symbol=symbol)
            for key, volume, change, age, symbol in [
                ('b', 10, -2, 2, 'Z'), ('a', 10, -2, 3, 'A'),
                ('d', None, None, 0, 'B'), ('c', 0, 1, 1, 'A'),
            ]]
    assert [row['id'] for row in select_tokens(rows)] == ['a', 'b', 'c', 'd']
    assert [row['id'] for row in select_tokens(rows, sort='change')] == ['c', 'a', 'b', 'd']
    assert [row['id'] for row in select_tokens(rows, sort='newest')] == ['a', 'b', 'c', 'd']
    assert [row['id'] for row in select_tokens(rows, sort='symbol')] == ['a', 'c', 'd', 'b']


def test_new_launch_window_excludes_future_and_exactly_24h_old():
    snapshot = demo_snapshot()
    original = snapshot['tokens'][0]
    snapshot['tokens'] = [dict(original, id=str(age), launched_at=MOCK_NOW-age)
                          for age in (-1, 0, 86399, 86400)]
    result = project_snapshot(snapshot)
    assert result['metrics']['new_24h'] == 2
    assert [row['id'] for row in result['newly_launched']] == ['0', '86399']


def test_rankings_require_positive_price_and_change_but_not_two_sided_lp():
    snapshot = demo_snapshot()
    original = snapshot['tokens'][0]
    snapshot['tokens'] = [dict(original, id=str(index), price_usd=price,
                              change_24h=change, lp_state=state)
                          for index, (price, change, state) in enumerate([
                              (1, 2, 'two-sided'), (None, 500, 'unknown'),
                              (1, -8, 'two-sided'), (0, 50, 'one-token'),
                              (1, 10, 'one-quote'), (1, 0, 'two-sided'),
                              (1, None, 'two-sided'), (1, -2, 'one-token'),
                          ])]
    result = project_snapshot(snapshot)
    assert [row['id'] for row in result['gainers']] == ['4', '0']
    assert [row['id'] for row in result['losers']] == ['2', '7']


def test_no_matches_and_projection_mutation_do_not_damage_input():
    snapshot = demo_snapshot()
    original = deepcopy(snapshot)
    result = project_snapshot(snapshot, query='no matching token')
    assert result['metrics']['total'] == 0
    assert result['metrics']['volume_24h'] is None
    assert all(result[key] == [] for key in ('tokens', 'newly_launched', 'gainers', 'losers', 'activity'))
    result = project_snapshot(snapshot)
    result['tokens'][0]['sparkline'][0] = -1
    result['activity'][0]['amount'] = -1
    select_tokens(snapshot['tokens'])[0]['sparkline'][0] = -1
    assert snapshot == original
