"""Launchpad ranking and thresholds.  Pure: no I/O, injected clock."""

import pytest

from maxpane_dashboard.analytics import surf_launchpad as L


def _swaps(**by_coin):
    return dict(by_coin)


def test_hot_threshold_is_three_times_the_median() -> None:
    counts = _swaps(a=1, b=2, c=3, d=4, e=100)
    assert L.hot_coin_threshold(counts) == 9   # median 3 -> 9


def test_hot_threshold_has_a_floor_of_five() -> None:
    """A quiet day with median 1 must not promote a coin on 3 swaps."""
    counts = _swaps(a=1, b=1, c=1, d=1, e=1)
    assert L.hot_coin_threshold(counts) == 5


def test_no_threshold_below_five_active_coins() -> None:
    """Fewer than 5 coins traded means no meaningful median: OK, not a fire."""
    assert L.hot_coin_threshold(_swaps(a=50, b=1)) is None
    assert L.hot_coin_threshold({}) is None


def test_hot_coin_can_fire_on_a_days_distribution_and_stays_dark_on_an_hours() -> None:
    """Measured live 2026-08-23: an hour held 1 active coin against
    ``HOT_MIN_ACTIVE=5``, so at that window the detector was permanently
    dark and had never fired. The same day held 10 active coins.
    """
    hour_like = _swaps(**{"0x1": 1})
    day_like = {f"0x{i}": n for i, n in enumerate([18, 14, 6, 2, 1, 1, 1, 1, 1, 1])}
    assert L.hot_coin_threshold(hour_like) is None
    assert L.hot_coin_threshold(day_like) == 5      # max(HOT_FLOOR, median 1 * 3)


def test_the_hot_coin_staleness_bound_is_the_window_it_measures() -> None:
    """Already in the suite -- it must now pin 24h, not an hour."""
    from maxpane_dashboard.data import surf_client as sc

    assert L.HOT_MAX_AGE_S == sc.LAUNCHPAD_DAY_BLOCKS * sc._LAUNCHPAD_BLOCK_SECONDS


def test_ranking_is_by_day_swaps_desc_and_bounded() -> None:
    launches = [
        {"pool_id": "0xa", "ticker": "A", "name": "Alpha", "creator": "0x1", "ts": 100.0},
        {"pool_id": "0xb", "ticker": "B", "name": "Beta", "creator": "0x2", "ts": 200.0},
        {"pool_id": "0xc", "ticker": "C", "name": "Gamma", "creator": "0x3", "ts": 300.0},
    ]
    day_swaps = [{"pool_id": "0xb"}] * 9 + [{"pool_id": "0xa"}] * 4 + [{"pool_id": "0xc"}]
    rows = L.rank_coins(launches, day_swaps, swaps_all={}, now_ts=1000.0, limit=2)
    assert [r["ticker"] for r in rows] == ["B", "A"]
    assert rows[0]["swaps_24h"] == 9
    assert rows[0]["age_s"] == 800.0
    assert rows[0]["pool_id"] == "0xb"


def test_two_coins_sharing_a_ticker_keep_their_own_swap_counts() -> None:
    """`launch(string,string)` is permissionless: a ticker is not an identity.

    Counting by ticker handed the impostor and the real coin one merged total
    -- 10 swaps each here -- which each row then rendered as its own and
    ranked on. Attribution is by `pool_id` (final fix wave, I1).
    """
    launches = [
        {"pool_id": "0xreal", "ticker": "ICE", "name": "Icecream", "creator": "0x1",
         "ts": 100.0},
        {"pool_id": "0xfake", "ticker": "ICE", "name": "Icecream", "creator": "0x2",
         "ts": 200.0},
    ]
    day_swaps = [{"pool_id": "0xreal"}] * 9 + [{"pool_id": "0xfake"}]
    rows = L.rank_coins(launches, day_swaps, swaps_all={}, now_ts=1000.0, limit=5)
    by_pool = {row["pool_id"]: row["swaps_24h"] for row in rows}
    assert by_pool == {"0xreal": 9, "0xfake": 1}


def test_a_coin_with_no_swaps_has_none_change_not_zero() -> None:
    """`0%` asserts we measured a flat day; `None` is 'nothing traded'."""
    launches = [{"pool_id": "0xq", "ticker": "Q", "name": "Quiet", "creator": "0x9",
                 "ts": 10.0}]
    rows = L.rank_coins(launches, [], swaps_all={}, now_ts=100.0, limit=5)
    assert rows[0]["swaps_24h"] == 0
    assert rows[0]["change_24h_pct"] is None


def test_a_never_traded_coin_reports_zero_swaps_not_none() -> None:
    """`0` here is a real answer: the coin exists and has never traded."""
    rows = L.rank_coins(
        [{"pool_id": "0xa", "ticker": "A", "name": "A", "creator": "0x1", "ts": 0}],
        day_swaps=[], swaps_all={}, now_ts=1000, limit=10,
    )
    assert rows[0]["swaps_24h"] == 0 and rows[0]["swaps_all"] == 0


def test_a_day_swap_outranks_a_bigger_all_time_count() -> None:
    launches = [
        {"pool_id": "0xa", "ticker": "A", "name": "A", "creator": "0x1", "ts": 0},
        {"pool_id": "0xb", "ticker": "B", "name": "B", "creator": "0x2", "ts": 0},
    ]
    rows = L.rank_coins(
        launches,
        day_swaps=[{"pool_id": "0xb", "trader": "0x9", "is_buy": True}],
        swaps_all={"0xa": 999, "0xb": 1},
        now_ts=1000, limit=10,
    )
    assert [r["ticker"] for r in rows] == ["B", "A"]


def test_ranking_falls_back_to_all_time_not_to_age_when_the_day_is_quiet() -> None:
    """The bug this replaces: 1 swap in an hour across 146 coins sorted every
    coin to 0, the sort fell through to -age_s, and the panel showed the 20
    OLDEST never-traded coins at an identical initial curve price. Widening
    the window to 24h does not fix this by itself -- a quiet day can still
    tie every coin at 0 -- so the tiebreak has to be ``swaps_all``, not age.
    """
    launches = [
        {"pool_id": "0xquiet_old", "ticker": "OLD", "name": "Old", "creator": "0x1", "ts": 0},
        {"pool_id": "0xbusy_new", "ticker": "BUSY", "name": "Busy", "creator": "0x2", "ts": 900},
    ]
    rows = L.rank_coins(
        launches, day_swaps=[], swaps_all={"0xbusy_new": 677},
        now_ts=1000, limit=10,
    )
    assert [r["ticker"] for r in rows] == ["BUSY", "OLD"]


def test_ranking_never_reads_the_clock_itself() -> None:
    """now_ts is injected; a module that calls time.time() cannot be tested."""
    import inspect
    assert "time.time()" not in inspect.getsource(L)
