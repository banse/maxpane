"""Off-chain market client for the FWA dashboard — Pool C sources only.

Four third-party HTTP contracts, all **keyless**, none of them load-bearing for
correctness:

===================  ==========================================================
DexScreener          ``$FWA`` spot price / FDV / liquidity / 24 h flow.  Exactly
                     one pair exists: the Uniswap **v4** ``FWA/ETH`` pool.
GeckoTerminal        hourly OHLCV for the sparkline (and pool stats, whose
                     ``market_cap_usd`` is a broken ``"0.0"`` — see below).
CoinGecko NFT        per-contract NFT floor prices.  **The weak link.**
DefiLlama            protocol fees / revenue, for the take-rate cross-check.
===================  ==========================================================

Nothing here is a dependency of the dashboard's correctness.  Every method
returns ``(value, availability_flag)`` and **never raises**: all four sources
dying at once degrades the sparkline, the USD conversions and the floor column,
and nothing else.

Traps this module exists to contain
-----------------------------------

1. **Floor coverage is partial and that fact is the product.**  CoinGecko covers
   only ~22 of the 38 collections with live positions, and the two largest
   weight buckets (Ten Thousand Tokens 49.08 %, Art Blocks Explorations
   18.99 % — ~68 % of pool weight combined) are **not** among them.  An unpriced
   collection is marked unpriced (:attr:`FloorQuote.floor_eth` is ``None``,
   :attr:`FloorQuote.source` says why); it is never defaulted to ``0`` and never
   dropped from the result.  Both of those would turn the Pull EV *band* into a
   confident lie — see :func:`maxpane_dashboard.analytics.fwa_ev.pull_ev_band`,
   whose ``lower_eth`` leg zeroes unknown floors precisely because this module
   tells the truth about which ones are unknown.  Feed it with
   :func:`floors_for_ev`, which **omits** unpriced collections rather than
   passing a zero.

2. **404 and 429 are different states.**  A 404 is permanent absence: CoinGecko
   has no record of the contract, and re-asking every 15 minutes just burns the
   rate limit, so it is cached for :data:`MISSING_TTL`.  A 429 is transient
   throttling: it keeps whatever value was previously known, marks it stale, and
   is retried on the next sweep.  Conflating the two would make a rate limit look
   like a permanently unlisted collection.

3. **Art Blocks floors are suppressed structurally, not by convention.**  One
   Art Blocks contract hosts many distinct collections with different floors
   (``0x942BC2d3…`` reports ``name() == "Art Blocks Explorations"`` while OpenSea
   resolves it to ``friendship-bracelets-by-alexis-andre``), so *any*
   per-contract floor there is false rather than merely imprecise.  Those two
   addresses are never requested over the network at all and always come back
   with ``floor_eth = None`` and :data:`ART_BLOCKS_NOTE`.

4. **CoinGecko must never touch the fast path.**  ``fetch_nft_floors()`` paces
   itself at :data:`COINGECKO_MIN_SPACING` seconds per call — a full 38-collection
   sweep takes ~100 s — and is a background job on a 15-minute cadence.  Hot-tier
   code calls :meth:`FWAMarketClient.cached_floors`, which performs no I/O
   whatsoever.

5. **GeckoTerminal's ``market_cap_usd`` is the string ``"0.0"``** on this pool
   and is unusable.  Use DexScreener's ``fdv``.  :func:`parse_pool_stats` drops
   it to ``None`` so it cannot be rendered as a market cap of zero.

6. **DefiLlama ``/tvl/{slug}`` returns a bare number, not JSON.**  And its TVL
   ($3.2 M) diverges sharply from the core contract's real ETH balance
   (2,340–2,551 ETH); they measure different things.  **Prefer the on-chain
   balance always** — DefiLlama is a cross-check, never the TVL display source.

7. **OpenSea is opportunistic only.**  ``/collections/{slug}/stats`` answers 200
   without a key for CDN-popular slugs and 401 for others, unpredictably.  A 401
   is a *silent miss*: not an error, not a degraded flag, never a dependency.

8. **The pool is ~10 days old** (created 2026-07-16), so hourly OHLCV tops out
   near 100 candles and a requested window may simply not exist yet.  A short
   series is normal, not a failure.

References: ``docs/fwa_technical_findings.md`` §9 (payload shapes), §10 (the
floor coverage table), §11 (rate limits and TTLs), §12.2 item 11 (OpenSea).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoints — keyless, every one of them.  No Alchemy, no OpenSea key, no
# Etherscan key, no Reservoir (DNS is gone).
# ---------------------------------------------------------------------------

FWA_TOKEN_ADDRESS = "0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845"
"""$FWA ERC-20.  DexScreener returns exactly one pair for it."""

FWA_POOL_ID = "0x230ecd3c25b44af30db59c15f70df7794eb13f67a200f230b7400daa96fe804d"
"""Uniswap **v4 poolId** — a 32-byte pool identifier, **not** a contract address.

Do not ``eth_getCode`` it.  DexScreener reports it as ``pairAddress`` and
GeckoTerminal accepts it directly in the pool path; both are fine, but nothing
on-chain lives there.
"""

DEXSCREENER_TOKENS_API = "https://api.dexscreener.com/latest/dex/tokens"
GECKO_API = "https://api.geckoterminal.com/api/v2"
GECKO_NETWORK = "eth"
COINGECKO_NFT_API = "https://api.coingecko.com/api/v3/nfts"
DEFILLAMA_FEES_API = "https://api.llama.fi/summary/fees"
DEFILLAMA_TVL_API = "https://api.llama.fi/tvl"
DEFILLAMA_SLUG = "fake-world-assets"
OPENSEA_STATS_API = "https://api.opensea.io/api/v2/collections"

# ---------------------------------------------------------------------------
# Pacing.  Mirrors the ``_wait_dexscreener`` / ``_wait_gecko`` helpers in
# ``maxpane_dashboard/data/base_client.py`` (same values, same shape); CoinGecko
# NFT gets its own, far harsher budget from findings §11.
# ---------------------------------------------------------------------------

DEXSCREENER_MIN_DELAY = 0.9
GECKO_MIN_DELAY = 0.75
COINGECKO_MIN_SPACING = 2.5
"""Findings §11: ``>= 2.5 s`` between CoinGecko NFT calls **and expect 429s anyway**.

A 38-collection sweep took 203 s live.  This is why floors are a background job.
"""

COINGECKO_COOLDOWN_CAP = 60.0
"""Ceiling on the ``Retry-After`` pause honoured mid-sweep after a 429.

The observed header value is 60.  Waiting it out once is far cheaper than the
alternative: a measured sweep at the mandated 2.5 s spacing still drew **26
consecutive 429s** in one run, which is 26 requests spent deepening a throttle
instead of collecting floors.
"""

COINGECKO_MAX_CONSECUTIVE_429 = 2
"""Abort the sweep after this many 429s in a row.

One cooldown is worth trying; a second consecutive 429 means the budget is gone
for now.  The untouched collections are **parked as retryable**, not marked
missing — the next sweep picks them up, and the coverage badge keeps counting
them as throttled rather than absent.  Hammering on would neither collect a
floor nor tell the truth any better.
"""

# ---------------------------------------------------------------------------
# TTLs (findings §11)
# ---------------------------------------------------------------------------

MARKET_TTL = 30.0
"""DexScreener / GeckoTerminal — 30 s is plenty."""

DEFILLAMA_TTL = 60.0
"""DefiLlama is daily-granularity; 60 s is generous."""

FLOOR_TTL = 900.0
"""15 min: how often the background floor sweep re-asks CoinGecko."""

FLOOR_MAX_AGE = 6 * 3600.0
"""How long a floor stays *usable* once stale.

Floors are cached for hours on purpose.  Between :data:`FLOOR_TTL` and this, a
quote is still served but is relabelled ``source="cached"`` and flagged
:attr:`FloorQuote.stale`; past it the collection reverts to unpriced rather than
showing a number nobody can vouch for.
"""

MISSING_TTL = 24 * 3600.0
"""A CoinGecko 404 is permanent absence.  Cache the negative for a day instead of
re-spending 2.5 s of the rate-limit budget on it every sweep.
"""

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Art Blocks suppression
# ---------------------------------------------------------------------------

ART_BLOCKS_CONTRACTS: frozenset[str] = frozenset(
    {
        "0x942bc2d3e7a589fe5bd4a5c6ef9727dfd82f5c8a",  # "Art Blocks Explorations"
        "0xab00000000002ade39f58f9d8278a31574ffbe77",  # Art Blocks (newer engine)
    }
)
"""Multi-collection contracts.  Both hold live FWA positions (18.99 % and 0.07 %
of draw weight); neither has a meaningful per-contract floor.
"""

ART_BLOCKS_NOTE = "multi-collection contract — floor not meaningful"

# Floor sources, matching ``CollectionOdds.floor_source`` in ``fwa_models``.
SOURCE_COINGECKO = "coingecko"
SOURCE_OPENSEA = "opensea"
SOURCE_CACHED = "cached"
SOURCE_MISSING = "missing"
SOURCE_SUPPRESSED = "suppressed"

# Fetch outcomes.  Finer-grained than ``floor_source`` on purpose: the odds board
# only needs to know a row is unpriced, but the sweep scheduler and the coverage
# badge need to know *why*, and "permanently absent" must not read the same as
# "throttled, try again in a minute".
STATUS_OK = "ok"
STATUS_CACHED = "cached"
STATUS_MISSING = "missing"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_SUPPRESSED = "suppressed"
STATUS_ERROR = "error"

_RETRYABLE_STATUSES = frozenset({STATUS_RATE_LIMITED, STATUS_ERROR})

_NOTE_MISSING = "no CoinGecko listing for this contract"
_NOTE_RATE_LIMITED = "rate limited — retry pending"
_NOTE_DEFERRED = "sweep deferred — rate limit budget exhausted"
_NOTE_STALE = "cached floor — refresh pending"
_NOTE_ERROR = "floor lookup failed"


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FloorQuote:
    """One collection's floor lookup result — including the failures.

    ``floor_eth is None`` means *unpriced*, always.  It is never ``0.0`` as a
    stand-in, because a zero floor would flow straight into the Pull EV upper
    leg and read as "this collection is worthless" rather than "nobody knows".

    * ``source`` is the widget-facing label, one of the five strings
      ``CollectionOdds.floor_source`` accepts:
      ``coingecko`` | ``opensea`` | ``cached`` | ``missing`` | ``suppressed``.
    * ``status`` is the operational outcome and is strictly finer:
      ``ok`` | ``cached`` | ``missing`` | ``rate_limited`` | ``suppressed`` |
      ``error``.  A rate-limited collection with no prior value reports
      ``source="missing"`` (the row genuinely has no floor to draw) but
      ``status="rate_limited"``, so the sweep retries it and the coverage badge
      counts it apart from the hard 404s.
    * ``note`` is human-facing and always says which of those it was.
    """

    address: str
    floor_eth: float | None = None
    floor_usd: float | None = None
    source: str = SOURCE_MISSING
    status: str = STATUS_MISSING
    note: str = ""
    name: str | None = None
    fetched_at: float = 0.0
    stale: bool = False

    @property
    def priced(self) -> bool:
        """True when a number exists that a widget may render."""
        return self.floor_eth is not None

    @property
    def retryable(self) -> bool:
        """True when the miss is transient and worth another call next sweep."""
        return self.status in _RETRYABLE_STATUSES

    def as_dict(self) -> dict[str, Any]:
        """Plain-primitive form, for persistence by WP-9's cache."""
        return {
            "address": self.address,
            "floor_eth": self.floor_eth,
            "floor_usd": self.floor_usd,
            "source": self.source,
            "status": self.status,
            "note": self.note,
            "name": self.name,
            "fetched_at": self.fetched_at,
            "stale": self.stale,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> FloorQuote:
        """Rebuild from :meth:`as_dict`, tolerating missing/extra keys."""
        return cls(
            address=str(raw.get("address", "")).lower(),
            floor_eth=_opt_float(raw.get("floor_eth")),
            floor_usd=_opt_float(raw.get("floor_usd")),
            source=str(raw.get("source", SOURCE_MISSING)),
            status=str(raw.get("status", STATUS_MISSING)),
            note=str(raw.get("note", "")),
            name=raw.get("name") or None,
            fetched_at=float(raw.get("fetched_at") or 0.0),
            stale=bool(raw.get("stale", False)),
        )


def _opt_float(value: Any) -> float | None:
    """Float, or ``None`` — never a silent ``0.0`` for a missing input."""
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """The ``Retry-After`` header in seconds, when it is a plain number.

    CoinGecko sends ``retry-after: 60`` alongside its 429.  HTTP-date form is
    not attempted: the caller falls back to its own pacing rather than guessing.
    """
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _pos_float(value: Any) -> float | None:
    """Like :func:`_opt_float` but treats non-positive as absent.

    Used for prices and floors, where ``0`` upstream means "no data" rather than
    "free" (GeckoTerminal's ``market_cap_usd = "0.0"`` is the canonical case).
    """
    out = _opt_float(value)
    if out is None or out <= 0.0:
        return None
    return out


# ---------------------------------------------------------------------------
# Pure parsers.  Separated from the client so every payload shape is testable
# from a recorded fixture with no client, no clock and no transport at all.
# ---------------------------------------------------------------------------


def parse_dexscreener(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Parse a DexScreener ``/latest/dex/tokens/{addr}`` body.

    Returns ``None`` when the body carries no pair — an empty ``pairs`` list, a
    ``null`` ``pairs``, or a missing key.  That is *unavailable*, not a zeroed
    market: a price of 0 would propagate into every USD conversion on the
    dashboard.
    """
    pairs = payload.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        return None
    pair = pairs[0]
    if not isinstance(pair, Mapping):
        return None

    liquidity = pair.get("liquidity") or {}
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    h24 = txns.get("h24") or {}
    change = pair.get("priceChange") or {}

    return {
        "chain_id": pair.get("chainId"),
        "dex_id": pair.get("dexId"),
        "labels": list(pair.get("labels") or ()),
        "pool_id": pair.get("pairAddress"),
        "price_usd": _pos_float(pair.get("priceUsd")),
        "price_native_eth": _pos_float(pair.get("priceNative")),
        "fdv_usd": _pos_float(pair.get("fdv")),
        "liquidity_usd": _opt_float(liquidity.get("usd")),
        "liquidity_base": _opt_float(liquidity.get("base")),
        "liquidity_quote_eth": _opt_float(liquidity.get("quote")),
        "volume_24h_usd": _opt_float(volume.get("h24")),
        "buys_24h": int(h24.get("buys") or 0),
        "sells_24h": int(h24.get("sells") or 0),
        "price_change_24h_pct": _opt_float(change.get("h24")),
        "pair_created_at_ms": int(pair.get("pairCreatedAt") or 0),
    }


def parse_ohlcv(payload: Mapping[str, Any]) -> list[list[float]]:
    """Parse GeckoTerminal OHLCV into ``[[ts, close], …]`` **oldest first**.

    The API returns ``data.attributes.ohlcv_list`` as bare
    ``[ts, open, high, low, close, volume]`` arrays, **newest first**.  Plotting
    that unreversed draws the chart backwards, so the order is normalised here
    once rather than at every call site.

    Malformed candles are skipped rather than raising; a short list is returned
    as-is.  The pool is only days old, so "fewer candles than asked for" is the
    normal case.
    """
    data = payload.get("data") or {}
    attrs = data.get("attributes") or {} if isinstance(data, Mapping) else {}
    raw = attrs.get("ohlcv_list") or []
    if not isinstance(raw, list):
        return []

    out: list[list[float]] = []
    for candle in raw:
        if not isinstance(candle, Sequence) or isinstance(candle, str | bytes):
            continue
        if len(candle) < 5:
            continue
        ts = _opt_float(candle[0])
        close = _opt_float(candle[4])
        if ts is None or close is None:
            continue
        out.append([int(ts), close])

    out.sort(key=lambda point: point[0])
    return out


def parse_pool_stats(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Parse a GeckoTerminal ``/pools/{poolId}`` body.

    ``market_cap_usd`` comes back as the string ``"0.0"`` for this pool and is
    dropped to ``None`` here — findings §9.2.  Rendering it would show a $0
    market cap next to a $27 M FDV.  DexScreener's ``fdv`` is the market-cap
    source.
    """
    data = payload.get("data") or {}
    if not isinstance(data, Mapping):
        return None
    attrs = data.get("attributes") or {}
    if not isinstance(attrs, Mapping) or not attrs:
        return None

    changes = attrs.get("price_change_percentage") or {}
    return {
        "name": attrs.get("name"),
        "price_usd": _pos_float(attrs.get("base_token_price_usd")),
        "price_native_eth": _pos_float(attrs.get("base_token_price_native_currency")),
        "fdv_usd": _pos_float(attrs.get("fdv_usd")),
        # Always None in practice: "0.0" upstream.  Never fall back to fdv here —
        # the caller should reach for DexScreener explicitly, not be handed a
        # substitute under the market-cap name.
        "market_cap_usd": _pos_float(attrs.get("market_cap_usd")),
        "market_cap_unavailable": _pos_float(attrs.get("market_cap_usd")) is None,
        "price_change_24h_pct": _opt_float(changes.get("h24")),
        "pool_created_at": attrs.get("pool_created_at"),
    }


def parse_coingecko_floor(address: str, payload: Mapping[str, Any], *, now: float) -> FloorQuote:
    """Turn a CoinGecko NFT 200 body into a :class:`FloorQuote`.

    A 200 with no usable ``floor_price.native_currency`` is *not* an ``ok`` with
    a zero floor — it degrades to ``missing``.
    """
    floor = payload.get("floor_price") or {}
    native = _pos_float(floor.get("native_currency")) if isinstance(floor, Mapping) else None
    usd = _pos_float(floor.get("usd")) if isinstance(floor, Mapping) else None
    if native is None:
        return FloorQuote(
            address=address,
            source=SOURCE_MISSING,
            status=STATUS_MISSING,
            note="CoinGecko returned no floor price for this contract",
            name=payload.get("name") or None,
            fetched_at=now,
        )
    return FloorQuote(
        address=address,
        floor_eth=native,
        floor_usd=usd,
        source=SOURCE_COINGECKO,
        status=STATUS_OK,
        name=payload.get("name") or None,
        fetched_at=now,
    )


def parse_defillama_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Parse one ``/summary/fees/{slug}?dataType=…`` body."""
    chart = payload.get("totalDataChart") or []
    points: list[list[float]] = []
    if isinstance(chart, list):
        for point in chart:
            if isinstance(point, Sequence) and not isinstance(point, str | bytes) and len(point) >= 2:
                ts = _opt_float(point[0])
                val = _opt_float(point[1])
                if ts is not None and val is not None:
                    points.append([int(ts), val])
    return {
        "name": payload.get("name"),
        "slug": payload.get("slug"),
        "category": payload.get("category"),
        "chains": list(payload.get("chains") or ()),
        "total_24h": _opt_float(payload.get("total24h")),
        "total_7d": _opt_float(payload.get("total7d")),
        "total_30d": _opt_float(payload.get("total30d")),
        "total_all_time": _opt_float(payload.get("totalAllTime")),
        "change_1d": _opt_float(payload.get("change_1d")),
        "chart": points,
    }


def parse_defillama_tvl(body: str) -> float | None:
    """Parse ``/tvl/{slug}``, which answers with a **bare number, not JSON**.

    ``json.loads`` on it yields a float, and any code doing ``response["tvl"]``
    raises.  A JSON object is still accepted here in case the endpoint ever
    grows one.

    The value is a **cross-check only**.  DefiLlama's TVL sits far below the
    core contract's real ETH balance; ``eth_getBalance(core)`` is the number the
    dashboard shows.
    """
    text = (body or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return _opt_float(text)
    if isinstance(parsed, int | float):
        return float(parsed)
    if isinstance(parsed, Mapping):
        return _opt_float(parsed.get("tvl"))
    return None


# ---------------------------------------------------------------------------
# Coverage reporting — the honest accounting of the floor gap
# ---------------------------------------------------------------------------


def floors_for_ev(quotes: Mapping[str, FloorQuote]) -> dict[str, float]:
    """The ``floors_eth`` mapping :func:`…fwa_ev.pull_ev_band` expects.

    **Priced collections only.**  Unpriced ones are *omitted* — never present
    with a ``0.0``.  ``pull_ev_band`` reads a missing key as "unknown" and splits
    the band on it (zeroed in ``lower_eth``, excluded from the ``max()`` in
    ``best_eth``); a literal zero would instead assert the collection is
    worthless and silently collapse the band's upper leg onto the sell-back
    value for the wrong reason.
    """
    return {
        addr.lower(): quote.floor_eth
        for addr, quote in quotes.items()
        if quote.floor_eth is not None
    }


def coverage_summary(
    quotes: Mapping[str, FloorQuote],
    weight_shares: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Count exactly what is and is not priced — the coverage badge's input.

    ``weight_shares`` maps address → ``weight_share_pct``.  The 38 live shares
    sum to **100.000001**, not 100.0 (they are rounded to 6 dp upstream), so the
    priced percentage is computed against the *observed* total rather than
    against a hardcoded 100 — no exact-100 assumption anywhere.

    Returns ``priced`` / ``total`` plus the per-reason breakdown, because "16
    unpriced" splits into hard 404s, throttled retries and deliberately
    suppressed multi-collection contracts, and those three deserve different
    words in the UI.
    """
    total = len(quotes)
    priced = missing = rate_limited = suppressed = errors = cached = 0
    for quote in quotes.values():
        if quote.status == STATUS_SUPPRESSED:
            suppressed += 1
        elif quote.status == STATUS_RATE_LIMITED:
            rate_limited += 1
        elif quote.status == STATUS_MISSING:
            missing += 1
        elif quote.status == STATUS_ERROR:
            errors += 1
        if quote.status == STATUS_CACHED:
            cached += 1
        if quote.priced:
            priced += 1

    weight_priced_pct = 0.0
    weight_total = 0.0
    if weight_shares:
        weight_total = sum(float(v) for v in weight_shares.values())
        if weight_total > 0:
            weight_priced = sum(
                float(weight_shares.get(addr, 0.0))
                for addr, quote in quotes.items()
                if quote.priced
            )
            weight_priced_pct = 100.0 * weight_priced / weight_total

    summary: dict[str, Any] = {
        "total": total,
        "priced": priced,
        "unpriced": total - priced,
        "cached": cached,
        "missing": missing,
        "rate_limited": rate_limited,
        "suppressed": suppressed,
        "errors": errors,
        "weight_priced_pct": weight_priced_pct,
        "weight_unpriced_pct": (100.0 - weight_priced_pct) if weight_shares else 0.0,
    }
    summary["caveat"] = _coverage_caveat(summary, bool(weight_shares))
    return summary


def _coverage_caveat(summary: Mapping[str, Any], has_weights: bool) -> str:
    """One sentence a widget can render verbatim under the EV band."""
    base = f"floor available for {summary['priced']} of {summary['total']} collections"
    if has_weights:
        base += f"; {summary['weight_unpriced_pct']:.1f}% of pool weight uncovered"
    return base


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FWAMarketClient:
    """Keyless off-chain client for $FWA market data and NFT floors.

    Every public fetch returns ``(value, available)`` and swallows every
    exception.  ``available=False`` means "this source could not answer"; it
    never means "the answer is zero".

    Parameters
    ----------
    http_client:
        Optional shared ``httpx.AsyncClient``.  One is created (and closed on
        :meth:`close`) if not supplied.
    clock / sleep:
        Injectable monotonic clock and async sleep.  Tests drive a fake pair so
        the ``>= 2.5 s`` CoinGecko spacing is *asserted* rather than *waited
        out* — the whole suite runs with no wall-clock delay and no network.
    floor_ttl / floor_max_age / missing_ttl:
        Floor cache tiers; see :data:`FLOOR_TTL`, :data:`FLOOR_MAX_AGE` and
        :data:`MISSING_TTL`.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        wall_clock: Callable[[], float] | None = None,
        floor_ttl: float = FLOOR_TTL,
        floor_max_age: float = FLOOR_MAX_AGE,
        missing_ttl: float = MISSING_TTL,
        coingecko_min_spacing: float = COINGECKO_MIN_SPACING,
        coingecko_cooldown_cap: float = COINGECKO_COOLDOWN_CAP,
        coingecko_max_consecutive_429: int = COINGECKO_MAX_CONSECUTIVE_429,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None

        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        # Wall clock for cache timestamps; defaults to the monotonic clock when a
        # fake one is injected so tests get a single consistent timeline.
        self._wall_clock = wall_clock or (time.time if clock is None else self._clock)

        self._floor_ttl = floor_ttl
        self._floor_max_age = floor_max_age
        self._missing_ttl = missing_ttl
        self._cg_spacing = coingecko_min_spacing
        self._cg_cooldown_cap = coingecko_cooldown_cap
        self._cg_max_consecutive_429 = coingecko_max_consecutive_429
        # One-shot override of the CoinGecko spacing, armed by a 429's
        # Retry-After and consumed by the next call's pacing.
        self._cg_next_min_delay: float | None = None

        self._last_dex = float("-inf")
        self._last_gecko = float("-inf")
        self._last_coingecko = float("-inf")

        self._floor_cache: dict[str, FloorQuote] = {}
        self._market_cache: tuple[float, dict[str, Any]] | None = None
        self._fees_cache: tuple[float, dict[str, Any]] | None = None

        # Observability: how many calls each source actually received, and
        # whether the last floor sweep gave up early on the rate limit.
        self.request_counts: dict[str, int] = {}
        self.sweep_aborted: bool = False

    # -- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> FWAMarketClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- internals ---------------------------------------------------------

    async def _pace(self, attr: str, min_delay: float) -> None:
        """Enforce a minimum gap since the last call to one service.

        Same shape as ``base_client._wait_dexscreener`` / ``_wait_gecko``, with
        the clock and sleep injected so pacing is observable in tests.
        """
        last = getattr(self, attr)
        elapsed = self._clock() - last
        if elapsed < min_delay:
            await self._sleep(min_delay - elapsed)
        setattr(self, attr, self._clock())

    async def _get(
        self,
        url: str,
        *,
        source: str,
        retry_on_5xx: bool = True,
    ) -> httpx.Response | None:
        """GET with bounded retries.  Returns ``None`` only on transport failure.

        A non-2xx **response** is returned to the caller: 404 and 429 carry
        meaning here and must not be flattened into "it broke".  Only 5xx and
        transport errors are retried.
        """
        self.request_counts[source] = self.request_counts.get(source, 0) + 1
        last_error: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(url)
            except Exception as exc:  # httpx transport errors, and anything else
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    await self._sleep(_BACKOFF_SECONDS[attempt])
                    continue
                logger.warning("%s: GET %s failed after %d attempts: %s", source, url, _MAX_RETRIES, exc)
                return None
            if retry_on_5xx and resp.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                await self._sleep(_BACKOFF_SECONDS[attempt])
                continue
            return resp
        logger.warning("%s: GET %s exhausted retries: %s", source, url, last_error)
        return None

    @staticmethod
    def _json(resp: httpx.Response) -> Any | None:
        try:
            return resp.json()
        except Exception:
            try:
                return json.loads(resp.text)
            except Exception:
                return None

    # -- 1. DexScreener ----------------------------------------------------

    async def fetch_fwa_market(self, *, force: bool = False) -> tuple[dict[str, Any] | None, bool]:
        """$FWA spot market from DexScreener.  30 s TTL.

        Exactly one pair exists (Uniswap v4, ``FWA/ETH``).  Nonzero *buys*
        despite ``externalBuysEnabled == false`` are FWARewards-routed protocol
        buys — a UI footnote, not a parsing bug.

        Returns ``(None, False)`` when the pair is absent or the call fails.
        """
        now = self._clock()
        if not force and self._market_cache and (now - self._market_cache[0]) < MARKET_TTL:
            return self._market_cache[1], True

        try:
            await self._pace("_last_dex", DEXSCREENER_MIN_DELAY)
            url = f"{DEXSCREENER_TOKENS_API}/{FWA_TOKEN_ADDRESS}"
            resp = await self._get(url, source="dexscreener")
            if resp is None or resp.status_code != 200:
                return self._market_fallback()
            payload = self._json(resp)
            if not isinstance(payload, Mapping):
                return self._market_fallback()
            parsed = parse_dexscreener(payload)
            if parsed is None:
                logger.warning("DexScreener returned no pair for %s", FWA_TOKEN_ADDRESS)
                return self._market_fallback()
            self._market_cache = (self._clock(), parsed)
            return parsed, True
        except Exception as exc:  # never raise into the refresh loop
            logger.warning("fetch_fwa_market failed: %s", exc)
            return self._market_fallback()

    def _market_fallback(self) -> tuple[dict[str, Any] | None, bool]:
        """Serve the last good market snapshot if one exists, else unavailable."""
        if self._market_cache:
            return self._market_cache[1], False
        return None, False

    # -- 2. GeckoTerminal --------------------------------------------------

    async def fetch_ohlcv_hour(
        self,
        *,
        limit: int = 100,
        hours: int | None = None,
    ) -> tuple[list[list[float]], bool]:
        """Hourly OHLCV for the sparkline, as ``[[ts, close], …]`` oldest-first.

        ``hours`` trims to the most recent N hours **if that much history
        exists**.  The pool was created 2026-07-16, so ~10 days is the hard
        ceiling and a request for a longer window returns everything there is —
        a short series is the expected steady state, not an error.  The caller
        gets ``available=True`` for any non-empty series and decides for itself
        whether the span is worth drawing.
        """
        try:
            await self._pace("_last_gecko", GECKO_MIN_DELAY)
            url = (
                f"{GECKO_API}/networks/{GECKO_NETWORK}/pools/{FWA_POOL_ID}"
                f"/ohlcv/hour?limit={int(limit)}"
            )
            resp = await self._get(url, source="geckoterminal")
            if resp is None or resp.status_code != 200:
                return [], False
            payload = self._json(resp)
            if not isinstance(payload, Mapping):
                return [], False
            candles = parse_ohlcv(payload)
            if not candles:
                return [], False
            if hours is not None and hours > 0:
                candles = candles[-hours:]
            return candles, True
        except Exception as exc:
            logger.warning("fetch_ohlcv_hour failed: %s", exc)
            return [], False

    async def fetch_pool_stats(self) -> tuple[dict[str, Any] | None, bool]:
        """GeckoTerminal pool attributes.  ``market_cap_usd`` is always ``None``.

        See :func:`parse_pool_stats`.  This is a secondary source; DexScreener
        is the primary for price and FDV.
        """
        try:
            await self._pace("_last_gecko", GECKO_MIN_DELAY)
            url = f"{GECKO_API}/networks/{GECKO_NETWORK}/pools/{FWA_POOL_ID}"
            resp = await self._get(url, source="geckoterminal")
            if resp is None or resp.status_code != 200:
                return None, False
            payload = self._json(resp)
            if not isinstance(payload, Mapping):
                return None, False
            parsed = parse_pool_stats(payload)
            return (parsed, True) if parsed else (None, False)
        except Exception as exc:
            logger.warning("fetch_pool_stats failed: %s", exc)
            return None, False

    # -- 3. CoinGecko NFT floors (background only) -------------------------

    def cached_floors(self) -> dict[str, FloorQuote]:
        """Every known floor, **with zero I/O**.

        This is the only floor accessor the hot refresh tier may call.  Quotes
        older than :data:`FLOOR_TTL` come back relabelled ``cached`` and stale;
        past :data:`FLOOR_MAX_AGE` they revert to unpriced rather than showing a
        number that may be hours out of date.
        """
        now = self._wall_clock()
        return {addr: self._age(quote, now) for addr, quote in self._floor_cache.items()}

    def _age(self, quote: FloorQuote, now: float) -> FloorQuote:
        if quote.status == STATUS_SUPPRESSED or quote.floor_eth is None:
            return quote
        age = now - quote.fetched_at
        if age < self._floor_ttl:
            return quote
        if age < self._floor_max_age:
            return replace(
                quote,
                source=SOURCE_CACHED,
                status=STATUS_CACHED,
                stale=True,
                note=quote.note or _NOTE_STALE,
            )
        return replace(
            quote,
            floor_eth=None,
            floor_usd=None,
            source=SOURCE_MISSING,
            status=STATUS_MISSING,
            stale=True,
            note="cached floor expired",
        )

    def _needs_refresh(self, quote: FloorQuote | None, now: float) -> bool:
        if quote is None:
            return True
        if quote.status == STATUS_SUPPRESSED:
            return False
        if quote.status == STATUS_MISSING and quote.floor_eth is None:
            # A hard 404 is permanent: do not re-spend the rate limit on it for
            # a day.  Transient statuses fall through and are retried.
            return (now - quote.fetched_at) >= self._missing_ttl
        if quote.retryable:
            return True
        return (now - quote.fetched_at) >= self._floor_ttl

    async def fetch_nft_floors(
        self,
        addresses: Iterable[str],
        *,
        opensea_slugs: Mapping[str, str] | None = None,
        force: bool = False,
    ) -> tuple[dict[str, FloorQuote], bool]:
        """Background floor sweep over the live collection set.

        **Never call this from a fast tier.**  It paces itself at
        :data:`COINGECKO_MIN_SPACING` per collection (~100 s for 38) and is meant
        to run every 15 minutes with its results persisted.  Hot code reads
        :meth:`cached_floors`.

        Outcome per collection:

        * **Art Blocks** — suppressed before any request is made.
        * **200** — ``coingecko`` / ``ok``.
        * **404** — ``missing`` / ``missing``, cached for :data:`MISSING_TTL`.
          Permanent absence, and the only case where ``opensea_slugs`` is
          consulted for an opportunistic gap-fill.
        * **429** — the previous value is kept and flagged stale
          (``cached`` / ``rate_limited``); with no previous value the row is
          unpriced but still marked ``rate_limited``, so it is retried next
          sweep and the badge does not count it as permanently absent.  The
          sweep then honours ``Retry-After`` once and, on a second consecutive
          429, parks the remaining collections instead of hammering — see
          :data:`COINGECKO_MAX_CONSECUTIVE_429`.
        * anything else / transport failure — ``error``, previous value kept if
          there is one.

        Returns ``(quotes, available)``.  ``available`` is False only when the
        sweep produced no usable floor at all.
        """
        slugs = {k.lower(): v for k, v in (opensea_slugs or {}).items()}
        result: dict[str, FloorQuote] = {}
        consecutive_429 = 0
        self.sweep_aborted = False

        for raw_addr in addresses:
            addr = str(raw_addr).lower()
            now = self._wall_clock()

            if addr in ART_BLOCKS_CONTRACTS:
                quote = FloorQuote(
                    address=addr,
                    floor_eth=None,
                    source=SOURCE_SUPPRESSED,
                    status=STATUS_SUPPRESSED,
                    note=ART_BLOCKS_NOTE,
                    fetched_at=now,
                )
                self._floor_cache[addr] = quote
                result[addr] = quote
                continue

            cached = self._floor_cache.get(addr)
            if not force and not self._needs_refresh(cached, now):
                result[addr] = self._age(cached, now) if cached else FloorQuote(address=addr)
                continue

            if self.sweep_aborted:
                # Budget gone.  Park it as retryable without spending a request:
                # "we did not get to ask" is a different claim from "CoinGecko
                # has no record", and only one of them is true here.
                parked = self._degrade(addr, cached, STATUS_RATE_LIMITED, _NOTE_DEFERRED, now)
                self._floor_cache[addr] = parked
                result[addr] = parked
                continue

            quote = await self._fetch_one_floor(addr, cached, slugs.get(addr))
            self._floor_cache[addr] = quote
            result[addr] = quote

            if quote.status == STATUS_RATE_LIMITED:
                consecutive_429 += 1
                if consecutive_429 >= self._cg_max_consecutive_429:
                    self.sweep_aborted = True
                    logger.info(
                        "CoinGecko floor sweep aborted after %d consecutive 429s; "
                        "remaining collections parked as retryable",
                        consecutive_429,
                    )
            else:
                consecutive_429 = 0

        available = any(q.priced for q in result.values())
        return result, available

    async def _fetch_one_floor(
        self,
        addr: str,
        previous: FloorQuote | None,
        opensea_slug: str | None,
    ) -> FloorQuote:
        """One CoinGecko lookup, with the four outcomes kept distinct."""
        try:
            # A 429 on the previous call arms a one-shot longer gap (its
            # Retry-After, capped) in place of the normal spacing.
            min_delay = self._cg_next_min_delay if self._cg_next_min_delay is not None else self._cg_spacing
            self._cg_next_min_delay = None
            await self._pace("_last_coingecko", min_delay)
            url = f"{COINGECKO_NFT_API}/ethereum/contract/{addr}"
            # 429 must not be retried inside the sweep: the header says
            # retry-after 60 s, and burning three attempts on it just deepens the
            # throttle for every collection behind it in the queue.
            resp = await self._get(url, source="coingecko")
            now = self._wall_clock()

            if resp is None:
                return self._degrade(addr, previous, STATUS_ERROR, _NOTE_ERROR, now)

            if resp.status_code == 200:
                payload = self._json(resp)
                if isinstance(payload, Mapping):
                    return parse_coingecko_floor(addr, payload, now=now)
                return self._degrade(addr, previous, STATUS_ERROR, _NOTE_ERROR, now)

            if resp.status_code == 404:
                # Permanent absence.  Try OpenSea once, opportunistically.
                gap = await self._try_opensea(addr, opensea_slug)
                if gap is not None:
                    return gap
                return FloorQuote(
                    address=addr,
                    floor_eth=None,
                    source=SOURCE_MISSING,
                    status=STATUS_MISSING,
                    note=_NOTE_MISSING,
                    fetched_at=self._wall_clock(),
                )

            if resp.status_code == 429:
                retry_after = _retry_after_seconds(resp) or self._cg_spacing
                self._cg_next_min_delay = min(max(retry_after, self._cg_spacing), self._cg_cooldown_cap)
                return self._degrade(addr, previous, STATUS_RATE_LIMITED, _NOTE_RATE_LIMITED, now)

            return self._degrade(addr, previous, STATUS_ERROR, _NOTE_ERROR, now)
        except Exception as exc:
            logger.warning("floor lookup failed for %s: %s", addr, exc)
            return self._degrade(addr, previous, STATUS_ERROR, _NOTE_ERROR, self._wall_clock())

    def _degrade(
        self,
        addr: str,
        previous: FloorQuote | None,
        status: str,
        note: str,
        now: float,
    ) -> FloorQuote:
        """Keep the last known floor across a transient failure, marked stale.

        The value survives; the *freshness claim* does not.  A transient failure
        never overwrites a real number with ``None``, and never promotes itself
        into the permanent ``missing`` state — that distinction is the whole
        point of separating 404 from 429.
        """
        if previous is not None and previous.floor_eth is not None:
            return replace(
                previous,
                source=SOURCE_CACHED,
                status=status,
                stale=True,
                note=note,
            )
        return FloorQuote(
            address=addr,
            floor_eth=None,
            source=SOURCE_MISSING,
            status=status,
            note=note,
            fetched_at=now,
            stale=True,
        )

    async def _try_opensea(self, addr: str, slug: str | None) -> FloorQuote | None:
        """Opportunistic gap-fill.  Any failure — including 401 — is a silent miss.

        OpenSea answers 200 without a key for CDN-popular slugs and 401 for
        others, unpredictably (findings §12.2 item 11).  It is never a
        dependency, never sets a degraded flag and never logs an error; it either
        produces a floor or it never happened.
        """
        if not slug:
            return None
        try:
            resp = await self._get(
                f"{OPENSEA_STATS_API}/{slug}/stats",
                source="opensea",
                retry_on_5xx=False,
            )
            if resp is None or resp.status_code != 200:
                return None  # 401 included: silent
            payload = self._json(resp)
            if not isinstance(payload, Mapping):
                return None
            total = payload.get("total") or {}
            floor = _pos_float(total.get("floor_price")) if isinstance(total, Mapping) else None
            if floor is None:
                floor = _pos_float(payload.get("floor_price"))
            if floor is None:
                return None
            return FloorQuote(
                address=addr,
                floor_eth=floor,
                source=SOURCE_OPENSEA,
                status=STATUS_OK,
                note="opportunistic OpenSea quote — indicative, not a feed",
                fetched_at=self._wall_clock(),
            )
        except Exception:
            return None  # silent by design

    # -- floor cache persistence hand-off (WP-9 owns the storage) ----------

    def export_floor_cache(self) -> dict[str, dict[str, Any]]:
        """Plain-dict snapshot for persistence."""
        return {addr: quote.as_dict() for addr, quote in self._floor_cache.items()}

    def import_floor_cache(self, raw: Mapping[str, Mapping[str, Any]]) -> None:
        """Restore a persisted snapshot.  Ages are re-evaluated on read."""
        for addr, blob in (raw or {}).items():
            try:
                quote = FloorQuote.from_dict({**blob, "address": blob.get("address", addr)})
            except Exception:
                continue
            self._floor_cache[addr.lower()] = quote

    def floor_coverage(self, weight_shares: Mapping[str, float] | None = None) -> dict[str, Any]:
        """:func:`coverage_summary` over the current cache, no I/O."""
        return coverage_summary(self.cached_floors(), weight_shares)

    # -- 4. DefiLlama ------------------------------------------------------

    async def fetch_protocol_fees(self, *, force: bool = False) -> tuple[dict[str, Any] | None, bool]:
        """Fees + revenue from DefiLlama, plus the derived take rate.  60 s TTL.

        The take rate (``dailyRevenue.total24h / dailyFees.total24h``, ~8–9 %) is
        the one number that captures the protocol's economic posture: ~91 % of
        fees flow to depositors, not the team.

        ``holders_revenue_24h`` is 0 all-time, consistent with
        ``protocolFeeToTokenBps = 0``; that is a real finding, not a fetch
        failure.
        """
        now = self._clock()
        if not force and self._fees_cache and (now - self._fees_cache[0]) < DEFILLAMA_TTL:
            return self._fees_cache[1], True

        try:
            fees = await self._fetch_llama_summary("dailyFees")
            revenue = await self._fetch_llama_summary("dailyRevenue")
            if fees is None and revenue is None:
                return (self._fees_cache[1], False) if self._fees_cache else (None, False)

            fees = fees or {}
            revenue = revenue or {}
            fees_24h = fees.get("total_24h")
            revenue_24h = revenue.get("total_24h")
            take_rate = None
            if fees_24h and revenue_24h is not None and fees_24h > 0:
                take_rate = revenue_24h / fees_24h

            out = {
                "name": fees.get("name") or revenue.get("name"),
                "category": fees.get("category") or revenue.get("category"),
                "fees_24h": fees_24h,
                "fees_7d": fees.get("total_7d"),
                "fees_all_time": fees.get("total_all_time"),
                "revenue_24h": revenue_24h,
                "revenue_7d": revenue.get("total_7d"),
                "revenue_all_time": revenue.get("total_all_time"),
                "take_rate": take_rate,
                "take_rate_pct": (take_rate * 100.0) if take_rate is not None else None,
                "fees_chart": fees.get("chart", []),
            }
            self._fees_cache = (self._clock(), out)
            return out, True
        except Exception as exc:
            logger.warning("fetch_protocol_fees failed: %s", exc)
            return (self._fees_cache[1], False) if self._fees_cache else (None, False)

    async def _fetch_llama_summary(self, data_type: str) -> dict[str, Any] | None:
        url = f"{DEFILLAMA_FEES_API}/{DEFILLAMA_SLUG}?dataType={data_type}"
        resp = await self._get(url, source="defillama")
        if resp is None or resp.status_code != 200:
            return None
        payload = self._json(resp)
        if not isinstance(payload, Mapping):
            return None
        return parse_defillama_summary(payload)

    async def fetch_protocol_tvl(self) -> tuple[float | None, bool]:
        """DefiLlama TVL — a **bare number** response, and a cross-check only.

        It diverges sharply from ``eth_getBalance(core)``.  Never render this as
        the protocol's TVL; the on-chain balance is the source of truth.
        """
        try:
            resp = await self._get(f"{DEFILLAMA_TVL_API}/{DEFILLAMA_SLUG}", source="defillama")
            if resp is None or resp.status_code != 200:
                return None, False
            value = parse_defillama_tvl(resp.text)
            return (value, True) if value is not None else (None, False)
        except Exception as exc:
            logger.warning("fetch_protocol_tvl failed: %s", exc)
            return None, False
