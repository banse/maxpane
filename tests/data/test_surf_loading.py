"""Loading observes owned asynchronous work; passive repaint never offers reads."""
import asyncio
from copy import deepcopy

import pytest

from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager
from tests.data.test_swarm_token_detail import Overview
from tests.data.test_swarm_tokens_live import Market, Pages, Source, rows


class NoNetwork:
    async def close(self):
        pass

    def __getattr__(self, name):
        if name.startswith('fetch_'):
            raise AssertionError(f'unexpected network offer: {name}')
        raise AttributeError(name)


@pytest.fixture
def surf(tmp_path):
    client = NoNetwork()
    return SurfManager(client=client, pool4_client=client, swarm_client=client,
                       npm_client=client, earnings_client=client,
                       cache_path=tmp_path / 'surf.json', clock=lambda: 1000)


@pytest.mark.parametrize('field,yes,no', [
    ('_full_task', 'dashboard', 'work'),
    ('_launchpad_task', 'launchpad', 'agent'),
    ('_pool4_task', 'pool4', 'board'),
    ('_pool4_stakers_task', 'pool4_user', 'swarm'),
    ('_swarm_task', 'swarm', 'pool4_user'),
    ('_swarm_scores_task', 'swarm', 'launchpad'),
    ('_swarm_board_task', 'board', 'pool4'),
    ('_swarm_launches_task', 'swarm', 'pool4'),
    ('_swarm_seat_task', 'agent', 'board'),
    ('_runtime_task', 'agent', 'dashboard'),
])
async def test_surf_loading_tracks_relevant_real_tasks_and_cancellation(surf, field, yes, no):
    task = asyncio.create_task(asyncio.Event().wait())
    setattr(surf, field, task)
    try:
        assert surf.is_loading(yes)
        assert surf.is_loading()
        assert not surf.is_loading(no)
        task.cancel()
        # Cancellation has been requested, but the task has not settled yet.
        assert not task.done()
        assert not surf.is_loading(yes)
        await asyncio.gather(task, return_exceptions=True)
        assert not surf.is_loading()
    finally:
        await surf.close()


@pytest.mark.parametrize('reader,view', [
    ('_work_reader', 'work'), ('_oracles_reader', 'oracles'),
    ('_launch_contribution_reader', 'board'),
])
async def test_surf_detached_readers_stay_loading_until_completion(surf, reader, view):
    release = asyncio.Event()
    task = asyncio.create_task(release.wait())
    getattr(surf, reader).task = task
    try:
        assert surf.is_loading(view)
        assert not surf.is_loading('pool4')
        release.set()
        await task
        assert not surf.is_loading(view)
    finally:
        await surf.close()


async def test_boardroom_observes_shared_sources_and_token_reads_only_when_relevant(surf):
    tokens = SwarmTokensManager(Source(), client=Pages(), market=Market(), clock=lambda: 1000)
    surf._swarm_tokens_manager = tokens
    task = asyncio.create_task(asyncio.Event().wait())
    try:
        surf._hub_source_tasks['records'] = task
        assert surf.is_loading('agent') and surf.is_loading('board')
        assert surf.is_loading('surfboard')
        assert not surf.is_loading('pool4')
        surf._hub_source_tasks.clear()
        tokens._tasks['history'] = task
        assert tokens.is_loading()
        assert not surf.is_loading('surfboard')
        tokens._tasks['volume'] = task
        assert surf.is_loading('surfboard')
        task.cancel()
        assert not surf.is_loading('surfboard')
    finally:
        await surf.close()


async def test_loading_ignores_source_failures_without_tasks(surf):
    detail = SwarmTokenDetailManager(Overview(), Overview().token, clock=lambda: 1000)
    try:
        assert not surf.is_loading()
        assert not detail.is_loading()  # sources begin pending, but nothing was offered
        detail._sources['launch']['state'] = 'unavailable'
        assert not detail.is_loading()
    finally:
        await detail.close()
        await surf.close()


async def test_token_loading_scopes_accepted_batches_and_passive_snapshot_preserves_data():
    entered, release = asyncio.Event(), asyncio.Event()

    class HeldMarket(Market):
        async def fetch_markets(self, tokens):
            entered.set()
            await release.wait()
            return {row['id']: dict(state='ok', price_usd=7.5,
                                   market_pool='pool', market_source='fixture') for row in tokens}

    manager = SwarmTokensManager(Source(), client=Pages(rows()[:3]),
                                 market=HeldMarket(), clock=lambda: 1000)
    try:
        manager._catalogue = rows()[:3]
        manager._complete, manager._cat_as_of, manager._cat_attempt = True, 1000, 1000
        before = manager.get_snapshot()
        assert before['tokens'] and not manager._tasks
        selected = before['tokens'][0]
        await manager.fetch_selected_token(selected['id'], launch_uuid=selected['launch_uuid'])
        assert manager.is_loading(token_id=selected['id'])
        assert not manager.is_loading(token_id='other-token')
        await entered.wait()
        release.set()
        await manager.wait_pending()
        assert not manager.is_loading()
        after = manager.get_selected_token(selected['id'], launch_uuid=selected['launch_uuid'])
        assert after['price_usd'] == 7.5
        tasks = dict(manager._tasks)
        assert manager.get_snapshot()['tokens'][0]['price_usd'] == 7.5
        assert manager._tasks == tasks
        assert manager.get_selected_token(selected['id'], launch_uuid='different-launch') is None
    finally:
        await manager.close()


async def test_token_loading_accepted_batch_is_not_overwritten_by_skipped_offer():
    manager = SwarmTokensManager(Source(), client=Pages(), market=Market(), clock=lambda: 1000)
    release = asyncio.Event()
    try:
        manager._start('markets', release.wait(), token_ids=['first'])
        manager._start('markets', release.wait(), token_ids=['second'])
        assert manager.is_loading(token_id='first')
        assert not manager.is_loading(token_id='second')
        manager._tasks['markets'].cancel()
        assert not manager.is_loading(token_id='first')
    finally:
        await manager.close()


async def test_detail_loading_uses_own_task_and_only_selected_overview_work():
    overview = Overview()
    seen = []
    overview.is_loading = lambda view=None, *, token_id=None: seen.append(token_id) or token_id == overview.token['id']
    detail = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    try:
        assert detail.is_loading()
        assert seen == [overview.token['id']]
        overview.is_loading = lambda *a, **kw: False
        detail._task = asyncio.create_task(asyncio.Event().wait())
        assert detail.is_loading()
        detail._task.cancel()
        assert not detail.is_loading()
        await detail.close()
        overview.is_loading = lambda *a, **kw: True
        assert not detail.is_loading()
    finally:
        await detail.close()


async def test_detail_passive_snapshot_updates_borrowed_values_without_fetching():
    overview = Overview()
    detail = SwarmTokenDetailManager(overview, overview.token, clock=lambda: 1000)
    selected_calls = []
    overview.get_selected_token = lambda identity, *, launch_uuid=None: (
        selected_calls.append((identity, launch_uuid)) or deepcopy(overview.token))
    try:
        first = detail.get_snapshot()
        assert first['launch'] is None and detail._task is None
        overview.token['price_usd'] = 9.0
        second = detail.get_snapshot()
        assert second['token']['price_usd'] == 9.0
        assert not overview.selected_calls and detail._task is None
        assert len(selected_calls) == 2
        second['token']['price_usd'] = 99
        assert detail.get_snapshot()['token']['price_usd'] == 9.0
        overview.token['id'] = 'wrong-token'
        assert detail.get_snapshot()['token']['price_usd'] == 9.0
    finally:
        await detail.close()


async def test_surf_passive_snapshot_is_existing_hub_projection(surf, monkeypatch):
    expected = {'cached': 1}
    monkeypatch.setattr(surf, 'get_hub_snapshot', lambda: expected)
    try:
        assert surf.get_snapshot() is expected
        assert surf._full_task is None and not surf._hub_source_tasks
    finally:
        await surf.close()
