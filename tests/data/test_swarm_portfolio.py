"""Public scan contracts and wallet isolation; all transports are injected."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.swarm_portfolio_client import SwarmPortfolioClient, normalize_result
from maxpane_dashboard.data.swarm_portfolio_manager import SwarmPortfolioManager


@pytest.fixture
def capture():
    return json.loads(Path('tests/fixtures/portfolio_scan/captured.json').read_text())


def sample(raw):
    raw = deepcopy(raw)
    token = raw['holdings'][0]['token']
    raw['holdings'] = [dict(raw['holdings'][0], amount=10, value={'usd': 100, 'eth': 1})]
    pos = raw['positions'][0]
    pos['stake'].update(token=token['key'], amount=3, value={'usd': 30, 'eth': .3})
    pos['rewards'] = [dict(token=token['key'], symbol='IMDSTR', amount=.4, value={'usd':4,'eth':.04}, fn='earned')]
    raw['positions'] = [pos]
    claim = raw['claims'][0]
    claim.update(token=token['key'], amount=.3, value={'usd':3,'eth':.03}, unlock=None)
    raw['claims'] = [claim]
    return raw


def test_normalizer_preserves_canonical_exposure_without_counting_rewards_twice(capture):
    raw = sample(capture)
    result = normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    asset = result['assets'][0]
    assert asset['id'] == raw['holdings'][0]['token']['key']
    assert asset['wallet_usd'] == 100 and asset['staked_usd'] == 30
    assert asset['pending_usd'] == 4 and asset['unknown_reward_usd'] == 3
    assert asset['total_usd'] == 137
    assert asset['ready_usd'] == 0
    assert result['rewards'][0]['status'] == 'pending'
    assert result['as_of'] == raw['at']


def test_identity_deduplication_and_conflicts_cannot_inflate_value(capture):
    raw = sample(capture)
    raw['holdings'] *= 2
    result = normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    assert result['assets'][0]['wallet_usd'] == 100
    raw['holdings'][1] = dict(raw['holdings'][1], amount=999)
    result = normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    assert result['state'] == 'partial'
    assert result['coverage']['malformed_rows'] > 0


@pytest.mark.parametrize('change', ['wallet', 'future', 'array'])
def test_invalid_snapshot_rejected(capture, change):
    raw = deepcopy(capture)
    if change == 'wallet': raw['wallet']['address'] = '0x' + '11' * 20
    if change == 'future': raw['at'] += 1000
    if change == 'array': raw['holdings'] = {}
    assert normalize_result(raw, capture['wallet']['address'], now=capture['at']) is None


def test_missing_value_and_incomplete_claims_are_not_zero(capture):
    raw = sample(capture)
    raw['holdings'][0]['value'] = None
    raw['claimsComplete'] = False
    result = normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    assert result['assets'][0]['wallet_usd'] is None
    assert result['state'] == 'partial'
    assert result['coverage']['claims_complete'] is False


def test_missing_quantity_and_nft_count_are_partial_without_destroying_known_values(capture):
    raw=sample(capture)
    raw['holdings'][0]['amount']=None
    raw['nfts'][0]['count']=None
    result=normalize_result(raw,raw['wallet']['address'],now=raw['at'])
    assert result['assets'][0]['wallet_quantity'] is None
    assert result['assets'][0]['wallet_usd']==100
    assert result['nfts'][0]['count'] is None
    assert result['state']=='partial'


def test_string_holding_identity_keeps_value_without_requiring_label_metadata(capture):
    raw=sample(capture)
    identity=raw['holdings'][0]['token']['key']
    raw['holdings'][0]['token']=identity
    result=normalize_result(raw,raw['wallet']['address'],now=raw['at'])
    assert result['assets'][0]['id']==identity
    assert result['assets'][0]['wallet_usd']==100


def test_invalid_nft_contract_identity_marks_coverage_partial(capture):
    raw=sample(capture)
    raw['nfts']=[raw['nfts'][0]]
    raw['nfts'][0]['contract']['address']='broken'
    result=normalize_result(raw,raw['wallet']['address'],now=raw['at'])
    assert result['state']=='partial'
    assert result['coverage']['malformed_rows']==1
    assert result['nfts']==[]


def test_future_unlock_is_locked_and_unproven_readiness_stays_unknown(capture):
    raw = sample(capture)
    raw['claims'][0]['unlock'] = {'unlocksAt': raw['at'] + 60}
    result = normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    assert result['rewards'][1]['status'] == 'locked'
    assert result['assets'][0]['locked_usd'] == 3


async def test_client_fixed_hosts_parameters_and_no_redirects(capture):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'state':'done','result':capture})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SwarmPortfolioClient(http_client=http)
        assert (await client.read(capture['wallet']['address'], fresh=True))['state'] == 'done'
        assert await client.read('not-an-address') is None
        assert len(calls) == 1
        assert calls[0].url.host == 'imd.vibingco.de'
        assert calls[0].url.params['fresh'] == '1'
        await client.close()
        assert not http.is_closed


@pytest.mark.parametrize('body,status', [(b'not json',200),(b'{}',302),
    (json.dumps({'state':'running','log':['x'*(8*1024*1024)]}).encode(),200)],
    ids=['malformed','redirect','oversized'])
async def test_client_refuses_failed_malformed_oversized_reads(body,status,capture):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(status,content=body))) as http:
        assert await SwarmPortfolioClient(http_client=http).read(capture['wallet']['address']) is None


async def test_seats_count_owned_tokens_including_unpaired_and_reject_conflicting_duplicates(capture):
    wallet = capture['wallet']['address']
    body = {'wallet':wallet,'tokens':[{'tokenId':7,'device':{'online':True}}, {'tokenId':'42','device':None}]}
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client=SwarmPortfolioClient(http_client=http)
        seats=await client.read_seats(wallet)
        assert [row['token_id'] for row in seats] == ['7','42']
        assert seats[1]['paired'] is False and seats[1]['online'] is None
        assert requests[0].url.host == 'api.imd.fun'
        assert requests[0].url.path == '/pair/wallet/'+wallet
        body['tokens'].append({'tokenId':7,'device':None})
        assert await client.read_seats(wallet) is None


async def test_timeout_is_an_unavailable_read(capture):
    def handler(request): raise httpx.ReadTimeout('deadline',request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await SwarmPortfolioClient(http_client=http).read(capture['wallet']['address']) is None


class Client:
    def __init__(self, raw): self.raw, self.calls, self.closed = raw, [], False
    async def read(self,wallet,*,fresh=False):
        self.calls.append((wallet,fresh)); return {'state':'done','result':deepcopy(self.raw)}
    async def read_seats(self,wallet): return []
    async def close(self): self.closed=True


async def test_manager_fresh_only_on_explicit_refresh_and_retains_failure(capture):
    client = Client(capture); clock=[capture['at']]
    manager = SwarmPortfolioManager(capture['wallet']['address'],client=client,clock=lambda:clock[0])
    await manager.fetch_and_compute()
    await manager.fetch_and_compute()
    assert not any(fresh for _,fresh in client.calls)
    manager.request_refresh(); await manager.fetch_and_compute()
    assert client.calls[-1][1] is True
    client.raw=None
    result=await manager.fetch_and_compute()
    assert result['state']=='stale' and result['as_of']==capture['at']
    assert result['assets'] is not None
    await manager.close()
    assert not client.closed  # injected clients belong to their caller


async def test_wallet_switch_aba_ignores_late_result_and_close_cancels(capture):
    client=Client(capture); entered=asyncio.Event(); release=asyncio.Event()
    async def slow(wallet,*,fresh=False):
        entered.set()
        try: await release.wait()
        except asyncio.CancelledError: await release.wait()
        return {'state':'done','result':capture}
    client.read=slow
    manager=SwarmPortfolioManager(capture['wallet']['address'],client=client,clock=lambda:capture['at'])
    task=asyncio.create_task(manager.fetch_and_compute()); await entered.wait()
    manager.set_wallet('0x'+'11'*20); manager.set_wallet(capture['wallet']['address'])
    assert manager.get_snapshot()['assets'] is None
    release.set(); await asyncio.gather(task, return_exceptions=True)
    assert manager.get_snapshot()['assets'] is None
    await manager.close()


async def test_generation_rejects_late_uncancellable_provider_result(capture):
    client=Client(capture); entered=asyncio.Event(); release=asyncio.Event()
    async def slow(wallet,*,fresh=False):
        entered.set(); await release.wait()
        return {'state':'done','result':capture}
    client.read=slow
    wallet=capture['wallet']['address']
    manager=SwarmPortfolioManager(wallet,client=client,clock=lambda:capture['at'])
    # A detached provider operation models a response that cancellation cannot stop.
    task=asyncio.create_task(manager._read(manager._generation,wallet,False))
    await entered.wait()
    manager.set_wallet('0x'+'11'*20); manager.set_wallet(wallet)
    release.set(); await task
    assert manager.get_snapshot()['assets'] is None
    assert manager.get_snapshot()['seats'] is None
    await manager.close()


async def test_single_flight_seat_ttl_and_source_clocks_remain_independent(capture):
    client=Client(capture); clock=[capture['at']]; seat_calls=[]
    async def seats(wallet):
        seat_calls.append(wallet)
        return [{'id':'7','token_id':'7'}] if len(seat_calls)==1 else None
    client.read_seats=seats
    manager=SwarmPortfolioManager(capture['wallet']['address'],client=client,clock=lambda:clock[0])
    await asyncio.gather(manager.fetch_and_compute(),manager.fetch_and_compute())
    assert len(client.calls)==1 and len(seat_calls)==1
    clock[0]+=59; await manager.fetch_and_compute()
    assert len(seat_calls)==1
    clock[0]+=2; await manager.fetch_and_compute()
    result=manager.get_snapshot()
    assert len(seat_calls)==2 and result['seats_state']=='stale'
    assert result['seats_as_of']==capture['at'] and result['seats'][0]['token_id']=='7'
    assert result['state']=='ok'
    clock[0]+=600
    assert manager.get_snapshot()['state']=='stale'
    await manager.close()


async def test_close_cancels_pending_request(capture):
    client=Client(capture); entered=asyncio.Event(); cancelled=asyncio.Event()
    async def slow(wallet,*,fresh=False):
        entered.set()
        try: await asyncio.Event().wait()
        finally: cancelled.set()
    client.read=slow
    manager=SwarmPortfolioManager(capture['wallet']['address'],client=client,clock=lambda:capture['at'])
    task=asyncio.create_task(manager.fetch_and_compute()); await entered.wait()
    await manager.close(); await task
    assert cancelled.is_set() and manager.get_snapshot()['assets'] is None


async def test_view_suspend_cancels_and_drains_reads_preserving_same_wallet_facts(capture):
    client=Client(capture)
    manager=SwarmPortfolioManager(capture['wallet']['address'],client=client,clock=lambda:capture['at'])
    await manager.fetch_and_compute()
    previous=manager.get_snapshot()
    entered=asyncio.Event(); cancelled=asyncio.Event()
    async def slow(wallet,*,fresh=False):
        entered.set()
        try: await asyncio.Event().wait()
        finally: cancelled.set()
    client.read=slow
    waiter=asyncio.create_task(manager.fetch_and_compute()); await entered.wait()
    waiter.cancel(); await asyncio.gather(waiter,return_exceptions=True)
    manager.set_active_view(None)
    assert manager._task is None
    await manager.drain_reads()
    assert cancelled.is_set() and manager.get_snapshot()==previous
    assert await manager.fetch_and_compute()==previous
    client.read=Client(capture).read
    manager.set_active_view('PORTFOLIO')
    await manager.fetch_and_compute()
    assert client.read.__self__.calls==[(capture['wallet']['address'],False)]
    await manager.close()


async def test_view_generation_rejects_response_after_suspend_and_resume(capture):
    client=Client(capture); entered=asyncio.Event(); release=asyncio.Event()
    async def slow(wallet,*,fresh=False):
        entered.set(); await release.wait()
        return {'state':'done','result':capture}
    client.read=slow
    wallet=capture['wallet']['address']
    manager=SwarmPortfolioManager(wallet,client=client,clock=lambda:capture['at'])
    task=asyncio.create_task(manager._read(manager._generation,wallet,False))
    await entered.wait()
    manager.set_active_view(None); manager.set_active_view('PORTFOLIO')
    release.set(); await task
    assert manager.get_snapshot()['assets'] is None
    await manager.close()
