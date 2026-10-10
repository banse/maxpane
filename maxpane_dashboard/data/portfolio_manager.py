"""Nonblocking wallet reads over the retained SWARM TOKENS market provider."""
import asyncio
from copy import deepcopy
import math
import time

from maxpane_dashboard.analytics.surf_launch_checks import address, ZERO
from maxpane_dashboard.data.portfolio_models import BALANCE_KEYS
from maxpane_dashboard.data.surfboard import timestamp
from maxpane_dashboard.data.swarm_tokens_models import TOKEN_KEYS


def _source(state='pending', *, as_of=None, complete=False, **extra):
    return dict(state=state, as_of=as_of, complete=complete, **extra)


def _quantity(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


class PortfolioManager:
    is_mock = False
    BALANCE_TTL, CLAIM_TTL, PARTIAL_RETRY = 60, 120, 5
    BALANCE_BATCH = 64

    def __init__(self, market, wallet=None, *, balances=None, claims=None, clock=time.time):
        self.market, self._clock = market, clock
        if balances is None:
            from maxpane_dashboard.data.portfolio_balance_client import PortfolioBalanceClient
            balances = PortfolioBalanceClient(now_fn=clock)
            self._owns_balances = True
        else:
            self._owns_balances = False
        if claims is None:
            from maxpane_dashboard.data.portfolio_claims_client import PortfolioClaimsClient
            claims = PortfolioClaimsClient(clock=clock)
            self._owns_claims = True
        else:
            self._owns_claims = False
        self.balances, self.claims = balances, claims
        self._wallet, self._generation = None, 0
        self._tasks, self._active = set(), {}
        self._closed, self._error_count = False, 0
        self._reset()
        self.set_wallet(wallet)

    @property
    def wallet(self):
        return self._wallet

    def _reset(self):
        self._balances, self._balance_attempts, self._balance_failed = {}, {}, set()
        self._claim_payload, self._claim_attempt = None, None
        self._claim_failed = False

    def set_wallet(self, value):
        wallet = address(value) if value else None
        if value and wallet in (None, ZERO):
            return False
        if wallet == self._wallet:
            return False
        self._wallet = wallet
        self._generation += 1
        for task in self._tasks:
            task.cancel()
        self._active.clear()
        self._reset()
        return True

    def _start(self, name, coroutine):
        if self._closed or name in self._active and not self._active[name].done():
            coroutine.close()
            return
        task = asyncio.create_task(coroutine)
        self._active[name] = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_pending(self):
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    def _current(self, wallet, generation):
        return not self._closed and wallet == self.wallet and generation == self._generation

    async def _read_balances(self, wallet, generation, rows):
        try:
            result = await self.balances.read_balances(wallet, rows)
        except Exception:
            result = None
        if not self._current(wallet, generation):
            return
        for row in rows:
            key = row['id']
            point = result.get(key) if isinstance(result, dict) else None
            if point and point.get('balance_state') == 'ok' and _quantity(point.get('held_quantity')) is not None:
                self._balances[key] = deepcopy(point)
                self._balance_failed.discard(key)
            else:
                self._balance_failed.add(key)
        if self._balance_failed:
            self._error_count += 1

    async def _read_claims(self, wallet, generation):
        try:
            result = await self.claims.fetch_claims(wallet)
        except Exception:
            result = None
        if not self._current(wallet, generation):
            return
        if isinstance(result, dict):
            # Agent association and claims degrade independently.
            prior = self._claim_payload or {}
            result = deepcopy(result)
            sources = result.setdefault('sources', {})
            for field, name in (('allocations', 'claims'), ('agents', 'agents')):
                if result.get(field) is None and prior.get(field) is not None:
                    result[field] = deepcopy(prior[field])
                    old = (prior.get('sources') or {}).get(name) or {}
                    sources[name] = dict(old, state='stale', complete=False)
            self._claim_payload = result
            self._claim_failed = False
        else:
            self._claim_failed = True
            self._error_count += 1

    def _claim_snapshot(self, now):
        payload = deepcopy(self._claim_payload or dict(allocations=None, agents=None, sources={}))
        agents = payload['sources'].setdefault('agents', _source())
        stamp = agents.get('as_of')
        if self._claim_failed or stamp is not None and not 0 <= now-stamp <= self.CLAIM_TTL:
            agents.update(state='stale' if stamp is not None else 'unavailable', complete=False)
        source = payload['sources'].setdefault('claims', _source())
        failed = self._claim_failed or source.get('state') in ('stale', 'unavailable')
        allocations = payload.get('allocations') or []
        for allocation in allocations:
            stamp = allocation.get('claim_read_at')
            if failed or stamp is not None and not 0 <= now-stamp <= self.CLAIM_TTL:
                allocation['claim_read_state'] = 'stale'
        states = [row.get('claim_read_state') for row in allocations]
        stamp = source.get('as_of')
        expired_empty = not allocations and stamp is not None and not 0 <= now-stamp <= self.CLAIM_TTL
        if failed or expired_empty or 'stale' in states:
            state = 'partial' if not failed and 'ok' in states else 'stale' if stamp is not None else 'unavailable'
            source.update(state=state, complete=False)
        return payload

    def _claim_fields(self, allocations, complete):
        if not allocations:
            return dict(claimable_quantity=0 if complete else None,
                        claim_state='none' if complete else 'unavailable',
                        claim_read_state='ok' if complete else 'unavailable',
                        claim_read_at=None, locked_quantity=0 if complete else None,
                        claimed_quantity=0 if complete else None, unlock_at=None,
                        claim_reason=None if complete else 'Claim checks incomplete')
        unique = {}
        conflict = False
        for row in allocations:
            key = row.get('allocation_id')
            if key is None or key in unique and unique[key] != row:
                conflict = True
            else:
                unique[key] = row
        rows = list(unique.values())
        verified = not conflict and all(row.get('claim_read_state') in ('ok', 'stale') for row in rows)
        stale = any(row.get('claim_read_state') == 'stale' for row in rows)
        state = 'ready' if any(row.get('claim_state') == 'ready' for row in rows) else (
                'locked' if any(row.get('claim_state') == 'locked' for row in rows) else
                'claimed' if all(row.get('claim_state') == 'claimed' for row in rows) else 'none')
        values = [_quantity(row.get('claimable_quantity')) for row in rows]
        quantity = sum(values) if verified and all(v is not None for v in values) else None
        stamps = [row['claim_read_at'] for row in rows if row.get('claim_read_at') is not None]
        unlocks = [stamp for row in rows if (stamp := timestamp(row.get('unlock_at'))) is not None]
        result = dict(claimable_quantity=quantity, claim_state=state if verified else 'unavailable',
                      claim_read_state='stale' if verified and stale else 'ok' if verified else 'unavailable',
                      claim_read_at=min(stamps) if stamps else None, unlock_at=min(unlocks) if unlocks else None,
                      claim_reason='Conflicting allocation records' if conflict else next(
                          (row['claim_reason'] for row in rows if row.get('claim_reason')), None))
        for field in ('locked_quantity', 'claimed_quantity'):
            amounts = [_quantity(row.get(field)) for row in rows]
            result[field] = sum(amounts) if all(v is not None for v in amounts) else None
        return result

    async def fetch_and_compute(self):
        now, wallet, generation = self._clock(), self.wallet, self._generation
        if wallet is None:
            return dict(tokens=[], activity=[], as_of=now, is_mock=False, wallet=None,
                        agents=[], wallet_generation=generation, sources={})
        priorities = [key for key, row in self._balances.items() if row.get('held_quantity', 0) > 0]
        for row in (self._claim_payload or {}).get('allocations') or []:
            contract = address(row.get('token_address'))
            if contract and (_quantity(row.get('claimable_quantity')) or 0) > 0:
                priorities.append(f"{row.get('chain_id')}:{contract}")
        try:
            market = await self.market.fetch_portfolio(priority_ids=priorities)
        except Exception:
            market = dict(tokens=None, activity=[], sources={'catalogue': _source('unavailable')})
        if not self._current(wallet, generation):
            raise asyncio.CancelledError('obsolete portfolio market snapshot')
        sources = deepcopy(market.get('sources') or {})
        catalogue = sources.get('catalogue') or _source()
        claims = self._claim_snapshot(now)
        claim_source = claims['sources']['claims']
        allocations = {}
        for row in claims.get('allocations') or []:
            contract = address(row.get('token_address'))
            if contract and contract != ZERO:
                allocations.setdefault(f"{row.get('chain_id')}:{contract}", []).append(row)
        rows = deepcopy(market.get('tokens'))
        if rows is None and allocations:
            rows = []
        if rows is not None:
            existing = {row['id'] for row in rows}
            # Earned launches can arrive before the paginated catalogue; preserve
            # verified claim-only membership and enrich when discovery catches up.
            for key, points in allocations.items():
                point = points[0]
                chain = {1: 'eth', 8453: 'base', 4663: 'rh'}.get(point.get('chain_id'))
                if key not in existing and chain and point.get('launch_uuid'):
                    token = dict.fromkeys(TOKEN_KEYS)
                    token.update(id=key, chain=chain, chain_id=point['chain_id'], token_address=point['token_address'],
                                 launch_uuid=point['launch_uuid'], launch_id=point.get('launch_id'),
                                 symbol=point.get('symbol') or '—', name=point.get('name') or '—',
                                 market_state='pending', history_state='pending', liquidity_state='unknown', lp_state='unknown')
                    rows.append(token)
            for row in rows:
                key = row['id']
                balance = deepcopy(self._balances.get(key))
                if balance is None:
                    balance = dict.fromkeys(BALANCE_KEYS)
                    balance['balance_state'] = 'unavailable' if key in self._balance_failed else 'pending'
                elif key in self._balance_failed or not 0 <= now-(balance.get('balance_read_at') or 0) <= self.BALANCE_TTL:
                    balance['balance_state'] = 'stale'
                row.update(balance)
                row.update(self._claim_fields(allocations.get(key, []), claim_source.get('complete', False)))
                row.update(held_cost_usd=None, basis_state='unavailable', basis_read_at=None,
                           basis_quantity=None, basis_source=None, basis_reason='Cost basis unavailable')
            due = [row for row in rows if row['id'] not in self._balance_attempts
                   or now-self._balance_attempts[row['id']] >= self.BALANCE_TTL]
            due.sort(key=lambda row: (self._balance_attempts.get(row['id'], -1), row['id']))
            if due and not ('balances' in self._active and not self._active['balances'].done()):
                batch = due[:self.BALANCE_BATCH]
                for row in batch:
                    self._balance_attempts[row['id']] = now
                self._start('balances', self._read_balances(wallet, generation, batch))
        current = [row for row in rows or [] if row['balance_state'] == 'ok']
        stamps = [row['balance_read_at'] for row in rows or [] if row.get('balance_read_at') is not None]
        covered = bool(catalogue.get('coverage_complete', catalogue.get('complete'))) and catalogue.get('state') == 'ok'
        complete = rows is not None and len(current) == len(rows) and covered
        balance_state = ('ok' if complete else 'partial' if current else 'stale' if stamps else
                         'unavailable' if self._balance_failed else 'pending')
        sources['balances'] = _source(balance_state, as_of=min(stamps) if stamps else None,
            complete=complete, checked=len(current), total=len(rows) if rows is not None else None,
            positives=sum(row['held_quantity'] > 0 for row in current),
            zeros=sum(row['held_quantity'] == 0 for row in current))
        sources.update(claims['sources'])
        sources['basis'] = _source('unavailable', reason='No verified remaining-position cost basis')
        interval = self.CLAIM_TTL if claim_source.get('complete') else self.PARTIAL_RETRY
        if self._claim_attempt is None or now-self._claim_attempt >= interval:
            self._claim_attempt = now
            self._start('claims', self._read_claims(wallet, generation))
        return deepcopy(dict(tokens=rows, activity=market.get('activity') or [], as_of=now,
                    is_mock=False, wallet=wallet, agents=claims.get('agents'),
                    wallet_generation=generation, sources=sources))

    async def close(self):
        if self._closed:
            return
        self._closed = True
        for task in self._tasks:
            task.cancel()
        await self.wait_pending()
        if self._owns_balances:
            await self.balances.close()
        if self._owns_claims:
            await self.claims.close()
