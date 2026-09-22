"""Polish data: frozen captures, exact answer identity and truthful availability."""
import copy
from collections import Counter

import httpx
import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_swarm_client import SwarmClient
from maxpane_dashboard.data.surf_models import SURF_ROW_KEYS
from tests.surf_swarm_fixtures import swarm_capture_v4 as capture


def selected(name='submissions_73d7dcd7'):
    payload = capture(name)
    item = next(s for s in payload['submissions'] if int(s['seat']['tokenId']) == 420)
    return payload, item


@pytest.mark.parametrize(('source', 'expected'), [
    ('Created [answer.json](/home/alice/private/answer.json). Next.', 'Created answer.json.'),
    ('- **Used** `/Users/alice/private/answer.json`. Next.', 'Used answer.json.'),
    ('Used /root/private/result.txt! Next.', 'Used result.txt!'),
    ('Used /tmp/private/result.txt. Next.', 'Used result.txt.'),
    ('Used /workspace/private/result.txt? Next.', 'Used result.txt?'),
    (r'Used C:\Users\alice\private\answer.json. Next.', 'Used answer.json.'),
    ('Used [report](/Users/alice/My Folder/result(v2).json). Next.', 'Used report.'),
    ('First line\nSecond line.', 'First line'),
    ('1. __Paid__ 0.19 ETH. Next.', 'Paid 0.19 ETH.'),
    ('```text\nMade answer.json.\n```', 'Made answer.json.'),
    ('See https://example.org/docs/item. Next.', 'See https://example.org/docs/item.'),
])
def test_answer_sentence_drops_private_targets_paths_and_preserves_sentence_boundaries(source, expected):
    assert sw.answer_sentence(source) == expected


def test_captured_answer_uses_own_exact_hash_and_same_usage():
    for name in ('submissions_73d7dcd7', 'submissions_76296dcd', 'submissions_hostile'):
        payload, item = selected(name)
        answer = sw.submission_answer(payload, payload['jobId'], item['hash'], 420)
        assert answer == dict(answer=sw.answer_sentence(item['summary']), state='read',
                              model=item['usage']['model'], took_s=item['usage']['wallClockMs'] / 1000)
        assert '/home/' not in answer['answer'] and '/Users/' not in answer['answer']
        assert len(answer['answer']) > 0


@pytest.mark.parametrize(('defect', 'state'), [
    ('unread', 'unavailable'), ('empty', 'not_served'), ('empty_summary', 'no_reply'),
    ('null_summary', 'no_reply'), ('missing_summary', 'unavailable'), ('wrong_job', 'unavailable'), ('wrong_seat', 'unavailable'),
    ('duplicate_conflict', 'unavailable'), ('bad_summary', 'unavailable'),
])
def test_submission_states_are_distinct(defect, state):
    payload, item = selected(); payload['submissions'] = [item]
    job, key = payload['jobId'], item['hash']
    if defect == 'unread': payload = None
    elif defect == 'empty': payload['submissions'] = []
    elif defect == 'empty_summary': item['summary'] = ''
    elif defect == 'null_summary': item['summary'] = None
    elif defect == 'missing_summary': item.pop('summary')
    elif defect == 'wrong_job': payload['jobId'] = '00000000-0000-0000-0000-000000000001'
    elif defect == 'wrong_seat': item['seat']['tokenId'] = '421'
    elif defect == 'duplicate_conflict': payload['submissions'].append(dict(item, summary='Other.'))
    elif defect == 'bad_summary': item['summary'] = 42
    assert sw.submission_answer(payload, job, key, 420)['state'] == state


def test_exact_hash_does_not_match_a_prefix_or_another_seat():
    payload, item = selected(); key = item['hash']
    payload['submissions'] = [dict(item, hash=key[:8] + ('a' if key[8] != 'a' else 'b') + key[9:])]
    assert sw.submission_answer(payload, payload['jobId'], key, 420)['state'] == 'not_served'
    payload['submissions'] = [item]
    assert sw.submission_answer(payload, payload['jobId'], key, 421)['state'] == 'unavailable'


def point():
    payload, item = selected()
    value = sw.submission_answer(payload, payload['jobId'], item['hash'], 420)
    return payload['jobId'], item['hash'], dict(value, read_ts=1000.0, terminal=True)


@pytest.mark.parametrize(('field', 'bad'), [
    ('answer', 42), ('answer', '/home/private/answer.json.'), ('answer', None), ('state', 'not_read'), ('state', 'bogus'),
    ('read_ts', True), ('read_ts', -1), ('read_ts', float('inf')),
    ('terminal', 1), ('took_s', -1), ('took_s', True), ('took_s', float('nan')),
    ('model', []), ('extra', 'raw summary'),
])
def test_answer_cache_refuses_any_bad_point(field, bad):
    job, key, value = point(); value[field] = bad
    assert sw.coerce_answers_slot({job: {key: value}}) is None


def test_answer_cache_rejects_invalid_keys_states_and_retains_no_raw_payload():
    job, key, value = point()
    assert sw.coerce_answers_slot({job: {key: value}}) == {job: {key: value}}
    for bad_job, bad_hash in [('bad', key), (job, key[:8]), (job, True)]:
        assert sw.coerce_answers_slot({bad_job: {bad_hash: value}}) is None
    assert sw.coerce_answers_slot({job: {key: dict(value, state='not_served')}}) is None
    assert set(value) == {'answer', 'model', 'took_s', 'state', 'read_ts', 'terminal'}


def test_answer_pruning_counts_points_not_jobs_and_refuses_old_or_future_entries():
    job, key, value = point()
    entries = {job: {f'{i:064x}': dict(value, read_ts=float(i)) for i in range(5)}}
    assert len(sw.prune_answers(entries, now_ts=5, cap=2, max_age_s=10)[job]) == 2
    assert set(sw.prune_answers(entries, now_ts=5, cap=20, max_age_s=2)[job]) == {f'{i:064x}' for i in (3,4)}
    assert sw.prune_answers({job: {key: value}}, now_ts=999, cap=20, max_age_s=10) == {}


def test_worker_advertised_pairs_are_exact_and_aligned_without_losing_effort():
    workers = capture('workers'); counts = Counter()
    for row in workers['workers']:
        pairs = {(r['premiumModel']['model'], r['premiumModel'].get('effort'))
                 for r in row['runtimes'] if isinstance(r.get('premiumModel'), dict)}
        counts.update(pairs or {(None, None)})
    assert {(r['model'], r['effort']): r['count'] for r in sw.fleet(workers)['models']} == counts
    row = next(w for w in workers['workers'] if int(w['seat']['tokenId']) == 420)
    row['runtimes'] = [dict(id='a', premiumModel=dict(model='same', effort='high')),
                       dict(id='b', premiumModel=dict(model='same', effort='xhigh')),
                       dict(id='c', premiumModel=dict(model='zeta'))]
    live = sw.seat_live(dict(count=1, workers=[row]), 420)
    assert live['advertised_model'] == 'same, same, zeta'
    assert live['advertised_effort'] == 'high, xhigh, —'
    row['runtimes'] = []
    assert sw.seat_live(dict(count=1, workers=[row]), 420)['advertised_model'] is None
    slot = sw.normalize_workers(workers)
    assert sw.coerce_workers_slot(slot) == slot
    slot['workers'][0]['advertised_models'] = [{'model': True, 'effort': None}]
    assert sw.coerce_workers_slot(slot) is None


def test_live_state_keeps_unknown_pause_distinct_from_idle_and_positive_evidence():
    row = capture('workers')['workers'][0]; token=int(row['seat']['tokenId'])
    row.update(working=0, paused=None)
    assert sw.seat_live(dict(count=1, workers=[row]), token)['live_state'] == 'idle'
    row.pop('paused')
    assert sw.seat_live(dict(count=1, workers=[row]), token)['live_state'] is None
    row['working']=1
    assert sw.seat_live(dict(count=1, workers=[row]), token)['live_state'] == 'working'
    assert sw.seat_live(dict(count=0, workers=[]), token)['live_state'] == 'offline'


def test_skill_records_and_health_status_follow_capture_not_constants():
    skills = capture('skills')['skills']; folded={r['skill_id']: r for r in sw.skill_rows(skills)}
    for item in skills:
        row=folded[item['id']]
        assert tuple(row) == SURF_ROW_KEYS['swarm_skill_rows']
        assert row['inference'] == item.get('inference')
        for field in ('attempts','accepted','rejected','pending'):
            value=(item.get('record') or {}).get(field)
            assert row[field] == (None if value is None else int(value))
    assert sw.health_facts(capture('health'))['health_status'] == capture('health')['status']
    assert sw.health_facts(None)['health_status'] is None
    assert sw.health_facts({'status':'unknown-new-state'})['health_status'] == 'unknown-new-state'


@pytest.mark.parametrize('job', ['bad','../x','00000000000000000000000000000000', True, None])
async def test_submissions_refuses_non_uuid_before_any_request(job):
    def dead(request): raise AssertionError('invalid id attempted I/O')
    async with SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(dead))) as client:
        assert await client.submissions(job) is None


async def test_submissions_uses_pool_pacing_and_404_is_one_job_failure():
    payload,_=selected(); seen=[]; sleeps=[]
    async def sleep(delay): sleeps.append(delay)
    def handler(request):
        seen.append(request)
        return httpx.Response(404, text='missing')
    async with SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),sleep=sleep) as client:
        assert await client.submissions(payload['jobId']) is None
    assert len(seen)==1 and len(sleeps)==1 and sleeps[0]==0.12
    assert seen[0].url.path == f"/jobs/{payload['jobId']}/submissions"
    assert seen[0].method=='GET'


@pytest.mark.parametrize('shape', [None, {}, {'submissions': None}, {'submissions': []}])
def test_missing_job_or_submissions_envelope_is_not_a_successful_absence(shape):
    payload,item=selected()
    assert sw.submission_answer(shape,payload['jobId'],item['hash'],420)['state']=='unavailable'


def test_due_answer_order_uses_oldest_attempt_after_all_unread_rows():
    from tests.data.test_surf_manager_answers import work
    rows=sw.seat_work_rows(work(5)); _,_,value=point()
    answers={row['job_id']:{row['submission_hash']:dict(value,terminal=False,read_ts=stamp)}
             for row,stamp in zip(rows,(900,800,700,600,500))}
    answers.pop(rows[2]['job_id'])
    due=sw.answer_jobs_due(rows,answers,now_ts=1000,due_s=120,cap=4)
    assert [job for job,_ in due]==[rows[i]['job_id'] for i in (2,4,3,1)]


async def test_submissions_success_rotates_failed_host_and_preserves_whole_capture():
    payload,_=selected();seen=[];delays=[]
    async def sleep(delay): delays.append(delay)
    def handler(request):
        seen.append(request)
        return httpx.Response(503) if len(seen)==1 else httpx.Response(200,json=payload)
    async with SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),sleep=sleep) as client:
        assert await client.submissions(payload['jobId'])==payload
    assert len(seen)==2 and seen[0].url.host!=seen[1].url.host
    assert delays==[0.12]


def test_multiple_devices_keep_advertised_model_effort_correspondence():
    one=capture('workers')['workers'][0];two=copy.deepcopy(one)
    token=int(one['seat']['tokenId']);two['deviceKey']='second-device'
    one['runtimes']=[dict(id='claude',premiumModel=dict(model='z-model',effort='low'))]
    two['runtimes']=[dict(id='codex',premiumModel=dict(model='a-model',effort='xhigh'))]
    live=sw.seat_live(dict(count=2,workers=[one,two]),token)
    assert (live['advertised_model'],live['advertised_effort'])==('a-model, z-model','xhigh, low')


def test_cached_answers_match_exact_submission_hash_in_both_seat_orders():
    job,key,value=point();other='f'*64
    answers={job:{key:value,other:dict(value,answer='Seat B reply.')}}
    for order in ((key,other),(other,key)):
        rows=[dict(job_id=job,submission_hash=hash_,answer=None,answer_state='not_read',model=None,took_s=None)
              for hash_ in order]
        result=sw.enrich_work_rows(rows,answers)
        assert [row['answer'] for row in result]==[answers[job][hash_]['answer'] for hash_ in order]


@pytest.mark.parametrize(('source','expected'),[
    ('Used "/Users/Alice Smith/private/answer.json". Next.', 'Used "answer.json".'),
    ('Used `/Users/Alice Smith/private/answer.json`. Next.', 'Used answer.json.'),
    (r'Used "C:\Users\Alice Smith\private\answer.json". Next.', 'Used "answer.json".'),
    (r'Used `C:\Users\Alice Smith\private\answer.json`. Next.', 'Used answer.json.'),
])
def test_delimited_absolute_paths_with_spaces_keep_only_basename(source,expected):
    assert sw.answer_sentence(source)==expected
    job,key,value=point();value['answer']=source
    assert sw.coerce_answers_slot({job:{key:value}}) is None


@pytest.mark.parametrize(('source','expected'),[
    ('Used C:/Users/Alice/private/answer.json. Next.', 'Used answer.json.'),
    ('Used "C:/Users/Alice Smith/private/answer.json". Next.', 'Used "answer.json".'),
    ('Used `C:/Users/Alice Smith/private/answer.json`. Next.', 'Used answer.json.'),
])
def test_windows_forward_slash_absolute_paths_keep_only_basename(source,expected):
    assert sw.answer_sentence(source)==expected
    job,key,value=point();value['answer']=source
    assert sw.coerce_answers_slot({job:{key:value}}) is None
