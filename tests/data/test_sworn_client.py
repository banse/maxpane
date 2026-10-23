"""Captured mainnet read replies; injected transport never opens a socket."""
import base64
import copy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.sworn_client import SwornClient, SwornReadError, decode_metadata, selector

FIXTURE = json.loads((Path(__file__).parents[1] / 'fixtures/sworn/token_1_rpc.json').read_text())
CLAIMANT = '0xe5b1275fb926613d983da33fbfe1f331b7f64f2a'
HOLDER = '0x' + 'a' * 40


def transport(*, replace=None):
    requests = []
    calls = {selector(k): v for k, v in FIXTURE['calls'].items()}
    def respond(request):
        batch = json.loads(request.content)
        requests.append(batch)
        replies = []
        for q in batch:
            if q['method'] == 'eth_chainId':
                result = {'result': '0x1'}
            elif q['method'] == 'eth_blockNumber':
                result = {'result': FIXTURE['provenance']['block']}
            else:
                assert q['method'] == 'eth_call'
                assert q['params'][1] == FIXTURE['provenance']['block']
                result = copy.deepcopy(calls[q['params'][0]['data'][:10]])
            if replace:
                result = replace(q, result)
            replies.append({**result, 'jsonrpc': '2.0', 'id': q['id']})
        return httpx.Response(200, json=list(reversed(replies)))
    return httpx.MockTransport(respond), requests


async def test_pinned_reads_and_transferred_holder_remains_separate():
    def transferred(q, result):
        if q['method'] == 'eth_call' and q['params'][0]['data'].startswith(selector('ownerOf(uint256)')):
            return {'result': '0x' + HOLDER[2:].zfill(64)}
        return result
    mock, requests = transport(replace=transferred)
    async with httpx.AsyncClient(transport=mock) as http:
        client = SwornClient(http_client=http, endpoints=('https://test.invalid',))
        result = await client.fetch('1')
        assert result['supply'] == 10
        assert result['card']['claimant'] == CLAIMANT
        assert result['card']['holder'] == HOLDER
        assert result['card']['metadata']['traits'] == []
        assert result['card']['svg'].startswith('<svg')
        assert len(requests) == 3
        assert sum(len(x) for x in requests) == 9
        await client.close()
        assert not http.is_closed


@pytest.mark.parametrize('signature,bad', [('renderer()', '0x'+'0'*64), ('composer()', '0x'), ('totalSupply()', '0x')])
async def test_missing_or_wrong_binding_never_returns_an_empty_collection(signature, bad):
    def corrupt(q, result):
        if q['method'] == 'eth_call' and q['params'][0]['data'] == selector(signature):
            return {'result': bad}
        return result
    mock, _ = transport(replace=corrupt)
    async with httpx.AsyncClient(transport=mock) as http:
        client = SwornClient(http_client=http, endpoints=('https://test.invalid',))
        with pytest.raises(SwornReadError):
            await client.fetch('1')


async def test_wrong_chain_rejected_before_contract_reads():
    mock, requests = transport(replace=lambda q, v: {'result': '0x2105'} if q['method']=='eth_chainId' else v)
    async with httpx.AsyncClient(transport=mock) as http:
        with pytest.raises(SwornReadError):
            await SwornClient(http_client=http, endpoints=('https://test.invalid',)).fetch('1')
    assert len(requests) == 1


async def test_card_read_error_is_unknown_not_unminted():
    mock, _ = transport(replace=lambda q, v: {'error': {'message': 'execution failed'}} if q['method']=='eth_call' and q['params'][0]['data'].startswith(selector('tokenURI(uint256)')) else v)
    async with httpx.AsyncClient(transport=mock) as http:
        with pytest.raises(SwornReadError):
            await SwornClient(http_client=http, endpoints=('https://test.invalid',)).fetch('1')


@pytest.mark.parametrize('found', [0, 1])
async def test_claimant_lookup_uses_token_of_without_scanning_holders(found):
    calls = []
    def lookup(q, result):
        if q['method'] == 'eth_call':
            calls.append(q['params'][0]['data'])
        return result
    base_mock, requests = transport(replace=lookup)
    def respond(request):
        batch = json.loads(request.content)
        if len(batch) == 1 and batch[0]['params'][0]['data'].startswith(selector('tokenOf(address)')):
            calls.append(batch[0]['params'][0]['data'])
            return httpx.Response(200, json=[{'jsonrpc':'2.0', 'id':batch[0]['id'], 'result':'0x'+f'{found:064x}'}])
        return base_mock.handler(request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await SwornClient(http_client=http, endpoints=('https://test.invalid',)).fetch(CLAIMANT)
    assert (result['card'] is None) == (found == 0)
    assert selector('tokenOf(address)') + CLAIMANT[2:].zfill(64) in calls
    assert not any(q.startswith(selector('balanceOf(address)')) for q in calls)


async def test_observed_zero_supply_is_a_real_zero_without_card_reads():
    def empty(q, result):
        if q['method']=='eth_call' and q['params'][0]['data']==selector('totalSupply()'):
            return {'result':'0x'+'0'*64}
        return result
    mock, requests = transport(replace=empty)
    async with httpx.AsyncClient(transport=mock) as http:
        result = await SwornClient(http_client=http, endpoints=('https://test.invalid',)).fetch()
    assert result['supply'] == 0 and result['card'] is None
    assert len(requests) == 2


def test_standard_selectors_match_erc721_abi():
    assert selector('tokenURI(uint256)') == '0xc87b56dd'
    assert selector('ownerOf(uint256)') == '0x6352211e'
    assert selector('totalSupply()') == '0x18160ddd'


def test_metadata_rejects_nondata_images_and_claimant_mismatch():
    from maxpane_dashboard.data.evm_abi import decode_string
    uri = decode_string(FIXTURE['calls']['tokenURI(uint256)']['result'], max_len=1_000_000)
    data = json.loads(base64.b64decode(uri.split(',', 1)[1]))
    def encode():
        return 'data:application/json;base64,' + base64.b64encode(json.dumps(data).encode()).decode()
    with pytest.raises(SwornReadError):
        decode_metadata(encode(), HOLDER)
    data['image'] = 'https://attacker.invalid/image.svg'
    with pytest.raises(SwornReadError):
        decode_metadata(encode(), CLAIMANT)


@pytest.mark.parametrize('field,entry', [
    ('attributes', None), ('attributes', {'trait_type': 'Spawned', 'value': {'held': True}}),
    ('attributes', {'trait_type': ['Claimant'], 'value': CLAIMANT}),
    ('oracle', None), ('oracle', {'traitId': '601'}),
])
def test_metadata_rejects_malformed_list_members(field, entry):
    from maxpane_dashboard.data.evm_abi import decode_string
    uri = decode_string(FIXTURE['calls']['tokenURI(uint256)']['result'], max_len=1_000_000)
    data = json.loads(base64.b64decode(uri.split(',', 1)[1]))
    data[field].append(entry)
    encoded = 'data:application/json;base64,' + base64.b64encode(json.dumps(data).encode()).decode()
    with pytest.raises(SwornReadError):
        decode_metadata(encoded, CLAIMANT)


def test_metadata_accepts_typed_oracle_evidence_shape():
    """Synthetic mutation of the capture; exercises Renderer._oracle's shape."""
    from maxpane_dashboard.data.evm_abi import decode_string
    uri = decode_string(FIXTURE['calls']['tokenURI(uint256)']['result'], max_len=1_000_000)
    data = json.loads(base64.b64decode(uri.split(',', 1)[1]))
    proof = {'traitId':601, 'template':'T5', 'evidence':'panel', 'fromBlock':10, 'toBlock':20,
             'minPanelSize':11, 'minQuorum':7, 'requestId':'0x'+'1'*64,
             'oracleRequestId':'0x'+'2'*64, 'target':CLAIMANT, 'name':'Swarmed'}
    data['oracle'] = [proof]
    encoded = 'data:application/json;base64,' + base64.b64encode(json.dumps(data).encode()).decode()
    metadata, _ = decode_metadata(encoded, CLAIMANT)
    assert metadata['oracle'] == [proof]
