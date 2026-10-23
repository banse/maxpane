"""Reader dependency gates and retained token observations, entirely offline."""
import asyncio
from copy import deepcopy
import json
from collections import Counter

import pytest

from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager
from tests.data.test_swarm_tokens_live import Source, Pages, Market, rows
from tests.data.test_swarm_token_detail import Overview, Client


class Quotes(Market):
    def __init__(self):
        self.calls = []

    async def fetch_markets(self, tokens):
        self.calls.append(('markets', tuple(t['id'] for t in tokens)))
        return {t['id']: dict(state='ok', price_usd=2, market_pool='0x'+'a'*40,
                             market_source='DexScreener') for t in tokens}

    async def fetch_history(self, token):
        self.calls.append(('history', token['id']))
        return dict(state='ok', sparkline=[1, None, 2], timestamps=[1, 2, 3])

    async def fetch_trades(self, token):
        self.calls.append(('trades', token['id']))
        return dict(state='ok', activity=[])


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def test_catalogue_chains_to_markets_and_history_without_next_poll():
    market = Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: 1000)
    try:
        assert (await manager.fetch_and_compute())['tokens'] is None
        await manager.wait_pending()
        assert any(call[0] == 'history' for call in market.calls)
        assert any(call[0] == 'trades' for call in market.calls)
        assert any(row['price_usd'] == 2 for row in manager.get_snapshot()['tokens'])
    finally:
        await manager.close()


async def test_navigation_keeps_fresh_catalogue_and_enrichment_attempts():
    market, pages = Quotes(), Pages()
    manager = SwarmTokensManager(Source(), client=pages, market=market, clock=lambda: 1000)
    try:
        manager.set_active_view('SWARM TOKENS')
        await manager.fetch_and_compute()
        await manager.wait_pending()
        calls, heads = list(market.calls), list(pages.calls)
        manager.set_active_view(None)
        await manager.drain_reads()
        manager.set_active_view('SWARM TOKENS')
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert all(Counter(market.calls)[call] == Counter(calls)[call] for call in calls)
        assert pages.calls == heads
    finally:
        await manager.close()


@pytest.mark.parametrize('chains', [('eth', 'base'), ('base', 'eth')])
async def test_market_chain_is_published_before_another_chain_finishes(chains):
    entered, release = asyncio.Event(), asyncio.Event()
    class Gated(Quotes):
        async def fetch_markets(self, tokens):
            if any(t['chain'] == 'base' for t in tokens):
                entered.set()
                await release.wait()
            return await super().fetch_markets(tokens)
    manager = SwarmTokensManager(Source(), client=Pages(), market=Gated(), clock=lambda: 1000)
    # Exercise exactly one bounded market batch, independent of catalogue scope.
    tokens = [dict(id=f'{chain}:token', chain=chain, launch_pool=None) for chain in chains]
    task = asyncio.create_task(manager._refresh_markets(tokens))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await until(lambda: 'eth:token' in manager._market)
        assert manager._market['eth:token'][1] == 1000
        assert 'base:token' not in manager._market
    finally:
        release.set()
        await task
        await manager.close()


async def test_chain_fanout_keeps_total_budget_and_cancels_every_child():
    calls, cancelled = [], []
    class Gated(Quotes):
        async def fetch_markets(self, tokens):
            calls.append([row['id'] for row in tokens])
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(tokens[0]['chain'])
    manager = SwarmTokensManager(Source(), client=Pages(), market=Gated(), clock=lambda: 1000)
    tokens = [dict(id=str(n), launch_id=n, chain=('eth', 'base', 'rh')[n % 3],
                   launch_pool=None, market_pool=None) for n in range(40)]
    try:
        manager._offer_enrichment(tokens, 1000, markets_only=True)
        await until(lambda: len(calls) == 3)
        manager._offer_enrichment(tokens, 1000, markets_only=True)
        assert sum(map(len, calls)) == manager.MARKET_BATCH == 30
        assert len({identity for batch in calls for identity in batch}) == 30
        manager.set_active_view(None)
        await manager.drain_reads()
        assert sorted(cancelled) == ['base', 'eth', 'rh']
        assert not manager.is_loading() and not manager._attempts['markets']
    finally:
        await manager.close()


async def test_completed_contributors_do_not_wait_for_sites():
    entered, release = asyncio.Event(), asyncio.Event()
    class Gated(Client):
        async def fetch_sites(self):
            entered.set()
            await release.wait()
            return await super().fetch_sites()
    overview = Overview(Gated())
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        await until(lambda: manager.get_snapshot()['contributors'] is not None)
        assert manager.get_snapshot()['sources']['contributors']['read_ts'] == 1000
        assert manager.is_loading()
    finally:
        release.set()
        await manager.close()


async def test_restart_restores_bounded_observations_and_original_clocks(tmp_path):
    path = tmp_path / 'tokens.json'
    first = SwarmTokensManager(Source(), client=Pages(), market=Quotes(), clock=lambda: 1000,
                               cache_path=path)
    await first.fetch_and_compute()
    await first.wait_pending()
    await first.fetch_and_compute()
    await first.wait_pending()  # finish the remaining bounded history candidate
    expected = first.get_snapshot()
    await first.close()
    pages, market = Pages(), Quotes()
    second = SwarmTokensManager(Source(), client=pages, market=market, clock=lambda: 1001,
                                cache_path=path)
    try:
        retained = second.get_snapshot()
        assert retained['sources']['catalogue']['as_of'] == 1000
        assert retained['sources']['catalogue']['complete']
        assert [r['price_usd'] for r in retained['tokens']] == [r['price_usd'] for r in expected['tokens']]
        assert all(r['market_read_at'] == 1000 for r in retained['tokens'])
        await second.fetch_and_compute()
        await second.wait_pending()
        assert pages.calls == [] and market.calls == []
    finally:
        await second.close()


async def test_selected_identity_reuses_unchanged_source_index(monkeypatch):
    import maxpane_dashboard.data.swarm_tokens_manager as module
    source = Source()
    source.revision = object()
    source.swarm_tokens_source_revision = lambda: (source.revision,)
    manager = SwarmTokensManager(source, client=Pages(), market=Quotes(), clock=lambda: 1000)
    await manager.fetch_and_compute()
    await manager.wait_pending()
    token = manager.get_snapshot()['tokens'][0]
    original, calls = module.launch_rows, []
    artifacts, artifact_calls = module._token_artifacts, []
    def project(raw):
        calls.append(len(raw))
        return original(raw)
    monkeypatch.setattr(module, 'launch_rows', project)
    def project_artifacts(row):
        artifact_calls.append(row['launch_id'])
        return artifacts(row)
    monkeypatch.setattr(module, '_token_artifacts', project_artifacts)
    try:
        manager.get_selected_token(token['id'])
        calls.clear()
        artifact_calls.clear()
        source.catalogues.clear()
        selected = manager.get_selected_token(token['id'])
        assert selected['id'] == token['id'] and selected['price_usd'] == 2
        assert calls == [] and source.catalogues == []
        assert artifact_calls == [token['launch_uuid']]
    finally:
        await manager.close()


async def test_selected_enrichment_never_expands_to_full_catalogue():
    market = Quotes()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: 1000)
    try:
        manager.offer_catalogue()
        await manager.wait_pending()
        tokens = manager.get_snapshot()['tokens']
        chosen = tokens[0]['id']
        # Other identities already have pools, but this request may only offer
        # the selected identity's missing history and trades.
        manager._market = {row['id']: (dict(state='ok', market_pool='0x'+'a'*40), 1000)
                           for row in tokens}
        await manager.fetch_selected_token(chosen)
        await manager.wait_pending()
        assert market.calls
        assert all((ids == (chosen,) if kind == 'markets' else ids == chosen)
                   for kind, ids in market.calls)
    finally:
        await manager.close()


async def test_cancelled_market_attempt_retries_without_forcing_fresh_siblings():
    entered, release = asyncio.Event(), asyncio.Event()
    class Gated(Quotes):
        async def fetch_markets(self, tokens):
            if tokens[0]['chain'] == 'rh':
                entered.set()
                await release.wait()
            return await super().fetch_markets(tokens)
    market = Gated()
    manager = SwarmTokensManager(Source(), client=Pages(), market=market, clock=lambda: 1000)
    try:
        await manager.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        assert manager._market
        manager.set_active_view(None)
        await manager.drain_reads()
        first = list(market.calls)
        release.set()
        manager.set_active_view('SWARM TOKENS')
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert all(row['market_read_at'] == 1000 for row in manager.get_snapshot()['tokens'])
        assert all(Counter(market.calls)[call] == Counter(first)[call] for call in first)
    finally:
        release.set()
        await manager.close()


@pytest.mark.parametrize('missing', [None, 'bad', -2, float('nan'), True])
def test_persisted_points_validate_individually_and_keep_gaps(tmp_path, missing):
    from maxpane_dashboard.data.swarm_tokens_cache import SwarmTokensCache
    key = '1:0x'+'a'*40
    bad = '1:0x'+'b'*40
    path = tmp_path / 'tokens.json'
    state = dict(version=1, catalogue=rows(), cat_as_of=999, complete=True,
                 market={key: [dict(state='ok', price_usd=3), 999],
                         bad: [dict(state='ok', price_usd=float('inf')), 999]},
                 history={key: [dict(state='ok', timestamps=[1, 2, 3], sparkline=[1, missing, 3]), 998],
                          bad: [dict(state='ok', timestamps=[1], sparkline=[2]), 1001]},
                 volume={key: [dict(state='ok', timestamps=[1, 2, 3], volume_usd=[1, missing, 3]), 997]},
                 trades={key: [dict(state='ok', activity=[
                     dict(id='trade', token_id=key, kind='BUY', ts=999, asset='USD'),
                     dict(id='wrong', token_id=bad, kind='BUY', ts=999, asset='USD', amount=1),
                     dict(id='future', token_id=key, kind='BUY', ts=1001, asset='USD', amount=1)
                 ]), 999]})
    path.write_text(json.dumps(state))
    loaded = SwarmTokensCache(path).load(1000)
    assert loaded['market'][key][1] == 999 and bad not in loaded['market']
    assert loaded['history'][key][0]['sparkline'] == [1, None, 3]
    assert loaded['history'][key][1] == 998
    assert loaded['volume'][key][0]['volume_usd'] == [1, None, 3]
    assert loaded['volume'][key][1] == 997
    assert bad not in loaded['history']
    assert loaded['trades'][key][0]['state'] == 'partial'
    assert [event['id'] for event in loaded['trades'][key][0]['activity']] == ['trade']
    assert loaded['trades'][key][0]['activity'][0]['amount'] is None


def test_cache_bounds_cannot_claim_complete_catalogue(tmp_path, monkeypatch):
    import maxpane_dashboard.data.swarm_tokens_cache as module
    monkeypatch.setattr(module, 'MAX_ROWS', 2)
    monkeypatch.setattr(module, 'MAX_TOKENS', 1)
    cache = module.SwarmTokensCache(tmp_path / 'tokens.json')
    older, newest = '1:0x'+'a'*40, '1:0x'+'b'*40
    cache.save(dict(version=1, catalogue=rows(), cat_as_of=999, complete=True,
                    market={older: [dict(state='ok'), 998], newest: [dict(state='ok'), 999]}), 1000)
    loaded = cache.load(1000)
    assert len(loaded['catalogue']) == 2 and loaded['complete'] is False
    assert list(loaded['market']) == [newest]
    monkeypatch.setattr(module, 'MAX_BYTES', 1)
    assert cache.load(1000) == {}


async def test_restart_of_partial_catalogue_resumes_without_waiting_its_ttl(tmp_path):
    from maxpane_dashboard.data.swarm_tokens_cache import SwarmTokensCache
    path = tmp_path / 'tokens.json'
    SwarmTokensCache(path).save(dict(version=1, catalogue=rows()[:1], cat_as_of=1000,
                                    complete=False), 1000)
    pages = Pages()
    manager = SwarmTokensManager(Source(), client=pages, market=Quotes(), clock=lambda: 1001,
                                 cache_path=path)
    try:
        assert manager.get_snapshot()['sources']['catalogue']['complete'] is False
        manager.offer_catalogue()
        await manager.wait_pending()
        assert pages.calls and manager.get_snapshot()['sources']['catalogue']['complete']
    finally:
        await manager.close()


async def test_detail_close_cancels_independent_sites_read():
    entered, cancelled = asyncio.Event(), asyncio.Event()
    class Gated(Client):
        async def fetch_sites(self):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    overview = Overview(Gated())
    manager = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    await manager.fetch_and_compute()
    await asyncio.wait_for(entered.wait(), 1)
    await until(lambda: manager.get_snapshot()['contributors'] is not None)
    await asyncio.wait_for(manager.close(), 1)
    assert cancelled.is_set() and not manager.is_loading()
