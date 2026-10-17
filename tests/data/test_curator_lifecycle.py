"""Curator visibility owns its detached holders, cross-check and analysis reads."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from maxpane_dashboard.data.curator_cache import TIER_ANALYSIS, TIER_SLOW
from maxpane_dashboard.data.curator_list_filters import PREDEFINED_NFT_COLLECTIONS
from maxpane_dashboard.data.curator_manager import CuratorManager


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError('lifecycle tests must not use the network')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)


def manager():
    value = CuratorManager.__new__(CuratorManager)
    value._nft_task = value._crosscheck_task = value._analysis_task = None
    value._nft_running_request = value._nft_queued_request = None
    value._nft_failed_until = {}
    value._clock = lambda: 100
    stored = []
    value.cache = SimpleNamespace(nft_holders=lambda *args: None,
        store_nft_holders=lambda *args, **kwargs: stored.append((args, kwargs)))
    return value, stored


async def test_curator_suspend_drains_three_readers_and_discards_queued_followup():
    value, _ = manager()
    started = [asyncio.Event() for _ in range(3)]
    calls, finished = [], []

    async def read(index, *args):
        calls.append(index)
        started[index].set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(index)

    value._nft_client = SimpleNamespace(scan=lambda *args: read(0, *args))
    value._pool_crosscheck = lambda *args: read(1, *args)
    value._pool_analysis = lambda *args: read(2, *args)
    value.set_active_view('curator')
    for _ in range(2):
        value._queue_nft_scan(PREDEFINED_NFT_COLLECTIONS[:1], (), 'first')
        value._spawn_crosscheck({TIER_SLOW}, 100, {}, {})
        value._spawn_analysis({TIER_ANALYSIS}, 100, {})
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started)), 1)
        value._queue_nft_scan(PREDEFINED_NFT_COLLECTIONS[:1], (), 'queued')
        assert value._nft_queued_request is not None and value.is_loading()
        value.set_active_view(None)
        await value.drain_reads()
        assert not value.is_loading() and value._nft_queued_request is None
        prior = list(calls)
        value._queue_nft_scan(PREDEFINED_NFT_COLLECTIONS[:1], (), 'hidden')
        assert value._spawn_crosscheck({TIER_SLOW}, 100, {}, {}) is None
        assert value._spawn_analysis({TIER_ANALYSIS}, 100, {}) is None
        assert calls == prior
        for event in started:
            event.clear()
        value.set_active_view('curator')
    assert sorted(finished) == [0, 0, 1, 1, 2, 2]


async def test_retired_nft_scan_cannot_store_or_restart_after_reactivation():
    value, stored = manager()
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    async def scan(collection, wallets):
        calls.append(collection.key)
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
        return SimpleNamespace(complete=True, checked=0, failed=0, holders=(), block_number=1)

    value._nft_client = SimpleNamespace(scan=scan)
    value.set_active_view('curator')
    value._queue_nft_scan(PREDEFINED_NFT_COLLECTIONS[:1], (), 'first')
    await asyncio.wait_for(entered.wait(), 1)
    value.set_active_view(None)
    await asyncio.wait_for(cancelled.wait(), 1)
    value.set_active_view('curator')
    value._queue_nft_scan(PREDEFINED_NFT_COLLECTIONS[1:2], (), 'new')
    release.set()
    await value.drain_reads()
    assert len(calls) == 1 and stored == []
    assert value._nft_queued_request is None and not value.is_loading()
