"""Nonblocking live SWARM TOKENS adapter; borrows SURF's launch evidence.

Catalogue createdAt is launch-record time, not a proven deployment block time.
Session caches keep their independent successful clocks; no demo values enter here.
"""
import asyncio
from copy import deepcopy
import math
import time

from maxpane_dashboard.analytics.surf_launch_checks import ZERO, address
from maxpane_dashboard.analytics.swarm_tokens import select_tokens
from maxpane_dashboard.data.surf_swarm import launch_rows
from maxpane_dashboard.data.series_points import coerce_points
from maxpane_dashboard.data.swarm_tokens_client import SwarmTokensClient
from maxpane_dashboard.data.swarm_tokens_models import TOKEN_KEYS

CHAINS = {1: 'eth', 8453: 'base', 4663: 'rh'}
MARKET_FIELDS = ('price_usd', 'change_24h', 'mcap_usd', 'fdv_usd', 'volume_24h',
                 'buys_24h', 'sells_24h', 'market_pool', 'market_source')


def _number(value):
    try:
        return value if type(value) in (int, float) and math.isfinite(value) else None
    except OverflowError:
        return None


def _token_artifacts(row):
    artifacts = [a for a in row.get('artifacts', []) if a.get('role') == 'token']
    valid = {address(a.get('address')): a for a in artifacts
             if address(a.get('address')) not in (None, ZERO)}
    malformed = any(address(a.get('address')) in (None, ZERO) for a in artifacts)
    return valid, bool(artifacts) and (malformed or len(valid) != 1)


def _volume_hours(payload, now):
    stamps, values = payload.get('timestamps'), payload.get('volume_usd')
    if (not isinstance(stamps, list) or not isinstance(values, list)
            or len(stamps) != 24 or len(values) != 24
            or any(_number(t) is None or t <= 0 or t % 3600 for t in stamps)
            or stamps != list(range(int(stamps[0]), int(stamps[0])+86400, 3600))):
        return {}
    points, _ = coerce_points([(stamp, _number(value)) for stamp, value in zip(stamps, values)],
                             now=now, max_age=86400+3600)
    return dict(points)


class SwarmTokensManager:
    is_mock = False
    _error_count = 0
    CATALOGUE_TTL, MARKET_TTL = 300, 120
    HISTORY_TTL, TRADES_TTL, LIQUIDITY_TTL = 900, 120, 600
    PAGE_SIZE, PAGE_BUDGET, MARKET_BATCH, DETAIL_BATCH = 500, 3, 30, 2
    VOLUME_BATCH = 10

    def __init__(self, surf_manager, *, client=None, market=None, clock=time.time):
        self.surf = surf_manager
        self.client = client or SwarmTokensClient()
        if market is None:
            from maxpane_dashboard.data.swarm_tokens_market import SwarmTokensMarketClient
            market = SwarmTokensMarketClient()
            self._owns_market = True
        else:
            self._owns_market = False
        self.market = market
        self._owns_client = client is None
        self._clock = clock
        self._catalogue = None
        self._cat_as_of = self._cat_attempt = None
        self._complete = self._cat_failed = False
        self._scan = None
        self._cursor = None
        self._tasks = {}
        self._closed = False
        self._market, self._history, self._trades, self._volume = {}, {}, {}, {}
        self._market_expectations = {}
        self._attempts = {name: {} for name in ('markets', 'history', 'trades', 'volume')}
        self._failed = {name: set() for name in self._attempts}
        self._detail_pools = {'history': {}, 'trades': {}, 'volume': {}}
        self._portfolio_active = False
        self._portfolio_priority_ids = set()

    def _start(self, name, coroutine):
        if self._closed or name in self._tasks and not self._tasks[name].done():
            coroutine.close()
            return
        self._tasks[name] = asyncio.create_task(coroutine)

    async def wait_pending(self):
        """Observable completion seam for offline tests and one-shot live captures."""
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks.values()), return_exceptions=True)

    async def _scan_catalogue(self):
        self._cat_attempt = self._clock()
        if self._scan is None:
            self._scan, self._cursor = {}, None
        try:
            for _ in range(self.PAGE_BUDGET):
                page = await self.client.fetch_page(before=self._cursor, limit=self.PAGE_SIZE)
                if (page is None or any(row['id'] in self._scan for row in page)
                        or page and self._cursor is not None and page[0]['launchNumber'] >= self._cursor):
                    raise ValueError('failed or nonprogressing catalogue page')
                self._scan.update({row['id']: row for row in page})
                if not self._complete:
                    prior = {row['id']: row for row in self._catalogue or []}
                    prior.update(self._scan)
                    self._catalogue = list(prior.values())
                    self._cat_as_of = self._clock()
                if len(page) < self.PAGE_SIZE:
                    self._catalogue = list(self._scan.values())
                    self._cat_as_of = self._clock()
                    self._complete, self._cat_failed = True, False
                    self._scan = self._cursor = None
                    return
                self._cursor = page[-1]['launchNumber']
            self._cat_failed = False
        except Exception:
            self._cat_failed = True
            self._error_count += 1
            self._scan = self._cursor = None

    def _catalogue_rows(self):
        if self._scan:
            merged = {row['id']: row for row in self._catalogue or []}
            merged.update(self._scan)
            return list(merged.values())
        return self._catalogue

    def _base_rows(self, source):
        raw = self._catalogue_rows()
        return launch_rows(raw) if raw is not None else source.get('rows')

    def _tokens(self, source, now, *, include_inactive=False):
        base = self._base_rows(source)
        if base is None:
            return None
        enriched = {row['launch_id']: row for row in source.get('rows') or []}
        result = {}
        # Keep the market view's live representative when the same deployment
        # has inactive aliases, so switching views never churns its pool cache.
        for row in sorted(base, key=lambda r: (r.get('status') == 'live',
                                             r.get('launch_number') or -1), reverse=True):
            chain = row.get('chain_id')
            artifacts, ambiguous = _token_artifacts(row)
            if chain not in CHAINS or len(artifacts) != 1 or include_inactive and ambiguous:
                continue
            contract, artifact = next(iter(artifacts.items()))
            token_id = f'{chain}:{contract}'
            if token_id in result:
                result[token_id]['launch_uuids'].append(row['launch_id'])
                continue
            if not include_inactive and row.get('status') != 'live':
                continue
            evidence = enriched.get(row['launch_id'], {})
            if (evidence.get('chain_id') != chain or address(evidence.get('token_address')) != contract
                    or evidence.get('updated_ts') != row.get('updated_ts')):
                evidence = {}
            token = dict.fromkeys(TOKEN_KEYS)
            token.update(id=token_id, launch_id=row['launch_number'], launch_uuid=row['launch_id'],
                         launch_uuids=[row['launch_id']],
                         chain=CHAINS[chain], chain_id=chain, token_address=contract,
                         symbol=evidence.get('ticker') or artifact.get('name') or '—',
                         name=evidence.get('token_name') or artifact.get('name') or '—',
                         launched_at=row.get('created_ts'), status=row['status'],
                         verdict=(evidence.get('verdict') or {}).get('state', 'unknown'),
                         lp_state='unknown', market_state='pending', history_state='pending',
                         trades_state='pending', market_read_at=None, history_read_at=None,
                         trades_read_at=None, liquidity_read_at=None, liquidity_state='unknown',
                         market_pool=None, market_source=None, token_amount=None, withdrawn_pct=None,
                         launch_pool=(source.get('pool_ids') or {}).get(row['launch_id']) if evidence else None)
            liquidity = evidence.get('liquidity') or {}
            stamp = _number(liquidity.get('read_ts'))
            if stamp is not None:
                token.update(liquidity_read_at=stamp, liquidity_state='stale')
                if 0 <= now-stamp <= self.LIQUIDITY_TTL and liquidity.get('state') in ('info', 'warn'):
                    paired, amount = (_number(liquidity.get(key)) for key in ('paired_amount', 'token_amount'))
                    token.update(paired_amount=paired, token_amount=amount,
                                 withdrawn_pct=_number(liquidity.get('withdrawn_pct')),
                                 paired_symbol=liquidity.get('paired_symbol'),
                                 fee_pct=liquidity['pool_fee']/10000 if _number(liquidity.get('pool_fee')) is not None else None,
                                 liquidity_state='ok')
                    if liquidity.get('lock') == 'withdrawn' and paired is not None and amount is not None:
                        token['lp_state'] = 'withdrawn'
                    elif paired is not None and amount is not None:
                        token['lp_state'] = ('two-sided' if paired > 0 and amount > 0 else
                                             'one-token' if amount > 0 else 'one-quote' if paired > 0 else 'unknown')
            for name, cache, ttl in (('markets', self._market, self.MARKET_TTL),
                                     ('history', self._history, self.HISTORY_TTL),
                                     ('trades', self._trades, self.TRADES_TTL)):
                point = cache.get(token_id)
                if name == 'markets' and point and point[0].get('_expected_pool') != token['launch_pool']:
                    point = None
                if name != 'markets' and point and point[0].get('_pool') != token['market_pool']:
                    point = None
                label = 'market' if name == 'markets' else name
                if point:
                    payload, read_at = point
                    state = payload.get('state', 'ok')
                    stale = token_id in self._failed[name] or not 0 <= now-read_at <= ttl
                    token[label+'_state'] = 'unsupported' if state == 'unsupported' else 'stale' if stale else state
                    token[label+'_read_at'] = None if state == 'unsupported' else read_at
                    if name == 'markets':
                        token.update({key: payload.get(key) for key in MARKET_FIELDS})
                        for key in ('symbol', 'name'):
                            if payload.get(key):
                                token[key] = payload[key]
                    elif name == 'history':
                        token['sparkline'] = payload.get('sparkline')
                        token['sparkline_timestamps'] = payload.get('timestamps')
                elif token_id in self._failed[name]:
                    token[label+'_state'] = 'unavailable'
            if token['market_state'] in ('unsupported', 'unindexed'):
                token.update(history_state=token['market_state'], trades_state=token['market_state'])
            result[token_id] = token
        return list(result.values())

    async def _refresh_markets(self, tokens):
        now = self._clock()
        for token in tokens:
            self._attempts['markets'][token['id']] = now
            self._market_expectations[token['id']] = token.get('launch_pool')
        try:
            response = await self.market.fetch_markets(tokens)
        except Exception:
            response = None
        for token in tokens:
            key = token['id']
            point = response.get(key) if isinstance(response, dict) else None
            if point is not None and point.get('state') not in ('unavailable', 'error'):
                self._market[key] = (dict(point, _expected_pool=token.get('launch_pool')), self._clock())
                self._failed['markets'].discard(key)
            else:
                self._failed['markets'].add(key)

    async def _refresh_details(self, name, tokens):
        cache = getattr(self, '_'+name)
        method = getattr(self.market, 'fetch_volume_history' if name == 'volume' else 'fetch_'+name)
        for token in tokens:
            key = token['id']
            self._attempts[name][key] = self._clock()
            self._detail_pools[name][key] = token.get('market_pool')
            try:
                point = await method(token)
            except Exception:
                point = None
            if point is not None and point.get('state') not in ('unavailable', 'error'):
                cache[key] = (dict(point, _pool=token.get('market_pool')), self._clock())
                self._failed[name].discard(key)
            else:
                self._failed[name].add(key)

    def offer_catalogue(self):
        """Schedule only catalogue discovery."""
        now = self._clock()
        if self._cat_attempt is None or self._scan is not None or now-self._cat_attempt >= self.CATALOGUE_TTL:
            self._start('catalogue', self._scan_catalogue())

    def offer_hub_volume(self):
        """Offer catalogue, shared selected markets and hourly USD volumes only."""
        now = self._clock()
        source = self.surf.swarm_tokens_source(catalogue=self._catalogue if self._complete else None)
        tokens = self._tokens(source, now, include_inactive=True)
        self.offer_catalogue()
        self._offer_enrichment(tokens, now, hub_volume=True)

    def _catalogue_source(self, tokens, source, now, *, portfolio=False):
        state = ('unavailable' if tokens is None else 'stale' if self._complete and self._cat_failed else
                 'partial' if not self._complete or self._scan is not None else
                 'stale' if now-(self._cat_as_of or 0) > self.CATALOGUE_TTL else 'ok')
        rows = self._catalogue_rows()
        result = {'state': state, 'as_of': self._cat_as_of if self._cat_as_of is not None else source.get('as_of'),
                  'complete': self._complete, 'loaded': len(rows if rows is not None else source.get('rows') or [])}
        if portfolio:
            unsupported = ambiguous = 0
            for row in self._base_rows(source) or []:
                artifacts, invalid = _token_artifacts(row)
                ambiguous += invalid
                unsupported += bool(artifacts) and row.get('chain_id') not in CHAINS
            reasons = []
            if unsupported:
                reasons.append(f'{unsupported} token launches on unsupported chains')
            if ambiguous:
                reasons.append(f'{ambiguous} token launches with ambiguous artifacts')
            if reasons and state == 'ok':
                result['state'] = 'partial'
            result.update(coverage_complete=state == 'ok' and not reasons,
                          candidates=len(tokens) if tokens is not None else None,
                          unsupported_candidates=unsupported if tokens is not None else None,
                          ambiguous_candidates=ambiguous if tokens is not None else None,
                          reasons=reasons)
        return result

    def catalogue_summary(self, source=None):
        """Cached live-token summary, plus volume across all launch statuses."""
        now = self._clock()
        source = source or {}
        tokens = self._tokens(source, now)
        catalogue = self._catalogue_source(tokens, source, now)
        latest = None
        if tokens is not None:
            latest = []
            for token in select_tokens(tokens, sort='newest')[:3]:
                launched = token['launched_at']
                latest.append(dict(age_s=now-launched if launched is not None and launched <= now else None,
                                   **{key: token[key] for key in ('symbol', 'chain', 'lp_state',
                                                                'liquidity_state', 'paired_symbol')}))
        return {'count': len(tokens) if tokens is not None else None,
                'state': catalogue['state'], 'as_of': catalogue['as_of'], 'latest_launches': latest,
                'volume': self._volume_summary(source, now, catalogue)}

    def _volume_summary(self, source, now, catalogue):
        """One fixed pool cohort per curve; missing hours stay gaps in its sums."""
        end = int(now//3600)*3600
        candidates = set()
        for row in self._base_rows(source) or []:
            artifacts, ambiguous = _token_artifacts(row)
            if ambiguous:
                candidates.add(('ambiguous', row['launch_id']))
            elif artifacts:
                candidates.add((row['chain_id'], next(iter(artifacts))))
        result = dict(points=None, state='unavailable', known=0, total=len(candidates),
                      as_of=None, until=float(end))
        pools, stamps, stale_stamps = {}, [], []
        for token in self._tokens(source, now, include_inactive=True) or []:
            point = self._volume.get(token['id'])
            if not point:
                continue
            payload, read_at = point
            if (payload.get('_pool') != token['market_pool'] or not token['market_pool']
                    or _number(read_at) is None or read_at > now or payload.get('state') != 'ok'):
                continue
            if (now-read_at > self.HISTORY_TTL or token['id'] in self._failed['volume']
                    or token['market_state'] != 'ok'):
                stale_stamps.append(read_at)
                continue
            hours = _volume_hours(payload, now)
            values = [hours.get(t) for t in range(end-86400, end, 3600)]
            if not any(all(v is not None for v in values[i:i+3]) for i in range(0, 24, 3)):
                continue
            key = (token['chain'], token['market_pool'])
            if key in pools:
                old, ids = pools[key]
                pools[key] = (old if old == values else None, ids+[token['id']])
            else:
                pools[key] = (values, [token['id']])
            stamps.append(read_at)
        cohort = [values for values, _ in pools.values() if values is not None]
        result['known'] = sum(len(ids) for values, ids in pools.values() if values is not None)
        points = []
        for start in range(0, 24, 3):
            values = [value for hours in cohort for value in hours[start:start+3]]
            total = sum(values) if values and all(v is not None for v in values) else None
            points.append(total if total is not None and math.isfinite(total) else None)
        if any(value is not None for value in points):
            result.update(points=points, as_of=min(stamps), state=(
                'ok' if result['known'] == result['total'] and catalogue['state'] == 'ok'
                and all(value is not None for value in points) else 'partial'))
        elif stale_stamps:
            result.update(state='stale', as_of=min(stale_stamps))
        return result

    def _offer_enrichment(self, tokens, now, *, hub_volume=False):
        tiers = [('markets', self.MARKET_TTL, self.MARKET_BATCH)]
        tiers += ([('volume', self.HISTORY_TTL, self.VOLUME_BATCH)] if hub_volume else [
            ('history', self.HISTORY_TTL, self.DETAIL_BATCH),
            ('trades', self.TRADES_TTL, self.DETAIL_BATCH)])
        for name, ttl, limit in tiers:
            attempts = self._attempts[name]
            due = [row for row in tokens or []
                   if (name == 'markets' or row.get('market_pool'))
                   and (row['id'] not in attempts or now-attempts[row['id']] >= ttl
                        or name == 'volume' and now//3600 > attempts[row['id']]//3600
                        or name == 'markets' and self._market_expectations.get(row['id']) != row.get('launch_pool')
                        or name != 'markets' and self._detail_pools[name].get(row['id']) != row['market_pool'])]
            due.sort(key=lambda row: (attempts.get(row['id'], -1), -row['launch_id']))
            if due:
                # Reserve half the existing budget for relevant wallet tokens;
                # the oldest-due remainder guarantees the market keeps moving.
                priority = [row for row in due if row['id'] in self._portfolio_priority_ids][:limit//2]
                chosen = {row['id'] for row in priority}
                batch = priority + [row for row in due if row['id'] not in chosen][:limit-len(priority)]
                self._start(name, self._refresh_markets(batch) if name == 'markets'
                            else self._refresh_details(name, batch))

    async def fetch_and_compute(self):
        """Existing live-launch market view, sharing Portfolio's refresh work."""
        return self._snapshot()

    async def fetch_portfolio(self, priority_ids=()):
        """Cached candidates on supported chains, including inactive launches.

        Artifacts identify candidates, not verified ERC-20 deployments. The
        wallet reader must still confirm balances and actual token decimals.
        No network is awaited here; catalogue and enrichment use shared tasks.
        """
        self._portfolio_active = True
        self._portfolio_priority_ids = set(priority_ids)
        return self._snapshot(portfolio=True)

    def _snapshot(self, *, portfolio=False):
        now = self._clock()
        source = self.surf.swarm_tokens_source(catalogue=self._catalogue if self._complete else None)
        tokens = self._tokens(source, now, include_inactive=portfolio)
        enrichment = tokens
        if self._portfolio_active:
            market_tokens = self._tokens(source, now) if portfolio else tokens
            candidates = tokens if portfolio else self._tokens(source, now, include_inactive=True)
            # Portfolio's stricter artifact validation must not stop refreshing
            # rows still displayed by the market. Schedule each identity once.
            enrichment = list({row['id']: row for population in (candidates, market_tokens)
                               for row in population or []}.values())
        self.offer_catalogue()
        self._offer_enrichment(enrichment, now)
        activity = {f"launch:{row['id']}:{row['launch_uuid']}":
                    {'id': f"launch:{row['id']}:{row['launch_uuid']}", 'token_id': row['id'],
                     'ts': row['launched_at'], 'kind': 'LAUNCH', 'amount': None, 'asset': ''}
                    for row in tokens or [] if row['launched_at'] is not None}
        for row in tokens or []:
            cached = self._trades.get(row['id'])
            if cached and cached[0].get('_pool') != row['market_pool']:
                cached = None
            for event in (cached[0].get('activity', []) if cached else []):
                if event.get('token_id') == row['id']:
                    activity[event['id']] = event
        sources = {'catalogue': self._catalogue_source(tokens, source, now, portfolio=portfolio)}
        for name, label in (('markets', 'market'), ('history', 'history'), ('trades', 'trades'), ('liquidity', 'liquidity')):
            states = [row[label+'_state'] for row in tokens or []]
            stamps = [row[label+'_read_at'] for row in tokens or [] if row[label+'_read_at'] is not None]
            known = sum(s == 'ok' for s in states)
            sources[name] = {'state': 'ok' if states and known == len(states) else 'partial' if known else
                            'stale' if 'stale' in states else states[0] if states and len(set(states)) == 1 and states[0] in ('unsupported', 'unindexed') else 'unavailable',
                             'as_of': min(stamps) if stamps else None, 'stale': states.count('stale'),
                             'known': known, 'total': len(states)}
        return deepcopy({'tokens': tokens, 'activity': sorted(activity.values(), key=lambda r: (-r['ts'], r['id']))[:200],
                         'as_of': now, 'is_mock': False, 'sources': sources})

    async def close(self):
        if self._closed:
            return
        self._closed = True
        for task in self._tasks.values():
            task.cancel()
        await self.wait_pending()
        if self._owns_client:
            await self.client.close()
        if self._owns_market:
            await self.market.close()
