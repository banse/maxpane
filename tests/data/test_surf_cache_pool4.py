"""WP7 — the pool4 tier, slot and the two network-namespaced reserve series.

Companion to ``tests/data/test_surf_cache.py``, which owns everything the
cache did before the surf ``p`` body existed. Nothing here sleeps, nothing
here reads a real clock and nothing here touches a socket: ``SurfCache`` does
no I/O but its own JSON file, and that file lives under ``tmp_path``.

The centre of gravity is the **splice**. ``pool4`` reads the vendored Sepolia
deployment until a mainnet hook is discovered and adopted, so a single reserve
series would join a testnet history to a mainnet one at the switchover and
draw one sparkline across two chains — a line whose halves are different
tokens on different networks, with nothing on screen saying so. Two series,
chosen by the network the reading came from, is the fix; these tests are what
stop it being quietly undone.
"""

from __future__ import annotations

import json

import pytest

from maxpane_dashboard.data.surf_cache import (
    POOL4_RESERVE_SERIES,
    SERIES_ALLOW_NEGATIVE,
    SERIES_IMD_SUPPLY,
    SERIES_NAMES,
    SERIES_POOL4_RESERVE_MAINNET,
    SERIES_POOL4_RESERVE_SEPOLIA,
    SLOT_POOL4,
    SLOTS,
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_POOL4,
    TIER_TTL_SECONDS,
    TIERS,
    SurfCache,
    pool4_reserve_series_name,
)
from maxpane_dashboard.data.surf_models import POOL4_NETWORKS

SEPOLIA, MAINNET = POOL4_NETWORKS

HOUR = 3600.0
T0 = 1_786_190_400.0          # a real hour boundary, like the WP4 suite's


def _cache(tmp_path, now: float = T0) -> SurfCache:
    return SurfCache(path=str(tmp_path / "surf_cache.json"), clock=lambda: now)


# ---------------------------------------------------------------------------
# The tier and the slot
# ---------------------------------------------------------------------------


def test_pool4_has_its_own_tier_with_a_shorter_failure_backoff() -> None:
    """A long TTL with a much shorter backoff — ``TIER_LAUNCHPAD``'s shape.

    The two numbers are asserted as a *relation*, not as literals: what makes
    this tier correct is that a rate-limited endpoint is retried well before
    the full TTL, and that the panels behind it run on a slower clock than the
    title bar's. Pinning 600/180 exactly would turn a deliberate re-tune into
    a red test with nothing to say about it.
    """
    assert TIER_POOL4 in TIERS
    assert TIER_TTL_SECONDS[TIER_POOL4] >= 300.0
    assert 0.0 < TIER_FAILURE_BACKOFF_SECONDS[TIER_POOL4] < TIER_TTL_SECONDS[TIER_POOL4]


def test_every_tier_has_both_a_ttl_and_a_backoff() -> None:
    assert set(TIER_TTL_SECONDS) == set(TIERS)
    assert set(TIER_FAILURE_BACKOFF_SECONDS) == set(TIERS)


def test_pool4_has_its_own_last_good_slot(tmp_path) -> None:
    c = _cache(tmp_path)
    assert SLOT_POOL4 in SLOTS
    c.store_last_good(SLOT_POOL4, {"network": SEPOLIA}, ts=T0)
    assert c.get_last_good(SLOT_POOL4).payload == {"network": SEPOLIA}
    assert c.as_of_ts(SLOT_POOL4) == T0


def test_a_failed_pool4_tier_keeps_the_slot_and_only_spaces_the_retry(tmp_path) -> None:
    """The last-good rule, at the cache boundary: a failure is a backoff, not
    an erasure. The payload *and its timestamp* survive, so the marker above
    it goes stale rather than being reprinted fresh over dashes.
    """
    c = _cache(tmp_path)
    c.store_last_good(SLOT_POOL4, {"network": SEPOLIA}, ts=T0)
    c.mark_failed(TIER_POOL4, now=T0 + 10.0)
    assert c.get_last_good(SLOT_POOL4).ts == T0
    assert TIER_POOL4 not in c.tiers_due(T0 + 10.0)
    assert TIER_POOL4 in c.tiers_due(
        T0 + 10.0 + TIER_FAILURE_BACKOFF_SECONDS[TIER_POOL4] + 1.0
    )


# ---------------------------------------------------------------------------
# The two series, and the vocabulary agreement
# ---------------------------------------------------------------------------


def test_the_reserve_series_map_agrees_with_the_contracts_networks() -> None:
    """``POOL4_RESERVE_SERIES``' keys are ``POOL4_NETWORKS``, restated.

    Amendment A24's shape: the cache restates the two words (it imports
    nothing from the project but the ``series_points`` leaf) and the *test*
    imports the contract's tuple. Deriving the map's keys from
    ``POOL4_NETWORKS`` would make this compare a constant against itself.

    It bites in both directions — a network added to the contract and not to
    the map means readings on that chain land nowhere, and a word invented in
    the map with no contract behind it means a series nothing can publish.
    """
    assert set(POOL4_RESERVE_SERIES) == set(POOL4_NETWORKS)
    assert len(POOL4_RESERVE_SERIES) == len(POOL4_NETWORKS)


def test_the_two_series_are_distinct_registered_and_non_negative() -> None:
    assert SERIES_POOL4_RESERVE_SEPOLIA != SERIES_POOL4_RESERVE_MAINNET
    for name in (SERIES_POOL4_RESERVE_SEPOLIA, SERIES_POOL4_RESERVE_MAINNET):
        assert name in SERIES_NAMES
        # A pool's token balance cannot be negative; a negative one is
        # corruption, not a spread. (``pool4_floor_distance`` legitimately
        # goes below zero, and is a per-cycle derived value, never stored.)
        assert SERIES_ALLOW_NEGATIVE[name] is False


@pytest.mark.parametrize("network", [None, "", "BASE", "sepolia ", 3, ["SEPOLIA"]])
def test_an_unrecognised_network_names_no_series(network) -> None:
    """A word outside the closed vocabulary is a producer bug, not a chain.

    ``"sepolia "`` is in the list on purpose: a trailing space is exactly the
    kind of near-miss a loose lookup would launder into the wrong history.
    """
    assert pool4_reserve_series_name(network) is None


def test_each_network_names_its_own_series() -> None:
    assert pool4_reserve_series_name(SEPOLIA) == SERIES_POOL4_RESERVE_SEPOLIA
    assert pool4_reserve_series_name(MAINNET) == SERIES_POOL4_RESERVE_MAINNET


# ---------------------------------------------------------------------------
# Sampling — and the sentinel rule
# ---------------------------------------------------------------------------


def test_a_reading_lands_only_in_its_own_networks_series(tmp_path) -> None:
    c = _cache(tmp_path)
    c.sample_pool4_reserve(T0, 152_030_338.54, network=SEPOLIA)
    assert c.get_pool4_reserve_series(SEPOLIA) == [[T0, 152_030_338.54]]
    assert c.get_pool4_reserve_series(MAINNET) == []


def test_a_failed_read_never_reaches_either_series(tmp_path) -> None:
    """``None`` is not zero and must not be written anywhere.

    A sentinel in a history outlives the outage that produced it: the
    sparkline draws a cliff to zero that never happened, and it is persisted,
    so it survives the restart too.
    """
    c = _cache(tmp_path)
    c.sample_pool4_reserve(T0, 100.0, network=SEPOLIA)
    c.sample_pool4_reserve(T0 + HOUR, None, network=SEPOLIA)
    c.sample_pool4_reserve(T0 + 2 * HOUR, None, network=MAINNET)
    assert c.get_pool4_reserve_series(SEPOLIA) == [[T0, 100.0]]
    assert c.get_pool4_reserve_series(MAINNET) == []


def test_a_reading_with_no_known_network_is_dropped_not_guessed(tmp_path) -> None:
    """No "whichever series we used last" fallback — that *is* the splice."""
    c = _cache(tmp_path)
    c.sample_pool4_reserve(T0, 100.0, network=SEPOLIA)
    c.sample_pool4_reserve(T0 + HOUR, 200.0, network="BASE")
    c.sample_pool4_reserve(T0 + HOUR, 300.0, network=None)
    assert c.get_pool4_reserve_series(SEPOLIA) == [[T0, 100.0]]
    assert c.get_pool4_reserve_series(MAINNET) == []


def test_a_negative_reserve_is_refused(tmp_path) -> None:
    c = _cache(tmp_path)
    c.sample_pool4_reserve(T0, -1.0, network=SEPOLIA)
    assert c.get_pool4_reserve_series(SEPOLIA) == []


def test_the_two_series_never_interleave_across_a_network_switch(tmp_path) -> None:
    """**The splice test.** A simulated Sepolia -> mainnet adoption.

    Sepolia readings at Sepolia scale, then adoption, then mainnet readings at
    a completely different scale. Neither series may contain a point from the
    other's chain, and the mainnet series must not open with the testnet's
    history behind it — which is what one shared series would render as a
    single continuous line.
    """
    c = _cache(tmp_path)
    for i in range(4):
        c.sample_pool4_reserve(T0 + i * HOUR, 150_000_000.0 + i, network=SEPOLIA)
    # ... the mainnet hook is adopted here ...
    for i in range(3):
        c.sample_pool4_reserve(T0 + (10 + i) * HOUR, 42.0 + i, network=MAINNET)

    sepolia = c.get_pool4_reserve_series(SEPOLIA)
    mainnet = c.get_pool4_reserve_series(MAINNET)
    assert [v for _ts, v in sepolia] == [150_000_000.0 + i for i in range(4)]
    assert [v for _ts, v in mainnet] == [42.0, 43.0, 44.0]
    assert not set(ts for ts, _v in sepolia) & set(ts for ts, _v in mainnet)
    # And the published series is the one matching the active network only.
    assert c.get_pool4_reserve_series(MAINNET) != c.get_pool4_reserve_series(SEPOLIA)


def test_no_network_publishes_none_rather_than_an_empty_history(tmp_path) -> None:
    """``None`` and ``[]`` are different claims and RATCHET renders them so."""
    c = _cache(tmp_path)
    assert c.get_pool4_reserve_series(None) is None
    assert c.get_pool4_reserve_series("BASE") is None
    assert c.get_pool4_reserve_series(SEPOLIA) == []


# ---------------------------------------------------------------------------
# Folding the log-derived history
# ---------------------------------------------------------------------------


def test_log_derived_points_back_fill_the_right_series(tmp_path) -> None:
    c = _cache(tmp_path)
    folded = c.fold_pool4_reserve_history(
        [[T0, 10.0], [T0 + HOUR, 11.0], [T0 + 2 * HOUR, 12.0]], network=SEPOLIA
    )
    assert folded == 3
    assert c.get_pool4_reserve_series(SEPOLIA) == [
        [T0, 10.0], [T0 + HOUR, 11.0], [T0 + 2 * HOUR, 12.0]
    ]
    assert c.get_pool4_reserve_series(MAINNET) == []


def test_folding_a_failed_read_folds_nothing(tmp_path) -> None:
    c = _cache(tmp_path)
    assert c.fold_pool4_reserve_history(None, network=SEPOLIA) == 0
    assert c.fold_pool4_reserve_history([], network=SEPOLIA) == 0
    assert c.fold_pool4_reserve_history([[T0, 1.0]], network="BASE") == 0
    assert c.get_pool4_reserve_series(SEPOLIA) == []


def test_folding_survives_malformed_points_one_at_a_time(tmp_path) -> None:
    """A single unusable point costs that point, never the whole fold.

    This is ``coerce_points``' rule one layer out: the log decoder is total,
    but a hand-edited or replayed payload is third-party input all the same.
    """
    c = _cache(tmp_path)
    folded = c.fold_pool4_reserve_history(
        [[T0, 10.0], "nonsense", [None, 3.0], [T0 + HOUR], [T0 + HOUR, 11.0],
         [float("inf"), 1.0], [-5.0, 1.0]],
        network=SEPOLIA,
    )
    assert folded == 2
    assert c.get_pool4_reserve_series(SEPOLIA) == [[T0, 10.0], [T0 + HOUR, 11.0]]


def test_a_fold_then_a_sample_in_the_same_hour_keeps_the_sample(tmp_path) -> None:
    """The current reading wins its own bucket, and the series stays ordered.

    The order the manager uses is back-fill first, live reading second, so
    the live one is the last writer for the hour it lands in — the reading
    nearest to "now" is the one the sparkline's right-hand end shows.
    """
    c = _cache(tmp_path)
    c.fold_pool4_reserve_history(
        [[T0 + 2 * HOUR, 10.0], [T0, 8.0], [T0 + HOUR, 9.0]], network=SEPOLIA
    )
    c.sample_pool4_reserve(T0 + 2 * HOUR + 60.0, 99.0, network=SEPOLIA)
    series = c.get_pool4_reserve_series(SEPOLIA)
    assert series == [[T0, 8.0], [T0 + HOUR, 9.0], [T0 + 2 * HOUR, 99.0]]
    assert [ts for ts, _v in series] == sorted(ts for ts, _v in series)
    assert len({ts for ts, _v in series}) == len(series)


# ---------------------------------------------------------------------------
# The counter accumulator (S17)
# ---------------------------------------------------------------------------

_ACC = {"genesis_block": 100, "cursor_block": 500, "sums": {"fee_imd": 7}}


def test_an_accumulator_lands_only_in_its_own_network(tmp_path) -> None:
    """A total accumulated on Sepolia, reconciled against mainnet counters, is
    not a weaker check -- it is a wrong one. The reserve series' argument,
    applied to evidence instead of history."""
    c = _cache(tmp_path)
    c.set_pool4_accumulator(SEPOLIA, _ACC)
    assert c.get_pool4_accumulator(SEPOLIA) == _ACC
    assert c.get_pool4_accumulator(MAINNET) is None
    assert c.get_pool4_accumulator("BASE") is None


def test_an_unrecognised_network_stores_no_accumulator(tmp_path) -> None:
    c = _cache(tmp_path)
    c.set_pool4_accumulator("BASE", _ACC)
    c.set_pool4_accumulator(None, _ACC)
    assert c.get_pool4_accumulator(SEPOLIA) is None
    assert c.get_pool4_accumulator(MAINNET) is None


def test_a_stored_accumulator_is_a_copy_not_a_live_reference(tmp_path) -> None:
    """A caller mutating its own dict afterwards must not rewrite history."""
    c = _cache(tmp_path)
    mine = dict(_ACC)
    c.set_pool4_accumulator(SEPOLIA, mine)
    mine["cursor_block"] = 999_999
    assert c.get_pool4_accumulator(SEPOLIA)["cursor_block"] == 500


def test_the_accumulator_round_trips_and_stays_namespaced(tmp_path) -> None:
    """A running total that did not survive a restart would mean the counter
    control only ever worked on the day of deployment."""
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=lambda: T0)
    c.set_pool4_accumulator(SEPOLIA, _ACC)
    c.set_pool4_accumulator(MAINNET, dict(_ACC, cursor_block=900))
    c.save()

    restored = SurfCache(path=path, clock=lambda: T0)
    restored.load()
    assert restored.get_pool4_accumulator(SEPOLIA) == _ACC
    assert restored.get_pool4_accumulator(MAINNET)["cursor_block"] == 900


@pytest.mark.parametrize(
    "bad",
    [
        {"genesis_block": None, "cursor_block": 5, "sums": {}},
        {"genesis_block": 1, "cursor_block": None, "sums": {}},
        {"genesis_block": 1, "cursor_block": "5", "sums": {}},
        {"genesis_block": True, "cursor_block": 5, "sums": {}},
        {"genesis_block": -1, "cursor_block": 5, "sums": {}},
        {"genesis_block": 9, "cursor_block": 5, "sums": {}},
        {"genesis_block": 1, "cursor_block": 5, "sums": {"fee_imd": -3}},
        {"genesis_block": 1, "cursor_block": 5, "sums": {"fee_imd": "3"}},
        {"genesis_block": 1, "cursor_block": 5, "sums": {"fee_imd": 1.5}},
        {"genesis_block": 1, "cursor_block": 5, "sums": {"fee_imd": True}},
        {"genesis_block": 1, "cursor_block": 5, "sums": "nope"},
        {"genesis_block": 1, "cursor_block": 5},
        "not a mapping",
        None,
    ],
)
def test_the_accumulator_block_is_validated_per_field(bad) -> None:
    """It is **cache-supplied evidence**, and the validation is why that is
    tolerable rather than alarming.

    What actually bounds a forgery is not this method: it is the *alignment*
    invariant. A forged total is believed only while its ``cursor_block``
    equals the block the counters were just read at -- a live chain read
    nobody can predict -- so it must be rewritten in lockstep with the chain
    to keep working, and it perishes on its own. What this does is refuse
    anything structurally wrong, so a malformed file costs the accumulator
    rather than the startup (``coerce_points``' precedent).
    """
    assert SurfCache._coerce_accumulator(bad) is None


def test_a_bad_accumulator_on_disk_costs_only_itself(tmp_path) -> None:
    path = str(tmp_path / "surf_cache.json")
    payload = {
        "version": 1, "saved_at": T0, "last_good": {},
        "series": {SERIES_POOL4_RESERVE_SEPOLIA: [[T0, 1.0]]},
        "baselines": {}, "burned_cum": 0.0,
        "last_supply": None, "last_supply_block": None,
        "pool4_accumulators": {
            SERIES_POOL4_RESERVE_SEPOLIA: {"genesis_block": "x"},
            SERIES_POOL4_RESERVE_MAINNET: _ACC,
            "not_a_series": _ACC,
        },
    }
    with open(path, "w") as handle:
        json.dump(payload, handle)

    c = SurfCache(path=path, clock=lambda: T0)
    c.load()
    assert c.get_pool4_accumulator(SEPOLIA) is None      # the bad one, dropped
    assert c.get_pool4_accumulator(MAINNET) == _ACC      # the good one, kept
    assert c.get_pool4_reserve_series(SEPOLIA) == [[T0, 1.0]]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_both_series_round_trip_separately_through_the_cache_file(tmp_path) -> None:
    """A restart must not merge them either — the splice has a second door."""
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=lambda: T0 + 10 * HOUR)
    c.sample_pool4_reserve(T0, 150_000_000.0, network=SEPOLIA)
    c.sample_pool4_reserve(T0 + HOUR, 42.0, network=MAINNET)
    c.store_last_good(SLOT_POOL4, {"network": SEPOLIA}, ts=T0)
    c.save()

    on_disk = json.loads(open(path).read())
    assert set(on_disk["series"]) <= set(SERIES_NAMES)
    assert SLOT_POOL4 in on_disk["last_good"]

    restored = SurfCache(path=path, clock=lambda: T0 + 10 * HOUR)
    restored.load()
    assert restored.get_pool4_reserve_series(SEPOLIA) == [[T0, 150_000_000.0]]
    assert restored.get_pool4_reserve_series(MAINNET) == [[T0 + HOUR, 42.0]]
    assert restored.get_last_good(SLOT_POOL4).ts == T0


def test_a_single_bad_persisted_point_costs_that_point_only(tmp_path) -> None:
    """``coerce_points``' per-point validation covers the new series too.

    A ``null`` in a cache file used to abort startup for every dashboard;
    adding a series that bypassed that validation would reopen it.
    """
    path = str(tmp_path / "surf_cache.json")
    payload = {
        "version": 1,
        "saved_at": T0,
        "last_good": {},
        "series": {
            SERIES_POOL4_RESERVE_SEPOLIA: [[T0, 1.0], None, [T0 + HOUR, "x"],
                                           [T0 + 2 * HOUR, 3.0]],
            SERIES_IMD_SUPPLY: [[T0, 5.0]],
        },
        "baselines": {},
        "burned_cum": 0.0,
        "last_supply": None,
        "last_supply_block": None,
    }
    with open(path, "w") as handle:
        json.dump(payload, handle)

    c = SurfCache(path=path, clock=lambda: T0 + 10 * HOUR)
    c.load()
    assert c.get_pool4_reserve_series(SEPOLIA) == [[T0, 1.0], [T0 + 2 * HOUR, 3.0]]
    assert c.get_series(SERIES_IMD_SUPPLY) == [[T0, 5.0]]
