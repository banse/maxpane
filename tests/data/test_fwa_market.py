"""Contract tests for the FWA off-chain market client (Pool C).

Every payload here is a **live capture** replayed from ``tests/fixtures/fwa/``,
including the unhappy paths: ``coingecko_nft_404.json`` is a real 404 for Ten
Thousand Tokens (49.08 % of pool weight, and CoinGecko has never heard of it)
and ``coingecko_nft_429.json`` is a real rate limit provoked by 24 unspaced
requests.

Two invariants the whole file exists to hold:

* **No network.** ``_forbid_real_network`` replaces httpx's real async transport
  with one that raises on use, so a missing mock surfaces as a hard failure
  rather than a slow test that quietly hits the internet.
* **No sleeping.** The client's clock and sleep are injected, so the ``>= 2.5 s``
  CoinGecko spacing is asserted against a fake timeline instead of waited out.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from maxpane_dashboard.analytics.fwa_ev import pull_ev_band
from maxpane_dashboard.data.fwa_market import (
    ART_BLOCKS_CONTRACTS,
    ART_BLOCKS_NOTE,
    COINGECKO_MIN_SPACING,
    SOURCE_CACHED,
    SOURCE_COINGECKO,
    SOURCE_MISSING,
    SOURCE_OPENSEA,
    SOURCE_SUPPRESSED,
    STATUS_MISSING,
    STATUS_OK,
    STATUS_RATE_LIMITED,
    STATUS_SUPPRESSED,
    FloorQuote,
    FWAMarketClient,
    coverage_summary,
    floors_for_ev,
    parse_defillama_tvl,
    parse_ohlcv,
    parse_pool_stats,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fwa"

# Documented anchors from docs/fwa_technical_findings.md §10.
TTT = "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"          # 49.083 % of weight, hard 404
PUNKS_721 = "0x000000000000003607fce1ac9e043a86675c5c2f"     # wrapper, hard 404
AB_EXPLORATIONS = "0x942bc2d3e7a589fe5bd4a5c6ef9727dfd82f5c8a"  # 18.987 % of weight, suppressed
AB_ENGINE = "0xab00000000002ade39f58f9d8278a31574ffbe77"     # suppressed
BAYC = "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d"          # covered by CoinGecko
AZUKI = "0xed5af388653567af2f388e6224dc7c4b3241c544"         # the 429 fixture's subject


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _body(name: str) -> str:
    return _fixture(name)["response"]["raw_body"]


def _payload(name: str) -> dict[str, Any]:
    return json.loads(_body(name))


def _live_collections() -> dict[str, dict[str, Any]]:
    """The 38 collections with live positions, from the invariant-verified sweep."""
    return _fixture("backing_distribution")["by_collection"]


# ---------------------------------------------------------------------------
# Harness: no network, no wall clock
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _forbid_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any un-mocked request an immediate, loud failure."""

    async def _boom(self: Any, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"real network access attempted: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _boom)


class FakeClock:
    """Monotonic clock that only advances when the client sleeps."""

    def __init__(self, start: float = 10_000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Recorder:
    """Routing mock transport that records the fake-clock time of every call."""

    def __init__(self, clock: FakeClock, route: Any) -> None:
        self._clock = clock
        self._route = route
        self.calls: list[tuple[float, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((self._clock.now, str(request.url)))
        return self._route(request)

    @property
    def urls(self) -> list[str]:
        return [url for _, url in self.calls]

    @property
    def times(self) -> list[float]:
        return [t for t, _ in self.calls]


def _make_client(route: Any, clock: FakeClock | None = None, **kwargs: Any) -> tuple[FWAMarketClient, Recorder, FakeClock]:
    clock = clock or FakeClock()
    recorder = Recorder(clock, route)
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    client = FWAMarketClient(http_client=http, clock=clock, sleep=clock.sleep, **kwargs)
    return client, recorder, clock


def _raising_route(exc: Exception) -> Any:
    def _route(request: httpx.Request) -> httpx.Response:
        raise exc

    return _route


# ---------------------------------------------------------------------------
# 1. DexScreener
# ---------------------------------------------------------------------------


class TestDexScreener:
    async def test_dexscreener_parses_single_pair(self) -> None:
        def route(request: httpx.Request) -> httpx.Response:
            assert "api.dexscreener.com" in str(request.url)
            return httpx.Response(200, text=_body("dexscreener_fwa"))

        client, recorder, _ = _make_client(route)
        market, available = await client.fetch_fwa_market()

        assert available is True
        assert market is not None
        expected = _fixture("dexscreener_fwa")["expected_decoded"]
        assert market["chain_id"] == expected["chainId"]
        assert market["dex_id"] == expected["dexId"]
        assert market["labels"] == ["v4"]
        # pairAddress is the v4 poolId, not a deployed contract.
        assert market["pool_id"] == expected["pairAddress"]
        assert market["price_usd"] == float(expected["priceUsd"])
        assert market["price_native_eth"] == float(expected["priceNative"])
        assert market["fdv_usd"] == float(expected["fdv"])
        assert market["liquidity_usd"] == expected["liquidity"]["usd"]
        assert market["volume_24h_usd"] == expected["volume"]["h24"]
        assert market["buys_24h"] == expected["txns"]["h24"]["buys"]
        assert market["sells_24h"] == expected["txns"]["h24"]["sells"]
        assert market["price_change_24h_pct"] == expected["priceChange"]["h24"]
        assert market["pair_created_at_ms"] == expected["pairCreatedAt"]
        assert len(recorder.calls) == 1

    async def test_dexscreener_missing_pair_returns_unavailable(self) -> None:
        """An empty ``pairs`` list is unavailable — never a price of zero."""

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"schemaVersion": "1.0.0", "pairs": []})

        client, _, _ = _make_client(route)
        market, available = await client.fetch_fwa_market()

        assert available is False
        assert market is None

    async def test_dexscreener_ttl_serves_cache_without_a_second_call(self) -> None:
        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_body("dexscreener_fwa"))

        client, recorder, _ = _make_client(route)
        first, _ = await client.fetch_fwa_market()
        second, available = await client.fetch_fwa_market()

        assert available is True
        assert second == first
        assert len(recorder.calls) == 1


# ---------------------------------------------------------------------------
# 2. GeckoTerminal
# ---------------------------------------------------------------------------


class TestGeckoTerminal:
    async def test_ohlcv_parses_100_candles_newest_first(self) -> None:
        """The API sends newest-first; the client hands back oldest-first."""
        raw = _payload("geckoterminal_ohlcv_hour")["data"]["attributes"]["ohlcv_list"]
        expected = _fixture("geckoterminal_ohlcv_hour")["expected_decoded"]
        assert raw[0][0] > raw[-1][0], "fixture precondition: upstream order is descending"

        def route(request: httpx.Request) -> httpx.Response:
            assert "/ohlcv/hour" in str(request.url)
            assert "limit=100" in str(request.url)
            # The v4 poolId goes straight into the pool path.
            assert "0x230ecd3c" in str(request.url)
            return httpx.Response(200, text=_body("geckoterminal_ohlcv_hour"))

        client, _, _ = _make_client(route)
        candles, available = await client.fetch_ohlcv_hour()

        assert available is True
        assert len(candles) == expected["candle_count"] == 100
        assert [c[0] for c in candles] == sorted(c[0] for c in candles)
        assert candles[0][0] == expected["oldest_timestamp"]
        assert candles[-1][0] == expected["newest_timestamp"]
        assert candles[-1][1] == expected["first_candle"][4]  # close of the newest candle
        assert candles[0][1] == expected["last_candle"][4]

    async def test_ohlcv_short_series_is_not_an_error(self) -> None:
        """~10 days of history is all that exists; a sparse series is normal."""
        full = _payload("geckoterminal_ohlcv_hour")
        full["data"]["attributes"]["ohlcv_list"] = full["data"]["attributes"]["ohlcv_list"][:6]

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=full)

        client, _, _ = _make_client(route)
        candles, available = await client.fetch_ohlcv_hour()

        assert available is True
        assert len(candles) == 6

    async def test_ohlcv_window_longer_than_history_degrades_gracefully(self) -> None:
        """Asking for 30 days of hourly candles yields what exists, not an error."""

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_body("geckoterminal_ohlcv_hour"))

        client, _, _ = _make_client(route)
        candles, available = await client.fetch_ohlcv_hour(hours=720)

        assert available is True
        assert len(candles) == 100  # not padded, not truncated to zero

    async def test_ohlcv_empty_list_is_unavailable(self) -> None:
        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"attributes": {"ohlcv_list": []}}})

        client, _, _ = _make_client(route)
        candles, available = await client.fetch_ohlcv_hour()

        assert candles == []
        assert available is False

    async def test_gecko_market_cap_zero_is_ignored(self) -> None:
        """``market_cap_usd`` is the string ``"0.0"`` on this pool — findings §9.2.

        Rendering it would put a $0 market cap next to a $27 M FDV.  It must come
        back ``None``, flagged, and must never be silently backfilled from FDV.
        """
        pool_body = {
            "data": {
                "id": "eth_0x230ecd3c",
                "type": "pool",
                "attributes": {
                    "name": "FWA / ETH",
                    "base_token_price_usd": "0.0319594670947466",
                    "base_token_price_native_currency": "0.0000166",
                    "fdv_usd": "31959467.09",
                    "market_cap_usd": "0.0",
                    "price_change_percentage": {"h24": "50.32"},
                    "pool_created_at": "2026-07-16T17:43:35Z",
                },
            }
        }

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=pool_body)

        client, _, _ = _make_client(route)
        stats, available = await client.fetch_pool_stats()

        assert available is True
        assert stats is not None
        assert stats["market_cap_usd"] is None
        assert stats["market_cap_unavailable"] is True
        assert stats["fdv_usd"] == pytest.approx(31_959_467.09)
        # And the pure parser agrees, without a client in the way.
        assert parse_pool_stats(pool_body)["market_cap_usd"] is None


# ---------------------------------------------------------------------------
# 3. CoinGecko NFT floors
# ---------------------------------------------------------------------------


class TestCoinGeckoFloors:
    async def test_coingecko_floor_ok_200(self) -> None:
        def route(request: httpx.Request) -> httpx.Response:
            assert BAYC in str(request.url).lower()
            return httpx.Response(200, text=_body("coingecko_nft_200"))

        client, _, _ = _make_client(route)
        quotes, available = await client.fetch_nft_floors([BAYC])

        expected = _fixture("coingecko_nft_200")["expected_decoded"]
        quote = quotes[BAYC]
        assert available is True
        assert quote.floor_eth == expected["floor_price_native"]
        assert quote.floor_usd == expected["floor_price_usd"]
        assert quote.source == SOURCE_COINGECKO
        assert quote.status == STATUS_OK
        assert quote.stale is False
        assert quote.priced is True

    async def test_coingecko_404_classified_missing(self) -> None:
        """TTT: 1,732 positions, 49.083 % of weight, and no CoinGecko record.

        Unpriced, explicitly — not zero, and not absent from the result.
        """

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text=_body("coingecko_nft_404"))

        client, _, _ = _make_client(route)
        quotes, available = await client.fetch_nft_floors([TTT])

        quote = quotes[TTT]
        assert available is False
        assert TTT in quotes, "an unpriced collection is never dropped from the result"
        assert quote.floor_eth is None
        assert quote.priced is False
        assert quote.source == SOURCE_MISSING
        assert quote.status == STATUS_MISSING
        assert quote.note
        assert quote.retryable is False, "a hard 404 is permanent, not retryable"

    async def test_coingecko_404_is_cached_and_not_re_requested(self) -> None:
        """A permanent absence must not burn 2.5 s of budget every sweep."""

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text=_body("coingecko_nft_404"))

        client, recorder, _ = _make_client(route)
        await client.fetch_nft_floors([TTT])
        await client.fetch_nft_floors([TTT])

        assert len(recorder.calls) == 1

    async def test_coingecko_429_keeps_previous_and_marks_stale(self) -> None:
        """A rate limit keeps the last good number and flags it — it never blanks it."""
        responses = [
            httpx.Response(200, text=_body("coingecko_nft_200")),
            httpx.Response(429, text=_body("coingecko_nft_429"), headers={"retry-after": "60"}),
        ]

        def route(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        client, _, _ = _make_client(route)
        first, _ = await client.fetch_nft_floors([AZUKI])
        good_floor = first[AZUKI].floor_eth
        assert good_floor is not None

        second, available = await client.fetch_nft_floors([AZUKI], force=True)
        quote = second[AZUKI]

        assert quote.floor_eth == good_floor, "throttling must not destroy a known floor"
        assert quote.stale is True
        assert quote.source == SOURCE_CACHED
        assert quote.status == STATUS_RATE_LIMITED
        assert quote.retryable is True
        assert available is True  # a stale-but-real floor is still usable

    async def test_429_and_404_are_different_states(self) -> None:
        """Conflating them makes transient throttling look like permanent absence."""

        def route(request: httpx.Request) -> httpx.Response:
            if TTT in str(request.url).lower():
                return httpx.Response(404, text=_body("coingecko_nft_404"))
            return httpx.Response(429, text=_body("coingecko_nft_429"))

        client, recorder, _ = _make_client(route)
        quotes, _ = await client.fetch_nft_floors([TTT, AZUKI])

        assert quotes[TTT].status == STATUS_MISSING
        assert quotes[AZUKI].status == STATUS_RATE_LIMITED
        assert quotes[TTT].status != quotes[AZUKI].status
        assert quotes[TTT].retryable is False
        assert quotes[AZUKI].retryable is True

        # And the difference is operational, not cosmetic: only the 429 is retried.
        await client.fetch_nft_floors([TTT, AZUKI])
        retried = [url for url in recorder.urls if AZUKI in url.lower()]
        not_retried = [url for url in recorder.urls if TTT in url.lower()]
        assert len(retried) == 2
        assert len(not_retried) == 1

    async def test_art_blocks_floor_suppressed(self) -> None:
        """One contract, many collections, many floors — a per-contract number is false.

        Both Art Blocks contracts hold live positions (18.987 % and 0.071 % of
        draw weight).  Neither is ever requested over the network.
        """
        client, recorder, _ = _make_client(_raising_route(AssertionError("must not be requested")))
        quotes, available = await client.fetch_nft_floors([AB_EXPLORATIONS, AB_ENGINE])

        assert set(quotes) == ART_BLOCKS_CONTRACTS
        for addr in (AB_EXPLORATIONS, AB_ENGINE):
            quote = quotes[addr]
            assert quote.floor_eth is None
            assert quote.source == SOURCE_SUPPRESSED
            assert quote.status == STATUS_SUPPRESSED
            assert quote.note == ART_BLOCKS_NOTE
        assert available is False
        assert recorder.calls == [], "suppressed contracts make no HTTP call at all"

        # Structurally impossible to render as a number: they are absent from the
        # EV floor map too, rather than present with a zero.
        assert floors_for_ev(quotes) == {}

    async def test_opensea_401_is_silent_miss(self) -> None:
        """OpenSea 401 leaves the CoinGecko 404 verdict untouched — no error state."""
        seen: list[str] = []

        def route(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen.append(url)
            if "coingecko" in url:
                return httpx.Response(404, text=_body("coingecko_nft_404"))
            return httpx.Response(401, json={"detail": "Unauthorized"})

        client, _, _ = _make_client(route)
        quotes, available = await client.fetch_nft_floors(
            [TTT], opensea_slugs={TTT: "ten-thousand-tokens"}
        )

        quote = quotes[TTT]
        assert any("opensea" in url for url in seen), "the gap-fill was attempted"
        assert quote.floor_eth is None
        assert quote.source == SOURCE_MISSING
        assert quote.status == STATUS_MISSING, "a 401 is a silent miss, never an error"
        assert available is False

    async def test_opensea_gap_fill_succeeds_when_the_slug_is_cdn_popular(self) -> None:
        def route(request: httpx.Request) -> httpx.Response:
            if "coingecko" in str(request.url):
                return httpx.Response(404, text=_body("coingecko_nft_404"))
            return httpx.Response(200, json={"total": {"floor_price": 0.0514}})

        client, _, _ = _make_client(route)
        quotes, available = await client.fetch_nft_floors(
            [TTT], opensea_slugs={TTT: "ten-thousand-tokens"}
        )

        assert available is True
        assert quotes[TTT].floor_eth == pytest.approx(0.0514)
        assert quotes[TTT].source == SOURCE_OPENSEA
        assert "indicative" in quotes[TTT].note

    async def test_min_spacing_enforced_between_coingecko_calls(self) -> None:
        """>= 2.5 s between calls, proven on a fake clock — nothing actually sleeps."""

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_body("coingecko_nft_200"))

        addresses = [BAYC, AZUKI, "0x60e4d786628fea6478f785a6d7e704777c86a7c6"]
        client, recorder, clock = _make_client(route)

        wall_start = time.monotonic()
        await client.fetch_nft_floors(addresses)
        wall_elapsed = time.monotonic() - wall_start

        assert len(recorder.calls) == 3
        gaps = [b - a for a, b in zip(recorder.times, recorder.times[1:], strict=False)]
        assert gaps, "need at least two calls to measure spacing"
        assert all(gap >= COINGECKO_MIN_SPACING for gap in gaps), gaps
        assert clock.sleeps == pytest.approx([COINGECKO_MIN_SPACING, COINGECKO_MIN_SPACING])
        assert wall_elapsed < 1.0, "the spacing is asserted, not waited out"

    async def test_429_triggers_a_retry_after_cooldown_before_the_next_call(self) -> None:
        """One 429 buys a ``Retry-After`` pause, not another immediate request.

        Measured live: at the mandated 2.5 s spacing a real sweep still drew 26
        consecutive 429s.  Pushing through them collects nothing and deepens the
        throttle.
        """
        codes = [429, 200, 200]

        def route(request: httpx.Request) -> httpx.Response:
            code = codes.pop(0)
            if code == 429:
                return httpx.Response(429, text=_body("coingecko_nft_429"), headers={"retry-after": "60"})
            return httpx.Response(200, text=_body("coingecko_nft_200"))

        client, recorder, clock = _make_client(route)
        await client.fetch_nft_floors([TTT, BAYC, AZUKI])

        gaps = [b - a for a, b in zip(recorder.times, recorder.times[1:], strict=False)]
        assert gaps[0] == pytest.approx(60.0), "the Retry-After pause was honoured"
        assert gaps[1] == pytest.approx(COINGECKO_MIN_SPACING), "and normal pacing resumes after"
        assert client.sweep_aborted is False
        assert max(clock.sleeps) == pytest.approx(60.0)

    async def test_retry_after_pause_is_capped(self) -> None:
        """A hostile ``Retry-After: 3600`` cannot stall the background job for an hour."""
        codes = [429, 200]

        def route(request: httpx.Request) -> httpx.Response:
            if codes.pop(0) == 429:
                return httpx.Response(429, text=_body("coingecko_nft_429"), headers={"retry-after": "3600"})
            return httpx.Response(200, text=_body("coingecko_nft_200"))

        client, _, clock = _make_client(route, coingecko_cooldown_cap=60.0)
        await client.fetch_nft_floors([TTT, BAYC])

        assert max(clock.sleeps) == pytest.approx(60.0)

    async def test_sweep_parks_the_remainder_instead_of_hammering(self) -> None:
        """After two consecutive 429s the rest is parked as retryable, unrequested.

        "We never got to ask" and "CoinGecko has no record" are different claims,
        and only the first is true for a parked collection.
        """

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text=_body("coingecko_nft_429"), headers={"retry-after": "60"})

        addresses = [BAYC, AZUKI, TTT, PUNKS_721, "0x60e4d786628fea6478f785a6d7e704777c86a7c6"]
        client, recorder, _ = _make_client(route)
        quotes, available = await client.fetch_nft_floors(addresses)

        assert client.sweep_aborted is True
        assert len(recorder.calls) == 2, "gave up after two consecutive 429s"
        assert set(quotes) == set(addresses), "parked collections are still reported"
        for addr in addresses:
            assert quotes[addr].status == STATUS_RATE_LIMITED
            assert quotes[addr].retryable is True
            assert quotes[addr].status != STATUS_MISSING
            assert quotes[addr].floor_eth is None
        assert available is False

        # The whole point of parking: the next sweep actually retries them.
        recorder.calls.clear()
        await client.fetch_nft_floors(addresses)
        assert len(recorder.calls) == 2

    async def test_a_known_floor_survives_being_parked(self) -> None:
        """Parking degrades the freshness claim, never the value."""
        codes = [200, 429, 429]

        def route(request: httpx.Request) -> httpx.Response:
            code = codes.pop(0)
            if code == 200:
                return httpx.Response(200, text=_body("coingecko_nft_200"))
            return httpx.Response(429, text=_body("coingecko_nft_429"), headers={"retry-after": "60"})

        client, _, _ = _make_client(route)
        seeded, _ = await client.fetch_nft_floors([BAYC])
        known = seeded[BAYC].floor_eth
        assert known is not None

        quotes, available = await client.fetch_nft_floors([AZUKI, TTT, BAYC], force=True)

        assert client.sweep_aborted is True
        assert quotes[BAYC].floor_eth == known, "the parked collection keeps its known floor"
        assert quotes[BAYC].source == SOURCE_CACHED
        assert quotes[BAYC].stale is True
        assert available is True

    async def test_cached_floors_never_touches_the_network(self) -> None:
        """The hot tier reads the cache; CoinGecko is background-only."""
        client, recorder, _ = _make_client(_raising_route(AssertionError("hot path hit the network")))
        client.import_floor_cache(
            {BAYC: {"address": BAYC, "floor_eth": 8.75, "source": SOURCE_COINGECKO, "status": STATUS_OK, "fetched_at": 10_000.0}}
        )

        floors = client.cached_floors()

        assert floors[BAYC].floor_eth == 8.75
        assert recorder.calls == []

    async def test_stale_cached_floor_is_relabelled_then_expires(self) -> None:
        """Floors survive for hours, but never claim to be fresh."""
        client, _, clock = _make_client(_raising_route(AssertionError("no network")), floor_ttl=900.0, floor_max_age=3600.0)
        client.import_floor_cache(
            {BAYC: {"address": BAYC, "floor_eth": 8.75, "source": SOURCE_COINGECKO, "status": STATUS_OK, "fetched_at": clock.now}}
        )

        assert client.cached_floors()[BAYC].stale is False

        clock.now += 1000.0  # past the TTL, inside the usable window
        aged = client.cached_floors()[BAYC]
        assert aged.floor_eth == 8.75
        assert aged.source == SOURCE_CACHED
        assert aged.stale is True

        clock.now += 5000.0  # past the usable window
        expired = client.cached_floors()[BAYC]
        assert expired.floor_eth is None, "an hours-old floor reverts to unpriced, not a stale number"
        assert expired.source == SOURCE_MISSING


# ---------------------------------------------------------------------------
# Coverage accounting — the flagship metric's honesty layer
# ---------------------------------------------------------------------------


def _weight_ordered_addresses() -> list[str]:
    return [
        addr
        for addr, _ in sorted(
            _live_collections().items(), key=lambda kv: -kv[1]["weight_share_pct"]
        )
    ]


def _simulated_coverage_routing() -> tuple[list[str], dict[str, int]]:
    """Reproduce the observed 22 OK / 11 404 / 5 429 split over the real 38.

    Findings §10 names the anchors (TTT and the CryptoPunks 721 wrapper 404;
    both Art Blocks contracts suppressed before any request is made) but not
    every address in each bucket, so the rest is assigned in weight order for
    determinism.  The **counts** are the observed ones; the per-address bucket
    beyond the anchors is a simulation and nothing in the client depends on it.

    The five 429s are spread out rather than clustered, because a real sweep
    that draws two in a row deliberately parks its remainder — that behaviour
    has its own test and would otherwise mask this one.
    """
    ordered = _weight_ordered_addresses()
    requested = [a for a in ordered if a not in ART_BLOCKS_CONTRACTS]

    status: dict[str, int] = {TTT: 404, PUNKS_721: 404}
    rest = [a for a in requested if a not in status]
    for addr in rest[:7]:
        status[addr] = 404               # 9 hard 404s once 2 Art Blocks are suppressed
    remaining = rest[7:]
    for index, addr in enumerate(remaining):
        status[addr] = 429 if (index % 5 == 1 and index < 25) else 200

    assert sum(1 for v in status.values() if v == 429) == 5
    assert sum(1 for v in status.values() if v == 404) == 9
    assert sum(1 for v in status.values() if v == 200) == 22
    codes = [status[a] for a in requested]
    assert not any(
        a == 429 and b == 429 for a, b in zip(codes, codes[1:], strict=False)
    ), "the simulation must not trip the consecutive-429 abort"
    return ordered, status


class TestCoverage:
    def test_coverage_summary_counts_each_reason_separately(self) -> None:
        """Pure accounting, no client: 22 priced, and 16 unpriced for three reasons."""
        addresses = _weight_ordered_addresses()
        requested = [a for a in addresses if a not in ART_BLOCKS_CONTRACTS]
        quotes: dict[str, FloorQuote] = {
            addr: FloorQuote(addr, source=SOURCE_SUPPRESSED, status=STATUS_SUPPRESSED, note=ART_BLOCKS_NOTE)
            for addr in addresses
            if addr in ART_BLOCKS_CONTRACTS
        }
        for index, addr in enumerate(requested):
            if index < 9:
                quotes[addr] = FloorQuote(addr, source=SOURCE_MISSING, status=STATUS_MISSING)
            elif index < 14:
                quotes[addr] = FloorQuote(addr, source=SOURCE_MISSING, status=STATUS_RATE_LIMITED)
            else:
                quotes[addr] = FloorQuote(addr, floor_eth=1.0, source=SOURCE_COINGECKO, status=STATUS_OK)

        summary = coverage_summary(quotes)
        assert summary == {
            "total": 38,
            "priced": 22,
            "unpriced": 16,
            "cached": 0,
            "missing": 9,
            "rate_limited": 5,
            "suppressed": 2,
            "errors": 0,
            "weight_priced_pct": 0.0,
            "weight_unpriced_pct": 0.0,
            "caveat": "floor available for 22 of 38 collections",
        }

    async def test_coverage_summary_reports_22_of_38(self) -> None:
        by_collection = _live_collections()
        assert len(by_collection) == 38
        addresses, routing = _simulated_coverage_routing()

        def route(request: httpx.Request) -> httpx.Response:
            addr = str(request.url).rsplit("/", 1)[-1].lower()
            code = routing[addr]
            if code == 200:
                return httpx.Response(200, text=_body("coingecko_nft_200"))
            if code == 404:
                return httpx.Response(404, text=_body("coingecko_nft_404"))
            return httpx.Response(429, text=_body("coingecko_nft_429"))

        client, _, _ = _make_client(route)
        quotes, available = await client.fetch_nft_floors(addresses)

        weights = {a: v["weight_share_pct"] for a, v in by_collection.items()}
        summary = coverage_summary(quotes, weights)

        assert available is True
        assert client.sweep_aborted is False
        assert summary["total"] == 38
        assert summary["priced"] == 22
        assert summary["unpriced"] == 16
        assert summary["missing"] == 9
        assert summary["rate_limited"] == 5
        assert summary["suppressed"] == 2
        assert summary["errors"] == 0
        assert summary["caveat"].startswith("floor available for 22 of 38 collections")
        # The two largest weight buckets are among the unpriced.
        assert quotes[TTT].floor_eth is None
        assert quotes[AB_EXPLORATIONS].floor_eth is None
        assert summary["weight_unpriced_pct"] > 68.0

    def test_weight_shares_sum_to_100_000001_and_coverage_does_not_assume_100(self) -> None:
        """The 38 shares are 6-dp rounded and total 100.000001, not 100.0."""
        weights = {a: v["weight_share_pct"] for a, v in _live_collections().items()}
        total = sum(weights.values())
        assert total == pytest.approx(100.000001, abs=1e-9)
        assert total != 100.0

        # Everything priced => exactly 100 % of weight covered, computed against
        # the observed total rather than a hardcoded 100.
        quotes = {
            addr: FloorQuote(
                address=addr,
                floor_eth=1.0,
                source=SOURCE_COINGECKO,
                status=STATUS_OK,
            )
            for addr in weights
        }
        summary = coverage_summary(quotes, weights)
        assert summary["weight_priced_pct"] == pytest.approx(100.0)
        assert summary["weight_unpriced_pct"] == pytest.approx(0.0, abs=1e-9)

    async def test_unpriced_collection_is_omitted_from_ev_floors_never_zeroed(self) -> None:
        """A zero floor would collapse the band's upper leg for the wrong reason."""

        def route(request: httpx.Request) -> httpx.Response:
            if BAYC in str(request.url).lower():
                return httpx.Response(200, text=_body("coingecko_nft_200"))
            return httpx.Response(404, text=_body("coingecko_nft_404"))

        client, _, _ = _make_client(route)
        quotes, _ = await client.fetch_nft_floors([BAYC, TTT, AB_EXPLORATIONS])

        floors = floors_for_ev(quotes)
        assert set(floors) == {BAYC}
        assert TTT not in floors
        assert AB_EXPLORATIONS not in floors
        assert 0.0 not in floors.values()

        # A zeroed floor is not a harmless placeholder: ``max(sellback, 0.0)``
        # hands the unpriced position its full sell-back value in the
        # *pessimistic* leg, so the band narrows onto a number that was never
        # verified — the confident lie the band exists to prevent.
        positions = [(2 * 10**17, BAYC), (5 * 10**16, TTT), (10**17, AB_EXPLORATIONS)]
        band = pull_ev_band(positions, floors, acquisition_fee_wei=136_829_134_522_020_108)
        zeroed = pull_ev_band(
            positions,
            {**floors, TTT: 0.0, AB_EXPLORATIONS: 0.0},
            acquisition_fee_wei=136_829_134_522_020_108,
        )
        assert band["lower_eth"] <= band["best_eth"]
        assert band["lower_eth"] < band["best_eth"], "the band is open while coverage is partial"
        assert zeroed["lower_eth"] > band["lower_eth"], (
            "passing 0.0 for an unknown floor inflates the pessimistic bound — "
            "which is exactly why floors_for_ev omits it"
        )
        assert zeroed["lower_eth"] == pytest.approx(zeroed["best_eth"])
        assert zeroed["collections_priced"] == 3, "zeros masquerade as coverage"
        assert band["collections_priced"] == 1
        assert band["weight_priced_pct"] < zeroed["weight_priced_pct"]


# ---------------------------------------------------------------------------
# 4. DefiLlama
# ---------------------------------------------------------------------------


class TestDefiLlama:
    async def test_protocol_fees_and_take_rate(self) -> None:
        fixture = _fixture("defillama_fees_summary")

        def route(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            data_type = url.rsplit("dataType=", 1)[-1]
            return httpx.Response(200, text=fixture["responses"][data_type]["raw_body"])

        client, _, _ = _make_client(route)
        fees, available = await client.fetch_protocol_fees()

        expected = fixture["expected_decoded"]
        assert available is True
        assert fees is not None
        assert fees["fees_24h"] == expected["dailyFees"]["total24h"]
        assert fees["revenue_24h"] == expected["dailyRevenue"]["total24h"]
        assert fees["take_rate"] == pytest.approx(expected["take_rate_24h"])
        assert fees["category"] == "Gamified Mining"

    async def test_defillama_tvl_bare_number_handled(self) -> None:
        """``/tvl/{slug}`` answers ``3680844.830019135`` — not an object."""
        tvl_fixture = _fixture("defillama_fees_summary")["tvl_endpoint"]
        raw = tvl_fixture["raw_body"]
        assert not raw.strip().startswith("{"), "fixture precondition: bare number"

        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=raw)

        client, _, _ = _make_client(route)
        tvl, available = await client.fetch_protocol_tvl()

        assert available is True
        assert tvl == pytest.approx(3_680_844.830019135)
        assert parse_defillama_tvl(raw) == pytest.approx(float(raw))
        assert parse_defillama_tvl("") is None


# ---------------------------------------------------------------------------
# Degradation and hygiene
# ---------------------------------------------------------------------------


class TestDegradation:
    async def test_every_source_dying_never_raises(self) -> None:
        client, _, _ = _make_client(_raising_route(httpx.ConnectError("dns is gone")))

        market, market_ok = await client.fetch_fwa_market()
        candles, spark_ok = await client.fetch_ohlcv_hour()
        stats, stats_ok = await client.fetch_pool_stats()
        quotes, floors_ok = await client.fetch_nft_floors([BAYC])
        fees, fees_ok = await client.fetch_protocol_fees()
        tvl, tvl_ok = await client.fetch_protocol_tvl()

        assert (market, market_ok) == (None, False)
        assert (candles, spark_ok) == ([], False)
        assert (stats, stats_ok) == (None, False)
        assert (fees, fees_ok) == (None, False)
        assert (tvl, tvl_ok) == (None, False)
        assert floors_ok is False
        # The collection is still present and explicitly unpriced.
        assert BAYC in quotes
        assert quotes[BAYC].floor_eth is None
        assert quotes[BAYC].stale is True

    async def test_server_errors_are_retried_then_reported_unavailable(self) -> None:
        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="upstream unavailable")

        client, recorder, _ = _make_client(route)
        market, available = await client.fetch_fwa_market()

        assert available is False
        assert market is None
        assert len(recorder.calls) == 3

    def test_no_api_keys_and_no_banned_hosts(self) -> None:
        """Keyless only.  Reservoir's DNS is gone; Alchemy et al. need keys."""
        source = (
            Path(__file__).resolve().parents[2]
            / "maxpane_dashboard"
            / "data"
            / "fwa_market.py"
        ).read_text().lower()

        for banned in (
            "reservoir.tools",
            "alchemy.com",
            "alchemyapi",
            "infura.io",
            "moralis",
            "etherscan.io",
            "api-mainnet.magiceden.dev",
            "api_key",
            "apikey",
            "x-api-key",
            "getenv",
        ):
            assert banned not in source, f"banned token in fwa_market.py: {banned}"

    def test_parse_ohlcv_skips_malformed_candles_without_raising(self) -> None:
        payload = {
            "data": {
                "attributes": {
                    "ohlcv_list": [
                        [1785117600, 1, 2, 0.5, 1.5, 10],
                        "garbage",
                        [1785114000],
                        [None, 1, 2, 3, 4, 5],
                        [1785110400, 1, 2, 0.5, 1.25, 10],
                    ]
                }
            }
        }
        assert parse_ohlcv(payload) == [[1785110400, 1.25], [1785117600, 1.5]]
