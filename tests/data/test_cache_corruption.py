"""A corrupt persisted point must never abort MaxPane startup (MEDI-14).

Every cache module persists its sparklines as ``[timestamp, value]`` pairs
and reloads them in ``load_from_file``, which every manager calls from its
``__init__``.  Each loader used to do a bare ``float(pt[1])``, so a single
``null`` in one dashboard's cache file raised ``TypeError`` and took down
*every* dashboard -- and the loaders' own docstrings promise the opposite
("silently does nothing if the file is missing or corrupted").

These tests drive the real loaders with a hostile payload: ``null``, a
string, ``NaN``, a wrong-length tuple, a non-sequence entry, a bool, a
negative value and a future-dated timestamp.  The load must survive and
keep exactly the good points.  A happy-path test passes the broken code,
so every case here is deliberately nasty.
"""

from __future__ import annotations

import json
import math
import time

import pytest

from maxpane_dashboard.data.base_cache import BaseTokenCache
from maxpane_dashboard.data.cache import DataCache
from maxpane_dashboard.data.cattown_cache import CatTownCache
from maxpane_dashboard.data.dota_cache import DOTACache
from maxpane_dashboard.data.frenpet_cache import FrenPetCache
from maxpane_dashboard.data.fwa_cache import SERIES_FWA_PRICE_USD, FWACache
from maxpane_dashboard.data.series_points import coerce_point, coerce_points

NOW = time.time()

# One hostile series: every entry but the two flagged below must be dropped.
HOSTILE = [
    [NOW - 60, None],           # the reported crash: TypeError on float(None)
    [NOW - 59, "banana"],       # a string that is not a number
    [NOW - 58, float("nan")],   # NaN would poison every downstream mean
    [NOW - 57, float("inf")],
    "not a point",              # not a sequence at all
    [NOW - 56],                 # wrong length
    [NOW - 55, 1.0, 2.0],       # wrong length the other way
    [NOW - 54, True],           # bool is an int in Python; still corruption
    [None, 5.0],                # corrupt timestamp
    [NOW - 53, -1.0],           # counts and prices are never negative
    [NOW + 86400, 999.0],       # future-dated
    [0, 7.0],                   # non-positive timestamp
    [NOW - 30, 100],            # GOOD
    [NOW - 10, 200.5],          # GOOD
]
GOOD = [(NOW - 30, 100.0), (NOW - 10, 200.5)]

# json.dumps writes NaN/Infinity as bare literals, which json.load accepts.
_dump = json.dumps


def _write(path, payload) -> str:
    path.write_text(_dump(payload))
    return str(path)


# ---------------------------------------------------------------------------
# The shared helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "not a point",
        [],
        [1.0],
        [1.0, 2.0, 3.0],
        [1.0, None],
        [None, 1.0],
        [1.0, "x"],
        [1.0, float("nan")],
        [1.0, float("-inf")],
        [1.0, True],
        [True, 1.0],
        [1.0, -0.5],
        [0.0, 1.0],
        [-5.0, 1.0],
    ],
)
def test_coerce_point_drops_every_flavour_of_corruption(bad):
    assert coerce_point(bad, now=NOW) is None


def test_coerce_point_keeps_and_normalises_a_good_pair():
    assert coerce_point([NOW - 5, 3], now=NOW) == (NOW - 5, 3.0)
    assert coerce_point((NOW - 5, "3.5"), now=NOW) == (NOW - 5, 3.5)


def test_coerce_point_windows_are_opt_in():
    old = [NOW - 10 * 86400, 1.0]
    assert coerce_point(old, now=NOW) is not None            # no window: kept
    assert coerce_point(old, now=NOW, max_age=3600) is None  # windowed: dropped
    assert coerce_point([NOW - 5, -1.0], now=NOW, allow_negative=True) == (
        NOW - 5,
        -1.0,
    )


def test_coerce_points_counts_what_it_dropped():
    good, dropped = coerce_points(HOSTILE, now=NOW)
    assert good == GOOD
    assert dropped == len(HOSTILE) - len(GOOD)
    assert coerce_points("garbage", now=NOW) == ([], 0)
    assert coerce_points(None, now=NOW) == ([], 0)


# ---------------------------------------------------------------------------
# The six loaders, each driven with the hostile payload
# ---------------------------------------------------------------------------


def test_base_cache_survives_corrupt_points(tmp_path, caplog):
    path = _write(
        tmp_path / "base_cache.json",
        {
            "histories": {"0xABC": HOSTILE},
            "overview_volume": HOSTILE,
            "overview_eth_price": HOSTILE,
            "overview_trade_count": HOSTILE,
        },
    )
    cache = BaseTokenCache(max_history=120)
    with caplog.at_level("WARNING"):
        cache.load_from_file(path)  # must not raise

    assert cache.get_price_history("0xabc") == GOOD
    assert cache.get_volume_history() == GOOD
    assert cache.get_eth_price_history() == GOOD
    assert cache.get_trade_count_history() == GOOD
    assert "Skipped" in caplog.text


def test_data_cache_survives_corrupt_points(tmp_path, caplog):
    path = _write(
        tmp_path / "cache.json", {"histories": {"Sourdough Syndicate": HOSTILE}}
    )
    cache = DataCache(max_history=120)
    with caplog.at_level("WARNING"):
        cache.load_from_file(path)  # must not raise

    assert cache.get_cookie_history("Sourdough Syndicate") == GOOD
    assert "Skipped" in caplog.text


def test_cattown_cache_survives_corrupt_points(tmp_path, caplog):
    """The exact reported repro: {"prize_pool_history": [[1.0, null]]}."""
    path = _write(
        tmp_path / "cattown_cache.json",
        {
            "prize_pool_history": HOSTILE,
            "leader_weight_history": [[1.0, None]],
            "raffle_tickets_history": HOSTILE,
        },
    )
    cache = CatTownCache(max_history=120)
    with caplog.at_level("WARNING"):
        cache.load_from_file(path)  # must not raise

    assert cache.get_prize_pool_history() == GOOD
    assert cache.get_leader_weight_history() == []
    assert cache.get_raffle_tickets_history() == GOOD
    assert "Skipped" in caplog.text


def test_dota_cache_survives_corrupt_points(tmp_path, caplog):
    path = _write(
        tmp_path / "dota_cache.json",
        {"top_history": HOSTILE, "mid_history": HOSTILE, "bot_history": HOSTILE},
    )
    cache = DOTACache(max_history=120)
    with caplog.at_level("WARNING"):
        cache.load_from_file(path)  # must not raise

    assert cache.get_top_history() == GOOD
    assert cache.get_mid_history() == GOOD
    assert cache.get_bot_history() == GOOD
    assert "Skipped" in caplog.text


def test_frenpet_cache_survives_corrupt_points(tmp_path, caplog):
    path = _write(tmp_path / "frenpet_cache.json", {"histories": {"7": HOSTILE}})
    cache = FrenPetCache(max_history=120)
    with caplog.at_level("WARNING"):
        cache.load_from_file(path)  # must not raise

    assert cache.get_pet_score_history(7) == GOOD
    assert "Skipped" in caplog.text


def test_fwa_cache_survives_corrupt_points(tmp_path, caplog):
    path = _write(
        tmp_path / "fwa_cache.json",
        {"version": 1, "series": {SERIES_FWA_PRICE_USD: HOSTILE}},
    )
    cache = FWACache(clock=lambda: NOW)
    with caplog.at_level("WARNING"):
        cache.load_from_file(path)  # must not raise

    assert cache.get_series(SERIES_FWA_PRICE_USD) == [list(pt) for pt in GOOD]
    assert "Skipped" in caplog.text


# ---------------------------------------------------------------------------
# The startup story the finding is really about
# ---------------------------------------------------------------------------


def test_one_bad_file_no_longer_aborts_every_dashboard(tmp_path):
    """Managers load their caches in __init__; a raise there kills the app."""
    bad = _write(tmp_path / "any_cache.json", {"prize_pool_history": [[1.0, None]]})
    for cache, loader in (
        (CatTownCache(), "load_from_file"),
        (DOTACache(), "load_from_file"),
        (DataCache(), "load_from_file"),
        (BaseTokenCache(), "load_from_file"),
        (FrenPetCache(), "load_from_file"),
    ):
        getattr(cache, loader)(bad)  # none of these may raise


def test_nan_really_does_reach_the_loader(tmp_path):
    """Guard the guard: json.load must actually hand a NaN to the loader."""
    raw = json.dumps({"top_history": [[NOW - 5, float("nan")]]})
    assert "NaN" in raw
    assert math.isnan(json.loads(raw)["top_history"][0][1])
