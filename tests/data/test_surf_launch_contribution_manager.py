"""The board's background launch ranking has a visibility-only I/O boundary."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_CONTRIBUTION


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
        assert reopened.get_launch_contribution_snapshot()["rows"] == expected
    finally:
        await reopened.close()
