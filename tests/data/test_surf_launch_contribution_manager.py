"""The board's background launch ranking has a visibility-only I/O boundary."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCH_CONTRIBUTION, SLOT_SWARM_WORKERS
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data import surfboard as hub
from maxpane_dashboard.data.surf_models import SWARM_LAUNCH_CONTRIBUTION_ROW_FIELDS


async def test_catalogue_and_reader_are_offered_only_for_visible_board(tmp_path):
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
        snapshot = manager.get_launch_contribution_snapshot()
        assert snapshot['rows'] == [] and snapshot['summary']['seats'] == 0
        reader.offer.assert_not_called()
        manager.offer_launch_contribution()
        catalogue.offer_catalogue.assert_called_once_with()
        reader.offer.assert_called_once_with([], complete=True, failed=False, read_ts=123.0)
        assert manager._project_hub()["swarm_launch_contribution"] == snapshot
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


async def test_launch_summary_and_board_hero_share_live_cache_only_projection(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    now = manager._clock()
    history = dict(state='ok', read_ts=now - 90, jobs=3, rows=[
        dict(rank=1, token_id=7, jobs=2, launches=2, build_jobs=2, review_jobs=0),
        dict(rank=2, token_id=527, jobs=2, launches=1, build_jobs=1, review_jobs=1),
        dict(rank=3, token_id=90, jobs=1, launches=1, build_jobs=1, review_jobs=0)])
    manager._launch_contribution_reader.project = Mock(return_value=history)
    workers = sw.normalize_workers(swarm.workers)
    sample = workers['workers'][0]
    workers.update(count=4, malformed_tokens=[], workers=[
        dict(sample, token_id=7, runtimes=['claude']), dict(sample, token_id=7, runtimes=['codex']),
        dict(sample, token_id=527, runtimes=None), dict(sample, token_id=999, runtimes=['codex'])])
    manager.cache.store_last_good(SLOT_SWARM_WORKERS, workers, ts=now - 20)
    entry = manager.cache.get_last_good(SLOT_SWARM_WORKERS)
    manager._swarm_board_observations[SLOT_SWARM_WORKERS] = dict(entry=entry, read_ts=now - 10, failed=False)
    try:
        snapshot = manager.get_launch_contribution_snapshot()
        assert snapshot['summary'] == dict(state='ok', read_ts=now - 90, seats=3,
            claude=1, codex=1, jobs=3, runtime_known=1, runtime_state='ok', runtime_read_ts=now - 10,
            percent=None, total_seats=None, records_state='unavailable', records_read_ts=None)
        board = manager._swarm_board_keys(None, entry, None)
        assert board['swarm_launch_contribution'] == snapshot
        assert board['surf_leaderboard_hero']['launches'] == snapshot['summary']
        assert manager._project_hub()['surf_leaderboard_hero']['launches'] == snapshot['summary']
        history.update(state='pending')
        assert manager.get_launch_contribution_snapshot()['summary'] == dict(snapshot['summary'], state='pending')
        history.update(state='stale')
        assert manager.get_launch_contribution_snapshot()['summary'] == dict(snapshot['summary'], state='stale')
        assert not swarm.calls
    finally:
        await manager.close()


async def test_cold_launch_summary_keeps_pending_and_worker_clock_independent(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    try:
        summary = manager.get_launch_contribution_snapshot()['summary']
        assert summary == dict(state='pending', read_ts=None, seats=None, claude=None, codex=None,
            jobs=None, runtime_known=None, runtime_state='unavailable', runtime_read_ts=None,
            percent=None, total_seats=None, records_state='unavailable', records_read_ts=None)
        assert manager._swarm_board_keys(None, None, None)['surf_leaderboard_hero']['launches'] == summary
        assert not swarm.calls
    finally:
        await manager.close()


async def test_recorded_online_counts_unique_canonical_seats_and_uses_captured_roster(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    now = manager._clock()
    workers = sw.normalize_workers(swarm.workers)
    sample = workers['workers'][0]
    workers.update(count=3, malformed_tokens=[], workers=[
        dict(sample, token_id=7), dict(sample, token_id=7), dict(sample, token_id=999)])
    manager.cache.store_last_good(SLOT_SWARM_WORKERS, workers, ts=now - 40)
    entry = manager.cache.get_last_good(SLOT_SWARM_WORKERS)
    source = dict(state='ok', read_ts=now - 80, payload=dict(count=2, seats=[
        dict(token_id=7, agent_id=None, accepted=3, attempts=4, rejected=0, failed=1, pending=0),
        dict(token_id=527, agent_id=None, accepted=1, attempts=2, rejected=0, failed=0, pending=1)]))
    captured = manager._swarm_board_hero_sources(None, entry, now=now)
    manager.cache.store_last_good(SLOT_SWARM_WORKERS, dict(workers, count=0, workers=[]), ts=now)
    try:
        board = manager._swarm_board_keys(None, entry, None, records_source=source, hero_sources=captured)
        assert board['surf_leaderboard_hero']['recorded'] == dict(state='ok', read_ts=now - 80,
            seats=2, attempts=6, online=1, online_state='stale', online_read_ts=now - 40)
        assert not swarm.calls
    finally:
        await manager.close()


async def test_periodic_launch_share_uses_current_records_and_board_uses_its_captured_source(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    now = manager._clock()
    manager._launch_contribution_reader.project = Mock(return_value=dict(state='ok', read_ts=now - 90,
        jobs=3, rows=[dict(rank=1, token_id=7, jobs=2, launches=2, build_jobs=2, review_jobs=0),
                     dict(rank=2, token_id=527, jobs=2, launches=2, build_jobs=0, review_jobs=2)]))
    records = dict(count=4, seats=[dict(token_id=token, agent_id=None, attempts=1, accepted=1,
        rejected=0, failed=0, pending=0) for token in (7, 90, 527, 999)])
    current = hub.source_envelope(records, now - 50)
    manager.cache.store_last_good(hub.SOURCE_SLOTS['records'], current, ts=now - 50)
    captured = hub.source_envelope(dict(count=2, seats=records['seats'][:2]), now - 100)
    try:
        periodic = manager.get_launch_contribution_snapshot()['summary']
        assert periodic['percent'] == 50 and periodic['total_seats'] == 4
        assert periodic['records_state'] == 'ok' and periodic['records_read_ts'] == now - 50
        assert periodic['read_ts'] == now - 90 and periodic['state'] == 'ok'
        board = manager._swarm_board_keys(None, None, None, records_source=captured)
        summary = board['surf_leaderboard_hero']['launches']
        assert summary == board['swarm_launch_contribution']['summary']
        assert summary['total_seats'] == board['surf_leaderboard_hero']['recorded']['seats'] == 2
        assert summary['percent'] == 100 and summary['records_read_ts'] == now - 100
        assert manager.get_launch_contribution_snapshot()['summary'] == periodic
        manager._clock.advance(121)
        assert manager.get_launch_contribution_snapshot()['summary'] == dict(periodic, records_state='stale')
        assert not swarm.calls
    finally:
        await manager.close()


async def test_records_failure_keeps_launch_share_when_retained_and_never_erases_launch_totals(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    now = manager._clock()
    manager._launch_contribution_reader.project = Mock(return_value=dict(state='ok', read_ts=now - 90,
        jobs=1, rows=[dict(rank=1, token_id=7, jobs=1, launches=1, build_jobs=1, review_jobs=0)]))
    records = dict(count=2, seats=[dict(token_id=token, agent_id=None, attempts=1, accepted=1,
        rejected=0, failed=0, pending=0) for token in (7, 527)])
    source = hub.source_envelope(records, now - 50)
    failed = hub.source_envelope(None, now, prior=source)
    manager.cache.store_last_good(hub.SOURCE_SLOTS['records'], failed, ts=now)
    try:
        retained = manager.get_launch_contribution_snapshot()['summary']
        assert retained['percent'] == 50 and retained['total_seats'] == 2
        assert retained['records_state'] == 'stale' and retained['records_read_ts'] == now - 50
        manager.cache.store_last_good(hub.SOURCE_SLOTS['records'], hub.source_envelope(None, now), ts=now)
        unread = manager.get_launch_contribution_snapshot()['summary']
        assert unread == dict(retained, percent=None, total_seats=None,
                             records_state='unavailable', records_read_ts=None)
        assert unread['state'] == 'ok' and unread['read_ts'] == now - 90
        assert unread['seats'] == unread['jobs'] == 1 and not swarm.calls
    finally:
        await manager.close()
