"""Manager-layer tests for the bakery ``DataManager``.

Covers three review findings that all land in this one class:

* **MEDI-13** -- ``manager.py`` had no manager-layer test at all.  Its
  ``fetch_and_compute`` dict is the contract every bakery widget reads via
  ``data[...]``/``data.get(...)``; a key rename blanked widgets behind a
  warning log and nothing failed.
* **MEDI-8** -- Late-Join EV multiplied a top-three probability by the
  *whole* prize pool and never used ``member_count``, and the manager
  computed it with no season gating.  A finalized season still reports a
  pool, so the SignalsPanel could advertise "consider joining" for a
  season nobody can join.
* **MEDI-22** -- the persisted history was restored in full regardless of
  age, so ``calculate_production_rate`` regressed over a stale cluster for
  the first hour after every restart.

Model builders are reused from ``test_manager_ev_catalog`` (verbatim live
``agent.json`` shapes) rather than re-derived here.  Zero network.
"""

from __future__ import annotations

import json
import time

import pytest

from maxpane_dashboard.data import manager as manager_module
from maxpane_dashboard.data.manager import DataManager
from maxpane_dashboard.data.snapshot import GameSnapshot
from tests.data.test_manager_ev_catalog import (
    _agent_config,
    _bakery,
    _live_items,
    _season,
    _StubClient,
)

_COOKIE_SCALE = 10_000


def _snapshot(
    *,
    fetched_at: float,
    leader_cookies: float = 10_000.0,
    member_count: int = 10,
    is_active: bool = True,
    prize_pool_wei: str = "2000000000000000000",
    end_offset: float = 86_400.0,
) -> GameSnapshot:
    season = _season().model_copy(
        update={
            "is_active": is_active,
            "ended": not is_active,
            "finalized": not is_active,
            "prize_pool": prize_pool_wei,
            "end_time": str(int(time.time() + end_offset)),
        }
    )
    bakeries = [
        _bakery("Alpha Bakery", leader_cookies, bakery_id=1).model_copy(
            update={"member_count": member_count}
        ),
        _bakery("Beta Bakery", leader_cookies / 2, bakery_id=2),
    ]
    return GameSnapshot(
        season=season,
        bakeries=bakeries,
        activity=[],
        agent_config=_agent_config(_live_items()),
        eth_price_usd=2500.0,
        fetched_at=fetched_at,
    )


@pytest.fixture
def make_manager(monkeypatch, tmp_path):
    cache_file = tmp_path / "history.json"

    def _factory(snapshots: list[GameSnapshot], poll_interval: int = 30):
        stub = _StubClient(snapshots)
        monkeypatch.setattr(manager_module, "GameDataClient", lambda: stub)
        monkeypatch.setattr(manager_module, "_CACHE_FILE", cache_file)
        return DataManager(poll_interval=poll_interval)

    _factory.cache_file = cache_file  # type: ignore[attr-defined]
    return _factory


# ---------------------------------------------------------------------------
# MEDI-13: the widget-facing dict contract
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "prize_pool_eth", "prize_pool_usd", "hours_remaining", "season_id",
    "season_active", "leader_name", "leader_cookies", "leader_rate",
    "bakeries", "production_rates", "chart_histories", "events",
    "late_join_ev", "gap_analysis", "gap_to_third", "dominance",
    "recommendation", "boost_rankings", "attack_rankings",
    "ev_catalog_source", "last_updated_seconds_ago", "error_count",
    "poll_interval",
}


@pytest.mark.asyncio
async def test_all_contract_keys_present(make_manager) -> None:
    manager = make_manager([_snapshot(fetched_at=time.time())])
    data = await manager.fetch_and_compute()
    missing = REQUIRED_KEYS - set(data.keys())
    assert not missing, f"missing keys: {missing}"


@pytest.mark.asyncio
async def test_values_are_computed_not_just_present(make_manager) -> None:
    now = time.time()
    manager = make_manager([
        _snapshot(fetched_at=now - 3600.0, leader_cookies=10_000.0),
        _snapshot(fetched_at=now, leader_cookies=11_000.0),
    ])
    await manager.fetch_and_compute()
    data = await manager.fetch_and_compute()

    assert data["leader_name"] == "Alpha Bakery"
    assert data["leader_cookies"] == pytest.approx(11_000.0)
    assert data["leader_rate"] == pytest.approx(1000.0, rel=1e-6)
    assert data["prize_pool_eth"] == pytest.approx(2.0)
    assert data["prize_pool_usd"] == pytest.approx(5000.0)
    assert data["dominance"] == pytest.approx(2.0)
    assert data["season_active"] is True
    assert data["poll_interval"] == 30
    assert isinstance(data["recommendation"], str) and data["recommendation"]


@pytest.mark.asyncio
async def test_fetch_failure_raises_and_counts(make_manager) -> None:
    manager = make_manager([_snapshot(fetched_at=time.time())])

    async def _boom() -> GameSnapshot:
        raise RuntimeError("tRPC 502")

    manager.client.fetch_all = _boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await manager.fetch_and_compute()
    assert manager._error_count == 1


# ---------------------------------------------------------------------------
# MEDI-8: Late-Join EV
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ended_season_never_advertises_positive_ev(make_manager) -> None:
    """A finalized season still reports a pool -- the reviewer saw
    ``ev_usd=9749.3`` and "consider joining" for season 10, already over."""
    manager = make_manager([
        _snapshot(
            fetched_at=time.time(),
            is_active=False,
            end_offset=-86_400.0,
            prize_pool_wei="100000000000000000000",  # 100 ETH still in the pool
        )
    ])
    data = await manager.fetch_and_compute()

    assert data["season_active"] is False
    assert data["late_join_ev"]["ev_usd"] <= 0
    assert "Season over" in data["late_join_ev"]["recommendation"]


@pytest.mark.asyncio
async def test_ev_shrinks_with_the_leader_member_count(make_manager) -> None:
    """``member_count`` was accepted and ignored; the bakery's share of the
    70/20/10 split is divided among its members."""
    now = time.time()
    small = make_manager([_snapshot(fetched_at=now, member_count=2)])
    data_small = await small.fetch_and_compute()

    big = make_manager([_snapshot(fetched_at=now, member_count=60)])
    data_big = await big.fetch_and_compute()

    assert data_big["late_join_ev"]["ev_usd"] < data_small["late_join_ev"]["ev_usd"]


@pytest.mark.asyncio
async def test_ev_is_not_the_whole_prize_pool(make_manager) -> None:
    manager = make_manager([_snapshot(fetched_at=time.time(), member_count=30)])
    data = await manager.fetch_and_compute()

    prize_pool_usd = data["prize_pool_usd"]
    # Two bakeries => top3_probability is 1.0; the old formula returned
    # the entire pool minus the buy-in.
    assert data["late_join_ev"]["ev_usd"] < prize_pool_usd / 50


# ---------------------------------------------------------------------------
# MEDI-22: stale persisted history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_day_old_cache_is_not_restored(make_manager) -> None:
    """120 samples at a 30s poll is a 60-minute window; nothing older than
    that window can inform the current production rate."""
    cache_file = make_manager.cache_file
    now = time.time()
    cache_file.write_text(json.dumps({
        "saved_at": now - 86_400,
        "max_history": 120,
        "histories": {
            "Alpha Bakery": [[now - 86_400 + i, 500_000.0 + i] for i in range(20)],
        },
    }))

    manager = make_manager([_snapshot(fetched_at=now, leader_cookies=10_000.0)])
    assert manager.cache.get_cookie_history("Alpha Bakery") == []

    data = await manager.fetch_and_compute()
    # One fresh sample is not enough for a rate -- which is the honest
    # answer.  Before the fix the rate came from last night's cluster.
    assert data["leader_rate"] == 0.0
    assert data["leader_cookies"] == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_recent_cache_is_still_restored(make_manager) -> None:
    """The age filter must not break persistence for a normal restart."""
    cache_file = make_manager.cache_file
    now = time.time()
    cache_file.write_text(json.dumps({
        "saved_at": now - 60,
        "max_history": 120,
        "histories": {
            "Alpha Bakery": [[now - 1800.0, 9_500.0], [now - 900.0, 9_750.0]],
        },
    }))

    manager = make_manager([_snapshot(fetched_at=now, leader_cookies=10_000.0)])
    assert len(manager.cache.get_cookie_history("Alpha Bakery")) == 2

    data = await manager.fetch_and_compute()
    assert data["leader_rate"] == pytest.approx(1000.0, rel=0.05)
