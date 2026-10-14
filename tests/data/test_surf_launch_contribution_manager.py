"""The board's background launch ranking has a visibility-only I/O boundary."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_CONTRIBUTION, SLOT_SWARM_WORKERS
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_models import SWARM_LAUNCH_CONTRIBUTION_ROW_FIELDS


async def test_catalogue_and_reader_are_offered_only_for_visible_launch_tab(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    catalogue = SimpleNamespace(offer_catalogue=Mock(), _catalogue_rows=Mock(return_value=[]),
        _complete=True, _cat_failed=False, _cat_as_of=123.0, close=AsyncMock(),
        catalogue_summary=Mock(return_value=None), _tasks={}, _scan=None)
    manager._swarm_tokens_manager = catalogue
    reader = SimpleNamespace(offer=Mock(), project=Mock(return_value={"rows": []}),
                             cancel=Mock(), close=AsyncMock())
    manager._launch_contribution_reader = reader
    try:
        manager.offer_launch_contribution()
        catalogue.offer_catalogue.assert_not_called()
        manager.set_launch_contribution_active(True)
        reader.offer.assert_not_called()
        assert manager.get_launch_contribution_snapshot() == {"rows": []}
        reader.offer.assert_not_called()
        manager.offer_launch_contribution()
        catalogue.offer_catalogue.assert_called_once_with()
        reader.offer.assert_called_once_with([], complete=True, failed=False, read_ts=123.0)
        assert manager._project_hub()["swarm_launch_contribution"] == {"rows": []}
        manager.set_launch_contribution_active(False)
        reader.cancel.assert_called_once_with()
        manager.offer_launch_contribution()
        assert reader.offer.call_count == 1
    finally:
        await manager.close()
    reader.close.assert_awaited_once_with()
    manager.set_launch_contribution_active(True)
    manager.offer_launch_contribution()
    assert reader.offer.call_count == 1


async def test_incomplete_or_failed_catalogue_reaches_reader_unchanged(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    manager._swarm_tokens_manager = SimpleNamespace(offer_catalogue=Mock(),
        _catalogue_rows=Mock(return_value=None), _complete=False, _cat_failed=True,
        _cat_as_of=None, close=AsyncMock(), _scan=None)
    manager._launch_contribution_reader.offer = Mock()
    try:
        manager.set_launch_contribution_active(True)
        manager.offer_launch_contribution()
        manager._launch_contribution_reader.offer.assert_called_once_with(
            None, complete=False, failed=True, read_ts=None)
        catalogue = manager._swarm_tokens_manager
        catalogue._complete, catalogue._cat_failed, catalogue._scan = True, False, {}
        manager.offer_launch_contribution()
        manager._launch_contribution_reader.offer.assert_called_with(
            None, complete=False, failed=False, read_ts=None)
    finally:
        await manager.close()


async def test_manager_restores_completed_ranking_after_loading_disk_cache(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    expected = [{"token_id": 401, "rank": 1, "jobs": 4, "launches": 3}]
    manager.cache.store_last_good(SLOT_SWARM_LAUNCH_CONTRIBUTION,
        {"snapshot": {"rows": expected, "read_ts": manager._clock() - 60}})
    await manager.close()
    reopened = _manager(tmp_path, _FakeSwarm())
    try:
        assert reopened.get_launch_contribution_snapshot()["rows"] == [dict(
            row, build_jobs=None, review_jobs=None, advertised_models=None) for row in expected]
    finally:
        await reopened.close()


async def test_current_models_join_all_workers_without_mutating_history_or_fetching(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    history = {"rows": [dict(rank=1, token_id=98765, jobs=4, launches=3,
                            build_jobs=2, review_jobs=3)]}
    manager._launch_contribution_reader.project = Mock(return_value=history)
    workers = sw.normalize_workers(swarm.workers)
    sample = workers['workers'][0]
    workers['workers'] = [dict(sample, token_id=98765, advertised_models=[
        {'model': 'fable 5.1', 'effort': 'high'}, {'model': 'astra 6', 'effort': None}]),
        dict(sample, token_id=98765, advertised_models=[
        {'model': 'astra 6', 'effort': 'xhigh'}, {'model': 'fable 5.1', 'effort': 'high'}])]
    workers['count'] = 2
    manager.cache.store_last_good(SLOT_SWARM_WORKERS, workers)
    original = copy.deepcopy((history, workers))
    try:
        row = manager.get_launch_contribution_snapshot()['rows'][0]
        assert set(row) == set(SWARM_LAUNCH_CONTRIBUTION_ROW_FIELDS)
        assert row['advertised_models'] == [
            {'model': 'astra 6', 'effort': None}, {'model': 'astra 6', 'effort': 'xhigh'},
            {'model': 'fable 5.1', 'effort': 'high'}]
        assert manager._project_hub()['swarm_launch_contribution']['rows'] == [row]
        row['advertised_models'][0]['model'] = 'edited'
        assert (history, workers) == original
        assert manager.get_launch_contribution_snapshot()['rows'][0]['advertised_models'][0]['model'] == 'astra 6'
        assert not swarm.calls
    finally:
        await manager.close()


@pytest.mark.parametrize('source,expected', [('missing', None), ('malformed', None),
                                          ('complete', []), ('partial', None)])
async def test_no_advertised_models_preserves_source_availability(tmp_path, source, expected):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    manager._launch_contribution_reader.project = Mock(return_value={
        'rows': [dict(rank=1, token_id=98765, jobs=1, launches=1, build_jobs=1, review_jobs=0)]})
    if source != 'missing':
        workers = sw.normalize_workers(swarm.workers)
        workers['workers'] = []
        workers['count'] = 0 if source == 'complete' else 1
        if source == 'malformed':
            workers['workers'] = [{'token_id': 98765, 'advertised_models': [{'model': 3}]}]
        manager.cache.store_last_good(SLOT_SWARM_WORKERS, workers)
    try:
        assert manager.get_launch_contribution_snapshot()['rows'][0]['advertised_models'] == expected
    finally:
        await manager.close()
