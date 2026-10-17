"""NFT filtering preserves identities, evidence and source clocks."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def nft():
    return importlib.import_module('maxpane_dashboard.analytics.surf_nft')


@pytest.fixture
def raw():
    return json.loads((Path(__file__).parents[1] / 'fixtures/surf/nft/projection.json').read_text())


@pytest.fixture
def snapshot(nft, raw):
    rows = [nft.normalize_record(row) for row in raw['records']]
    return {
        'nft_rows': [row for row in rows if row['category'] == 'launched'],
        'nft_build_rows': [row for row in rows if row['category'] == 'in_the_making'],
        'nft_summary': {'observed_at': raw['observed_at']}, 'nft_selected': None,
        'nft_sources': {'discovery': {'observed_at': raw['observed_at'], 'state': 'partial'}},
        'nft_coverage': raw['coverage'], 'as_of': raw['observed_at'] + 900,
    }


def test_normalizer_preserves_scanner_nested_evidence_without_mutating_it(nft, raw):
    original = deepcopy(raw['records'][0])
    result = nft.normalize_record(original)
    assert result['chain_id'] == 1
    assert result['contract'] == original['contractAddress'].lower()
    for source, target in [('mint','mint'), ('stats','stats'), ('utility','utility'),
                           ('idmdBenefit','idmd_benefit'), ('tokens','related_tokens')]:
        assert result[target] == original[source]
    result['mint']['routes'][0]['state'] = 'changed'
    assert original == raw['records'][0]


@pytest.mark.parametrize('chain', [None, True, 1.0, '1', 8453, 11155111])
def test_identity_refuses_unsupported_or_ambiguous_chains(nft, raw, chain):
    record = deepcopy(raw['records'][0]); record['chainId'] = chain
    assert nft.normalize_record(record) is None
    assert nft.collection_identity(chain, record['contractAddress']) is None


def test_same_name_never_joins_contracts_or_chains(nft, snapshot):
    twins = [row for row in snapshot['nft_rows'] if row['name'] == 'BMC Illuminati Pass']
    cross_chain = deepcopy(twins[0]); cross_chain.update(chain_id=4663, id='4663:'+twins[0]['contract'])
    selected = nft.select_rows(twins+[cross_chain], filters={'search':'BMC'})
    assert len(selected) == 3
    assert len({row['id'] for row in selected}) == 3


def test_identity_rejects_conflicting_top_level_fields_and_forged_id(nft, raw):
    record = deepcopy(raw['records'][0]); record['id'] = '1:0x'+'b'*40
    assert nft.normalize_record(record) is None
    record = deepcopy(raw['records'][0]); record['chain_id'] = 4663
    assert nft.normalize_record(record) is None


def test_build_identity_uses_project_uuid_and_never_contract(nft, raw):
    source = next(row for row in raw['records'] if row['category']=='in_the_making')
    row = nft.normalize_record(source)
    assert row['id'] == source['id']
    assert row['project_id'] == source['id'].split(':',2)[2]
    assert row['contract'] is None
    source['contractAddress'] = '0x'+'c'*40
    assert nft.normalize_record(source) is None


def test_common_filters_scope_heroes_stage_does_not(nft, snapshot):
    launched = nft.project_snapshot(snapshot, filters={'idmd':'yes','stage':'launched'})
    builds = nft.project_snapshot(snapshot, filters={'idmd':'yes','stage':'building'})
    assert launched['nft_summary'] == builds['nft_summary']
    assert launched['nft_summary']['deployed'] == 2
    assert launched['nft_summary']['idmd_free'] == 2
    assert launched['nft_summary']['conditional'] == 0
    assert launched['nft_selected']['category'] == 'launched'
    assert builds['nft_selected'] is None
    assert len(snapshot['nft_rows']) == 7


@pytest.mark.parametrize('status,count', [('yes',2),('conditional',1),('no',3),('unknown',1)])
def test_all_four_idmd_statuses_remain_distinct(nft,snapshot,status,count):
    result = nft.project_snapshot(snapshot,filters={'idmd':status})
    assert len(result['nft_rows']) == count
    assert all(row['idmd_benefit']['status']==status for row in result['nft_rows'])


def test_open_public_route_does_not_open_closed_idmd_route(nft,snapshot):
    row = deepcopy(snapshot['nft_rows'][0])
    row['mint'].update(state='open',routes=[{'name':'Public mint','state':'open'},
                                           {'name':'IDMD claim','state':'ended'}])
    result = nft.select_rows([row],filters={'mint':'open'})
    assert len(result)==1
    assert result[0]['mint']['routes'][1]['state']=='ended'
    assert nft.select_rows([row],filters={'mint':'ended'})==[]


@pytest.mark.parametrize('state', ['conditional', 'awaiting-season-end',
                                 'awaiting-finalization', 'blank-season', 'auction-open'])
def test_scanner_specific_mint_states_have_exact_filters(nft, snapshot, state):
    row = deepcopy(snapshot['nft_rows'][0])
    row['mint']['state'] = state
    assert nft.select_rows([row], filters={'mint': state}) == [row]
    assert nft.select_rows([row], filters={'mint': 'open'}) == []


def test_route_open_can_be_filtered_without_rewriting_overall_state(nft,snapshot):
    row=deepcopy(snapshot['nft_rows'][0]);row['mint']['state']='auction / delivery'
    row['mint']['routes']=[{'name':'Snapshot','state':'open'}]
    assert nft.select_rows([row],filters={'mint':'open'})==[]
    result=nft.select_rows([row],filters={'mint':'route-open'})
    assert result[0]['mint']['state']=='auction / delivery'


def test_search_uses_job_project_contract_and_name_identity(nft,snapshot):
    row=snapshot['nft_rows'][0]
    assert nft.select_rows([row],filters={'search':row['contract'].upper()})==[row]
    assert nft.select_rows([row],filters={'search':row['jobs'][0]['id']})==[row]
    build=snapshot['nft_build_rows'][0]
    assert nft.select_rows([build],filters={'search':build['project_id']})==[build]
    assert nft.select_rows([row],filters={'search':'no such collection'})==[]


def test_utility_filter_keeps_evidence_status(nft,snapshot):
    row=deepcopy(snapshot['nft_rows'][0]);row['utility']=[{'kind':'game','status':'inferred'}]
    selected=nft.select_rows([row],filters={'utility':'game'})
    assert selected[0]['utility'][0]['status']=='inferred'
    assert nft.select_rows([row],filters={'utility':'staking'})==[]


def test_selection_tracks_identity_and_filters_choose_first_or_clear(nft,snapshot):
    row=snapshot['nft_rows'][-1]
    result=nft.project_snapshot(snapshot,filters={'sort':'name'},selected_id=row['id'])
    assert result['nft_selected']['id']==row['id']
    result=nft.project_snapshot(snapshot,filters={'chain':'robinhood'},selected_id=row['id'])
    assert result['nft_selected']['name']=='FarmItems'
    result=nft.project_snapshot(snapshot,filters={'search':'nothing matches'},selected_id=row['id'])
    assert result['nft_selected'] is None


def test_readme_projection_is_bound_to_selected_identity_and_preserves_source_clock(nft, snapshot):
    identity = snapshot['nft_rows'][0]['id']
    snapshot['nft_readme'] = dict(identity=identity, repository_url='https://github.com/example/collection',
        readme_url=None, revision='a' * 40, text='Source excerpt', observed_at=123., state='ok')
    result = nft.project_snapshot(snapshot, selected_id=identity)
    assert result['nft_readme'] == snapshot['nft_readme']
    result['nft_readme']['text'] = 'modified'
    assert snapshot['nft_readme']['text'] == 'Source excerpt'
    assert nft.project_snapshot(snapshot, selected_id=snapshot['nft_rows'][1]['id'])['nft_readme'] is None
    assert nft.project_snapshot(snapshot, filters={'search': 'nothing matches'})['nft_readme'] is None


def test_normalized_records_round_trip_and_nested_numbers_are_not_substituted(nft,raw):
    farm=nft.normalize_record(next(row for row in raw['records'] if row['name']=='FarmItems'))
    assert nft.normalize_record(farm)==farm
    assert farm['stats']['totalMinted']==114
    assert farm['stats']['totalSupply']==110
    assert farm['stats']['burnedItems']==4
    imd=nft.normalize_record(raw['records'][0])
    assert imd['stats']['totalSupply'] is None


def test_unknown_inventory_is_not_known_empty(nft,snapshot):
    snapshot.update(nft_rows=None,nft_build_rows=None)
    unknown=nft.project_snapshot(snapshot)
    assert unknown['nft_rows'] is None
    assert all(unknown['nft_summary'][k] is None for k in ('deployed','building','mint_open','idmd_free','conditional','chains'))
    snapshot.update(nft_rows=[],nft_build_rows=[],nft_coverage={'complete':True})
    empty=nft.project_snapshot(snapshot)
    assert all(empty['nft_summary'][k]==0 for k in ('deployed','building','mint_open','idmd_free','conditional','chains'))
    assert empty['nft_summary']['partial'] is False


def test_unread_rules_do_not_establish_zero_open_or_zero_idmd_benefit(nft,snapshot):
    snapshot['nft_rows']=[row for row in snapshot['nft_rows'] if row['name']=='Unreviewed Example']
    result=nft.project_snapshot(snapshot)
    assert result['nft_summary']['deployed']==1
    assert result['nft_summary']['mint_open'] is None
    assert result['nft_summary']['idmd_free'] is None
    assert result['nft_summary']['conditional'] is None
    assert result['nft_summary']['mint_known']==result['nft_summary']['idmd_known']==0
    assert result['nft_summary']['partial'] is True


def test_projection_never_renews_source_clocks_or_mutates_cached_input(nft,snapshot):
    before=deepcopy(snapshot)
    result=nft.project_snapshot(snapshot)
    assert result['nft_summary']['observed_at']==snapshot['nft_summary']['observed_at']
    assert result['nft_sources']==snapshot['nft_sources']
    assert result['as_of']==snapshot['as_of']
    result['nft_rows'][0]['mint']['state']='wrong'
    result['nft_sources']['discovery']['observed_at']=999
    assert snapshot==before


def test_newest_sort_uses_event_time_unknown_last_not_projection_clock(nft,snapshot):
    rows=deepcopy(snapshot['nft_rows'][:3])
    for row, stamp in zip(rows,('2026-10-16T10:00:00Z',None,'2026-10-17T10:00:00Z')):
        row['deployment']['timestamp']=stamp
    assert [r['id'] for r in nft.select_rows(rows,filters={'sort':'newest'})]==[rows[2]['id'],rows[0]['id'],rows[1]['id']]


def test_invalid_filter_choice_fails_instead_of_quietly_broadening(nft,snapshot):
    with pytest.raises(ValueError):
        nft.project_snapshot(snapshot,filters={'chain':'sepolia'})
