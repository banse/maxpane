"""Bounded live-work projection; source data is captured, never fetched."""
import copy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_work as work


@pytest.fixture
def captured():
    return json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())


def snapshot(raw):
    return work.snapshot(raw['jobs'], raw['workflows'],
                         {row['id']: row for row in raw['details']},
                         read_ts=raw['read_ts'])


def test_captured_work_counts_current_nodes_not_historic_verdicts(captured):
    data = work.project(snapshot(captured), now=captured['read_ts'])
    assert data['summary'] == dict(jobs=2, workflows=1, seats=2, build=2, review=0, blocked=1)
    assert data['jobs_loaded'] == 3
    assert data['jobs'][0]['nodes'][0]['seat'] == 398
    assert data['jobs'][0]['nodes'][0]['verdict']['status'] == 'accepted'
    assert data['jobs'][1]['nodes'][1]['state'] == 'accepted'
    assert data['partial']  # workflow-linked detail is absent


def test_failed_or_old_read_retains_clock_and_rows(captured):
    slot = snapshot(captured)
    for now, failed in ((captured['read_ts'], True), (captured['read_ts'] + 121, False)):
        data = work.project(slot, now=now, failed=failed)
        assert data['state'] == 'stale'
        assert data['read_ts'] == captured['read_ts']
        assert data['summary']['jobs'] == 2
    assert work.project(slot, now=captured['read_ts'] + 120)['state'] == 'ok'


def test_unavailable_is_not_empty():
    missing = work.project(None, now=1000)
    empty = work.project(work.snapshot([], [], {}, read_ts=1000), now=1000)
    assert missing['jobs'] is None and missing['summary']['jobs'] is None
    assert empty['jobs'] == [] and set(empty['summary'].values()) == {0}


@pytest.mark.parametrize('change,expected', [
    ('missing_detail', (None, None, None)),
    ('missing_seat', (None, 2, 0)),
    ('bool_seat', (None, 2, 0)),
    ('unknown_role', (2, None, None)),
    ('review', (2, 1, 1)),
])
def test_uncertain_counts_are_never_reported_as_zero(captured, change, expected):
    raw = copy.deepcopy(captured)
    node = raw['details'][0]['nodes'][0]
    if change == 'missing_detail': raw['details'].pop(0)
    if change == 'missing_seat': node['seat'] = None
    if change == 'bool_seat': node['seat']['tokenId'] = True
    if change == 'unknown_role': node['role'] = 'future-role'
    if change == 'review': node['role'] = 'review'
    summary = work.project(snapshot(raw), now=raw['read_ts'])['summary']
    assert tuple(summary[k] for k in ('seats', 'build', 'review')) == expected


def test_duplicates_malformed_and_capped_pages_mark_partial(captured):
    raw = copy.deepcopy(captured)
    raw['jobs'] += [raw['jobs'][0], {'id': False}]
    data = work.project(snapshot(raw), now=raw['read_ts'])
    assert len(data['jobs']) == 3 and data['partial']
    slot = work.snapshot([], [], {}, read_ts=1000)
    assert not work.project(slot, now=1000)['partial']


def test_persisted_payload_validates_every_row_and_clock(captured):
    slot = snapshot(captured)
    assert work.coerce_snapshot(slot, now=captured['read_ts']) == slot
    for bad in (True, float('nan'), captured['read_ts'] + 1):
        changed = copy.deepcopy(slot); changed['read_ts'] = bad
        assert work.coerce_snapshot(changed, now=captured['read_ts']) is None
    changed = copy.deepcopy(slot); changed['jobs'][0]['nodes'][0]['attempt'] = True
    assert work.coerce_snapshot(changed, now=captured['read_ts']) is None
    changed = copy.deepcopy(slot); changed['workflows'][0]['waiting_for_hosting'] = 1
    assert work.coerce_snapshot(changed, now=captured['read_ts']) is None


@pytest.mark.parametrize('key', ['details_loaded', 'details_expected'])
@pytest.mark.parametrize('value', [True, False, 1.0, '1', -1, float('nan')])
def test_persisted_counts_require_nonnegative_strict_integer(captured, key, value):
    slot = snapshot(captured)
    slot[key] = value
    assert work.coerce_snapshot(slot, now=captured['read_ts']) is None


def test_unique_seats_and_linked_jobs_are_counted_once(captured):
    raw = copy.deepcopy(captured)
    raw['details'][1]['nodes'][0]['seat'] = {'tokenId': '398', 'agentId': '51725'}
    raw['jobs'] = raw['jobs'][1:]
    data = work.project(snapshot(raw), now=raw['read_ts'])
    assert data['summary']['jobs'] == 2
    assert data['summary']['seats'] == 1


def test_detail_priority_and_foreign_details_do_not_replace_list_identity(captured):
    raw = copy.deepcopy(captured)
    jobs, workflows, _ = work.decode_pages(raw['jobs'], raw['workflows'], now=raw['read_ts'])
    ids = work.detail_ids(jobs, workflows)
    assert ids[:2] == [j['id'] for j in jobs[:2]]
    assert ids[2] == workflows[0]['contracts_job_id']
    assert ids[-1] == jobs[2]['id']
    details = {raw['jobs'][0]['id']: raw['details'][1]}
    data = work.project(work.snapshot(raw['jobs'], [], details, read_ts=raw['read_ts']), now=raw['read_ts'])
    assert data['jobs'][0]['id'] == raw['jobs'][0]['id']
    assert data['jobs'][0]['detail_state'] == 'unavailable'
    assert data['details_loaded'] == 0


def test_full_page_and_malformed_nodes_mark_partial_without_fabricating_totals(captured):
    raw = copy.deepcopy(captured)
    raw['jobs'] = [dict(raw['jobs'][0], id=f'00000000-0000-0000-0000-{n:012d}', state='completed') for n in range(100)]
    data = work.project(work.snapshot(raw['jobs'], [], {}, read_ts=raw['read_ts']), now=raw['read_ts'])
    assert data['partial'] and data['summary']['jobs'] == 0
    raw = copy.deepcopy(captured)
    raw['details'][0]['nodes'].append({'key': 'bad node'})
    data = work.project(snapshot(raw), now=raw['read_ts'])
    assert data['jobs'][0]['nodes'] is None
    assert data['summary']['build'] is None and data['partial']


def test_loaded_collection_contract_is_exact(captured):
    from maxpane_dashboard.data.surf_models import SURF_WORK_FIELDS
    assert set(work.project(snapshot(captured), now=captured['read_ts'])) == set(SURF_WORK_FIELDS)


def test_page_count_excludes_extra_linked_details(captured):
    raw = copy.deepcopy(captured)
    raw['jobs'] = raw['jobs'][1:]
    data = work.project(snapshot(raw), now=raw['read_ts'])
    assert data['jobs_loaded'] == 2
    assert len(data['jobs']) == 3
    slot = snapshot(raw)
    for bad in (True, -1, 4, 101):
        slot['jobs_loaded'] = bad
        assert work.coerce_snapshot(slot, now=raw['read_ts']) is None


def test_legacy_snapshot_migrates_to_partial_empty_projects(captured):
    slot = snapshot(captured)
    for key in ('projects', 'current_job_ids', 'current_workflow_ids', 'context_job_ids', 'context_workflow_ids', 'active_scan_complete'):
        slot.pop(key)
    migrated = work.coerce_snapshot(slot, now=captured['read_ts'])
    assert migrated['projects'] == [] and migrated['partial']
    assert not migrated['active_scan_complete']
    data = work.project(migrated, now=captured['read_ts'])
    assert data['summary']['jobs'] == 2 and data['summary']['seats'] is None
    from maxpane_dashboard.data.surf_models import SURF_WORK_FIELDS
    assert set(data) == set(SURF_WORK_FIELDS)
