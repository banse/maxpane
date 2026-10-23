"""Original workflow lifecycle shared by projections and local navigation."""

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
