"""Exact launchpad windows from committed logs and synthetic block headers."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_client

FIXTURES = Path(__file__).parents[1] / 'fixtures/surf/launchpad'


def fixture(name):
    return json.loads((FIXTURES / (name+'.json')).read_text())


async def snapshot(*, rows=None, headers=None, total=13, start=None, calls=None):
    from maxpane_dashboard.data.surf_launchpad_volume import fetch_snapshot
    logs, capture = fixture('launchpad_logs'), fixture('volume_headers')
    answers = capture['headers'] if headers is None else headers
    async def read(batch):
        if calls is not None:
            calls.append(batch)
        assert all(method == 'eth_getBlockByNumber' and params[1] is False for method, params in batch)
        return [deepcopy(answers.get(str(int(params[0], 16)))) for _, params in batch]
    return await fetch_snapshot(
        [r for r in logs['curve_swap'] if r['topics'][1] in {r['topics'][1] for r in logs['launched']}] if rows is None else rows,
        {r['topics'][1] for r in logs['launched']}, coin_count=total,
        start_block=capture['start'] if start is None else start,
        head_block=capture['head'], now=capture['now'], read_headers=read,
        decode_swap=surf_client._decode_curve_swap_log)


async def test_uncapped_pool_volume_uses_real_headers_and_closed_quarter_hours():
    logs, capture = fixture('launchpad_logs'), fixture('volume_headers')
    calls = []
    got = await snapshot(calls=calls)
    expected = [0]*8
    pools = {r['topics'][1] for r in logs['launched']}
    until = capture['now']//900*900
    for row in logs['curve_swap']:
        decoded = surf_client._decode_curve_swap_log(row)
        ts = int(capture['headers'][str(decoded['block'])]['timestamp'], 16)
        if decoded['pool_id'] in pools and until-7200 <= ts < until:
            expected[(ts-(until-7200))//900] += decoded['eth_amount_wei']
    assert got == dict(state='ok', points_wei=expected, read_ts=capture['now'],
                       head_ts=capture['now'], until=until, known=13, total=13)
    assert sum(expected) > 0 and len({value for value in expected if value}) > 1
    assert len(calls[0]) == 2 and all(len(batch) <= 32 for batch in calls)


async def test_replayed_log_deduplicates_but_conflicting_identity_rejects_snapshot():
    logs = fixture('launchpad_logs')
    rows = [r for r in logs['curve_swap'] if r['topics'][1] in {r['topics'][1] for r in logs['launched']}]
    expected = await snapshot(rows=rows)
    assert await snapshot(rows=rows+[deepcopy(rows[-1])]) == expected
    conflict = deepcopy(rows[-1])
    conflict['data'] = conflict['data'][:66] + 'f'*64 + conflict['data'][130:]
    assert await snapshot(rows=rows+[conflict]) is None


async def test_unknown_pool_never_silently_understates_factory_volume():
    assert await snapshot(rows=fixture('launchpad_logs')['curve_swap']) is None


async def test_rows_before_the_covered_day_do_not_invalidate_the_current_window():
    row = deepcopy(fixture('launchpad_logs')['curve_swap'][0])
    row['blockNumber'] = hex(fixture('volume_headers')['start']-1)
    assert (await snapshot(rows=[row]))['points_wei'] == [0]*8


async def test_conflicting_non_amount_words_still_reject_duplicate_identity():
    original = fixture('launchpad_logs')['curve_swap'][0]
    conflict = deepcopy(original)
    conflict['data'] = conflict['data'][:130]+'f'*64+conflict['data'][194:]
    assert await snapshot(rows=[original, conflict]) is None


async def test_window_boundaries_use_actual_timestamps_and_distinct_log_indices():
    capture = fixture('volume_headers')
    headers, rows = capture['headers'], []
    until = capture['now']//900*900
    stamps = [until-7201, until-7200, until-1, until, until+1]
    for index, stamp in enumerate(stamps):
        block = capture['head']-len(stamps)+index
        row = deepcopy(fixture('launchpad_logs')['curve_swap'][0])
        row.update(blockNumber=hex(block), logIndex=hex(index))
        rows.append(row)
        headers[str(block)] = dict(number=hex(block), timestamp=hex(stamp), hash='0x'+f'{block:064x}')
    amount = surf_client._decode_curve_swap_log(rows[0])['eth_amount_wei']
    assert (await snapshot(rows=rows, headers=headers))['points_wei'] == [amount, 0, 0, 0, 0, 0, 0, amount]


async def test_failed_trade_header_and_chain_hash_conflict_are_unknown():
    row = fixture('launchpad_logs')['curve_swap'][0]
    headers = fixture('volume_headers')['headers']
    headers.pop(str(int(row['blockNumber'], 16)))
    assert await snapshot(rows=[row], headers=headers) is None
    row['blockHash'] = '0x'+'f'*64
    assert await snapshot(rows=[row]) is None


@pytest.mark.parametrize('damage', ['missing', 'wrong_number', 'future', 'hash', 'coverage'])
async def test_missing_or_invalid_header_never_becomes_zero(damage):
    capture = fixture('volume_headers')
    headers = capture['headers']
    key = str(capture['head'])
    if damage == 'missing':
        headers.pop(key)
    elif damage == 'wrong_number':
        headers[key]['number'] = hex(capture['head']-1)
    elif damage == 'future':
        headers[key]['timestamp'] = hex(capture['now']+1)
    elif damage == 'hash':
        headers[key]['hash'] = 'not a hash'
    else:
        headers[str(capture['start'])]['timestamp'] = hex(capture['now']-100)
    assert await snapshot(rows=[] if damage == 'coverage' else None, headers=headers) is None


@pytest.mark.parametrize('damage', ['amount', 'index', 'tx', 'pool', 'address', 'removed'])
async def test_malformed_swap_cannot_certify_quiet_buckets(damage):
    rows = fixture('launchpad_logs')['curve_swap']
    row = rows[-1]
    if damage == 'amount':
        row['data'] = '0x'+'z'*384
    elif damage == 'index':
        row['logIndex'] = None
    elif damage == 'tx':
        row['transactionHash'] = '0x123'
    elif damage == 'pool':
        row['topics'][1] = '0x123'
    elif damage == 'address':
        row['address'] = '0x'+'f'*40
    else:
        row['removed'] = True
    assert await snapshot(rows=rows) is None


async def test_quiet_window_is_zero_only_after_full_time_and_factory_coverage():
    assert (await snapshot(rows=[]))['points_wei'] == [0]*8
    partial = await snapshot(rows=[], total=14)
    assert partial['state'] == 'partial' and partial['points_wei'] is None
    assert partial['known'] == 13 and partial['total'] == 14
    assert (await snapshot(rows=[], total=None))['points_wei'] is None
    assert await snapshot(rows=[], headers={}) is None


async def test_block_budget_is_bounded_and_exhaustion_is_unknown():
    from maxpane_dashboard.data.surf_launchpad_volume import MAX_BLOCK_HEADERS
    logs, capture = fixture('launchpad_logs'), fixture('volume_headers')
    rows, headers = [], capture['headers']
    for index in range(MAX_BLOCK_HEADERS+1):
        block = capture['head']-index-1
        row = deepcopy(logs['curve_swap'][0])
        row.update(blockNumber=hex(block), transactionHash='0x'+f'{index+1:064x}')
        rows.append(row)
        headers[str(block)] = dict(number=hex(block), timestamp=hex(capture['now']-index-1), hash='0x'+f'{block:064x}')
    calls = []
    assert await snapshot(rows=rows, headers=headers, calls=calls) is None
    assert sum(len(batch) for batch in calls) <= MAX_BLOCK_HEADERS+2


async def test_snapshot_validation_rechecks_persisted_points_and_keeps_read_clock():
    from maxpane_dashboard.data.surf_launchpad_volume import coerce_snapshot
    got = await snapshot()
    assert coerce_snapshot(got, now=got['read_ts']+1000) == got
    for field, value in [('points_wei', [True]*8), ('until', got['until']+1),
                          ('read_ts', got['read_ts']+1), ('known', 12)]:
        bad = dict(got, **{field: value})
        assert coerce_snapshot(bad, now=got['read_ts']) is None
    assert coerce_snapshot(dict(got, until=0, head_ts=10), now=got['read_ts']) is None


async def test_header_deadline_returns_unknown_without_waiting_for_slow_provider(monkeypatch):
    import asyncio
    from maxpane_dashboard.data import surf_launchpad_volume as volume
    class Expired:
        async def __aenter__(self):
            raise TimeoutError
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(asyncio, 'timeout', lambda seconds: Expired())
    assert await snapshot() is None
