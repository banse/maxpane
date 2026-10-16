"""Exact-pool market reads. All transports are explicitly offline fixtures."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data import surf_client as module
from maxpane_dashboard.data.surf_client import SurfClient

FIXTURES = Path(__file__).parents[1] / 'fixtures/surf/market_loading'
POOL = A.POOL_V4_ID_FALLBACK.lower()
DEX_URL = f'https://api.dexscreener.com/latest/dex/pairs/ethereum/{POOL}'
GECKO_URL = f'https://api.geckoterminal.com/api/v2/networks/eth/pools/{POOL}'
FP_URL = f'{module.DEXSCREENER_TOKENS_API}/{A.FP_TOKEN_BASE}'


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def client_on(handler):
    return SurfClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                      inter_call_delay=0, backoff_seconds=(0, 0))


@pytest.mark.parametrize('provider', ['dex', 'gecko'])
def test_market_identity_and_orientation(provider):
    body = fixture('dex_pair.json' if provider == 'dex' else 'gecko_pool.json')
    decode = getattr(module, f'_decode_imd_{provider}')
    snap = decode(body, POOL)
    assert snap.imd_price_usd > 0
    assert snap.chain_id == 1
    assert snap.pool_id == POOL
    assert snap.base_token == A.IMD_TOKEN.lower()
    assert snap.target_side == 'base'
    assert snap.provider_ts is None and snap.block_number is None
    assert snap.base_decimals is None and snap.quote_decimals is None
    wrong = deepcopy(body)
    if provider == 'dex':
        wrong['pairs'][0]['chainId'] = 'base'
    else:
        wrong['data']['id'] = 'base_' + POOL
    assert decode(wrong, POOL) is None
    assert decode(body, '0x' + 'ab' * 32) is None
    wrong = deepcopy(body)
    if provider == 'dex':
        wrong['pairs'][0]['baseToken']['address'] = '0x' + 'aa' * 20
    else:
        wrong['data']['relationships']['base_token']['data']['id'] = 'eth_0x' + 'aa' * 20
    assert decode(wrong, POOL) is None


def test_dex_decoy_first_does_not_change_exact_pair():
    body = fixture('dex_pair.json')
    decoy = deepcopy(body['pairs'][0])
    decoy.update(pairAddress='0x' + 'ab' * 32, priceUsd='10000')
    body['pairs'].insert(0, decoy)
    assert module._decode_imd_dex(body, POOL).imd_price_usd == 0.7074


@pytest.mark.parametrize('value', fixture('identity_cases.json')['invalid_prices'])
@pytest.mark.parametrize('provider', ['dex', 'gecko'])
def test_empty_200_null_cap_and_invalid_numbers(provider, value):
    decode = getattr(module, f'_decode_imd_{provider}')
    assert decode({}, POOL) is None
    body = fixture('dex_pair.json' if provider == 'dex' else 'gecko_pool.json')
    attrs = body['pairs'][0] if provider == 'dex' else body['data']['attributes']
    attrs['priceUsd' if provider == 'dex' else 'base_token_price_usd'] = value
    assert decode(body, POOL) is None


@pytest.mark.parametrize('provider', ['dex', 'gecko'])
def test_null_cap_is_not_fdv_and_volume_zero_is_valid(provider):
    body = fixture('dex_pair.json' if provider == 'dex' else 'gecko_pool.json')
    attrs = body['pairs'][0] if provider == 'dex' else body['data']['attributes']
    attrs['marketCap' if provider == 'dex' else 'market_cap_usd'] = None
    attrs['volume' if provider == 'dex' else 'volume_usd']['h24'] = 0
    snap = getattr(module, f'_decode_imd_{provider}')(body, POOL)
    assert snap.market_cap_usd is None
    assert snap.fdv_usd > 0
    assert snap.imd_vol_24h_usd == 0


@pytest.mark.parametrize('provider', ['dex', 'gecko'])
def test_quote_orientation_never_relabels_base_fields(provider):
    body = fixture('dex_pair.json' if provider == 'dex' else 'gecko_pool.json')
    if provider == 'dex':
        attrs = body['pairs'][0]
        attrs['baseToken'], attrs['quoteToken'] = attrs['quoteToken'], attrs['baseToken']
        # DexScreener's actual pair schema has no explicit quote USD price.
        assert module._decode_imd_dex(body, POOL) is None
        return
    rel = body['data']['relationships']
    rel['base_token'], rel['quote_token'] = rel['quote_token'], rel['base_token']
    attrs = body['data']['attributes']
    attrs['quote_token_price_usd'] = '7.25'
    # An unrelated first included token must not determine orientation/decimals.
    body['included'] = [{'id': 'eth_0x' + 'aa' * 20, 'attributes': {'decimals': 3}}]
    snap = module._decode_imd_gecko(body, POOL)
    assert snap.imd_price_usd == 7.25
    assert snap.target_side == 'quote'
    assert snap.imd_change_24h_pct is None
    assert snap.fdv_usd is None and snap.market_cap_usd is None
    assert snap.base_decimals is None and snap.quote_decimals is None
    attrs.pop('quote_token_price_usd')
    assert module._decode_imd_gecko(body, POOL) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('pool', fixture('identity_cases.json')['bad_pool_ids'])
async def test_no_pool_id_never_guesses_a_pool(pool):
    def reject(request):
        raise AssertionError(f'unexpected transport: {request.url}')
    async with client_on(reject) as client:
        assert await client.fetch_market(pool) is None


@pytest.mark.asyncio
async def test_dex_primary_is_not_blended_with_gecko():
    calls = []
    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url == DEX_URL:
            body = fixture('dex_pair.json')
            body['pairs'][0]['marketCap'] = None
            return httpx.Response(200, json=body)
        if url == FP_URL:
            return httpx.Response(200, json={'pairs': []})
        raise AssertionError(f'unexpected transport: {url}')
    async with client_on(handler) as client:
        snap = await client.fetch_market(POOL)
    assert snap.market_source == 'DexScreener'
    assert snap.market_cap_usd is None
    assert snap.imd_price_usd_gecko is None and snap.sources_agree is None
    assert snap.eth_usd is None
    assert calls.count(DEX_URL) == 1 and len(calls) == 2


@pytest.mark.asyncio
async def test_healthy_primary_does_not_wait_for_gecko():
    def handler(request):
        if str(request.url) == DEX_URL:
            return httpx.Response(200, json=fixture('dex_pair.json'))
        if str(request.url) == FP_URL:
            return httpx.Response(200, json={'pairs': []})
        raise AssertionError(f'healthy primary unexpectedly requested {request.url}')
    async with client_on(handler) as client:
        assert (await client.fetch_market(POOL)).imd_price_usd == 0.7074


@pytest.mark.asyncio
@pytest.mark.parametrize('primary', ['empty', 'timeout', '429', 'wrong_pool'])
async def test_exact_gecko_fallback_after_primary_gap(primary):
    calls = []
    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url == DEX_URL:
            if primary == 'timeout':
                raise httpx.ReadTimeout('fixture timeout', request=request)
            if primary == '429':
                return httpx.Response(429, json={})
            if primary == 'wrong_pool':
                body = fixture('dex_pair.json')
                body['pairs'][0]['pairAddress'] = '0x' + 'aa' * 32
                return httpx.Response(200, json=body)
            return httpx.Response(200, json={'pairs': []})
        if url == GECKO_URL:
            return httpx.Response(200, json=fixture('gecko_pool.json'))
        if url == FP_URL:
            return httpx.Response(200, json={'pairs': []})
        raise AssertionError(f'unexpected transport: {url}')
    async with client_on(handler) as client:
        snap = await client.fetch_market(POOL)
    assert snap.market_source == 'GeckoTerminal'
    assert snap.imd_price_usd == pytest.approx(5.42278794913207)
    assert snap.market_cap_usd is None
    assert calls.count(GECKO_URL) == 1
    assert calls.count(DEX_URL) == (2 if primary in {'timeout', '429'} else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [1917.74, None, 0, -1, True, 'NaN', 'Infinity', {}, []])
async def test_eth_success_survives_missing_imd(value):
    def handler(request):
        assert str(request.url) == module.COINGECKO_ETH_URL
        return httpx.Response(200, json={'ethereum': {'usd': value}})
    async with client_on(handler) as client:
        assert await client.fetch_eth_usd() == (1917.74 if value == 1917.74 else None)


@pytest.mark.asyncio
async def test_market_cancel_drains_all_children():
    started = set()
    all_started = asyncio.Event()
    drained = set()
    async def handler(request):
        url = str(request.url)
        assert url in {DEX_URL, FP_URL}
        started.add(url)
        if len(started) == 2:
            all_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            drained.add(url)
    async with client_on(handler) as client:
        task = asyncio.create_task(client.fetch_market(POOL))
        await asyncio.wait_for(all_started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert drained == started


@pytest.mark.parametrize('provider', ['dex', 'gecko'])
@pytest.mark.parametrize('value', [True, False, 'NaN', 'Infinity', -1, [], {}])
def test_market_optional_numbers_are_finite_and_nonnegative(provider, value):
    body = fixture('dex_pair.json' if provider == 'dex' else 'gecko_pool.json')
    attrs = body['pairs'][0] if provider == 'dex' else body['data']['attributes']
    if provider == 'dex':
        attrs.update(marketCap=value, fdv=value, liquidity={'usd': value, 'base': value, 'quote': value}, volume={'h24': value})
    else:
        attrs.update(market_cap_usd=value, fdv_usd=value, reserve_in_usd=value, volume_usd={'h24': value})
    snap = getattr(module, f'_decode_imd_{provider}')(body, POOL)
    assert snap is not None
    assert snap.fdv_usd is None and snap.market_cap_usd is None
    assert snap.imd_vol_24h_usd is None and snap.pool_liquidity_usd is None
    assert snap.pool_imd is None and snap.pool_weth is None


@pytest.mark.parametrize('body', [None, [], True, {'pairs': [None, 'bad', []]}, {'pairs': {}}, {'data': []}, {'data': {'attributes': [], 'relationships': []}}])
def test_market_malformed_containers_degrade(body):
    assert module._decode_imd_dex(body, POOL) is None
    assert module._decode_imd_gecko(body, POOL) is None


@pytest.mark.parametrize('provider', ['dex', 'gecko'])
@pytest.mark.parametrize('mutation', ['wrong_quote', 'wrong_id', 'wrong_pool', 'wrong_network_token', 'malformed_token'])
def test_pool_and_both_token_identities_are_required(provider, mutation):
    body = fixture('dex_pair.json' if provider == 'dex' else 'gecko_pool.json')
    if provider == 'dex':
        pair = body['pairs'][0]
        if mutation in {'wrong_id', 'wrong_pool'}:
            pair['pairAddress'] = '0x' + 'ab' * 32
        else:
            pair['quoteToken']['address'] = (None if mutation == 'malformed_token' else '0x' + 'aa' * 20)
    else:
        data = body['data']
        if mutation == 'wrong_id':
            data['id'] = 'eth_0x' + 'ab' * 32
        elif mutation == 'wrong_pool':
            data['attributes']['address'] = '0x' + 'ab' * 32
        else:
            data['relationships']['quote_token']['data']['id'] = (
                None if mutation == 'malformed_token' else
                'base_' + '0x' + '00' * 20 if mutation == 'wrong_network_token' else
                'eth_0x' + 'aa' * 20)
    assert getattr(module, f'_decode_imd_{provider}')(body, POOL) is None


@pytest.mark.asyncio
async def test_market_cancel_during_fallback_drains_fp_and_gecko():
    started = set()
    all_started = asyncio.Event()
    drained = set()
    async def handler(request):
        url = str(request.url)
        if url == DEX_URL:
            return httpx.Response(200, json={'pairs': []})
        assert url in {GECKO_URL, FP_URL}
        started.add(url)
        if len(started) == 2:
            all_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            drained.add(url)
    async with client_on(handler) as client:
        task = asyncio.create_task(client.fetch_market(POOL))
        await asyncio.wait_for(all_started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert drained == started


@pytest.mark.asyncio
async def test_market_transport_error_drains_sibling_before_returning():
    fp_started = asyncio.Event()
    fp_drained = asyncio.Event()
    async def handler(request):
        if str(request.url) == DEX_URL:
            await fp_started.wait()
            raise AssertionError('unexpected provider transport')
        assert str(request.url) == FP_URL
        fp_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            fp_drained.set()
    async with client_on(handler) as client:
        with pytest.raises(AssertionError, match='unexpected provider transport'):
            await client.fetch_market(POOL)
        assert fp_drained.is_set()
