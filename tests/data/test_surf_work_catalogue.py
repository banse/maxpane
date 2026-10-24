"""Validated WIP catalogue deltas; all input comes from local fixtures."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_work as work
from maxpane_dashboard.data import surf_work_catalogue as catalogue


@pytest.fixture
def captured():
    return json.loads(Path('tests/fixtures/surf/work/captured.json').read_text())


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def entry(captured, kind='jobs'):
    now = captured['read_ts']
    return catalogue.make_entry(captured[kind], kind, now=now, read_ts=now, full_ts=now)


def job(captured, number, *, created=None, updated=None, state='blocked'):
    now = captured['read_ts']
    return dict(captured['jobs'][0], id=f'00000000-0000-0000-0000-{number:012d}',
                state=state, createdAt=iso(now - 20 if created is None else created),
                updatedAt=iso(now - 10 if updated is None else updated))


@pytest.mark.parametrize('kind', ['jobs', 'workflows'])
def test_cache_roundtrip_and_source_rows(captured, kind):
    original = entry(captured, kind)
    stored = json.loads(json.dumps({kind: original}))
    restored = catalogue.coerce_catalogue(stored, now=captured['read_ts'])
    assert restored[kind] == original
    assert restored['workflows' if kind == 'jobs' else 'jobs'] is None
    decoder = work._job if kind == 'jobs' else work._workflow
    assert [decoder(row, captured['read_ts']) for row in catalogue.source_rows(original, kind)] == original['rows']


@pytest.mark.parametrize('change', [
    lambda e: e.update(extra=True),
    lambda e: e.update(watermark=None),
    lambda e: e.update(watermark=True),
    lambda e: e.update(watermark=e['rows'][0]['updated_ts'] - 1),
    lambda e: e.update(full_ts=e['read_ts'] + 1),
    lambda e: e.update(read_ts=float('nan')),
    lambda e: e['rows'][0].update(updated_ts=None),
    lambda e: e['rows'][0].update(nodes=[]),
    lambda e: e['rows'][0].update(detail_state='ok'),
    lambda e: e['rows'][0].update(extra=True),
    lambda e: e['rows'].append(e['rows'][0]),
])
def test_bad_cache_discards_only_bad_source(captured, change):
    jobs, workflows = entry(captured), entry(captured, 'workflows')
    change(jobs)
    restored = catalogue.coerce_catalogue({'jobs': jobs, 'workflows': workflows}, now=captured['read_ts'])
    assert restored == {'jobs': None, 'workflows': workflows}


def test_pruning_does_not_lose_watermark_or_old_open_jobs(captured):
    now = captured['read_ts']
    rows = [job(captured, 1, created=now - 90000, updated=now - 1, state='completed'),
            job(captured, 2, created=now - 90000, updated=now - 2), job(captured, 3)]
    result = catalogue.make_entry(rows, 'jobs', now=now, read_ts=now, full_ts=now)
    assert {r['id'] for r in result['rows']} == {row['id'] for row in rows}
    assert result['watermark'] == work._ts(rows[0]['updatedAt'])
    assert all(row['nodes'] is None and row['detail_state'] == 'not_loaded' for row in result['rows'])
    expired = catalogue.make_entry(rows, 'jobs', now=now + 86401, read_ts=now + 86401, full_ts=now)
    assert {r['id'] for r in expired['rows']} == {rows[1]['id'], rows[2]['id']}
    assert expired['watermark'] == result['watermark']


@pytest.mark.parametrize('field,value', [('id', 'bad'), ('state', None), ('createdAt', None),
                                      ('updatedAt', 'nonsense'), ('updatedAt', '2999-01-01T00:00:00.000Z')])
def test_invalid_api_row_cannot_certify_catalogue(captured, field, value):
    rows = copy.deepcopy(captured['jobs'])
    rows[-1][field] = value
    now = captured['read_ts']
    assert catalogue.make_entry(rows, 'jobs', now=now, read_ts=now, full_ts=now) is None


def test_duplicate_or_oversized_catalogues_are_rejected(captured, monkeypatch):
    now = captured['read_ts']
    assert catalogue.make_entry(captured['jobs'] * 2, 'jobs', now=now, read_ts=now, full_ts=now) is None
    cached = entry(captured)
    monkeypatch.setattr(work, 'HISTORY_JOB_LIMIT', 2)
    assert catalogue.make_entry(captured['jobs'], 'jobs', now=now, read_ts=now, full_ts=now) is None
    assert catalogue.coerce_catalogue({'jobs': cached}, now=now)['jobs'] is None


def test_workflow_cap_and_malformed_link_cannot_certify_catalogue(captured, monkeypatch):
    now = captured['read_ts']
    rows = copy.deepcopy(captured['workflows'])
    rows[0]['contractsJobId'] = 'not-a-job'
    assert catalogue.make_entry(rows, 'workflows', now=now, read_ts=now, full_ts=now) is None
    cached = entry(captured, 'workflows')
    monkeypatch.setattr(work, 'WORKFLOW_LIMIT', 1)
    assert catalogue.make_entry(captured['workflows'], 'workflows', now=now, read_ts=now, full_ts=now) is None
    assert catalogue.coerce_catalogue({'workflows': cached}, now=now)['workflows'] is None


async def test_delta_updates_old_created_job_without_regressing_other_rows(captured):
    initial = entry(captured)
    before = copy.deepcopy(initial)
    now = captured['read_ts'] + 30
    changed = dict(captured['jobs'][2], state='executing', updatedAt=iso(now - 1))
    earlier = dict(captured['jobs'][0], state='blocked', updatedAt=iso(initial['rows'][0]['updated_ts'] - 1))
    calls = []
    async def fetch(method, **kwargs):
        calls.append((method, kwargs)); return [earlier, changed]
    result = await catalogue.read_delta(fetch, initial, 'jobs', now=now, start=now)
    rows = {row['id']: row for row in result['rows']}
    assert calls == [('fetch_jobs', {'limit': 500, 'since': iso(initial['watermark'] - 300)})]
    assert rows[changed['id']]['state'] == 'executing'
    assert rows[earlier['id']]['state'] == 'executing'
    assert result['watermark'] == work._ts(changed['updatedAt'])
    assert result['full_ts'] == initial['full_ts'] and result['read_ts'] == now
    assert initial == before


@pytest.mark.parametrize('kind', ['jobs', 'workflows'])
async def test_empty_delta_retains_rows_and_watermark(captured, kind):
    initial = entry(captured, kind)
    async def fetch(method, **kwargs):
        assert method == 'fetch_' + kind
        assert kwargs['limit'] == (500 if kind == 'jobs' else 100)
        assert kwargs['since'] == iso(initial['watermark'] - 300)
        return []
    result = await catalogue.read_delta(fetch, initial, kind, now=captured['read_ts'] + 30, start=captured['read_ts'] + 30)
    assert result['rows'] == initial['rows'] and result['watermark'] == initial['watermark']
    assert result['read_ts'] > initial['read_ts']


async def test_workflow_delta_keeps_source_fields_and_newest_revision(captured):
    initial = entry(captured, 'workflows'); now = captured['read_ts'] + 30
    changed = dict(captured['workflows'][-1], status='deployment', updatedAt=iso(now - 1), waitingForHosting=True)
    async def fetch(method, **kwargs):
        return [changed]
    result = await catalogue.read_delta(fetch, initial, 'workflows', now=now, start=now)
    row = next(row for row in catalogue.source_rows(result, 'workflows') if row['id'] == changed['id'])
    assert row == changed
    assert result['watermark'] == work._ts(changed['updatedAt'])


async def test_clock_is_rechecked_after_awaited_fetch(captured):
    start = captured['read_ts']
    current = [start]
    async def fetch(method, **kwargs):
        current[0] += 5
        return [job(captured, 10, updated=current[0] - 1)]
    result = await catalogue.read_delta(fetch, entry(captured), 'jobs', now=lambda: current[0], start=start)
    assert result['watermark'] > start and result['read_ts'] == start


async def test_certified_empty_catalogue_discovers_first_job(captured):
    now = captured['read_ts']
    initial = catalogue.make_entry([], 'jobs', now=now, read_ts=now, full_ts=now)
    async def fetch(method, **kwargs):
        assert kwargs == {'limit': 500}
        return [captured['jobs'][0]]
    result = await catalogue.read_delta(fetch, initial, 'jobs', now=now + 30, start=now + 30)
    assert len(result['rows']) == 1 and result['watermark'] is not None


async def test_pagination_preserves_since_and_commits_only_after_last_page(captured, monkeypatch):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT', 2)
    initial = entry(captured)
    now = captured['read_ts'] + 30
    pages = [[job(captured, 10, created=now - 10, updated=now - 1),
              job(captured, 11, created=now - 20, updated=now - 1)],
             [job(captured, 12, created=now - 30, updated=now - 1)]]
    calls = []
    async def fetch(method, **kwargs):
        calls.append(kwargs); return pages[len(calls) - 1]
    result = await catalogue.read_delta(fetch, initial, 'jobs', now=now, start=now)
    assert calls[1] == dict(calls[0], before=iso(work._ts(pages[0][-1]['createdAt']) + .001))
    assert len(result['rows']) == len(initial['rows']) + 3


@pytest.mark.parametrize('failure', ['missing', 'malformed', 'duplicate', 'reversal', 'ignored_since'])
async def test_failed_tail_keeps_entire_prior_entry(captured, monkeypatch, failure):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT', 2)
    initial = entry(captured); before = copy.deepcopy(initial)
    now = captured['read_ts'] + 30
    first = [job(captured, 10, created=now - 10, updated=now - 1),
             job(captured, 11, created=now - 20, updated=now - 1)]
    tail = {'missing': None, 'malformed': [{'id': False}],
            'duplicate': [dict(first[0], createdAt=iso(now - 30))],
            'reversal': [job(captured, 12, created=now - 15, updated=now - 1)],
            'ignored_since': [job(captured, 12, created=now - 1000, updated=initial['watermark'] - 301)]}[failure]
    calls = []
    async def fetch(method, **kwargs):
        calls.append(kwargs); return first if len(calls) == 1 else tail
    with pytest.raises(ValueError):
        await catalogue.read_delta(fetch, initial, 'jobs', now=now, start=now)
    assert initial == before


async def test_ambiguous_full_page_boundary_tie_does_not_advance(captured, monkeypatch):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT', 2)
    now = captured['read_ts']
    async def fetch(method, **kwargs):
        return [job(captured, 10), job(captured, 11)]
    with pytest.raises(ValueError, match='boundary'):
        await catalogue.read_delta(fetch, entry(captured), 'jobs', now=now, start=now)


async def test_page_budget_exhaustion_is_not_success(captured, monkeypatch):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT', 2)
    monkeypatch.setattr(work, 'SCAN_PAGES', 1)
    now = captured['read_ts']
    async def fetch(method, **kwargs):
        return [job(captured, 10, created=now - 10), job(captured, 11, created=now - 20)]
    with pytest.raises(ValueError, match='budget'):
        await catalogue.read_delta(fetch, entry(captured), 'jobs', now=now, start=now)


async def test_merged_row_bound_is_enforced(captured, monkeypatch):
    initial = entry(captured); now = captured['read_ts']
    monkeypatch.setattr(work, 'HISTORY_JOB_LIMIT', len(initial['rows']))
    async def fetch(method, **kwargs):
        return [job(captured, 10)]
    with pytest.raises(ValueError, match='merged'):
        await catalogue.read_delta(fetch, initial, 'jobs', now=now, start=now)


async def test_cancelled_read_does_not_modify_checkpoint(captured):
    import asyncio
    initial = entry(captured); before = copy.deepcopy(initial)
    async def fetch(method, **kwargs):
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await catalogue.read_delta(fetch, initial, 'jobs', now=captured['read_ts'], start=captured['read_ts'])
    assert initial == before


async def test_workflow_catchup_includes_changes_from_earlier_scan_pages(captured):
    scan_start = captured['read_ts']
    finished = scan_start + 900
    pages = copy.deepcopy(captured['workflows'])
    pages[-1]['updatedAt'] = iso(finished - 1)
    initial = catalogue.make_entry(pages, 'workflows', now=finished, read_ts=scan_start, full_ts=scan_start)
    before = copy.deepcopy(initial)
    changed = dict(pages[0], status='completed', updatedAt=iso(scan_start + 60))
    calls = []
    async def fetch(method, **kwargs):
        calls.append((method, kwargs))
        # A real since filter would omit this update if based on the last page.
        return [changed] if work._ts(kwargs['since']) <= work._ts(changed['updatedAt']) else []
    result = await catalogue.read_delta(fetch, initial, 'workflows', now=finished,
                                        start=finished, since_ts=scan_start)
    assert calls == [('fetch_workflows', {'limit': 100, 'since': iso(scan_start - 300)})]
    assert next(row for row in result['rows'] if row['id'] == changed['id'])['status'] == 'completed'
    assert result['watermark'] == initial['watermark']
    assert result['full_ts'] == scan_start and result['read_ts'] == finished
    assert initial == before


async def test_catchup_anchor_never_narrows_existing_watermark(captured):
    initial = entry(captured)
    now = captured['read_ts']
    async def fetch(method, **kwargs):
        assert kwargs['since'] == iso(initial['watermark'] - 300)
        return []
    await catalogue.read_delta(fetch, initial, 'jobs', now=now, start=now, since_ts=now)


@pytest.mark.parametrize('since_ts', [False, 0, -1, float('nan'), float('inf'), '2026-10-13', 1e20])
async def test_invalid_scan_start_is_rejected_before_fetch(captured, since_ts):
    async def fetch(method, **kwargs):
        pytest.fail('invalid scan timestamp must not issue a read')
    with pytest.raises(ValueError, match='scan'):
        await catalogue.read_delta(fetch, entry(captured), 'jobs', now=captured['read_ts'],
                                    start=captured['read_ts'], since_ts=since_ts)


def listing_row(captured, kind, number, created):
    row = job(captured, number, created=created, updated=captured['read_ts'] - 1)
    if kind == 'workflows':
        row = dict(captured[kind][0], **{key: row[key] for key in ('id', 'createdAt', 'updatedAt')})
    return row


@pytest.mark.parametrize('kind', ['jobs', 'workflows'])
@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('page_size', [2, 3])
async def test_hidden_boundary_tie_is_never_silently_skipped(captured, monkeypatch, kind, empty, page_size):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT' if kind == 'jobs' else 'PAGE_LIMIT', page_size)
    now = captured['read_ts']
    initial = catalogue.make_entry([] if empty else captured[kind], kind, now=now, read_ts=now, full_ts=now)
    before = copy.deepcopy(initial)
    # A tie just beyond the first page used to be excluded by the next cursor.
    ages = [10, 20, 20] if page_size == 2 else [10, 20, 30, 30, 40]
    records = [listing_row(captured, kind, index + 10, now - age) for index, age in enumerate(ages)]
    calls = []
    async def fetch(method, **kwargs):
        calls.append(kwargs)
        return [row for row in records if 'before' not in kwargs
                or work._ts(row['createdAt']) < work._ts(kwargs['before'])][:kwargs['limit']]
    if page_size == 2:
        # A full page containing only ties cannot prove that no more ties exist.
        with pytest.raises(ValueError, match='boundary'):
            await catalogue.read_delta(fetch, initial, kind, now=now, start=now)
    else:
        result = await catalogue.read_delta(fetch, initial, kind, now=now, start=now)
        assert {row['id'] for row in result['rows']} == {row['id'] for row in initial['rows']} | {row['id'] for row in records}
        assert result['watermark'] == work._ts(records[0]['updatedAt'])
    assert calls[1]['before'] == iso(work._ts(records[page_size - 1]['createdAt']) + .001)
    assert initial == before


@pytest.mark.parametrize('kind', ['jobs', 'workflows'])
async def test_boundary_overlap_handles_exact_cap_and_final_duplicate_probe(captured, monkeypatch, kind):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT' if kind == 'jobs' else 'PAGE_LIMIT', 2)
    monkeypatch.setattr(work, 'HISTORY_JOB_LIMIT' if kind == 'jobs' else 'WORKFLOW_LIMIT', 4)
    now = captured['read_ts']
    initial = catalogue.make_entry([], kind, now=now, read_ts=now, full_ts=now)
    records = [listing_row(captured, kind, index + 10, now - index * 10 - 10) for index in range(4)]
    calls = []
    async def fetch(method, **kwargs):
        calls.append(kwargs)
        return [row for row in records if 'before' not in kwargs
                or work._ts(row['createdAt']) < work._ts(kwargs['before'])][:kwargs['limit']]
    result = await catalogue.read_delta(fetch, initial, kind, now=now, start=now)
    assert len(calls) == 4
    assert len(result['rows']) == 4
    assert {row['id'] for row in result['rows']} == {row['id'] for row in records}


async def test_boundary_duplicate_does_not_replace_newer_revision(captured, monkeypatch):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT', 2)
    now = captured['read_ts']
    first = [job(captured, 10, created=now - 10, updated=now - 5),
             job(captured, 11, created=now - 20, updated=now - 1, state='executing')]
    pages = [first, [dict(first[-1], state='blocked', updatedAt=iso(now - 2))]]
    async def fetch(method, **kwargs):
        return pages.pop(0)
    result = await catalogue.read_delta(fetch, entry(captured), 'jobs', now=now, start=now)
    assert next(row for row in result['rows'] if row['id'] == first[-1]['id'])['state'] == 'executing'
    assert result['watermark'] == work._ts(first[-1]['updatedAt'])


@pytest.mark.parametrize('kind', ['jobs', 'workflows'])
async def test_repeated_full_page_does_not_certify_catalogue(captured, monkeypatch, kind):
    monkeypatch.setattr(work, 'SCAN_PAGE_LIMIT' if kind == 'jobs' else 'PAGE_LIMIT', 2)
    now = captured['read_ts']
    initial = entry(captured, kind); before = copy.deepcopy(initial)
    page = [listing_row(captured, kind, 10, now - 10), listing_row(captured, kind, 11, now - 20)]
    async def fetch(method, **kwargs):
        return page
    with pytest.raises(ValueError, match='cursor'):
        await catalogue.read_delta(fetch, initial, kind, now=now, start=now)
    assert initial == before


@pytest.mark.parametrize('stamp,expected', [(1791858930.999, '2026-10-13T02:35:31.000Z'),
                                           (1791858930.123, '2026-10-13T02:35:30.124Z')])
def test_cursor_after_preserves_millisecond_boundary(stamp, expected):
    assert catalogue.cursor_after(stamp) == expected
