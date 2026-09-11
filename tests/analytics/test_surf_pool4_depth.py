"""WP1 -- the pure depth ladder.

Every assertion here is either an identity derived from the price move itself
or a property the formula does not assert about itself. Nothing in this file
restates the implementation.
"""

import ast
import math
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import surf_pool4_depth as d

L = 1e18

#: The tick at which price doubles: log(2) / log(1.0001) == 6931.82, so 6932.
#: Derived here rather than imported, so a change to the module's base cannot
#: silently agree with itself.
#:
#: The plan's draft of this test said 13863 and called it a doubling. It is
#: not -- 1.0001 ** 13863 == 3.9997, a *quadrupling*; 13863 is the doubling
#: tick of sqrt(price), not of price. Reported as a finding, not propagated.
DOUBLING_TICK = 6932


def test_eth_between_matches_a_value_derived_outside_the_formula():
    """Independent oracle, not a restatement of the implementation.

    1.0001 ** 6932 == 2.0 (to 4 dp), so over that range the price doubles and
    sqrt(price) goes 1 -> sqrt(2). A full-range position pays out exactly
    ``1 - 1/sqrt(2)`` of its notional in currency0 across a doubling. That
    identity comes from the price move, not from the code under test.
    """
    assert 1.0001**DOUBLING_TICK == pytest.approx(2.0, rel=1e-4)
    assert d.sqrt_ratio(DOUBLING_TICK) == pytest.approx(math.sqrt(2.0), rel=1e-4)
    expected = 1.0 - 1.0 / math.sqrt(2.0)  # 0.2928932...
    got = d.eth_between(L, 0, DOUBLING_TICK)
    assert got == pytest.approx(expected, rel=1e-4)


def test_eth_between_is_additive_across_a_split_range():
    """A property the formula does not assert about itself: walking a range in
    two hops must pay exactly what walking it in one hop pays."""
    whole = d.eth_between(L, 1000, 9000)
    halves = d.eth_between(L, 1000, 5000) + d.eth_between(L, 5000, 9000)
    assert whole == pytest.approx(halves, rel=1e-12)


def test_eth_between_is_zero_when_the_range_does_not_open():
    assert d.eth_between(L, 5000, 5000) == 0.0
    assert d.eth_between(L, 5000, 4000) == 0.0


def test_a_price_drop_raises_the_tick_because_tick_up_is_imd_cheaper():
    assert d.tick_for_price_drop(68196, 50.0) > 68196
    # halving the price doubles IMD-per-ETH: +6932 ticks
    assert d.tick_for_price_drop(0, 50.0) == pytest.approx(DOUBLING_TICK, abs=2)


def test_a_zero_or_total_drop_is_a_no_op_rather_than_a_nonsense_tick():
    """0% has nowhere to move to and 100% has no finite tick; both return the
    tick they were given rather than an infinity or a ValueError."""
    assert d.tick_for_price_drop(68196, 0.0) == 68196
    assert d.tick_for_price_drop(68196, 100.0) == 68196


def test_more_liquidity_pays_more_and_less_pays_less():
    """Both directions. A one-directional check cannot see a sign error."""
    base = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
    )
    richer = d.depth_rows(
        tick=68196,
        position_liquidity=2 * 6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
    )
    poorer = d.depth_rows(
        tick=68196,
        position_liquidity=0.5 * 6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
    )
    for b, r, p in zip(base, richer, poorer):
        assert r["eth_paid"] > b["eth_paid"] > p["eth_paid"]


def test_the_ladder_is_cumulative_and_band_use_never_exceeds_one():
    rows = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
    )
    assert [r["move_pct"] for r in rows] == list(d.DEPTH_MOVES)
    assert all(
        rows[i]["eth_paid"] < rows[i + 1]["eth_paid"] for i in range(len(rows) - 1)
    )
    assert all(0.0 <= r["band_used_pct"] <= 100.0 for r in rows)


def test_band_use_rises_strictly_with_the_move():
    """A ladder that reported the same band use at -1% and -50% would look
    plausible and be meaningless. Each deeper rung must consume strictly more
    of the band than the one above it."""
    rows = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
    )
    used = [r["band_used_pct"] for r in rows]
    assert all(used[i] < used[i + 1] for i in range(len(used) - 1)), used


def test_a_band_the_move_never_reaches_contributes_nothing():
    """A band parked far above spot is untouched by a shallow move: its use is
    a true 0.0 and the rung's ETH is the full-range position alone. Without
    this, an implementation that always charged the band would still pass the
    monotonicity check above.

    A band starting at tick 70000 is out of reach of the -1%, -5% and -10%
    rungs (which reach 68296, 68709 and 69250) and is reached only by -20%
    and -50%.
    """
    far = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=70000,
        band_liquidity=8.0e20,
    )
    none_at_all = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=None,
        band_liquidity=None,
    )
    assert [r["band_used_pct"] for r in far[:3]] == [0.0, 0.0, 0.0]
    assert all(r["band_used_pct"] > 0.0 for r in far[3:])
    for shallow, bandless in zip(far[:3], none_at_all[:3]):
        assert shallow["eth_paid"] == pytest.approx(bandless["eth_paid"], rel=1e-12)
    assert far[-1]["eth_paid"] > none_at_all[-1]["eth_paid"]


def test_a_missing_input_returns_none_and_never_a_zero_ladder():
    """A failed read is None, never 0. A ladder of zeros would render as
    'this pool bids nothing', which is a confident wrong answer."""
    assert (
        d.depth_rows(
            tick=None,
            position_liquidity=6.9e20,
            band_lower_tick=68280,
            band_liquidity=8.0e20,
        )
        is None
    )
    assert (
        d.depth_rows(
            tick=68196,
            position_liquidity=None,
            band_lower_tick=68280,
            band_liquidity=8.0e20,
        )
        is None
    )


def test_no_band_still_gives_a_ladder_from_the_full_range_position():
    """No backstop deployed is a real state, not a failure: the full-range
    position still bids. band_used_pct is 0.0, not None."""
    rows = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=None,
        band_liquidity=None,
    )
    assert rows is not None
    assert all(r["band_used_pct"] == 0.0 for r in rows)
    assert all(r["eth_paid"] > 0.0 for r in rows)


def test_depth_rows_refuses_positional_arguments():
    """Two ticks and two liquidities side by side is the signature where a
    positional swap is silent. Keyword-only makes it a TypeError."""
    with pytest.raises(TypeError):
        d.depth_rows(68196, 6.948e20, 68280, 8.0e20)  # type: ignore[misc]


def test_the_module_is_pure_stdlib_and_imports_nothing_from_the_app():
    """It joins the surf widget-contract allowlist in WP9, whose recursive
    purity walk will check this too. Assert it here at the source so the
    module cannot grow an import between now and then."""
    src = Path(d.__file__).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import is by definition in-app
                names.add("<relative>")
            elif node.module:
                names.add(node.module.split(".")[0])
    assert names <= {"__future__", "math"}, names
