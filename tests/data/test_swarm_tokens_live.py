"""Offline catalogue boundaries and nonblocking live adapter ownership."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.swarm_tokens_client import SwarmTokensClient
from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
from maxpane_dashboard.data.surf_swarm import launch_rows
from maxpane_dashboard.data.swarm_tokens_models import TOKEN_KEYS

FIXTURE = Path(__file__).parents[1] / 'fixtures/swarm_tokens/catalogue/launches.json'


def rows():
    return json.loads(FIXTURE.read_text())['launches']


class Source:
    def __init__(self, data=None):
        self.data = {'rows': data, 'as_of': 1000 if data is not None else None, 'pool_ids': {}}
        self.catalogues = []
        self.closed = False

    def swarm_tokens_source(self, catalogue=None):
        self.catalogues.append(deepcopy(catalogue))
        return deepcopy(self.data)

    async def close(self):
        self.closed = True


class Pages:
    def __init__(self, data=None):
        self.data = rows() if data is None else data
        self.calls = []
        self.closed = False
        self.failed = False

    async def fetch_page(self, *, before=None, limit=500):
        self.calls.append(before)
        if self.failed:
            return None
        return deepcopy([r for r in self.data if before is None or r['launchNumber'] < before][:limit])

    async def close(self):
        self.closed = True


class Market:
    async def fetch_markets(self, tokens):
        return {}

    async def fetch_history(self, token):
        return None

    async def fetch_trades(self, token):
        return None

    async def close(self):
        self.closed = True


async def settle(manager):
    await manager.wait_pending()
    return await manager.fetch_and_compute()


async def test_client_passes_numeric_cursor_and_rejects_malformed_or_repeated_pages():
    data = rows()[:2]
    seen = []
    response = {'launches': data}
    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=response)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SwarmTokensClient(http_client=http, hosts=['https://fixture.invalid'], inter_call_delay=0)
        assert await client.fetch_page(limit=2) == data
        assert seen == [{'limit': '2'}]
        assert await client.fetch_page(before=data[-1]['launchNumber'], limit=2) is None
        assert seen[-1]['before'] == str(data[-1]['launchNumber'])
        response['launches'] = [data[0], data[0]]
        assert await client.fetch_page(limit=2) is None
        response['launches'] = [data[0], None]
        assert await client.fetch_page(limit=2) is None
        response['launches'] = []
        assert await client.fetch_page() == []
        assert await client.fetch_page(before=True) is None


async def test_cold_read_is_immediate_single_flight_and_unknown_not_zero():
    gate = asyncio.Event()
    class Slow(Pages):
        async def fetch_page(self, **kw):
            self.calls.append(kw)
            await gate.wait()
            return rows()
    source, pages = Source(), Slow()
    manager = SwarmTokensManager(source, client=pages, market=Market(), clock=lambda: 1000)
    try:
        first = await asyncio.wait_for(manager.fetch_and_compute(), .1)
        assert first['tokens'] is None and first['is_mock'] is False
        await manager.fetch_and_compute()
        await asyncio.sleep(0)
        assert len(pages.calls) == 1
        gate.set()
        snapshot = await settle(manager)
        assert len(snapshot['tokens']) == 3
        assert snapshot['sources']['catalogue']['complete'] is True
        assert snapshot['sources']['catalogue']['state'] == 'ok'
    finally:
        await manager.close()
    assert not source.closed


async def test_pagination_resumes_capped_scan_and_revisits_head_after_ttl():
    now = [1000]
    pages = Pages()
    manager = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda: now[0])
    manager.PAGE_SIZE, manager.PAGE_BUDGET = 2, 1
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        partial = await manager.fetch_and_compute()
        assert partial['sources']['catalogue']['state'] == 'partial'
        assert not partial['sources']['catalogue']['complete']
        await manager.wait_pending()
        await manager.fetch_and_compute()
        await manager.wait_pending()
        full = await manager.fetch_and_compute()
        assert len(pages.calls) == 3
        assert full['sources']['catalogue']['complete']
        assert pages.calls == [None, rows()[1]['launchNumber'], rows()[3]['launchNumber']]
        now[0] += manager.CATALOGUE_TTL
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert pages.calls[-1] is None
    finally:
        await manager.close()


async def test_failure_retains_last_complete_catalogue_and_original_clock():
    now = [1000]
    pages = Pages()
    manager = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda: now[0])
    try:
        await manager.fetch_and_compute()
        first = await settle(manager)
        pages.failed = True
        now[0] += manager.CATALOGUE_TTL
        await manager.fetch_and_compute()
        failed = await settle(manager)
        assert [{key: row[key] for key in TOKEN_KEYS} for row in failed['tokens']] == [
            {key: row[key] for key in TOKEN_KEYS} for row in first['tokens']]
        assert failed['sources']['catalogue'] == {'state': 'stale', 'as_of': 1000, 'complete': True, 'loaded': 5}
    finally:
        await manager.close()


async def test_chain_address_identity_unknown_timestamp_and_exact_shared_join():
    raw = rows()
    production = next(r for r in raw if r['chainId'] == 1 and r['status'] == 'live')
    duplicate = deepcopy(production)
    duplicate['id'] = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
    duplicate['launchNumber'] = production['launchNumber'] + 1
    duplicate['createdAt'] = 'bad'
    same_address_other_chain = deepcopy(duplicate)
    same_address_other_chain.update(id='bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb', chainId=8453, launchNumber=9999)
    raw.extend([duplicate, same_address_other_chain])
    shared = launch_rows(raw)
    for row in shared:
        row.update(ticker='UNTRUSTED', token_address='0x'+'f'*40, production=True)
    manager = SwarmTokensManager(Source(shared), client=Pages(raw), market=Market(), clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        snapshot = await settle(manager)
        assert len(snapshot['tokens']) == 4
        ids = [r['id'] for r in snapshot['tokens']]
        assert len(ids) == len(set(ids))
        chosen = next(r for r in snapshot['tokens'] if r['launch_uuid'] == duplicate['id'])
        assert chosen['launched_at'] is None
        assert chosen['symbol'] != 'UNTRUSTED'
        assert chosen['price_usd'] is None and chosen['lp_state'] == 'unknown'
        assert set(TOKEN_KEYS) <= chosen.keys()
        assert all(row['chain'] in ('eth', 'base', 'rh') for row in snapshot['tokens'])
    finally:
        await manager.close()


async def test_liquidity_clock_is_independent_and_stale_positions_are_unknown():
    shared = launch_rows(rows())
    for row in shared:
        token = next((a for a in row['artifacts'] if a['role'] == 'token'), None)
        if token:
            row.update(token_address=token['address'], production=True, ticker='EXACT')
            row['liquidity'] = {'paired_amount': 7, 'token_amount': 10, 'paired_symbol': 'IMD',
                                'read_ts': 1000, 'lock': 'locked', 'state': 'info'}
    now = [1000]
    manager = SwarmTokensManager(Source(shared), client=Pages(), market=Market(), clock=lambda: now[0])
    try:
        await manager.fetch_and_compute()
        snapshot = await settle(manager)
        assert all(r['lp_state'] == 'two-sided' for r in snapshot['tokens'])
        now[0] += manager.LIQUIDITY_TTL + 1
        old = await manager.fetch_and_compute()
        assert all(r['lp_state'] == 'unknown' and r['liquidity_state'] == 'stale' for r in old['tokens'])
        assert all(r['liquidity_read_at'] == 1000 for r in old['tokens'])
    finally:
        await manager.close()


async def test_changed_catalogue_version_does_not_reuse_old_provenance():
    raw = rows()
    shared = launch_rows(raw)
    for row in shared:
        artifact = next((a for a in row['artifacts'] if a['role']=='token'), None)
        if artifact:
            row.update(token_address=artifact['address'], verdict={'state':'swarm'},
                       updated_ts=row['updated_ts']-1)
    manager = SwarmTokensManager(Source(shared),client=Pages(raw),market=Market(),clock=lambda:1000)
    try:
        await manager.fetch_and_compute()
        snapshot = await settle(manager)
        assert all(row['verdict']=='unknown' for row in snapshot['tokens'])
    finally:
        await manager.close()


async def test_failed_continuation_retains_successful_partial_population():
    pages = Pages()
    manager = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda: 1000)
    manager.PAGE_SIZE, manager.PAGE_BUDGET = 2, 1
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        pages.failed = True
        partial = await manager.fetch_and_compute()
        await manager.wait_pending()
        failed = await manager.fetch_and_compute()
        assert failed['tokens'] is not None
        assert {r['id'] for r in failed['tokens']} == {r['id'] for r in partial['tokens']}
        assert failed['sources']['catalogue']['state'] == 'partial'
        assert not failed['sources']['catalogue']['complete']
    finally:
        await manager.close()


async def test_market_failure_does_not_advance_success_clock_or_fabricate_trades():
    class Quotes(Market):
        fail = False
        async def fetch_markets(self, tokens):
            if self.fail:
                return None
            return {t['id']: {'state': 'ok', 'price_usd': 2, 'mcap_usd': None,
                             'fdv_usd': 5000, 'volume_24h': 0, 'buys_24h': 0,
                             'sells_24h': 0, 'market_source': 'captured fixture',
                             'market_pool': '0x'+'a'*40} for t in tokens}
    now = [1000]
    market = Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: now[0])
    try:
        await manager.fetch_and_compute()
        await settle(manager)
        first = await settle(manager)
        assert all(r['market_read_at'] == 1000 and r['volume_24h'] == 0 for r in first['tokens'])
        assert all(r['mcap_usd'] is None and r['fdv_usd'] == 5000 for r in first['tokens'])
        assert all(event['kind'] == 'LAUNCH' for event in first['activity'])
        market.fail = True
        now[0] += manager.MARKET_TTL
        await manager.fetch_and_compute()
        failed = await settle(manager)
        assert all(r['price_usd'] == 2 and r['market_state'] == 'stale' for r in failed['tokens'])
        assert all(r['market_read_at'] == 1000 for r in failed['tokens'])
    finally:
        await manager.close()


async def test_close_cancels_pending_work_and_never_closes_borrowed_providers():
    started, gate = asyncio.Event(), asyncio.Event()
    class Slow(Pages):
        async def fetch_page(self, **kw):
            started.set()
            await gate.wait()
    pages, market, source = Slow(), Market(), Source()
    manager = SwarmTokensManager(source, client=pages, market=market, clock=lambda: 1000)
    await manager.fetch_and_compute()
    await started.wait()
    await manager.close()
    assert all(task.done() for task in manager._tasks.values())
    assert not source.closed and not pages.closed
    assert not getattr(market, 'closed', False)


async def test_successful_empty_catalogue_is_distinct_from_first_read_failure():
    pages = Pages([])
    manager = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        empty = await settle(manager)
        assert empty['tokens'] == []
        assert empty['sources']['catalogue']['state'] == 'ok'
        assert empty['sources']['catalogue']['complete']
    finally:
        await manager.close()
    pages.failed = True
    failed = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda: 1000)
    try:
        await failed.fetch_and_compute()
        unavailable = await settle(failed)
        assert unavailable['tokens'] is None
        assert unavailable['sources']['catalogue']['state'] == 'unavailable'
        assert not unavailable['sources']['catalogue']['complete']
    finally:
        await failed.close()


async def test_history_and_trade_work_waits_for_market_discovery():
    class Quotes(Market):
        calls = []
        async def fetch_markets(self, tokens):
            return {t['id']: {'state': 'ok', 'price_usd': 2, 'market_pool': '0x'+'a'*40} for t in tokens}
        async def fetch_history(self, token):
            self.calls.append(('history', token.get('market_pool')))
            return {'state': 'ok', 'sparkline': [1, None, 2], 'timestamps': [1, 2, 3]}
        async def fetch_trades(self, token):
            self.calls.append(('trades', token.get('market_pool')))
            return {'state': 'ok', 'activity': []}
    market = Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        await settle(manager)
        await manager.wait_pending()
        assert not market.calls
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert market.calls and all(pool is not None for _, pool in market.calls)
    finally:
        await manager.close()


async def test_history_and_activity_do_not_cross_selected_market_pools():
    class Quotes(Market):
        pool = '0x'+'a'*40
        async def fetch_markets(self, tokens):
            return {t['id']: {'state': 'ok', 'price_usd': 2, 'market_pool': self.pool} for t in tokens}
        async def fetch_history(self, token):
            return {'state': 'ok', 'sparkline': [1, 2], 'timestamps': [1, 2]}
        async def fetch_trades(self, token):
            return {'state': 'ok', 'activity': [{'id': token['id']+self.pool,
                    'token_id': token['id'], 'ts': 1, 'kind': 'BUY', 'amount': 1, 'asset': 'ETH'}]}
    now, market = [1000], Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: now[0])
    try:
        await manager.fetch_and_compute()
        for _ in range(3):
            await settle(manager)
        before = await manager.fetch_and_compute()
        assert any(row['sparkline'] for row in before['tokens'])
        assert any(row['kind'] == 'BUY' for row in before['activity'])
        market.pool = '0x'+'b'*40
        now[0] += manager.MARKET_TTL
        await manager.fetch_and_compute()
        await manager.wait_pending()
        after = await manager.fetch_and_compute()
        assert all(row['sparkline'] is None for row in after['tokens'])
        assert all(row['kind'] == 'LAUNCH' for row in after['activity'])
    finally:
        await manager.close()


async def test_partial_withdrawal_remains_an_issue_and_keeps_observed_amounts():
    shared = launch_rows(rows())
    for row in shared:
        token = next((a for a in row['artifacts'] if a['role'] == 'token'), None)
        if token:
            row.update(token_address=token['address'], production=True)
            row['liquidity'] = {'paired_amount': 7, 'token_amount': 10, 'paired_symbol': 'IMD',
                                'read_ts': 1000, 'lock': 'withdrawn', 'state': 'warn',
                                'withdrawn_pct': 25}
    manager = SwarmTokensManager(Source(shared), client=Pages(), market=Market(), clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        snapshot = await settle(manager)
        assert all(r['lp_state'] == 'withdrawn' for r in snapshot['tokens'])
        assert all(r['paired_amount'] == 7 and r['token_amount'] == 10 and r['withdrawn_pct'] == 25
                   for r in snapshot['tokens'])
    finally:
        await manager.close()


async def test_unsupported_market_classification_is_not_a_successful_read_clock():
    class Unsupported(Market):
        async def fetch_markets(self, tokens):
            return {t['id']: {'state': 'unsupported'} for t in tokens}
    manager = SwarmTokensManager(Source(), client=Pages(), market=Unsupported(), clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        await settle(manager)
        snapshot = await settle(manager)
        assert all(r['market_state'] == r['history_state'] == r['trades_state'] == 'unsupported'
                   for r in snapshot['tokens'])
        assert all(r['market_read_at'] is None for r in snapshot['tokens'])
        assert snapshot['sources']['markets']['state'] == 'unsupported'
    finally:
        await manager.close()


async def test_confirmed_unindexed_token_clears_old_quote_without_inventing_a_failure():
    class Quotes(Market):
        indexed = True
        async def fetch_markets(self, tokens):
            return {t['id']: ({'state': 'ok', 'price_usd': 2, 'market_pool': '0x'+'a'*40}
                    if self.indexed else {'state': 'unindexed', 'market_pool': None}) for t in tokens}
    now, market = [1000], Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: now[0])
    try:
        await manager.fetch_and_compute()
        await settle(manager)
        before = await settle(manager)
        assert all(row['price_usd'] == 2 for row in before['tokens'])
        market.indexed = False
        now[0] += manager.MARKET_TTL
        await manager.fetch_and_compute()
        after = await settle(manager)
        assert all(row['price_usd'] is None and row['market_state'] == 'unindexed' for row in after['tokens'])
        assert all(row['market_read_at'] == now[0] and row['history_read_at'] is None for row in after['tokens'])
        assert after['sources']['markets']['state'] == 'unindexed'
    finally:
        await manager.close()


@pytest.mark.parametrize('inflight', [False, True])
async def test_new_expected_pool_withholds_cached_or_inflight_quote_and_reads_immediately(inflight):
    shared = launch_rows(rows())
    for row in shared:
        artifact = next((a for a in row['artifacts'] if a['role'] == 'token'), None)
        if artifact:
            row['token_address'] = artifact['address']
    source = Source(shared)
    gate, entered = asyncio.Event(), asyncio.Event()
    if not inflight:
        gate.set()
    old_pool, new_pool = '0x'+'a'*64, '0x'+'b'*64

    class Quotes(Market):
        calls = []
        async def fetch_markets(self, tokens):
            self.calls.append(deepcopy(tokens))
            entered.set()
            await gate.wait()
            return {t['id']: {'state':'ok', 'market_pool':t.get('launch_pool') or old_pool,
                              'price_usd':2 if t.get('launch_pool') else 99} for t in tokens}

    market = Quotes()
    manager = SwarmTokensManager(source, client=Pages(), market=market, clock=lambda:1000)
    try:
        await manager.fetch_and_compute()
        await entered.wait()
        if not inflight:
            await manager.wait_pending()
            assert (await manager.fetch_and_compute())['tokens'][0]['price_usd'] == 99
        source.data['pool_ids'] = {r['launch_id']:new_pool for r in shared}
        gate.set()
        await manager.wait_pending()
        changed = await manager.fetch_and_compute()
        assert all(t['launch_pool'] == new_pool and t['price_usd'] is None
                   and t['market_pool'] is None for t in changed['tokens'])
        await manager.wait_pending()
        fresh = await manager.fetch_and_compute()
        assert all(t['market_pool'] == new_pool and t['price_usd'] == 2 for t in fresh['tokens'])
        assert len(market.calls) == 2  # same clock: invalidation, not TTL expiry
    finally:
        gate.set()
        await manager.close()


async def test_hub_catalogue_summary_agrees_with_dashboard_without_market_reads():
    now = [1000.]
    manager = SwarmTokensManager(Source(), client=Pages(), market=Market(), clock=lambda: now[0])
    try:
        assert manager.catalogue_summary() == {'count': None, 'state': 'unavailable', 'as_of': None}
        manager.offer_catalogue()
        manager.offer_catalogue()
        await manager.wait_pending()
        summary = manager.catalogue_summary()
        assert summary == {'count': 3, 'state': 'ok', 'as_of': 1000.}
        assert set(manager._tasks) == {'catalogue'}
        assert manager.client.calls == [None]
        dashboard = await manager.fetch_and_compute()
        assert summary['count'] == len(dashboard['tokens'])
        assert summary['state'] == dashboard['sources']['catalogue']['state']
        now[0] += 301
        assert manager.catalogue_summary() == {'count': 3, 'state': 'stale', 'as_of': 1000.}
        manager._complete = False
        assert manager.catalogue_summary()['state'] == 'partial'
    finally:
        await manager.close()


async def test_portfolio_retains_inactive_candidates_and_all_launch_aliases():
    # Synthetic status/duplicate variants of the committed catalogue capture.
    raw = rows()[:3]
    raw[0]['status'] = 'abandoned'
    alias = dict(deepcopy(raw[1]), id='aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',
                 launchNumber=1300, status='retired')
    raw.insert(0, alias)
    manager = SwarmTokensManager(Source(), client=Pages(raw), market=Market(), clock=lambda:1000)
    try:
        cold = await manager.fetch_portfolio()
        assert cold['tokens'] is None
        await manager.wait_pending()
        portfolio = await manager.fetch_portfolio()
        market = await manager.fetch_and_compute()
        assert len(portfolio['tokens']) == 3 and len(market['tokens']) == 2
        assert {r['status'] for r in market['tokens']} == {'live'}
        aliased = next(r for r in portfolio['tokens'] if r['launch_uuid'] == raw[2]['id'])
        assert set(aliased['launch_uuids']) == {raw[2]['id'], alias['id']}
        assert next(r for r in market['tokens'] if r['id'] == aliased['id']) == aliased
        assert all(r['price_usd'] is None for r in portfolio['tokens'])
        assert portfolio['sources']['catalogue']['coverage_complete']
        portfolio['tokens'][0]['launch_uuids'].clear()
        portfolio['sources']['catalogue']['reasons'].append('mutated')
        detached = await manager.fetch_portfolio()
        assert detached['tokens'][0]['launch_uuids']
        assert 'mutated' not in detached['sources']['catalogue']['reasons']
    finally:
        await manager.close()


async def test_portfolio_discovery_counts_unresolved_candidates_without_certifying_coverage():
    raw = rows()
    # A second token address is ambiguous; a malformed token address cannot be
    # silently discarded to make the remaining artifact look unambiguous.
    token = next(a for a in raw[0]['artifacts'] if a['role'] == 'token')
    raw[0]['artifacts'].append(dict(token, address='0x'+'f'*40))
    raw[1]['artifacts'].append(dict(token, address='broken address'))
    manager = SwarmTokensManager(Source(), client=Pages(raw), market=Market(), clock=lambda:1000)
    try:
        await manager.fetch_portfolio()
        await manager.wait_pending()
        snapshot = await manager.fetch_portfolio()
        coverage = snapshot['sources']['catalogue']
        assert coverage['complete'] and coverage['loaded'] == 5
        assert not coverage['coverage_complete'] and coverage['state'] == 'partial'
        assert coverage['candidates'] == 1
        assert coverage['unsupported_candidates'] == 1
        assert coverage['ambiguous_candidates'] == 2
        assert coverage['reasons']
        assert [r['chain_id'] for r in snapshot['tokens']] == [4663]
    finally:
        await manager.close()


async def test_portfolio_pages_include_old_inactive_token_after_first_page():
    raw = rows()[:3]
    raw[-1]['status'] = 'retired'
    pages = Pages(raw)
    manager = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda:1000)
    manager.PAGE_SIZE, manager.PAGE_BUDGET = 1, 1
    try:
        for _ in range(4):
            await manager.fetch_portfolio()
            await manager.wait_pending()
        snapshot = await manager.fetch_portfolio()
        assert len(snapshot['tokens']) == 3
        assert snapshot['sources']['catalogue']['coverage_complete']
        assert pages.calls == [None, 1202, 1191, 1172]
    finally:
        await manager.close()


async def test_portfolio_status_change_does_not_erase_deployed_candidate():
    now, pages = [1000], Pages(rows()[:1])
    manager = SwarmTokensManager(Source(), client=pages, market=Market(), clock=lambda:now[0])
    try:
        await manager.fetch_portfolio()
        await manager.wait_pending()
        before = await manager.fetch_portfolio()
        pages.data[0]['status'] = 'abandoned'
        now[0] += manager.CATALOGUE_TTL
        await manager.fetch_and_compute()
        await manager.wait_pending()
        after = await manager.fetch_portfolio()
        assert [r['id'] for r in after['tokens']] == [r['id'] for r in before['tokens']]
        assert after['tokens'][0]['status'] == 'abandoned'
        assert (await manager.fetch_and_compute())['tokens'] == []
    finally:
        await manager.close()


async def test_portfolio_and_market_share_singleflight_clocks_and_enrichment():
    gate, entered = asyncio.Event(), asyncio.Event()
    class Quotes(Market):
        def __init__(self):
            self.calls, self.histories, self.trades = [], [], []
        async def fetch_markets(self, tokens):
            self.calls.append([t['id'] for t in tokens])
            entered.set()
            await gate.wait()
            return {t['id']: {'state':'ok', 'price_usd':2, 'market_pool':'0x'+'a'*40} for t in tokens}
        async def fetch_history(self, token):
            self.histories.append(token['id'])
            return {'state':'ok', 'sparkline':[1,2], 'timestamps':[1,2]}
        async def fetch_trades(self, token):
            self.trades.append(token['id'])
            return {'state':'ok', 'activity':[]}
    market, pages = Quotes(), Pages(rows()[:2])
    manager = SwarmTokensManager(Source(), client=pages, market=market, clock=lambda:1000)
    try:
        await manager.fetch_portfolio()
        await manager.wait_pending()
        await manager.fetch_portfolio()
        await entered.wait()
        await manager.fetch_and_compute()
        await manager.fetch_portfolio()
        assert len(market.calls) == 1 and pages.calls == [None]
        gate.set()
        await manager.wait_pending()
        await manager.fetch_and_compute()
        await manager.fetch_portfolio()
        await manager.wait_pending()
        portfolio = await manager.fetch_portfolio()
        swarm = await manager.fetch_and_compute()
        assert portfolio['tokens'] == swarm['tokens']
        assert len(market.histories) == len(set(market.histories)) == 2
        assert len(market.trades) == len(set(market.trades)) == 2
        assert all(t['market_read_at'] == t['history_read_at'] == 1000 for t in portfolio['tokens'])
    finally:
        gate.set()
        await manager.close()


@pytest.mark.parametrize('refresh_view', ['fetch_portfolio', 'fetch_and_compute'])
async def test_portfolio_activation_keeps_market_only_candidates_refreshing(refresh_view):
    # Synthetic malformed duplicate of a captured token artifact: the existing
    # market view accepts the valid address, while Portfolio reports ambiguity.
    raw = rows()[:2]
    token = next(a for a in raw[0]['artifacts'] if a['role'] == 'token')
    raw[0]['artifacts'].append(dict(token, address='invalid address'))
    class Quotes(Market):
        def __init__(self):
            self.calls = []
        async def fetch_markets(self, tokens):
            self.calls.append([t['id'] for t in tokens])
            return {t['id']: {'state':'ok', 'price_usd':len(self.calls)} for t in tokens}
    now, market = [1000], Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(raw), market=market, clock=lambda:now[0])
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        await manager.fetch_and_compute()
        await manager.wait_pending()
        before = await manager.fetch_and_compute()
        portfolio = await manager.fetch_portfolio()
        assert len(before['tokens']) == 2 and len(portfolio['tokens']) == 1
        assert portfolio['sources']['catalogue']['ambiguous_candidates'] == 1
        now[0] += manager.MARKET_TTL
        await getattr(manager, refresh_view)()
        await manager.wait_pending()
        after = await manager.fetch_and_compute()
        expected = {t['id'] for t in before['tokens']}
        assert len(market.calls) == 2
        assert len(market.calls[1]) == 2 and set(market.calls[1]) == expected
        assert all(t['price_usd'] == 2 and t['market_read_at'] == now[0] for t in after['tokens'])
        assert len((await manager.fetch_portfolio())['tokens']) == 1
    finally:
        await manager.close()


async def test_portfolio_priority_reserves_capacity_for_oldest_market_candidates():
    class Quotes(Market):
        def __init__(self):
            self.calls = []
        async def fetch_markets(self, tokens):
            self.calls.append([t['id'] for t in tokens])
            return {t['id']: {'state':'ok', 'price_usd':2} for t in tokens}
    raw = rows()[:3]
    extra = deepcopy(raw[0])
    extra.update(id='aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa', launchNumber=1300)
    for artifact in extra['artifacts']:
        if artifact['role'] == 'token':
            artifact['address'] = '0x'+'e'*40
    raw.insert(0, extra)
    now, market = [1000], Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(raw), market=market, clock=lambda:now[0])
    manager.MARKET_BATCH = 2
    priority = '4663:0x1a2170fee814b824556f3ada2e90385a29aae8f4'
    try:
        await manager.fetch_portfolio(priority_ids=[priority])
        await manager.wait_pending()
        await manager.fetch_and_compute()  # persisted portfolio priorities apply here too
        await manager.wait_pending()
        assert market.calls[0][0] == priority
        assert len(market.calls[0]) == 2
        # Make priorities due again: never-refreshed market tokens still get slots.
        now[0] += manager.MARKET_TTL
        await manager.fetch_portfolio(priority_ids=[priority])
        await manager.wait_pending()
        await manager.fetch_portfolio(priority_ids=[priority])
        await manager.wait_pending()
        assert len({key for batch in market.calls for key in batch}) == 4
    finally:
        await manager.close()
