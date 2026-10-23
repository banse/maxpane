"""Independent second-row clocks and selected-seat joins; all reads are offline."""
from copy import deepcopy
from datetime import datetime

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data import surf_agent_hero as hero
from tests.surf_swarm_fixtures import swarm_capture_v3
from tests.data.test_surf_agent_hero import snapshot, NOW


def test_connection_normalization_cache_upgrade_and_invalid_timestamp():
    raw = swarm_capture_v3('workers')
    normalized = sw.normalize_workers(raw)
    first = raw['workers'][0]
    expected = datetime.fromisoformat(first['connectedAt'].replace('Z', '+00:00')).timestamp()
    assert normalized['workers'][0]['connected_ts'] == expected
    legacy = deepcopy(normalized)
    for row in legacy['workers']:
        del row['connected_ts']
    assert sw.coerce_workers_slot(legacy)['workers'][0]['connected_ts'] is None
    normalized['workers'][0]['connected_ts'] = float('nan')
    assert sw.coerce_workers_slot(normalized) is None


def test_runtime_connection_uses_matching_seat_and_runtime_and_worker_clock(snapshot):
    snapshot['data']['_agent_workers'] = [
        dict(token_id=420, runtimes=['claude'], connected_ts=NOW-90),
        dict(token_id=420, runtimes=['claude'], connected_ts=NOW-40),
        dict(token_id=420, runtimes=['codex'], connected_ts=NOW-5),
        dict(token_id=7, runtimes=['claude'], connected_ts=NOW-1),
    ]
    runtime = hero.project(**snapshot)['runtime']
    assert runtime['connected_ts'] == NOW-40
    assert runtime['connected_read_ts'] == NOW-10
    assert runtime['connected_state'] == 'ok'
    snapshot['sources']['workers']['state'] = 'stale'
    assert hero.project(**snapshot)['runtime']['connected_ts'] == NOW-40
    snapshot['sources']['workers']['state'] = 'partial'
    assert hero.project(**snapshot)['runtime']['connected_ts'] is None


def test_runtime_missing_one_matching_connection_is_unknown(snapshot):
    snapshot['data']['_agent_workers'] = [
        dict(token_id=420, runtimes=['claude'], connected_ts=NOW-90),
        dict(token_id=420, runtimes=['claude'], connected_ts=None),
    ]
    assert hero.project(**snapshot)['runtime']['connected_ts'] is None


def test_earnings_independent_clock_and_unknown_work_coverage(snapshot):
    snapshot['sources']['earnings'] = dict(state='ok', read_ts=NOW-25)
    snapshot['data']['_agent_earnings'] = dict(earned=12, worked_on=2, earned_24h=4, worked_on_24h=1, worked_recent=True)
    result = hero.project(**snapshot)['earnings']
    assert result == dict(state='ok', read_ts=NOW-25, earned=12, worked_on=2, earned_24h=4, worked_on_24h=1,
                         worked_recent=True, owner=snapshot['data']['swarm_seat_summary']['owner'])
    snapshot['sources']['earnings']['state'] = 'stale'
    assert hero.project(**snapshot)['earnings']['earned'] == 12
    snapshot['sources']['earnings'] = dict(state='pending', read_ts=None)
    assert hero.project(**snapshot)['earnings']['earned'] is None
    snapshot['sources']['earnings'] = dict(state='ok', read_ts=NOW-25)
    snapshot['data']['_agent_earnings']['worked_on'] = None
    assert hero.project(**snapshot)['earnings']['state'] == 'partial'


def test_nodes_keep_oracle_when_launch_membership_is_incomplete(snapshot):
    snapshot['data']['_agent_nodes'] = dict(oracle=10, launches=None, other=None, known_jobs=2, total_jobs=5)
    snapshot['sources']['agent_work'] = dict(state='partial', read_ts=NOW-15)
    nodes = hero.project(**snapshot)['nodes']
    assert nodes['oracle'] == 10 and nodes['launches'] is nodes['other'] is None
    assert nodes['known_jobs'] == 2 and nodes['total_jobs'] == 5
    assert nodes['read_ts'] == NOW-50 and nodes['launch_read_ts'] == NOW-15
    assert nodes['launch_state'] == 'partial'


def test_nodes_project_total_job_counts_without_replacing_accepted_counts(snapshot):
    snapshot['data']['_agent_nodes'] = dict(oracle=3, oracle_total=5, launches=2,
        launches_total=4, other=0, known_jobs=2, total_jobs=2)
    nodes = hero.project(**snapshot)['nodes']
    assert (nodes['launches'], nodes['launches_total']) == (2, 4)
    assert (nodes['oracle'], nodes['oracle_total']) == (3, 5)
    snapshot['data']['_agent_nodes']['launches_total'] = True
    assert hero.project(**snapshot)['nodes']['launches_total'] is None
