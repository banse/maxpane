"""The points curve — ``isqrt(weight_wei) * points_per_eth // 10**9``.

Owned by WP1 (controller ruling R1).  Every value below is wei-exact and
asserted with ``==``; ``pytest.approx`` on a wei value is a review failure.

Three named tests below are the designated victims of the three mandated
curve mutations, one each:

* ``//`` → ``round(...)``            reddens ``test_the_curve_floors_never_rounds``
* ``isqrt`` → ``int(math.sqrt(...))``  reddens ``test_float_sqrt_is_off_by_one_on_a_large_weight``
* divide before multiply              reddens ``test_a_sub_eth_weight_keeps_its_points``
"""

from __future__ import annotations

import math

from sybilkit.curve import curve_points


def test_the_documented_anchor_values() -> None:
    """The WP1.6 brief's own three anchors, integer arguments throughout."""
    assert curve_points(10**18, 1000) == 1000
    assert curve_points(1000 * 10**18, 1000) == 31_622
    assert curve_points(0, 1000) == 0


def test_the_curve_floors_never_rounds() -> None:
    """1000 ETH-weight sits at sqrt = 31 622.776...; the protocol floors it to
    31 622, and ``round`` would say 31 623.  Designated victim of curve
    mutation (a)."""
    assert curve_points(1000 * 10**18, 1000) == 31_622
    # a second point whose fraction is below .5, so a round() that happens to
    # floor one case cannot pass both
    assert curve_points(1_010 * 10**18, 1000) == 31_780  # sqrt = 31780.497...


def test_float_sqrt_is_off_by_one_on_a_large_weight() -> None:
    """W = (31 623·10⁶)² − 1 is ~1000.014 ETH of weight.  ``float(W)`` rounds
    up to the perfect square, so ``int(math.sqrt(W))`` returns 31 623 000 000
    where ``isqrt`` returns 31 622 999 999 — and the points cross a floor
    boundary: 31 623 against the true 31 622.  Designated victim of curve
    mutation (b)."""
    weight = (31_623 * 10**6) ** 2 - 1
    assert math.isqrt(weight) == 31_622_999_999  # the fixture's own arithmetic
    assert curve_points(weight, 1000) == 31_622


def test_a_sub_eth_weight_keeps_its_points() -> None:
    """A weight one wei under 1 ETH has isqrt 999 999 999 — just under 10⁹.
    Dividing before multiplying floors that to 0 and the wallet loses all 999
    points.  Designated victim of curve mutation (c)."""
    assert curve_points(10**18 - 1, 1000) == 999
    assert curve_points(10**14, 1000) == 10  # 0.0001 ETH-weight: still not 0


def test_points_per_eth_is_a_live_parameter_not_a_memory() -> None:
    """The rate scales the result linearly before the floor — proof that the
    implementation multiplies by the parameter rather than a remembered
    1000."""
    weight = 821_025_000_000_000_000  # a real 0.45-deposit weight
    assert curve_points(weight, 1000) == 906
    assert curve_points(weight, 2000) == 1812
    assert curve_points(weight, 1) == 0  # floors: 906104516... // 10**9


def test_the_curve_agrees_with_the_committed_population_total() -> None:
    """Folding the committed population's final weights through the curve at
    the swept rate reproduces the audited total exactly — the wei-exact fold
    the whole-population smoke test pins again at detect() level."""
    from tests.sybilkit_fixtures import load

    last: dict[str, tuple[tuple[int, int], int]] = {}
    for row in load("deposits.json.gz"):
        key = (row["block"], row["log_index"])
        addr = row["contributor"].lower()
        if addr not in last or key > last[addr][0]:
            last[addr] = (key, row["new_weight_wei"])
    total = sum(curve_points(w, 1000) for _, w in last.values())
    assert total == 26_585_740
