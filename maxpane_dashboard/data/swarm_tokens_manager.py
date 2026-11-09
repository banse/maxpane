"""Nonblocking live SWARM TOKENS adapter; borrows SURF's launch evidence.

Catalogue createdAt is launch-record time, not a proven deployment block time.
Retained observations keep independent successful clocks; no demo values enter here.
"""
import asyncio
from copy import deepcopy
import math
from pathlib import Path
import time

from maxpane_dashboard.analytics.surf_launch_checks import ZERO, address
from maxpane_dashboard.analytics.swarm_tokens import select_tokens
from maxpane_dashboard.data.surf_swarm import launch_rows
from maxpane_dashboard.data.series_points import coerce_points
from maxpane_dashboard.data.swarm_tokens_client import SwarmTokensClient
from maxpane_dashboard.data.swarm_tokens_models import TOKEN_KEYS
from maxpane_dashboard.data.swarm_tokens_cache import SwarmTokensCache

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
    PROVENANCE_BATCH, PROVENANCE_RETRY = 3, 60

    def __init__(self, surf_manager, *, client=None, market=None, clock=time.time, cache_path=None):
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
        self._task_token_ids = {}
        self._closed = False
        self._market, self._history, self._trades, self._volume = {}, {}, {}, {}
        self._market_expectations = {}
        self._price_baselines = {}
        self._first_launch = {}
        self._attempts = {name: {} for name in ('markets', 'history', 'trades', 'volume')}
        self._failed = {name: set() for name in self._attempts}
        self._detail_pools = {'history': {}, 'trades': {}, 'volume': {}}
        self._portfolio_active = False
        self._portfolio_priority_ids = set()
        self._active_view = 'legacy'
        self._retired = set()
        self._provenance_attempts = {}
        parent_path = getattr(getattr(surf_manager, 'cache', None), 'path', None)
        if cache_path is None and parent_path:
            cache_path = Path(parent_path).with_name('swarm_tokens_cache.json')
        self._cache = SwarmTokensCache(cache_path)
        retained = self._cache.load(clock())
        self._catalogue = retained.get('catalogue')
        self._cat_as_of = retained.get('cat_as_of')
        self._complete = retained.get('complete', False)
        self._cat_attempt = self._cat_as_of if self._complete else None
        for kind in ('market', 'history', 'trades', 'volume'):
            values = retained.get(kind, {})
            setattr(self, '_' + kind, values)
            name = 'markets' if kind == 'market' else kind
            self._attempts[name] = {key: point[1] for key, point in values.items()}
            if kind == 'market':
                self._market_expectations = {key: point[0].get('_expected_pool') for key, point in values.items()}
            else:
                self._detail_pools[name] = {key: point[0].get('_pool') for key, point in values.items()}
        self._catalogue_generation = 0
        self._source_revision = self._source_generation = self._source_cached = None
        self._base_input = self._base_cached = self._indexed_base = None
        self._identity_rows = {}
        self._enriched_source, self._enriched_index = None, {}
        self._enrichment_mode = None
        self._selected_id = None
        self._dependent_details = set()

    def _save(self):
        self._cache.save(dict(version=1, catalogue=self._catalogue, cat_as_of=self._cat_as_of,
                              complete=self._complete, market=self._market, history=self._history,
                              trades=self._trades, volume=self._volume), self._clock())

    def reader_offer_only(self, view):
        return True

    def _source(self):
        revision = getattr(self.surf, 'swarm_tokens_source_revision', None)
        current = tuple(revision()) if callable(revision) else None
        if (current is not None and self._source_revision is not None
                and len(current) == len(self._source_revision)
                and all(a is b for a, b in zip(current, self._source_revision))
                and self._source_generation == self._catalogue_generation):
            return self._source_cached
        source = self.surf.swarm_tokens_source(catalogue=self._catalogue if self._complete else None)
        if source != self._source_cached:
            self._source_cached = source
        self._source_revision, self._source_generation = current, self._catalogue_generation
        return self._source_cached

    def set_active_view(self, view):
        if view == self._active_view:
            return
        self._active_view = view
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
                self._retired.add(task)
        self._tasks.clear()
        self._task_token_ids.clear()
        self._portfolio_active = view == 'portfolio'
        self._enrichment_mode = None
        self._selected_id = None
        self._dependent_details.clear()

    async def drain_reads(self):
        if self._retired:
            await asyncio.gather(*self._retired, return_exceptions=True)
            self._retired.clear()

    def _start(self, name, coroutine, *, token_ids=()):
        if (self._closed or self._active_view is None or self._retired
                or name in self._tasks and not self._tasks[name].done()):
            coroutine.close()
            return
        self._tasks[name] = asyncio.create_task(coroutine)
        self._task_token_ids[name] = frozenset(token_ids)
        if name in self._detail_pools:
            self._tasks[name].add_done_callback(lambda _: self._resume_details(name))

    def _resume_details(self, name):
        if name in self._dependent_details:
            self._dependent_details.discard(name)
            self._offer_dependent(only=name)

    def is_loading(self, view: str | None = None, *, token_id: str | None = None) -> bool:
        """Observe accepted tasks, optionally scoped to one selected deployment."""
        if self._closed:
            return False
        names = ('catalogue', 'markets', 'volume') if view == 'surfboard' else self._tasks
        return any(task is not None and not task.done() and not task.cancelling()
                   and (token_id is None or name == 'catalogue' or name != 'volume'
                        and token_id in self._task_token_ids.get(name, ()))
                   for name in names for task in (self._tasks.get(name),))

    async def wait_pending(self):
        """Observable completion seam for offline tests and one-shot live captures."""
        while pending := [task for task in self._tasks.values() if not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

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
                self._catalogue_generation += 1
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
        finally:
            # A cold catalogue completes between polls. Start its missing
            # provenance now; passive UI projections must never schedule I/O.
            self._save()
            if not asyncio.current_task().cancelling():
                self._offer_provenance()
                self._offer_dependent()

    def _catalogue_rows(self):
        if self._scan:
            merged = {row['id']: row for row in self._catalogue or []}
            merged.update(self._scan)
            return list(merged.values())
        return self._catalogue

    def _base_rows(self, source):
        raw = self._catalogue_rows()
        if raw is None:
            return source.get('rows')
        if raw != self._base_input:
            self._base_input, self._base_cached = deepcopy(raw), launch_rows(raw)
        return self._base_cached

    def _tokens(self, source, now, *, include_inactive=False, selected_id=None):
        base = self._base_rows(source)
        if base is None:
            return None
        if source is not self._enriched_source:
            self._enriched_source = source
            self._enriched_index = {row['launch_id']: row for row in source.get('rows') or []}
        enriched = self._enriched_index
        result = {}
        if base is not self._indexed_base:
            self._indexed_base = base
            self._ordered_rows = sorted(base, key=lambda r: (r.get('status') == 'live',
                                        r.get('launch_number') or -1), reverse=True)
            self._identity_rows = {}
            for row in self._ordered_rows:
                artifacts, _ = _token_artifacts(row)
                for contract in artifacts:
                    self._identity_rows.setdefault(f"{row.get('chain_id')}:{contract}", []).append(row)
        # A selected identity uses the same representative and alias order.
        population = self._ordered_rows if selected_id is None else self._identity_rows.get(selected_id, [])
        for row in population:
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
                    # Newly verified provenance may confirm the very pool
                    # already quoted. Keep that observation and its clock;
                    # a different or withdrawn identity still invalidates it.
                    if not token['launch_pool'] or point[0].get('market_pool') != token['launch_pool']:
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
        # The existing token budget is split over at most three independent
        # chains. Cancellation drains every child before another offer starts.
        async with asyncio.TaskGroup() as group:
            for chain in dict.fromkeys(token.get('chain') for token in tokens):
                if chain in CHAINS.values():
                    batch = [token for token in tokens if token.get('chain') == chain]
                    group.create_task(self._refresh_market_batch(batch))

    async def _refresh_market_batch(self, batch):
        previous_pools = {token['id']: self._market.get(token['id'], ({},))[0].get('market_pool')
                          for token in batch}
        for token in batch:
            self._attempts['markets'][token['id']] = self._clock()
            self._market_expectations[token['id']] = token.get('launch_pool')
            baseline = self._price_baselines.get(token['id'])
            if baseline and baseline[0][0] != token.get('launch_pool'):
                self._price_baselines.pop(token['id'])
        try:
            await self._refresh_market_chain(batch)
        except asyncio.CancelledError:
            for token in batch:
                self._attempts['markets'].pop(token['id'], None)
            raise
        self._save()
        new_pools = [token for token in batch if
                     (pool := self._market.get(token['id'], ({},))[0].get('market_pool'))
                     and pool != previous_pools[token['id']]]
        if not new_pools:
            return
        # Coalesce newly discovered pools while an existing bounded detail
        # batch is busy; its completion offers one bounded follow-up.
        for name, pools in self._detail_pools.items():
            task = self._tasks.get(name)
            if task is not None and not task.done() and any(
                    (pool := self._market.get(token['id'], ({},))[0].get('market_pool'))
                    and pools.get(token['id']) != pool for token in new_pools):
                self._dependent_details.add(name)
        self._offer_dependent()

    async def _refresh_market_chain(self, tokens):
        try:
            response = await self.market.fetch_markets(tokens)
        except Exception:
            response = None
        for token in tokens:
            key = token['id']
            point = response.get(key) if isinstance(response, dict) else None
            if point is not None and point.get('state') not in ('unavailable', 'error'):
                direction = None
                identity = (token.get('launch_pool'), point.get('market_pool'), point.get('market_source'))
                baseline = self._price_baselines.get(key)
                if point.get('market_pool') and baseline and baseline[0] != identity:
                    self._price_baselines.pop(key)
                    baseline = None
                price = _number(point.get('price_usd'))
                if point.get('state') == 'ok' and identity[1] and price is not None and price > 0:
                    if baseline:
                        direction = 'up' if price > baseline[1] else 'down' if price < baseline[1] else 'flat'
                    self._price_baselines[key] = (identity, price)
                self._market[key] = (dict(point, _expected_pool=token.get('launch_pool'),
                                         _price_direction=direction), self._clock())
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
            except asyncio.CancelledError:
                self._attempts[name].pop(key, None)
                raise
            except Exception:
                point = None
            if point is not None and point.get('state') not in ('unavailable', 'error'):
                cache[key] = (dict(point, _pool=token.get('market_pool')), self._clock())
                self._failed[name].discard(key)
            else:
                self._failed[name].add(key)
        self._save()

    def _offer_dependent(self, *, only=None):
        """Use newly published inputs without scheduling another catalogue scan."""
        if self._closed or self._active_view is None or self._retired or self._enrichment_mode is None:
            return
        now = self._clock()
        source = self._source()
        view = self._active_view
        if self._selected_id is not None:
            tokens = self._tokens(source, now, include_inactive=True, selected_id=self._selected_id)
            self._offer_enrichment(tokens, now, only=only)
        elif self._enrichment_mode in ('markets', 'volume'):
            tokens = self._tokens(source, now, include_inactive=True)
            self._offer_enrichment(tokens, now, markets_only=self._enrichment_mode == 'markets',
                                   hub_volume=self._enrichment_mode == 'volume', only=only)
        elif view in ('legacy', 'SWARM TOKENS', 'portfolio'):
            tokens = self._tokens(source, now)
            if self._portfolio_active:
                candidates = self._tokens(source, now, include_inactive=True)
                tokens = list({row['id']: row for group in (tokens, candidates) for row in group or []}.values())
            self._offer_enrichment(tokens, now, only=only)
        elif str(view).startswith('token:'):
            tokens = self._tokens(source, now, include_inactive=True, selected_id=view[6:])
            self._offer_enrichment(tokens, now, only=only)

    def offer_catalogue(self):
        """Schedule only catalogue discovery."""
        now = self._clock()
        if self._cat_attempt is None or self._scan is not None or now-self._cat_attempt >= self.CATALOGUE_TTL:
            self._start('catalogue', self._scan_catalogue())

    def offer_hub_volume(self):
        """Offer catalogue, shared selected markets and hourly USD volumes only."""
        now = self._clock()
        self._selected_id = None
        source = self._source()
        tokens = self._tokens(source, now, include_inactive=True)
        self.offer_catalogue()
        self._offer_enrichment(tokens, now, hub_volume=True)

    def offer_hub_markets(self):
        """Offer only shared catalogue and bounded selected-market reads."""
        now = self._clock()
        self._selected_id = None
        source = self._source()
        self.offer_catalogue()
        self._offer_enrichment(self._tokens(source, now, include_inactive=True), now, markets_only=True)

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
        """Cached live-token summary and shipped deployments across all statuses."""
        now = self._clock()
        source = source or {}
        tokens = self._tokens(source, now)
        catalogue = self._catalogue_source(tokens, source, now)
        shipped = self._tokens(source, now, include_inactive=True)
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
                'shipped': dict(count=len(shipped) if shipped is not None else None,
                                state=catalogue['state'], as_of=catalogue['as_of']),
                'volume': self._volume_summary(source, now, catalogue),
                'turnover': self._turnover_summary(source, now, catalogue),
                'ranking': self._ranking_summary(source, now, catalogue)}

    def _turnover_summary(self, source, now, catalogue):
        """Rolling USD volume of every launched token, once per selected pool."""
        base = self._base_rows(source)
        result = dict(value=None, state='unavailable', known=0, total=None, as_of=None)
        if base is None:
            return result
        candidates = set()
        for row in base:
            artifacts, ambiguous = _token_artifacts(row)
            if ambiguous:
                candidates.add(('ambiguous', row['launch_id']))
            elif artifacts:
                candidates.add((row['chain_id'], next(iter(artifacts))))
        result['total'] = len(candidates)
        pools = {}
        for token in self._tokens(source, now, include_inactive=True) or []:
            value, stamp = _number(token['volume_24h']), _number(token['market_read_at'])
            if (value is None or value < 0 or stamp is None or not 0 <= now-stamp <= self.MARKET_TTL or not token['market_pool']
                    or token['market_state'] != 'ok'):
                continue
            key = (token['chain'], token['market_pool'])
            if key in pools:
                previous, ids, clock = pools[key]
                pools[key] = (previous if previous == value else None,
                              ids + [token['id']], min(clock, stamp))
            else:
                pools[key] = (value, [token['id']], stamp)
        quotes = [point for point in pools.values() if point[0] is not None]
        result['known'] = sum(len(ids) for _, ids, _ in quotes)
        complete = result['known'] == result['total'] and catalogue['state'] == 'ok'
        if quotes or complete:
            value = sum(point[0] for point in quotes)
            if math.isfinite(value):
                result.update(value=value, state='ok' if complete else 'partial',
                              as_of=min(point[2] for point in quotes) if quotes else catalogue['as_of'])
        return result

    def _ranking_summary(self, source, now, catalogue):
        """Rank canonical launches; retain independent successful source clocks."""
        tokens = self._tokens(source, now, include_inactive=True)
        result = dict(rows=None, newest=None, latest=None, state='unavailable',
                      read_ts=catalogue['as_of'], known=0, total=None)
        if tokens is None:
            return result
        incomplete = False
        for row in self._base_rows(source) or []:
            if row.get('chain_id') not in CHAINS:
                continue
            artifacts, ambiguous = _token_artifacts(row)
            if ambiguous:
                incomplete = True
                continue
            stamp = _number(row.get('created_ts'))
            if artifacts and stamp is not None and stamp > 0:
                key = f"{row['chain_id']}:{next(iter(artifacts))}"
                self._first_launch[key] = min(stamp, self._first_launch.get(key, stamp))
        launched = []
        for token in tokens:
            stamp = self._first_launch.get(token['id'])
            if stamp is None:
                incomplete = True
            elif stamp <= now:
                launched.append(dict(token, launched_at=stamp))
        launched.sort(key=lambda t: (-t['launched_at'], t['id']))

        def launch_fields(token):
            return dict(id=token['id'], age_s=now-token['launched_at'],
                        symbol=token['symbol'], chain=token['chain'])

        if launched:
            result['newest'] = launch_fields(launched[0])
        result['latest'] = [dict(launch_fields(token), price_direction=(
            self._market.get(token['id'], ({},))[0].get('_price_direction')
            if token['market_state'] == 'ok' and catalogue['state'] != 'stale' else None))
            for token in launched[:3]]
        eligible = [t for t in launched if 0 <= now-t['launched_at'] < 86400]
        result['total'] = len(eligible)
        fresh, stale = [], []
        stamps = [catalogue['as_of']] if _number(catalogue['as_of']) is not None else []
        for token in eligible:
            volume, stamp = _number(token['volume_24h']), _number(token['market_read_at'])
            if (volume is None or volume < 0 or stamp is None or not 0 < stamp <= now
                    or not token['market_pool'] or token['market_state'] not in ('ok', 'stale')):
                continue
            row = dict(launch_fields(token), volume_usd=volume, price_direction=None)
            if token['market_state'] == 'ok':
                row['price_direction'] = self._market[token['id']][0].get('_price_direction')
                fresh.append(row)
            else:
                stale.append(row)
            stamps.append(stamp)
        result['known'] = len(fresh)
        if fresh or stale:
            # Rotating quote batches must not replace leaders with lower-volume
            # fresh rows. Keep cached volume evidence and qualify its age.
            chosen = fresh + stale
            chosen.sort(key=lambda r: (-r['volume_usd'], r['age_s'], r['id']))
            result['rows'] = chosen[:3]
            result['state'] = ('stale' if stale or catalogue['state'] == 'stale' else
                               'ok' if len(fresh) == len(eligible) and not incomplete
                               and catalogue['state'] == 'ok' else 'partial')
        elif not eligible:
            result['state'] = ('stale' if catalogue['state'] == 'stale' else
                               'partial' if incomplete or catalogue['state'] != 'ok' else 'ok')
            if not incomplete and catalogue['complete']:
                result['rows'] = []
        if catalogue['state'] == 'stale':
            for row in result['rows'] or []:
                row['price_direction'] = None
        result['read_ts'] = min(stamps) if stamps else None
        return result

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

    def _offer_provenance(self, tokens=None):
        read = getattr(self.surf, 'refresh_swarm_token_evidence', None)
        task = self._tasks.get('provenance')
        if (not callable(read) or self._closed or self._retired
                or self._active_view not in ('SWARM TOKENS', 'legacy')
                or task is not None and not task.done()):
            return
        now = self._clock()
        if tokens is None:
            source = self.surf.swarm_tokens_source(catalogue=self._catalogue_rows())
            tokens = self._tokens(source, now)
        raw = {row['id']: row for row in self._catalogue_rows() or []}
        due = []
        for token in tokens or []:
            row = raw.get(token['launch_uuid'])
            if (row is None or token['verdict'] not in ('unknown', 'partial')
                    or _token_artifacts(row)[1]):
                continue
            version = (row.get('status'), row.get('updatedAt'),
                       row.get('chainId'), token['token_address'])
            prior_version, attempted = self._provenance_attempts.get(row['id'], (None, -1))
            attempted = attempted if version == prior_version else -1
            if attempted == -1 or now - attempted >= self.PROVENANCE_RETRY:
                due.append((attempted, -row['launchNumber'], row, version, token['id']))
        due.sort(key=lambda candidate: candidate[:2])
        batch = due[:self.PROVENANCE_BATCH]
        if batch:
            self._start('provenance', self._refresh_provenance(read, deepcopy(batch)),
                        token_ids=(candidate[4] for candidate in batch))

    async def _refresh_provenance(self, read, batch):
        for _, _, row, version, _ in batch:
            self._provenance_attempts[row['id']] = (version, self._clock())
        try:
            await read([candidate[2] for candidate in batch])
        except asyncio.CancelledError:
            for _, _, row, _, _ in batch:
                self._provenance_attempts.pop(row['id'], None)
            raise
        except Exception:
            # Keep last-good facts and let the bounded retry queue advance.
            self._error_count += 1

    def _offer_enrichment(self, tokens, now, *, hub_volume=False, markets_only=False, only=None):
        self._enrichment_mode = 'markets' if markets_only else 'volume' if hub_volume else 'all'
        tiers = [('markets', self.MARKET_TTL, self.MARKET_BATCH)]
        tiers += ([] if markets_only else [('volume', self.HISTORY_TTL, self.VOLUME_BATCH)] if hub_volume else [
            ('history', self.HISTORY_TTL, self.DETAIL_BATCH),
            ('trades', self.TRADES_TTL, self.DETAIL_BATCH)])
        for name, ttl, limit in tiers:
            if only is not None and name != only:
                continue
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
                            else self._refresh_details(name, batch),
                            token_ids=(row['id'] for row in batch))

    async def fetch_and_compute(self):
        """Existing live-launch market view, sharing Portfolio's refresh work."""
        await self.drain_reads()
        return self._snapshot()

    def get_snapshot(self):
        """Read completed cache data without offering catalogue or enrichment work."""
        return self._snapshot(offer=False)

    def get_portfolio_snapshot(self):
        """Retained wallet universe without scheduling catalogue or market reads."""
        return self._snapshot(portfolio=True, offer=False)

    async def fetch_selected_token(self, token_id, *, launch_uuid=None):
        """Offer existing cache work for exactly one identity; no overview mode change."""
        token = self.get_selected_token(token_id, launch_uuid=launch_uuid)
        await self.drain_reads()
        self._selected_id = token_id
        if not str(self._active_view).startswith('token:'):
            self.offer_catalogue()
        if token is not None:
            self._offer_enrichment([token], self._clock())
        return token

    def get_selected_token(self, token_id, *, launch_uuid=None):
        """Project one immutable identity from cache without offering network work."""
        now = self._clock()
        source = self._source()
        tokens = self._tokens(source, now, include_inactive=True, selected_id=token_id)
        token = next((row for row in tokens or [] if row['id'] == token_id
                      and (launch_uuid is None or row['launch_uuid'] == launch_uuid)), None)
        if token is None:
            return None
        if self._catalogue_source(tokens, source, now)['state'] == 'stale':
            for name in ('market', 'history', 'trades', 'liquidity'):
                if token.get(name + '_read_at') is not None:
                    token[name + '_state'] = 'stale'
        return deepcopy(token)

    async def fetch_portfolio(self, priority_ids=()):
        """Cached candidates on supported chains, including inactive launches.

        Artifacts identify candidates, not verified ERC-20 deployments. The
        wallet reader must still confirm balances and actual token decimals.
        No network is awaited here; catalogue and enrichment use shared tasks.
        """
        await self.drain_reads()
        self._portfolio_active = True
        self._portfolio_priority_ids = set(priority_ids)
        return self._snapshot(portfolio=True)

    def _snapshot(self, *, portfolio=False, offer=True):
        now = self._clock()
        source = self._source()
        tokens = self._tokens(source, now, include_inactive=portfolio)
        enrichment = tokens
        if self._portfolio_active:
            market_tokens = self._tokens(source, now) if portfolio else tokens
            candidates = tokens if portfolio else self._tokens(source, now, include_inactive=True)
            # Portfolio's stricter artifact validation must not stop refreshing
            # rows still displayed by the market. Schedule each identity once.
            enrichment = list({row['id']: row for population in (candidates, market_tokens)
                               for row in population or []}.values())
        if offer:
            self._selected_id = None
            self.offer_catalogue()
            self._offer_enrichment(enrichment, now)
            if not portfolio:
                self._offer_provenance(tokens)
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
        await self.drain_reads()
        for task in self._tasks.values():
            task.cancel()
        await self.wait_pending()
        self._save()
        if self._owns_client:
            await self.client.close()
        if self._owns_market:
            await self.market.close()
