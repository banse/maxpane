"""Pure bounded current-work snapshot, separate from historical job folds."""
from __future__ import annotations

import math

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_launch_checks import integer
from maxpane_dashboard.data.surf_swarm import _ts, clean_reply, parse_seat_token
from maxpane_dashboard.data.surf_models import (
    SURF_WORK_JOB_FIELDS as JOB_FIELDS, SURF_WORK_NODE_FIELDS as NODE_FIELDS,
    SURF_WORK_PROJECT_FIELDS as PROJECT_FIELDS, SURF_WORK_FIELDS,
    SURF_WORK_WORKFLOW_FIELDS as WORKFLOW_FIELDS, SURF_WORK_SUMMARY_KEYS as SUMMARY_KEYS,
)

PAGE_LIMIT = 100
DETAIL_LIMIT = 24  # Optional background enrichment only.
SCAN_PAGE_LIMIT = 500
SCAN_PAGES = 100
CONTEXT_DETAIL_LIMIT = 512
WORKFLOW_DETAIL_LIMIT = 128
VERSION_LIMIT = 256
CONTEXT_JOB_LIMIT = 4096
JOB_LIMIT = PAGE_LIMIT * 3 + CONTEXT_JOB_LIMIT + CONTEXT_DETAIL_LIMIT
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


def _page(raw, decoder, now, limit=PAGE_LIMIT):
    rows, seen = [], set()
    partial = len(raw) >= limit
    for value in raw[:limit]:
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


def project_context(raw, *, active_only=True):
    """Only a fresh active detail can authorize one bounded project membership."""
    if not isinstance(raw, dict) or (active_only and raw.get('state') != 'executing'):
        return None
    project = raw.get('project')
    if not isinstance(project, dict) or parse_job_id(project.get('id')) is None:
        return None
    versions = project.get('versions')
    if not isinstance(versions, list) or not 1 <= len(versions) <= VERSION_LIMIT:
        return None
    ids, workflows = [], []
    for version in versions:
        if not isinstance(version, dict) or parse_job_id(version.get('jobId')) is None:
            return None
        identity, workflow = version['jobId'], version.get('workflowId')
        if identity in ids or (workflow is not None and parse_job_id(workflow) is None):
            return None
        ids.append(identity)
        if workflow is not None and workflow not in workflows: workflows.append(workflow)
    if raw.get('id') not in ids:
        return None
    for key in ('head', 'running'):
        if project.get(key) is not None and project[key] not in ids: return None
    parent = raw.get('parentJobId')
    if parent is not None and (parent not in ids or parent == raw['id']): return None
    return dict(id=project['id'], objective=_text(versions[0].get('objective')) or _text(raw.get('objective')),
                job_ids=ids, workflow_ids=workflows, active_job_ids=[raw['id']]), versions


def workflow_context(raw, identity, members, *, now):
    """Direct workflow responses use nested jobs; require the referring members."""
    if not isinstance(raw, dict) or raw.get('id') != identity:
        return None
    normalized = dict(raw)
    for name in ('contracts', 'frontend'):
        nested, flat = raw.get(name), raw.get(name + 'JobId')
        if nested is not None:
            if not isinstance(nested, dict) or parse_job_id(nested.get('id')) is None: return None
            if flat is not None and flat != nested['id']: return None
            normalized[name + 'JobId'] = nested['id']
        elif flat is not None and parse_job_id(flat) is None: return None
    row = _workflow(normalized, now)
    linked = [row[k] for k in ('contracts_job_id', 'frontend_job_id') if row and row[k]]
    if row is None or len(set(linked)) != len(linked) or not set(members) <= set(linked):
        return None
    return normalized


def snapshot(jobs, workflows, details, *, read_ts, now=None, projects=None, metadata=None,
             expected_ids=None, active_scan_complete=True, coverage_partial=False,
             context_job_ids=(), context_workflow_ids=()):
    """Current evidence and historical context share rows, but never count scopes."""
    now = read_ts if now is None else now
    job_rows, job_partial = _page(jobs, _job, now, JOB_LIMIT)
    workflow_rows, flow_partial = _page(workflows, _workflow, now, PAGE_LIMIT + WORKFLOW_DETAIL_LIMIT)
    # Legacy callers still describe a single recent page.
    partial = coverage_partial or job_partial or flow_partial
    if expected_ids is None: partial |= len(jobs) >= PAGE_LIMIT or len(workflows) >= PAGE_LIMIT
    projects = projects or []
    expected = list(dict.fromkeys(expected_ids if expected_ids is not None else detail_ids(job_rows, workflow_rows)))
    rows = {row['id']: row for row in job_rows}
    current = set(rows)
    for identity, raw in (metadata or {}).items():
        row = _job(dict(raw, id=identity), now)
        if row is not None and identity not in rows:
            row['detail_state'] = 'unavailable'; rows[identity] = row
    for identity, raw in list(details.items())[:CONTEXT_DETAIL_LIMIT + DETAIL_LIMIT]:
        row = _job(raw, now, detail=True)
        if row is not None and row['id'] == identity:
            rows[identity] = row
            if row['state'] == 'executing' or identity not in (metadata or {}): current.add(identity)
        else:
            partial = True
            if identity in rows: rows[identity]['detail_state'] = 'unavailable'
    context_jobs = set(context_job_ids) | {identity for p in projects for identity in p['job_ids']}
    current -= {identity for identity in context_jobs
                if not (isinstance(details.get(identity), dict) and details[identity].get('id') == identity
                        and details[identity].get('state') == 'executing')}
    context_flows = set(context_workflow_ids) | {identity for p in projects for identity in p['workflow_ids']}
    current_flows = [w['id'] for w in workflow_rows if w['id'] not in context_flows or
                     any(rows.get(w[k], {}).get('state') == 'executing' and w[k] in current
                         for k in ('contracts_job_id', 'frontend_job_id'))]
    partial |= not active_scan_complete or any(rows.get(identity, {}).get('detail_state') != 'ok' for identity in expected)
    return dict(read_ts=read_ts, partial=bool(partial), jobs_loaded=len(job_rows), jobs=list(rows.values()),
                workflows=workflow_rows, projects=projects, current_job_ids=[i for i in rows if i in current],
                current_workflow_ids=current_flows, active_scan_complete=active_scan_complete,
                context_job_ids=sorted(context_jobs), context_workflow_ids=sorted(context_flows),
                details_expected=len(expected), details_loaded=sum(r['detail_state'] == 'ok' for r in rows.values()))


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


def _ids(value, cap):
    return (isinstance(value, list) and len(value) <= cap and all(parse_job_id(x) is not None for x in value)
            and len(set(value)) == len(value))


def coerce_snapshot(raw, *, now):
    """Validate persisted scopes and migrate pre-project snapshots without a reset."""
    if not isinstance(raw, dict) or _stamp(raw.get('read_ts'), now) is None or type(raw.get('partial')) is not bool:
        return None
    raw = dict(raw)
    legacy = 'projects' not in raw
    if any(integer(raw.get(k)) is None for k in ('jobs_loaded', 'details_expected', 'details_loaded')):
        return None
    for name, fields, cap in (('jobs', JOB_FIELDS, JOB_LIMIT), ('workflows', WORKFLOW_FIELDS, PAGE_LIMIT + WORKFLOW_DETAIL_LIMIT)):
        rows = raw.get(name)
        if not isinstance(rows, list) or len(rows) > cap or any(not _valid_row(row, fields, now) for row in rows): return None
        if len({row['id'] for row in rows}) != len(rows): return None
    jobs, flows = {j['id']: j for j in raw['jobs']}, {w['id']: w for w in raw['workflows']}
    if not 0 <= raw['jobs_loaded'] <= min(len(jobs), PAGE_LIMIT + CONTEXT_DETAIL_LIMIT): return None
    for job in jobs.values():
        if not job['state'] or job['detail_state'] not in ('ok', 'unavailable', 'not_loaded'): return None
        if (job['detail_state'] == 'ok') != isinstance(job['nodes'], list): return None
        if any(not node['state'] or not node['key'] for node in job['nodes'] or []): return None
    if any(not row['status'] for row in flows.values()): return None
    if raw['details_loaded'] != sum(row['detail_state'] == 'ok' for row in jobs.values()): return None
    if raw['details_loaded'] > min(CONTEXT_DETAIL_LIMIT + DETAIL_LIMIT, raw['details_expected']) or raw['details_expected'] > JOB_LIMIT: return None
    if legacy:
        raw.update(projects=[], current_job_ids=list(jobs), current_workflow_ids=list(flows),
                   context_job_ids=[], context_workflow_ids=[], active_scan_complete=False, partial=True)
    if type(raw.get('active_scan_complete')) is not bool: return None
    for name, values in (('current_job_ids', jobs), ('current_workflow_ids', flows)):
        if not _ids(raw.get(name), len(values)) or not set(raw[name]) <= values.keys(): return None
    if not _ids(raw.get('context_job_ids'), CONTEXT_JOB_LIMIT) or not _ids(raw.get('context_workflow_ids'), CONTEXT_JOB_LIMIT + CONTEXT_DETAIL_LIMIT): return None
    if any(jobs[i]['state'] != 'executing' for i in set(raw['context_job_ids']) & set(raw['current_job_ids'])): return None
    for identity in set(raw['context_workflow_ids']) & set(raw['current_workflow_ids']):
        if not any(flows[identity][k] in raw['current_job_ids'] and jobs[flows[identity][k]]['state'] == 'executing'
                   for k in ('contracts_job_id', 'frontend_job_id')): return None
    projects = raw['projects']
    if not isinstance(projects, list) or len(projects) > CONTEXT_DETAIL_LIMIT: return None
    seen, owned = set(), set()
    for p in projects:
        if not isinstance(p, dict) or set(p) != set(PROJECT_FIELDS) or parse_job_id(p.get('id')) is None: return None
        if p['id'] in seen or (p['objective'] is not None and (not isinstance(p['objective'], str) or _text(p['objective']) != p['objective'])): return None
        if not _ids(p['job_ids'], VERSION_LIMIT + WORKFLOW_DETAIL_LIMIT * 2) or not _ids(p['workflow_ids'], VERSION_LIMIT * 2): return None
        if not p['job_ids'] or not _ids(p['active_job_ids'], CONTEXT_DETAIL_LIMIT) or not p['active_job_ids']: return None
        if not set(p['active_job_ids']) <= set(p['job_ids']) or owned.intersection(p['job_ids']): return None
        if not set(p['job_ids']) <= set(raw['context_job_ids']) or not set(p['workflow_ids']) <= set(raw['context_workflow_ids']): return None
        if any(i not in jobs or jobs[i]['state'] != 'executing' or i not in raw['current_job_ids'] for i in p['active_job_ids']): return None
        if any(w in flows and not {flows[w][k] for k in ('contracts_job_id', 'frontend_job_id') if flows[w][k]} <= set(p['job_ids']) for w in p['workflow_ids']): return None
        seen.add(p['id']); owned.update(p['job_ids'])
    if len(owned) > CONTEXT_JOB_LIMIT: return None
    if not raw['partial'] and (not raw['active_scan_complete'] or any(i not in jobs for i in owned)
                              or any(w not in flows for p in projects for w in p['workflow_ids'])): return None
    keys = ('read_ts', 'partial', 'jobs_loaded', 'jobs', 'workflows', 'projects', 'details_expected', 'details_loaded',
            'current_job_ids', 'current_workflow_ids', 'context_job_ids', 'context_workflow_ids', 'active_scan_complete')
    return {key: raw[key] for key in keys}


def project(raw, *, now, failed=False):
    slot = coerce_snapshot(raw, now=now)
    result = dict(state='unavailable', read_ts=None, now_ts=now, partial=False,
                  jobs_loaded=None, workflows_loaded=None, details_loaded=None, details_expected=None,
                  summary=dict.fromkeys(SUMMARY_KEYS), jobs=None, workflows=None, projects=None)
    if slot is None:
        return result
    jobs = [j for j in slot['jobs'] if j['id'] in slot['current_job_ids']]
    workflows = [w for w in slot['workflows'] if w['id'] in slot['current_workflow_ids']]
    executing = [job for job in jobs if job['state'] == 'executing']
    nodes = [node for job in executing for node in job['nodes'] or [] if node['state'] == 'working']
    missing = not slot['active_scan_complete'] or any(job['nodes'] is None for job in executing)
    roles_unknown = any(node['role'] not in ('implement', 'integrate', 'test', 'tests', 'review') for node in nodes)
    summary = dict(jobs=len(executing) if executing or slot['active_scan_complete'] else None,
                   workflows=sum(w['status'] not in TERMINAL | {'blocked'} for w in workflows),
                   seats=None if missing or any(n['seat'] is None for n in nodes) else len({n['seat'] for n in nodes}),
                   build=None if missing or roles_unknown else sum(n['role'] != 'review' for n in nodes),
                   review=None if missing or roles_unknown else sum(n['role'] == 'review' for n in nodes),
                   blocked=sum(j['state'] == 'blocked' for j in jobs))
    result.update({key: value for key, value in slot.items() if key in SURF_WORK_FIELDS})
    result.update(state='stale' if failed or now - slot['read_ts'] > 120 else 'ok',
                  workflows_loaded=len(slot['workflows']), summary=summary,
                  partial=slot['partial'] or any(value is None for value in summary.values()))
    return result
