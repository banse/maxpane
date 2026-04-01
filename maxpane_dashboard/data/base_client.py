"""Async client for Base chain market data.

Integrates three upstream APIs:
- **Bankr** -- AI-powered trending token discovery (submit prompt, poll job)
- **DexScreener** -- token pair enrichment with market data
- **GeckoTerminal** -- trending pools on Base network

Uses httpx for non-blocking HTTP with manual exponential backoff retries,
following the same patterns as ``dashboard.data.client.GameDataClient``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

import httpx

from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken, TokenDetail, TokenLaunch, TrendingPool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry / rate-limit configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 15.0

_DEXSCREENER_BATCH_SIZE = 30
_DEXSCREENER_MIN_DELAY = 0.9  # 900 ms between requests
_GECKO_MIN_DELAY = 0.75  # 750 ms between requests

# ---------------------------------------------------------------------------
# Bankr API constants
# ---------------------------------------------------------------------------

_BANKR_API = "https://api.bankr.bot"
_BANKR_POLL_INTERVAL = 2.0  # seconds
_BANKR_MAX_POLLS = 60
_BANKR_PROMPT = (
    "List the top 20 trending tokens on Base chain right now. "
    "For each token include: name, symbol, price in USD, "
    "24h price change percent, 24h volume in USD, market cap in USD, "
    "and contract address. Format each as a numbered list."
)

# ---------------------------------------------------------------------------
# Address extraction regex (matches 0x followed by 40 hex chars)
# ---------------------------------------------------------------------------

_ADDRESS_RE = re.compile(r"(?:Contract(?:\s+Address)?|Address):\s*(0x[a-fA-F0-9]{40})", re.IGNORECASE)

# Fallback: parse symbols from bullet-point format like "• giza (giza)" or "1. TokenName ($SYM)"
_SYMBOL_RE = re.compile(r"[•\d]+\.?\s+.+?\((\$?[A-Za-z0-9_]+)\)")

_DEXSCREENER_SEARCH_API = "https://api.dexscreener.com/latest/dex/search"

# ---------------------------------------------------------------------------
# Clanker API
# ---------------------------------------------------------------------------

_CLANKER_API = "https://www.clanker.world/api/tokens"
_CLANKER_ENRICH_LIMIT = 10  # only DexScreener-enrich the N newest launches

# ---------------------------------------------------------------------------
# DexScreener / GeckoTerminal endpoints
# ---------------------------------------------------------------------------

_DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
_GECKO_API = "https://api.geckoterminal.com/api/v2"
_GECKO_TRADES_API = "https://api.geckoterminal.com/api/v2/networks/base/pools"


def _safe_trade_float(value: Any) -> float:
    """Convert a trade field to float, returning 0.0 on failure."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class BaseChainClient:
    """Fetches Base chain market data from Bankr, DexScreener, and GeckoTerminal.

    Parameters
    ----------
    bankr_api_key:
        API key for the Bankr agent API.  Falls back to the ``BANKR_API_KEY``
        environment variable if not supplied.
    alchemy_api_key:
        Optional Alchemy key for future RPC calls.  Falls back to
        ``ALCHEMY_API_KEY`` env var.
    http_client:
        Optional shared ``httpx.AsyncClient``.  If not provided one is
        created internally and closed on ``close()``.
    """

    def __init__(
        self,
        bankr_api_key: str | None = None,
        alchemy_api_key: str | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._bankr_api_key = bankr_api_key or os.getenv("BANKR_API_KEY", "")
        self._alchemy_api_key = alchemy_api_key or os.getenv("ALCHEMY_API_KEY", "")

        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None

        # Rate-limit bookkeeping (timestamps of last request per service)
        self._last_dex_request: float = 0.0
        self._last_gecko_request: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> BaseChainClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: retry helper
    # ------------------------------------------------------------------

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue an HTTP request with exponential-backoff retries.

        Retries on transport errors and 5xx status codes.
        """
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                if method == "POST":
                    resp = await self._client.post(url, headers=headers, json=json_body)
                else:
                    resp = await self._client.get(url, headers=headers)

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.StreamError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Request to %s failed (attempt %d/%d): %s -- retrying in %.1fs",
                        url,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Request to %s failed after %d attempts: %s",
                        url,
                        _MAX_RETRIES,
                        exc,
                    )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Internal: rate-limit helpers
    # ------------------------------------------------------------------

    async def _wait_dexscreener(self) -> None:
        """Enforce minimum delay between DexScreener requests."""
        elapsed = time.monotonic() - self._last_dex_request
        if elapsed < _DEXSCREENER_MIN_DELAY:
            await asyncio.sleep(_DEXSCREENER_MIN_DELAY - elapsed)
        self._last_dex_request = time.monotonic()

    async def _wait_gecko(self) -> None:
        """Enforce minimum delay between GeckoTerminal requests."""
        elapsed = time.monotonic() - self._last_gecko_request
        if elapsed < _GECKO_MIN_DELAY:
            await asyncio.sleep(_GECKO_MIN_DELAY - elapsed)
        self._last_gecko_request = time.monotonic()

    # ------------------------------------------------------------------
    # Bankr: submit prompt and poll for result
    # ------------------------------------------------------------------

    async def _bankr_submit_prompt(self, prompt: str) -> str:
        """Submit a prompt to Bankr and return the job ID."""
        if not self._bankr_api_key:
            raise RuntimeError("BANKR_API_KEY not configured")

        resp = await self._request_with_retry(
            "POST",
            f"{_BANKR_API}/agent/prompt",
            headers={
                "x-api-key": self._bankr_api_key,
                "Content-Type": "application/json",
            },
            json_body={"prompt": prompt},
        )
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("error", "Failed to submit Bankr prompt"))
        return data["jobId"]

    async def _bankr_poll_job(self, job_id: str) -> dict[str, Any]:
        """Poll a Bankr job until completion, failure, or timeout."""
        for _ in range(_BANKR_MAX_POLLS):
            resp = await self._request_with_retry(
                "GET",
                f"{_BANKR_API}/agent/job/{job_id}",
                headers={"x-api-key": self._bankr_api_key},
            )
            data = resp.json()
            status = data.get("status", "")

            if status == "completed":
                return data
            if status == "failed":
                raise RuntimeError(data.get("error", "Bankr job failed"))
            if status == "cancelled":
                raise RuntimeError("Bankr job cancelled")

            await asyncio.sleep(_BANKR_POLL_INTERVAL)

        raise TimeoutError("Bankr job timed out after polling")

    @staticmethod
    def parse_addresses_from_response(text: str) -> list[str]:
        """Extract unique token addresses from Bankr AI response text.

        Tries ``Contract Address: 0x...`` patterns first. Falls back to
        any raw ``0x`` + 40 hex char match.
        """
        seen: set[str] = set()
        addresses: list[str] = []
        for match in _ADDRESS_RE.finditer(text):
            addr = match.group(1).lower()
            if addr not in seen:
                seen.add(addr)
                addresses.append(addr)
        if addresses:
            return addresses

        # Fallback: any 0x address in the text
        for match in re.finditer(r"0x[a-fA-F0-9]{40}", text):
            addr = match.group(0).lower()
            if addr not in seen:
                seen.add(addr)
                addresses.append(addr)
        return addresses

    @staticmethod
    def parse_symbols_from_response(text: str) -> list[str]:
        """Extract token symbols from bullet-point Bankr response.

        Matches patterns like ``• giza (giza)`` or ``1. TokenName ($SYM)``.
        """
        seen: set[str] = set()
        symbols: list[str] = []
        for match in _SYMBOL_RE.finditer(text):
            sym = match.group(1).lstrip("$").upper()
            if sym not in seen and sym not in ("WETH", "ETH", "USDC", "USDT"):
                seen.add(sym)
                symbols.append(sym)
        return symbols

    async def search_token_by_symbol(self, symbol: str) -> BaseToken | None:
        """Search DexScreener for a token by symbol on Base chain."""
        try:
            resp = await self._request_with_retry("GET", f"{_DEXSCREENER_SEARCH_API}?q={symbol}")
            data = resp.json()
            pairs = data.get("pairs", [])
            # Filter to Base chain pairs
            for pair in pairs:
                if pair.get("chainId") == "base":
                    return BaseToken.from_dexscreener_pair(pair)
        except Exception as exc:
            logger.debug("DexScreener search for %s failed: %s", symbol, exc)
        return None

    # ------------------------------------------------------------------
    # DexScreener: batch enrichment
    # ------------------------------------------------------------------

    async def enrich_tokens(self, addresses: list[str]) -> list[BaseToken]:
        """Batch DexScreener enrichment for a list of token addresses.

        Addresses are chunked into batches of 30 with rate-limited
        requests.  Returns one ``BaseToken`` per unique address (best
        pair selected by keeping the first match).
        """
        if not addresses:
            return []

        chunks = [
            addresses[i : i + _DEXSCREENER_BATCH_SIZE]
            for i in range(0, len(addresses), _DEXSCREENER_BATCH_SIZE)
        ]

        seen: set[str] = set()
        tokens: list[BaseToken] = []

        for chunk in chunks:
            await self._wait_dexscreener()
            try:
                url = f"{_DEXSCREENER_API}/{','.join(chunk)}"
                resp = await self._request_with_retry("GET", url)
                data = resp.json()
                pair_list: list[dict[str, Any]] = (
                    data if isinstance(data, list) else data.get("pairs", [])
                )

                for pair in pair_list:
                    addr = (pair.get("baseToken", {}).get("address") or "").lower()
                    if not addr or addr in seen:
                        continue
                    seen.add(addr)
                    tokens.append(BaseToken.from_dexscreener_pair(pair))

            except Exception as exc:
                logger.warning("DexScreener batch enrichment failed: %s", exc)
                # Graceful degradation: continue with remaining batches
                continue

        return tokens

    # ------------------------------------------------------------------
    # GeckoTerminal: trending pools on Base
    # ------------------------------------------------------------------

    async def get_trending_pools(self) -> list[TrendingPool]:
        """Fetch trending pools on Base from GeckoTerminal."""
        await self._wait_gecko()
        try:
            url = f"{_GECKO_API}/networks/base/trending_pools?include=base_token&page=1"
            resp = await self._request_with_retry(
                "GET",
                url,
                headers={"Accept": "application/json"},
            )
            data = resp.json()
            pools_raw: list[dict[str, Any]] = data.get("data", [])
            included: list[dict[str, Any]] = data.get("included", [])

            # Build token lookup from included sideloaded data
            token_map: dict[str, dict[str, Any]] = {}
            for item in included:
                if item.get("type") == "token":
                    token_map[item["id"]] = item.get("attributes", {})

            pools: list[TrendingPool] = []
            seen: set[str] = set()

            for pool_data in pools_raw:
                pool = TrendingPool.from_gecko_pool(pool_data, token_map)
                if pool is None:
                    continue
                if pool.token_address in seen:
                    continue
                seen.add(pool.token_address)
                pools.append(pool)

            logger.info("GeckoTerminal: fetched %d trending pools on Base", len(pools))
            return pools

        except Exception as exc:
            logger.error("GeckoTerminal trending pools failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Token detail: on-demand deep-dive for a single token
    # ------------------------------------------------------------------

    async def get_token_detail(self, address: str) -> TokenDetail | None:
        """Fetch comprehensive data for a single token.

        Uses the DexScreener token endpoint for market data.  Selects the
        best pair (highest liquidity on Base chain) from the response.

        Parameters
        ----------
        address:
            Token contract address (``0x...``).

        Returns ``None`` if DexScreener has no data for this token.
        """
        await self._wait_dexscreener()
        try:
            url = f"{_DEXSCREENER_API}/{address}"
            resp = await self._request_with_retry("GET", url)
            data = resp.json()
            pair_list: list[dict[str, Any]] = (
                data if isinstance(data, list) else data.get("pairs", [])
            )

            if not pair_list:
                return None

            # Filter to Base chain and pick highest-liquidity pair
            base_pairs = [
                p for p in pair_list
                if (p.get("chainId") or "").lower() == "base"
            ]
            if not base_pairs:
                # Fall back to all pairs if none explicitly tagged "base"
                base_pairs = pair_list

            best_pair = max(
                base_pairs,
                key=lambda p: float(
                    (p.get("liquidity") or {}).get("usd") or 0
                ),
            )

            return TokenDetail.from_dexscreener_pair(best_pair)

        except Exception as exc:
            logger.error("Token detail fetch for %s failed: %s", address, exc)
            return None

    async def get_token_trades(
        self,
        pair_address: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Fetch recent trades for a token pair via GeckoTerminal.

        DexScreener does not expose a trades API, so we use:
        ``GET {_GECKO_TRADES_API}/{pool_address}/trades``

        Parameters
        ----------
        pair_address:
            The pool / pair contract address on Base.
        limit:
            Maximum number of trades to return (default 30).

        Returns a list of dicts with keys:
            ``timestamp``, ``type`` (buy/sell), ``price_usd``,
            ``amount_token``, ``amount_usd``, ``maker``.

        Returns an empty list on any failure (graceful degradation).
        """
        await self._wait_gecko()
        try:
            url = f"{_GECKO_TRADES_API}/{pair_address}/trades"
            resp = await self._request_with_retry(
                "GET",
                url,
                headers={"Accept": "application/json"},
            )
            data = resp.json()
            raw_trades: list[dict[str, Any]] = data.get("data", [])

            trades: list[dict[str, Any]] = []
            for trade_data in raw_trades[:limit]:
                attrs = trade_data.get("attributes", {})
                trades.append({
                    "timestamp": attrs.get("block_timestamp"),
                    "type": attrs.get("kind", "unknown"),
                    "price_usd": _safe_trade_float(
                        attrs.get("price_to_in_usd")
                        or attrs.get("price_from_in_usd")
                    ),
                    "amount_token": _safe_trade_float(
                        attrs.get("from_token_amount")
                        or attrs.get("to_token_amount")
                    ),
                    "amount_usd": _safe_trade_float(
                        attrs.get("volume_in_usd")
                    ),
                    "maker": attrs.get("tx_from_address", ""),
                })

            logger.info(
                "GeckoTerminal: fetched %d trades for pool %s",
                len(trades),
                pair_address,
            )
            return trades

        except Exception as exc:
            logger.warning(
                "GeckoTerminal trades for pool %s failed: %s",
                pair_address,
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Bankr + DexScreener: trending tokens
    # ------------------------------------------------------------------

    async def get_trending_tokens(self) -> list[BaseToken]:
        """Fetch trending tokens — fast path via DexScreener/GeckoTerminal.

        Uses GeckoTerminal trending pools to discover tokens, then
        enriches via DexScreener for full market data. This is instant
        (no polling). Bankr is NOT used here to avoid 60s+ delays.
        """
        try:
            # Get trending pool tokens from GeckoTerminal
            pools = await self.get_trending_pools()
            if not pools:
                logger.warning("No trending pools from GeckoTerminal")
                return []

            # Extract unique token addresses from pools
            seen: set[str] = set()
            addresses: list[str] = []
            for pool in pools:
                addr = pool.token_address.lower()
                if addr and addr not in seen:
                    seen.add(addr)
                    addresses.append(addr)

            if not addresses:
                return []

            logger.info("Trending: %d tokens from GeckoTerminal, enriching via DexScreener", len(addresses))
            return await self.enrich_tokens(addresses)

        except Exception as exc:
            logger.error("Trending tokens failed: %s", exc)
            return []

    async def get_trending_tokens_bankr(self) -> list[BaseToken]:
        """Fetch trending tokens via Bankr (SLOW — 30-90 seconds).

        Use as background enrichment, NOT for primary dashboard data.
        """
        try:
            job_id = await self._bankr_submit_prompt(_BANKR_PROMPT)
            result = await self._bankr_poll_job(job_id)

            response_text = result.get("response", "")
            if not response_text:
                return []

            addresses = self.parse_addresses_from_response(response_text)
            if addresses:
                logger.info("Bankr: extracted %d addresses", len(addresses))
                return await self.enrich_tokens(addresses)

            symbols = self.parse_symbols_from_response(response_text)
            if not symbols:
                return []

            tokens: list[BaseToken] = []
            for sym in symbols[:20]:
                await self._wait_dexscreener()
                token = await self.search_token_by_symbol(sym)
                if token:
                    tokens.append(token)
            return tokens

        except Exception as exc:
            logger.error("Bankr trending failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Clanker: recent token launches
    # ------------------------------------------------------------------

    async def get_clanker_launches(self, limit: int = 30) -> list[TokenLaunch]:
        """Fetch recent token launches from the Clanker API.

        Retrieves the newest tokens from
        ``GET https://www.clanker.world/api/tokens?sort=desc&page=1&type=all``
        and optionally enriches the most recent *_CLANKER_ENRICH_LIMIT*
        tokens with DexScreener market data.  The remaining tokens are
        returned without market enrichment to avoid rate-limit pressure.

        Parameters
        ----------
        limit:
            Maximum number of launches to return (default 30).
        """
        now = time.time()

        try:
            resp = await self._request_with_retry(
                "GET",
                f"{_CLANKER_API}?sort=desc&page=1&type=all",
            )
            data = resp.json()
            raw_tokens: list[dict[str, Any]] = data.get("data") or data.get("tokens") or (
                data if isinstance(data, list) else []
            )
        except Exception as exc:
            logger.error("Clanker API fetch failed: %s", exc)
            return []

        if not raw_tokens:
            return []

        # Deduplicate by address, keep order (newest first)
        seen: set[str] = set()
        unique_tokens: list[dict[str, Any]] = []
        for token in raw_tokens:
            addr = (token.get("contract_address") or token.get("contractAddress") or "").lower()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            unique_tokens.append(token)
            if len(unique_tokens) >= limit:
                break

        # Enrich the newest N tokens with DexScreener data
        enrich_count = min(len(unique_tokens), _CLANKER_ENRICH_LIMIT)
        enrich_addresses = [
            (t.get("contract_address") or t.get("contractAddress") or "").lower()
            for t in unique_tokens[:enrich_count]
        ]

        market_map: dict[str, dict[str, Any]] = {}
        if enrich_addresses:
            try:
                await self._wait_dexscreener()
                url = f"{_DEXSCREENER_API}/{','.join(enrich_addresses)}"
                dex_resp = await self._request_with_retry("GET", url)
                dex_data = dex_resp.json()
                pair_list: list[dict[str, Any]] = (
                    dex_data if isinstance(dex_data, list)
                    else dex_data.get("pairs") or []
                )
                for pair in pair_list:
                    addr = (pair.get("baseToken", {}).get("address") or "").lower()
                    if addr and addr not in market_map:
                        market_map[addr] = pair
            except Exception as exc:
                logger.warning("DexScreener enrichment for launches failed: %s", exc)

        # Build TokenLaunch models
        launches: list[TokenLaunch] = []
        for token in unique_tokens:
            addr = (token.get("contract_address") or token.get("contractAddress") or "").lower()
            md = market_map.get(addr)
            try:
                launches.append(TokenLaunch.from_clanker_token(token, market_data=md, now=now))
            except Exception as exc:
                logger.debug("Failed to parse Clanker token %s: %s", addr, exc)

        logger.info(
            "Clanker: fetched %d launches (%d enriched with market data)",
            len(launches),
            len(market_map),
        )
        return launches

    @staticmethod
    def get_launch_stats(launches: list[TokenLaunch]) -> dict[str, Any]:
        """Compute aggregate statistics over a list of token launches.

        Returns
        -------
        dict with keys:
            ``total_launches_1h`` -- launches created within the last hour.
            ``graduated_count`` -- number of graduated tokens.
            ``avg_age`` -- average age in seconds of all launches.
            ``launch_rate_per_hour`` -- estimated launches per hour based
            on the time span covered by the provided launches.
        """
        now = time.time()
        one_hour_ago = now - 3600

        total_1h = sum(1 for t in launches if t.created_at >= one_hour_ago)
        graduated_count = sum(1 for t in launches if t.graduated)
        avg_age = (sum(t.age_seconds for t in launches) / len(launches)) if launches else 0.0

        # Estimate launch rate from the time span of provided data
        if len(launches) >= 2:
            oldest_ts = min(t.created_at for t in launches)
            newest_ts = max(t.created_at for t in launches)
            span_hours = max((newest_ts - oldest_ts) / 3600, 1 / 3600)
            launch_rate = len(launches) / span_hours
        else:
            launch_rate = float(total_1h)

        return {
            "total_launches_1h": total_1h,
            "graduated_count": graduated_count,
            "avg_age": avg_age,
            "launch_rate_per_hour": round(launch_rate, 1),
        }

    # ------------------------------------------------------------------
    # GeckoTerminal: trending pools on Base (public, no key)
    # ------------------------------------------------------------------

    _GECKO_TRENDING = "https://api.geckoterminal.com/api/v2/networks/base/trending_pools"

    async def get_dexscreener_trending(self) -> list[BaseToken]:
        """Fetch trending tokens on Base via GeckoTerminal trending pools.

        Returns ``BaseToken`` objects sorted by 24h volume descending.
        Despite the method name (kept for backward compatibility), this
        now uses GeckoTerminal which provides richer data (buy/sell counts,
        volume, price change) than the DexScreener boosts endpoint.
        """
        try:
            resp = await self._request_with_retry(
                "GET",
                self._GECKO_TRENDING,
            )
            data = resp.json()
            pools = data.get("data", [])

            tokens: list[BaseToken] = []
            seen: set[str] = set()

            for pool in pools:
                attrs = pool.get("attributes", {})
                # Extract token name/symbol from pool name (format: "TOKEN / WETH")
                pool_name = attrs.get("name", "")
                parts = pool_name.split(" / ")
                token_symbol = parts[0].strip() if parts else "???"
                token_name = attrs.get("base_token_name", token_symbol)

                # Token address from relationships
                rels = pool.get("relationships", {})
                base_token_data = rels.get("base_token", {}).get("data", {})
                token_addr = base_token_data.get("id", "").replace("base_", "")
                if not token_addr or token_addr in seen:
                    continue
                seen.add(token_addr)

                # Parse numeric fields
                vol_24h = float(attrs.get("volume_usd", {}).get("h24", 0) or 0)
                price_change = float(attrs.get("price_change_percentage", {}).get("h24", 0) or 0)
                price_usd = float(attrs.get("base_token_price_usd", 0) or 0)
                reserve = float(attrs.get("reserve_in_usd", 0) or 0)
                txns = attrs.get("transactions", {}).get("h24", {})
                buys = int(txns.get("buys", 0) or 0)
                sells = int(txns.get("sells", 0) or 0)
                market_cap = float(attrs.get("market_cap_usd") or 0)
                fdv = float(attrs.get("fdv_usd") or 0)
                pool_addr = attrs.get("address", "")

                tokens.append(BaseToken(
                    address=token_addr,
                    name=token_name,
                    symbol=token_symbol,
                    price_usd=price_usd,
                    price_change_5m=None,
                    price_change_1h=None,
                    price_change_24h=price_change,
                    volume_24h=vol_24h,
                    liquidity=reserve / 2 if reserve else 0,
                    market_cap=market_cap or 0,
                    fdv=fdv or None,
                    pair_address=pool_addr,
                    dex=attrs.get("dex_id"),
                    created_at=None,
                    buys_24h=buys,
                    sells_24h=sells,
                ))

            tokens.sort(key=lambda t: t.volume_24h, reverse=True)
            logger.info("GeckoTerminal trending: fetched %d Base tokens", len(tokens))
            return tokens

        except Exception as exc:
            logger.error("GeckoTerminal trending fetch failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # ETH price on Base (via WETH pair)
    # ------------------------------------------------------------------

    async def get_eth_price(self) -> tuple[float, float]:
        """Fetch current ETH price and 24h change from DexScreener.

        Queries the WETH token on Base (address ``0x4200...0006``) and
        selects the pair with highest liquidity.

        Returns
        -------
        tuple[float, float]
            ``(price_usd, price_change_24h_pct)``.  Returns ``(0.0, 0.0)``
            on failure.
        """
        await self._wait_dexscreener()
        try:
            weth_address = "0x4200000000000000000000000000000000000006"
            resp = await self._request_with_retry(
                "GET",
                f"{_DEXSCREENER_API}/{weth_address}",
            )
            data = resp.json()
            pair_list: list[dict[str, Any]] = (
                data if isinstance(data, list) else data.get("pairs", [])
            )

            if not pair_list:
                return (0.0, 0.0)

            # Pick highest-liquidity pair
            best_pair = max(
                pair_list,
                key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
            )

            price_usd = _safe_trade_float(best_pair.get("priceUsd"))
            price_change = best_pair.get("priceChange", {})
            change_24h = _safe_trade_float(price_change.get("h24"))

            return (price_usd, change_24h)

        except Exception as exc:
            logger.error("ETH price fetch failed: %s", exc)
            return (0.0, 0.0)

    # ------------------------------------------------------------------
    # Base chain gas price
    # ------------------------------------------------------------------

    async def get_base_gas_price(self) -> float:
        """Fetch current gas price on Base via JSON-RPC ``eth_gasPrice``.

        Returns gas price in **gwei**.  Returns ``0.0`` on failure.
        """
        try:
            resp = await self._request_with_retry(
                "POST",
                "https://mainnet.base.org",
                json_body={
                    "jsonrpc": "2.0",
                    "method": "eth_gasPrice",
                    "params": [],
                    "id": 1,
                },
            )
            data = resp.json()
            hex_result = data.get("result", "0x0")
            gas_wei = int(hex_result, 16)
            return gas_wei / 1e9  # Convert wei to gwei

        except Exception as exc:
            logger.error("Base gas price fetch failed: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Unified snapshot
    # ------------------------------------------------------------------

    async def fetch_snapshot(self, *, remote_only: bool = False) -> BaseSnapshot:
        """Fetch all trending and launch data in one call.

        Parameters
        ----------
        remote_only:
            When ``True``, skip Bankr/GeckoTerminal/Clanker flows and use
            only DexScreener trending (boosted tokens).  Suitable for the
            Base Trading Overview dashboard where speed matters and Bankr
            polling is undesirable.  When ``False`` (default), existing
            behaviour is preserved.

        Runs data sources concurrently.  Each source degrades
        independently on failure.
        """
        if remote_only:
            # Lightweight path: DexScreener trending only
            async def _safe_dex_trending() -> list[BaseToken]:
                try:
                    return await self.get_dexscreener_trending()
                except Exception as exc:
                    logger.error("DexScreener trending fetch failed: %s", exc)
                    return []

            tokens = await _safe_dex_trending()

            return BaseSnapshot(
                trending_tokens=tuple(tokens),
                trending_pools=(),
                launches=(),
                fetched_at=time.time(),
            )

        # Default path: full Bankr + GeckoTerminal + Clanker flow
        async def _safe_trending_tokens() -> list[BaseToken]:
            try:
                return await self.get_trending_tokens()
            except Exception as exc:
                logger.error("Trending tokens fetch failed: %s", exc)
                return []

        async def _safe_trending_pools() -> list[TrendingPool]:
            try:
                return await self.get_trending_pools()
            except Exception as exc:
                logger.error("Trending pools fetch failed: %s", exc)
                return []

        async def _safe_launches() -> list[TokenLaunch]:
            try:
                return await self.get_clanker_launches()
            except Exception as exc:
                logger.error("Clanker launches fetch failed: %s", exc)
                return []

        tokens, pools, launches = await asyncio.gather(
            _safe_trending_tokens(),
            _safe_trending_pools(),
            _safe_launches(),
        )

        return BaseSnapshot(
            trending_tokens=tuple(tokens),
            trending_pools=tuple(pools),
            launches=tuple(launches),
            fetched_at=time.time(),
        )
