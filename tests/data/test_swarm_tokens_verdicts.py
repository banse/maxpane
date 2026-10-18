"""The token board owns bounded provenance reads; passive snapshots own none."""
import asyncio
from copy import deepcopy
import threading
from uuid import UUID

import pytest

from maxpane_dashboard.data.reader import ReaderRuntime
from maxpane_dashboard.data.surf_swarm import launch_rows
from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
from tests.data.test_reader import eventually
from tests.data.test_swarm_tokens_live import Market, Pages, Source, rows


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError('unexpected network request')
    monkeypatch.setattr('httpx.AsyncHTTPTransport.handle_async_request', refuse)


def catalogue(count=1):
    template = rows()[0]
    result = []
    for number in range(count, 0, -1):
        row = deepcopy(template)
        row.update(id=str(UUID(int=number)), launchNumber=2000 + number)
        for artifact in row['artifacts']:
            if artifact['role'] == 'token':
                artifact['address'] = '0x' + f'{number:040x}'
        result.append(row)
    return result


class Evidence(Source):
    def __init__(self, *, blocked=False, fail=False):
        super().__init__([])
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.fail = fail
        if not blocked:
            self.release.set()

    async def refresh_swarm_token_evidence(self, requested):
        self.calls.append(deepcopy(requested))
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        if self.fail:
            raise RuntimeError('temporary evidence outage')
        indexed = {row['launch_id']: row for row in self.data['rows']}
        for row in launch_rows(requested):
            token = next(a for a in row['artifacts'] if a['role'] == 'token')
            row.update(token_address=token['address'], verdict={'state': 'swarm'})
            indexed[row['launch_id']] = row
        self.data['rows'] = list(indexed.values())


def adapter(source, data, now=None):
    now = now or [1000.]
    manager = SwarmTokensManager(source, client=Pages(data), market=Market(), clock=lambda: now[0])
    manager.set_active_view('SWARM TOKENS')
    return manager


async def test_cold_catalogue_starts_verification_without_another_poll():
    source = Evidence(blocked=True)
    manager = adapter(source, catalogue())
    try:
        first = await asyncio.wait_for(manager.fetch_and_compute(), .2)
        assert not first['tokens']
        await asyncio.wait_for(source.started.wait(), .5)
        assert manager.is_loading()
        assert manager.get_snapshot()['tokens'][0]['verdict'] == 'unknown'
        for _ in range(3):
            await manager.fetch_and_compute()
            manager.get_snapshot()
        assert len(source.calls) == 1
        source.release.set()
        await manager.wait_pending()
        assert manager.get_snapshot()['tokens'][0]['verdict'] == 'swarm'
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert len(source.calls) == 1
    finally:
        source.release.set()
        await manager.close()
    assert not source.closed


@pytest.mark.parametrize('view', [None, 'surfboard', 'board', 'portfolio', 'token:one'])
async def test_hidden_and_other_views_never_start_token_verification(view):
    source = Evidence()
    manager = adapter(source, catalogue())
    manager.set_active_view(view)
    try:
        await manager.fetch_and_compute()
        manager.offer_hub_markets()
        manager.offer_hub_volume()
        await manager.wait_pending()
        manager.get_snapshot()
        manager.get_portfolio_snapshot()
        assert source.calls == []
    finally:
        await manager.close()


async def test_failed_batch_does_not_starve_unattempted_launches_or_retry_immediately():
    source, now = Evidence(fail=True), [1000.]
    data = catalogue(7)
    manager = adapter(source, data, now)
    try:
        await manager.fetch_and_compute()
        await manager.wait_pending()
        await manager.wait_pending()
        assert [r['launchNumber'] for r in source.calls[0]] == [2007, 2006, 2005]
        now[0] += 30
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert [r['launchNumber'] for r in source.calls[1]] == [2004, 2003, 2002]
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert [r['launchNumber'] for r in source.calls[2]] == [2001]
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert len(source.calls) == 3
        assert all(r['verdict'] == 'unknown' for r in manager.get_snapshot()['tokens'])
        now[0] += 30
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert [r['launchNumber'] for r in source.calls[3]] == [2007, 2006, 2005]
    finally:
        await manager.close()


async def test_new_catalogue_revision_does_not_accept_inflight_old_verdict():
    source = Evidence(blocked=True)
    manager = adapter(source, catalogue())
    try:
        await manager.fetch_and_compute()
        await asyncio.wait_for(source.started.wait(), .5)
        manager._catalogue[0]['updatedAt'] = '2026-10-18T04:00:00.000Z'
        source.release.set()
        await manager.wait_pending()
        assert manager.get_snapshot()['tokens'][0]['verdict'] == 'unknown'
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert len(source.calls) == 2
        assert source.calls[1][0]['updatedAt'] == '2026-10-18T04:00:00.000Z'
        assert manager.get_snapshot()['tokens'][0]['verdict'] == 'swarm'
    finally:
        source.release.set()
        await manager.close()


async def test_leaving_cancels_evidence_and_reentry_retries_missing_verdict():
    source = Evidence(blocked=True)
    manager = adapter(source, catalogue())
    try:
        await manager.fetch_and_compute()
        await asyncio.wait_for(source.started.wait(), .5)
        manager.set_active_view(None)
        await asyncio.wait_for(manager.drain_reads(), .5)
        assert source.cancelled.is_set() and not manager.is_loading()
        assert manager.get_snapshot()['tokens'][0]['verdict'] == 'unknown'
        source.release.set()
        manager.set_active_view('SWARM TOKENS')
        await manager.fetch_and_compute()
        await manager.wait_pending()
        assert len(source.calls) == 2
        assert manager.get_snapshot()['tokens'][0]['verdict'] == 'swarm'
    finally:
        source.release.set()
        await manager.close()


async def test_reader_publishes_completed_verdict_without_ui_refresh():
    started, release = threading.Event(), threading.Event()
    owner = []
    class ThreadEvidence(Evidence):
        async def refresh_swarm_token_evidence(self, requested):
            owner.append(threading.get_ident())
            started.set()
            while not release.is_set():
                await asyncio.sleep(.001)
            await super().refresh_swarm_token_evidence(requested)

    runtime = ReaderRuntime(poll_interval=60, publish_interval=.01)
    handle = runtime.register('tokens', lambda: adapter(ThreadEvidence(), catalogue()))
    try:
        handle.set_active_view('SWARM TOKENS')
        await eventually(started.is_set)
        await eventually(lambda: bool((handle.get_snapshot() or {}).get('tokens')))
        assert handle.get_snapshot()['tokens'][0]['verdict'] == 'unknown'
        assert handle.is_loading()
        release.set()
        await eventually(lambda: handle.get_snapshot()['tokens'][0]['verdict'] == 'swarm')
        assert owner == [runtime.thread.ident] and owner[0] != threading.get_ident()
    finally:
        release.set()
        await runtime.close()


async def test_real_tokens_gain_fixture_verdict_while_parent_remains_inactive(tmp_path, monkeypatch):
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES
    from tests.data.test_surf_manager_launches import LaunchSwarm, NOW, fixture, manager as surf

    swarm, data = LaunchSwarm(), [fixture('launch_737')]
    parent = surf(tmp_path, swarm)
    parent.set_active_view(None)
    async def unrelated(*args, **kwargs):
        pytest.fail('token provenance started an unrelated parent collector')
    monkeypatch.setattr(parent, '_pool_swarm_launches', unrelated)
    monkeypatch.setattr(parent.client, 'fetch_launch_pool_state', unrelated)
    token_manager = adapter(parent, data, [NOW])
    try:
        await token_manager.fetch_and_compute()
        await token_manager.wait_pending()
        await token_manager.wait_pending()
        row = token_manager.get_snapshot()['tokens'][0]
        assert row['verdict'] == 'swarm' and row['symbol'] == 'ZTO'
        assert parent._active_view is None and parent._swarm_launches_task is None
        assert parent.cache.is_due(TIER_SWARM_LAUNCHES, NOW)
        assert not {'launches', 'sites'} & set(c for c in swarm.calls if isinstance(c, str))
        assert not any(isinstance(c, tuple) and c[0] == 'site_job' for c in swarm.calls)
        assert parent.swarm_tokens_source()['as_of'] is None
    finally:
        await token_manager.close()
        await parent.close()


@pytest.mark.parametrize('same_pool', [True, False])
async def test_new_verified_pool_retains_only_matching_market_quote_with_original_clock(same_pool):
    source, data = Evidence(), catalogue()
    manager = adapter(source, data)
    manager._catalogue = deepcopy(data)
    pool = '0x' + 'a' * 64
    token = manager.get_snapshot()['tokens'][0]
    manager._market[token['id']] = ({'_expected_pool': None, 'state': 'ok',
        'market_pool': pool if same_pool else '0x' + 'b' * 64,
        'price_usd': 2.5, 'volume_24h': 42}, 990)
    try:
        assert manager.get_snapshot()['tokens'][0]['price_usd'] == 2.5
        await source.refresh_swarm_token_evidence(data)
        source.data['pool_ids'][data[0]['id']] = pool
        verified = manager.get_snapshot()['tokens'][0]
        assert verified['verdict'] == 'swarm'
        assert verified['price_usd'] == (2.5 if same_pool else None)
        assert verified['volume_24h'] == (42 if same_pool else None)
        assert verified['market_read_at'] == (990 if same_pool else None)
    finally:
        await manager.close()
