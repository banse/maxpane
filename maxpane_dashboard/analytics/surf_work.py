"""Original workflow lifecycle shared by projections and local navigation."""

from math import isfinite
from maxpane_dashboard.analytics.surf_ids import parse_job_id


def _timestamp(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value >= 0


def activity_ts(row):
    """Latest valid activity in a normalized job/workflow, without reading a clock."""
    return max((row.get(key) for key in ("created_ts", "updated_ts") if _timestamp(row.get(key))), default=None)


def recent_activity(row, now_ts, seconds=86400):
    stamp = activity_ts(row)
    return _timestamp(now_ts) and stamp is not None and now_ts - seconds <= stamp <= now_ts

WORKFLOW_OPEN = frozenset({
    'queued', 'pending', 'running', 'executing', 'contracts', 'deployment',
    'frontend', 'publishing', 'validating',
})
WORKFLOW_STOPPED = frozenset({'blocked', 'paused'})
WORKFLOW_CLOSED = frozenset({'completed', 'cancelled', 'failed', 'superseded'})


def workflow_is_open(status: object) -> bool | None:
    """A continuation cannot reopen its original workflow; unknown stays unknown."""
    if not isinstance(status, str):
        return None
    if status in WORKFLOW_OPEN:
        return True
    if status in WORKFLOW_STOPPED | WORKFLOW_CLOSED:
        return False
    return None


def job_family(raw):
    """Explicit job purpose; a continuation's parent or prose proves no launch."""
    launch, workflow = raw.get('launch'), raw.get('workflow')
    if isinstance(workflow, dict) and parse_job_id(workflow.get('id')) is not None:
        return 'launch'
    if not isinstance(launch, dict) or type(launch.get('requested')) is not bool:
        return None
    if launch['requested']:
        return 'launch'
    if (parse_job_id(raw.get('oracleRequestId')) is not None
            or raw.get('template') in ('goal', 'research', 'skill:research-report', 'skill:oracle-assess')):
        return 'research'
    return 'other' if isinstance(raw.get('template'), str) and workflow is None else None
