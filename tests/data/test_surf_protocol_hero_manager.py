"""PROTOCOL cards and native body share a captured POOL4 observation."""
from maxpane_dashboard.data.surf_cache import SLOT_POOL4, TIER_POOL4
from tests.data.test_surf_manager_surfboard import manager


def seed(m):
    m.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET',
        total_burned_wei=33 * 10**18, total_rewarded_wei=6 * 10**18,
        total_fee_token_wei=4 * 10**18, reward_path='via-distributor',
        distributor_staking_bps=3000, distributor_nodes_bps=2000,
        bps_denominator=10000, unsettled_burn=2, unsettled_stakers=9), ts=800)


async def test_hub_uses_existing_whole_units_and_pool_clock_without_market(manager):
    m, clock = manager
    seed(m)
    try:
        result = m._project_hub()
        hero = result['surf_protocol_hero']
        assert hero['totals'] == dict(state='ok', read_ts=800, burned=33, rewarded=6, fees=4)
        assert hero['unsettled'] == dict(state='ok', read_ts=800, burn=2, rewards=9)
        assert hero['split'] == dict(state='ok', read_ts=800, path='via-distributor',
                                     staking_pct=30, nodes_pct=20, bonding_pct=50)
        assert hero['totals']['burned'] == result['pool4_total_burned']
        clock.now = 1500
        assert m._project_hub()['surf_protocol_hero']['totals']['state'] == 'stale'
        m._cycle.assert_not_awaited()
    finally:
        await m.close()


async def test_confirmed_unchanged_read_advances_clock_but_failed_read_does_not(manager):
    m, _ = manager
    seed(m)
    try:
        m.cache.mark_fetched(TIER_POOL4, 950)
        assert m._project_hub()['surf_protocol_hero']['totals']['read_ts'] == 950
        m.cache.mark_failed(TIER_POOL4, 999)
        assert m._project_hub()['surf_protocol_hero']['totals'] == dict(
            state='stale', read_ts=950, burned=33, rewarded=6, fees=4)
    finally:
        await m.close()


async def test_cycle_and_retained_hub_keep_pre_spawn_value_and_clock(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, FakeClock
    m = _manager(tmp_path, clock=FakeClock(1000))
    seed(m)

    def replace_pool(*args):
        m.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET',
            total_burned_wei=99 * 10**18, total_rewarded_wei=66 * 10**18,
            total_fee_token_wei=44 * 10**18), ts=999)
        m.cache.mark_fetched(TIER_POOL4, 999)

    monkeypatch.setattr(m, '_spawn_pool4', replace_pool)
    try:
        result = await m._cycle()
        assert result['pool4_total_burned'] == 33
        assert result['surf_protocol_hero']['totals'] == dict(
            state='ok', read_ts=800, burned=33, rewarded=6, fees=4)
        assert m.cache.get_last_good(SLOT_POOL4).ts == 999
        m._last_full_payload = result
        retained = m._project_hub(refresh_legacy=False)
        assert retained['surf_protocol_hero'] == result['surf_protocol_hero']
        assert m._project_hub()['surf_protocol_hero']['totals'] == dict(
            state='ok', read_ts=999, burned=99, rewarded=66, fees=44)
    finally:
        await m.close()
