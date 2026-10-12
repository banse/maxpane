"""Selected AGENT snapshots bind their own facts to independent confirmations."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SEAT
from tests.data.test_surf_manager import FakeClock
from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager, _seat_payload_of
from tests.data.test_surf_manager_seat_rewards import _RewardsClient

NOW = 1791806400.0  # after the committed seat's pairing and work timestamps


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
    from maxpane_dashboard.widgets.fmt import hhmm
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
        async with Harness(hero).run_test(size=(width, 45)) as pilot:
            await pilot.pause()
            for key in ('seat', 'owner', 'runtime', 'models', 'feedback', 'collab', 'nodes', 'rewards'):
                content = painted(pilot.app, key)
                assert 'never paired' in content, (key, content)
                assert 'stale' in content and hhmm(NOW) in content, (key, content)
            swarm.fetch_seat = AsyncMock(return_value=dict(UNKNOWN_SEAT))
            await manager._pool_swarm_seat(420, clock())
            fresh = manager._project_hub()['surf_agent_hero']
            pilot.app.query_one('SurfSwarmAgentRackHero').update_data(surf_agent_hero=fresh)
            await pilot.pause()
            assert 'stale' not in painted(pilot.app, 'seat')
            assert 'never paired' in painted(pilot.app, 'seat')
    finally:
        await manager.close()
