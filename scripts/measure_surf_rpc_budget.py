#!/usr/bin/env python3
"""Count real SURF reads over fixed offline fixtures in one or two source trees.

Example (use the project interpreter, never the system Python)::

    .venv/bin/python scripts/measure_surf_rpc_budget.py \
      --baseline /private/tmp/maxpane-rpc-budget-r1-a02d9b50 --repo . \
      --output /private/tmp/surf-rpc-budget-r2-measured.json

This is a deterministic request-count replay, NOT a latency benchmark or a
claim about current chain density. No request can reach a network transport.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict, is_dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures/surf'
MULTICALL = '0xca11bde05977b3631167028862be2a173976ca11'
GET_BLOCK = '0x42cbb15c'
STATE_FIXTURES = ('mainnet_hook_state', 'mainnet_dripper_state', 'mainnet_vault_state',
                  'mainnet_distributor_state', 'mainnet_pool_slot0', 'mainnet_vault_path')
LOADED_FIXTURES = set()


def load(relative):
    LOADED_FIXTURES.add(relative)
    return json.loads((FIXTURES / relative).read_text())


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True).encode()).hexdigest()


def unpack(data):
    """Use the existing independent test ABI codec, not the client encoder."""
    from tests.data.test_surf_client import decode_aggregate3_calldata
    return [(target, data) for target, _allow, data in decode_aggregate3_calldata(data)]


def pack(results):
    from tests.data.test_surf_client import encode_aggregate3_result
    return encode_aggregate3_result(results)


class Meter:
    """Observe each actual HTTP dispatch, including failures and confirmations."""
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.responses = []

    def __call__(self, request):
        body = json.loads(request.content) if request.method == 'POST' else None
        self.calls.append((request.method, request.url.host + request.url.path, body))
        response = self.handler(request)
        try:
            self.responses.append(response.json())
        except ValueError:
            self.responses.append(None)
        return response

    def counts(self, start=0):
        requests = entries = rest = subcalls = 0
        requested_blocks = returned_rows = 0
        methods, paths = Counter(), Counter()
        for (method, path, body), response in zip(self.calls[start:], self.responses[start:]):
            if method == 'GET':
                rest += 1
                paths[path] += 1
                continue
            requests += 1
            for entry in body if isinstance(body, list) else [body]:
                entries += 1
                methods[entry['method']] += 1
                if entry['method'] == 'eth_getLogs':
                    flt = entry['params'][0]
                    requested_blocks += int(flt['toBlock'], 16) - int(flt['fromBlock'], 16) + 1
                    replies = response if isinstance(response, list) else [response]
                    for reply in replies:
                        if isinstance(reply, dict) and reply.get('id') == entry.get('id'):
                            result = reply.get('result')
                            if isinstance(result, list):
                                returned_rows += len(result)
                if entry['method'] == 'eth_call':
                    call = entry.get('params', [{}])[0]
                    if call.get('to', '').lower() == MULTICALL:
                        subcalls += len(unpack(call['data']))
        return dict(requests=requests, entries=entries, rest=rest,
                    log_requested_blocks=requested_blocks, log_returned_rows=returned_rows,
                    multicall_subcalls=subcalls, methods=dict(sorted(methods.items())),
                    rest_paths=dict(sorted(paths.items())))


def synthetic_header(entry, head):
    """Replay chain oracle, not a captured header or proof about a live host."""
    block = int(entry['params'][0], 16)
    if not 0 <= block <= head:
        return None
    return dict(number=hex(block), timestamp=hex(1_700_000_000 + block * 12))


def with_target_headers(handler, head):
    """Provide the same explicit proof fixture to both selected code trees."""
    def wrapped(request):
        import httpx
        entry = json.loads(request.content)
        if (isinstance(entry, dict) and entry.get('method') == 'eth_getBlockByNumber'
                and str(entry.get('id', '')).startswith('surf-block-')):
            return httpx.Response(200, json=dict(jsonrpc='2.0', id=entry['id'],
                                               result=synthetic_header(entry, head())))
        return handler(request)
    return wrapped


class PoolReplay:
    def __init__(self):
        self.table = {}
        for name in STATE_FIXTURES:
            request = load(f'pool4/{name}.request.json')['body']
            response = load(f'pool4/{name}.json')['response']
            by_id = {entry['id']: entry for entry in response if isinstance(entry, dict)}
            for entry in request if isinstance(request, list) else [request]:
                call = entry['params'][0]
                self.table[(call['to'].lower(), call['data'].lower())] = by_id.get(entry['id'], {})
        self.fixture = load('pool4/mainnet_hook_state.json')
        self.head = self.fixture['block_number']
        self.addresses = self.fixture['addresses']
        self.pool_id = load('pool4/mainnet_pool_slot0.json')['pool_id']
        self.path = dict(path=[self.addresses['distributor'], self.addresses['dripper']],
                         dripper=self.addresses['dripper'], vault=self.addresses['vault'])
        self.transfers = load('pool4/simd_transfers_full.json')
        self.logs = []

    def _value(self, target, data, block):
        if target == MULTICALL and data == GET_BLOCK:
            return '0x' + format(block, '064x')
        return self.table.get((target, data), {}).get('result')

    def _answer(self, entry, host):
        method, params = entry['method'], entry.get('params', [])
        if method == 'eth_blockNumber':
            return {'result': hex(self.head)}
        if method == 'eth_getBlockByNumber':
            return {'result': synthetic_header(entry, self.head)}
        if method == 'eth_getCode':
            # Synthetic historical state oracle derived from the complete
            # transfer corpus; deliberately NOT claimed as a captured RPC.
            block = int(params[1], 16)
            return {'result': '0x' if block < self.transfers['first_log_block'] else '0x6000'}
        if method == 'eth_getLogs':
            flt = params[0]
            lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
            rows = [row for row in self.logs if lo <= int(row['blockNumber'], 16) <= hi
                    and row['address'].lower() == flt['address'].lower()]
            return capped_logs(host, lo, hi, rows)
        if method == 'eth_call':
            call = params[0]
            target, data = call['to'].lower(), call['data'].lower()
            block = self.head if params[-1] == 'latest' else int(params[-1], 16)
            if target == MULTICALL:
                values = [(self._value(t, d, block)) for t, d in unpack(data)]
                return {'result': pack([(v is not None and v != '0x', v or '0x') for v in values])}
            if self.logs and target == self.addresses['vault'].lower() and data == '0x18160ddd':
                zero = '0x' + '0' * 64
                supply = sum((1 if row['topics'][1] == zero else -1 if row['topics'][2] == zero else 0)
                             * int(row['data'], 16) for row in self.logs
                             if int(row['blockNumber'], 16) <= block)
                return {'result': '0x' + format(supply, '064x')}
            answer = self.table.get((target, data))
            return answer or {'result': '0x'}
        raise AssertionError(f'unrecorded POOL4 method: {method}')

    def __call__(self, request):
        import httpx
        payload = json.loads(request.content)
        entries = payload if isinstance(payload, list) else [payload]
        if request.url.host == 'eth.drpc.org' and len(entries) > 3:
            return httpx.Response(500, json={'error': {'message': 'Batch of more than 3 requests are not allowed'}})
        body = [dict(self._answer(entry, request.url.host), jsonrpc='2.0', id=entry['id']) for entry in entries]
        return httpx.Response(200, json=body if isinstance(payload, list) else body[0])


def capped_logs(host, lo, hi, rows):
    """Apply only capture-supported refusals; sparse MEV ranges may be wide."""
    cases = load('rpc_budget_errors.json')['cases']
    for key, span in (('thirdweb_range', 1000), ('nodies_range', 50)):
        capture = cases[key]
        if host == capture['host'] and hi - lo + 1 > span:
            return {'error': capture['body']['error']}
    if 'mevblocker' in host and hi - lo + 1 > 10_000 and len(rows) > 10_000:
        return {'error': cases['mevblocker_range']['body']['error']}
    return {'result': rows}


def pool_client(meter):
    import httpx
    from maxpane_dashboard.data.surf_pool4_client import Pool4Client
    return Pool4Client(http_client=httpx.AsyncClient(transport=httpx.MockTransport(meter)),
                       inter_call_delay=0, backoff_seconds=(0, 0))


class UnusedClient:
    async def close(self):
        pass

    def __getattr__(self, name):
        raise AssertionError(f'unmeasured source was used: {name}')


def manager(tmp, clock, client, pool):
    from maxpane_dashboard.data.surf_manager import SurfManager
    tmp.mkdir(parents=True, exist_ok=True)
    return SurfManager(client=client, pool4_client=pool, swarm_client=UnusedClient(),
                       npm_client=UnusedClient(), earnings_client=UnusedClient(),
                       launch_rpc_clients={}, clock=lambda: clock.now,
                       cache_path=str(tmp / 'not-a-user-cache.json'))


def record(rows, scenario, meter, value, start=0, **details):
    projection = plain(value)
    rows.append(dict(scenario=scenario, counts=meter.counts(start), projection=projection,
                     projection_digest=digest(projection), **details))


async def known_state(rows, tmp):
    from maxpane_dashboard.data.surf_manager import POOL4_ADOPTED
    from maxpane_dashboard.data.surf_models import Pool4Discovery
    rpc = PoolReplay()
    meter = Meter(rpc)
    client = pool_client(meter)
    clock = SimpleNamespace(now=2_000_000_000.)
    m = manager(tmp, clock, UnusedClient(), client)
    a = rpc.addresses
    try:
        if hasattr(client, 'fetch_state_bundle'):
            state = await client.fetch_state_bundle(a['hook'], network='MAINNET', token_addr=a['token'],
                path=rpc.path, pool_id=rpc.pool_id, pool_manager=a['pool_manager'])
            projection = {key: state[key] for key in ('hook', 'vault', 'dripper', 'distributor', 'reference')}
        else:
            projection = dict(
                hook=await client.fetch_hook_state(a['hook'], network='MAINNET', token_addr=a['token']),
                vault=await client.fetch_vault_state(a['vault'], network='MAINNET'),
                dripper=await client.fetch_dripper_state(a['dripper'], network='MAINNET', token_addr=a['token']),
                distributor=await client.fetch_distributor_state(a['distributor'], network='MAINNET'),
                reference=await client.fetch_reference_slot0(rpc.pool_id, network='MAINNET', pool_manager=a['pool_manager']))
        slot = m._pool4_payload(discovery=Pool4Discovery(network='MAINNET', state=POOL4_ADOPTED,
            hook_addr=a['hook'], detail='offline fixture'),
            network='MAINNET', hook_addr=a['hook'], token_addr=a['token'],
            dripper_addr=a['dripper'], vault_addr=a['vault'], distributor_addr=a['distributor'],
            path=rpc.path, logs=None, **projection)
        record(rows, 'pool4-known-state', meter, m._pool4_keys(slot, None, clock.now),
               scope='Known-address state getters only; discovery and history measured separately or excluded.')
    finally:
        await m.close()


async def launch_history(rows):
    import httpx
    from tests.data.test_surf_client import _client_on, _launchpad_fixture_handler
    from maxpane_dashboard.data.surf_manager import SurfManager
    raw = load('launchpad/full_history.json')
    handler = _launchpad_fixture_handler(load('launchpad/launchpad_reads.json'), raw, {})
    meter = Meter(with_target_headers(handler, lambda: raw['head_block']))
    client = _client_on(httpx.MockTransport(meter), now_fn=lambda: 2_000_000_000.)
    state = None
    try:
        for name, delta in (('cold', 0), ('steady', 2), ('day', 7_200), ('week', 50_400)):
            raw['head_block'] += delta
            begin = len(meter.calls)
            state = await client.fetch_launchpad(resume=state.cursor if state else None)
            slot = SurfManager._launchpad_payload(None, None, None, state)
            # This is the production manager's complete launchpad projection;
            # unrelated other dashboard keys are not manufactured for comparison.
            projection = SurfManager._launchpad_keys(SurfManager.__new__(SurfManager), slot, None, eth_usd=None)
            record(rows, f'launchpad/{name}', meter, projection, begin,
                   head=raw['head_block'], complete=state.launch_count is not None)
    finally:
        await client.close()


async def decoy_history(rows):
    import httpx
    from tests.data.test_surf_client import _client_on
    fixture = load('launchpad/v4_initializes.json')['rows']
    head = max(int(row['blockNumber'], 16) for row in fixture) + 1
    real = fixture[0]['topics'][1]
    def handler(request):
        entry = json.loads(request.content)
        if entry['method'] == 'eth_blockNumber':
            result = {'result': hex(head)}
        elif entry['method'] == 'eth_getBlockByNumber':
            result = {'result': synthetic_header(entry, head)}
        else:
            assert entry['method'] == 'eth_getLogs'
            f = entry['params'][0]
            lo, hi = int(f['fromBlock'], 16), int(f['toBlock'], 16)
            result = capped_logs(request.url.host, lo, hi,
                [r for r in fixture if lo <= int(r['blockNumber'], 16) <= hi])
        return httpx.Response(200, json=dict(result, jsonrpc='2.0', id=entry['id']))
    meter = Meter(handler)
    client = _client_on(httpx.MockTransport(meter))
    try:
        for name, delta in (('cold', 0), ('steady', 2), ('day', 7_200), ('week', 50_400)):
            head += delta
            begin = len(meter.calls)
            result = await client.fetch_decoy_pool_count(real_pool_id=real)
            record(rows, f'decoy/{name}', meter, result, begin, head=head)
    finally:
        await client.close()


async def stakers(rows, tmp):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4, SLOT_POOL4_STAKERS, TIER_POOL4_STAKERS
    rpc = PoolReplay()
    fx = rpc.transfers
    rpc.head, rpc.logs = fx['head_block'], fx['response']['result']
    meter = Meter(rpc)
    client = pool_client(meter)
    clock = SimpleNamespace(now=2_000_000_000.)
    tmp = tmp / 'stakers'
    m = manager(tmp, clock, UnusedClient(), client)
    pool_slot = dict(network='MAINNET', vault_addr=fx['addresses']['vault'],
        vault_decimals=fx['share_decimals'], share_price_wei=fx['share_price_wei_per_whole_share'])
    m.cache.store_last_good(SLOT_POOL4, pool_slot, ts=clock.now)
    try:
        for name, delta in (('cold', 0), ('steady', 150), ('day', 7_200), ('week', 50_400)):
            rpc.head += delta
            clock.now += delta * 12
            begin = len(meter.calls)
            value = await m._pool_pool4_stakers({TIER_POOL4_STAKERS}, clock.now)
            slot = m.cache.get_last_good(SLOT_POOL4_STAKERS)
            projection = m._pool4_stakers_keys(getattr(slot, 'payload', None) or {}, None)
            record(rows, f'stakers/{name}', meter, projection, begin,
                   head=rpc.head, complete=bool(value and value.get('complete')))
        await m.close()
        rpc.head += 150
        clock.now += 1800
        m = manager(tmp, clock, UnusedClient(), pool_client(meter))
        begin = len(meter.calls)
        value = await m._pool_pool4_stakers({TIER_POOL4_STAKERS}, clock.now)
        slot = m.cache.get_last_good(SLOT_POOL4_STAKERS)
        record(rows, 'stakers/reloaded', meter,
               m._pool4_stakers_keys(getattr(slot, 'payload', None) or {}, None), begin,
               head=rpc.head, complete=bool(value and value.get('complete')))
        await m.close()
        # A new process past the old eight-week window: no saved cursor helps.
        rpc.head = fx['first_log_block'] + 403_200
        m = manager(tmp / 'later-cold', clock, UnusedClient(), pool_client(meter))
        m.cache.store_last_good(SLOT_POOL4, pool_slot, ts=clock.now)
        begin = len(meter.calls)
        value = await m._pool_pool4_stakers({TIER_POOL4_STAKERS}, clock.now)
        slot = m.cache.get_last_good(SLOT_POOL4_STAKERS)
        record(rows, 'stakers/lifetime-late', meter,
               m._pool4_stakers_keys(getattr(slot, 'payload', None) or {}, None), begin,
               head=rpc.head, complete=bool(value and value.get('complete')))
    finally:
        await m.close()


class LogReplay:
    """Complete recorded/synthetic corpus, exact range and positional topics."""
    def __init__(self, head, logs):
        self.head, self.logs = head, logs

    def __call__(self, request):
        import httpx
        from tests.data.test_surf_client import _topics_match
        entry = json.loads(request.content)
        method = entry['method']
        if method == 'eth_blockNumber':
            result = {'result': hex(self.head)}
        elif method == 'eth_getBlockByNumber':
            result = {'result': synthetic_header(entry, self.head)}
        else:
            assert method == 'eth_getLogs', method
            flt = entry['params'][0]
            lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
            result = capped_logs(request.url.host, lo, hi, [row for row in self.logs
                if lo <= int(row['blockNumber'], 16) <= hi
                and row['address'].lower() == flt['address'].lower()
                and _topics_match(row['topics'], flt.get('topics', []))])
        return httpx.Response(200, json=dict(result, jsonrpc='2.0', id=entry['id']))


async def pool_rolling(rows):
    """Each family has an independent cache, matching one real log consumer."""
    for family, source in (('hook', 'mainnet_flow_logs'), ('swaps', 'mainnet_flow_swaps'),
                           ('drip', 'dripped_logs_7d')):
        fixture = load(f'pool4/{source}.json')
        logs = fixture['response']['result']
        rpc = LogReplay(fixture['to_block'], logs)
        width = fixture['to_block'] - fixture['from_block']
        meter = Meter(rpc)
        client = pool_client(meter)
        try:
            for phase, delta in (('cold', 0), ('steady', 2), ('day', 7_200), ('week', 50_400)):
                rpc.head += delta
                lo = rpc.head - width
                begin = len(meter.calls)
                if family == 'swaps':
                    value = await client.fetch_swap_logs(fixture['pool_manager'], fixture['pool_id'],
                                                         lo, rpc.head, network='MAINNET')
                else:
                    address = fixture['hook' if family == 'hook' else 'dripper']
                    value = await client.fetch_flow_logs(address, lo, rpc.head, network='MAINNET')
                expected = [row for row in logs if lo <= int(row['blockNumber'], 16) <= rpc.head]
                record(rows, f'pool4-{family}/{phase}', meter, value, begin,
                       head=rpc.head, complete=value is not None, expected_projection=expected,
                       expected_rows=len(expected), fixture=f'pool4/{source}.json',
                       scope='Complete raw production log-window result; not the entire POOL4 manager flat dict.')
        finally:
            await client.close()


async def recent_rolling(rows):
    import httpx
    from tests.data.test_surf_client import _client_on
    from maxpane_dashboard.data import surf_addresses as A
    fixture = load('rpc_budget_measure_recent.json')
    rpc = LogReplay(fixture['head_block'], fixture['rows'])
    meter = Meter(rpc)
    client = _client_on(httpx.MockTransport(meter))
    try:
        for phase, delta in (('cold', 0), ('steady', 2), ('day', 7_200), ('week', 50_400)):
            rpc.head += delta
            begin = len(meter.calls)
            value = await client.fetch_recent_logs()
            lo = rpc.head - client._log_window_blocks
            expected = dict(from_block=lo, to_block=rpc.head, bridge_mints=[],
                            identity_updates=[], v4_initializes=[], seaport_sales=[])
            for log in fixture['rows']:
                if not lo <= int(log['blockNumber'], 16) <= rpc.head:
                    continue
                topic = log['topics'][0]
                if topic == A.TOPIC_TRANSFER:
                    expected['bridge_mints'].append(log)
                elif topic == A.TOPIC_IDENTITY_HASH_UPDATED:
                    expected['identity_updates'].append(log)
                elif topic == A.TOPIC_V4_INITIALIZE:
                    expected['v4_initializes'].append(log)
                elif A.IDMD_NFT[2:].lower() in log['data'].lower():
                    expected['seaport_sales'].append(log)
            record(rows, f'recent/{phase}', meter, value, begin, head=rpc.head,
                   complete=value is not None and not any(client.log_group_failed.values()),
                   expected_projection=expected, expected_rows=sum(len(expected[k]) for k in
                       ('bridge_mints', 'identity_updates', 'v4_initializes', 'seaport_sales')),
                   scope='Actual recent-window API, complete explicitly synthetic corpus; no live-density claim.')
    finally:
        await client.close()


class NftReplay:
    """Stable synthetic ERC-721 wire, shared by baseline and candidate runs."""
    def __init__(self, chain=1):
        self.chain = chain

    def value(self, method, params):
        if method == 'eth_chainId':
            return hex(self.chain)
        if method == 'eth_blockNumber':
            return '0x100'
        if method == 'eth_getBlockByNumber':
            return ({'number': params[0], 'timestamp': '0x65000000'}
                    if int(params[0], 16) <= 256 else None)
        if method == 'eth_getCode':
            return '0x6000'
        if method == 'eth_getTransactionReceipt':
            return dict(status='0x1', blockNumber='0x90', transactionHash='0x' + '34' * 32)
        assert method == 'eth_call', method
        data = params[0]['data']
        value = int(data[10:18] in ('01ffc9a7', '80ac58cd')) if data.startswith('0x01ffc9a7') else int(data == '0x18160ddd')
        return '0x' + format(value, '064x')

    def __call__(self, request):
        import httpx
        if request.method == 'GET':
            return httpx.Response(200, json={})
        payload = json.loads(request.content)
        entries = payload if isinstance(payload, list) else [payload]
        replies = [dict(jsonrpc='2.0', id=entry['id'], result=self.value(entry['method'], entry['params']))
                   for entry in entries]
        return httpx.Response(200, json=list(reversed(replies)) if isinstance(payload, list) else replies[0])


async def nft_reads(rows):
    import httpx
    from copy import deepcopy
    from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector
    from maxpane_dashboard.data.surf_nft_client import Budget, SurfNftClient
    from maxpane_dashboard.data.surf_nft_manager import SurfNftManager
    load('rpc_budget_measure.json')  # Explicit provenance for this synthetic wire.
    now = SimpleNamespace(value=1_792_200_000.)
    candidate = dict(chainId=1, address='0x' + '12' * 20,
                     artifact=dict(name='NFT', txHash='0x' + '34' * 32), launch={})
    def client(meter):
        return SurfNftClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(meter)),
                             clock=lambda: now.value, monotonic=lambda: 1., inter_call_delay=0)
    for chain in (1, 4663):
        meter = Meter(NftReplay(chain))
        nft = client(meter)
        try:
            result = await SurfNftInspector(nft, clock=lambda: now.value).advance(
                dict(candidate, chainId=chain), budget=Budget(monotonic=lambda: 1., http_limit=80))
            record(rows, f'nft/full-{chain}', meter, result.evidence, complete=result.complete,
                   scope='Full inspector result over synthetic ERC-721, not a recorded public chain capture.')
        finally:
            await nft.close()
    class Cache:
        def load(self):
            return dict(records=None, discovery={}, evidence={}, progress={}, child_candidates={})
        def save(self, state, **kwargs):
            return True
    meter = Meter(NftReplay())
    nft = client(meter)
    m = SurfNftManager(swarm=SimpleNamespace(), client=nft, cache=Cache(),
                       clock=lambda: now.value, monotonic=lambda: 1.)
    identity = '1:' + candidate['address']
    m._candidates = lambda: {identity: candidate}
    async def discovered(*args, **kwargs):
        return None
    m._discover = discovered
    try:
        for phase, delta in (('cold', 0), ('repeat', 601)):
            now.value += delta
            begin = len(meter.calls)
            await m._cycle(proof_only=True)
            evidence = deepcopy(m.state['evidence'].get(identity, {}))
            # Cache revision and observation time are expected to differ when
            # immutable proof is reused. Preserve both beside the comparable
            # public proof rather than silently claiming whole-state equality.
            metadata = {key: evidence.pop(key) for key in list(evidence)
                        if key.startswith('_') or key == 'checkedAt'}
            record(rows, f'nft/proof-{phase}', meter, evidence, begin,
                   complete=evidence.get('deploymentConfirmed') is True,
                   excluded_observation_metadata=metadata,
                   scope='Actual proof-only manager cycle; discovery excluded, public proof compared without internal revision/checkedAt.')
    finally:
        await nft.close()


async def boardroom(rows, tmp):
    import httpx
    from unittest.mock import AsyncMock
    from tests.data.test_surf_client import _client_on, _market_handler
    from maxpane_dashboard.data import surf_addresses as A
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4, SLOT_LAUNCHPAD, SLOT_CHANNEL
    rpc = PoolReplay()
    market = _market_handler()
    scenario = load('rpc_budget_measure.json')
    channel = load('client/announce_txs_page1.json')
    channel['items'][0]['raw_input'] = '0x' + scenario['channel_text'].encode().hex()
    def handler(request):
        if request.method == 'POST':
            return rpc(request)
        if 'blockscout' in request.url.host:
            return httpx.Response(200, json=channel)
        if request.url.host == 'api.coingecko.com':
            return httpx.Response(200, json=scenario['eth_quote'])
        return market(request)
    meter = Meter(handler)
    surf = _client_on(httpx.MockTransport(meter))
    pool = pool_client(meter)
    clock = SimpleNamespace(now=2_000_000_000.)
    m = manager(tmp, clock, surf, pool)
    # Same synthetic announcement on both trees; the real discovery/getter
    # gate and its cache execute. This is not evidence of a live self-post.
    parsed = [surf._parse_channel_tx(row) for row in channel['items']]
    m.cache.store_last_good(SLOT_CHANNEL, m._channel_payload(parsed, None), ts=clock.now)
    m.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET', hook_addr=rpc.addresses['hook'],
        vault_addr=rpc.addresses['vault'], dripper_addr=rpc.addresses['dripper'],
        distributor_addr=rpc.addresses['distributor'], path=rpc.path,
        pool_id=rpc.pool_id, pool_manager=rpc.addresses['pool_manager']), ts=clock.now)
    m.cache.store_last_good(SLOT_LAUNCHPAD, dict(pool_id=A.POOL_V4_ID_FALLBACK), ts=clock.now)
    reader = m._card_reader
    reader._work = AsyncMock()
    reader._current = AsyncMock()
    try:
        reader.offer()
        await reader.wait_pending()
        record(rows, 'boardroom/cold', meter, reader.pool_snapshot(),
               scope='POOL4 card, actual discovery and medium REST sources; no swarm/NFT collectors.')
        begin = len(meter.calls)
        for _ in range(2):
            clock.now += 30
            reader.offer()
            await reader.wait_pending()
        record(rows, 'boardroom/steady-minute', meter, reader.pool_snapshot(), begin)
        begin = len(meter.calls)
        for _ in range(2):
            clock.now += 30
            reader.offer()
            await reader.wait_pending()
        record(rows, 'boardroom/revalidation-minute', meter, reader.pool_snapshot(), begin)
        clock.now += 30
        reader.offer()
        await reader.wait_pending()
        record(rows, 'boardroom/180s', meter, reader.pool_snapshot(),
               scope='Six polls t=0,30,60,90,120,150; half-open 180 second interval.')
    finally:
        await m.close()


async def measure(tmp, only=None):
    from maxpane_dashboard.data import surf_manager
    LOADED_FIXTURES.clear()
    load('rpc_budget_measure.json')
    rows = []
    for name, run in (
        ('pool4-known-state', lambda: known_state(rows, tmp)),
        ('launchpad', lambda: launch_history(rows)),
        ('decoy', lambda: decoy_history(rows)),
        ('stakers', lambda: stakers(rows, tmp)),
        ('pool4-rolling', lambda: pool_rolling(rows)),
        ('recent-rolling', lambda: recent_rolling(rows)),
        ('nft', lambda: nft_reads(rows)),
        ('boardroom', lambda: boardroom(rows, tmp)),
    ):
        if only is None or name in only:
            await run()
    production = Path(surf_manager.__file__).parent
    # Existing test helpers load these from their selected source tree. Refuse
    # a comparison if their corpus differs, instead of attributing input drift
    # to a production optimization.
    helper_fixtures = []
    if only is None or 'launchpad' in only:
        helper_fixtures.append('launchpad/volume_headers.json')
    if only is None or 'boardroom' in only:
        helper_fixtures.extend(('client/dexscreener_imd.json', 'client/dexscreener_fp.json',
                                'market_loading/gecko_pool.json'))
    for name in helper_fixtures:
        selected = production.parent.parent / 'tests/fixtures/surf' / name
        if selected.read_bytes() != (FIXTURES / name).read_bytes():
            raise ValueError(f'helper fixture differs between source trees: {name}')
        LOADED_FIXTURES.add(name)
    # Fingerprint every SURF data module, including cache/models and indirect
    # readers; the scenario list still defines the actual measured scope.
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(production.glob('surf*.py'))}
    fixture_hashes = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
                      for name in sorted(LOADED_FIXTURES)}
    capture = Path(__file__).resolve().parents[1] / 'docs/codex_surf_rpc_budget_captures-2026-10-22.json'
    return dict(rows=rows, import_root=str(production.parent.parent),
                harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                reference_sha256={str(capture.relative_to(capture.parent.parent)):
                                  hashlib.sha256(capture.read_bytes()).hexdigest()},
                helper_sha256={'tests/data/test_surf_client.py': hashlib.sha256(
                    (production.parent.parent / 'tests/data/test_surf_client.py').read_bytes()).hexdigest()},
                production_sha256=hashes, fixture_sha256=fixture_hashes, limitations=[
        'Deterministic counts only, not measured latency, statistical confidence, current log density or IP-rate-limit behavior.',
        'Recorded full POOL4 getters, 1116 Transfer logs, 74 hook logs, 24 swaps and 323 drips; launchpad/decoy corpora are pre-existing generated fixtures.',
        'Recent-log and NFT wires are explicitly synthetic complete scenarios, not public chain captures; header proof oracle only answers at or below replay head.',
        'Requested log blocks sum every attempted filter range including failures and independent confirmations; returned rows count wire deliveries, not unique events.',
        'Catch-up extends the fixture head at 7200 blocks/day without inventing later events: quiet-range correctness premiums are included.',
        'Historical zero supply/code is a synthetic oracle derived from the complete Transfer corpus; not a new endpoint capture.',
        'BOARDROOM runs actual discovery on a synthetic self-post naming the captured mainnet hook; no claim of live announcement provenance.',
        'Work/current swarm and Base/Robinhood archive paths are not covered; Robinhood NFT uses synthetic scalar transport only.',
        'Pool4 known-state row excludes history. POOL4/launchpad/stakers use production manager projections, not complete all-view flat dicts.',
        'Recorded CoinGecko response is unavailable: rpc_budget_measure.json labels the synthetic ETH quote; REST counts remain actual dispatches.',
        'No arbitrary Tenderly span cap is invented: the supplied 403200-block success does not prove a maximum.',
    ])


def table(before, after):
    prior = {row['scenario']: row for row in before['rows']} if before else {}
    lines = ['| Scenario | RPC requests before → after | Entries before → after | REST before → after | Log blocks before → after | Wire rows before → after | Projection equal |',
             '|---|---:|---:|---:|---:|---:|---|']
    for row in after['rows']:
        old = prior.get(row['scenario'])
        def cell(key):
            return f"{old['counts'][key] if old else '—'} → {row['counts'][key]}"
        equal = str(old['projection'] == row['projection']).lower() if old else '—'
        lines.append(f"| {row['scenario']} | {cell('requests')} | {cell('entries')} | {cell('rest')} | {cell('log_requested_blocks')} | {cell('log_returned_rows')} | {equal} |")
    return '\n'.join(lines)


def compact_report(report):
    """Keep measured counts/hashes and explicit failures without large logs."""
    from copy import deepcopy
    output = deepcopy(report)
    before, after = report.get('before'), report['after']
    prior = {row['scenario']: row for row in before['rows']} if before else {}
    output['checks'] = dict(
        same_fixtures=before['fixture_sha256'] == after['fixture_sha256'] if before else None,
        same_harness=before['harness_sha256'] == after['harness_sha256'] if before else None,
        projection_mismatches=[row['scenario'] for row in after['rows']
            if row['scenario'] in prior and row['projection'] != prior[row['scenario']]['projection']],
        incomplete_after=[row['scenario'] for row in after['rows'] if row.get('complete') is False],
        fixture_projection_mismatches=[row['scenario'] for row in after['rows']
            if 'expected_projection' in row and row['projection'] != row['expected_projection']])
    for run in (output.get('before'), output['after']):
        if run:
            for row in run['rows']:
                row.pop('projection', None)
                expected = row.pop('expected_projection', None)
                if expected is not None:
                    row['expected_projection_digest'] = digest(expected)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--summary-output', type=Path,
                        help='Write counts, hashes and equality checks without large fixture projections.')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, str(args.repo.resolve()))
        with tempfile.TemporaryDirectory(prefix='surf-rpc-measure-') as tmp:
            print(json.dumps(asyncio.run(measure(Path(tmp))), sort_keys=True))
        return
    def run(repo):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--repo', str(repo.resolve())],
                                cwd=repo, text=True, capture_output=True)
        if result.returncode:
            raise SystemExit(result.stderr)
        return json.loads(result.stdout)
    before = run(args.baseline) if args.baseline else None
    after = run(args.repo)
    report = dict(baseline=str(args.baseline.resolve()) if args.baseline else None,
                  repo=str(args.repo.resolve()), before=before, after=after)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    if args.summary_output:
        args.summary_output.write_text(json.dumps(compact_report(report), indent=2, sort_keys=True) + '\n')
    print(table(before, after))
    for note in after['limitations']:
        print('- ' + note)


if __name__ == '__main__':
    main()
