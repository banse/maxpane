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
