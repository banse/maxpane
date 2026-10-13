"""AGENT facts keep identity, source clocks and real negatives independent."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_agent_hero as hero
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data import surfboard_activity as activity
from maxpane_dashboard.data.surf_models import (
    SURF_AGENT_HERO_FIELDS, SURF_AGENT_HERO_STATES, SURF_AGENT_HERO_MODEL_FIELDS,
    SURF_AGENT_HERO_COLLAB_FIELDS, SURF_AGENT_HERO_NODE_FIELDS,
)
from tests.surf_swarm_fixtures import swarm_agent_sources, swarm_seat_capture
from tests.data.test_surfboard_activity import workers

NOW = 1_791_800_000


@pytest.fixture
def snapshot():
    seat = swarm_seat_capture('seat_420')
    data = swarm_agent_sources(420)
    data.update(swarm_seat_selected=dict(token_id=420, selected_by='saved'),
                swarm_seat_state='ok', swarm_seat_summary=sw.seat_summary_from_seat(seat),
                swarm_seat_node_rows=sw.seat_node_rows(seat), swarm_seat_teammates=sw.seat_teammates(seat),
                swarm_seat_rewards=dict(imd=12.84, usd=120.8244, seats=3), swarm_seat_rewards_state='ok',
                swarm_seat_rank_delta=2, swarm_seat_owner_ens='example.eth',
                swarm_runtime_latest={'claude': '2.1.278'},
                swarm_fleet_daemon=('0.1.0+6c2c43ef', 40, 60))
    return dict(now=NOW, data=data, sources={
        name: dict(state='ok', read_ts=NOW-age) for name, age in
        [('seat', 50), ('records', 60), ('workers', 10), ('contributors', 80), ('rewards', 40), ('market', 20)]
    } | {'runtime': {'claude': dict(state='ok', read_ts=NOW-30)}},
        activity=activity.observe(None, workers(0), now=NOW-10))


def test_contract_canonical_arithmetic_and_independent_source_clocks(snapshot):
    before = deepcopy(snapshot)
    result = hero.project(**snapshot)
    assert tuple(result) == tuple(SURF_AGENT_HERO_FIELDS)
    for key, fields in SURF_AGENT_HERO_FIELDS.items():
        assert tuple(result[key]) == fields
        assert result[key]['state'] in SURF_AGENT_HERO_STATES
    assert result['accepted'] == dict(state='ok', read_ts=NOW-60, listed=True,
        accepted=3253, attempts=3392, percent=pytest.approx(95.90212264150944))
    assert result['effort'] == dict(state='ok', read_ts=NOW-80, listed=True,
        hours=pytest.approx(8.093120833333334), output_tokens=1215919,
        premium_percent=None, premium_jobs=None, model_jobs=None, work_jobs=None)
    assert result['rank'] == dict(state='ok', read_ts=NOW-60, listed=True, rank=1, ranked_of=2, delta=2)
    assert result['rewards'] == dict(state='ok', read_ts=NOW-40, imd=12.84, usd=120.8244,
                                    seats=3, usd_state='ok', usd_read_ts=NOW-20, last_paid_ts=None, paid_recent=False)
    assert result['owner']['address'] == '0xe5b1275fb926613d983da33fbfe1f331b7f64f2a'
    assert result['owner']['name'] == 'example.eth'
    assert result['earnings']['earned'] is None and result['earnings']['state'] == 'unavailable'
    assert result['collab']['count'] == 24 and result['collab']['rows'][0] == dict(token_id=1299, shared_jobs=7)
    assert result['nodes']['rows'][0] == dict(node_key='oracle_assess', accepted=10, attempts=None)
    assert result['models']['rows'] == []
    for section, fields in (('models', SURF_AGENT_HERO_MODEL_FIELDS),
                            ('collab', SURF_AGENT_HERO_COLLAB_FIELDS), ('nodes', SURF_AGENT_HERO_NODE_FIELDS)):
        assert all(tuple(row) == fields for row in result[section]['rows'])
    assert result['runtime']['update_state'] == 'current'
    assert result['runtime']['checked_ts'] == NOW-30
    assert result['runtime']['daemon_differs'] is False
    assert result['status']['live_state'] == result['status']['meter_state'] == 'idle'
    assert result['status']['last_work_ts'] == 1789963809.585
    assert result['status']['last_work_kind'] == 'accepted'
    assert result['status']['work_read_ts'] == NOW-50
    assert snapshot == before


def test_premium_share_counts_actual_known_models_and_reports_coverage(snapshot):
    # Attempts on the same job still represent separate work; configured models
    # must not turn a Sonnet submission into premium usage.
    snapshot['data']['swarm_seat_summary']['models'] = [dict(model='astra', effort='high')]
    models = ['openai/gpt-6-astra', 'Claude-Opus-4.6', 'claude-fable-5-1',
              'claude-sonnet-5', 'astral', 'my-fablet', None, '', 123]
    rows = [dict(job_id='same-job', model=model, answer_state='read') for model in models]
    rows[2]['answer_state'] = 'no_reply'  # usage remains valid without answer prose
    rows += [dict(model='opus', answer_state='unavailable')]
    snapshot['data']['swarm_seat_work_rows'] = rows
    before = deepcopy(snapshot)
    effort = hero.project(**snapshot)['effort']
    assert {key: effort[key] for key in ('premium_percent', 'premium_jobs', 'model_jobs', 'work_jobs')} == dict(
        premium_percent=50., premium_jobs=3, model_jobs=6, work_jobs=10)
    assert snapshot == before


@pytest.mark.parametrize('rows,expected', [
    ([], (None, 0, 0, 0)),
    ([dict(model=None, answer_state='read')], (None, 0, 0, 1)),
    ([dict(model='sonnet', answer_state='read')], (0., 0, 1, 1)),
    ([dict(model='OPUS', answer_state='read')], (100., 1, 1, 1)),
    (None, (None, None, None, None)),
    ([None], (None, None, None, None)),
])
def test_premium_zero_and_unknown_are_distinct(snapshot, rows, expected):
    snapshot['data']['swarm_seat_work_rows'] = rows
    effort = hero.project(**snapshot)['effort']
    assert tuple(effort[key] for key in ('premium_percent', 'premium_jobs', 'model_jobs', 'work_jobs')) == expected


@pytest.mark.parametrize('state', ['ok', 'stale', 'pending', 'busy', 'unavailable', 'unknown_seat'])
def test_premium_models_follow_detail_availability_not_contributor_clock(snapshot, state):
    snapshot['data']['swarm_seat_work_rows'] = [dict(model='fable', answer_state='read')]
    snapshot['sources']['contributors'] = dict(state='unavailable', read_ts=None)
    snapshot['sources']['seat']['state'] = state if state != 'unknown_seat' else 'ok'
    snapshot['data']['swarm_seat_state'] = 'ok' if state in ('ok', 'stale') else state
    effort = hero.project(**snapshot)['effort']
    assert effort['hours'] is None
    assert effort['premium_percent'] == (100. if state in ('ok', 'stale') else None)
    assert effort['work_jobs'] == (1 if state in ('ok', 'stale') else None)


@pytest.mark.parametrize('state', ['pending', 'busy', 'unknown_seat', None])
def test_detail_states_leave_canonical_effort_and_worker_reads_independent(snapshot, state):
    before = hero.project(**snapshot)
    snapshot['data']['swarm_seat_state'] = state
    snapshot['sources']['seat'] = dict(state='ok' if state == 'unknown_seat' else state, read_ts=NOW-50 if state == 'unknown_seat' else None)
    result = hero.project(**snapshot)
    assert result['seat']['token_id'] == 420
    for key in ('owner', 'runtime', 'models', 'earnings', 'collab', 'nodes', 'rewards'):
        assert result[key]['state'] == (state or 'unavailable')
    for key in ('accepted', 'rank', 'effort'):
        assert result[key] == before[key]
    assert result['status']['live_state'] == 'idle'
    assert result['status']['last_work_ts'] is None


def test_missing_selection_and_wrong_canonical_identity_never_borrow_another_seat(snapshot):
    snapshot['data']['swarm_seat_outcome']['token_id'] = 7
    result = hero.project(**snapshot)
    assert result['accepted']['listed'] is result['accepted']['accepted'] is None
    assert result['rank']['rank'] is None
    snapshot['data']['swarm_seat_selected'] = None
    assert all(card['state'] == 'empty' for card in hero.project(**snapshot).values())


def test_real_zero_missing_counter_and_unlisted_remain_distinct(snapshot):
    snapshot['data']['swarm_seat_outcome'].update(accepted=0, attempts=0, rank=None)
    result = hero.project(**snapshot)
    assert result['accepted'] == dict(state='ok', read_ts=NOW-60, listed=True, accepted=0, attempts=0, percent=None)
    snapshot['data']['swarm_seat_outcome']['accepted'] = None
    assert hero.project(**snapshot)['accepted']['state'] == 'partial'
    snapshot['data']['swarm_seat_outcome']['listed'] = False
    snapshot['data']['swarm_seat_contrib']['listed'] = False
    result = hero.project(**snapshot)
    assert result['accepted']['state'] == result['effort']['state'] == 'ok'
    assert result['accepted']['listed'] is result['effort']['listed'] is False
    assert result['accepted']['accepted'] is result['effort']['hours'] is None
    snapshot['sources']['records']['state'] = 'partial'
    snapshot['sources']['contributors']['state'] = 'partial'
    result = hero.project(**snapshot)
    assert result['accepted']['listed'] is result['effort']['listed'] is None


def test_stale_sources_keep_values_and_independent_usd_gating(snapshot):
    for name in ('seat', 'records', 'contributors', 'rewards'):
        snapshot['sources'][name]['state'] = 'stale'
    snapshot['sources']['market']['state'] = 'unavailable'
    result = hero.project(**snapshot)
    assert result['accepted']['state'] == result['effort']['state'] == result['rewards']['state'] == 'stale'
    assert result['rewards']['imd'] == 12.84 and result['rewards']['usd'] is None
    assert result['rewards']['usd_state'] == 'unavailable'
    assert result['status']['state'] == 'ok' and result['status']['work_state'] == 'stale'


def test_partial_workers_cannot_turn_absence_into_offline_or_show_incomplete_sums(snapshot):
    snapshot['sources']['workers'].update(state='partial', partial=True)
    snapshot['data']['swarm_seat_live'].update(live=False, live_state='offline', working=0, devices=0)
    result = hero.project(**snapshot)['status']
    assert result['live_state'] is result['working'] is result['devices'] is None
    snapshot['data']['swarm_seat_live'].update(live=True, live_state='working', working=2, devices=1)
    result = hero.project(**snapshot)['status']
    assert result['live_state'] == 'working'
    assert result['working'] is result['capacity'] is None


@pytest.mark.parametrize('runtime,newest,state,expected', [
    ('claude 2.1.277', '2.1.278', 'ok', 'outdated'),
    ('claude broken', '2.1.278', 'ok', 'unavailable'),
    ('claude 2.1.278', None, 'unavailable', 'unavailable'),
    ('claude 2.1.278', '2.1.278', 'stale', 'unavailable'),
    ('claude 2.1.278', '2.1.278', 'pending', 'pending'),
    ('other 1.0.0', '2.1.278', 'ok', 'not_checked'),
])
def test_runtime_never_claims_current_without_a_fresh_valid_check(snapshot, runtime, newest, state, expected):
    snapshot['data']['swarm_seat_summary']['runtime'] = runtime
    snapshot['data']['swarm_runtime_latest']['claude'] = newest
    snapshot['sources']['runtime']['claude']['state'] = state
    assert hero.project(**snapshot)['runtime']['update_state'] == expected


def test_unknown_lists_stay_unknown_and_empty_lists_are_real_negatives(snapshot):
    summary = snapshot['data']['swarm_seat_summary']
    summary.update(models=None, collaborators=None, review_status=None)
    snapshot['data'].update(swarm_seat_teammates=None, swarm_seat_node_rows=None)
    result = hero.project(**snapshot)
    assert result['models']['rows'] is result['collab']['rows'] is result['nodes']['rows'] is None
    assert result['earnings']['earned'] is None
    summary.update(models=[], collaborators=0, review_status=dict(sent=0, submitted=0, queued=0))
    snapshot['data'].update(swarm_seat_teammates=[], swarm_seat_node_rows=[])
    snapshot['data']['_agent_nodes'] = dict(oracle=0, launches=0, other=0, known_jobs=0, total_jobs=0)
    result = hero.project(**snapshot)
    assert result['models']['rows'] == result['collab']['rows'] == result['nodes']['rows'] == []
    assert result['models']['state'] == result['collab']['state'] == result['nodes']['state'] == 'ok'
    assert result['nodes']['oracle'] == result['nodes']['launches'] == result['nodes']['other'] == 0


def test_status_uses_newest_work_never_feedback_and_no_date_is_unknown(snapshot):
    summary = snapshot['data']['swarm_seat_summary']
    summary.update(last_worked_ts=NOW-100, last_won_ts=NOW-200, last_sent_ts=NOW-1)
    result = hero.project(**snapshot)['status']
    assert (result['last_work_ts'], result['last_work_kind']) == (NOW-100, 'worked')
    summary.update(last_worked_ts=None, last_won_ts=None, accepted=0)
    result = hero.project(**snapshot)['status']
    assert result['last_work_ts'] is result['last_work_kind'] is None


@pytest.mark.parametrize('elapsed,kind,numerator,denominator', [
    (0, 'activity', 86400, 86400), (43200, 'activity', 43200, 86400),
    (86400, 'activity-cooldown', 172800, 172800),
    (172800, 'activity-cooldown', 86400, 172800),
    (259200, 'activity-cooldown', 0, 172800), (300000, 'activity-cooldown', 0, 172800),
])
def test_status_uses_shared_linear_meter_for_both_drain_windows(snapshot, elapsed, kind, numerator, denominator):
    past = NOW-elapsed
    observed = activity.observe(None, workers(1), now=past-60)
    observed = activity.observe(observed, workers(0), now=past)
    snapshot['activity'] = activity.observe(observed, workers(0), now=NOW)
    status = hero.project(**snapshot)['status']
    assert {key: status[key] for key in ('meter_kind', 'meter_state', 'numerator', 'denominator')} == dict(
        meter_kind=kind, meter_state='idle', numerator=numerator, denominator=denominator)
    snapshot['activity'] = activity.observe(observed, workers(1), now=NOW)
    status = hero.project(**snapshot)['status']
    assert status['meter_kind'] == 'activity' and status['meter_state'] == 'busy'
    assert status['numerator'] == status['denominator'] == 86400


def test_offline_paused_and_stale_activity_follow_boardroom_meter(snapshot):
    snapshot['activity'] = activity.observe(None, workers(), now=NOW)
    live = snapshot['data']['swarm_seat_live']
    live.update(live=False, live_state='offline', working=0, devices=0)
    status = hero.project(**snapshot)['status']
    assert status['live_state'] == status['meter_state'] == 'offline'
    live.update(live=True, live_state='paused', paused_until_ts=NOW+600, failures=3)
    status = hero.project(**snapshot)['status']
    assert status['live_state'] == 'paused'
    assert status['meter_state'] == 'idle'
    assert status['paused_until_ts'] == NOW+600 and status['failures'] == 3
    snapshot['sources']['workers'].update(state='partial', partial=True)
    assert hero.project(**snapshot)['status']['meter_state'] == 'idle'
    snapshot['sources']['workers'].update(state='ok', partial=False)
    live.update(live_state='idle', paused_until_ts=None, failures=None)
    snapshot['activity'] = activity.observe(None, workers(1), now=NOW-301)
    assert hero.project(**snapshot)['status']['meter_state'] == 'stale'


@pytest.mark.parametrize('source,sections', [
    ('records', ('accepted', 'rank')), ('contributors', ('effort',)),
    ('rewards', ('rewards',)), ('workers', ('status',)),
])
@pytest.mark.parametrize('stamp', [None, True, -1, float('nan'), float('inf'), NOW+1])
def test_bad_source_clocks_cannot_publish_values(snapshot, source, sections, stamp):
    snapshot['sources'][source]['read_ts'] = stamp
    result = hero.project(**snapshot)
    for section in sections:
        assert result[section]['state'] == 'unavailable'
        assert result[section]['read_ts'] is None
    assert result['owner']['state'] == 'ok'


@pytest.mark.parametrize('bad', [None, True, -1, '3', float('nan'), float('inf')])
def test_invalid_and_impossible_counts_never_turn_into_zero(snapshot, bad):
    snapshot['data']['swarm_seat_outcome'].update(accepted=bad, attempts=3)
    snapshot['data']['swarm_seat_contrib'].update(wall_clock_s=bad, output_tokens=bad)
    snapshot['data']['_agent_earnings'] = dict(earned=bad, worked_on=0, earned_24h=1, worked_on_24h=bad, worked_recent=False)
    snapshot['sources']['earnings'] = dict(state='ok', read_ts=NOW-25)
    result = hero.project(**snapshot)
    assert result['accepted']['accepted'] is result['accepted']['percent'] is None
    assert result['effort']['hours'] is result['effort']['output_tokens'] is None
    assert result['earnings']['earned'] is None and result['earnings']['earned_24h'] == 1
    assert result['earnings']['worked_on_24h'] is None
    snapshot['data']['swarm_seat_outcome']['accepted'] = 4
    result = hero.project(**snapshot)
    assert result['accepted']['accepted'] is result['accepted']['percent'] is None


def test_full_model_node_and_collaborator_lists_are_not_truncated(snapshot):
    snapshot['data']['swarm_seat_summary']['models'] = [dict(model=f'model-{i}', effort='high') for i in range(6)]
    result = hero.project(**snapshot)
    assert len(result['models']['rows']) == 6 and len(result['collab']['rows']) == 24
    snapshot['data']['swarm_seat_summary']['models'] = [True]
    assert hero.project(**snapshot)['models']['rows'] is None


def test_zero_rank_and_zero_reward_seats_are_not_valid_facts(snapshot):
    snapshot['data']['swarm_seat_outcome']['rank'] = 0
    snapshot['data']['swarm_seat_rewards']['seats'] = 0
    result = hero.project(**snapshot)
    assert result['rank']['rank'] is result['rank']['delta'] is None
    assert result['rewards']['seats'] is None


@pytest.mark.parametrize('state,partial', [('stale', False), ('partial', True), ('ok', True)])
def test_daemon_comparison_requires_a_fresh_complete_fleet(snapshot, state, partial):
    snapshot['sources']['workers'].update(state=state, partial=partial)
    result = hero.project(**snapshot)['runtime']
    assert result['daemon_differs'] is result['fleet_daemon'] is None


def test_stale_detail_does_not_make_owner_based_rewards_or_usd_look_fresh(snapshot):
    snapshot['sources']['seat']['state'] = 'stale'
    result = hero.project(**snapshot)['rewards']
    assert result['imd'] == 12.84 and result['usd'] == 120.8244
    assert result['state'] == result['usd_state'] == 'stale'
    assert result['read_ts'] == NOW-40 and result['usd_read_ts'] == NOW-20


def test_seat_registration_uses_selected_detail_and_never_selection_fallback(snapshot):
    snapshot['data']['swarm_seat_selected']['agent_id'] = 'wrong-agent'
    snapshot['data']['swarm_seat_summary']['agent_id'] = '1234567890123456789012345'
    assert hero.project(**snapshot)['seat']['agent_id'] == '1234567890123456789012345'
    snapshot['data']['swarm_seat_state'] = 'pending'
    assert hero.project(**snapshot)['seat']['agent_id'] is None
    snapshot['data']['swarm_seat_state'] = 'unknown_seat'
    assert hero.project(**snapshot)['seat']['agent_id'] is None


@pytest.mark.parametrize('elapsed,recent', [(40, True), (86399, True), (86400, False), (90000, False)])
def test_reward_recent_window_uses_verified_payment_time_not_source_clock(snapshot, elapsed, recent):
    snapshot['data']['swarm_seat_rewards']['last_paid_ts'] = NOW-elapsed
    result = hero.project(**snapshot)['rewards']
    assert result['last_paid_ts'] == NOW-elapsed
    assert result['paid_recent'] is recent
    assert result['state'] == 'ok'


@pytest.mark.parametrize('stamp', [None, True, -1, float('nan'), float('inf'), NOW+1, NOW-39, 1])
def test_bad_or_unobserved_reward_time_does_not_erase_valid_amount(snapshot, stamp):
    snapshot['data']['swarm_seat_rewards']['last_paid_ts'] = stamp
    result = hero.project(**snapshot)['rewards']
    assert result['imd'] == 12.84 and result['state'] == 'ok'
    assert result['last_paid_ts'] is None and result['paid_recent'] is False


def test_zero_reward_and_unavailable_reward_source_do_not_signal_recent_payment(snapshot):
    snapshot['data']['swarm_seat_rewards'].update(last_paid_ts=NOW-100, imd=0)
    result = hero.project(**snapshot)['rewards']
    assert result['last_paid_ts'] is None and result['paid_recent'] is False
    snapshot['data']['swarm_seat_rewards']['imd'] = 1
    snapshot['sources']['rewards']['state'] = 'unavailable'
    result = hero.project(**snapshot)['rewards']
    assert result['last_paid_ts'] is None and result['paid_recent'] is False


@pytest.mark.parametrize('source,sections', [
    ('records', ('accepted', 'rank')), ('contributors', ('effort',)),
    ('workers', ('status',)), ('rewards', ('rewards',)),
    ('seat', ('seat', 'owner', 'runtime', 'models', 'earnings', 'collab', 'nodes', 'rewards')),
])
def test_first_source_read_keeps_pending_without_inventing_facts(snapshot, source, sections):
    snapshot['sources'][source] = dict(state='pending', read_ts=None)
    result = hero.project(**snapshot)
    for section in sections:
        assert result[section]['state'] == 'pending'
        assert result[section]['read_ts'] is None
    for section, field in [('accepted', 'accepted'), ('rank', 'rank'), ('effort', 'hours'),
                           ('status', 'working'), ('rewards', 'imd'), ('seat', 'agent_id')]:
        if section in sections:
            assert result[section][field] is None
    if source != 'records':
        assert result['accepted']['state'] == 'ok'
    if source != 'workers':
        assert result['status']['working'] == 0
    if source != 'seat':
        assert result['owner']['state'] == 'ok'


def test_pending_market_keeps_known_imd_reward(snapshot):
    snapshot['sources']['market'] = dict(state='pending', read_ts=None)
    result = hero.project(**snapshot)['rewards']
    assert result['imd'] == 12.84 and result['state'] == 'ok'
    assert result['usd'] is None and result['usd_state'] == 'pending'


def test_first_rewards_read_stays_pending_with_retained_known_seat(snapshot):
    snapshot['sources']['seat']['state'] = 'stale'
    snapshot['sources']['rewards'] = dict(state='pending', read_ts=None)
    result = hero.project(**snapshot)['rewards']
    assert result['state'] == 'pending' and result['imd'] is None
