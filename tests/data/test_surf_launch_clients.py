import json
import httpx
import pytest
from tests.analytics.test_surf_launch_checks import fixture, evidence
from maxpane_dashboard.data.surf_swarm_client import SwarmClient
from maxpane_dashboard.data.surf_client import SurfClient
from maxpane_dashboard.data.surf_launch_base_client import SwarmBaseClient
from maxpane_dashboard.data.surf_launch_rh_client import SwarmRobinhoodClient

@pytest.mark.asyncio
async def test_launch_routes_use_fixed_limit_uuid_and_busy_is_unavailable():
    seen = []
    def respond(request):
        seen.append(request)
        if request.url.path == '/launches':
            return httpx.Response(200, json=fixture('launches_100'))
        if request.url.path == '/launch/policies':
            return httpx.Response(200, json=fixture('launch_policies'))
        return httpx.Response(503, json={'error': 'busy'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = SwarmClient(http_client=http, inter_call_delay=0)
        assert len(await client.fetch_launches()) == 100
        assert seen[0].url.params['limit'] == '100'
        assert await client.fetch_launch(fixture('launch_737')['id']) is None
        assert await client.fetch_launch('../escape') is None
        assert len(await client.fetch_launch_policies()) == 27

@pytest.mark.asyncio
@pytest.mark.parametrize('cls', [SwarmBaseClient, SwarmRobinhoodClient, SurfClient])
async def test_chain_launch_rpc_batches_reads_and_rotates(cls):
    row, rpc = evidence(737); posted = []
    def respond(request):
        posted.append(json.loads(request.content))
        if len(posted) == 1:
            return httpx.Response(521)
        result = []
        for call in posted[-1]:
            source = {'eth_getTransactionByHash': rpc['transactions'], 'eth_getTransactionReceipt': rpc['receipts'], 'eth_getCode': rpc['codes']}[call['method']]
            result.append({'jsonrpc': '2.0', 'id': call['id'], 'result': source.get(call['params'][0])})
        return httpx.Response(200, json=list(reversed(result)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = cls(http_client=http, inter_call_delay=0) if cls is SurfClient else cls(http_client=http)
        out = await client.fetch_launch_evidence(list(rpc['transactions']), list(rpc['codes']))
        assert out == rpc
        assert len(posted) == 2 and len(posted[0]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('cls', [SwarmBaseClient, SwarmRobinhoodClient, SurfClient])
async def test_pool_storage_batch_keeps_independent_missing_items(cls):
    from tests.analytics.test_surf_launch_liquidity import live_fixture
    from maxpane_dashboard.analytics import surf_launch_liquidity as ll
    from maxpane_dashboard.data.keccak import keccak256
    _,pool,answers,_=live_fixture(791 if cls is SwarmRobinhoodClient else 737)
    calls=ll.state_calls(pool,keccak=keccak256)
    posted=[]
    def respond(request):
        batch=json.loads(request.content); posted.append(batch)
        return httpx.Response(200,json=list(reversed([
            dict(jsonrpc='2.0',id=c['id'],**({'error':{'code':-32000,'message':'execution reverted'}} if i==1 else {'result':answers[i]}))
            for i,c in enumerate(batch)])))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client=cls(http_client=http,inter_call_delay=0) if cls is SurfClient else cls(http_client=http)
        assert await client.fetch_launch_pool_state(calls)==[answers[0],None,answers[2]]
        assert [[c['method'],c['params']] for c in posted[0]]==[[method,params] for method,params in calls]
