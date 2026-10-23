"""Native re-entry refreshes current values without expiring retained history."""
import asyncio
import copy
from dataclasses import asdict, replace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_cache import SLOT_LAUNCHPAD, SLOT_POOL4, TIER_LAUNCHPAD, TIER_POOL4
from tests.data.test_surf_manager import _launchpad_state, _pool_v4_state
from tests.data.test_surf_manager_pool4 import (
    FLOW_LOGS_FULL, HOOK_BLOCK, HOOK_STATE, FakePool4Client, RECONCILED, UNCHECKED, _manager,
)
from tests.data.test_surf_launchpad_getters import GETTERS


def current_launchpad(**changes):
    state = asdict(_launchpad_state(**changes))
    return {field: state[field] for field, _, _ in GETTERS}


@pytest.mark.parametrize('view', ['pool4', 'pool4_user', 'launchpad'])
async def test_native_reentry_offers_getters_when_history_tier_is_fresh(tmp_path, view):
    m = _manager(tmp_path)
    tier = TIER_LAUNCHPAD if view == 'launchpad' else TIER_POOL4
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    try:
        if view == 'launchpad':
            await m._pool_launchpad({tier}, m._clock())
            async def getters():
                calls.append('getters')
                entered.set()
                await release.wait()
                return current_launchpad(coin_count=999)
            m.client.fetch_launchpad_getters = getters
        else:
            await m._pool_pool4({tier}, m._clock(), None)
            original = m.pool4_client.fetch_state_bundle
            async def getters(*args, **kwargs):
                calls.append('getters')
                entered.set()
                await release.wait()
                return await original(*args, **kwargs)
            m.pool4_client.fetch_state_bundle = getters
        observed = m.cache.last_fetch_ts(tier)
        m._clock_double.advance(30)
        m.set_active_view('surfboard')
        m.set_active_view(view)
        assert not m.cache.is_due(tier, m._clock())
        due_in = m.cache.seconds_until_due(tier, m._clock())
        m._card_reader._market = AsyncMock()
        await asyncio.wait_for(m._fetch_visible_detail(), 1)
        await asyncio.wait_for(entered.wait(), 1)
        assert m._force_view is False
        await m._fetch_visible_detail()
        assert calls == ['getters']
        release.set()
        await m._full_task
        await (m._launchpad_task if view == 'launchpad' else m._pool4_task)
        assert m.cache.last_fetch_ts(tier) == observed
        assert m.cache.seconds_until_due(tier, m._clock()) == due_in
    finally:
        release.set()
        await m.close()


async def test_pool4_entry_refresh_retains_history_clock_and_clears_cross_block_verdict(tmp_path):
    m = _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL))
    try:
        await m._pool_pool4({TIER_POOL4}, m._clock(), None)
        before = copy.deepcopy(m.cache.get_last_good(SLOT_POOL4))
        assert before.payload['counter_state'] == RECONCILED
        m._clock_double.advance(30)
        updated = replace(HOOK_STATE, block_number=HOOK_BLOCK + 2,
                          tokens_in_pool_wei=HOOK_STATE.tokens_in_pool_wei + 123)
        m.pool4_client._returns['fetch_hook_state'] = updated
        m._pool4_logs = AsyncMock(side_effect=AssertionError('fresh history was refetched'))
        m._pool4_drip_read = AsyncMock(side_effect=AssertionError('fresh drip history was refetched'))
        await m._pool_pool4(set(), m._clock(), None, refresh_current=True)
        after = m.cache.get_last_good(SLOT_POOL4)
        assert after.payload['tokens_in_pool_wei'] == updated.tokens_in_pool_wei
        assert after.payload['block_number'] == HOOK_BLOCK + 2
        for field in ('flow', 'unsettled_burn', 'unsettled_stakers', 'dripped_imd',
                      'drip_window_seconds', 'drip_seconds_per_block', 'drip_from_block', 'drip_to_block'):
            assert after.payload[field] == before.payload[field]
        assert after.payload['counter_state'] == UNCHECKED
        assert after.ts == before.ts
        assert m.cache.last_fetch_ts(TIER_POOL4) == before.ts
        m._pool4_logs.assert_not_awaited()
        m._pool4_drip_read.assert_not_awaited()
    finally:
        await m.close()


@pytest.mark.parametrize('failure', ['transport', 'partial', 'empty_at_block'])
async def test_pool4_entry_failed_getters_do_not_retime_history_or_mix_atomic_fields(tmp_path, failure):
    m = _manager(tmp_path)
    try:
        await m._pool_pool4({TIER_POOL4}, m._clock(), None)
        before = copy.deepcopy(m.cache.get_last_good(SLOT_POOL4))
        m._clock_double.advance(30)
        due_in = m.cache.seconds_until_due(TIER_POOL4, m._clock())
        if failure != 'transport':
            bundle = await m.pool4_client.fetch_state_bundle(
                before.payload['hook_addr'], network=before.payload['network'],
                token_addr=before.payload['token_addr'])
            if failure == 'partial':
                bundle['hook'] = replace(HOOK_STATE, block_number=HOOK_BLOCK + 2)
                bundle['vault'] = None
            else:
                for field in ('hook', 'dripper', 'vault'):
                    state = bundle[field]
                    bundle[field] = replace(state, **{key: None for key in state.__dataclass_fields__
                                                      if key != 'block_number'})
            m.pool4_client.fetch_state_bundle = AsyncMock(return_value=bundle)
        else:
            m.pool4_client.fetch_state_bundle = AsyncMock(return_value=None)
        m._pool4_logs = AsyncMock(side_effect=AssertionError('history called after getter failure'))
        await m._pool_pool4(set(), m._clock(), None, refresh_current=True)
        after = m.cache.get_last_good(SLOT_POOL4)
        assert after.ts == before.ts
        assert m.cache.last_fetch_ts(TIER_POOL4) == before.ts
        assert m.cache.seconds_until_due(TIER_POOL4, m._clock()) == due_in
        if failure == 'partial':
            assert before.payload['share_price_wei'] is not None
            assert after.payload['share_price_wei'] is None
            assert after.payload['total_assets_wei'] is None
            assert after.payload['flow'] == before.payload['flow']
        else:
            assert after.payload == before.payload
        m._pool4_logs.assert_not_awaited()
    finally:
        await m.close()


async def test_pool4_entry_changed_binding_cannot_carry_prior_history(tmp_path):
    m = _manager(tmp_path, pool4_client=FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL))
    entered, release = asyncio.Event(), asyncio.Event()
    task = None
    try:
        await m._pool_pool4({TIER_POOL4}, m._clock(), None)
        previous = m.cache.get_last_good(SLOT_POOL4)
        prior = copy.deepcopy(previous.payload)
        assert m.cache.get_pool4_accumulator(prior['network'])['genesis_block'] is not None
        prior['hook_addr'] = '0x' + '12' * 20
        assert prior['flow']
        m.cache.store_last_good(SLOT_POOL4, prior, ts=previous.ts)
        m._clock_double.advance(30)
        original = m._pool4_logs
        async def history(*args):
            entered.set()
            await release.wait()
            return await original(*args)
        m._pool4_logs = history
        task = asyncio.create_task(m._pool_pool4(set(), m._clock(), None, refresh_current=True))
        await asyncio.wait_for(entered.wait(), 1)
        staged = m.cache.get_last_good(SLOT_POOL4)
        assert staged.payload['hook_addr'] != prior['hook_addr']
        assert staged.payload['flow'] is None
        assert staged.payload['dripped_imd'] is None
        assert staged.payload['unsettled_burn'] is None
        assert staged.payload['counter_state'] == UNCHECKED
        assert staged.ts == m._clock()
        assert m.cache.get_pool4_accumulator(prior['network'])['genesis_block'] is None
    finally:
        release.set()
        if task is not None:
            await task
        await m.close()


@pytest.mark.parametrize('failed', [False, True])
async def test_launchpad_entry_refresh_keeps_cursor_history_and_observation_clock(tmp_path, failed):
    m = _manager(tmp_path)
    try:
        await m._pool_launchpad({TIER_LAUNCHPAD}, m._clock())
        prior = copy.deepcopy(m.cache.get_last_good(SLOT_LAUNCHPAD))
        m._clock_double.advance(30)
        readings = current_launchpad(coin_count=999, imd_to_burn_wei=0)
        if failed:
            readings = {field: None for field in readings}
            m.client.fetch_pool_v4 = AsyncMock(return_value=None)
        m.client.fetch_launchpad_getters = AsyncMock(return_value=readings)
        m.client.fetch_launchpad = AsyncMock(side_effect=AssertionError('history was refetched'))
        m.client.fetch_decoy_pool_count = AsyncMock(side_effect=AssertionError('decoys were refetched'))
        await m._pool_launchpad(set(), m._clock(), refresh_current=True)
        after = m.cache.get_last_good(SLOT_LAUNCHPAD)
        assert after.ts == prior.ts
        assert m.cache.last_fetch_ts(TIER_LAUNCHPAD) == prior.ts
        expected = dict(prior.payload)
        if not failed:
            expected.update(coin_count=999, imd_to_burn_wei=0)
        assert after.payload == expected
        m.client.fetch_launchpad_getters.assert_awaited_once_with()
        m.client.fetch_launchpad.assert_not_awaited()
        m.client.fetch_decoy_pool_count.assert_not_awaited()
    finally:
        await m.close()


async def test_launchpad_entry_new_real_pool_drops_prior_decoy_identity(tmp_path):
    m = _manager(tmp_path)
    try:
        await m._pool_launchpad({TIER_LAUNCHPAD}, m._clock())
        prior = copy.deepcopy(m.cache.get_last_good(SLOT_LAUNCHPAD))
        assert prior.payload['decoy_pool_count'] is not None
        m._clock_double.advance(30)
        pool = _pool_v4_state(pool_id='0x' + '34' * 32)
        m.client.fetch_pool_v4 = AsyncMock(return_value=pool)
        m.client.fetch_launchpad_getters = AsyncMock(return_value=current_launchpad())
        m.client.fetch_decoy_pool_count = AsyncMock(side_effect=AssertionError('decoys were refetched'))
        await m._pool_launchpad(set(), m._clock(), refresh_current=True)
        after = m.cache.get_last_good(SLOT_LAUNCHPAD)
        assert after.payload['pool_id'] == pool.pool_id
        assert after.payload['decoy_pool_count'] is None
        assert after.payload['decoy_newest_fee_bps'] is None
        assert after.payload['cursor'] == prior.payload['cursor']
        assert after.ts == prior.ts
        assert m.cache.last_fetch_ts(TIER_LAUNCHPAD) == prior.ts
        m.client.fetch_decoy_pool_count.assert_not_awaited()
    finally:
        await m.close()


@pytest.mark.parametrize('view', ['pool4', 'launchpad'])
async def test_native_entry_keeps_full_sweep_when_history_is_due(tmp_path, view):
    m = _manager(tmp_path)
    try:
        if view == 'launchpad':
            m.client.fetch_launchpad_getters = AsyncMock(side_effect=AssertionError('entry path bypassed full history'))
            await m._pool_launchpad({TIER_LAUNCHPAD}, m._clock(), refresh_current=True)
            assert 'fetch_launchpad' in m.client.calls
            assert 'fetch_decoy_pool_count' in m.client.calls
            m.client.fetch_launchpad_getters.assert_not_awaited()
            assert m.cache.last_fetch_ts(TIER_LAUNCHPAD) == m._clock()
        else:
            await m._pool_pool4({TIER_POOL4}, m._clock(), None, refresh_current=True)
            assert 'fetch_flow_logs' in m.pool4_client.calls
            assert 'fetch_swap_logs' in m.pool4_client.calls
            assert m.cache.last_fetch_ts(TIER_POOL4) == m._clock()
    finally:
        await m.close()
