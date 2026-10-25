"""Bounded Boardroom detector inputs, independent of native dashboard collectors."""
import asyncio

from maxpane_dashboard.data import surf_swarm as swarm
from maxpane_dashboard.data.surf_cache import (
    SLOT_ACTIVITY, SLOT_CHANNEL, SLOT_LAUNCHPAD, SLOT_LOGS, SLOT_SWARM_LAUNCHES,
    TIER_MEDIUM, TIER_SLOW, TIER_LAUNCHPAD, TIER_SWARM_LAUNCHES,
    TIER_TTL_SECONDS, TIER_FAILURE_BACKOFF_SECONDS,
)


class SurfCardSignals:
    def __init__(self, reader):
        self.reader, self.manager = reader, reader.manager
        self.points, self.next_read, self.failed = {}, {}, set()
        self.cursor = None
        self.all_known = False

    def readers(self, *, force=False):
        return [(f'signals-{name}', lambda name=name: self.read(name, force=force))
                for name in ('chain', 'logs', 'activity', 'getters', 'decoy', 'history', 'launches')]

    def _tier(self, name):
        return {'logs': TIER_MEDIUM, 'feed': TIER_MEDIUM, 'activity': TIER_SLOW, 'decoy': TIER_LAUNCHPAD,
                'history': TIER_LAUNCHPAD, 'launches': TIER_SWARM_LAUNCHES}.get(name)

    async def read(self, name, *, force=False):
        now = self.manager._clock()
        if not force and now < self.next_read.get(name, -1e20):
            return
        tier = self._tier(name)
        self.next_read[name] = now + TIER_FAILURE_BACKOFF_SECONDS.get(tier, 30)
        try:
            ok = await getattr(self, '_' + name)()
        except BaseException:
            self.failed.add(name)
            raise
        if ok:
            self.failed.discard(name)
            self.next_read[name] = self.manager._clock() + TIER_TTL_SECONDS.get(tier, 30)
        else:
            self.failed.add(name)

    def _publish(self, name, value):
        self.points[name] = (value, float(self.manager._clock()))

    def _value(self, name):
        return self.points.get(name, (None, None))[0] if name not in self.failed else None

    def nonce(self, name='announce'):
        from .surf_manager import _field, _opt_int
        return _opt_int(_field((self._value('chain') or {}).get('nonces'), name))

    async def wait_chain(self):
        task = self.reader.tasks.get('signals-chain')
        if task is not None and not task.done():
            try:
                # A slow state provider must not prevent independent HTTP reads.
                await asyncio.wait_for(asyncio.shield(task), timeout=3)
            except TimeoutError:
                pass

    async def _chain(self):
        value = await self.manager._pool_chain(self.manager._clock())
        if value['nonces'] is not None or value['state'] is not None:
            self._publish('chain', value)
            return True
        return False

    async def _logs(self):
        return await self.manager._pool_logs({TIER_MEDIUM}, self.manager._clock()) is not None

    async def _activity(self):
        await self.wait_chain()
        return await self.manager._pool_activity({TIER_SLOW}, self.manager._clock(),
            self.nonce('dev'), self.nonce('ops')) is not None

    async def _getters(self):
        value = await self.manager.client.fetch_launchpad_getters()
        if isinstance(value, dict) and any(type(value.get(key)) is int for key in
                ('imd_to_burn_wei', 'bridge_amount_wei')):
            self._publish('getters', value)
            return True
        return False

    async def _decoy(self):
        from .surf_manager import _field
        pool = await self.manager.client.fetch_pool_v4()
        identity = _field(pool, 'pool_id')
        if not isinstance(identity, str) or not identity:
            return False
        value = await self.manager.client.fetch_decoy_pool_count(identity)
        if isinstance(value, tuple) and len(value) == 2 and type(value[0]) is int and value[0] >= 0:
            self._publish('decoy', dict(decoy_pool_count=value[0],
                decoy_newest_fee_bps=value[1].get('fee') if isinstance(value[1], dict) else None))
            return True
        return False

    async def _history(self):
        prior = self.manager.cache.get_last_good(SLOT_LAUNCHPAD)
        cursor = self.cursor or (getattr(prior, 'payload', None) or {}).get('cursor')
        value = await self.manager.client.fetch_launchpad(resume=cursor)
        payload = self.manager._launchpad_payload(None, None, None, value)
        if payload.get('cursor') is not None:
            self.cursor = payload['cursor']
        if self.manager._swaps_by_coin(payload.get('swaps_by_coin')) is not None:
            self._publish('history', payload)
            return True
        return False

    async def _launches(self):
        manager = self.manager
        manager._swarm_launch_read_ok = False
        raw = await manager.swarm_client.fetch_launches()
        if not isinstance(raw, list):
            return False
        now = manager._clock()
        prior = manager.cache.get_last_good(SLOT_SWARM_LAUNCHES)
        slot = dict(getattr(prior, 'payload', None) or {}, launches=raw, launches_ts=now)
        clean = swarm.coerce_launches_slot(slot, now=now)
        if clean is None or len(clean['launches'] or []) != len(raw):
            return False
        manager.cache.store_last_good(SLOT_SWARM_LAUNCHES, clean, ts=now)
        manager._swarm_launch_read_ok = True
        return True

    def snapshot(self, data, *, now):
        from .surf_manager import _field, _opt_int, _tokens
        manager = self.manager
        chain = self._value('chain') or {}
        nonces, state = chain.get('nonces'), chain.get('state')
        values = dict(data, feed_nonce=self.nonce(),
            lp_liquidity=_opt_int(_field(state, 'lp_liquidity')),
            gate_open=manager._opt_bool(_field(state, 'identity_allowed')),
            imd_supply=_tokens(_field(state, 'imd_supply_wei')))
        launch_entry = manager.cache.get_last_good(SLOT_LAUNCHPAD)
        launch = dict(self._value('history') or getattr(launch_entry, 'payload', None) or {})
        launch.update(self._value('getters') or {})
        launch.update(self._value('decoy') or {})
        if 'getters' in self.failed:
            launch.update(imd_to_burn_wei=None, bridge_amount_wei=None)
        if 'decoy' in self.failed:
            launch.update(decoy_pool_count=None, decoy_newest_fee_bps=None)
        if 'history' in self.failed:
            launch['swaps_by_coin'] = None
        values.update(manager._launchpad_keys(launch, launch_entry, eth_usd=None))
        channel = getattr(manager.cache.get_last_good(SLOT_CHANNEL), 'payload', None) or {}
        activity = getattr(manager.cache.get_last_good(SLOT_ACTIVITY), 'payload', None)
        history_ts = self.points.get('history', (None, getattr(launch_entry, 'ts', None)))[1]
        rows = manager._swarm_launch_keys()['swarm_launch_rows']
        readings = manager._readings(values, nonces, channel,
            activity.get('rows') if activity else None, launch, launchpad_ts=history_ts,
            state=state, swarm_launch_events=manager._swarm_launch_events(rows))
        if 'logs' in self.failed:
            readings.update(bridge_mints=None, v4_hook_pools=None, identities_written=None)
        if 'activity' in self.failed:
            readings.update(burn_transfers=None, deploy_events=None)
        result = manager._signal_keys(readings, now)
        from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
        self.all_known = all(result.get(f'sig_{name}_state') in ('ok', 'watch', 'fired') for name in SIGNAL_NAMES)
        return result

    def source(self, *, now):
        stamps = {name: point[1] for name, point in self.points.items()}
        for name, slot in (('logs', SLOT_LOGS), ('activity', SLOT_ACTIVITY), ('feed', SLOT_CHANNEL)):
            stamps[name] = getattr(self.manager.cache.get_last_good(slot), 'ts', None)
        launches = self.manager.cache.get_last_good(SLOT_SWARM_LAUNCHES)
        stamps['launches'] = (getattr(launches, 'payload', None) or {}).get('launches_ts')
        expected = {'chain', 'logs', 'activity', 'feed', 'getters', 'decoy', 'history', 'launches'}
        known = [stamp for stamp in stamps.values() if stamp is not None]
        partial = not self.all_known or bool(self.failed) or any(stamps.get(name) is None for name in expected)
        stale = any(now - stamp > TIER_TTL_SECONDS.get(self._tier(name), 30)
                    for name, stamp in stamps.items() if stamp is not None)
        return dict(state='unavailable' if not known else 'partial' if partial else 'stale' if stale else 'ok',
                    read_ts=min(known, default=None))
