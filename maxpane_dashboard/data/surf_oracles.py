"""Bounded oracle request facts; panel semantics belong to the shared RECORD decoder."""
from __future__ import annotations

import math

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_models import SURF_ORACLES_ROW_FIELDS, SURF_ROW_KEYS

PAGE_LIMIT, DETAIL_LIMIT, MEMBER_LIMIT = 100, 8, 64
DETAIL_TTL, MAX_AGE = 120, 86400
TERMINAL = frozenset({'attested', 'disagreed', 'blocked'})
SUMMARY_FIELDS = ('panel_answer_type', 'panel_answer_bool', 'panel_figure', 'agreed', 'quorum', 'panel_size')


def _stamp(value, now):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= now else None


def _row(raw, now):
    if not isinstance(raw, dict) or parse_job_id(raw.get('id')) is None:
        return None
    status = sw._oracle_text(raw.get('status'), 80, paragraphs=False)
    if not status:
        return None
    return dict(id=raw['id'], job_id=parse_job_id(raw.get('jobId')), status=status,
                chain_id=raw.get('chainId') if type(raw.get('chainId')) is int and raw['chainId'] > 0 else None,
                question=sw._oracle_text(raw.get('question'), 1000),
                created_ts=_stamp(sw._ts(raw.get('createdAt')), now),
                updated_ts=_stamp(sw._ts(raw.get('updatedAt')), now))


def decode_page(raw, *, now):
    if not isinstance(raw, list):
        raise ValueError('oracle list unavailable')
    rows, seen, partial = [], set(), len(raw) >= PAGE_LIMIT
    for value in raw[:PAGE_LIMIT]:
        row = _row(value, now)
        if row is None or row['id'] in seen:
            partial = True
            continue
        rows.append(row); seen.add(row['id'])
    if raw and not rows:
        raise ValueError('nonempty oracle page has no valid rows')
    rows.sort(key=lambda row: row['created_ts'] or 0, reverse=True)
    return rows, partial


def version(row):
    return [row['status'], row['updated_ts']]


def decode_detail(raw, row, *, read_ts, now=None):
    """Extract canonical points once per exact hash; never retain the raw envelope."""
    if (not isinstance(raw, dict) or raw.get('id') != row['id']
            or raw.get('jobId') != row['job_id']):
        return None
    header = _row(raw, read_ts if now is None else now)
    served = raw.get('members')
    if served is None and raw.get('status') == 'blocked':
        served = []
    if header is None or not isinstance(served, list):
        return None
    members = [member for member in served if isinstance(member, dict)]
    raw = dict(raw, members=members, chainId=header['chain_id'])
    # An absent hash obtains panel-level facts through the same strict decoder.
    hashes = {member.get('submissionHash') for member in members if isinstance(member.get('submissionHash'), str)}
    absent = 0
    while f'{absent:064x}' in hashes:
        absent += 1
    sample = sw.oracle_point(raw, row['job_id'], f'{absent:064x}', now_ts=read_ts)
    if sample is None:
        return None
    extracted, seen = [], set()
    truncated = len(served) > MEMBER_LIMIT or len(served) != len(members)
    for member in members:
        key = member.get('submissionHash')
        if not isinstance(key, str) or key in seen:
            truncated = True
            continue
        seen.add(key)
        if len(extracted) >= MEMBER_LIMIT:
            break
        point = sw.oracle_point(raw, row['job_id'], key, now_ts=read_ts)
        if point is None or not point['on_panel']:
            truncated = True
            continue
        extracted.append(dict(hash=key, seat=sw.parse_seat_token(member.get('tokenId')), point=point))
    summary = dict(zip(SUMMARY_FIELDS, (sample['answer_type'], sample['answer_bool'], sample['figure'],
                                      sample['agreed'], sample['quorum'], sample['panel_size'])))
    return dict(row=header, version=version(row), read_ts=read_ts, access_ts=read_ts,
                summary=summary, member_count=len(served), members=extracted, truncated=truncated)


def project_detail(entry):
    row = entry['row']
    rows, points = [], {}
    for member in entry['members']:
        item = dict.fromkeys(SURF_ROW_KEYS['swarm_seat_work_rows'])
        item.update(job_id=row['job_id'], node_key='oracle_assess',
                    submission_hash=member['hash'], seat=member['seat'])
        rows.append(item); points[member['hash']] = member['point']
    members = sw.enrich_panel_rows(rows, {row['job_id']: points}, sw.SWARM_ORACLE_NODE_KEYS)
    return {**{key: row[key] for key in ('id', 'job_id', 'status', 'chain_id', 'question')},
            **entry['summary'], 'member_count': entry['member_count'],
            'members': members, 'truncated': entry['truncated']}


def _valid_row(row, now):
    return (isinstance(row, dict) and set(row) == set(SURF_ORACLES_ROW_FIELDS)
            and parse_job_id(row['id']) is not None
            and (row['job_id'] is None or parse_job_id(row['job_id']) is not None)
            and isinstance(row['status'], str) and bool(row['status'])
            and sw._oracle_text(row['status'], 80, paragraphs=False) == row['status']
            and (row['chain_id'] is None or type(row['chain_id']) is int and row['chain_id'] > 0)
            and (row['question'] is None or isinstance(row['question'], str)
                 and sw._oracle_text(row['question'], 1000) == row['question'])
            and all(row[key] is None or _stamp(row[key], now) is not None
                    for key in ('created_ts', 'updated_ts')))


def _coerce_detail(entry, identity, now):
    fields = {'row', 'version', 'read_ts', 'access_ts', 'summary', 'member_count', 'members', 'truncated'}
    if (not isinstance(entry, dict) or set(entry) != fields or not _valid_row(entry['row'], now)
            or entry['row']['id'] != identity or entry['row']['job_id'] is None
            or _stamp(entry['read_ts'], now) is None
            or _stamp(entry['access_ts'], now) is None or type(entry['truncated']) is not bool
            or type(entry['member_count']) is not int or entry['member_count'] < 0
            or not isinstance(entry['members'], list) or len(entry['members']) > MEMBER_LIMIT):
        return None
    basis = entry['version']
    if (not isinstance(basis, list) or len(basis) != 2 or not isinstance(basis[0], str)
            or not basis[0] or basis[1] is not None and _stamp(basis[1], now) is None):
        return None
    summary = entry['summary']
    if (not isinstance(summary, dict) or set(summary) != set(SUMMARY_FIELDS)
            or summary['panel_answer_type'] is not None and not isinstance(summary['panel_answer_type'], str)
            or summary['panel_answer_bool'] is not None and type(summary['panel_answer_bool']) is not bool
            or summary['panel_figure'] is not None and sw._oracle_figure(summary['panel_figure']) is None
            or any(summary[k] is not None and sw._oracle_count(summary[k]) is None
                   for k in ('agreed', 'quorum', 'panel_size'))):
        return None
    members, seen = [], set()
    for member in entry['members']:
        if not isinstance(member, dict) or set(member) != {'hash', 'seat', 'point'}:
            continue
        key, point, seat = member['hash'], member['point'], member['seat']
        if (not isinstance(key, str) or key in seen or seat is not None
                and (type(seat) is not int or sw.parse_seat_token(seat) is None)):
            continue
        job = entry['row']['job_id']
        valid = sw.coerce_oracle_slot({job: {key: point}}) or {}
        if (key not in valid.get(job, {}) or point['request_id'] != identity
                or point['status'] != entry['row']['status'] or not point['on_panel']
                or point['read_ts'] != entry['read_ts']):
            continue
        members.append(member); seen.add(key)
    if entry['member_count'] < len(members):
        return None
    return dict(entry, members=members, truncated=entry['truncated'] or len(members) != len(entry['members']))


def coerce_snapshot(payload, *, now):
    if (not isinstance(payload, dict) or set(payload) != {'read_ts', 'rows', 'partial', 'details'}
            or type(payload['partial']) is not bool or not isinstance(payload['details'], dict)
            or payload['read_ts'] is not None and _stamp(payload['read_ts'], now) is None
            or payload['rows'] is not None and not isinstance(payload['rows'], list)):
        return None
    rows, partial = None, payload['partial']
    if payload['rows'] is not None:
        rows, seen = [], set()
        for row in payload['rows'][:PAGE_LIMIT]:
            if not _valid_row(row, now) or row['id'] in seen:
                partial = True
                continue
            rows.append(row); seen.add(row['id'])
        partial |= len(payload['rows']) > PAGE_LIMIT
        if payload['rows'] and not rows or payload['read_ts'] is None:
            return None
    details = {}
    for identity, entry in payload['details'].items():
        clean = _coerce_detail(entry, identity, now)
        if clean is not None:
            details[identity] = clean
    details = dict(sorted(details.items(), key=lambda pair: pair[1]['access_ts'], reverse=True)[:DETAIL_LIMIT])
    return dict(read_ts=payload['read_ts'], rows=rows, partial=partial, details=details)


def empty_snapshot():
    return dict(read_ts=None, rows=None, partial=False, details={})
