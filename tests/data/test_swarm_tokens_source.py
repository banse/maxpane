"""The live token view borrows only the existing launch evidence tier."""
import asyncio
import copy

import pytest

from tests.data.test_surf_manager_launches import manager, LaunchSwarm, NOW, fixture
from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES


@pytest.mark.asyncio
async def test_source_is_nonblocking_singleflight_and_keeps_catalogue_history(tmp_path):
    swarm = LaunchSwarm()
    swarm.rows = [fixture('launch_737')]
    m = manager(tmp_path, swarm)
    gate = asyncio.Event()
    original = swarm.fetch_launches

    async def blocked():
        await gate.wait()
        return await original()

    swarm.fetch_launches = blocked
    try:
        older = fixture('launch_734')
        first = m.swarm_tokens_source(catalogue=[older])
        assert first['rows'] is None and first['as_of'] is None
        task = m._swarm_launches_task
        m.swarm_tokens_source()
        assert m._swarm_launches_task is task and not task.done()
        gate.set()
        await task
        source = m.swarm_tokens_source()
        assert source['as_of'] == NOW
        assert {r['launch_number'] for r in source['rows']} == {734, 737}
        assert source['pool_ids']
        assert swarm.calls.count('launches') == 1
        source['rows'].clear()
        assert len(m.swarm_tokens_source()['rows']) == 2
        assert all(m.cache.is_due(tier, NOW) for tier in ('fast', 'medium', 'slow'))
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_newest_head_overrides_catalogue_status_and_pool_input_is_copied(tmp_path):
    swarm = LaunchSwarm()
    old = fixture('launch_737')
    swarm.rows = [dict(copy.deepcopy(old), status='abandoned')]
    m = manager(tmp_path, swarm)
    try:
        m.swarm_tokens_source(catalogue=[old])
        old['status'] = 'invalid mutation'
        await m._swarm_launches_task
        rows = m.swarm_tokens_source()['rows']
        assert rows[0]['status'] == 'abandoned'
        assert rows[0]['production'] is False
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_failed_head_cannot_replace_newer_catalogue_version(tmp_path):
    swarm = LaunchSwarm()
    row = fixture('launch_737')
    swarm.rows = [row]
    m = manager(tmp_path, swarm)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        newer = dict(copy.deepcopy(row), status='abandoned', updatedAt='2026-10-10T00:00:00.000Z')
        swarm.fail.add('launches')
        m.swarm_tokens_source(catalogue=[newer])
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW+61)
        facts = m._launch_slot('swarm_launch_facts', {'launches':{}})
        assert row['id'] not in facts['launches']
    finally:
        await m.close()


@pytest.mark.parametrize('detail_succeeds', [False, True])
async def test_revision_withholds_old_metadata_pool_and_balances(tmp_path, detail_succeeds):
    from maxpane_dashboard.analytics.surf_launch_liquidity import empty_liquidity
    from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
    from tests.data.test_swarm_tokens_live import Pages, Market

    swarm = LaunchSwarm()
    original = fixture('launch_737')
    swarm.rows = [copy.deepcopy(original)]
    m = manager(tmp_path, swarm)
    adapter = SwarmTokensManager(m, client=Pages([]), market=Market(), clock=lambda:NOW)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        point = m.cache.get_last_good('swarm_launch_facts').payload['launches'][original['id']]
        point['liquidity'] = dict(empty_liquidity('info'), paired_amount=123, token_amount=456,
                                 paired_symbol='IMD', read_ts=NOW)
        changed = copy.deepcopy(original)
        changed['updatedAt'] = '2026-10-10T00:00:00.000Z'
        for artifact in changed['artifacts']:
            if artifact['role'] == 'token':
                artifact.update(address='0x'+'f'*40, name='NewToken')
        swarm.rows = [changed]
        # A cached row/detail mismatch must already be safe before the next read.
        point['row'] = copy.deepcopy(changed)
        source = m.swarm_tokens_source()
        assert original['id'] not in source['pool_ids']
        adapter._catalogue = [changed]
        tokens = adapter._tokens(source, NOW)
        assert tokens[0]['symbol'] != 'ZTO' and tokens[0]['paired_amount'] is None
        async def detail(_):
            return copy.deepcopy(changed) if detail_succeeds else None
        swarm.fetch_launch = detail
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, NOW)
        source = m.swarm_tokens_source()
        tokens = adapter._tokens(source, NOW)
        assert tokens[0]['token_address'] == '0x'+'f'*40
        assert tokens[0]['paired_amount'] is None and tokens[0]['lp_state'] == 'unknown'
        assert original['id'] not in source['pool_ids']
        point = m._launch_slot('swarm_launch_facts', {'launches':{}})['launches'][original['id']]
        assert 'pool_initialize' not in point
    finally:
        await adapter.close()
        await m.close()
