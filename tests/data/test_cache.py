"""Tests for DataCache: TTL, time-series accumulation, persistence."""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from maxpane_dashboard.data.cache import DataCache
from maxpane_dashboard.data.snapshot import GameSnapshot
from maxpane_dashboard.data.models import (
    AgentConfig,
    BakerySummary,
    Contracts,
    GameplayCaps,
    LiveState,
    Network,
    ReferralWeights,
    Season,
)


# ---------------------------------------------------------------------------
# Fixtures -- minimal valid models for snapshot construction
# ---------------------------------------------------------------------------

def _make_season(**overrides: object) -> Season:
    defaults = dict(
        id=3,
        start_time="1774535903",
        end_time="1775746803",
        claim_deadline=None,
        protocol_fee_bps=0,
        seed_amount="1000000",
        results_root=None,
        finalized=False,
        ended=False,
        is_active=True,
        prize_pool="2000000",
    )
    defaults.update(overrides)
    return Season(**defaults)  # type: ignore[arg-type]


def _make_bakery(name: str, tx_count: str, **overrides: object) -> BakerySummary:
    defaults = dict(
        id=1,
        name=name,
        creator="0xaaa",
        leader="0xaaa",
        top_cook=None,
        member_count=10,
        active_cook_count=2,
        season_id=3,
        created_at="1774542117",
        tx_count=tx_count,
        raw_tx_count=tx_count,
        buffs=0,
        debuffs=0,
        active_buffs=(),
        active_debuffs=(),
    )
    defaults.update(overrides)
    return BakerySummary(**defaults)  # type: ignore[arg-type]


def _make_agent_config() -> AgentConfig:
    return AgentConfig(
        name="Bakery",
        version="1.0",
        generated_at="2026-03-27T04:26:31.659Z",
        network=Network(
            name="Abstract",
            chain_id=2741,
            rpc_http="https://api.mainnet.abs.xyz",
            explorer="https://abscan.org",
            currency="ETH",
            wallet_model="Abstract Global Wallet",
        ),
        contracts=Contracts(
            season_manager="0x1",
            prize_pool="0x2",
            player_registry="0x3",
            clan_registry="0x4",
            boost_manager="0x5",
            bakery="0x6",
        ),
        live_state=LiveState(
            current_season_id=3,
            is_season_active=True,
            buy_in_wei="2000000000000000",
            buy_in_eth="0.002",
            vrf_fee_wei="22006155000000",
            vrf_fee_eth="0.000022006155",
            minimum_required_wei_excluding_gas="2022006155000000",
            minimum_required_eth_excluding_gas="0.002022006155",
            referral_weights=ReferralWeights(
                referred_weight_bps=10500,
                not_referred_weight_bps=10000,
                referral_bonus_bps=500,
            ),
            gameplay_caps=GameplayCaps(
                cookie_scale=10000,
                max_active_boosts=5,
                max_active_debuffs=5,
                leave_penalty_bps=10000,
            ),
            active_boost_catalog=(),
        ),
        live_data_status="fresh",
    )


def _make_snapshot(
    bakeries: list[BakerySummary] | None = None,
    fetched_at: float | None = None,
) -> GameSnapshot:
    return GameSnapshot(
        season=_make_season(),
        bakeries=bakeries or [
            _make_bakery("Alpha Bakery", "1000000"),
            _make_bakery("Beta Bakery", "500000", id=2),
        ],
        activity=[],
        agent_config=_make_agent_config(),
        eth_price_usd=2500.0,
        fetched_at=fetched_at or time.time(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDataCacheUpdate:
    def test_update_stores_latest(self) -> None:
        cache = DataCache(max_history=10)
        snap = _make_snapshot()
        cache.update(snap)
        assert cache.get_latest() is snap

    def test_update_records_time_series(self) -> None:
        cache = DataCache(max_history=10)
        snap = _make_snapshot(fetched_at=100.0)
        cache.update(snap)

        history = cache.get_cookie_history("Alpha Bakery")
        assert len(history) == 1
        # Raw tx_count "1000000" / cookie_scale 10000 = 100.0 display cookies
        assert history[0] == (100.0, 100.0)

    def test_multiple_updates_accumulate(self) -> None:
        cache = DataCache(max_history=10)

        for i in range(5):
            snap = _make_snapshot(
                bakeries=[_make_bakery("Alpha Bakery", str(1000 * (i + 1)))],
                fetched_at=float(100 + i * 30),
            )
            cache.update(snap)

        history = cache.get_cookie_history("Alpha Bakery")
        assert len(history) == 5
        # Verify ordering is chronological
        assert history[0][0] < history[-1][0]
        # Verify values are correct (raw / 10000 cookie_scale)
        assert history[0][1] == 0.1   # 1000 / 10000
        assert history[-1][1] == 0.5  # 5000 / 10000

    def test_last_updated_tracks_latest(self) -> None:
        cache = DataCache()
        assert cache.last_updated is None

        snap = _make_snapshot(fetched_at=42.0)
        cache.update(snap)
        assert cache.last_updated == 42.0


class TestDataCacheHistoryLimits:
    def test_max_history_enforced(self) -> None:
        cache = DataCache(max_history=3)

        for i in range(10):
            snap = _make_snapshot(
                bakeries=[_make_bakery("Test", str(i))],
                fetched_at=float(i),
            )
            cache.update(snap)

        history = cache.get_cookie_history("Test")
        assert len(history) == 3
        # Should keep the last 3 entries (raw / 10000 cookie_scale)
        assert history[0][1] == 0.0007  # 7 / 10000
        assert history[1][1] == 0.0008  # 8 / 10000
        assert history[2][1] == 0.0009  # 9 / 10000

    def test_unknown_bakery_returns_empty(self) -> None:
        cache = DataCache()
        assert cache.get_cookie_history("Nonexistent") == []

    def test_get_all_histories(self) -> None:
        cache = DataCache(max_history=10)
        snap = _make_snapshot()
        cache.update(snap)

        all_h = cache.get_all_histories()
        assert "Alpha Bakery" in all_h
        assert "Beta Bakery" in all_h
        assert len(all_h) == 2


class TestDataCachePersistence:
    def test_save_and_load_roundtrip(self) -> None:
        cache = DataCache(max_history=10)

        for i in range(5):
            snap = _make_snapshot(
                bakeries=[
                    _make_bakery("Alpha", str(100 * (i + 1))),
                    _make_bakery("Beta", str(50 * (i + 1)), id=2),
                ],
                fetched_at=float(1000 + i),
            )
            cache.update(snap)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            cache.save_to_file(path)

            # Verify file exists and is valid JSON
            with open(path) as f:
                saved = json.load(f)
            assert "histories" in saved
            assert "Alpha" in saved["histories"]
            assert len(saved["histories"]["Alpha"]) == 5

            # Load into a fresh cache
            cache2 = DataCache(max_history=10)
            cache2.load_from_file(path)

            alpha = cache2.get_cookie_history("Alpha")
            assert len(alpha) == 5
            # Raw 100 / 10000 = 0.01, raw 500 / 10000 = 0.05
            assert alpha[0] == (1000.0, 0.01)
            assert alpha[-1] == (1004.0, 0.05)

            beta = cache2.get_cookie_history("Beta")
            assert len(beta) == 5
        finally:
            os.unlink(path)

    def test_load_missing_file_is_silent(self) -> None:
        cache = DataCache()
        cache.load_from_file("/nonexistent/path/cache.json")
        assert cache.get_latest() is None

    def test_load_corrupted_file_is_silent(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {{{")
            path = f.name

        try:
            cache = DataCache()
            cache.load_from_file(path)
            assert cache.history_size == 0
        finally:
            os.unlink(path)

    def test_save_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "cache.json")
            cache = DataCache(max_history=5)
            snap = _make_snapshot(fetched_at=1.0)
            cache.update(snap)
            cache.save_to_file(path)
            assert os.path.exists(path)
