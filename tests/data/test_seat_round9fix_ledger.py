"""Round 9 fix packages 2/6/11: real SQLite, captured jobs, compositor."""
import pytest

from maxpane_dashboard.analytics.seat_records import node_rows, record_window
from maxpane_dashboard.data import seat_api as api
from maxpane_dashboard.data.seat_log_grammar import classify
from maxpane_dashboard.widgets.seat import SeatRecords
from tests.data.test_seat_round9_cache import body, ledger, work, JOB, HASH
from tests.widgets.test_seat_hero import composite_lines

AS_OF = '2026-10-03T12:02:00Z'


def store_job(l, raw):
    l.store_job_detail(raw['id'], api.ApiResult(True, api.normalise_job_detail(raw), 200,
                                              AS_OF, None, 0, '/jobs/fixture'))


def unread(l, raw, *, node_key=None):
    l.seed_api_rows([dict(work(job=raw['id']), nodeKey=node_key)], seat=3)
    l._conn.execute("UPDATE tasks SET outcome=NULL,source_outcome='none',work_status=NULL,job_state=NULL")
    l._conn.commit()


def chain():
    return body('api-2026-10-03-job-03810410-chain.json')


@pytest.mark.parametrize('first,second,want', [
    ('failed', 'accepted', 'failed'), ('accepted', 'failed', 'accepted'),
    ('rejected', 'accepted', 'rejected'), ('pending', 'accepted', None),
])
def test_fallback_reassignment_preserves_terminal_and_releases_pending(tmp_path, first, second, want):
    l = ledger(tmp_path)
    raw = chain()
    unread(l, raw)
    raw['nodes'][0].update(seat={'tokenId': '3'}, state=first, failureReason='timeout')
    store_job(l, raw)
    assert l.rows()[0]['outcome'] == first
    raw['nodes'][0].update(seat={'tokenId': '721'}, state=second)
    store_job(l, raw)
    row = l.record_rows()[0]
    assert row['outcome'] == want
    if first == 'failed':
        assert row['failureReason'] == 'timeout'
    if first == 'pending':
        assert row['source']['outcome'] == 'none'
        assert l.today('2026-10-03')['pending'] == 0
    l.close()


def test_fallback_first_read_with_known_foreign_node_stays_unknown(tmp_path):
    l = ledger(tmp_path)
    raw = chain()
    unread(l, raw, node_key=raw['nodes'][0]['key'])
    store_job(l, raw)
    assert l.record_rows()[0]['outcome'] is None
    assert l.record_rows()[0]['jobState'] is None
    l.close()


@pytest.mark.parametrize('reason_source,want', [('job node state', None), ('submissions', 'timeout')])
def test_fallback_clears_only_its_own_reason_group(tmp_path, reason_source, want):
    l = ledger(tmp_path)
    raw = chain()
    unread(l, raw)
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='failed', failureReason='timeout')
    store_job(l, raw)
    l.attach_reason(raw['id'], reason='timeout', failure_class='runtime', source=reason_source)
    raw['nodes'][0]['state'] = 'accepted'
    store_job(l, raw)
    row = l.rows()[0]
    assert row['outcome'] == 'accepted'
    assert row['failureReason'] == want
    assert row['failureClass'] == (None if want is None else 'runtime')
    assert row['source']['reason'] == (None if want is None else reason_source)
    l.close()


def test_dag_known_key_still_narrows_this_seats_three_nodes(tmp_path):
    l = ledger(tmp_path, seat=2)
    raw = body('api-2026-10-03-job-86c76df1-dag-workflow-launch.json')
    own = [n for n in raw['nodes'] if n.get('seat', {}).get('tokenId') == '2']
    assert len(own) == 3
    key = own[0]['key']
    l.seed_api_rows([dict(work(job=raw['id']), nodeKey=key)], seat=2)
    l._conn.execute("UPDATE tasks SET outcome=NULL,source_outcome='none',work_status=NULL,job_state=NULL")
    l._conn.commit()
    own[0]['state'] = 'accepted'
    store_job(l, raw)
    assert l.rows()[0]['outcome'] == 'accepted'
    l.close()


async def test_fallback_accepted_record_paints_job_state_and_completed_filter(tmp_path):
    l = ledger(tmp_path)
    raw = chain()
    unread(l, raw)
    raw['state'] = 'running'
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='accepted')
    store_job(l, raw)
    rows = l.record_rows()
    text = '\n'.join(await composite_lines(SeatRecords, (132, 12), seat_records_rows=rows))
    assert 'running' in text
    assert len(record_window(rows, 40, True)) == 1
    raw['state'] = 'completed'
    store_job(l, raw)
    rows = l.record_rows()
    text = '\n'.join(await composite_lines(SeatRecords, (132, 12), seat_records_rows=rows))
    assert 'completed' in text
    assert record_window(rows, 40, True) == []
    # The seat-work row becomes authoritative; future details cannot rewrite it.
    l.attach_work([dict(work(job=raw['id']), jobState='working')], as_of_utc=AS_OF)
    store_job(l, raw)
    assert l.record_rows()[0]['jobState'] == 'working'
    l.close()


@pytest.mark.parametrize('case', ['dag', 'oracle', 'cancelled', 'local_fail', 'pre_agent', 'interrupted'])
def test_unknown_attempt_never_inherits_completed_job_state(tmp_path, case):
    l = ledger(tmp_path, seat=2 if case == 'dag' else 3)
    raw = (body('api-2026-10-03-job-86c76df1-dag-workflow-launch.json') if case == 'dag' else chain())
    raw['state'] = 'completed'
    if case == 'dag':
        l.seed_api_rows([dict(work(job=raw['id']), nodeKey=None)], seat=2)
        l._conn.execute("UPDATE tasks SET outcome=NULL,source_outcome='none',work_status=NULL,job_state=NULL")
    else:
        unread(l, raw)
        raw['nodes'][0].update(seat={'tokenId': '3'}, state='accepted')
        if case == 'oracle':
            raw['oracleRequestId'] = 'fixture-oracle'
        elif case == 'cancelled':
            l._conn.execute("UPDATE tasks SET cancelled='superseded'")
        elif case == 'local_fail':
            l._conn.execute("UPDATE tasks SET phases_json='[\"failed\"]'")
        elif case == 'pre_agent':
            l._conn.execute("UPDATE tasks SET pre_agent_failure=1")
        else:
            l._conn.execute("UPDATE tasks SET interrupted_by_restart=1")
    l._conn.commit()
    store_job(l, raw)
    rows = l.record_rows()
    assert rows[0]['outcome'] is None
    assert rows[0]['jobState'] is None
    assert len(record_window(rows, 40, True)) == 1
    l.close()


def local_closed(l):
    l.ingest([classify(s) for s in [
        '2026-10-03T11:59:00.000Z accepted implement 12345678 — artifacts/answer.json (max 60 turns)',
        '2026-10-03T12:00:00.000Z submitted implement for 12345678',
    ]])
    l.attach_work_dirs([dict(jobId=JOB, nodeId='12345678-0000-4000-8000-000000000000',
                             mtimeUtc='2026-10-03T11:59:00Z')])
    return next(r['key'] for r in l.rows() if r['source']['row'] == 'local')


def stored(l):
    l.ingest([classify('2026-10-03T12:00:00.100Z submission stored (aaaaaaaaaaaa) — awaiting verdict')])


@pytest.mark.parametrize('api_status,local_reason,api_reason,want,want_reason,source', [
    ('accepted', 'timeout', None, 'accepted', None, None),
    ('unknown', 'timeout', None, 'failed', 'timeout', 'job node state'),
    ('failed', None, 'runtime_error', 'failed', 'runtime_error', 'submissions'),
    ('failed', 'timeout', 'runtime_error', 'failed', 'runtime_error', 'submissions'),
    ('unknown', 'timeout', 'runtime_error', 'failed', 'timeout', 'job node state'),
    ('failed', 'timeout', None, 'failed', 'timeout', 'job node state'),
])
def test_stored_merge_preserves_fact_groups(tmp_path, api_status, local_reason, api_reason, want, want_reason, source):
    l = ledger(tmp_path)
    key = local_closed(l)
    l._conn.execute("UPDATE tasks SET outcome='failed',source_outcome='job node state',objective='local objective', "
                    "node_key='local_node',job_state='local state',failure_reason=?,failure_class=?,source_reason=? WHERE key=?",
                    (local_reason, 'local class' if local_reason else None,
                     'job node state' if local_reason else None, key))
    l._conn.commit()
    l.seed_api_rows([dict(work(), status=api_status, objective=None, nodeKey=None, jobState=None)], seat=3)
    if api_reason:
        l._conn.execute("UPDATE tasks SET failure_reason=?,failure_class='api class',source_reason='submissions' WHERE source_row='api'", (api_reason,))
        l._conn.commit()
    stored(l)
    row = l.record_rows()[0]
    assert len(l.rows()) == 1
    assert row['key'] == key and row['nodeId8'] == '12345678'
    assert row['acceptedUtc'] == '2026-10-03T11:59:00.000Z'
    assert row['objective'] == 'local objective' and row['nodeKey'] == 'local_node'
    assert row['outcome'] == want and row['failureReason'] == want_reason
    assert row['source']['reason'] == source
    assert row['failureClass'] == (None if source is None else 'api class' if source == 'submissions' else 'local class')
    assert row['source']['outcome'] == ('job node state' if api_status == 'unknown' else 'api')
    assert row['jobState'] == ('local state' if api_status == 'unknown' else None)
    l.close()


@pytest.mark.parametrize('order', ['local_first', 'plane_first'])
def test_missed_stored_exact_attempt_reconciles_without_duplicate_counts(tmp_path, order):
    l = ledger(tmp_path)
    if order == 'plane_first':
        l.attach_work([work()], as_of_utc=AS_OF)
    key = local_closed(l)
    l.attach_work([work()], as_of_utc=AS_OF)
    l.attach_work([work()], as_of_utc=AS_OF)
    rows = l.record_rows()
    assert len(rows) == 1
    assert rows[0]['key'] == key and rows[0]['source']['row'] == 'local'
    assert rows[0]['submissionHash'] == HASH and rows[0]['outcome'] == 'accepted'
    assert rows[0]['storedUtc'] is None  # a journal gap never invents a stored line
    assert node_rows(rows)[0]['attempts'] == 1
    l.close()


@pytest.mark.parametrize('ambiguity', ['local', 'plane', 'persisted_plane', 'time', 'job', 'node', 'cancelled', 'local_fail', 'interrupted', 'lease_closed'])
def test_missed_stored_ambiguous_evidence_keeps_separate_rows(tmp_path, ambiguity):
    l = ledger(tmp_path)
    key = local_closed(l)
    rows = [work()]
    if ambiguity == 'local':
        l._conn.execute("INSERT INTO tasks(key,seat,node8,accepted_utc,submitted_utc,job_id,source_row) "
                        "VALUES ('second',3,'87654321','2026-10-03T11:59:30Z','2026-10-03T12:00:00Z',?,'local')", (JOB,))
    elif ambiguity == 'plane':
        rows.append(work(digest='b' * 64))
    elif ambiguity == 'persisted_plane':
        l.seed_api_rows([work(digest='b' * 64)], seat=3)
    elif ambiguity == 'time':
        rows[0]['submittedAt'] = '2026-10-03T12:00:01Z'
    elif ambiguity == 'job':
        rows[0]['jobId'] = 'foreign-job'
    elif ambiguity == 'node':
        l._conn.execute("UPDATE tasks SET node_key='different_node' WHERE key=?", (key,))
    elif ambiguity == 'cancelled':
        l._conn.execute("UPDATE tasks SET cancelled='superseded' WHERE key=?", (key,))
    elif ambiguity == 'local_fail':
        l._conn.execute("UPDATE tasks SET phases_json='[\"failed\"]' WHERE key=?", (key,))
    elif ambiguity == 'interrupted':
        l._conn.execute("UPDATE tasks SET interrupted_by_restart=1 WHERE key=?", (key,))
    else:
        l._conn.execute("UPDATE tasks SET lease_closed=1 WHERE key=?", (key,))
    l._conn.commit()
    l.attach_work(rows, as_of_utc=AS_OF)
    local = next(r for r in l.record_rows() if r['key'] == key)
    assert local['hash12'] is None
    assert local['outcome'] is None
    assert len(l.rows()) == (3 if ambiguity in ('local', 'plane', 'persisted_plane') else 2)
    l.close()


def test_missed_stored_fallback_failed_is_mergeable_and_real_stored_can_arrive_later(tmp_path):
    l = ledger(tmp_path)
    key = local_closed(l)
    l._conn.execute("UPDATE tasks SET outcome='failed',source_outcome='job node state', "
                    "failure_reason='timeout',source_reason='job node state' WHERE key=?", (key,))
    l._conn.commit()
    l.attach_work([work()], as_of_utc=AS_OF)
    assert len(l.rows()) == 1 and l.rows()[0]['outcome'] == 'accepted'
    assert l.rows()[0]['failureReason'] is None
    stored(l)
    assert l.rows()[0]['storedUtc'] == '2026-10-03T12:00:00.100Z'
    l.close()
