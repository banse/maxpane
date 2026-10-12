"""Offline ranking evidence: canonical launches, source clocks and price reads."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
from maxpane_dashboard.data.surf_swarm import launch_rows
from tests.data.test_swarm_tokens_live import Market, Pages, Source, rows


NOW = 1_800_000_000.
POOL = '0x' + 'a' * 40


def launch(index, age=60, *, chain=1, status='live', contract=None):
    """Vary the committed catalogue capture, retaining its decoded shape."""
    item = deepcopy(rows()[0])
    item.update(id=f'{index:08x}-aaaa-4aaa-aaaa-aaaaaaaaaaaa', launchNumber=index,
                chainId=chain, status=status,
                createdAt=datetime.fromtimestamp(NOW-age, timezone.utc).isoformat())
    item['artifacts'] = [dict(item['artifacts'][-1], name=f'T{index}',
                              address=contract or f'0x{index:040x}')]
    return item


def token_id(item):
    return f"{item['chainId']}:{item['artifacts'][0]['address'].lower()}"


class Quotes(Market):
    def __init__(self):
        self.values, self.calls = {}, []
        self.failed = False
        self.price, self.pool, self.source = 2, POOL, 'fixture'

    async def fetch_markets(self, tokens):
        self.calls.append([t['id'] for t in tokens])
        if self.failed:
            return None
        return {t['id']: dict(state='ok', price_usd=self.price,
                             market_pool=self.pool, market_source=self.source,
                             volume_24h=self.values.get(t['id'], 1)) for t in tokens}

    async def fetch_history(self, token):
        raise AssertionError('hub must not offer price history')

    async def fetch_trades(self, token):
        raise AssertionError('hub must not offer trades')

    async def fetch_volume_history(self, token):
        raise AssertionError('hub must not offer volume history')


def manager_for(raw):
    now, market = [NOW], Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(raw), market=market,
                                 clock=lambda: now[0])
    return manager, now, market


async def load(manager):
    manager.offer_hub_markets()
    await manager.wait_pending()
    manager.offer_hub_markets()
    await manager.wait_pending()
    return manager.catalogue_summary(manager.surf.data)['ranking']


async def test_rank_volume_includes_inactive_and_zero_with_deterministic_ties():
    raw = [launch(1, 400), launch(2, 200, status='parked'), launch(3, 200), launch(4, 0)]
    manager, _, market = manager_for(raw)
    market.values = {token_id(raw[0]): 0, token_id(raw[1]): 9, token_id(raw[2]): 9,
                     token_id(raw[3]): 2}
    try:
        ranking = await load(manager)
        assert set(ranking) == {'rows', 'newest', 'state', 'read_ts', 'known', 'total'}
        assert ranking['state'] == 'ok' and ranking['known'] == ranking['total'] == 4
        assert [r['id'] for r in ranking['rows']] == [token_id(raw[i]) for i in (1, 2, 3)]
        assert [r['volume_usd'] for r in ranking['rows']] == [9, 9, 2]
        assert set(ranking['rows'][0]) == {'id', 'age_s', 'symbol', 'chain', 'volume_usd', 'price_direction'}
        assert ranking['newest'] == dict(id=token_id(raw[3]), age_s=0, symbol='T4', chain='eth')
        assert all(r['price_direction'] is None for r in ranking['rows'])
        assert ranking['read_ts'] == NOW
    finally:
        await manager.close()


async def test_exact_window_earliest_alias_and_newest_independent_of_market():
    old = launch(1, 86400)
    alias = launch(2, 1, contract=old['artifacts'][0]['address'])
    recent, future, unknown = launch(3, 86399), launch(4, -1), launch(5)
    unknown['createdAt'] = 'invalid'
    raw = [alias, old, recent, future, unknown]
    manager, now, market = manager_for(raw)
    market.values[token_id(alias)] = 1000
    try:
        ranking = await load(manager)
        assert ranking['known'] == ranking['total'] == 1
        assert [r['id'] for r in ranking['rows']] == [token_id(recent)]
        assert ranking['newest']['id'] == token_id(recent)
        now[0] += 1
        manager._catalogue = [alias, recent, unknown]  # removed alias cannot reset the age
        ranking = manager.catalogue_summary()['ranking']
        assert ranking['rows'] is None and ranking['total'] == 0
        assert ranking['state'] == 'partial'  # unknown timestamp prevents a known-empty claim
        assert ranking['newest']['id'] == token_id(recent)
        assert ranking['newest']['age_s'] == 86400
        market.failed = True
        now[0] += manager.MARKET_TTL
        await load(manager)
        assert manager.catalogue_summary()['ranking']['newest']['id'] == token_id(recent)
    finally:
        await manager.close()


async def test_supported_valid_deployments_deduplicate_chain_address_and_reject_ambiguity():
    good = launch(1)
    duplicate = launch(2, contract=good['artifacts'][0]['address'].upper().replace('0X', '0x'))
    other_chain = launch(3, chain=8453, contract=good['artifacts'][0]['address'])
    unsupported, malformed, ambiguous = launch(4, chain=11155111), launch(5), launch(6)
    malformed['artifacts'][0]['address'] = '0x' + '0' * 40
    ambiguous['artifacts'].append(dict(ambiguous['artifacts'][0], address='bad'))
    manager, _, _ = manager_for([good, duplicate, other_chain, unsupported, malformed, ambiguous])
    try:
        ranking = await load(manager)
        assert ranking['known'] == ranking['total'] == 2
        assert {r['id'] for r in ranking['rows']} == {token_id(good), token_id(other_chain)}
    finally:
        await manager.close()


@pytest.mark.parametrize('value', [None, -1, True, float('nan'), float('inf'), '2'])
async def test_invalid_volume_is_unknown_not_zero(value):
    raw = [launch(1), launch(2)]
    manager, _, market = manager_for(raw)
    market.values = {token_id(raw[0]): value, token_id(raw[1]): 0}
    try:
        ranking = await load(manager)
        assert ranking['state'] == 'partial'
        assert (ranking['known'], ranking['total']) == (1, 2)
        assert [(r['id'], r['volume_usd']) for r in ranking['rows']] == [(token_id(raw[1]), 0)]
    finally:
        await manager.close()


async def test_unknown_empty_partial_and_stale_keep_successful_source_clock():
    manager, now, market = manager_for([launch(1)])
    try:
        assert manager.catalogue_summary()['ranking'] == dict(
            rows=None, newest=None, state='unavailable', read_ts=None, known=0, total=None)
        first = await load(manager)
        manager._complete = False
        assert manager.catalogue_summary()['ranking']['state'] == 'partial'
        manager._complete = True
        market.failed = True
        now[0] += manager.MARKET_TTL
        failed = await load(manager)
        assert failed['state'] == 'stale' and failed['rows']
        assert failed['known'] == 0 and failed['read_ts'] == first['read_ts']
        assert failed['rows'][0]['price_direction'] is None
        now[0] += 1
        assert manager.catalogue_summary()['ranking']['read_ts'] == first['read_ts']
        manager._catalogue = []
        empty = manager.catalogue_summary()['ranking']
        assert empty == dict(rows=[], newest=None, state='ok', read_ts=NOW, known=0, total=0)
    finally:
        await manager.close()


async def test_fresh_subset_excludes_stale_volume_and_neutralizes_catalogue_stale_arrows():
    raw = [launch(1), launch(2)]
    manager, now, market = manager_for(raw)
    try:
        await load(manager)
        now[0] += manager.MARKET_TTL
        market.price = 3
        await load(manager)
        manager._failed['markets'].add(token_id(raw[0]))
        ranking = manager.catalogue_summary()['ranking']
        assert ranking['state'] == 'partial' and ranking['known'] == 1
        assert [r['id'] for r in ranking['rows']] == [token_id(raw[1])]
        assert ranking['rows'][0]['price_direction'] == 'up'
        manager._cat_failed = True
        stale = manager.catalogue_summary()['ranking']
        assert stale['state'] == 'stale' and stale['rows'][0]['price_direction'] is None
    finally:
        await manager.close()


async def test_market_ttl_and_future_clock_never_present_cached_arrow_as_current():
    manager, now, market = manager_for([launch(1)])
    try:
        await load(manager)
        market.price = 3
        now[0] += manager.MARKET_TTL
        fresh = await load(manager)
        assert fresh['rows'][0]['price_direction'] == 'up'
        now[0] += manager.MARKET_TTL + 1
        stale = manager.catalogue_summary()['ranking']
        assert stale['state'] == 'stale' and stale['known'] == 0
        assert stale['rows'][0]['price_direction'] is None
        assert stale['read_ts'] == fresh['read_ts']
        key = stale['rows'][0]['id']
        payload, _ = manager._market[key]
        manager._market[key] = payload, now[0] + 1
        future = manager.catalogue_summary()['ranking']
        assert future['rows'] is None and future['state'] == 'unavailable'
        assert future['newest']['id'] == key
    finally:
        await manager.close()


async def test_price_reads_advance_once_preserve_failed_baseline_and_reset_pool_source():
    manager, now, market = manager_for([launch(1)])
    try:
        assert (await load(manager))['rows'][0]['price_direction'] is None
        for price, expected in ((3, 'up'), (1, 'down'), (1, 'flat')):
            now[0] += manager.MARKET_TTL
            market.price = price
            assert (await load(manager))['rows'][0]['price_direction'] == expected
            assert manager.catalogue_summary()['ranking']['rows'][0]['price_direction'] == expected
            await load(manager)
            assert manager.catalogue_summary()['ranking']['rows'][0]['price_direction'] == expected
        market.failed = True
        now[0] += manager.MARKET_TTL
        assert (await load(manager))['rows'][0]['price_direction'] is None
        market.failed, market.price = False, 4
        now[0] += manager.MARKET_TTL
        assert (await load(manager))['rows'][0]['price_direction'] == 'up'
        market.pool = '0x' + 'b' * 40
        now[0] += manager.MARKET_TTL
        assert (await load(manager))['rows'][0]['price_direction'] is None
        market.source = 'other fixture'
        now[0] += manager.MARKET_TTL
        assert (await load(manager))['rows'][0]['price_direction'] is None
    finally:
        await manager.close()


@pytest.mark.parametrize('price', [None, 0, -1, True, float('nan'), float('inf')])
async def test_invalid_price_never_advances_or_erases_valid_baseline(price):
    manager, now, market = manager_for([launch(1)])
    try:
        await load(manager)
        now[0] += manager.MARKET_TTL
        market.price = price
        assert (await load(manager))['rows'][0]['price_direction'] is None
        now[0] += manager.MARKET_TTL
        market.price = 3
        assert (await load(manager))['rows'][0]['price_direction'] == 'up'
    finally:
        await manager.close()


async def test_expected_pool_change_resets_baseline_even_after_failed_fetch():
    raw = [launch(1)]
    manager, _, market = manager_for(raw)
    shared = launch_rows(raw)
    shared[0]['token_address'] = raw[0]['artifacts'][0]['address']
    manager.surf.data.update(rows=shared, pool_ids={raw[0]['id']: POOL})
    try:
        await load(manager)
        new_pool = '0x' + 'c' * 40
        manager.surf.data['pool_ids'][raw[0]['id']] = new_pool
        market.failed = True
        await load(manager)
        assert manager.catalogue_summary(manager.surf.data)['ranking']['rows'] is None
        manager.surf.data['pool_ids'][raw[0]['id']] = POOL
        market.failed, market.price = False, 3
        await load(manager)
        assert manager.catalogue_summary(manager.surf.data)['ranking']['rows'][0]['price_direction'] is None
    finally:
        await manager.close()


async def test_hub_market_offer_is_bounded_singleflight_and_excludes_all_details():
    manager, now, market = manager_for([launch(i) for i in range(1, 6)])
    manager.MARKET_BATCH = 2
    gate, started = asyncio.Event(), asyncio.Event()
    fetch = market.fetch_markets
    async def blocked(tokens):
        started.set()
        await gate.wait()
        return await fetch(tokens)
    market.fetch_markets = blocked
    try:
        manager.offer_hub_markets()
        await manager.wait_pending()
        manager.offer_hub_markets()
        await started.wait()
        for _ in range(4):
            manager.offer_hub_markets()
        assert not market.calls and set(manager._tasks) == {'catalogue', 'markets'}
        gate.set()
        await manager.wait_pending()
        await load(manager)
        assert [len(call) for call in market.calls] == [2, 2, 1]
        assert len({item for call in market.calls for item in call}) == 5
        await load(manager)
        assert len(market.calls) == 3
        assert not any(manager._attempts[name] for name in ('volume', 'history', 'trades'))
        now[0] += manager.MARKET_TTL
        manager.offer_hub_markets()
        await manager.wait_pending()
        assert len(market.calls) == 4
    finally:
        gate.set()
        await manager.close()
