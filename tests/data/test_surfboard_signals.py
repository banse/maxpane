"""Boardroom offers every detector source without entering a native board."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.analytics.surf_signals import SIGNAL_NAMES
from maxpane_dashboard.data.surf_cache import SLOT_CHANNEL, SLOT_SWARM_LAUNCHES
from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from tests.data.test_surf_manager import FakeSurfClient, _launchpad_state
from tests.data.test_surf_manager_surfboard import manager
from tests.surf_swarm_fixtures import swarm_capture_v2


@pytest.fixture
def signals_manager(manager):
    m, clock = manager
    clock.now = 1_800_000_000.0
    m.client = FakeSurfClient()
    state = _launchpad_state()
    m.client.fetch_launchpad_getters = AsyncMock(return_value={name: getattr(state, name)
        for name in ('coin_count', 'imd_to_burn_wei', 'executor_balance_wei',
                     'min_bridge_wei', 'bridge_amount_wei', 'creator_eth_owed_wei')})
    m.swarm_client.fetch_launches = AsyncMock(return_value=swarm_capture_v2('launches')['launches'])
    m._card_reader._feed = SurfCardReader._feed.__get__(m._card_reader)
    m._pool_swarm_launches = AsyncMock(side_effect=AssertionError('full launch enrichment'))
    m._pool_nft = AsyncMock(side_effect=AssertionError('unrelated NFT statistics'))
    m.set_hub_seats([None] * 4)
    m.set_active_view('surfboard')
    return m, clock


async def test_cold_boardroom_offers_all_eleven_signal_inputs(signals_manager):
    m, clock = signals_manager
    try:
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        data = m._card_reader.signal_snapshot({}, now=clock.now)
        assert {name: data[f'sig_{name}_state'] for name in SIGNAL_NAMES}.keys() == set(SIGNAL_NAMES)
        assert all(data[f'sig_{name}_state'] in ('ok', 'watch', 'fired') for name in SIGNAL_NAMES), data
        assert {'fetch_nonces', 'fetch_chain_state', 'fetch_channel_txs', 'fetch_dev_activity',
                'fetch_recent_logs', 'fetch_pool_v4', 'fetch_launchpad',
                'fetch_decoy_pool_count'} <= set(m.client.calls)
        m.client.fetch_launchpad_getters.assert_awaited_once()
        m.swarm_client.fetch_launches.assert_awaited_once()
        m._cycle.assert_not_awaited()
        m._pool_nft.assert_not_awaited()
        m._pool_swarm_launches.assert_not_awaited()
        assert m._card_reader.signal_source(now=clock.now) == {'state': 'ok', 'read_ts': clock.now}
        card = next(card for card in m.get_hub_snapshot()['surfboard_cards'] if card['key'] == 'announce')
        assert card['denominator'] == 11 and '11/11 detectors known' in card['detail']
    finally:
        await m.close()


async def test_signal_snapshots_never_offer_reads_or_freshen_observation_clocks(signals_manager):
    m, clock = signals_manager
    try:
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        first = m._card_reader.signal_snapshot({}, now=clock.now)
        source = m._card_reader.signal_source(now=clock.now)
        calls = list(m.client.calls)
        baseline = deepcopy(m.cache.get_baselines())
        clock.now += 10
        second = m._card_reader.signal_snapshot({}, now=clock.now)
        assert second['sig_hot_state'] == first['sig_hot_state']
        assert m.cache.get_baselines() == baseline
        assert m.client.calls == calls
        assert m._card_reader.signal_source(now=clock.now) == source
    finally:
        await m.close()


async def test_slow_history_does_not_hold_up_other_detector_sources(signals_manager):
    m, clock = signals_manager
    started = asyncio.Event()
    async def blocked(resume=None):
        started.set()
        await asyncio.Event().wait()
    m.client.fetch_launchpad = blocked
    try:
        await m.fetch_hub_snapshot()
        await started.wait()
        await asyncio.gather(*(task for name, task in m._card_reader.tasks.items() if name != 'signals-history'))
        data = m._card_reader.signal_snapshot({}, now=clock.now)
        for name in set(SIGNAL_NAMES) - {'hot'}:
            assert data[f'sig_{name}_state'] in ('ok', 'watch', 'fired'), (name, data)
        assert data['sig_hot_state'] is None
        assert m._card_reader.signal_source(now=clock.now)['state'] == 'partial'
        task = m._card_reader.tasks['signals-history']
        m.set_active_view(None)
        await m.drain_reads()
        assert task.cancelled()
    finally:
        await m.close()


async def test_changed_announce_nonce_reloads_channel_before_medium_ttl(signals_manager):
    from dataclasses import replace
    m, clock = signals_manager
    try:
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        clock.now += 30
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert m.cache.get_last_good(SLOT_CHANNEL).payload['nonce'] == 14
        m.client._returns['fetch_nonces'] = replace(m.client._returns['fetch_nonces'], announce=15)
        clock.now += 30
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        clock.now += 30
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert m.cache.get_last_good(SLOT_CHANNEL).payload['nonce'] == 15
    finally:
        await m.close()


async def test_failed_signal_sources_retain_baselines_and_original_clocks(signals_manager):
    m, clock = signals_manager
    try:
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        m._card_reader.signal_snapshot({}, now=clock.now)
        baselines = deepcopy(m.cache.get_baselines())
        launches = deepcopy(m.cache.get_last_good(SLOT_SWARM_LAUNCHES))
        for name in ('fetch_nonces', 'fetch_chain_state', 'fetch_recent_logs', 'fetch_dev_activity',
                     'fetch_launchpad', 'fetch_pool_v4', 'fetch_decoy_pool_count', 'fetch_channel_txs'):
            m.client._returns[name] = None
        m.client.fetch_launchpad_getters.return_value = None
        m.swarm_client.fetch_launches.return_value = None
        clock.now += 600
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        m._card_reader.signal_snapshot({}, now=clock.now)
        assert m.cache.get_baselines() == baselines
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCHES) == launches
        assert m._card_reader.signal_source(now=clock.now)['state'] != 'ok'
    finally:
        await m.close()
