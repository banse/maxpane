"""R2 NFT budgets use actual MockTransport sends, never live RPCs."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
import pytest

from maxpane_dashboard.data.surf_nft_chain import Inspector, SurfNftInspector, selector
from maxpane_dashboard.data.surf_nft_client import Budget, SourceUnavailable, SurfNftClient
from maxpane_dashboard.data.surf_nft_manager import SurfNftManager
from maxpane_dashboard.data.surf_transport import HostCoordinator, SurfTransport, read_cycle
from tests.data.test_surf_nft_chain import ADDRESS, TX, FakeRPC, word
from tests.data.test_surf_nft_manager import Cache


NOW=1792200000.
CANDIDATE=dict(chainId=1,address=ADDRESS,artifact=dict(name='NFT',txHash=TX),launch={})


class Wire:
    def __init__(self, *, failure=None, chain=1):
        self.rpc=FakeRPC(chain=chain); self.sent=[]; self.failure=failure; self.chain=chain

    def value(self, method, params):
        if method=='eth_call' and not params[0]['data'].startswith('0x01ffc9a7'):
            if params[0]['data']==selector('paused()') and self.failure:
                raise RuntimeError(self.failure)
            return word(1) if params[0]['data']==selector('totalSupply()') else word(0)
        return self.rpc(self.chain,method,params)

    def __call__(self, request):
        body=json.loads(request.content) if request.content else None
        self.sent.append((request.url.host,body))
        if body is None:
            return httpx.Response(200,json={})
        rows=[]
        for call in body if isinstance(body,list) else [body]:
            row=dict(jsonrpc='2.0',id=call['id'])
            try:
                row['result']=self.value(call['method'],call['params'])
            except RuntimeError as error:
                row['error']=dict(code=-32000,message=str(error))
            rows.append(row)
        return httpx.Response(200,json=list(reversed(rows)) if isinstance(body,list) else rows[0])


def client(wire, **kwargs):
    return SurfNftClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(wire)),
                         clock=lambda:NOW,monotonic=lambda:1.,inter_call_delay=0,**kwargs)


def budget(**kwargs):
    return Budget(monotonic=lambda:1.,**kwargs)


async def test_independent_getters_batch_at_one_block_and_reduce_physical_posts():
    serial_wire,batched_wire=Wire(),Wire()
    serial=client(serial_wire); batched=client(batched_wire)
    # A legacy client without rpc_batch exercises the unchanged serial seam.
    legacy=SimpleNamespace(rpc=serial.rpc,source_json=serial.source_json,source_text=serial.source_text)
    before=await SurfNftInspector(legacy,clock=lambda:NOW).advance(CANDIDATE,budget=budget(http_limit=80))
    after=await SurfNftInspector(batched,clock=lambda:NOW).advance(CANDIDATE,budget=budget(http_limit=80))
    assert before.complete and after.complete
    assert after.evidence==before.evidence
    posts=lambda wire:[body for _,body in wire.sent if body is not None]
    assert len(posts(serial_wire))==22
    assert len(posts(batched_wire))==11
    batches=[body for body in posts(batched_wire) if isinstance(body,list)]
    assert len(batches)==1 and len(batches[0])==12
    assert {call['params'][1] for call in batches[0]}=={'0x100'}
    assert sum(body is None for _,body in serial_wire.sent)==sum(body is None for _,body in batched_wire.sent)==2


async def test_batch_field_revert_keeps_other_getters_and_progress_resumes_without_duplicates():
    wire=Wire(failure='execution reverted'); reader=SurfNftInspector(client(wire),clock=lambda:NOW)
    progress=None
    for _ in range(20):
        result=await reader.advance(CANDIDATE,progress,budget=budget(http_limit=3,rpc_limit=5))
        progress=result.progress
        if result.complete:
            break
    assert result.complete
    assert result.evidence['reads']['totalSupply']==1
    assert 'paused' not in result.evidence['reads']
    assert 'execution reverted' in result.evidence['readErrors']['paused']
    calls=[call for _,body in wire.sent if body is not None
           for call in (body if isinstance(body,list) else [body])]
    getters=[call for call in calls if call['method']=='eth_call' and not call['params'][0]['data'].startswith('0x01ffc9a7')]
    assert len(getters)==12
    assert len({json.dumps(call['params'],sort_keys=True) for call in getters})==12
    assert any(isinstance(body,list) for _,body in wire.sent)
    assert all(call['params'][1]=='0x100' for call in getters)


async def test_nft_head_shares_parent_refresh_and_next_refresh_reads_again():
    wire=Wire(); nft=client(wire)
    transport=SurfTransport(delay=0,coordinator=HostCoordinator(monotonic=lambda:1.))
    nft._transport=transport
    @read_cycle
    async def poll():
        first=await nft.rpc(1,'eth_blockNumber',[],budget=budget())
        second=await nft.rpc(1,'eth_blockNumber',[],budget=budget())
        return first,second
    assert await poll()==('0x100','0x100')
    assert await poll()==('0x100','0x100')
    heads=[body for _,body in wire.sent if body and body.get('method')=='eth_blockNumber']
    assert len(heads)==2


async def test_nft_transport_shares_host_pacing_and_cooldown_without_spending_skipped_budget():
    now=[1.]; starts=[]
    async def sleep(delay): now[0]+=delay
    coordinator=HostCoordinator(monotonic=lambda:now[0],clock=lambda:NOW,sleep=sleep)
    transport=SurfTransport(delay=.5,coordinator=coordinator)
    def handler(request):
        starts.append((request.url.host,now[0]))
        return httpx.Response(429,headers={'Retry-After':'60'})
    nft=SurfNftClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                      clock=lambda:NOW,monotonic=lambda:now[0],transport=transport)
    await transport.acquire('https://api.imd.fun/another-path')
    b=Budget(monotonic=lambda:now[0])
    with pytest.raises(SourceUnavailable):
        await nft._request('GET','https://api.imd.fun/sites',budget=b)
    assert starts==[('api.imd.fun',1.5)]
    with pytest.raises(SourceUnavailable):
        await nft._request('GET','https://api.imd.fun/other',budget=b)
    assert b.http_attempts==1 and transport.coordinator.cooling('https://api.imd.fun/')


async def test_boardroom_reuses_unchanged_proof_but_changed_inputs_and_details_stay_due():
    now=[NOW]; wire=Wire(); nft=client(wire)
    manager=SurfNftManager(swarm=SimpleNamespace(),client=nft,cache=Cache(),clock=lambda:now[0],monotonic=lambda:1.)
    candidate=deepcopy(CANDIDATE); identity=f'1:{ADDRESS}'
    manager._candidates=lambda:{identity:candidate}
    async def discover(*_args,**_kwargs): return None
    manager._discover=discover
    await manager._cycle(proof_only=True)
    evidence=deepcopy(manager.state['evidence'][identity]); sent=len(wire.sent)
    assert evidence['deploymentConfirmed'] is True
    assert identity not in manager.state['progress']  # Proven rows cannot fill every bounded stage slot.
    now[0]+=601
    await manager._cycle(proof_only=True)
    assert len(wire.sent)==sent
    assert manager.state['evidence'][identity]==evidence
    assert manager._due(identity)  # Mutable detail enrichment is still required.
    candidate['artifact']['blockNumber']=144
    await manager._cycle(proof_only=True)
    assert len(wire.sent)>sent


async def test_robinhood_inspection_keeps_single_call_transport():
    wire=Wire(chain=4663); nft=client(wire)
    result=await SurfNftInspector(nft,clock=lambda:NOW).advance(
        dict(CANDIDATE,chainId=4663),budget=budget(http_limit=80))
    assert result.complete and result.evidence['stats']['totalSupply']==1
    assert len(wire.sent)==22
    assert all(isinstance(body,dict) for _,body in wire.sent)


async def test_large_getter_set_is_bounded_to_32_entries_per_send():
    wire=Wire(); candidate=deepcopy(CANDIDATE)
    candidate['abi']=[dict(type='function',name=f'getter{i}',stateMutability='view',inputs=[],
                           outputs=[dict(type='uint256')]) for i in range(60)]
    result=await SurfNftInspector(client(wire),clock=lambda:NOW).advance(candidate,budget=budget(http_limit=80))
    assert result.complete and len(result.evidence['reads'])==64
    assert [len(body) for _,body in wire.sent if isinstance(body,list)]==[32,32]


async def test_retained_complete_proof_survives_cache_and_revision_refresh_keeps_detail_clock():
    now=[NOW]; wire=Wire(); candidate=deepcopy(CANDIDATE); identity=f'1:{ADDRESS}'
    cache=Cache(); nft=client(wire)
    manager=SurfNftManager(swarm=SimpleNamespace(),client=nft,cache=cache,clock=lambda:now[0],monotonic=lambda:1.)
    await manager._inspect(identity,candidate,budget(http_limit=80))
    assert identity not in manager.state['progress']
    cache.save(manager.state)
    restored=SurfNftManager(swarm=SimpleNamespace(),client=nft,cache=cache,clock=lambda:now[0],monotonic=lambda:1.)
    restored._candidates=lambda:{identity:candidate}
    async def discover(*_args,**_kwargs): return None
    restored._discover=discover
    now[0]+=121; before=len(wire.sent)
    await restored._cycle(proof_only=True)
    assert len(wire.sent)==before
    old=deepcopy(restored.state['evidence'][identity])
    candidate['launch']['attestation']={'manifest':{'notes':'New proof input'}}
    await restored._cycle(proof_only=True)
    refreshed=restored.state['evidence'][identity]
    assert len(wire.sent)>before and refreshed['checkedAt']==old['checkedAt']
    assert refreshed['reads']==old['reads']
    before=len(wire.sent); now[0]+=601
    await restored._cycle(proof_only=True)
    assert len(wire.sent)==before


async def test_changed_runtime_drops_old_replay_and_failed_proof_remains_retryable():
    now=[NOW]; wire=Wire(); candidate=deepcopy(CANDIDATE); identity=f'1:{ADDRESS}'
    manager=SurfNftManager(swarm=SimpleNamespace(),client=client(wire),cache=Cache(),
                           clock=lambda:now[0],monotonic=lambda:1.)
    manager._candidates=lambda:{identity:candidate}
    async def discover(*_args,**_kwargs): return None
    manager._discover=discover
    await manager._cycle(proof_only=True)
    old=deepcopy(manager.state['evidence'][identity])
    wire.rpc.code='0x6001'
    manager.state['evidence'][identity]['codeHash']='0x'+'f'*64
    before=len(wire.sent)
    await manager._cycle(proof_only=True)
    assert len(wire.sent)>before
    assert manager.state['evidence'][identity]['codeHash'] not in (old['codeHash'],'0x'+'f'*64)
    manager.state['evidence'][identity]['deploymentConfirmed']=False
    now[0]+=601; before=len(wire.sent)
    await manager._cycle(proof_only=True)
    assert len(wire.sent)>before and manager.state['evidence'][identity]['deploymentConfirmed'] is True


async def test_nft_logs_reject_lagging_host_and_budget_every_exact_header():
    seen=[]
    def handler(request):
        body=json.loads(request.content); seen.append((request.url.host,body['method']))
        result='0x1'
        if body['method']=='eth_getBlockByNumber':
            result=None if request.url.host=='gateway.tenderly.co' else {'number':body['params'][0]}
        elif body['method']=='eth_getLogs':
            result=[]
        return httpx.Response(200,json=dict(jsonrpc='2.0',id=body['id'],result=result))
    nft=client(handler); b=budget()
    @read_cycle
    async def read():
        for _ in range(2):
            assert await nft.rpc(1,'eth_getLogs',[dict(fromBlock='0xf0',toBlock='0x100')],budget=b)==[]
    await read()
    assert ('gateway.tenderly.co','eth_getLogs') not in seen
    assert seen.count(('gateway.tenderly.co','eth_getBlockByNumber'))==1
    assert seen.count(('rpc.mevblocker.io','eth_getBlockByNumber'))==1
    assert b.http_attempts==len(seen)==6
    assert b.rpc_calls==6
