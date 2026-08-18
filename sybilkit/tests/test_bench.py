"""WP2.4 — the labeled-benchmark regression gate.

The ChainCred pattern (research §7): a committed labeled list plus **two**
bars, because either one alone is gameable.

* A **precision floor** alone is met perfectly by a heuristic that flags
  nothing at all — no false positives when there are no positives.
* A **median-gap ceiling** alone is met by a heuristic that flags everybody.

Together they are the thing that made heuristic drift visible on ChainCred, and
they are what a later signal change has to argue with before it lands.

Offline by construction: the gate reads ``labeled_subset.json`` and nothing
else.  ``bench.py`` itself imports no transport and takes no URL — it is core,
and the core is stdlib-only.
"""

from __future__ import annotations

import statistics

import pytest

from sybilkit import DetectConfig
from sybilkit.bench import BenchResult, run_benchmark
from sybilkit.curator import CuratorPreset
from tests.sybilkit_fixtures import labeled_subset

#: The gate.  Both numbers sit clear of the measured values with room for real
#: movement and no room for a collapse: measured 2026-08-18 on the committed
#: subset at the default config — precision **1.0**, median gap **1.5**.
PRECISION_FLOOR = 0.95
MEDIAN_GAP_CEILING = 4.0


@pytest.fixture(scope="module")
def bench() -> BenchResult:
    return run_benchmark(labeled_subset())


def test_the_gate_runs_over_the_sixteen_audited_operators_and_the_controls(
    bench: BenchResult,
) -> None:
    assert bench.operators_audited == 16
    assert bench.controls == 60
    assert bench.members == 160
    assert len(bench.operators) == 16
    assert sum(op.sampled for op in bench.operators) == 160


def test_precision_clears_the_floor_and_no_control_is_flagged(
    bench: BenchResult,
) -> None:
    """False positives are the failure mode, not a rounding error: Hop rejected
    any report with "a non-negligible chance of eliminating legitimate users".
    The 60 controls include six adversarial ones whose fingerprints match a
    real operator's."""
    assert bench.false_positives == 0
    assert bench.controls_flagged == 0
    assert bench.precision == 1.0
    assert bench.precision >= PRECISION_FLOOR


def test_the_median_gap_clears_the_ceiling(bench: BenchResult) -> None:
    """The gap is per audited operator: how many of its ten sampled members the
    detector failed to put in one cluster together.  A median, not a mean, so a
    single operator the sample cannot express (the 0.05 and 0.1 crowds, which
    live on the full population and not in a 220-address slice) does not drag
    the bar."""
    assert bench.median_gap == statistics.median(op.gap for op in bench.operators)
    assert bench.median_gap <= MEDIAN_GAP_CEILING
    assert bench.median_gap == 1.5


def test_passes_is_the_two_bars_together(bench: BenchResult) -> None:
    assert bench.passes(PRECISION_FLOOR, MEDIAN_GAP_CEILING) is True
    assert bench.passes(1.01, MEDIAN_GAP_CEILING) is False          # floor unmet
    assert bench.passes(PRECISION_FLOOR, bench.median_gap - 0.1) is False


def test_a_heuristic_tuned_to_zero_recall_fails_the_gate() -> None:
    """The reason the ceiling exists at all.

    Two ways to reach a heuristic that convicts nobody, and neither may pass:
    an impossible size gate, and — the realistic one — a tier-A-only run, where
    the corroborating families cannot fire and the ≥2-family gate quite
    correctly refuses almost everything.  Both keep a **perfect** precision and
    both are useless, and only the median-gap ceiling says so.
    """
    silent = run_benchmark(labeled_subset(), config=DetectConfig(min_size=10**6))
    assert silent.true_positives == 0
    assert silent.precision == 0.0  # nothing flagged is not perfect precision
    assert silent.median_gap == 10.0
    assert silent.passes(PRECISION_FLOOR, MEDIAN_GAP_CEILING) is False

    blind = run_benchmark(labeled_subset(), tiers="a")
    assert blind.recall < 0.1
    assert blind.median_gap == 10.0
    assert blind.passes(PRECISION_FLOOR, MEDIAN_GAP_CEILING) is False


def test_the_gate_runs_under_the_curator_preset_too() -> None:
    """Ruling R13 changes the answer, and the gate has to survive the change.

    With the protocol minimum threaded in, the 0.05 crowd's identicalness stops
    being evidence, so recall falls and the median gap doubles — and both bars
    still hold.  If a future calibration cannot clear them here, that is the
    conversation this gate exists to force.
    """
    preset = CuratorPreset(points_per_eth=1000, min_deposit_wei=5 * 10**16)
    res = run_benchmark(labeled_subset(), config=preset.detect_config())
    assert res.precision == 1.0
    assert res.median_gap == 3.0
    assert res.recall < 0.7
    assert res.passes(PRECISION_FLOOR, MEDIAN_GAP_CEILING) is True


def test_the_gate_reports_where_each_operator_was_found(bench: BenchResult) -> None:
    by_name = {op.name: op for op in bench.operators}
    assert by_name["amt_0.45_h3"].found == 10
    assert by_name["amt_0.45_h3"].gap == 0
    assert by_name["amt_0.45_h3"].cluster_id is not None
    # The two 2.067 waves are 18 hours apart with zero member overlap and are
    # united only by the identical ODD amount — the shape a byte-identical rule
    # with a window would miss entirely.
    assert by_name["amt_2.067_h13"].cluster_id == by_name["amt_2.067_h18"].cluster_id
    # And the two shapes the 220-address sample genuinely cannot express: the
    # 0.05 and 0.1 crowds are found on the full population, not in a slice.
    assert by_name["amt_0.05_h7"].found == 0
    assert by_name["amt_0.1_h17"].found == 0


def test_the_gate_never_opens_a_socket_and_takes_no_url() -> None:
    """Structural: ``bench.py`` is core.  It reads the committed fixture the
    caller hands it and has no idea an endpoint exists."""
    import ast
    from pathlib import Path

    import sybilkit.bench as bench_mod

    src = Path(bench_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    assert not ({"httpx", "requests", "socket", "asyncio", "urllib"} & roots), roots
    assert "http" not in src


def test_a_result_is_reproducible(bench: BenchResult) -> None:
    """The core is pure, so the gate is a measurement and not a sample."""
    again = run_benchmark(labeled_subset())
    assert (again.precision, again.recall, again.median_gap) == (
        bench.precision,
        bench.recall,
        bench.median_gap,
    )
    assert [op.gap for op in again.operators] == [op.gap for op in bench.operators]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "TODO(cluster-level target, PRD §3.5): every one of the 16 audited "
        "operators recovered with >= 9 of its 10 sampled members in ONE "
        "cluster.  Measured 2026-08-18: 9 of 16 reach it.  The seven that do "
        "not are the two minimum-amount crowds (which live on the full "
        "population, not in a 220-address slice), the 14.0 metronome (whose "
        "hour window splits the h5/h7 samples off), and the four index-run "
        "batches (whose same-block near rule sheds out-of-block samples).  "
        "STRICT: this test FAILS the day detection reaches the target, which "
        "is the signal to delete the xfail and keep the assertion."
    ),
)
def test_every_audited_operator_is_recovered_almost_whole(bench: BenchResult) -> None:
    missed = [op.name for op in bench.operators if op.gap > 1]
    assert missed == [], missed
