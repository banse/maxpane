"""Tests for OCMCache: burn series, persistence, and corrupt-file handling."""

from __future__ import annotations

import json
import time

from maxpane_dashboard.data.ocm_cache import OCMCache
from maxpane_dashboard.data.ocm_models import (
    OCMCollectionStats,
    OCMSnapshot,
    OCMStakingStats,
)


def _snap(
    *,
    fetched_at: float,
    total_supply: int = 4000,
    burned: int = 12,
    staked: int = 1500,
    ocmd_supply: float = 5_000.0,
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
            ocmd_total_supply=ocmd_supply,
            daily_emission=float(staked),
            staking_ratio=40.0,
            days_to_earn_mint=10.0,
        ),
        holder_count=0,
    )


# ---------------------------------------------------------------------------
# Burn series accumulation
# ---------------------------------------------------------------------------


def test_update_records_burned_count_not_supply():
    now = time.time()
    c = OCMCache()
    c.update(_snap(fetched_at=now, total_supply=4000, burned=12))

    assert c.get_burn_history() == [(now, 12.0)]
    assert c.get_supply_history() == [(now, 4000.0)]


def test_mints_alone_do_not_extend_the_burn_series():
    """120 polls, supply climbing, burn count flat -> one burn keepalive/hour."""
    now = time.time()
    c = OCMCache()
    for i in range(120):
        c.update(
            _snap(
                fetched_at=now + i * 60,
                total_supply=4000 + i,  # a mint every poll
                burned=12,
            )
        )

    burns = c.get_burn_history()
    # Supply history got a point per poll; the burn series is downsampled.
    assert len(c.get_supply_history()) == 120
    assert len(burns) == 2  # t0 and the +1h keepalive (window ends at +119min)
    # Crucially: every value is identical, so any delta is zero.
    assert {v for _, v in burns} == {12.0}


def test_a_changed_burn_count_is_recorded_immediately():
    now = time.time()
    c = OCMCache()
    c.update(_snap(fetched_at=now, burned=12))
    c.update(_snap(fetched_at=now + 60, burned=12))  # unchanged -> skipped
    c.update(_snap(fetched_at=now + 120, burned=13))  # burn -> recorded now

    assert c.get_burn_history() == [(now, 12.0), (now + 120, 13.0)]


def test_burn_series_prunes_beyond_the_window_but_keeps_two_points():
    now = time.time()
    c = OCMCache()
    for days in range(0, 20):
        c.update(_snap(fetched_at=now + days * 86400, burned=10 + days))

    burns = c.get_burn_history()
    assert len(burns) >= 2
    oldest = burns[0][0]
    newest = burns[-1][0]
    assert newest - oldest <= OCMCache.BURN_WINDOW_SECONDS


def test_history_size_and_latest():
    now = time.time()
    c = OCMCache()
    assert c.get_latest() is None
    assert c.last_updated is None
    snap = _snap(fetched_at=now)
    c.update(snap)
    assert c.get_latest() is snap
    assert c.last_updated == now
    assert c.history_size == 1


def test_holder_count_cache():
    c = OCMCache()
    assert c.holder_count == 0
    c.update_holder_count(1234)
    assert c.holder_count == 1234
    assert c.holder_count_updated > 0


def test_dead_burn_plumbing_is_gone():
    """update_burned_count/cumulative_burned were never wired; they are gone."""
    c = OCMCache()
    assert not hasattr(c, "update_burned_count")
    assert not hasattr(c, "cumulative_burned")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path):
    now = time.time()
    path = str(tmp_path / "ocm_cache.json")
    c = OCMCache()
    c.update(_snap(fetched_at=now - 120, burned=12))
    c.update(_snap(fetched_at=now, burned=13))
    c.update_holder_count(77)
    c.save_to_file(path)

    payload = json.loads((tmp_path / "ocm_cache.json").read_text())
    assert payload["version"] == 2
    assert "burn_history" in payload
    assert "cumulative_burned" not in payload

    loaded = OCMCache()
    loaded.load_from_file(path)
    assert loaded.get_burn_history() == c.get_burn_history()
    assert loaded.get_supply_history() == c.get_supply_history()
    assert loaded.holder_count == 77


def test_missing_file_is_a_no_op(tmp_path):
    c = OCMCache()
    c.load_from_file(str(tmp_path / "nope.json"))
    assert c.get_burn_history() == []
    assert c.get_supply_history() == []


def test_corrupt_json_is_a_no_op(tmp_path):
    p = tmp_path / "ocm_cache.json"
    p.write_text("{not json")
    c = OCMCache()
    c.load_from_file(str(p))  # must not raise
    assert c.get_supply_history() == []


def test_non_dict_payload_is_a_no_op(tmp_path):
    p = tmp_path / "ocm_cache.json"
    p.write_text("[1, 2, 3]")
    c = OCMCache()
    c.load_from_file(str(p))
    assert c.get_supply_history() == []


def test_null_point_does_not_crash_startup(tmp_path):
    """MEDI-24: one bad value used to abort MaxPane for every dashboard."""
    now = time.time()
    p = tmp_path / "ocm_cache.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "supply_history": [
                    [now - 60, None],
                    [now - 30, "banana"],
                    [now - 20, float("nan")],
                    [now - 10, 4000],
                    "not a point",
                    [now - 5],
                    [now, True],
                ],
            }
        )
    )
    c = OCMCache()
    c.load_from_file(str(p))  # must not raise
    assert c.get_supply_history() == [(now - 10, 4000.0)]


def test_stale_points_are_dropped(tmp_path):
    now = time.time()
    p = tmp_path / "ocm_cache.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "supply_history": [[now - 5 * 86400, 3000], [now - 60, 4000]],
                "burn_history": [[now - 30 * 86400, 2], [now - 86400, 12]],
            }
        )
    )
    c = OCMCache()
    c.load_from_file(str(p))
    # Sparkline points older than a day cannot inform a ~2h trend.
    assert c.get_supply_history() == [(now - 60, 4000.0)]
    # Burn points older than the 7-day window are dropped too, so a decade-old
    # cache cannot manufacture a burn delta.
    assert c.get_burn_history() == [(now - 86400, 12.0)]


def test_future_dated_points_are_dropped(tmp_path):
    now = time.time()
    p = tmp_path / "ocm_cache.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "burn_history": [[now - 60, 12], [now + 86400, 99]],
            }
        )
    )
    c = OCMCache()
    c.load_from_file(str(p))
    assert c.get_burn_history() == [(now - 60, 12.0)]


def test_v1_cache_does_not_seed_the_burn_series(tmp_path):
    """A pre-fix file holds a supply-derived history and a bogus scalar.

    None of it may reach the burn signal: the burn series must start empty
    and accumulate from the next poll.
    """
    now = time.time()
    p = tmp_path / "ocm_cache.json"
    p.write_text(
        json.dumps(
            {
                "saved_at": now,
                "max_history": 120,
                "supply_history": [[now - 3600, 4000], [now - 60, 4001]],
                "staked_history": [[now - 3600, 1500], [now - 60, 1500]],
                "ocmd_supply_history": [[now - 3600, 5000.0], [now - 60, 5001.0]],
                "cumulative_burned": 0,
                "holder_count": 900,
            }
        )
    )
    c = OCMCache()
    c.load_from_file(str(p))

    assert c.get_burn_history() == []
    # The sparkline series still load -- only the burn series is withheld.
    assert len(c.get_supply_history()) == 2
    assert c.holder_count == 900


def test_v1_file_with_an_injected_burn_history_is_ignored(tmp_path):
    """Version gating, not key presence, decides whether burns are trusted."""
    now = time.time()
    p = tmp_path / "ocm_cache.json"
    p.write_text(
        json.dumps({"burn_history": [[now - 3600, 0], [now - 60, 500]]})
    )
    c = OCMCache()
    c.load_from_file(str(p))
    assert c.get_burn_history() == []


def test_save_failure_is_swallowed(tmp_path):
    c = OCMCache()
    c.update(_snap(fetched_at=time.time()))
    # A directory where the file should be -> os.replace fails.
    target = tmp_path / "dir_in_the_way"
    target.mkdir()
    c.save_to_file(str(target))  # must not raise
