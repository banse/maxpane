"""Independent POOL4 burn stages: cold entry, cancellation and source clocks."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from tests.data.test_surf_manager_surfboard import manager

HOOK = '0x' + '11' * 20
IDENTITY = dict(network='MAINNET', hook=HOOK, executor='0x' + '22' * 20,
                token='0x' + '33' * 20, oft='0x' + '33' * 20, dst_eid=30184,
                receiver='0x' + '44' * 20, base_token='0x' + '55' * 20)


def queue(stamp=1000., identity=None):
    return dict(identity=copy.deepcopy(identity or IDENTITY), queue=dict(state='ok',
        read_ts=stamp, block=100, amount_wei=29 * 10**18, min_bridge_wei=0,
        bridge_amount_wei=29 * 10**18, decimals=18))


def history(stamp=1000.):
    return dict(state='ok', read_ts=stamp, from_block=1, to_block=100,
                complete=True, event=None)


def reader(m):
    r = Mock()
    r.fetch_queue = AsyncMock(return_value=queue())
    r.fetch_bridge = AsyncMock(return_value=history())
    r.fetch_base_burn = AsyncMock(return_value=history())
    m._pool4_burn_client = r
    return r


async def finish(m):
    # Queue completion offers two independent tasks; await each generation.
    await asyncio.gather(*list(m._hub_source_tasks.values()))
    await asyncio.gather(*list(m._hub_source_tasks.values()))


@pytest.mark.parametrize('view', ['pool4', 'pool4_user'])
async def test_cold_native_entry_offers_queue_before_slow_hook_bundle(manager, view):
    m, _ = manager
    r = reader(m)
    m.set_active_view(view)
    m._pool4_discovery = AsyncMock(return_value=(SimpleNamespace(state='adopted', hook_addr=HOOK), 'docs'))
    bundle_started = asyncio.Event()

    async def bundle(*a, **kw):
        bundle_started.set()
        await asyncio.Event().wait()

    m.pool4_client.fetch_state_bundle = bundle
    sweep = asyncio.create_task(m._pool_pool4(set(), 1000., [], refresh_current=True))
    try:
        await asyncio.sleep(0)
        if sweep.done():
            await sweep
        await asyncio.wait_for(bundle_started.wait(), 1)
        await finish(m)
        r.fetch_queue.assert_awaited_once_with('MAINNET', HOOK)
        data = m.get_snapshot()['pool4_burn_pipeline']
        assert data['queue']['amount_wei'] == 29 * 10**18
        assert data['base_burn']['complete'] is True
        m._cycle.assert_not_awaited()
        assert m._launchpad_task is None
    finally:
        sweep.cancel()
        await asyncio.gather(sweep, return_exceptions=True)
        await m.close()


async def test_queue_publishes_while_base_is_held_and_passive_reads_do_no_io(manager):
    m, clock = manager
    r = reader(m)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def held(identity):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    r.fetch_base_burn.side_effect = held
    m.set_active_view('pool4_user')
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await asyncio.wait_for(entered.wait(), 1)
        clock.now = 1010.
        data = m.get_snapshot()['pool4_burn_pipeline']
        assert data['queue']['read_ts'] == 1000.
        assert data.get('base_burn') is None
        assert m.is_loading('pool4_user')
        m.get_snapshot()
        r.fetch_queue.assert_awaited_once()
        r.fetch_base_burn.assert_awaited_once()
        m.set_active_view(None)
        await m.drain_reads()
        assert cancelled.is_set()
        assert not m.is_loading('pool4_user')
    finally:
        await m.close()


async def test_failure_keeps_source_clocks_and_backoff_does_not_block_siblings(manager):
    m, clock = manager
    r = reader(m)
    m.set_active_view('pool4')
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        first = copy.deepcopy(m.get_snapshot()['pool4_burn_pipeline'])
        clock.now = 1100.
        r.fetch_queue.return_value = None
        r.fetch_bridge.return_value = None
        r.fetch_base_burn.return_value = history(1100.)
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        data = m.get_snapshot()['pool4_burn_pipeline']
        assert data['queue'] == first['queue']
        assert data['bridge'] == first['bridge']
        assert data['base_burn']['read_ts'] == 1100.
        clock.now += 30
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        assert r.fetch_queue.await_count == 2
        assert r.fetch_bridge.await_count == 2
    finally:
        await m.close()


async def test_changed_executor_drops_old_history_and_rejects_late_reply(manager):
    m, clock = manager
    r = reader(m)
    m.set_active_view('pool4')
    entered, release = asyncio.Event(), asyncio.Event()
    previous_task = None

    async def late(identity):
        if identity['executor'] == IDENTITY['executor']:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()  # Deliberately misbehaving transport.
            return history(9999.)
        return None

    r.fetch_base_burn.side_effect = late
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await asyncio.wait_for(entered.wait(), 1)
        previous_task = m._hub_source_tasks['native_burn_base_burn']
        new = dict(IDENTITY, executor='0x' + '66' * 20)
        clock.now = 1031.
        r.fetch_queue.return_value = queue(clock.now, new)
        r.fetch_bridge.return_value = None
        m._offer_pool4_burn('MAINNET', HOOK)
        await m._hub_source_tasks['native_burn_queue']
        release.set()
        await previous_task
        await finish(m)
        data = m.get_snapshot()['pool4_burn_pipeline']
        assert data['identity'] == new
        assert data.get('base_burn') is None
        assert data.get('bridge') is None
    finally:
        release.set()
        await m.close()


async def test_pipeline_survives_restart_without_using_cache_to_start_network(manager, tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    m, clock = manager
    r = reader(m)
    m.set_active_view('pool4')
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        expected = m.get_snapshot()['pool4_burn_pipeline']
        m.save_cache()
        restored = SurfCache(path=m._cache_path, clock=lambda: clock.now)
        restored.load()
        assert restored.get_last_good('pool4_burn_pipeline').payload == expected
        m.cache = restored
        m.get_snapshot()
        r.fetch_queue.assert_awaited_once()
    finally:
        await m.close()


async def test_other_views_do_not_offer_pipeline_and_network_switch_clears_it(manager):
    m, _ = manager
    r = reader(m)
    try:
        m.set_active_view('surfboard')
        m._offer_pool4_burn('MAINNET', HOOK)
        r.fetch_queue.assert_not_awaited()
        m.set_active_view('pool4')
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        m._offer_pool4_burn('SEPOLIA', HOOK)
        assert m.get_snapshot()['pool4_burn_pipeline'] is None
        assert r.fetch_queue.await_count == 1
    finally:
        await m.close()


async def test_pipeline_poll_is_independent_of_slow_hook_history_and_channel(manager):
    m, clock = manager
    r = reader(m)
    m.set_active_view('pool4')
    async def held_channel(*args):
        await asyncio.Event().wait()
    m._pool_channel = held_channel
    m._spawn_pool4_stakers = Mock()
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        clock.now += 31
        r.fetch_queue.return_value = queue(clock.now)
        await m._collect_visible_detail('pool4', clock.now)
        await m._hub_source_tasks['native_burn_queue']
        assert r.fetch_queue.await_count == 2
        assert m.get_snapshot()['pool4_burn_pipeline']['queue']['read_ts'] == clock.now
    finally:
        await m.close()


@pytest.mark.parametrize('bad', [dict(identity=[]), dict(identity=dict(IDENTITY, hook=14))])
async def test_bad_persisted_identity_is_unknown_not_a_crash(manager, bad):
    m, clock = manager
    try:
        m.cache.store_last_good('pool4_burn_pipeline', bad, ts=clock.now)
        assert m.get_snapshot()['pool4_burn_pipeline'] is None
    finally:
        await m.close()


async def test_cancelled_queue_cannot_publish_after_reopening_same_view(manager):
    m, _ = manager
    r = reader(m)
    entered, release = asyncio.Event(), asyncio.Event()

    async def late(*args):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return queue()

    r.fetch_queue.side_effect = late
    m.set_active_view('pool4')
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await asyncio.wait_for(entered.wait(), 1)
        old = m._hub_source_tasks['native_burn_queue']
        m.set_active_view(None)
        m.set_active_view('pool4')
        release.set()
        await old
        assert m.get_snapshot()['pool4_burn_pipeline'] is None
        r.fetch_bridge.assert_not_awaited()
    finally:
        release.set()
        await m.close()


@pytest.mark.parametrize('observed', [dict(executor='0x'+'77'*20), dict(dst_eid=999),
                                    dict(receiver='0x'+'00'*20)])
async def test_observed_incompatible_binding_clears_old_evidence(manager, observed):
    m, clock = manager
    r = reader(m)
    m.set_active_view('pool4')
    try:
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        clock.now += 31
        r.fetch_queue.return_value = dict(observed_identity=observed, queue=None)
        m._offer_pool4_burn('MAINNET', HOOK)
        await finish(m)
        assert m.get_snapshot()['pool4_burn_pipeline'] is None
    finally:
        await m.close()


async def test_queue_deadline_keeps_observed_executor_change(manager, monkeypatch):
    from maxpane_dashboard.data.surf_pool4_burn import Pool4BurnClient
    m, clock = manager
    m.set_active_view('pool4')
    m.cache.store_last_good('pool4_burn_pipeline', queue(), ts=clock.now)
    entered = asyncio.Event()

    async def rpc(network, calls):
        if len(calls) == 2:
            return ['0x1', {'number': '0x101'}]
        if len(calls) == 1:
            return ['0x' + '0' * 24 + '6' * 40]
        entered.set()
        await asyncio.Event().wait()

    client = Pool4BurnClient(SimpleNamespace(_rpc_state_batch=rpc), clock=lambda: clock.now)
    client.fetch_bridge = AsyncMock(return_value=None)
    client.fetch_base_burn = AsyncMock(return_value=None)
    m._pool4_burn_client = client
    original = asyncio.wait_for

    async def deadline(awaitable, timeout):
        if timeout != 12.:
            return await original(awaitable, timeout)
        task = asyncio.create_task(awaitable)
        await entered.wait()
        task.cancel()
        try:
            return await task
        except asyncio.CancelledError:
            raise TimeoutError from None

    monkeypatch.setattr(asyncio, 'wait_for', deadline)
    try:
        clock.now += 31
        m._offer_pool4_burn('MAINNET', HOOK)
        await m._hub_source_tasks['native_burn_queue']
        assert m.get_snapshot()['pool4_burn_pipeline'] is None
    finally:
        await m.close()
