"""Optional native reads cannot hold the next independent source offer."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from tests.data.test_surf_manager_surfboard import manager


@pytest.mark.parametrize('view', ['agent', 'launchpad', 'pool4', 'pool4_user'])
async def test_due_native_sources_are_offered_while_quote_is_held(manager, view):
    m, clock = manager
    m.set_active_view(view)
    quote_started, quote_cancelled = asyncio.Event(), asyncio.Event()
    quote_calls, offers = [], []

    async def quote():
        quote_calls.append(clock.now)
        quote_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            quote_cancelled.set()

    m._card_reader._market = quote
    m._pool_channel = AsyncMock()
    m._offer_swarm_seat = AsyncMock()
    m._spawn_runtime_latest = Mock()
    m._spawn_pool4_stakers = Mock()
    spawn = {'agent': '_spawn_swarm_board', 'launchpad': '_spawn_launchpad'}.get(view, '_spawn_pool4')
    offered = asyncio.Event()

    def record_offer(*args, **kwargs):
        offers.append(clock.now)
        offered.set()

    setattr(m, spawn, Mock(side_effect=record_offer))
    try:
        await m.fetch_and_compute()
        await asyncio.wait_for(asyncio.gather(quote_started.wait(), offered.wait()), 1)
        offered.clear()
        assert offers == [1000.]
        clock.now += 30
        await m.fetch_and_compute()
        await asyncio.wait_for(offered.wait(), 1)
        assert offers == [1000., 1030.]
        assert quote_calls == [1000.]
        assert m.is_loading(view)
        if view.startswith('pool4'):
            assert m._pool_channel.await_count == 2
        m.set_active_view(None)
        await m.drain_reads()
        assert quote_cancelled.is_set()
        await m.fetch_and_compute()
        assert offers == [1000., 1030.] and quote_calls == [1000.]
    finally:
        m.set_active_view(None)
        await m.drain_reads()
        await m.close()


async def test_held_channel_does_not_block_stakers_or_overlap_itself(manager):
    m, clock = manager
    m.set_active_view('pool4')
    entered, cancelled, stakers_offered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    channel_calls, stakers = [], []

    async def channel(*args):
        channel_calls.append(clock.now)
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    def offer_stakers(*args):
        stakers.append(clock.now)
        stakers_offered.set()

    m._pool_channel = channel
    m._spawn_pool4_stakers = Mock(side_effect=offer_stakers)
    m._spawn_pool4 = Mock()
    try:
        await m.fetch_and_compute()
        await asyncio.wait_for(entered.wait(), 1)
        stakers_offered.clear()
        clock.now += 30
        await m.fetch_and_compute()
        await asyncio.wait_for(stakers_offered.wait(), 1)
        assert stakers == [1000., 1030.]
        assert channel_calls == [1000.]
        assert m.is_loading('pool4')
        m.set_active_view(None)
        await m.drain_reads()
        assert cancelled.is_set()
        m._spawn_pool4.assert_not_called()
    finally:
        m.set_active_view(None)
        await m.drain_reads()
        await m.close()
