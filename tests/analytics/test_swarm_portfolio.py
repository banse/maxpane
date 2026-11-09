from copy import deepcopy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data.swarm_portfolio_client import normalize_result
from maxpane_dashboard.analytics.swarm_portfolio import project
from tests.data.test_swarm_portfolio import sample


def snapshot():
    raw=sample(json.loads(Path('tests/fixtures/portfolio_scan/captured.json').read_text()))
    return normalize_result(raw,raw['wallet']['address'],now=raw['at'])


def test_projection_total_counts_each_bucket_once_and_excludes_utility_tvl():
    result=project(snapshot(),show_no_sale=True)
    assert result['metrics']['total_usd']==137
    assert result['metrics']['unclaimed_usd']==7
    assert result['metrics']['pending_usd']==4
    assert result['metrics']['seats_count'] is None


def test_filters_recompute_all_monetary_sections_and_keep_identity():
    source=snapshot(); asset=source['assets'][0]
    shown=project(source,query=asset['symbol'])
    assert shown['metrics']['total_usd']==137
    hidden=project(source,chain=8453)
    assert hidden['metrics']['total_usd']==0
    assert hidden['holdings']==[] and hidden['positions']==[] and hidden['rewards']==[]
    assert source['assets'][0]['total_usd']==137


def test_unknown_is_not_zero_and_no_sale_filter_preserves_unknown():
    source=snapshot(); source['assets'][0]['wallet_usd']=None
    source['assets'][0]['total_usd']=None
    source['state']='partial'
    result=project(source)
    assert result['metrics']['wallet_usd'] is None
    assert result['metrics']['partial'] is True
    assert len(result['holdings'])==1


def test_cold_snapshot_keeps_metrics_unknown():
    result=project({'wallet':None,'assets':None,'positions':None,'rewards':None,'nfts':None,'standings':None,'utilities':None})
    assert result['metrics']['total_usd'] is None
    assert result['metrics']['nft_count'] is None


@pytest.mark.parametrize('state', ['loading', 'unavailable'])
@pytest.mark.parametrize('seats,count,ids', [
    ([{'id':'7','token_id':'7'}],1,['7']), ([],0,[]), (None,None,[]),
])
def test_independent_seat_observation_survives_unavailable_assets(state,seats,count,ids):
    source={'state':state,'assets':None,'seats':seats,
            'seats_as_of':200 if seats is not None else None,
            'seats_state':'ok' if seats is not None else 'unavailable'}
    result=project(source)
    assert result['metrics']['seats_count']==count
    assert result['metrics']['seat_ids']==ids
    assert result['seats_as_of']==source['seats_as_of']
    assert result['seats_state']==source['seats_state']
    assert all(result['metrics'][key] is None for key in
               ('total_usd','wallet_usd','staked_usd','unclaimed_usd'))


def test_unknown_stake_identity_does_not_turn_its_value_into_zero():
    source=snapshot()
    source['assets'][0]['staked_usd']=0
    source['positions'][0].update(asset_id=None,value_usd=None)
    source['state']='partial'
    assert project(source)['metrics']['staked_usd'] is None


def test_invalid_rows_do_not_create_known_empty_totals():
    source=snapshot()
    for name in ('assets','positions','rewards'): source[name]=[]
    source['state']='partial'; source['coverage']['malformed_rows']=1
    result=project(source)
    assert result['metrics']['total_usd'] is None
