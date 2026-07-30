"""In-memory cache with time-series accumulation for Base chain token prices.

The ``BaseTokenCache`` accumulates per-token price histories over time so the
dashboard can render sparklines and trend indicators.  It follows the same
patterns as ``DataCache`` and ``FrenPetCache``.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict, deque
from typing import Any

from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken
from maxpane_dashboard.data.series_points import coerce_points

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, price_usd)
TimeSeriesPoint = tuple[float, float]

# Upper bound on distinct token addresses tracked at once.  The trending
# response normally holds a few dozen tokens, but the upstream list is
# attacker- (or bug-) controlled and every new address costs a 120-point
# deque that is persisted to ``~/.maxpane/base_cache.json`` and reloaded
# on every MaxPane startup, for every dashboard.  Beyond this many
# addresses the least-recently-updated entry is evicted.
_MAX_TRACKED_TOKENS = 500

# Upper bound on tokens accepted from a single upstream snapshot.  Guards
# the per-cycle blowup: one hostile response cannot allocate more than
# this many deques before eviction kicks in.
_MAX_TOKENS_PER_UPDATE = 100


def _last_timestamp(points: Any) -> float:
    """Best-effort epoch of a raw history's newest point, ``-inf`` if unknown.

    Used only to rank persisted histories for the load-time cap, so it
    never raises: an unparseable entry simply sorts oldest and is the
    first to be dropped.
    """
    if not isinstance(points, list) or not points:
        return float("-inf")
    last = points[-1]
    if not isinstance(last, (list, tuple)) or not last:
        return float("-inf")
    try:
        return float(last[0])
    except (TypeError, ValueError):
        return float("-inf")


class BaseTokenCache:
    """Caches Base chain token price histories for sparkline rendering.

    The set of tracked token addresses is bounded: at most
    ``max_tokens`` addresses are kept, evicting the least recently
    updated one first (LRU).  The bound is enforced on ``update()``,
    ``record_token()`` **and** ``load_from_file()``, so an already-bloated
    cache file shrinks on load instead of re-bloating the process.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per token.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    max_tokens:
        Maximum number of distinct token addresses tracked.
    max_tokens_per_update:
        Maximum number of tokens accepted from one upstream snapshot.
    """

    def __init__(
        self,
        max_history: int = 120,
        *,
        max_tokens: int = _MAX_TRACKED_TOKENS,
        max_tokens_per_update: int = _MAX_TOKENS_PER_UPDATE,
    ) -> None:
        self._max_history = max_history
        self._max_tokens = max(1, max_tokens)
        self._max_tokens_per_update = max(1, max_tokens_per_update)
        # OrderedDict, most-recently-updated address last.
        self._price_histories: OrderedDict[str, deque[TimeSeriesPoint]] = OrderedDict()
        self._latest: BaseSnapshot | None = None
        self._last_updated: float | None = None

        # Overview time-series (for Base Trading Overview dashboard)
        self.volume_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.eth_price_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.trade_count_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _touch(self, addr: str) -> deque[TimeSeriesPoint]:
        """Return the history deque for ``addr``, creating and LRU-capping it.

        Marks ``addr`` as most-recently-used and evicts the oldest entries
        once the tracked-address budget is exceeded.
        """
        dq = self._price_histories.get(addr)
        if dq is None:
            dq = deque(maxlen=self._max_history)
            self._price_histories[addr] = dq
        else:
            self._price_histories.move_to_end(addr)

        evicted = 0
        while len(self._price_histories) > self._max_tokens:
            self._price_histories.popitem(last=False)
            evicted += 1
        if evicted:
            logger.debug(
                "Base token cache at capacity (%d); evicted %d "
                "least-recently-updated token(s)",
                self._max_tokens,
                evicted,
            )
        return dq

    def update(self, snapshot: BaseSnapshot) -> None:
        """Store latest snapshot and append price points to per-token histories.

        Each token's ``price_usd`` is recorded as a ``(timestamp, price)``
        pair keyed by lowercase token address.  At most
        ``max_tokens_per_update`` tokens are taken from the snapshot, and
        the total number of tracked addresses stays within ``max_tokens``.
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at

        tokens = snapshot.trending_tokens
        if len(tokens) > self._max_tokens_per_update:
            logger.warning(
                "Upstream snapshot carried %d tokens; truncating to %d",
                len(tokens),
                self._max_tokens_per_update,
            )
            tokens = tokens[: self._max_tokens_per_update]

        for token in tokens:
            addr = token.address.lower()
            self._touch(addr).append((snapshot.fetched_at, token.price_usd))

    def record_token(self, token: BaseToken, timestamp: float | None = None) -> None:
        """Record a single token price point outside of a full snapshot update.

        Useful for enrichment-only refreshes where a full snapshot is not
        available.
        """
        ts = timestamp or time.time()
        addr = token.address.lower()
        self._touch(addr).append((ts, token.price_usd))

    def get_price_history(self, token_address: str) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, price), ...]`` for a single token.

        Returns an empty list if the token has never been seen.
        """
        dq = self._price_histories.get(token_address.lower())
        if dq is None:
            return []
        return list(dq)

    def get_all_histories(self) -> dict[str, list[TimeSeriesPoint]]:
        """Return price histories for every tracked token."""
        return {addr: list(dq) for addr, dq in self._price_histories.items()}

    def get_latest(self) -> BaseSnapshot | None:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of distinct tokens being tracked."""
        return len(self._price_histories)

    # ------------------------------------------------------------------
    # Overview time-series
    # ------------------------------------------------------------------

    def record_overview_point(
        self,
        timestamp: float,
        total_volume: float | None,
        eth_price: float | None,
        trade_count: int | None,
    ) -> None:
        """Append a single overview data point to the three time-series.

        Called once per poll cycle by the manager when running in overview
        mode.

        Each series is recorded independently and ``None`` means "no
        reading this cycle" -- the point is skipped, not zero-filled.
        These deques are persisted to ``~/.maxpane/base_cache.json``, so a
        sentinel written here outlives the outage that produced it: it
        crushes the ETH sparkline's scale, and ``compute_volume_trend``
        reads a zero previous volume as "Rising" on the next successful
        cycle regardless of reality.
        """
        if total_volume is not None:
            self.volume_history.append((timestamp, float(total_volume)))
        if eth_price is not None:
            self.eth_price_history.append((timestamp, float(eth_price)))
        if trade_count is not None:
            self.trade_count_history.append((timestamp, float(trade_count)))

    def get_volume_history(self) -> list[TimeSeriesPoint]:
        """Return accumulated total-volume time-series."""
        return list(self.volume_history)

    def get_eth_price_history(self) -> list[TimeSeriesPoint]:
        """Return accumulated ETH price time-series."""
        return list(self.eth_price_history)

    def get_trade_count_history(self) -> list[TimeSeriesPoint]:
        """Return accumulated trade-count time-series."""
        return list(self.trade_count_history)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        File format::

            {
                "saved_at": <float>,
                "max_history": <int>,
                "histories": {
                    "<token_address>": [[ts, price], ...],
                    ...
                }
            }
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
            "histories": {
                addr: [list(pt) for pt in dq]
                for addr, dq in self._price_histories.items()
            },
            "overview_volume": [list(pt) for pt in self.volume_history],
            "overview_eth_price": [list(pt) for pt in self.eth_price_history],
            "overview_trade_count": [list(pt) for pt in self.trade_count_history],
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "Base token cache saved to %s (%d tokens)",
                path,
                len(self._price_histories),
            )
        except OSError as exc:
            logger.warning("Failed to save Base token cache: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def load_from_file(self, path: str) -> None:
        """Load previously saved history from a JSON file.

        Silently does nothing if the file is missing or corrupted.
        Existing in-memory data is replaced on successful load.

        Individual points are validated: anything unusable (``null``, a
        string, ``NaN``, a wrong-length entry, a negative price, a
        future-dated timestamp) is dropped and counted rather than
        raising, because every manager loads its cache in ``__init__``
        and one bad value used to abort MaxPane startup for every
        dashboard.
        """
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No Base token cache file to load (%s): %s", path, exc)
            return

        histories = payload.get("histories", {})
        if not isinstance(histories, dict):
            logger.warning(
                "Base token cache file %s has unexpected format, skipping", path
            )
            return

        loaded = 0
        skipped = 0
        now = time.time()

        # Apply the tracked-address cap on load as well, otherwise a cache
        # file that grew before the cap existed (or was tampered with)
        # re-bloats the process on every startup.  Keep the addresses with
        # the newest last sample and insert oldest-first so LRU order is
        # preserved.
        candidates = [
            (addr, points)
            for addr, points in histories.items()
            if isinstance(points, list)
        ]
        dropped_addrs = 0
        if len(candidates) > self._max_tokens:
            candidates.sort(key=lambda item: _last_timestamp(item[1]))
            dropped_addrs = len(candidates) - self._max_tokens
            candidates = candidates[-self._max_tokens :]
        else:
            candidates.sort(key=lambda item: _last_timestamp(item[1]))

        for addr, points in candidates:
            good, dropped = coerce_points(points, now=now)
            skipped += dropped
            dq: deque[TimeSeriesPoint] = deque(good, maxlen=self._max_history)
            self._price_histories[addr.lower()] = dq
            self._price_histories.move_to_end(addr.lower())
            loaded += 1

        # Guard against duplicate addresses differing only by case.
        while len(self._price_histories) > self._max_tokens:
            self._price_histories.popitem(last=False)
            dropped_addrs += 1

        if dropped_addrs:
            logger.warning(
                "Base token cache %s held more than %d tokens; dropped the "
                "%d least-recently-updated",
                path,
                self._max_tokens,
                dropped_addrs,
            )

        # Load overview time-series if present
        for key, target_deque in [
            ("overview_volume", self.volume_history),
            ("overview_eth_price", self.eth_price_history),
            ("overview_trade_count", self.trade_count_history),
        ]:
            series = payload.get(key, [])
            if isinstance(series, list):
                good, dropped = coerce_points(series, now=now)
                skipped += dropped
                target_deque.extend(good)

        if skipped:
            logger.warning(
                "Skipped %d unusable point(s) while loading Base token "
                "cache %s",
                skipped,
                path,
            )
        logger.info(
            "Loaded Base token cache from %s: %d tokens, up to %d points each",
            path,
            loaded,
            self._max_history,
        )
