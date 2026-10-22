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
        {'method': 'eth_blockNumber'}, {'method': 'eth_getLogs'}]))
    meter(httpx.Request('POST', 'https://two.test', json={'method': 'eth_blockNumber'}))
    meter(httpx.Request('GET', 'https://api.test/items'))
    assert meter.counts() == {
        'requests': 2, 'entries': 3, 'rest': 1, 'multicall_subcalls': 0,
        'methods': {'eth_blockNumber': 2, 'eth_getLogs': 1},
        'rest_paths': {'api.test/items': 1},
    }


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
