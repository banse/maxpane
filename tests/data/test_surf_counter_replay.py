"""Reorg corrections must reach cumulative POOL4 controls, including restart."""
from copy import deepcopy

from maxpane_dashboard.data.surf_cache import SurfCache
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data import surf_pool4 as P
from tests.data.test_surf_manager_pool4 import FLOW_LOGS_FULL, SEPOLIA, _manager


def window():
    rows = deepcopy(FLOW_LOGS_FULL)
    # A controlled reorg of captured events; payloads stay byte-for-byte.
    for i, row in enumerate(rows):
        row['blockNumber'] = hex(100 + i)
    return rows, 100 + len(rows) - 1


def test_reorg_removes_old_counter_contribution_and_survives_cache_reload(tmp_path):
    rows, head = window()
    manager = _manager(tmp_path)
    first = manager._pool4_accumulate(SEPOLIA, rows, 90, head)
    assert first['sums'] == P.accumulate_counters(P.empty_accumulator(), rows, 90, head)['sums']
    saved = SurfCache._coerce_accumulator(manager.cache.get_pool4_accumulator(SEPOLIA))
    manager.cache.set_pool4_accumulator(SEPOLIA, saved)
    replacement = rows[:-3]
    start = head - 11
    tail = [row for row in replacement if int(row['blockNumber'], 16) >= start]
    changed = manager._pool4_accumulate(SEPOLIA, tail, start, head + 1)
    expected = P.accumulate_counters(P.empty_accumulator(), replacement, 90, head + 1)
    assert changed['sums'] == expected['sums']
    assert changed['sums'] != first['sums']


def test_gap_still_discards_counters(tmp_path):
    rows, head = window()
    manager = _manager(tmp_path)
    manager._pool4_accumulate(SEPOLIA, rows, 90, head)
    assert manager._pool4_accumulate(SEPOLIA, [], head + 100, head + 200) is None


def test_failed_read_preserves_checkpoint(tmp_path):
    rows, head = window()
    manager = _manager(tmp_path)
    prior = manager._pool4_accumulate(SEPOLIA, rows, 90, head)
    assert manager._pool4_accumulate(SEPOLIA, None, 90, head + 1) == prior
