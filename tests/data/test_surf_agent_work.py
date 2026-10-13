"""Accepted work counts retain unknown membership until all jobs are checked."""
import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from maxpane_dashboard.data import surf_agent_work as work

NOW = 1_800_000_000.0
LIVE = 'f708c332-034f-47b3-b204-318734811863'
BLOCKED = '6a7439e9-e9aa-469b-bdb5-633bd6c7f423'
PLAIN = '22624be0-d2da-400e-91c4-51dac0a9a7f5'
FIXTURES = Path('tests/fixtures/surf/agent_work')


def capture(job):
    return json.loads((FIXTURES / f'{job}.json').read_text())


def row(job, node='build', status='accepted'):
    return dict(jobId=job, nodeKey=node, status=status)


def point(launched=False, age=0):
    return dict(read_ts=NOW-age, launched=launched)


def test_exact_captures_require_actual_launch_not_requested_kind():
    assert work.membership_point(capture(LIVE), LIVE, NOW) == point(True)
    assert work.membership_point(capture(BLOCKED), BLOCKED, NOW) == point(False)
    assert work.membership_point(capture(PLAIN), PLAIN, NOW) == point(False)


@pytest.mark.parametrize('change', [
    {'id': PLAIN}, {'launch': None}, {'launch': {}},
    {'launch': {'requested': True}},
])
def test_missing_or_mismatched_evidence_is_unknown(change):
    raw = capture(LIVE)
    raw.update(change)
    assert work.membership_point(raw, LIVE, NOW) is None


@pytest.mark.parametrize('field,value', [
    ('requested', 1), ('requested', False), ('kind', None), ('kind', ''),
    ('id', 'bad'), ('id', None), ('status', None), ('status', 'future-state'),
    ('chainId', True), ('chainId', 0), ('chainId', '1'), ('chainId', None),
])
def test_malformed_launch_never_becomes_a_positive_or_negative(field, value):
    raw = capture(LIVE)
    raw['launch'][field] = value
    assert work.membership_point(raw, LIVE, NOW) is None


def test_live_testnet_counts_and_parked_launch_is_checked_but_not_live():
    raw = capture(LIVE)
    raw['launch']['chainId'] = 11155111
    assert work.membership_point(raw, LIVE, NOW) == point(True)
    raw['launch']['status'] = 'parked'
    assert work.membership_point(raw, LIVE, NOW) == point(False)


def test_accepted_rows_and_ids_keep_legacy_rows_exclude_other_attempts():
    legacy = row(PLAIN)
    del legacy['status']
    seat = {'work': [row(LIVE), row(LIVE, 'review'), legacy,
                     row(BLOCKED, status='pending'), row(BLOCKED, status='rejected')]}
    assert work.accepted_rows(seat) == seat['work'][:3]
    assert work.accepted_job_ids(seat) == {LIVE, PLAIN}
    assert work.candidates(seat) == [LIVE, PLAIN]


def test_summary_counts_work_rows_oracle_precedes_launch_and_unknown_blocks_partition():
    seat = {'work': [row(LIVE), row(LIVE, 'review'), row(LIVE, 'oracle_assess'),
                     row(PLAIN), row(BLOCKED), row(BLOCKED, status='failed')]}
    partial = work.summarize(seat, {LIVE: point(True), PLAIN: point()}, NOW)
    assert partial == dict(oracle=1, launches=None, other=None, known_jobs=2, total_jobs=3)
    assert work.summarize(seat, {LIVE: point(True), PLAIN: point(), BLOCKED: point()}, NOW) == dict(
        oracle=1, launches=2, other=2, known_jobs=3, total_jobs=3)
    assert work.candidates({'work': [row(LIVE, 'oracle_assess')]}) == []
    assert work.summarize({'work': [row(LIVE, 'oracle_assess')]}, {}, NOW) == dict(
        oracle=1, launches=0, other=0, known_jobs=0, total_jobs=0)


@pytest.mark.parametrize('seat', [None, {}, {'work': None}, {'work': [None]},
                                   {'work': [dict(jobId=LIVE)]}])
def test_missing_or_malformed_work_is_not_zero(seat):
    assert work.accepted_rows(seat) is None
    assert work.summarize(seat, {}, NOW) == dict(
        oracle=None, launches=None, other=None, known_jobs=None, total_jobs=None)


def test_true_empty_work_and_invalid_job_coverage_are_distinct():
    assert work.summarize({'work': []}, {}, NOW) == dict(
        oracle=0, launches=0, other=0, known_jobs=0, total_jobs=0)
    assert work.summarize({'work': [row(None), row(LIVE)]}, {LIVE: point(True)}, NOW) == dict(
        oracle=0, launches=None, other=None, known_jobs=1, total_jobs=2)


@pytest.mark.parametrize('bad', [None, {}, dict(read_ts=NOW),
    dict(read_ts=NOW, launched=1), dict(read_ts=NOW, launched=False, extra=1),
    dict(read_ts=True, launched=False), dict(read_ts=float('nan'), launched=False),
    dict(read_ts=float('inf'), launched=False), dict(read_ts=NOW+1, launched=False),
    dict(read_ts=10**1000, launched=False),
    dict(read_ts=-1, launched=False), dict(read_ts=NOW-48*3600-1, launched=False)])
def test_persisted_points_are_validated_independently(bad):
    values = {LIVE: point(True), BLOCKED: bad, 'bad-job': point()}
    assert work.coerce_points(values, NOW) == {LIVE: point(True)}


def test_cache_retention_boundary_and_newest_cap():
    assert work.coerce_points({LIVE: point(age=48*3600)}, NOW) == {LIVE: point(age=48*3600)}
    values = {str(UUID(int=i+1)): point(age=i) for i in range(405)}
    got = work.coerce_points(values, NOW)
    assert len(got) == 400
    assert str(UUID(int=400)) in got and str(UUID(int=401)) not in got


def test_due_prioritizes_unknown_then_oldest_expired_and_terminal_jobs_refresh():
    seat = {'work': [row(LIVE), row(BLOCKED), row(PLAIN), row(LIVE, 'review')]}
    seat['work'][0]['jobState'] = 'completed'
    points = {LIVE: point(True, 600), BLOCKED: point(False, 700)}
    assert work.due(seat, points, NOW) == [PLAIN, BLOCKED, LIVE]
    assert work.due(seat, points, NOW, cap=2) == [PLAIN, BLOCKED]
    assert work.due(seat, dict(points, **{PLAIN: point(False, 599)}), NOW) == [BLOCKED, LIVE]
    assert work.due({'work': [row(LIVE, 'oracle_assess')]}, {}, NOW) == []


def test_helpers_do_not_mutate_raw_payload_or_cache():
    raw, seat, points = capture(LIVE), {'work': [row(LIVE)]}, {LIVE: point(True)}
    before = copy.deepcopy((raw, seat, points))
    work.membership_point(raw, LIVE, NOW)
    work.summarize(seat, points, NOW)
    work.due(seat, points, NOW)
    assert (raw, seat, points) == before
