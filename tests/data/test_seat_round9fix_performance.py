"""Bounded detail hydration with complete historical NODES facts, offline SQLite."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from maxpane_dashboard.data.seat_api import SeatApiClient
from maxpane_dashboard.data.seat_ledger import SeatLedger
from maxpane_dashboard.data.seat_manager import SeatManager

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc).timestamp()


def work(index, *, days=0, status='accepted'):
    stamp = datetime(2026, 10, 3, 12, tzinfo=timezone.utc) + timedelta(seconds=index, days=-days)
    return dict(jobId=f'{index:08x}-0000-4000-8000-000000000000',
                submissionHash=f'{index + 1:064x}', submittedAt=stamp.isoformat().replace('+00:00', 'Z'),
                status=status, nodeKey='research_report', role='implement', jobState='completed')


def manager(tmp_path, rows=()):
    ledger = SeatLedger(tmp_path / 'ledger.sqlite', seat=3, now=lambda: NOW)
    ledger.seed_api_rows(list(rows), seat=3)
    result = SeatManager(ledger=ledger, seat=3, offline=True, host='fixture',
                         maxpane_dir=tmp_path, now=lambda: NOW)
    return result, ledger


def test_3000_rows_bound_full_detail_reads_to_carried_records_and_jobs(tmp_path, monkeypatch):
    m, ledger = manager(tmp_path, [work(i) for i in range(3000)])
    calls = []
    original = ledger.task_detail
    monkeypatch.setattr(ledger, 'task_detail', lambda key: (calls.append(key), original(key))[1])
    doc = {}
    m._dashboard_blocks(doc, NOW)
    assert len(doc['records']['rows']) == 400
    assert doc['nodes']['coverage']['attempts'] == 3000
    assert doc['nodes']['allRows'][0]['attempts'] == 3000
    assert len(calls) <= 400 + len(doc['jobs'])
    assert all(key in {r['key'] for r in doc['records']['rows'] + doc['jobs']} for key in calls)
    ledger.close()


def test_document_shares_one_record_query_across_jobs_today_and_dashboard(tmp_path, monkeypatch):
    m, ledger = manager(tmp_path, [work(i) for i in range(3)])
    calls = []
    original = ledger.record_rows
    monkeypatch.setattr(ledger, 'record_rows', lambda **kw: (calls.append(kw), original(**kw))[1])
    doc = m._build_document(NOW, '2026-10-04T12:00:00Z')
    assert doc['nodes']['coverage']['attempts'] == 3
    assert calls == [{}]
    ledger.close()


def test_dashboard_joins_history_once_and_aggregates_window_facts(tmp_path):
    m, ledger = manager(tmp_path, [work(i) for i in range(5)])
    queries = []
    ledger._conn.set_trace_callback(queries.append)
    doc = {}
    m._dashboard_blocks(doc, NOW)
    joins = [sql.lower() for sql in queries if 'join job_details' in sql.lower()]
    assert len(joins) == 2
    assert len([sql for sql in joins if 'count(*)' in sql and 'min(' in sql and 'max(' in sql]) == 1
    assert doc['records']['window']['rows'] == 5
    ledger._conn.set_trace_callback(None)
    ledger.close()


def test_empty_history_window_and_foreign_seat_are_not_counted(tmp_path):
    m, ledger = manager(tmp_path)
    ledger.seed_api_rows([work(9)], seat=4)
    doc = {}
    m._dashboard_blocks(doc, NOW)
    assert doc['records'] == dict(rows=[], window=dict(rows=0, asOfUtc=None, fromUtc=None, toUtc=None, reason='offline'))
    assert doc['nodes'] == dict(allRows=[], weekRows=[], coverage=dict(attempts=0, covered=0, detailsRead=0, asOfUtc=None, reason='offline'))
    ledger.close()


@pytest.mark.parametrize('cached_json', [' { } ', 'null', 'broken'])
def test_empty_or_unreadable_cache_keeps_unknown_coverage_and_timestamp(tmp_path, cached_json):
    m, ledger = manager(tmp_path, [work(0)])
    ledger._conn.execute('INSERT INTO job_details VALUES (?,?,?)', (work(0)['jobId'], cached_json, None))
    ledger._conn.execute("UPDATE tasks SET outcome_as_of_utc='',launch_json='{}'")
    ledger._conn.commit()
    doc = {}
    m._dashboard_blocks(doc, NOW)
    assert doc['nodes']['coverage']['detailsRead'] == 0
    assert doc['nodes']['coverage']['asOfUtc'] is None
    assert doc['records']['window']['asOfUtc'] is None
    assert doc['nodes']['allRows'][0]['paid'] is None
    assert ledger.record_rows()[0]['launch'] == {}
    ledger.close()


def test_nodes_preserve_mixed_local_api_medians_payer_launch_and_old_history(tmp_path):
    m, ledger = manager(tmp_path, [work(0, days=8), work(1), work(2), work(3), work(4)])
    # Local metrics remain distinct from submission usage fallback and API rows.
    ledger._conn.execute("UPDATE tasks SET source_row='local',duration_s=10,tokens_output=100 WHERE job_id=?", (work(0)['jobId'],))
    ledger._conn.execute("UPDATE tasks SET source_row='local',duration_s=30,tokens_output=300 WHERE job_id=?", (work(1)['jobId'],))
    ledger._conn.execute("UPDATE tasks SET source_row='local' WHERE job_id=?", (work(2)['jobId'],))
    ledger._conn.execute("UPDATE tasks SET duration_s=900,tokens_output=900 WHERE job_id=?", (work(3)['jobId'],))
    ledger._conn.execute("UPDATE tasks SET outcome='failed',node_key=NULL WHERE job_id=?", (work(4)['jobId'],))
    for i, detail in enumerate([{'paid': True, 'launchLinked': False}, {'paid': False, 'launchLinked': True}, {'paid': None}, {'paid': True}]):
        ledger._conn.execute('INSERT INTO job_details VALUES (?,?,?)', (work(i)['jobId'], json.dumps(detail), '2026-10-04T11:00:00Z'))
    ledger._conn.execute('UPDATE tasks SET launch_json=? WHERE job_id=?', (json.dumps({'kind': 'workflow'}), work(0)['jobId']))
    ledger._conn.execute('INSERT INTO attempt_details VALUES (?,?,?)', (work(2)['jobId'], work(2)['submissionHash'], json.dumps({'usage': {'outputTokens': 700, 'wallClockMs': 50000}})))
    ledger._conn.execute("UPDATE tasks SET outcome_as_of_utc='2026-10-04T11:59:00Z'")
    ledger._conn.commit()
    doc = {}
    m._dashboard_blocks(doc, NOW)
    nodes = doc['nodes']['allRows']
    assert nodes[0] == dict(nodeKey='research_report', role='implement', attempts=4,
                           accepted=4, rejected=0, failed=0, pending=0, acceptedPercent=100,
                           durationP50S=20, outputTokensP50=200, paid=2, launch=2, detailsRead=4,
                           lastSubmittedUtc=work(3)['submittedAt'])
    week = doc['nodes']['weekRows'][0]
    assert (week['attempts'], week['durationP50S'], week['outputTokensP50'], week['paid'], week['launch']) == (3, 30, 300, 1, 1)
    assert nodes[1]['nodeKey'] == '(plane unread)' and nodes[1]['paid'] is None and nodes[1]['launch'] is None
    assert doc['nodes']['coverage'] == dict(attempts=5, covered=4, detailsRead=4, asOfUtc='2026-10-04T11:59:00Z', reason='offline')
    assert doc['records']['window'] == dict(rows=5, asOfUtc='2026-10-04T11:59:00Z', fromUtc=work(0, days=8)['submittedAt'], toUtc=work(4)['submittedAt'], reason='offline')
    fallback = next(r for r in doc['records']['rows'] if r['jobId'] == work(2)['jobId'])
    assert fallback['tokens']['output'] == 700 and fallback['durationS'] == 50
    ledger.close()


def test_nodes_keep_structured_local_facts_beyond_400_text_records(tmp_path):
    m, ledger = manager(tmp_path, [work(0, days=8)] + [work(i) for i in range(1, 401)])
    ledger._conn.execute("UPDATE tasks SET source_row='local',duration_s=10,tokens_output=100,launch_json=? WHERE job_id=?",
                         (json.dumps({'kind': 'workflow'}), work(0)['jobId']))
    ledger._conn.execute('INSERT INTO job_details VALUES (?,?,?)', (work(0)['jobId'], json.dumps({'paid': True}), None))
    ledger._conn.commit()
    doc = {}
    m._dashboard_blocks(doc, NOW)
    assert len(doc['records']['rows']) == 400
    assert all(r['jobId'] != work(0)['jobId'] for r in doc['records']['rows'])
    node = doc['nodes']['allRows'][0]
    assert (node['attempts'], node['detailsRead'], node['paid'], node['launch'], node['durationP50S'], node['outputTokensP50']) == (401, 1, 1, 1, 10, 100)
    week = doc['nodes']['weekRows'][0]
    assert (week['attempts'], week['detailsRead'], week['paid'], week['launch'], week['durationP50S'], week['outputTokensP50']) == (400, 0, None, None, None, None)
    ledger.close()


def test_failed_reason_candidates_do_not_hydrate_expired_record_text(tmp_path, monkeypatch):
    m, ledger = manager(tmp_path, [work(i, days=3, status='failed') for i in range(402)])
    ledger._conn.execute('UPDATE tasks SET stored_utc=submitted_utc,text_expired=1')
    ledger._conn.commit()
    calls = []
    original = ledger.task_detail
    monkeypatch.setattr(ledger, 'task_detail', lambda key: (calls.append(key), original(key))[1])
    candidates = m._detail_candidates(NOW)
    assert not [c for c in candidates if c[0] == 'submissions']
    assert calls == []
    ledger.close()


async def test_detached_details_snapshot_once_then_refresh_next_run(tmp_path, monkeypatch):
    m, ledger = manager(tmp_path, [work(0), work(1)])
    ledger._conn.execute('UPDATE tasks SET stored_utc=NULL')
    ledger._conn.commit()
    requests = []
    def handler(request):
        job = request.url.path.split('/')[2]
        requests.append(job)
        if len(requests) == 1:
            ledger.seed_api_rows([work(2)], seat=3)
            ledger._conn.execute('UPDATE tasks SET stored_utc=NULL')
            ledger._conn.commit()
        return httpx.Response(200, json={'id': job, 'state': 'completed', 'nodes': []})
    client = SeatApiClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), now=lambda: NOW)
    m._api = client
    m._offline = False
    m.select_dashboard('NODES')
    builds = []
    original = m._detail_candidates
    monkeypatch.setattr(m, '_detail_candidates', lambda now: (builds.append(now), original(now))[1])
    await m._tier_details()
    assert requests == [work(1)['jobId'], work(0)['jobId']]
    assert builds == [NOW]
    await m._tier_details()
    assert requests == [work(1)['jobId'], work(0)['jobId'], work(2)['jobId']]
    assert builds == [NOW, NOW]
    await client.close()
    ledger.close()


@pytest.mark.parametrize('shared_recent', [False, True])
async def test_failed_candidate_expired_by_first_cache_store_does_not_spend_budget(tmp_path, monkeypatch, shared_recent):
    old = work(0, days=3, status='failed')
    recent = dict(work(401, status='failed'), jobId=old['jobId'], submittedAt='2026-10-03T10:00:00Z')
    count = 399 if shared_recent else 400
    rows = [old] + [work(i) for i in range(1, count + 1)]
    if shared_recent:
        rows.append(recent)
    m, ledger = manager(tmp_path, rows)
    ledger._conn.execute('UPDATE tasks SET stored_utc=NULL WHERE job_id!=?', (old['jobId'],))
    if shared_recent:
        # The old candidate sorts first, but the recent attempt still has retained text.
        ledger._conn.execute('UPDATE tasks SET stored_utc=? WHERE submission_hash=?', ('2026-10-03T11:00:00Z', old['submissionHash']))
    ledger._conn.commit()
    requests, builds, detail_reads = [], [], []
    def handler(request):
        requests.append(request.url.path)
        job = request.url.path.split('/')[2]
        return httpx.Response(200, json={'id': job, 'state': 'completed', 'nodes': [], 'submissions': []})
    client = SeatApiClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), now=lambda: NOW)
    m._api = client
    m._offline = False
    original_candidates, original_detail = m._detail_candidates, ledger.task_detail
    monkeypatch.setattr(m, '_detail_candidates', lambda now: (builds.append(now), original_candidates(now))[1])
    monkeypatch.setattr(ledger, 'task_detail', lambda key: (detail_reads.append(key), original_detail(key))[1])
    try:
        await m._tier_details()
        state = {r['submissionHash']: r for r in ledger.record_rows()}
        assert state[old['submissionHash']]['textExpired'] is True
        expected = [f"/jobs/{work(count)['jobId']}"]
        if shared_recent:
            assert state[recent['submissionHash']]['textExpired'] is False
            expected.append(f"/jobs/{old['jobId']}/submissions")
        assert requests == expected
        assert builds == [NOW]
        assert detail_reads == []
    finally:
        await client.close()
        ledger.close()
