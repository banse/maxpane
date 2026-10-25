"""Four assigned cards borrow shared snapshots without changing active selection."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surfboard as hub
from maxpane_dashboard.data import surfboard_activity as activity
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_WORKERS, SLOT_SURFBOARD_ACTIVITY, SLOT_SWARM_SEAT
from tests.data.test_surfboard import capture
from tests.data.test_surfboard_activity import workers
from tests.data.test_surf_manager_surfboard import manager

KEYS = ('agent', 'agent-2', 'agent-3', 'agent-4')


def agent_cards(rows):
    return [next(row for row in rows if row['key'] == key) for key in KEYS]


def evidence():
    read = workers(1, token=420)
    read['workers'] += workers(0, token=1836)['workers']
    read['count'] = 2
    return read


def test_explicit_four_empty_assignments_do_not_borrow_selected_or_leading_seat():
    data = dict(swarm_seat_selected={'token_id':420}, swarm_seat_live={'live_state':'working'},
                swarm_board_rows=[dict(rank=1, token_id=420)])
    rows = hub.cards(data, {}, now=100, agent_seats=[{'token_id':None}]*4,
                     activity=activity.observe(None, evidence(), now=100))
    for slot, row in enumerate(agent_cards(rows)):
        assert (row['seat_slot'],row['token_id']) == (slot,None)
        assert row['title'] == 'AGENT'
        assert row['status'] == row['meter_state'] == 'empty'
        assert (row['primary'],row['secondary'],row['destination']) == ('','type in',None)
        assert row['numerator'] is row['denominator'] is None
    assert all(row['seat_slot'] is row['token_id'] is None for row in rows if row['key'] not in KEYS)


def test_each_assigned_card_uses_its_own_activity_capacity_and_outcomes():
    records = hub.normalize_records(capture('records'))
    assignments = [
        dict(token_id=420, live={'working':1,'max_concurrency':2,'live_state':'working'}, outcome=hub.seat_outcome(records,420)),
        dict(token_id=1836, live={'working':0,'max_concurrency':4,'live_state':'idle'}, outcome=hub.seat_outcome(records,1836)),
        dict(token_id=0, live={'working':0,'max_concurrency':0,'live_state':'offline'}, outcome=hub.seat_outcome(records,0)),
        dict(token_id=None),
    ]
    observed = activity.observe(None,evidence(),now=100)
    before = deepcopy(observed)
    rows = agent_cards(hub.cards({}, {'records':hub.source_envelope(records,100)}, now=100,
                                agent_seats=assignments, activity=observed))
    assert [r['token_id'] for r in rows] == [420,1836,0,None]
    assert [r['status'] for r in rows] == ['working','idle','offline','empty']
    assert [r['secondary'] for r in rows[:3]] == ['1 of 2 slots','0 of 4 slots','offline']
    assert '95.9% accepted' in rows[0]['detail'] and '100.0% accepted' in rows[1]['detail']
    assert 'no submitted record' in rows[2]['detail']
    assert [r['destination'] for r in rows] == ['agent','agent','agent',None]
    assert observed == before
    old = agent_cards(hub.cards({}, {}, now=401, agent_seats=assignments,activity=observed))
    assert [r['meter_state'] for r in old] == ['stale','stale','stale','empty']


async def test_manager_assignments_are_memory_only_and_survive_transient_selection(manager, monkeypatch):
    m,_ = manager
    monkeypatch.setattr(m.cache,'store_last_good',lambda *a,**k: pytest.fail('assignment wrote cache'))
    assert m.get_hub_seats() == (420,None,None,None)
    m.set_hub_seats([420,1836,0,None])
    m.set_seat(516)
    assert m.get_hub_seats() == (420,1836,0,None) and m._seat_saved == 516
    for bad in ([1,2], [1,2,3,True], [1,2,3,10_000_000_000], '1234'):
        with pytest.raises(ValueError):
            m.set_hub_seats(bad)
        assert m.get_hub_seats() == (420,1836,0,None)
    await m.close()


async def test_manager_projects_every_saved_token_from_shared_sources_without_reads(manager):
    m,clock = manager
    read = evidence()
    m.cache.store_last_good(SLOT_SWARM_WORKERS,read,ts=clock.now)
    m.cache.store_last_good(SLOT_SURFBOARD_ACTIVITY,activity.observe(None,read,now=clock.now),ts=clock.now)
    m.cache.store_last_good(hub.SOURCE_SLOTS['records'],hub.source_envelope(hub.normalize_records(capture('records')),clock.now),ts=clock.now)
    m.set_hub_seats([420,1836,0,None])
    m.set_seat(516)
    rows = agent_cards(m._project_hub()['surfboard_cards'])
    assert [r['token_id'] for r in rows] == [420,1836,0,None]
    assert [r['status'] for r in rows] == ['working','idle','offline','empty']
    assert '95.9% accepted' in rows[0]['detail'] and '100.0% accepted' in rows[1]['detail']
    m.set_hub_seats([None]*4)
    assert all(r['status']=='empty' for r in agent_cards(m._project_hub()['surfboard_cards']))
    m.swarm_client.fetch_seat_records.assert_not_awaited()
    assert m._swarm_seat_task is None
    await m.close()


async def test_incomplete_workers_cannot_give_absent_assigned_seat_zero_capacity(manager):
    m,clock = manager
    read = evidence()
    read['count'] = 3
    m.cache.store_last_good(SLOT_SWARM_WORKERS,read,ts=clock.now)
    m.cache.store_last_good(SLOT_SURFBOARD_ACTIVITY,activity.observe(None,read,now=clock.now),ts=clock.now)
    m.set_hub_seats([420,0,None,None])
    rows = agent_cards(m._project_hub()['surfboard_cards'])
    assert rows[0]['meter_state'] == 'busy'
    assert rows[1]['meter_state'] == 'unavailable'
    assert rows[1]['secondary'] == '— of — slots'
    await m.close()


async def test_offline_cards_use_each_seats_cached_api_status(manager):
    from tests.surf_swarm_fixtures import swarm_seat_capture
    m, clock = manager
    read = workers()
    m.cache.store_last_good(SLOT_SWARM_WORKERS, read, ts=clock.now)
    m.cache.store_last_good(SLOT_SURFBOARD_ACTIVITY, activity.observe(None, read, now=clock.now), ts=clock.now)
    points = {}
    for token, status in ((7, 'revoked'), (420, 'suspended')):
        seat = dict(swarm_seat_capture('seat_420'), tokenId=str(token), status=status)
        points[str(token)] = dict(state='ok', read_ts=clock.now, seat=seat)
    m.cache.store_last_good(SLOT_SWARM_SEAT, dict(seats=points), ts=clock.now)
    m.set_hub_seats([7, 420, 3, 7])
    m.set_seat(420)
    rows = agent_cards(m._project_hub()['surfboard_cards'])
    assert [row['secondary'] for row in rows] == ['revoked', 'suspended', 'offline', 'revoked']
    assert all(row['status'] == row['meter_state'] == 'offline' for row in rows)
    m.swarm_client.fetch_seat_records.assert_not_awaited()
    assert m._swarm_seat_task is None
    await m.close()


def test_reassignment_and_duplicate_slots_reuse_only_the_named_tokens_stop_history():
    read = evidence()
    read['workers'][1]['working'] = 1
    observed = activity.observe(None,read,now=100)
    read['workers'][0]['working'] = 0
    observed = activity.observe(observed,read,now=200)
    observed = activity.observe(observed,read,now=43200)
    assigned = [dict(token_id=t,live={'live_state':'idle'}) for t in (420,1836,420,0)]
    first = agent_cards(hub.cards({}, {},now=43200,activity=observed,agent_seats=assigned))
    assert [r['numerator'] for r in first] == [43400,86400,43400,None]
    assigned[0]['token_id'] = 1836
    assigned[1]['token_id'] = 420
    second = agent_cards(hub.cards({}, {},now=43200,activity=observed,agent_seats=assigned))
    assert [r['numerator'] for r in second] == [86400,43400,43400,None]
    assert [r['meter_state'] for r in second] == ['busy','idle','idle','idle']


def test_one_unknown_worker_does_not_erase_another_assigned_tokens_positive_work():
    read = evidence()
    read['workers'][0]['working'] = None
    read['workers'][1]['working'] = 2
    assigned = [dict(token_id=t) for t in (420,1836,None,None)]
    rows = agent_cards(hub.cards({}, {},now=100,activity=activity.observe(None,read,now=100),agent_seats=assigned))
    assert [r['meter_state'] for r in rows] == ['unavailable','busy','empty','empty']
    assert rows[0]['secondary'] == '— of — slots'


def test_mismatched_outcome_identity_never_relabels_another_seats_acceptance():
    outcome = hub.seat_outcome(hub.normalize_records(capture('records')),420)
    rows = agent_cards(hub.cards({}, {},now=100,agent_seats=[dict(token_id=1836,outcome=outcome)]+[{}]*3))
    assert 'acceptance —' in rows[0]['detail']
    assert '95.9%' not in rows[0]['detail']


def detail_reads(m):
    from tests.data.test_surf_manager_swarm import _seat_payload_of
    m.swarm_client.fetch_seat = AsyncMock(side_effect=lambda token: _seat_payload_of(token))
    for name in ('_resolve_seat_owner','_pool_swarm_seat_rewards','_pool_swarm_answers',
                 '_pool_swarm_oracle','_pool_swarm_job_details'):
        setattr(m,name,AsyncMock())


async def test_active_b_keeps_its_details_when_an_inflight_full_refresh_returns_a(manager):
    m,clock = manager
    detail_reads(m)
    await m._pool_swarm_seat(420,clock.now)
    clock.now += 60
    await m._pool_swarm_seat(516,clock.now)
    m.set_seat(420)
    old = m._project_hub()
    gate,entered = asyncio.Event(),asyncio.Event()
    async def full():
        entered.set()
        await gate.wait()
        return old
    m._cycle.side_effect = full
    waiting = asyncio.create_task(m.fetch_and_compute())
    await entered.wait()
    m.set_seat(516)
    expected = m._project_hub()
    gate.set()
    got = await waiting
    assert got['swarm_seat_selected']['token_id'] == 516
    for field in ('summary','work_rows','node_rows','teammates','as_of_hhmm','owner_ens'):
        assert got['swarm_seat_'+field] == expected['swarm_seat_'+field]
    assert got['swarm_seat_summary'] != old['swarm_seat_summary']
    m.set_seat(420)
    assert m._project_hub()['swarm_seat_summary'] == old['swarm_seat_summary']
    assert m.get_hub_seats() == (420,None,None,None)
    await m.close()


@pytest.mark.parametrize('fails', [False,True])
async def test_late_a_detail_read_or_failure_cannot_paint_b_or_change_assignments(manager, fails):
    from tests.data.test_surf_manager_swarm import _seat_payload_of
    m,clock = manager
    detail_reads(m)
    await m._pool_swarm_seat(516,clock.now)
    gate,entered = asyncio.Event(),asyncio.Event()
    async def late(token):
        assert token == 420
        entered.set()
        await gate.wait()
        return None if fails else _seat_payload_of(token)
    m.swarm_client.fetch_seat.side_effect = late
    task = asyncio.create_task(m._pool_swarm_seat(420,clock.now))
    await entered.wait()
    m.set_hub_seats([None,516,420,None])
    m.set_seat(516)
    before = m._project_hub()
    gate.set()
    await task
    after = m._project_hub()
    assert after['swarm_seat_selected']['token_id'] == 516
    assert after['swarm_seat_summary'] == before['swarm_seat_summary']
    assert after['swarm_seat_read'] is None
    assert m.get_hub_seats() == (None,516,420,None)
    assert agent_cards(after['surfboard_cards']) == agent_cards(before['surfboard_cards'])
    assert m.cache.get_last_good(SLOT_SWARM_SEAT).payload['seats']['516']['read_ts'] == clock.now
    await m.close()


def boardroom_reads(m, clock):
    from tests.data.test_surfboard_activity import NOW, seat_records
    from tests.surf_swarm_fixtures import swarm_capture_v3
    clock.now = NOW
    raw = swarm_capture_v3('workers')
    raw['workers'] = [raw['workers'][0]]
    raw['count'] = 1
    raw['workers'][0]['seat']['tokenId'] = '420'
    raw['workers'][0]['working'] = 0
    m.swarm_client.fetch_workers = AsyncMock(return_value=raw)
    m.swarm_client.fetch_contributors = AsyncMock(return_value=swarm_capture_v3('contributors'))
    m.swarm_client.fetch_seat = AsyncMock(side_effect=lambda token: dict(
        seat_records(token=token)['seats'][str(token)]['seat'], status='revoked' if token == 7 else 'active'))
    m._pool_swarm_seat = AsyncMock(side_effect=AssertionError('Boardroom offered agent detail fanout'))
    m.set_active_view('surfboard')


@pytest.mark.parametrize('first', ['workers', 'seats'])
async def test_cold_boardroom_hydrates_each_assignment_without_opening_agent(manager, first):
    m, clock = manager
    boardroom_reads(m, clock)
    m.set_hub_seats([420, 7, 420, None])
    m.set_seat(516)
    release = asyncio.Event()
    if first == 'workers':
        read_seat = m.swarm_client.fetch_seat.side_effect
        async def wait_for_workers(token):
            await release.wait()
            return read_seat(token)
        m.swarm_client.fetch_seat.side_effect = wait_for_workers
    else:
        read_workers = m.swarm_client.fetch_workers.return_value
        async def wait_for_seats():
            await release.wait()
            return read_workers
        m.swarm_client.fetch_workers.side_effect = wait_for_seats
    try:
        await m.fetch_hub_snapshot()
        await (m._swarm_board_task if first == 'workers' else m._card_reader.wait_pending())
        release.set()
        await asyncio.gather(m._swarm_board_task, m._card_reader.wait_pending())
        cards = agent_cards(m.get_hub_snapshot()['surfboard_cards'])
        assert cards[0]['numerator'] == cards[2]['numerator'] == 72000
        assert cards[1]['secondary'] == 'revoked'
        assert [call.args[0] for call in m.swarm_client.fetch_seat.await_args_list] == [420, 7]
        assert m._seat_saved == 516 and m._swarm_seat_task is None
        m._pool_swarm_seat.assert_not_awaited()
        m.get_hub_snapshot()
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert m.swarm_client.fetch_seat.await_count == 2
    finally:
        await m.close()


async def test_boardroom_four_concurrent_reads_merge_each_seat_and_preserve_cached_sibling(manager):
    from tests.data.test_surfboard_activity import seat_records
    m, clock = manager
    boardroom_reads(m, clock)
    prior = seat_records(token=516)
    m.cache.store_last_good(SLOT_SWARM_SEAT, prior, ts=clock.now)
    m.set_hub_seats([420, 7, 3, 0])
    entered = {token: asyncio.Event() for token in m.get_hub_seats()}
    release = {token: asyncio.Event() for token in m.get_hub_seats()}
    read_seat = m.swarm_client.fetch_seat.side_effect
    async def ordered(token):
        entered[token].set()
        await release[token].wait()
        return read_seat(token)
    m.swarm_client.fetch_seat.side_effect = ordered
    try:
        await m.fetch_hub_snapshot()
        await asyncio.gather(*(event.wait() for event in entered.values()))
        for token in (7, 0, 420, 3):
            clock.now += 1
            release[token].set()
            await m._card_reader.tasks[f'seat:{token}']
            point = m.cache.get_last_good(SLOT_SWARM_SEAT).payload['seats'][str(token)]
            assert point['seat']['tokenId'] == str(token) and point['read_ts'] == clock.now
        assert set(m.cache.get_last_good(SLOT_SWARM_SEAT).payload['seats']) == {'516', '420', '7', '3', '0'}
        m.set_hub_seats([None] * 4)
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert m.swarm_client.fetch_seat.await_count == 4
        assert all(card['status'] == 'empty' for card in agent_cards(m.get_hub_snapshot()['surfboard_cards']))
    finally:
        await m.close()


async def test_boardroom_assignment_change_cancels_old_read_and_starts_new_without_wait(manager):
    m, clock = manager
    boardroom_reads(m, clock)
    started, cancelled = asyncio.Event(), asyncio.Event()
    release = asyncio.Event()
    initial = m.swarm_client.fetch_seat.side_effect
    async def blocked(token):
        if token == 420:
            started.set()
            try:
                await release.wait()
            finally:
                cancelled.set()
        return initial(token)
    m.swarm_client.fetch_seat.side_effect = blocked
    m.set_hub_seats([420, None, None, None])
    try:
        await m.fetch_hub_snapshot()
        await started.wait()
        m.set_hub_seats([7, None, None, None])
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert cancelled.is_set()
        assert agent_cards(m.get_hub_snapshot()['surfboard_cards'])[0]['secondary'] == 'revoked'
        assert set(m.cache.get_last_good(SLOT_SWARM_SEAT).payload['seats']) == {'7'}
        assert m._seat_saved == 420
    finally:
        release.set()
        await m.close()


@pytest.mark.parametrize('failure', [None, 'mismatched', 'raised'])
async def test_boardroom_failed_seat_read_retains_own_last_good_and_backoff(manager, failure):
    m, clock = manager
    boardroom_reads(m, clock)
    m.set_hub_seats([7, None, None, None])
    try:
        await m.fetch_hub_snapshot()
        await asyncio.gather(m._swarm_board_task, m._card_reader.wait_pending())
        old = deepcopy(m.cache.get_last_good(SLOT_SWARM_SEAT).payload)
        clock.now += 30
        m.swarm_client.fetch_seat.side_effect = RuntimeError('offline') if failure == 'raised' else None
        m.swarm_client.fetch_seat.return_value = (dict(old['seats']['7']['seat'], tokenId='420')
                                                 if failure == 'mismatched' else None)
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert m.cache.get_last_good(SLOT_SWARM_SEAT).payload == old
        assert agent_cards(m.get_hub_snapshot()['surfboard_cards'])[0]['secondary'] == 'revoked'
        await m.fetch_hub_snapshot()
        await m._card_reader.wait_pending()
        assert m.swarm_client.fetch_seat.await_count == 2
    finally:
        await m.close()


async def test_leaving_boardroom_cancels_assigned_reads_without_cache_or_detail_work(manager):
    m, clock = manager
    boardroom_reads(m, clock)
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def blocked(token):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    m.swarm_client.fetch_seat.side_effect = blocked
    try:
        await m.fetch_hub_snapshot()
        await started.wait()
        m.set_active_view(None)
        await m.drain_reads()
        assert cancelled.is_set()
        assert m.cache.get_last_good(SLOT_SWARM_SEAT) is None
        m._pool_swarm_seat.assert_not_awaited()
    finally:
        await m.close()
