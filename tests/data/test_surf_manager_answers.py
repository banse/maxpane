"""Bounded selected-seat submission enrichment; all reads are injected captures."""
import asyncio
import copy

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data import surf_manager as manager_mod
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_ANSWERS, SLOT_SWARM_SEAT, SurfCache, TIER_SWARM_SEAT
from tests.data.test_surf_manager_swarm import _manager, _FakeSwarm
from tests.data.test_surf_manager import FakeClock
from tests.data.test_surf_swarm_polish import selected
from tests.surf_swarm_fixtures import swarm_capture_v4 as capture

NOW=2_000_000_000.0


def work(n=6, state='executing'):
    seat=capture('seat_420'); source=seat['work'][0]
    seat['work']=[dict(source, jobId=f'00000000-0000-0000-0000-{i:012x}',
                       submissionHash=f'{i:064x}', jobState=state) for i in range(n)]
    return seat


class Answers(_FakeSwarm):
    def __init__(self, seat=None):
        self.seat=seat or work()
        super().__init__(seats={420:self.seat})
        self.answer_calls=[]; self.responses={}; self.answer_gate=None; self.answer_entered=asyncio.Event()
        payload,item=selected()
        for index,row in enumerate(self.seat['work']):
            self.responses[row['jobId']]=dict(payload,jobId=row['jobId'],submissions=[
                dict(item,hash=row['submissionHash'],summary=f'Answer {index}. More.')])
    async def submissions(self, job):
        self.answer_calls.append(job); self.answer_entered.set()
        if self.answer_gate is not None: await self.answer_gate.wait()
        await asyncio.sleep(0)
        return copy.deepcopy(self.responses.get(job))


def data(manager, now=NOW):
    return manager._swarm_seat_keys({},None,{},manager.cache.get_last_good(SLOT_SWARM_SEAT),
                                   manager.cache.get_last_good(SLOT_SWARM_ANSWERS),now)


async def test_progressive_answers_distinguish_queued_failed_absent_and_reply(tmp_path):
    fake=Answers(); rows=fake.seat['work']; fake.responses[rows[0]['jobId']]=None
    fake.responses[rows[1]['jobId']]['submissions']=[]
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        result=data(manager)['swarm_seat_work_rows']
        assert [r['answer_state'] for r in result]==['unavailable','not_served','read','read','not_read','not_read']
        assert len(fake.answer_calls)==manager_mod.SWARM_ANSWER_PER_CYCLE==4
        assert manager.cache.last_fetch_ts(TIER_SWARM_SEAT) == NOW
        await manager._pool_swarm_seat(420,NOW+120)
        # New unread rows precede refreshes of earlier failures.
        assert fake.answer_calls[4:6]==[rows[4]['jobId'],rows[5]['jobId']]
        assert len(fake.answer_calls)==8
    finally: await manager.close()


async def test_record_window_job_grouping_and_definitive_terminal_answers_never_reread(tmp_path):
    fake=Answers(work(42,'completed')); rows=fake.seat['work']
    # Two hashes in one job cost one request and both points must be populated.
    second=fake.responses[rows[1]['jobId']]['submissions'][0]
    rows[1]['jobId']=rows[0]['jobId'];fake.responses[rows[0]['jobId']]['submissions'].append(second)
    from maxpane_dashboard.data.surf_swarm_client import SUBMISSIONS_NOT_FOUND
    fake.responses[rows[2]['jobId']]=dict(SUBMISSIONS_NOT_FOUND)
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        for cycle in range(12): await manager._pool_swarm_seat(420,NOW+cycle*120)
        expected=list(dict.fromkeys(row['jobId'] for row in rows[:40]))
        assert fake.answer_calls==expected
        result=data(manager,NOW+1320)['swarm_seat_work_rows']
        assert result[0]['answer_state']==result[1]['answer_state']=='read'
        assert result[2]['answer_state']=='not_served'
        assert all(row['answer_state']=='not_read' for row in result[40:])
        assert manager_mod.SWARM_ANSWER_CACHE_CAP==400
        assert manager_mod.SWARM_ANSWER_MAX_AGE_S==48*3600
    finally: await manager.close()


async def test_nonterminal_due_and_terminal_transition_preserve_retained_results(tmp_path):
    fake=Answers(work(1)); manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        await manager._pool_swarm_seat(420,NOW+119)
        assert len(fake.answer_calls)==1
        await manager._pool_swarm_seat(420,NOW+120)
        assert len(fake.answer_calls)==2
        fake.seats[420]['work'][0]['jobState']='completed'
        await manager._pool_swarm_seat(420,NOW+240)
        assert len(fake.answer_calls)==2
        entry=manager.cache.get_last_good(SLOT_SWARM_ANSWERS)
        assert next(iter(next(iter(entry.payload.values())).values()))['terminal'] is True
    finally: await manager.close()


async def test_switch_isolates_exact_hash_and_cancels_inflight_answer(tmp_path):
    fake=Answers(work(1)); row=fake.seat['work'][0]; other=copy.deepcopy(fake.seat)
    other['tokenId']='421';other['work'][0]['submissionHash']='f'*64;fake.seats[421]=other
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        manager.set_seat(421)
        assert data(manager)['swarm_seat_work_rows'] is None
        await manager._pool_swarm_seat(421,NOW+120)
        result=data(manager,NOW+120)['swarm_seat_work_rows'][0]
        assert result['answer_state']=='not_served' and result['answer'] is None
        fake.answer_gate=asyncio.Event();manager.set_seat(420)
        task=await manager._offer_swarm_seat({TIER_SWARM_SEAT},420,None,NOW+240)
        fake.answer_entered.clear();await asyncio.wait_for(fake.answer_entered.wait(), 1)
        manager.set_seat(421)
        replacement=await manager._offer_swarm_seat({TIER_SWARM_SEAT},421,None,NOW+240)
        assert task.cancelled()
        fake.answer_gate.set();await replacement
        assert data(manager,NOW+240)['swarm_seat_selected']['token_id']==421
    finally: await manager.close()


async def test_cache_load_and_consumption_revalidate_every_answer(tmp_path):
    fake=Answers(work(1,'completed'));clock=FakeClock(NOW)
    manager=_manager(tmp_path,fake,clock=clock);manager.set_seat(420)
    await manager._pool_swarm_seat(420,NOW);manager.cache.save()
    fresh=_manager(tmp_path,Answers(work(1,'completed')),clock=clock);fresh.set_seat(420)
    try:
        assert data(fresh)['swarm_seat_work_rows'][0]['answer']=='Answer 0.'
        slot=fresh.cache.get_last_good(SLOT_SWARM_ANSWERS).payload
        value=next(iter(next(iter(slot.values())).values()));value['answer']='Used /home/alice/private.txt.'
        assert data(fresh)['swarm_seat_work_rows'][0]['answer'] is None
        fresh.cache.store_last_good(SLOT_SWARM_ANSWERS,slot,ts=NOW+1);fresh.cache.save()
        last=_manager(tmp_path,Answers(work(1)),clock=clock)
        try: assert last.cache.get_last_good(SLOT_SWARM_ANSWERS).payload == {}
        finally: await last.close()
    finally: await manager.close();await fresh.close()


async def test_answer_read_is_detached_and_seat_failure_preserves_answers(tmp_path):
    fake=Answers(work(1));fake.answer_gate=asyncio.Event()
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        payload=await asyncio.wait_for(manager.fetch_and_compute(),2)
        await asyncio.wait_for(fake.answer_entered.wait(), 1)
        assert payload['swarm_seat_state']=='pending'
        assert manager.cache.get_last_good(SLOT_SWARM_SEAT) is not None
        assert manager.cache.get_last_good(SLOT_SWARM_ANSWERS) is None
        fake.answer_gate.set();await manager._swarm_seat_task
        before=manager.cache.get_last_good(SLOT_SWARM_ANSWERS)
        fake.seats[420]=None
        await manager._pool_swarm_seat(420,NOW+120)
        assert manager.cache.get_last_good(SLOT_SWARM_ANSWERS)==before
    finally: await manager.close()


async def test_fix_i1_six_job_slot_survives_nested_summary_and_terminal_cycle_two(tmp_path,monkeypatch):
    monkeypatch.setattr(manager_mod,'SWARM_ANSWER_PER_CYCLE',6) # reviewer probe, normal cap remains4
    fake=Answers(work(6,'completed')); first=fake.seat['work'][0]['jobId']
    fake.responses[first]['submissions'][0]['summary']='- 1) Wrote answer.json. More.'
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        rows=data(manager)['swarm_seat_work_rows']
        assert rows[0]['answer']=='Wrote answer.json.'
        assert all(row['answer_state']=='read' for row in rows[1:])
        await manager._pool_swarm_seat(420,NOW+120)
        assert len(fake.answer_calls)==6
        slot=manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload
        key=next(iter(slot[first]));slot[first][key]['answer']='unsafe /home/bob/secret.txt'
        await manager._pool_swarm_seat(420,NOW+240)
        assert fake.answer_calls[6:]==[first]
        assert all(row['answer_state']=='read' for row in data(manager,NOW+240)['swarm_seat_work_rows'])
    finally: await manager.close()


@pytest.mark.parametrize('failure',[None,{'jobId':'bad','submissions':[]}])
async def test_fix_i3_transient_terminal_answer_recovers_at_next_due_cycle(tmp_path,failure):
    fake=Answers(work(1,'completed'));job=fake.seat['work'][0]['jobId'];good=copy.deepcopy(fake.responses[job])
    fake.responses[job]=failure
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        assert data(manager)['swarm_seat_work_rows'][0]['answer_state']=='unavailable'
        fake.responses[job]=good
        await manager._pool_swarm_seat(420,NOW+119)
        assert len(fake.answer_calls)==1
        await manager._pool_swarm_seat(420,NOW+120)
        assert len(fake.answer_calls)==2
        assert data(manager,NOW+120)['swarm_seat_work_rows'][0]['answer_state']=='read'
    finally: await manager.close()


async def test_fix_i3_running_failure_and_legacy_terminal_failure_remain_retryable(tmp_path):
    fake=Answers(work(1));job=fake.seat['work'][0]['jobId'];good=copy.deepcopy(fake.responses[job]);fake.responses[job]=None
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        slot=manager.cache.get_last_good(SLOT_SWARM_ANSWERS).payload
        next(iter(slot[job].values()))['terminal']=True # legacy failure from §2.5
        fake.seats[420]['work'][0]['jobState']='completed';fake.responses[job]=good
        await manager._pool_swarm_seat(420,NOW+120)
        assert len(fake.answer_calls)==2
        assert data(manager,NOW+120)['swarm_seat_work_rows'][0]['answer_state']=='read'
    finally: await manager.close()


@pytest.mark.parametrize('negative',['404','absent'])
async def test_fix_i3_real_negative_freezes_even_while_job_running(tmp_path,negative):
    from maxpane_dashboard.data.surf_swarm_client import SUBMISSIONS_NOT_FOUND
    fake=Answers(work(1));job=fake.seat['work'][0]['jobId']
    fake.responses[job]=dict(SUBMISSIONS_NOT_FOUND) if negative=='404' else dict(jobId=job,submissions=[])
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        assert data(manager)['swarm_seat_work_rows'][0]['answer_state']=='not_served'
        await manager._pool_swarm_seat(420,NOW+120)
        assert len(fake.answer_calls)==1
    finally: await manager.close()
