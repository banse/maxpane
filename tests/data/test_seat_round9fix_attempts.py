"""Unique standing/local attempt joins, exercised through manager consumers."""
from types import SimpleNamespace
import pytest
from maxpane_dashboard.analytics.seat_signals import parse_iso
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
