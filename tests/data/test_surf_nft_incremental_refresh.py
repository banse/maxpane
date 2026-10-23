"""Revision refresh and early publication boundaries; no live transport."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from maxpane_dashboard.data.surf_nft_client import Budget, Page, SourceUnavailable, SurfNftClient
from maxpane_dashboard.data.surf_nft_discovery import SOURCES, SurfNftDiscovery, empty_discovery_state
from maxpane_dashboard.data.surf_nft_manager import SurfNftManager
from tests.data.test_surf_nft_manager import Cache

FIXTURE = json.loads((Path(__file__).parents[1] / 'fixtures/surf/nft/discovery/public.json').read_text())
NOW = 1792195200.
UPDATED = '2026-10-17T00:00:00Z'


def budget():
    return Budget(monotonic=lambda: 1.)


@pytest.mark.parametrize('name', ['jobs', 'workflows'])
async def test_delta_refresh_reads_old_created_rows_and_retains_observation(name):
    row = dict(FIXTURE['job'], objective='NFT collection', updatedAt=UPDATED)
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index(name)
    state['sources'][name].update(head_at=NOW-301, terminal=True, updated_at=NOW-400,
        reconcile_at=NOW-400, head_ids=['a-previous-head'])
    client = SimpleNamespace(page=AsyncMock(return_value=Page([row], None, True, NOW)),
                             can_read_shared_job=lambda: False)
    reader = SurfNftDiscovery(client=client, swarm=None, clock=lambda: NOW)
    result = await reader.advance(state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    call = client.page.await_args
    assert call.args[0] == name
    assert call.kwargs['since'] == '2026-10-16T23:48:20.000Z'
    assert result.state['sources'][name]['updated_at'] == NOW
    if name == 'jobs':
        assert row['id'] in result.state['pending_jobs']
    else:
        assert result.state['raw']['workflows'][0]['updatedAt'] == UPDATED


async def test_failed_delta_does_not_advance_watermark_or_lose_cursor():
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index('jobs')
    state['sources']['jobs'].update(head_at=NOW-301, terminal=True, updated_at=NOW-400,
        reconcile_at=NOW-400)
    client = SimpleNamespace(page=AsyncMock(side_effect=SourceUnavailable('offline')),
                             can_read_shared_job=lambda: False)
    reader = SurfNftDiscovery(client=client, swarm=None, clock=lambda: NOW)
    result = await reader.advance(state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    source = result.state['sources']['jobs']
    assert source['updated_at'] == NOW-400
    assert source['delta_since'] is not None
    assert source['delta_cursor'] is None
    assert source['terminal'] is True


async def test_launch_reconciliation_passes_previous_head_to_update_old_row():
    old = dict(FIXTURE['launches']['launches'][0], launchNumber=99, updatedAt=UPDATED)
    head = dict(old, id='10000000-0000-4000-8000-000000000099', launchNumber=100)
    state = empty_discovery_state()
    state['sources']['launches'].update(head_at=NOW-301, terminal=True, reconcile_at=NOW-601,
                                        head_ids=[head['id']])
    client = SimpleNamespace(page=AsyncMock(side_effect=[Page([head],100,False,NOW),
                                                        Page([old],99,True,NOW)]),
                             can_read_shared_job=lambda: False)
    reader = SurfNftDiscovery(client=client, swarm=None, clock=lambda: NOW)
    first = await reader.advance(state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert not first.state['sources']['launches']['terminal']
    first.state['rotation'] = 0
    second = await reader.advance(json.loads(json.dumps(first.state)), budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert [c.kwargs['cursor'] for c in client.page.await_args_list] == [None, 100]
    assert old['id'] in {r['id'] for r in second.state['raw']['launches']}
    assert second.state['sources']['launches']['terminal'] is True


async def test_client_forwards_since_and_rejects_old_updates():
    row = dict(FIXTURE['job'], updatedAt=UPDATED)
    seen = []
    def read(request):
        seen.append(request)
        return httpx.Response(200, json={'jobs':[row]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(read)) as http:
        client = SurfNftClient(http_client=http, clock=lambda:NOW, monotonic=lambda:1., inter_call_delay=0)
        result = await client.page('jobs', since=UPDATED, budget=budget())
        assert result.rows == [row]
        assert seen[0].url.params['since'] == UPDATED
        with pytest.raises(SourceUnavailable):
            await client.page('jobs', since='2026-10-18T00:00:00Z', budget=budget())


def test_candidates_reused_until_discovery_identity_changes(monkeypatch):
    import maxpane_dashboard.data.surf_nft_manager as module
    project = Mock(return_value={})
    monkeypatch.setattr(module, 'discovery_candidates', project)
    manager = SurfNftManager(swarm=None, client=SimpleNamespace(), cache=Cache())
    manager._candidates(); manager._candidates()
    assert project.call_count == 1
    manager.state['discovery'] = {'raw': {}}
    manager._candidates()
    assert project.call_count == 2


async def test_selected_result_publishes_before_discovery_tail():
    manager = SurfNftManager(swarm=None, client=SimpleNamespace(), cache=Cache(),
                             clock=lambda:NOW, monotonic=lambda:1.)
    manager._selected = '1:0x'+'1'*40
    candidate = {'id': manager._selected}
    manager._candidates = lambda:{manager._selected:candidate}
    manager._due = lambda _key:True
    manager._focus = lambda *_args, **_kw:None
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def discover(*_args, **_kw):
        nonlocal calls
        calls += 1
        if calls > 1:
            entered.set()
            await release.wait()
    manager._discover = discover
    manager._slice = AsyncMock()
    manager._publish = Mock()
    task = asyncio.create_task(manager._cycle())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert manager._slice.await_count == 1
        assert manager._publish.call_count == 1
    finally:
        release.set()
        await task


async def test_long_delta_retains_scan_start_as_next_overlap_anchor():
    now = [NOW]
    state = empty_discovery_state()
    source = state['sources']['jobs']
    source.update(head_at=NOW-301, terminal=True, updated_at=NOW-400, reconcile_at=NOW-400)
    state['rotation'] = SOURCES.index('jobs')
    first = dict(FIXTURE['job'], updatedAt=UPDATED, objective='NFT collection')
    later = dict(first, id='10000000-0000-4000-8000-000000000099', updatedAt='2026-10-17T00:10:00Z')
    client = SimpleNamespace(page=AsyncMock(side_effect=[Page([first], first['createdAt'], False, NOW),
                                                      Page([later], None, True, NOW+600)]),
                             can_read_shared_job=lambda: False)
    reader = SurfNftDiscovery(client=client, swarm=None, clock=lambda:now[0])
    one = await reader.advance(state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    now[0] += 600
    one.state['rotation'] = SOURCES.index('jobs')
    # The active delta must finish before a periodic reconciliation can replace it.
    two = await reader.advance(one.state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert two.state['sources']['jobs']['updated_at'] == NOW
    assert two.state['sources']['jobs']['delta_since'] is None
    assert client.page.await_args.kwargs['cursor'] == first['createdAt']


def test_prepare_and_save_validates_once_and_retains_same_clock(tmp_path, monkeypatch):
    from maxpane_dashboard.data.surf_nft_cache import SurfNftCache
    cache = SurfNftCache(path=tmp_path/'nft.json', clock=lambda:NOW)
    state = cache.empty()
    state['discovery'] = empty_discovery_state()
    state['discovery']['observed_at'] = NOW-60
    coerce = Mock(wraps=cache._coerce)
    monkeypatch.setattr(cache, '_coerce', coerce)
    clean = cache.prepare_and_save(state)
    assert coerce.call_count == 1
    assert clean['discovery']['observed_at'] == NOW-60
    assert json.loads(cache.path.read_text())['discovery']['observed_at'] == NOW-60


async def test_updates_do_not_wait_for_or_rewind_initial_history():
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index('jobs')
    cursor = '2026-10-10T00:00:00Z'
    state['sources']['jobs'].update(head_at=NOW-301, terminal=False, tail_cursor=cursor,
        updated_at=NOW-400, reconcile_at=NOW-400)
    row = dict(FIXTURE['job'], objective='NFT collection', updatedAt=UPDATED)
    client = SimpleNamespace(page=AsyncMock(return_value=Page([row], None, True, NOW)),
                             can_read_shared_job=lambda:False)
    result = await SurfNftDiscovery(client=client, swarm=None, clock=lambda:NOW).advance(
        state, budget=budget(), page_limit=1, detail_limit=0, launch_limit=0)
    assert client.page.await_args.kwargs['since'] is not None
    assert result.state['sources']['jobs']['tail_cursor'] == cursor
    assert result.state['sources']['jobs']['terminal'] is False


@pytest.mark.parametrize('tail_failed', [False, True])
async def test_reconciliation_head_stays_fresh_without_rewinding_history(tail_failed):
    state = empty_discovery_state()
    source = state['sources']['launches']
    old = dict(FIXTURE['launches']['launches'][0], launchNumber=100)
    fresh = dict(old, id='10000000-0000-4000-8000-000000000099', launchNumber=101)
    source.update(head_at=NOW-301, tail_cursor=50, terminal=False, reconciling=True,
                  reconcile_at=NOW-400, head_ids=[old['id']],
                  retry_at=NOW+100 if tail_failed else 0)
    client = SimpleNamespace(page=AsyncMock(return_value=Page([fresh, old], 100, True, NOW)),
                             can_read_shared_job=lambda: False)
    reader = SurfNftDiscovery(client=client, swarm=None, clock=lambda: NOW)
    result = await reader.advance(state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert client.page.await_args.args[0] == 'launches'
    assert client.page.await_args.kwargs['cursor'] is None
    resumed = result.state['sources']['launches']
    assert resumed['tail_cursor'] == 50 and resumed['terminal'] is False
    assert fresh['id'] in {row['id'] for row in result.state['raw']['launches']}
    assert resumed['head_at'] == NOW
    if not tail_failed:
        history_row = dict(old, id='10000000-0000-4000-8000-000000000088', launchNumber=49)
        client.page.return_value = Page([history_row], 49, False, NOW+1)
        result.state['rotation'] = 0
        later = await reader.advance(result.state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
        assert client.page.await_args.kwargs['cursor'] == 50
        assert later.state['sources']['launches']['tail_cursor'] == 49
        assert later.state['sources']['launches']['head_at'] == NOW


@pytest.mark.parametrize('warning', [None, 'timestamp_boundary_tie'])
async def test_history_watermark_only_promotes_after_certified_terminal(warning):
    now = [NOW]
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index('workflows')
    first = dict(FIXTURE['job'], objective='NFT collection', updatedAt=UPDATED)
    old = dict(first, id='10000000-0000-4000-8000-000000000099',
               createdAt='2026-10-09T00:00:00Z', updatedAt='2026-10-16T23:00:00Z')
    client = SimpleNamespace(page=AsyncMock(side_effect=[Page([first], first['createdAt'], False, NOW, warning=warning),
                                                       Page([old], None, True, NOW+1)]),
                             can_read_shared_job=lambda: False)
    reader = SurfNftDiscovery(client=client, swarm=None, clock=lambda: now[0])
    first_result = await reader.advance(state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert first_result.state['sources']['workflows']['updated_at'] is None
    now[0] += 1
    first_result.state['rotation'] = SOURCES.index('workflows')
    result = await reader.advance(json.loads(json.dumps(first_result.state)), budget=budget(), page_limit=1,
                                  launch_limit=0, detail_limit=0)
    assert result.state['sources']['workflows']['updated_at'] == (NOW if warning is None else None)


@pytest.mark.parametrize('since,cursor', [('2026-10-16', None), (UPDATED, '2026-10-16')])
async def test_invalid_optional_delta_progress_restarts_transport_without_losing_facts(since, cursor):
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index('workflows')
    kept = dict(FIXTURE['job'], objective='NFT collection', updatedAt=UPDATED, _observed_at=NOW-60)
    state['raw']['workflows'] = [kept]
    state['sources']['workflows'].update(head_at=NOW-301, terminal=False, tail_cursor='2026-10-10T00:00:00Z',
        updated_at=NOW-400, reconcile_at=NOW-400, delta_since=since, delta_cursor=cursor,
        delta_started=NOW-301, delta_max=NOW-100)
    seen = []
    def read(request):
        seen.append(request)
        return httpx.Response(200, json={'workflows': []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(read)) as http:
        client = SurfNftClient(http_client=http, clock=lambda:NOW, monotonic=lambda:1., inter_call_delay=0)
        result = await SurfNftDiscovery(client=client, swarm=None, clock=lambda:NOW).advance(
            state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert len(seen) == 1
    assert seen[0].url.params['since'] == '2026-10-16T23:48:20.000Z'
    assert 'before' not in seen[0].url.params
    assert result.state['raw']['workflows'][0]['id'] == kept['id']
    assert result.state['raw']['workflows'][0]['_observed_at'] == NOW-60
    assert result.state['sources']['workflows']['tail_cursor'] == '2026-10-10T00:00:00Z'


async def test_cancelled_detail_keeps_completed_discovery_page_and_persists_cursor():
    entered = asyncio.Event()
    row = dict(FIXTURE['launches']['launches'][0], launchNumber=100)
    async def blocked_detail(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()
    client = SimpleNamespace(page=AsyncMock(return_value=Page([row], 100, False, NOW)),
                             detail=blocked_detail, can_read_shared_job=lambda: False)
    cache = Cache()
    manager = SurfNftManager(swarm=None, client=client, cache=cache, clock=lambda:NOW, monotonic=lambda:1.)
    manager._publish = Mock()  # Observe retained source state, independent of rendering/proof.
    task = asyncio.create_task(manager._cycle())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        for state in (manager.state, cache.state):
            discovery = state['discovery']
            assert [fact['id'] for fact in discovery['raw']['launches']] == [row['id']]
            assert discovery['sources']['launches']['tail_cursor'] == 100
            assert discovery['sources']['launches']['terminal'] is False
            assert discovery['raw']['coverage']['complete'] is False
            assert discovery['raw']['launches'][0]['_observed_at'] == NOW
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_history_tail_without_saved_scan_evidence_cannot_certify_baseline():
    state = empty_discovery_state()
    state['rotation'] = SOURCES.index('workflows')
    state['sources']['workflows'].update(head_at=NOW-1, tail_cursor='2026-10-10T00:00:00Z')
    row = dict(FIXTURE['job'], objective='NFT collection', updatedAt=UPDATED)
    client = SimpleNamespace(page=AsyncMock(return_value=Page([row], None, True, NOW)),
                             can_read_shared_job=lambda: False)
    result = await SurfNftDiscovery(client=client, swarm=None, clock=lambda:NOW).advance(
        state, budget=budget(), page_limit=1, launch_limit=0, detail_limit=0)
    assert result.state['sources']['workflows']['updated_at'] is None
    assert result.state['sources']['workflows']['terminal'] is True
