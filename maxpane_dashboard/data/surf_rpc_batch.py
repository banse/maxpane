"""Cap-safe JSON-RPC arrays for Surf's state-only clients.

Keep successes by request ID while unresolved entries rotate. This is Surf
policy; parked dashboards keep their existing RPC implementation.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.data.rpc_classify import (
    ETH_ENDPOINT_LIMITATION_FRAGMENTS, looks_like_endpoint_limitation,
)
from maxpane_dashboard.data.rpc_common import ENDPOINT_DEAD_CODES


async def read_state_batch(
    payloads: Sequence[dict], endpoints: Sequence[str],
    post_rpc: Callable[[str, Any], Awaitable[httpx.Response]], *,
    batch_limit: int = 100, retries: int = 2,
    backoff_seconds: Sequence[float] = (0.5, 1.5),
) -> list[Any] | None:
    """Return aligned results; failed entries rotate, a total outage is None.

    The captured drpc free-tier limit is three entries. Other hosts receive
    at most ``batch_limit`` entries. Responses may be shuffled or partial;
    absent IDs, explicit errors and null results remain unresolved.
    """
    if not payloads:
        return []
    results = [None] * len(payloads)
    positions = {p['id']: i for i, p in enumerate(payloads)}
    answered = False
    for url in endpoints:
        pending = [p for p in payloads if results[positions[p['id']]] is None]
        if not pending:
            break
        host = (urlparse(url).hostname or '').lower()
        limit = min(max(1, batch_limit), 3) if host.endswith('.drpc.org') else max(1, batch_limit)
        host_failed = False
        for start in range(0, len(pending), limit):
            chunk = pending[start:start + limit]
            chunk_ids = {p['id'] for p in chunk}
            for attempt in range(max(1, retries)):
                try:
                    response = await post_rpc(url, chunk)
                    if response.status_code in ENDPOINT_DEAD_CODES:
                        host_failed = True
                        break
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    if isinstance(body, dict) and body.get('error'):
                        if not looks_like_endpoint_limitation(
                            body['error'], fragments=ETH_ENDPOINT_LIMITATION_FRAGMENTS,
                        ):
                            raise RuntimeError(f"malformed request: {body['error']}")
                        host_failed = True
                        break
                    if response.status_code >= 400:
                        raise httpx.HTTPError(f'HTTP {response.status_code}')
                    if not isinstance(body, list):
                        host_failed = True
                        break
                    answered = True
                    # Conflicting duplicate IDs are not trustworthy readings.
                    entries = {}
                    duplicates = set()
                    for entry in body:
                        if not isinstance(entry, dict):
                            continue
                        ident = entry.get('id')
                        if not isinstance(ident, (str, int)) or ident not in chunk_ids:
                            continue
                        if ident in entries and entries[ident] != entry:
                            duplicates.add(ident)
                        entries[ident] = entry
                    for ident, entry in entries.items():
                        if ident not in duplicates and not entry.get('error'):
                            results[positions[ident]] = entry.get('result')
                    break
                except (httpx.HTTPError, ValueError):
                    if attempt + 1 < max(1, retries):
                        delay = backoff_seconds[min(attempt, len(backoff_seconds) - 1)] if backoff_seconds else 0
                        await asyncio.sleep(delay)
                    else:
                        host_failed = True
            if host_failed:
                break
    return results if answered else None
