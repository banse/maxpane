"""Visible nested boards own reads; passive snapshots retain completed facts."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.portfolio_manager import PortfolioManager
from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError('lifecycle tests must not use the network')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)


class Market:
    is_mock = False

    def __init__(self):
        path = Path(__file__).parents[1] / 'fixtures/surf/swarm/v9/launch_791.json'
        self.launch = json.loads(path.read_text())
        self.launch['jobs'] = []
        contract = next(a['address'] for a in self.launch['artifacts'] if a['role'] == 'token')
        self.token = dict(id=f'4663:{contract}', chain_id=4663, token_address=contract,
                          launch_uuid=self.launch['id'], launch_id=791, name='Slabs',
                          symbol='SLABS', price_usd=1.25, market_read_at=100)
        self.calls, self.views = [], []
        self.client = self
        self.block = False
        self.started, self.cancelled = asyncio.Event(), asyncio.Event()

    def set_active_view(self, view):
        self.views.append(view)

    async def drain_reads(self):
        return None

    def get_selected_token(self, *args, **kwargs):
        return deepcopy(self.token)

    async def fetch_selected_token(self, *args, **kwargs):
        self.calls.append('selected')
        return self.get_selected_token()

    def get_portfolio_snapshot(self):
        return dict(tokens=[deepcopy(self.token)], activity=[], sources={
            'catalogue': dict(state='ok', as_of=100, complete=True)})

    async def fetch_portfolio(self, **kwargs):
        self.calls.append('portfolio')
        return self.get_portfolio_snapshot()

    async def fetch_launch_jobs(self, identity):
        self.calls.append('launch')
        if self.block:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        return deepcopy(self.launch)

    async def fetch_sites(self):
        self.calls.append('sites')
        return []


class WalletReads:
    def __init__(self):
        self.calls = 0
        self.block = False
        self.started, self.cancelled = asyncio.Event(), asyncio.Event()

    async def gate(self):
        self.calls += 1
        if self.block:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()

    async def read_balances(self, wallet, rows):
        await self.gate()
        return {row['id']: dict(held_quantity=2, balance_state='ok',
                               balance_read_at=100) for row in rows}

    async def fetch_claims(self, wallet):
        await self.gate()
        return dict(allocations=[], agents=[], sources={
            name: dict(state='ok', as_of=100, complete=True)
            for name in ('claims', 'agents')})


def portfolio():
    now, market, balances, claims = [100], Market(), WalletReads(), WalletReads()
    manager = PortfolioManager(market, '0x' + 'ab' * 20, balances=balances,
                               claims=claims, clock=lambda: now[0])
    return manager, market, balances, claims, now


async def test_portfolio_passive_snapshot_and_reopen_refresh_inside_ttl():
    manager, market, balances, claims, now = portfolio()
    manager.set_active_view('PORTFOLIO')
    first = await manager.fetch_and_compute()
    assert first['tokens'][0]['held_quantity'] is None
    await manager.wait_pending()
    ready = manager.get_snapshot()
    assert ready['tokens'][0]['held_quantity'] == 2
    assert market.calls == ['portfolio']
    manager.set_active_view(None)
    await manager.drain_reads()
    now[0] = 101
    assert manager.get_snapshot()['tokens'][0]['balance_read_at'] == 100
    manager.set_active_view('PORTFOLIO')
    await manager.fetch_and_compute()
    await manager.wait_pending()
    assert balances.calls == claims.calls == 2
    assert market.views == ['portfolio', None, 'portfolio']
    await manager.close()


async def test_portfolio_suspend_drains_wallet_reads_and_inactive_fetch_is_passive():
    manager, market, balances, claims, _ = portfolio()
    manager.set_active_view('PORTFOLIO')
    balances.block = claims.block = True
    await manager.fetch_and_compute()
    await asyncio.wait_for(asyncio.gather(balances.started.wait(), claims.started.wait()), 1)
    assert manager.is_loading()
    manager.set_active_view(None)
    await manager.drain_reads()
    assert balances.cancelled.is_set() and claims.cancelled.is_set()
    assert not manager.is_loading()
    await manager.fetch_and_compute()
    assert market.calls == ['portfolio']
    assert balances.calls == claims.calls == 1
    await manager.close()


async def test_token_detail_suspend_and_reopen_keep_cache_but_refresh_now():
    market, now = Market(), [100]
    manager = SwarmTokenDetailManager(market, market.token, clock=lambda: now[0])
    manager.set_active_view('TOKEN')
    await manager.fetch_and_compute()
    await manager.wait_pending()
    ready = manager.get_snapshot()
    assert ready['launch']['number'] == 791
    assert ready['sources']['launch']['read_ts'] == 100
    manager.set_active_view(None)
    await manager.drain_reads()
    assert (await manager.fetch_and_compute())['launch'] == ready['launch']
    assert market.calls.count('selected') == market.calls.count('launch') == 1
    now[0] = 101
    market.block = True
    manager.set_active_view('TOKEN')
    await manager.fetch_and_compute()
    await asyncio.wait_for(market.started.wait(), 1)
    assert manager.get_snapshot()['sources']['launch']['read_ts'] == 100
    assert market.calls.count('launch') == 2
    manager.set_active_view(None)
    await manager.drain_reads()
    assert market.cancelled.is_set() and not manager.is_loading()
    assert market.views == ['token:' + market.token['id'], None,
                            'token:' + market.token['id'], None]
    await manager.close()


@pytest.mark.parametrize('kind', ['portfolio', 'token'])
async def test_retired_read_cannot_publish_after_rapid_reactivation(kind):
    if kind == 'portfolio':
        manager, market, source, _, now = portfolio()
        method = 'read_balances'
    else:
        market, now = Market(), [100]
        source, method = market, 'fetch_launch_jobs'
        manager = SwarmTokenDetailManager(market, market.token, clock=lambda: now[0])
    manager.set_active_view('active')
    await manager.fetch_and_compute()
    await manager.wait_pending()
    original = getattr(source, method)
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def late_read(*args, **kwargs):
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
        result = await original(*args, **kwargs)
        if kind == 'portfolio':
            for row in result.values():
                row['held_quantity'] = 999
        else:
            result['status'] = 'failed'
        return result

    setattr(source, method, late_read)
    now[0] += 1000
    await manager.fetch_and_compute()
    await asyncio.wait_for(entered.wait(), 1)
    manager.set_active_view(None)
    await asyncio.wait_for(cancelled.wait(), 1)
    manager.set_active_view('active')
    release.set()
    await manager.drain_reads()
    snapshot = manager.get_snapshot()
    if kind == 'portfolio':
        assert snapshot['tokens'][0]['held_quantity'] == 2
    else:
        assert snapshot['launch']['status'] != 'failed'
        assert market.calls.count('sites') == 1
    await manager.close()
