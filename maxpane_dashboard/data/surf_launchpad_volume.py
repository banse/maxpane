"""Bounded exact-time CurveSwap volume; the existing log sweep owns coverage.

All amounts remain integer ETH wei until the hub applies its observed USD
quote. Header failure or an exceeded budget cannot certify an empty interval.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import math
import re

from maxpane_dashboard.data import surf_addresses as A

BUCKET_SECONDS = 900
BUCKET_COUNT = 8
SNAPSHOT_TTL = 600
MAX_BLOCK_HEADERS = 256
HEADER_BATCH = 32
HEADER_TIMEOUT = 20
_HASH = re.compile(r'0x[0-9a-fA-F]{64}\Z')
_QUANTITY = re.compile(r'0x[0-9a-fA-F]+\Z')
_WORDS = re.compile(r'0x[0-9a-fA-F]{384}\Z')
_FIELDS = {'state', 'points_wei', 'read_ts', 'head_ts', 'until', 'known', 'total'}


def _integer(value):
    return type(value) is int and value >= 0


def _finite(value):
    try:
        return type(value) in (int, float) and value >= 0 and math.isfinite(value)
    except OverflowError:
        return False


def _quantity(value):
    return int(value, 16) if isinstance(value, str) and _QUANTITY.fullmatch(value) else None


def coerce_snapshot(value, *, now):
    """Validate persisted clocks/coverage/amounts without advancing freshness."""
    if not isinstance(value, dict) or set(value) != _FIELDS or not _finite(now):
        return None
    if any(not _finite(value[k]) for k in ('read_ts', 'head_ts', 'until')):
        return None
    if (not BUCKET_COUNT*BUCKET_SECONDS <= value['until'] <= value['head_ts'] <= value['read_ts'] <= now
            or value['until'] % BUCKET_SECONDS
            or value['head_ts']-value['until'] >= BUCKET_SECONDS
            or not _integer(value['known'])
            or value['total'] is not None and not _integer(value['total'])):
        return None
    points = value['points_wei']
    if value['state'] == 'partial':
        if points is not None:
            return None
    elif (value['state'] != 'ok' or value['known'] != value['total']
          or not isinstance(points, list) or len(points) != BUCKET_COUNT
          or any(not _integer(p) or not _finite(p) for p in points)):
        return None
    return deepcopy(value)


async def fetch_snapshot(rows, pools, *, coin_count, start_block, head_block, now,
                         read_headers, decode_swap):
    """Reuse uncapped logs and at most 258 headers in a 20-second budget."""
    try:
        async with asyncio.timeout(HEADER_TIMEOUT):
            return await _fetch(rows, pools, coin_count, start_block, head_block, now,
                                read_headers, decode_swap)
    except (TimeoutError, RuntimeError, ValueError, TypeError, OverflowError):
        return None


async def _fetch(rows, pools, coin_count, start_block, head_block, now, read_headers, decode_swap):
    if (not isinstance(rows, list) or not _integer(start_block) or not _integer(head_block)
            or start_block > head_block or not _finite(now)
            or any(not isinstance(pool, str) or not _HASH.fullmatch(pool) for pool in pools)):
        return None
    events, signatures = {}, {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        topics = row.get('topics')
        block, index = _quantity(row.get('blockNumber')), _quantity(row.get('logIndex'))
        if block is not None and block < start_block:
            continue  # cold sweeps also carry older lifetime history
        tx = row.get('transactionHash')
        if (row.get('removed', False) is not False or not isinstance(row.get('address'), str)
                or row['address'].lower() != A.LAUNCHPAD_HOOK.lower()
                or not isinstance(topics, list) or len(topics) != 4
                or topics[0] != A.TOPIC_CURVE_SWAP or not isinstance(topics[1], str)
                or not _HASH.fullmatch(topics[1])
                or any(not isinstance(topic, str) or not _HASH.fullmatch(topic)
                       or topic[2:26] != '0'*24 for topic in topics[2:])
                or not isinstance(tx, str) or not _HASH.fullmatch(tx)
                or block is None or index is None or not start_block <= block <= head_block
                or not isinstance(row.get('data'), str) or not _WORDS.fullmatch(row['data'])):
            return None
        parsed = decode_swap(row)
        if (parsed is None or not _integer(parsed.get('eth_amount_wei'))
                or int(row['data'][2:66], 16) not in (0, 1)
                or parsed['pool_id'] not in pools):
            return None
        block_hash = row.get('blockHash')
        if block_hash is not None and (not isinstance(block_hash, str) or not _HASH.fullmatch(block_hash)):
            return None
        key = (tx.lower(), index)
        signature = (block, tuple(topic.lower() for topic in topics), row['data'].lower(), block_hash)
        event = (block, parsed['pool_id'], parsed['eth_amount_wei'],
                 block_hash.lower() if block_hash is not None else None)
        if key in signatures and signatures[key] != signature:
            return None
        signatures[key] = signature
        events[key] = event

    headers = {}
    async def fetch_blocks(blocks):
        blocks = sorted(set(blocks))
        reply = await read_headers([('eth_getBlockByNumber', [hex(block), False]) for block in blocks])
        if not isinstance(reply, list) or len(reply) != len(blocks):
            return False
        for block, header in zip(blocks, reply):
            if not isinstance(header, dict):
                return False
            stamp = _quantity(header.get('timestamp'))
            digest = header.get('hash')
            if (_quantity(header.get('number')) != block or stamp is None or stamp > now
                    or not isinstance(digest, str) or not _HASH.fullmatch(digest)):
                return False
            headers[block] = (stamp, digest.lower())
        ordered = [headers[block][0] for block in sorted(headers)]
        return all(earlier < later for earlier, later in zip(ordered, ordered[1:]))

    if not await fetch_blocks([start_block, head_block]):
        return None
    head_ts = headers[head_block][0]
    until = head_ts // BUCKET_SECONDS * BUCKET_SECONDS
    since = until - BUCKET_COUNT * BUCKET_SECONDS
    if since < 0 or headers[start_block][0] > since:
        return None
    result = dict(state='partial', points_wei=None, read_ts=float(now),
                  head_ts=float(head_ts), until=float(until), known=len(pools),
                  total=coin_count if _integer(coin_count) else None)
    if not _integer(coin_count) or coin_count != len(pools):
        return coerce_snapshot(result, now=now)
    events = list(events.values())
    blocks = sorted({event[0] for event in events} - headers.keys(), reverse=True)
    for offset in range(0, len(blocks), HEADER_BATCH):
        if offset >= MAX_BLOCK_HEADERS:
            return None
        batch = blocks[offset:offset+HEADER_BATCH]
        if not await fetch_blocks(batch):
            return None
        # Block timestamps increase strictly; the remaining blocks are older.
        if headers[min(batch)][0] < since:
            break
    points = [0] * BUCKET_COUNT
    for block, pool, amount, digest in events:
        if block not in headers:
            continue  # proven older than the window by the batch boundary
        stamp, observed_hash = headers[block]
        if digest is not None and digest != observed_hash:
            return None
        if since <= stamp < until:
            points[(stamp-since)//BUCKET_SECONDS] += amount
    result.update(state='ok', points_wei=points)
    return coerce_snapshot(result, now=now)
