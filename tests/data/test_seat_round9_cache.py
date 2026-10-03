"""Round 9 detail cache: offline transports only, real SQLite and captured API shapes."""
from __future__ import annotations
import asyncio
import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from maxpane_dashboard.data import seat_api as api, seat_models as models
from maxpane_dashboard.data.seat_ledger import SeatLedger
from maxpane_dashboard.data.seat_manager import SeatManager
from maxpane_dashboard.data.seat_log_grammar import classify
from maxpane_dashboard.data.surf_swarm import oracle_point, enrich_panel_rows

ROOT = Path(__file__).parents[1] / 'fixtures/seat/api/r9'
JOB = '4003eaef-7083-421d-b60c-f2ddc584b84a'
HASH = 'a' * 64
NOW = 1791046800.0

def body(name):
    return json.loads((ROOT / name).read_text())

def job_body():
    return body('api-2026-10-03-job-4003eaef-research-paid.json')

def work(job=JOB, digest=HASH, at='2026-10-03T12:00:00.000Z', **extra):
    return dict(jobId=job, submissionHash=digest, submittedAt=at, acceptedAt=at,
                objective='short sentence', status='accepted', jobState='completed', nodeKey='research_report',
                role='implement', launch=None, **extra)

def subs(reply='[literal]\nsecond line', digest=HASH):
    return {'jobId': JOB, 'count': 1, 'submissions': [{'hash': digest, 'seat': {'tokenId':'3','agentId':'52082'},
            'nodeKey':'research_report', 'role':'implement', 'outcome':'completed', 'accepted':True,
            'summary':reply, 'createdAt':'2026-10-03T12:00:00Z', 'usage':{'model':'api model','turns':6,'outputTokens':10250,'wallClockMs':55000},
            'verdict':{'status':'accepted','detail':'structural '+ 'z'*600,'secret':'discard'}, 'artifacts':[], 'findings':[]}]}

class Clock:
    def __init__(self): self.now = NOW
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds

def client(handler, clock=None):
    async def no_sleep(_): pass
    return api.SeatApiClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), now=clock or (lambda:NOW), sleep=no_sleep)

def ledger(tmp_path, seat=3):
    return SeatLedger(tmp_path/'ledger.sqlite',seat=seat,now=lambda:NOW)

async def test_routes_project_nested_fields_keep_only_own_reply_and_parse_controls(tmp_path):
    raw=subs('masked sk-svcac******** [literal]\nline\x01\x1b[31m')
    raw['submissions'].append(dict(raw['submissions'][0], seat={'tokenId':'4'}, summary='foreign reply'))
    raw['secret']='discard';job=job_body();job['objective']='[literal]\nfull objective';job['launch']['secret']='discard'
    requests=[]
    def handler(req):
        requests.append(str(req.url))
        payload=raw if req.url.path.endswith('/submissions') else job
        return httpx.Response(200, content=json.dumps(payload).replace('\\u0001','\x01'))
    c=client(handler)
    result=await c.job_submissions(JOB,seat=3)
    assert len(result.data['submissions'])==1
    row=result.data['submissions'][0]
    assert row['reply'].startswith('masked sk-[redacted] [literal]\nline')
    assert '\x01' not in json.dumps(result.data) and 'secret' not in json.dumps(result.data)
    assert len(row['structuralCheck']['detail'])==512 and row['structuralCheck']['detail'].endswith('…')
    detail=await c.job_detail(JOB)
    assert detail.data['objective']=='[literal]\nfull objective'
    assert detail.data['paid'] is True and detail.data['paidBy']==job['paidBy']
    assert detail.data['launch']['requested'] is False
    assert detail.data['delivery']=={'url':job['delivery']['repoUrl'],'atUtc':job['delivery']['deliveredAt']}
    assert detail.data['nodes'][0]['seatTokenId']==3
    assert 'secret' not in json.dumps(detail.data)
    await c.close()

@pytest.mark.parametrize('name,paid,linked',[
 ('api-2026-10-03-job-4003eaef-research-paid.json',True,False),
 ('api-2026-10-03-job-5692e031-oracle-unpaid.json',False,False),
 ('api-2026-10-03-job-86c76df1-dag-workflow-launch.json',True,True),
 ('job_missing_payer_synthetic.json',None,False)])
async def test_real_job_payer_three_states_and_launch_objects(name,paid,linked):
    raw=body(name); c=client(lambda req:httpx.Response(200,json=raw))
    r=await c.job_detail(raw['id'])
    assert r.data['paid'] is paid and r.data['launchLinked'] is linked
    await c.close()

async def test_oracle_full_hash_join_agrees_with_surf_and_keeps_literal_text():
    raw=body('oracle_hit.json'); h='b'*64;raw['members'][0]['submissionHash']=h
    raw['agreement']['cluster']=[h];raw['members'].insert(0,dict(raw['members'][0],submissionHash=h[:12]+'c'*52,answer={'answer':'WRONG'}))
    raw['question']='[question]\nline';raw['members'][1]['answer']['notes']='[notes]\nline'
    point=oracle_point(raw,raw['jobId'],h,now_ts=NOW)
    surf=enrich_panel_rows([{'job_id':raw['jobId'],'submission_hash':h,'node_key':'oracle_assess'}],{raw['jobId']:{h:point}},('oracle_assess',))[0]
    requests=[]
    def handler(req): requests.append(req); return httpx.Response(200,json=raw)
    c=client(handler); r=await c.oracle_request(raw['id'],job_id=raw['jobId'],submission_hash=h)
    assert requests[0].url.params['members']==h
    assert r.data['panel']['state']==surf['panel_state']=='no_quorum_in'
    assert r.data['panel']['agreed']==surf['panel_agreed']
    assert r.data['question']=='[question]\nline' and r.data['notes']=='[notes]\nline'
    assert r.data['answer']=='0' and h not in json.dumps(r.data) and 'cluster' not in json.dumps(r.data)
    await c.close()

@pytest.mark.parametrize('order',['plane_first','local_first'])
def test_work_inserts_plane_rows_then_merges_local_hash_without_duplicates(tmp_path,order):
    l=ledger(tmp_path)
    lines=['2026-10-03T11:59:00.000Z accepted implement 12345678 — artifacts/answer.json (max 60 turns)',
           '2026-10-03T12:00:00.000Z submitted implement for 12345678',
           '2026-10-03T12:00:00.100Z submission stored (aaaaaaaaaaaa) — awaiting verdict']
    if order=='plane_first': l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    l.ingest([classify(x) for x in lines])
    if order=='local_first': l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    rows=l.record_rows()
    assert len(rows)==1 and rows[0]['source']['row']=='local'
    assert rows[0]['submissionHash']==HASH and rows[0]['jobState']=='completed'
    assert rows[0]['outcome']=='accepted' and rows[0]['nodeId8']=='12345678'
    l.close()

async def cache_job(l,raw=None):
    raw=raw or job_body();c=client(lambda req:httpx.Response(200,json=raw));r=await c.job_detail(raw['id']);l.store_job_detail(raw['id'],r);await c.close()

async def cache_subs(l,raw=None,job=JOB):
    c=client(lambda req:httpx.Response(200,json=raw or subs()));r=await c.job_submissions(job,seat=3);l.store_submissions(job,r);await c.close()

@pytest.mark.parametrize('case', ['detail_kind_only', 'work_kind', 'requested', 'workflow'])
async def test_launch_linkage_uses_work_kind_provenance_in_cache_and_node_count(tmp_path, case):
    from maxpane_dashboard.analytics.seat_records import node_rows
    raw=job_body();raw['launch'].update(kind='evm_project',requested=case=='requested')
    raw['workflow']={'id': 'workflow'} if case=='workflow' else None
    row=work()
    if case=='work_kind': row['launch']={'kind': 'evm_project'}
    assert api.normalise_job_detail(raw)['launchLinked'] is (case in ('requested', 'workflow'))
    l=ledger(tmp_path);l.attach_work([row],as_of_utc='2026-10-03T12:01:00Z')
    await cache_job(l,raw)
    detail=l.task_detail(l.rows()[0]['key'])
    linked=case!='detail_kind_only'
    assert (detail['launchLinked'],node_rows([detail])[0]['launch'])==(linked,int(linked))
    l.close()

async def test_masked_reply_and_100kb_cap_are_sanitized_before_sqlite(tmp_path):
    l=ledger(tmp_path);l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    reply='sk-svcac******** eyJ'+'YWJjZGVm'*15+' abc.def.ghi\x01 [literal]\n'+('q'*100000)
    await cache_job(l);await cache_subs(l,subs(reply))
    d=l.task_detail(l.rows()[0]['key'])
    assert len(d['reply'])==4096 and d['reply'].endswith('…')
    assert 'sk-svcac' not in d['reply'] and 'eyJ' not in d['reply'] and '\x01' not in d['reply']
    assert '[literal]\n' in d['reply'] and len(d['structuralCheck']['detail'])==512
    assert l.rows()[0]['objective']=='short sentence'
    assert len(d['objective'])>160
    dump='\n'.join(l._conn.iterdump())
    assert 'sk-svcac' not in dump and 'eyJ' not in dump and '"secret"' not in dump
    l.close()

async def test_retention_401st_expires_text_but_preserves_structure(tmp_path):
    l=ledger(tmp_path)
    old=work(at='2026-09-01T00:00:00.000Z');l.attach_work([old],as_of_utc='2026-10-03T12:01:00Z')
    key=l.rows()[0]['key'];await cache_job(l);await cache_subs(l)
    newer=[]
    for i in range(400):
        w=work(job=f'{i:08x}-0000-4000-8000-000000000000',digest=f'{i+1:064x}',at=f'2026-10-03T12:{i//60:02d}:{i%60:02d}.000Z')
        newer.append(w)
    l.attach_work(newer,as_of_utc='2026-10-03T12:10:00Z')
    l.prune_detail_text()
    d=l.task_detail(key)
    assert d['reply'] is None and d['objective'] is None and d['replyState']=='text expired'
    assert d['paid'] is True and d['template'] is not None and d['outcome']=='accepted'
    assert l.detail_due('submissions',JOB,NOW+9999) is False
    l.close()

@pytest.mark.parametrize('case',['valid','ambiguous_nodes','ambiguous_attempts','oracle','review_verifier','review_accepted','other_state'])
async def test_fallback_requires_unique_attempt_and_uses_node_state(tmp_path,case):
    raw=job_body();l=ledger(tmp_path)
    # API-seeded row is changed to represent a local row whose work verdict is still unread.
    l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    l._conn.execute("UPDATE tasks SET outcome=NULL, source_outcome='none', work_status=NULL")
    if case=='ambiguous_nodes': raw['nodes'].append(dict(raw['nodes'][0],key='second'))
    if case=='ambiguous_attempts':
        l.attach_work([work(digest='c'*64,at='2026-10-03T12:00:01.000Z')],as_of_utc='2026-10-03T12:01:00Z')
        l._conn.execute("UPDATE tasks SET outcome=NULL, source_outcome='none', work_status=NULL")
    if case=='oracle': raw['oracleRequestId']='5692e031-4efa-46f3-b2d6-b7e4433fb583'
    if case=='review_verifier': raw['nodes'][0].update(role='review',state='working',verdict={'status':'accepted'})
    if case=='review_accepted': raw['nodes'][0].update(role='review',state='accepted',verdict=None)
    if case=='other_state': raw['nodes'][0]['state']='completed'
    if case=='ambiguous_nodes': l._conn.execute('UPDATE tasks SET node_key=NULL')
    l._conn.commit();await cache_job(l,raw)
    expected='accepted' if case in ('valid','review_accepted') else None
    assert all(r['outcome']==expected for r in l.rows())
    if expected:
        assert l.rows()[0]['source']['outcome']=='job node state'
        assert l.today('2026-10-03')['accepted']==1
        l.attach_work([dict(work(),status='rejected')],as_of_utc='2026-10-03T12:03:00Z')
        assert l.rows()[0]['outcome']=='rejected' and l.today('2026-10-03')['accepted']==0
    l.close()

def test_f4de533_schema_forward_and_rollback_open(tmp_path):
    # Execute the actual historical module in an isolated namespace; no checkout and no home data.
    source=subprocess.check_output(['git','show','f4de533:maxpane_dashboard/data/seat_ledger.py'],text=True)
    import types
    old=types.ModuleType('seat_ledger_rollback');sys.modules[old.__name__]=old;exec(compile(source,'f4de533/seat_ledger.py','exec'),old.__dict__)
    path=tmp_path/'compat.sqlite';before=old.SeatLedger(path,seat=3,now=lambda:NOW)
    before.seed_api_rows([work()],seat=3);before.close()
    new=SeatLedger(path,seat=3,now=lambda:NOW)
    assert new.counts()['rows']==1 and new.meta_get('schema_version')==1
    assert new.record_rows()[0]['jobId']==JOB
    projected=api.normalise_job_detail(job_body())
    new.store_job_detail(JOB,api.ApiResult(True,projected,200,'2026-10-03T12:02:00Z',None,0,f'/jobs/{JOB}'))
    assert new.task_detail(new.rows()[0]['key'])['paid'] is True
    new.attach_work([work(digest='c'*64,at='2026-10-03T12:01:00.000Z')],as_of_utc='2026-10-03T12:02:00Z');new.close()
    after=old.SeatLedger(path,seat=3,now=lambda:NOW)
    assert after.counts()['rows']==2 and after.meta_get('schema_version')==1
    after.close()

async def cycle(m):
    result=await m.fetch_and_compute();await m.settle();return result

def manager(tmp_path,c,clock):
    m=SeatManager(api=c,seat=3,maxpane_dir=tmp_path,now=clock)
    # Irrelevant host/broker/live tiers are held; detail reads remain real.
    for tier in m._due_at:
        if tier != 'details': m._due_at[tier]=float('inf')
    return m

async def test_manager_combined_budget_selection_cadence_and_terminal_cache(tmp_path):
    clock=Clock();requests=[]
    def handler(req):
        requests.append(req.url.path)
        return httpx.Response(200,json=subs() if req.url.path.endswith('/submissions') else job_body())
    c=client(handler,clock);m=manager(tmp_path,c,clock)
    m._ledger.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    await cycle(m)
    assert requests==[f'/jobs/{JOB}',f'/jobs/{JOB}/submissions']
    await cycle(m);assert len(requests)==2
    flat=await m.fetch_and_compute()
    assert flat['seat_jobs'][0]['reply']=='[literal]\nsecond line'
    assert flat['seat_records_rows'][0]['answerPreview']=='[literal]'
    assert flat['seat_nodes_all_rows'][0]['paid']==1 and flat['seat_nodes_all_rows'][0]['launch']==0
    assert job_body()['paidBy'] not in json.dumps(m.document()) and HASH not in json.dumps(m.document())
    assert m.cached_task_detail(m._ledger.rows()[0]['key'])['reply']=='[literal]\nsecond line'
    await m.close();await c.close()

async def test_offline_has_no_detail_requests_and_serves_cache(tmp_path):
    l=ledger(tmp_path);l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z');await cache_job(l);await cache_subs(l)
    def forbidden(req):raise AssertionError('offline request')
    c=client(forbidden);m=SeatManager(api=c,offline=True,ledger=l,seat=3,maxpane_dir=tmp_path,now=lambda:NOW)
    flat=await cycle(m)
    assert flat['seat_records_rows'][0]['outcome']=='accepted'
    assert flat['seat_jobs'][0]['reply']=='[literal]\nsecond line'
    await m.close();await c.close();l.close()

async def test_selected_records_window_and_nodes_only_missing_newest400(tmp_path):
    clock=Clock();requests=[]
    def handler(req):
        requests.append(req.url.path)
        data=job_body();data['id']=req.url.path.split('/')[2]
        return httpx.Response(200,json=data if not req.url.path.endswith('/submissions') else {'submissions':[]})
    c=client(handler,clock);m=manager(tmp_path,c,clock)
    newer=[]
    for i in range(402):
        newer.append(work(job=f'{i:08x}-0000-4000-8000-000000000000',digest=f'{i+1:064x}',at=f'2026-10-03T12:{i//60:02d}:{i%60:02d}.000Z'))
    m._ledger.attach_work(newer,as_of_utc='2026-10-03T12:10:00Z')
    await cycle(m);assert len(requests)==2
    await cycle(m);assert len(requests)==2,'SEAT does not hydrate historical records'
    m.select_dashboard('RECORDS');m.set_record_window(40,open_only=True)
    await cycle(m);assert len(requests)==2,'completed filter is applied before the window'
    m.set_record_window(40,open_only=False)
    await cycle(m);assert len(requests)==4 and '00000190' in requests[-2]
    m.select_dashboard('NODES')
    before=len(requests);await cycle(m)
    assert len(requests)-before==2 and all(not r.endswith('/submissions') for r in requests[before:])
    m.select_dashboard('SEAT');before=len(requests);await cycle(m);assert len(requests)==before
    # Simulate an already hydrated newest-400 window; older structured history is deliberately unread.
    for row in m._ledger.record_rows(limit=400):
        m._ledger._conn.execute('INSERT OR REPLACE INTO job_details VALUES (?,?,?)',
                               (row['jobId'],json.dumps({'jobId':row['jobId'],'paid':False}),'2026-10-03T12:10:00Z'))
        m._ledger._conn.execute('INSERT OR REPLACE INTO detail_reads VALUES (?,?,?,?,?,?,?,?,?)',
                               ('job',row['jobId'],'read',None,'2026-10-03T12:10:00Z',NOW,0,0,1))
    m._ledger._conn.commit();m.select_dashboard('NODES')
    await cycle(m);assert len(requests)==before, 'NODES never hydrates the 401st/402nd records'
    await m.close();await c.close()

async def test_busy_class_floor_does_not_spend_budget_or_count_skipped_failures(tmp_path):
    clock=Clock();requests=[];busy=True
    def handler(req):
        if req.url.path.startswith('/seats/'):
            return httpx.Response(200,json={})
        requests.append(req.url.path)
        if busy and not req.url.path.endswith('/submissions'):return httpx.Response(503,json={'error':'busy'})
        return httpx.Response(200,json=subs() if req.url.path.endswith('/submissions') else job_body())
    c=client(handler,clock);m=manager(tmp_path,c,clock);m._ledger.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    await cycle(m);assert len(requests)==2,'one busy job request plus submissions'
    assert m._ledger.detail_read('job',JOB)['reason']=='busy'
    failures=m._failures['reasons'];m.plan_open=True;m.bump('standing',0)
    await cycle(m);assert len(requests)==2 and m._failures['reasons']==failures
    flat=await m.fetch_and_compute()
    assert flat['seat_records_rows'][0]['outcome']=='accepted'
    assert flat['seat_nodes_all_rows'][0]['attempts']==1
    assert flat['seat_jobs'][0]['reply']=='[literal]\nsecond line'
    assert m._ledger.detail_read('job',JOB)['reason']=='busy'
    await m.settle()
    clock.advance(59);await cycle(m);assert len(requests)==2
    clock.advance(1);await cycle(m);assert len(requests)==3
    busy=False;clock.advance(119);await cycle(m);assert len(requests)==3
    clock.advance(1);await cycle(m);assert len(requests)==4 and c.pause_until('job')==0
    flat=await m.fetch_and_compute()
    assert flat['seat_records_rows'][0]['outcome']=='accepted'
    assert flat['seat_nodes_all_rows'][0]['attempts']==1
    await m.close();await c.close()

async def test_submissions_wait60_after_stored_and_failures_backoff(tmp_path):
    clock=Clock();requests=[];ok=False
    def handler(req):
        requests.append((clock(),req.url.path))
        if req.url.path.endswith('/submissions') and not ok:return httpx.Response(500,json={})
        return httpx.Response(200,json=subs() if req.url.path.endswith('/submissions') else job_body())
    c=client(handler,clock);m=manager(tmp_path,c,clock)
    from datetime import datetime,timezone
    stamp=datetime.fromtimestamp(NOW,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    m._ledger.attach_work([work(at=stamp)],as_of_utc=stamp)
    await cycle(m);assert len(requests)==1
    clock.advance(59);await cycle(m);assert len(requests)==1
    clock.advance(1);await cycle(m);assert len(requests)==3,'regular 500 retries once'
    clock.advance(59);await cycle(m);assert len(requests)==3
    clock.advance(1);await cycle(m);assert len(requests)==5
    ok=True;clock.advance(119);await cycle(m);assert len(requests)==5
    clock.advance(1);await cycle(m);assert len(requests)==6
    clock.advance(1000);await cycle(m);assert len(requests)==6
    await m.close();await c.close()

def test_node_aggregates_keep_unread_payer_unknown_and_local_medians():
    from maxpane_dashboard.analytics.seat_records import node_rows
    rows=[dict(nodeKey='oracle_assess',role='implement',outcome='accepted',source={'row':'local'},durationS=10,tokens={'output':100},detailRead=False,paid=None,launchLinked=False,submittedUtc='2026-10-03T12:00:00Z'),
          dict(nodeKey='oracle_assess',role='implement',outcome='pending',source={'row':'api'},durationS=900,tokens={'output':900},detailRead=False,paid=None,launchLinked=False,submittedUtc='2026-10-03T12:01:00Z')]
    node=node_rows(rows)[0]
    assert (node['attempts'],node['accepted'],node['pending'],node['acceptedPercent'])==(2,1,1,50)
    assert node['paid'] is None and node['launch'] is None and node['detailsRead']==0
    assert node['durationP50S']==10 and node['outputTokensP50']==100
    rows[1].update(detailRead=True,paid=False,launchLinked=True)
    node=node_rows(rows)[0];assert (node['paid'],node['launch'],node['detailsRead'])==(0,1,1)


def test_job_contract_exposes_failure_enum_and_check_evaluation():
    doc=models.shape_dashboard_document({'jobs':[{'jobId':JOB,'failureReason':'runtime_error','structuralCheck':{'status':'accepted','evaluation':'structural','detail':'paths verified'}}]})
    assert doc['jobs'][0]['failureReason']=='runtime_error'
    assert doc['jobs'][0]['structuralCheck']['evaluation']=='structural'

async def test_new_attempt_can_read_after_earlier_terminal_submission(tmp_path):
    l=ledger(tmp_path);l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z');await cache_subs(l)
    l.attach_work([work(digest='d'*64,at='2026-10-03T12:04:00.000Z')],as_of_utc='2026-10-03T12:05:00Z')
    assert l.detail_due('submissions',JOB,NOW)
    l.close()

async def test_null_text_is_unavailable_and_orphan_reply_is_not_retained(tmp_path):
    l=ledger(tmp_path);l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z');await cache_subs(l,subs(None))
    row=l.task_detail(l.rows()[0]['key'])
    assert row['replyState']=='unavailable' and row['replyReason']=='reply absent'
    raw=subs('orphan text',digest='e'*64)
    await cache_subs(l,raw)
    dump='\n'.join(l._conn.iterdump())
    assert 'orphan text' not in dump
    l.close()

async def test_ledger_sanitizes_raw_projected_reply_at_storage_boundary(tmp_path):
    l=ledger(tmp_path);l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    projected=api.normalise_submission(subs()['submissions'][0],keep_reply=True)
    projected['reply']='masked sk-svcac******** '+('Q'*100000)
    result=api.ApiResult(True,{'submissions':[projected]},200,'2026-10-03T12:02:00Z',None,0,'/jobs/test/submissions')
    l.store_submissions(JOB,result)
    saved=l.task_detail(l.rows()[0]['key'])['reply']
    assert 'sk-svcac' not in saved and len(saved)==4096 and saved.endswith('…')
    l.close()

async def test_real_oracle_and_dag_ambiguity_do_not_supply_attempt_verdict(tmp_path):
    for name,seat in [('api-2026-10-03-job-5692e031-oracle-unpaid.json',398),('api-2026-10-03-job-86c76df1-dag-workflow-launch.json',2)]:
        path=tmp_path/str(seat);path.mkdir();l=ledger(path,seat);raw=body(name)
        row=work(job=raw['id']);row['nodeKey']=None
        l.attach_work([row],as_of_utc='2026-10-03T12:01:00Z')
        l._conn.execute("UPDATE tasks SET source_outcome='none',outcome=NULL,work_status=NULL");l._conn.commit()
        await cache_job(l,raw);assert l.rows()[0]['outcome'] is None;l.close()

async def test_three_running_jobs_get_immediate_standing_question_then_full_cache(tmp_path):
    clock=Clock();requests=[]
    jobs=[f'{i:08x}-0000-4000-8000-000000000000' for i in (1,2,3)]
    running=[dict(jobId=job,nodeKey='research_report',role='implement',objective='standing question '+str(i),since=f'2026-10-03T12:00:0{i}Z') for i,job in enumerate(jobs)]
    def handler(req):
        requests.append(req.url.path)
        raw=job_body();raw.update(id=req.url.path.split('/')[2],state='working',objective='[FULL]\nquestion')
        return httpx.Response(200,json=raw)
    c=client(handler,clock);m=manager(tmp_path,c,clock)
    m._land('standing',{'running':running,'working':3},clock())
    flat=await m.fetch_and_compute()
    assert [r['jobId'] for r in flat['seat_current_jobs']]==jobs[::-1]
    assert flat['seat_jobs'][0]['objective']=='standing question 2'
    await m.settle();assert requests==[f'/jobs/{jobs[2]}',f'/jobs/{jobs[1]}']
    flat=await m.fetch_and_compute();assert flat['seat_jobs'][0]['objective']=='[FULL]\nquestion'
    await m.settle();assert requests[-1]==f'/jobs/{jobs[0]}'
    await m.close();await c.close()

async def test_busy_success_restores_nonterminal_detail_cadence(tmp_path):
    clock=Clock();requests=[]
    def handler(req):
        requests.append(clock())
        if len(requests)==1:return httpx.Response(503,json={'error':'busy'})
        return httpx.Response(200,json=dict(job_body(),state='working'))
    c=client(handler,clock);m=manager(tmp_path,c,clock)
    m._land('standing',{'running':[dict(jobId=JOB,since='2026-10-03T12:00:00Z')]},clock())
    await cycle(m);clock.advance(60);await cycle(m)
    assert requests==[NOW,NOW+60]
    clock.advance(59);await cycle(m);assert len(requests)==2
    clock.advance(1);await cycle(m);assert requests[-1]==NOW+120
    await m.close();await c.close()

async def test_submission_reasons_attach_to_exact_attempt_hash_not_creation_proximity(tmp_path):
    l=ledger(tmp_path)
    l.attach_work([dict(work(),status='failed'),dict(work(digest='f'*64,at='2026-10-03T12:01:00.000Z'),status='failed')],as_of_utc='2026-10-03T12:02:00Z')
    raw=subs();first=raw['submissions'][0];first.update(outcome='failed',failureReason='runtime_error')
    second=copy.deepcopy(first);second.update(hash='f'*64,failureReason='path_violation')
    raw['submissions'].append(second)
    await cache_subs(l,raw)
    reasons={r['hash12']:r['failureReason'] for r in l.rows()}
    assert reasons=={'a'*12:'runtime_error','f'*12:'path_violation'}
    l.close()

async def test_oracle_third_route_shares_budget_and_cached_fields_reach_job(tmp_path):
    raw=body('oracle_hit.json');raw['members'][0]['submissionHash']=HASH;raw['agreement']['cluster']=[HASH]
    job=raw['jobId'];request_id=raw['id'];requests=[];clock=Clock()
    detail=dict(job_body(),id=job,oracleRequestId=request_id)
    submission=subs();submission['jobId']=job
    def handler(req):
        requests.append(req.url.path)
        payload=raw if req.url.path.startswith('/oracle/') else submission if req.url.path.endswith('/submissions') else detail
        return httpx.Response(200,json=payload)
    c=client(handler,clock);m=manager(tmp_path,c,clock)
    row=work(job=job);row.update(nodeKey='oracle_assess',status='pending')
    m._ledger.attach_work([row],as_of_utc='2026-10-03T12:01:00Z')
    await cycle(m);assert requests==[f'/jobs/{job}',f'/jobs/{job}/submissions']
    await cycle(m);assert requests[-1]==f'/oracle/requests/{request_id}' and len(requests)==3
    flat=await cycle(m);assert len(requests)==3
    shown=flat['seat_jobs'][0]
    assert shown['oracleAnswer']=='0' and shown['panel']['state']=='no_quorum_in'
    assert shown['oracleQuestion']==raw['question'] and shown['outcome']=='pending'
    assert HASH not in json.dumps(m.document())
    await m.close();await c.close()

async def test_local_running_job_uses_standing_objective_before_detail(tmp_path):
    clock=Clock();c=client(lambda req:httpx.Response(503,json={'error':'busy'}),clock);m=manager(tmp_path,c,clock)
    m.feed_lines(['2026-10-03T12:00:00.000Z accepted implement 12345678 — answer (max 60 turns)'])
    m._ledger.attach_work_dirs([dict(jobId=JOB,nodeId='12345678-0000-4000-8000-000000000000',mtimeUtc='2026-10-03T12:00:00.000Z')])
    m._land('standing',{'running':[dict(jobId=JOB,nodeKey='research_report',objective='standing first question',since='2026-10-03T11:59:58Z')]},clock())
    flat=await m.fetch_and_compute()
    assert len(flat['seat_current_jobs'])==1 and flat['seat_jobs'][0]['objective']=='standing first question'
    await m.settle();await m.close();await c.close()

async def test_real_oracle_submission_preserves_result_separate_from_structural_check(tmp_path):
    raw=body('submissions_oracle.json');first=raw['submissions'][0];seat=int(first['seat']['tokenId'])
    c=client(lambda req:httpx.Response(200,json=raw));result=await c.job_submissions(raw['jobId'],seat=seat)
    item=result.data['submissions'][0]
    assert item['structuralCheck']['status']=='accepted' and item['oracleResult']['status']=='rejected'
    l=ledger(tmp_path,seat);w=work(job=raw['jobId'],digest=first['hash']);w['status']='pending'
    l.attach_work([w],as_of_utc='2026-10-03T12:01:00Z');l.store_submissions(raw['jobId'],result)
    cached=l.task_detail(l.rows()[0]['key'])
    assert cached['oracleResult']['status']=='rejected' and cached['outcome']=='pending'
    assert cached['artifactsCount']==1 and cached['findingsCount']==0
    l.close();await c.close()

async def test_failed_node_fallback_keeps_failure_enum_for_job(tmp_path):
    l=ledger(tmp_path);raw=job_body();raw['nodes'][0].update(state='failed',failureReason='runtime_error')
    l.attach_work([work()],as_of_utc='2026-10-03T12:01:00Z')
    l._conn.execute("UPDATE tasks SET outcome=NULL,source_outcome='none',work_status=NULL");l._conn.commit()
    await cache_job(l,raw)
    detail=l.task_detail(l.rows()[0]['key'])
    assert detail['outcome']=='failed' and detail['failureReason']=='runtime_error'
    assert detail['source']['reason']=='job node state'
    l.close()

async def test_oracle_address_array_answer_uses_shared_typed_representation():
    raw=body('oracle_hit.json');raw['members'][0]['submissionHash']=HASH;raw['agreement']['cluster']=[HASH]
    addresses=['0x'+'1'*40,'0x'+'2'*40];raw['answerType']='address[]';raw['members'][0]['answer']['answer']=addresses
    c=client(lambda req:httpx.Response(200,json=raw))
    result=await c.oracle_request(raw['id'],job_id=raw['jobId'],submission_hash=HASH)
    assert result.data['answer']==' '.join(addresses)
    assert result.data['answer']==oracle_point(raw,raw['jobId'],HASH,now_ts=NOW)['seat_answer']
    await c.close()
