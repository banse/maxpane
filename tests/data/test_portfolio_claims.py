"""Captured public claim facts, with transport-only synthetic failure variants."""
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.portfolio_claims_client import PortfolioClaimsClient

FIXTURES = Path(__file__).parents[1] / 'fixtures/portfolio/claims'
WALLET = '0x65fcec1f5bfa9c8d8b93bc1dba740b5977019696'
OTHER = '0x1111111111111111111111111111111111111111'
LAUNCH = 'c792b3eb-7f6d-495d-89f2-0bdf03c67edd'
SECOND = 'da96d809-3473-4ad0-b8ed-54acaff7c647'


def fixture(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


class PublicReads:
    def __init__(self):
        self.earned = {'claimable': [LAUNCH], 'unlocks': []}
        self.claim = fixture('claim')
        self.launch = fixture('launch')
        self.agents = fixture('agents')
        capture = fixture('rpc')
        self.block = capture['block']['result']
        self.responses = {req['params'][0]['data'][:10]: next(r['result'] for r in capture['responses'] if r['id'] == req['id']) for req in capture['requests']}
        self.fail = set()
        self.requests = []
        self.chain = '0x1'

    def __call__(self, request):
        self.requests.append(request)
        if request.url.path in self.fail or request.method in self.fail:
            return httpx.Response(503)
        if request.method == 'GET':
            if request.url.path == '/api/earned': data = self.earned
            elif request.url.path == '/api/claim': data = self.claim
            elif request.url.path.startswith('/pair/wallet/'):
                data = deepcopy(self.agents)
                data['wallet'] = request.url.path.rsplit('/', 1)[-1]
            elif request.url.path.startswith('/launches/'):
                data = deepcopy(self.launch)
                data['id'] = request.url.path.rsplit('/', 1)[-1]
            else: raise AssertionError(request.url)
            return httpx.Response(200, json=data)
        batch = json.loads(request.content)
        assert isinstance(batch, list)
        result = []
        for call in batch:
            method = call['method']
            if method == 'eth_chainId': value = self.chain
            elif method == 'eth_getBlockByNumber': value = self.block
            elif method == 'eth_call':
                assert call['params'][1] == self.block['number']
                value = self.responses.get(call['params'][0]['data'][:10])
            else: raise AssertionError(method)
            result.append({'jsonrpc': '2.0', 'id': call['id'], 'result': value})
        return httpx.Response(200, json=result)


@pytest.fixture
def reads():
    return PublicReads()


def client(reads, **kwargs):
    return PortfolioClaimsClient(transport=httpx.MockTransport(reads), clock=lambda: 1800000000, inter_call_delay=0, rpcs={1: ('https://state.example',)}, **kwargs)


@pytest.mark.asyncio
async def test_public_proof_and_fixed_block_reads_prove_ready_without_agent_multiplier(reads):
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    row, = result['allocations']
    assert row['claim_state'] == 'ready'
    assert row['claim_read_state'] == 'ok'
    assert row['claimable_quantity'] == pytest.approx(95351.60905840286)
    assert row['claim_raw'] == 95351609058402860548272
    assert row['decimals'] == 18
    assert row['claim_block'] == int(reads.block['number'], 16)
    assert row['claim_read_at'] == 1800000000
    assert result['agents'][0]['id'] == '52152'
    assert result['agents'][0]['online'] is True
    assert result['sources']['claims']['complete'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('offset,state', [(-1, 'locked'), (0, 'ready'), (1, 'ready')])
async def test_unlock_boundary_uses_chain_timestamp_not_local_clock(reads, offset, state):
    unlock = int(reads.responses['0xc7c38091'][-64:], 16)
    reads.block['timestamp'] = hex(unlock + offset)
    reads.earned['unlocks'] = [{'id': LAUNCH, 'at': '2099-01-01T00:00:00.000Z'}]
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    row, = result['allocations']
    assert row['claim_state'] == state
    assert row['claimable_quantity'] > 0 if state == 'ready' else row['locked_quantity'] > 0


@pytest.mark.asyncio
@pytest.mark.parametrize('selector,value,expected', [
    ('0x120aa877', '0x' + format(1, '064x'), 'claimed'),
    ('0x6d05936d', '0x' + format(1, '064x'), 'none'),
    ('0x120aa877', '0x', 'unavailable'),
    ('0x313ce567', '0x', 'unavailable'),
    ('0xfc0c546a', '0x' + '0' * 64, 'unavailable'),
    ('0x70a08231', '0x' + '0' * 64, 'unavailable'),
])
async def test_claimed_closed_and_missing_or_conflicting_read_never_ready(reads, selector, value, expected):
    reads.responses[selector] = value
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    row, = result['allocations']
    assert row['claim_state'] == expected
    assert row['claimable_quantity'] in (0, None)
    if expected == 'unavailable': assert not result['sources']['claims']['complete']


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('amount', '-1'), ('amount', 'NaN'), ('proof', []), ('root', '0x' + '0' * 64)])
async def test_invalid_or_conflicting_proof_never_becomes_numeric_ready(reads, field, value):
    reads.claim['claim'][field] = value
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert result['allocations'][0]['claimable_quantity'] is None
    assert not result['sources']['claims']['complete']


@pytest.mark.asyncio
async def test_null_allocation_and_successful_empty_are_distinct_from_failed_read(reads):
    reads.claim = fixture('no_allocation')
    async with client(reads) as api:
        null = await api.fetch_claims(WALLET)
        reads.earned = {'claimable': [], 'unlocks': []}
        empty = await api.fetch_claims(OTHER)
        reads.fail.add('/api/earned')
        failed = await api.fetch_claims('0x' + '2' * 40)
    assert null['allocations'][0]['claim_state'] == 'none'
    assert null['allocations'][0]['claimable_quantity'] == 0
    assert empty['allocations'] == [] and empty['sources']['claims']['complete']
    assert failed['allocations'] is None and not failed['sources']['claims']['complete']


@pytest.mark.asyncio
async def test_duplicate_launch_ids_and_same_leaf_are_counted_once(reads):
    reads.earned['claimable'] = [LAUNCH, LAUNCH, SECOND]
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert len(result['allocations']) == 1
    assert set(result['allocations'][0]['launch_uuids']) == {LAUNCH, SECOND}
    assert sum(r.url.path == '/api/claim' for r in reads.requests) == 2


@pytest.mark.asyncio
async def test_bounded_progress_does_not_certify_unread_claims_or_erase_prior_rows(reads):
    reads.earned['claimable'] = [LAUNCH, SECOND]
    async with client(reads, max_launches=1) as api:
        first = await api.fetch_claims(WALLET)
        second = await api.fetch_claims(WALLET)
    assert first['sources']['claims']['checked'] == 1
    assert first['sources']['claims']['total'] == 2
    assert first['sources']['claims']['complete'] is False
    assert second['sources']['claims']['complete'] is True
    assert len(second['allocations']) == 1


@pytest.mark.asyncio
async def test_failed_refresh_retains_old_ready_as_stale_and_agents_are_independent(reads):
    async with client(reads) as api:
        first = await api.fetch_claims(WALLET)
        reads.fail.add('/api/earned')
        reads.agents['tokens'][0]['device']['online'] = False
        later = await api.fetch_claims(WALLET)
    assert later['allocations'][0]['claim_read_state'] == 'stale'
    assert later['allocations'][0]['claim_read_at'] == first['allocations'][0]['claim_read_at']
    assert later['sources']['claims']['state'] == 'stale'
    assert later['agents'][0]['online'] is False


@pytest.mark.asyncio
async def test_current_missing_devices_do_not_erase_historical_allocation(reads):
    reads.agents['tokens'] = []
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert result['allocations'][0]['claim_state'] == 'ready'
    assert result['agents'] == []


@pytest.mark.asyncio
async def test_pagination_marker_and_wrong_chain_never_certify_complete(reads):
    reads.earned['nextCursor'] = 'more'
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert result['allocations'] is None
    reads.earned.pop('nextCursor')
    reads.chain = '0x2105'
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert result['allocations'][0]['claim_read_state'] == 'unavailable'


@pytest.mark.asyncio
async def test_invalid_wallet_is_refused_before_network(reads):
    async with client(reads) as api:
        result = await api.fetch_claims('../malformed')
    assert result['allocations'] is None
    assert reads.requests == []


@pytest.mark.asyncio
async def test_cancelled_cycle_retries_every_unread_launch(reads):
    import asyncio
    reads.earned['claimable'] = [LAUNCH, SECOND]
    async with client(reads, max_launches=1) as api:
        original = api._allocation
        entered = asyncio.Event()
        async def delayed(*args):
            entered.set()
            await asyncio.Event().wait()
        api._allocation = delayed
        task = asyncio.create_task(api.fetch_claims(WALLET))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        api._allocation = original
        result = await api.fetch_claims(WALLET)
    assert result['allocations'][0]['launch_uuid'] == LAUNCH
    assert result['sources']['claims']['total'] == 2
    assert result['sources']['claims']['complete'] is False


@pytest.mark.asyncio
async def test_live_decimals_and_partly_used_round_keep_wallet_entitlement(reads):
    reads.responses['0x313ce567'] = '0x' + format(6, '064x')
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    row, = result['allocations']
    # Capture has nonzero round-wide claimed value, but this wallet is unclaimed.
    assert row['claim_state'] == 'ready'
    assert row['claimable_quantity'] == int(reads.claim['claim']['amount']) / 10**6
    assert row['claimed_quantity'] == 0


@pytest.mark.asyncio
async def test_failed_agent_lookup_and_offline_entitlement_are_independent(reads):
    reads.fail.add('/pair/wallet/' + WALLET)
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert result['agents'] is None
    assert result['sources']['agents']['state'] == 'unavailable'
    assert result['allocations'][0]['claim_state'] == 'ready'


@pytest.mark.asyncio
async def test_unsupported_chain_and_ambiguous_artifact_are_explicit(reads):
    reads.launch['chainId'] = 11155111
    async with client(reads) as api:
        unsupported = await api.fetch_claims(WALLET)
    assert unsupported['allocations'][0]['claim_read_state'] == 'unsupported'
    reads.launch['chainId'] = 1
    reads.launch['artifacts'].append({'role': 'token', 'address': OTHER})
    async with client(reads) as api:
        ambiguous = await api.fetch_claims(WALLET)
    assert ambiguous['allocations'][0]['claimable_quantity'] is None
    assert ambiguous['sources']['claims']['complete'] is False


@pytest.mark.asyncio
async def test_out_of_range_unlock_is_unavailable_not_a_client_crash(reads):
    reads.responses['0xc7c38091'] = reads.responses['0xc7c38091'][:-64] + format(2**64 - 1, '064x')
    async with client(reads) as api:
        result = await api.fetch_claims(WALLET)
    assert result['allocations'][0]['claimable_quantity'] is None
    assert result['sources']['claims']['complete'] is False
