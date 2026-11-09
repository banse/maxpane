"""Bounded public portfolio reads and an explicit normalization boundary."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient
from maxpane_dashboard.data.swarm_portfolio_models import BUCKETS, CHAINS, empty_snapshot

ORIGIN = 'https://imd.vibingco.de/portfolio'
MAX_BYTES, MAX_ROWS = 8 * 1024 * 1024, 10000


def address(value):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', value) else None


def _number(value):
    return value if type(value) in (int, float) and 0 <= value <= 1e100 and math.isfinite(value) else None


def _text(value):
    return value[:4000] if isinstance(value, str) else ''


def _url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parts = urlsplit(value)
        return value if parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password else None
    except ValueError:
        return None


def _identity(value):
    if isinstance(value, dict):
        chain, token = value.get('chain'), address(value.get('address'))
        identity = f'{chain}:{token}' if type(chain) is int and chain in CHAINS and token else None
        return identity if value.get('key', identity) == identity else None
    if isinstance(value, str) and ':' in value:
        chain, token = value.split(':', 1)
        if chain in tuple(map(str, CHAINS)) and address(token):
            return chain + ':' + address(token)
    return None


def _stamp(value):
    if _number(value) is not None:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _usd(value):
    return _number(value.get('usd')) if isinstance(value, dict) else None


def _contract(raw):
    raw = raw if isinstance(raw, dict) else {}
    identity = _identity(raw)
    return dict(id=identity, chain_id=int(identity.split(':')[0]) if identity else None,
                contract_address=identity.split(':')[1] if identity else None,
                name=_text(raw.get('name')), site_url=_url(raw.get('siteUrl')),
                launch_id=_text(raw.get('launchId')), launch_number=_number(raw.get('launch')))


def normalize_result(raw, wallet, *, now):
    """Return a new trusted-shape snapshot, or None when its identity is invalid."""
    wallet = address(wallet)
    names = ('holdings', 'positions', 'claims', 'nfts', 'standings', 'utilities')
    if (not wallet or not isinstance(raw, dict) or not isinstance(raw.get('wallet'), dict)
            or address(raw['wallet'].get('address')) != wallet
            or _number(raw.get('at')) is None or raw['at'] > now + 60
            or any(not isinstance(raw.get(name), list) or len(raw[name]) > MAX_ROWS for name in names)):
        return None
    result = empty_snapshot(wallet)
    result.update(state='ok', as_of=raw['at'], assets=[], positions=[], rewards=[],
                  nfts=[], standings=[], utilities=[], coverage=dict(
                      claims_complete=raw.get('claimsComplete') if type(raw.get('claimsComplete')) is bool else None,
                      malformed_rows=0, contracts_scanned=_number((raw.get('counts') or {}).get('contracts'))
                      if isinstance(raw.get('counts'), dict) else None))
    assets, seen = {}, {}

    def bad():
        result['coverage']['malformed_rows'] += 1

    def unique(kind, key, row):
        if not key:
            bad(); return False
        previous = seen.get((kind, key))
        if previous is not None:
            if previous != row: bad()
            return False
        seen[kind, key] = deepcopy(row)
        return True

    def asset(identity, symbol='', label=None):
        if identity not in assets:
            chain, token = identity.split(':')
            label = label if isinstance(label, dict) else {}
            item = dict(id=identity, chain_id=int(chain), token_address=token,
                        symbol=_text(symbol), name=_text(label.get('name')) or _text(symbol),
                        sell_state='unknown', sellable_pct=None, pool={}, connections=[], source={})
            for bucket in BUCKETS:
                item[bucket + '_quantity'] = item[bucket + '_usd'] = 0
            assets[identity] = item
        return assets[identity]

    def add(identity, bucket, row, symbol='', label=None):
        if not identity:
            bad(); return
        item = asset(identity, symbol, label)
        for suffix, value in (('quantity', _number(row.get('amount'))), ('usd', _usd(row.get('value')))):
            key = bucket + '_' + suffix
            item[key] = item[key] + value if item[key] is not None and value is not None else None
        state = row.get('sell')
        if state in ('full', 'partial', 'none', 'no_pool'):
            item['sell_state'] = state

    def reward(row, source, pending=False):
        if not isinstance(row, dict):
            bad(); return None
        identity = _identity(row.get('token'))
        contract = _contract(source)
        # Same getter/source/token/NFT can appear in both a position and claim list.
        parts = [contract['id'] or contract['launch_id'] or contract['name'], identity,
                 _text(row.get('fn')), _text(source.get('item')), str(row.get('at') or '')]
        key = hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:24]
        if not unique('reward', key, {k:v for k,v in row.items() if k != 'kind'}):
            return None
        unlock = row.get('unlock')
        unlock_at = _stamp(unlock.get('unlocksAt')) if isinstance(unlock, dict) else _stamp(unlock)
        state = 'pending' if pending else 'locked' if unlock_at is not None and unlock_at > raw['at'] else 'unknown'
        # Neither a past unlock nor a generic earned() getter proves readiness.
        normalized = dict(id=key, asset_id=identity, chain_id=int(identity.split(':')[0]) if identity else contract['chain_id'],
                          token_address=identity.split(':')[1] if identity else None,
                          symbol=_text(row.get('symbol')), quantity=_number(row.get('amount')),
                          value_usd=_usd(row.get('value')) if identity else None, status=state,
                          unlock_at=unlock_at, source_name=_text(source.get('item')) or contract['name'],
                          source_address=contract['contract_address'], site_url=contract['site_url'],
                          kind='Stake reward' if pending else _text(row.get('kind')))
        if normalized['kind'] == 'Launch reward':
            normalized['site_url'] = f'https://explorer.imd.fun/wallet/{wallet}/earned'
        result['rewards'].append(normalized)
        add(identity, state if state != 'unknown' else 'unknown_reward', row, row.get('symbol'))
        return key

    for row in raw['holdings']:
        if not isinstance(row, dict): bad(); continue
        identity = _identity(row.get('token'))
        if not unique('holding', identity, row): continue
        add(identity, 'wallet', row, row.get('symbol'), row['token'])
        item = assets[identity]
        item['source'] = _contract(row['token'])
        pct = _number(row.get('sellablePct'))
        item['sellable_pct'] = pct if pct is not None and pct <= 100 else None
        pool = row.get('pool') if isinstance(row.get('pool'), dict) else {}
        item['pool'] = dict(id=_text(pool.get('id')), fee=_number(pool.get('fee')),
                            hook=address(pool.get('hook')), pair=address(pool.get('pair')),
                            pair_symbol=_text(pool.get('pairSymbol')))
        connected = row.get('connected') if isinstance(row.get('connected'), dict) else {}
        for group in ('hooks', 'tokens', 'nfts', 'contracts'):
            for link in (connected.get(group) or [])[:100] if isinstance(connected.get(group), list) else []:
                if isinstance(link, dict):
                    item['connections'].append(dict(name=_text(link.get('name')), kind=group,
                        how=_text(link.get('how')), url=_url(link.get('explorer'))))

    for row in raw['positions']:
        if not isinstance(row, dict): bad(); continue
        contract = _contract(row.get('contract'))
        if not unique('position', contract['id'], row): continue
        stake = row.get('stake') if isinstance(row.get('stake'), dict) else {}
        identity = _identity(stake.get('token'))
        if stake: add(identity, 'staked', stake, stake.get('symbol'))
        pending = []
        nested = row.get('rewards')
        if isinstance(nested, list) and len(nested) <= MAX_ROWS:
            pending = [key for entry in nested if (key := reward(entry, row['contract'], True))]
        else: bad()
        values = [entry['value_usd'] for entry in result['rewards'] if entry['id'] in pending]
        result['positions'].append(dict(**contract, asset_id=identity,
            quantity=_number(stake.get('amount')), value_usd=_usd(stake.get('value')) if identity else None,
            pending_usd=sum(value for value in values if value is not None) if all(value is not None for value in values) else None,
            apr=_number(row.get('apr')), apr_method=_text(row.get('aprMethod')), rewards=pending,
            symbol=_text(stake.get('symbol'))))

    for row in raw['claims']:
        if not isinstance(row, dict) or not isinstance(row.get('source'), dict): bad(); continue
        reward(row, row['source'])

    for name in ('nfts', 'standings', 'utilities'):
        for row in raw[name]:
            if not isinstance(row, dict): bad(); continue
            item = _contract(row.get('contract'))
            identity = _identity(row.get('token')) if name == 'utilities' else None
            key = str(identity) + ':' + str(item['id']) if name == 'utilities' else item['id']
            if not item['id']:
                bad(); continue
            if not unique(name, key, row): continue
            item['id'] = key
            if name == 'nfts':
                count = _number(row.get('count'))
                item.update(symbol=_text(row.get('symbol')), count=count if count is not None and count == int(count) else None,
                            token_ids=[str(value) for value in (row.get('ids') or [])[:256] if type(value) in (str,int)]
                            if isinstance(row.get('ids'), list) else [])
            elif name == 'standings':
                item.update(fields=[dict(name=_text(field.get('name')), value=_number(field.get('value')))
                    for field in (row.get('fields') or [])[:100] if isinstance(field, dict)] if isinstance(row.get('fields'),list) else [],
                    sites=[dict(label=_text(site.get('label')), url=_url(site.get('url')))
                    for site in (row.get('sites') or [])[:100] if isinstance(site,dict)] if isinstance(row.get('sites'),list) else [])
            else:
                if not identity: bad(); continue
                item.update(asset_id=identity, symbol=_text(row.get('symbol')), kind=_text(row.get('kind')),
                            role=_text(row.get('role')), joined=row.get('joined') is True,
                            tvl_quantity=_number(row.get('tvl')), tvl_usd=_usd(row.get('tvlValue')),
                            apr=_number(row.get('apr')), apr_method=_text(row.get('aprMethod')))
            result[name].append(item)

    for item in assets.values():
        values = [item[bucket + '_usd'] for bucket in BUCKETS]
        item['total_usd'] = sum(values) if all(value is not None for value in values) else None
    result['assets'] = list(assets.values())
    heads = raw.get('heads') if isinstance(raw.get('heads'), dict) else {}
    result['chains'] = [dict(chain_id=chain, block=_number(heads.get(str(chain)))) for chain in CHAINS]
    if (result['coverage']['claims_complete'] is not True or result['coverage']['malformed_rows']
            or any(item['total_usd'] is None or any(item[bucket + '_quantity'] is None for bucket in BUCKETS)
                   for item in result['assets'])
            or any(item['value_usd'] is None for item in result['positions'])
            or any(item['count'] is None for item in result['nfts'])):
        result['state'] = 'partial'
    return result


class SwarmPortfolioClient(OwnedHttpClient):
    def __init__(self, *, http_client=None):
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=25, follow_redirects=False)

    async def _get(self, url, params=None):
        try:
            async with self._client.stream('GET', url, params=params, timeout=25, follow_redirects=False) as response:
                if response.status_code != 200: return None
                body = bytearray()
                async for part in response.aiter_bytes():
                    if len(body) + len(part) > MAX_BYTES: return None
                    body.extend(part)
            value = json.loads(body)
            return value if isinstance(value, dict) else None
        except (httpx.HTTPError, ValueError, RecursionError, UnicodeError):
            return None

    async def read(self, wallet, *, fresh=False):
        wallet = address(wallet)
        if not wallet: return None
        params = {'wallet': wallet}
        if fresh: params['fresh'] = '1'
        body = await self._get(ORIGIN + '/api/scan', params)
        return body if body and body.get('state') in ('running', 'done', 'error') else None

    async def read_seats(self, wallet):
        wallet = address(wallet)
        if not wallet: return None
        body = await self._get('https://api.imd.fun/pair/wallet/' + wallet)
        if (not isinstance(body, dict) or address(body.get('wallet')) != wallet
                or not isinstance(body.get('tokens'), list) or len(body['tokens']) > MAX_ROWS):
            return None
        seats = {}
        for token in body['tokens']:
            if not isinstance(token, dict): return None
            key = str(token.get('tokenId', ''))
            if not key.isascii() or not key.isdecimal() or len(key) > 78: return None
            key, device = str(int(key)), token.get('device')
            if device is not None and not isinstance(device, dict): return None
            row = dict(id=key, token_id=key, paired=device is not None,
                       online=device.get('online') if device and type(device.get('online')) is bool else None,
                       agent_id=str(token['agentId']) if token.get('agentId') is not None else None)
            if key in seats and seats[key] != row: return None
            seats[key] = row
        return list(seats.values())
