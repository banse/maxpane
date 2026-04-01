"""Lightweight ETH/USD price fetcher with in-memory TTL cache.

Uses the CoinGecko free ``/simple/price`` endpoint. Failures are
swallowed and logged -- the dashboard falls back to showing ETH-only
values when the price is unavailable (returned as ``0.0``).
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=ethereum&vs_currencies=usd"
)
_REQUEST_TIMEOUT = 10.0


class PriceClient:
    """Fetches ETH/USD price with a configurable TTL cache.

    Parameters
    ----------
    cache_seconds:
        How long a successful price lookup is considered fresh.
        Defaults to 300 (5 minutes).
    http_client:
        Optional pre-configured ``httpx.AsyncClient`` for testing.
    """

    def __init__(
        self,
        cache_seconds: int = 300,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cache_seconds = cache_seconds
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._cached_price: float = 0.0
        self._cached_at: float = 0.0

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def get_eth_usd(self) -> float:
        """Return the current ETH/USD price.

        Returns the cached value if it is still within the TTL window.
        On any failure, returns ``0.0`` so callers never need to handle
        exceptions from the price layer.
        """
        now = time.time()
        if self._cached_price > 0 and (now - self._cached_at) < self._cache_seconds:
            return self._cached_price

        try:
            resp = await self._client.get(_COINGECKO_URL)
            resp.raise_for_status()
            data = resp.json()
            price = float(data["ethereum"]["usd"])
            self._cached_price = price
            self._cached_at = now
            return price
        except Exception as exc:
            logger.warning("ETH price fetch failed, returning cached/zero: %s", exc)
            return self._cached_price
