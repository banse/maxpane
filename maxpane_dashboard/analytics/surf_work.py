"""Original workflow lifecycle shared by projections and local navigation."""

from math import isfinite


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
