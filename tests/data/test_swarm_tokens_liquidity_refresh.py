"""The token evidence path refreshes bounded K8 observations without network."""
import asyncio
import copy

import pytest

from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_FACTS
from tests.analytics.test_surf_launch_liquidity import live_fixture
from tests.data.test_surf_manager_launches import NOW, manager
from tests.data.test_surf_manager_liquidity import responder, seed


@pytest.mark.asyncio
async def test_token_evidence_refreshes_only_three_pools_and_retains_failed_result(tmp_path):
    m = manager(tmp_path)
    _, answers, decimals = seed(m, 6)
    rows = copy.deepcopy(m.swarm_client.rows)
    batches, fail = responder(m, answers, decimals)
    try:
        await m.refresh_swarm_token_evidence(rows)
        points = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        selected = {row['id'] for row in rows[:3]}
        observed = {key for key, point in points.items()
                    if point.get('liquidity', {}).get('read_ts') == NOW}
        assert observed == selected
        assert len(batches) == 1
        assert sum(method == 'eth_call' and params[0]['data'].startswith('0x1e2eaeaf')
                   for method, params in batches[0]) == 9
        assert all(points[key]['liquidity']['paired_amount'] == pytest.approx(4726.591141)
                   for key in selected)
        assert not any(isinstance(call, tuple) for call in m.swarm_client.calls)

        await m.refresh_swarm_token_evidence(rows)
        assert len(batches) == 1, 'fresh pools keep their independent 300-second cadence'
        old = {key: copy.deepcopy(points[key]['liquidity']) for key in selected}
        m._clock.advance(300)
        fail.add(0)
        await m.refresh_swarm_token_evidence(rows)
        points = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches']
        retained = [key for key in selected if points[key]['liquidity']['read_ts'] == NOW]
        assert len(retained) == 1
        assert points[retained[0]]['liquidity'] == old[retained[0]]
        assert points[retained[0]]['liquidity_attempt_ts'] == NOW + 300
        assert len(batches) == 2
        assert all('liquidity' not in points[row['id']] for row in rows[3:])
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_token_evidence_reuses_provenance_receipts_for_liquidity(tmp_path):
    m = manager(tmp_path)
    row, _, answers, decimals = live_fixture(737)
    batches, _ = responder(m, answers, decimals)
    bootstraps = []
    original = m.client.fetch_launch_receipts

    async def receipts(hashes):
        bootstraps.append(hashes)
        return await original(hashes)

    m.client.fetch_launch_receipts = receipts
    try:
        m.swarm_tokens_source(catalogue=[row])
        await m.refresh_swarm_token_evidence([row])
        point = m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload['launches'][row['id']]
        assert point.get('liquidity', {}).get('read_ts') == NOW
        assert point['liquidity']['paired_amount'] == pytest.approx(4726.591141)
        assert len(batches) == 1 and bootstraps == []
        assert m.swarm_tokens_source()['rows'][0]['verdict']['state'] == 'swarm'
    finally:
        await m.close()


@pytest.mark.asyncio
async def test_token_liquidity_result_cannot_replace_a_newer_catalogue_identity(tmp_path):
    m = manager(tmp_path)
    _, answers, decimals = seed(m)
    row = copy.deepcopy(m.swarm_client.rows[0])
    responder(m, answers, decimals)
    original = m.client.fetch_launch_pool_state
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked(calls):
        started.set()
        await release.wait()
        return await original(calls)

    m.client.fetch_launch_pool_state = blocked
    task = None
    try:
        m.swarm_tokens_source(catalogue=[row])
        before = copy.deepcopy(m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload)
        task = asyncio.create_task(m.refresh_swarm_token_evidence([row]))
        await asyncio.wait_for(started.wait(), .5)
        newer = dict(copy.deepcopy(row), updatedAt='2026-10-10T00:00:00Z')
        next(a for a in newer['artifacts'] if a['role'] == 'token')['address'] = '0x' + 'f' * 40
        m.swarm_tokens_source(catalogue=[newer])
        release.set()
        await task
        assert m.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS).payload == before
        source = m.swarm_tokens_source()
        assert source['rows'][0]['verdict'] is None
        assert source['rows'][0]['liquidity'] is None
        assert not source['pool_ids']
    finally:
        release.set()
        if task is not None:
            await task
        await m.close()
