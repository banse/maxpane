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


def imd_reference():
    return json.loads(Path('tests/fixtures/portfolio_scan/imd-reference.json').read_text())['asset']


def test_imd_reference_identity_and_quantity_fields_agree_with_source_contract():
    from maxpane_dashboard.analytics.swarm_portfolio import IMD_REFERENCE, IMD_QUANTITY_FIELDS
    from maxpane_dashboard.data.surf_addresses import IMD_TOKEN
    from maxpane_dashboard.data.swarm_portfolio_models import BUCKETS
    assert IMD_REFERENCE == (1, IMD_TOKEN.lower())
    assert IMD_QUANTITY_FIELDS == tuple(bucket + '_quantity' for bucket in BUCKETS)


def test_imd_equivalent_uses_the_complete_canonical_exposure_and_preserves_snapshot():
    from maxpane_dashboard.analytics.swarm_portfolio import imd_equivalent
    source = {'assets': [imd_reference()]}
    before = deepcopy(source)
    assert imd_equivalent(source, 2518.7962726347896) == pytest.approx(1005.0619074640103)
    assert imd_equivalent(source, 0) == 0
    assert source == before
    source['assets'][0]['symbol'] = 'RENAMED'
    assert imd_equivalent(source, 2518.7962726347896) == pytest.approx(1005.0619074640103)


@pytest.mark.parametrize('change', [
    {'chain_id': 4663}, {'token_address': '0x'+'ab'*20}, {'sell_state': 'partial'},
    {'total_usd': None}, {'total_usd': 0}, {'total_usd': -1}, {'total_usd': float('inf')},
    {'staked_quantity': None}, {'wallet_quantity': float('nan')}, {'pending_quantity': -1},
])
def test_imd_equivalent_rejects_unusable_or_wrong_token_quotes(change):
    from maxpane_dashboard.analytics.swarm_portfolio import imd_equivalent
    asset = imd_reference(); asset.update(change)
    assert imd_equivalent({'assets': [asset]}, 1000) is None


@pytest.mark.parametrize('total', [None, -1, float('nan'), float('inf'), True])
def test_imd_equivalent_unknown_total_stays_unknown(total):
    from maxpane_dashboard.analytics.swarm_portfolio import imd_equivalent
    assert imd_equivalent({'assets': [imd_reference()]}, total) is None


def test_imd_equivalent_rejects_missing_duplicate_and_zero_quantity_references():
    from maxpane_dashboard.analytics.swarm_portfolio import imd_equivalent, IMD_QUANTITY_FIELDS
    assert imd_equivalent({'assets': None}, 1000) is None
    assert imd_equivalent({'assets': []}, 1000) is None
    assert imd_equivalent({'assets': [imd_reference(), imd_reference()]}, 1000) is None
    asset = imd_reference()
    asset.update({key:0 for key in IMD_QUANTITY_FIELDS})
    assert imd_equivalent({'assets': [asset]}, 1000) is None
