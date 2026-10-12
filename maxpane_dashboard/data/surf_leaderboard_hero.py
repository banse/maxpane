"""LEADERBOARD rack facts from canonical records and independent observations."""
from maxpane_dashboard.analytics.surfboard import count, number, ratio, seat_token
from maxpane_dashboard.data.surf_pool4_hero import _facts, _source


def _count(value):
    return count(value) if number(value) is not None else None


def _top(rows, source):
    unknown = dict(source, state='unavailable', token_id=None, accepted=None, rank=None, empty=None)
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
    return _facts(source, token_id=row['token_id'], accepted=accepted, rank=1, empty=False)


def project(*, data: dict, sources: dict, now: float) -> dict:
    """No fallback from contributor receipts to canonical recorded outcomes."""
    records, workers, contributors = (_source(sources, name, now)
                                      for name in ('records', 'workers', 'contributors'))
    summary = data.get('swarm_board_summary')
    summary = summary if isinstance(summary, dict) else {}
    top = _top(data.get('swarm_board_rows'), records)
    recorded = _facts(records, seats=_count(summary.get('seats')), attempts=_count(summary.get('attempts')))
    accepted, attempts = _count(summary.get('accepted')), _count(summary.get('attempts'))
    if accepted is not None and attempts is not None and accepted > attempts:
        accepted = None
    rate = _facts(records, accepted=accepted, attempts=attempts)
    fraction = ratio(rate['accepted'], rate['attempts'])
    # A known 0/0 pair means no attempts, not missing source coverage.
    rate['percent'] = fraction * 100 if fraction is not None else None
    outcomes = _facts(records, rejected=_count(summary.get('rejected')),
                      failed=_count(summary.get('failed')), pending=_count(summary.get('pending')))

    roster = sources.get('workers')
    incomplete = isinstance(roster, dict) and roster.get('partial') is True
    worker_facts = _facts(workers, live=_count(summary.get('live')),
                         working=None if incomplete else _count(summary.get('working')),
                         capacity=None if incomplete else _count(summary.get('capacity')))
    milliseconds = number(summary.get('wall_clock_ms'))
    effort = _facts(contributors, receipts=_count(summary.get('receipts')),
                    turns=_count(summary.get('turns')),
                    hours=milliseconds / 3_600_000 if milliseconds is not None else None)
    return dict(top=top, recorded=recorded, rate=rate, outcomes=outcomes,
                workers=worker_facts, effort=effort)
