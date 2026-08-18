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
from sybilkit.curator import CuratorPreset, curve_points
from tests.conftest import build_labeled_dataset, build_population_dataset

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
