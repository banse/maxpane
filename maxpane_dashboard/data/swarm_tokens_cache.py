"""Bounded private token observations; successful read clocks survive restart."""
import json
import math
from pathlib import Path
import re
import tempfile

from maxpane_dashboard.data.surf_swarm import _launch_list_row
from maxpane_dashboard.data.series_points import coerce_points

MAX_BYTES, MAX_ROWS, MAX_TOKENS = 16 * 1024 * 1024, 5000, 2048
TOKEN = re.compile(r'(1|8453|4663):0x[0-9a-f]{40}\Z')
POOL = re.compile(r'0x(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z')
NUMBERS = ('price_usd', 'change_24h', 'mcap_usd', 'fdv_usd', 'volume_24h', 'buys_24h', 'sells_24h')


def number(value, *, signed=False):
    try:
        return (type(value) in (int, float) and math.isfinite(value)
                and (signed or value >= 0))
    except OverflowError:
        return False


def stamp(value, now):
    return number(value) and value <= now


def point(value, kind, key, now):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not stamp(value[1], now):
        return None
    raw, observed = value
    if not isinstance(raw, dict) or raw.get('state') not in ('ok', 'partial', 'unsupported', 'unindexed'):
        return None
    out = {'state': raw['state']}
    for field in ('_pool', '_expected_pool', 'market_pool'):
        pool = raw.get(field)
        if pool is not None and (not isinstance(pool, str) or not POOL.fullmatch(pool)):
            return None
        out[field] = pool
    if kind == 'market':
        for field in NUMBERS:
            value = raw.get(field)
            if value is not None and not number(value, signed=field == 'change_24h'):
                return None
            out[field] = value
        for field in ('symbol', 'name', 'market_source'):
            value = raw.get(field)
            out[field] = value[:256] if isinstance(value, str) else None
        # No direction is inferred without a new pair of price observations.
        out['_price_direction'] = None
    elif kind in ('history', 'volume'):
        if raw['state'] in ('unsupported', 'unindexed'):
            return out, observed
        field = 'sparkline' if kind == 'history' else 'volume_usd'
        times, values = raw.get('timestamps'), raw.get(field)
        if (not isinstance(times, list) or not isinstance(values, list)
                or len(times) != len(values) or len(times) > 24):
            return None
        pairs = [(t, v if number(v) else None) for t, v in zip(times, values)
                 if stamp(t, now) and t > 0]
        valid, _ = coerce_points(pairs, now=now)
        observed_values = dict(valid)
        times = [t for t, _ in pairs]
        ordered = sorted(set(times))
        # Bad values and ambiguous duplicate timestamps remain gaps; one
        # corrupt point must never discard its valid neighboring observations.
        out.update(timestamps=ordered, **{field: [observed_values.get(t)
                   if times.count(t) == 1 else None for t in ordered]})
    else:
        events = raw.get('activity')
        if not isinstance(events, list):
            return None
        valid = []
        for event in events[:200]:
            if (not isinstance(event, dict) or not isinstance(event.get('id'), str)
                    or len(event['id']) > 256 or event.get('token_id') != key
                    or event.get('kind') not in ('BUY', 'SELL') or not stamp(event.get('ts'), now)
                    or event.get('amount') is not None and not number(event['amount'])
                    or not isinstance(event.get('asset'), str)):
                continue
            valid.append({field: event.get(field) for field in ('id', 'token_id', 'kind', 'ts', 'asset', 'amount')})
            valid[-1]['asset'] = valid[-1]['asset'][:32]
        out['activity'] = valid
        if len(valid) != len(events):
            out['state'] = 'partial'
    return out, observed


def coerce(raw, now):
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1:
        return {}
    out = dict(version=1, catalogue=None, cat_as_of=None, complete=False)
    rows = raw.get('catalogue')
    if isinstance(rows, list) and stamp(raw.get('cat_as_of'), now):
        valid = {}
        for row in rows[:MAX_ROWS]:
            if (not isinstance(row, dict) or type(row.get('launchNumber')) is not int
                    or type(row.get('chainId')) is not int or not isinstance(row.get('artifacts'), list)
                    or len(row['artifacts']) > 64 or any(not isinstance(a, dict) for a in row['artifacts'])):
                continue
            item = _launch_list_row(row)
            if item is not None and item['launchNumber'] > 0:
                valid[item['id']] = item
        out.update(catalogue=list(valid.values()), cat_as_of=raw['cat_as_of'],
                   complete=raw.get('complete') is True and len(valid) == len(rows))
    for kind in ('market', 'history', 'trades', 'volume'):
        values = raw.get(kind)
        valid = {}
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(key, str) and TOKEN.fullmatch(key):
                    checked = point(value, kind, key, now)
                    if checked is not None:
                        valid[key] = checked
        out[kind] = dict(sorted(valid.items(), key=lambda item: item[1][1], reverse=True)[:MAX_TOKENS])
    return out


class SwarmTokensCache:
    def __init__(self, path):
        self.path = Path(path) if path is not None else None

    def load(self, now):
        if self.path is None:
            return {}
        try:
            if self.path.stat().st_size > MAX_BYTES:
                return {}
            return coerce(json.loads(self.path.read_text()), now)
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            return {}

    def save(self, state, now):
        if self.path is None:
            return
        temporary = None
        try:
            body = json.dumps(coerce(state, now), allow_nan=False, separators=(',', ':'))
            if len(body.encode()) > MAX_BYTES:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(body)
            temporary.replace(self.path)
        except (OSError, ValueError, TypeError, OverflowError):
            pass  # A failed persistence write never replaces in-memory observations.
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
