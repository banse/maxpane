"""WP-12 — orchestration, tiering and degradation tests for :class:`FWAManager`.

Zero network: all three clients are doubles, the clock is a fake, and both
persistence paths point at ``tmp_path``.  Nothing here sleeps.

The centre of gravity is degradation, because that is the deliverable: the manager
must return exactly ``FWA_DATA_KEYS`` under **every** combination of pool failures,
must never let an exception escape, and must let each pool's death darken exactly
one region of the screen.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.data.fwa_cache import (
    TIER_FAST,
    TIER_MEDIUM,
    FWACache,
)
from maxpane_dashboard.data.fwa_client import FWA_HOT_KEYS
from maxpane_dashboard.data.fwa_manager import COINGECKO_MIN_SPACING, FWAManager
from maxpane_dashboard.data.fwa_market import FloorQuote
from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS, FWA_ROW_KEYS, Position

# ---------------------------------------------------------------------------
# Fixture data — shaped like the live pool, small enough to reason about
# ---------------------------------------------------------------------------

BLOCK = 25_612_701
ETH = 10**18

COLL_CHEAP = "0x" + "11" * 20     # the dust that owns the draw
COLL_MID = "0x" + "22" * 20
COLL_PUNKS = "0x" + "99" * 20     # 221 ETH for ~0.000% of the weight

CROWN_LISTING_ID = 56_508
CROWN_HOLDER = "0x" + "cc" * 20


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
        "mismatches": () if invariants_ok else ("count 3 != activeListingCount 4",),
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
    """A hot batch with every key present, matching ``FWA_HOT_KEYS`` discipline."""
    hot = dict.fromkeys(FWA_HOT_KEYS)
    hot.update(
        {
            "acquisition_fee": 136_829_134_522_020_108,
            "total_weight": 31_280_618_816_683_353_089_152,
            "weighted_backing_total": 3_890_999_999_999_999_999_275_601_332_649_457_427_323,
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
            "accrued_owner_fees": 0,
            "acquisition_escrow_total": 0,
            "acquisition_refund_credit_total": 0,
            "reserved_staged_count": 0,
            "pending_acquisition_count": 2,
            "unsettled_acquisition_count": 1,
            "unfulfilled_vrf_count": 0,
            "last_issued_sequence": 120,
            "next_sequence_to_process": 105,
            "emission_start": 1_784_574_083,
            "emission_duration": 15 * 24 * 3_600,
            "current_epoch": 3,
            "hot_gap": 60,
            "cold_gap": 3_600,
            "forced_token_share_bps": -1,
            "last_acquisition_ts": 1_785_900_000,
            "sqrt_backing_total": 1,
            "token_buy_allowance_total": 0,
            "subscription_native_balance": 5 * ETH,
            "minimum_subscription_buffer": ETH,
            "available_processor_surplus": 0,
            "token_total_supply": 1_000_000_000 * ETH,
            "token_launched": True,
            "last_buyback_block": 0,
            "token_symbol": "FWA",
            "external_buys_enabled": False,
            "ttt_amount": 0,
            "splitter_total_received": 91 * ETH,
            "splitter_claimable_per_token": 0,
            "quote_fee_wei": 136_829_134_522_020_108,
            "quote_vrf_wei": 1_040_000_000_000_000,
            "quote_total_wei": 137_869_134_522_020_108,
            "quote_gas_price_wei": 1_000_000_000,
            "token_share_bps": 0,
            "_ok": True,
            "_failed": (),
            "_fetched_at": 1_785_900_100.0,
            "_error": None,
        }
    )
    hot.update(over)
    return hot


def _log_snapshot(*, available: bool = True, as_of_ts: float | None = 1_785_900_000.0) -> dict:
    return {
        "available": available,
        "reason": None if available else "logs endpoint unavailable",
        "as_of_ts": as_of_ts,
        "last_seen_block": BLOCK,
        "settlement_mix": [
            {"outcome": "bid_fwa", "label": "Accept bid, paid in $FWA",
             "count": 38_083, "share_pct": 73.92},
            {"outcome": "bid_eth", "label": "Accept bid, paid in ETH",
             "count": 7_131, "share_pct": 13.84},
            {"outcome": "relist", "label": "Purchaser relists", "count": 3_936,
             "share_pct": 7.64},
            {"outcome": "kept", "label": "Keep the NFT", "count": 2_370,
             "share_pct": 4.60},
            {"outcome": "forced", "label": "Force-finalized", "count": 2,
             "share_pct": 0.0},
        ],
        # Presentation payload with no model behind it: already ETH.
        "crown_history": [
            {"rank": 1, "holder": CROWN_HOLDER, "reigns": 4,
             "payout_eth": 41.5, "last_block": BLOCK, "last_ts": 1_785_899_000},
        ],
        "crown_sets_total": 17,
        "crown_payouts_total": 12,
        "crown_paid_eth": 91.096,
        # Wei-native: DrawEvent dumps carry amount_wei, the manager emits amount_eth.
        "draw_events": [
            {
                "ts": 1_785_899_900,
                "block_number": BLOCK,
                "tx_hash": "0x" + "ab" * 32,
                "purchaser": "0x" + "de" * 20,
                "collection": COLL_CHEAP,
                "collection_name": None,
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
    """Only the cheap collection is priced — 1 of 3, like the live 22 of 38."""
    return {
        COLL_CHEAP: FloorQuote(
            address=COLL_CHEAP,
            floor_eth=0.0421,
            source="coingecko",
            status="ok",
            name="Ten Thousand Tokens",
            fetched_at=1_785_899_000.0,
        ),
        COLL_MID: FloorQuote(
            address=COLL_MID,
            floor_eth=None,
            source="missing",
            status="missing",
            note="no CoinGecko listing for this contract",
            fetched_at=1_785_899_000.0,
        ),
        COLL_PUNKS: FloorQuote(
            address=COLL_PUNKS,
            floor_eth=None,
            source="suppressed",
            status="suppressed",
            note="multi-collection contract — floor not meaningful",
            fetched_at=1_785_899_000.0,
        ),
    }


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 1_785_900_100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeStateClient:
    """Pool A double.  ``fail`` makes every read behave like a dead RPC."""

    def __init__(self, *, fail: bool = False, invariants_ok: bool = True) -> None:
        self.fail = fail
        self.invariants_ok = invariants_ok
        self.positions = _positions()
        self.hot_calls = 0
        self.sweep_calls = 0
        self.balance_calls = 0
        self.closed = False
        self.sweep_gate: asyncio.Event | None = None
        self.raise_on_hot = False

    async def fetch_hot_batch(self, **_kwargs):
        self.hot_calls += 1
        if self.raise_on_hot:
            raise RuntimeError("every endpoint refused")
        if self.fail:
            # Exactly what the real client returns on a dead pool: every key
            # present, every value None, never a zero.
            out = dict.fromkeys(FWA_HOT_KEYS)
            out.update({"_ok": False, "_failed": tuple(FWA_HOT_KEYS),
                        "_error": "all endpoints failed", "_fetched_at": 0.0})
            return out
        return _hot_batch()

    async def sweep_positions(self, **_kwargs):
        self.sweep_calls += 1
        if self.sweep_gate is not None:
            await self.sweep_gate.wait()
        if self.fail:
            return (0, [], {"invariants_ok": False, "collected": 0, "expected": 0,
                            "skipped": False, "mismatches": ("sweep failed",)})
        return (
            BLOCK,
            list(self.positions),
            _sweep_report(self.positions, invariants_ok=self.invariants_ok),
        )

    async def fetch_eth_balance(self, *_a, **_k):
        self.balance_calls += 1
        return 0 if self.fail else 2_551 * ETH

    async def close(self):
        self.closed = True


class FakeLogClient:
    """Pool B double."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.backfills = 0
        self.tails = 0
        self.closed = False
        self.state_imported = None
        self.raise_on_snapshot = False

    async def head_block(self):
        return BLOCK

    async def backfill(self, _from_block, _to_block, _events=None):
        self.backfills += 1
        return {"available": self.available, "added": 1}

    async def tail(self, *_a, **_k):
        self.tails += 1
        return {"available": self.available, "added": 0}

    def snapshot(self, *, feed_limit: int = 50):
        if self.raise_on_snapshot:
            raise RuntimeError("decoder blew up")
        snap = _log_snapshot(available=self.available)
        snap["draw_events"] = snap["draw_events"][:feed_limit]
        if not self.available:
            # Never scanned successfully in this process: nothing in the store.
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
                    "as_of_ts": None,
                }
            )
        return snap

    def entries(self, event):
        if event == "ConfigSet":
            return [{"key": 15, "value": 100, "block_number": 25_592_190,
                     "log_index": 0}]
        return []

    def backing_updates(self, since: int = 0):
        return []

    def export_state(self):
        return {"version": 1, "last_seen_block": BLOCK, "scanned_from": 0,
                "as_of_ts": 1_785_900_000.0, "launch_block": None, "events": {}}

    def import_state(self, state):
        self.state_imported = state
        return bool(state)

    async def close(self):
        self.closed = True


class FakeMarketClient:
    """Pool C double.  Records the CoinGecko spacing it was constructed with."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.market_calls = 0
        self.ohlcv_calls = 0
        self.floor_sweeps = 0
        self.closed = False
        self.floors = _floor_quotes()

    async def fetch_fwa_market(self, *, force: bool = False):
        self.market_calls += 1
        return (None, False) if self.fail else (_market_payload(), True)

    async def fetch_ohlcv_hour(self, *, limit: int = 100, hours=None):
        self.ohlcv_calls += 1
        if self.fail:
            return [], False
        return [[1_785_896_400 + 3600 * i, 0.0004 + i / 100_000] for i in range(5)], True

    async def fetch_protocol_fees(self, *, force: bool = False):
        if self.fail:
            return None, False
        return {"take_rate_pct": 8.8, "fees_24h": 12.0, "revenue_24h": 1.05}, True

    async def fetch_nft_floors(self, addresses, **_kwargs):
        self.floor_sweeps += 1
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


# ---------------------------------------------------------------------------
# Fixtures
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
    manager._clock_double = clock  # convenience handle for the tests
    return manager


@pytest.fixture
def manager(tmp_path):
    return _manager(tmp_path)


async def _drain(manager):
    """Let any detached floor task finish so no test leaks a pending task."""
    task = manager._floor_task
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# The frozen contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_exactly_fwa_data_keys(manager):
    data = await manager.fetch_and_compute()
    assert set(data) == set(FWA_DATA_KEYS)
    assert len(data) == len(FWA_DATA_KEYS)
    await _drain(manager)


@pytest.mark.asyncio
async def test_crown_listing_id_is_a_data_key_and_is_dispatched(manager):
    """WP-11's chase board can only flag the crown/jackpot coincidence with this."""
    assert "crown_listing_id" in FWA_DATA_KEYS
    data = await manager.fetch_and_compute()
    assert data["crown_listing_id"] == CROWN_LISTING_ID
    # and it names a row the board actually renders
    assert CROWN_LISTING_ID in {row["listing_id"] for row in data["chase_positions"]}
    await _drain(manager)


@pytest.mark.asyncio
async def test_row_payloads_match_the_frozen_row_keys(manager):
    data = await manager.fetch_and_compute()
    for payload, keys in FWA_ROW_KEYS.items():
        for row in data[payload]:
            assert set(row) == set(keys), payload
    await _drain(manager)


# ---------------------------------------------------------------------------
# Degradation — one dead source darkens exactly one region
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_pool_failure_degrades_only_state_widgets(tmp_path):
    manager = _manager(tmp_path, state=FakeStateClient(fail=True))
    data = await manager.fetch_and_compute()

    assert data["degraded_sources"] == ["chain"]
    # chain-derived goes dark, and says so
    assert data["price_available"] is False
    assert data["acquisition_fee_eth"] is None
    assert data["crown_available"] is False
    assert data["ev_available"] is False
    assert data["odds_available"] is False
    assert data["odds_stale"] is True
    assert data["core_balance_eth"] is None
    # log-derived and market-derived keep working
    assert data["feed_available"] is True
    assert data["settle_available"] is True
    assert data["crown_paid_eth"] == pytest.approx(91.096)
    assert data["spark_available"] is True
    assert data["fwa_price_usd"] == pytest.approx(0.0004)
    await _drain(manager)


@pytest.mark.asyncio
async def test_log_pool_failure_degrades_only_log_widgets(tmp_path):
    manager = _manager(tmp_path, logs=FakeLogClient(available=False))
    data = await manager.fetch_and_compute()

    assert data["degraded_sources"] == ["logs"]
    assert data["feed_available"] is False
    assert data["feed_unavailable_reason"] == "logs endpoint unavailable"
    assert data["settle_available"] is False
    # everything else is untouched
    assert data["price_available"] is True
    assert data["crown_available"] is True
    assert data["odds_available"] is True
    assert data["ev_available"] is True
    assert data["spark_available"] is True
    await _drain(manager)


@pytest.mark.asyncio
async def test_market_pool_failure_degrades_only_market_widgets(tmp_path):
    manager = _manager(tmp_path, market=FakeMarketClient(fail=True))
    data = await manager.fetch_and_compute()

    assert data["degraded_sources"] == ["market"]
    assert data["spark_available"] is False
    assert data["fwa_price_usd"] is None
    assert data["fwa_price_change_24h"] is None
    # No USD source means no USD cell — never an invented rate.
    assert data["crown_pot_usd"] is None
    assert data["crown_pot_eth"] is not None
    assert data["take_rate_pct"] is None
    # chain and logs keep working, and the EV degrades to unpriced rather than
    # to a confident zero
    assert data["price_available"] is True
    assert data["feed_available"] is True
    assert data["ev_available"] is True
    assert data["ev_collections_priced"] == 0
    assert data["ev_collections_total"] == 3
    await _drain(manager)


@pytest.mark.asyncio
async def test_all_pools_fail_still_returns_full_key_set(tmp_path):
    manager = _manager(
        tmp_path,
        state=FakeStateClient(fail=True),
        logs=FakeLogClient(available=False),
        market=FakeMarketClient(fail=True),
    )
    data = await manager.fetch_and_compute()

    assert set(data) == set(FWA_DATA_KEYS)
    assert data["degraded_sources"] == ["chain", "logs", "market"]
    for flag in (
        "ev_available", "price_available", "crown_available", "odds_available",
        "spark_available", "feed_available", "chase_available", "settle_available",
    ):
        assert data[flag] is False, flag
    assert data["error_count"] > 0
    await _drain(manager)


@pytest.mark.asyncio
async def test_degraded_sources_populated_and_sorted(tmp_path):
    manager = _manager(
        tmp_path,
        logs=FakeLogClient(available=False),
        market=FakeMarketClient(fail=True),
    )
    data = await manager.fetch_and_compute()
    assert data["degraded_sources"] == ["logs", "market"]
    assert "chain" not in data["degraded_sources"]
    await _drain(manager)


@pytest.mark.asyncio
async def test_no_exception_escapes_when_a_pool_raises(tmp_path):
    """A pool that raises is caught by ``gather`` and reported, not propagated."""
    state = FakeStateClient()
    state.raise_on_hot = True
    logs = FakeLogClient()
    logs.raise_on_snapshot = True
    manager = _manager(tmp_path, state=state, logs=logs)

    data = await manager.fetch_and_compute()
    assert set(data) == set(FWA_DATA_KEYS)
    assert "logs" in data["degraded_sources"]
    assert data["feed_available"] is False
    await _drain(manager)


@pytest.mark.asyncio
async def test_log_pool_failure_serves_last_good_with_its_original_as_of_ts(tmp_path):
    """Pool B is the single point of failure — it must go stale, not blank."""
    clock = FakeClock()
    logs = FakeLogClient(available=True)
    manager = _manager(tmp_path, logs=logs, clock=clock)

    first = await manager.fetch_and_compute()
    assert first["settle_available"] is True
    good_ts = first["settle_as_of_ts"]
    assert good_ts == pytest.approx(1_785_900_000.0)
    await _drain(manager)

    # A fresh process: same cache file, nothing in the log store, endpoint dead.
    logs_down = FakeLogClient(available=False)
    revived = FWAManager(
        poll_interval=30,
        clock=clock,
        cache_path=str(tmp_path / "fwa_cache.json"),
        log_state_path=str(tmp_path / "fwa_log_state.json"),
        client=FakeStateClient(),
        log_client=logs_down,
        market_client=FakeMarketClient(),
        cache=FWACache(clock=clock),
        persist_log_state=False,
    )
    clock.advance(600)
    data = await revived.fetch_and_compute()

    # The aggregates survive, carrying the timestamp they were captured at, and
    # the feed says why rather than pretending to be live.
    assert data["settle_available"] is True
    assert data["settle_as_of_ts"] == pytest.approx(good_ts)
    assert data["crown_paid_eth"] == pytest.approx(91.096)
    assert data["feed_available"] is False
    assert data["feed_unavailable_reason"]
    assert data["feed_as_of_ts"] == pytest.approx(good_ts)
    await _drain(revived)


# ---------------------------------------------------------------------------
# Sweep discipline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invariant_failure_sets_odds_stale_and_withholds_the_ev(tmp_path):
    manager = _manager(tmp_path, state=FakeStateClient(invariants_ok=False))
    data = await manager.fetch_and_compute()

    assert data["invariants_ok"] is False
    assert data["odds_stale"] is True
    # the board still renders (stale, not wrong) ...
    assert data["odds_available"] is True
    assert data["odds_as_of_block"] == BLOCK
    # ... but nothing derived from an incomplete sweep is published
    assert data["ev_available"] is False
    await _drain(manager)


@pytest.mark.asyncio
async def test_single_flight_sweep_skipped_not_queued(tmp_path):
    """A tick landing on an in-flight sweep skips it; it never queues behind it."""
    state = FakeStateClient()
    state.sweep_gate = asyncio.Event()
    manager = _manager(tmp_path, state=state)

    first = asyncio.create_task(manager.fetch_and_compute())
    await asyncio.sleep(0)          # let the first cycle enter the sweep
    while state.sweep_calls == 0:
        await asyncio.sleep(0)

    second = await manager.fetch_and_compute()
    assert state.sweep_calls == 1, "the second tick queued a sweep instead of skipping"
    assert set(second) == set(FWA_DATA_KEYS)

    state.sweep_gate.set()
    await first
    assert state.sweep_calls == 1
    await _drain(manager)


@pytest.mark.asyncio
async def test_sweeps_are_never_rewound_across_blocks(tmp_path):
    """A sweep pinned to an older block is refused; the board never walks back."""
    clock = FakeClock()
    state = FakeStateClient()
    manager = _manager(tmp_path, state=state, clock=clock)
    await manager.fetch_and_compute()
    await _drain(manager)

    async def _older_sweep(**_kwargs):
        state.sweep_calls += 1
        return (BLOCK - 500, list(state.positions), _sweep_report(state.positions))

    state.sweep_positions = _older_sweep
    clock.advance(120)
    data = await manager.fetch_and_compute()
    assert data["odds_as_of_block"] == BLOCK
    await _drain(manager)


# ---------------------------------------------------------------------------
# Tiering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_respected_fast_does_not_trigger_sweep(tmp_path):
    clock = FakeClock()
    state = FakeStateClient()
    market = FakeMarketClient()
    manager = _manager(tmp_path, state=state, market=market, clock=clock)

    await manager.fetch_and_compute()
    await _drain(manager)
    assert state.sweep_calls == 1
    assert state.hot_calls == 1
    assert market.market_calls == 1

    clock.advance(16)               # fast due (15 s), medium (60 s) is not
    assert TIER_FAST in manager.cache.tiers_due(clock.now)
    assert TIER_MEDIUM not in manager.cache.tiers_due(clock.now)

    await manager.fetch_and_compute()
    await _drain(manager)
    assert state.hot_calls == 2, "the fast tier should have refetched"
    assert state.sweep_calls == 1, "the medium tier is still fresh"
    assert market.market_calls == 1, "the slow tier is 15 minutes wide"

    clock.advance(60)               # now medium is due too
    await manager.fetch_and_compute()
    await _drain(manager)
    assert state.sweep_calls == 2


@pytest.mark.asyncio
async def test_once_tier_backfills_once_then_tails(tmp_path):
    clock = FakeClock()
    logs = FakeLogClient()
    manager = _manager(tmp_path, logs=logs, clock=clock)

    await manager.fetch_and_compute()
    await _drain(manager)
    assert (logs.backfills, logs.tails) == (1, 0)

    clock.advance(31)               # tail tier is 30 s
    await manager.fetch_and_compute()
    await _drain(manager)
    assert (logs.backfills, logs.tails) == (1, 1), "the backfill must be one-time"


@pytest.mark.asyncio
async def test_failed_backfill_backs_off_instead_of_hammering(tmp_path):
    """The once tier has no TTL, so a failure needs an explicit retry spacing."""
    clock = FakeClock()
    logs = FakeLogClient(available=False)
    manager = _manager(tmp_path, logs=logs, clock=clock)

    await manager.fetch_and_compute()
    await _drain(manager)
    assert logs.backfills == 1

    clock.advance(16)               # a fast tick, well inside the backoff
    await manager.fetch_and_compute()
    await _drain(manager)
    assert logs.backfills == 1, "a dead log endpoint was retried on the next tick"


@pytest.mark.asyncio
async def test_hot_tier_reads_floors_from_cache_never_from_the_network(tmp_path):
    """``cached_floors()`` is synchronous and free; the sweep is background-only."""
    clock = FakeClock()
    market = FakeMarketClient()
    manager = _manager(tmp_path, market=market, clock=clock)

    await manager.fetch_and_compute()
    await _drain(manager)
    sweeps_after_first = market.floor_sweeps

    for _ in range(4):
        clock.advance(16)
        await manager.fetch_and_compute()
        await _drain(manager)

    assert market.floor_sweeps == sweeps_after_first, (
        "a fast tick must not trigger the paced CoinGecko sweep"
    )


@pytest.mark.asyncio
async def test_market_client_is_constructed_with_the_six_second_coingecko_spacing(
    tmp_path,
):
    """2.5 s drew 26 consecutive 429s out of 36 calls (findings §13.14)."""
    assert COINGECKO_MIN_SPACING == 6.0
    manager = FWAManager(
        cache_path=str(tmp_path / "c.json"),
        log_state_path=str(tmp_path / "l.json"),
        client=FakeStateClient(),
        log_client=FakeLogClient(),
        persist_log_state=False,
    )
    try:
        assert manager.market._cg_spacing == 6.0
    finally:
        await manager.market.close()


# ---------------------------------------------------------------------------
# Units, means and the honest EV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wei_to_eth_happens_exactly_once_at_this_boundary(manager):
    data = await manager.fetch_and_compute()

    # draw_events arrive wei-native and leave as ETH
    row = data["draw_events"][0]
    assert "amount_wei" not in row
    assert row["amount_eth"] == pytest.approx(0.118)

    # crown_history is a presentation payload and is passed through untouched
    assert data["crown_history"][0]["payout_eth"] == pytest.approx(41.5)

    assert data["crown_pot_eth"] == pytest.approx(60_242_085_156_350_313 / 1e18)
    assert data["core_balance_eth"] == pytest.approx(2_551.0)
    await _drain(manager)


@pytest.mark.asyncio
async def test_arithmetic_mean_comes_from_the_sweep_not_from_eth_get_balance(manager):
    """``eth_getBalance`` includes escrow and accrued fees — an upper bound."""
    data = await manager.fetch_and_compute()
    backings = [p.backing_wei for p in _positions()]
    expected = sum(backings) // len(backings) / 1e18

    assert data["arithmetic_mean_eth"] == pytest.approx(expected)
    # and it is emphatically not the core balance divided by the position count
    assert data["arithmetic_mean_eth"] != pytest.approx(2_551.0 / len(backings))
    assert data["core_balance_eth"] == pytest.approx(2_551.0)
    await _drain(manager)


@pytest.mark.asyncio
async def test_hm_am_gap_is_computed_live_never_hardcoded(tmp_path):
    """The gap is a live ratio: 3.885x on one distribution, less on another."""
    state = FakeStateClient()
    manager = _manager(tmp_path, state=state)
    first = await manager.fetch_and_compute()
    await _drain(manager)

    backings = [p.backing_wei for p in _positions()]
    assert first["hm_am_gap_x"] == pytest.approx(fwa_ev.hm_am_gap(backings))
    assert first["hm_am_gap_x"] != pytest.approx(4.0)

    # Flatten the distribution and the gap must move with it.
    flat = [_position(i, COLL_MID, ETH) for i in range(1, 5)]
    manager.cache.set_sweep(BLOCK + 1, flat, invariants_ok=True)
    manager._clock_double.advance(120)
    state.positions = flat
    second = await manager.fetch_and_compute()
    await _drain(manager)
    assert second["hm_am_gap_x"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_ev_band_is_fed_priced_floors_only(manager):
    """A ``0.0`` default would *raise* the pessimistic bound and inflate coverage."""
    data = await manager.fetch_and_compute()

    assert data["ev_available"] is True
    assert data["ev_collections_priced"] == 1     # only COLL_CHEAP has a floor
    assert data["ev_collections_total"] == 3
    assert data["pull_ev_lower_eth"] <= data["pull_ev_best_eth"]
    # The band is genuinely open: coverage is partial, so the bounds differ.
    assert data["pull_ev_best_eth"] > data["pull_ev_lower_eth"]
    assert 0.0 < data["ev_weight_priced_pct"] < 100.0
    await _drain(manager)


@pytest.mark.asyncio
async def test_weighted_backing_total_never_reaches_a_widget(manager):
    data = await manager.fetch_and_compute()
    assert "weighted_backing_total" not in data
    assert not any("tvl" in key for key in data)
    await _drain(manager)


@pytest.mark.asyncio
async def test_a_failed_read_is_none_not_zero(tmp_path):
    """``externalBuysEnabled()`` legitimately reads false; a dead RPC does not."""
    hot = _hot_batch(external_buys_enabled=None, ttt_amount=None)

    class _Client(FakeStateClient):
        async def fetch_hot_batch(self, **_kwargs):
            self.hot_calls += 1
            return hot

    manager = _manager(tmp_path, state=_Client())
    data = await manager.fetch_and_compute()
    gate = data["buy_gate_signal"]
    assert gate is not None
    assert "unavailable" in gate["value_str"].lower()
    assert gate["color"] == "dim"
    await _drain(manager)

    # ... and a genuine false is loud, not silent
    manager2 = _manager(tmp_path, state=FakeStateClient())
    data2 = await manager2.fetch_and_compute()
    assert data2["buy_gate_signal"]["color"] == "red"
    assert "GATED" in data2["buy_gate_signal"]["value_str"]
    await _drain(manager2)


@pytest.mark.asyncio
async def test_odds_rows_withhold_eth_per_odds_point_when_unpriced(manager):
    data = await manager.fetch_and_compute()
    by_address = {row["address"]: row for row in data["collection_odds"]}

    priced = by_address[COLL_CHEAP]
    assert priced["eth_per_odds_point"] == pytest.approx(
        priced["eth_backed"] / priced["weight_share_pct"]
    )
    assert by_address[COLL_MID]["eth_per_odds_point"] is None
    assert by_address[COLL_PUNKS]["floor_source"] == "suppressed"
    assert by_address[COLL_PUNKS]["floor_note"]
    # The inversion is the point: dust owns the draw, the chase item does not.
    assert priced["weight_share_pct"] > by_address[COLL_PUNKS]["weight_share_pct"]
    await _drain(manager)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_persists_cache_and_closes_clients(tmp_path):
    state, logs, market = FakeStateClient(), FakeLogClient(), FakeMarketClient()
    manager = _manager(
        tmp_path, state=state, logs=logs, market=market, persist_log_state=True
    )
    await manager.fetch_and_compute()
    await _drain(manager)
    await manager.close()

    cache_file = tmp_path / "fwa_cache.json"
    log_file = tmp_path / "fwa_log_state.json"
    assert cache_file.exists()
    assert log_file.exists()

    saved = json.loads(cache_file.read_text())
    assert "log_aggregates" in saved["last_good"]
    assert saved["sweep_provenance"]["block"] == BLOCK
    assert json.loads(log_file.read_text())["last_seen_block"] == BLOCK

    assert state.closed and logs.closed and market.closed


@pytest.mark.asyncio
async def test_error_count_increments_and_is_reported(tmp_path):
    manager = _manager(tmp_path, state=FakeStateClient(fail=True))
    first = await manager.fetch_and_compute()
    await _drain(manager)
    manager._clock_double.advance(120)
    second = await manager.fetch_and_compute()
    await _drain(manager)

    assert first["error_count"] > 0
    assert second["error_count"] > first["error_count"]
    assert second["poll_interval"] == 30
