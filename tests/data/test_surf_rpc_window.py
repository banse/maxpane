"""Deterministic replay of full-window rows and twelve-block reorgs."""
import asyncio
import copy
import json

import httpx
import pytest

from maxpane_dashboard.data.surf_rpc_history import RpcHistoryReader
from maxpane_dashboard.data.surf_rpc_window import RpcLogWindow
from tests.data.test_surf_client import _load_launchpad, _rpc_ok

ENDPOINTS = ('https://first.example', 'https://second.example')
FILTER = {'address': '0x' + '11' * 20, 'topics': ['0x' + '22' * 32]}
CAPTURE = _load_launchpad('full_history.json')['curve_swap'][0]


def row(block, ident):
    return dict(CAPTURE, blockNumber=hex(block), transactionHash='0x' + format(ident, '064x'),
                logIndex='0x0', blockHash='0x' + format(block, '064x'))


def setup(rows, *, max_pages=256, max_rows=200000, max_windows=16):
    calls = []
    mode = {'fail': False, 'cancel_at': None}

    async def post(url, payload):
        flt = payload['params'][0]
        lo, hi = int(flt['fromBlock'], 16), int(flt['toBlock'], 16)
        calls.append((lo, hi))
        if mode['cancel_at'] == lo:
            raise asyncio.CancelledError()
        if mode['fail']:
            return httpx.Response(503)
        return httpx.Response(200, json=_rpc_ok(payload, [copy.deepcopy(r) for r in rows
            if lo <= int(r['blockNumber'], 16) <= hi]))

    history = RpcHistoryReader(post, max_pages=max_pages)
    return RpcLogWindow(history, max_rows=max_rows, max_windows=max_windows), calls, mode


@pytest.mark.asyncio
async def test_window_reads_only_new_blocks_plus_twelve_replay_and_prunes_expired_rows():
    rows = [row(0, 1), row(50, 2), row(89, 3), row(100, 4)]
    window, calls, _ = setup(rows)
    assert await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps') == rows
    rows.append(row(110, 5))
    calls.clear()
    actual = await window.read(ENDPOINTS, FILTER, 10, 110, group='swaps')
    assert actual == rows[1:]
    assert calls == [(89, 110)]


@pytest.mark.asyncio
async def test_reorg_replaces_old_tail_including_removed_logs_without_duplicates():
    rows = [row(20, 1), row(89, 2), row(96, 3), row(100, 4)]
    window, calls, _ = setup(rows)
    await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps')
    rows[:] = [rows[0], row(90, 5), row(98, 6), row(104, 7)]
    calls.clear()
    expected = copy.deepcopy(rows)
    assert await window.read(ENDPOINTS, FILTER, 4, 104, group='swaps') == expected
    assert calls == [(89, 104)]
    assert await window.read(ENDPOINTS, FILTER, 4, 104, group='swaps') == expected


@pytest.mark.asyncio
async def test_failed_tail_never_publishes_partial_or_overwrites_complete_window():
    rows = [row(20, 1), row(95, 2)]
    window, calls, mode = setup(rows)
    await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps')
    mode['fail'] = True
    assert await window.read(ENDPOINTS, FILTER, 10, 110, group='swaps') is None
    mode['fail'] = False
    rows[:] = [row(20, 1), row(98, 3), row(110, 4)]
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 10, 110, group='swaps') == rows
    assert calls == [(89, 110)]


@pytest.mark.asyncio
async def test_window_head_rollback_discards_orphaned_rows():
    rows = [row(20, 1), row(95, 2), row(100, 3)]
    window, calls, _ = setup(rows)
    await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps')
    rows[:] = [row(20, 1), row(92, 4)]
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 0, 95, group='swaps') == rows
    assert calls == [(89, 95)]


@pytest.mark.asyncio
async def test_widening_window_cold_reads_missing_history_and_eviction_is_safe():
    rows = [row(0, 1), row(50, 2), row(95, 3)]
    window, calls, _ = setup(rows, max_windows=1)
    await window.read(ENDPOINTS, FILTER, 50, 100, group='swaps')
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 0, 110, group='swaps') == rows
    assert calls[0] == (0, 110)
    await window.read(ENDPOINTS, FILTER, 0, 110, group='other')
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 0, 110, group='swaps') == rows
    assert calls[0] == (0, 110)


@pytest.mark.asyncio
async def test_page_budget_keeps_cold_progress_until_complete():
    rows = [row(10, 1), row(60, 2), row(110, 3)]
    window, calls, _ = setup(rows, max_pages=2)
    assert await window.read(ENDPOINTS, FILTER, 0, 149, group='swaps', page_size=50) is None
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 0, 149, group='swaps', page_size=50) == rows
    assert calls == [(100, 149)]


@pytest.mark.asyncio
async def test_duplicate_rows_count_once_but_conflicting_identity_is_unknown():
    original = row(50, 1)
    rows = [original, copy.deepcopy(original)]
    window, _, _ = setup(rows)
    assert await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps') == [original]
    rows[:] = [row(100, 2), dict(row(100, 2), data='0x1234')]
    assert await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps') is None


@pytest.mark.asyncio
async def test_window_memory_limit_never_publishes_truncated_rows():
    rows = [row(50, 1), row(95, 2)]
    window, calls, _ = setup(rows, max_rows=1)
    assert await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps') is None
    rows[:] = rows[:1]
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 0, 100, group='swaps') == rows
    assert calls[0] == (0, 100)


@pytest.mark.asyncio
async def test_pending_tail_replays_reorg_after_cancellation():
    rows = [row(10, 1), row(90, 2), row(100, 3)]
    window, calls, mode = setup(rows)
    mode['cancel_at'] = 100
    with pytest.raises(asyncio.CancelledError):
        await window.read(ENDPOINTS, FILTER, 0, 109, group='swaps', page_size=50)
    rows[:] = [row(10, 1), row(90, 2), row(99, 4), row(109, 5)]
    mode['cancel_at'] = None
    calls.clear()
    assert await window.read(ENDPOINTS, FILTER, 0, 109, group='swaps', page_size=50) == rows
    assert calls == [(98, 109)]


@pytest.mark.asyncio
async def test_history_proves_global_upper_bound_before_accepting_any_page():
    calls = []
    proofs = []
    async def prove(url, block):
        proofs.append((url, block))
        return url == ENDPOINTS[1]
    async def post(url, payload):
        calls.append((url, payload['params'][0]))
        return httpx.Response(200, json=_rpc_ok(payload, [row(int(payload['params'][0]['fromBlock'], 16), len(calls))]))
    history = RpcHistoryReader(post, prove_block=prove)
    result = await history.read(ENDPOINTS, FILTER, 0, 100, group='proof', page_size=50)
    assert result is not None
    assert all(block == 100 for _, block in proofs)
    assert all(url == ENDPOINTS[1] for url, _ in calls)
    assert len(calls) == 3
