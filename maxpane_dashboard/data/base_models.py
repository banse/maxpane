"""Pydantic v2 models for Base chain token and pool data.

All models are frozen (immutable) and map to responses from Bankr,
DexScreener, and GeckoTerminal APIs after normalisation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Base token (DexScreener-enriched)
# ---------------------------------------------------------------------------

class BaseToken(BaseModel):
    """A token on Base chain with market data."""

    model_config = ConfigDict(frozen=True)

    address: str
    name: str
    symbol: str
    price_usd: float
    price_change_5m: float | None
    price_change_1h: float | None
    price_change_24h: float | None
    volume_24h: float
    market_cap: float
    fdv: float | None
    liquidity: float
    pair_address: str | None
    dex: str | None
    """DEX name, e.g. 'aerodrome', 'uniswap'."""
    created_at: str | int | None
    """Pool creation timestamp (ISO string, epoch ms int, or None)."""
    buys_24h: int = 0
    """Number of buy transactions in the last 24 hours."""
    sells_24h: int = 0
    """Number of sell transactions in the last 24 hours."""

    @classmethod
    def from_dexscreener_pair(cls, pair: dict[str, Any]) -> BaseToken:
        """Construct from a single DexScreener pair object."""
        base_token = pair.get("baseToken", {})
        price_change = pair.get("priceChange", {})
        volume = pair.get("volume", {})
        liquidity_data = pair.get("liquidity", {})

        txns = pair.get("txns", {})
        txns_24h = txns.get("h24", {})

        return cls(
            address=(base_token.get("address") or "").lower(),
            name=base_token.get("name", "Unknown"),
            symbol=base_token.get("symbol", "???"),
            price_usd=_safe_float(pair.get("priceUsd")),
            price_change_5m=_safe_float_or_none(price_change.get("m5")),
            price_change_1h=_safe_float_or_none(price_change.get("h1")),
            price_change_24h=_safe_float_or_none(price_change.get("h24")),
            volume_24h=_safe_float(volume.get("h24")),
            market_cap=_safe_float(pair.get("marketCap") or pair.get("mcap")),
            fdv=_safe_float_or_none(pair.get("fdv")),
            liquidity=_safe_float(liquidity_data.get("usd")),
            pair_address=pair.get("pairAddress"),
            dex=pair.get("dexId"),
            created_at=pair.get("pairCreatedAt"),
            buys_24h=_safe_int(txns_24h.get("buys")),
            sells_24h=_safe_int(txns_24h.get("sells")),
        )


# ---------------------------------------------------------------------------
# Trending pool (GeckoTerminal)
# ---------------------------------------------------------------------------

class TrendingPool(BaseModel):
    """A trending pool from GeckoTerminal."""

    model_config = ConfigDict(frozen=True)

    pool_address: str
    token_name: str
    token_symbol: str
    token_address: str
    price_usd: float
    volume_24h: float
    price_change_24h: float

    @classmethod
    def from_gecko_pool(
        cls,
        pool: dict[str, Any],
        token_map: dict[str, dict[str, Any]],
    ) -> TrendingPool | None:
        """Construct from a GeckoTerminal pool object with included token map.

        Returns ``None`` if the pool lacks a resolvable base token address.
        """
        attrs = pool.get("attributes", {})
        rels = pool.get("relationships", {})

        base_token_id = (rels.get("base_token", {}).get("data", {}).get("id", ""))
        base_token_entry = token_map.get(base_token_id, {})
        base_token_attrs = base_token_entry.get("attributes", base_token_entry)
        token_address = base_token_attrs.get("address", "")
        if not token_address:
            return None

        pct = attrs.get("price_change_percentage", {})
        vol = attrs.get("volume_usd", {})

        return cls(
            pool_address=attrs.get("address", ""),
            token_name=base_token_attrs.get("name") or attrs.get("name", "Unknown"),
            token_symbol=base_token_attrs.get("symbol", "???"),
            token_address=token_address.lower(),
            price_usd=_safe_float(attrs.get("base_token_price_usd")),
            volume_24h=_safe_float(vol.get("h24")),
            price_change_24h=_safe_float(pct.get("h24")),
        )


# ---------------------------------------------------------------------------
# Unified snapshot
# ---------------------------------------------------------------------------

class TokenLaunch(BaseModel):
    """A newly launched token on Base via Clanker or similar deployers."""

    model_config = ConfigDict(frozen=True)

    address: str
    name: str
    symbol: str
    deployer: str
    """Deployer identifier: ``'clanker'``, ``'bankr'``, ``'doppler'``, or ``'unknown'``."""
    created_at: int
    """Unix timestamp (seconds) of token creation."""
    age_seconds: int
    """Computed: ``now - created_at``."""
    initial_liquidity: float | None
    current_price: float | None
    price_change_5m: float | None
    market_cap: float | None
    volume_24h: float | None
    buy_count: int | None
    sell_count: int | None
    graduated: bool
    """Whether the token has reached Clanker's 'champagne' graduation threshold."""

    @classmethod
    def from_clanker_token(
        cls,
        token: dict[str, Any],
        *,
        market_data: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> TokenLaunch:
        """Construct from a raw Clanker API token object.

        Parameters
        ----------
        token:
            Raw token dict from the Clanker ``/api/tokens`` endpoint.
        market_data:
            Optional DexScreener pair data for enrichment.
        now:
            Current unix timestamp.  Defaults to ``time.time()``.
        """
        import time as _time

        if now is None:
            now = _time.time()

        address = (token.get("contract_address") or token.get("contractAddress") or "").lower()
        created_iso = token.get("created_at", "")
        created_ts = _parse_timestamp(created_iso)
        age = max(0, int(now - created_ts)) if created_ts else 0

        # Determine deployer from token metadata
        deployer = _detect_deployer(token)

        # Determine graduation status
        token_type = (token.get("type") or "").lower()
        graduated = token_type == "graduated" or bool(token.get("champagne"))

        # Extract market data from DexScreener pair if available
        current_price: float | None = None
        price_change_5m: float | None = None
        market_cap: float | None = None
        volume_24h: float | None = None
        buy_count: int | None = None
        sell_count: int | None = None
        initial_liquidity: float | None = None

        if market_data:
            current_price = _safe_float_or_none(market_data.get("priceUsd"))
            price_change = market_data.get("priceChange", {})
            price_change_5m = _safe_float_or_none(price_change.get("m5"))
            market_cap = _safe_float_or_none(
                market_data.get("marketCap") or market_data.get("mcap")
            )
            vol = market_data.get("volume", {})
            volume_24h = _safe_float_or_none(vol.get("h24"))
            liq = market_data.get("liquidity", {})
            initial_liquidity = _safe_float_or_none(liq.get("usd"))
            txns = market_data.get("txns", {})
            buys_data = txns.get("h24", txns.get("h1", {}))
            buy_count = _safe_int_or_none(buys_data.get("buys"))
            sell_count = _safe_int_or_none(buys_data.get("sells"))

        return cls(
            address=address,
            name=token.get("name", "Unknown"),
            symbol=token.get("symbol", "???"),
            deployer=deployer,
            created_at=created_ts,
            age_seconds=age,
            initial_liquidity=initial_liquidity,
            current_price=current_price,
            price_change_5m=price_change_5m,
            market_cap=market_cap,
            volume_24h=volume_24h,
            buy_count=buy_count,
            sell_count=sell_count,
            graduated=graduated,
        )


class TokenDetail(BaseModel):
    """Deep-dive data for a single token.

    Fetched on-demand when the user selects a token in the detail view.
    Combines DexScreener pair data with pool-level transaction counts
    and price history for charting.
    """

    model_config = ConfigDict(frozen=True)

    address: str
    name: str
    symbol: str
    price_usd: float
    price_change_5m: float | None
    price_change_1h: float | None
    price_change_24h: float | None
    volume_24h: float
    market_cap: float
    fdv: float | None
    liquidity: float
    pair_address: str | None
    dex: str | None
    created_at: str | int | None
    # Pool info
    base_token_symbol: str
    quote_token_symbol: str
    fee_tier: str | None
    # Transaction counts
    buys_24h: int
    sells_24h: int
    buys_1h: int
    sells_1h: int
    # Price history for chart
    price_history: list[tuple[float, float]]
    """List of ``(timestamp, price)`` tuples for sparkline rendering."""

    @classmethod
    def from_dexscreener_pair(cls, pair: dict[str, Any]) -> TokenDetail:
        """Construct from a single DexScreener pair object.

        Extracts pool-level fields (quote token, fee tier, transaction
        counts) that are not available on the simpler ``BaseToken`` model.
        """
        base_token = pair.get("baseToken", {})
        quote_token = pair.get("quoteToken", {})
        price_change = pair.get("priceChange", {})
        volume = pair.get("volume", {})
        liquidity_data = pair.get("liquidity", {})
        txns = pair.get("txns", {})
        txns_24h = txns.get("h24", {})
        txns_1h = txns.get("h1", {})

        return cls(
            address=(base_token.get("address") or "").lower(),
            name=base_token.get("name", "Unknown"),
            symbol=base_token.get("symbol", "???"),
            price_usd=_safe_float(pair.get("priceUsd")),
            price_change_5m=_safe_float_or_none(price_change.get("m5")),
            price_change_1h=_safe_float_or_none(price_change.get("h1")),
            price_change_24h=_safe_float_or_none(price_change.get("h24")),
            volume_24h=_safe_float(volume.get("h24")),
            market_cap=_safe_float(pair.get("marketCap") or pair.get("mcap")),
            fdv=_safe_float_or_none(pair.get("fdv")),
            liquidity=_safe_float(liquidity_data.get("usd")),
            pair_address=pair.get("pairAddress"),
            dex=pair.get("dexId"),
            created_at=pair.get("pairCreatedAt"),
            base_token_symbol=base_token.get("symbol", "???"),
            quote_token_symbol=quote_token.get("symbol", "???"),
            fee_tier=pair.get("labels", [None])[0] if pair.get("labels") else None,
            buys_24h=_safe_int(txns_24h.get("buys")),
            sells_24h=_safe_int(txns_24h.get("sells")),
            buys_1h=_safe_int(txns_1h.get("buys")),
            sells_1h=_safe_int(txns_1h.get("sells")),
            price_history=[],  # populated separately if OHLCV data is available
        )


class BaseSnapshot(BaseModel):
    """Unified snapshot for dashboard consumption."""

    model_config = ConfigDict(frozen=True)

    trending_tokens: tuple[BaseToken, ...]
    trending_pools: tuple[TrendingPool, ...]
    launches: tuple[TokenLaunch, ...]
    fetched_at: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float:
    """Convert a value to float, returning 0.0 on failure."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_float_or_none(value: Any) -> float | None:
    """Convert a value to float, returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int:
    """Convert a value to int, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _safe_int_or_none(value: Any) -> int | None:
    """Convert a value to int, returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_timestamp(value: Any) -> int:
    """Parse an ISO-8601 string or epoch number into a unix timestamp (seconds).

    Returns ``0`` if parsing fails.
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        # If value looks like milliseconds, convert to seconds
        v = int(value)
        return v // 1000 if v > 1e12 else v
    if isinstance(value, str) and value:
        try:
            from datetime import datetime, timezone

            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return 0
    return 0


def _detect_deployer(token: dict[str, Any]) -> str:
    """Detect the deployer from Clanker token metadata.

    Checks ``source``, ``deployer``, and ``description`` fields.
    """
    source = (token.get("source") or "").lower()
    if "bankr" in source:
        return "bankr"

    deployer_field = (token.get("deployer") or "").lower()
    description = (token.get("description") or "").lower()

    if "bankr" in deployer_field or "bankr" in description:
        return "bankr"
    if "doppler" in deployer_field or "doppler" in description:
        return "doppler"
    if "clanker" in deployer_field or "clanker" in description:
        return "clanker"

    # Default: tokens from the Clanker API are Clanker-deployed
    return "clanker"
