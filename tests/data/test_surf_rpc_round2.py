"""Surf-specific complete windows, shared heads and canonical-tail counter replay."""
import copy
import json

import httpx
import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.surf_transport import read_cycle
from tests.data.test_surf_client import (
    _client_on, _launchpad_fixture_handler, _load_launchpad, _rpc_ok,
    _standard_logs, _topics_match, RecordingTransport,
)


def header(payload):
    return httpx.Response(200, json=_rpc_ok(payload, {
        'number': payload['params'][0], 'hash': '0x' + 'ab' * 32,
    }))


def launch_transport(logs):
    reads = _load_launchpad('launchpad_reads.json')
    reads['coin_count'] = len(logs['launched'])
    original = _launchpad_fixture_handler(reads, logs, {})
    def handle(request):
        payload = json.loads(request.content)
        if isinstance(payload, dict) and payload['method'] == 'eth_getBlockByNumber':
            return header(payload)
        reads['coin_count'] = len(logs['launched'])
        return original(request)
    return RecordingTransport(handle)


@pytest.mark.asyncio
async def test_recent_logs_tail_replay_matches_fresh_full_window_and_sales():
    rows = _standard_logs()
    state = {'head': 25820000}
    # Unique log positions are part of real EVM identity; the old small double
    # reused a transaction/index across two different Seaport events.
    for values in rows.values():
        for i, row in enumerate(values):
            row['blockNumber'] = hex(state['head'] - 5)
            row['logIndex'] = hex(i)
    calls = []
    def handle(request):
        payload = json.loads(request.content)
        method = payload['method']
        if method == 'eth_blockNumber':
            return httpx.Response(200, json=_rpc_ok(payload, hex(state['head'])))
        if method == 'eth_getBlockByNumber':
            return header(payload)
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'],16), int(flt['toBlock'],16)
        calls.append((lo,hi))
        return httpx.Response(200, json=_rpc_ok(payload, [r for r in rows.get(flt['topics'][0], [])
            if lo <= int(r['blockNumber'],16) <= hi and _topics_match(r['topics'], flt['topics'])]))
    transport = RecordingTransport(handle)
    async with _client_on(transport) as client:
        initial = await client.fetch_recent_logs()
        assert len(initial.seaport_sales) == 1
        rows[A.TOPIC_SEAPORT_ORDER_FULFILLED][0]['transactionHash'] = '0x' + 'cd'*32
        state['head'] += 10
        calls.clear()
        updated = await client.fetch_recent_logs()
        assert all(lo == state['head']-21 for lo, _ in calls)
        assert not any(client.log_group_failed.values())
    async with _client_on(transport) as cold:
        assert updated == await cold.fetch_recent_logs()


@pytest.mark.asyncio
async def test_launchpad_reorg_rebuilds_lifetime_counters_from_pre_tail_snapshot():
    logs = _load_launchpad('full_history.json')
    head = logs['head_block']
    old = copy.deepcopy(logs['curve_swap'][0])
    old['blockNumber'] = hex(head - 5)
    old['transactionHash'] = '0x' + 'cd'*32
    old['logIndex'] = '0x0'
    old['topics'][2] = '0x' + '00'*12 + 'de'*20
    logs['curve_swap'].append(old)
    orphan_launch = copy.deepcopy(logs['launched'][-1])
    orphan_launch['blockNumber'] = hex(head-4)
    orphan_launch['topics'][1] = '0x' + 'fe'*32
    logs['launched'].append(orphan_launch)
    orphan_burn = dict(logs['imd_burned'][0], blockNumber=hex(head-2), transactionHash='0x'+'ef'*32)
    logs['imd_burned'].append(orphan_burn)
    transport = launch_transport(logs)
    async with _client_on(transport, now_fn=lambda: 1_800_000_000) as client:
        initial = await client.fetch_launchpad()
        assert initial.swap_count == 166
        logs['curve_swap'].remove(old)
        logs['launched'].remove(orphan_launch)
        logs['imd_burned'].remove(orphan_burn)
        replacement = dict(old, blockNumber=hex(head+1), transactionHash='0x'+'ac'*32,
                           topics=list(old['topics']))
        replacement['topics'][2] = '0x'+'00'*12+'fa'*20
        logs['curve_swap'].append(replacement)
        logs['head_block'] += 10
        transport.requests.clear()
        updated = await client.fetch_launchpad(resume=initial.cursor)
        log_calls = [p for _,_,p in transport.requests if isinstance(p,dict) and p['method']=='eth_getLogs']
        assert all(int(p['params'][0]['fromBlock'],16) == head-11 for p in log_calls)
    async with _client_on(launch_transport(logs), now_fn=lambda: 1_800_000_000) as cold:
        expected = await cold.fetch_launchpad()
    assert updated == expected
    assert updated.burned_total_wei < initial.burned_total_wei
    assert updated.launch_count == initial.launch_count - 1
    assert '0x'+'de'*20 not in updated.cursor['traders']


@pytest.mark.asyncio
async def test_restart_rebuilds_lifetime_history_without_trusting_unreplayable_cursor():
    logs = _load_launchpad('full_history.json')
    async with _client_on(launch_transport(logs)) as client:
        first = await client.fetch_launchpad()
    logs['head_block'] += 20  # restart after the old head is outside replay tail
    cursor = copy.deepcopy(first.cursor)
    cursor['swaps_all'] = {key: value+1000 for key,value in cursor['swaps_all'].items()}
    async with _client_on(launch_transport(logs)) as restarted:
        rebuilt = await restarted.fetch_launchpad(resume=cursor)
    assert rebuilt.swap_count == first.swap_count
    assert rebuilt.cursor['swaps_all'] == first.cursor['swaps_all']


@pytest.mark.asyncio
async def test_one_mainnet_head_per_read_cycle_across_nonces_recent_and_launchpad():
    logs = _load_launchpad('full_history.json')
    original = launch_transport(logs)
    def handle(request):
        payload = json.loads(request.content)
        if isinstance(payload,list) and all(p['method']=='eth_getTransactionCount' for p in payload):
            return httpx.Response(200, json=[_rpc_ok(p,'0x1') for p in payload])
        return original.handler(request)
    transport = RecordingTransport(handle)
    @read_cycle
    async def fetch(client):
        await client.fetch_nonces()
        await client.fetch_recent_logs()
        await client.fetch_launchpad()
    async with _client_on(transport) as client:
        await fetch(client)
    entries = [p for _,_,payload in transport.requests for p in (payload if isinstance(payload,list) else [payload])]
    assert sum(p['method']=='eth_blockNumber' for p in entries) == 1
