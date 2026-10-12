"""Independent BOARD read clocks, including unchanged and interleaved reads."""
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_CONTRIBUTORS, SLOT_SWARM_WORKERS, TIER_SWARM_BOARD
from tests.data.test_surf_manager_surfboard import manager
from tests.surf_swarm_fixtures import swarm_capture_v3


def readers(m):
    m.swarm_client.fetch_contributors = AsyncMock(return_value=swarm_capture_v3('contributors'))
    m.swarm_client.fetch_workers = AsyncMock(return_value=swarm_capture_v3('workers'))


@pytest.mark.parametrize('failed,healthy', [('workers', 'effort'), ('contributors', 'workers')])
async def test_confirmed_unchanged_reads_and_failures_keep_independent_clocks(manager, failed, healthy):
    m, clock = manager
    readers(m)
    try:
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        initial = m._project_hub()['surf_leaderboard_hero']
        assert all(initial[key]['state'] == 'ok' for key in ('top', 'recorded', 'rate', 'outcomes', 'workers', 'effort'))
        clock.now = 1050
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        for slot in (SLOT_SWARM_CONTRIBUTORS, SLOT_SWARM_WORKERS):
            assert m.cache.get_last_good(slot).ts == 1000  # version unchanged
        assert m._project_hub()['surf_leaderboard_hero'][healthy]['read_ts'] == 1050
        clock.now = 1100
        getattr(m.swarm_client, f'fetch_{failed}').return_value = None
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        result = m._project_hub()['surf_leaderboard_hero']
        failed_card = 'effort' if failed == 'contributors' else 'workers'
        assert result[failed_card]['state'] == 'stale' and result[failed_card]['read_ts'] == 1050
        assert result[healthy]['state'] == 'ok' and result[healthy]['read_ts'] == 1100
        for field, value in initial[failed_card].items():
            if field not in ('state', 'read_ts'):
                assert result[failed_card][field] == value
        clock.now = 1221
        assert m._project_hub()['surf_leaderboard_hero'][healthy]['state'] == 'stale'
        clock.now = 1230
        getattr(m.swarm_client, f'fetch_{failed}').return_value = swarm_capture_v3(failed)
        await m._pool_swarm_board({TIER_SWARM_BOARD}, clock.now)
        recovered = m._project_hub()['surf_leaderboard_hero'][failed_card]
        assert recovered['state'] == 'ok' and recovered['read_ts'] == 1230
    finally:
        await m.close()


async def test_restored_values_are_dated_until_confirmed_and_partial_workers_keep_only_served_total(manager):
    m, _ = manager
    workers = sw.normalize_workers(swarm_capture_v3('workers'))
    m.cache.store_last_good(SLOT_SWARM_WORKERS, dict(workers, count=999), ts=999)
    try:
        result = m._project_hub()['surf_leaderboard_hero']
        assert result['workers'] == dict(state='stale', read_ts=999, live=999, working=None, capacity=None)
        assert result['effort']['state'] == 'unavailable'
        m._cycle.assert_not_awaited()
    finally:
        await m.close()


async def test_cycle_captures_matching_board_values_and_clocks_before_detached_read(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, FakeClock
    m = _manager(tmp_path, clock=FakeClock(1000))
    readers(m)
    try:
        await m._pool_swarm_board({TIER_SWARM_BOARD}, 1000)
        original = m._project_hub()['surf_leaderboard_hero']

        def replace_board(*args):
            prior = m.cache.get_last_good(SLOT_SWARM_WORKERS)
            m.cache.store_last_good(SLOT_SWARM_WORKERS, dict(prior.payload, count=999), ts=1000)
            m._swarm_board_observations[SLOT_SWARM_WORKERS] = dict(
                entry=m.cache.get_last_good(SLOT_SWARM_WORKERS), read_ts=1000, failed=False)

        monkeypatch.setattr(m, '_spawn_swarm_board', replace_board)
        result = await m._cycle()
        assert result['surf_leaderboard_hero']['workers'] == original['workers']
        assert result['surf_leaderboard_hero']['effort'] == original['effort']
        fresh = m._project_hub()['surf_leaderboard_hero']['workers']
        assert fresh['live'] == 999 and fresh['working'] is None and fresh['state'] == 'partial'
    finally:
        await m.close()


async def test_board_read_completed_during_chain_await_is_not_future(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_pool4 import _manager, FakeClock
    clock = FakeClock(1000)
    m = _manager(tmp_path, clock=clock)
    readers(m)
    original = m._pool_chain

    async def finish_board_during_chain(now):
        clock.advance(5)
        await m._pool_swarm_board({TIER_SWARM_BOARD}, now)
        return await original(now)

    monkeypatch.setattr(m, '_pool_chain', finish_board_during_chain)
    try:
        result = await m._cycle()
        assert result['swarm_board_summary']['live'] is not None
        assert result['swarm_board_summary']['receipts'] is not None
        for key in ('workers', 'effort'):
            card = result['surf_leaderboard_hero'][key]
            assert card['state'] == 'ok'
            assert card['read_ts'] == 1005
    finally:
        await m.close()
