"""Pure rack facts from the selected token cohort and its successful read clocks."""
from maxpane_dashboard.analytics.surfboard import number


def _stamp(value, now):
    value = number(value)
    return value if value is not None and 0 < value <= now else None


def _signed(value):
    return value if type(value) in (int, float) and number(abs(value)) is not None else None


def _source(row, label, now, mock):
    state = row.get(label + '_state', 'ok' if mock else 'unavailable')
    stamp = _stamp(row.get(label + '_read_at', now if mock else None), now)
    return state, stamp


def observed(row, label, now, is_mock=False):
    """A retained observation keeps its successful source clock, even when stale."""
    state, stamp = _source(row, label, now, is_mock)
    return state in ('ok', 'stale') and stamp is not None


def _select(rows, label, valid, now, mock):
    observations, stale = [], []
    for row in rows:
        state, stamp = _source(row, label, now, mock)
        if observed(row, label, now, mock) and valid(row):
            observations.append((row, stamp))
            if state == 'stale':
                stale.append(stamp)
    return observations, stale


def _metadata(observations, stale, total, catalogue):
    if observations:
        state = ('stale' if stale or catalogue['state'] == 'stale' else
                 'ok' if len(observations) == total and catalogue['state'] == 'ok' else 'partial')
        return dict(state=state, read_ts=min(stamp for _, stamp in observations))
    if total == 0 and catalogue['state'] == 'ok':
        return dict(catalogue)
    return dict(state='unavailable', read_ts=None)


def has_price_change(row):
    price = number(row.get('price_usd'))
    return price is not None and price > 0 and _signed(row.get('change_24h')) is not None


def project(tokens, *, catalogue, now, is_mock=False):
    """Never refresh timestamps or confuse an unread source with a known zero."""
    catalogue = catalogue if isinstance(catalogue, dict) else {}
    state = catalogue.get('state', 'ok' if is_mock else 'unavailable')
    stamp = _stamp(catalogue.get('as_of', now if is_mock else None), now)
    if state not in ('ok', 'partial', 'stale') or stamp is None or tokens is None:
        state = 'unavailable'
    cat = dict(state=state, read_ts=stamp)
    unknown = dict(state='unavailable', read_ts=None)
    result = dict(
        tokens=dict(cat, tracked=None, new_24h=None, chains=None),
        volume=dict(unknown, amount=None, known=None, total=None),
        liquidity=dict(unknown, imd=None, eth=None, known=None, total=None, partial=True),
        pools=dict(unknown, two_sided=None, one_sided=None, unknown=None, other=None),
        momentum=dict(unknown, rising=None, falling=None, flat=None, known=None, total=None),
        top_volume=dict(unknown, rows=None, known=None, total=None),
    )
    if state == 'unavailable':
        return result
    total = len(tokens)
    result['tokens'].update(tracked=total,
        new_24h=sum(1 for row in tokens if (created := number(row.get('launched_at'))) is not None
                    and 0 <= now-created < 86400),
        chains=len({row['chain'] for row in tokens if row.get('chain')}))

    volumes, stale = _select(tokens, 'market', lambda r: number(r.get('volume_24h')) is not None, now, is_mock)
    meta = _metadata(volumes, stale, total, cat)
    empty = total == 0 and state == 'ok'
    amount = sum(row['volume_24h'] for row, _ in volumes) if volumes or empty else None
    result['volume'].update(meta, amount=amount, known=len(volumes), total=total)
    leaders = sorted((row for row, _ in volumes), key=lambda r: (-r['volume_24h'], r['id']))
    result['top_volume'].update(meta, rows=[dict(symbol=row['symbol'], volume_usd=row['volume_24h'])
        for row in leaders[:3]] if leaders or empty else None, known=len(volumes), total=total)

    def paired(row):
        symbol = row.get('paired_symbol')
        return (number(row.get('paired_amount')) is not None and isinstance(symbol, str)
                and symbol.strip().upper() in ('IMD', 'ETH'))

    liquidity, stale = _select(tokens, 'liquidity', paired, now, is_mock)
    meta = _metadata(liquidity, stale, total, cat)
    partial = len(liquidity) < total or state != 'ok'
    assets = {}
    for symbol in ('IMD', 'ETH'):
        amounts = [row['paired_amount'] for row, _ in liquidity if row['paired_symbol'].strip().upper() == symbol]
        assets[symbol.lower()] = sum(amounts) if amounts or empty or not partial else None
    result['liquidity'].update(meta, **assets, known=len(liquidity), total=total, partial=partial)

    def classified(row):
        return isinstance(row.get('lp_state'), str) and row['lp_state'] not in ('', 'unknown')

    pools, stale = _select(tokens, 'liquidity', classified, now, is_mock)
    meta = _metadata(pools, stale, total, cat)
    two = sum(row['lp_state'] == 'two-sided' for row, _ in pools)
    one = sum(row['lp_state'] in ('one-token', 'one-quote') for row, _ in pools)
    result['pools'].update(meta, two_sided=two if pools or empty else None,
        one_sided=one if pools or empty else None, unknown=total-len(pools),
        other=len(pools)-two-one if pools or empty else None)

    momentum, stale = _select(tokens, 'market', has_price_change, now, is_mock)
    meta = _metadata(momentum, stale, total, cat)
    changes = [row['change_24h'] for row, _ in momentum]
    result['momentum'].update(meta, rising=sum(value > 0 for value in changes) if changes or empty else None,
        falling=sum(value < 0 for value in changes) if changes or empty else None,
        flat=sum(value == 0 for value in changes) if changes or empty else None,
        known=len(momentum), total=total)
    return result
