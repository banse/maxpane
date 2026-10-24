"""Private WIP catalogue checkpoints and atomic, bounded update deltas."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from maxpane_dashboard.data import surf_work as work

DELTA_OVERLAP_SECONDS = 300
RECONCILE_SECONDS = 600
_ENTRY_FIELDS = {'rows', 'watermark', 'full_ts', 'read_ts'}
_JOB_NAMES = {'created_ts': 'createdAt', 'updated_ts': 'updatedAt', 'blocked_reason': 'blockedReason'}
_FLOW_NAMES = {'created_ts': 'createdAt', 'updated_ts': 'updatedAt', 'contracts_job_id': 'contractsJobId',
               'frontend_job_id': 'frontendJobId', 'waiting_for_hosting': 'waitingForHosting'}


def _iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def cursor_after(stamp):
    """Overlap the boundary of an exclusive millisecond ``createdAt`` cursor."""
    cursor = datetime.fromtimestamp(stamp, timezone.utc) + timedelta(milliseconds=1)
    return cursor.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _settings(kind):
    if kind == 'jobs':
        return work._job, work.JOB_FIELDS, work.HISTORY_JOB_LIMIT
    if kind == 'workflows':
        return work._workflow, work.WORKFLOW_FIELDS, work.WORKFLOW_LIMIT
    raise ValueError('unknown catalogue source')


def _coerce_entry(raw, kind, now):
    _, fields, cap = _settings(kind)
    if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
        return None
    if any(work._stamp(raw[key], now) is None for key in ('read_ts', 'full_ts')):
        return None
    if raw['full_ts'] > raw['read_ts']:
        return None
    rows, watermark = raw['rows'], raw['watermark']
    if not isinstance(rows, list) or len(rows) > cap:
        return None
    if watermark is not None and work._stamp(watermark, now) is None:
        return None
    if rows and watermark is None:
        return None
    seen = set()
    for row in rows:
        if (not work._valid_row(row, fields, now) or row['id'] in seen
                or row['created_ts'] is None or row['updated_ts'] is None
                or row['created_ts'] > row['updated_ts'] or row['updated_ts'] > watermark
                or not row['state' if kind == 'jobs' else 'status']):
            return None
        if kind == 'jobs' and (row['nodes'] is not None or row['detail_state'] != 'not_loaded'):
            return None
        seen.add(row['id'])
    return dict(raw, rows=[dict(row) for row in rows])


def coerce_catalogue(raw, *, now):
    """Bad private checkpoints cannot invalidate their sibling or display data."""
    source = raw if isinstance(raw, dict) else {}
    return {kind: _coerce_entry(source.get(kind), kind, now) for kind in ('jobs', 'workflows')}


def source_rows(entry, kind):
    """Recreate only the allowlisted API fields needed by the existing collector."""
    names = _JOB_NAMES if kind == 'jobs' else _FLOW_NAMES
    return [{names.get(key, key): _iso(value) if key.endswith('_ts') and value is not None else value
             for key, value in row.items() if key not in ('nodes', 'detail_state')}
            for row in entry['rows']]


def _decode(raw_rows, kind, now):
    decoder, _, cap = _settings(kind)
    if not isinstance(raw_rows, list) or len(raw_rows) > cap:
        return None
    rows, seen = [], set()
    for raw in raw_rows:
        row = decoder(raw, now)
        if (row is None or row['id'] in seen or row['created_ts'] is None or row['updated_ts'] is None
                or row['created_ts'] > row['updated_ts']):
            return None
        if kind == 'workflows' and any(raw.get(key) is not None and work.parse_job_id(raw[key]) is None
                                       for key in ('contractsJobId', 'frontendJobId')):
            return None
        rows.append(row); seen.add(row['id'])
    return rows


def make_entry(raw_rows, kind, *, now, read_ts, full_ts, watermark=None):
    """A caller certifies listing coverage; never derive its watermark from details."""
    rows = _decode(raw_rows, kind, now)
    if rows is None or watermark is not None and work._stamp(watermark, now) is None:
        return None
    points = [row['updated_ts'] for row in rows]
    if watermark is not None:
        points.append(watermark)
    watermark = max(points, default=None)
    if kind == 'jobs':
        rows = [row for row in rows if row['state'] not in work.TERMINAL
                or work.recent_activity(row, now, work.HISTORY_SECONDS)]
    rows.sort(key=lambda row: (row['created_ts'], row['id']), reverse=True)
    return _coerce_entry(dict(rows=rows, watermark=watermark, full_ts=full_ts, read_ts=read_ts), kind, now)


async def read_delta(fetch, entry, kind, *, now, start, since_ts=None):
    """Return a complete merged checkpoint, or raise without changing the prior one.

    ``now`` may be an injected clock so revisions created during paging are valid.
    A certified empty catalogue has no watermark and uses a bounded unfiltered read.
    ``since_ts`` widens catch-up to the start of a scan spanning multiple cycles.
    """
    clock = now if callable(now) else lambda: now
    previous = _coerce_entry(entry, kind, clock())
    if previous is None:
        raise ValueError('invalid catalogue checkpoint')
    if since_ts is not None and work._stamp(since_ts, clock()) is None:
        raise ValueError('invalid catalogue scan start')
    limit = work.SCAN_PAGE_LIMIT if kind == 'jobs' else work.PAGE_LIMIT
    # Each subsequent full page spends one slot checking the prior boundary.
    page_budget = work.SCAN_PAGES if kind == 'jobs' else work.WORKFLOW_LIMIT // max(1, limit - 1) + 1
    _, _, cap = _settings(kind)
    anchor = previous['watermark']
    if since_ts is not None:
        anchor = min(anchor, since_ts) if anchor is not None else since_ts
    cutoff = max(0.001, anchor - DELTA_OVERLAP_SECONDS) if anchor is not None else None
    params = {'limit': limit}
    if cutoff is not None:
        params['since'] = _iso(cutoff)
        cutoff = work._ts(params['since'])
    updates, boundary = {}, None
    for _ in range(page_budget):
        page = await fetch('fetch_' + kind, **params)
        rows = _decode(page, kind, clock())
        if rows is None or len(rows) > limit:
            raise ValueError('invalid catalogue delta page')
        stamps = [row['created_ts'] for row in rows]
        if (stamps != sorted(stamps, reverse=True) or boundary is not None and any(stamp > boundary for stamp in stamps)
                or any(row['id'] in updates and (row['created_ts'] != boundary
                       or updates[row['id']]['created_ts'] != boundary) for row in rows)
                or cutoff is not None and any(row['updated_ts'] < cutoff for row in rows)):
            raise ValueError('catalogue delta cursor or update filter violated')
        for row in rows:
            if row['id'] not in updates or row['updated_ts'] >= updates[row['id']]['updated_ts']:
                updates[row['id']] = row
        if len(updates) > cap:
            raise ValueError('catalogue delta row budget exceeded')
        if len(rows) < limit:
            break
        if stamps.count(stamps[-1]) > 1 or boundary is not None and stamps[-1] >= boundary:
            raise ValueError('ambiguous catalogue page boundary')
        boundary = stamps[-1]
        params['before'] = cursor_after(boundary)
    else:
        raise ValueError('catalogue delta page budget exceeded')
    merged = {row['id']: row for row in previous['rows']}
    for identity, row in updates.items():
        if identity not in merged or row['updated_ts'] >= merged[identity]['updated_ts']:
            merged[identity] = row
    points = [row['updated_ts'] for row in updates.values()]
    if previous['watermark'] is not None:
        points.append(previous['watermark'])
    result = make_entry(source_rows({'rows': list(merged.values())}, kind), kind, now=clock(), read_ts=start,
                        full_ts=previous['full_ts'], watermark=max(points, default=None))
    if result is None:
        raise ValueError('invalid merged catalogue checkpoint')
    return result
