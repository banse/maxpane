"""Pure wallet request and artifact projections; unknown observations stay unknown."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import math


def timestamp(value):
    if type(value) in (int, float):
        return float(value) if math.isfinite(value) and value >= 0 else None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, OverflowError):
        return None


def usage_source(artifact, by_id):
    return by_id.get(artifact.get('linked_id')) if artifact.get('kind') == 'SITE' else artifact


def usage_signal(artifact, by_id):
    source = usage_source(artifact, by_id)
    if source is None:
        return 'NO ONCHAIN LINK' if artifact.get('binding_checked') is True else 'NO DATA'
    usage = source.get('usage') or {}
    count = usage.get('count')
    if type(count) not in (int, float) or not math.isfinite(count) or count < 0 or (count == 0 and usage.get('complete') is not True):
        return 'NO DATA'
    signal = 'QUIET' if count == 0 else 'FIRST SEEN' if usage.get('first_seen') is True else 'ACTIVE'
    return ('LINKED QUIET' if signal == 'QUIET' else 'LINKED ACTIVE') if artifact.get('kind') == 'SITE' else signal


def usage_text(artifact, by_id):
    if usage_signal(artifact, by_id) in ('NO DATA', 'NO ONCHAIN LINK'):
        return '--'
    value = usage_source(artifact, by_id)['usage']
    result = ('' if value.get('complete') is True else '>=') + f"{value['count']} {value.get('unit') or 'actions'}"
    if value['count'] and type(value.get('actors')) is int and value['actors'] >= 0:
        result += f" / {value['actors']} addresses"
    return result


def _amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def payment_totals(orders):
    """Sum only proven payments, deduplicating the same receipt log across orders."""
    if orders is None:
        return None
    groups, seen, complete = {}, set(), True
    for row in orders:
        if row.get('payment_state') != 'settled':
            continue
        payments = row.get('payments')
        if not isinstance(payments, list) or not payments:
            complete = False
            continue
        for payment in payments:
            amount = _amount(payment.get('amount'))
            chain, asset = payment.get('chain_id'), payment.get('asset')
            decimals = payment.get('decimals')
            if amount is None or type(chain) is not int or not isinstance(asset, str) or type(decimals) is not int or not 0 <= decimals <= 255:
                complete = False
                continue
            identity = (chain, asset.lower(), payment.get('tx_hash'), payment.get('log_index'))
            if not identity[2]:
                complete = False
                continue
            if identity in seen:
                continue
            seen.add(identity)
            key = (chain, asset.lower())
            group = groups.setdefault(key, dict(chain_id=chain, asset=asset.lower(), symbol=payment.get('symbol'),
                decimals=decimals, paid=Decimal(0), refunded=None, paid_complete=True, refund_complete=False, count=0))
            if group['decimals'] != decimals:
                group['paid_complete'] = False
                continue
            with localcontext() as context:
                context.prec = 340  # uint256 amounts scaled by any uint8 decimals.
                group['paid'] += amount
            group['count'] += 1
    for group in groups.values():
        group['paid'] = format(group['paid'], 'f')
        group['paid_complete'] &= complete
    return list(groups.values()) if groups or complete else None


def summary(snapshot, now):
    """30D request metrics and ALL KNOWN artifacts; no sum across unlike assets."""
    now = timestamp(now) if now is not None else timestamp(snapshot.get('as_of'))
    raw_orders, assets = snapshot.get('orders'), snapshot.get('artifacts')
    orders = None if raw_orders is None or now is None else [r for r in raw_orders
        if (stamp := timestamp(r.get('timestamp'))) is not None and now - 30 * 86400 <= stamp <= now]
    labels = ('REQUESTS', 'JOBS', 'WORKFLOWS', 'LAUNCHES', 'ORACLES', 'SCHEDULES', 'IN FLIGHT', 'ATTENTION')
    counts = dict.fromkeys(labels)
    daily = states = None
    outcomes = dict.fromkeys(('shipped', 'deployed', 'attested'))
    settled = unsettled = None
    if orders is not None:
        actions = Counter(r.get('action') for r in orders)
        counts.update(REQUESTS=len(orders), JOBS=actions['job.open'] + actions['job.continue'],
            WORKFLOWS=actions['workflow.open'], LAUNCHES=actions['launch.open'],
            ORACLES=actions['oracle.request'] + actions['oracle.group'],
            SCHEDULES=actions['schedule.create'] + actions['schedule.topup'])
        counts['IN FLIGHT'] = sum(r.get('in_flight') is True for r in orders)
        counts['ATTENTION'] = sum(r.get('follow_up') is True for r in orders)
        states = dict.fromkeys(('Completed', 'In flight', 'Attention', 'Not admitted', 'Unknown'), 0)
        for row in orders:
            state = ('Not admitted' if row.get('payment_state') == 'failed' or row.get('outcome') == 'refused' else
                'In flight' if row.get('in_flight') is True else
                'Attention' if row.get('follow_up') is True else
                'Completed' if row.get('outcome') in ('completed', 'delivered', 'done', 'succeeded', 'shipped', 'attested', 'live', 'deployed', 'active', 'runs added') else 'Unknown')
            states[state] += 1
        settled = sum(r.get('payment_state') == 'settled' for r in orders)
        unsettled = len(orders) - settled
        daily = [0] * 30
        for row in orders:
            day = min(29, int((timestamp(row['timestamp']) - (now - 30 * 86400)) // 86400))
            daily[day] += 1
        if (snapshot.get('sources', {}).get('orders') or {}).get('truncated') and orders:
            earliest = min(timestamp(row['timestamp']) for row in orders)
            daily = [None if now - 30 * 86400 + (i + 1) * 86400 <= earliest else n for i, n in enumerate(daily)]
        outcomes = dict(shipped=sum(r.get('action') == 'workflow.open' and r.get('outcome') in ('completed', 'shipped') for r in orders),
            deployed=sum(r.get('action') == 'launch.open' and r.get('outcome') in ('live', 'deployed') for r in orders),
            attested=sum(r.get('action') in ('oracle.request', 'oracle.group') and r.get('outcome') == 'attested' for r in orders))
    counts.update(dict.fromkeys(('SITES', 'CONTRACTS', 'TOKENS')))
    signals = rules = complete = linked = None
    if assets is not None:
        by_id = {a['id']: a for a in assets}
        contracts = [a for a in by_id.values() if a.get('kind') in ('CONTRACT', 'TOKEN')]
        counts.update(SITES=sum(a.get('kind') == 'SITE' for a in by_id.values()), CONTRACTS=len(contracts),
            TOKENS=sum(a.get('kind') == 'TOKEN' for a in contracts))
        signals = dict.fromkeys(('Active', 'Quiet', 'Unknown'), 0)
        for a in contracts:
            signal = usage_signal(a, by_id)
            signals['Quiet' if signal == 'QUIET' else 'Unknown' if signal == 'NO DATA' else 'Active'] += 1
        rules = sum(bool(a.get('usage') and a['usage'].get('rule')) for a in contracts)
        complete = sum(bool(a.get('usage') and a['usage'].get('complete') is True) for a in contracts)
        linked = sum(a.get('kind') == 'SITE' and a.get('linked_id') in by_id for a in assets)
    return dict(counts=counts, orders=orders, daily=daily, states=states, signals=signals,
        rules=rules, complete=complete, linked_sites=linked, settled=settled, unsettled=unsettled,
        outcomes=outcomes, payment_totals=payment_totals(orders), coverage=snapshot.get('coverage') or [], as_of=snapshot.get('as_of'))
