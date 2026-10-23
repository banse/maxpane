"""ONCHAIN bounds optional Launchpad history while retaining current values."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surf_manager
from maxpane_dashboard.data.surf_cache import SLOT_LAUNCHPAD, TIER_LAUNCHPAD
from tests.data.test_surf_entry_refresh import current_launchpad
from tests.data.test_surf_manager import _pool_v4_state
from tests.data.test_surf_manager_pool4 import _manager


async def test_onchain_history_budget_publishes_getters_and_yields_with_backoff(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    m.set_active_view('dashboard')
    monkeypatch.setattr(surf_manager, 'ONCHAIN_LAUNCHPAD_BUDGET_S', .05, raising=False)
    m.client.fetch_pool_v4 = AsyncMock(return_value=_pool_v4_state())
    m.client.fetch_launchpad_getters = AsyncMock(return_value=current_launchpad(coin_count=99))
    cancelled = asyncio.Event()
    progress = object()

    async def history(**kwargs):
        m.client._launchpad_pending = progress
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    m.client.fetch_launchpad = history
    try:
        stamp = m._clock()
        task = m._spawn_launchpad({TIER_LAUNCHPAD}, stamp)
        await asyncio.wait_for(task, 1)
        assert cancelled.is_set()
        current = m.cache.get_last_good(SLOT_LAUNCHPAD)
        assert current.payload['coin_count'] == 99
        assert current.ts == stamp
        assert current.payload.get('swaps_by_coin') is None
        assert m.client._launchpad_pending is progress
        assert m.cache.last_fetch_ts(TIER_LAUNCHPAD) is None
        assert m.cache.last_failure_ts(TIER_LAUNCHPAD) is not None
        assert not m.cache.is_due(TIER_LAUNCHPAD, m._clock())
        assert not m.is_loading('dashboard')
        assert m._spawn_launchpad(set(m.cache.tiers_due(m._clock())), m._clock()) is None
        m.client.fetch_launchpad_getters.assert_awaited_once()
    finally:
        await m.close()


@pytest.mark.parametrize('view', ['dashboard', 'launchpad'])
async def test_only_onchain_bounds_history_and_old_observation_clock_is_retained(tmp_path, monkeypatch, view):
    m = _manager(tmp_path)
    m.set_active_view(view)
    monkeypatch.setattr(surf_manager, 'ONCHAIN_LAUNCHPAD_BUDGET_S', .05, raising=False)
    old = m._clock() - 500
    m.cache.store_last_good(SLOT_LAUNCHPAD, {'coin_count': 1, 'swaps_by_coin': {'old': 7}}, ts=old)
    m.client.fetch_pool_v4 = AsyncMock(return_value=_pool_v4_state())
    m.client.fetch_launchpad_getters = AsyncMock(return_value=current_launchpad(coin_count=99))
    entered, release = asyncio.Event(), asyncio.Event()

    async def history(*args, **kwargs):
        entered.set()
        await release.wait()

    m._pool_launchpad = history
    try:
        task = m._spawn_launchpad({TIER_LAUNCHPAD}, m._clock())
        await asyncio.wait_for(entered.wait(), 1)
        if view == 'dashboard':
            await asyncio.wait_for(task, 1)
            point = m.cache.get_last_good(SLOT_LAUNCHPAD)
            assert point.payload['coin_count'] == 99
            assert point.payload['swaps_by_coin'] == {'old': 7}
            assert point.ts == old
        else:
            # Longer than the shortened ONCHAIN budget, without cancelling history.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), .1)
            assert not task.done()
            m.client.fetch_launchpad_getters.assert_not_awaited()
    finally:
        release.set()
        await m.close()
