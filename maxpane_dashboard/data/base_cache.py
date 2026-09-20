"""In-memory cache with time-series accumulation for Base chain token prices.

The ``BaseTokenCache`` accumulates per-token price histories over time so the
dashboard can render sparklines and trend indicators, plus three fixed
overview series for the Base Trading Overview dashboard.

Everything but ``update()``, the LRU bookkeeping and the named getters is
inherited from ``data/series_cache.SeriesCache``; see that module for the
persistence contract and for why ``record()`` drops ``None`` instead of
zero-filling.  The three overview deques are declared as ``SERIES`` and
carry an explicit ``key=``: they have always been written as
``overview_volume`` / ``overview_eth_price`` / ``overview_trade_count``,
and renaming either half would make every existing
``~/.maxpane/base_cache.json`` load its sparklines empty.

Thread safety: this module is designed for single-threaded asyncio use.
No locking is performed.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from typing import Any

from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken
from maxpane_dashboard.data.series_cache import (
    SeriesCache,
    SeriesSpec,
    TimeSeriesPoint,
)

logger = logging.getLogger(__name__)

__all__ = ["BaseTokenCache", "TimeSeriesPoint"]

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

# The persisted key order, oldest file first.  ``SeriesCache._payload``
# writes the declared series before ``extra_payload``; this file has
# always carried ``histories`` first, and a cache file whose keys
# reshuffle on every save is a diff nobody can read.
_PAYLOAD_KEY_ORDER = (
    "saved_at",
    "max_history",
    "histories",
    "overview_volume",
    "overview_eth_price",
    "overview_trade_count",
)


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


class BaseTokenCache(SeriesCache):
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

    SERIES = (
        SeriesSpec("volume_history", key="overview_volume"),
        SeriesSpec("eth_price_history", key="overview_eth_price"),
        SeriesSpec("trade_count_history", key="overview_trade_count"),
    )
    NOUN = "Base token cache"
    SIZE_NOUN = "tokens"

    volume_history: deque[TimeSeriesPoint]
    eth_price_history: deque[TimeSeriesPoint]
    trade_count_history: deque[TimeSeriesPoint]
    _latest: BaseSnapshot | None

    def __init__(
        self,
        max_history: int = 120,
        *,
        max_tokens: int = _MAX_TRACKED_TOKENS,
        max_tokens_per_update: int = _MAX_TOKENS_PER_UPDATE,
    ) -> None:
        super().__init__(max_history)
        self._max_tokens = max(1, max_tokens)
        self._max_tokens_per_update = max(1, max_tokens_per_update)
        # OrderedDict, most-recently-updated address last.
        self._price_histories: OrderedDict[str, deque[TimeSeriesPoint]] = OrderedDict()
        # Number of token histories the last load restored, or ``None``
        # when the load bailed out on a malformed ``histories`` value.
        self._loaded_tokens: int | None = None

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
        self._mark(snapshot)

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

        ``timestamp is None`` -- not a falsy ``timestamp`` -- is what
        means "stamp it now": epoch ``0.0`` is a timestamp like any
        other, and ``timestamp or time.time()`` silently replaced it with
        the wall clock, which is the one value a caller passing ``0.0``
        did not want.
        """
        ts = time.time() if timestamp is None else timestamp
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
        cycle regardless of reality.  ``SeriesCache.record`` is the
        repo-wide copy of that rule.
        """
        self.record("volume_history", timestamp, total_volume)
        self.record("eth_price_history", timestamp, eth_price)
        self.record("trade_count_history", timestamp, trade_count)

    def get_volume_history(self) -> list[TimeSeriesPoint]:
        """Return accumulated total-volume time-series."""
        return self.get_series("volume_history")

    def get_eth_price_history(self) -> list[TimeSeriesPoint]:
        """Return accumulated ETH price time-series."""
        return self.get_series("eth_price_history")

    def get_trade_count_history(self) -> list[TimeSeriesPoint]:
        """Return accumulated trade-count time-series."""
        return self.get_series("trade_count_history")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def extra_payload(self) -> dict[str, Any]:
        """The per-token histories; the three overview series are ``SERIES``."""
        return {
            "histories": {
                addr: [list(pt) for pt in dq]
                for addr, dq in self._price_histories.items()
            }
        }

    def _payload(self) -> dict[str, Any]:
        """The saved payload, in this file's historical key order::

            {
                "saved_at": <float>,
                "max_history": <int>,
                "histories": {
                    "<token_address>": [[ts, price], ...],
                    ...
                },
                "overview_volume": [[ts, usd], ...],
                "overview_eth_price": [[ts, usd], ...],
                "overview_trade_count": [[ts, trades], ...]
            }

        All six keys -- the previous version of this docstring listed
        only the first three, while the code wrote all six.  No version
        key: this file has never carried one, and an older MaxPane
        reading a new key would treat its own cache as a downgrade.

        The base writes the declared series before ``extra_payload``'s
        keys; this file has always led with ``histories``.  Nothing reads
        a JSON object's key order, but a save that reshuffles a user's
        file makes every backup diff unreadable for no gain.
        """
        payload = super()._payload()
        ordered = {k: payload.pop(k) for k in _PAYLOAD_KEY_ORDER if k in payload}
        # Anything unexpected still gets written rather than dropped.
        ordered.update(payload)
        return ordered

    def restore_extra(
        self,
        payload: dict[str, Any],
        *,
        path: str,
        now: float,
        max_age: float | None = None,
    ) -> int:
        """Rebuild the per-token histories, applying the tracked-address cap.

        The cap is applied on load as well as on update, otherwise a
        cache file that grew before the cap existed (or was tampered
        with) re-bloats the process on every startup.  The addresses with
        the newest last sample win, and they are inserted oldest-first so
        the LRU order survives the round trip.

        ``max_age`` is deliberately not forwarded: these histories have
        never been windowed on load, and starting now would silently
        shorten every user's restored sparkline (follow-up #42).
        """
        raw = payload.get("histories", {})
        if not isinstance(raw, dict):
            logger.warning(
                "%s file %s has unexpected format, skipping", self.NOUN, path
            )
            self._loaded_tokens = None
            return 0

        candidates = [
            (addr, points)
            for addr, points in raw.items()
            if isinstance(points, list)
        ]
        dropped_addrs = 0
        candidates.sort(key=lambda item: _last_timestamp(item[1]))
        if len(candidates) > self._max_tokens:
            dropped_addrs = len(candidates) - self._max_tokens
            candidates = candidates[-self._max_tokens :]

        series, skipped = self.coerce_keyed(dict(candidates), now=now)
        for addr, good in series.items():
            dq: deque[TimeSeriesPoint] = deque(good, maxlen=self._max_history)
            self._price_histories[addr.lower()] = dq
            self._price_histories.move_to_end(addr.lower())
        loaded = len(series)

        # Guard against duplicate addresses differing only by case.
        while len(self._price_histories) > self._max_tokens:
            self._price_histories.popitem(last=False)
            dropped_addrs += 1

        if dropped_addrs:
            logger.warning(
                "%s %s held more than %d tokens; dropped the "
                "%d least-recently-updated",
                self.NOUN,
                path,
                self._max_tokens,
                dropped_addrs,
            )

        self._loaded_tokens = loaded
        return skipped

    def _log_loaded(self, path: str, loaded: int) -> None:
        """The closing info line, in tokens rather than overview points."""
        if self._loaded_tokens is None:
            return
        logger.info(
            "Loaded %s from %s: %d tokens, up to %d points each",
            self.NOUN,
            path,
            self._loaded_tokens,
            self._max_history,
        )
