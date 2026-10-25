"""Independent, bounded POOL4 executor and destination-burn evidence.

The hook counter, an executor bridge and a Base receiver burn are distinct
facts. This reader borrows Pool4Client's keyless transport; it owns no sockets.
Only complete recent windows publish an event (or an observed empty window).
"""
from __future__ import annotations

import asyncio
import re
import time

import httpx

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.keccak import keccak256
from maxpane_dashboard.data.rpc_common import jsonrpc_payload
from maxpane_dashboard.data.surf_launch_base_client import BASE_LAUNCH_RPCS
from maxpane_dashboard.data.surf_rpc_batch import read_state_batch
from maxpane_dashboard.data.surf_rpc_history import RpcHistoryReader
from maxpane_dashboard.data.surf_rpc_window import RpcLogWindow
from maxpane_dashboard.data.surf_transport import read_cycle

SELECTORS = {signature: '0x' + keccak256(signature.encode()).hex()[:8] for signature in (
    'burnSink()', 'token()', 'oft()', 'dstEid()', 'baseBurnReceiver()',
    'tokenBalance()', 'minBridgeAmount()', 'previewBridge()', 'decimals()',
)}
BURN_EXECUTED = '0x' + keccak256(b'BurnExecuted(address,address)').hex()
TRANSFER = '0x' + keccak256(b'Transfer(address,address,uint256)').hex()
# Captured 2026-10-25: both serve 40,000-block empty windows and the same
# receiver burn / finalized header. Base publicnode rejects >50,000 blocks.
# Bloxroute is a log fallback only; state retains the existing Base pool.
BASE_BURN_LOG_RPCS = ('https://base-rpc.publicnode.com', 'https://base.rpc.blxrbdn.com')
ETH_SPAN, BASE_SPAN = 50_400, 302_400
BASE_EID = 30184
_ZERO = '0x' + '0' * 64
_HEX = re.compile(r'0x[0-9a-fA-F]*\Z')


def _uint(raw):
    if not isinstance(raw, str) or not re.fullmatch(r'0x[0-9a-fA-F]{1,64}', raw):
        raise ValueError('invalid integer')
    return int(raw, 16)


def _words(raw, count):
    if not isinstance(raw, str) or not _HEX.fullmatch(raw) or len(raw) != 2 + 64 * count:
        raise ValueError('invalid ABI words')
    return [int(raw[2 + i*64:2 + (i+1)*64], 16) for i in range(count)]


def _address(raw):
    if not isinstance(raw, str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', raw) or int(raw, 16) == 0:
        raise ValueError('invalid address')
    return raw.lower()


def _word_address(raw, *, allow_zero=False):
    value = _words(raw, 1)[0]
    if not 0 <= value < 2**160 or (value == 0 and not allow_zero):
        raise ValueError('invalid address word')
    return f'0x{value:040x}'


def _hash(raw):
    _words(raw, 1)
    return raw.lower()


def _topic(address):
    return '0x' + _address(address)[2:].zfill(64)


def _identity(identity):
    if not isinstance(identity, dict) or identity.get('network') != 'MAINNET' or identity.get('dst_eid') != BASE_EID:
        raise ValueError('unsupported destination')
    for key in ('hook', 'executor', 'token', 'oft', 'receiver', 'base_token'):
        if identity.get(key) != _address(identity.get(key)):
            raise ValueError('noncanonical identity')
    if (identity['token'] != A.IMD_TOKEN.lower() or identity['oft'] != A.IMD_TOKEN.lower()
            or identity['base_token'] != A.FP_TOKEN_BASE.lower()):
        raise ValueError('unbound token')


def _position(log):
    if not isinstance(log, dict) or log.get('removed') is not False:
        raise ValueError('removed or malformed log')
    _address(log.get('address'))
    _hash(log.get('transactionHash'))
    _hash(log.get('blockHash'))
    if not isinstance(log.get('topics'), list):
        raise ValueError('invalid topics')
    for topic in log['topics']:
        _hash(topic)
    data = log.get('data')
    if not isinstance(data, str) or not _HEX.fullmatch(data) or len(data) % 2:
        raise ValueError('invalid log data')
    return _uint(log.get('blockNumber')), _uint(log.get('logIndex'))


def _receipt_event(receipt, log, header, decimals):
    block, index = _position(log)
    if not isinstance(receipt, dict) or not isinstance(header, dict) or not isinstance(decimals, int) or not 0 <= decimals <= 36:
        raise ValueError('missing receipt/header/decimals')
    if (_uint(receipt.get('status')) != 1 or _uint(receipt.get('blockNumber')) != block
            or _uint(header.get('number')) != block
            or _hash(receipt.get('transactionHash')) != _hash(log['transactionHash'])
            or _hash(receipt.get('blockHash')) != _hash(log['blockHash'])
            or _hash(header.get('hash')) != _hash(log['blockHash'])):
        raise ValueError('unconfirmed receipt')
    logs = receipt.get('logs')
    if not isinstance(logs, list) or len(logs) > 4096:
        raise ValueError('invalid receipt logs')
    fields = ('address', 'topics', 'data', 'blockNumber', 'blockHash', 'transactionHash', 'logIndex')
    if not any(isinstance(item, dict) and all(item.get(k) == log.get(k) for k in fields)
               and item.get('removed') is False for item in logs):
        raise ValueError('event absent from receipt')
    return {'tx': log['transactionHash'].lower(), 'block': block, 'log_index': index,
            'timestamp': _uint(header.get('timestamp')), 'decimals': decimals}


def decode_bridge_receipt(receipt, log, header, identity, decimals):
    """A successful source receipt proves a send, never destination burning."""
    try:
        _identity(identity)
        result = _receipt_event(receipt, log, header, decimals)
        topics = log['topics']
        if (_address(log['address']) != identity['executor'] or len(topics) != 4
                or topics[0].lower() != A.TOPIC_TOKENS_BRIDGED_FOR_BURN.lower()
                or _word_address(topics[1]) != identity['oft']
                or _uint(topics[2]) != identity['dst_eid']
                or _word_address(topics[3]) != identity['receiver']):
            return None
        amount, minimum, guid = _words(log['data'], 3)
        if minimum > amount:
            return None
        return dict(result, amount_wei=amount, dst_eid=identity['dst_eid'],
                    receiver=identity['receiver'], guid=f'0x{guid:064x}')
    except (KeyError, TypeError, ValueError):
        return None


def decode_base_burn_receipt(receipt, log, header, identity, decimals):
    """Require receiver BurnExecuted AND its token's Transfer to zero."""
    try:
        _identity(identity)
        result = _receipt_event(receipt, log, header, decimals)
        topics = log['topics']
        if (_address(log['address']) != identity['receiver'] or len(topics) != 3
                or topics[0].lower() != BURN_EXECUTED
                or _word_address(topics[2]) != identity['base_token'] or log['data'] != '0x'):
            return None
        amounts = {}
        for transfer in receipt['logs']:
            if not isinstance(transfer, dict) or str(transfer.get('address', '')).lower() != identity['base_token']:
                continue
            wanted = [TRANSFER, _topic(identity['receiver']), _ZERO]
            if transfer.get('topics') != wanted:
                continue
            block, index = _position(transfer)
            if (block != result['block'] or _hash(transfer['transactionHash']) != result['tx']
                    or _hash(transfer['blockHash']) != _hash(log['blockHash'])):
                return None
            amount = _words(transfer['data'], 1)[0]
            if index in amounts and amounts[index] != amount:
                return None
            amounts[index] = amount
        return dict(result, amount_wei=sum(amounts.values())) if amounts else None
    except (KeyError, TypeError, ValueError):
        return None


class Pool4BurnClient:
    """Three independent reads; caller owns deadlines, due clocks and merging."""

    def __init__(self, pool4_client, *, clock=time.time):
        self._pool, self._clock = pool4_client, clock
        self._history = RpcHistoryReader(self._post_history, max_pages=12, max_rows=4096,
            max_pending=4, prove_block=lambda url, block: self._pool._transport.prove_block(
                self._pool._client, url, block))
        self._windows = RpcLogWindow(self._history, max_windows=4, max_rows=4096)

    def clear(self):
        self._windows.clear()

    async def _base(self, calls):
        payloads = [jsonrpc_payload(i+1, method, params) for i, (method, params) in enumerate(calls)]
        return await read_state_batch(payloads, BASE_LAUNCH_RPCS, self._pool._post_rpc,
                                      retries=1, backoff_seconds=())

    async def _post_history(self, url, payload):
        response = await self._pool._post_rpc(url, payload)
        body = response.json()
        rows = body.get('result') if isinstance(body, dict) else None
        if isinstance(rows, list) and payload['method'] == 'eth_getLogs':
            flt = payload['params'][0]
            for row in rows:
                block, _ = _position(row)
                if (not _uint(flt['fromBlock']) <= block <= _uint(flt['toBlock'])
                        or _address(row['address']) != flt['address']
                        or any(topic is not None and (len(row['topics']) <= i or row['topics'][i].lower() != topic)
                               for i, topic in enumerate(flt['topics']))):
                    raise ValueError('log outside requested filter')
        return response

    @staticmethod
    def _call(address, signature, block):
        return 'eth_call', [{'to': address, 'data': SELECTORS[signature]}, hex(block)]

    async def fetch_queue(self, network, hook):
        # Transient observations let the manager invalidate an old binding even
        # when a changed executor cannot supply a usable queue. Never persist
        # these as a verified pipeline or freshen a last-good value with them.
        observed = None
        if network != 'MAINNET':
            return None
        try:
            hook = _address(hook)
            raw = await self._pool._rpc_state_batch(network, [
                ('eth_chainId', []), ('eth_getBlockByNumber', ['latest', False])])
            if not isinstance(raw, list) or len(raw) != 2 or _uint(raw[0]) != 1:
                return None
            block = _uint(raw[1]['number'])
            raw = await self._pool._rpc_state_batch(network, [self._call(hook, 'burnSink()', block)])
            executor = _word_address(raw[0], allow_zero=True)
            observed = {'network': network, 'hook': hook, 'executor': executor}
            if int(executor, 16) == 0:
                return {'observed_identity': observed, 'queue': None}
            signatures = ('token()', 'oft()', 'dstEid()', 'baseBurnReceiver()',
                          'tokenBalance()', 'minBridgeAmount()', 'previewBridge()')
            raw = await self._pool._rpc_state_batch(network,
                [self._call(executor, signature, block) for signature in signatures]
                + [self._call(A.IMD_TOKEN, 'decimals()', block)])
            if not isinstance(raw, list) or len(raw) != 8:
                return {'observed_identity': observed, 'queue': None}
            for i, key in enumerate(('token', 'oft', 'dst_eid', 'receiver')):
                try:
                    value = _words(raw[i], 1)[0] if key == 'dst_eid' else _word_address(raw[i], allow_zero=True)
                    if key != 'dst_eid' or value < 2**32:
                        observed[key] = value
                except ValueError:
                    pass  # An unread getter cannot contradict a prior binding.
            identity = dict(observed, base_token=A.FP_TOKEN_BASE.lower())
            _identity(identity)
            balance, minimum, decimals = (_words(raw[i], 1)[0] for i in (4, 5, 7))
            preview, received, _ = _words(raw[6], 3)
            if decimals > 36 or preview > balance or received > preview:
                return {'observed_identity': observed, 'queue': None}
            return {'identity': identity, 'queue': {'state': 'ok', 'read_ts': self._clock(),
                'block': block, 'amount_wei': balance, 'min_bridge_wei': minimum,
                'bridge_amount_wei': preview, 'decimals': decimals}}
        except asyncio.CancelledError:
            # Deadline cancellation must not hide a sink change already read.
            # Return only invalidation evidence and perform no further I/O;
            # the manager's generation guard rejects a retired view's result.
            if observed is not None:
                return {'observed_identity': observed, 'queue': None}
            raise
        except (KeyError, TypeError, ValueError, IndexError, httpx.HTTPError, RuntimeError):
            return {'observed_identity': observed, 'queue': None} if observed is not None else None

    async def fetch_bridge(self, identity):
        return await self._fetch_history(identity, base=False)

    async def fetch_base_burn(self, identity):
        return await self._fetch_history(identity, base=True)

    @read_cycle
    async def _fetch_history(self, identity, *, base):
        try:
            _identity(identity)
            read = self._base if base else lambda calls: self._pool._rpc_state_batch('MAINNET', calls)
            raw = await read([('eth_chainId', []), ('eth_getBlockByNumber', ['finalized', False])])
            if not isinstance(raw, list) or len(raw) != 2 or _uint(raw[0]) != (8453 if base else 1):
                return None
            head = _uint(raw[1]['number'])
            token = identity['base_token'] if base else identity['token']
            calls = [self._call(token, 'decimals()', head)]
            if base:
                calls.append(self._call(identity['receiver'], 'token()', head))
            raw = await read(calls)
            decimals = _words(raw[0], 1)[0]
            if decimals > 36 or (base and _word_address(raw[1]) != token):
                return None
            start = max(0, head - (BASE_SPAN if base else ETH_SPAN) + 1)
            address = identity['receiver'] if base else identity['executor']
            topics = ([BURN_EXECUTED, None, _topic(token)] if base else
                      [A.TOPIC_TOKENS_BRIDGED_FOR_BURN, _topic(identity['oft']),
                       f'0x{identity["dst_eid"]:064x}', _topic(identity['receiver'])])
            endpoints = BASE_BURN_LOG_RPCS if base else self._pool.log_endpoints('MAINNET')
            group = ('base-burn:' if base else 'bridge:') + repr(sorted(identity.items()))
            logs = await self._windows.read(endpoints, {'address': address, 'topics': topics},
                start, head, group=group, page_size=40_000 if base else 10_000)
            if logs is None:
                return None
            event = None
            if logs:
                latest = max(logs, key=_position)
                raw = await read([('eth_getTransactionReceipt', [latest['transactionHash']]),
                                  ('eth_getBlockByNumber', [latest['blockNumber'], False])])
                decoder = decode_base_burn_receipt if base else decode_bridge_receipt
                event = decoder(raw[0], latest, raw[1], identity, decimals)
                if event is None:
                    return None
            return {'state': 'ok', 'read_ts': self._clock(), 'from_block': start,
                    'to_block': head, 'complete': True, 'event': event}
        except (KeyError, TypeError, ValueError, IndexError, httpx.HTTPError, RuntimeError):
            return None
