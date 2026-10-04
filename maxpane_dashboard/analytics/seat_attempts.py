"""Pure attempt identity and unique standing/local joins."""
from maxpane_dashboard.analytics.seat_signals import parse_iso


def is_open(row):
    return (row.get('submittedUtc') is None and not row.get('cancelled')
            and not row.get('interruptedByRestart') and 'failed' not in (row.get('phases') or []))


def start(row):
    return row.get('acceptedUtc') or row.get('startedUtc') or row.get('since')


def in_start_window(plane, local):
    since, accepted = parse_iso(start(plane)), parse_iso(start(local))
    return since is not None and accepted is not None and -2 <= accepted - since <= 8


def compatible(left, right):
    # Unknown job ids can be learned from standing, but known contradictions cannot.
    return all(not (left.get(name) and right.get(name) and left[name] != right[name])
               for name in ('jobId', 'key', 'nodeId8', 'nodeKey'))


def same_attempt(left, right):
    if not compatible(left, right):
        return False
    left_start, right_start = parse_iso(start(left)), parse_iso(start(right))
    if left_start is not None and right_start is not None:
        # Two standing-only selections have exact starts; clock allowance is for the local join.
        if not left.get('acceptedUtc') and not right.get('acceptedUtc'):
            return left_start == right_start
        plane, local = (right, left) if left.get('acceptedUtc') and not right.get('acceptedUtc') else (left, right)
        if not in_start_window(plane, local):
            return False
    if any(left.get(name) and right.get(name) for name in ('key', 'nodeId8', 'nodeKey')):
        return True
    return in_start_window(left, right)


def unique_pairs(planes, locals):
    """Return plane-index -> local-index only when both ends have one candidate."""
    candidates = []
    for plane in planes:
        eligible = [j for j, row in enumerate(locals) if compatible(plane, row)]
        matches = []
        for j in eligible:
            row = locals[j]
            known = parse_iso(start(plane)) is not None and parse_iso(start(row)) is not None
            named = any(plane.get(name) and row.get(name) for name in ('key', 'nodeId8', 'nodeKey'))
            single = (sum(p.get('jobId') == plane.get('jobId') for p in planes) == 1
                      and sum(not r.get('jobId') or r.get('jobId') == plane.get('jobId') for r in locals) == 1)
            matches_time = in_start_window(plane, row) if known else named or single
            if matches_time:
                matches.append(j)
        named_matches = [j for j in matches if any(plane.get(name) and locals[j].get(name)
                         for name in ('key', 'nodeId8', 'nodeKey'))]
        candidates.append(named_matches or matches)
    return {i: matches[0] for i, matches in enumerate(candidates) if len(matches) == 1
            and sum(matches[0] in other for other in candidates) == 1}


def stale_plane(plane, rows):
    return any(not is_open(row) and row.get('jobId') == plane.get('jobId')
               and row.get('nodeKey') and row.get('nodeKey') == plane.get('nodeKey')
               and in_start_window(plane, row) for row in rows)
