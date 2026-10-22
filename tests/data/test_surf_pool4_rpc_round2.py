"""POOL4 round-two optimizations; only recorded payloads and injected transports."""
from __future__ import annotations

from copy import deepcopy
import json

import httpx
import pytest

from maxpane_dashboard.data import surf_pool4 as P
from maxpane_dashboard.data.surf_pool4_client import Pool4Client
from tests.data.test_surf_pool4_client import load
from tests.data.test_surf_pool4_rpc_budget import A, CaptureRPC, PATH, POOL, client


def log_at(block, index=0, *, branch=1):
    """A captured event body relocated to a synthetic fork/window boundary."""
    row = deepcopy(load('mainnet_flow_logs')['response']['result'][0])
    row.update(blockNumber=hex(block), logIndex=hex(index),
               blockHash='0x' + format(branch * 10_000_000 + block, '064x'),
               transactionHash='0x' + format(block * 100 + index, '064x'))
    return row


def target_header(payload):
    """Explicit synthetic target header, preserving the RPC envelope."""
    assert payload['method'] == 'eth_getBlockByNumber'
    assert payload['params'][1] is False
    return httpx.Response(200, json={'jsonrpc': '2.0', 'id': payload['id'],
                                  'result': {'number': payload['params'][0]}})


@pytest.mark.parametrize('kind', ['hook', 'swap', 'drip'])
async def test_pool4_reads_only_twelve_block_overlap_and_new_tail_but_returns_full_window(kind):
    before = [log_at(1_001), log_at(2_000), log_at(3_390), log_at(3_399)]
    after = [log_at(1_001), log_at(2_000), log_at(3_390, branch=2), log_at(3_405)]
    current, ranges, proofs = before, [], []

    def handler(request):
        payload = json.loads(request.content)
        if payload['method'] == 'eth_getBlockByNumber':
            proofs.append((request.url.host, payload['params'][0]))
            return target_header(payload)
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        ranges.append((lo, hi))
        if kind == 'swap':
            assert flt['topics'] == [[P.TOPIC_SWAP, P.TOPIC_MODIFY_LIQUIDITY], POOL.lower()]
        else:
            assert 'topics' not in flt
        return httpx.Response(200, json={'id': payload['id'], 'result':
            [row for row in current if lo <= int(row['blockNumber'], 16) <= hi]})

    c = Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                    mainnet_log_rpcs=['https://first.test', 'https://second.test'],
                    inter_call_delay=0, backoff_seconds=(0, 0))
    async def read(start, end):
        if kind == 'swap':
            return await c.fetch_swap_logs(A['pool_manager'], POOL, start, end, network='MAINNET')
        address = A['dripper'] if kind == 'drip' else A['hook']
        return await c.fetch_flow_logs(address, start, end, network='MAINNET')

    assert await read(1_000, 3_399) == before
    current = after
    actual = await read(1_010, 3_409)
    assert ranges == [(1_000, 3_399), (3_388, 3_409)]
    assert proofs == [('first.test', hex(3_399)), ('first.test', hex(3_409))]
    assert actual == after[1:]
    assert all(int(row['blockNumber'], 16) != 3_399 for row in actual)
    assert len({(r['transactionHash'], r['logIndex']) for r in actual}) == len(actual)


async def test_overlapping_contract_windows_never_share_rows():
    asked = []
    def handler(request):
        payload = json.loads(request.content)
        if payload['method'] == 'eth_getBlockByNumber':
            return target_header(payload)
        flt = payload['params'][0]
        asked.append(flt)
        row = log_at(int(flt['fromBlock'], 16))
        row['address'] = flt['address']
        return httpx.Response(200, json={'id': payload['id'], 'result': [row]})
    c = Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                    mainnet_log_rpcs=['https://first.test', 'https://second.test'],
                    inter_call_delay=0, backoff_seconds=(0, 0))
    first = await c.fetch_flow_logs(A['hook'], 1_000, 3_399, network='MAINNET')
    second = await c.fetch_flow_logs(A['dripper'], 1_000, 3_409, network='MAINNET')
    assert first and second
    assert all(row['address'] == A['dripper'] for row in second)
    assert asked[1]['fromBlock'] == hex(1_000)


async def test_lagging_log_host_cannot_turn_unknown_history_into_empty():
    asked = []
    def handler(request):
        payload = json.loads(request.content)
        asked.append((request.url.host, payload['method']))
        assert payload['method'] == 'eth_getBlockByNumber'
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': payload['id'],
                                      'result': {'number': hex(3_398)}})
    c = Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                    mainnet_log_rpcs=['https://first.test', 'https://second.test'],
                    inter_call_delay=0, backoff_seconds=(0, 0))
    assert await c.fetch_flow_logs(A['hook'], 1_000, 3_399, network='MAINNET') is None
    assert asked == [('first.test', 'eth_getBlockByNumber'),
                     ('second.test', 'eth_getBlockByNumber')]


async def test_one_atomic_bundle_executes_identical_contract_calldata_only_once():
    rpc = CaptureRPC()
    got = await client(rpc).fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'],
                                               path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert got['identity_valid']
    for _host, _payload, calls in rpc.requests:
        assert len(calls) == len(set(calls)), 'identity and model aliases must share one EVM subcall'
    assert got['hook'].rewards_recipient.lower() == PATH['path'][0].lower()
    assert got['vault'].asset.lower() == A['token'].lower()


async def test_unproven_metadata_and_a_temporary_revert_are_rechecked_next_poll():
    rpc = CaptureRPC()
    c = client(rpc)
    selector = P.HOOK_SELECTORS['totalBurned']
    key = (A['hook'].lower(), selector)
    saved = rpc.table.pop(key)
    first = await c.fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'],
                                       path=PATH, pool_id=POOL, pool_manager=A['pool_manager'])
    assert first['hook'].total_burned_wei is None
    rpc.table[key] = saved
    before = len(rpc.requests)
    second = await c.fetch_state_bundle(A['hook'], network='MAINNET', token_addr=A['token'])
    assert second['hook'].total_burned_wei is not None
    calls = [call for _, _, calls in rpc.requests[before:] for call in calls]
    assert key in calls
    assert (A['vault'].lower(), P.VAULT_SELECTORS['decimals']) in calls
    assert (A['vault'].lower(), P.VAULT_SELECTORS['name']) in calls
    assert (A['vault'].lower(), P.VAULT_SELECTORS['symbol']) in calls


class TransportProbe:
    def __init__(self):
        self.events = []

    async def post(self, http_client, url, payload):
        self.events.append(('post', url))
        return await http_client.post(url, json=payload)

    async def acquire(self, url):
        self.events.append(('acquire', url))

    def observe(self, url, response):
        self.events.append(('observe', url, response.status_code))


async def test_rpc_and_docs_use_the_injected_shared_host_transport():
    from tests.data.test_surf_pool4_client import _DOCS_HTML
    scheduler = TransportProbe()
    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, content=_DOCS_HTML.encode())
        return httpx.Response(200, json={'result': '0x1'})
    c = Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                    transport=scheduler, inter_call_delay=0, backoff_seconds=(0, 0))
    response = await c._post_rpc('https://first.test', {'id': 1})
    assert response.json()['result'] == '0x1'
    assert await c.fetch_docs_page() == _DOCS_HTML
    assert scheduler.events == [('post', 'https://first.test'),
                                ('acquire', 'https://pool4.imd.fun/docs'),
                                ('observe', 'https://pool4.imd.fun/docs', 200)]


async def test_docs_429_is_observed_and_does_not_retry_the_same_host():
    scheduler, requests = TransportProbe(), []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(429, headers={'Retry-After': '30'})
    c = Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                    transport=scheduler, inter_call_delay=0, backoff_seconds=(0, 0))
    assert await c.fetch_docs_page() is None
    assert len(requests) == 1
    assert scheduler.events[-1] == ('observe', requests[0], 429)


async def test_pool4_heads_share_only_within_one_read_cycle_and_one_chain():
    import asyncio
    from maxpane_dashboard.data.surf_transport import read_cycle
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(str(request.url))
        return httpx.Response(200, json=[{'id': p['id'], 'result': '0x10'} for p in payload])
    def make():
        return Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                            mainnet_state_rpcs=['https://mainnet.test'],
                            sepolia_state_rpcs=['https://sepolia.test'], inter_call_delay=0)
    a, b = make(), make()
    @read_cycle
    async def tick():
        return await asyncio.gather(a.fetch_block_number(network='MAINNET'),
                                    b.fetch_block_number(network='MAINNET'),
                                    b.fetch_block_number(network='SEPOLIA'))
    assert await tick() == [16, 16, 16]
    assert sorted(requests) == ['https://mainnet.test', 'https://sepolia.test']
    assert await a.fetch_block_number(network='MAINNET') == 16
    assert len(requests) == 3
