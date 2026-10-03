"""Round 9 WP2 regressions. All I/O uses committed metadata or synthetic fakes."""
import asyncio
import json
import queue
import subprocess
from pathlib import Path

import httpx
import pytest

from imd_dashd import summarise_claude as scl
from maxpane_dashboard.analytics.seat_redact import find_secret
from maxpane_dashboard.data import seat_api as api_mod, seat_models as models
from maxpane_dashboard.data.seat_broker_client import FakeBroker, SystemdUnitReader
from maxpane_dashboard.data.seat_manager import SeatManager
from maxpane_dashboard.data.seat_tail import KIND_JOURNALD, ListLineSource, TailState, TailThread

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/seat/round9/claude_recovered.json'
T0 = 1791043200.0
JOB = '73d7dcd7-5a72-483a-9f34-bb6cdac42b58'
NODE = '12345678-1234-1234-1234-123456789abc'
BLOB = 'tokenURI data:application/json;base64,eyJuYW1lIjoiYWJjZGVmZ2hpaiJ9 end'


def manager(tmp_path, **kwargs):
    return SeatManager(maxpane_dir=tmp_path, now=lambda: T0, broker=FakeBroker(reachable=False),
                       offline=True, seat=3, runtime='claude', **kwargs)


async def document(m):
    await m.fetch_and_compute()
    await m.settle()
    await m.fetch_and_compute()
    return m.document()


def test_d1_real_capture_string_identities_match():
    body = json.loads((ROOT / 'tests/fixtures/surf/swarm/v4/submissions_73d7dcd7.json').read_text())
    rows = [api_mod.normalise_submission(row) for row in body['submissions']]
    assert len(rows) == 40
    assert [row['seatTokenId'] for row in rows] == [int(row['seat']['tokenId']) for row in body['submissions']]
    wanted = int(body['submissions'][0]['seat']['tokenId'])
    assert api_mod.submissions_for_seat({'submissions': rows}, str(wanted))
    assert api_mod.normalise_standing({'enrollment': {'agentId': '51075'}})['agentId'] == 51075
    assert not api_mod.validate_counters(dict(attempts='0', accepted=0, rejected=0, failed=0, pending=0))


@pytest.mark.parametrize('home', ['/home/imd', '/home/imd-worker'])
def test_d2_root_home_classifies_tasks_research_doctor_manual(tmp_path, monkeypatch, home):
    fixture = json.loads(FIXTURE.read_text())
    prefix = fixture['homes'][home]
    root = home + '/.claude/projects'
    slugs = [prefix + '--identitymd-work-' + JOB + '-' + NODE,
             prefix + '--identitymd-work', prefix + '--identitymd-work-doctor-zN5enH', prefix]
    files = []
    for slug in slugs:
        path = tmp_path / slug / 'synthetic.jsonl'
        path.parent.mkdir()
        path.write_text('\n'.join(json.dumps(r) for r in fixture['records']) + '\n')
        files.append((1., str(path), path.stat().st_size))
    monkeypatch.setattr(scl, '_candidates', lambda _: files)
    monkeypatch.setattr(scl.os.path, 'isdir', lambda _: True)
    result = scl.summarise_dir(root, since_mtime=0., now=T0)
    assert [s['kind'] for s in result['sessions']] == ['task', 'research', 'doctor', 'manual']
    assert result['sessions'][0]['jobId'] == JOB
    assert result['sessions'][0]['tokens']['output'] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401, 403, 429])
@pytest.mark.parametrize('recovered', [True, False])
async def test_d5_summariser_ledger_document_and_fresh_process_agree(tmp_path, status, recovered):
    fixture = json.loads(FIXTURE.read_text())
    records = fixture['records']
    records[0]['status'] = status
    if not recovered:
        records = records[:1]
    path = tmp_path / '-home-imd--identitymd-work-doctor-zN5enH' / 'synthetic.jsonl'
    path.parent.mkdir()
    path.write_text('\n'.join(json.dumps(r) for r in records) + '\n')
    session = scl.summarise_file(str(path), now=T0)
    m = manager(tmp_path)
    m._broker = FakeBroker({'sessions': {'sessions': [session], 'watermarkMtime': session['mtime']}})
    await m._tier_sessions()
    persisted = json.loads(m._ledger._conn.execute('SELECT api_errors_json FROM sessions').fetchone()[0])
    assert persisted[0].get('outputFollowed') is recovered
    first = await document(m)
    assert first['auth']['degraded'] is (not recovered)
    await m.close()
    fresh = manager(tmp_path)
    fresh._broker = FakeBroker({'sessions': {'sessions': [], 'watermarkMtime': session['mtime']}})
    await fresh._tier_sessions()
    second = await document(fresh)
    assert second['auth'] == first['auth']
    await fresh.close()


@pytest.mark.asyncio
async def test_d3_startup_facts_and_restart_flag_survive_empty_tail(tmp_path):
    m = manager(tmp_path, tail=ListLineSource([
        '2026-10-03T00:00:00.000Z runtimes: claude 2.1.286 (using claude)',
        '2026-10-03T00:00:01.000Z release 0.1.0+ae69e4ec, the latest',
        '2026-10-03T00:00:02.000Z admitted (session 12345678)',
        '2026-10-03T00:00:03.000Z alive 1m · idle · 7 submitted',
    ]))
    await m.backfill()
    m.set_restart_required(True)
    first = await document(m)
    assert first['seat']['daemonVersion'] == '0.1.0+ae69e4ec'
    assert first['daemon']['submittedSinceStart'] == 7
    await m.close()
    fresh = manager(tmp_path, tail=ListLineSource([]))
    await fresh.backfill()
    second = await document(fresh)
    for key in ['daemonVersion', 'releaseAvailable']:
        assert second['seat'][key] == first['seat'][key]
    assert second['daemon']['lastAdmittedUtc'] == first['daemon']['lastAdmittedUtc']
    assert second['daemon']['submittedSinceStart'] == 7
    assert second['control']['restartRequired'] is True
    await fresh.close()


@pytest.mark.asyncio
async def test_d9_busy_stops_retry_and_applies_class_floor(tmp_path):
    now = [T0]
    calls = []
    busy = json.loads((ROOT / 'tests/fixtures/surf/swarm/seats_503_busy.json').read_text())
    responses = [httpx.Response(503, json=busy)] * 5 + [httpx.Response(200, json={}), httpx.Response(503, json=busy)]
    def handler(req):
        if req.url.path in ("/services", "/health"):
            return httpx.Response(200, json={})
        calls.append(req.url.path)
        return responses.pop(0)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = api_mod.SeatApiClient(http_client=http, now=lambda: now[0], sleep=lambda _: asyncio.sleep(0))
        for delay in [60, 120, 240, 480, 600]:
            before = len(calls)
            result = await api.standing(3)
            assert result.reason == 'busy' and len(calls) == before + 1
            assert api.pause_until('seat') == now[0] + delay
            assert (await api.seat_work(3)).reason == 'busy'
            assert len(calls) == before + 1
            now[0] += delay
        assert (await api.standing(3)).ok
        assert api.pause_until('seat') == 0
        assert (await api.standing(3)).reason == 'busy'
        assert api.pause_until('seat') == now[0] + 60
        m = SeatManager(maxpane_dir=tmp_path, now=lambda: now[0], api=api, seat=3, broker=FakeBroker(reachable=False))
        m.plan_open = True
        m.bump('standing', 0)
        for _ in range(4):
            await document(m)
        assert len(calls) == 7 and m._failures['standing'] == 0
        await m.close()


@pytest.mark.asyncio
async def test_d10_successful_empty_backfill_with_watermark_is_healthy(tmp_path):
    TailState(last_ts_utc='2026-10-03T00:00:00.000Z').save(tmp_path / 'seat_tail.json')
    m = manager(tmp_path, tail=ListLineSource([]))
    await m.backfill()
    doc = await document(m)
    assert doc['sources']['tail']['ok'] is True
    assert doc['sources']['tail']['reason'] is None
    await m.close()


def test_gapnote_empty_nonzero_cursor_attach_keeps_real_gap(tmp_path):
    fixture = json.loads((ROOT / 'tests/fixtures/seat/round9/empty_cursor_attach.json').read_text())
    source = ListLineSource(fixture['lines'], exit_code=fixture['exitCode'])
    source.kind = KIND_JOURNALD
    state = TailState(cursor=fixture['cursor'], last_ts_utc=fixture['lastTsUtc'])
    tail = TailThread(lambda _: source, queue.Queue(), state=state, state_path=tmp_path / 'tail.json', now=lambda: T0)
    tail.run_once()
    assert tail.gap_note == 'gap ' + fixture['lastTsUtc'] + '→?'
    assert state.cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [BLOB, BLOB + 'x' * 100_000, 'eyJabcdefghijk.abcdefghijk.abcdefghijk'], ids=['base64', '100kb', 'jwt'])
async def test_d11_objective_reply_document_is_not_refused(tmp_path, monkeypatch, text):
    m = manager(tmp_path)
    original = m._build_document
    def build(now, started):
        doc = original(now, started)
        doc['jobs'] = [{'jobId': JOB, 'objective': text, 'reply': text, 'secret': 'discard this field'}]
        doc['current'] = {'objective': text}
        return doc
    monkeypatch.setattr(m, '_build_document', build)
    doc = await document(m)
    assert doc['current']['objective'] and doc['jobs'][0]['reply']
    assert models.validate_status_document(doc) is None
    assert find_secret(doc) is None
    assert len(doc['jobs'][0]['reply']) <= 4096
    await m.close()


def test_d4_journal_facts_use_three_bounded_reads(tmp_path):
    calls = []
    outputs = [b'Archived and active journals take up 48.0M in the file system.',
               b'2026-10-02T20:39:25+00:00 host imd-worker[1]: start',
               b'System Journal (/var/log/journal/id) is 24.0M, max 4G, 3.9G free.']
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, outputs[len(calls) - 1], b'')
    reader = SystemdUnitReader(run=run, home=str(tmp_path))
    facts = reader.read_journal()
    assert facts['journal']['firstUtc'] == '2026-10-02T20:39:25Z'
    assert '4G' in facts['journal']['capNote'] and '48.0M' in facts['journal']['capNote']
    assert [c[0] for c in calls] == [
        ['journalctl', '--disk-usage'],
        ['journalctl', '-u', 'imd-worker.service', '-n', '+1', '-o', 'short-iso', '--no-pager'],
        ['journalctl', '-u', 'systemd-journald', '--grep', 'System Journal', '-n', '1', '-o', 'cat', '--no-pager']]
    assert all(c[1]['timeout'] > 0 for c in calls)


def test_d11_sanitizer_cut_and_dollar_join_boundaries():
    from maxpane_dashboard.analytics.seat_text import sanitize_text
    for raw in ['sk-ant-abcdefghijk', 'eyJabcde$fghijklmno', 'a' * 32 + '$' + 'b' * 32, BLOB]:
        for cap in range(1, 85):
            cleaned = sanitize_text(raw, cap=cap)
            assert len(cleaned) <= cap and find_secret(cleaned) is None
            assert '$' not in cleaned


@pytest.mark.asyncio
async def test_d4_journal_work_runs_off_refresh_with_300_second_floor(tmp_path):
    import threading
    now = [T0]
    calls = []
    main = threading.get_ident()
    class Reader:
        def read_unit(self):
            return {'activeState': 'active'}
        def read_host(self):
            return {}
        def read_journal(self):
            calls.append(threading.get_ident())
            return {'journal': {'firstUtc': '2026-10-02T20:39:25Z', 'lastUtc': None, 'capNote': '4G'}, 'reason': None}
    m = SeatManager(maxpane_dir=tmp_path, now=lambda: now[0], offline=True, unit_reader=Reader(), broker=FakeBroker(reachable=False))
    await m.fetch_and_compute()
    assert calls == []
    await m.settle()
    assert len(calls) == 1 and calls[0] != main
    for advance in [5, 290]:
        now[0] += advance
        m.bump('workstat', 0)
        await document(m)
        assert len(calls) == 1
    now[0] += 5
    m.bump('workstat', 0)
    doc = await document(m)
    assert len(calls) == 2 and doc['machine']['journal']['capNote'] == '4G'
    await m.close()


@pytest.mark.parametrize('failure', ['timeout', 'exit', 'malformed'])
def test_d4_unreadable_journal_is_none_with_safe_reason(tmp_path, failure):
    def run(argv, **kwargs):
        assert kwargs['timeout'] == 5
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(argv, 5)
        return subprocess.CompletedProcess(argv, 1 if failure == 'exit' else 0, b'unknown', b'')
    facts = SystemdUnitReader(run=run, home=str(tmp_path)).read_journal()
    assert facts['journal'] is None and facts['reason']
    assert find_secret(facts['reason']) is None and '--disk-usage' not in facts['reason']


def test_d9_busy_does_not_gate_ledger_verdicts():
    doc = models.empty_document(producer='test', started_at_utc='2026-10-03T00:00:00Z', host={})
    doc['sources']['seatWork'].update(ok=False, reason='busy', unavailable=True)
    doc['sources']['reasons'].update(ok=False, reason='busy', unavailable=True)
    doc['tasks']['rows'] = [{'key': 'persisted', 'outcome': 'failed', 'failureReason': 'runtime_error',
                             'outcomeAsOfUtc': '2026-10-02T00:00:00Z'}]
    row = models.fold_status_document(doc, now=T0)['seat_tasks_rows'][0]
    assert row['outcome'] == 'failed' and row['failureReason'] == 'runtime_error'
    assert row['outcomeAsOfUtc'] == '2026-10-02T00:00:00Z'


def test_d9_busy_keeps_ledger_day_counts_and_timestamp():
    doc = models.empty_document(producer='test', started_at_utc='2026-10-03T00:00:00Z', host={})
    doc['sources']['seatWork'].update(ok=False, reason='busy', unavailable=True)
    doc['today'].update(accepted=4, rejected=1, failed=2, pending=3, verdictLagP50S=15,
                        verdictsAsOfUtc='2026-10-02T00:00:00Z')
    flat = models.fold_status_document(doc, now=T0)
    assert flat['seat_today_accepted'] == 4 and flat['seat_today_failed'] == 2
    assert flat['seat_today_verdicts_as_of_utc'] == '2026-10-02T00:00:00Z'


def test_d5_recovery_is_per_error_and_requires_positive_model_output(tmp_path):
    fixture = json.loads(FIXTURE.read_text())
    error, output = fixture['records']
    path = tmp_path / 'synthetic.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in [error, output, error]) + '\n')
    session = scl.summarise_file(str(path), now=T0)
    assert [e['outputFollowed'] for e in session['apiErrors']] == [True, False]
    output['message']['usage']['output_tokens'] = 0
    path.write_text('\n'.join(json.dumps(r) for r in [error, output]) + '\n')
    assert scl.summarise_file(str(path), now=T0)['apiErrors'][0]['outputFollowed'] is False


@pytest.mark.asyncio
async def test_d10_nonzero_empty_attach_still_reports_failure(tmp_path):
    TailState(last_ts_utc='2026-10-03T00:00:00.000Z').save(tmp_path / 'seat_tail.json')
    m = manager(tmp_path, tail=ListLineSource([], exit_code=1))
    await m.backfill()
    assert (await document(m))['sources']['tail']['ok'] is False
    await m.close()


def test_d11_ledger_objective_and_session_text_pass_shared_sanitizer(tmp_path):
    from maxpane_dashboard.data.seat_ledger import SeatLedger
    ledger = SeatLedger(tmp_path / 'ledger.sqlite', seat=3, now=lambda: T0)
    ledger.seed_api_rows([{'submissionHash': 'a' * 64, 'submittedAt': '2026-10-03T00:00:00Z',
                          'status': 'accepted', 'objective': BLOB + ' $123', 'role': BLOB}], seat=3)
    row = ledger.rows()[0]
    assert row['objective'] and find_secret(row) is None and '$' not in row['objective']
    ledger.attach_sessions([{'path': 'synthetic', 'mtime': 1, 'kind': 'manual', 'model': BLOB,
                            'apiErrors': [{'status': 401, 'message': BLOB, 'secret': 'untrusted key'}],
                            'sideModel': {'model': BLOB, 'secret': 'untrusted key'}}], runtime='claude')
    raw = '\n'.join(ledger._conn.iterdump())
    assert 'eyJ' not in raw and '$123' not in raw and 'untrusted key' not in raw
    ledger.close()


@pytest.mark.asyncio
async def test_d9_busy_counts_only_real_reads_and_preserves_live_failure_threshold(tmp_path):
    now = [T0]
    requests = []
    def handler(req):
        requests.append(req.url.path)
        if len(requests) == 1:
            return httpx.Response(200, json={'standing': {'working': 1, 'running': []}})
        return httpx.Response(503, json={'error': 'busy'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = api_mod.SeatApiClient(http_client=http, now=lambda: now[0])
        m = SeatManager(maxpane_dir=tmp_path, now=lambda: now[0], api=api, seat=3, broker=FakeBroker(reachable=False))
        m._due_at.update({tier: float('inf') for tier in m._due_at if tier != 'standing'})
        await document(m)
        assert m.document()['standing']['working'] == 1
        for failures, moment in enumerate([60, 120, 240], 1):
            now[0] = T0 + moment
            m.bump('standing', 0)
            flat = await m.fetch_and_compute()
            await m.settle()
            flat = await m.fetch_and_compute()
            assert m._failures['standing'] == failures
            assert len(requests) == 1 + failures
            assert m.document()['sources']['standing']['reason'] == 'busy'
            assert m.document()['sources']['standing']['unavailable'] is (failures == 3)
            assert flat['seat_standing_working'] == (None if failures == 3 else 1)
            m.plan_open = True
            now[0] += 1
            for _ in range(4):
                m.bump('standing', 0)
                await document(m)
            assert m._failures['standing'] == failures and len(requests) == 1 + failures
        await m.close()


@pytest.mark.asyncio
async def test_d1_digit_string_route_and_submission_agent_identity():
    urls = []
    def handler(req):
        urls.append(req.url.path)
        return httpx.Response(200, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = api_mod.SeatApiClient(http_client=http)
        assert (await api.standing('003')).ok
        assert urls == ['/seats/3/standing']
    assert api_mod.normalise_submission({'seat': {'tokenId': '3', 'agentId': '51075'}})['seatAgentId'] == 51075
    for value in [True, 3.0, '-3', '3.0', '٣', '']:
        assert api_mod.identity_int(value) is None
