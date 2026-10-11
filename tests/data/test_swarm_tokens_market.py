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


async def test_history_volume_uses_completed_hours_and_preserves_price_window():
    payload = fixture('ohlcv')
    row = payload['data']['attributes']['ohlcv_list'][0]
    end = row[0] + 3600
    # Synthetic oldest/current/zero-volume candles derived from the capture.
    payload['data']['attributes']['ohlcv_list'] += [
        [end-86400, *row[1:5], 12], [end, *row[1:5], 999],
        [end-7200, *row[1:5], 0]]
    def handler(request):
        volume = request.url.params['include_empty_intervals'] == 'true'
        assert dict(request.url.params) == {
            'aggregate': '1', 'currency': 'usd', 'token': 'base', 'limit': '25' if volume else '24',
            'before_timestamp': str(end+10), 'include_empty_intervals': 'true' if volume else 'false'}
        return httpx.Response(200, json=payload)
    c = client(handler, end+10)
    async with c._client:
        history = await c.fetch_history(token())
        volume = await c.fetch_volume_history(token())
    assert history['timestamps'] == list(range(end-23*3600, end+1, 3600))
    assert history['sparkline'][-1] == row[4]
    assert history['sparkline'][-3] == row[4]  # valid zero-volume close survives
    assert volume['timestamps'] == list(range(end-86400, end, 3600))
    assert volume['volume_usd'] == [12] + [None]*21 + [0, row[5]]


@pytest.mark.parametrize('bad', [None, True, -1, 'NaN', 'Infinity', {}])
async def test_bad_hourly_volume_does_not_destroy_valid_price_history(bad):
    payload = fixture('ohlcv')
    row = payload['data']['attributes']['ohlcv_list'][0]
    row[5] = bad
    c = client(lambda request: httpx.Response(200, json=payload), row[0]+3600)
    async with c._client:
        history = await c.fetch_history(token())
        volume = await c.fetch_volume_history(token())
    assert history['state'] == 'ok' and history['sparkline'][-2] == row[4]
    assert volume['volume_usd'] == [None]*24


async def test_conflicting_volume_duplicate_stays_unknown_even_after_valid_duplicate():
    payload = fixture('ohlcv')
    row = payload['data']['attributes']['ohlcv_list'][0]
    payload['data']['attributes']['ohlcv_list'] += [[*row[:5], row[5]+1], row[:]]
    c = client(lambda request: httpx.Response(200, json=payload), row[0]+3600)
    async with c._client:
        history = await c.fetch_history(token())
        volume = await c.fetch_volume_history(token())
    assert history['state'] == 'ok' and history['sparkline'][-2] == row[4]
    assert volume['volume_usd'] == [None]*24


@pytest.mark.parametrize('stamp', [True, -3600, 1791576001, 'NaN', 'Infinity'])
async def test_invalid_candle_timestamp_rejects_history(stamp):
    payload = fixture('ohlcv')
    payload['data']['attributes']['ohlcv_list'][0][0] = stamp
    c = client(lambda request: httpx.Response(200, json=payload))
    async with c._client:
        assert (await c.fetch_history(token()))['state'] == 'unavailable'
        assert (await c.fetch_volume_history(token()))['state'] == 'unavailable'


async def test_volume_checks_token_identity_and_reuses_price_trade_rate_limiter():
    payload = fixture('ohlcv')
    sleeps = []
    async def record_sleep(delay):
        sleeps.append(delay)
    c = client(lambda request: httpx.Response(200, json=payload))
    c._sleep = record_sleep
    async with c._client:
        await c.fetch_history(token())
        assert (await c.fetch_volume_history(token()))['state'] == 'ok'
        payload['meta']['base']['address'] = '0x'+'f'*40
        assert (await c.fetch_volume_history(token()))['state'] == 'unavailable'
        await c.fetch_trades(token())
    assert sleeps == [2.1, 2.1, 2.1]


async def test_volume_is_independent_of_invalid_close_and_does_not_fill_missing_hours():
    payload = fixture('ohlcv')
    row = payload['data']['attributes']['ohlcv_list'][0]
    row[4] = 'NaN'
    c = client(lambda request: httpx.Response(200, json=payload), row[0]+3600)
    async with c._client:
        assert (await c.fetch_history(token()))['state'] == 'unavailable'
        volume = await c.fetch_volume_history(token())
    assert volume['volume_usd'] == [None]*23+[row[5]]


async def test_volume_accepts_quote_identity_without_relaxing_price_history():
    payload = fixture('ohlcv')
    row = payload['data']['attributes']['ohlcv_list'][0]
    quote = dict(token(), token_address=payload['meta']['quote']['address'])
    c = client(lambda request: httpx.Response(200, json=payload), row[0]+3600)
    async with c._client:
        # USD volume is the selected pool's turnover; either pool member proves
        # its identity. The base-token close is not the quote token's USD price.
        volume = await c.fetch_volume_history(quote)
        assert volume['state'] == 'ok'
        assert volume['volume_usd'] == [None]*23+[row[5]]
        assert (await c.fetch_history(quote))['state'] == 'unavailable'
        payload['meta']['quote'] = {'symbol': quote['token_address'], 'address': 'invalid'}
        assert (await c.fetch_volume_history(quote))['state'] == 'unavailable'
