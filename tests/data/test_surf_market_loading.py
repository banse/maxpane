"""Pool and quote observations remain independent through passive projections."""
import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surf_cache as cache_mod
from maxpane_dashboard.data.surf_cache import LastGood, SLOT_LAUNCHPAD, SLOT_MARKET, SLOT_POOL4, SurfCache
from tests.data.test_surf_manager import FakeClock, FakeSurfClient, _manager, _market


def quote(manager, price, stamp):
    # A fixture can represent a new-format persisted entry before its registration exists.
    manager.cache.last_good['eth_usd'] = LastGood(dict(eth_usd=price, source='CoinGecko', provider_ts=None), stamp)


def identity(**changes):
    return dict(market_source='DexScreener', chain_id=1, pool_id='0x'+'1'*64,
                base_token='0x'+'2'*40, quote_token='0x'+'3'*40, target_side='base', **changes)


async def test_eth_partial_success_and_failure_keep_independent_clock(tmp_path):
    clock = FakeClock(1000)
    client = FakeSurfClient(fetch_market=None)
    async def fetch_quote():
        clock.advance(2)
        return 2000.0
    client.fetch_eth_usd = AsyncMock(side_effect=fetch_quote)
    manager = _manager(tmp_path, clock=clock, client=client)
    try:
        data = await manager._cycle()
        entry = manager.cache.get_last_good('eth_usd')
        assert entry is not None
        assert entry.payload == dict(eth_usd=2000., source='CoinGecko', provider_ts=None)
        assert entry.ts == 1002 and data['eth_usd'] == 2000
        assert manager.cache.get_last_good(SLOT_MARKET) is None
        clock.advance(90)
        client.fetch_eth_usd.side_effect = None
        client.fetch_eth_usd.return_value = None
        client._returns['fetch_market'] = _market(eth_usd=None, fp_price_usd=None)
        data = await manager._cycle()
        assert manager.cache.get_last_good('eth_usd') == entry
        assert data['eth_usd'] == 2000
        assert manager._hub_card_sources(data)['quote'] == dict(state='stale', read_ts=1002)
    finally:
        await manager.close()


async def test_legacy_cache_without_quote_starts_unknown(tmp_path):
    path = tmp_path/'surf_cache.json'
    old = SurfCache(path=path, clock=lambda: 1000.)
    old.store_last_good(SLOT_MARKET, dict(imd_price_usd=2., eth_usd=3000.), ts=990)
    old.save()
    manager = _manager(tmp_path, clock=FakeClock(1000))
    try:
        data = manager.get_snapshot()
        assert data['eth_usd'] is None
        assert data['imd_price_usd'] == 2.
        assert manager._hub_card_sources(data)['quote'] == dict(state='unavailable', read_ts=None)
    finally:
        await manager.close()


async def test_passive_projection_reprices_without_fetching(tmp_path):
    clock = FakeClock(1000)
    client = FakeSurfClient()
    manager = _manager(tmp_path, clock=clock, client=client)
    manager.cache.store_last_good(SLOT_MARKET, dict(identity(), imd_price_usd=10, fp_price_usd=2), ts=980)
    manager.cache.store_last_good(SLOT_LAUNCHPAD, dict(pool_id='0x'+'1'*64, sqrt_price_x96=2**96,
        coins=[dict(ticker='X', mcap_eth=3.)]), ts=900)
    manager.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET', current_tick=0,
        hook_addr='0x'+'4'*40), ts=910)
    quote(manager, 2000., 990)
    before = copy.deepcopy(manager.cache.series)
    try:
        first = manager.get_snapshot()
        assert first['imd_price_usd'] == first['pool4_price_usd'] == 2000
        assert first['launchpad_coins'][0]['mcap_usd'] == 6000
        quote(manager, 3000., 1000)
        second = manager.get_snapshot()
        assert second['imd_price_usd'] == second['pool4_price_usd'] == 3000
        assert second['surf_news_hero']['market']['price_usd'] == 3000
        assert second['launchpad_coins'][0]['mcap_usd'] == 9000
        assert second['parity_pct'] != first['parity_pct']
        assert manager.cache.get_last_good(SLOT_MARKET).ts == 980
        assert manager.cache.get_last_good(SLOT_POOL4).ts == 910
        assert manager.cache.series == before
        assert client.calls == []
    finally:
        await manager.close()


async def test_quote_update_preserves_pool_clock_and_resets_identity_baseline(tmp_path):
    clock = FakeClock(1000)
    manager = _manager(tmp_path, clock=clock)
    market = dict(identity(), imd_price_usd=1)
    manager.cache.store_last_good(SLOT_MARKET, market, ts=990)
    manager.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET', current_tick=0,
        hook_addr='0x'+'4'*40), ts=990)
    def card():
        data = manager.get_snapshot()
        return next(row for row in data['surfboard_cards'] if row['key']=='pool4')
    try:
        quote(manager, 8., 990)
        assert card()['status'] == 'idle'
        clock.advance(1)
        quote(manager, 9., clock())
        assert card()['status'] == 'active'
        assert manager.cache.get_last_good(SLOT_POOL4).ts == 990
        clock.advance(1)
        manager.cache.store_last_good(SLOT_MARKET, dict(market, target_side='quote'), ts=clock())
        quote(manager, 10., clock())
        assert card()['status'] == 'idle'
        clock.advance(1)
        quote(manager, 11., clock())
        assert card()['status'] == 'active'
        manager._quote_failed = True
        clock.advance(1)
        quote(manager, 4., clock())
        assert card()['status'] == 'stale'
        manager._quote_failed = False
        clock.advance(1)
        quote(manager, 9., clock())
        assert card()['status'] == 'falling'
    finally:
        await manager.close()


async def test_new_market_without_fp_does_not_rejuvenate_old_fp(tmp_path):
    clock = FakeClock(1000)
    client = FakeSurfClient(fetch_market=_market(eth_usd=None, fp_price_usd=2))
    manager = _manager(tmp_path, clock=clock, client=client)
    try:
        await manager._pool_market({cache_mod.TIER_MEDIUM}, clock(), '0x'+'1'*64)
        clock.advance(90)
        client._returns['fetch_market'] = _market(eth_usd=None, fp_price_usd=None)
        await manager._pool_market({cache_mod.TIER_MEDIUM}, clock(), '0x'+'1'*64)
        assert manager.get_snapshot()['fp_price_usd'] is None
        assert 'eth_usd' not in manager.cache.get_last_good(SLOT_MARKET).payload
    finally:
        await manager.close()


async def test_cancelled_quote_read_preserves_last_good_without_publication(tmp_path):
    clock = FakeClock(1000)
    client = FakeSurfClient()
    entered, stopped = asyncio.Event(), asyncio.Event()
    async def pending():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    client.fetch_eth_usd = pending
    manager = _manager(tmp_path, clock=clock, client=client)
    quote(manager, 2000., 990)
    before = manager.cache.get_last_good('eth_usd')
    try:
        task = asyncio.create_task(manager._pool_eth_usd({cache_mod.TIER_MEDIUM}, clock()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
        assert manager.cache.get_last_good('eth_usd') == before
        assert manager._quote_failed is False
    finally:
        await manager.close()


async def test_completed_quote_remains_available_in_full_pool4_hero(tmp_path):
    clock = FakeClock(1000)
    client = FakeSurfClient(fetch_market=None)
    async def completed_quote():
        clock.advance(2)
        return 2000.
    client.fetch_eth_usd = completed_quote
    manager = _manager(tmp_path, clock=clock, client=client)
    manager.cache.store_last_good(SLOT_POOL4, dict(network='MAINNET', current_tick=0,
        hook_addr='0x'+'4'*40), ts=990)
    try:
        data = await manager._cycle()
        assert data['pool4_price_usd'] == 2000.
        assert data['surf_pool4_hero']['price']['usd'] == 2000.
        assert data['surf_pool4_hero']['price']['state'] == 'ok'
        assert data['surf_pool4_hero']['price']['read_ts'] == 990
        assert manager.cache.get_last_good(cache_mod.SLOT_ETH_USD).ts == 1002
    finally:
        await manager.close()


@pytest.mark.parametrize('fresh_market', [False, True], ids=['retained-dex-fresh-eth', 'fresh-dex-failed-eth'])
async def test_dex_fallback_agent_source_matches_actual_price_source(tmp_path, fresh_market):
    clock = FakeClock(1000)
    client = FakeSurfClient(fetch_market=_market(imd_price_usd=2., eth_usd=None) if fresh_market else None,
                            fetch_eth_usd=None if fresh_market else 2000.)
    manager = _manager(tmp_path, clock=clock, client=client)
    manager.cache.store_last_good(SLOT_MARKET, dict(imd_price_usd=2.), ts=900)
    captured = []
    original = manager._agent_hero
    def capture(data, snapshot, board_sources, price_source, **kwargs):
        captured.append(price_source)
        return original(data, snapshot, board_sources, price_source, **kwargs)
    manager._agent_hero = capture
    try:
        data = await manager._cycle()
        assert data['imd_price_usd'] == 2.
        expected = dict(state='ok', read_ts=1000.) if fresh_market else dict(state='stale', read_ts=900.)
        assert captured[-1] == expected
        assert {key: data['surf_news_hero']['market'][key] for key in ('state', 'read_ts')} == expected
    finally:
        await manager.close()
