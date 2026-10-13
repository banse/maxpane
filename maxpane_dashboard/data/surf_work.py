"""Pure bounded current-work snapshot, separate from historical job folds."""
from __future__ import annotations

import math

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_launch_checks import integer
from maxpane_dashboard.data.surf_swarm import _ts, clean_reply, parse_seat_token
from maxpane_dashboard.data.surf_models import (
    SURF_WORK_JOB_FIELDS as JOB_FIELDS, SURF_WORK_NODE_FIELDS as NODE_FIELDS,
    SURF_WORK_WORKFLOW_FIELDS as WORKFLOW_FIELDS, SURF_WORK_SUMMARY_KEYS as SUMMARY_KEYS,
)

PAGE_LIMIT = 100
DETAIL_LIMIT = 24
NODE_LIMIT = 200
TERMINAL = frozenset({'completed', 'cancelled', 'superseded', 'failed'})


def _stamp(value, now):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 < value <= now else None


def _text(value, cap=4000):
    return clean_reply(value, cap=cap)


def _node(raw, now):
    if not isinstance(raw, dict) or not _text(raw.get('key'), 200) or not _text(raw.get('state'), 80):
        return None
    seat = raw.get('seat') if isinstance(raw.get('seat'), dict) else {}
    dependencies = raw.get('dependsOn')
    verdict = raw.get('verdict')
    return dict(key=_text(raw['key'], 200), role=_text(raw.get('role'), 80),
                state=_text(raw['state'], 80), seat=parse_seat_token(seat.get('tokenId')),
                agent_id=_text(seat.get('agentId'), 200), attempt=integer(raw.get('attempt')),
                revisions=integer(raw.get('revisions')),
                depends_on=[_text(x, 200) for x in dependencies] if isinstance(dependencies, list)
                and len(dependencies) <= NODE_LIMIT and all(_text(x, 200) for x in dependencies) else None,
                updated_ts=_stamp(_ts(raw.get('updatedAt')), now),
                dispatch_note=_text(raw.get('dispatchNote')), dispatch_ts=_stamp(_ts(raw.get('dispatchNoteAt')), now),
                failure=_text(raw.get('failureReason')),
                verdict={'status': _text(verdict.get('status'), 80), 'detail': _text(verdict.get('detail'))}
                if isinstance(verdict, dict) else None)


def _job(raw, now, *, detail=False):
    if not isinstance(raw, dict) or parse_job_id(raw.get('id')) is None or not _text(raw.get('state'), 80):
        return None
    nodes = None
    if detail and isinstance(raw.get('nodes'), list) and len(raw['nodes']) <= NODE_LIMIT:
        parsed = [_node(node, now) for node in raw['nodes']]
        if all(node is not None for node in parsed) and len({node['key'] for node in parsed}) == len(parsed):
            nodes = parsed
    return dict(id=raw['id'], state=_text(raw['state'], 80), template=_text(raw.get('template'), 200),
                objective=_text(raw.get('objective')), created_ts=_stamp(_ts(raw.get('createdAt')), now),
                updated_ts=_stamp(_ts(raw.get('updatedAt')), now), blocked_reason=_text(raw.get('blockedReason')),
                detail_state=('ok' if nodes is not None else 'unavailable') if detail else 'not_loaded', nodes=nodes)


def _workflow(raw, now):
    if not isinstance(raw, dict) or parse_job_id(raw.get('id')) is None or not _text(raw.get('status'), 80):
        return None
    return dict(id=raw['id'], status=_text(raw['status'], 80), objective=_text(raw.get('objective')),
                failure=_text(raw.get('failure')), contracts_job_id=parse_job_id(raw.get('contractsJobId')),
                frontend_job_id=parse_job_id(raw.get('frontendJobId')),
                created_ts=_stamp(_ts(raw.get('createdAt')), now), updated_ts=_stamp(_ts(raw.get('updatedAt')), now),
                waiting_for_hosting=raw.get('waitingForHosting') if type(raw.get('waitingForHosting')) is bool else None)


def _page(raw, decoder, now):
    rows, seen = [], set()
    partial = len(raw) >= PAGE_LIMIT
    for value in raw[:PAGE_LIMIT]:
        row = decoder(value, now)
        if row is None or row['id'] in seen:
            partial = True
            continue
        rows.append(row); seen.add(row['id'])
    return rows, partial


def detail_ids(jobs, workflows):
    """Current executing jobs first, unfinished workflow links next, blocked last."""
    ids = [j['id'] for j in jobs if j['state'] == 'executing']
    for blocked in (False, True):
        for row in workflows:
            if row['status'] not in TERMINAL and (row['status'] == 'blocked') == blocked:
                ids.extend(row[key] for key in ('contracts_job_id', 'frontend_job_id') if row[key])
    ids.extend(j['id'] for j in jobs if j['state'] == 'blocked')
    return list(dict.fromkeys(ids))


def decode_pages(jobs, workflows, *, now):
    job_rows, job_partial = _page(jobs, _job, now)
    workflow_rows, workflow_partial = _page(workflows, _workflow, now)
    return job_rows, workflow_rows, job_partial or workflow_partial


def snapshot(jobs, workflows, details, *, read_ts, now=None):
    """One coherent read; successful linked details extend only this recent page."""
    now = read_ts if now is None else now
    job_rows, workflow_rows, partial = decode_pages(jobs, workflows, now=now)
    expected = detail_ids(job_rows, workflow_rows)
    rows = {row['id']: row for row in job_rows}
    loaded = 0
    for identity, raw in list(details.items())[:DETAIL_LIMIT]:
        row = _job(raw, now, detail=True)
        if row is not None and row['id'] == identity:
            rows[identity] = row
            loaded += row['detail_state'] == 'ok'
        else:
            partial = True
            if identity in rows:
                rows[identity]['detail_state'] = 'unavailable'
    partial |= any(rows.get(identity, {}).get('detail_state') != 'ok' for identity in expected)
    return dict(read_ts=read_ts, partial=bool(partial), jobs_loaded=len(job_rows), jobs=list(rows.values()), workflows=workflow_rows,
                details_expected=len(expected), details_loaded=loaded)


def _valid_row(row, fields, now):
    if not isinstance(row, dict) or set(row) != set(fields):
        return False
    for key, value in row.items():
        if key in ('id', 'contracts_job_id', 'frontend_job_id'):
            if (value is not None or key == 'id') and parse_job_id(value) is None: return False
        elif key.endswith('_ts'):
            if value is not None and _stamp(value, now) is None: return False
        elif key in ('seat', 'attempt', 'revisions'):
            if value is not None and integer(value) is None: return False
        elif key == 'waiting_for_hosting':
            if value is not None and type(value) is not bool: return False
        elif key == 'depends_on':
            if value is not None and (not isinstance(value, list) or len(value) > NODE_LIMIT
                                     or any(not isinstance(x, str) or not x or _text(x, 200) != x for x in value)): return False
        elif key == 'verdict':
            if value is not None and not _valid_row(value, ('status', 'detail'), now): return False
        elif key == 'nodes':
            if value is not None and (not isinstance(value, list) or len(value) > NODE_LIMIT
                                     or any(not _valid_row(x, NODE_FIELDS, now) for x in value)): return False
            if isinstance(value, list) and len({x['key'] for x in value}) != len(value): return False
        elif value is not None and (not isinstance(value, str) or _text(value) != value):
            return False
    return True


def coerce_snapshot(raw, *, now):
    """Reject corrupt persisted evidence rather than turning missing facts into zero."""
    if not isinstance(raw, dict) or _stamp(raw.get('read_ts'), now) is None or type(raw.get('partial')) is not bool:
        return None
    if any(integer(raw.get(k)) is None for k in ('jobs_loaded', 'details_expected', 'details_loaded')):
        return None
    for name, fields, cap in (('jobs', JOB_FIELDS, PAGE_LIMIT + DETAIL_LIMIT), ('workflows', WORKFLOW_FIELDS, PAGE_LIMIT)):
        rows = raw.get(name)
        if not isinstance(rows, list) or len(rows) > cap or any(not _valid_row(row, fields, now) for row in rows):
            return None
        if len({row['id'] for row in rows}) != len(rows): return None
    if not max(0, len(raw['jobs']) - DETAIL_LIMIT) <= raw['jobs_loaded'] <= min(PAGE_LIMIT, len(raw['jobs'])):
        return None
    for job in raw['jobs']:
        if not job['state'] or job['detail_state'] not in ('ok', 'unavailable', 'not_loaded'): return None
        if (job['detail_state'] == 'ok') != isinstance(job['nodes'], list): return None
        if any(not node['state'] or not node['key'] for node in job['nodes'] or []): return None
    if any(not row['status'] for row in raw['workflows']): return None
    if raw['details_loaded'] != sum(row['detail_state'] == 'ok' for row in raw['jobs']): return None
    if raw['details_loaded'] > DETAIL_LIMIT or raw['details_expected'] > PAGE_LIMIT * 3: return None
    return {key: raw[key] for key in ('read_ts', 'partial', 'jobs_loaded', 'jobs', 'workflows', 'details_expected', 'details_loaded')}


def project(raw, *, now, failed=False):
    slot = coerce_snapshot(raw, now=now)
    result = dict(state='unavailable', read_ts=None, now_ts=now, partial=False,
                  jobs_loaded=None, workflows_loaded=None, details_loaded=None, details_expected=None,
                  summary=dict.fromkeys(SUMMARY_KEYS), jobs=None, workflows=None)
    if slot is None:
        return result
    jobs, workflows = slot['jobs'], slot['workflows']
    executing = [job for job in jobs if job['state'] == 'executing']
    nodes = [node for job in executing for node in job['nodes'] or [] if node['state'] == 'working']
    missing = any(job['nodes'] is None for job in executing)
    roles_unknown = any(node['role'] not in ('implement', 'integrate', 'test', 'tests', 'review') for node in nodes)
    summary = dict(jobs=len(executing), workflows=sum(w['status'] not in TERMINAL | {'blocked'} for w in workflows),
                   seats=None if missing or any(n['seat'] is None for n in nodes) else len({n['seat'] for n in nodes}),
                   build=None if missing or roles_unknown else sum(n['role'] != 'review' for n in nodes),
                   review=None if missing or roles_unknown else sum(n['role'] == 'review' for n in nodes),
                   blocked=sum(j['state'] == 'blocked' for j in jobs))
    result.update(slot, state='stale' if failed or now - slot['read_ts'] > 120 else 'ok',
                  workflows_loaded=len(workflows), summary=summary,
                  partial=slot['partial'] or any(value is None for value in summary.values()))
    return result
