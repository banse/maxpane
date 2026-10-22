"""The offline budget command counts wire work, not estimates of client cost."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/measure_surf_rpc_budget.py'


def harness():
    spec = importlib.util.spec_from_file_location('rpc_budget_measure', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wire_counts_distinguish_requests_entries_and_rest():
    h = harness()
    meter = h.Meter(lambda request: httpx.Response(200, json={}))
    meter(httpx.Request('POST', 'https://one.test', json=[
        {'method': 'eth_blockNumber'}, {'method': 'eth_getLogs',
         'params': [{'fromBlock': '0x10', 'toBlock': '0x20'}]}]))
    meter(httpx.Request('POST', 'https://two.test', json={'method': 'eth_blockNumber'}))
    meter(httpx.Request('GET', 'https://api.test/items'))
    assert meter.counts() == {
        'requests': 2, 'entries': 3, 'rest': 1, 'multicall_subcalls': 0,
        'log_requested_blocks': 17, 'log_returned_rows': 0,
        'methods': {'eth_blockNumber': 2, 'eth_getLogs': 1},
        'rest_paths': {'api.test/items': 1},
    }


def test_wire_log_counts_include_repeated_ranges_and_match_response_ids():
    h = harness()
    meter = h.Meter(lambda request: httpx.Response(200, json=[
        {'id': 2, 'result': [{'blockNumber': '0x12'}]},
        {'id': 1, 'error': {'code': -32000}}]))
    calls = [{'id': i, 'method': 'eth_getLogs',
              'params': [{'fromBlock': '0x10', 'toBlock': '0x20'}]} for i in (1, 2)]
    meter(httpx.Request('POST', 'https://one.test', json=calls))
    assert meter.counts()['log_requested_blocks'] == 34
    assert meter.counts()['log_returned_rows'] == 1


def test_synthetic_header_never_proves_a_future_block():
    h = harness()
    entry = {'id': 'surf-block-16', 'method': 'eth_getBlockByNumber', 'params': ['0x10', False]}
    assert h.synthetic_header(entry, 16)['number'] == '0x10'
    assert h.synthetic_header(entry, 15) is None


def test_compact_report_keeps_evidence_of_projection_and_completeness_failures():
    h = harness()
    def run(value, complete):
        return {'rows': [{'scenario': 'example', 'counts': {'requests': 1},
                         'projection': value, 'projection_digest': h.digest(value), 'complete': complete}],
                'fixture_sha256': {'fixture': 'same'}, 'harness_sha256': 'same'}
    report = h.compact_report({'before': run({'count': 1}, True), 'after': run({'count': 2}, False)})
    assert report['checks']['projection_mismatches'] == ['example']
    assert report['checks']['incomplete_after'] == ['example']
    assert 'projection' not in report['after']['rows'][0]
    assert report['after']['rows'][0]['projection_digest'] == h.digest({'count': 2})


@pytest.mark.asyncio
async def test_rolling_replay_preserves_complete_corpus_and_reduces_warm_ranges(tmp_path):
    h = harness()
    rows = (await h.measure(tmp_path, only={'pool4-rolling', 'recent-rolling'}))['rows']
    assert len(rows) == 16
    for family in ('pool4-hook', 'pool4-swaps', 'pool4-drip', 'recent'):
        selected = {row['scenario'].split('/')[-1]: row for row in rows
                    if row['scenario'].startswith(family + '/')}
        assert all(row['complete'] for row in selected.values())
        assert selected['cold']['expected_rows'] > 0
        assert selected['cold']['projection'] == selected['cold']['expected_projection']
        assert selected['steady']['counts']['log_requested_blocks'] < selected['cold']['counts']['log_requested_blocks'] / 10
        assert all(row['projection'] == row['expected_projection'] for row in selected.values())


@pytest.mark.asyncio
async def test_nft_wire_counts_full_inspection_and_proof_reuse(tmp_path):
    rows = {row['scenario']: row for row in (await harness().measure(tmp_path, only={'nft'}))['rows']}
    assert all(row['complete'] for row in rows.values())
    assert rows['nft/full-1']['counts']['requests'] == 11
    assert rows['nft/full-4663']['counts']['requests'] == 22
    assert rows['nft/full-1']['projection']['stats']['totalSupply'] == 1
    assert rows['nft/proof-repeat']['counts']['requests'] == 0
    assert rows['nft/proof-repeat']['projection'] == rows['nft/proof-cold']['projection']


@pytest.mark.asyncio
async def test_replay_uses_real_clients_and_preserves_full_staker_population(tmp_path):
    h = harness()
    report = await h.measure(tmp_path, only={'pool4-known-state', 'stakers'})
    known = next(row for row in report['rows'] if row['scenario'] == 'pool4-known-state')
    assert known['counts']['requests'] == 2
    assert known['counts']['entries'] == 2
    assert known['counts']['multicall_subcalls'] > 50
    stakers = [row for row in report['rows'] if row['scenario'].startswith('stakers/')]
    balances = {}
    for row in h.load('pool4/simd_transfers_full.json')['response']['result']:
        amount = int(row['data'], 16)
        for topic, direction in ((row['topics'][1], -1), (row['topics'][2], 1)):
            address = '0x' + topic[-40:]
            if int(address, 16):
                balances[address] = balances.get(address, 0) + direction * amount
    assert len(stakers) == 6
    assert all(row['complete'] for row in stakers)
    assert all(row['projection']['pool4_staker_count'] == sum(value > 0 for value in balances.values())
               for row in stakers)
    assert len({row['projection_digest'] for row in stakers}) == 1
    assert all(row['counts']['methods'].get('eth_getLogs', 0) <= 2
               for row in stakers if row['scenario'] in ('stakers/steady', 'stakers/reloaded'))


def test_captured_caps_allow_sparse_wide_mev_ranges_and_preserve_exact_error():
    h = harness()
    fixture = h.load('rpc_budget_errors.json')['cases']
    rows = [{'blockNumber': '0x1'}]
    assert h.capped_logs('rpc.mevblocker.io', 0, 1_200_000, rows) == {'result': rows}
    assert h.capped_logs('rpc.mevblocker.io', 0, 1_200_000, rows * 10001) == {
        'error': fixture['mevblocker_range']['body']['error']}
    assert h.capped_logs('1.rpc.thirdweb.com', 0, 1000, rows) == {
        'error': fixture['thirdweb_range']['body']['error']}


@pytest.mark.asyncio
async def test_boardroom_budget_includes_discovery_and_all_medium_source_dispatches(tmp_path):
    rows = (await harness().measure(tmp_path, only={'boardroom'}))['rows']
    minute = next(row for row in rows if row['scenario'] == 'boardroom/revalidation-minute')
    assert 0 < minute['counts']['entries'] <= 10
    assert minute['counts']['methods'].get('eth_getLogs', 0) == 0
    ttl = next(row for row in rows if row['scenario'] == 'boardroom/180s')
    paths = ttl['counts']['rest_paths']
    assert len(paths) == 4
    assert all(0 < count <= 2 for count in paths.values())
    assert all(row['projection']['pool4_share_price'] > 0 for row in rows)
