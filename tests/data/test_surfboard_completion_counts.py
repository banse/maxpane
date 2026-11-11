"""Completion and working-seat facts use existing certified public sources."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from maxpane_dashboard.data import surfboard as hub
from maxpane_dashboard.data.surf_card_reader import SurfCardReader
from maxpane_dashboard.data.surf_models import SURFBOARD_OVERVIEW_FIELDS


def overview():
    return json.loads(Path('tests/fixtures/surf/swarm/hub/overview.json').read_text())


def test_overview_counts_launches_and_distinct_busy_seats_independently():
    raw = overview()
    raw['seats']['420']['working'] = True
    before = deepcopy(raw)
    normalized = hub.normalize_overview(raw)
    assert set(normalized['overview']) == set(SURFBOARD_OVERVIEW_FIELDS)
    assert normalized['overview']['launches_live'] == 285
    assert normalized['overview']['working_seats'] == 1
    assert raw == before
    raw['counts']['launchesLive'] = 0
    raw['seats'] = {}
    normalized = hub.normalize_overview(raw)
    assert normalized['overview']['launches_live'] == normalized['overview']['working_seats'] == 0


@pytest.mark.parametrize('failure', ['missing', 'bad_flag', 'bad_identity', 'duplicate'])
def test_bad_seat_map_only_invalidates_working_seat_count(failure):
    raw = overview()
    if failure == 'missing': raw.pop('seats')
    if failure == 'bad_flag': raw['seats']['420']['working'] = 1
    if failure == 'bad_identity': raw['seats']['420']['tokenId'] = 99
    if failure == 'duplicate': raw['seats']['0420'] = deepcopy(raw['seats']['420'])
    normalized = hub.normalize_overview(raw)
    assert normalized['overview']['working_seats'] is None
    assert normalized['overview']['launches_live'] == 285


@pytest.mark.parametrize('bad', [None, -1, True, 3.5, '10'])
def test_invalid_optional_launch_count_stays_unknown(bad):
    raw = overview(); raw['counts']['launchesLive'] = bad
    assert hub.normalize_overview(raw)['overview']['launches_live'] is None


def test_legacy_overview_upgrade_preserves_clocks_and_checks_original_hash():
    payload = hub.normalize_overview(overview())
    for key in ('working_seats', 'launches_live'):
        payload['overview'].pop(key, None)
    source = hub.source_envelope(payload, 100, provider_ts=90)
    before = deepcopy(source)
    upgraded = hub.coerce_source(source, 'overview', now=200)
    assert upgraded['payload']['overview']['launches_live'] is None
    assert upgraded['payload']['overview']['working_seats'] is None
    assert (upgraded['read_ts'], upgraded['attempt_ts'], upgraded['provider_ts']) == (100, 100, 90)
    assert source == before
    source['payload']['overview']['jobs'] += 1
    assert hub.coerce_source(source, 'overview', now=200) is None


@pytest.mark.parametrize('key', ['launches_live', 'working_seats'])
@pytest.mark.parametrize('bad', [-1, True, 1.5, '12'])
def test_restored_optional_counters_are_validated(key, bad):
    payload = hub.normalize_overview(overview()); payload['overview'][key] = bad
    assert hub.coerce_source(hub.source_envelope(payload, 100), 'overview', now=200) is None


async def test_completed_workflows_require_full_known_catalogue_and_keep_last_good():
    raw = json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())
    template = raw['workflows'][0]
    rows = [dict(template, id=f'00000000-0000-4000-8000-{i:012d}', status=status) for i, status in
            enumerate(('completed', 'superseded', 'executing', 'cancelled', 'blocked', 'failed'))]
    catalogue = AsyncMock(return_value=(rows, True, 100))
    reader = SurfCardReader(SimpleNamespace(_clock=lambda: 200, _refresh_workflow_catalogue=catalogue))
    await reader._work()
    facts = reader.current_work({})
    assert (reader.workflows, facts['completed_workflows'], facts['workflows_read_ts']) == (1, 2, 100)
    for incomplete, complete in (([], False), ([dict(template, status='future')], True)):
        catalogue.return_value = incomplete, complete, 150
        await reader._work()
        assert reader.current_work({})['completed_workflows'] == 2
        assert reader.current_work({})['workflows_read_ts'] == 100
    catalogue.return_value = [], True, 180
    await reader._work()
    assert (reader.workflows, reader.current_work({})['completed_workflows']) == (0, 0)
    assert reader.current_work({})['workflows_read_ts'] == 180
