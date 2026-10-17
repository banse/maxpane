"""Visibility is the network boundary; card reads cannot hydrate hidden boards."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from tests.data.test_surf_manager_surfboard import manager


async def test_boardroom_never_offers_full_boards(manager):
    m, _ = manager
    m._offer_full = Mock(side_effect=AssertionError('full dashboard collection'))
    m._work_reader.offer = Mock(side_effect=AssertionError('work details'))
    m.set_active_view('surfboard')
    try:
        await m.fetch_hub_snapshot()
        assert m._full_task is None
        assert m._work_reader.task is None
    finally:
        await m.close()


async def test_scope_change_drains_detached_reads_before_reentry(manager):
    m, _ = manager
    entered, cancelled, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def read():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
            await finish.wait()
    m.set_active_view('dashboard')
    old = m._full_task = asyncio.create_task(read())
    await entered.wait()
    try:
        m.set_active_view(None)
        await asyncio.wait_for(cancelled.wait(), 1)
        m.set_active_view('work')
        drain = asyncio.create_task(m.drain_reads())
        await asyncio.sleep(0)
        assert not drain.done()
        assert m._work_reader.task is None
        finish.set()
        await drain
        assert old.cancelled()
        assert m._last_full_payload is None
    finally:
        finish.set()
        old.cancel()
        await asyncio.gather(old, return_exceptions=True)
        await m.close()


async def test_work_summary_uses_global_counter_without_job_details(manager):
    m, clock = manager
    m.swarm_client.fetch_jobs = AsyncMock(side_effect=AssertionError('job body'))
    m.swarm_client.fetch_workflows = AsyncMock(return_value=[])
    m.set_active_view('surfboard')
    try:
        await m.fetch_hub_snapshot()
        await asyncio.gather(*m._hub_source_tasks.values())
        await m._card_reader.wait_pending()
        data = m.get_hub_snapshot()
        card = next(c for c in data['surfboard_cards'] if c['key'] == 'work')
        assert card['primary'] == '4'
        assert card['work_summary']['build'] is None
        m.swarm_client.fetch_jobs.assert_not_awaited()
        m.swarm_client.fetch_job.assert_not_awaited()
    finally:
        await m.close()


async def test_native_work_scope_does_not_start_hidden_launch_pipeline(manager):
    m, _ = manager
    m._spawn_swarm_launches = Mock(side_effect=AssertionError('hidden launches'))
    m._work_reader.offer = Mock()
    m.set_active_view('work')
    try:
        await m.fetch_and_compute()
        m._work_reader.offer.assert_called_once()
    finally:
        await m.close()


async def test_nft_card_stops_at_proof_boundary_and_reuses_it_for_details():
    from maxpane_dashboard.data.surf_nft_chain import SurfNftInspector
    from maxpane_dashboard.data.surf_nft_client import Budget
    from tests.data.test_surf_nft_chain import AsyncReads, ADDRESS, TX
    client = AsyncReads()
    inspector = SurfNftInspector(client, clock=lambda: 1792200000.)
    candidate = dict(chainId=1, address=ADDRESS, artifact=dict(txHash=TX), launch={})
    result = await inspector.advance(candidate, budget=Budget(monotonic=lambda: 10.), proof_only=True)
    assert result.evidence['deploymentConfirmed'] is True
    assert result.evidence['proofOnly'] is True
    assert not result.complete
    assert not any(method == 'source' for method, _ in client.sent)
    assert not any(method == 'eth_call' and not json.loads(params)[0]['data'].startswith('0x01ffc9a7')
                   for method, params in client.sent)
    previous = len(client.sent)
    detailed = await inspector.advance(candidate, result.progress,
                                      budget=Budget(monotonic=lambda: 10.))
    assert detailed.complete
    assert len(client.sent) > previous


async def test_token_scope_cancels_history_but_retains_market_cache(manager):
    m, _ = manager
    tokens = m._swarm_tokens_manager
    started = asyncio.Event()
    async def history():
        started.set()
        await asyncio.Event().wait()
    tokens.set_active_view('swarm-tokens')
    tokens._history['retained'] = ({'points': [1, 2]}, 900)
    old = tokens._tasks['history'] = asyncio.create_task(history())
    await started.wait()
    tokens.set_active_view(None)
    tokens.set_active_view('surfboard')
    await tokens.drain_reads()
    assert old.cancelled()
    assert tokens._history['retained'][0]['points'] == [1, 2]
    await m.close()


async def test_passive_token_snapshot_cannot_start_launch_verification(manager):
    m, _ = manager
    m._spawn_swarm_launches = Mock(side_effect=AssertionError('passive network offer'))
    try:
        m._swarm_tokens_manager.get_snapshot()
        m._swarm_tokens_manager.get_portfolio_snapshot()
        m.get_hub_snapshot()
    finally:
        await m.close()


@pytest.mark.parametrize('view, expected', [
    ('swarm', {'swarm', 'scores', 'launches'}),
    ('agent', {'board', 'seat'}),
    ('board', {'board'}),
    ('launchpad', {'launchpad'}),
    ('pool4', {'pool4', 'stakers'}),
    ('pool4_user', {'pool4', 'stakers'}),
])
async def test_native_detail_has_an_explicit_collector_boundary(manager, view, expected):
    m, _ = manager
    calls = set()
    for suffix, label in (('swarm', 'swarm'), ('swarm_scores', 'scores'),
                          ('swarm_launches', 'launches'), ('swarm_board', 'board'),
                          ('launchpad', 'launchpad'), ('pool4', 'pool4'), ('pool4_stakers', 'stakers')):
        setattr(m, '_spawn_' + suffix, Mock(side_effect=lambda *a, name=label: calls.add(name)))
    m._offer_swarm_seat = AsyncMock(side_effect=lambda *a: calls.add('seat'))
    m._pool_channel = AsyncMock()
    m.set_active_view(view)
    try:
        await m.fetch_and_compute()
        await m._full_task
        assert calls == expected
        m._cycle.assert_not_awaited()
    finally:
        await m.close()


async def test_card_pool_never_reads_logs_or_stakers_and_preserves_failed_fields(manager):
    from maxpane_dashboard.data.surf_card_reader import SurfCardReader
    m, clock = manager
    trace = []
    async def answer(name, value):
        trace.append(name)
        return value
    m._pool4_discovery = AsyncMock(return_value=(None, None))
    m.pool4_client = SimpleNamespace(
        fetch_hook_state=lambda *a, **kw: answer('hook', dict(rewards_recipient='recipient',
                                                            pool_id='pool', pool_manager='manager')),
        resolve_vault_path=lambda *a, **kw: answer('path', {'vault': 'vault'}),
        fetch_vault_state=lambda *a, **kw: answer('vault', {'share_price_wei': 2 * 10**18}),
        fetch_pool_slot0=lambda *a, **kw: answer('slot0', {'tick': 0}),
        close=AsyncMock(),
    )
    reader = SurfCardReader(m)
    try:
        await reader._pool()
        assert sorted(trace) == ['hook', 'path', 'slot0', 'vault']
        assert reader.pool_snapshot()['pool4_share_price'] == 2
        stamp = reader.pool_ts
        clock.now += 30
        m.pool4_client.fetch_pool_slot0 = AsyncMock(return_value=None)
        await reader._pool()
        assert reader.pool_ts == stamp  # A fresh vault cannot re-date the retained price.
    finally:
        await m.close()


async def test_roster_card_sources_start_in_parallel(manager):
    m, _ = manager
    entered = set()
    release = asyncio.Event()
    async def read(name):
        entered.add(name)
        if len(entered) == 2:
            release.set()
        await release.wait()
        return None  # Both failures must still have been admitted concurrently.
    m.swarm_client.fetch_workers = lambda: read('workers')
    m.swarm_client.fetch_contributors = lambda: read('contributors')
    m.set_active_view('surfboard')
    try:
        await m.fetch_hub_snapshot()
        await asyncio.wait_for(m._swarm_board_task, 1)
        assert entered == {'workers', 'contributors'}
    finally:
        await m.close()


def _seed_pool_card(manager, clock, *, stamp):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4
    from tests.data.test_surf_manager_surfboard import seed_quote
    manager.set_active_view('surfboard')
    manager._card_reader.pool = dict(pool4_network='ethereum', pool4_share_price=2, tick=0)
    manager._card_reader.pool_ts = stamp
    manager.cache.store_last_good(SLOT_POOL4, {'network': 'sepolia'}, ts=stamp)
    seed_quote(manager, 2000, clock.now)


async def test_pool_card_retained_observation_keeps_its_age(manager):
    m, clock = manager
    _seed_pool_card(m, clock, stamp=100)
    try:
        card = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert card['status'] == 'stale'
        assert card['primary'] == '2,000.00'
        assert m._card_reader.pool_ts == 100
    finally:
        await m.close()


@pytest.mark.parametrize('failure', ['exception', 'empty', 'partial'])
async def test_pool_card_fresh_retained_data_records_failed_refresh(manager, failure):
    from maxpane_dashboard.data.surf_card_reader import SurfCardReader
    from maxpane_dashboard.data.surf_manager import POOL4_NETWORK_SEPOLIA, POOL4_SEPOLIA_HOOK
    m, clock = manager
    _seed_pool_card(m, clock, stamp=990)
    reader = m._card_reader
    reader.pool.update(identity=(POOL4_NETWORK_SEPOLIA, POOL4_SEPOLIA_HOOK),
                       tick_ts=990, share_ts=990)
    m._pool4_discovery = AsyncMock(return_value=(None, None))
    hook = dict(rewards_recipient='recipient', pool_id='pool', pool_manager='manager')
    m.pool4_client = SimpleNamespace(
        fetch_hook_state=AsyncMock(side_effect=RuntimeError('offline') if failure == 'exception' else None,
                                  return_value=hook if failure == 'partial' else None),
        resolve_vault_path=AsyncMock(return_value={'vault': 'vault'}),
        fetch_vault_state=AsyncMock(return_value={'share_price_wei': 2 * 10**18}),
        fetch_pool_slot0=AsyncMock(return_value=None), close=AsyncMock())
    try:
        before = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert before['status'] == 'idle'
        await reader._guard(lambda: SurfCardReader._pool(reader), 'pool4')
        card = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert card['status'] == 'stale'
        assert card['primary'] == before['primary']
        assert reader.pool_ts == 990
        m.pool4_client.fetch_hook_state = AsyncMock(return_value=hook)
        m.pool4_client.fetch_pool_slot0 = AsyncMock(return_value={'tick': 0})
        await reader._guard(lambda: SurfCardReader._pool(reader), 'pool4')
        recovered = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert recovered['status'] == 'idle'
        assert reader.pool_ts == clock.now
    finally:
        await m.close()


async def test_pool_card_cancelled_read_does_not_mark_retained_data_failed(manager):
    m, clock = manager
    _seed_pool_card(m, clock, stamp=990)
    async def cancelled():
        raise asyncio.CancelledError
    try:
        with pytest.raises(asyncio.CancelledError):
            await m._card_reader._guard(cancelled, 'pool4')
        card = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert card['status'] == 'idle'
        assert m._card_reader.pool_ts == 990
    finally:
        await m.close()


async def test_pool_card_failed_first_refresh_marks_retained_detail_cache(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4
    from maxpane_dashboard.data.surf_manager import POOL4_NETWORK_SEPOLIA
    m, clock = manager
    _seed_pool_card(m, clock, stamp=990)
    m._card_reader.pool, m._card_reader.pool_ts = {}, None
    m.cache.store_last_good(SLOT_POOL4, dict(network=POOL4_NETWORK_SEPOLIA,
                           current_tick=0, share_price_wei=2 * 10**18), ts=990)
    async def failed():
        raise OSError('offline')
    try:
        before = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert before['status'] == 'idle'
        await m._card_reader._guard(failed, 'pool4')
        retained = next(c for c in m.get_hub_snapshot()['surfboard_cards'] if c['key'] == 'pool4')
        assert retained['status'] == 'stale'
        assert retained['primary'] == before['primary'] == '2,000.00'
        assert m.cache.get_last_good(SLOT_POOL4).ts == 990
    finally:
        await m.close()
