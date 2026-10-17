"""Small Boardroom-only reads; never populate a hidden dashboard's detail tier."""
import asyncio
import logging

from maxpane_dashboard.analytics import surf_pool4_depth
from maxpane_dashboard.data import surf_work as work
from maxpane_dashboard.data.surf_cache import SLOT_CHANNEL, SLOT_ETH_USD, SLOT_POOL4

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
        self.pool = {}
        self.pool_ts = None
        self.pool_failed = False

    def offer(self, *, force=False):
        now = self.manager._clock()
        for name, read in (('work', self._work), ('pool4', self._pool), ('feed', self._feed),
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

    async def _feed(self):
        from maxpane_dashboard.data.surf_cache import TIER_MEDIUM
        await self.manager._pool_channel({TIER_MEDIUM}, self.manager._clock(), None)

    async def _market(self):
        from maxpane_dashboard.data.surf_cache import TIER_MEDIUM, SLOT_LAUNCHPAD
        manager = self.manager
        launch = getattr(manager.cache.get_last_good(SLOT_LAUNCHPAD), 'payload', None) or {}
        await asyncio.gather(manager._pool_market({TIER_MEDIUM}, manager._clock(), launch.get('pool_id')),
                             manager._pool_eth_usd({TIER_MEDIUM}, manager._clock()))

    async def _pool(self):
        from maxpane_dashboard.data.surf_manager import (
            IMD_TOKEN, POOL4_ADOPTED, POOL4_NETWORK_MAINNET,
            POOL4_NETWORK_SEPOLIA, POOL4_SEPOLIA_HOOK, POOL4_SEPOLIA_TOKEN,
        )
        manager = self.manager
        prior = getattr(manager.cache.get_last_good(SLOT_POOL4), 'payload', None) or {}
        channel = getattr(manager.cache.get_last_good(SLOT_CHANNEL), 'payload', None) or {}
        discovery, _source = await manager._pool4_discovery(channel.get('items'), prior)
        adopted = _field(discovery, 'state') == POOL4_ADOPTED and _field(discovery, 'hook_addr')
        network = POOL4_NETWORK_MAINNET if adopted else POOL4_NETWORK_SEPOLIA
        hook_addr = _field(discovery, 'hook_addr') if adopted else POOL4_SEPOLIA_HOOK
        token = IMD_TOKEN if adopted else POOL4_SEPOLIA_TOKEN
        client = manager.pool4_client
        hook = await client.fetch_hook_state(hook_addr, network=network, token_addr=token)
        recipient = _field(hook, 'rewards_recipient')
        pool_id, pool_manager = _field(hook, 'pool_id'), _field(hook, 'pool_manager')
        async def vault():
            path = await client.resolve_vault_path(recipient, network=network) if recipient else None
            address = (path or {}).get('vault')
            return await client.fetch_vault_state(address, network=network) if address else None
        async def price():
            return await client.fetch_pool_slot0(pool_id, network=network, pool_manager=pool_manager) if pool_id and pool_manager else None
        vault_state, pool_state = await asyncio.gather(vault(), price())
        share, tick = _field(vault_state, 'share_price_wei'), _field(pool_state, 'tick')
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
