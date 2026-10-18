import asyncio
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.surf_nft_client import (
    Budget, BudgetExhausted, SourceUnavailable, SurfNftClient,
)

FIXTURE = json.loads((Path(__file__).parents[1] / 'fixtures/surf/nft/discovery/public.json').read_text())


def budget(**kwargs):
    return Budget(monotonic=lambda: 1., **kwargs)


def client(handler, **kwargs):
    return SurfNftClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                         inter_call_delay=0, clock=lambda: 100., monotonic=lambda: 1., **kwargs)


@pytest.mark.asyncio
async def test_attempts_and_rpc_ids_are_bound_separately():
    sent = []
    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json=[{'jsonrpc':'2.0','id':item['id'],'result':value}
                                      for item,value in reversed(list(zip(body,FIXTURE['rpc_results'])))])
    c, b = client(handler), budget(http_limit=1, rpc_limit=2)
    assert await c.rpc_batch(1, [('eth_chainId',[]),('eth_blockNumber',[])], budget=b) == ['0x1','0x64']
    assert (b.http_attempts,b.rpc_calls,len(sent)) == (1,2,1)
    with pytest.raises(BudgetExhausted):
        await c.rpc(1,'eth_chainId',[],budget=b)
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_retry_after_prevents_same_host_retry_and_counts_rotation():
    seen=[]
    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(429,headers={'Retry-After':'60'})
    c,b=client(handler),budget()
    with pytest.raises(SourceUnavailable):
        await c.page('launches',budget=b)
    with pytest.raises(SourceUnavailable):
        await c.page('launches',budget=b)
    assert len(seen)==b.http_attempts==2
    assert len(set(seen))==2


@pytest.mark.asyncio
async def test_cursor_regression_and_timestamp_tie_do_not_certify_end():
    data=FIXTURE['jobs']
    c=client(lambda _:httpx.Response(200,json=data))
    with pytest.raises(SourceUnavailable):
        await c.page('jobs',cursor=data['jobs'][0]['createdAt'],budget=budget())
    rows=[dict(data['jobs'][0],id=f'20000000-0000-4000-8000-{i:012d}') for i in range(100)]
    c=client(lambda _:httpx.Response(200,json={'jobs':rows}))
    p=await c.page('jobs',budget=budget())
    assert not p.terminal and p.warning == 'timestamp_boundary_tie'


@pytest.mark.asyncio
async def test_source_urls_and_read_methods_rejected_before_send():
    seen=[]
    c=client(lambda r:seen.append(r) or httpx.Response(200,json={}))
    for url in ['https://127.0.0.1/private','https://raw.githubusercontent.com/u/r/main/a.sol',
                'https://raw.githubusercontent.com/u/r/'+'a'*40+'/../a.sol']:
        with pytest.raises(ValueError):
            await c.source_text(url,budget=budget())
    with pytest.raises(ValueError):
        await c.rpc(1,'eth_sendRawTransaction',['0x00'],budget=budget())
    assert seen==[]


@pytest.mark.asyncio
async def test_oversize_and_wrong_rpc_ids_are_failures():
    c=client(lambda _:httpx.Response(200,content=b'x'*1025),max_response_bytes=1024)
    with pytest.raises(SourceUnavailable):
        await c.page('jobs',budget=budget())
    c=client(lambda _:httpx.Response(200,json={'jsonrpc':'2.0','id':999,'result':'0x1'}))
    with pytest.raises(SourceUnavailable):
        await c.rpc(1,'eth_chainId',[],budget=budget())


def test_shared_job_reservations_are_not_physical_request_counts():
    b=budget(http_limit=3)
    b.reserve_shared_job()
    assert (b.reserved_http,b.http_attempts)==(2,0)
    b.consume(http=1)
    with pytest.raises(BudgetExhausted):
        b.reserve_shared_job()
    b.refund_shared_job()
    assert b.can_admit(http=2)


@pytest.mark.asyncio
async def test_concurrency_cap_and_cancelled_queue_do_not_spend_attempt():
    entered=asyncio.Event(); release=asyncio.Event(); active=peak=0
    async def handler(request):
        nonlocal active,peak
        active+=1; peak=max(peak,active)
        if active==2: entered.set()
        await release.wait(); active-=1
        return httpx.Response(200,json={'sites':[]})
    c=client(handler); b=budget()
    tasks=[asyncio.create_task(c.page('sites',budget=b)) for _ in range(5)]
    await entered.wait()
    tasks[-1].cancel()
    release.set()
    await asyncio.gather(*tasks,return_exceptions=True)
    assert peak==2 and b.http_attempts==4


def test_nested_budget_limit_retains_global_counts_and_restores_on_pause():
    b=budget(http_limit=24,rpc_limit=256)
    b.consume(http=2,rpc=4)
    with b.limit(http=2,rpc=3):
        b.consume(http=2,rpc=3)
        assert not b.can_admit()
    assert (b.http_limit,b.rpc_limit,b.http_attempts,b.rpc_calls)==(24,256,4,7)


@pytest.mark.asyncio
async def test_rotated_endpoint_must_prove_chain_before_serving_data():
    seen=[]
    def handler(request):
        body=json.loads(request.content); seen.append((request.url.host,body['method']))
        if request.url.host=='ethereum-rpc.publicnode.com':return httpx.Response(503)
        return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],'result':'0x2105'})
    c,b=client(handler),budget()
    with pytest.raises(SourceUnavailable):
        await c.rpc(1,'eth_getCode',['0x'+'1'*40,'latest'],budget=b)
    assert all(method=='eth_chainId' for _,method in seen)
    assert b.http_attempts==2 and b.rpc_calls==3


@pytest.mark.asyncio
async def test_single_rpc_verifies_chain_and_records_completion_clock():
    seen=[]
    def handler(request):
        body=json.loads(request.content); seen.append(body['method'])
        return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],
                                       'result':'0x1' if body['method']=='eth_chainId' else '0x6000'})
    c,b=client(handler),budget()
    assert await c.rpc(1,'eth_getCode',['0x'+'1'*40,'latest'],budget=b)=='0x6000'
    assert seen==['eth_chainId','eth_getCode'] and b.http_attempts==2


@pytest.mark.asyncio
async def test_response_observation_uses_completion_time_and_unknown_is_not_empty():
    wall=[100.]
    def handler(request):
        wall[0]=130.
        return httpx.Response(200,json={'launches':[]})
    c=SurfNftClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                    clock=lambda:wall[0],inter_call_delay=0)
    page=await c.page('launches',budget=Budget())
    assert page.rows==[] and page.terminal and page.observed_at==130.
    invalid=client(lambda _:httpx.Response(200,json={'launches':None}))
    with pytest.raises(SourceUnavailable):
        await invalid.page('launches',budget=budget())


@pytest.mark.asyncio
async def test_rpc_rotation_preserves_bounded_provider_error_text():
    def handler(request):
        body=json.loads(request.content)
        response={'jsonrpc':'2.0','id':body['id']}
        if body['method']=='eth_chainId':
            response['result']='0x1'
        else:
            response['error']={'code':-32000,'message':'missing trie node: historical state unavailable\n'+'x'*5000}
        return httpx.Response(200,json=response)
    c=client(handler)
    with pytest.raises(SourceUnavailable) as caught:
        await c.rpc(1,'eth_getCode',['0x'+'11'*20,'0x100'],budget=budget())
    message=str(caught.value)
    assert 'missing trie node: historical state unavailable' in message
    assert len(message)<600 and '\n' not in message


@pytest.mark.asyncio
async def test_real_client_archive_error_restarts_inspector_pinned_stage():
    from tests.data.test_surf_nft_chain import FakeRPC, ADDRESS, TX
    from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector
    rpc=FakeRPC()
    fail=[True]
    def handler(request):
        body=json.loads(request.content)
        response={'jsonrpc':'2.0','id':body['id']}
        if body['method']=='eth_getCode' and fail[0]:
            response['error']={'code':-32000,'message':'missing trie node: historical state unavailable'}
        elif body['method']=='eth_blockNumber' and not fail[0]:
            response['result']='0x200'
        else:
            response['result']=rpc(1,body['method'],body['params'])
        return httpx.Response(200,json=response)
    c=client(handler)
    inspector=SurfNftInspector(c,clock=lambda:1792200000.)
    candidate={'chainId':1,'address':ADDRESS,'artifact':{'txHash':TX}}
    first=await inspector.advance(candidate,None,budget=budget(http_limit=7))
    assert first.progress['block_number']==256
    second=await inspector.advance(candidate,first.progress,budget=budget(http_limit=4))
    assert 'historical state unavailable' in second.progress.get('restart_reason','')
    assert second.evidence is None and second.complete is False
    fail[0]=False
    third=await inspector.advance(candidate,second.progress,budget=budget(http_limit=3))
    assert third.progress['block_number']==512
    assert third.progress['responses']
    assert not any('"0x100"' in key for key in third.progress['responses'])


@pytest.mark.parametrize('revision', ['a' * 40, None])
async def test_readme_uses_only_validated_public_root_path_and_optional_ref(revision):
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/surf/nft/readme/intro.json').read_text())
    sent = []
    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=fixture)
    c, b = client(handler), budget(http_limit=1)
    result = await c.readme('https://github.com/example/collection', revision, budget=b)
    assert result.payload['state'] == 'ok' and result.observed_at == 100
    assert len(sent) == b.http_attempts == 1
    request = sent[0]
    assert request.url.host == 'api.github.com'
    assert request.url.path == '/repos/example/collection/contents/README.md'
    assert dict(request.url.params) == ({'ref': revision} if revision else {})
    assert not any(key.lower() in ('authorization', 'x-api-key') for key in request.headers)


@pytest.mark.parametrize('status', [302, 403, 429, 500])
async def test_readme_failure_never_follows_redirects_or_download_urls(status):
    sent = []
    c = client(lambda request: sent.append(request) or httpx.Response(
        status, headers={'Location': 'http://127.0.0.1/private', 'Retry-After': '60'}))
    with pytest.raises(SourceUnavailable):
        await c.readme('https://github.com/example/collection', None, budget=budget())
    assert len(sent) == 1


async def test_readme_missing_is_distinct_from_unread_and_bad_metadata_does_not_send():
    sent = []
    c = client(lambda request: sent.append(request) or httpx.Response(404))
    result = await c.readme('https://github.com/example/collection', None, budget=budget())
    assert result.payload['state'] == 'missing' and result.payload['text'] is None
    for repository, revision in [('https://evil.example/a/b', None),
                                 ('https://github.com/example/collection', 'main')]:
        with pytest.raises(ValueError):
            await c.readme(repository, revision, budget=budget())
    assert len(sent) == 1


async def test_readme_uses_cycle_deadline():
    async def handler(request):
        await asyncio.Event().wait()
    c = client(handler)
    with pytest.raises(BudgetExhausted):
        await c.readme('https://github.com/example/collection', None,
                       budget=budget(deadline_seconds=.01))


def test_budget_wall_time_slice_restores_deadline_and_keeps_spent_credits():
    clock = [100.]
    b = Budget(monotonic=lambda: clock[0])
    clock[0] += 2
    with b.limit(http=6, rpc=64, seconds=3):
        assert b.remaining_seconds == 3
        b.consume(http=1, rpc=2)
        with b.limit(http=3, rpc=16, seconds=10):
            assert b.remaining_seconds == 3  # Nested limits never extend a deadline.
        clock[0] += 3
        with pytest.raises(BudgetExhausted):
            b.consume(http=1)
    assert b.remaining_seconds == 10
    assert (b.http_attempts, b.rpc_calls) == (1, 2)
    assert b.can_admit(http=23, rpc=254)
