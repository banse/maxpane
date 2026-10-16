"""Selected AGENT snapshots bind their own facts to independent confirmations."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SEAT
from tests.data.test_surf_manager import FakeClock
from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager, _seat_payload_of
from tests.data.test_surf_manager_seat_rewards import _RewardsClient

NOW = 1791806400.0  # after the committed seat's pairing and work timestamps


async def test_premium_usage_uses_all_loaded_answers_and_clears_when_seat_changes(tmp_path):
    from tests.data.test_surf_manager_answers import Answers
    fake = Answers()
    for response, model in zip(fake.responses.values(), ('gpt-6-astra', 'opus', 'fable', 'sonnet', 'sonnet', 'sonnet')):
        submission = response['submissions'][0]
        submission['usage'] = dict(submission['usage'], model=model)
    m = _manager(tmp_path, fake, clock=FakeClock(NOW))
    m.set_seat(420)
    try:
        await m._pool_swarm_seat(420, NOW)
        effort = m._project_hub()['surf_agent_hero']['effort']
        assert (effort['premium_percent'], effort['premium_jobs'], effort['model_jobs'], effort['work_jobs']) == (75., 3, 4, 6)
        m.record_cap = 1
        assert m._project_hub()['surf_agent_hero']['effort'] == effort
        assert len(fake.answer_calls) == 4  # projection adds no eager history reads
        m.set_seat(7)
        assert m._project_hub()['surf_agent_hero']['effort']['premium_percent'] is None
    finally:
        await m.close()


async def test_rank_color_delta_compares_confirmed_reads_not_repaints(agent):
    m, clock, _, _ = agent
    capture = dict(seats={}, rewards={}, rewards_failed=set(), runtime={}, activity=None)
    data = dict(swarm_seat_selected=dict(token_id=420), swarm_seat_rank_delta=99,
                swarm_seat_outcome=dict(token_id=420, listed=True, rank=69, ranked_of=1059),
                swarm_outcomes_source=dict(state='ok', read_ts=NOW))
    def shown():
        return m._agent_hero(data, capture, {}, {}, now=clock())['rank']['delta']
    try:
        assert shown() is None
        clock.advance(120)
        data['swarm_outcomes_source']['read_ts'] = clock()
        data['swarm_seat_outcome']['rank'] = 67
        assert shown() == 2
        assert shown() == 2  # repaint of that same read retains the comparison
        clock.advance(120)
        data['swarm_outcomes_source']['read_ts'] = clock()
        assert shown() == 0
        clock.advance(120)
        data['swarm_outcomes_source']['read_ts'] = clock()
        data['swarm_seat_outcome']['rank'] = 70
        assert shown() == -3
        data['swarm_outcomes_source']['state'] = 'stale'
        assert shown() is None
        data['swarm_seat_selected']['token_id'] = 7
        data['swarm_seat_outcome'].update(token_id=7, rank=10)
        data['swarm_outcomes_source']['state'] = 'ok'
        assert shown() is None
        assert data['swarm_seat_rank_delta'] == 99  # legacy card history untouched
    finally:
        await m.close()


async def test_first_reads_show_loading_only_while_their_own_tasks_are_pending(agent):
    import asyncio
    m, clock, _, _ = agent
    entered, release = asyncio.Event(), asyncio.Event()
    async def hold():
        entered.set()
        await release.wait()
    task = asyncio.create_task(hold())
    await entered.wait()
    m._swarm_board_task = task
    m._swarm_board_pending = {'workers', 'contributors'}
    m._hub_source_tasks['records'] = task
    try:
        hero = m._project_hub()['surf_agent_hero']
        for key in ('accepted', 'rank', 'effort', 'status'):
            assert hero[key]['state'] == 'pending'
        release.set()
        await task
        hero = m._project_hub()['surf_agent_hero']
        for key in ('accepted', 'rank', 'effort', 'status'):
            assert hero[key]['state'] == 'unavailable'
    finally:
        release.set()
        await task
        await m.close()


async def test_finished_failure_does_not_keep_loading_while_sibling_read_waits(agent, monkeypatch):
    import asyncio
    from maxpane_dashboard.data.surf_manager import TIER_SWARM_BOARD
    m, clock, swarm, _ = agent
    entered, release = asyncio.Event(), asyncio.Event()
    async def workers():
        entered.set()
        await release.wait()
        return None
    swarm.fetch_contributors = AsyncMock(return_value=None)
    swarm.fetch_workers = workers
    monkeypatch.setattr(m, '_offer_hub_source', lambda *args: None)
    task = m._spawn_swarm_board({TIER_SWARM_BOARD}, clock())
    try:
        await entered.wait()
        hero = m._project_hub()['surf_agent_hero']
        assert hero['effort']['state'] == 'unavailable'
        assert hero['status']['state'] == 'pending'
        release.set()
        await task
        assert m._project_hub()['surf_agent_hero']['status']['state'] == 'unavailable'
    finally:
        release.set()
        await task
        await m.close()


@pytest.fixture
def agent(tmp_path, monkeypatch):
    clock = FakeClock(NOW)
    client = _RewardsClient()
    swarm = _FakeSwarm(seats={420: _seat_payload_of(420), 421: dict(_seat_payload_of(420), tokenId='421')})
    manager = _manager(tmp_path, swarm, client=client, clock=clock, seat=420)
    for name in ('_resolve_seat_owner', '_pool_swarm_answers', '_pool_swarm_oracle', '_pool_swarm_job_details'):
        monkeypatch.setattr(manager, name, AsyncMock())
    return manager, clock, swarm, client


async def test_unchanged_selected_seat_read_confirms_only_its_own_cards(agent):
    m, clock, swarm, _ = agent
    try:
        await m._pool_swarm_seat(420, clock())
        initial = m._project_hub()['surf_agent_hero']
        assert initial['owner']['state'] == 'ok'
        assert initial['owner']['read_ts'] == NOW
        clock.advance(200)
        await m._pool_swarm_seat(420, clock())
        assert m.cache.get_last_good(SLOT_SWARM_SEAT).payload['seats']['420']['read_ts'] == NOW
        fresh = m._project_hub()['surf_agent_hero']
        assert fresh['owner']['read_ts'] == NOW + 200 and fresh['owner']['state'] == 'ok'
        assert fresh['rewards']['read_ts'] == initial['rewards']['read_ts']
        swarm.fetch_seat = AsyncMock(return_value=None)
        clock.advance(1)
        await m._pool_swarm_seat(420, clock())
        stale = m._project_hub()['surf_agent_hero']
        assert stale['owner']['state'] == 'stale' and stale['owner']['read_ts'] == NOW + 200
        assert stale['owner']['address'] == initial['owner']['address']
        assert stale['seat']['read_error'] == 'failed'
        assert stale['rewards']['imd'] == initial['rewards']['imd']
    finally:
        await m.close()


async def test_selection_and_restarted_cache_never_borrow_another_seat_confirmation(agent):
    m, clock, _, _ = agent
    try:
        await m._pool_swarm_seat(420, clock())
        m.set_seat(421)
        pending = m._project_hub()['surf_agent_hero']
        assert pending['seat']['token_id'] == 421
        assert pending['owner']['state'] == 'pending' and pending['owner']['address'] is None
        clock.advance(10)
        await m._pool_swarm_seat(421, clock())
        assert m._project_hub()['surf_agent_hero']['owner']['read_ts'] == NOW + 10
        m.set_seat(420)
        assert m._project_hub()['surf_agent_hero']['owner']['read_ts'] == NOW
        m._agent_seat_observations.clear()  # restored payload has no process-local confirmation
        restored = m._project_hub()['surf_agent_hero']
        assert restored['owner']['state'] == 'stale' and restored['owner']['read_ts'] == NOW
    finally:
        await m.close()


async def test_reward_failure_retains_own_value_and_clock_and_sold_seat_loses_it(agent):
    m, clock, _, client = agent
    try:
        await m._pool_swarm_seat(420, clock())
        original = m._project_hub()['surf_agent_hero']['rewards']
        clock.advance(601)
        client.result = None
        await m._pool_swarm_seat(420, clock())
        current = m._project_hub()['surf_agent_hero']['rewards']
        assert current['imd'] == original['imd'] and current['read_ts'] == NOW
        assert current['state'] == 'stale'
        entry = m.cache.get_last_good(SLOT_SWARM_SEAT)
        sold = deepcopy(entry.payload)
        sold['seats']['420']['seat']['owner'] = '0x' + 'ab' * 20
        sold['seats']['420']['read_ts'] = clock()
        m.cache.store_last_good(SLOT_SWARM_SEAT, sold, ts=clock())
        assert m._project_hub()['surf_agent_hero']['rewards']['imd'] is None
    finally:
        await m.close()


async def test_full_cycle_captures_seat_source_before_detached_board_mutation(agent, monkeypatch):
    m, clock, _, _ = agent
    try:
        await m._pool_swarm_seat(420, clock())
        original = m.cache.get_last_good(SLOT_SWARM_SEAT)
        before = m._project_hub()['surf_agent_hero']['owner']
        def replace(*_):
            changed = deepcopy(original.payload)
            changed['seats']['420']['seat']['owner'] = '0x' + 'ab' * 20
            changed['seats']['420']['read_ts'] = clock()
            m.cache.store_last_good(SLOT_SWARM_SEAT, changed, ts=clock())
        monkeypatch.setattr(m, '_spawn_swarm_board', replace)
        data = await m._cycle()
        assert data['surf_agent_hero']['owner'] == before
        after = m._project_hub()['surf_agent_hero']['owner']
        assert after['address'] != before['address'] and after['state'] == 'stale'
    finally:
        await m.close()


@pytest.mark.parametrize('reason', ['failed', 'busy', 'expired', 'restored'])
@pytest.mark.parametrize('width', [134, 149])
async def test_retained_never_paired_result_keeps_its_stale_clock(agent, reason, width, monkeypatch):
    from tests.data.test_surf_manager_swarm import UNKNOWN_SEAT
    from maxpane_dashboard.data.surf_swarm_client import SEAT_BUSY
    from tests.widgets.test_surf_agent_rack_hero import Harness, painted

    async def refuse(*args, **kwargs):
        raise AssertionError('no network in manager/compositor regression')
    monkeypatch.setattr('httpx.AsyncClient.send', refuse)
    monkeypatch.delenv('NO_COLOR', raising=False)
    manager, clock, swarm, _ = agent
    try:
        swarm.fetch_seat = AsyncMock(return_value=dict(UNKNOWN_SEAT))
        await manager._pool_swarm_seat(420, clock())
        assert manager._project_hub()['surf_agent_hero']['seat']['state'] == 'unknown_seat'
        clock.advance(3601)
        if reason in ('failed', 'busy'):
            swarm.fetch_seat = AsyncMock(return_value=None if reason == 'failed' else SEAT_BUSY)
            await manager._pool_swarm_seat(420, clock())
        elif reason == 'restored':
            manager._agent_seat_observations.clear()
        hero = manager._project_hub()['surf_agent_hero']
        assert hero['seat']['token_id'] == 420
        assert hero['seat']['state'] == 'stale_unknown_seat'
        assert hero['seat']['read_ts'] == NOW
        async with Harness(hero).run_test(size=(width, 45)) as pilot:
            await pilot.pause()
            for key in ('seat', 'owner', 'runtime', 'models', 'earnings', 'collab', 'nodes', 'rewards'):
                content = painted(pilot.app, key)
                assert 'never paired' in content, (key, content)
                assert 'stale' not in content, (key, content)
            swarm.fetch_seat = AsyncMock(return_value=dict(UNKNOWN_SEAT))
            await manager._pool_swarm_seat(420, clock())
            fresh = manager._project_hub()['surf_agent_hero']
            pilot.app.query_one('SurfSwarmAgentRackHero').update_data(surf_agent_hero=fresh)
            await pilot.pause()
            assert 'stale' not in painted(pilot.app, 'seat')
            assert 'never paired' in painted(pilot.app, 'seat')
    finally:
        await manager.close()


@pytest.fixture
async def working_agent(agent, monkeypatch):
    from tests.surf_swarm_fixtures import swarm_details_v2
    from maxpane_dashboard.data.surf_cache import TIER_SWARM, TIER_SWARM_BOARD
    manager, clock, swarm, _ = agent
    detail = deepcopy(next(row for row in swarm_details_v2().values() if row['state'] == 'executing'))
    detail['nodes'][0]['seat']['tokenId'] = '420'
    swarm._jobs = [dict(id=detail['id'], state='executing', createdAt=detail['createdAt'])]
    swarm._details = {detail['id']: detail}
    worker = deepcopy(swarm.workers['workers'][0])
    worker.update(working=1, maxConcurrency=2)
    worker['seat']['tokenId'] = '420'
    swarm.workers = dict(count=1, workers=[worker])
    monkeypatch.setattr(manager, '_offer_hub_source', lambda *args: None)
    await manager._pool_swarm({TIER_SWARM}, clock())
    await manager._pool_swarm_board({TIER_SWARM_BOARD}, clock())
    return manager, clock, swarm, detail


async def test_current_action_direct_agent_uses_existing_live_snapshot_and_refreshes(working_agent):
    from maxpane_dashboard.data.surf_cache import TIER_SWARM, TIER_SWARM_BOARD
    manager, clock, swarm, detail = working_agent
    try:
        assert manager._work_reader.task is None
        calls = deepcopy(swarm.calls)
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] == 'oracling'
        assert swarm.calls == calls  # projection performs no new reads
        detail['nodes'][0]['key'] = 'build_contract_project_4'
        clock.advance(10)
        await manager._pool_swarm({TIER_SWARM}, clock())
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] == 'building'
        manager.set_seat(421)
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] is None
        manager.set_seat(420)
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] == 'building'
        # An unchanged complete worker read remains fresh independently.
        swarm.workers['workers'][0]['working'] = 0
        await manager._pool_swarm_board({TIER_SWARM_BOARD}, clock())
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] is None
    finally:
        await manager.close()


@pytest.mark.parametrize('reason', ['failed', 'expired', 'unconfirmed', 'partial_workers', 'failed_workers'])
async def test_current_action_retained_snapshot_cannot_claim_current_work(working_agent, reason):
    from maxpane_dashboard.data.surf_cache import TIER_SWARM, TIER_SWARM_BOARD
    manager, clock, swarm, _ = working_agent
    try:
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] == 'oracling'
        if reason == 'failed':
            swarm._fail = True
            await manager._pool_swarm({TIER_SWARM}, clock())
        elif reason == 'expired':
            clock.advance(61)
        elif reason == 'unconfirmed':
            manager.cache._tier_last_fetch.pop(TIER_SWARM)  # restored cache has no live confirmation
        elif reason == 'partial_workers':
            swarm.workers['count'] += 1
            await manager._pool_swarm_board({TIER_SWARM_BOARD}, clock())
        else:
            swarm.fail_workers = True
            await manager._pool_swarm_board({TIER_SWARM_BOARD}, clock())
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] is None
    finally:
        await manager.close()


async def test_current_action_capture_keeps_payload_with_its_confirmation(working_agent):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM, TIER_SWARM
    manager, clock, _, _ = working_agent
    try:
        data = manager._project_hub()
        capture = manager._agent_hero_capture(None, now=clock())
        board_sources = dict(workers=dict(state='ok', read_ts=clock(), partial=False))
        before = manager._agent_hero(data, capture, board_sources, {}, now=clock())['status']
        replacement = deepcopy(manager.cache.get_last_good(SLOT_SWARM).payload)
        replacement['details'][0]['nodes'][0]['key'] = 'test'
        clock.advance(1)
        manager.cache.store_last_good(SLOT_SWARM, replacement, ts=clock())
        manager.cache.mark_fetched(TIER_SWARM, clock())
        assert manager._agent_hero(data, capture, board_sources, {}, now=clock())['status'] == before
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] == 'testing'
        replacement = dict(replacement, details=[])
        manager.cache.store_last_good(SLOT_SWARM, replacement, ts=clock())
        assert manager._project_hub()['surf_agent_hero']['status']['current_action'] is None
    finally:
        await manager.close()
