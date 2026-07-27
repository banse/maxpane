"""Tests for :mod:`maxpane_dashboard.analytics.fwa_ev`.

Every expected value here comes from a measurement, not from re-running the
implementation:

* ``tests/fixtures/fwa/backing_distribution.json`` — WP-3's complete,
  invariant-verified sweep of all 3,867 live positions at pinned block
  25612701.  Its ``statistics`` block is marked AUTHORITATIVE and is what the
  mean/gap tests assert against.
* ``tests/fixtures/fwa/pinned_aggregates.json`` — raw ``eth_call`` returns and
  decoded aggregates at blocks 25612655 and 25612701.
* ``docs/fwa_technical_findings.md`` §4.1, §6, §13.7 ·
  ``docs/fwa_game_mechanics.md`` §5-§14 · ``docs/fwa_PRD.md`` §3, §4, §7

The prose figures 0.1247 ETH / 0.5002 ETH / 4.0x were measured off an unpinned,
drifting scan and have been superseded (findings §13.7).  The fixture keeps
them under ``documented_statistics_from_prose`` for provenance only; nothing
here asserts against that block.  The harmonic/arithmetic gap is a **live
ratio**, not a constant — it is asserted only against the distribution it was
measured on.

No ``pytest.approx`` is used on any wei integer — wei assertions are ``==``.
"""

from __future__ import annotations

import inspect
import json
import math
from functools import lru_cache
from pathlib import Path
from statistics import median

import pytest

from maxpane_dashboard.analytics import fwa_ev

# ---------------------------------------------------------------------------
# Fixtures (WP-3 — authoritative, read-only here)
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "fwa"
BACKING_DISTRIBUTION = FIXTURE_DIR / "backing_distribution.json"
PINNED_AGGREGATES = FIXTURE_DIR / "pinned_aggregates.json"


@lru_cache(maxsize=None)
def _distribution() -> dict:
    return json.loads(BACKING_DISTRIBUTION.read_text())


@lru_cache(maxsize=None)
def _backings() -> tuple[int, ...]:
    """The 3,867 live backings at block 25612701 (fixture stores them as strings)."""
    return tuple(int(v) for v in _distribution()["backing_values_wei"])


def _statistics() -> dict:
    return _distribution()["statistics"]


def _by_collection() -> dict:
    return _distribution()["by_collection"]


@lru_cache(maxsize=None)
def _pinned() -> dict:
    return json.loads(PINNED_AGGREGATES.read_text())


def _block(number: int) -> dict:
    return _pinned()["blocks"][str(number)]["expected_decoded"]


# ---------------------------------------------------------------------------
# Documented / measured constants
# ---------------------------------------------------------------------------

# Pinned block 25612655
WEIGHTED_TOTAL_25612655 = 3890999999999999999275601332649457427323
TOTAL_WEIGHT_25612655 = 31280618816683353089152
EV_25612655 = 124390122292745553
FEE_25612655 = 136829134522020108

# Pinned block 25612701 — the full-sweep proof-of-completeness block
WEIGHTED_TOTAL_25612701 = 3866999999999999999373145521289217360095
TOTAL_WEIGHT_25612701 = 31217322873711845581134
EV_25612701 = 123873530592093356
FEE_25612701 = 136260883651302691
ACTIVE_LISTINGS_25612701 = 3867

# Measured distribution statistics at 25612701 (fixture `statistics`)
MEASURED_HARMONIC_MEAN_WEI = 123873530592093356  # 0.123874 ETH
MEASURED_ARITHMETIC_MEAN_WEI = 481327464769128452  # 0.481327 ETH
MEASURED_TOTAL_BACKING_WEI = 1861293306262219725629  # 1,861.29 ETH
MEASURED_GAP = 3.8856361199076925

# listings(56508) — the largest live position, findings §4.1
MAX_BACKING_WEI = 221 * 10**18
MAX_BACKING_WEIGHT = 4524886877828054

# Collection addresses, lowercased, as keyed in `by_collection`
TTT_ADDRESS = "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"
ART_BLOCKS_ADDRESS = "0x942bc2d3e7a589fe5bd4a5c6ef9727dfd82f5c8a"
PUNKS721_ADDRESS = "0x000000000000003607fce1ac9e043a86675c5c2f"

ETH = 10**18


# ---------------------------------------------------------------------------
# Fixture integrity — independent recomputation of every published statistic
# ---------------------------------------------------------------------------


def test_fixture_statistics_recompute_from_the_raw_backing_values():
    """Cross-check WP-3's authoritative block against the array it came from.

    Nothing downstream is trustworthy if these disagree, so every field is
    recomputed independently rather than taken on faith.
    """
    backings = list(_backings())
    stats = _statistics()

    assert len(backings) == stats["count"] == ACTIVE_LISTINGS_25612701
    assert min(backings) == stats["min_wei"]
    assert max(backings) == stats["max_wei"] == MAX_BACKING_WEI
    assert int(median(backings)) == stats["median_wei"]
    assert sum(backings) == stats["total_wei"] == MEASURED_TOTAL_BACKING_WEI
    assert len(set(backings)) == stats["distinct_backing_values"]
    assert len(_by_collection()) == stats["collections_with_live_positions"] == 38

    assert fwa_ev.arithmetic_mean_wei(backings) == stats["arithmetic_mean_wei"]
    assert fwa_ev.harmonic_mean_wei(backings) == stats["harmonic_mean_wei"]
    assert fwa_ev.hm_am_gap(backings) == pytest.approx(
        stats["arithmetic_over_harmonic_gap"], rel=1e-12
    )


def test_fixture_reproduces_the_three_onchain_invariants():
    """findings §6.1 step 5 — the completeness proof, recomputed here."""
    backings = list(_backings())
    decoded = _block(25612701)

    total_weight = fwa_ev.total_weight(backings)
    weighted_total = fwa_ev.weighted_backing_total(backings)

    assert total_weight == decoded["totalWeight"]
    assert weighted_total == decoded["weightedBackingTotal"]
    assert fwa_ev.acquisition_fee_wei(weighted_total, total_weight) == decoded["acquisitionFee"]
    assert len(backings) == decoded["activeListingCount"] == decoded["feeShareTotal"]


def test_measured_statistics_supersede_the_prose_figures():
    """findings §13.7 — the 0.1247 / 0.5002 / 4.0x triple came from a bad scan.

    The fixture retains the prose numbers for provenance under
    ``documented_statistics_from_prose``.  This asserts only that the measured
    values are what we track, and that they are genuinely different.
    """
    stats = _statistics()
    prose = _distribution().get("documented_statistics_from_prose", {})

    assert stats["harmonic_mean_wei"] == MEASURED_HARMONIC_MEAN_WEI
    assert stats["arithmetic_mean_wei"] == MEASURED_ARITHMETIC_MEAN_WEI
    assert stats["harmonic_mean_eth"] != prose.get("harmonic_mean_eth")
    assert stats["arithmetic_mean_eth"] != prose.get("arithmetic_mean_eth")


# ---------------------------------------------------------------------------
# 1-3 — weights (PRD rule 1, rule 4)
# ---------------------------------------------------------------------------


def test_inverse_weight_exact():
    """findings §4.1: 10**36 // (221e18) == 4524886877828054, zero error."""
    assert fwa_ev.inverse_weight(MAX_BACKING_WEI) == MAX_BACKING_WEIGHT
    assert fwa_ev.INVERSE_WEIGHT_NUMERATOR == 10**36
    # minBacking 0.01 ETH -> max weight per position 1e20 (mechanics §5)
    assert fwa_ev.inverse_weight(10**16) == 10**20
    # never rounds to zero for any realistic backing
    assert fwa_ev.inverse_weight(10_000 * ETH) > 0


def test_inverse_weight_rejects_non_positive():
    with pytest.raises(ValueError):
        fwa_ev.inverse_weight(0)
    with pytest.raises(ValueError):
        fwa_ev.inverse_weight(-1)


def test_total_weight_matches_onchain():
    """Sum(1e36 // backing) over the pinned sweep == totalWeight()."""
    assert fwa_ev.total_weight(_backings()) == TOTAL_WEIGHT_25612701


def test_weighted_backing_total_matches_onchain():
    """Sum(weight * backing) == weightedBackingTotal()."""
    assert fwa_ev.weighted_backing_total(_backings()) == WEIGHTED_TOTAL_25612701


def test_total_weight_is_sum_of_inverse_weights():
    backings = [ETH, 2 * ETH, 4 * ETH]
    assert fwa_ev.total_weight(backings) == 10**18 + 5 * 10**17 + 25 * 10**16
    assert fwa_ev.total_weight([]) == 0


def test_weighted_backing_total_is_approximately_count_times_1e36():
    """findings §6.4 (TRAP 3): the quantity is ~ count * 1e36 and is not ETH."""
    wbt = fwa_ev.weighted_backing_total(_backings())
    count = len(_backings())
    assert wbt <= count * 10**36
    assert wbt > count * 10**36 * 0.999
    # ...and it is 1e18 times larger than the ETH actually held, which is the trap
    assert wbt > MEASURED_TOTAL_BACKING_WEI * 10**18


def test_weighted_backing_total_docstring_warns_it_is_not_tvl():
    """PRD rule 4 — the docstring must say it is neither wei nor ETH, nor TVL."""
    doc = (fwa_ev.weighted_backing_total.__doc__ or "").lower()
    assert "not" in doc
    assert "wei" in doc
    assert "eth" in doc
    assert "tvl" in doc


# ---------------------------------------------------------------------------
# 4-5 — the two floor divisions (PRD rule 2)
# ---------------------------------------------------------------------------


def test_acquisition_fee_bit_exact_25612655():
    """mechanics §6 / findings §4.1 — reproduced with zero wei error."""
    decoded = _block(25612655)
    assert decoded["weightedBackingTotal"] == WEIGHTED_TOTAL_25612655
    assert decoded["totalWeight"] == TOTAL_WEIGHT_25612655

    ev = fwa_ev.expected_value_wei(WEIGHTED_TOTAL_25612655, TOTAL_WEIGHT_25612655)
    assert ev == EV_25612655

    fee = fwa_ev.acquisition_fee_wei(WEIGHTED_TOTAL_25612655, TOTAL_WEIGHT_25612655)
    assert fee == FEE_25612655
    assert fee == decoded["acquisitionFee"]


def test_acquisition_fee_bit_exact_25612701():
    """findings §6.1 — the full-sweep proof block."""
    decoded = _block(25612701)
    fee = fwa_ev.acquisition_fee_wei(WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)
    assert fee == FEE_25612701
    assert fee == decoded["acquisitionFee"]


def test_acquisition_fee_zero_total_weight():
    """Solidity: ``if (totalWeight == 0) return 0;`` — must not raise."""
    assert fwa_ev.acquisition_fee_wei(0, 0) == 0
    assert fwa_ev.acquisition_fee_wei(10**40, 0) == 0
    assert fwa_ev.expected_value_wei(10**40, 0) == 0


def test_two_floor_divisions_not_one():
    """Collapsing the two divisions into one changes the answer.

    At block 25612701 the difference is real and one wei wide: the contract's
    two-step ``(W / T) * 11000 / 10000`` yields ...691, while the algebraically
    equivalent single-step ``W * 11000 / (T * 10000)`` yields ...692.  The
    onchain value is ...691, so the two-step form is the only correct one.
    """
    two_step = fwa_ev.acquisition_fee_wei(WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)
    one_step = WEIGHTED_TOTAL_25612701 * 11000 // (TOTAL_WEIGHT_25612701 * 10000)

    assert one_step == 136260883651302692
    assert two_step == FEE_25612701 == _block(25612701)["acquisitionFee"]
    assert two_step != one_step
    assert one_step - two_step == 1

    # ...and at 25612655 the two forms happen to agree, which is exactly why a
    # single sample is not enough to catch the collapse.
    assert fwa_ev.acquisition_fee_wei(
        WEIGHTED_TOTAL_25612655, TOTAL_WEIGHT_25612655
    ) == WEIGHTED_TOTAL_25612655 * 11000 // (TOTAL_WEIGHT_25612655 * 10000)


def test_pinned_aggregates_fixture_agrees():
    """Every block in the fixture must reproduce its own recorded fee."""
    blocks = _pinned()["blocks"]
    assert set(blocks) == {"25612655", "25612701"}

    for number, entry in blocks.items():
        decoded = entry["expected_decoded"]
        assert entry["block_number"] == int(number)
        fee = fwa_ev.acquisition_fee_wei(decoded["weightedBackingTotal"], decoded["totalWeight"])
        assert fee == decoded["acquisitionFee"], number
        # feeShareTotal == activeListingCount is a free onchain invariant (rule 5)
        assert decoded["feeShareTotal"] == decoded["activeListingCount"], number


def test_surcharge_bps_is_configurable():
    """surchargeBps is a live parameter (rule 6), 1000 bps is only the default."""
    w, t = WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701
    ev = fwa_ev.expected_value_wei(w, t)
    assert fwa_ev.acquisition_fee_wei(w, t, surcharge_bps=0) == ev
    assert fwa_ev.acquisition_fee_wei(w, t, surcharge_bps=2000) == ev * 12000 // 10000


# ---------------------------------------------------------------------------
# 6 — means and the gap (mechanics §5, §6, §14.2; findings §13.7)
# ---------------------------------------------------------------------------


def test_harmonic_mean():
    """The harmonic mean is what the price tracks (mechanics §6).

    Measured across all 3,867 live positions at block 25612701:
    123873530592093356 wei (0.123874 ETH), identical to the wei to
    ``weightedBackingTotal // totalWeight``.
    """
    # 3 / (1/1 + 1/2 + 1/4) = 12/7 ETH
    assert fwa_ev.harmonic_mean_wei([ETH, 2 * ETH, 4 * ETH]) == 12 * 10**18 // 7

    measured = fwa_ev.harmonic_mean_wei(_backings())
    assert measured == MEASURED_HARMONIC_MEAN_WEI
    assert measured == _statistics()["harmonic_mean_wei"]

    # the derivation the fixture claims: count * 1e36 // totalWeight
    assert measured == ACTIVE_LISTINGS_25612701 * 10**36 // TOTAL_WEIGHT_25612701
    # ...and the pool price is exactly this, to the wei
    assert measured == fwa_ev.expected_value_wei(WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)

    assert fwa_ev.harmonic_mean_wei([]) == 0


def test_arithmetic_mean():
    """Sum(backing) // n across the pinned sweep: 481327464769128452 wei."""
    assert fwa_ev.arithmetic_mean_wei([ETH, 2 * ETH, 4 * ETH]) == 7 * 10**18 // 3

    measured = fwa_ev.arithmetic_mean_wei(_backings())
    assert measured == MEASURED_ARITHMETIC_MEAN_WEI
    assert measured == _statistics()["arithmetic_mean_wei"]
    assert measured == MEASURED_TOTAL_BACKING_WEI // ACTIVE_LISTINGS_25612701

    assert fwa_ev.arithmetic_mean_wei([]) == 0


def test_hm_am_gap_measured_not_assumed():
    """``arithmetic / harmonic`` — the protocol in one number, but a *live* one.

    3.8856x on the block 25612701 distribution.  The gap moves with pool
    composition (measured as low as ~3.49x after the pool grew 53% two days
    later), so it is asserted only against the distribution it was measured on
    and must never be hardcoded as a constant.
    """
    backings = list(_backings())
    gap = fwa_ev.hm_am_gap(backings)

    assert gap == pytest.approx(MEASURED_GAP, rel=1e-12)
    assert gap == pytest.approx(_statistics()["arithmetic_over_harmonic_gap"], rel=1e-12)
    # it is exactly the ratio of the two means, not an independent estimate
    assert gap == pytest.approx(
        fwa_ev.arithmetic_mean_wei(backings) / fwa_ev.harmonic_mean_wei(backings),
        rel=1e-15,
    )

    # a flat pool has no gap at all; the gap is created by dispersion
    assert fwa_ev.hm_am_gap([ETH] * 10) == pytest.approx(1.0)
    assert fwa_ev.hm_am_gap([]) == 0.0
    # and it responds to composition rather than being pinned to any multiple
    assert fwa_ev.hm_am_gap([ETH] * 9 + [1000 * ETH]) > gap


def test_module_hardcodes_no_gap_constant():
    """The gap is live-varying; no module constant may pretend otherwise.

    Every public constant in the module is an exact protocol integer (bps, a
    numerator, a wei scale, a ramp boundary in seconds).  A hardcoded 3.89x or
    4.0x ratio would necessarily be a float, so "no float constants" is the
    check that actually forbids it.
    """
    constants = {
        name: value
        for name, value in vars(fwa_ev).items()
        if name.isupper() and not name.startswith("_")
    }
    assert constants, "expected the module to declare public constants"

    floats = {name: value for name, value in constants.items() if isinstance(value, float)}
    assert not floats, f"module declares float constants: {floats}"

    # ...and nothing named after the harmonic/arithmetic gap.  HOT_GAP_SECONDS
    # and COLD_GAP_SECONDS are the surcharge ramp's *time* boundaries (PRD §4),
    # which are genuine protocol constants and are exempt.
    gap_named = [name for name in constants if "GAP" in name and not name.endswith("_SECONDS")]
    assert not gap_named, gap_named


# ---------------------------------------------------------------------------
# 7 — selection odds (mechanics §5)
# ---------------------------------------------------------------------------


def test_selection_probability_and_expected_draws():
    p = fwa_ev.selection_probability(MAX_BACKING_WEI, TOTAL_WEIGHT_25612701)
    # mechanics §14.2 quotes ~1.45e-7 for the 221 ETH chase position
    assert p == pytest.approx(1.45e-7, rel=1e-2)

    draws = fwa_ev.expected_draws_until(MAX_BACKING_WEI, TOTAL_WEIGHT_25612701)
    assert draws == pytest.approx(1.0 / p, rel=1e-9)
    assert draws > 6_000_000

    assert fwa_ev.selection_probability(ETH, 0) == 0.0


def test_weight_shares_sum_to_one():
    """Over the real distribution the probabilities form a proper distribution."""
    tw = fwa_ev.total_weight(_backings())
    total_p = sum(fwa_ev.selection_probability(b, tw) for b in _backings())
    assert total_p == pytest.approx(1.0, rel=1e-12)

    # inverse weighting, rule 1: more backing -> strictly less likely
    ps = [fwa_ev.selection_probability(b, tw) for b in (ETH, 2 * ETH, 4 * ETH)]
    assert ps[0] > ps[1] > ps[2]


def test_punks_weight_share_rounds_to_zero():
    """CryptoPunks 721 wrapper: 3 positions, 137.10 ETH, 0.000% of the weight."""
    punks = _by_collection()[PUNKS721_ADDRESS]
    assert punks["positions"] == 3
    assert punks["backing_wei"] == 137_100_000_000_000_000_000  # 137.10 ETH
    assert round(punks["weight_share_pct"], 3) == 0.000
    assert punks["weight_share_pct"] > 0.0  # small, but not literally nothing

    # recompute independently from the fixture's own weight and the pool total
    assert punks["weight"] / TOTAL_WEIGHT_25612701 * 100 == pytest.approx(
        punks["weight_share_pct"], abs=5e-7
    )

    # and through the public function, on positions of that size
    shares = fwa_ev.collection_weight_shares(
        [(45_700_000_000_000_000_000, "CryptoPunks 721")] * 3,
        total_weight=TOTAL_WEIGHT_25612701,
    )
    assert round(shares["CryptoPunks 721"], 3) == 0.000


def test_ttt_weight_share():
    """Ten Thousand Tokens holds 49.083% of selection weight (measured)."""
    ttt = _by_collection()[TTT_ADDRESS]
    assert ttt["positions"] == 1732
    assert ttt["weight_share_pct"] == pytest.approx(49.083, abs=0.001)
    assert ttt["weight"] / TOTAL_WEIGHT_25612701 * 100 == pytest.approx(
        ttt["weight_share_pct"], abs=5e-7
    )

    # 44.8% of the positions but 49.1% of the weight — inverse weighting does
    # not simply track position count either
    assert ttt["positions"] / ACTIVE_LISTINGS_25612701 * 100 < ttt["weight_share_pct"]

    # the per-collection breakdown accounts for the whole pool, exactly
    assert sum(v["weight"] for v in _by_collection().values()) == TOTAL_WEIGHT_25612701
    assert sum(v["positions"] for v in _by_collection().values()) == ACTIVE_LISTINGS_25612701
    assert sum(v["backing_wei"] for v in _by_collection().values()) == MEASURED_TOTAL_BACKING_WEI
    assert sum(v["weight_share_pct"] for v in _by_collection().values()) == pytest.approx(
        100.0, abs=1e-3
    )


def test_collection_weight_shares_over_real_backings():
    """Split the real distribution in two and check the shares are exact."""
    backings = list(_backings())
    head, tail = backings[:1732], backings[1732:]
    pairs = [(b, "head") for b in head] + [(b, "tail") for b in tail]

    shares = fwa_ev.collection_weight_shares(pairs)
    total = fwa_ev.total_weight(backings)
    assert shares["head"] == pytest.approx(fwa_ev.total_weight(head) / total * 100, rel=1e-12)
    assert shares["tail"] == pytest.approx(fwa_ev.total_weight(tail) / total * 100, rel=1e-12)
    assert sum(shares.values()) == pytest.approx(100.0, rel=1e-12)
    # ordered largest first
    assert list(shares.values()) == sorted(shares.values(), reverse=True)


def test_collection_weight_shares_are_exact_for_a_known_split():
    positions = [(ETH, "a"), (ETH, "a"), (2 * ETH, "b")]
    shares = fwa_ev.collection_weight_shares(positions)
    # weights 1e18 + 1e18 vs 5e17 -> 80% / 20%
    assert shares["a"] == pytest.approx(80.0)
    assert shares["b"] == pytest.approx(20.0)
    assert sum(shares.values()) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 8 — the EV band (PRD §3, rule 3)
# ---------------------------------------------------------------------------

BAND_POSITIONS = [
    (1 * ETH, "alpha"),  # sell-back 0.85, floor 2.0  -> keep
    (4 * ETH, "beta"),  # sell-back 3.40, floor UNKNOWN
    (10**17, "gamma"),  # sell-back 0.085, floor 0.05 -> sell back
]
BAND_FLOORS_PARTIAL = {"alpha": 2.0, "gamma": 0.05}
BAND_FLOORS_FULL = {"alpha": 2.0, "beta": 1.0, "gamma": 0.05}


def _band(floors, **kw):
    return fwa_ev.pull_ev_band(
        BAND_POSITIONS,
        floors,
        acquisition_fee_wei=FEE_25612701,
        **kw,
    )


def test_ev_band_has_no_point_estimate_field():
    """PRD §3 / plan risk R13 — there must be no single confident number."""
    band = _band(BAND_FLOORS_PARTIAL)
    forbidden = {"ev", "ev_eth", "point", "point_eth", "value", "value_eth", "estimate"}
    assert forbidden.isdisjoint(band.keys())
    assert "lower_eth" in band and "best_eth" in band


def test_ev_band_lower_le_best():
    """Property-style over several floor maps, including pathological ones."""
    floor_maps = [
        {},
        BAND_FLOORS_PARTIAL,
        BAND_FLOORS_FULL,
        {"alpha": 0.0, "beta": 0.0, "gamma": 0.0},
        {"beta": 99.0},
        {"alpha": 1e-9, "gamma": 500.0},
        {"delta": 5.0},  # a floor for a collection that is not in the pool
    ]
    for floors in floor_maps:
        band = _band(floors)
        assert band["lower_eth"] <= band["best_eth"], floors


def test_ev_band_unknown_floors_zeroed_in_lower():
    """beta is unpriced, so it contributes nothing at all to the lower bound."""
    band = _band(BAND_FLOORS_PARTIAL)
    # p_alpha*2.0 + p_beta*0 + p_gamma*0.085 - fee
    assert band["lower_eth"] == pytest.approx(0.117072449682, abs=1e-9)


def test_ev_band_unknown_floors_excluded_in_best():
    """beta keeps its guaranteed 0.85 x backing; only the max() drops the floor."""
    band = _band(BAND_FLOORS_PARTIAL)
    assert band["best_eth"] == pytest.approx(0.192628005238, abs=1e-9)
    assert band["best_eth"] > band["lower_eth"]


def test_ev_band_full_coverage_collapses_band():
    band = _band(BAND_FLOORS_FULL)
    assert band["lower_eth"] == band["best_eth"]
    assert band["collections_priced"] == band["collections_total"] == 3
    assert band["weight_priced_pct"] == pytest.approx(100.0)


def test_ev_band_zero_coverage():
    """No floors at all: best falls back to the sell-back-only expectation."""
    band = _band({})
    assert band["collections_priced"] == 0
    assert band["weight_priced_pct"] == pytest.approx(0.0)
    assert band["best_eth"] == pytest.approx(band["sellback_only_eth"], abs=1e-12)
    assert band["best_eth"] == pytest.approx(0.090405783015, abs=1e-9)
    # strictly pessimistic: nothing is verifiable, so the lower bound is -fee
    assert band["lower_eth"] == pytest.approx(-FEE_25612701 / ETH, abs=1e-12)
    assert band["lower_eth"] < band["best_eth"]


def test_ev_band_reports_coverage():
    """PRD §3 coverage badge: '22/38 - N% of weight priced'."""
    positions = [(int((i + 1) * 10**17), f"c{i}") for i in range(38)]
    floors = {f"c{i}": 1.0 for i in range(22)}
    band = fwa_ev.pull_ev_band(positions, floors, acquisition_fee_wei=FEE_25612701)

    assert band["collections_priced"] == 22
    assert band["collections_total"] == 38
    assert 0.0 < band["weight_priced_pct"] < 100.0
    # inverse weighting concentrates weight in the cheap (priced) end here
    assert band["weight_priced_pct"] > 50.0
    assert band["positions"] == 38


def test_ev_band_over_the_real_collection_mix():
    """The live coverage gap: the biggest weight buckets have no keyless floor.

    findings §10 — CoinGecko 404s on TTT (49.08% of weight), Art Blocks
    Explorations (18.99%) and the CryptoPunks 721 wrapper.  Uses the measured
    per-collection weights, so the band really is unpriced where the pool is.
    """
    by_collection = _by_collection()
    unpriced = {TTT_ADDRESS, ART_BLOCKS_ADDRESS, PUNKS721_ADDRESS}

    # one representative position per collection, at that collection's mean backing
    positions = [
        (max(1, v["backing_wei"] // v["positions"]), address)
        for address, v in by_collection.items()
    ]
    floors = {address: 1.0 for address in by_collection if address not in unpriced}

    band = fwa_ev.pull_ev_band(positions, floors, acquisition_fee_wei=FEE_25612701)
    assert band["collections_total"] == 38
    assert band["collections_priced"] == 35
    assert band["lower_eth"] < band["best_eth"]  # a genuine band, not a point
    assert 0.0 < band["weight_priced_pct"] < 100.0


def test_ev_band_empty_pool_does_not_raise():
    band = fwa_ev.pull_ev_band([], {}, acquisition_fee_wei=FEE_25612701)
    assert band["collections_total"] == 0
    assert band["weight_priced_pct"] == 0.0
    assert band["lower_eth"] <= band["best_eth"]


def test_ev_band_rebate_lifts_both_bounds():
    """PRD §3 component 3 / §4 — the cold-pool $FWA rebate."""
    cold = _band(BAND_FLOORS_PARTIAL, rebate_share=1.0)
    hot = _band(BAND_FLOORS_PARTIAL, rebate_share=0.0)
    # surcharge is 1000/11000 of the fee, ~0.01239 ETH
    surcharge_eth = FEE_25612701 * 1000 // 11000 / ETH
    assert cold["rebate_eth"] == pytest.approx(surcharge_eth, abs=1e-9)
    assert cold["best_eth"] - hot["best_eth"] == pytest.approx(surcharge_eth, abs=1e-9)
    assert cold["lower_eth"] - hot["lower_eth"] == pytest.approx(surcharge_eth, abs=1e-9)


def test_ev_band_invariant_is_enforced_inside_the_function():
    """The lower<=best guard must live in the implementation, not just here."""
    src = inspect.getsource(fwa_ev.pull_ev_band)
    assert "lower" in src and "best" in src
    assert "AssertionError" in src or "assert " in src


def test_pure_flip_is_negative_ev():
    """PRD §3.1 — sell-back at the harmonic mean is about -22%."""
    ev_wei = fwa_ev.expected_value_wei(WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)
    edge = fwa_ev.round_trip_return(ev_wei, FEE_25612701) - 1.0
    assert -0.23 < edge < -0.22
    assert round(edge, 3) == -0.227


def test_payout_bps_is_payout_not_discount():
    """mechanics §7 naming trap: 8500 means the purchaser RECEIVES 85%."""
    assert fwa_ev.sellback_payout_wei(ETH) == 85 * 10**16
    assert fwa_ev.sellback_payout_wei(ETH) != 15 * 10**16
    assert fwa_ev.DEFAULT_PURCHASER_PAYOUT_BPS == 8500

    # the retained slice is the complement, and it is the smaller number
    retained = ETH - fwa_ev.sellback_payout_wei(ETH)
    assert retained == 15 * 10**16
    assert fwa_ev.sellback_payout_wei(ETH) > retained

    # and the band uses it the same way round
    band = fwa_ev.pull_ev_band(
        [(ETH, "solo")], {}, acquisition_fee_wei=0, purchaser_payout_bps=8500
    )
    assert band["best_eth"] == pytest.approx(0.85, abs=1e-12)


# ---------------------------------------------------------------------------
# 9-11 — jackpot, crown, surcharge ramp
# ---------------------------------------------------------------------------


def test_jackpot_ratio_1378x():
    """mechanics §14.2: 221 ETH backing at a 0.1363 ETH fee -> ~1,378x."""
    ratio = fwa_ev.jackpot_ratio(MAX_BACKING_WEI, 136_300_000_000_000_000)
    assert round(ratio) == 1378

    live = fwa_ev.jackpot_ratio(MAX_BACKING_WEI, FEE_25612701)
    assert 1370 < live < 1390

    prob = fwa_ev.jackpot_probability(MAX_BACKING_WEI, TOTAL_WEIGHT_25612701)
    assert prob == pytest.approx(1.45e-7, rel=1e-2)

    # a 1,378x payout at 1.45e-7 contributes ~0.0002x — a story, not an edge
    assert live * prob < 0.001

    assert fwa_ev.jackpot_ratio(MAX_BACKING_WEI, 0) == 0.0


def test_crown_seize_is_110pct():
    """mechanics §11 ``_beatsTop``: challenger >= 1.10 x incumbent."""
    assert fwa_ev.crown_seize_wei(100 * ETH) == 110 * ETH
    assert fwa_ev.crown_seize_wei(MAX_BACKING_WEI) == 221 * ETH * 11000 // 10000
    assert fwa_ev.DEFAULT_TOP_THRESHOLD_BPS == 1000
    # threshold is live-read, not hardcoded (rule 6)
    assert fwa_ev.crown_seize_wei(100 * ETH, threshold_bps=5000) == 150 * ETH
    # integer floor, never a float
    assert isinstance(fwa_ev.crown_seize_wei(3), int)

    # the crown at 25612701 is listing 56508, the 221 ETH position: 243.1 ETH to take it
    assert _block(25612701)["topListingId"] == 56508
    assert fwa_ev.crown_seize_wei(MAX_BACKING_WEI) == 243_100_000_000_000_000_000


def test_surcharge_ramp_endpoints():
    """PRD §4: 0% to the purchaser at <=60 s, 100% at >=3600 s, ramp between."""
    assert fwa_ev.surcharge_ramp_share(0) == 0.0
    assert fwa_ev.surcharge_ramp_share(60) == 0.0
    assert fwa_ev.surcharge_ramp_share(3600) == 1.0
    assert fwa_ev.surcharge_ramp_share(999_999) == 1.0
    assert fwa_ev.surcharge_ramp_share(1830) == pytest.approx(0.5, abs=1e-3)

    previous = -1.0
    for gap in range(0, 4000, 37):
        share = fwa_ev.surcharge_ramp_share(gap)
        assert 0.0 <= share <= 1.0
        assert share >= previous
        previous = share


def test_surcharge_ramp_docstring_flags_it_as_a_fallback():
    """PRD §4 note / §13 — linearity unconfirmed; the live value always wins."""
    doc = (fwa_ev.surcharge_ramp_share.__doc__ or "").lower()
    assert "fallback" in doc
    assert "unconfirmed" in doc
    assert "tokensharebps" in doc


# ---------------------------------------------------------------------------
# 12-13 — revenue split, fee split, round trip
# ---------------------------------------------------------------------------


def test_take_rate():
    """findings §9.4: dailyRevenue / dailyFees = 8.8%."""
    assert fwa_ev.take_rate(512_877, 5_797_920) == pytest.approx(0.0885, abs=5e-4)
    assert round(fwa_ev.take_rate(512_877, 5_797_920) * 100, 1) == 8.8
    assert fwa_ev.take_rate(1.0, 0) == 0.0


def test_per_position_credit_equal_split():
    """PRD rule 5 / mechanics §9.2 — feeShare is 1 for every position."""
    assert fwa_ev.per_position_credit(10**18, 4) == 25 * 10**16
    # floor division: credited <= collected, always
    assert fwa_ev.per_position_credit(10, 3) == 3
    assert fwa_ev.per_position_credit(10, 3) * 3 <= 10
    # backing buys duration, not share size
    assert fwa_ev.per_position_credit(10**18, ACTIVE_LISTINGS_25612701) == (
        10**18 // ACTIVE_LISTINGS_25612701
    )
    assert fwa_ev.per_position_credit(10**18, 0) == 0

    # the split denominator is the onchain feeShareTotal (rule 5)
    decoded = _block(25612701)
    assert fwa_ev.per_position_credit(10**18, decoded["feeShareTotal"]) == (
        fwa_ev.per_position_credit(10**18, decoded["activeListingCount"])
    )


def test_settlement_shares_sum_to_100():
    """mechanics §7 — 51,522 settlements, all-time."""
    counts = {
        "accept_bid_tokens": 38_083,
        "accept_bid_eth": 7_133,
        "relist": 3_934,
        "keep": 2_372,
        "force_finalized": 0,
    }
    rows = fwa_ev.settlement_shares(counts)
    assert [r["outcome"] for r in rows] == [
        "accept_bid_tokens",
        "accept_bid_eth",
        "relist",
        "keep",
        "force_finalized",
    ]
    assert [round(r["share_pct"], 2) for r in rows] == [73.92, 13.84, 7.64, 4.60, 0.00]
    assert sum(r["count"] for r in rows) == 51_522
    assert math.isclose(sum(r["share_pct"] for r in rows), 100.0, abs_tol=1e-9)

    assert fwa_ev.settlement_shares({}) == []
    assert all(r["share_pct"] == 0.0 for r in fwa_ev.settlement_shares({"a": 0, "b": 0}))


def test_round_trip_return_is_0_773():
    """mechanics §14.2 — 0.85 / 1.10 = 0.773, a structural -23%."""
    ev_wei = fwa_ev.expected_value_wei(WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)
    assert round(fwa_ev.round_trip_return(ev_wei, FEE_25612701), 3) == 0.773

    # drawing the 221 ETH position is the other end of the same formula
    assert fwa_ev.round_trip_return(MAX_BACKING_WEI, FEE_25612701) > 1000.0
    assert fwa_ev.round_trip_return(ETH, 0) == 0.0


# ---------------------------------------------------------------------------
# Purity guards
# ---------------------------------------------------------------------------

WEI_FUNCTIONS = [
    (fwa_ev.inverse_weight, (10**18,)),
    (fwa_ev.total_weight, ([10**18, 2 * 10**18],)),
    (fwa_ev.weighted_backing_total, ([10**18, 2 * 10**18],)),
    (fwa_ev.expected_value_wei, (WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)),
    (fwa_ev.acquisition_fee_wei, (WEIGHTED_TOTAL_25612701, TOTAL_WEIGHT_25612701)),
    (fwa_ev.harmonic_mean_wei, ([10**18, 3 * 10**18],)),
    (fwa_ev.arithmetic_mean_wei, ([10**18, 3 * 10**18],)),
    (fwa_ev.sellback_payout_wei, (10**18,)),
    (fwa_ev.crown_seize_wei, (10**18,)),
    (fwa_ev.per_position_credit, (10**18, 7)),
    (fwa_ev.surcharge_wei, (FEE_25612701,)),
]


def test_no_float_in_wei_paths():
    for func, args in WEI_FUNCTIONS:
        result = func(*args)
        assert type(result) is int, f"{func.__name__} returned {type(result).__name__}"

    # and on the real 3,867-position distribution, not just toy inputs
    for func in (
        fwa_ev.total_weight,
        fwa_ev.weighted_backing_total,
        fwa_ev.harmonic_mean_wei,
        fwa_ev.arithmetic_mean_wei,
    ):
        assert type(func(_backings())) is int, func.__name__


def test_module_imports_stdlib_only():
    """Acceptance criterion: zero imports outside the stdlib."""
    source = Path(fwa_ev.__file__).read_text()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and " import " in f" {stripped} ":
            assert "maxpane" not in stripped, stripped
            assert "textual" not in stripped, stripped
            assert "pydantic" not in stripped, stripped
            assert "requests" not in stripped, stripped
            assert "httpx" not in stripped, stripped
