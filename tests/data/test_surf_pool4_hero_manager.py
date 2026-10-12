"""POOL4 hero source snapshots use the clocks of the values they accompany."""
import pytest
from maxpane_dashboard.data.surf_cache import SLOT_POOL4, SLOT_POOL4_STAKERS, SLOT_MARKET, TIER_POOL4
from maxpane_dashboard.data import surf_pool4_hero
from tests.data.test_surf_manager_surfboard import manager


def seed(m, *, complete=True, network='MAINNET'):
    m.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET', current_tick=0, share_price_wei=8*10**18,
        total_assets_wei=80*10**18, total_shares_raw=10*10**24, vault_decimals=24), ts=800)
    m.cache.store_last_good(SLOT_POOL4_STAKERS, dict(network=network, complete=complete, staker_count=3), ts=700)
    m.cache.store_last_good(SLOT_MARKET, dict(eth_usd=2000), ts=990)


async def test_pool4_hero_uses_existing_units_and_independent_clocks(manager):
    m, clock = manager
    seed(m)
    try:
        hero=m._project_hub()['surf_pool4_hero']
        assert hero['price']['usd'] == 2000 and hero['price']['read_ts'] == 800
        assert hero['rate'] == dict(state='ok', read_ts=800, imd=8)
        assert hero['vault'] == dict(state='ok', read_ts=700, imd=80, simd=10, holders=3, holders_state='ok', holders_read_ts=700, holders_partial=False)
        clock.now=1500
        hero=m._project_hub()['surf_pool4_hero']
        assert hero['rate']['state'] == 'stale'
        assert hero['vault']['holders_state'] == 'ok'
        m._cycle.assert_not_awaited()
    finally: await m.close()


@pytest.mark.parametrize('complete,network,state,holders', [(False,'MAINNET','partial',3),(True,'SEPOLIA','unavailable',None)])
async def test_holder_coverage_and_network_do_not_claim_full_vault_count(manager,complete,network,state,holders):
    m,_=manager;seed(m,complete=complete,network=network)
    try:
        vault=m._project_hub()['surf_pool4_hero']['vault']
        assert vault['holders_state'] == state and vault['holders'] == holders
        assert vault['imd'] == 80 and vault['state'] == 'partial'
    finally: await m.close()


async def test_unchanged_confirmed_read_and_failure_keep_honest_clock(manager):
    m,_=manager;seed(m)
    try:
        m.cache.mark_fetched(TIER_POOL4,950)
        assert m._project_hub()['surf_pool4_hero']['rate']['read_ts'] == 950
        m.cache.mark_failed(TIER_POOL4,999)
        rate=m._project_hub()['surf_pool4_hero']['rate']
        assert rate == dict(state='stale',read_ts=950,imd=8)
    finally: await m.close()


async def test_captured_sources_survive_detached_slot_replacement(manager):
    m,_=manager;seed(m)
    try:
        sources=m._pool4_hero_sources(m.cache.get_last_good(SLOT_POOL4),m.cache.get_last_good(SLOT_POOL4_STAKERS),m.cache.get_last_good(SLOT_MARKET),1000)
        m.cache.store_last_good(SLOT_POOL4,dict(share_price_wei=99*10**18),ts=999)
        m.cache.mark_fetched(TIER_POOL4,999)
        projected=surf_pool4_hero.project(data={'pool4_share_price':8},sources=sources,now=1000)
        assert projected['rate'] == dict(state='ok',read_ts=800,imd=8)
        m._last_full_payload={'surf_pool4_hero':projected}
        assert m._project_hub(refresh_legacy=False)['surf_pool4_hero'] == projected
    finally: await m.close()


async def test_cycle_publishes_pre_spawn_value_with_pre_spawn_clock(tmp_path,monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, FakeClock
    m=_manager(tmp_path,clock=FakeClock(1000))
    seed(m)
    def replace_pool(*args):
        m.cache.store_last_good(SLOT_POOL4,dict(network='MAINNET',share_price_wei=99*10**18),ts=999)
        m.cache.mark_fetched(TIER_POOL4,999)
    monkeypatch.setattr(m,'_spawn_pool4',replace_pool)
    try:
        result=await m._cycle()
        assert result['pool4_share_price'] == 8
        assert result['surf_pool4_hero']['rate'] == dict(state='ok',read_ts=800,imd=8)
        assert m.cache.get_last_good(SLOT_POOL4).ts == 999
    finally: await m.close()


@pytest.mark.parametrize('expired',[False,True])
async def test_incomplete_holders_keep_staleness_and_lower_bound(manager,expired):
    m,clock=manager;seed(m,complete=False)
    from maxpane_dashboard.data.surf_cache import TIER_POOL4_STAKERS
    try:
        if expired:
            clock.now=3000
            m.cache.mark_fetched(TIER_POOL4,2990)
        else:
            m.cache.mark_failed(TIER_POOL4_STAKERS,999)
        vault=m._project_hub()['surf_pool4_hero']['vault']
        assert vault['state'] == vault['holders_state'] == 'stale'
        assert vault['holders_partial'] is True
        assert vault['holders'] == 3 and vault['holders_read_ts'] == 700
    finally: await m.close()
