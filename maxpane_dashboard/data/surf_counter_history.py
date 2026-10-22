"""POOL4's existing cumulative fold with a replaceable twelve-block tail."""
from . import surf_pool4 as P


def replay_counters(prior, logs, start, head):
    if logs is None:
        return dict(prior)
    if type(start) is not int or type(head) is not int:
        return P.empty_accumulator()
    # Preserve S17: a hole still discards the accumulated history.
    cursor = prior.get('cursor_block')
    if type(cursor) is int and start > cursor + 1:
        return P.empty_accumulator()
    checkpoint = prior.get('_rollback')
    if (not isinstance(checkpoint, dict) or type(cursor) is not int
            or head < cursor - 12 or start > cursor - 11):
        # Old caches load normally, but cannot prove an unseen rollback tail.
        # Re-seed only when this complete window actually includes genesis.
        checkpoint = P.empty_accumulator()
    folded = P.accumulate_counters(checkpoint, logs, start, head)
    genesis = folded.get('genesis_block')
    if genesis is None:
        return folded
    stable = head - 12
    if stable < genesis:
        folded['_rollback'] = P.empty_accumulator()
    else:
        tail = [row for row in logs if int(row['blockNumber'], 16) > stable]
        sums = P._sum_logs(tail)
        folded['_rollback'] = {
            'genesis_block': genesis, 'cursor_block': stable,
            'sums': {key: folded['sums'][key] - int(sums[key] or 0)
                     for key in P.COUNTER_SUM_FIELDS},
        }
    return folded
