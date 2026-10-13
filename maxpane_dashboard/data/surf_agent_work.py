"""Pure accepted-work partition and bounded, independently refreshed launch facts."""
from collections.abc import Mapping
from math import isfinite

from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.data.surf_models import SWARM_ORACLE_NODE_KEYS

MAX_AGE = 48 * 3600
REFRESH_AFTER = 600
MAX_POINTS = 400
_LAUNCH_FIELDS = {'requested', 'kind', 'id', 'status', 'chainId'}
_LAUNCH_STATES = {'live', 'parked', 'abandoned', 'deployment'}


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
    """Network reads deduplicate jobs; work counts retain individual node rows."""
    return list(dict.fromkeys(job for row in accepted_rows(seat) or []
        if row['nodeKey'] not in SWARM_ORACLE_NODE_KEYS
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
    return dict(read_ts=now, launched=status == 'live')


def coerce_points(value: object, now: float) -> dict:
    """Validate persisted facts per point; retain at most 400 reads for 48 hours."""
    if not isinstance(value, Mapping) or not _timestamp(now):
        return {}
    result = {}
    for job, point in value.items():
        if (parse_job_id(job) is None or not isinstance(point, Mapping)
                or set(point) != {'read_ts', 'launched'}
                or type(point['launched']) is not bool
                or not _timestamp(point['read_ts'])
                or not 0 <= now-point['read_ts'] <= MAX_AGE):
            continue
        result[job] = dict(point)
    return dict(sorted(result.items(), key=lambda item: (-item[1]['read_ts'], item[0]))[:MAX_POINTS])


def due(seat: object, points: object, now: float, cap: int = 12) -> list[str]:
    """Read unknown jobs first; terminal jobs still refresh because they can deploy later."""
    points = coerce_points(points, now)
    jobs = [job for job in candidates(seat)
            if job not in points or now-points[job]['read_ts'] >= REFRESH_AFTER]
    return sorted(jobs, key=lambda job: (job in points, points.get(job, {}).get('read_ts', 0)))[:cap]


def summarize(seat: object, points: object, now: float) -> dict:
    """Oracle work has precedence; never silently classify unread jobs as other."""
    rows = accepted_rows(seat)
    if rows is None:
        return dict(oracle=None, launches=None, other=None, known_jobs=None, total_jobs=None)
    points = coerce_points(points, now)
    nonoracle = [row for row in rows if row['nodeKey'] not in SWARM_ORACLE_NODE_KEYS]
    jobs = candidates(seat)
    # A missing job ID cannot be fetched, but must still make coverage incomplete.
    missing = sum(parse_job_id(row.get('jobId')) is None for row in nonoracle)
    known = sum(job in points for job in jobs)
    complete = not missing and known == len(jobs)
    launched = sum(points[row['jobId']]['launched'] for row in nonoracle) if complete else None
    return dict(oracle=len(rows)-len(nonoracle), launches=launched,
                other=len(nonoracle)-launched if complete else None,
                known_jobs=known, total_jobs=len(jobs)+missing)
