"""Captured executor and receiver evidence; no socket is opened by these tests."""
import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import surf_pool4_burn as burn
from maxpane_dashboard.data.surf_pool4_client import Pool4Client
from maxpane_dashboard.data.surf_transport import SurfTransport

FIXTURE = json.loads((Path(__file__).parents[1] / 'fixtures/surf_pool4_burn/live.json').read_text())
HOOK = '0xc6c965bd164c483e87d0b550671798e9a3602840'
IDENTITY = {'network': 'MAINNET', 'hook': HOOK,
    'executor': '0xe29386719c155b6847ad5a4e97c6674f10ffc750',
    'token': '0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7',
    'oft': '0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7', 'dst_eid': 30184,
    'receiver': '0xf9d7cbf5bef2f5c9ba93a70f31ddca6457716793',
    'base_token': '0xff0c532fdb8cd566ae169c1cb157ff2bdc83e105'}


def bridge_parts():
    data = copy.deepcopy(FIXTURE['bridge'])
    header = {'number': data['log']['blockNumber'], 'hash': data['log']['blockHash'],
              'timestamp': data['log']['blockTimestamp']}
    return data['receipt'], data['log'], header


def base_parts():
    data = copy.deepcopy(FIXTURE['base'])
    log = next(x for x in data['receipt']['logs'] if x['address'] == IDENTITY['receiver'])
    return data['receipt'], log, data['block']


def test_bridge_receipt_uses_real_live_amount_and_destination():
    event = burn.decode_bridge_receipt(*bridge_parts(), IDENTITY, 18)
    assert event['amount_wei'] == 159563587000000000000
    assert event['receiver'] == IDENTITY['receiver']
    assert event['dst_eid'] == 30184
    assert event['tx'] == FIXTURE['bridge']['receipt']['transactionHash']


def test_base_burn_amount_is_proven_by_transfer_to_zero():
    event = burn.decode_base_burn_receipt(*base_parts(), IDENTITY, 18)
    assert event['amount_wei'] == 159563587000000000000
    assert event['timestamp'] == int(FIXTURE['base']['block']['timestamp'], 16)
    assert event['tx'] != FIXTURE['bridge']['receipt']['transactionHash']


@pytest.mark.parametrize('fault', ['failed', 'no_transfer', 'wrong_token', 'wrong_sender', 'wrong_recipient',
                                    'removed', 'wrong_block', 'wrong_tx', 'malformed_amount', 'wrong_event_token'])
def test_base_burn_rejects_unproven_or_unrelated_receipt(fault):
    receipt, log, header = base_parts()
    transfer = receipt['logs'][0]
    if fault == 'failed': receipt['status'] = '0x0'
    elif fault == 'no_transfer': receipt['logs'] = [receipt['logs'][1]]
    elif fault == 'wrong_token': transfer['address'] = '0x' + '1' * 40
    elif fault == 'wrong_sender': transfer['topics'][1] = '0x' + '0' * 24 + '1' * 40
    elif fault == 'wrong_recipient': transfer['topics'][2] = '0x' + '0' * 24 + '1' * 40
    elif fault == 'removed': log['removed'] = True
    elif fault == 'wrong_block': header['hash'] = '0x' + '1' * 64
    elif fault == 'wrong_tx': receipt['transactionHash'] = '0x' + '1' * 64
    elif fault == 'malformed_amount': transfer['data'] = '0x1'
    elif fault == 'wrong_event_token': log['topics'][2] = '0x' + '0' * 24 + '1' * 40
    assert burn.decode_base_burn_receipt(receipt, log, header, IDENTITY, 18) is None


@pytest.mark.parametrize('fault', ['failed', 'wrong_oft', 'wrong_destination', 'wrong_receiver', 'missing_log'])
def test_bridge_rejects_wrong_identity_or_failed_receipt(fault):
    receipt, log, header = bridge_parts()
    if fault == 'failed': receipt['status'] = '0x0'
    elif fault == 'wrong_oft': log['topics'][1] = '0x' + '0' * 24 + '1' * 40
    elif fault == 'wrong_destination': log['topics'][2] = '0x' + '0' * 63 + '1'
    elif fault == 'wrong_receiver': log['topics'][3] = '0x' + '0' * 24 + '1' * 40
    elif fault == 'missing_log': receipt['logs'] = []
    if fault.startswith('wrong_'):
        receipt['logs'] = [copy.deepcopy(log) if item.get('logIndex') == log['logIndex'] else item
                           for item in receipt['logs']]
    assert burn.decode_bridge_receipt(receipt, log, header, IDENTITY, 18) is None


def test_base_transfer_duplicates_cannot_double_count():
    receipt, log, header = base_parts()
    receipt['logs'].append(copy.deepcopy(receipt['logs'][0]))
    assert burn.decode_base_burn_receipt(receipt, log, header, IDENTITY, 18)['amount_wei'] == 159563587000000000000
    receipt['logs'][-1]['data'] = '0x' + '0' * 63 + '1'
    assert burn.decode_base_burn_receipt(receipt, log, header, IDENTITY, 18) is None


class Replay:
    def __init__(self):
        self.calls = []
        self.mutate_call = None
        self.empty = False
        self.dead_fallback = False
        self.bad_log = False
        self.bad_header = False
        self.pause = None

    async def __call__(self, request):
        payload = json.loads(request.content)
        base = 'base' in request.url.host
        entries = payload if isinstance(payload, list) else [payload]
        output = []
        for call in entries:
            self.calls.append((request.url.host, call))
            method, params = call['method'], call['params']
            if self.pause and method == 'eth_getLogs':
                self.pause.set()
                await asyncio.Event().wait()
            result = None
            if method == 'eth_chainId': result = '0x2105' if base else '0x1'
            elif method == 'eth_getBlockByNumber':
                fixture = FIXTURE['base'] if base else FIXTURE['queue']
                result = copy.deepcopy(fixture['head'])
                if params[0] not in ('latest', 'finalized'):
                    result['number'] = params[0]
                    if params[0] == FIXTURE['bridge']['log']['blockNumber']:
                        _, _, result = bridge_parts()
                    elif params[0] == FIXTURE['base']['block']['number']:
                        result = copy.deepcopy(FIXTURE['base']['block'])
                if self.bad_header and not isinstance(payload, list): result = None
            elif method == 'eth_call':
                data = params[0]['data']
                if data == burn.SELECTORS['burnSink()']: result = FIXTURE['queue']['hook_burn_sink']
                elif base:
                    result = FIXTURE['base']['token'] if data == burn.SELECTORS['token()'] else FIXTURE['base']['decimals']
                else:
                    sig = next(s for s, sel in burn.SELECTORS.items() if sel == data)
                    result = FIXTURE['queue']['calls'].get(sig)
                if self.mutate_call: result = self.mutate_call(call, result)
            elif method == 'eth_getLogs':
                if self.dead_fallback and request.url.host != 'base-rpc.publicnode.com':
                    output.append({'jsonrpc':'2.0','id':call['id'],'error':{'code':-32000,'message':'archive unavailable'}})
                    continue
                logs = FIXTURE['base']['logs'] if base else [FIXTURE['bridge']['log']]
                start, end = int(params[0]['fromBlock'],16), int(params[0]['toBlock'],16)
                result = [] if self.empty else [copy.deepcopy(x) for x in logs if start <= int(x['blockNumber'],16) <= end]
                if self.bad_log:
                    result = [copy.deepcopy(logs[-1])]
                    result[0]['address'] = '0x'+'1'*40
            elif method == 'eth_getTransactionReceipt':
                result = copy.deepcopy(FIXTURE['base' if base else 'bridge']['receipt'])
            output.append({'jsonrpc': '2.0', 'id': call['id'], 'result': result})
        return httpx.Response(200, json=output if isinstance(payload,list) else output[0])


@pytest.fixture
async def reader():
    replay = Replay()
    async with httpx.AsyncClient(transport=httpx.MockTransport(replay)) as http:
        pool = Pool4Client(http_client=http, transport=SurfTransport(delay=0), backoff_seconds=())
        yield burn.Pool4BurnClient(pool, clock=lambda: 1234), replay


@pytest.mark.asyncio
async def test_queue_pins_calls_to_one_block_and_does_not_read_base(reader):
    client, replay = reader
    result = await client.fetch_queue('MAINNET', HOOK)
    assert result['identity'] == IDENTITY
    assert result['queue'] == {'state':'ok','read_ts':1234,'block':int(FIXTURE['queue']['head']['number'],16),
        'amount_wei':29946233978030186465,'min_bridge_wei':0,'bridge_amount_wei':29946233000000000000,'decimals':18}
    assert not any('base' in host for host, _ in replay.calls)
    assert all(call['params'][1] == FIXTURE['queue']['head']['number']
               for _, call in replay.calls if call['method'] == 'eth_call')


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['wrong_token','wrong_oft','wrong_eid','zero_receiver','bad_decimals','no_sink'])
async def test_queue_rejects_wrong_binding(reader, fault):
    client, replay = reader
    key = {'wrong_token':'token()','wrong_oft':'oft()','wrong_eid':'dstEid()',
           'zero_receiver':'baseBurnReceiver()','bad_decimals':'decimals()','no_sink':'burnSink()'}[fault]
    def mutate(call, result):
        if call['params'][0]['data'] != burn.SELECTORS[key]: return result
        if fault == 'no_sink': return '0x'
        if fault == 'zero_receiver': return '0x'+'0'*64
        if fault == 'wrong_eid': return f'0x{30183:064x}'
        if fault == 'bad_decimals': return f'0x{99:064x}'
        return '0x'+'0'*24+'1'*40
    replay.mutate_call = mutate
    result = await client.fetch_queue('MAINNET', HOOK)
    if fault == 'no_sink':
        assert result is None
    else:
        assert result['queue'] is None
        assert result['observed_identity']['executor'] == IDENTITY['executor']
        if fault == 'wrong_eid': assert result['observed_identity']['dst_eid'] == 30183
        if fault == 'zero_receiver': assert result['observed_identity']['receiver'] == '0x'+'0'*40


@pytest.mark.asyncio
async def test_unsupported_network_performs_no_reads(reader):
    client, replay = reader
    assert await client.fetch_queue('SEPOLIA', HOOK) is None
    assert replay.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['bridge','base_burn'])
async def test_completed_history_is_finalized_and_receipt_verified(reader, stage):
    client, replay = reader
    result = await getattr(client,'fetch_'+stage)(IDENTITY)
    assert result['state'] == 'ok' and result['complete'] is True
    assert result['event']['amount_wei'] == 159563587000000000000
    assert result['read_ts'] == 1234
    assert result['to_block']-result['from_block']+1 == (302400 if stage=='base_burn' else 50400)
    assert any(call['params'][0]=='finalized' for _,call in replay.calls if call['method']=='eth_getBlockByNumber')
    assert any(call['method']=='eth_getTransactionReceipt' for _,call in replay.calls)
    assert all(int(call['params'][0]['toBlock'],16)-int(call['params'][0]['fromBlock'],16)<40000
               for _,call in replay.calls if call['method']=='eth_getLogs')


@pytest.mark.asyncio
async def test_empty_window_requires_two_hosts_and_carries_no_lifetime_zero(reader):
    client, replay = reader
    replay.empty = True
    result = await client.fetch_base_burn(IDENTITY)
    assert result['complete'] is True and result['event'] is None
    log_hosts = {host for host,call in replay.calls if call['method']=='eth_getLogs'}
    assert len(log_hosts) == 2
    replay.dead_fallback = True
    assert await client.fetch_base_burn(IDENTITY) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['bad_log','bad_header'])
async def test_untrusted_log_or_unproven_host_cannot_certify_history(reader, failure):
    client, replay = reader
    setattr(replay,failure,True)
    assert await client.fetch_base_burn(IDENTITY) is None


@pytest.mark.asyncio
async def test_page_bound_resumes_and_clear_discards_progress(reader):
    client, replay = reader
    client._history._max_pages = 1
    assert await client.fetch_base_burn(IDENTITY) is None
    first_calls = len(replay.calls)
    assert await client.fetch_base_burn(IDENTITY) is None
    first = next(call for _,call in replay.calls[first_calls:] if call['method']=='eth_getLogs')
    assert int(first['params'][0]['fromBlock'],16) > int(FIXTURE['base']['head']['number'],16)-302399
    client.clear()
    first_calls = len(replay.calls)
    assert await client.fetch_base_burn(IDENTITY) is None
    first = next(call for _,call in replay.calls[first_calls:] if call['method']=='eth_getLogs')
    assert int(first['params'][0]['fromBlock'],16) == int(FIXTURE['base']['head']['number'],16)-302399


@pytest.mark.asyncio
async def test_cancellation_releases_the_borrowed_transport(reader):
    client, replay = reader
    replay.pause = asyncio.Event()
    task = asyncio.create_task(client.fetch_base_burn(IDENTITY))
    await asyncio.wait_for(replay.pause.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not client._pool._client.is_closed


@pytest.mark.asyncio
async def test_wrong_address_page_is_rejected_before_receipt_selection(reader):
    client, replay = reader
    replay.bad_log = True
    log = FIXTURE['base']['logs'][-1]
    payload = {'id':1, 'jsonrpc':'2.0', 'method':'eth_getLogs', 'params':[{
        'address': IDENTITY['receiver'], 'topics':[burn.BURN_EXECUTED],
        'fromBlock':log['blockNumber'], 'toBlock':log['blockNumber']}]}
    with pytest.raises(ValueError, match='outside requested filter'):
        await client._post_history('https://base-rpc.publicnode.com', payload)


@pytest.mark.asyncio
async def test_changed_executor_survives_failure_of_its_getters(reader):
    client, replay = reader
    def mutate(call, result):
        if call['params'][0]['data'] == burn.SELECTORS['burnSink()']:
            return '0x'+'0'*24+'1'*40
        return '0x'
    replay.mutate_call = mutate
    assert await client.fetch_queue('MAINNET', HOOK) == {
        'observed_identity': {'network':'MAINNET', 'hook':HOOK, 'executor':'0x'+'1'*40},
        'queue':None}


@pytest.mark.asyncio
async def test_changed_executor_is_reported_when_followup_rpc_raises(reader):
    client, replay = reader
    read = client._pool._rpc_state_batch
    replay.mutate_call = lambda call, result: ('0x'+'0'*24+'1'*40
        if call['params'][0]['data'] == burn.SELECTORS['burnSink()'] else result)
    async def failing_config(network, calls):
        if len(calls) == 8:
            raise httpx.ReadTimeout('executor read timeout')
        return await read(network, calls)
    client._pool._rpc_state_batch = failing_config
    assert await client.fetch_queue('MAINNET', HOOK) == {
        'observed_identity': {'network':'MAINNET', 'hook':HOOK, 'executor':'0x'+'1'*40},
        'queue':None}
