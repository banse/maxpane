#!/usr/bin/env python3
"""Count real SURF reads over fixed offline fixtures in one or two source trees.

Example (use the project interpreter, never the system Python)::

    .venv/bin/python scripts/measure_surf_rpc_budget.py \
      --baseline /private/tmp/maxpane-rpc-budget-base-adfe652e --repo . \
      --output /private/tmp/surf-rpc-budget.json

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

    def __call__(self, request):
        body = json.loads(request.content) if request.method == 'POST' else None
        self.calls.append((request.method, request.url.host + request.url.path, body))
        return self.handler(request)

    def counts(self, start=0):
        requests = entries = rest = subcalls = 0
        methods, paths = Counter(), Counter()
        for method, path, body in self.calls[start:]:
            if method == 'GET':
                rest += 1
                paths[path] += 1
                continue
            requests += 1
            for entry in body if isinstance(body, list) else [body]:
                entries += 1
                methods[entry['method']] += 1
                if entry['method'] == 'eth_call':
                    call = entry.get('params', [{}])[0]
                    if call.get('to', '').lower() == MULTICALL:
                        subcalls += len(unpack(call['data']))
        return dict(requests=requests, entries=entries, rest=rest,
                    multicall_subcalls=subcalls, methods=dict(sorted(methods.items())),
                    rest_paths=dict(sorted(paths.items())))


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
    meter = Meter(handler)
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
    rows = []
    for name, run in (
        ('pool4-known-state', lambda: known_state(rows, tmp)),
        ('launchpad', lambda: launch_history(rows)),
        ('decoy', lambda: decoy_history(rows)),
        ('stakers', lambda: stakers(rows, tmp)),
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
    hashes = {name: hashlib.sha256((production / name).read_bytes()).hexdigest()
              for name in ('surf_manager.py', 'surf_client.py', 'surf_pool4_client.py',
                           'surf_card_reader.py', 'surf_rpc_history.py', 'surf_rpc_batch.py',
                           'surf_staker_history.py') if (production / name).exists()}
    fixture_hashes = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
                      for name in sorted(LOADED_FIXTURES)}
    return dict(rows=rows, import_root=str(production.parent.parent),
                production_sha256=hashes, fixture_sha256=fixture_hashes, limitations=[
        'Deterministic counts only, not measured latency, statistical confidence, current log density or IP-rate-limit behavior.',
        'Recorded full POOL4 getters/1116 Transfer logs; launchpad and decoy corpora are pre-existing generated fixtures.',
        'Catch-up extends the fixture head at 7200 blocks/day without inventing later events: quiet-range correctness premiums are included.',
        'Historical zero supply/code is a synthetic oracle derived from the complete Transfer corpus; not a new endpoint capture.',
        'BOARDROOM runs actual discovery on a synthetic self-post naming the captured mainnet hook; no claim of live announcement provenance.',
        'Work/current swarm, NFT, Base and Robinhood paths are not covered by this command.',
        'Pool4 known-state row excludes history. POOL4/launchpad/stakers use production manager projections, not complete all-view flat dicts.',
        'Recorded CoinGecko response is unavailable: rpc_budget_measure.json labels the synthetic ETH quote; REST counts remain actual dispatches.',
        'No arbitrary Tenderly span cap is invented: the supplied 403200-block success does not prove a maximum.',
    ])


def table(before, after):
    prior = {row['scenario']: row for row in before['rows']} if before else {}
    lines = ['| Scenario | RPC requests before → after | Entries before → after | REST before → after | Projection equal |',
             '|---|---:|---:|---:|---|']
    for row in after['rows']:
        old = prior.get(row['scenario'])
        def cell(key):
            return f"{old['counts'][key] if old else '—'} → {row['counts'][key]}"
        equal = str(old['projection'] == row['projection']).lower() if old else '—'
        lines.append(f"| {row['scenario']} | {cell('requests')} | {cell('entries')} | {cell('rest')} | {equal} |")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path)
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
    print(table(before, after))
    for note in after['limitations']:
        print('- ' + note)


if __name__ == '__main__':
    main()
