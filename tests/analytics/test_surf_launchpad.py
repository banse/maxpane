"""Launchpad ranking and thresholds.  Pure: no I/O, injected clock."""

import pytest

from maxpane_dashboard.analytics import surf_launchpad as L


def _swaps(**by_coin):
    return dict(by_coin)


def test_hot_threshold_is_three_times_the_median() -> None:
    counts = _swaps(a=1, b=2, c=3, d=4, e=100)
    assert L.hot_coin_threshold(counts) == 9   # median 3 -> 9


def test_hot_threshold_has_a_floor_of_five() -> None:
    """A quiet hour with median 1 must not promote a coin on 3 swaps."""
    counts = _swaps(a=1, b=1, c=1, d=1, e=1)
    assert L.hot_coin_threshold(counts) == 5


def test_no_threshold_below_five_active_coins() -> None:
    """Fewer than 5 coins traded means no meaningful median: OK, not a fire."""
    assert L.hot_coin_threshold(_swaps(a=50, b=1)) is None
    assert L.hot_coin_threshold({}) is None


def test_ranking_is_by_recent_swaps_desc_and_bounded() -> None:
    launches = [
        {"ticker": "A", "name": "Alpha", "creator": "0x1", "ts": 100.0},
        {"ticker": "B", "name": "Beta", "creator": "0x2", "ts": 200.0},
        {"ticker": "C", "name": "Gamma", "creator": "0x3", "ts": 300.0},
    ]
    swaps = [{"coin": "B"}] * 9 + [{"coin": "A"}] * 4 + [{"coin": "C"}]
    rows = L.rank_coins(launches, swaps, now_ts=1000.0, limit=2)
    assert [r["ticker"] for r in rows] == ["B", "A"]
    assert rows[0]["swaps_1h"] == 9
    assert rows[0]["age_s"] == 800.0


def test_a_coin_with_no_swaps_has_none_change_not_zero() -> None:
    """`0%` asserts we measured a flat hour; `None` is 'nothing traded'."""
    launches = [{"ticker": "Q", "name": "Quiet", "creator": "0x9", "ts": 10.0}]
    rows = L.rank_coins(launches, [], now_ts=100.0, limit=5)
    assert rows[0]["swaps_1h"] == 0
    assert rows[0]["change_1h_pct"] is None


def test_ranking_never_reads_the_clock_itself() -> None:
    """now_ts is injected; a module that calls time.time() cannot be tested."""
    import inspect
    assert "time.time()" not in inspect.getsource(L)
