"""Measurement seams exercise real clients/managers; HTTP is fixture-only."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts import measure_surf_loading as measure


async def test_event_order_distinguishes_request_publish_and_paint():
    async def response(request):
        return httpx.Response(200, json={'id': 'fixture'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        trace = measure.Measurement(max_requests=3, deadline=2)
        trace.instrument_http(client)
        await client.get('https://fixture.invalid/jobs/fixture')
        trace.event('slot_publish', slot='fixture')
        trace.projection({'eth_usd': 3000})
        assert [e['kind'] for e in trace.events] == [
            'request_start', 'request_end', 'slot_publish', 'first_useful_snapshot']
        assert trace.summary()['first_paint_ms'] is None
        trace.event('paint')
        assert trace.summary()['first_paint_ms'] is not None
        assert trace.summary()['attempts'] == 1
        assert trace.events[1]['bytes'] > 0


@pytest.mark.parametrize('limit,deadline,reason', [(1, 2, 'request_budget'), (5, .01, 'deadline')])
async def test_attempt_budget_and_deadline_close_every_task(limit, deadline, reason):
    release, entered = asyncio.Event(), asyncio.Event()
    async def response(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        trace = measure.Measurement(max_requests=limit, deadline=deadline)
        trace.instrument_http(client)
        children = []
        async def work():
            children.append(asyncio.create_task(client.get('https://fixture.invalid/a')))
            await entered.wait()
            if limit == 1:
                await client.get('https://fixture.invalid/b')
            await children[0]
        async def close():
            for child in children:
                child.cancel()
            await asyncio.gather(*children, return_exceptions=True)
        result = await trace.run(work(), close)
        assert result['censored'] and result['reason'] == reason
        assert all(task.done() for task in children)
        assert result['attempts'] == 1


def test_censored_sample_is_not_latency_success():
    result = measure.summarize_samples([
        {'censored': True, 'elapsed_ms': 10}, {'censored': False, 'elapsed_ms': 30}])
    assert result == {'n': 2, 'complete_n': 1, 'censored_n': 1,
                      'median_ms': 30, 'range_ms': [30, 30]}
    assert measure.summarize_samples([{'censored': True, 'elapsed_ms': 1}])['median_ms'] is None


async def test_429_stops_before_host_rotation():
    from maxpane_dashboard.data.surf_swarm_client import SwarmClient
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={}))) as http:
        trace = measure.Measurement(max_requests=8, deadline=2)
        trace.instrument_http(http)
        swarm = SwarmClient(http_client=http, inter_call_delay=0)
        result = await trace.run(swarm.fetch_job('fixture'), swarm.close)
        assert result['reason'] == 'http_429' and result['attempts'] == 1


async def test_five_same_job_readers_measure_actual_transport_attempts():
    from maxpane_dashboard.data.surf_swarm_client import SwarmClient
    fixture = json.loads(Path('tests/fixtures/surf/agent_work/f708c332-034f-47b3-b204-318734811863.json').read_text())
    entered, release = asyncio.Event(), asyncio.Event()
    attempts = 0
    async def response(request):
        nonlocal attempts
        attempts += 1
        entered.set()
        await release.wait()
        return httpx.Response(200, json=fixture)
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        trace = measure.Measurement(max_requests=20, deadline=2)
        trace.instrument_http(http)
        swarm = SwarmClient(http_client=http, inter_call_delay=0)
        trace.instrument_async(swarm, 'fetch_job')
        readers = [asyncio.create_task(swarm.fetch_job(fixture['id'])) for _ in range(5)]
        try:
            await asyncio.wait_for(entered.wait(), 1)
            release.set()
            assert all(item['id'] == fixture['id'] for item in await asyncio.gather(*readers))
            assert trace.summary()['attempts'] == attempts
            assert 1 <= attempts <= 5
            assert sum(e['kind'] == 'logical_start' for e in trace.events) == 5
        finally:
            release.set()
            await asyncio.gather(*readers, return_exceptions=True)
            await swarm.close()


async def test_baseline_64_membership_and_earnings_gate_record(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_answers import Answers, work, NOW
    from tests.data.test_surf_manager_swarm import _manager
    from tests.data.test_surf_manager import FakeClock
    from maxpane_dashboard.data.surf_cache import SLOT_SWARM_SEAT
    seat = work(64)
    for row in seat['work']:
        row['nodeKey'] = 'build'
    fake = Answers(seat)
    membership_entered, membership_release = asyncio.Event(), asyncio.Event()
    earnings_entered, earnings_release = asyncio.Event(), asyncio.Event()
    all_membership = asyncio.Event()
    calls = 0
    async def detail(job):
        nonlocal calls
        calls += 1
        if calls == 4:
            membership_entered.set()
        await membership_release.wait()
        if calls == 64:
            all_membership.set()
        return dict(id=job, launch=dict(requested=False, kind=None, id=None, status=None, chainId=None))
    async def earnings(owner):
        earnings_entered.set()
        await earnings_release.wait()
        return []
    monkeypatch.setattr(fake, 'fetch_job', detail)
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW))
    manager.set_agent_active(True)
    manager.set_seat(420)
    monkeypatch.setattr(manager.earnings_client, 'fetch', earnings)
    task = asyncio.create_task(manager._pool_swarm_seat(420, NOW))
    try:
        await asyncio.wait_for(membership_entered.wait(), 1)
        await asyncio.wait_for(earnings_entered.wait(), 1)
        assert calls == 4 and fake.answer_calls == []
        assert manager.cache.get_last_good(SLOT_SWARM_SEAT) is not None
        membership_release.set()
        await asyncio.wait_for(all_membership.wait(), 1)
        assert calls == 64 and fake.answer_calls == [] and not task.done()
        earnings_release.set()
        await asyncio.wait_for(task, 2)
        assert len(fake.answer_calls) == 4
    finally:
        membership_release.set()
        earnings_release.set()
        await asyncio.gather(task, return_exceptions=True)
        await manager.close()


async def test_baseline_chain_and_full_gate_market_and_selected_seat(tmp_path, monkeypatch):
    from tests.data.test_surf_manager_swarm import _manager, _FakeSwarm
    from tests.data.test_surf_manager import FakeClock
    fake = _FakeSwarm()
    manager = _manager(tmp_path, fake, clock=FakeClock(2_000_000_000))
    manager.set_seat(420)
    chain_entered, chain_release, market_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_chain, original_market = manager.client.fetch_chain_state, manager.client.fetch_market
    async def chain():
        chain_entered.set()
        await chain_release.wait()
        return await original_chain()
    async def market(*args, **kwargs):
        market_entered.set()
        return await original_market(*args, **kwargs)
    monkeypatch.setattr(manager.client, 'fetch_chain_state', chain)
    monkeypatch.setattr(manager.client, 'fetch_market', market)
    task = asyncio.create_task(manager.fetch_and_compute())
    try:
        await asyncio.wait_for(chain_entered.wait(), 1)
        assert not market_entered.is_set() and fake.seat_calls == []
        chain_release.set()
        await asyncio.wait_for(task, 2)
        await asyncio.wait_for(market_entered.wait(), 1)
        assert manager._full_task.done()
    finally:
        chain_release.set()
        await asyncio.gather(task, return_exceptions=True)
        await manager.close()


async def test_baseline_a_b_a_cancels_old_seat_and_keeps_exact_hash(tmp_path):
    from copy import deepcopy
    from tests.data.test_surf_manager_answers import Answers, work, NOW, data
    from tests.data.test_surf_manager_swarm import _manager
    from tests.data.test_surf_manager import FakeClock
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_SEAT
    fake = Answers(work(1))
    other = deepcopy(fake.seat)
    other['tokenId'] = '421'
    other['work'][0]['submissionHash'] = 'f'*64
    fake.seats[421] = other
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW))
    fake.seat_gate = asyncio.Event()
    try:
        manager.set_seat(420)
        first = await manager._offer_swarm_seat({TIER_SWARM_SEAT}, 420, None, NOW)
        await asyncio.wait_for(fake.seat_entered.wait(), 1)
        manager.set_seat(421)
        fake.seat_entered.clear()
        second = await manager._offer_swarm_seat({TIER_SWARM_SEAT}, 421, None, NOW)
        await asyncio.wait_for(fake.seat_entered.wait(), 1)
        assert first.cancelled()
        manager.set_seat(420)
        fake.seat_entered.clear()
        third = await manager._offer_swarm_seat({TIER_SWARM_SEAT}, 420, None, NOW)
        await asyncio.wait_for(fake.seat_entered.wait(), 1)
        assert second.cancelled()
        fake.seat_gate.set()
        await asyncio.wait_for(third, 2)
        result = data(manager)
        assert fake.seat_calls == [420, 421, 420]
        assert result['swarm_seat_selected']['token_id'] == 420
        assert result['swarm_seat_work_rows'][0]['submission_hash'] == fake.seat['work'][0]['submissionHash']
    finally:
        fake.seat_gate.set()
        await manager.close()


async def test_warm_popup_and_work_selection_have_no_requests(monkeypatch):
    from tests.screens.test_submission_detail import row_for
    from maxpane_dashboard.screens.surf import SurfScreen
    from maxpane_dashboard.screens.submission_detail import SubmissionDetailScreen
    from maxpane_dashboard.widgets.surf._oracle_answer import can_open_submission
    from tests.widgets.test_surf_work import Harness, payload, node, painted
    from maxpane_dashboard.widgets.surf.work import SurfWorkBody
    from textual.widgets import Tree
    requests = []
    async def refuse(*args, **kwargs):
        requests.append(args)
        raise AssertionError('local selection attempted network')
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)
    row, popups = row_for(), []
    async def push(screen):
        popups.append(screen)
    view = SimpleNamespace(_oracle_answer_rows=[row], app=SimpleNamespace(push_screen=push))
    await SurfScreen._open_record_detail(view, row['job_id'], row['submission_hash'],
                                        can_open_submission, SubmissionDetailScreen)
    assert popups[0].row['submission_hash'] == row['submission_hash']
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        tree = pilot.app.query_one(Tree)
        body = pilot.app.query_one(SurfWorkBody)
        tree.select_node(node(tree, 'job:job-b'))
        await pilot.pause()
        assert body._selected == 'job:job-b'
        assert 'Vault frontend' in painted(pilot.app, '#work-detail')
    assert requests == []


@pytest.mark.parametrize('chain', [8453, 4663])
@pytest.mark.parametrize('status,reason', [(503, 'request_budget'), (429, 'http_429')])
async def test_late_launch_factory_counts_and_stops_before_second_attempt(
        tmp_path, monkeypatch, chain, status, reason):
    from tests.data.test_surf_manager_swarm import _manager, _FakeSwarm
    from maxpane_dashboard.data import surf_manager as manager_mod
    attempts = 0
    async def respond(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        name = 'SwarmBaseClient' if chain == 8453 else 'SwarmRobinhoodClient'
        client_type = getattr(manager_mod, name)
        monkeypatch.setattr(manager_mod, name, lambda: client_type(http_client=http))
        manager = _manager(tmp_path, _FakeSwarm())
        trace = measure.Measurement(max_requests=1, deadline=2)
        trace.instrument_manager(manager)
        async def work():
            late = manager._launch_rpc_client(chain)
            await late._rpc([('eth_chainId', [])])
            await late._rpc([('eth_chainId', [])])
        result = await trace.run(work(), manager.close)
        assert result['attempts'] == attempts == 1
        assert result['censored'] and result['reason'] == reason
        assert manager._closing and not trace.accepting_requests



@pytest.mark.parametrize('factory', ['swarm_tokens_manager', 'portfolio_manager'])
async def test_late_adapter_factories_instrument_before_first_send(tmp_path, monkeypatch, factory):
    from tests.data.test_surf_manager_swarm import _manager, _FakeSwarm
    from maxpane_dashboard.data import swarm_tokens_client, swarm_tokens_market
    from maxpane_dashboard.data import portfolio_balance_client, portfolio_claims_client
    attempts = 0
    async def respond(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        for module, name in ((swarm_tokens_client, 'SwarmTokensClient'),
                             (swarm_tokens_market, 'SwarmTokensMarketClient'),
                             (portfolio_balance_client, 'PortfolioBalanceClient'),
                             (portfolio_claims_client, 'PortfolioClaimsClient')):
            original = getattr(module, name)
            monkeypatch.setattr(module, name, lambda *a, cls=original, **kw: cls(*a, http_client=http, **kw))
        manager = _manager(tmp_path, _FakeSwarm())
        trace = measure.Measurement(max_requests=1, deadline=2)
        trace.instrument_manager(manager)
        async def work():
            adapter = getattr(manager, factory)()
            client = adapter.client if factory == 'swarm_tokens_manager' else adapter.claims
            await client._client.get('https://fixture.invalid/late-adapter')
            await client._client.get('https://fixture.invalid/late-adapter')
        result = await trace.run(work(), manager.close)
        assert result['attempts'] == attempts == 1
        assert result['reason'] == 'http_429' and result['censored']
