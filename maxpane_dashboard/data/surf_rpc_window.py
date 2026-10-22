"""Bounded complete log windows with twelve-block canonical-tail replay."""
from __future__ import annotations

import copy
import json
from collections import OrderedDict
from dataclasses import dataclass

from maxpane_dashboard.data.surf_rpc_history import RpcHistoryReader


@dataclass
class _Window:
    start: int
    end: int
    rows: list[dict]


class RpcLogWindow:
    """Reuse the finalized prefix; replace the full replay suffix each read.

    A failed or bounded-out tail stays unknown and never changes the last
    complete window. Prefixes come only from RpcHistoryReader's complete
    results. Cold progress survives between invocations, including cancellation.
    """

    def __init__(self, history: RpcHistoryReader, *, replay_blocks: int = 12,
                 max_windows: int = 16, max_rows: int = 200_000) -> None:
        self._history = history
        self.replay_blocks = max(1, replay_blocks)
        self._max_windows = max(1, max_windows)
        self._max_rows = max_rows
        self._windows: OrderedDict[tuple, _Window] = OrderedDict()
        self._attempts: OrderedDict[tuple, int] = OrderedDict()

    def clear(self, group: str | None = None) -> None:
        for mapping in (self._windows, self._attempts):
            for key in list(mapping):
                if group is None or key[1] == group:
                    del mapping[key]
        self._history.clear(None if group is None else 'window:' + group)

    async def read(self, endpoints, base_filter, from_block, to_block, *,
                   group, page_size=2400):
        if from_block > to_block:
            return []
        key = (tuple(endpoints), group, json.dumps(base_filter, sort_keys=True))
        prior = self._windows.get(key)
        start = from_block
        if (prior is not None and from_block >= prior.start
                and from_block <= prior.end + 1
                and to_block >= prior.end - self.replay_blocks + 1):
            start = max(from_block, prior.end - self.replay_blocks + 1)
        else:
            prior = None
        pending_group = 'window:' + group
        if key in self._attempts:
            self._history.rewind(pending_group, self._attempts[key] - self.replay_blocks + 1)
        self._attempts[key] = to_block
        self._attempts.move_to_end(key)
        while len(self._attempts) > self._max_windows:
            self._attempts.popitem(last=False)
        fresh = await self._history.read(endpoints, base_filter, start, to_block,
                                         group=pending_group, page_size=page_size)
        if fresh is None:
            return None
        prefix = [] if prior is None else [r for r in prior.rows
                  if from_block <= int(r['blockNumber'], 16) < start]
        rows = self._merge(prefix + fresh, from_block, to_block)
        if rows is None or len(rows) > self._max_rows:
            return None
        self._windows[key] = _Window(from_block, to_block, copy.deepcopy(rows))
        self._windows.move_to_end(key)
        self._attempts.pop(key, None)
        while len(self._windows) > self._max_windows:
            self._windows.popitem(last=False)
        return rows

    @staticmethod
    def _merge(rows, start, end):
        unique = {}
        for row in rows:
            try:
                block = int(row['blockNumber'], 16)
            except (KeyError, TypeError, ValueError):
                return None
            if not start <= block <= end or row.get('removed') is True:
                continue
            tx, index = row.get('transactionHash'), row.get('logIndex')
            identity = (str(tx).lower(), str(index).lower()) if tx and index is not None else json.dumps(row, sort_keys=True)
            if identity in unique and unique[identity] != row:
                return None
            unique[identity] = row
        return list(unique.values())
