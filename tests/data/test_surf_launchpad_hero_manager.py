"""Native launchpad values and rack cards share captured observations."""
from unittest.mock import AsyncMock

from maxpane_dashboard.data.surf_cache import SLOT_LAUNCHPAD, SLOT_ETH_USD, TIER_LAUNCHPAD
from tests.data.test_surf_manager_surfboard import manager


def seed(m):
    slot = dict(coin_count=210, launch_count=210, new_24h=2, creator_count=64,
                swap_count=12400, trader_count=486, imd_to_burn_wei=250 * 10**18,
                executor_balance_wei=120 * 10**18, bridge_amount_wei=120 * 10**18,
                min_bridge_wei=100 * 10**18, creator_eth_owed_wei=842 * 10**14,
                burned_total_wei=15700 * 10**18,
                volume_2h=dict(state='ok', points_wei=[10**18] * 8,
                               read_ts=9990, head_ts=9990, until=9900, known=210, total=210))
    m.cache.store_last_good(SLOT_LAUNCHPAD, slot, ts=9990)
    m.cache.store_last_good(SLOT_ETH_USD, dict(eth_usd=2000, source='CoinGecko', provider_ts=None), ts=9995)
    return slot


async def test_hub_refreshes_getters_and_history_from_same_slot(manager):
    m, clock = manager
    clock.now = 10000
    slot = seed(m)
    try:
        data = m._project_hub()
        hero = data['surf_launchpad_hero']
        assert hero['coins'] == dict(state='ok', read_ts=9990, count=210, new_24h=2, swept=210)
        assert hero['fees']['eth'] == data['launchpad_creator_eth_owed'] == .0842
        assert hero['burned']['imd'] == data['launchpad_burned_total'] == 15700
        assert hero['queue']['sendable'] == data['burn_bridgeable'] == 120
        assert hero['queue']['ready'] is data['burn_ready'] is True
        assert hero['volume']['usd'] == 16000 and hero['volume']['points'] == [2000] * 8
        m.cache.store_last_good(SLOT_LAUNCHPAD, dict(slot, bridge_amount_wei=0,
            creator_eth_owed_wei=0, burned_total_wei=16000 * 10**18), ts=10000)
        changed = m._project_hub()
        assert changed['surf_launchpad_hero']['queue']['ready'] is changed['burn_ready'] is False
        assert changed['surf_launchpad_hero']['fees']['eth'] == changed['launchpad_creator_eth_owed'] == 0
        assert changed['surf_launchpad_hero']['burned']['imd'] == changed['launchpad_burned_total'] == 16000
        m._cycle.assert_not_awaited()
    finally:
        await m.close()


async def test_launchpad_failure_and_market_expiry_keep_independent_states(manager):
    m, clock = manager
    clock.now = 10000
    seed(m)
    try:
        clock.now = 10100
        expired = m._project_hub()['surf_launchpad_hero']
        assert expired['fees']['state'] == 'ok' and expired['coins']['state'] == 'ok'
        assert expired['volume']['state'] == 'unavailable' and expired['volume']['usd'] is None
        m.cache.store_last_good(SLOT_ETH_USD, dict(eth_usd=2000, source='CoinGecko', provider_ts=None), ts=10100)
        m.cache.mark_failed(TIER_LAUNCHPAD, 10100)
        stale = m._project_hub()['surf_launchpad_hero']
        assert stale['fees'] == dict(state='stale', read_ts=9990, eth=.0842)
        assert stale['coins']['state'] == 'stale' and stale['coins']['count'] == 210
        assert stale['volume']['state'] == 'stale' and stale['volume']['usd'] == 16000
    finally:
        await m.close()


async def test_cycle_and_retained_hub_keep_pre_spawn_launchpad_values_and_clock(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, FakeClock
    m = _manager(tmp_path, clock=FakeClock(10000))
    slot = seed(m)

    def replace_launchpad(*args):
        m.cache.store_last_good(SLOT_LAUNCHPAD, dict(slot, coin_count=211, launch_count=211,
            creator_eth_owed_wei=10**18), ts=10000)
        m.cache.mark_fetched(TIER_LAUNCHPAD, 10000)

    monkeypatch.setattr(m, '_spawn_launchpad', replace_launchpad)
    monkeypatch.setattr(m, '_pool_market', AsyncMock(return_value=None))
    monkeypatch.setattr(m, '_pool_eth_usd', AsyncMock(return_value=None))
    try:
        result = await m._cycle()
        hero = result['surf_launchpad_hero']
        assert hero['coins'] == dict(state='ok', read_ts=9990, count=210, new_24h=2, swept=210)
        assert hero['fees']['eth'] == result['launchpad_creator_eth_owed'] == .0842
        assert hero['volume']['usd'] == 16000
        m._last_full_payload = result
        assert m._project_hub(refresh_legacy=False)['surf_launchpad_hero'] == hero
        assert m._project_hub()['surf_launchpad_hero']['coins']['count'] == 211
        assert m._project_hub()['surf_launchpad_hero']['fees']['eth'] == 1
    finally:
        await m.close()


async def test_sources_completed_after_cycle_start_use_capture_clock(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, FakeClock
    clock = FakeClock(10000)
    m = _manager(tmp_path, clock=clock)
    slot = seed(m)
    original = m._pool_chain

    async def finish_launchpad_during_chain(now):
        clock.advance(5)
        m.cache.store_last_good(SLOT_LAUNCHPAD, slot, ts=clock())
        m.cache.mark_fetched(TIER_LAUNCHPAD, clock())
        return await original(now)

    async def finish_quote(*args):
        clock.advance(5)
        m.cache.store_last_good(SLOT_ETH_USD, dict(eth_usd=3000, source='CoinGecko', provider_ts=None), ts=clock())
        return None

    monkeypatch.setattr(m, '_pool_chain', finish_launchpad_during_chain)
    monkeypatch.setattr(m, '_pool_eth_usd', finish_quote)
    monkeypatch.setattr(m, '_spawn_launchpad', lambda *args: None)
    try:
        hero = (await m._cycle())['surf_launchpad_hero']
        assert hero['coins']['state'] == 'ok' and hero['coins']['read_ts'] == 10005
        assert hero['fees']['eth'] == .0842
        assert hero['volume']['state'] == 'ok' and hero['volume']['usd'] == 24000
        assert hero['volume']['quote_read_ts'] == 10010
        assert hero['volume']['read_ts'] == 9990
    finally:
        await m.close()
