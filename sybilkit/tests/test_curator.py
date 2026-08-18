"""WP2.1 / WP2.2 — the THE-LIST preset: the curve, the segments, the clean list.

Nothing in here opens a socket and nothing in here imports ``httpx``: the
preset is pure, stdlib-only library code that a caller feeds a
:class:`sybilkit.Dataset` and a :class:`sybilkit.DetectResult`.

The one rule this file exists to keep honest
    **The preset holds THE LIST's constants as *inputs*, never as documentation
    it typed in.**  ``POINTS_PER_ETH`` and ``minDeposit`` are read off the chain
    by whoever builds the preset (the CLI does it with an ``eth_call``); the
    library never carries a remembered 1000 or a remembered 0.05.  CLAUDE.md
    hard constraint 4 — "read values live; never hardcode a documented one" —
    and controller rulings R10 and R13.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math
from pathlib import Path

import pytest

from sybilkit import DetectConfig, curve, detect
from sybilkit import curator as preset_mod
from sybilkit.report import DetectResult
from sybilkit.curator import (
    FORBIDDEN_LABEL_WORDS,
    Segment,
    CuratorPreset,
    clean_list,
    curve_points,
    multiplier_bps,
    segments,
)

SRC = Path(preset_mod.__file__).resolve().parent

ETH = 10**18

#: A live-read pair.  Every test that needs a preset builds one from *these*
#: two numbers rather than from a default, because there is no default: the
#: rate and the minimum are what a caller measured, this hour, on this chain.
LIVE_RATE = 1000
LIVE_MIN_DEPOSIT_WEI = 5 * 10**16


def a_preset(**over) -> CuratorPreset:
    kwargs = {"points_per_eth": LIVE_RATE, "min_deposit_wei": LIVE_MIN_DEPOSIT_WEI}
    kwargs.update(over)
    return CuratorPreset(**kwargs)


# ===========================================================================
# WP2.1 — the curve is the core curve, re-exported (ruling R1)
# ===========================================================================


def test_the_preset_curve_is_the_core_curve() -> None:
    """Ruling R1: ``sybilkit.curator`` re-exports ``sybilkit.curve``'s
    function — the same object, not a copy that agrees today.

    A second implementation is always the one nobody mutation-tests, and the
    two drift in the last digits where nobody looks.  ``is`` rather than an
    equality of outputs, because equality of outputs is exactly what a drifted
    copy has on the day it is written.
    """
    assert curve_points is curve.curve_points


@pytest.mark.parametrize(
    "weight_wei, points",
    [
        (0, 0),
        (1 * ETH, 1_000),
        (4 * ETH, 2_000),
        (100 * ETH, 10_000),
        (1_000 * ETH, 31_622),
        (2_000 * ETH, 44_721),
    ],
)
def test_the_documented_points_come_out_of_the_re_export(
    weight_wei: int, points: int
) -> None:
    """The six anchors from ``curator_game_mechanics.md``, asked of the preset's
    own name — so a re-export that pointed at the wrong function would be
    caught here and not only by identity."""
    assert curve_points(weight_wei, LIVE_RATE) == points


def test_a_sub_eth_weight_keeps_its_points_through_the_preset() -> None:
    """Multiplication before division, checked through the preset's door.

    ``isqrt(w) // 10**9 * rate`` floors twice: a weight whose integer square
    root is just under 1e9 loses **every** point.  The one-line arithmetic that
    makes this pass lives in ``curve.py`` and is mutation-proven there (WP1
    bites 2–4); this asserts the preset did not grow a second one.
    """
    weight = (10**9 - 1) ** 2
    assert math.isqrt(weight) == 10**9 - 1
    assert curve_points(weight, LIVE_RATE) == 999


def test_the_rate_is_a_parameter_and_the_preset_has_no_remembered_one() -> None:
    """CLAUDE.md hard constraint 4 / ruling R10.

    Two halves.  The curve module carries no ``1000`` at all — the rate reaches
    it only as an argument.  And ``CuratorPreset.points_per_eth`` has **no
    default**: a caller that has not read the chain cannot construct a preset
    that quietly agrees with someone's memory of the rate.
    """
    tree = ast.parse((SRC / "curve.py").read_text(encoding="utf-8"))
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    ]
    assert 1000 not in literals, literals

    params = inspect.signature(CuratorPreset).parameters
    assert params["points_per_eth"].default is inspect.Parameter.empty


# ===========================================================================
# WP2.1 — the preset cannot be built without the two live reads (R10 / R13)
# ===========================================================================


def test_a_preset_cannot_be_built_without_the_live_rate_and_minimum() -> None:
    """Ruling R13's must-verify.

    Without ``protocol_min_amount_wei`` the 0.05-minimum crowd welds wholesale
    (WP1 measured 1 468 of 1 468 flagged with the knob off against 272 with it
    on), so the minimum is not an optional refinement — it is the difference
    between an analysis and a libel.  ``CuratorPreset`` therefore refuses to be
    constructed without it, and without the rate, at the door.
    """
    with pytest.raises(TypeError):
        CuratorPreset()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        CuratorPreset(points_per_eth=LIVE_RATE)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        CuratorPreset(min_deposit_wei=LIVE_MIN_DEPOSIT_WEI)  # type: ignore[call-arg]
    # and both together is enough — nothing else is a live read
    assert a_preset().points_per_eth == LIVE_RATE


def test_a_nonsense_rate_or_minimum_is_refused_at_construction() -> None:
    """A negative rate would make every point negative and a negative minimum
    would exempt nothing; both are programming errors, and a programming error
    raises rather than producing a plausible-looking analysis."""
    with pytest.raises(ValueError):
        a_preset(points_per_eth=0)
    with pytest.raises(ValueError):
        a_preset(points_per_eth=-1000)
    with pytest.raises(ValueError):
        a_preset(min_deposit_wei=-1)


def test_the_preset_threads_both_live_reads_into_the_detect_config() -> None:
    """Ruling R10 + R13: the rate and the minimum reach ``DetectConfig``, which
    is the only path there is — WP1 removed the dataset-attribute fallback."""
    cfg = a_preset().detect_config()
    assert isinstance(cfg, DetectConfig)
    assert cfg.points_per_eth == LIVE_RATE
    assert cfg.protocol_min_amount_wei == LIVE_MIN_DEPOSIT_WEI
    assert (cfg.min_size, cfg.min_families) == (5, 2)


def test_the_gate_knobs_travel_through_the_preset_too() -> None:
    cfg = a_preset(min_size=9, min_families=3, near_amount_tol=0.05).detect_config()
    assert (cfg.min_size, cfg.min_families, cfg.near_amount_tol) == (9, 3, 0.05)


def test_a_caller_supplied_rate_reaches_the_point_folds(labeled_ds) -> None:
    """Ruling R10's agreement test: **demonstrably** reaches ``detect``'s folds.

    Two presets differing only in the rate.  Every fold — the population total
    and each cluster's own points — is re-derived in the test from
    ``curve_points`` at that rate and compared wei-exactly, so a preset that
    dropped the rate on the floor (and let ``DetectConfig``'s documented
    default answer instead) cannot pass: the default *is* 1000, so only the
    doubled run can catch it, and it does.
    """
    last_weight: dict[str, int] = {}
    for dep in labeled_ds.deposits:  # chain order: last write is final weight
        last_weight[dep.contributor] = dep.new_weight_wei

    at_rate = detect(labeled_ds, a_preset().detect_config())
    at_double = detect(labeled_ds, a_preset(points_per_eth=2 * LIVE_RATE).detect_config())

    assert at_rate.total_points == sum(
        curve_points(w, LIVE_RATE) for w in last_weight.values()
    )
    assert at_double.total_points == sum(
        curve_points(w, 2 * LIVE_RATE) for w in last_weight.values()
    )
    assert at_double.total_points > at_rate.total_points

    assert at_rate.clusters and len(at_double.clusters) == len(at_rate.clusters)
    for cl in at_double.clusters:
        assert cl.points == sum(
            curve_points(last_weight[m], 2 * LIVE_RATE) for m in cl.members
        )

    # Membership and ordering do not move with the rate at all — the rate is a
    # scale on the *scoring*, never on the linking.
    assert [c.members for c in at_double.clusters] == [
        c.members for c in at_rate.clusters
    ]
    # Shares are rate-invariant only up to the curve's own floor: each member's
    # points are floored independently, so a different rate rounds a different
    # set of wallets down and the share moves in the fifth decimal.  Measured
    # max drift across the eleven labeled clusters at 1000 -> 2000: 3.4e-05.
    # Asserted as a bound rather than an equality because the equality is
    # simply not true, and a test that claims it is would have to be relaxed by
    # the next person who ran it on real data.
    for doubled, single in zip(at_double.clusters, at_rate.clusters):
        assert abs(doubled.points_share - single.points_share) < 1e-4


def test_doubling_the_rate_doubles_the_points_wei_exactly() -> None:
    """The same claim without the floor's noise: on a weight whose square root
    is a whole gwei, ``2×rate`` is exactly ``2×points`` — no rounding, no
    ``approx``."""
    weight = (7 * 10**9) ** 2  # isqrt == 7e9 exactly
    assert curve_points(weight, LIVE_RATE) == 7_000
    assert curve_points(weight, 2 * LIVE_RATE) == 14_000


def test_the_minimum_knob_is_load_bearing_on_the_real_population(
    population_ds,
) -> None:
    """Ruling R13, measured rather than asserted from memory: with the live
    minimum threaded through the preset, the crowd that all paid the floor is
    not flagged wholesale; with the knob off it welds.

    The bar is a band, not a pinned count — WP1 measured 272 of 1 468 with the
    knob on and 1 468 of 1 468 with it off, and this asserts the *gap*, which
    is what the knob is for.
    """
    minimum_payers = {
        dep.contributor
        for dep in population_ds.deposits
        if dep.amount_wei == LIVE_MIN_DEPOSIT_WEI
    }
    assert len(minimum_payers) > 1_000  # the crowd really is in this fixture

    cfg = a_preset().detect_config()
    with_knob = detect(population_ds, cfg)
    without = detect(population_ds, dataclasses.replace(cfg, protocol_min_amount_wei=None))
    flagged_with = len(minimum_payers & with_knob.flagged)
    flagged_without = len(minimum_payers & without.flagged)
    assert flagged_without > flagged_with * 2
    assert flagged_with < len(minimum_payers) // 2


# ===========================================================================
# WP2.2 — segments: whale OPERATORS, cohorts, hour and multiplier bands
# ===========================================================================


@pytest.fixture(scope="module")
def population_analysis(population_ds):
    """One ``detect`` over the whole population, reused by every segment test.

    Module-scoped because the run is ~0.4 s and eleven tests want the same
    answer; the core is pure, so one run and eleven readers cannot disagree.
    """
    preset = a_preset()
    res = detect(population_ds, preset.detect_config())
    return preset, population_ds, res


def _final_weight(ds) -> dict[str, int]:
    last: dict[str, int] = {}
    for dep in ds.deposits:  # chain order: the last write is the final weight
        last[dep.contributor] = dep.new_weight_wei
    return last


def _first_deposit(ds) -> dict[str, object]:
    first: dict[str, object] = {}
    for dep in ds.deposits:
        first.setdefault(dep.contributor, dep)
    return first


def test_the_whale_segment_is_the_operator_not_the_single_send(
    population_analysis,
) -> None:
    """Research §5 / Adam's ask, re-derived from the committed population.

    A credit-threshold whale list at 800 ETH+ finds **two wallets holding
    0.25% of the points**, because real whale capital on this contract is
    *split*: 171.99×10, 14×997, 10×769.  So the whale segment has to be defined
    on the combined credit of an **operator**, and the preset's
    ``largest_operators`` is exactly that — an order of magnitude more points
    than the single-send list, off the same threshold.
    """
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)

    weights = _final_weight(ds)
    biggest_send: dict[str, int] = {}
    for dep in ds.deposits:
        addr = dep.contributor
        if dep.amount_wei > biggest_send.get(addr, 0):
            biggest_send[addr] = dep.amount_wei
    single_send_whales = {
        a for a, m in biggest_send.items() if m >= preset.largest_operator_credit_wei
    }
    single_send_points = sum(preset.points(weights[a]) for a in single_send_whales)

    # The measured facts the whole segment design turns on.
    assert len(single_send_whales) == 2
    assert single_send_points == 67_014
    assert round(100 * single_send_points / segs.total_points, 2) == 0.25

    largest = segs.largest_operators
    assert largest, "no operator cleared the combined-credit line"
    assert all(op.credit_wei >= preset.largest_operator_credit_wei for op in largest)
    assert sum(op.size for op in largest) > 100 * len(single_send_whales)
    assert sum(op.points for op in largest) > 20 * single_send_points


def test_the_operator_list_is_ranked_by_combined_credit(population_analysis) -> None:
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    credits = [op.credit_wei for op in segs.operators]
    assert credits == sorted(credits, reverse=True)
    assert len(segs.operators) == len(res.clusters)
    assert {op.cluster_id for op in segs.operators} == {
        c.cluster_id for c in res.clusters
    }


def test_an_operator_carries_its_own_sqrt_subsidy(population_analysis) -> None:
    """The number that makes the sqrt curve's invitation legible: the points
    the group earned split, over the points the same weight would have earned
    in one wallet.  Always ≥ 1 by concavity, and re-derived here from the
    curve rather than read back off the object that produced it."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    weights = _final_weight(ds)
    by_id = {c.cluster_id: c for c in res.clusters}
    checked = 0
    for op in segs.operators[:5]:
        members = by_id[op.cluster_id].members
        combined = sum(weights[m] for m in members)
        alone = curve_points(combined, preset.points_per_eth)
        assert op.weight_wei == combined
        assert op.subsidy_x == pytest.approx(op.points / alone)
        assert op.subsidy_x >= 1.0
        checked += 1
    assert checked == 5


def test_the_early_cohort_is_seven_point_six_one_percent_of_points(
    population_analysis,
) -> None:
    """Research §5: join index 1–1000 is 6.4% of wallets and **7.61% of
    points**.  Re-derived from ``first_deposits.json.gz`` rather than retyped:
    1 000 contributors, 2 024 397 points of 26 585 740."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    (early,) = [s for s in segs.bands if s.key == "early_cohort"]
    assert early.contributors == 1_000
    assert early.points == 2_024_397
    assert round(100 * early.points_share, 2) == 7.61
    assert segs.total_points == 26_585_740


def test_the_late_grace_cohort_is_two_point_three_nine_percent_of_points(
    population_analysis,
) -> None:
    """Research §5: hours 22–23, the last of the grace window — 742 wallets,
    **2.39% of points**.  FOMO at ≤1.06×, not multiplier chasers."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    (late,) = [s for s in segs.bands if s.key == "late_cohort"]
    assert late.contributors == 742
    assert late.points == 634_538
    assert round(100 * late.points_share, 2) == 2.39


def _mini_dataset(specs):
    """A tiny ``Dataset`` from ``(join_index, hour)`` pairs — one deposit each.

    Small on purpose: the committed population covers hours 0–23 and join
    indices 1–N contiguously, so it cannot exhibit either edge the two tests
    below are about (a dataset younger than the late-cohort window, and a
    first-1 000 slice that is a *sample* rather than a prefix).
    """
    from sybilkit.model import Dataset

    deposits, firsts = [], []
    for i, (index, hour) in enumerate(specs, start=1):
        addr = f"0x{i:040x}"
        deposits.append(
            {
                "contributor": addr,
                "hour": hour,
                "amount_wei": 10**18,
                "credited_delta_wei": 10**18,
                "weight_added_wei": 15 * 10**17,
                "new_weight_wei": 15 * 10**17,
                "tx_count": 1,
                "block_number": 100 + i,
                "log_index": 1,
                "tx_hash": "0x" + f"{i:064x}",
            }
        )
        firsts.append({"contributor": addr, "index": index})
    return Dataset.from_events(deposits, firsts)


def test_the_late_cohort_window_never_names_an_hour_before_zero() -> None:
    """**Review #15a.**  The window is ``last_hour - late_cohort_hours + 1``
    with no floor, so a dataset younger than the window prints an hour that
    does not exist: with ``late_cohort_hours=3`` on a sweep whose newest join
    is hour 1, the detail read "joined in hours -1–1".

    Hour −1 is not a slow hour or an empty hour — it is not an hour, and the
    band's own membership was never filtered by it (no deposit can carry it).
    A detail line is a claim about the data; this one was arithmetic leaking
    out of a range.
    """
    preset = a_preset(late_cohort_hours=3)
    ds = _mini_dataset([(1, 0), (2, 0), (3, 1), (4, 1), (5, 1), (6, 1)])
    res = detect(ds, preset.detect_config())
    segs = segments(ds, res, preset)

    (late,) = [s for s in segs.bands if s.key == "late_cohort"]
    assert late.detail == "joined in hours 0–1"
    assert "-1" not in late.detail
    # the whole population is inside the clamped window, so nothing was lost
    assert late.contributors == segs.total_contributors


def test_the_late_cohort_window_is_exactly_the_hours_the_preset_asks_for() -> None:
    """**Review R4.1.**  The clamp above pins only the window's *floor*, and it
    cannot pin its *size*: where ``max(0, …)`` bites, ``last_hour - hours`` and
    ``last_hour - hours + 1`` are both negative and both clamp to ``0``, so the
    ``+ 1`` — the difference between an ``hours``-wide window and an
    ``hours + 1``-wide one — is invisible there.

    This is that arithmetic, measured away from the clamp: ``late_cohort_hours=3``
    on a dataset whose newest join is hour 5 covers hours **3–5**, three hours
    and three wallets.  Without the ``+ 1`` it would reach back to hour 2 and
    quietly enlarge both the span it prints and the cohort it counts.  Only the
    full-population percentage test caught that before, which is a fact about
    one committed capture rather than about the arithmetic.
    """
    preset = a_preset(late_cohort_hours=3)
    ds = _mini_dataset([(1, 0), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5)])
    res = detect(ds, preset.detect_config())
    segs = segments(ds, res, preset)

    (late,) = [s for s in segs.bands if s.key == "late_cohort"]
    assert late.detail == "joined in hours 3–5"
    # three hours asked for, three hours' worth of wallets — not the four an
    # off-by-one window would sweep in, and not the whole six-hour population.
    assert late.contributors == 3
    assert segs.total_contributors == 6


def test_a_dataset_whose_only_hour_is_zero_reads_as_one_hour_not_a_range() -> None:
    """The singular branch the clamp newly makes reachable.

    With the default ``late_cohort_hours=2`` and every join in hour 0, the
    clamped window is ``range(0, 1)`` — length one — so the detail is the
    singular ``"joined in hour 0"``.  Unclamped it was ``range(-1, 1)``, length
    two, and the band advertised ``"joined in hours -1–0"``: a two-hour span
    over a one-hour dataset, one of whose hours does not exist.

    Worth its own test because the ``len(window) == 1`` arm of the span string
    was unreachable before the clamp — no window could be one hour wide — so
    the fix created a branch and nothing exercised it.
    """
    preset = a_preset()
    assert preset.late_cohort_hours == 2
    ds = _mini_dataset([(1, 0), (2, 0), (3, 0)])
    res = detect(ds, preset.detect_config())
    segs = segments(ds, res, preset)

    (late,) = [s for s in segs.bands if s.key == "late_cohort"]
    assert late.detail == "joined in hour 0"
    assert late.contributors == 3


def test_the_early_cohort_detail_counts_indices_present_not_addresses_on_the_list() -> None:
    """**Review #15b.**  The early-cohort detail said "the first N addresses on
    the list", where N is only how many of the first ``early_cohort_size`` join
    indices are **in this dataset**.

    On a partial sweep — which is every sweep the adapter runs before it has
    walked the whole history — that turns a fact about the *sample* into a
    fact about *the list*.  Here indices 1, 5 and 900 are present and 2–4 and
    6–899 are not: three addresses, and not one of them is "the first three".
    """
    preset = a_preset()
    ds = _mini_dataset([(1, 0), (5, 0), (900, 0), (1_400, 0), (1_700, 0)])
    res = detect(ds, preset.detect_config())
    segs = segments(ds, res, preset)

    (early,) = [s for s in segs.bands if s.key == "early_cohort"]
    assert early.contributors == 3
    assert ds.first_index["0x" + f"{3:040x}"] == 900  # the sample is not a prefix
    assert early.detail == "3 of the first 1,000 join indices present"
    assert "the first 3 addresses" not in early.detail


def test_the_hour_bands_partition_the_whole_population(population_analysis) -> None:
    """Every contributor lands in exactly one join-hour band, and the bands'
    points sum to the population's.  A band set that does not partition is a
    band set that quietly drops people."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    hours = [s for s in segs.bands if s.kind == "hour"]
    assert len(hours) == 24  # this sweep covers hours 0..23
    assert sum(s.contributors for s in hours) == segs.total_contributors
    assert sum(s.points for s in hours) == segs.total_points
    assert sum(s.points_share for s in hours) == pytest.approx(1.0)


def test_the_multiplier_bands_partition_the_whole_population(
    population_analysis,
) -> None:
    """The early-bird multiplier is not a field on ``Deposit`` — it is derived
    wei-exactly from the deposit's own words (``weight_added / credited_delta``
    in basis points), so nothing has to be remembered about the decay curve."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    bands = [s for s in segs.bands if s.kind == "multiplier"]
    assert len(bands) == len(preset.multiplier_band_bps)
    assert sum(s.contributors for s in bands) == segs.total_contributors
    assert sum(s.points for s in bands) == segs.total_points


def test_a_deposit_above_the_credit_cap_has_no_representable_multiplier(
    population_analysis,
) -> None:
    """``credited_delta_wei`` is legitimately ``0`` for a deposit above the
    cap, and nothing may divide by it.  Those contributors get an explicit
    unknown band rather than a silent 1.0× — the representable negative."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    unknown = [s for s in segs.bands if s.key == "multiplier_unknown"]
    # This population happens to contain none, so the band is absent rather
    # than present-and-zero: an empty band would read as a measured zero.
    assert unknown == []
    assert multiplier_bps(_first_deposit(ds)["0x200e710acaa6a93bbc77146026328c40f1d60fb1"]) == 19_975


def test_a_multiplier_below_the_lowest_band_is_unknown_not_the_lowest_band(
    labeled_ds,
) -> None:
    """**Review M4.**  The bottom band's fallback used to swallow anything it
    could not place.

    A deposit whose derived multiplier is *below* the lowest edge cannot happen
    on a decay curve that bottoms out at 1.0x — which is precisely why filing it
    under "1.00x-1.25x" is a fabricated fact rather than a harmless rounding.
    It is either a different deployment or a decode fault, and both belong in
    the band that says "no representable multiplier".
    """
    from sybilkit.model import Dataset

    rows = [
        {
            "contributor": f"0x{i:040x}", "hour": 0,
            "amount_wei": 10**18, "credited_delta_wei": 10**18,
            # weight BELOW the credit: a 0.5x multiplier, which the decay curve
            # never produces and the bands therefore cannot place.
            "weight_added_wei": 5 * 10**17, "new_weight_wei": 5 * 10**17,
            "tx_count": 1, "block_number": 100 + i, "log_index": 1,
            "tx_hash": "0x" + f"{i:064x}",
        }
        for i in range(1, 4)
    ]
    ds = Dataset.from_events(
        rows, [{"contributor": r["contributor"], "index": i}
               for i, r in enumerate(rows, start=1)]
    )
    preset = a_preset()
    res = detect(ds, preset.detect_config())
    segs = segments(ds, res, preset)

    assert multiplier_bps(ds.deposits[0]) == 5_000  # 0.5x, below every edge
    unknown = [s for s in segs.bands if s.key == "multiplier_unknown"]
    assert len(unknown) == 1
    assert unknown[0].contributors == 3
    assert not [s for s in segs.bands if s.key == "multiplier_10000"]


def test_the_linked_groups_band_is_not_named_after_the_credit_line(
    population_analysis,
) -> None:
    """**Review finding #12**, decision D4 ruled A (rename, do not filter).

    The aggregate band collects the members of **every** linked cluster,
    however small, and that is the number worth showing.  It was keyed and
    labelled ``largest_operators`` / "largest operators" — the name of the
    credit-line slice, which is a different and much smaller set — so the
    consumer's headline row claimed a fact about whales while measuring one
    about linked groups.

    Every measured number on the band stays exactly as it was; only the name
    moves.  ``kind`` stays ``"operators"`` so a consumer's ordering does not.
    """
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)

    (band,) = segs.by_kind("operators")
    assert band.key == "linked_groups"
    assert band.label == "linked groups"
    assert "largest" not in band.key and "largest" not in band.label

    # what it measures, and why the old name was wrong: it is every linked
    # wallet, not the credit-line slice, and the two are far apart here.
    linked = {m for c in res.clusters for m in c.members}
    over_the_line = {
        m
        for op in segs.largest_operators
        for m in next(c for c in res.clusters if c.cluster_id == op.cluster_id).members
    }
    assert band.contributors == len(linked)
    assert len(over_the_line) < len(linked)


def test_the_largest_operators_property_is_the_only_thing_the_credit_line_gates(
    population_ds,
) -> None:
    """The credit line gates the *property* and nothing a band renders.

    Two presets differing only in ``largest_operator_credit_wei``: the bands
    are byte-identical, the ``largest_operators`` slice is not.  That is the
    whole content of ruling D4/A — the knob whose purpose is defining
    "largest" keeps meaning that, and stops sharing a name with an aggregate
    it never gated.
    """
    low = a_preset(largest_operator_credit_wei=1)
    high = a_preset(largest_operator_credit_wei=10_000 * ETH)
    res = detect(population_ds, low.detect_config())

    at_low = segments(population_ds, res, low)
    at_high = segments(population_ds, res, high)

    assert at_low.bands == at_high.bands
    assert len(at_low.largest_operators) == len(at_low.operators)
    assert len(at_high.largest_operators) < len(at_low.largest_operators)


def test_the_segment_key_vocabulary_is_exactly_what_the_docstring_names(
    population_analysis,
) -> None:
    """**Review M3.**  The `Segment` docstring named a key spelling
    (``multiplier_17500_20000``) the code has never emitted.  A key vocabulary
    a consumer reads off a docstring and then keys on is worse than none.

    This is the agreement test, not a defect pin: it moved with the D4 rename
    (``largest_operators`` -> ``linked_groups``) rather than being weakened by
    it, and it now also asserts the retired spelling is gone from both the
    emitted keys and the docstring — see
    ``docs/curator_sybil_review_fixes_plan.md``, WP5.3.
    """
    import re

    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    allowed = re.compile(
        r"^(linked_groups|early_cohort|late_cohort|hour_\d+"
        r"|multiplier_\d+|multiplier_unknown)$"
    )
    for band in segs.bands:
        assert allowed.match(band.key), band.key
    doc = Segment.__doc__ or ""
    for spelling in ("linked_groups", "early_cohort", "late_cohort",
                     "hour_<h>", "multiplier_<edge_bps>", "multiplier_unknown"):
        assert spelling in doc, spelling
    assert "multiplier_17500_20000" not in doc
    assert "``largest_operators``" not in doc  # the band never carried it


def test_no_segment_label_carries_an_accusatory_word(population_analysis) -> None:
    """PRD §8 / research §8.  The library may say "sybil" in its own name — it
    is a general sybil-analysis toolkit and lives outside every scanned
    surface — but a preset's ``label`` and ``detail`` are what a consumer
    renders, so they are written in pattern language and the adapter never has
    to translate an accusation into a description."""
    preset, ds, res = population_analysis
    segs = segments(ds, res, preset)
    strings = [s.label for s in segs.bands] + [s.detail for s in segs.bands]
    strings += [op.label for op in segs.operators]
    strings += [r for op in segs.operators for r in op.reasons]
    assert strings
    for text in strings:
        lowered = text.lower()
        for word in FORBIDDEN_LABEL_WORDS:
            assert word not in lowered, f"{word!r} in {text!r}"


# ===========================================================================
# WP2.2 — the cleaned list
# ===========================================================================


def test_the_clean_list_removes_the_flagged_and_ranks_the_survivors(
    population_analysis,
) -> None:
    preset, ds, res = population_analysis
    clean = clean_list(ds, res, preset)

    assert clean.total_points == res.total_points
    assert clean.flagged_points == res.flagged_points
    assert clean.clean_points == res.clean_points
    assert clean.clean_points == clean.total_points - clean.flagged_points

    assert clean.contributors_total == len(res.analyzed)
    assert clean.flagged_contributors == len(res.flagged)
    assert clean.clean_contributors == clean.contributors_total - clean.flagged_contributors
    assert len(clean.entries) == clean.clean_contributors

    ranks = [e.clean_rank for e in clean.entries]
    assert ranks == list(range(1, len(ranks) + 1))  # dense, 1-based
    points = [e.points for e in clean.entries]
    assert points == sorted(points, reverse=True)
    assert sum(points) == clean.clean_points


def test_a_flagged_member_has_no_clean_rank_and_a_survivor_has_a_dense_one(
    population_analysis,
) -> None:
    preset, ds, res = population_analysis
    clean = clean_list(ds, res, preset)
    flagged = sorted(res.flagged)[0]
    survivor = clean.entries[0].address

    assert clean.clean_rank(flagged) is None
    assert clean.clean_rank(survivor) == 1
    assert clean.clean_rank(survivor.upper()) == 1  # lookup is case-insensitive


def test_the_three_standings_are_never_collapsed(population_analysis) -> None:
    """CLAUDE.md's representable-negative rule, applied to a rank.

    ``clean_rank`` answers ``None`` for a removed member **and** for an address
    nobody analyzed, which is exactly the row that reads confident and green
    through an outage.  ``standing`` keeps the three apart, so a consumer can
    render "removed from the list" differently from "not on the list at all".
    """
    preset, ds, res = population_analysis
    clean = clean_list(ds, res, preset)
    stranger = "0x" + "ff" * 20
    assert clean.standing(clean.entries[0].address) == "clean"
    assert clean.standing(sorted(res.flagged)[0]) == "removed"
    assert clean.standing(stranger) == "unknown"
    assert clean.clean_rank(stranger) is None


def test_the_clean_list_carries_wei_not_ether(population_analysis) -> None:
    """Wei-native to the edge: nothing in the library divides by 1e18, because
    a float cannot hold 1 363 396 200 000 000 000 000 wei and the presentation
    boundary is the only place that should be losing digits."""
    preset, ds, res = population_analysis
    clean = clean_list(ds, res, preset)
    top = clean.entries[0]
    weights = _final_weight(ds)
    credits: dict[str, int] = {}
    for dep in ds.deposits:
        credits[dep.contributor] = credits.get(dep.contributor, 0) + dep.credited_delta_wei
    assert isinstance(top.credit_wei, int) and isinstance(top.weight_wei, int)
    assert top.weight_wei == weights[top.address]
    assert top.credit_wei == credits[top.address]
    assert top.points == preset.points(top.weight_wei)


def test_the_clean_list_on_an_empty_result_keeps_everybody(labeled_ds) -> None:
    """Nothing linked is not the same as nothing analyzed: with an empty
    :class:`DetectResult` every analyzed contributor is a survivor, and the
    clean total equals the population total.

    Note what this pins and what it does not.  ``empty`` here comes from a
    **real** ``detect`` run, which always populates ``analyzed`` — so this is
    "no *clusters* keeps everybody", not "no *analyzed* keeps everybody".  The
    three tests below cover the second, which used to answer "clean" for
    wallets nobody had looked at (review finding #4).
    """
    preset = a_preset()
    empty = detect(labeled_ds, dataclasses.replace(preset.detect_config(), min_size=10**6))
    assert empty.clusters == []
    assert empty.analyzed  # a real run always says who it looked at
    clean = clean_list(labeled_ds, empty, preset)
    assert clean.flagged_contributors == 0
    assert clean.clean_points == clean.total_points
    assert len(clean.entries) == len(empty.analyzed)


def _unanalyzed_result(total_points: int = 0) -> DetectResult:
    """A hand-built result that looked at nobody — ``analyzed`` stays empty.

    Exactly what a caller constructs when it has counters but no run: the
    class documents the empty default as "the safe default is never a
    confident clean", and these tests hold the preset to that.
    """
    return DetectResult([], total_points, 0, total_points)


def test_a_result_that_analyzed_nobody_produces_no_survivors() -> None:
    """**Review finding #4.**  ``analyzed = set(res.analyzed) or set(weights)``
    rewrote *analyzed nobody* into *everybody analyzed and clean*.

    The population is not the analysis.  A result with an empty ``analyzed``
    has no survivors to rank, because nothing was looked at — and
    ``contributors_total`` is the size of what was analyzed, so it is ``0``
    rather than the number of wallets that happen to be in the dataset.
    """
    preset = a_preset()
    ds = _mini_dataset([(1, 0), (2, 0), (3, 1), (4, 1), (5, 1)])
    res = _unanalyzed_result()

    clean = clean_list(ds, res, preset)

    assert clean.entries == ()
    assert clean.clean_contributors == 0
    assert clean.contributors_total == 0


def test_standing_of_an_unanalyzed_address_is_unknown_not_clean() -> None:
    """``CleanList.standing``'s own docstring promises three words that are
    never collapsed; the fallback made the third one unreachable.

    A wallet ``res.wallet()`` answers ``None`` for — never analyzed — must not
    come back "clean" from the object whose whole job is telling clean,
    removed and unknown apart.  That is CLAUDE.md's confident-negative hazard
    in the one place it is least survivable.
    """
    preset = a_preset()
    ds = _mini_dataset([(1, 0), (2, 0), (3, 1), (4, 1), (5, 1)])
    addr = "0x" + f"{1:040x}"
    res = _unanalyzed_result()

    assert res.wallet(addr) is None  # the detector says: never looked at
    clean = clean_list(ds, res, preset)
    assert clean.standing(addr) == "unknown"
    assert clean.clean_rank(addr) is None


def test_a_hand_built_result_never_makes_the_clean_list_speak_for_the_unanalyzed() -> None:
    """The general form: ``standing`` and ``wallet`` agree, address by address.

    Asserted on a **partially** analyzed result as well as an empty one,
    because that is the shape a resumable sweep produces — a cursor that has
    walked two of five wallets — and it is where "everybody clean" would be
    most plausible and most wrong.
    """
    preset = a_preset()
    ds = _mini_dataset([(1, 0), (2, 0), (3, 1), (4, 1), (5, 1)])
    addrs = [f"0x{i:040x}" for i in range(1, 6)]

    for analyzed in (frozenset(), frozenset(addrs[:2])):
        res = _unanalyzed_result()
        res.analyzed = analyzed
        clean = clean_list(ds, res, preset)

        for addr in addrs:
            looked_at = res.wallet(addr) is not None
            assert (clean.standing(addr) == "unknown") is not looked_at, addr
        assert clean.contributors_total == len(analyzed)
        assert {e.address for e in clean.entries} == set(analyzed)
