"""The live token view borrows only the existing launch evidence tier."""
import asyncio
import copy

import pytest

from tests.data.test_surf_manager_launches import manager, LaunchSwarm, NOW, fixture
from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES


@pytest.mark.asyncio
async def test_source_is_passive_and_explicit_evidence_keeps_cold_catalogue(tmp_path):
    m = manager(tmp_path)
    catalogue = [fixture('launch_737'), fixture('launch_747')]
    try:
        first = m.swarm_tokens_source(catalogue=catalogue)
        assert first['as_of'] is None
        assert {r['launch_number'] for r in first['rows']} == {737, 747}
        assert not m.swarm_client.calls and m._swarm_launches_task is None
        await m.refresh_swarm_token_evidence(catalogue)
        source = m.swarm_tokens_source()
        assert source['as_of'] is None
        assert all(row['verdict']['state'] == 'swarm' for row in source['rows'])
        assert source['pool_ids']
        assert not {'launches', 'sites'} & set(x for x in m.swarm_client.calls if isinstance(x, str))
        assert not any(isinstance(x, tuple) and x[0] == 'site_job' for x in m.swarm_client.calls)
        assert m._swarm_launches_task is None
        assert all(m.cache.is_due(tier, NOW) for tier in ('fast', 'medium', 'slow', TIER_SWARM_LAUNCHES))
        calls = list(m.swarm_client.calls)
        source['rows'].clear()
        assert len(m.swarm_tokens_source()['rows']) == 2
        await m.refresh_swarm_token_evidence(catalogue)
        assert m.swarm_client.calls == calls  # completed checks and detail are retained
        restored = manager(tmp_path)
        try:
            assert all(row['verdict']['state'] == 'swarm'
                       for row in restored.swarm_tokens_source(catalogue=catalogue)['rows'])
        finally:
            await restored.close()
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_newest_head_overrides_catalogue_status_and_pool_input_is_copied(tmp_path):
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCHES
    m = manager(tmp_path)
    old = fixture('launch_737')
    m.cache.store_last_good(SLOT_SWARM_LAUNCHES,
        {'launches': [dict(copy.deepcopy(old), status='abandoned')], 'launches_ts': NOW}, ts=NOW)
    try:
        m.swarm_tokens_source(catalogue=[old])
        old['status'] = 'invalid mutation'
        await m.refresh_swarm_token_evidence([fixture('launch_737')])
        rows = m.swarm_tokens_source()['rows']
        assert rows[0]['status'] == 'abandoned'
        assert rows[0]['production'] is False
        assert not m.swarm_client.calls and m._swarm_launches_task is None
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_token_evidence_is_bounded_and_rejects_nonproduction_ambiguous_rows(tmp_path):
    from uuid import UUID
    m = manager(tmp_path)
    requested = []
    for number in range(1, 7):
        row = fixture('launch_737')
        row.update(id=str(UUID(int=number)), launchNumber=2000 + number)
        requested.append(row)
    unsupported = dict(copy.deepcopy(requested[0]), chainId=11155111)
    abandoned = dict(copy.deepcopy(requested[0]), status='abandoned')
    ambiguous = copy.deepcopy(requested[0])
    ambiguous['artifacts'].append(copy.deepcopy(next(a for a in ambiguous['artifacts'] if a['role'] == 'token')))
    requested = [unsupported, abandoned, ambiguous, *requested]
    async def forbidden(*args, **kwargs):
        pytest.fail('token provenance must not collect K8')
    m._refresh_launch_liquidity = forbidden
    try:
        await m.refresh_swarm_token_evidence(requested)
        reads = [call for call in m.swarm_client.calls if isinstance(call, tuple)]
        assert len(reads) == 3 and all(call[0] == 'detail' for call in reads)
        facts = m._launch_slot('swarm_launch_facts', {'launches': {}})['launches']
        assert len(facts) == 3
        assert all(point['row']['chainId'] == 1 and point.get('checks') is None for point in facts.values())
    finally:
        await m.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['id', 'chainId', 'updatedAt', 'artifact'])
async def test_token_evidence_rejects_foreign_detail_identity(tmp_path, change):
    m = manager(tmp_path)
    row = fixture('launch_737')
    detail = copy.deepcopy(row)
    if change == 'artifact':
        next(a for a in detail['artifacts'] if a['role'] == 'token')['address'] = '0x' + 'f' * 40
    else:
        detail[change] = {'id': fixture('launch_747')['id'], 'chainId': 8453,
                          'updatedAt': '2026-10-10T00:00:00Z'}[change]
    async def wrong(_):
        return detail
    m.swarm_client.fetch_launch = wrong
    try:
        m.swarm_tokens_source(catalogue=[row])
        await m.refresh_swarm_token_evidence([row])
        point = m._launch_slot('swarm_launch_facts', {'launches': {}})['launches'][row['id']]
        assert point.get('detail_version') is None and point.get('checks') is None
        assert m.swarm_tokens_source()['rows'][0]['verdict'] is None
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_token_evidence_discards_superseded_inflight_identity(tmp_path):
    m = manager(tmp_path)
    row = fixture('launch_737')
    started, release = asyncio.Event(), asyncio.Event()
    async def blocked(_):
        started.set()
        await release.wait()
        return copy.deepcopy(row)
    m.swarm_client.fetch_launch = blocked
    try:
        m.swarm_tokens_source(catalogue=[row])
        task = asyncio.create_task(m.refresh_swarm_token_evidence([row]))
        await asyncio.wait_for(started.wait(), .5)
        newer = dict(copy.deepcopy(row), updatedAt='2026-10-10T00:00:00Z')
        next(a for a in newer['artifacts'] if a['role'] == 'token')['address'] = '0x' + 'f' * 40
        m.swarm_tokens_source(catalogue=[newer])
        release.set()
        await task
        source = m.swarm_tokens_source()
        assert source['rows'][0]['verdict'] is None and not source['pool_ids']
        facts = m._launch_slot('swarm_launch_facts', {'launches': {}})['launches']
        assert row['id'] not in facts
    finally:
        release.set()
        await m.close()


@pytest.mark.asyncio
async def test_cancelled_token_evidence_does_not_publish_private_facts(tmp_path):
    m = manager(tmp_path)
    row = fixture('launch_737')
    started = asyncio.Event()
    async def blocked(_):
        started.set()
        await asyncio.Event().wait()
    m.swarm_client.fetch_launch = blocked
    try:
        m.swarm_tokens_source(catalogue=[row])
        task = asyncio.create_task(m.refresh_swarm_token_evidence([row]))
        await asyncio.wait_for(started.wait(), .5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert m.cache.get_last_good('swarm_launch_facts') is None
        assert m.cache.get_last_good('swarm_launches') is None
        assert m.swarm_tokens_source()['rows'][0]['verdict'] is None
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
