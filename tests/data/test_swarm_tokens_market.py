"""Keyless quotes/history/trades preserve exact token identity and missing data."""
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.swarm_tokens_market import SwarmTokensMarketClient

FIXTURES=Path(__file__).parents[1]/'fixtures/swarm_tokens/market'
def fixture(name): return json.loads((FIXTURES/(name+'.json')).read_text())
def token(chain='eth'):
    pair=fixture('dex' if chain=='eth' else 'dex-rh')[0]
    address=pair['baseToken']['address'].lower()
    return dict(id=chain+':'+address,chain=chain,token_address=address,
                market_pool=pair['pairAddress'].lower(),launch_pool=pair['pairAddress'].lower())
async def no_sleep(_): pass

def client(handler,now=1791579600):
    return SwarmTokensMarketClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),clock=lambda:now,sleep=no_sleep)

@pytest.mark.parametrize('chain,network', [('eth','ethereum'),('rh','robinhood')])
async def test_captured_markets_exact_chain_token_pool_and_independent_cap(chain,network):
    pair=fixture('dex' if chain=='eth' else 'dex-rh')[0]
    pair.pop('marketCap',None)
    pair['fdv']=123
    t=token(chain)
    wrong=dict(deepcopy(pair),pairAddress='0x'+'f'*64,liquidity={'usd':1e99})
    wrong_chain=dict(deepcopy(pair),chainId='base',priceUsd='999')
    wrong_token=dict(deepcopy(pair),baseToken={'address':'0x'+'e'*40},priceUsd='888')
    def handler(request):
        assert request.url.path.startswith('/tokens/v1/'+network+'/')
        return httpx.Response(200,json=[wrong,wrong_chain,wrong_token,pair])
    c=client(handler)
    async with c._client:
        data=(await c.fetch_markets([t]))[t['id']]
        assert data['state']=='ok' and data['market_pool']==t['launch_pool']
        assert data['price_usd']==float(pair['priceUsd'])
        assert data['mcap_usd'] is None and data['fdv_usd']==123
        assert data['buys_24h']==pair['txns']['h24']['buys']

async def test_invalid_numbers_missing_pool_and_transport_failure_do_not_become_zero():
    pair=fixture('dex')[0]; t=token(); response=[pair]
    c=client(lambda request:httpx.Response(200,json=response))
    async with c._client:
        pair.update(priceUsd='NaN',marketCap=-1,volume={'h24':None},txns={'h24':{'buys':True,'sells':0}})
        data=(await c.fetch_markets([t]))[t['id']]
        assert data['price_usd'] is data['mcap_usd'] is data['volume_24h'] is data['buys_24h'] is None
        assert data['sells_24h']==0
        response.clear()
        assert (await c.fetch_markets([t]))[t['id']]['state']=='unindexed'
    bad=client(lambda request:httpx.Response(429))
    async with bad._client:
        assert (await bad.fetch_markets([t]))[t['id']]['state']=='unavailable'

async def test_history_preserves_hour_buckets_gaps_and_checks_token():
    t=token(); payload=fixture('ohlcv'); original=deepcopy(payload)
    row=payload['data']['attributes']['ohlcv_list'][0]
    now=row[0]+7200
    c=client(lambda request:httpx.Response(200,json=payload),now)
    async with c._client:
        history=await c.fetch_history(t)
        assert history['state']=='ok' and len(history['sparkline'])==24
        assert sum(v is not None for v in history['sparkline'])==1
        index=history['timestamps'].index(row[0])
        assert history['sparkline'][index]==row[4]
        assert history['sparkline'][-1] is None
        payload['meta']['base']['address']='0x'+'f'*40
        assert (await c.fetch_history(t))['state']=='unavailable'
        assert original['meta']['base']['address']==t['token_address']

async def test_trades_validate_direction_token_and_deduplicate_real_events():
    t=token(); payload=fixture('trades')
    payload['data'].append(deepcopy(payload['data'][0]))
    other=deepcopy(payload['data'][0]);other['id']='other'
    other['attributes']['to_token_address']='0x'+'f'*40
    payload['data'].append(other)
    c=client(lambda request:httpx.Response(200,json=payload))
    async with c._client:
        data=await c.fetch_trades(t)
        events=data['activity']
        assert data['state']=='ok' and events
        assert len({e['id'] for e in events})==len(events)
        assert all(e['token_id']==t['id'] and e['asset']=='USD' for e in events)
        assert events[0]['amount']==float(payload['data'][0]['attributes']['volume_in_usd'])
        assert not any(e['id'].endswith(':other') for e in events)

async def test_invalid_chain_address_and_pool_do_not_issue_requests():
    def forbidden(request): raise AssertionError('unexpected request')
    c=client(forbidden)
    async with c._client:
        t=token();t['chain']='testnet'
        assert (await c.fetch_markets([t]))[t['id']]['state']=='unsupported'
        assert (await c.fetch_history(t))['state']=='unsupported'
        t=token();t['market_pool']='../secret'
        assert (await c.fetch_trades(t))['state']=='unavailable'
