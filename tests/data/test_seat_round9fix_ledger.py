"""Round 9 fix packages 2/6/11: real SQLite, captured jobs, compositor."""
import subprocess
import sys
import types

import pytest

from maxpane_dashboard.analytics.seat_records import node_rows, record_window
from maxpane_dashboard.data import seat_api as api
from maxpane_dashboard.data.seat_log_grammar import classify
from maxpane_dashboard.widgets.seat import SeatJob, SeatRecords
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
@pytest.mark.parametrize('stamp,merges', [
    ('2026-10-03T12:00:00.000Z', True),
    ('2026-10-03T12:00:00.073Z', True),  # measured API lead over the journal
    ('2026-10-03T11:59:58.000Z', True),
    ('2026-10-03T12:00:05.000Z', True),
    ('2026-10-03T11:59:57.999Z', False),
    ('2026-10-03T12:00:05.001Z', False),
    ('2026-10-03T12:00:06.000Z', False),
])
def test_missed_stored_exact_attempt_reconciles_without_duplicate_counts(tmp_path, order, stamp, merges):
    l = ledger(tmp_path)
    item = work(at=stamp)
    if order == 'plane_first':
        l.attach_work([item], as_of_utc=AS_OF)
    key = local_closed(l)
    l.attach_work([item], as_of_utc=AS_OF)
    l.attach_work([item], as_of_utc=AS_OF)
    rows = l.record_rows()
    if not merges:
        assert len(rows) == 2
        local = next(r for r in rows if r['key'] == key)
        assert local['hash12'] is None and local['outcome'] is None
        l.close()
        return
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
        rows[0]['submittedAt'] = '2026-10-03T12:00:06Z'
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


def test_late_known_stored_never_claims_newer_attempt(tmp_path):
    l = ledger(tmp_path)
    old_key = local_closed(l)
    l.attach_work([work()], as_of_utc=AS_OF)
    l.ingest([classify(s) for s in [
        '2026-10-03T12:01:00.000Z accepted implement 87654321 — artifacts/answer.json (max 60 turns)',
        '2026-10-03T12:02:00.000Z submitted implement for 87654321',
        '2026-10-03T12:02:00.100Z submission stored (aaaaaaaaaaaa) — awaiting verdict',
    ]])
    new_key = next(r['key'] for r in l.rows() if r['key'] != old_key)
    l.attach_work([work()], as_of_utc=AS_OF)
    rows = {r['key']: r for r in l.record_rows()}
    assert l.today('2026-10-03')['accepted'] == 1
    assert rows[new_key]['hash12'] is None and rows[new_key]['storedUtc'] is None
    assert rows[new_key]['outcome'] is None
    assert rows[old_key]['hash12'] == 'aaaaaaaaaaaa'
    assert rows[old_key]['storedUtc'] == '2026-10-03T12:02:00.100Z'
    l.close()


@pytest.mark.parametrize('reopen', [False, True])
def test_gap_merge_unknown_preserves_local_verdict_on_every_read(tmp_path, reopen):
    l = ledger(tmp_path)
    key = local_closed(l)
    l._conn.execute("UPDATE tasks SET outcome='failed',source_outcome='job node state', "
                    "failure_reason='timeout',failure_class='runtime',source_reason='job node state', "
                    "outcome_as_of_utc='2026-10-03T12:00:30Z',job_state='running' WHERE key=?", (key,))
    l._conn.commit()
    for i in range(3):
        if reopen and i:
            l.close()
            l = ledger(tmp_path)
        l.attach_work([dict(work(), status='unknown')], as_of_utc=AS_OF)
        row = l.record_rows()[0]
        assert l.today('2026-10-03')['failed'] == 1
        assert row['outcome'] == 'failed' and row['source']['outcome'] == 'job node state'
        assert row['outcomeAsOfUtc'] == '2026-10-03T12:00:30Z'
        assert row['workStatus'] is None and row['jobState'] == 'running'
        assert row['failureReason'] == 'timeout' and row['failureClass'] == 'runtime'
        assert row['source']['reason'] == 'job node state'
    # A real API verdict still wins and clears the merged failure group.
    l.attach_work([work()], as_of_utc=AS_OF)
    row = l.record_rows()[0]
    assert l.today('2026-10-03')['failed'] == 0 and l.today('2026-10-03')['accepted'] == 1
    assert row['outcome'] == 'accepted' and row['jobState'] == 'completed'
    assert row['source']['outcome'] == 'api'
    assert row['failureReason'] is None and row['failureClass'] is None and row['source']['reason'] is None
    l.close()


@pytest.mark.parametrize('actual_stored', [False, True])
def test_gap_merge_keeps_local_objective_on_every_read(tmp_path, actual_stored):
    l = ledger(tmp_path)
    key = local_closed(l)
    l._conn.execute("UPDATE tasks SET objective='local objective',node_key='research_report' WHERE key=?", (key,))
    l._conn.commit()
    for i in range(3):
        if i == 1:
            if actual_stored:
                stored(l)
            l.close()
            l = ledger(tmp_path)
        l.attach_work([work()], as_of_utc=AS_OF)
        row = l.record_rows()[0]
        assert row['objective'] == 'local objective'
        assert row['nodeKey'] == 'research_report' and row['source']['row'] == 'local'
        assert len(l.rows()) == 1
    l.close()


def test_unmerged_local_row_retains_ordinary_seat_work_authority(tmp_path):
    l = ledger(tmp_path)
    key = local_closed(l)
    stored(l)  # work joins by the journal hash directly, without an API-row merge
    l._conn.execute("UPDATE tasks SET outcome='failed',source_outcome='job node state',objective='local objective' WHERE key=?", (key,))
    l._conn.commit()
    l.attach_work([dict(work(), status='unknown')], as_of_utc=AS_OF)
    row = l.record_rows()[0]
    assert row['outcome'] == 'unknown' and row['source']['outcome'] == 'api'
    assert row['objective'] == 'short sentence'
    l.attach_work([work()], as_of_utc=AS_OF)
    assert l.rows()[0]['outcome'] == 'accepted'
    l.close()


@pytest.mark.parametrize('invalid', ['ambiguous_hash', 'before_submission'])
def test_late_known_stored_requires_unique_hash_and_valid_time(tmp_path, invalid):
    l = ledger(tmp_path)
    key = local_closed(l)
    l.attach_work([work()], as_of_utc=AS_OF)
    if invalid == 'ambiguous_hash':
        l._conn.execute("INSERT INTO tasks(key,seat,node8,accepted_utc,submitted_utc,hash12,source_row) "
                        "VALUES ('second',3,'87654321','2026-10-03T11:59:30Z','2026-10-03T12:00:00Z','aaaaaaaaaaaa','local')")
        l._conn.commit()
        stamp = '2026-10-03T12:00:00.100Z'
    else:
        stamp = '2026-10-03T11:59:59Z'
    l.ingest([classify(stamp + ' submission stored (aaaaaaaaaaaa) — awaiting verdict')])
    assert all(r['storedUtc'] is None for r in l.rows())
    assert next(r for r in l.rows() if r['key'] == key)['outcome'] == 'accepted'
    l.close()


def test_stored_api_merge_keeps_groups_on_repeated_work_reads(tmp_path):
    l = ledger(tmp_path)
    key = local_closed(l)
    l._conn.execute("UPDATE tasks SET outcome='failed',source_outcome='job node state', "
                    "failure_reason='timeout',source_reason='job node state',objective='local objective' WHERE key=?", (key,))
    l._conn.commit()
    l.seed_api_rows([dict(work(), status='unknown')], seat=3)
    stored(l)
    for _ in range(2):
        l.attach_work([dict(work(), status='unknown')], as_of_utc=AS_OF)
        row = l.record_rows()[0]
        assert row['outcome'] == 'failed' and row['failureReason'] == 'timeout'
        assert row['objective'] == 'local objective'
    l.close()


def test_merged_ledger_remains_readable_by_previous_ledger(tmp_path):
    source = subprocess.check_output(['git', 'show', '757455b:maxpane_dashboard/data/seat_ledger.py'], text=True)
    old = types.ModuleType('seat_ledger_pre_review_fix')
    sys.modules[old.__name__] = old
    try:
        exec(compile(source, '757455b/seat_ledger.py', 'exec'), old.__dict__)
        before = old.SeatLedger(tmp_path / 'ledger.sqlite', seat=3)
        local_closed(before)
        before.close()
        l = ledger(tmp_path)
        l.attach_work([work()], as_of_utc=AS_OF)
        l.close()
        previous = old.SeatLedger(tmp_path / 'ledger.sqlite', seat=3)
        rows = previous.record_rows()
        assert len(rows) == 1 and rows[0]['outcome'] == 'accepted'
        assert rows[0]['source']['row'] == 'local'
        assert previous.meta_get('schema_version') == 1
        previous.close()
        l = ledger(tmp_path)
        l.attach_work([work()], as_of_utc=AS_OF)
        assert len(l.record_rows()) == 1 and l.record_rows()[0]['outcome'] == 'accepted'
        l.close()
    finally:
        sys.modules.pop(old.__name__, None)


def seat_local_open(l, raw):
    l.ingest([classify('2026-10-03T10:00:00.000Z accepted implement 12345678 — q (max 60 turns)')])
    l.attach_work_dirs([dict(jobId=raw['id'], nodeId='12345678-0000-4000-8000-000000000000',
                             mtimeUtc='2026-10-03T10:00:00Z')])
    return next(r['key'] for r in l.rows() if r['source']['row'] == 'local')


def seat_close_unsubmitted(l, close):
    line = {
        'local_fail': 'question failed: boom',
        'cancelled': 'cancelled 12345678: superseded',
        'interrupted': 'runtimes: codex codex-cli 0.157.0 (using codex, as asked)',
    }[close]
    l.ingest([classify('2026-10-03T10:01:00.000Z ' + line)])


@pytest.mark.parametrize('close', ['local_fail', 'cancelled', 'interrupted'])
def test_closed_unsubmitted_can_read_owned_failure_without_prior_fallback(tmp_path, close):
    l = ledger(tmp_path)
    raw = chain()
    seat_local_open(l, raw)
    seat_close_unsubmitted(l, close)
    assert l.record_rows()[0]['nodeKey'] is None
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='failed', failureReason='timeout')
    store_job(l, raw)
    row = l.record_rows()[0]
    assert row['outcome'] == 'failed' and row['failureReason'] == 'timeout'
    assert row['source']['outcome'] == row['source']['reason'] == 'job node state'
    assert row['jobState'] is None
    l.close()


@pytest.mark.parametrize('close', ['local_fail', 'cancelled', 'interrupted'])
@pytest.mark.parametrize('failed_read', [False, True])
async def test_closed_unsubmitted_releases_pending_and_retains_owned_failure(tmp_path, close, failed_read):
    l = ledger(tmp_path)
    raw = chain()
    raw['state'] = 'running'
    key = seat_local_open(l, raw)
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='pending')
    store_job(l, raw)
    assert l.record_rows()[0]['outcome'] == 'pending'
    seat_close_unsubmitted(l, close)
    if failed_read:
        raw['nodes'][0].update(state='failed', failureReason='timeout')
        store_job(l, raw)
        row = l.record_rows()[0]
        assert row['outcome'] == 'failed' and row['failureReason'] == 'timeout'
        assert row['source']['outcome'] == row['source']['reason'] == 'job node state'
    raw['nodes'][0].update(seat={'tokenId': '721'}, state='accepted')
    store_job(l, raw)
    row = l.record_rows()[0]
    assert row['outcome'] == ('failed' if failed_read else None)
    assert row['source']['outcome'] == ('job node state' if failed_read else 'none')
    assert row['jobState'] is None and row['submittedUtc'] is None
    assert l.today('2026-10-03')['pending'] == 0
    records = '\n'.join(await composite_lines(SeatRecords, (132, 12), seat_records_rows=[row]))
    job = '\n'.join(await composite_lines(SeatJob, (110, 30), seat_jobs=[l.task_detail(key)]))
    assert 'pending' not in records and 'pending' not in job
    if failed_read:
        assert 'failed' in records and 'timeout' in job
    l.close()


@pytest.mark.parametrize('state', ['accepted', 'rejected', 'pending'])
def test_cancelled_unsubmitted_never_takes_other_attempt_states(tmp_path, state):
    l = ledger(tmp_path)
    raw = chain()
    raw['state'] = 'completed'
    seat_local_open(l, raw)
    seat_close_unsubmitted(l, 'cancelled')
    raw['nodes'][0].update(seat={'tokenId': '3'}, state=state)
    store_job(l, raw)
    assert l.record_rows()[0]['outcome'] is None
    assert l.record_rows()[0]['jobState'] is None
    l.close()


@pytest.mark.parametrize('other', ['open', 'closed', 'api'])
def test_closed_unsubmitted_same_node_reattempt_blocks_fallback_for_both(tmp_path, other):
    l = ledger(tmp_path)
    raw = chain()
    seat_local_open(l, raw)
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='pending')
    store_job(l, raw)
    assert l.record_rows()[0]['outcome'] == 'pending'
    seat_close_unsubmitted(l, 'local_fail')
    if other == 'api':
        l.seed_api_rows([dict(work(job=raw['id']), status='unknown', nodeKey=None)], seat=3)
    else:
        l.ingest([classify('2026-10-03T10:02:00.000Z accepted implement 12345678 — q (max 60 turns)')])
        l.attach_work_dirs([dict(jobId=raw['id'], nodeId='12345678-0000-4000-8000-000000000000',
                                 mtimeUtc='2026-10-03T10:02:00Z')])
        if other == 'closed':
            l.ingest([classify('2026-10-03T10:03:00.000Z question failed: boom')])
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='failed', failureReason='timeout')
    store_job(l, raw)
    assert len(l.rows()) == 2
    assert all(r['outcome'] in (None, 'unknown') for r in l.rows())
    assert all(r['source']['outcome'] != 'job node state' for r in l.rows())
    l.close()


@pytest.mark.parametrize('state', ['accepted', 'rejected', 'pending'])
def test_closed_unsubmitted_releases_pending_before_owned_state_is_refused(tmp_path, state):
    l = ledger(tmp_path)
    raw = chain()
    seat_local_open(l, raw)
    raw['nodes'][0].update(seat={'tokenId': '3'}, state='pending')
    store_job(l, raw)
    seat_close_unsubmitted(l, 'cancelled')
    raw['nodes'][0]['state'] = state
    store_job(l, raw)
    assert l.record_rows()[0]['outcome'] is None
    assert l.today('2026-10-03')['pending'] == 0
    l.close()


async def test_missed_stored_measured_window_needs_no_api_node_identity_and_paints_one_record(tmp_path):
    l = ledger(tmp_path)
    key = local_closed(l)
    item = work(at='2026-10-03T12:00:00.073Z')
    item.pop('nodeKey')  # work has no node id; nodeKey is not required evidence either.
    l.attach_work([item], as_of_utc=AS_OF)
    rows = l.record_rows()
    assert len(rows) == 1 and rows[0]['key'] == key
    assert rows[0]['submissionHash'] == HASH and rows[0]['storedUtc'] is None
    text = '\n'.join(await composite_lines(SeatRecords, (132, 12), seat_records_rows=rows))
    assert text.count(JOB[:8]) == 1
    assert 'completed' in text
    l.close()


@pytest.mark.parametrize('evidence', ['work', 'persisted'])
def test_missed_stored_window_hash_uniqueness_includes_already_stored_attempt(tmp_path, evidence):
    l = ledger(tmp_path)
    key = local_closed(l)
    # A second submitted attempt already has its stored hash; it is not a missing-stored candidate.
    l.ingest([classify(s) for s in [
        '2026-10-03T12:00:01.000Z accepted implement 87654321 — q (max 60 turns)',
        '2026-10-03T12:00:02.000Z submitted implement for 87654321',
        '2026-10-03T12:00:02.100Z submission stored (bbbbbbbbbbbb) — awaiting verdict',
    ]])
    l.attach_work_dirs([dict(jobId=JOB, nodeId='87654321-0000-4000-8000-000000000000',
                             mtimeUtc='2026-10-03T12:00:01Z')])
    second = work(digest='b' * 64, at='2026-10-03T12:00:02.073Z')
    items = [work(at='2026-10-03T12:00:00.073Z')]
    if evidence == 'work':
        items.append(second)
    else:
        # Persisted API evidence inside the window must block even when omitted by this read.
        l.seed_api_rows([work(digest='c' * 64, at='2026-10-03T12:00:03Z')], seat=3)
    l.attach_work(items, as_of_utc=AS_OF)
    local = next(r for r in l.rows() if r['key'] == key)
    assert local['hash12'] is None and local['outcome'] is None
    l.close()
