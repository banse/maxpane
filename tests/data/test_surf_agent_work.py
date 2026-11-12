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


def point(launched=False, age=0, chain_id=None, shipped=None):
    return dict(read_ts=NOW-age, launched=launched,
                chain_id=chain_id if chain_id is not None else 1 if launched else None,
                shipped=launched if shipped is None else shipped,
                family="launch" if launched or chain_id is not None else "other")


def complete_history(seat):
    """Give synthetic full-history fixtures the served lifetime counters."""
    if not isinstance(seat, dict) or not isinstance(seat.get('work'), list):
        return seat
    return dict(dict(attempts=len(seat['work']), accepted=sum(
        isinstance(row, dict) and row.get('status') == 'accepted' for row in seat['work'])), **seat)


def test_exact_captures_require_actual_launch_not_requested_kind():
    assert work.membership_point(capture(LIVE), LIVE, NOW) == point(True)
    assert work.membership_point(capture(BLOCKED), BLOCKED, NOW) == point(False, chain_id=11155111)
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


def test_testnet_membership_remains_available_for_record_but_not_shipped():
    raw = capture(LIVE)
    raw['launch']['chainId'] = 11155111
    testnet = work.membership_point(raw, LIVE, NOW)
    assert testnet == point(True, chain_id=11155111)
    assert work.summarize(complete_history({'work': [row(LIVE)]}), {LIVE: testnet}, NOW)['launches'] == 0
    assert work.record_rows([dict(job_id=LIVE, node_key='build')], {LIVE: testnet}, now=NOW)[0]['launch_state'] == 'launched'
    raw['launch']['status'] = 'parked'
    assert work.membership_point(raw, LIVE, NOW) == point(False, chain_id=11155111)


def test_accepted_rows_and_ids_keep_legacy_rows_exclude_other_attempts():
    legacy = row(PLAIN)
    del legacy['status']
    seat = {'work': [row(LIVE), row(LIVE, 'review'), legacy,
                     row(BLOCKED, status='pending'), row(BLOCKED, status='rejected')]}
    assert work.accepted_rows(seat) == seat['work'][:3]
    assert work.accepted_job_ids(seat) == {LIVE, PLAIN}
    assert work.candidates(seat) == [LIVE, PLAIN]


def test_summary_counts_distinct_jobs_oracle_precedes_launch_and_completeness_is_independent():
    seat = {'work': [row(LIVE), row(LIVE, 'review'), row(PLAIN, 'oracle_assess'),
                     row(PLAIN, 'build'), row(PLAIN, 'oracle_assess'), row(BLOCKED)]}
    assert work.candidates(seat) == [LIVE, BLOCKED]
    assert work.oracle_candidates(seat) == [PLAIN]
    partial = work.summarize(complete_history(seat), {LIVE: point(True)}, NOW, oracle_chains={PLAIN: 1})
    assert partial == dict(oracle=1, launches=None, other=None, known_jobs=1, total_jobs=2, launches_total=None, oracle_total=1, research=None, research_total=None)
    points = {LIVE: point(True), BLOCKED: point()}
    assert work.summarize(complete_history(seat), points, NOW, oracle_chains={PLAIN: 1}) == dict(
        oracle=1, launches=1, other=1, known_jobs=2, total_jobs=2, launches_total=1, oracle_total=1, research=1, research_total=1)
    assert work.summarize(complete_history(seat), points, NOW) == dict(
        oracle=None, launches=1, other=1, known_jobs=2, total_jobs=2, launches_total=1, oracle_total=None, research=None, research_total=None)
    assert work.summarize(complete_history(seat), points, NOW, oracle_chains={PLAIN: 11155111})['oracle'] == 0


@pytest.mark.parametrize('chain,oracle', [
    (1, 1), (8453, 1), (4663, 1), (56, 1), (42161, 1),
    (11155111, 0), (84532, 0), (46630, 0), (97, 0), (421614, 0), (999999, None),
])
def test_launch_policy_and_verified_oracle_network_classification(chain, oracle):
    seat = {'work': [row(LIVE), row(PLAIN, 'oracle_assess')]}
    got = work.summarize(complete_history(seat), {LIVE: point(True, chain_id=chain)}, NOW,
                         oracle_chains={PLAIN: chain})
    assert got['launches'] == int(chain in (1, 8453, 4663))
    assert got['oracle'] == oracle


@pytest.mark.parametrize('chains', [{}, {PLAIN: None}, {PLAIN: True}, {PLAIN: '1'}, {PLAIN: 0}])
def test_missing_or_invalid_oracle_chain_is_unknown_without_blocking_launches(chains):
    seat = {'work': [row(LIVE), row(PLAIN, 'oracle_assess')]}
    got = work.summarize(complete_history(seat), {LIVE: point(True)}, NOW, oracle_chains=chains)
    assert got['oracle'] is None and got['launches'] == 1


def test_oracle_invalid_job_never_uses_objective_or_seat_registration_chain():
    seat = {'chainId': 1, 'work': [dict(row(None, 'oracle_assess'), objective='chain 1')]}
    assert work.summarize(complete_history(seat), {}, NOW)['oracle'] is None
    assert work.oracle_candidates(seat) == []


@pytest.mark.parametrize('launched', [False, True])
def test_legacy_cache_keeps_record_membership_but_shipped_requires_backfill(launched):
    old = {LIVE: dict(read_ts=NOW, launched=launched)}
    seat = {'work': [row(LIVE)]}
    assert work.coerce_points(old, NOW) == old
    assert work.summarize(complete_history(seat), old, NOW)['launches'] is None
    assert work.due(seat, old, NOW) == [LIVE]
    assert work.record_rows([dict(job_id=LIVE, node_key='build')], old, now=NOW)[0]['launch_state'] == (
        'launched' if launched else 'not_launched')


@pytest.mark.parametrize('seat', [None, {}, {'work': None}, {'work': [None]},
                                   {'work': [dict(jobId=LIVE)]}])
def test_missing_or_malformed_work_is_not_zero(seat):
    assert work.accepted_rows(seat) is None
    assert work.summarize(complete_history(seat), {}, NOW) == dict(
        oracle=None, launches=None, other=None, known_jobs=None, total_jobs=None, launches_total=None, oracle_total=None, research=None, research_total=None)


def test_true_empty_work_and_invalid_job_coverage_are_distinct():
    assert work.summarize(complete_history({'work': []}), {}, NOW) == dict(
        oracle=0, launches=0, other=0, known_jobs=0, total_jobs=0, launches_total=0, oracle_total=0, research=0, research_total=0)
    assert work.summarize(complete_history({'work': [row(None), row(LIVE)]}), {LIVE: point(True)}, NOW) == dict(
        oracle=0, launches=None, other=None, known_jobs=1, total_jobs=2, launches_total=None, oracle_total=None, research=None, research_total=None)


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
    work.summarize(complete_history(seat), points, NOW)
    work.due(seat, points, NOW)
    assert (raw, seat, points) == before


def test_record_membership_discovery_includes_all_attempts_without_changing_nodes_counts():
    seat = {'work': [row(LIVE), row(BLOCKED, status='failed'), row(BLOCKED, status='rejected'),
                     row(PLAIN, 'oracle_assess'), row(None), None]}
    assert work.record_candidates(seat) == [LIVE, BLOCKED]
    valid = dict(seat, work=seat['work'][:4])
    assert work.candidates(valid) == [LIVE]
    assert work.due(valid, {}, NOW, include_attempts=True) == [LIVE, BLOCKED]
    assert work.summarize(complete_history(valid), {LIVE: point(True), BLOCKED: point(True)}, NOW)['launches'] == 1


def test_record_rows_require_confirmed_launch_and_count_unknowns_without_mutation():
    rows = [dict(job_id=LIVE, node_key='audit', work_status='failed', launch=None),
            dict(job_id=BLOCKED, node_key='build', launch='custom_token'),
            dict(job_id=PLAIN, node_key='build', launch='custom_token'),
            dict(job_id=LIVE, node_key='oracle_assess'), dict(job_id=None, node_key='build')]
    points = {LIVE: point(True), BLOCKED: point(False)}
    original = copy.deepcopy((rows, points))
    enriched = work.record_rows(rows, points, now=NOW)
    assert [r['launch_state'] for r in enriched] == [
        'launched', 'not_launched', 'not_read', 'not_launched', 'unavailable']
    assert work.record_rows(rows, points, failed={LIVE}, now=NOW)[0]['launch_state'] == 'unavailable'
    assert work.record_rows(rows, points, now=NOW+48*3600+1)[0]['launch_state'] == 'not_read'
    assert (rows, points) == original


@pytest.mark.parametrize('changes', [
    dict(chain_id=True), dict(chain_id='1'), dict(chain_id=0), dict(chain_id=-1),
    dict(shipped=1), dict(shipped='true'), dict(shipped=None), dict(shipped=False), dict(chain_id=None),
])
def test_new_cache_rejects_invalid_chain_or_shipped_evidence(changes):
    assert work.coerce_points({LIVE: dict(point(True), **changes)}, NOW) == {}


def test_missing_workflow_evidence_does_not_prove_no_launch_contribution():
    raw = capture(PLAIN)
    del raw['workflow']
    assert work.membership_point(raw, PLAIN, NOW) is None


def test_all_job_totals_include_unsuccessful_attempts_dedupe_and_exclude_testnets():
    testnet, oracle_failed, oracle_testnet = (str(UUID(int=n)) for n in (901, 902, 903))
    seat = {'work': [row(LIVE), row(LIVE, 'review'), row(BLOCKED, status='failed'),
                     row(BLOCKED, status='rejected'), row(testnet),
                     row(PLAIN, 'oracle_assess'), row(oracle_failed, 'oracle_assess', 'pending'),
                     row(oracle_testnet, 'oracle_assess')]}
    points = {LIVE: point(True), BLOCKED: point(True), testnet: point(True, chain_id=11155111)}
    chains = {PLAIN: 1, oracle_failed: 8453, oracle_testnet: 11155111}
    result = work.summarize(complete_history(seat), points, NOW, oracle_chains=chains)
    assert (result['launches'], result['launches_total']) == (1, 2)
    assert (result['oracle'], result['oracle_total']) == (1, 2)
    assert work.oracle_candidates(seat, include_attempts=True) == [PLAIN, oracle_failed, oracle_testnet]
    assert work.oracle_candidates(seat) == [PLAIN, oracle_testnet]
    del points[BLOCKED]
    partial = work.summarize(complete_history(seat), points, NOW, oracle_chains=chains)
    assert partial['launches'] == 1 and partial['launches_total'] is None
    assert partial['oracle_total'] == 2
    del chains[oracle_failed]
    assert work.summarize(complete_history(seat), points, NOW, oracle_chains=chains)['oracle_total'] is None


def test_totals_do_not_invent_legacy_or_malformed_attempt_coverage():
    for bad in ({'jobId': LIVE, 'nodeKey': 'build'}, row(LIVE, status='new-status'),
                row(LIVE, status=None), row(None, status='failed')):
        result = work.summarize(complete_history({'work': [bad]}), {LIVE: point(True)}, NOW)
        assert result['launches_total'] is None
    empty = work.summarize(complete_history({'work': []}), {}, NOW)
    assert empty['launches_total'] == empty['oracle_total'] == 0


@pytest.mark.parametrize('rows', [None, True, {}, [None], [{'nodeKey': []}]])
def test_oracle_total_discovery_skips_malformed_work_without_crashing(rows):
    assert work.oracle_candidates({'work': rows}, include_attempts=True) == []


@pytest.mark.parametrize('accepted_node', ['implement', 'oracle_assess'])
@pytest.mark.parametrize('reverse', [False, True])
def test_mixed_job_uses_one_category_and_any_accepted_contribution(accepted_node, reverse):
    rejected_node = 'oracle_assess' if accepted_node == 'implement' else 'implement'
    rows = [row(LIVE, accepted_node), row(LIVE, rejected_node, 'rejected'),
            row(LIVE, accepted_node), row(PLAIN, 'oracle_assess', 'failed'),
            row(BLOCKED, 'build', 'pending')]
    if reverse:
        rows.reverse()
    seat = {'work': rows}
    before = copy.deepcopy(seat)
    points = {LIVE: point(True), BLOCKED: point(True)}
    for chain, accepted, total in [(1, 1, 2), (11155111, 0, 0), (None, None, None)]:
        result = work.summarize(complete_history(seat), points, NOW, oracle_chains={LIVE: chain, PLAIN: chain})
        assert (result['oracle'], result['oracle_total']) == (accepted, total)
        assert (result['launches'], result['launches_total']) == (0, 1)
    # Earnings and accepted-membership callers still receive accepted work only.
    assert work.accepted_job_ids(seat) == {LIVE}
    assert work.accepted_rows(seat) == [item for item in rows if item['status'] == 'accepted']
    assert seat == before
