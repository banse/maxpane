"""Keyless selected-pool quotes and observed hourly history/trades.

Indexer liquidity is used only to select a market, never to classify the
swarm's launch position. Missing candles stay gaps; FDV never substitutes cap.
"""
import asyncio
import math
import re
import time

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient
from maxpane_dashboard.data.surf_swarm import _ts

NETWORKS = {'eth': ('ethereum', 'eth'), 'base': ('base', 'base'),
            'rh': ('robinhood', 'robinhood')}
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
POOL = re.compile(r'0x(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z')


def _number(value, *, signed=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and (signed or number >= 0) else None


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _hex(value, pattern=ADDRESS):
    return value.lower() if isinstance(value, str) and pattern.fullmatch(value) else None


class SwarmTokensMarketClient(OwnedHttpClient):
    def __init__(self, *, http_client=None, clock=time.time, sleep=asyncio.sleep):
        self._client = http_client or httpx.AsyncClient(
            timeout=10, headers={'Accept': 'application/json', 'User-Agent': 'MaxPane'})
        self._owns_client = http_client is None
        self._clock, self._sleep = clock, sleep
        self._gecko_lock = asyncio.Lock()
        self._last_gecko = None

    async def _get(self, url, *, params=None, gecko=False):
        try:
            if gecko:
                # Shared by prices, volume and trades: below public 30/min.
                async with self._gecko_lock:
                    if self._last_gecko is not None:
                        await self._sleep(max(0, 2.1 - (self._clock() - self._last_gecko)))
                    self._last_gecko = self._clock()
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def fetch_markets(self, tokens):
        result = {}
        for chain, (network, _) in NETWORKS.items():
            rows = [t for t in tokens if t.get('chain') == chain
                    and _hex(t.get('token_address'))]
            for start in range(0, len(rows), 30):
                batch = rows[start:start + 30]
                addresses = ','.join(_hex(t['token_address']) for t in batch)
                pairs = await self._get(f'https://api.dexscreener.com/tokens/v1/{network}/{addresses}')
                valid = isinstance(pairs, list) and all(isinstance(p, dict) for p in pairs)
                for token in batch:
                    key = token['id']
                    result[key] = {'state': 'unavailable'}
                    if not valid:
                        continue
                    expected = token.get('launch_pool')
                    if expected is not None and _hex(expected, POOL) is None:
                        continue
                    matches = [p for p in pairs if p.get('chainId') == network
                               and _hex(_mapping(p.get('baseToken')).get('address')) == _hex(token['token_address'])
                               and _hex(p.get('pairAddress'), POOL)
                               and (expected is None or _hex(p['pairAddress'], POOL) == _hex(expected, POOL))]
                    if not matches:
                        result[key] = {'state': 'unindexed'}
                        continue
                    pair = sorted(matches, key=lambda p: (
                        -(_number(_mapping(p.get('liquidity')).get('usd')) or 0), p['pairAddress'].lower()))[0]
                    base = _mapping(pair.get('baseToken'))
                    txns = _mapping(_mapping(pair.get('txns')).get('h24'))
                    result[key] = dict(
                        state='ok', market_pool=pair['pairAddress'].lower(), market_source='DexScreener',
                        symbol=base.get('symbol') if isinstance(base.get('symbol'), str) else None,
                        name=base.get('name') if isinstance(base.get('name'), str) else None,
                        price_usd=_number(pair.get('priceUsd')), mcap_usd=_number(pair.get('marketCap')),
                        fdv_usd=_number(pair.get('fdv')),
                        change_24h=_number(_mapping(pair.get('priceChange')).get('h24'), signed=True),
                        volume_24h=_number(_mapping(pair.get('volume')).get('h24')),
                        buys_24h=_number(txns.get('buys')), sells_24h=_number(txns.get('sells')))
        for token in tokens:
            result.setdefault(token['id'], {'state': 'unsupported' if token.get('chain') not in NETWORKS else 'unavailable'})
        return result

    async def _pool(self, token, suffix, params=None):
        network = NETWORKS.get(token.get('chain'))
        if network is None:
            return None, 'unsupported'
        pool = _hex(token.get('market_pool'), POOL)
        if not pool or not _hex(token.get('token_address')):
            return None, 'unavailable'
        body = await self._get(f'https://api.geckoterminal.com/api/v2/networks/{network[1]}/pools/{pool}/{suffix}',
                               params=params, gecko=True)
        return body, 'unavailable'

    async def fetch_history(self, token):
        now = self._clock()
        body, state = await self._pool(token, 'ohlcv/hour', {
            'aggregate': 1, 'currency': 'usd', 'token': 'base', 'limit': 24,
            'before_timestamp': int(now), 'include_empty_intervals': 'false'})
        if not isinstance(body, dict):
            return {'state': state}
        base = _mapping(_mapping(body.get('meta')).get('base'))
        rows = _mapping(_mapping(body.get('data')).get('attributes')).get('ohlcv_list')
        if _hex(base.get('address')) != _hex(token['token_address']) or not isinstance(rows, list):
            return {'state': 'unavailable'}
        end = int(now // 3600) * 3600
        timestamps = list(range(end - 23 * 3600, end + 1, 3600))
        points = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                return {'state': 'unavailable'}
            stamp, close = _number(row[0]), _number(row[4])
            if stamp is None or close is None or stamp % 3600:
                return {'state': 'unavailable'}
            if stamp in timestamps:
                if stamp in points and points[stamp] != close:
                    return {'state': 'unavailable'}
                points[stamp] = close
        return {'state': 'ok', 'sparkline': [points.get(t) for t in timestamps], 'timestamps': timestamps}

    async def fetch_volume_history(self, token):
        """Observed USD volumes of the last 24 completed hourly candles.

        Kept separate from prices: empty-interval filling carries the previous
        close forward and must not change the existing observed-price gaps.
        """
        now = self._clock()
        body, state = await self._pool(token, 'ohlcv/hour', {
            'aggregate': 1, 'currency': 'usd', 'token': 'base', 'limit': 25,
            'before_timestamp': int(now), 'include_empty_intervals': 'true'})
        if not isinstance(body, dict):
            return {'state': state}
        meta = _mapping(body.get('meta'))
        members = {_hex(_mapping(meta.get(side)).get('address')) for side in ('base', 'quote')}
        rows = _mapping(_mapping(body.get('data')).get('attributes')).get('ohlcv_list')
        if _hex(token['token_address']) not in members or not isinstance(rows, list):
            return {'state': 'unavailable'}
        end = int(now // 3600) * 3600
        timestamps = list(range(end - 86400, end, 3600))
        points = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                return {'state': 'unavailable'}
            stamp, volume = _number(row[0]), _number(row[5])
            if stamp is None or stamp % 3600:
                return {'state': 'unavailable'}
            if stamp in timestamps:
                # Conflict/invalid volume poisons only this hour, permanently.
                points[stamp] = None if stamp in points and points[stamp] != volume else volume
        return {'state': 'ok', 'volume_usd': [points.get(t) for t in timestamps],
                'timestamps': timestamps}

    async def fetch_trades(self, token):
        body, state = await self._pool(token, 'trades')
        if not isinstance(body, dict) or not isinstance(body.get('data'), list):
            return {'state': state}
        events = {}
        for row in body['data']:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                return {'state': 'unavailable'}
            attrs = _mapping(row.get('attributes'))
            kind = attrs.get('kind')
            field = 'to_token_address' if kind == 'buy' else 'from_token_address' if kind == 'sell' else None
            if field is None or _hex(attrs.get(field)) != _hex(token['token_address']):
                continue
            stamp = _ts(attrs.get('block_timestamp'))
            if stamp is None or not 0 <= self._clock() - stamp <= 86400:
                continue
            key = f"{token['chain']}:{token['market_pool']}:{row['id']}"
            events[key] = dict(id=key, token_id=token['id'], ts=stamp, kind=kind.upper(),
                               amount=_number(attrs.get('volume_in_usd')), asset='USD')
        return {'state': 'ok', 'activity': sorted(events.values(), key=lambda e: (-e['ts'], e['id']))}
