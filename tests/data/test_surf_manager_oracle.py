"""Oracle scheduling and cancellation with injected clients and a dead transport."""
import asyncio
import copy

import pytest

from maxpane_dashboard.data import surf_manager as mod
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_ORACLE, SLOT_SWARM_ORACLE_INDEX, SLOT_SWARM_SEAT, SLOT_SWARM_ANSWERS, TIER_SWARM_SEAT
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

    async def fetch_oracle_request(self,request_id,submission_hash):
        self.oracle_calls.append(('detail',request_id,submission_hash))
        await asyncio.sleep(0)
        detail = copy.deepcopy(self.details.get(request_id))
        if detail is not None and isinstance(detail.get('members'), list):
            detail['members'] = [m for m in detail['members'] if m['submissionHash'] == submission_hash]
        return detail


async def test_shared_job_reads_each_hash_and_keeps_its_own_member_facts(tmp_path):
    fake = Oracle(2)
    first, second = fake.seat['work']
    second['jobId'] = first['jobId']
    detail = next(iter(fake.details.values()))
    detail['answerType'] = 'bool'
    template = detail['members'][0]
    detail['members'] = [dict(template, submissionHash=row['submissionHash'],
                              answer=dict(template['answer'], answer=value, notes=note))
                         for row, value, note in [(first, True, 'First evidence'), (second, False, 'Second evidence')]]
    detail['agreement']['cluster'] = [first['submissionHash'], second['submissionHash']]
    fake.details = {detail['id']: detail}
    fake.requests = [{k: detail[k] for k in ('id', 'jobId', 'createdAt')}]
    assert (await fake.fetch_oracle_request(detail['id'], 'f'*64))['members'] == []
    fake.oracle_calls.clear()
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert [c[1:] for c in fake.oracle_calls if c[0] == 'detail'] == [
            (detail['id'], first['submissionHash']), (detail['id'], second['submissionHash'])]
        result = {row['submission_hash']: row for row in rows(manager)}
        for source, value, note in [(first, 'true', 'First evidence'), (second, 'false', 'Second evidence')]:
            row = result[source['submissionHash']]
            assert row['oracle_seat_answer'] == value
            assert row['oracle_notes'] == note and row['oracle_member_ok'] is True
    finally:
        await manager.close()


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


@pytest.mark.parametrize('status', ['attested', 'disagreed'])
async def test_known_final_without_agreement_retries_next_due_cycle(tmp_path, status):
    fake = Oracle(status=status)
    detail = next(iter(fake.details.values()))
    agreement = detail['agreement']
    detail['agreement'] = None
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'unavailable'
        point = next(iter(next(iter(manager.cache.get_last_good(SLOT_SWARM_ORACLE).payload.values())).values()))
        assert not point['terminal']
        detail['agreement'] = agreement
        await manager._pool_swarm_seat(420, NOW + 120)
        assert len([c for c in fake.oracle_calls if c[0] == 'detail']) == 2
        assert rows(manager, NOW + 120)[0]['panel_state'] == ('agreed' if status == 'attested' else 'no_quorum_in')
    finally:
        await manager.close()


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


def seed_index(manager, *, complete=True, newest='2026-09-23T21:00:00Z'):
    index = dict(jobs={'30000000-0000-4000-8000-000000000000':
                       '20000000-0000-4000-8000-000000000000'},
                 newest=newest, oldest='2026-09-20T00:00:00Z', complete=complete)
    manager.cache.store_last_good(SLOT_SWARM_ORACLE_INDEX, index, ts=NOW)
    return index


async def test_complete_index_proves_only_submissions_within_coverage(tmp_path):
    fake = Oracle(); manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    seed_index(manager)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'off_panel'
        assert fake.oracle_calls == []
    finally: await manager.close()


async def test_due_indexed_rows_need_no_list_even_when_assessing(tmp_path):
    fake = Oracle(status='assessing')
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        fake.oracle_calls.clear()
        await manager._pool_swarm_seat(420, NOW + 120)
        assert [c[0] for c in fake.oracle_calls] == ['detail']
        assert rows(manager, NOW + 120)[0]['panel_state'] == 'assessing'
        prior = manager.cache.get_last_good(SLOT_SWARM_ORACLE)
        fake.details = {}
        await manager._pool_swarm_seat(420, NOW + 240)
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE) is prior
    finally: await manager.close()


@pytest.mark.parametrize('populated', [False, True])
async def test_empty_first_page_is_a_failed_read(tmp_path, populated):
    fake = Oracle(); fake.lists = [[]]
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    previous = seed_index(manager, newest='2026-09-23T19:00:00Z') if populated else None
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'unavailable'
        entry = manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX)
        if populated:
            assert entry.payload == previous
        else:
            assert entry is None or not entry.payload['complete']
    finally: await manager.close()


async def test_glitched_empty_first_build_never_completes_the_index_later(tmp_path, monkeypatch):
    # Re-review N1: cycle 1 serves one empty page on a first build; cycle 2
    # serves a newer unrelated request, then the seat's, then the end. The
    # seat's request is older than page 1 and must still be found.
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_LIMIT', 1)
    fake = Oracle()
    match = fake.requests[0]
    unrelated = dict(match, id='20000000-0000-4000-8000-000000000000',
                     jobId='30000000-0000-4000-8000-000000000000',
                     createdAt='2026-09-23T21:00:00Z')
    pages = iter([[], [unrelated], [match], []])

    async def fetch(**kwargs):
        fake.oracle_calls.append(('list', kwargs['limit'], kwargs.get('before')))
        return next(pages)

    fake.fetch_oracle_requests = fetch
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'unavailable'
        await manager._pool_swarm_seat(420, NOW + 120)
        assert rows(manager, NOW + 120)[0]['panel_state'] == 'agreed'
    finally:
        await manager.close()


def test_a_complete_index_with_no_entries_is_discarded_on_load():
    assert sw.coerce_oracle_index(dict(sw.empty_oracle_index(), complete=True)) is None
    assert sw.coerce_oracle_index(sw.empty_oracle_index()) == sw.empty_oracle_index()


@pytest.mark.parametrize('bad_stamp', ['2026-09-23T19:00:00+00:00', '2026-02-30T00:00:00Z', '123'])
async def test_invalid_page_timestamp_never_becomes_a_cursor(tmp_path, bad_stamp):
    fake = Oracle(); fake.requests[0]['createdAt'] = bad_stamp
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'unavailable'
        assert fake.oracle_calls == [('list', 500, None)]
    finally: await manager.close()


async def test_hostile_index_is_discarded_on_load_and_rebuilt(tmp_path):
    fake = Oracle(); manager = _manager(tmp_path, fake, clock=FakeClock(NOW))
    manager.cache.store_last_good(SLOT_SWARM_ORACLE_INDEX,
        dict(jobs={'bad': 'also bad'}, newest='2026-09-23T21:00:00Z',
             oldest='2026-09-23T19:00:00Z', complete=True), ts=NOW)
    manager.cache.save(); await manager.close()
    fresh = _manager(tmp_path, fake, clock=FakeClock(NOW)); fresh.set_seat(420)
    try:
        assert fresh.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX) is None
        await fresh._pool_swarm_seat(420, NOW)
        assert rows(fresh)[0]['panel_state'] == 'agreed'
        assert sw.coerce_oracle_index(fresh.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload)
    finally: await fresh.close()


async def test_forward_gap_beyond_page_cap_discards_index(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_LIMIT', 1)
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_CAP', 2)
    fake = Oracle(); match = fake.requests[0]
    fake.lists = [[dict(match, createdAt='2026-09-23T23:00:00Z')],
                  [dict(match, createdAt='2026-09-23T22:00:00Z')]]
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    seed_index(manager, newest='2026-09-23T19:00:00Z')
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload == sw.empty_oracle_index()
        assert rows(manager)[0]['panel_state'] == 'not_read'
        assert [c[0] for c in fake.oracle_calls] == ['list', 'list']
    finally: await manager.close()


async def test_backfill_resumes_next_cycle_with_shared_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_LIMIT', 1)
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_CAP', 2)
    fake = Oracle(); match = fake.requests[0]
    first = dict(match, id='20000000-0000-4000-8000-000000000001',
                 jobId='30000000-0000-4000-8000-000000000001', createdAt='2026-09-23T21:00:00Z')
    second = dict(first, id='20000000-0000-4000-8000-000000000002',
                  jobId='30000000-0000-4000-8000-000000000002', createdAt='2026-09-23T20:00:00Z')
    pages = iter([[first], [second], [first], [match]])
    async def fetch(**kwargs):
        fake.oracle_calls.append(('list', kwargs['limit'], kwargs.get('before')))
        return next(pages)
    fake.fetch_oracle_requests = fetch
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'not_read'
        assert not manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload['complete']
        await manager._pool_swarm_seat(420, NOW + 120)
        assert rows(manager, NOW + 120)[0]['panel_state'] == 'agreed'
        assert [c[2] for c in fake.oracle_calls if c[0] == 'list'] == [
            None, first['createdAt'], None, second['createdAt']]
    finally: await manager.close()


async def test_failed_forward_page_keeps_additions_without_advancing_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_LIMIT', 1)
    fake = Oracle(); match = fake.requests[0]
    extra = dict(match, createdAt='2026-09-23T23:00:00Z')
    fake.lists = [[extra], None]
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    previous = seed_index(manager, newest='2026-09-23T19:00:00Z')
    try:
        await manager._pool_swarm_seat(420, NOW)
        index = manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload
        assert index['newest'] == previous['newest']
        assert index['jobs'][match['jobId']] == match['id']
        assert rows(manager)[0]['panel_state'] == 'agreed'
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
        assert manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX) is None
        assert manager.cache.last_fetch_ts(TIER_SWARM_SEAT)==NOW
    finally: fake.list_gate.set();await manager.close()


async def test_request_older_than_submission_on_page_two_is_never_off_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_LIMIT', 1)
    fake = Oracle()
    match = fake.requests[0]
    unrelated = dict(match, id='20000000-0000-4000-8000-000000000000',
                     jobId='30000000-0000-4000-8000-000000000000',
                     createdAt='2026-09-23T19:30:00Z')
    pages = iter([[unrelated], [match], []])

    async def fetch(**kwargs):
        fake.oracle_calls.append(('list', kwargs['limit'], kwargs.get('before')))
        return next(pages)

    fake.fetch_oracle_requests = fetch
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert rows(manager)[0]['panel_state'] == 'agreed'
        assert len([c for c in fake.oracle_calls if c[0] == 'list']) == 3
    finally:
        await manager.close()


async def test_valid_index_survives_restart_beyond_point_retention_without_list_read(tmp_path):
    fake = Oracle(status='assessing')
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    await manager._pool_swarm_seat(420, NOW)
    index = copy.deepcopy(manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload)
    manager.cache.save(); await manager.close()
    later = NOW + 49 * 3600
    fake.oracle_calls.clear()
    fresh = _manager(tmp_path, fake, clock=FakeClock(later)); fresh.set_seat(420)
    try:
        assert fresh.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload == index
        await fresh._pool_swarm_seat(420, later)
        assert [c[0] for c in fake.oracle_calls] == ['detail']
        assert rows(fresh, later)[0]['panel_state'] == 'assessing'
    finally: await fresh.close()


async def test_forward_refresh_closes_gap_and_extends_complete_index(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'SWARM_ORACLE_PAGE_LIMIT', 1)
    fake = Oracle(); match = fake.requests[0]
    fake.lists = [[dict(match, createdAt='2026-09-23T21:00:00Z')],
                  [dict(id='20000000-0000-4000-8000-000000000000',
                        jobId='30000000-0000-4000-8000-000000000000',
                        createdAt='2026-09-23T19:00:00Z')]]
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    previous = seed_index(manager, newest='2026-09-23T19:00:00Z')
    try:
        await manager._pool_swarm_seat(420, NOW)
        index = manager.cache.get_last_good(SLOT_SWARM_ORACLE_INDEX).payload
        assert index['complete'] and index['oldest'] == previous['oldest']
        assert index['newest'] == '2026-09-23T21:00:00Z'
        assert rows(manager)[0]['panel_state'] == 'agreed'
        assert [c[0] for c in fake.oracle_calls] == ['list', 'list', 'detail']
    finally: await manager.close()


async def test_record_view_80_enriches_old_oracle_rows_with_four_pair_budget(tmp_path):
    fake = Oracle(81); manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    manager.set_record_view(80, False)
    try:
        for cycle in range(20):
            before = sum(c[0] == 'detail' for c in fake.oracle_calls)
            await manager._pool_swarm_seat(420, NOW+cycle*120)
            assert sum(c[0] == 'detail' for c in fake.oracle_calls)-before == 4
        assert [c[1] for c in fake.oracle_calls if c[0] == 'detail'] == list(fake.details)[:80]
    finally:
        await manager.close()


async def test_record_open_filter_enriches_old_oracle_attempt(tmp_path):
    fake = Oracle(81)
    for row in fake.seat['work']: row['status'] = 'accepted'
    fake.seat['work'][80]['status'] = 'rejected'
    manager = _manager(tmp_path, fake, clock=FakeClock(NOW)); manager.set_seat(420)
    manager.set_record_view(40, True)
    try:
        await manager._pool_swarm_seat(420, NOW)
        assert [c[1] for c in fake.oracle_calls if c[0] == 'detail'] == list(fake.details)[80:]
    finally:
        await manager.close()
