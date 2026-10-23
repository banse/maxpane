"""Independent source publication and bounded, reusable enrichment."""
import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.data.test_surf_manager_surfboard import manager
from maxpane_dashboard.data.surf_cache import (
    SurfCache, SLOT_SWARM_WORKERS, SLOT_SWARM_SCORES, TIER_SWARM_SCORES, TIER_SWARM_SEAT,
)


async def test_navigation_keeps_fresh_optional_tier_but_refreshes_seat(manager):
    m, clock = manager
    m.cache.mark_fetched(TIER_SWARM_SCORES, clock.now)
    m.cache.mark_fetched(TIER_SWARM_SEAT, clock.now)
    m.set_active_view('surfboard')
    m.set_active_view('agent')
    try:
        assert not m.cache.is_due(TIER_SWARM_SCORES, clock.now)
        assert m.cache.is_due(TIER_SWARM_SEAT, clock.now)
    finally:
        await m.close()


async def test_pool4_atomic_getters_publish_before_log_history(tmp_path):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4, TIER_POOL4
    from tests.data.test_surf_manager_pool4 import (
        HOOK_BLOCK, SHARE_PRICE, UNCHECKED, VAULT_SHARES, _manager,
    )

    m = _manager(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original_logs = m._pool4_logs

    async def held_logs(*args):
        entered.set()
        await release.wait()
        return await original_logs(*args)

    m._pool4_logs = held_logs
    task = asyncio.create_task(m._pool_pool4({TIER_POOL4}, m._clock(), None))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        entry = m.cache.get_last_good(SLOT_POOL4)
        assert entry is not None
        assert entry.payload['block_number'] == HOOK_BLOCK
        assert entry.ts == m._clock()
        early = m._pool4_keys(entry.payload, entry, m._clock())
        assert early['pool4_vault_shares'] == pytest.approx(VAULT_SHARES)
        assert early['pool4_share_price'] == pytest.approx(SHARE_PRICE)
        assert early['pool4_flow'] is None
        assert early['pool4_counter_state'] == UNCHECKED
        assert not task.done()
        release.set()
        await task
        complete = m.cache.get_last_good(SLOT_POOL4)
        assert complete.payload['flow']
        assert complete.payload['counter_state'] != UNCHECKED
    finally:
        release.set()
        await task
        await m.close()


async def test_pool4_unchanged_final_bundle_restores_history_and_original_age(tmp_path):
    from maxpane_dashboard.data.surf_cache import SLOT_POOL4, TIER_POOL4
    from tests.data.test_surf_manager_pool4 import (
        FLOW_LOGS_FULL, FLOW_SWAPS_FULL, FakeClock, FakePool4Client, RECONCILED, UNCHECKED, _manager,
    )

    # The full-history capture ends later than the smaller default window.
    clock = FakeClock(max(int(row['blockTimestamp'], 16) for row in FLOW_SWAPS_FULL) + 60)
    m = _manager(tmp_path, clock=clock,
                 pool4_client=FakePool4Client(fetch_flow_logs=FLOW_LOGS_FULL))
    entered, release = asyncio.Event(), asyncio.Event()
    task = None
    try:
        await m._pool_pool4({TIER_POOL4}, m._clock(), None)
        original = copy.deepcopy(m.cache.get_last_good(SLOT_POOL4))
        initial = m._pool4_keys(original.payload, original, m._clock())
        assert initial['pool4_counter_state'] == RECONCILED
        assert initial['pool4_flow']
        m._clock_double.advance(60)
        original_logs = m._pool4_logs

        async def held_logs(*args):
            entered.set()
            await release.wait()
            return await original_logs(*args)

        m._pool4_logs = held_logs
        task = asyncio.create_task(m._pool_pool4({TIER_POOL4}, m._clock(), None))
        await asyncio.wait_for(entered.wait(), 1)
        staged = m.cache.get_last_good(SLOT_POOL4)
        assert staged.payload['flow'] == original.payload['flow']
        assert staged.payload['counter_state'] == UNCHECKED
        assert staged.ts == original.ts
        assert not task.done()
        release.set()
        result = await task
        assert result['changed'] is False
        final = m.cache.get_last_good(SLOT_POOL4)
        assert final.payload == original.payload
        assert final.ts == original.ts
        projected = m._pool4_keys(final.payload, final, m._clock())
        assert projected['pool4_counter_state'] == RECONCILED
        assert [row['age_s'] for row in projected['pool4_flow']] == pytest.approx(
            [row['age_s'] + 60 for row in initial['pool4_flow']])
        assert projected['pool4_as_of_hhmm'] == initial['pool4_as_of_hhmm']
    finally:
        release.set()
        if task is not None:
            await task
        await m.close()


async def test_onchain_offer_and_source_updates_do_not_wait_for_full_cycle(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_ACTIVITY, SLOT_CHANNEL, TIER_MEDIUM, TIER_SLOW
    from tests.data.test_surf_manager import FakeSurfClient

    m, clock = manager
    m.client = FakeSurfClient()
    m.set_active_view('dashboard')
    entered, release = asyncio.Event(), asyncio.Event()

    async def held_cycle():
        entered.set()
        await release.wait()
        return m._blank_payload()

    m._cycle = held_cycle
    try:
        offered = await asyncio.wait_for(m.fetch_and_compute(), 1)
        await asyncio.wait_for(entered.wait(), 1)
        assert offered['feed_items'] is None
        assert offered['dev_activity'] is None
        assert not m._full_task.done()
        await m._pool_channel({TIER_MEDIUM}, clock.now, None)
        await m._pool_activity({TIER_SLOW}, clock.now, None, None)
        snapshot = m.get_snapshot()
        channel = m.cache.get_last_good(SLOT_CHANNEL).payload['items']
        activity = m.cache.get_last_good(SLOT_ACTIVITY).payload['rows']
        assert channel and activity
        assert snapshot['feed_items'] == channel
        assert snapshot['dev_activity'] == activity
        assert 'activity_rows' not in snapshot
        assert not m._full_task.done()
    finally:
        release.set()
        if m._full_task is not None:
            await m._full_task
        await m.close()


async def test_agent_answers_publish_while_cards_and_ens_are_held(tmp_path):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_ANSWERS
    from tests.data.test_surf_manager import FakeClock
    from tests.data.test_surf_manager_answers import Answers, NOW, data, work
    from tests.data.test_surf_manager_swarm import _manager

    fake = Answers(work(1))
    m = _manager(tmp_path, fake, clock=FakeClock(NOW))
    m.set_seat(420)
    m.set_active_view('agent')
    cards_entered, ens_entered, published = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release_cards, release_ens = asyncio.Event(), asyncio.Event()
    priorities = []

    async def held_cards(seat, now, *, priority_jobs):
        priorities.extend(priority_jobs)
        cards_entered.set()
        await release_cards.wait()

    async def held_ens(*args):
        ens_entered.set()
        await release_ens.wait()

    store = m.cache.store_last_good

    def observed_store(slot, payload, **kwargs):
        result = store(slot, payload, **kwargs)
        if slot == SLOT_SWARM_ANSWERS:
            published.set()
        return result

    m.cache.store_last_good = observed_store
    m._agent_card_sources.read = held_cards
    m._resolve_seat_owner = held_ens
    m._pool_swarm_oracle = AsyncMock()
    m._pool_swarm_job_details = AsyncMock()
    task = asyncio.create_task(m._pool_swarm_seat(420, NOW))
    try:
        await asyncio.wait_for(asyncio.gather(
            cards_entered.wait(), ens_entered.wait(), published.wait()), 1)
        rows = data(m)['swarm_seat_work_rows']
        assert len(rows) == 1
        assert rows[0]['job_id'] == fake.seat['work'][0]['jobId']
        assert rows[0]['submission_hash'] == fake.seat['work'][0]['submissionHash']
        assert rows[0]['answer_state'] == 'read'
        assert rows[0]['answer'] == 'Answer 0.'
        assert priorities == [rows[0]['job_id']]
        assert not task.done()
        assert not release_cards.is_set() and not release_ens.is_set()
    finally:
        release_cards.set()
        release_ens.set()
        await task
        await m.close()


async def test_pool4_protocol_starts_without_waiting_for_market(manager):
    m, clock = manager
    m.set_active_view('pool4_user')
    market_entered, protocol_entered = asyncio.Event(), asyncio.Event()
    release_market, release_protocol = asyncio.Event(), asyncio.Event()

    async def market():
        market_entered.set()
        await release_market.wait()

    async def protocol(*args):
        protocol_entered.set()
        await release_protocol.wait()

    m._card_reader._market = market
    m._pool_channel = AsyncMock(return_value=None)
    m._pool_pool4 = protocol
    m._pool_pool4_stakers = AsyncMock(return_value=None)
    task = asyncio.create_task(m._collect_visible_detail('pool4_user', clock.now))
    try:
        await asyncio.wait_for(asyncio.gather(
            market_entered.wait(), protocol_entered.wait()), 1)
        await task
        assert not release_market.is_set()
        assert m._pool4_task is not None and not m._pool4_task.done()
        m._pool_channel.assert_awaited_once()
    finally:
        release_market.set()
        release_protocol.set()
        await task
        await m.close()


async def test_scores_publish_workflows_before_optional_job_details(manager):
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    clock.now = raw['read_ts']
    entered, release = asyncio.Event(), asyncio.Event()
    async def detail(*_):
        entered.set()
        await release.wait()
        return None
    m.swarm_client.fetch_jobs = AsyncMock(return_value=raw['jobs'][:1])
    m.swarm_client.fetch_skills = AsyncMock(return_value=[])
    m.swarm_client.fetch_workflows = AsyncMock(return_value=raw['workflows'])
    m.swarm_client.read_job_detail = detail
    task = asyncio.create_task(m._pool_swarm_scores({TIER_SWARM_SCORES}, clock.now))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        entry = m.cache.get_last_good(SLOT_SWARM_SCORES)
        assert entry is not None and entry.payload['workflows']
        assert not task.done()
    finally:
        release.set()
        await task
        await m.close()


async def test_workflow_summary_reuses_persisted_delta_catalogue(manager):
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    clock.now = raw['read_ts']
    m.swarm_client.fetch_workflows = AsyncMock(return_value=raw['workflows'])
    try:
        await m._card_reader._work()
        initial = m._card_reader.workflows
        assert initial is not None
        m.cache.save()
        cache = SurfCache(path=m.cache.path, clock=lambda: clock.now)
        cache.load()
        assert cache.workflow_catalogue is not None
        m.cache.workflow_catalogue = cache.workflow_catalogue
        clock.now += 31
        m.swarm_client.fetch_workflows = AsyncMock(return_value=[])
        await m._card_reader._work()
        assert m._card_reader.workflows == initial
        assert 'since' in m.swarm_client.fetch_workflows.call_args.kwargs
    finally:
        await m.close()


async def test_workers_publish_before_slow_contributors(manager):
    m, clock = manager
    entered, release, published = asyncio.Event(), asyncio.Event(), asyncio.Event()
    store = m.cache.store_last_good

    def observed_store(slot, payload, **kwargs):
        result = store(slot, payload, **kwargs)
        if slot == SLOT_SWARM_WORKERS:
            published.set()
        return result

    m.cache.store_last_good = observed_store
    async def contributors():
        entered.set()
        await release.wait()
        return None
    m.swarm_client.fetch_contributors = contributors
    m.swarm_client.fetch_workers = AsyncMock(return_value=json.loads(
        Path('tests/fixtures/surf/swarm/v3/workers.json').read_text()))
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_BOARD
    task = asyncio.create_task(m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now))
    try:
        await asyncio.wait_for(asyncio.gather(entered.wait(), published.wait()), 1)
        assert m.cache.get_last_good(SLOT_SWARM_WORKERS) is not None
        assert not task.done()
    finally:
        release.set()
        await task
        await m.close()


async def test_launch_list_is_published_before_optional_evidence(manager):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCHES, TIER_SWARM_LAUNCHES
    m, clock = manager
    raw = json.loads(Path('tests/fixtures/surf/swarm/v8/launches_100.json').read_text())
    clock.now = 1793000000.
    m.swarm_client.fetch_launches = AsyncMock(return_value=raw['launches'])
    m.swarm_client.fetch_sites = AsyncMock(return_value=[])
    m.swarm_client.fetch_launch_policies = AsyncMock(return_value=[])
    entered = asyncio.Event()
    async def evidence(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    m._enrich_swarm_launch_evidence = evidence
    task = asyncio.create_task(m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, clock.now))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        entry = m.cache.get_last_good(SLOT_SWARM_LAUNCHES)
        assert entry is not None and entry.payload['launches']
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await m.close()


async def test_malformed_launch_head_is_normalized_and_held_siblings_drain(manager):
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES
    m, clock = manager
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def sites():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    m.set_active_view('swarm')
    m.swarm_client.fetch_launches = AsyncMock(return_value=[{}, None, {'id': []}])
    m.swarm_client.fetch_sites = sites
    m.swarm_client.fetch_launch_policies = AsyncMock(return_value=[{}])
    task = m._spawn_swarm_launches({TIER_SWARM_LAUNCHES}, clock.now)
    try:
        await asyncio.wait_for(entered.wait(), 1)
        m.set_active_view(None)
        await m.drain_reads()
        assert cancelled.is_set()
        assert m._error_count == 0
    finally:
        # Even the broken implementation must leave no held test task behind.
        for child in asyncio.all_tasks():
            if 'read_head' in getattr(child.get_coro(), '__qualname__', ''):
                child.cancel()
        await m.close()
