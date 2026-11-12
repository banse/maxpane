"""AGENT cards count jobs once and include explicit non-oracle research."""
from copy import deepcopy
import pytest
from maxpane_dashboard.data import surf_agent_work as work
from tests.data.test_surf_agent_work import LIVE, PLAIN, BLOCKED, NOW, row, point, capture, complete_history


def test_accepted_jobs_deduplicate_contributions_and_reject_incomplete_history():
    rows = [row(LIVE), row(LIVE, 'review'), row(PLAIN, status='failed'),
            row(PLAIN), row(BLOCKED, status='pending')]
    seat = dict(work=rows, attempts=5, accepted=3)
    assert work.job_counts(seat) == dict(accepted=2, attempts=3)
    assert work.job_counts(dict(seat, work=rows[:-1])) == dict(accepted=None, attempts=None)
    assert work.job_counts(dict(work=[], attempts=0, accepted=0)) == dict(accepted=0, attempts=0)
    assert work.job_counts({'work': [dict(row(LIVE), jobId=None)]})['accepted'] is None
    legacy = row(LIVE); legacy.pop('status')
    assert work.job_counts({'work': [legacy]})['attempts'] is None


def test_research_adds_goal_and_report_jobs_without_double_counting_oracles():
    seat = {'work': [row(LIVE, 'oracle_assess'), row(LIVE, 'review'),
                     row(PLAIN, 'item_0001'), row(PLAIN, 'merge'),
                     row(BLOCKED, 'research_report', 'failed')]}
    points = {PLAIN: dict(point(), family='research'), BLOCKED: dict(point(), family='research')}
    got = work.summarize(complete_history(seat), points, NOW, oracle_chains={LIVE: 1})
    assert (got['research'], got['research_total']) == (2, 3)
    assert (got['oracle'], got['oracle_total']) == (1, 1)
    assert got['launches_total'] == 0
    assert work.summarize(complete_history(seat), points, NOW, oracle_chains={LIVE: 11155111})['research_total'] == 2
    assert work.summarize(complete_history(seat), {}, NOW, oracle_chains={LIVE: 1})['research_total'] is None


def test_membership_records_purpose_and_legacy_points_require_backfill():
    raw = capture(PLAIN)
    raw['template'] = 'goal'
    got = work.membership_point(raw, PLAIN, NOW)
    assert got['family'] == 'research'
    assert work.coerce_points({PLAIN: got}, NOW) == {PLAIN: got}
    old = dict(got); old.pop('family')
    assert work.due({'work': [row(PLAIN)]}, {PLAIN: old}, NOW) == [PLAIN]
    for bad in (True, 'future', 3):
        assert work.coerce_points({PLAIN: dict(got, family=bad)}, NOW) == {}


def test_projection_uses_job_counts_without_changing_canonical_rank():
    from maxpane_dashboard.data import surf_agent_hero as hero
    from tests.data.test_surf_agent_hero import snapshot
    values = snapshot.__wrapped__()
    values['data']['_agent_accepted'] = dict(accepted=3297, attempts=3439)
    result = hero.project(**values)
    assert result['accepted']['accepted'] == 3297
    assert result['accepted']['percent'] == pytest.approx(95.8708927)
    assert result['accepted']['read_ts'] == values['sources']['seat']['read_ts']
    assert result['rank']['rank'] == 1


def test_captured_seat_420_distinct_jobs_match_full_lifetime_history():
    import gzip, json
    from tests.data.test_surf_agent_work import FIXTURES
    with gzip.open(FIXTURES/'seat-420-20261112.json.gz', 'rt') as file:
        seat = json.load(file)
    assert seat['accepted'] == 3301 and len(seat['work']) == seat['attempts'] == 3453
    assert work.job_counts(seat) == dict(accepted=3297, attempts=3439)
    duplicate = deepcopy(seat)
    duplicate['work'][-1] = dict(duplicate['work'][0])
    assert work.job_counts(duplicate)['attempts'] is None


@pytest.mark.parametrize('job,family,launched', [
    ('63d64980-7a98-468c-86fc-b382f7a251e3', 'launch', True),
    ('d3229638-a2a2-4dd7-97f0-8e2552c31e96', 'other', False),
    ('51eb88fe-2113-4148-a771-9443d4abb201', 'research', False),
    ('bd06951d-9f21-42d3-a020-00766d467abd', 'research', False),
])
def test_captured_job_purposes_match_boardroom_and_launch_proof(job, family, launched):
    from maxpane_dashboard.data.surf_card_reader import _job_family
    raw = capture(job)
    point = work.membership_point(raw, job, NOW)
    assert point['family'] == _job_family(raw) == family
    assert point['launched'] is launched


def test_captured_seat_420_all_three_cards_have_complete_consistent_counts():
    import gzip, json
    from tests.data.test_surf_agent_work import FIXTURES
    from maxpane_dashboard.data.surf_agent_card_sources import project
    with gzip.open(FIXTURES/'seat-420-20261112.json.gz', 'rt') as file:
        seat = json.load(file)
    with gzip.open(FIXTURES/'seat-420-context-20261112.json.gz', 'rt') as file:
        captured = json.load(file)
    captured['oracle_chains'] = captured['oracle_index']['chains']
    facts, _ = project(captured, seat, now=captured['now'])
    assert facts['_agent_accepted'] == dict(accepted=3297, attempts=3439)
    counts = facts['_agent_nodes']
    assert (counts['launches'], counts['launches_total']) == (22, 23)
    assert (counts['oracle'], counts['oracle_total']) == (3218, 3345)
    assert (counts['research'], counts['research_total']) == (3225, 3353)
    assert counts['known_jobs'] == counts['total_jobs'] == 79


@pytest.mark.parametrize('missing', [('attempts',), ('accepted',), ('attempts', 'accepted')])
def test_missing_lifetime_counters_cannot_certify_a_partial_history(missing):
    import gzip, json
    from tests.data.test_surf_agent_work import FIXTURES
    with gzip.open(FIXTURES/'seat-420-20261112.json.gz', 'rt') as file:
        seat = json.load(file)
    seat['work'] = seat['work'][:20]
    seat['attempts'] = 20
    seat['accepted'] = sum(row['status'] == 'accepted' for row in seat['work'])
    for key in missing:
        seat.pop(key)
    assert work.job_counts(seat) == dict(accepted=None, attempts=None)
    assert work.summarize(seat, {}, NOW)['oracle_total'] is None
