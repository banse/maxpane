"""Unique standing/local attempt joins, exercised through manager consumers."""
from types import SimpleNamespace
import pytest
from maxpane_dashboard.analytics.seat_signals import parse_iso
from maxpane_dashboard.data.seat_api import ApiResult
from maxpane_dashboard.data.seat_ledger import SeatLedger
from maxpane_dashboard.data.seat_log_grammar import classify
from maxpane_dashboard.data.seat_manager import SeatManager

JOB = 'job-a'
NOW = parse_iso('2026-10-03T10:01:00Z')


def local(node, stamp, **extra):
    return dict(key='3/' + node + '/' + stamp, source={'row': 'local'}, jobId=JOB,
                nodeId8=node, nodeKey=None, acceptedUtc=stamp, submittedUtc=None,
                phases=['accepted', 'working'], **extra)


def plane(stamp, node='tests', **extra):
    return dict(jobId=JOB, nodeKey=node, since=stamp, objective='plane ' + node, role='implement', **extra)


def manager(rows, planes):
    result = SeatManager.__new__(SeatManager)
    result._ledger = SimpleNamespace(record_rows=lambda: rows)
    result._offline = False
    result._payload = lambda _: {'running': planes}
    result._source_entry = lambda *_: {'unavailable': False}
    return result


@pytest.fixture
def attempt_ledger(tmp_path):
    ledger = SeatLedger(tmp_path / 'attempts.sqlite', seat=3, now=lambda: NOW)
    yield ledger
    ledger.close()


def accept_attempt(ledger, node, stamp, *, job=JOB):
    stamp = stamp if '.' in stamp else stamp.replace('Z', '.000Z')
    result = ledger.ingest([classify(stamp + f' accepted implement {node} — q (max 60 turns)'),
                            classify(stamp + '   working: running codex on fixture-model')])
    assert result.opened == 1 and result.unknown == 0
    if job is not None:
        ledger.attach_work_dirs([dict(jobId=job, nodeId=node + '-0000-4000-8000-000000000000',
                                      mtimeUtc=stamp)])


def close_attempt(ledger, node, stamp, closed):
    stamp = stamp if '.' in stamp else stamp.replace('Z', '.000Z')
    text = {'submitted': f'submitted implement for {node}', 'failed': 'task failed: fixture failure',
            'cancelled': 'cancelled 12345678: superseded',
            'interrupted': 'runtimes: codex codex-cli 0.157.0 (using codex, as asked)'}[closed]
    ledger.ingest([classify(stamp + ' ' + text)])


def stored_node_name(ledger, node_key, stamp, digest):
    ledger.ingest([classify(stamp + f' submission stored ({digest[:12]}) — awaiting verdict')])
    ledger.attach_work([dict(jobId=JOB, submissionHash=digest, submittedAt=stamp,
                             nodeKey=node_key, status='failed')], as_of_utc=stamp)


def closed_dag_scenario(ledger, closed):
    accept_attempt(ledger, 'bbbb2222', '2026-10-03T10:00:03Z')
    if closed != 'submitted':
        close_attempt(ledger, 'bbbb2222', '2026-10-03T10:00:15Z', closed)
    accept_attempt(ledger, 'aaaa1111', '2026-10-03T10:00:22Z')
    if closed == 'submitted':
        close_attempt(ledger, 'bbbb2222', '2026-10-03T10:00:50Z', closed)
    rows = ledger.record_rows()
    assert len(rows) == 2
    assert all(row['source']['row'] == 'local' and row['nodeKey'] is None for row in rows)
    return rows, [plane('2026-10-03T10:00:01Z', 'contracts'), plane('2026-10-03T10:00:20Z')]


def test_realistic_two_attempts_pair_by_start_not_list_order():
    rows = [local('aaaa1111', '2026-10-03T10:00:03Z'), local('bbbb2222', '2026-10-03T10:00:22Z')]
    planes = [plane('2026-10-03T10:00:20Z'), plane('2026-10-03T10:00:01Z', 'contracts')]
    current, chosen = manager(rows, planes)._job_rows(NOW)
    assert {r['nodeId8']: r['nodeKey'] for r in current} == {'aaaa1111': 'contracts', 'bbbb2222': 'tests'}
    assert {r['nodeId8']: r['nodeKey'] for r in chosen} == {'aaaa1111': 'contracts', 'bbbb2222': 'tests'}


def test_ambiguous_same_second_accepts_stay_unlabelled_without_phantom():
    rows = [local(node, '2026-10-03T10:00:03Z') for node in ('aaaa1111', 'bbbb2222')]
    current = manager(rows, [plane('2026-10-03T10:00:01Z')])._current_jobs(NOW)
    assert len(current) == 2
    assert all(r['nodeKey'] is None for r in current)


def test_one_local_claimed_by_two_planes_pairs_with_neither():
    rows = [local('aaaa1111', '2026-10-03T10:00:03Z')]
    current = manager(rows, [plane('2026-10-03T10:00:01Z'), plane('2026-10-03T10:00:02Z', 'contracts')])._current_jobs(NOW)
    assert len(current) == 1
    assert current[0]['nodeKey'] is None


def test_missed_accept_keeps_plane_only_row_and_pairs_later_accept():
    rows = [local('bbbb2222', '2026-10-03T10:00:32Z')]
    current = manager(rows, [plane('2026-10-03T10:00:01Z', 'contracts'), plane('2026-10-03T10:00:30Z')])._current_jobs(NOW)
    assert len(current) == 2
    assert next(r for r in current if r.get('nodeId8'))['nodeKey'] == 'tests'
    assert next(r for r in current if not r.get('nodeId8'))['nodeKey'] == 'contracts'


@pytest.mark.parametrize('offset,paired', [(-3, False), (-2, True), (8, True), (9, False)])
def test_exact_asymmetric_window_never_overrides_known_time(offset, paired):
    rows = [local('aaaa1111', f'2026-10-03T10:00:{20 + offset:02d}Z')]
    current = manager(rows, [plane('2026-10-03T10:00:20Z')])._current_jobs(NOW)
    assert len(current) == 1  # same-job unpaired local suppresses a duplicate plane row
    assert (current[0]['nodeKey'] == 'tests') is paired


@pytest.mark.parametrize('accepted,since', [(None, None), ('2026-10-03T10:00:03Z', None)])
def test_single_pair_without_time_evidence_keeps_labels(accepted, since):
    row = local('aaaa1111', accepted or 'unknown')
    row['acceptedUtc'] = accepted
    assert manager([row], [plane(since)])._current_jobs(NOW)[0]['nodeKey'] == 'tests'


def test_unknown_local_job_pairs_by_time():
    row = local('aaaa1111', '2026-10-03T10:00:03Z')
    row['jobId'] = None
    current, chosen = manager([row], [plane('2026-10-03T10:00:01Z')])._job_rows(NOW)
    assert len(current) == 1 and current[0]['jobId'] == JOB
    assert chosen[0]['key'] == row['key'] and chosen[0]['nodeKey'] == 'tests'


def test_known_node_contradiction_never_joins():
    row = local('aaaa1111', '2026-10-03T10:00:03Z')
    row['nodeKey'] = 'contracts'
    current = manager([row], [plane('2026-10-03T10:00:01Z')])._current_jobs(NOW)
    assert len(current) == 1 and current[0]['nodeKey'] == 'contracts'


@pytest.mark.parametrize('closed', ['submitted', 'failed', 'cancelled', 'interrupted'])
def test_old_finished_attempt_never_supplies_live_usage_or_verdict(closed):
    row = local('aaaa1111', '2026-10-03T09:00:03Z', outcome='failed', usage={'turns': 9}, structuralCheck={'status': 'accepted'})
    row['nodeKey'] = 'tests'
    row.update({'submittedUtc': '2026-10-03T09:01:00Z'} if closed == 'submitted' else
               {'phases': ['accepted', 'failed']} if closed == 'failed' else
               {'cancelled': True} if closed == 'cancelled' else {'interruptedByRestart': True})
    current, chosen = manager([row], [plane('2026-10-03T10:00:01Z')])._job_rows(NOW)
    live = chosen[0]
    assert len(current) == 1 and live.get('key') is None
    assert live.get('outcome') is None and live.get('usage') is None and live.get('structuralCheck') is None


@pytest.mark.parametrize('closed', ['submitted', 'failed', 'cancelled', 'interrupted'])
def test_stale_standing_start_identifies_closed_attempt(closed):
    row = local('aaaa1111', '2026-10-03T10:00:03Z', lastMessageUtc='2026-10-03T10:00:30Z')
    row['nodeKey'] = 'tests'
    row.update({'submittedUtc': '2026-10-03T10:00:30Z'} if closed == 'submitted' else
               {'phases': ['accepted', 'failed']} if closed == 'failed' else
               {'cancelled': True} if closed == 'cancelled' else {'interruptedByRestart': True})
    assert manager([row], [plane('2026-10-03T10:00:01Z')])._current_jobs(NOW) == []


def test_known_node_name_takes_precedence_over_unlabelled_candidate():
    unnamed = local('aaaa1111', '2026-10-03T10:00:03Z')
    named = local('bbbb2222', '2026-10-03T10:00:03Z')
    named['nodeKey'] = 'tests'
    planes = [plane('2026-10-03T10:00:01Z'), plane('2026-10-03T10:00:01Z', 'contracts')]
    current = manager([unnamed, named], planes)._current_jobs(NOW)
    assert {r['nodeId8']: r['nodeKey'] for r in current} == {'aaaa1111': 'contracts', 'bbbb2222': 'tests'}


def test_missing_stamps_do_not_override_multiple_local_attempts():
    named = local('bbbb2222', 'unknown')
    named.update(nodeKey='contracts', acceptedUtc=None)
    unnamed = local('aaaa1111', 'unknown')
    unnamed['acceptedUtc'] = None
    current = manager([unnamed, named], [plane(None)])._current_jobs(NOW)
    assert len(current) == 2 and next(r for r in current if r['nodeId8'] == 'aaaa1111')['nodeKey'] is None


@pytest.mark.parametrize('known_job', [False, True], ids=['unknown-job', 'known-job'])
@pytest.mark.parametrize('field,value', [
    ('acceptedUtc', None), ('acceptedUtc', 'not-a-timestamp'), ('acceptedUtc', 'missing'),
    ('since', None), ('since', 'not-a-timestamp'), ('since', 'missing'),
])
@pytest.mark.parametrize('named_node', [False, True], ids=['unlabelled', 'named'])
def test_unknown_job_requires_usable_start_evidence_even_for_singleton(known_job, field, value, named_node):
    row = local('aaaa1111', '2026-10-03T10:00:03Z')
    row['jobId'] = JOB if known_job else None
    row['nodeKey'] = 'tests' if named_node else None
    live = plane('2026-10-03T10:00:01Z')
    target = row if field == 'acceptedUtc' else live
    if value == 'missing':
        target.pop(field)
    else:
        target[field] = value
    current, chosen = manager([row], [live])._job_rows(NOW)
    assert len(current) == (1 if known_job else 2)
    local_current = next(r for r in current if r.get('nodeId8') == 'aaaa1111')
    assert local_current['jobId'] == (JOB if known_job else None)
    assert local_current['nodeKey'] == ('tests' if known_job or named_node else None)
    assert local_current.get('planeSince') == (live.get('since') if known_job else None)
    assert next(r for r in chosen if r.get('key') == row['key'])['jobId'] == (JOB if known_job else None)
    if not known_job:
        plane_only = next(r for r in current if not r.get('nodeId8'))
        assert plane_only['jobId'] == JOB and plane_only['nodeKey'] == 'tests'
        assert local_current['objective'] is None


@pytest.mark.parametrize('closed', ['submitted', 'failed', 'cancelled', 'interrupted'])
def test_ledger_closed_dag_attempt_without_node_name_stops_working(attempt_ledger, closed):
    rows, planes = closed_dag_scenario(attempt_ledger, closed)
    current, chosen = manager(rows, planes)._job_rows(NOW)
    assert len(current) == 1 and len(chosen) == (2 if closed == 'submitted' else 1)
    assert current[0]['nodeId8'] == 'aaaa1111' and current[0]['nodeKey'] == 'tests'
    assert chosen[0]['key'] == current[0]['key']


def test_ledger_closed_unknown_job_can_remove_unique_stale_plane(attempt_ledger):
    accept_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03Z', job=None)
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:15Z', 'failed')
    rows = attempt_ledger.record_rows()
    assert rows[0]['jobId'] is None and rows[0]['nodeKey'] is None
    assert manager(rows, [plane('2026-10-03T10:00:01Z')])._current_jobs(NOW) == []


@pytest.mark.parametrize('named', [False, True], ids=['unnamed', 'named'])
@pytest.mark.parametrize('ambiguity', ['planes', 'locals'])
def test_ledger_ambiguous_closed_evidence_keeps_all_planes(attempt_ledger, named, ambiguity):
    accept_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03Z')
    if ambiguity == 'locals':
        accept_attempt(attempt_ledger, 'bbbb2222', '2026-10-03T10:00:04Z')
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:20Z', 'submitted')
    if named:
        stored_node_name(attempt_ledger, 'tests', '2026-10-03T10:00:20.100Z', 'a' * 64)
    if ambiguity == 'locals':
        close_attempt(attempt_ledger, 'bbbb2222', '2026-10-03T10:00:21Z', 'submitted')
        if named:
            stored_node_name(attempt_ledger, 'tests', '2026-10-03T10:00:21.100Z', 'b' * 64)
    rows = attempt_ledger.record_rows()
    assert all(row['source']['row'] == 'local' for row in rows)
    assert all(row['nodeKey'] == ('tests' if named else None) for row in rows)
    planes = [plane('2026-10-03T10:00:01Z')]
    if ambiguity == 'planes':
        planes.append(plane('2026-10-03T10:00:02Z'))
    current = manager(rows, planes)._current_jobs(NOW)
    assert len(current) == len(planes)
    assert {row['planeSince'] for row in current} == {row['since'] for row in planes}


@pytest.mark.parametrize('named', [False, True], ids=['unnamed', 'named'])
def test_api_closed_rows_never_remove_standing_attempt(attempt_ledger, named):
    attempt_ledger.seed_api_rows([dict(jobId=JOB, submissionHash='a' * 64,
                                      acceptedAt='2026-10-03T10:00:03Z', submittedAt='2026-10-03T10:00:03Z',
                                      nodeKey='tests' if named else None, status='failed')], seat=3)
    rows = attempt_ledger.record_rows()
    assert rows[0]['source']['row'] == 'api'
    current = manager(rows, [plane('2026-10-03T10:00:01Z')])._current_jobs(NOW)
    assert len(current) == 1 and current[0]['nodeKey'] == 'tests'


def test_removing_stale_plane_restores_ambiguous_open_attempt_labels(attempt_ledger):
    accept_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03Z')
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:06Z', 'failed')
    accept_attempt(attempt_ledger, 'bbbb2222', '2026-10-03T10:00:09Z')
    planes = [plane('2026-10-03T10:00:01Z', 'contracts'), plane('2026-10-03T10:00:09Z')]
    current, chosen = manager(attempt_ledger.record_rows(), planes)._job_rows(NOW)
    assert len(current) == len(chosen) == 1
    assert current[0]['nodeId8'] == 'bbbb2222' and current[0]['nodeKey'] == 'tests'
    assert chosen[0]['nodeKey'] == 'tests' and current[0]['planeSince'] == planes[1]['since']


def test_open_attempt_keeps_labels_when_closed_attempt_learned_same_node(attempt_ledger):
    accept_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03Z')
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03.500Z', 'failed')
    attempt_ledger.store_job_detail(JOB, ApiResult(True, dict(jobId=JOB, state='running', nodes=[
        dict(key='a', state='failed', role='implement', seatTokenId=3, failureReason='timeout')]),
        200, '2026-10-03T10:00:04Z', None, 0, '/jobs/fixture'))
    assert attempt_ledger.record_rows()[0]['nodeKey'] == 'a'
    accept_attempt(attempt_ledger, 'bbbb2222', '2026-10-03T10:00:05Z')
    current, chosen = manager(attempt_ledger.record_rows(), [plane('2026-10-03T10:00:04Z', 'a')])._job_rows(NOW)
    assert len(current) == len(chosen) == 1
    assert current[0]['nodeId8'] == 'bbbb2222' and current[0]['nodeKey'] == 'a'
    assert current[0]['role'] == 'implement' and current[0]['planeSince'] == '2026-10-03T10:00:04Z'
    assert chosen[0]['nodeKey'] == 'a' and chosen[0]['objective'] == 'plane a'


def test_second_pairing_preserves_first_pair_with_unknown_plane_job(attempt_ledger):
    accept_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03Z')
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:06Z', 'failed')
    accept_attempt(attempt_ledger, 'bbbb2222', '2026-10-03T10:00:15Z')
    first = plane('2026-10-03T10:00:14Z')
    first['jobId'] = None
    planes = [first, plane('2026-10-03T10:00:01Z', 'contracts'), plane(None, 'other')]
    current = manager(attempt_ledger.record_rows(), planes)._current_jobs(NOW)
    matched = next(row for row in current if row.get('nodeId8') == 'bbbb2222')
    assert matched['nodeKey'] == 'tests' and matched['planeSince'] == first['since']
    assert not any(row['nodeKey'] == 'contracts' for row in current)


@pytest.mark.parametrize('offset,stale', [(-3, False), (-2, True), (8, True), (9, False)])
def test_unnamed_closed_evidence_keeps_exact_start_window(attempt_ledger, offset, stale):
    accept_attempt(attempt_ledger, 'aaaa1111', f'2026-10-03T10:00:{20 + offset:02d}Z')
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:40Z', 'failed')
    current = manager(attempt_ledger.record_rows(), [plane('2026-10-03T10:00:20Z')])._current_jobs(NOW)
    assert (current == []) is stale


@pytest.mark.parametrize('field', ['jobId', 'key', 'nodeId8', 'nodeKey'])
def test_unnamed_closed_evidence_never_overrides_known_contradiction(attempt_ledger, field):
    accept_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:03Z')
    close_attempt(attempt_ledger, 'aaaa1111', '2026-10-03T10:00:20Z', 'submitted')
    if field == 'nodeKey':
        stored_node_name(attempt_ledger, 'contracts', '2026-10-03T10:00:20.100Z', 'a' * 64)
    live = plane('2026-10-03T10:00:01Z')
    live[field] = 'contradicting-value'
    current = manager(attempt_ledger.record_rows(), [live])._current_jobs(NOW)
    assert len(current) == 1 and current[0]['planeSince'] == live['since']
