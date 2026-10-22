"""Offline POOL4 state budgets, using the committed calldata captures."""
from __future__ import annotations

import json

import httpx
import pytest

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data.surf_pool4_client import Pool4Client
from tests.data.test_surf_pool4_client import answers_by_calldata, load, replay_handler

MULTICALL = '0xca11bde05977b3631167028862be2a173976ca11'
GET_BLOCK = '0x42cbb15c'
FX = ('mainnet_hook_state', 'mainnet_dripper_state', 'mainnet_vault_state',
      'mainnet_distributor_state', 'mainnet_pool_slot0', 'mainnet_vault_path')
A = load('mainnet_hook_state')['addresses']
HEAD = load('mainnet_hook_state')['block_number']
POOL = load('mainnet_pool_slot0')['pool_id']
PATH = {'path': [A['distributor'], A['dripper']], 'dripper': A['dripper'], 'vault': A['vault']}


def unpack_calls(data):
    """Decode request calldata independently of the production encoder."""
    raw = bytes.fromhex(data[10:])
    word = lambda offset: int.from_bytes(raw[offset:offset + 32], 'big')
    start = word(0)
    count, base = word(start), start + 32
    out = []
    for i in range(count):
        pos = base + word(base + i * 32)
        target = '0x' + raw[pos + 12:pos + 32].hex()
        assert word(pos + 32) == 1
        data_start = pos + word(pos + 64)
        length = word(data_start)
        out.append((target, '0x' + raw[data_start + 32:data_start + 32 + length].hex()))
    return out


def pack_results(results):
    word = lambda value: value.to_bytes(32, 'big')
    tails = []
    for success, raw in results:
        data = bytes.fromhex(raw[2:])
        tails.append(word(int(success)) + word(64) + word(len(data)) + data + bytes(-len(data) % 32))
    cursor, offsets = len(tails) * 32, []
    for tail in tails:
        offsets.append(word(cursor))
        cursor += len(tail)
    return '0x' + (word(32) + word(len(tails)) + b''.join(offsets + tails)).hex()


class CaptureRPC:
    def __init__(self, *, transient=None, corrupt_link=False, wrong_block=False):
        self.table = {}
        for name in FX:
            self.table.update(answers_by_calldata(name))
        self.transient, self.corrupt_link = transient, corrupt_link
        self.wrong_block = wrong_block
        self.requests = []

    def __call__(self, request):
        payload = json.loads(request.content)
        if isinstance(payload, list):
            self.requests.append((request.url.host, payload, []))
            results = []
            for entry in payload:
                if entry['method'] == 'eth_blockNumber':
                    raw = hex(HEAD)
                else:
                    params = entry['params'][0]
                    raw = self.table.get((params['to'].lower(), params['data'].lower()), '0x')
                results.append({'jsonrpc': '2.0', 'id': entry['id'], 'result': raw})
            return httpx.Response(200, json=results)
        assert isinstance(payload, dict), 'getter bundle must be one eth_call' 
        assert payload['method'] == 'eth_call'
        assert payload['params'][0]['to'].lower() == MULTICALL
        calls = unpack_calls(payload['params'][0]['data'])
        block = HEAD if payload['params'][1] == 'latest' else int(payload['params'][1], 16) + int(self.wrong_block)
        self.requests.append((request.url.host, payload, calls))
        values = []
        for target, data in calls:
            if (target, data) == (MULTICALL, GET_BLOCK):
                raw = '0x' + format(block, '064x')
            else:
                raw = self.table.get((target, data), '0x')
            if self.transient == data and request.url.host == 'first.test':
                values.append((False, '0x'))
                continue
            if self.corrupt_link and target == A['dripper'].lower() and data == P.DRIPPER_SELECTORS['vault']:
                raw = '0x' + '00' * 12 + '99' * 20
            values.append((raw != '0x', raw))
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': payload['id'], 'result': pack_results(values)})


def client(rpc):
    return Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(rpc)),
                       mainnet_state_rpcs=['https://first.test', 'https://second.test'],
                       inter_call_delay=0, backoff_seconds=(0, 0))


async def test_known_bundle_uses_two_calls_one_block_and_preserves_captured_values():
    rpc = CaptureRPC()
    c = client(rpc)
    got = await c.fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'],
                                     path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert got is not None and got['identity_valid'] is True
    assert len(rpc.requests) == 2
    assert rpc.requests[1][1]['params'][1] == hex(HEAD)
    for field in ('hook', 'dripper', 'vault'):
        assert got[field].block_number == HEAD
    assert got['reference']['block_number'] == HEAD
    baseline = Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(replay_handler(*FX))),
                           inter_call_delay=0, backoff_seconds=(0, 0))
    assert got['hook'] == await baseline.fetch_hook_state(A['hook'], network='MAINNET', token_addr=A['token'])
    assert got['dripper'] == await baseline.fetch_dripper_state(A['dripper'], network='MAINNET', token_addr=A['token'])
    assert got['vault'] == await baseline.fetch_vault_state(A['vault'], network='MAINNET')
    assert got['distributor'] == await baseline.fetch_distributor_state(A['distributor'], network='MAINNET')


async def test_failed_bundle_entry_retries_elsewhere_at_the_same_block():
    selector = P.HOOK_SELECTORS['totalBurned']
    rpc = CaptureRPC(transient=selector)
    got = await client(rpc).fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'],
                                               path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert got['hook'].total_burned_wei is not None
    assert len(rpc.requests) == 2
    assert rpc.requests[1][0] == 'second.test'
    assert rpc.requests[1][1]['params'][1] == hex(HEAD)
    assert (A['hook'].lower(), selector) in rpc.requests[1][2]
    assert (A['hook'].lower(), P.HOOK_SELECTORS['poolId']) not in rpc.requests[1][2]


async def test_changed_path_never_serves_previous_vault():
    rpc = CaptureRPC(corrupt_link=True)
    got = await client(rpc).fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'],
                                               path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert got is None or got['identity_valid'] is False
    if got:
        assert got['vault'] is None


async def test_warm_card_quote_costs_at_most_five_entries_per_tick():
    rpc = CaptureRPC()
    c = client(rpc)
    got = await c.fetch_card_quote(A['hook'], network='MAINNET', token_addr=A['token'],
                                    path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert got['share_price_wei'] is not None and got['tick'] is not None
    first_count = len(rpc.requests)
    again = await c.fetch_card_quote(A['hook'], network='MAINNET', token_addr=A['token'])
    assert again['share_price_wei'] == got['share_price_wei']
    assert again['tick'] == got['tick']
    assert len(rpc.requests) - first_count <= 5
    assert all(len(calls) < 15 for _, _, calls in rpc.requests)


@pytest.mark.parametrize('supply,code,want', [(0, '0x60', True), (3, '0x60', False),
                                           (None, '0x', True), (None, '0x60', None),
                                           (None, None, None)])
async def test_historical_zero_proof_is_at_exact_block_and_never_inferred_from_failure(supply, code, want):
    sent = []
    def handler(request):
        payload = json.loads(request.content)
        sent.extend(payload)
        return httpx.Response(200, json=[{'jsonrpc':'2.0','id': item['id'], 'result':
            code if item['method'] == 'eth_getCode' else (None if supply is None else '0x' + format(supply, '064x'))}
            for item in payload])
    got = await client(handler).fetch_zero_supply(A['vault'], HEAD - 1, network='MAINNET')
    assert got is want
    assert all(call['params'][-1] == hex(HEAD - 1) for call in sent)


async def test_pool4_pager_resumes_the_first_unread_page_without_replaying_prefix():
    seen, failing = [], True
    def handler(request):
        payload = json.loads(request.content)
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        seen.append((lo, hi))
        if failing and lo > 10_000:
            return httpx.Response(503, json={'error': {'code': -32005, 'message': 'rate limit exceeded'}})
        return httpx.Response(200, json={'id': payload['id'], 'result':
            [{'blockNumber': hex(lo), 'logIndex': '0x0', 'data': '0x', 'topics': []}]})
    c = client(handler)
    c._pools[('MAINNET', 'logs')] = ['https://first.test', 'https://second.test']
    assert await c.fetch_flow_logs(A['hook'], 10_000, 14_799, network='MAINNET') is None
    failing = False
    before = len(seen)
    result = await c.fetch_flow_logs(A['hook'], 10_000, 14_799, network='MAINNET')
    assert seen[before][0] == 12_400
    assert [int(row['blockNumber'], 16) for row in result] == [10_000, 12_400]
    assert seen.count((10_000, 12_399)) == 1


async def test_pool4_batch_caps_drpc_and_retries_failed_ids_only():
    sent = []
    def handler(request):
        payload = json.loads(request.content)
        sent.append((request.url.host, payload))
        assert len(payload) <= 3 if request.url.host == 'eth.drpc.org' else True
        return httpx.Response(200, json=[
            {'id': p['id'], 'error': {'code': 3, 'message': 'execution reverted'}}
            if request.url.host == 'eth.drpc.org' and p['params'] == ['failed']
            else {'id': p['id'], 'result': p['params'][0]} for p in reversed(payload)])
    c = client(handler)
    c._pools[('MAINNET', 'state')] = ['https://eth.drpc.org', 'https://second.test']
    result = await c._rpc_state_batch('MAINNET', [('eth_getCode', [value]) for value in ['a','b','c','failed','e','f','g']])
    assert result == ['a','b','c','failed','e','f','g']
    assert [p['params'] for host, payload in sent if host == 'second.test' for p in payload] == [['failed']]


async def test_cold_quote_discovers_once_then_reuses_only_revalidated_addresses():
    rpc = CaptureRPC()
    c = client(rpc)
    first = await c.fetch_card_quote(A['hook'], network='MAINNET', token_addr=A['token'])
    assert first and first['share_price_wei'] is not None
    count = len(rpc.requests)
    second = await c.fetch_card_quote(A['hook'], network='MAINNET', token_addr=A['token'])
    assert second == first
    assert len(rpc.requests) - count == 2
    assert all(isinstance(payload, dict) for _, payload, _ in rpc.requests[count:])


async def test_a_provider_ignoring_the_pinned_block_cannot_supply_the_share_price():
    rpc = CaptureRPC(wrong_block=True)
    got = await client(rpc).fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'],
                                               path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert got['identity_valid'] is True
    assert got['hook'].block_number == HEAD
    assert got['vault'].block_number == HEAD
    assert got['vault'].share_price_wei is None
