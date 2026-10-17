"""Finite RECORD revalidation against real, network-dead detail memo reads."""
import copy
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data import surf_agent_card_sources as sources
from maxpane_dashboard.data.surf_cache import (
    SLOT_AGENT_WORK, SLOT_SWARM_ANSWERS, SLOT_SWARM_JOB_DETAIL,
    SLOT_SWARM_SCORES, SLOT_SWARM_LAUNCH_FACTS, SurfCache,
    TIER_SWARM_SCORES, TIER_SWARM_LAUNCHES,
)
from maxpane_dashboard.data.surf_swarm_client import SwarmClient
from tests.data.test_surf_manager import FakeClock
from tests.data.test_surf_manager_answers import Answers, NOW, work
from tests.data.test_surf_manager_swarm import _manager


@asynccontextmanager
async def memo(clock, handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = SwarmClient(http_client=http, hosts=('https://one.test',),
                             inter_call_delay=0, clock=clock, monotonic=clock)
        try:
            yield client
        finally:
            await client.close()


def popup_seat(count=1):
    seat = work(count, 'completed')
    for row in seat['work']:
        row['nodeKey'] = 'hunt_d'
    return seat


def popup_body(job, nodes=True):
    return dict(id=job, state='completed', nodes=[dict(key='hunt_d', role='review',
                state='accepted', attempt=1)] if nodes else [])


async def test_late_terminal_publication_is_revalidated(tmp_path):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    job = fake.seat['work'][0]['jobId']
    body, calls = popup_body(job), []
    def handler(request):
        assert request.url.path == '/jobs/' + job
        calls.append(request)
        return httpx.Response(200, json=body)
    async with memo(clock, handler) as client:
        fake.fetch_job, fake.read_job_detail = client.fetch_job, client.read_job_detail
        fake._monotonic = client._monotonic
        manager = _manager(tmp_path, fake, clock=clock)
        try:
            await manager._pool_swarm_answers(fake.seat, 420, clock())
            await manager._pool_swarm_job_details(fake.seat, clock())
            body['nodes'].append(dict(key='late_node', role='review', state='accepted', attempt=1))
            clock.advance(599)
            await manager._pool_swarm_job_details(fake.seat, clock())
            assert len(calls) == 1
            clock.advance(1)
            await manager._pool_swarm_job_details(fake.seat, clock())
            point = manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL).payload[job]
            assert len(calls) == 2
            assert [node['key'] for node in point['nodes']] == ['hunt_d', 'late_node']
            assert point['read_ts'] == NOW + 600
        finally:
            await manager.close()


@pytest.mark.parametrize('kind', ['missing', 'empty', 'no_reply', 'incomplete'])
async def test_incomplete_empty_and_no_reply_retry_after_120s(tmp_path, kind):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    row = fake.seat['work'][0]
    job, key = row['jobId'], row['submissionHash']
    original = copy.deepcopy(fake.responses[job])
    if kind == 'missing':
        fake.responses[job] = None
    elif kind == 'empty':
        fake.responses[job]['submissions'] = []
    elif kind == 'no_reply':
        fake.responses[job]['submissions'][0]['summary'] = ''
    else:
        fake.responses[job]['complete'] = False
    manager = _manager(tmp_path, fake, clock=clock)
    try:
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        fake.responses[job] = original
        clock.advance(119)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 1
        clock.advance(1)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 2
        point = manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload[job][key]
        assert point['state'] == 'read' and point['read_ts'] == NOW + 120
    finally:
        await manager.close()


async def test_cached_membership_keeps_original_observed_at(tmp_path):
    clock = FakeClock(NOW - 60)
    job = 'f708c332-034f-47b3-b204-318734811863'
    body = json.loads(Path('tests/fixtures/surf/agent_work', job + '.json').read_text())
    calls = []
    def handler(request):
        assert request.url.path == '/jobs/' + job
        calls.append(request)
        return httpx.Response(200, json=body)
    async with memo(clock, handler) as client:
        await client.read_job_detail(job)
        clock.advance(60)
        cache = SurfCache(path=str(tmp_path/'membership.json'), clock=clock)
        reader = sources.AgentCardSources(cache, None, client, clock=clock)
        seat = dict(work=[dict(jobId=job, nodeKey='audit_economics', status='accepted')])
        await reader.read(seat, clock())
        point = cache.get_last_good(SLOT_AGENT_WORK).payload[job]
        assert len(calls) == 1
        assert point == dict(launched=True, read_ts=NOW-60)
        assert sources.project(reader.capture(NOW), seat, now=NOW)[1]['agent_work']['read_ts'] == NOW-60


async def test_incomplete_terminal_detail_forces_read_before_memo_ttl(tmp_path):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    job = fake.seat['work'][0]['jobId']
    body, calls = popup_body(job, nodes=False), []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=body)
    async with memo(clock, handler) as client:
        fake.fetch_job, fake.read_job_detail = client.fetch_job, client.read_job_detail
        fake._monotonic = client._monotonic
        manager = _manager(tmp_path, fake, clock=clock)
        try:
            await manager._pool_swarm_answers(fake.seat, 420, clock())
            await manager._pool_swarm_job_details(fake.seat, clock())
            body['nodes'] = popup_body(job)['nodes']
            clock.advance(120)
            await manager._pool_swarm_job_details(fake.seat, clock())
            point = manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL).payload[job]
            assert len(calls) == 2
            assert point['nodes'][0]['key'] == 'hunt_d'
            assert point['read_ts'] == NOW+120
        finally:
            await manager.close()


async def test_popup_memo_clock_and_failed_retry_preserve_last_good(tmp_path):
    clock = FakeClock(NOW-60)
    fake = Answers(popup_seat())
    job = fake.seat['work'][0]['jobId']
    body, calls = popup_body(job), []
    def handler(request):
        assert request.url.path == '/jobs/' + job
        calls.append(request)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404)
    async with memo(clock, handler) as client:
        await client.read_job_detail(job)
        clock.advance(60)
        fake.fetch_job, fake.read_job_detail = client.fetch_job, client.read_job_detail
        manager = _manager(tmp_path, fake, clock=clock)
        fake._monotonic = client._monotonic
        try:
            await manager._pool_swarm_answers(fake.seat, 420, clock())
            await manager._pool_swarm_job_details(fake.seat, clock())
            before = copy.deepcopy(manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL))
            assert before.payload[job]['read_ts'] == NOW-60
            assert len(calls) == 1
            body = None
            clock.advance(540)
            await manager._pool_swarm_job_details(fake.seat, clock())
            assert len(calls) == 2
            assert manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL) == before
            clock.advance(1)
            await manager._pool_swarm_job_details(fake.seat, clock())
            assert len(calls) == 2
        finally:
            await manager.close()


async def test_revalidation_failure_keeps_last_good_answer_clock(tmp_path):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    row = fake.seat['work'][0]
    manager = _manager(tmp_path, fake, clock=clock)
    try:
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        before = copy.deepcopy(manager.cache.get_last_good(SLOT_SWARM_ANSWERS))
        fake.responses[row['jobId']] = None
        clock.advance(600)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 2
        assert manager.cache.get_last_good(SLOT_SWARM_ANSWERS) == before
        clock.advance(1)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 2
    finally:
        await manager.close()


async def test_changed_job_state_revalidates_before_terminal_ttl(tmp_path):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    row = fake.seat['work'][0]
    job, key = row['jobId'], row['submissionHash']
    manager = _manager(tmp_path, fake, clock=clock)
    try:
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        clock.advance(1)
        row['jobState'] = 'executing'
        fake.responses[job]['submissions'][0]['summary'] = 'New execution.'
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 2
        assert manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload[job][key]['answer'] == 'New execution.'
    finally:
        await manager.close()


@pytest.mark.parametrize('resource', ['answers', 'details'])
async def test_changed_jobs_beyond_cap_remain_due(tmp_path, resource):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat(6))
    detail_state = ['completed']
    async def fetch(job):
        fake.detail_calls.append(job)
        return dict(popup_body(job), state=detail_state[0])
    fake.fetch_job = fetch
    manager = _manager(tmp_path, fake, clock=clock)
    try:
        for _ in range(3):
            await manager._pool_swarm_answers(fake.seat, 420, clock())
            await manager._pool_swarm_job_details(fake.seat, clock())
            clock.advance(1)
        for row in fake.seat['work']:
            row['jobState'] = 'failed'
            fake.responses[row['jobId']]['submissions'][0]['summary'] = 'Changed publication.'
        detail_state[0] = 'failed'
        for _ in range(3):
            before = len(fake.answer_calls), len(fake.detail_calls)
            if resource == 'answers':
                await manager._pool_swarm_answers(fake.seat, 420, clock())
                assert len(fake.answer_calls)-before[0] <= 4
            else:
                await manager._pool_swarm_job_details(fake.seat, clock())
                assert len(fake.detail_calls)-before[1] <= 2
            clock.advance(120)
        if resource == 'answers':
            points = manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload
            assert [points[row['jobId']][row['submissionHash']]['answer'] for row in fake.seat['work']] == ['Changed publication.']*6
        else:
            points = manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL).payload
            assert [points[row['jobId']]['state'] for row in fake.seat['work']] == ['failed']*6
    finally:
        await manager.close()


async def test_failed_changed_revalidation_retries_after_120s(tmp_path):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    row = fake.seat['work'][0]
    job, key = row['jobId'], row['submissionHash']
    manager = _manager(tmp_path, fake, clock=clock)
    try:
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        before = copy.deepcopy(manager.cache.get_last_good(SLOT_SWARM_ANSWERS))
        good = copy.deepcopy(fake.responses[job])
        clock.advance(1)
        row['jobState'] = 'failed'
        fake.responses[job] = None
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 2
        assert manager.cache.get_last_good(SLOT_SWARM_ANSWERS) == before
        fake.responses[job] = good
        fake.responses[job]['submissions'][0]['summary'] = 'Confirmed new version.'
        clock.advance(119)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 2
        clock.advance(1)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        assert len(fake.answer_calls) == 3
        assert manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload[job][key]['answer'] == 'Confirmed new version.'
    finally:
        await manager.close()


async def test_revalidation_respects_four_answers_two_details_and_retention(tmp_path):
    from maxpane_dashboard.data import surf_swarm as sw
    clock = FakeClock(NOW)
    fake = Answers(popup_seat(6))
    async def detail(job):
        fake.detail_calls.append(job)
        return popup_body(job)
    fake.fetch_job = detail
    manager = _manager(tmp_path, fake, clock=clock)
    try:
        for _ in range(3):
            await manager._pool_swarm_answers(fake.seat, 420, clock())
            await manager._pool_swarm_job_details(fake.seat, clock())
            clock.advance(1)
        assert len(fake.answer_calls) == 6 and len(fake.detail_calls) == 6
        clock.advance(597)
        before_answers, before_details = len(fake.answer_calls), len(fake.detail_calls)
        await manager._pool_swarm_answers(fake.seat, 420, clock())
        await manager._pool_swarm_job_details(fake.seat, clock())
        assert len(fake.answer_calls)-before_answers == 4
        assert len(fake.detail_calls)-before_details == 2
        answers = manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload
        details = manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL).payload
        assert sum(map(len, sw.prune_answers(answers, now_ts=clock(), cap=2, max_age_s=48*3600).values())) == 2
        assert len(sw.prune_job_details(details, now_ts=clock(), cap=2)) == 2
        assert sw.prune_answers(answers, now_ts=clock()+48*3600+1, cap=400, max_age_s=48*3600) == {}
        assert sw.prune_job_details(details, now_ts=clock()+48*3600+1) == {}
    finally:
        await manager.close()


async def test_sites_scores_cache_hit_keeps_observation_and_completes_tier(tmp_path):
    from tests.data.test_surf_manager_launches import LaunchSwarm, RPC, fixture
    clock = FakeClock(NOW-60)
    bodies = {fixture(name)['id']: fixture(name) for name in ('job_zto_site', 'job_adam_site')}
    calls = []
    def handler(request):
        job = request.url.path.removeprefix('/jobs/')
        assert job in bodies
        calls.append(job)
        return httpx.Response(200, json=bodies[job])
    async with memo(clock, handler) as client:
        for job in bodies:
            await client.read_job_detail(job)
        clock.advance(60)
        fake, launch = Answers(), LaunchSwarm()
        launch.rows = [fixture('launch_737')]
        async def sites():
            return [dict(site, createdAt='2026-10-06T01:00:00Z')
                    for site in fixture('sites')['sites'] if site['jobId'] in bodies]
        launch.fetch_sites = sites
        fake._jobs = [dict(id=job, state='completed', createdAt=body['createdAt'],
                          updatedAt=body.get('updatedAt')) for job, body in bodies.items()]
        fake.fetch_job, fake.read_job_detail = client.fetch_job, client.read_job_detail
        fake._monotonic = client._monotonic
        for name in ('fetch_launches', 'fetch_sites', 'fetch_launch_policies', 'fetch_launch'):
            setattr(fake, name, getattr(launch, name))
        manager = _manager(tmp_path, fake, clock=clock, client=RPC())
        try:
            await manager._pool_swarm_launches({TIER_SWARM_LAUNCHES}, clock())
            result = await manager._pool_swarm_scores({TIER_SWARM_SCORES}, clock())
            assert result['ok'] is True
            assert len(calls) == 2, 'warm SITES and Scores must share both original detail reads'
            facts = manager.cache.get_last_good(SLOT_SWARM_LAUNCH_FACTS)
            assert len(facts.payload['sites']) == 2
            assert facts.ts == NOW-60
            scores = manager.cache.get_last_good(SLOT_SWARM_SCORES)
            assert scores.ts == NOW-60
            assert scores.payload['workflows_ts'] == NOW
            assert manager.cache.last_fetch_ts(TIER_SWARM_SCORES) == NOW
            assert manager.cache.last_fetch_ts(TIER_SWARM_LAUNCHES) == NOW
        finally:
            await manager.close()


@pytest.mark.parametrize('refresh', [False, True], ids=['cold', 'terminal-refresh'])
async def test_popup_completion_observation_survives_current_cycle(tmp_path, refresh):
    from maxpane_dashboard.data import surf_swarm as sw
    clock = FakeClock(NOW)
    fake = Answers(popup_seat())
    job = fake.seat['work'][0]['jobId']
    body = popup_body(job)
    failed, calls = [False], []
    def handler(request):
        assert request.url.path == '/jobs/'+job
        calls.append(request)
        clock.advance(1)
        return httpx.Response(200, json={'error':'unavailable'} if failed[0] else body)
    async with memo(clock, handler) as client:
        client.submissions = fake.submissions
        manager = _manager(tmp_path, client, clock=clock)
        try:
            await manager._pool_swarm_answers(fake.seat, 420, clock())
            if refresh:
                manager.cache.store_last_good(SLOT_SWARM_JOB_DETAIL,
                    {job:sw.job_detail_point(body, job, now_ts=clock())}, ts=clock())
                clock.advance(600)
                body['nodes'].append(dict(key='late_node', role='review', state='accepted', attempt=1))
            started = clock()
            await manager._pool_swarm_job_details(fake.seat, started)
            point = manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL).payload[job]
            assert point['read_ts'] == started+1
            assert len(point['nodes']) == (2 if refresh else 1)
            before = copy.deepcopy(manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL))
            failed[0] = True
            clock.advance(600)
            await manager._pool_swarm_job_details(fake.seat, clock())
            assert manager.cache.get_last_good(SLOT_SWARM_JOB_DETAIL) == before
            assert len(calls) == 2
        finally:
            await manager.close()


@pytest.mark.parametrize('resource', ['answers', 'details'])
@pytest.mark.parametrize('fail_first', [False, True], ids=['success', 'failed-then-retry'])
async def test_known_revision_revalidates_record_with_caps_and_pending_retry(tmp_path, resource, fail_first):
    clock = FakeClock(NOW)
    fake = Answers(popup_seat(6))
    base = json.loads(Path('tests/fixtures/surf/detail_cache/cases.json').read_text())['terminal']
    jobs = [row['jobId'] for row in fake.seat['work']]
    bodies = {job:dict(copy.deepcopy(base), **popup_body(job), updatedAt='2026-10-17T10:00:00.000Z') for job in jobs}
    calls, failed = [], set()
    def handler(request):
        path = request.url.path
        if path == '/jobs':
            return httpx.Response(200, json={'jobs':list(bodies.values())})
        job = path.split('/')[2]
        assert job in bodies
        route = 'answers' if path.endswith('/submissions') else 'details'
        calls.append((route, job))
        if (route, job) in failed:
            failed.remove((route, job))
            return httpx.Response(200, json={'error':'unavailable'})
        return httpx.Response(200, json=fake.responses[job] if route == 'answers' else bodies[job])
    async with memo(clock, handler) as client:
        manager = _manager(tmp_path, client, clock=clock)
        try:
            # Other consumers have already observed these complete job versions.
            for job in jobs:
                await client.read_job_detail(job)
            for _ in range(3):
                await manager._pool_swarm_answers(fake.seat, 420, clock())
                await manager._pool_swarm_job_details(fake.seat, clock())
                clock.advance(1)
            slot = SLOT_SWARM_ANSWERS if resource == 'answers' else SLOT_SWARM_JOB_DETAIL
            prior = copy.deepcopy(manager.cache.get_last_good(slot).payload)
            for job in jobs:
                bodies[job]['updatedAt'] = '2026-10-17T10:00:01.000Z'
                bodies[job]['nodes'].append(dict(key='late_node', role='review', state='accepted', attempt=1))
                fake.responses[job]['submissions'][0]['summary'] = 'Revised publication.'
            await client.fetch_jobs()
            calls.clear()
            if fail_first:
                failed.add((resource, jobs[0]))
            changed_at = clock()
            for offset in (0, 1, 2, 120):
                clock.t = changed_at+offset
                before = len([r for r in calls if r[0] == resource])
                if resource == 'answers':
                    await manager._pool_swarm_answers(fake.seat, 420, clock())
                else:
                    await manager._pool_swarm_job_details(fake.seat, clock())
                delta = len([r for r in calls if r[0] == resource])-before
                assert delta <= (4 if resource == 'answers' else 2)
                if fail_first and offset < 120:
                    assert manager.cache.get_last_good(slot).payload[jobs[0]] == prior[jobs[0]]
                    assert calls.count((resource, jobs[0])) == 1
            points = manager.cache.get_last_good(slot).payload
            if resource == 'answers':
                assert [points[row['jobId']][row['submissionHash']]['answer'] for row in fake.seat['work']] == ['Revised publication.']*6
            else:
                assert [len(points[job]['nodes']) for job in jobs] == [2]*6
            assert sum(route == resource for route, _ in calls) == 6+int(fail_first)
        finally:
            await manager.close()
