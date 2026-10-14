"""LEADERBOARD rack facts from canonical records and independent observations."""
from maxpane_dashboard.analytics.surfboard import count, number, ratio, seat_token
from maxpane_dashboard.data.surf_pool4_hero import _facts, _source
from maxpane_dashboard.data.surf_swarm import _mix, _worker_groups


def _count(value):
    return count(value) if number(value) is not None else None


def _top(rows, source):
    unknown = dict(source, state='unavailable', token_id=None, accepted=None, rank=None, empty=None, percent=None)
    if not isinstance(rows, list) or source['state'] == 'unavailable':
        return unknown
    if not rows:
        return dict(unknown, state=source['state'], empty=True) if source['state'] != 'partial' else unknown
    leaders = [row for row in rows if isinstance(row, dict) and count(row.get('rank')) == 1]
    if len(leaders) != 1 or seat_token(leaders[0].get('token_id')) is None:
        return unknown
    row = leaders[0]
    accepted, attempts = _count(row.get('accepted')), _count(row.get('attempts'))
    if accepted is not None and attempts is not None and accepted > attempts:
        accepted = None
    result = _facts(source, token_id=row['token_id'], accepted=accepted, rank=1, empty=False)
    if attempts is None and result['state'] == 'ok':
        result['state'] = 'partial'
    fraction = ratio(accepted, attempts)
    return dict(result, percent=fraction * 100 if fraction is not None else None)


def _complete_workers(workers, source):
    return (workers is not None and source['state'] in ('ok', 'stale')
            and source.get('partial') is not True
            and workers['count'] == len(workers['workers']) and not workers['malformed_tokens'])


def _roster_source(workers, source):
    result = dict(state=source['state'], read_ts=source['read_ts'])
    if workers is None:
        result['state'] = 'unavailable'
    elif not _complete_workers(workers, source) and result['state'] == 'ok':
        result['state'] = 'partial'
    return result


def _runtime_leader(workers, source):
    """One vote per seat and runtime; a winner needs every seat's complete metadata."""
    result = dict(runtime=None, runtime_percent=None, runtime_count=None,
                  runtime_total=None, runtime_known=None)
    if workers is None or source['state'] == 'unavailable':
        return result
    groups = _worker_groups(workers)
    reported = [{runtime for worker in group for runtime in worker['runtimes']}
                for token, group in groups.items() if token not in workers['malformed_tokens']
                and all(worker['runtimes'] and all(runtime.strip() for runtime in worker['runtimes'])
                        for worker in group)]
    result['runtime_known'] = len(reported)
    if not _complete_workers(workers, source):
        return result
    result['runtime_total'] = len(groups)
    if not groups or len(reported) != len(groups):
        return result
    leader = _mix(runtime for runtimes in reported for runtime in runtimes)[0]
    result.update(runtime=leader['value'], runtime_count=leader['count'],
                  runtime_percent=leader['count'] / len(groups) * 100)
    return result


def launch_facts(snapshot, workers, worker_source, records_source=None):
    """All-history contribution totals plus independently timed current runtime coverage."""
    rows = snapshot.get('rows')
    seats = {row['token_id'] for row in rows} if isinstance(rows, list) else None
    runtime_source = _roster_source(workers, worker_source)
    claude = codex = known = None
    if seats is not None and _complete_workers(workers, worker_source):
        claude = codex = known = 0
        for token, group in _worker_groups(workers).items():
            if token not in seats:
                continue
            runtimes = {runtime for worker in group for runtime in worker['runtimes'] or []}
            known += bool(runtimes)
            claude += 'claude' in runtimes
            codex += 'codex' in runtimes
    jobs = _count(snapshot.get('jobs')) if seats is not None else None
    state = snapshot.get('state', 'unavailable')
    if state == 'ok' and jobs is None:
        state = 'partial' if seats is not None else 'unavailable'
    records_source = records_source or dict(state='unavailable', read_ts=None)
    records = records_source.get('payload') or {}
    total = (_count(records.get('count')) if records_source['state'] in ('ok', 'stale')
             and records_source.get('partial') is not True else None)
    fraction = ratio(len(seats) if seats is not None else None, total)
    return dict(state=state, read_ts=snapshot.get('read_ts'),
                seats=len(seats) if seats is not None else None, claude=claude, codex=codex,
                jobs=jobs, runtime_known=known, runtime_state=runtime_source['state'],
                runtime_read_ts=runtime_source['read_ts'],
                percent=fraction * 100 if fraction is not None else None, total_seats=total,
                records_state=records_source['state'], records_read_ts=records_source['read_ts'])


def project(*, data: dict, sources: dict, now: float) -> dict:
    """No fallback from contributor receipts to canonical recorded outcomes."""
    records, workers, contributors = (_source(sources, name, now)
                                      for name in ('records', 'workers', 'contributors'))
    summary = data.get('swarm_board_summary')
    summary = summary if isinstance(summary, dict) else {}
    top = _top(data.get('swarm_board_rows'), records)
    recorded = _facts(records, seats=_count(summary.get('seats')), attempts=_count(summary.get('attempts')))
    roster = sources.get('workers') or {}
    worker_slot = roster.get('payload')
    online_source = _roster_source(worker_slot, dict(workers, partial=roster.get('partial')))
    rows = data.get('swarm_board_rows')
    online = None
    if (isinstance(rows, list) and records['state'] in ('ok', 'stale')
            and _complete_workers(worker_slot, dict(online_source, partial=roster.get('partial')))):
        recorded_ids = {row['token_id'] for row in rows if isinstance(row, dict)
                        and seat_token(row.get('token_id')) is not None}
        online = len(recorded_ids & _worker_groups(worker_slot).keys())
    recorded.update(online=online, online_state=online_source['state'], online_read_ts=online_source['read_ts'])
    accepted, attempts = _count(summary.get('accepted')), _count(summary.get('attempts'))
    if accepted is not None and attempts is not None and accepted > attempts:
        accepted = None
    rate = _facts(records, accepted=accepted, attempts=attempts)
    fraction = ratio(rate['accepted'], rate['attempts'])
    # A known 0/0 pair means no attempts, not missing source coverage.
    rate['percent'] = fraction * 100 if fraction is not None else None
    snapshot = data.get('swarm_launch_contribution') or {}
    launches = snapshot.get('summary')
    launches = dict(launches) if isinstance(launches, dict) else launch_facts({}, None, workers)

    incomplete = isinstance(roster, dict) and roster.get('partial') is True
    worker_facts = _facts(workers, live=_count(summary.get('live')),
                         working=None if incomplete else _count(summary.get('working')),
                         capacity=None if incomplete else _count(summary.get('capacity')))
    worker_facts.update(_runtime_leader(worker_slot, dict(workers, partial=incomplete)))
    milliseconds = _count(summary.get('wall_clock_ms'))
    input_tokens, output_tokens = (_count(summary.get(name)) for name in ('input_tokens', 'output_tokens'))
    tokens = input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None
    effort = _facts(contributors, tokens=tokens,
                    turns=_count(summary.get('turns')),
                    hours=milliseconds / 3_600_000 if milliseconds is not None else None,
                    wall_clock_ms=milliseconds)
    return dict(top=top, recorded=recorded, rate=rate, launches=launches,
                workers=worker_facts, effort=effort)
