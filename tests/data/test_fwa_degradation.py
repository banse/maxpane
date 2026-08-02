"""WP-15 — the FWA degradation and failure-mode suite.

Seven scenarios, each driven **end to end**: a real :class:`FWAManager` with
doubled transports, a real :class:`FWAScreen` under ``App.run_test()``, and
every assertion made against **composited screen text**
(``screen._compositor.render_strips()``) rather than against a widget's content
string.  A string that never reaches a pixel passes a naive test while being
invisible to the user -- WP-13 and WP-16 both assert this way for the same
reason, and this suite inherits the discipline.

The single rule everything here reduces to::

    a dead source must produce an explicit unavailable state
    -- never a crash, never a blank screen,
       and never a silently wrong number presented as live.

Of those three the last is the one that costs someone ETH, so most of the
assertions below are about the third: what is *absent* from the screen when a
number would be wrong, and what marker stands beside a number that is merely
old.

The scenarios
-------------

1. **Emissions window elapsed** -- PRIMARY, written and asserted first.
2. **Logs endpoint down** (Pool B), cold and warm.
3. **Floors partially missing** -- 22 priced of 38.
4. **RPC fallback exhausted** (Pool A), cold and warm.
5. **Market feeds down** (Pool C).
6. **Combined worst case** -- all three pools dead, empty cache.
7. **Invariant mismatch** -- board stale, EV withheld.

Plus the three traps that already bit this build, each asserted as its own
test: the ``0.0`` floor, the ``None``-not-``0`` failed read, and the settlement
mix surviving a log trim.

Zero network and zero wall clock.  Every manager here is built with an injected
:class:`FakeClock`, so the 2026-08-04T19:01:23Z emissions stop is exercised from
both sides with identical results before and after that date; no test in this
module compares anything against ``time.time()``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager

import pytest
from textual.app import App

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.analytics.fwa_signals import (
    DOCUMENTED_EMISSION_STOP,
    SIGNAL_BAD,
)
from maxpane_dashboard.data import fwa_logs as fl
from maxpane_dashboard.data.fwa_cache import FWACache
from maxpane_dashboard.data.fwa_client import FWA_HOT_KEYS
from maxpane_dashboard.data.fwa_manager import LOG_RAW_MIN_ROWS, FWAManager
from maxpane_dashboard.data.fwa_market import FloorQuote, floors_for_ev
from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS, Position
from maxpane_dashboard.screens.fwa import FWAScreen

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

BLOCK = 25_612_701
ETH = 10**18

#: Fixed capture timestamp for every last-good payload.  Never ``time.time()``.
AS_OF_TS = 1_785_900_000.0

#: Default cycle clock, comfortably after the emissions stop -- the state the
#: dashboard spends its life in (PRD §8).  Overridden per scenario.
NOW_TS = DOCUMENTED_EMISSION_STOP + 21 * 86_400

COLL_CHEAP = "0x" + "11" * 20     # the dust that owns the draw
COLL_MID = "0x" + "22" * 20
COLL_PUNKS = "0x" + "99" * 20     # 221 ETH for ~0.000% of the weight

CROWN_LISTING_ID = 56_508
CROWN_HOLDER = "0x" + "cc" * 20

#: The realistic wide terminal the widgets were measured against (their own
#: docstrings quote slot widths "at a 200-column terminal").
WIDE = (200, 50)

#: WP-13's size.  Used wherever the assertion is about vertical budget, and in
#: the worst-case scenario, so degradation is proven to survive the narrow
#: layout too.
NARROW = (140, 42)

#: A negative *duration*: the one thing PRD §8 forbids the emissions row from
#: rendering.  Deliberately narrower than "any minus sign" -- the PULL EV band
#: and the 24h price change are legitimately negative and must stay that way.
NEGATIVE_DURATION = re.compile(r"[-−]\s*\d+(?:\.\d+)?\s*(?:d|h|m|s)\b")


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------


def _position(listing_id: int, collection: str, backing_wei: int, **over) -> Position:
    kwargs = dict(
        listing_id=listing_id,
        collection=collection,
        depositor="0x" + "ab" * 20,
        allocatee=None,
        token_id=listing_id,
        weight=fwa_ev.inverse_weight(backing_wei),
        backing_wei=backing_wei,
        fee_share=1,
        fee_debt=0,
        slot=listing_id,
        allocated_at=0,
        status=1,
    )
    kwargs.update(over)
    return Position(**kwargs)


def _positions() -> list[Position]:
    """The small pool: 4 positions, 3 collections, 1 of them priced."""
    return [
        _position(1, COLL_CHEAP, ETH // 20),                 # 0.05 ETH
        _position(2, COLL_CHEAP, ETH // 10),                 # 0.10 ETH
        _position(3, COLL_MID, ETH),                         # 1 ETH
        _position(
            CROWN_LISTING_ID, COLL_PUNKS, 221 * ETH, depositor=CROWN_HOLDER
        ),                                                   # the chase item
    ]


def _sweep_report(positions, *, invariants_ok: bool = True) -> dict:
    backings = [p.backing_wei for p in positions]
    total_weight = fwa_ev.total_weight(backings)
    weighted = fwa_ev.weighted_backing_total(backings)
    fee = fwa_ev.acquisition_fee_wei(weighted, total_weight)
    report = {
        "invariants_ok": invariants_ok,
        "collected": len(positions),
        "expected": len(positions),
        "mismatches": () if invariants_ok else ("count 37 != activeListingCount 38",),
        "total_weight_computed": total_weight,
        "total_weight_onchain": total_weight,
        "weighted_backing_total_computed": weighted,
        "weighted_backing_total_onchain": weighted,
        "acquisition_fee_computed": fee,
        "acquisition_fee_onchain": fee,
        "backing_total_wei": sum(backings),
        "weight_mismatches": 0,
        "block_number": BLOCK,
        "skipped": False,
    }
    if not invariants_ok:
        # A partial sweep: the numbers no longer reproduce at the pinned block.
        report["total_weight_onchain"] = total_weight + 1
    return report


def _hot_batch(**over) -> dict:
    """A hot batch with every ``FWA_HOT_KEYS`` key present."""
    hot = dict.fromkeys(FWA_HOT_KEYS)
    hot.update(
        {
            "acquisition_fee": 136_829_134_522_020_108,
            "total_weight": 31_280_618_816_683_353_089_152,
            "active_listing_count": 4,
            "next_listing_id": 60_000,
            "fee_share_total": 4,
            "bps": 10_000,
            "top_listing_id": CROWN_LISTING_ID,
            "top_listing_pot": 60_242_085_156_350_313,
            "top_threshold_bps": 1_000,
            "top_listing_share_bps": 100,
            "settlement_discount_bps": 8_500,
            "retained_to_protocol": True,
            "owner_acquisition_fee_bps": 0,
            "owner_settlement_fee_bps": 0,
            "selection_slippage_bps": 500,
            "selection_timeout_blocks": 100,
            "settlement_window": 86_400,
            "finalize_window": 86_400,
            "pending_acquisition_count": 2,
            "unsettled_acquisition_count": 1,
            "unfulfilled_vrf_count": 0,
            "last_issued_sequence": 120,
            "next_sequence_to_process": 105,
            # The documented window: start + duration == DOCUMENTED_EMISSION_STOP.
            "emission_start": 1_784_574_083,
            "emission_duration": 15 * 24 * 3_600,
            "current_epoch": 3,
            "hot_gap": 60,
            "cold_gap": 3_600,
            "forced_token_share_bps": -1,
            "last_acquisition_ts": int(AS_OF_TS),
            "subscription_native_balance": 5 * ETH,
            "minimum_subscription_buffer": ETH,
            "token_total_supply": 1_000_000_000 * ETH,
            "token_launched": True,
            "last_buyback_block": 0,
            "token_symbol": "FWA",
            "external_buys_enabled": False,
            "ttt_amount": 0,
            "splitter_total_received": 91 * ETH,
            "quote_fee_wei": 136_829_134_522_020_108,
            "quote_vrf_wei": 1_040_000_000_000_000,
            "quote_total_wei": 137_869_134_522_020_108,
            "quote_gas_price_wei": 1_000_000_000,
            "token_share_bps": 0,
            "_ok": True,
            "_failed": (),
            "_fetched_at": AS_OF_TS,
            "_error": None,
        }
    )
    hot.update(over)
    return hot


def _dead_hot_batch() -> dict:
    """What :class:`FWAClient` returns when every RPC endpoint is exhausted.

    Every key present, **every value ``None``** -- never a zero.  This shape is
    the contract that keeps a dead RPC from rendering as a closed buy gate.
    """
    out = dict.fromkeys(FWA_HOT_KEYS)
    out.update(
        {
            "_ok": False,
            "_failed": tuple(FWA_HOT_KEYS),
            "_error": "publicnode, cloudflare and 1rpc all failed",
            "_fetched_at": 0.0,
        }
    )
    return out


#: The real all-time settlement counts (findings §8): 51,522 events whose mix is
#: 73.92 / 13.84 / 7.64 / 4.60 / 0.00.  Used verbatim by the log-trim trap.
ALLTIME_SETTLEMENT_COUNTS = {
    "DepositorBidAcceptedAsTokens": 38_083,
    "DepositorBidAccepted": 7_131,
    "NFTRelisted": 3_936,
    "NFTKept": 2_370,
    "UnsettledFinalized": 2,
}

#: What the settlement table's SHARE column must read, before and after a trim.
ALLTIME_SHARES = ("73.92%", "13.84%", "7.64%", "4.60%", "0.00%")


def _log_snapshot(*, available: bool = True) -> dict:
    return {
        "available": available,
        "reason": None if available else fl.REASON_UNAVAILABLE,
        "as_of_ts": AS_OF_TS if available else None,
        "last_seen_block": BLOCK,
        "settlement_mix": [
            {"outcome": "bid_fwa", "label": "accept bid · $FWA",
             "count": 38_083, "share_pct": 73.92},
            {"outcome": "bid_eth", "label": "accept bid · ETH",
             "count": 7_131, "share_pct": 13.84},
            {"outcome": "relist", "label": "relist", "count": 3_936,
             "share_pct": 7.64},
            {"outcome": "kept", "label": "keep the NFT", "count": 2_370,
             "share_pct": 4.60},
            {"outcome": "forced", "label": "force-finalized", "count": 2,
             "share_pct": 0.0},
        ],
        # Presentation payload with no model behind it: already ETH.
        "crown_history": [
            {"rank": 1, "holder": CROWN_HOLDER, "reigns": 4,
             "payout_eth": 41.5, "last_block": BLOCK, "last_ts": int(AS_OF_TS)},
        ],
        "crown_sets_total": 17,
        "crown_payouts_total": 12,
        "crown_paid_eth": 91.096,
        # Wei-native: DrawEvent dumps carry amount_wei.
        "draw_events": [
            {
                "ts": int(AS_OF_TS) - 100,
                "block_number": BLOCK,
                "tx_hash": "0x" + "ab" * 32,
                "purchaser": "0x" + "de" * 20,
                "collection": COLL_CHEAP,
                "collection_name": "Ten Thousand Tokens",
                "token_id": 4471,
                "outcome": "bid_fwa",
                "outcome_label": "sold back ($FWA)",
                "amount_wei": 118_000_000_000_000_000,
            },
        ],
        "config_history": [
            {"key": 15, "name": "TOP_LISTING_SHARE_BPS", "value": 100,
             "block_number": 25_592_190, "settable": True},
        ],
        "collection_registry": {},
        "allowed_collections": [COLL_CHEAP, COLL_MID, COLL_PUNKS],
        "price_history": [],
        "backing_updates": [],
        "event_counts": {"NFTAllocated": 1},
    }


def _empty_log_snapshot() -> dict:
    """Pool B down and nothing ever scanned: no stale number to misread."""
    snap = _log_snapshot(available=False)
    snap.update(
        {
            "settlement_mix": [
                {**row, "count": 0, "share_pct": 0.0}
                for row in snap["settlement_mix"]
            ],
            "crown_history": [],
            "draw_events": [],
            "crown_sets_total": 0,
            "crown_payouts_total": 0,
            "crown_paid_eth": 0.0,
        }
    )
    return snap


def _market_payload() -> dict:
    return {
        "chain_id": "ethereum",
        "dex_id": "uniswap",
        "pool_id": "0xpool",
        "price_usd": 0.0004,
        "price_native_eth": 0.0000001,   # -> ETH/USD = 4000
        "fdv_usd": 400_000.0,
        "liquidity_usd": 90_000.0,
        "volume_24h_usd": 12_000.0,
        "buys_24h": 11_400,
        "sells_24h": 900,
        "price_change_24h_pct": -3.5,
        "pair_created_at_ms": 0,
    }


def _floor_quotes() -> dict[str, FloorQuote]:
    """1 priced of 3 -- the same shape as the live 22 of 38."""
    return {
        COLL_CHEAP: FloorQuote(
            address=COLL_CHEAP,
            floor_eth=0.0421,
            source="coingecko",
            status="ok",
            name="Ten Thousand Tokens",
            fetched_at=AS_OF_TS,
        ),
        COLL_MID: FloorQuote(
            address=COLL_MID,
            floor_eth=None,
            source="missing",
            status="missing",
            note="no CoinGecko listing for this contract",
            fetched_at=AS_OF_TS,
        ),
        COLL_PUNKS: FloorQuote(
            address=COLL_PUNKS,
            floor_eth=None,
            source="suppressed",
            status="suppressed",
            note="one contract hosts many collections",
            fetched_at=AS_OF_TS,
        ),
    }


# -- the 38-collection pool, for the partial-floor scenario ------------------

#: The live split (WP-15 brief): 22 priced, 10 hard 404s, 5 throttled 429s and
#: one deliberately suppressed multi-collection contract.
PRICED_COUNT = 22
MISSING_COUNT = 10
RATE_LIMITED_COUNT = 5
SUPPRESSED_COUNT = 1
POOL_SIZE = PRICED_COUNT + MISSING_COUNT + RATE_LIMITED_COUNT + SUPPRESSED_COUNT

#: The suppressed contract, given the smallest backing so its inverse weight is
#: the largest and it ranks first -- the suppression note has to be *visible*,
#: not merely present in a row that never gets painted.
ART_BLOCKS = "0x" + "a0" * 20


def _wide_pool() -> tuple[list[Position], dict[str, FloorQuote]]:
    """38 collections: 22 with a floor, 16 without, ~22% of weight priced.

    Priced collections are the expensive ones (1 ETH backing, low inverse
    weight); the unpriced ones are cheap (0.2 ETH, high weight).  That is the
    real inversion -- the collections nobody can price are the ones that own
    the draw -- and it is what makes the coverage badge worth rendering.
    """
    positions: list[Position] = []
    floors: dict[str, FloorQuote] = {}
    listing = 1

    for i in range(PRICED_COUNT):
        addr = f"0x{(0xb0 + i):02x}" + "b0" * 19
        positions.append(_position(listing, addr, ETH))
        floors[addr] = FloorQuote(
            address=addr, floor_eth=0.5 + i / 100, source="coingecko",
            status="ok", name=f"Priced {i:02d}", fetched_at=AS_OF_TS,
        )
        listing += 1

    for i in range(MISSING_COUNT):
        addr = f"0x{(0xc0 + i):02x}" + "c0" * 19
        positions.append(_position(listing, addr, ETH // 5))
        floors[addr] = FloorQuote(
            address=addr, floor_eth=None, source="missing", status="missing",
            note="no CoinGecko listing for this contract",
            name=f"Unpriced {i:02d}", fetched_at=AS_OF_TS,
        )
        listing += 1

    for i in range(RATE_LIMITED_COUNT):
        addr = f"0x{(0xd0 + i):02x}" + "d0" * 19
        positions.append(_position(listing, addr, ETH // 5))
        floors[addr] = FloorQuote(
            address=addr, floor_eth=None, source="missing",
            status="rate_limited", note="throttled by CoinGecko — will retry",
            name=f"Throttled {i:02d}", fetched_at=AS_OF_TS,
        )
        listing += 1

    # The suppressed one, ranked first by giving it the smallest backing.
    positions.append(_position(listing, ART_BLOCKS, ETH // 6))
    floors[ART_BLOCKS] = FloorQuote(
        address=ART_BLOCKS, floor_eth=None, source="suppressed",
        status="suppressed", note="one contract hosts many collections",
        name="Art Blocks", fetched_at=AS_OF_TS,
    )
    return positions, floors


# ---------------------------------------------------------------------------
# Doubles -- three independently failing transports
# ---------------------------------------------------------------------------


class FakeClock:
    """Injectable wall clock.  Nothing in this module reads the real one."""

    def __init__(self, start: float = NOW_TS) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeStateClient:
    """Pool A.  ``fail=True`` is *every RPC endpoint exhausted*."""

    def __init__(
        self,
        *,
        fail: bool = False,
        invariants_ok: bool = True,
        positions: list[Position] | None = None,
        hot: dict | None = None,
    ) -> None:
        self.fail = fail
        self.invariants_ok = invariants_ok
        self.positions = list(positions) if positions is not None else _positions()
        self.hot = hot
        self.hot_calls = 0
        self.sweep_calls = 0
        self.closed = False

    async def fetch_hot_batch(self, **_kwargs):
        self.hot_calls += 1
        if self.fail:
            return _dead_hot_batch()
        return dict(self.hot) if self.hot is not None else _hot_batch()

    async def sweep_positions(self, **_kwargs):
        self.sweep_calls += 1
        if self.fail:
            return (
                0,
                [],
                {"invariants_ok": False, "collected": 0, "expected": 0,
                 "skipped": False, "mismatches": ("every RPC endpoint failed",)},
            )
        return (
            BLOCK,
            list(self.positions),
            _sweep_report(self.positions, invariants_ok=self.invariants_ok),
        )

    async def fetch_eth_balance(self, *_a, **_k):
        # ``0`` is how the real client reports failure, and the core has never
        # held zero -- the manager treats it as unavailable.
        return 0 if self.fail else 2_551 * ETH

    async def close(self):
        self.closed = True


class FakeLogClient:
    """Pool B -- the design's single point of failure."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.head = BLOCK
        self.backfills = 0
        self.tails = 0
        self.closed = False

    async def head_block(self):
        return self.head if self.available else 0

    async def backfill(self, _from_block, _to_block, _events=None):
        self.backfills += 1
        return {"available": self.available, "added": 1}

    async def tail(self, *_a, **_k):
        self.tails += 1
        return {"available": self.available, "added": 0}

    def snapshot(self, *, feed_limit: int = 50):
        if not self.available:
            return _empty_log_snapshot()
        snap = _log_snapshot(available=True)
        snap["draw_events"] = snap["draw_events"][:feed_limit]
        return snap

    def entries(self, event):
        if event == "ConfigSet" and self.available:
            return [{"key": 15, "value": 100, "block_number": 25_592_190,
                     "log_index": 0}]
        return []

    def event_counts(self):
        return {"NFTAllocated": 1} if self.available else {}

    def backing_updates(self, since: int = 0):
        return []

    def listing_index(self):
        return {}

    def export_state(self):
        return {"version": 1, "last_seen_block": BLOCK, "scanned_from": 0,
                "as_of_ts": AS_OF_TS, "launch_block": None, "events": {}}

    def import_state(self, state):
        return bool(state)

    async def close(self):
        self.closed = True


class FakeMarketClient:
    """Pool C -- DexScreener + GeckoTerminal + DefiLlama + the floor sweep."""

    def __init__(self, *, fail: bool = False, floors: dict | None = None) -> None:
        self.fail = fail
        self.floors = dict(floors) if floors is not None else _floor_quotes()
        self.floor_sweeps = 0
        self.closed = False

    async def fetch_fwa_market(self, *, force: bool = False):
        return (None, False) if self.fail else (_market_payload(), True)

    async def fetch_ohlcv_hour(self, *, limit: int = 100, hours=None):
        if self.fail:
            return [], False
        base = int(AS_OF_TS) - 100 * 3_600
        return [[base + 3_600 * i, 0.0004 + i / 1_000_000] for i in range(100)], True

    async def fetch_protocol_fees(self, *, force: bool = False):
        if self.fail:
            return None, False
        return {"take_rate_pct": 8.8, "fees_24h": 12.0, "revenue_24h": 1.05}, True

    async def fetch_nft_floors(self, addresses, **_kwargs):
        self.floor_sweeps += 1
        if self.fail:
            return {}, False
        return dict(self.floors), True

    def cached_floors(self):
        return {} if self.fail else dict(self.floors)

    def import_floor_cache(self, raw):
        for addr, row in (raw or {}).items():
            self.floors[addr] = FloorQuote.from_dict(row)

    def export_floor_cache(self):
        return {a: q.as_dict() for a, q in self.floors.items()}

    async def close(self):
        self.closed = True


class _DeadTransport:
    """httpx-shaped stand-in proving the log-trim test touches no network."""

    async def aclose(self):
        return None

    async def post(self, *_a, **_k):  # pragma: no cover - must never be reached
        raise AssertionError("the degradation suite must not touch the network")


class OfflineLogClient(fl.FWALogClient):
    """The **real** log client with only its three network coroutines stubbed.

    Used by the log-trim trap, where a double would be testing itself: the
    point there is that the real decoders, the real ``export_state`` /
    ``import_state`` round trip and the real ``settlement_mix`` are what the
    count baseline has to survive.
    """

    def __init__(self, *, up: bool = True, head: int = BLOCK) -> None:
        super().__init__(http_client=_DeadTransport())
        self.up = up
        self.head = head
        self.tails = 0
        self.backfills = 0

    async def head_block(self) -> int:
        return self.head if self.up else 0

    async def backfill(self, from_block, to_block, events=None):
        self.backfills += 1
        return self._settle(to_block)

    async def tail(self, last_seen_block=None, head=None, events=None):
        self.tails += 1
        return self._settle(self.head)

    def _settle(self, to_block: int) -> dict:
        if not self.up:
            self._mark_down(fl.REASON_UNAVAILABLE)
        else:
            self._mark_ok(to_block)
            self._as_of_ts = AS_OF_TS   # never the wall clock
        return {**self.status(), "added": 0}

    async def close(self):
        return None


def _raw_log(event: str, block: int, seq: int, *, listing_id: int,
             words: int = 3, topics: int = 3) -> dict:
    """An RPC-shaped log the real ``fwa_logs`` decoders accept."""
    extra = [f"0x{listing_id:064x}" for _ in range(topics)]
    return {
        "blockNumber": hex(block),
        "logIndex": hex(seq % 8),
        "transactionHash": "0x" + f"{seq:064x}",
        "blockTimestamp": hex(1_785_000_000 + block),
        "address": fl.FWA_CORE_ADDRESS.lower(),
        "topics": [fl.topic0(event)] + extra,
        "data": "0x" + "".join(f"{(10**17 + seq):064x}" for _ in range(words)),
    }


def _populate(client: fl.FWALogClient, spec: dict[str, tuple[int, int, int]]) -> None:
    """Fill a real log client offline.  ``spec``: event -> (count, first, last)."""
    seq = 0
    head = 0
    shapes = {
        "NFTListed": (4, 3),
        "NFTAllocated": (3, 3),
        "AcquisitionRequested": (2, 2),
        "TopListingSet": (2, 2),
        "TopListingSettled": (2, 2),
        "ConfigSet": (2, 1),
        "CollectionWhitelistSet": (1, 2),
    }
    for event, (count, first, last) in spec.items():
        words, topics = shapes.get(event, (3, 3))
        logs = []
        for i in range(count):
            block = first + int(i * (last - first) / max(1, count - 1))
            head = max(head, block)
            logs.append(
                _raw_log(event, block, seq, listing_id=1_000 + i,
                         words=words, topics=topics)
            )
            seq += 1
        client._ingest(logs)
    client.last_seen_block = head
    client._available = True
    client._as_of_ts = AS_OF_TS


# ---------------------------------------------------------------------------
# Manager + screen harness
# ---------------------------------------------------------------------------


def _manager(tmp_path, *, state=None, logs=None, market=None, clock=None, **kwargs):
    clock = clock or FakeClock()
    manager = FWAManager(
        poll_interval=30,
        clock=clock,
        cache_path=str(tmp_path / "fwa_cache.json"),
        log_state_path=str(tmp_path / "fwa_log_state.json"),
        client=state if state is not None else FakeStateClient(),
        log_client=logs if logs is not None else FakeLogClient(),
        market_client=market if market is not None else FakeMarketClient(),
        cache=FWACache(clock=clock),
        persist_log_state=kwargs.pop("persist_log_state", False),
        **kwargs,
    )
    manager.clock = clock
    return manager


async def _drain(manager) -> None:
    """Await the detached floor sweep so no test leaks a pending task."""
    task = getattr(manager, "_floor_task", None)
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)


class _Recorder:
    """Transparent proxy that keeps the last payload the screen was handed."""

    def __init__(self, manager) -> None:
        self.manager = manager
        self.last: dict | None = None
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.last = await self.manager.fetch_and_compute()
        return self.last

    async def close(self) -> None:
        await self.manager.close()

    def __getattr__(self, name):
        return getattr(self.manager, name)


class _Harness(App):
    """Push a single FWAScreen for testing (no app stylesheet)."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _Session:
    """One mounted FWAScreen plus the manager driving it."""

    def __init__(self, app, screen, pilot, recorder, manager) -> None:
        self.app = app
        self.screen = screen
        self.pilot = pilot
        self.recorder = recorder
        self.manager = manager

    async def refresh(self) -> dict:
        """One full cycle, painted.  Returns the payload the screen received."""
        await self.screen._do_refresh()
        await self.pilot.pause()
        await _drain(self.manager)
        await self.pilot.pause()
        assert self.recorder.last is not None
        return self.recorder.last

    async def show_feed(self) -> str:
        """Composited text with the activity feed showing, then switch back.

        The feed shares the odds board's slot behind ``c``, so anything
        asserting on feed content has to switch to it first. This restores the
        previous view before returning so a test can assert on feed *and* odds
        content in any order -- a helper that left the screen toggled would
        silently break every later assertion about the odds board.
        """
        before = getattr(self.screen, "_active_view", "odds")
        if before != "activity":
            await self.pilot.press("c")
            await self.pilot.pause()
        text = self.text
        if before != "activity":
            await self.pilot.press("c")
            await self.pilot.pause()
        return text

    @property
    def text(self) -> str:
        """Composited screen text -- what a user would actually see.

        Reaching into the compositor is the only way to prove a line is *on
        screen* rather than merely present in a widget's content: a box with
        too little vertical room drops its last line silently.
        """
        strips = self.app.screen._compositor.render_strips()
        return "\n".join("".join(seg.text for seg in strip) for strip in strips)

    def plain(self, selector: str) -> str:
        """Rendered text of one widget, for row-level assertions."""
        visual = self.screen.query_one(selector).visual
        return getattr(visual, "plain", str(visual))


@asynccontextmanager
async def _on_screen(manager, *, size=WIDE):
    recorder = _Recorder(manager)
    screen = FWAScreen(recorder, poll_interval=30, name="fwa")
    app = _Harness(screen)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await _drain(manager)
        yield _Session(app, screen, pilot, recorder, manager)
    await _drain(manager)


def _hhmm(ts: float) -> str:
    """The widgets' own ``HH:MM``, computed the same way so the TZ cancels."""
    t = time.localtime(int(ts))
    return f"{t.tm_hour:02d}:{t.tm_min:02d}"


# ===========================================================================
# SCENARIO 1 -- emissions window elapsed.  PRIMARY.
# ===========================================================================
#
# The stop is 1785870083 = 2026-08-04T19:01:23Z.  It lands during this
# project's life, so *no* test may depend on where the wall clock sits
# relative to it: the clock is injected and the ended state -- what the
# dashboard will spend nearly all its time showing -- is asserted first.


async def test_emissions_ended_is_the_primary_rendered_state(tmp_path):
    """A clock past the hard stop renders ``emissions ended``, on screen."""
    clock = FakeClock(DOCUMENTED_EMISSION_STOP + 21 * 86_400)
    manager = _manager(tmp_path, clock=clock)
    async with _on_screen(manager) as session:
        data = await session.refresh()

        assert data["emissions_signal"]["value_str"].startswith("emissions ended")
        text = session.text
        assert "emissions ended · 21d ago · epoch 3" in text
        # Never a countdown that has gone negative (PRD §8).
        assert not NEGATIVE_DURATION.search(session.plain("#fwa-sig-emissions"))
        assert not NEGATIVE_DURATION.search(text), (
            "a negative duration reached the screen: "
            f"{NEGATIVE_DURATION.findall(text)}"
        )


async def test_emissions_ended_leaves_every_other_widget_fully_meaningful(tmp_path):
    """PRD §12.6: the dashboard past the stop is not a degraded dashboard."""
    clock = FakeClock(DOCUMENTED_EMISSION_STOP + 21 * 86_400)
    manager = _manager(tmp_path, clock=clock)
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        # The emissions row is the *only* thing that changed state.
        assert data["degraded_sources"] == []
        for flag in ("price_available", "crown_available", "odds_available",
                     "ev_available", "spark_available", "feed_available",
                     "chase_available", "settle_available"):
            assert data[flag] is True, flag

        assert "ODDS BOARD" in text
        assert "CHASE BOARD" in text
        assert "SETTLEMENT & CROWN" in text
        # The feed shares the odds board's slot behind `c`, so it is not on
        # screen until toggled to -- and it must be intact when it is.
        await session.pilot.press("c")
        await session.pilot.pause()
        assert "ACTIVITY" in session.text
        assert "of weight priced" in text          # the coverage badge
        assert "0.1368" in text                    # the live acquisition fee
        assert "$FWA / USD" in text
        # ...and no widget quietly fell back to an unavailable state.
        for absent in ("insufficient data", "quote unavailable",
                       "crown unavailable", "odds unavailable",
                       "price feed unavailable", "activity paused"):
            assert absent not in text, absent


async def test_emissions_live_countdown_is_the_secondary_state(tmp_path):
    """Before the stop the row counts down -- the other live branch."""
    clock = FakeClock(DOCUMENTED_EMISSION_STOP - (8 * 86_400 + 4 * 3_600))
    manager = _manager(tmp_path, clock=clock)
    async with _on_screen(manager) as session:
        data = await session.refresh()
        assert data["emissions_signal"]["value_str"].startswith("emissions live")
        text = session.text
        assert "emissions live · 8d 4h left · epoch 3" in text
        assert not NEGATIVE_DURATION.search(text)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-365 * 86_400, "emissions live"),   # a year before the stop
        (-1, "emissions live"),              # one second before
        (0, "emissions ended"),              # exactly at it
        (1, "emissions ended"),              # one second after
        (365 * 86_400, "emissions ended"),   # a year after
    ],
)
async def test_emissions_state_follows_the_injected_clock_only(
    tmp_path, offset, expected
):
    """Straddling the stop from both directions, with identical results
    whatever today's date happens to be.

    This is the guard that makes the whole suite reproducible: the state is a
    pure function of ``clock()`` and the two live reads, so the file reads the
    same before and after 2026-08-04T19:01:23Z.
    """
    clock = FakeClock(DOCUMENTED_EMISSION_STOP + offset)
    manager = _manager(tmp_path, clock=clock)
    async with _on_screen(manager) as session:
        await session.refresh()
        text = session.text
        assert expected in text
        assert not NEGATIVE_DURATION.search(text)


async def test_emissions_row_degrades_to_unavailable_not_to_a_countdown(tmp_path):
    """A missing live read is stated, never back-filled from the constants."""
    hot = _hot_batch(emission_start=None, emission_duration=None)
    manager = _manager(tmp_path, state=FakeStateClient(hot=hot))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        assert data["emissions_signal"]["value_str"] == "emissions status unavailable"
        assert "emissions status unavailable" in session.text


# ===========================================================================
# SCENARIO 2 -- logs endpoint down (Pool B).
# ===========================================================================


async def test_logs_down_cold_shows_explicit_unavailable_and_nothing_else_moves(
    tmp_path,
):
    """Tenderly and drpc both dead, nothing ever persisted."""
    manager = _manager(tmp_path, logs=FakeLogClient(available=False))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        assert data["degraded_sources"] == ["logs"]
        assert data["feed_available"] is False
        assert data["feed_unavailable_reason"] == fl.REASON_UNAVAILABLE
        assert data["settle_available"] is False

        # The feed says it is paused, and why -- it does not go blank.
        assert "logs unavailable — activity paused" in await session.show_feed()
        assert fl.REASON_UNAVAILABLE in await session.show_feed()
        assert "no draws recorded yet" in await session.show_feed()
        # The settlement/crown panel likewise.
        assert "logs unavailable" in text
        assert "settlement mix paused" in text
        # Stated once more, permanently, in the title bar.
        assert "degraded: logs" in text

        # ...and every non-log widget still shows real numbers.
        assert "0.1368" in text                       # acquisition fee, hero
        assert "of weight priced" in text             # PULL EV coverage badge
        assert f"block {BLOCK:,}" in text             # odds board, live sweep
        assert "$FWA / USD" in text
        for flag in ("price_available", "crown_available", "odds_available",
                     "ev_available", "spark_available", "chase_available"):
            assert data[flag] is True, flag
        # No stale number is presented: there is nothing to present.
        assert "as of" not in text


async def test_logs_down_warm_serves_last_good_behind_an_explicit_as_of(tmp_path):
    """The Pool B degradation story: stale but *labelled*, never blank."""
    clock = FakeClock()
    logs = FakeLogClient(available=True)
    manager = _manager(tmp_path, logs=logs, clock=clock)
    stamp = _hhmm(AS_OF_TS)

    async with _on_screen(manager) as session:
        good = await session.refresh()
        assert good["settle_available"] is True
        assert good["feed_available"] is True
        # A *live* feed wears no staleness stamp. (The settlement table always
        # carries one: its aggregates are a log capture even when Pool B is up,
        # so "as of" there is a fact, not a degradation marker.)
        await session.show_feed()
        assert "as of" not in session.plain("#fwa-feed-title")

        # The endpoint dies.
        logs.available = False
        clock.advance(600)
        data = await session.refresh()
        text = session.text

        assert data["degraded_sources"] == ["logs"]
        assert data["feed_available"] is False
        assert data["feed_unavailable_reason"] == fl.REASON_UNAVAILABLE
        # The aggregates survive, carrying the timestamp they were captured at.
        assert data["settle_available"] is True
        assert data["settle_as_of_ts"] == pytest.approx(AS_OF_TS)
        assert data["feed_as_of_ts"] == pytest.approx(AS_OF_TS)
        assert data["crown_paid_eth"] == pytest.approx(91.096)

        # On screen: the pause line, the stamp, and the persisted content.
        feed_text = await session.show_feed()
        assert "logs unavailable — activity paused" in feed_text
        assert f"as of {stamp}" in text          # settlement table's stamp
        assert f"last good content, as of {stamp}" in feed_text
        assert "73.92%" in text                      # the persisted mix
        assert "0xcccc..cccc" in text                # the persisted crown row
        assert "degraded: logs" in text

        # Everything else kept working through the failure.
        assert "0.1368" in text
        assert f"block {BLOCK:,}" in text
        assert "of weight priced" in text
        for flag in ("price_available", "crown_available", "odds_available",
                     "ev_available", "spark_available", "chase_available"):
            assert data[flag] is True, flag


async def test_logs_down_does_not_raise_and_the_next_cycle_still_runs(tmp_path):
    manager = _manager(tmp_path, logs=FakeLogClient(available=False))
    async with _on_screen(manager) as session:
        first = await session.refresh()
        manager.clock.advance(120)
        second = await session.refresh()
        assert set(first) == set(FWA_DATA_KEYS)
        assert set(second) == set(FWA_DATA_KEYS)
        assert second["degraded_sources"] == ["logs"]
        assert "SETTLEMENT & CROWN" in session.text


# ===========================================================================
# SCENARIO 3 -- floors partially missing.
# ===========================================================================


async def test_partial_floors_render_a_band_with_its_coverage_badge(tmp_path):
    """22 priced of 38: an EV number is only ever shown *with* its coverage."""
    positions, floors = _wide_pool()
    manager = _manager(
        tmp_path,
        state=FakeStateClient(positions=positions),
        market=FakeMarketClient(floors=floors),
    )
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        assert data["ev_available"] is True
        assert data["ev_collections_priced"] == PRICED_COUNT
        assert data["ev_collections_total"] == POOL_SIZE
        # A band, not a point.
        assert data["pull_ev_lower_eth"] <= data["pull_ev_best_eth"]
        assert data["pull_ev_lower_eth"] < data["pull_ev_best_eth"], (
            "partial coverage must leave the band genuinely open"
        )
        # Coverage by *weight* is the number that matters, and it is small.
        assert 10.0 < data["ev_weight_priced_pct"] < 35.0

        badge = (
            f"{PRICED_COUNT}/{POOL_SIZE} · "
            f"{data['ev_weight_priced_pct']:.1f}% of weight priced"
        )
        assert badge in text, f"coverage badge not on screen; wanted {badge!r}"
        assert "22/38" in text

        # The badge and the number are inseparable: if one is painted so is
        # the other, and neither is painted without the other.
        best = f"{data['pull_ev_best_eth']:+,.4f}"
        assert best in text
        ev_row = session.plain("#fwa-hero-ev")
        assert best in ev_row and "of weight priced" in ev_row


async def test_partial_floors_never_fabricate_a_floor_on_the_odds_board(tmp_path):
    """An unpriced row is marked unpriced -- never rendered as ``0``."""
    positions, floors = _wide_pool()
    manager = _manager(
        tmp_path,
        state=FakeStateClient(positions=positions),
        market=FakeMarketClient(floors=floors),
    )
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        rows = data["collection_odds"]
        assert len(rows) == POOL_SIZE
        priced = [r for r in rows if r["floor_eth"] is not None]
        assert len(priced) == PRICED_COUNT
        assert all(r["floor_eth"] > 0 for r in priced), "a 0.0 floor was published"
        # An unpriced collection also withholds the derived ETH/ODDS ratio.
        for row in rows:
            if row["floor_eth"] is None:
                assert row["eth_per_odds_point"] is None, row["name"]

        # The suppressed contract is ranked first, so its mark is on screen...
        assert rows[0]["address"] == ART_BLOCKS
        assert rows[0]["floor_source"] == "suppressed"
        assert "n/a*" in text
        # ...together with the footnote that says why.
        assert "one contract hosts many collections" in text
        # ...and the hard misses read as an em dash, not a zero.
        assert "—" in text


async def test_a_zero_floor_would_raise_the_pessimistic_bound(tmp_path):
    """TRAP 1 -- a ``0.0`` floor must never enter the EV.

    It *raises* ``lower_eth`` (``max(sellback, 0.0)`` hands the position its
    full sell-back value inside the pessimistic bound) and inflates
    ``collections_priced``, collapsing the band toward a confident lie from the
    direction nobody expects.  Asserted as a direction, not just as an absence:
    the wrong answer is measurably *better looking* than the right one.
    """
    positions, floors = _wide_pool()
    pairs = [(p.backing_wei, str(p.collection).lower()) for p in positions]
    honest = floors_for_ev(floors)
    zeroed = {
        str(p.collection).lower(): honest.get(str(p.collection).lower(), 0.0)
        for p in positions
    }

    fee = 136_829_134_522_020_108
    good = fwa_ev.pull_ev_band(pairs, honest, fee, 8_500, 0.0)
    bad = fwa_ev.pull_ev_band(pairs, zeroed, fee, 8_500, 0.0)

    # floors_for_ev omits, it does not zero.
    assert len(honest) == PRICED_COUNT
    assert set(honest) < set(zeroed)
    assert all(v is not None and v > 0 for v in honest.values())

    assert bad["lower_eth"] > good["lower_eth"], (
        "a 0.0 floor did not raise the pessimistic bound -- the trap has moved"
    )
    assert bad["collections_priced"] == POOL_SIZE
    assert good["collections_priced"] == PRICED_COUNT
    assert bad["weight_priced_pct"] > good["weight_priced_pct"]

    # And the screen shows the honest one.
    manager = _manager(
        tmp_path,
        state=FakeStateClient(positions=positions),
        market=FakeMarketClient(floors=floors),
    )
    async with _on_screen(manager) as session:
        data = await session.refresh()
        assert data["ev_collections_priced"] == good["collections_priced"]
        assert data["pull_ev_lower_eth"] == pytest.approx(good["lower_eth"])
        assert f"{PRICED_COUNT}/{POOL_SIZE}" in session.text
        assert f"{POOL_SIZE}/{POOL_SIZE}" not in session.text


# ===========================================================================
# SCENARIO 4 -- RPC fallback exhausted (Pool A).
# ===========================================================================


async def test_rpc_exhausted_cold_renders_explicit_unavailable_hero_cards(tmp_path):
    """publicnode + cloudflare + 1rpc all dead, with nothing cached."""
    manager = _manager(tmp_path, state=FakeStateClient(fail=True))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        assert data["degraded_sources"] == ["chain"]
        assert data["error_count"] > 0

        # Chain-derived is None, never 0.
        for key in ("acquisition_fee_eth", "quote_total_eth", "crown_pot_eth",
                    "crown_seize_eth", "core_balance_eth",
                    "cumulative_revenue_eth", "harmonic_mean_eth"):
            assert data[key] is None, f"{key} degraded to a number"
        for flag in ("price_available", "crown_available", "odds_available",
                     "ev_available", "chase_available"):
            assert data[flag] is False, flag

        # Every chain card says so in words.
        assert "quote unavailable" in text
        assert "crown unavailable" in text
        assert "insufficient data" in text
        assert "odds unavailable — position sweep failed" in text
        assert "positions unavailable" in text
        assert "degraded: chain" in text
        # The em-dash placeholder, never a zero.
        assert "— ETH in core" in text
        assert "fee — ETH" in text

        # Log- and market-derived widgets keep working.
        assert data["feed_available"] is True
        assert data["settle_available"] is True
        assert data["spark_available"] is True
        assert "73.92%" in text
        assert "$FWA / USD" in text
        assert "sold back ($FWA)" in await session.show_feed()


async def test_rpc_exhausted_warm_shows_last_good_block_marked_stale(tmp_path):
    """A cached sweep is still a sweep -- but it is labelled, and pinned."""
    clock = FakeClock()
    state = FakeStateClient()
    manager = _manager(tmp_path, state=state, clock=clock)

    async with _on_screen(manager) as session:
        good = await session.refresh()
        assert good["odds_stale"] is False
        assert "STALE" not in session.text

        state.fail = True
        clock.advance(120)                    # medium tier due -> sweep retried
        data = await session.refresh()
        text = session.text

        assert "chain" in data["degraded_sources"]
        # The board still renders, pinned to the block it was pinned to...
        assert data["odds_available"] is True
        assert data["odds_as_of_block"] == BLOCK
        assert f"block {BLOCK:,}" in text
        # ...and says it is not live.
        assert data["odds_stale"] is True
        assert "STALE — last good sweep" in text
        assert "degraded: chain" in text

        # Log-derived widgets are untouched by a dead RPC.
        assert data["feed_available"] is True
        assert "sold back ($FWA)" in await session.show_feed()
        assert "73.92%" in text

        # The error counter moved and the next cycle still runs.
        assert data["error_count"] > good["error_count"]
        clock.advance(120)
        third = await session.refresh()
        assert set(third) == set(FWA_DATA_KEYS)
        assert state.sweep_calls >= 3


async def test_a_failed_read_is_none_never_a_closed_buy_gate(tmp_path):
    """TRAP 2 -- ``externalBuysEnabled()`` legitimately reads ``false``.

    So does ``TTT_AMOUNT()`` and ``lastBuybackBlock()``.  A dead RPC that
    degraded to ``0`` would render as a *closed gate*, which is a real
    protocol state and the exact shape of a silently wrong number.
    """
    hot = _hot_batch(external_buys_enabled=None, ttt_amount=None,
                     last_buyback_block=None)
    manager = _manager(tmp_path, state=FakeStateClient(hot=hot))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        gate = data["buy_gate_signal"]
        text = session.text

        assert gate["color"] == "dim"
        assert "unavailable" in gate["value_str"].lower()
        assert "buy gate unavailable" in text
        assert "GATED" not in text, "an unreadable gate rendered as a closed gate"
        assert "OPEN" not in text

    # ...while a genuine ``false`` is loud.
    manager2 = _manager(tmp_path, state=FakeStateClient())
    async with _on_screen(manager2) as session:
        data = await session.refresh()
        assert data["buy_gate_signal"]["color"] == SIGNAL_BAD
        assert "GATED — no outside buys" in session.text


# ===========================================================================
# SCENARIO 5 -- market data down (Pool C).
# ===========================================================================


async def test_market_down_renders_no_invented_exchange_rate(tmp_path):
    """DexScreener + GeckoTerminal dead: ETH stays ETH, USD goes ``—``."""
    manager = _manager(tmp_path, market=FakeMarketClient(fail=True))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        assert data["degraded_sources"] == ["market"]
        assert data["spark_available"] is False
        assert data["fwa_price_usd"] is None
        assert data["fwa_price_change_24h"] is None
        assert data["take_rate_pct"] is None
        # The crown pot exists in ETH and has no USD leg -- no derived rate.
        assert data["crown_pot_eth"] is not None
        assert data["crown_pot_usd"] is None

        assert "price feed unavailable" in text
        assert "no market data" in text
        assert "usd n/a" in text
        assert "$FWA / USD" in text          # the row itself is still there
        assert "degraded: market" in text
        assert "$0.00" not in text, "a missing USD price rendered as a number"
        assert "take " not in text           # no take-rate field without a source

        # Chain- and log-derived widgets are untouched.
        assert data["price_available"] is True
        assert data["feed_available"] is True
        assert "0.1368" in text
        assert "73.92%" in text


async def test_market_down_degrades_the_ev_to_unpriced_not_to_a_confident_zero(
    tmp_path,
):
    """No floors at all is 0 priced, stated -- not 38 collections worth 0."""
    manager = _manager(tmp_path, market=FakeMarketClient(fail=True))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        assert data["ev_collections_priced"] == 0
        assert data["ev_collections_total"] == 3
        assert data["ev_weight_priced_pct"] == pytest.approx(0.0)
        assert "0/3 · 0.0% of weight priced" in session.text
        # Every odds row is honestly unpriced.
        assert all(r["floor_eth"] is None for r in data["collection_odds"])


# ===========================================================================
# SCENARIO 6 -- combined worst case.
# ===========================================================================


@pytest.mark.parametrize("size", [WIDE, NARROW], ids=["200x50", "140x42"])
async def test_all_three_pools_dead_with_an_empty_cache(tmp_path, size):
    """Every widget shows an explicit unavailable state, at either width."""
    manager = _manager(
        tmp_path,
        state=FakeStateClient(fail=True),
        logs=FakeLogClient(available=False),
        market=FakeMarketClient(fail=True),
    )
    async with _on_screen(manager, size=size) as session:
        data = await session.refresh()
        text = session.text

        # The frozen contract survives a total blackout.
        assert set(data) == set(FWA_DATA_KEYS)
        assert len(data) == len(FWA_DATA_KEYS)
        assert data["degraded_sources"] == ["chain", "logs", "market"]
        for flag in ("ev_available", "price_available", "crown_available",
                     "odds_available", "spark_available", "feed_available",
                     "chase_available", "settle_available"):
            assert data[flag] is False, flag
        assert data["error_count"] > 0

        # Seven widgets, seven explicit unavailable states.
        assert "insufficient data" in text          # PULL EV
        assert "quote unavailable" in text          # PRICE
        assert "crown unavailable" in text          # CROWN
        assert "odds unavailable" in text           # odds board
        assert "price feed unavailable" in text     # sparkline
        assert "unavailable" in session.plain("#fwa-sig-pool-temp")   # signals
        assert "activity paused" in await session.show_feed()   # activity feed
        assert "positions unavailable" in text      # chase board
        assert "logs unavailable" in text           # settlement table
        assert "degraded: chain, logs, market" in text

        # ...and the panel frames are all still standing, not blank.
        for title in ("ODDS BOARD", "CHASE BOARD", "SETTLEMENT & CROWN",
                      "SIGNALS", "$FWA PRICE"):
            assert title in text, title
        # The feed lives behind `c`; a blackout must not stop it rendering
        # its own frame when switched to.
        await session.pilot.press("c")
        await session.pilot.pause()
        assert "ACTIVITY" in session.text


async def test_worst_case_still_refreshes_on_the_next_cycle(tmp_path):
    """A blackout is a state, not a stop: the screen keeps ticking."""
    clock = FakeClock()
    manager = _manager(
        tmp_path,
        state=FakeStateClient(fail=True),
        logs=FakeLogClient(available=False),
        market=FakeMarketClient(fail=True),
        clock=clock,
    )
    async with _on_screen(manager) as session:
        for _ in range(3):
            data = await session.refresh()
            assert set(data) == set(FWA_DATA_KEYS)
            clock.advance(120)
        assert session.recorder.calls >= 3
        assert "ODDS BOARD" in session.text


async def test_worst_case_recovers_when_the_pools_come_back(tmp_path):
    """The unavailable state clears itself -- it is not sticky."""
    clock = FakeClock()
    state = FakeStateClient(fail=True)
    logs = FakeLogClient(available=False)
    market = FakeMarketClient(fail=True)
    manager = _manager(tmp_path, state=state, logs=logs, market=market, clock=clock)

    async with _on_screen(manager) as session:
        dark = await session.refresh()
        assert dark["degraded_sources"] == ["chain", "logs", "market"]

        state.fail = logs.available = market.fail = False
        logs.available = True
        clock.advance(1_200)                 # every tier due again
        data = await session.refresh()
        text = session.text

        assert data["degraded_sources"] == []
        assert "degraded:" not in text
        assert "insufficient data" not in text
        assert "quote unavailable" not in text
        assert "activity paused" not in await session.show_feed()
        assert "0.1368" in text


# ===========================================================================
# SCENARIO 7 -- invariant mismatch.
# ===========================================================================


async def test_invariant_mismatch_renders_the_board_stale_and_withholds_the_ev(
    tmp_path,
):
    """The subtle one: the odds board is *old*, the EV would be *wrong*.

    A listing is still a listing, so the rows keep rendering behind a STALE
    marker.  An EV derived from an incomplete position set is not stale but
    incorrect, so it is withheld entirely (PRD §7 rule 11) -- and this test
    asserts that the number the manager still carries in the payload never
    reaches a pixel.
    """
    manager = _manager(tmp_path, state=FakeStateClient(invariants_ok=False))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        assert data["invariants_ok"] is False
        assert data["odds_stale"] is True
        assert data["ev_available"] is False

        # Half one: the board still shows, with its rows and its block, marked.
        assert data["odds_available"] is True
        assert len(data["collection_odds"]) == 3
        assert data["odds_as_of_block"] == BLOCK
        assert f"block {BLOCK:,}" in text
        assert "3 collections" in text
        assert "STALE — last good sweep" in text
        assert "⚠ invariant mismatch" in text

        # Half two: no EV number, but the coverage frame stays put.
        assert "insufficient data" in text
        assert "of weight priced" in text

        # Nothing derived from the bad sweep is displayed. The manager still
        # computes the band -- withholding is a *rendering* decision -- so the
        # exact strings it would have printed must be absent from the screen.
        assert data["pull_ev_best_eth"] is not None
        for value in (data["pull_ev_best_eth"], data["pull_ev_lower_eth"]):
            assert f"{value:+,.4f}" not in text, (
                f"an EV number from an incomplete sweep reached the screen: {value}"
            )
        ev_row = session.plain("#fwa-hero-ev")
        assert "insufficient data" in ev_row
        assert "▲" not in ev_row and "▼" not in ev_row


async def test_invariant_mismatch_leaves_the_log_and_market_panels_alone(tmp_path):
    """A bad sweep is a Pool A problem and must not darken the others."""
    manager = _manager(tmp_path, state=FakeStateClient(invariants_ok=False))
    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text
        assert data["feed_available"] is True
        assert data["settle_available"] is True
        assert data["spark_available"] is True
        assert "sold back ($FWA)" in await session.show_feed()
        assert "73.92%" in text
        assert "$FWA / USD" in text


# ===========================================================================
# TRAP 3 -- aggregate counts must survive log trimming.
# ===========================================================================


def _trimmed_sidecar(tmp_path) -> tuple[dict, dict]:
    """Run the *real* trim over the *real* all-time settlement history.

    Returns ``(sidecar, full_mix)``: the parsed on-disk state and the mix the
    untrimmed store reported, so the test can prove the trim really did bite.
    """
    logs = OfflineLogClient()
    _populate(
        logs,
        {
            name: (count, BLOCK - 60_000, BLOCK)
            for name, count in ALLTIME_SETTLEMENT_COUNTS.items()
        }
        | {
            # All-time events, retained whole by policy.
            "TopListingSet": (33, BLOCK - 60_000, BLOCK - 50_000),
            "TopListingSettled": (12, BLOCK - 60_000, BLOCK - 50_000),
        },
    )
    full_mix = {row.outcome: row.share_pct for row in logs.settlement_mix()}

    writer = _manager(tmp_path, logs=logs, persist_log_state=True,
                      log_raw_window_blocks=300)
    writer._save_log_state()
    sidecar = json.loads((tmp_path / "fwa_log_state.json").read_text())
    return sidecar, full_mix


def test_the_trim_really_does_truncate_the_settlement_store(tmp_path):
    """The premise: a 300-block window over 51,522 events is destructive.

    Without this, the repair test below would pass vacuously.
    """
    sidecar, full_mix = _trimmed_sidecar(tmp_path)

    assert full_mix["bid_fwa"] == pytest.approx(73.92, abs=0.01)
    trimmed = 0
    for name, count in ALLTIME_SETTLEMENT_COUNTS.items():
        kept = len(sidecar["events"].get(name) or [])
        # The row floor keeps the newest LOG_RAW_MIN_ROWS regardless of the
        # window, so a low-volume event (UnsettledFinalized: 2 all-time) is
        # legitimately kept whole. The high-volume ones are what must shrink.
        if count > LOG_RAW_MIN_ROWS:
            assert kept < count, f"{name} was not trimmed at all"
            assert kept <= LOG_RAW_MIN_ROWS + 1, f"{name} barely shrank"
            trimmed += 1
        # ...and the all-time count baseline records what was really there.
        assert sidecar["event_baseline"][name] == count
    assert trimmed == 4, "the four high-volume settlement events must all trim"
    assert sidecar["event_baseline_block"] == BLOCK
    # The all-time events are never windowed.
    assert len(sidecar["events"]["TopListingSet"]) == 33


async def test_settlement_mix_survives_a_log_trim_all_the_way_to_the_screen(
    tmp_path,
):
    """TRAP 3 -- the mix is baseline + post-baseline events, never ``len()``.

    A naive ``len(store[event])`` over a trimmed store turns 73.92% of 51,522
    into a percentage of the last few hundred blocks.  The all-time count
    baseline is what prevents it, and the assertion has to be made on the
    composited screen: a repaired dict that never reaches the SHARE column
    would be no repair at all.
    """
    sidecar, full_mix = _trimmed_sidecar(tmp_path)

    # A fresh process: same sidecar, an empty real log client to restore into.
    restored_logs = OfflineLogClient()
    manager = _manager(tmp_path, logs=restored_logs)
    assert manager._event_baseline, "the count baseline did not survive the restore"

    # What the naive path would have produced from the trimmed store.
    naive = {row.outcome: row.share_pct for row in restored_logs.settlement_mix()}
    assert naive["bid_fwa"] != pytest.approx(full_mix["bid_fwa"], abs=0.05), (
        "the trimmed store already reports the all-time mix -- "
        "this test can no longer prove the baseline is doing anything"
    )

    async with _on_screen(manager) as session:
        data = await session.refresh()
        text = session.text

        mix = {row["outcome"]: row for row in data["settlement_mix"]}
        for name, outcome in fl.SETTLEMENT_EVENTS.items():
            assert mix[outcome]["count"] == ALLTIME_SETTLEMENT_COUNTS[name], outcome
            assert mix[outcome]["share_pct"] == pytest.approx(full_mix[outcome])

        # ...and the repaired shares are painted, to two decimals.
        for share in ALLTIME_SHARES:
            assert share in text, f"{share} never reached the SHARE column"
        # The window's own answer is emphatically not on screen.
        assert f"{naive['bid_fwa']:.2f}%" not in text


async def test_crown_totals_are_all_time_across_a_trim(tmp_path):
    """``TopListingSet``/``Settled`` are retained whole for the same reason."""
    _trimmed_sidecar(tmp_path)
    restored_logs = OfflineLogClient()
    manager = _manager(tmp_path, logs=restored_logs)
    async with _on_screen(manager) as session:
        data = await session.refresh()
        assert data["crown_sets_total"] == 33
        assert data["crown_payouts_total"] == 12
        assert "SETTLEMENT & CROWN" in session.text


# ===========================================================================
# Cross-cutting: no crash, ever
# ===========================================================================


@pytest.mark.parametrize(
    ("chain", "logs_up", "market"),
    [
        (dead, up, dead_m)
        for dead in (False, True)
        for up in (True, False)
        for dead_m in (False, True)
    ],
)
async def test_every_failure_combination_returns_the_full_contract(
    tmp_path, chain, logs_up, market
):
    """All eight pool combinations: full key set, no exception, screen stands."""
    manager = _manager(
        tmp_path,
        state=FakeStateClient(fail=chain),
        logs=FakeLogClient(available=logs_up),
        market=FakeMarketClient(fail=market),
    )
    async with _on_screen(manager) as session:
        data = await session.refresh()
        assert set(data) == set(FWA_DATA_KEYS)
        text = session.text
        # The frame is always there, whatever died.
        for title in ("ODDS BOARD", "CHASE BOARD", "SETTLEMENT & CROWN",
                      "SIGNALS"):
            assert title in text, title
        await session.pilot.press("c")
        await session.pilot.pause()
        assert "ACTIVITY" in session.text
        # No traceback text ever reaches a widget.
        assert "Traceback" not in text
        assert "Error" not in text


async def test_a_manager_that_raises_outright_leaves_the_screen_standing(tmp_path):
    """The outermost guard: even a broken manager only marks the StatusBar."""

    class _Exploding:
        _error_count = 7

        async def fetch_and_compute(self):
            raise RuntimeError("all three pools are down")

        async def close(self):
            pass

    async with _on_screen(_Exploding()) as session:
        await session.screen._do_refresh()      # must not raise
        await session.pilot.pause()
        text = session.text
        assert "ODDS BOARD" in text
        assert "SETTLEMENT & CROWN" in text
        assert "Gacha Terminal" in text
