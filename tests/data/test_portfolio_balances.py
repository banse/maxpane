"""Block-pinned ERC-20 reads, replayed offline with synthetic failure cases."""

import asyncio
import json
import math
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.portfolio_balance_client import PortfolioBalanceClient
from maxpane_dashboard.data.portfolio_models import BALANCE_KEYS
from maxpane_dashboard.data.surf_pool4 import ERC20_SELECTORS, encode_balance_of

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'portfolio' / 'balances'
REAL = json.loads((FIXTURES / 'ethereum_imd_ops.json').read_text())
CASES = json.loads((FIXTURES / 'synthetic_cases.json').read_text())['cases']
WALLET = REAL['provenance']['wallet']
RPCS = {1: ('https://eth.test',), 8453: ('https://base.test',), 4663: ('https://rh.test',)}


def _token(index=1, chain=1):
    return {'id': f'{chain}:{index}', 'chain_id': chain,
            'token_address': '0x' + format(index, '040x')}


def _word(value):
    return '0x' + format(value, '064x')


def _body(request, *, chain=1, block=100, cases=None):
    """Synthetic provider replies use the committed decoder cases."""
    result = []
    for item in json.loads(request.content):
        method = item['method']
        if method == 'eth_chainId':
            value = hex(chain)
        elif method == 'eth_blockNumber':
            value = hex(block)
        else:
            assert method == 'eth_call'
            assert item['params'][1] == hex(block), 'All reads must use the observed block'
            address = item['params'][0]['to']
            case = cases[int(address, 16)-1] if cases else CASES[0]
            value = case['decimals' if item['params'][0]['data'] == ERC20_SELECTORS['decimals'] else 'balance']
        result.append({'jsonrpc': '2.0', 'id': item['id'],
                       'error' if isinstance(value, dict) else 'result': value})
    return result


@pytest.fixture(autouse=True)
def prohibit_real_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError('A portfolio balance test attempted network access')

    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


@pytest.mark.asyncio
async def test_real_public_fixture_replays_exact_wallet_token_chain_and_block():
    exchanges = iter(deepcopy(REAL['exchanges']))

    def handle(request):
        exchange = next(exchanges)
        actual = json.loads(request.content)
        expected = exchange['request']
        # Address case is not an identity difference; calldata/chain/block are exact.
        for row in expected:
            if row['method'] == 'eth_call':
                row['params'][0]['to'] = row['params'][0]['to'].lower()
        assert actual == expected
        return httpx.Response(200, json=exchange['response'])

    token = dict(id='captured-imd', chain_id=1, token_address=REAL['provenance']['token'])
    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle),
                                    rpcs={1: (REAL['provenance']['endpoint'],)}, now_fn=lambda: 123)
    result = (await client.read_balances(WALLET, [token]))['captured-imd']
    raw = int(REAL['exchanges'][1]['response'][1]['result'], 16)
    assert tuple(result) == BALANCE_KEYS
    assert result == dict(balance_raw=raw, decimals=18, held_quantity=raw / 10**18,
                          balance_state='ok', balance_read_at=123,
                          balance_block=int('18f3465', 16))
    await client.close()


@pytest.mark.asyncio
async def test_mixed_decimals_uint_bounds_zero_and_malformed_results_stay_independent():
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=list(reversed(_body(request, cases=CASES))))

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS,
                                    batch_size=3, now_fn=lambda: 999)
    results = await client.read_balances(WALLET, [_token(i+1) for i in range(len(CASES))])
    for index, case in enumerate(CASES):
        row = results[f'1:{index+1}']
        assert row['balance_raw'] == case['expected_raw'], case['name']
        assert row['decimals'] == case['expected_decimals'], case['name']
        assert row['held_quantity'] == case['expected_quantity'], case['name']
        known = case['expected_quantity'] is not None
        assert row['balance_state'] == ('ok' if known else 'unavailable'), case['name']
        assert row['balance_read_at'] == (999 if known else None)
        assert row['balance_block'] == (100 if known else None)
        assert row['held_quantity'] is None or math.isfinite(row['held_quantity'])
    assert max(len(batch) for batch in calls) <= 7
    await client.close()


@pytest.mark.asyncio
async def test_missing_item_only_fails_its_token_and_never_rotates_contract_reverts():
    hosts = []

    def handle(request):
        hosts.append(request.url.host)
        body = _body(request)
        if json.loads(request.content)[-1]['method'] == 'eth_call':
            body = [item for item in body if item['id'] != 4]
            body[-1] = {'jsonrpc': '2.0', 'id': 5,
                        'error': {'code': -32602, 'message': 'execution reverted'}}
        return httpx.Response(200, json=body)

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle),
                                    rpcs={1: ('https://first.test', 'https://second.test')})
    rows = await client.read_balances(WALLET, [_token(), _token(2)])
    assert rows['1:1']['held_quantity'] == 123.456789
    assert rows['1:2']['balance_raw'] is rows['1:2']['decimals'] is rows['1:2']['held_quantity'] is None
    assert hosts == ['first.test', 'first.test']
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['wrong_header_chain', 'wrong_read_chain', 'limitation', 'http_failure'])
async def test_endpoint_failures_rotate_without_accepting_an_unverified_chain(failure):
    hosts = []

    def handle(request):
        hosts.append(request.url.host)
        is_read = json.loads(request.content)[-1]['method'] == 'eth_call'
        if request.url.host == 'first.test':
            if failure == 'http_failure':
                return httpx.Response(503)
            if failure == 'wrong_header_chain' or (failure == 'wrong_read_chain' and is_read):
                return httpx.Response(200, json=_body(request, chain=8453))
            if failure == 'limitation' and is_read:
                body = _body(request)
                body[1] = {'jsonrpc': '2.0', 'id': 2,
                           'error': {'code': -32602, 'message': 'rate limit exceeded'}}
                return httpx.Response(200, json=body)
        return httpx.Response(200, json=_body(request))

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle),
                                    rpcs={1: ('https://first.test', 'https://second.test')})
    row = (await client.read_balances(WALLET, [_token()]))['1:1']
    assert row['balance_state'] == 'ok'
    assert hosts[-2:] == ['second.test', 'second.test']
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('wallet', ['', 'sample', '0x123', '0x'+'z'*40, None])
async def test_invalid_wallet_never_reaches_rpc(wallet):
    def handle(request):
        pytest.fail('Invalid wallet reached RPC')

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS)
    rows = await client.read_balances(wallet, [_token()])
    assert rows['1:1']['balance_state'] == 'unavailable'
    assert all(value is None for key, value in rows['1:1'].items() if key != 'balance_state')
    await client.close()


@pytest.mark.asyncio
async def test_unsupported_chain_and_malformed_contract_never_issue_calls():
    def handle(request):
        pytest.fail('Unsupported token reached RPC')

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS)
    rows = await client.read_balances(WALLET, [_token(1, 999), dict(_token(), token_address='not-an-address')])
    assert rows['999:1']['balance_state'] == 'unsupported'
    assert rows['1:1']['balance_state'] == 'unavailable'
    await client.close()


@pytest.mark.asyncio
async def test_parallel_wallet_calls_keep_their_own_calldata_and_refresh_decimals():
    second_wallet = '0x' + 'b'*40
    first_arrived, release_first = asyncio.Event(), asyncio.Event()
    first_reads = 0

    async def handle(request):
        nonlocal first_reads
        calls = json.loads(request.content)
        reads = [row for row in calls if row['method'] == 'eth_call']
        body = _body(request)
        if reads:
            calldata = reads[0]['params'][0]['data']
            if calldata == encode_balance_of(WALLET):
                first_reads += 1
                if first_reads == 1:
                    first_arrived.set()
                    await release_first.wait()
                raw, decimals = 3*10**24, 24
            else:
                assert calldata == encode_balance_of(second_wallet)
                raw, decimals = 2*10**6, 6
            body[1]['result'], body[2]['result'] = _word(raw), _word(decimals)
        return httpx.Response(200, json=body)

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS)
    first = asyncio.create_task(client.read_balances(WALLET, [_token()]))
    await asyncio.wait_for(first_arrived.wait(), 1)
    second = await client.read_balances(second_wallet, [_token()])
    release_first.set()
    first_result = await first
    assert first_result['1:1']['held_quantity'] == 3
    assert second['1:1']['held_quantity'] == 2
    assert (await client.read_balances(WALLET, [_token()]))['1:1']['decimals'] == 24
    await client.close()


@pytest.mark.asyncio
async def test_chains_progress_independently_with_bounded_concurrency():
    blocked, base_done, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    active, maximum = 0, 0

    async def handle(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        chain = {'eth.test': 1, 'base.test': 8453, 'rh.test': 4663}[request.url.host]
        try:
            if chain == 1:
                blocked.set()
                await release.wait()
            if chain == 8453 and json.loads(request.content)[-1]['method'] == 'eth_call':
                base_done.set()
            return httpx.Response(200, json=_body(request, chain=chain))
        finally:
            active -= 1

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS, concurrency=2)
    task = asyncio.create_task(client.read_balances(WALLET, [_token(chain=chain) for chain in RPCS]))
    await asyncio.wait_for(blocked.wait(), 1)
    await asyncio.wait_for(base_done.wait(), 1)
    assert not task.done()
    release.set()
    rows = await task
    assert maximum == 2
    assert all(row['balance_state'] == 'ok' for row in rows.values())
    await client.close()


@pytest.mark.asyncio
async def test_owned_client_closes_but_injected_client_stays_open():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_body(request)))
    borrowed = httpx.AsyncClient(transport=transport)
    client = PortfolioBalanceClient(http_client=borrowed, rpcs=RPCS)
    await client.close()
    assert not borrowed.is_closed
    assert (await client.read_balances(WALLET, [_token()]))['1:1']['balance_state'] == 'ok'
    await borrowed.aclose()
    owned = PortfolioBalanceClient(transport=transport, rpcs=RPCS)
    await owned.close()
    assert owned._client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize('block', [None, 'latest', '0x', True, '-0x1'])
async def test_invalid_block_cannot_certify_a_balance(block):
    def handle(request):
        calls = json.loads(request.content)
        assert all(row['method'] != 'eth_call' for row in calls)
        body = _body(request)
        body[1]['result'] = block
        return httpx.Response(200, json=body)

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS)
    row = (await client.read_balances(WALLET, [_token()]))['1:1']
    assert row['balance_state'] == 'unavailable'
    assert row['held_quantity'] is row['balance_block'] is row['balance_read_at'] is None
    await client.close()


@pytest.mark.asyncio
async def test_verified_token_aliases_share_one_read_and_return_detached_records():
    batches = []

    def handle(request):
        batches.append(json.loads(request.content))
        return httpx.Response(200, json=_body(request))

    original = _token()
    alias = dict(original, id='second-launch')
    tokens = [original, alias]
    saved = deepcopy(tokens)
    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), rpcs=RPCS)
    rows = await client.read_balances(WALLET, tokens)
    assert tokens == saved
    assert [len(batch) for batch in batches] == [2, 3]
    assert rows['1:1'] == rows['second-launch']
    rows['1:1']['held_quantity'] = -1
    assert rows['second-launch']['held_quantity'] == 123.456789
    await client.close()


@pytest.mark.asyncio
async def test_completed_chunk_survives_later_endpoint_failure_and_block_change():
    requested = []

    def handle(request):
        calls = json.loads(request.content)
        reads = [row for row in calls if row['method'] == 'eth_call']
        address = reads[0]['params'][0]['to'] if reads else None
        requested.append((request.url.host, address))
        if request.url.host == 'first.test' and address == _token(2)['token_address']:
            return httpx.Response(503)
        block = 100 if request.url.host == 'first.test' else 101
        return httpx.Response(200, json=_body(request, block=block))

    client = PortfolioBalanceClient(transport=httpx.MockTransport(handle), batch_size=1,
                                    rpcs={1: ('https://first.test', 'https://second.test')})
    rows = await client.read_balances(WALLET, [_token(), _token(2)])
    assert rows['1:1']['balance_block'] == 100
    assert rows['1:2']['balance_block'] == 101
    assert ('second.test', _token()['token_address']) not in requested
    await client.close()
