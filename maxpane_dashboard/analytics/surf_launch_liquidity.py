"""Pure receipt facts and the frozen K8 display contract. No network or clock."""
from __future__ import annotations

import math
from collections.abc import Mapping

from .surf_launch_checks import address, mappings

INITIALIZE_TOPIC = '0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438'
LIQUIDITY_KEYS = (
    'state', 'range_state', 'paired_symbol', 'paired_amount', 'token_amount',
    'pool_fee', 'tick', 'tick_lower', 'tick_upper', 'owner', 'owner_is_factory',
    'lock', 'withdrawn_pct', 'share', 'read_ts',
)


def empty_liquidity(state='unknown'):
    return dict.fromkeys(LIQUIDITY_KEYS) | {'state': state}


def coerce_liquidity(value):
    """Rebuild bounded display facts; a corrupt point is not a numeric zero."""
    if not isinstance(value, dict) or set(value) != set(LIQUIDITY_KEYS):
        return None
    enums = {'state': ('info', 'warn', 'na', 'unknown'),
             'range_state': ('in range', 'at limit', 'token only', 'paired only'),
             'lock': ('burned', 'withdrawn', 'locked')}
    for key, val in value.items():
        if val is None:
            if key == 'state': return None
            continue
        if key in enums:
            if val not in enums[key]: return None
        elif key == 'owner':
            if address(val) is None: return None
        elif key == 'owner_is_factory':
            if type(val) is not bool: return None
        elif key == 'paired_symbol':
            if not isinstance(val, str) or len(val) > 256: return None
        elif key in ('tick', 'tick_lower', 'tick_upper'):
            if type(val) is not int or abs(val) > 887272: return None
        elif key == 'pool_fee':
            if type(val) is not int or not 0 <= val < 2**24: return None
        elif (type(val) not in (int, float) or not 0 <= val <= 1e100
              or (type(val) is float and not math.isfinite(val))):
            return None
    if value['share'] is not None and value['share'] > 1: return None
    if value['withdrawn_pct'] is not None and value['withdrawn_pct'] > 100: return None
    if value['tick_lower'] is not None and value['tick_upper'] is not None and value['tick_lower'] >= value['tick_upper']: return None
    return {key: address(value[key]) if key == 'owner' else value[key] for key in LIQUIDITY_KEYS}


def _word(value):
    if not isinstance(value, str) or len(value) != 66 or not value.startswith('0x'):
        return None
    try:
        raw = bytes.fromhex(value[2:])
        return raw if len(raw) == 32 else None
    except ValueError:
        return None


def coerce_initialize(value):
    """Validate the immutable Initialize evidence persisted by the launch tier."""
    if not isinstance(value, Mapping): return None
    out = {}
    for key in ('tx_hash', 'pool_id'):
        if _word(value.get(key)) is None: return None
        out[key] = value[key].lower()
    for key in ('emitter', 'currency0', 'currency1', 'hooks'):
        out[key] = address(value.get(key))
        if out[key] is None: return None
    for key, lo, hi in (('pool_fee', 0, 2**24 - 1), ('tick_spacing', 1, 2**23 - 1),
                        ('sqrt_price_x96', 1, 2**160 - 1), ('tick', -887272, 887272)):
        val = value.get(key)
        if type(val) is not int or not lo <= val <= hi: return None
        out[key] = val
    if out['currency0'] >= out['currency1']: return None
    return out


def pool_initialize(row, receipts):
    """Identify one token pool in its deploy receipts; ambiguous evidence is unknown.

    The Initialize emitter is the PoolManager identity for subsequent reads.
    No manifest fee or guessed per-chain PoolManager address is trusted.
    """
    tokens = {address(a.get('address')) for a in mappings(row.get('artifacts')) if a.get('role') == 'token'} - {None}
    if len(tokens) != 1 or not isinstance(receipts, Mapping): return None
    token = next(iter(tokens))
    hashes = {a.get('txHash') for a in mappings(row.get('artifacts')) if isinstance(a.get('txHash'), str)}
    found = []
    for tx_hash in hashes:
        receipt = receipts.get(tx_hash)
        for log in mappings(receipt.get('logs') if isinstance(receipt, Mapping) else None):
            topics = log.get('topics')
            if not isinstance(topics, list) or len(topics) != 4 or topics[0] != INITIALIZE_TOPIC:
                continue
            words = [_word(topic) for topic in topics[1:]]
            if any(w is None for w in words) or any(w[:12] != bytes(12) for w in words[1:]):
                continue
            data = log.get('data')
            if not isinstance(data, str) or len(data) != 322 or not data.startswith('0x'): continue
            try:
                payload = bytes.fromhex(data[2:])
            except ValueError:
                continue
            raw = [payload[i:i+32] for i in range(0, 160, 32)]
            if raw[2][:12] != bytes(12): continue
            candidate = coerce_initialize({
                'tx_hash': tx_hash, 'pool_id': topics[1], 'emitter': log.get('address'),
                'currency0': '0x' + words[1][-20:].hex(), 'currency1': '0x' + words[2][-20:].hex(),
                'pool_fee': int.from_bytes(raw[0], 'big'), 'tick_spacing': int.from_bytes(raw[1], 'big', signed=True),
                'hooks': '0x' + raw[2][-20:].hex(), 'sqrt_price_x96': int.from_bytes(raw[3], 'big'),
                'tick': int.from_bytes(raw[4], 'big', signed=True),
            })
            if candidate and token in (candidate['currency0'], candidate['currency1']) and candidate not in found:
                found.append(candidate)
    return found[0] if len(found) == 1 else None


MODIFY_TOPIC = '0xf208f4912782fd25c7f114ca3723a2d5dd6f3bcc3ac8db5af63baa85f711d5ec'


def coerce_pool_inputs(value):
    """Immutable receipt evidence, independently validated from market results."""
    if value == {'state': 'na'}:
        return {'state': 'na'}
    out = coerce_initialize(value)
    if out is None: return None
    out['owner'] = address(value.get('owner'))
    if out['owner'] is None or _word(value.get('salt')) is None: return None
    out['salt'] = value['salt'].lower()
    for key, lo, hi in (('tick_lower', -887272, 887272), ('tick_upper', -887272, 887272),
                        ('initial_liquidity', 1, 2**128 - 1)):
        val = value.get(key)
        if type(val) is not int or not lo <= val <= hi: return None
        out[key] = val
    if out['tick_lower'] >= out['tick_upper']: return None
    return out


def pool_inputs(row, receipts):
    """Only one matching Initialize/ModifyLiquidity pair identifies a position."""
    if row.get('kind') == 'evm_contracts': return {'state': 'na'}
    hashes = {a.get('txHash') for a in mappings(row.get('artifacts'))}
    if not hashes or None in hashes or not isinstance(receipts, Mapping): return None
    if any(not isinstance(receipts.get(h), Mapping) or not isinstance(receipts[h].get('logs'), list)
           or any(not isinstance(log, Mapping) or not isinstance(log.get('topics'), list) for log in receipts[h]['logs']) for h in hashes):
        return None
    initialize = pool_initialize(row, receipts)
    if initialize is None:
        # A malformed or ambiguous Initialize cannot prove there is no pool.
        seen = any(log.get('topics', [None])[:1] == [INITIALIZE_TOPIC]
                   for h in hashes for log in receipts[h]['logs'])
        return None if seen else {'state': 'na'}
    found = []
    for log in receipts[initialize['tx_hash']]['logs']:
        topics = log.get('topics')
        if (len(topics) != 3 or topics[0] != MODIFY_TOPIC or topics[1] != initialize['pool_id']
                or address(log.get('address')) != initialize['emitter']): continue
        owner = _word(topics[2])
        data = log.get('data')
        if owner is None or owner[:12] != bytes(12) or not isinstance(data, str) or len(data) != 258 or not data.startswith('0x'): continue
        try: raw = bytes.fromhex(data[2:])
        except ValueError: continue
        candidate = coerce_pool_inputs(dict(initialize, owner='0x'+owner[-20:].hex(),
            tick_lower=int.from_bytes(raw[:32], 'big', signed=True),
            tick_upper=int.from_bytes(raw[32:64], 'big', signed=True),
            initial_liquidity=int.from_bytes(raw[64:96], 'big', signed=True), salt='0x'+raw[96:].hex()))
        if candidate is not None and candidate not in found: found.append(candidate)
    return found[0] if len(found) == 1 else None


def state_calls(pool, *, keccak):
    """The three v4 storage words; Solidity's packed position key includes salt."""
    state_slot = int.from_bytes(keccak(bytes.fromhex(pool['pool_id'][2:]) + (6).to_bytes(32, 'big')), 'big')
    position_key = keccak(bytes.fromhex(pool['owner'][2:])
                         + pool['tick_lower'].to_bytes(3, 'big', signed=True)
                         + pool['tick_upper'].to_bytes(3, 'big', signed=True)
                         + bytes.fromhex(pool['salt'][2:]))
    position_slot = int.from_bytes(keccak(position_key + ((state_slot + 6) % 2**256).to_bytes(32, 'big')), 'big')
    return [('eth_call', [{'to': pool['emitter'], 'data': '0x1e2eaeaf'+(slot % 2**256).to_bytes(32, 'big').hex()}, 'latest'])
            for slot in (state_slot, state_slot + 3, position_slot)]


def decode_state(values):
    if not isinstance(values, (list, tuple)) or len(values) != 3: return None
    raw = [_word(v) for v in values]
    if any(w is None for w in raw): return None
    slot0, total, position = (int.from_bytes(w, 'big') for w in raw)
    tick = (slot0 >> 160) & (2**24 - 1)
    if tick >= 2**23: tick -= 2**24
    sqrt_price = slot0 & (2**160 - 1)
    if not sqrt_price or abs(tick) > 887272: return None
    return {'sqrt_price_x96': sqrt_price, 'tick': tick,
            'pool_liquidity': total & (2**128 - 1), 'position_liquidity': position & (2**128 - 1)}


def coerce_decimals(value):
    if not isinstance(value, Mapping): return {}
    return {address(k): v for k, v in value.items() if address(k) and type(v) is int and 0 <= v <= 255}


def decimals_result(value):
    raw = _word(value)
    val = int.from_bytes(raw, 'big') if raw is not None else None
    return val if val is not None and val <= 255 else None


def liquidity_result(row, pool, values, decimals, policies, checks, *, now):
    """Compute a display snapshot. Missing state/decimals is not a withdrawal."""
    from .surf_launch_checks import ZERO, PAIRS
    live = decode_state(values)
    if live is None: return None
    tokens = {address(a.get('address')) for a in mappings(row.get('artifacts')) if a.get('role') == 'token'} - {None}
    currencies = [pool['currency0'], pool['currency1']]
    if len(tokens) != 1 or next(iter(tokens)) not in currencies: return None
    token_index = currencies.index(next(iter(tokens)))
    places = [18 if c == ZERO else coerce_decimals(decimals).get(c) for c in currencies]
    if any(d is None for d in places): return None
    paired_index = 1 - token_index
    sa, sb = 1.0001 ** (pool['tick_lower']/2), 1.0001 ** (pool['tick_upper']/2)
    sp, liquidity = live['sqrt_price_x96'] / 2**96, live['position_liquidity']
    if sp <= sa:
        amounts = [liquidity * (sb-sa)/(sa*sb), 0]
    elif sp >= sb:
        amounts = [0, liquidity * (sb-sa)]
    else:
        amounts = [liquidity * (sb-sp)/(sp*sb), liquidity * (sp-sa)]
    amounts = [amount / 10**d for amount, d in zip(amounts, places)]
    tick = live['tick']
    in_range = pool['tick_lower'] <= tick < pool['tick_upper']
    range_state = ('at limit' if abs(tick) >= 887271 else 'in range' if in_range
                   else 'token only' if amounts[paired_index] == 0 else 'paired only')
    owner = pool['owner']
    withdrawn = liquidity < pool['initial_liquidity']
    lock = 'burned' if owner in (ZERO, '0x'+'0'*36+'dead') else 'withdrawn' if withdrawn else 'locked'
    factories = {address(p['params'].get('factory')) for p in mappings(policies)
                 if isinstance(p.get('params'), Mapping) and p['params'].get('chainId') == row.get('chainId')} - {None, ZERO}
    tos = {address(tx.get('to')) for tx in checks.get('K2', {}).get('evidence', {}).get('transactions', [])} - {None}
    owner_factory = owner in factories | tos if factories or tos else None
    # The caller injects the clock; timestamps are parsed without reading a clock.
    from datetime import datetime
    try: age = now - datetime.fromisoformat(row['createdAt'].replace('Z', '+00:00')).timestamp()
    except (KeyError, TypeError, ValueError): age = None
    warn = withdrawn or range_state == 'at limit' or (range_state == 'token only' and age is not None and age > 3600)
    share = liquidity / live['pool_liquidity'] if in_range and live['pool_liquidity'] else None
    if share is not None and share > 1: share = None
    paired = currencies[paired_index]
    return coerce_liquidity(dict(zip(LIQUIDITY_KEYS, (
        'warn' if warn else 'info', range_state, 'ETH' if paired == ZERO else PAIRS.get((row.get('chainId'), paired), paired),
        amounts[paired_index], amounts[token_index], pool['pool_fee'], tick, pool['tick_lower'], pool['tick_upper'],
        owner, owner_factory, lock, max(0, (1-liquidity/pool['initial_liquidity'])*100), share, now))))
