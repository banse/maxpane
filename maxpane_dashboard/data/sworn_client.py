"""Bounded, keyless reads of the owner's launch-2404 Sworn deployment."""
from __future__ import annotations

import base64
import json
import re
from urllib.parse import unquote

import httpx

from .evm_abi import decode_string
from .keccak import keccak256
from .rpc_common import OwnedHttpClient

# Website imd-deployment.json, independently checked against Registry getters
# 2026-10-23. Deployment identity is not inferred from the repo's older docs.
BINDING = {
    'chain_id': 1,
    'registry': '0x0da2679000ea5380d1361cc3cca7d4e8c881f766',
    'renderer': '0x3039eaf3b979759c77a2a3fc62850f9534162c3b',
    'composer': '0xf564dd76bd081554170c5e0b78144abfb39f7061',
    'source_commit': 'c4ff3238390fc51962fb67e86affc20cf418126e',
}
ENDPOINTS = ('https://ethereum-rpc.publicnode.com', 'https://gateway.tenderly.co/public/mainnet')
MAX_URI = 1_000_000
MAX_SVG = 256_000


class SwornReadError(ValueError):
    """A failed observation, distinct from a proven empty collection/wallet."""


def selector(signature):
    return '0x' + keccak256(signature.encode()).hex()[:8]


def address(value):
    return isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', value) is not None


def word(value):
    if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]{64}', value):
        raise SwornReadError('Incomplete contract read')
    return int(value, 16)


def abi_address(value):
    number = word(value)
    if not 0 < number < 2**160:
        raise SwornReadError('Invalid contract address')
    return '0x' + f'{number:040x}'


def validate_metadata(data, claimant):
    if not isinstance(data, dict) or len(json.dumps(data)) > MAX_URI:
        raise SwornReadError('Invalid card metadata')
    for key, limit in (('traits', 25), ('community', 32), ('attributes', 64), ('oracle', 57)):
        if not isinstance(data.get(key), list) or len(data[key]) > limit:
            raise SwornReadError('Invalid card metadata list')
    for key in ('traits', 'community'):
        if any(type(i) is not int or not 0 < i < 65536 for i in data[key]):
            raise SwornReadError('Invalid trait identifier')
    for item in data['attributes']:
        if not isinstance(item, dict) or not isinstance(item.get('trait_type'), str) or len(item['trait_type']) > 256:
            raise SwornReadError('Invalid metadata attribute')
        value = item.get('value')
        if not (type(value) is str and len(value) <= 2048 or type(value) is int and 0 <= value < 2**256):
            raise SwornReadError('Invalid metadata attribute value')
    for proof in data['oracle']:
        if not isinstance(proof, dict):
            raise SwornReadError('Invalid oracle evidence')
        for key in ('traitId', 'fromBlock', 'toBlock', 'minPanelSize', 'minQuorum'):
            if type(proof.get(key)) is not int or not 0 <= proof[key] < 2**64:
                raise SwornReadError('Invalid oracle evidence number')
        for key in ('name', 'template', 'evidence', 'requestId', 'oracleRequestId', 'target'):
            if not isinstance(proof.get(key), str) or len(proof[key]) > 2048:
                raise SwornReadError('Invalid oracle evidence text')
        if not address(proof['target']) or any(not re.fullmatch(r'0x[0-9a-fA-F]{64}', proof[k]) for k in ('requestId', 'oracleRequestId')):
            raise SwornReadError('Invalid oracle evidence identity')
    claims = [a.get('value') for a in data['attributes'] if isinstance(a, dict) and a.get('trait_type') == 'Claimant']
    if len(claims) != 1 or not address(claims[0]) or claims[0].lower() != claimant.lower():
        raise SwornReadError('Metadata claimant mismatch')


def decode_metadata(uri, claimant):
    try:
        if not isinstance(uri, str) or len(uri) > MAX_URI or not uri.startswith('data:application/json;base64,'):
            raise SwornReadError('Unsupported token metadata')
        data = json.loads(base64.b64decode(uri.split(',', 1)[1], validate=True))
        validate_metadata(data, claimant)
        image = data.pop('image')
        if not isinstance(image, str) or not image.startswith('data:image/svg+xml,'):
            raise SwornReadError('Unsupported card artwork')
        svg = unquote(image.split(',', 1)[1], errors='strict')
        if len(svg.encode()) > MAX_SVG or not svg.lstrip().startswith('<svg'):
            raise SwornReadError('Invalid card artwork')
        return data, svg
    except (KeyError, ValueError, TypeError, UnicodeError) as error:
        raise SwornReadError('Invalid card metadata or artwork') from error


class SwornClient(OwnedHttpClient):
    def __init__(self, *, http_client=None, endpoints=ENDPOINTS):
        self._client = http_client or httpx.AsyncClient(timeout=8.0)
        self._owns_client = http_client is None
        self.endpoints = tuple(endpoints)

    async def _batch(self, methods):
        queries = [{'jsonrpc': '2.0', 'id': i, 'method': m, 'params': p} for i, (m, p) in enumerate(methods)]
        for endpoint in self.endpoints:
            try:
                async with self._client.stream('POST', endpoint, json=queries, timeout=8.0) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 4_000_000:
                            raise SwornReadError('RPC response exceeds card budget')
                replies = json.loads(body)
                if not isinstance(replies, list) or len(replies) != len(queries):
                    raise SwornReadError('Incomplete RPC batch')
                indexed = {r['id']: r for r in replies if isinstance(r, dict) and type(r.get('id')) is int}
                if set(indexed) != set(range(len(queries))) or any('error' in r or not isinstance(r.get('result'), str) for r in indexed.values()):
                    raise SwornReadError('Incomplete RPC batch')
                return [indexed[i]['result'] for i in range(len(queries))]
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                continue
        raise SwornReadError('Sworn read did not complete')

    async def _calls(self, block, signatures):
        return await self._batch([('eth_call', [{'to': BINDING['registry'], 'data': selector(s) + arg}, hex(block)]) for s, arg in signatures])

    async def fetch(self, selection=None):
        chain, head = await self._batch([('eth_chainId', []), ('eth_blockNumber', [])])
        if int(chain, 16) != BINDING['chain_id']:
            raise SwornReadError('Sworn requires Ethereum mainnet')
        block = int(head, 16)
        renderer, composer, supply = await self._calls(block, [('renderer()', ''), ('composer()', ''), ('totalSupply()', '')])
        if abi_address(renderer) != BINDING['renderer'] or abi_address(composer) != BINDING['composer']:
            raise SwornReadError('Sworn deployment binding changed')
        supply = word(supply)
        if address(selection):
            found, = await self._calls(block, [('tokenOf(address)', selection[2:].lower().zfill(64))])
            token_id = word(found)
        else:
            token_id = int(selection) if selection is not None else supply
        result = {'supply': supply, 'block': block, 'card': None, 'error': None}
        if token_id == 0 or token_id > supply:
            result['error'] = 'No minted card for this claimant' if address(selection) else 'No minted card with this ID'
            return result
        if token_id < 0 or token_id >= 2**256:
            raise SwornReadError('Invalid token ID')
        arg = f'{token_id:064x}'
        claimant, holder, minted, uri = await self._calls(block, [(s, arg) for s in ('claimantOf(uint256)', 'ownerOf(uint256)', 'mintedAtBlock(uint256)', 'tokenURI(uint256)')])
        claimant, holder = abi_address(claimant), abi_address(holder)
        metadata, svg = decode_metadata(decode_string(uri, max_len=MAX_URI), claimant)
        result['card'] = {'token_id': token_id, 'claimant': claimant, 'holder': holder,
                          'minted_at_block': word(minted), 'metadata': metadata, 'svg': svg}
        return result
