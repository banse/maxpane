"""Small Boardroom-only reads; never populate a hidden dashboard's detail tier."""
import asyncio
import logging
from collections import Counter
from copy import deepcopy

from maxpane_dashboard.analytics import surf_pool4_depth
from maxpane_dashboard.analytics.surfboard import count
from maxpane_dashboard.data import surf_work as work
from maxpane_dashboard.data.surf_cache import (
    SLOT_CHANNEL, SLOT_ETH_USD, SLOT_MARKET, SLOT_POOL4, TIER_MEDIUM,
    TIER_TTL_SECONDS, TIER_FAILURE_BACKOFF_SECONDS,
)

log = logging.getLogger(__name__)


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


class SurfCardReader:
    def __init__(self, manager):
        self.manager = manager
        self.tasks = {}
        self.attempts = {}
        self.workflows = None
        self.workflows_ts = None
        self.current_jobs = {}
        self.current_ts = None
        self.current_failed = False
        self.current_complete = False
        self.pool = {}
        self.pool_ts = None
        self.pool_failed = False
        self.medium_due = {}
        self.discovery = None

    def offer(self, *, force=False):
        now = self.manager._clock()
        for name, read in (('work', self._work), ('current', self._current), ('pool4', self._pool), ('feed', self._feed),
                           ('market', self._market)):
            task = self.tasks.get(name)
            if task is not None and not task.done():
                continue
            if not force and now - self.attempts.get(name, -1e20) < 30:
                continue
            self.attempts[name] = now
            self.tasks[name] = asyncio.create_task(self._guard(read, name))

    async def _guard(self, read, name):
        try:
            async with asyncio.timeout(12):
                await read()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if name == 'pool4':
                self.pool_failed = True
            elif name == 'current':
                self.current_failed = True
            log.debug('Boardroom %s retained last observation: %s', name, exc)

    async def wait_pending(self):
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    async def _work(self):
        raw = await self.manager.swarm_client.fetch_workflows(limit=100)
        if not isinstance(raw, list):
            return
        rows, partial = work._page(raw, work._workflow, self.manager._clock())
        if len(rows) != len(raw):
            return
        self.workflows = None if partial else sum(row['status'] not in work.TERMINAL | {'blocked'} for row in rows)
        self.workflows_ts = self.manager._clock()

    async def _current(self):
        """One recent page plus at most 24 active details; no history or hidden board."""
        client = self.manager.swarm_client
        fence = client._monotonic()
        raw = await client.fetch_jobs(limit=100)
        if not isinstance(raw, list):
            self.current_failed = True
            return
        rows = {}
        complete = len(raw) <= 100
        for item in raw[:100]:
            row = work._job(item, self.manager._clock())
            if row is None:
                complete = False
            elif row['id'] in rows and rows[row['id']] != row:
                complete = False
            else:
                rows[row['id']] = row
        identities = list(dict.fromkeys(
            [key for key in self.current_jobs if key not in rows]
            + [key for key, row in rows.items() if row['state'] == 'executing']))
        complete &= len(identities) <= 24
        reads = await asyncio.gather(*(client.read_job_detail(key, fresh_after=fence)
                                      for key in identities[:24]))
        # An unread older active ID must remain eligible for the next bounded retry.
        jobs = {key: value for key, value in self.current_jobs.items() if key in identities[:24]}
        stamps = []
        for identity, read in zip(identities, reads):
            row = work._job(read.payload, self.manager._clock(), detail=True)
            if (row is None or row['id'] != identity or read.observed_at is None
                    or read.started_mono < fence or row['nodes'] is None):
                complete = False
                continue
            stamps.append(read.observed_at)
            if row['state'] == 'executing':
                jobs[identity] = dict(template=row['template'],
                    nodes=[dict(key=node['key'], state=node['state']) for node in row['nodes']])
            else:
                jobs.pop(identity, None)
        self.current_jobs = jobs
        self.current_ts = min(stamps, default=self.manager._clock())
        self.current_complete = complete
        self.current_failed = False

    def current_work(self, source):
        """A global count match is required before calling a bounded sample complete."""
        now = self.manager._clock()
        overview = (source.get('payload') or {}).get('overview') or {}
        expected = count((overview.get('job_states') or {}).get('executing'))
        source_ts = source.get('read_ts')
        fresh = (self.current_ts is not None and 0 <= now - self.current_ts <= 60
                 and type(source_ts) in (int, float) and 0 <= now - source_ts <= 60
                 and abs(self.current_ts - source_ts) <= 30
                 and source.get('state') == 'ok' and not self.current_failed)
        complete = fresh and self.current_complete and expected == len(self.current_jobs)
        facts = dict(state='ok' if complete else 'partial' if fresh else 'stale' if self.current_ts else 'unavailable',
                     read_ts=self.current_ts, node_counts=None, oracle_agents=None,
                     jobs_loaded=len(self.current_jobs), jobs_expected=expected,
                     reason='Current node coverage incomplete')
        if complete:
            nodes = [node for job in self.current_jobs.values() for node in job['nodes']
                     if node['state'] == 'working']
            facts['node_counts'] = dict(Counter(node['key'].replace('-', '_').split('_', 1)[0]
                                               for node in nodes))
            oracle = any(job['template'] is None or 'oracle' in job['template'].lower()
                         or any('oracle' in node['key'].lower() for node in job['nodes'])
                         for job in self.current_jobs.values())
            facts.update(oracle_agents=None if oracle else 0,
                         reason='API does not expose a complete live panel' if oracle else 'Complete current jobs; no oracle running')
        return facts

    def work_snapshot(self, source):
        payload = source.get('payload') or {}
        overview = payload.get('overview') or {}
        jobs = (overview.get('job_states') or {}).get('executing')
        result = self.manager._work_reader.project()
        result = dict(result, summary=dict.fromkeys(result['summary']))
        result['summary'].update(jobs=jobs, workflows=self.workflows)
        result.update(state=source.get('state', 'unavailable'), read_ts=source.get('read_ts'),
                      partial=True, details_loaded=None, details_expected=None)
        return result

    async def _medium(self, slot, read):
        """Per-source clocks: card reads cannot satisfy a hidden detail tier."""
        now = self.manager._clock()
        entry = self.manager.cache.get_last_good(slot)
        ttl = TIER_TTL_SECONDS[TIER_MEDIUM]
        if entry is not None and 0 <= now - entry.ts < ttl:
            return
        if now < self.medium_due.get(slot, -1e20):
            return
        # Set before awaiting, so cancellation/timeout also respects backoff.
        self.medium_due[slot] = now + TIER_FAILURE_BACKOFF_SECONDS[TIER_MEDIUM]
        result = await read()
        if result is not None:
            self.medium_due[slot] = self.manager._clock() + ttl

    async def _feed(self):
        await self._medium(SLOT_CHANNEL, lambda: self.manager._pool_channel(
            {TIER_MEDIUM}, self.manager._clock(), None))

    async def _market(self):
        from maxpane_dashboard.data.surf_cache import TIER_MEDIUM, SLOT_LAUNCHPAD
        manager = self.manager
        launch = getattr(manager.cache.get_last_good(SLOT_LAUNCHPAD), 'payload', None) or {}
        await asyncio.gather(
            self._medium(SLOT_MARKET, lambda: manager._pool_market(
                {TIER_MEDIUM}, manager._clock(), launch.get('pool_id'))),
            self._medium(SLOT_ETH_USD, lambda: manager._pool_eth_usd(
                {TIER_MEDIUM}, manager._clock())))

    async def _pool(self):
        from maxpane_dashboard.data.surf_manager import (
            IMD_TOKEN, POOL4_ADOPTED, POOL4_NETWORK_MAINNET,
            POOL4_NETWORK_SEPOLIA, POOL4_SEPOLIA_HOOK, POOL4_SEPOLIA_TOKEN,
        )
        manager = self.manager
        prior = getattr(manager.cache.get_last_good(SLOT_POOL4), 'payload', None) or {}
        channel = getattr(manager.cache.get_last_good(SLOT_CHANNEL), 'payload', None) or {}
        items = channel.get('items')
        now = manager._clock()
        if (self.discovery is None or self.discovery[0] != items
                or not 0 <= now - self.discovery[1] < TIER_TTL_SECONDS[TIER_MEDIUM]):
            discovery, _source = await manager._pool4_discovery(items, prior)
            # Cache only an established adoption; unknown never becomes a fact.
            self.discovery = ((deepcopy(items), now, discovery)
                              if _field(discovery, 'state') == POOL4_ADOPTED else None)
        else:
            discovery = self.discovery[2]
        adopted = _field(discovery, 'state') == POOL4_ADOPTED and _field(discovery, 'hook_addr')
        network = POOL4_NETWORK_MAINNET if adopted else POOL4_NETWORK_SEPOLIA
        hook_addr = _field(discovery, 'hook_addr') if adopted else POOL4_SEPOLIA_HOOK
        token = IMD_TOKEN if adopted else POOL4_SEPOLIA_TOKEN
        client = manager.pool4_client
        quote = await client.fetch_card_quote(hook_addr, network=network, token_addr=token)
        share, tick = _field(quote, 'share_price_wei'), _field(quote, 'tick')
        self.pool_failed = type(share) is not int or type(tick) is not int
        if type(share) is not int and type(tick) is not int:
            return
        identity = (network, hook_addr)
        if self.pool.get('identity') != identity:
            self.pool = {'identity': identity}
        if type(share) is int:
            self.pool['pool4_share_price'] = share / 1e18
            self.pool['share_ts'] = manager._clock()
        if type(tick) is int:
            self.pool['tick'] = tick
            self.pool['tick_ts'] = manager._clock()
        self.pool['pool4_network'] = network
        self.pool_ts = min(self.pool[key] for key in ('share_ts', 'tick_ts') if key in self.pool)

    def pool_snapshot(self):
        data = {key: value for key, value in self.pool.items() if key.startswith('pool4_')}
        quote = getattr(self.manager.cache.get_last_good(SLOT_ETH_USD), 'payload', None) or {}
        tick, eth_usd = self.pool.get('tick'), quote.get('eth_usd')
        if type(tick) is int and type(eth_usd) in (int, float) and eth_usd > 0:
            ratio = surf_pool4_depth.sqrt_ratio(tick) ** 2
            if ratio > 0:
                data['pool4_price_usd'] = eth_usd / ratio
        return data
