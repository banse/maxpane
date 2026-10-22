"""Lossless, resumable history pages shared only by Surf clients."""
from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from maxpane_dashboard.data.rpc_classify import (
    ETH_ENDPOINT_LIMITATION_FRAGMENTS, RANGE_CAP_FRAGMENTS,
    is_range_limitation, looks_like_endpoint_limitation, named_block_limit,
)
from maxpane_dashboard.data.rpc_common import jsonrpc_payload

logger = logging.getLogger(__name__)
# Captured 2026-10-22: thirdweb names the limit AFTER "requested blocks".
# Surf-only extension; parked clients keep the shared classifier unchanged.
_REQUESTED_BLOCKS_LIMIT = re.compile(r"requested blocks is (\d[\d,_]*)", re.I)


@dataclass
class _Progress:
    next_block: int
    rows: list[dict] = field(default_factory=list)


class RpcHistoryReader:
    """Keep acknowledged prefixes, never publish unfinished history.

    Each invocation accepts at most ``max_pages`` pages before yielding an
    unknown result; the next invocation resumes its acknowledged prefix.
    Pending buffers are process-local and bounded. Eviction restarts a read;
    it never advances a public cursor. Caps belong to the host which stated
    them. Empty pages require two distinct hosts, including fallback pages.
    """

    def __init__(self, post_rpc: Callable[[str, Any], Awaitable[httpx.Response]], *,
                 min_page: int = 300, max_shrinks: int = 3,
                 max_pending: int = 16, max_rows: int = 200_000,
                 max_pages: int = 256,
                 prove_block: Callable[[str, int], Awaitable[bool]] | None = None) -> None:
        self._post = post_rpc
        self._prove_block = prove_block
        self._min_page = min_page
        self._max_shrinks = max_shrinks
        self._max_pending = max_pending
        self._max_rows = max_rows
        self._max_pages = max(1, max_pages)
        self._pending: OrderedDict[tuple, _Progress] = OrderedDict()
        self._caps: dict[str, int] = {}
        self._request_id = 0

    def clear(self, group: str | None = None) -> None:
        for key in list(self._pending):
            if group is None or key[1] == group:
                del self._pending[key]

    def rewind(self, group: str, first_block: int) -> None:
        """Discard only a pending reorg-sensitive suffix, never claim it read."""
        for key, progress in list(self._pending.items()):
            if key[1] != group or progress.next_block <= first_block:
                continue
            cutoff = max(key[3], first_block)
            try:
                rows = [row for row in progress.rows
                        if int(row['blockNumber'], 16) < cutoff]
            except (KeyError, TypeError, ValueError):
                del self._pending[key]
                continue
            self._pending[key] = _Progress(cutoff, rows)

    async def read(self, endpoints: Sequence[str], base_filter: dict,
                   from_block: int, to_block: int, *, group: str,
                   page_size: int = 2400, keep_complete: bool = False) -> list[dict] | None:
        if from_block > to_block:
            return []
        key = (tuple(endpoints), group, json.dumps(base_filter, sort_keys=True), from_block)
        progress = self._pending.get(key)
        if progress is None:
            # A rolling window can move while an unfinished read is retried.
            # Reuse only an overlapping, acknowledged prefix of this filter.
            for prior_key in reversed(self._pending):
                prior = self._pending[prior_key]
                if (prior_key[:3] == key[:3] and prior_key[3] <= from_block
                        <= prior.next_block <= to_block + 1):
                    try:
                        rows = [row for row in prior.rows
                                if int(row['blockNumber'], 16) >= from_block]
                    except (KeyError, TypeError, ValueError):
                        break  # Unpositioned rows cannot safely be trimmed.
                    progress = _Progress(prior.next_block, rows)
                    del self._pending[prior_key]
                    self._pending[key] = progress
                    break
        if progress is None or progress.next_block > to_block + 1:
            progress = _Progress(from_block)
            self._pending[key] = progress
        self._pending.move_to_end(key)
        while len(self._pending) > self._max_pending:
            self._pending.popitem(last=False)
        pages = 0
        while progress.next_block <= to_block:
            if pages >= self._max_pages:
                # The next poll continues at this first unread block.
                return None
            result = await self._page(endpoints, base_filter, progress.next_block,
                                      to_block, max(1, page_size))
            if result is None:
                return None
            rows, end = result
            if len(progress.rows) + len(rows) > self._max_rows:
                self._pending.pop(key, None)
                logger.warning('history buffer exceeded row limit for %s', group)
                return None
            progress.rows.extend(rows)
            progress.next_block = end + 1
            pages += 1
        rows = list(progress.rows)
        if not keep_complete:
            self._pending.pop(key, None)
        return rows

    async def _page(self, endpoints, base_filter, start, to_block, page_size):
        # Try every host before narrowing one. A narrow provider may not
        # dictate the width used against a capable alternate.
        exhausted = set()
        shrinks = {url: 0 for url in endpoints}
        empty: dict[str, int] = {}
        while True:
            narrowed = False
            for url in endpoints:
                if url in exhausted:
                    continue
                host = (urlparse(url).hostname or url).lower()
                width = min(page_size, self._caps.get(url, page_size))
                end = min(start + width - 1, to_block)
                flt = dict(base_filter, fromBlock=hex(start), toBlock=hex(end))
                self._request_id += 1
                payload = jsonrpc_payload(self._request_id, 'eth_getLogs', [flt])
                try:
                    if self._prove_block is not None and not await self._prove_block(url, to_block):
                        exhausted.add(url)
                        continue
                    response = await self._post(url, payload)
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    if isinstance(body, dict) and body.get('error'):
                        err = body['error']
                        span = end - start + 1
                        message = str(err.get('message', '')) if isinstance(err, dict) else str(err)
                        thirdweb = _REQUESTED_BLOCKS_LIMIT.search(message)
                        named = (int(thirdweb[1].replace(',', '').replace('_', ''))
                                 if thirdweb else named_block_limit(message))
                        shrinkable = (span > named if thirdweb else is_range_limitation(
                            err, fragments=RANGE_CAP_FRAGMENTS, requested_span=span))
                        if shrinkable:
                            # A stated cap (e.g. Nodies' 50) is actionable even
                            # below the floor used for blind result-size halving.
                            narrower = (named if named is not None and 0 < named < span
                                        else max(self._min_page, span // 2))
                            if narrower < span and shrinks[url] < self._max_shrinks:
                                self._caps[url] = narrower
                                shrinks[url] += 1
                                narrowed = True
                                continue
                        if not looks_like_endpoint_limitation(err, fragments=ETH_ENDPOINT_LIMITATION_FRAGMENTS):
                            logger.warning('history request rejected: %s', err)
                        exhausted.add(url)
                        continue
                    if response.status_code >= 400 or not isinstance(body, dict):
                        exhausted.add(url)
                        continue
                    rows = body.get('result')
                    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                        exhausted.add(url)
                        continue
                    if rows:
                        return rows, end
                    empty[host] = end
                    if len(empty) >= 2:
                        # Both hosts covered this shared prefix completely.
                        return [], sorted(empty.values(), reverse=True)[1]
                    exhausted.add(url)
                except (httpx.HTTPError, ValueError):
                    exhausted.add(url)
            if not narrowed:
                return None
