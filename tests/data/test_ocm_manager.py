"""Tests for OCMManager wiring -- notably which series feeds the burn signal.

Zero network: the manager is constructed with a stub client and a tmp_path
cache file, so nothing touches ~/.maxpane or an RPC endpoint.
"""

from __future__ import annotations

import json

import pytest

from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.data.ocm_models import (
    OCMActivityEvent,
    OCMCollectionStats,
    OCMSnapshot,
    OCMStakingStats,
)

_T0 = 1_700_000_000.0


def _snap(
    *,
    fetched_at: float,
    total_supply: int = 4000,
    burned: int = 12,
    staked: int = 1600,
    read_failures: int = 0,
    events: list[OCMActivityEvent] | None = None,
) -> OCMSnapshot:
    return OCMSnapshot(
        fetched_at=fetched_at,
        collection=OCMCollectionStats(
            total_supply=total_supply,
            max_supply=10_000,
            current_minting_cost=10 * 10**18,
            burned_count=burned,
            net_supply=total_supply - burned,
            remaining=10_000 - total_supply,
            minted_pct=total_supply / 100,
        ),
        staking=OCMStakingStats(
            total_staked=staked,
            ocmd_total_supply=5000.0,
            daily_emission=float(staked),
            staking_ratio=(staked / max(1, total_supply - burned)) * 100,
            days_to_earn_mint=10.0,
        ),
        holder_count=0,
        faucet_open=True,
        recent_events=events or [],
        read_failures=read_failures,
    )


class _StubClient:
    """Serves a scripted list of snapshots."""

    def __init__(self, snapshots: list[OCMSnapshot]):
        self._snapshots = list(snapshots)
        self.closed = False

    async def fetch_snapshot(self) -> OCMSnapshot:
        if not self._snapshots:
            raise AssertionError("stub client exhausted")
        return self._snapshots.pop(0)

    async def close(self) -> None:
        self.closed = True


def _manager(snapshots: list[OCMSnapshot], tmp_path) -> OCMManager:
    return OCMManager(
        poll_interval=60,
        client=_StubClient(snapshots),
        cache_file=tmp_path / "ocm_cache.json",
    )


# ---------------------------------------------------------------------------
# HIGH-3: mints must never register as burn pressure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mint_only_window_reports_no_burn_pressure(tmp_path):
    """120 polls over ~2h in which 5 tokens are minted and nothing is burned.

    Before the fix this rendered "~84/week" with a red "high" indicator
    because the burn rate was computed from the totalSupply series.
    """
    snaps = [
        _snap(
            fetched_at=_T0 + i * 60,
            total_supply=4000 + (i // 24),  # a mint every ~24 min
            burned=12,  # nobody burns anything
        )
        for i in range(120)
    ]
    mgr = _manager(snaps, tmp_path)

    data: dict = {}
    for _ in range(120):
        data = await mgr.fetch_and_compute()

    assert data["burn_rate_signal"]["value_str"] == "~0/week"
    assert data["burn_rate_signal"]["color"] == "dim"
    # The mints are still counted where they belong.
    assert data["mint_velocity_signal"]["value_str"] != "~0/day"
    assert "contracting" not in data["recommendation"]
    await mgr.close()


@pytest.mark.asyncio
async def test_real_burns_are_counted(tmp_path):
    """7 tokens burned over a week -> ~7/week, red."""
    snaps = [
        _snap(fetched_at=_T0, total_supply=4000, burned=10),
        _snap(fetched_at=_T0 + 3 * 86400, total_supply=4050, burned=13),
        _snap(fetched_at=_T0 + 7 * 86400, total_supply=4100, burned=17),
    ]
    mgr = _manager(snaps, tmp_path)

    data: dict = {}
    for _ in range(3):
        data = await mgr.fetch_and_compute()

    assert data["burn_rate_signal"]["value_str"] == "~7/week"
    assert data["burn_rate_signal"]["color"] == "red"
    assert mgr.cache.get_burn_history() == [
        (_T0, 10.0),
        (_T0 + 3 * 86400, 13.0),
        (_T0 + 7 * 86400, 17.0),
    ]
    await mgr.close()


@pytest.mark.asyncio
async def test_burn_series_is_the_burned_count_not_the_supply(tmp_path):
    snaps = [
        _snap(fetched_at=_T0, total_supply=4000, burned=12),
        _snap(fetched_at=_T0 + 7200, total_supply=4500, burned=12),
    ]
    mgr = _manager(snaps, tmp_path)
    await mgr.fetch_and_compute()
    await mgr.fetch_and_compute()

    assert [v for _, v in mgr.cache.get_burn_history()] == [12.0, 12.0]
    assert [v for _, v in mgr.cache.get_supply_history()] == [4000.0, 4500.0]
    await mgr.close()


@pytest.mark.asyncio
async def test_single_poll_reports_no_burn_rate(tmp_path):
    mgr = _manager([_snap(fetched_at=_T0)], tmp_path)
    data = await mgr.fetch_and_compute()
    assert data["burn_rate_signal"]["value_str"] == "~0/week"
    await mgr.close()


# ---------------------------------------------------------------------------
# General wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_and_compute_shape(tmp_path):
    events = [
        OCMActivityEvent(
            tx_hash="0xa",
            block_number=100,
            timestamp=int(_T0),
            event_type="mint",
            actor_address="0x" + "11" * 20,
            token_id=4001,
            count=1,
        ),
        OCMActivityEvent(
            tx_hash="0xb",
            block_number=101,
            timestamp=int(_T0),
            event_type="burn",
            actor_address="0x" + "11" * 20,
            token_id=4002,
            count=1,
        ),
    ]
    mgr = _manager([_snap(fetched_at=_T0, events=events)], tmp_path)

    data = await mgr.fetch_and_compute()

    assert data["total_supply"] == 4000
    assert data["burned_count"] == 12
    assert data["net_supply"] == 3988
    assert data["recent_mints"] == 1
    assert data["recent_burns"] == 1
    assert len(data["recent_events"]) == 2
    assert data["error_count"] == 0
    assert data["poll_interval"] == 60
    assert data["time_to_next_tier"]
    await mgr.close()


@pytest.mark.asyncio
async def test_client_error_is_counted_and_reraised(tmp_path):
    class _Boom:
        async def fetch_snapshot(self):
            raise RuntimeError("rpc down")

        async def close(self):
            return None

    mgr = OCMManager(client=_Boom(), cache_file=tmp_path / "c.json")
    with pytest.raises(RuntimeError):
        await mgr.fetch_and_compute()
    assert mgr._error_count == 1
    await mgr.close()


# ---------------------------------------------------------------------------
# MEDI-25: failed reads must not be persisted as data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_reads_do_not_poison_history(tmp_path):
    """An all-zero snapshot from a dead RPC used to be appended as real data.

    The next good poll then saw 0 -> 4000 and reported an absurd mint
    velocity (and, before the burn fix, a red burn rate), persisted to disk.
    """
    snaps = [
        _snap(fetched_at=_T0, total_supply=4000, burned=12),
        _snap(fetched_at=_T0 + 60, total_supply=0, burned=0, read_failures=4),
        _snap(fetched_at=_T0 + 120, total_supply=4001, burned=12),
    ]
    mgr = _manager(snaps, tmp_path)

    await mgr.fetch_and_compute()
    degraded = await mgr.fetch_and_compute()
    good = await mgr.fetch_and_compute()

    # The outage is surfaced, not silently rendered as zeros.
    assert degraded["error_count"] == 1
    assert degraded["total_supply"] == 4000  # last good values, not 0
    assert degraded["burned_count"] == 12

    # No zero point ever entered a series.
    assert [v for _, v in mgr.cache.get_supply_history()] == [4000.0, 4001.0]
    assert [v for _, v in mgr.cache.get_burn_history()] == [12.0]
    # One mint over 2 minutes is 720/day; a 0 -> 4001 jump would be ~2.9M/day.
    assert good["mint_velocity_signal"]["value_str"] == "~720/day"
    await mgr.close()


@pytest.mark.asyncio
async def test_degraded_snapshot_with_no_history_still_returns_a_dict(tmp_path):
    """First-ever poll during an outage: degrade, do not crash or persist."""
    mgr = _manager([_snap(fetched_at=_T0, total_supply=0, burned=0,
                          read_failures=4)], tmp_path)

    data = await mgr.fetch_and_compute()

    assert data["error_count"] == 1
    assert data["total_supply"] == 0
    assert mgr.cache.get_supply_history() == []
    assert mgr.cache.get_burn_history() == []
    await mgr.close()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_persists_cache_to_the_given_path(tmp_path):
    path = tmp_path / "ocm_cache.json"
    mgr = _manager([_snap(fetched_at=_T0)], tmp_path)
    await mgr.fetch_and_compute()
    await mgr.close()

    payload = json.loads(path.read_text())
    assert payload["version"] == 2
    assert payload["burn_history"] == [[_T0, 12.0]]
    assert mgr.client.closed is True


@pytest.mark.asyncio
async def test_stale_v1_cache_cannot_feed_the_burn_signal(tmp_path):
    """A pre-fix cache file on disk must not produce a burn reading."""
    path = tmp_path / "ocm_cache.json"
    path.write_text(
        json.dumps(
            {
                "saved_at": _T0,
                "supply_history": [[_T0 - 3600, 3990], [_T0 - 60, 4000]],
                "cumulative_burned": 999,
                "holder_count": 800,
            }
        )
    )
    mgr = OCMManager(client=_StubClient([_snap(fetched_at=_T0)]), cache_file=path)

    assert mgr.cache.get_burn_history() == []
    data = await mgr.fetch_and_compute()
    assert data["burn_rate_signal"]["value_str"] == "~0/week"
    await mgr.close()
