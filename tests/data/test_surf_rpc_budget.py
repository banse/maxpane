"""Offline history and state budget regressions using the committed launch logs."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.surf_client import SurfClient
from maxpane_dashboard.data.surf_rpc_history import RpcHistoryReader
from maxpane_dashboard.data.surf_rpc_batch import read_state_batch
from tests.data.test_surf_client import (
    _client_on, _launchpad_fixture_handler, _load_launchpad, _rpc_ok,
    RecordingTransport,
)

ENDPOINTS = ('https://primary.example', 'https://fallback.example')
FILTER = {'address': A.LAUNCHPAD_FACTORY, 'topics': [A.TOPIC_LAUNCHED]}
HISTORY = _load_launchpad('full_history.json')
ROW = HISTORY['launched'][0]


def reader(handler, **kwargs):
    calls = []

    async def post(url, payload):
        calls.append((url, payload))
        return handler(url, payload)

    return RpcHistoryReader(post, **kwargs), calls


@pytest.mark.asyncio
async def test_empty_primary_is_confirmed_and_nonempty_alternate_wins():
    def handler(url, payload):
        return httpx.Response(200, json=_rpc_ok(payload, [] if url == ENDPOINTS[0] else [ROW]))

    history, calls = reader(handler)
    assert await history.read(ENDPOINTS, FILTER, 100, 199, group='launched') == [ROW]
    assert [url for url, _ in calls] == list(ENDPOINTS)


@pytest.mark.asyncio
@pytest.mark.parametrize('second', ['empty', 'outage', 'same_host'])
async def test_an_empty_page_requires_two_independent_hosts(second):
    def handler(url, payload):
        if second == 'outage' and url == ENDPOINTS[1]:
            return httpx.Response(503)
        return httpx.Response(200, json=_rpc_ok(payload, []))

    history, calls = reader(handler)
    endpoints = ENDPOINTS if second != 'same_host' else (ENDPOINTS[0], ENDPOINTS[0] + '/alternate')
    result = await history.read(endpoints, FILTER, 100, 199, group='launched')
    assert result == ([] if second == 'empty' else None)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_failed_history_resumes_first_unread_page_as_head_grows():
    failing = True

    def handler(url, payload):
        start = int(payload['params'][0]['fromBlock'], 16)
        if failing and start >= 2400:
            return httpx.Response(503)
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(start))]))

    history, calls = reader(handler)
    assert await history.read(ENDPOINTS, FILTER, 0, 4999, group='launched') is None
    calls.clear()
    failing = False
    rows = await history.read(ENDPOINTS, FILTER, 0, 5999, group='launched')
    assert [int(row['blockNumber'], 16) for row in rows] == [0, 2400, 4800]
    assert min(int(p['params'][0]['fromBlock'], 16) for _, p in calls) == 2400


@pytest.mark.asyncio
async def test_cap_on_one_endpoint_never_narrows_the_other():
    def handler(url, payload):
        if url == ENDPOINTS[0]:
            return httpx.Response(200, json=dict(id=payload['id'], error={
                'code': -32005, 'message': 'block range too large: maximum allowed is 1000 blocks'}))
        return httpx.Response(200, json=_rpc_ok(payload, [ROW]))

    history, calls = reader(handler)
    assert await history.read(ENDPOINTS, FILTER, 0, 2399, group='launched') == [ROW]
    assert [int(p['params'][0]['toBlock'], 16) for _, p in calls] == [2399, 2399]


async def test_explicit_captured_50_block_limit_is_honoured_below_heuristic_floor():
    capture = json.loads((Path(__file__).parents[1] / 'fixtures/surf/rpc_budget_errors.json').read_text())
    error = capture['cases']['nodies_range']['body']['error']
    def handler(url, payload):
        flt = payload['params'][0]
        start, end = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        if end - start + 1 > 50:
            return httpx.Response(200, json=dict(id=payload['id'], error=error))
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(start))]))
    history, calls = reader(handler)
    rows = await history.read(ENDPOINTS, FILTER, 0, 99, group='launched')
    assert rows is not None
    assert [int(row['blockNumber'], 16) for row in rows] == [0, 50]


@pytest.mark.asyncio
async def test_a_changing_cap_keeps_the_prefix_and_covers_every_block():
    accepted = []
    cap = 1200

    def handler(url, payload):
        nonlocal cap
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        if lo >= 1200:
            cap = 600
        if hi - lo + 1 > cap:
            return httpx.Response(200, json=dict(id=payload['id'], error={
                'code': -32005, 'message': f'block range too large: maximum allowed is {cap} blocks'}))
        accepted.append((lo, hi))
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(lo))]))

    history, calls = reader(handler)
    rows = await history.read(ENDPOINTS, FILTER, 0, 2999, group='launched')
    assert rows is not None
    assert accepted == [(0, 1199), (1200, 1799), (1800, 2399), (2400, 2999)]


@pytest.mark.asyncio
async def test_history_progress_is_filter_specific_and_bounded():
    def handler(url, payload):
        lo = int(payload['params'][0]['fromBlock'], 16)
        if lo:
            return httpx.Response(503)
        return httpx.Response(200, json=_rpc_ok(payload, [ROW]))

    history, calls = reader(handler, max_pending=1)
    assert await history.read(ENDPOINTS, FILTER, 0, 3000, group='first') is None
    assert await history.read(ENDPOINTS, dict(FILTER, address=A.LAUNCHPAD_HOOK), 0, 3000, group='second') is None
    calls.clear()
    assert await history.read(ENDPOINTS, FILTER, 0, 3000, group='first') is None
    assert int(calls[0][1]['params'][0]['fromBlock'], 16) == 0


@pytest.mark.asyncio
async def test_state_batch_retries_only_failed_ids_and_keeps_order():
    calls = []
    payloads = [dict(jsonrpc='2.0', id=i, method='eth_call', params=[]) for i in range(4)]

    async def post(url, payload):
        calls.append((url, [p['id'] for p in payload]))
        return httpx.Response(200, json=[
            dict(id=p['id'], error={'code': -32000, 'message': 'temporary failure'})
            if url == ENDPOINTS[0] and p['id'] == 2 else dict(id=p['id'], result=hex(p['id']))
            for p in reversed(payload)])

    assert await read_state_batch(payloads, ENDPOINTS, post) == ['0x0', '0x1', '0x2', '0x3']
    assert calls == [(ENDPOINTS[0], [0, 1, 2, 3]), (ENDPOINTS[1], [2])]


@pytest.mark.asyncio
async def test_state_batch_is_bounded_and_drpc_never_gets_more_than_three_entries():
    calls = []
    payloads = [dict(jsonrpc='2.0', id=i, method='eth_call', params=[]) for i in range(500)]

    async def post(url, payload):
        calls.append((url, len(payload)))
        if url == ENDPOINTS[0]:
            return httpx.Response(503)
        return httpx.Response(200, json=[dict(id=p['id'], result=hex(p['id'])) for p in payload])

    values = await read_state_batch(payloads, (ENDPOINTS[0], 'https://eth.drpc.org'), post,
                                    retries=1, backoff_seconds=(0,))
    assert values == [hex(i) for i in range(500)]
    assert all(size <= (3 if 'drpc.org' in url else 100) for url, size in calls)


@pytest.mark.asyncio
async def test_state_batch_complete_outage_is_none_but_answered_errors_are_unknown():
    payloads = [dict(jsonrpc='2.0', id=1, method='eth_call', params=[])]

    async def failed(url, payload):
        return httpx.Response(503)

    async def error(url, payload):
        return httpx.Response(200, json=[dict(id=1, error={'code': -32000, 'message': 'failed'})])

    assert await read_state_batch(payloads, ENDPOINTS, failed, retries=1) is None
    assert await read_state_batch(payloads, ENDPOINTS, error) == [None]


@pytest.mark.asyncio
async def test_launchpad_mismatch_is_unknown_then_rebuilds_without_restart():
    reads = _load_launchpad('launchpad_reads.json')
    full = _launchpad_fixture_handler(reads, HISTORY, {})
    incomplete = dict(HISTORY, launched=HISTORY['launched'][1:])
    short = _launchpad_fixture_handler(reads, incomplete, {})
    truncated = True

    def handler(request):
        return (short if truncated else full)(request)

    async with _client_on(RecordingTransport(handler), now_fn=lambda: 2_000_000_000) as client:
        partial = await client.fetch_launchpad()
        assert partial.coin_count == 146
        assert partial.launch_count is None
        assert partial.swap_count is None
        assert partial.cursor is None
        assert partial.coins == ()
        truncated = False
        complete = await client.fetch_launchpad(resume=partial.cursor)
    assert complete.launch_count == 146
    assert complete.swap_count == 165
    assert complete.cursor['last_block'] == HISTORY['head_block']


@pytest.mark.asyncio
async def test_launchpad_retry_keeps_completed_filter_pages_and_frozen_head():
    reads = _load_launchpad('launchpad_reads.json')
    base = _launchpad_fixture_handler(reads, HISTORY, {})
    failing = True

    def handler(request):
        payload = json.loads(request.content)
        if isinstance(payload, dict) and payload['method'] == 'eth_getLogs':
            flt = payload['params'][0]
            if failing and flt['topics'][0] == A.TOPIC_CURVE_SWAP and int(flt['fromBlock'], 16) >= A.LAUNCHPAD_FIRST_BLOCK + 2400:
                return httpx.Response(503)
        return base(request)

    transport = RecordingTransport(handler)
    async with _client_on(transport, now_fn=lambda: 2_000_000_000) as client:
        partial = await client.fetch_launchpad()
        assert partial.launch_count is None
        transport.requests.clear()
        failing = False
        complete = await client.fetch_launchpad(resume=partial.cursor)
    assert complete.launch_count == 146
    assert complete.swap_count == 165
    log_asks = [p for _, _, p in transport.requests if isinstance(p, dict) and p['method'] == 'eth_getLogs']
    assert not any(p['params'][0]['topics'][0] == A.TOPIC_LAUNCHED for p in log_asks)
    assert min(int(p['params'][0]['fromBlock'], 16) for p in log_asks) >= A.LAUNCHPAD_FIRST_BLOCK + 2400


@pytest.mark.asyncio
async def test_decoy_history_cap_never_discards_old_pools():
    rows = _load_launchpad('v4_initializes.json')['rows']
    head = max(int(row['blockNumber'], 16) for row in rows) + 100

    def handler(request):
        payload = json.loads(request.content)
        if payload['method'] == 'eth_blockNumber':
            return httpx.Response(200, json=_rpc_ok(payload, hex(head)))
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        if request.url.host == 'gateway.tenderly.co':
            return httpx.Response(503)
        if hi - lo + 1 > 10_000:
            return httpx.Response(200, json=dict(id=payload['id'], error={
                'code': -32005, 'message': 'block range too large: maximum allowed is 10000 blocks'}))
        found = [row for row in rows if lo <= int(row['blockNumber'], 16) <= hi]
        return httpx.Response(200, json=_rpc_ok(payload, found))

    # A second responding host is required to confirm genuinely empty pages.
    async with _client_on(RecordingTransport(handler), log_rpcs=[
        'https://gateway.tenderly.co/public/mainnet', 'https://rpc.mevblocker.io', 'https://confirmation.example',
    ]) as client:
        count, newest = await client.fetch_decoy_pool_count(A.POOL_V4_ID_FALLBACK)
    assert count == 37
    assert newest['fee'] == 80000


def captured_error(name):
    path = Path(__file__).parents[1] / 'fixtures/surf/rpc_budget_errors.json'
    return json.loads(path.read_text())['cases'][name]


@pytest.mark.asyncio
async def test_captured_drpc_archive_refusal_rotates_without_shrinking():
    evidence = captured_error('drpc_archive')

    def handler(url, payload):
        if url == ENDPOINTS[0]:
            return httpx.Response(evidence['status'], json=evidence['body'])
        return httpx.Response(200, json=_rpc_ok(payload, [ROW]))

    history, calls = reader(handler)
    assert await history.read(ENDPOINTS, FILTER, 0, 1999, group='archive') == [ROW]
    assert [(url, int(p['params'][0]['toBlock'], 16)) for url, p in calls] == [
        (ENDPOINTS[0], 1999), (ENDPOINTS[1], 1999)]


@pytest.mark.asyncio
async def test_captured_mevblocker_cap_is_learned_without_following_suggested_bounds():
    evidence = captured_error('mevblocker_range')
    accepted = []

    def handler(url, payload):
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        if hi - lo + 1 > 10000:
            return httpx.Response(evidence['status'], json=evidence['body'])
        accepted.append((lo, hi))
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(lo))]))

    history, calls = reader(handler)
    rows = await history.read(ENDPOINTS, FILTER, 0, 24999, group='archive', page_size=50000)
    assert rows is not None
    assert accepted == [(0, 9999), (10000, 19999), (20000, 24999)]


@pytest.mark.asyncio
async def test_rebuild_failure_retains_pages_until_count_can_certify_history():
    reads = _load_launchpad('launchpad_reads.json')
    truncated = True
    failing = False
    missing_count = False
    base = _launchpad_fixture_handler(reads, HISTORY, {})
    short = _launchpad_fixture_handler(reads, dict(HISTORY, launched=HISTORY['launched'][1:]), {})
    unverified = _launchpad_fixture_handler(dict(reads, coin_count=None), HISTORY, {})

    def handler(request):
        payload = json.loads(request.content)
        if isinstance(payload, dict) and payload['method'] == 'eth_getLogs':
            flt = payload['params'][0]
            if failing and flt['topics'][0] == A.TOPIC_CURVE_SWAP:
                return httpx.Response(503)
        return (short if truncated else unverified if missing_count else base)(request)

    transport = RecordingTransport(handler)
    async with _client_on(transport) as client:
        assert (await client.fetch_launchpad()).launch_count is None
        truncated, failing = False, True
        assert (await client.fetch_launchpad()).launch_count is None
        transport.requests.clear()
        failing, missing_count = False, True
        assert (await client.fetch_launchpad()).launch_count is None
        assert not any(isinstance(p, dict) and p['method'] == 'eth_getLogs' and
                       p['params'][0]['topics'][0] == A.TOPIC_LAUNCHED for _, _, p in transport.requests)
        transport.requests.clear()
        missing_count = False
        assert (await client.fetch_launchpad()).launch_count == 146
        assert not any(isinstance(p, dict) and p['method'] == 'eth_getLogs' for _, _, p in transport.requests)


@pytest.mark.asyncio
async def test_launchpad_population_witness_uses_the_same_block_as_history():
    from tests.data.test_surf_client import decode_aggregate3_calldata
    base = _launchpad_fixture_handler(_load_launchpad('launchpad_reads.json'), HISTORY, {})
    population_blocks = []

    def handler(request):
        payload = json.loads(request.content)
        if isinstance(payload, dict) and payload['method'] == 'eth_call':
            calls = decode_aggregate3_calldata(payload['params'][0]['data'])
            if any(data.startswith(A.SEL_COIN_COUNT) for _, _, data in calls):
                population_blocks.append(payload['params'][1])
        return base(request)

    async with _client_on(RecordingTransport(handler)) as client:
        result = await client.fetch_launchpad()
    assert result.launch_count == 146
    assert population_blocks == [hex(result.cursor['last_block'])]


@pytest.mark.asyncio
async def test_captured_thirdweb_cap_adapts_without_changing_other_endpoint_width():
    evidence = captured_error('thirdweb_range')
    accepted = []

    def handler(url, payload):
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        if hi - lo + 1 > 1000:
            return httpx.Response(evidence['status'], json=evidence['body'])
        accepted.append((lo, hi))
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(lo))]))

    history, calls = reader(handler)
    assert await history.read(ENDPOINTS, FILTER, 0, 2499, group='thirdweb') is not None
    assert accepted == [(0, 999), (1000, 1999), (2000, 2499)]


@pytest.mark.asyncio
async def test_cancelled_moving_window_reuses_only_the_overlapping_acknowledged_prefix():
    import asyncio
    cancel = True

    def handler(url, payload):
        lo = int(payload['params'][0]['fromBlock'], 16)
        if cancel and lo == 2400:
            raise asyncio.CancelledError()
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(lo))]))

    history, calls = reader(handler)
    with pytest.raises(asyncio.CancelledError):
        await history.read(ENDPOINTS, FILTER, 0, 4999, group='rolling')
    calls.clear()
    cancel = False
    rows = await history.read(ENDPOINTS, FILTER, 100, 5099, group='rolling')
    assert [int(r['blockNumber'], 16) for r in rows] == [2400, 4800]
    assert int(calls[0][1]['params'][0]['fromBlock'], 16) == 2400


@pytest.mark.asyncio
async def test_history_page_budget_defers_unread_tail_without_discarding_prefix():
    def handler(url, payload):
        lo = int(payload['params'][0]['fromBlock'], 16)
        return httpx.Response(200, json=_rpc_ok(payload, [dict(ROW, blockNumber=hex(lo))]))

    history, calls = reader(handler, max_pages=2)
    assert await history.read(ENDPOINTS, FILTER, 0, 5999, group='budgeted') is None
    assert [int(p['params'][0]['fromBlock'], 16) for _, p in calls] == [0, 2400]
    calls.clear()
    rows = await history.read(ENDPOINTS, FILTER, 0, 5999, group='budgeted')
    assert [int(r['blockNumber'], 16) for r in rows] == [0, 2400, 4800]
    assert [int(p['params'][0]['fromBlock'], 16) for _, p in calls] == [4800]
