"""Oracle scheduling and cancellation with injected clients and a dead transport."""
import asyncio
import copy

import pytest

from maxpane_dashboard.data import surf_manager as mod
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_ORACLE, SLOT_SWARM_SEAT, SLOT_SWARM_ANSWERS, TIER_SWARM_SEAT
from tests.data.test_surf_manager_answers import Answers, work, NOW
from tests.data.test_surf_manager_swarm import _manager
from tests.data.test_surf_manager import FakeClock
from tests.data.test_surf_swarm_oracle import captured


class Oracle(Answers):
    def __init__(self,n=1,status='attested'):
        seat=work(n,'completed')
        for row in seat['work']:
            row.update(nodeKey='oracle_assess',submittedAt='2026-09-23T20:00:00Z')
        super().__init__(seat)
        self.oracle_calls=[]; self.lists=None; self.details={}; self.list_gate=None; self.entered=asyncio.Event()
        template,_=captured()
        for i,row in enumerate(seat['work']):
            d=copy.deepcopy(template)
            d.update(id=f'10000000-0000-4000-8000-{i:012x}',jobId=row['jobId'],status=status,createdAt='2026-09-23T19:00:00Z')
            d['members']=[dict(d['members'][0],submissionHash=row['submissionHash'])]
            d['agreement']['cluster']=[row['submissionHash']]
            self.details[d['id']]=d
        self.requests=[{k:d[k] for k in ('id','jobId','createdAt')} for d in self.details.values()]

    async def fetch_oracle_requests(self,*,limit,before=None):
        self.oracle_calls.append(('list',limit,before))
        if self.list_gate is not None and before is not None:
            self.entered.set();await self.list_gate.wait()
        await asyncio.sleep(0)
        if self.lists is not None:
            return copy.deepcopy(self.lists[0 if before is None else 1])
        return copy.deepcopy(self.requests)

    async def fetch_oracle_request(self,request_id):
        self.oracle_calls.append(('detail',request_id))
        await asyncio.sleep(0)
        return copy.deepcopy(self.details.get(request_id))


def rows(manager,now=NOW):
    return manager._swarm_seat_keys({},None,{},manager.cache.get_last_good(SLOT_SWARM_SEAT),
        manager.cache.get_last_good(SLOT_SWARM_ANSWERS),now,
        oracle_entry=manager.cache.get_last_good(SLOT_SWARM_ORACLE))['swarm_seat_work_rows']


async def test_no_due_rows_means_zero_calls_and_no_rewrite(tmp_path):
    fake=Oracle();fake.seat['work'][0]['nodeKey']='build'
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        assert fake.oracle_calls==[]
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is None
    finally: await manager.close()


async def test_four_detail_cap_progressive_fill_then_terminal_zero_calls(tmp_path):
    fake=Oracle(6);manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        assert [r['panel_state'] for r in rows(manager)]==['agreed']*4+['not_read']*2
        assert len([c for c in fake.oracle_calls if c[0]=='detail'])==mod.SWARM_ORACLE_PER_CYCLE==4
        await manager._pool_swarm_seat(420,NOW+120)
        assert all(r['panel_state']=='agreed' for r in rows(manager,NOW+120))
        assert [c[1] for c in fake.oracle_calls if c[0]=='detail']==list(fake.details)
        prior=manager.cache.get_last_good(SLOT_SWARM_ORACLE);fake.oracle_calls.clear()
        await manager._pool_swarm_seat(420,NOW+240)
        assert fake.oracle_calls==[]
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is prior
    finally: await manager.close()


async def test_assessing_retries_only_after_120_seconds(tmp_path):
    fake=Oracle(status='assessing');manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        for now in (NOW,NOW+119,NOW+120): await manager._pool_swarm_seat(420,now)
        assert len([c for c in fake.oracle_calls if c[0]=='detail'])==2
        assert rows(manager,NOW+120)[0]['panel_state']=='assessing'
    finally: await manager.close()


@pytest.mark.parametrize('failure',['list','detail'])
async def test_failures_leave_seat_fetched_and_answer_intact(tmp_path,failure):
    fake=Oracle()
    if failure=='list': fake.lists=[None]
    else: fake.details={}
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        row=rows(manager)[0]
        assert row['panel_state']=='unavailable'
        assert row['answer']=='Answer 0.' and row['answer_state']=='read'
        assert manager.cache.last_fetch_ts(TIER_SWARM_SEAT)==NOW
    finally: await manager.close()


@pytest.mark.parametrize('reason',['matched','short','older','cap'])
async def test_page_walk_stop_reasons_and_negative_coverage(tmp_path,monkeypatch,reason):
    monkeypatch.setattr(mod,'SWARM_ORACLE_PAGE_LIMIT',2)
    monkeypatch.setattr(mod,'SWARM_ORACLE_PAGE_CAP',2)
    fake=Oracle();match=fake.requests[0]
    extra=dict(match,id='20000000-0000-4000-8000-000000000000',jobId='30000000-0000-4000-8000-000000000000')
    if reason=='matched': fake.lists=[[match,extra]]
    elif reason=='short': fake.lists=[[]]
    elif reason=='older': fake.lists=[[extra,dict(extra,jobId='30000000-0000-4000-8000-000000000001')]]
    else:
        extra['createdAt']='2026-09-23T23:00:00Z'
        second=dict(extra,jobId='30000000-0000-4000-8000-000000000001',createdAt='2026-09-23T22:00:00Z')
        fake.lists=[[extra,dict(extra)],[second,dict(second)]]
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        calls=[c for c in fake.oracle_calls if c[0]=='list']
        assert len(calls)==(2 if reason=='cap' else 1)
        assert rows(manager)[0]['panel_state']=={'matched':'agreed','short':'off_panel','older':'off_panel','cap':'not_read'}[reason]
        if reason=='cap': assert calls[1][2]=='2026-09-23T23:00:00Z'
    finally: await manager.close()


async def test_walk_second_page_finds_request_and_failure_preserves_prior(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'SWARM_ORACLE_PAGE_LIMIT',1)
    fake=Oracle(status='assessing');match=fake.requests[0]
    extra=dict(match,jobId='30000000-0000-4000-8000-000000000000',createdAt='2026-09-23T23:00:00Z')
    fake.lists=[[extra],[match]]
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        assert rows(manager)[0]['panel_state']=='assessing'
        prior=manager.cache.get_last_good(SLOT_SWARM_ORACLE)
        fake.lists=[None]
        await manager._pool_swarm_seat(420,NOW+120)
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is prior
        fake.lists=[[match]];fake.details={}
        await manager._pool_swarm_seat(420,NOW+240)
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is prior
    finally: await manager.close()


async def test_duplicate_job_is_unavailable_without_detail_read(tmp_path):
    fake=Oracle();fake.requests.append(dict(fake.requests[0],id='20000000-0000-4000-8000-000000000000'))
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420,NOW)
        assert rows(manager)[0]['panel_state']=='unavailable'
        assert not any(c[0]=='detail' for c in fake.oracle_calls)
    finally: await manager.close()


async def test_hostile_persisted_point_is_dropped_on_load(tmp_path):
    fake=Oracle();manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    await manager._pool_swarm_seat(420,NOW)
    slot=manager.cache.get_last_good(SLOT_SWARM_ORACLE).payload
    next(iter(next(iter(slot.values())).values()))['figure']=1.5
    manager.cache.store_last_good(SLOT_SWARM_ORACLE,slot,ts=NOW);manager.cache.save()
    fresh=_manager(tmp_path,Oracle(),clock=FakeClock(NOW))
    try: assert fresh.cache.get_last_good(SLOT_SWARM_ORACLE).payload=={}
    finally: await fresh.close();await manager.close()


async def test_cancel_mid_oracle_walk_never_stores_partial_slot(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'SWARM_ORACLE_PAGE_LIMIT',1)
    fake=Oracle(2);first=dict(fake.requests[0],createdAt='2026-09-23T23:00:00Z')
    fake.lists=[[first],[fake.requests[1]]];fake.list_gate=asyncio.Event()
    manager=_manager(tmp_path,fake,clock=FakeClock(NOW));manager.set_seat(420)
    try:
        task=await manager._offer_swarm_seat({TIER_SWARM_SEAT},420,None,NOW)
        await asyncio.wait_for(fake.entered.wait(),2)
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is None
        await manager._cancel_swarm_seat()
        assert task.cancelled()
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is None
        assert manager.cache.last_fetch_ts(TIER_SWARM_SEAT)==NOW
    finally: fake.list_gate.set();await manager.close()
