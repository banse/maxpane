"""Cancellation owns sibling HTTP reads and detached FWA sweeps."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from maxpane_dashboard.data.fwa_manager import FWAManager
from maxpane_dashboard.data.talismans_manager import TalismansManager
from maxpane_dashboard.data.ttt_manager import TTTManager


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError('lifecycle tests must not use the network')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)


@pytest.mark.parametrize('pair', ['ttt_state', 'ttt_market', 'talismans_state'])
async def test_cancelled_refresh_drains_both_independent_reads(pair):
    started = [asyncio.Event(), asyncio.Event()]
    tasks = []

    async def blocked(index):
        tasks.append(asyncio.current_task())
        started[index].set()
        await asyncio.Event().wait()

    async def noop(*args):
        return None

    async def value():
        return {}

    if pair == 'talismans_state':
        manager = TalismansManager.__new__(TalismansManager)
        manager.client = SimpleNamespace(fetch_block_number=lambda: blocked(0),
                                         fetch_collection_flags=lambda: blocked(1))
    else:
        manager = TTTManager.__new__(TTTManager)
        manager._cycle_count = manager._error_count = 0
        manager._last_factory = None
        manager.client = SimpleNamespace(fetch_factory_state=lambda: blocked(0),
                                         fetch_block_number=lambda: blocked(1))
        if pair == 'ttt_market':
            manager.client.fetch_factory_state = manager.client.fetch_block_number = value
            manager._scan_events = manager._fill_missing_metadata = manager._refresh_reservoirs = noop
            manager._refresh_market_data = lambda: blocked(0)
            manager.price_client = SimpleNamespace(get_eth_usd=lambda: blocked(1))
    refresh = asyncio.create_task(manager.fetch_and_compute())
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started)), 1)
        refresh.cancel()
        await asyncio.gather(refresh, return_exceptions=True)
        assert all(task.done() for task in tasks), 'a sibling HTTP read survived screen cancellation'
    finally:
        for task in tasks:
            task.cancel()
        refresh.cancel()
        await asyncio.gather(refresh, *tasks, return_exceptions=True)


async def test_fwa_suspension_drains_both_sweeps_without_closing_clients():
    manager = FWAManager.__new__(FWAManager)
    manager._floor_task = manager._name_task = None
    manager._clock = lambda: 100
    manager._collection_addresses = ('0x' + 'ab' * 20,)
    started, finished, closed = [], [], []
    signals = [asyncio.Event(), asyncio.Event()]

    async def read(index, *args):
        started.append(index)
        signals[index].set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(index)

    async def close():
        closed.append(True)

    manager.market = SimpleNamespace(fetch_nft_floors=lambda *args: read(0, *args), close=close)
    manager.client = SimpleNamespace(fetch_collection_names=lambda *args: read(1, *args), close=close)
    manager.cache = SimpleNamespace(get_collection_name=lambda value: None,
                                   ens_names_fresh=lambda *args: {}, ens_misses_fresh=lambda *args: set())
    manager.set_active_view('fwa')
    manager._start_floor_sweep()
    manager._start_name_sweep()
    await asyncio.wait_for(asyncio.gather(*(signal.wait() for signal in signals)), 1)
    assert manager.is_loading()
    manager.set_active_view(None)
    await manager.drain_reads()
    assert sorted(finished) == [0, 1] and not closed and not manager.is_loading()
    manager._start_floor_sweep()
    manager._start_name_sweep()
    assert started == [0, 1]
    manager.set_active_view('fwa')
    for signal in signals:
        signal.clear()
    manager._start_floor_sweep()
    manager._start_name_sweep()
    await asyncio.wait_for(asyncio.gather(*(signal.wait() for signal in signals)), 1)
    assert started == [0, 1, 0, 1]
    manager.set_active_view(None)
    await manager.drain_reads()
