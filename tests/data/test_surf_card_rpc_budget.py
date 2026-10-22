"""Card polling clocks must survive force-entry and empty-cache failures."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from maxpane_dashboard.data.surf_cache import SurfCache, SLOT_CHANNEL, SLOT_MARKET, SLOT_ETH_USD
from maxpane_dashboard.data.surf_card_reader import SurfCardReader


def reader(tmp_path):
    clock = [1000.0]
    manager = SimpleNamespace(cache=SurfCache(path=tmp_path / 'cache.json'), _clock=lambda: clock[0])
    async def save(slot, value):
        manager.cache.store_last_good(slot, value, ts=clock[0])
        return value
    manager._pool_channel = AsyncMock(side_effect=lambda *args: None)
    async def feed(*args):
        return await save(SLOT_CHANNEL, {'items': []})
    async def market(*args):
        return await save(SLOT_MARKET, {'imd_price_usd': 1.0})
    async def eth(*args):
        return await save(SLOT_ETH_USD, {'eth_usd': 3000.0})
    manager._pool_channel.side_effect = feed
    manager._pool_market = AsyncMock(side_effect=market)
    manager._pool_eth_usd = AsyncMock(side_effect=eth)
    result = SurfCardReader(manager)
    result._work = AsyncMock()
    result._current = AsyncMock()
    result._pool = AsyncMock()
    return result, manager, clock


async def test_medium_cards_respect_90_second_ttl_even_on_forced_entry(tmp_path):
    cards, manager, clock = reader(tmp_path)
    for second in (1000, 1030, 1060, 1090, 1120):
        clock[0] = second
        cards.offer(force=True)
        await cards.wait_pending()
    assert manager._pool_channel.await_count == 2
    assert manager._pool_market.await_count == 2
    assert manager._pool_eth_usd.await_count == 2


async def test_failed_card_retries_after_60_seconds_without_refetching_healthy_sibling(tmp_path):
    cards, manager, clock = reader(tmp_path)
    manager._pool_market.side_effect = None
    manager._pool_market.return_value = None
    for second in (1000, 1030, 1060):
        clock[0] = second
        await cards._market()
    assert manager._pool_market.await_count == 2
    assert manager._pool_eth_usd.await_count == 1


async def test_card_reader_uses_existing_fresh_slot_after_recreation(tmp_path):
    cards, manager, clock = reader(tmp_path)
    await cards._feed()
    cards = SurfCardReader(manager)
    clock[0] += 30
    await cards._feed()
    assert manager._pool_channel.await_count == 1


async def test_pool_card_uses_small_quote_and_revalidates_changed_announcement(tmp_path):
    from maxpane_dashboard.data.surf_manager import POOL4_ADOPTED
    cards, manager, clock = reader(tmp_path)
    manager.cache.store_last_good(SLOT_CHANNEL, {'items': [{'text': 'first'}]}, ts=clock[0])
    manager._pool4_discovery = AsyncMock(return_value=(dict(state=POOL4_ADOPTED, hook_addr='0x'+'12'*20), 'self-post'))
    manager.pool4_client = SimpleNamespace(fetch_card_quote=AsyncMock(
        return_value=dict(share_price_wei=2*10**18, tick=42)))
    # Use the actual pool reader; the other fixture helpers isolate unrelated cards.
    for second in (1000, 1030, 1060):
        clock[0] = second
        await SurfCardReader._pool(cards)
    assert manager._pool4_discovery.await_count == 1
    assert manager.pool4_client.fetch_card_quote.await_count == 3
    assert cards.pool['pool4_share_price'] == 2
    assert cards.pool['tick'] == 42
    manager.cache.store_last_good(SLOT_CHANNEL, {'items': [{'text': 'new hook'}]}, ts=clock[0])
    await SurfCardReader._pool(cards)
    assert manager._pool4_discovery.await_count == 2
    clock[0] += 90
    await SurfCardReader._pool(cards)
    assert manager._pool4_discovery.await_count == 3
