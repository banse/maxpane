"""Pure accepted-work partition and bounded, independently refreshed launch facts."""
from collections.abc import Mapping
from math import isfinite

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_launch_checks import is_production
from maxpane_dashboard.data.surf_models import SWARM_ORACLE_NODE_KEYS

MAX_AGE = 48 * 3600
REFRESH_AFTER = 600
MAX_POINTS = 400
_LAUNCH_FIELDS = {'requested', 'kind', 'id', 'status', 'chainId'}
_LAUNCH_STATES = {'live', 'parked', 'abandoned', 'deployment'}
# Oracle requests cover more networks than the platform's launch catalogue.
_ORACLE_MAINNETS = {1, 8453, 4663, 56, 42161}
_ORACLE_TESTNETS = {11155111, 84532, 46630, 97, 421614}


def accepted_rows(seat: object) -> list[dict] | None:
    """Count accepted attempts, including the legacy status-less work shape."""
    if not isinstance(seat, Mapping) or not isinstance(seat.get('work'), list):
        return None
    rows = []
    for item in seat['work']:
        if not isinstance(item, Mapping):
            return None
        if item.get('status') not in (None, 'accepted'):
            continue
        if not isinstance(item.get('nodeKey'), str) or not item['nodeKey'].strip():
            return None
        rows.append(dict(item))
    return rows


def accepted_job_ids(seat: object) -> set[str]:
    return {job for row in accepted_rows(seat) or []
            if (job := parse_job_id(row.get('jobId'))) is not None}


def candidates(seat: object) -> list[str]:
    """Distinct accepted non-oracle jobs; an oracle node takes precedence."""
    rows = accepted_rows(seat) or []
    oracle = set(oracle_candidates(seat))
    return [job for job in _candidate_jobs(rows) if job not in oracle]


def oracle_candidates(seat: object, *, include_attempts=False) -> list[str]:
    """Oracle identities for the shared bulk request index."""
    rows = seat.get("work") if include_attempts and isinstance(seat, Mapping) else accepted_rows(seat)
    rows = rows if isinstance(rows, list) else []
    return list(dict.fromkeys(job for row in rows
        if isinstance(row, Mapping) and isinstance(row.get('nodeKey'), str)
        and row['nodeKey'] in SWARM_ORACLE_NODE_KEYS
        and (job := parse_job_id(row.get('jobId'))) is not None))


def record_candidates(seat: object) -> list[str]:
    """RECORD includes rejected/failed attempts on jobs that eventually launched."""
    rows = seat.get('work') if isinstance(seat, Mapping) else None
    return _candidate_jobs(rows if isinstance(rows, list) else [])


def _candidate_jobs(rows) -> list[str]:
    return list(dict.fromkeys(job for row in rows
        if isinstance(row, Mapping) and isinstance(row.get('nodeKey'), str)
        and row['nodeKey'].strip() and row['nodeKey'] not in SWARM_ORACLE_NODE_KEYS
        and (job := parse_job_id(row.get('jobId'))) is not None))


def _timestamp(value: object) -> bool:
    try:
        return type(value) in (int, float) and isfinite(value) and value >= 0
    except OverflowError:
        return False


def membership_point(detail: object, job: str, now: float) -> dict | None:
    """A launch kind is only a request; a live ID on a served chain proves launch."""
    if (parse_job_id(job) is None or not _timestamp(now)
            or not isinstance(detail, Mapping) or detail.get('id') != job):
        return None
    launch = detail.get('launch')
    if not isinstance(launch, Mapping) or not _LAUNCH_FIELDS <= launch.keys():
        return None
    requested, kind, identity, status, chain = (launch[k] for k in
        ('requested', 'kind', 'id', 'status', 'chainId'))
    if (type(requested) is not bool
            or chain is not None and (type(chain) is not int or chain <= 0)):
        return None
    if not requested:
        if any(value is not None for value in (kind, identity, status, chain)):
            return None
    else:
        if not isinstance(kind, str) or not kind.strip():
            return None
        if identity is not None or status is not None:
            if (parse_job_id(identity) is None or not isinstance(status, str)
                    or status not in _LAUNCH_STATES or chain is None):
                return None
    launched = status == 'live'
    workflow = detail.get('workflow')
    if not launched and ('workflow' not in detail or workflow is not None and (
            not isinstance(workflow, Mapping) or parse_job_id(workflow.get('id')) is None)):
        return None
    return dict(read_ts=now, launched=launched, chain_id=chain,
                shipped=launched if launched or workflow is None else None)


def workflow_contract(detail: object, workflow: object, job: str) -> str | None:
    """Validate the selected job's workflow before following its contract job."""
    link = detail.get('workflow') if isinstance(detail, Mapping) else None
    if (not isinstance(link, Mapping) or not isinstance(workflow, Mapping)
            or parse_job_id(link.get('id')) is None or workflow.get('id') != link['id']):
        return None
    contracts, frontend = workflow.get('contracts'), workflow.get('frontend')
    if (not isinstance(contracts, Mapping) or parse_job_id(contracts.get('id')) is None
            or 'frontend' not in workflow or frontend is not None and (
                not isinstance(frontend, Mapping) or parse_job_id(frontend.get('id')) is None)):
        return None
    return contracts['id'] if job in (contracts['id'], frontend.get('id') if frontend else None) else None


def workflow_point(detail: object, workflow: object, contract: object, job: str, now: float) -> dict | None:
    """Join an explicitly linked frontend without changing RECORD's direct launch flag."""
    identity = workflow_contract(detail, workflow, job)
    point = membership_point(detail, job, now)
    contract_point = membership_point(contract, identity, now) if identity else None
    if point is None or contract_point is None:
        return None
    link = contract.get('workflow')
    if not isinstance(link, Mapping) or link.get('id') != workflow['id'] or 'launch' not in workflow:
        return None
    expected, actual = workflow['launch'], contract['launch']
    if expected is None:
        if actual['id'] is not None or actual['status'] is not None:
            return None
    elif (not isinstance(expected, Mapping) or parse_job_id(expected.get('id')) is None
            or expected['id'] != actual['id'] or expected.get('status') != actual['status']):
        return None
    return dict(point, shipped=contract_point['launched'], chain_id=contract_point['chain_id'])


def coerce_points(value: object, now: float) -> dict:
    """Validate persisted facts per point; retain at most 400 reads for 48 hours."""
    if not isinstance(value, Mapping) or not _timestamp(now):
        return {}
    result = {}
    for job, point in value.items():
        if (parse_job_id(job) is None or not isinstance(point, Mapping)
                or set(point) not in ({'read_ts', 'launched'}, {'read_ts', 'launched', 'chain_id', 'shipped'})
                or type(point['launched']) is not bool
                or not _timestamp(point['read_ts'])
                or not 0 <= now-point['read_ts'] <= MAX_AGE):
            continue
        if 'shipped' in point and (type(point['shipped']) is not bool
                or point['chain_id'] is not None and (type(point['chain_id']) is not int or point['chain_id'] <= 0)
                or point['launched'] and not point['shipped']
                or point['shipped'] and point['chain_id'] is None):
            continue
        result[job] = dict(point)
    return dict(sorted(result.items(), key=lambda item: (-item[1]['read_ts'], item[0]))[:MAX_POINTS])


def due(seat: object, points: object, now: float, cap: int = 12, *, include_attempts=False) -> list[str]:
    """Read unknown jobs first; terminal jobs still refresh because they can deploy later."""
    points = coerce_points(points, now)
    jobs = [job for job in (record_candidates(seat) if include_attempts else candidates(seat))
            if job not in points or 'shipped' not in points[job]
            or now-points[job]['read_ts'] >= REFRESH_AFTER]
    return sorted(jobs, key=lambda job: (job in points, points.get(job, {}).get('read_ts', 0)))[:cap]


def record_rows(rows, points, *, now, failed=()) -> list[dict]:
    """Join verified job membership; launch intent never proves a launch."""
    points = coerce_points(points, now)
    result = []
    for row in rows:
        job = parse_job_id(row.get('job_id'))
        if row.get('node_key') in SWARM_ORACLE_NODE_KEYS:
            state = 'not_launched'
        elif job is None or job in failed:
            state = 'unavailable'
        elif job not in points:
            state = 'not_read'
        else:
            state = 'launched' if points[job]['launched'] else 'not_launched'
        result.append(dict(row, launch_state=state))
    return result


def _summarize_rows(rows, points, chains, absent):
    """Oracle work has precedence; never classify unread jobs as other."""
    if rows is None:
        return dict(oracle=None, launches=None, other=None, known_jobs=None, total_jobs=None)
    oracle_jobs = {parse_job_id(row.get('jobId')) for row in rows
                   if row['nodeKey'] in SWARM_ORACLE_NODE_KEYS}
    requests = oracle_jobs - absent
    oracle = (sum(chains[job] in _ORACLE_MAINNETS for job in requests)
              if None not in oracle_jobs and all(type(chains.get(job)) is int
                  and chains[job] in _ORACLE_MAINNETS | _ORACLE_TESTNETS for job in requests) else None)
    nonoracle = [row for row in rows if row['nodeKey'] not in SWARM_ORACLE_NODE_KEYS]
    jobs = [job for job in _candidate_jobs(rows) if job not in oracle_jobs]
    # A missing job ID cannot be fetched, but must still make coverage incomplete.
    missing = sum(parse_job_id(row.get('jobId')) is None for row in nonoracle)
    known = sum(job in points and 'shipped' in points[job] for job in jobs)
    complete = not missing and known == len(jobs)
    launched = sum(points[job]['shipped'] and is_production(dict(chainId=points[job]['chain_id']))
                   for job in jobs) if complete else None
    return dict(oracle=oracle, launches=launched,
                other=len(jobs)-launched if complete else None,
                known_jobs=known, total_jobs=len(jobs)+missing)


def summarize(seat: object, points: object, now: float, *, oracle_chains=None, oracle_absent=()) -> dict:
    """Accepted and all-attempt distinct jobs share production and membership rules."""
    points = coerce_points(points, now)
    chains = oracle_chains if isinstance(oracle_chains, Mapping) else {}
    absent = {job for job in oracle_absent if parse_job_id(job) is not None and job not in chains}
    accepted = accepted_rows(seat)
    rows = seat.get('work') if isinstance(seat, Mapping) else None
    # Legacy work lists contain accepted attempts only, so their denominator is unknown.
    if not isinstance(rows, list) or any(not isinstance(row, Mapping)
            or not isinstance(row.get('nodeKey'), str) or not row['nodeKey'].strip()
            or row.get('status') not in ('accepted', 'pending', 'rejected', 'failed') for row in rows):
        rows = None
    if rows is not None:
        # Category is a job fact: unsuccessful nodes still establish oracle precedence.
        accepted_ids = {parse_job_id(row.get('jobId')) for row in accepted or []}
        accepted = [row for row in rows if parse_job_id(row.get('jobId')) in accepted_ids]
    accepted = _summarize_rows(accepted, points, chains, absent)
    total = _summarize_rows(rows, points, chains, absent)
    return dict(accepted, launches_total=total['launches'], oracle_total=total['oracle'])
