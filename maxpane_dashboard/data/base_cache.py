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
from collections import deque
from typing import Any

from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken

logger = logging.getLogger(__name__)

# Type alias for a single time-series data point: (epoch_seconds, price_usd)
TimeSeriesPoint = tuple[float, float]


class BaseTokenCache:
    """Caches Base chain token price histories for sparkline rendering.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per token.  At a 30-second
        poll interval, 120 samples covers 60 minutes.
    """

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        self._price_histories: dict[str, deque[TimeSeriesPoint]] = {}
        self._latest: BaseSnapshot | None = None
        self._last_updated: float | None = None

        # Overview time-series (for Base Trading Overview dashboard)
        self.volume_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.eth_price_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)
        self.trade_count_history: deque[TimeSeriesPoint] = deque(maxlen=max_history)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def update(self, snapshot: BaseSnapshot) -> None:
        """Store latest snapshot and append price points to per-token histories.

        Each token's ``price_usd`` is recorded as a ``(timestamp, price)``
        pair keyed by lowercase token address.
        """
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at

        for token in snapshot.trending_tokens:
            addr = token.address.lower()
            if addr not in self._price_histories:
                self._price_histories[addr] = deque(maxlen=self._max_history)
            self._price_histories[addr].append(
                (snapshot.fetched_at, token.price_usd)
            )

    def record_token(self, token: BaseToken, timestamp: float | None = None) -> None:
        """Record a single token price point outside of a full snapshot update.

        Useful for enrichment-only refreshes where a full snapshot is not
        available.
        """
        ts = timestamp or time.time()
        addr = token.address.lower()
        if addr not in self._price_histories:
            self._price_histories[addr] = deque(maxlen=self._max_history)
        self._price_histories[addr].append((ts, token.price_usd))

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
        total_volume: float,
        eth_price: float,
        trade_count: int,
    ) -> None:
        """Append a single overview data point to all three time-series.

        Called once per poll cycle by the manager when running in overview
        mode.
        """
        self.volume_history.append((timestamp, total_volume))
        self.eth_price_history.append((timestamp, eth_price))
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
        for addr, points in histories.items():
            if not isinstance(points, list):
                continue
            dq: deque[TimeSeriesPoint] = deque(maxlen=self._max_history)
            for pt in points:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    dq.append((float(pt[0]), float(pt[1])))
            self._price_histories[addr.lower()] = dq
            loaded += 1

        # Load overview time-series if present
        for key, target_deque in [
            ("overview_volume", self.volume_history),
            ("overview_eth_price", self.eth_price_history),
            ("overview_trade_count", self.trade_count_history),
        ]:
            series = payload.get(key, [])
            if isinstance(series, list):
                for pt in series:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        target_deque.append((float(pt[0]), float(pt[1])))

        logger.info(
            "Loaded Base token cache from %s: %d tokens, up to %d points each",
            path,
            loaded,
            self._max_history,
        )
