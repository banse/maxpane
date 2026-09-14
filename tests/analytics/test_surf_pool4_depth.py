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
        band_state=d.BAND_DEPLOYED,
    )
    richer = d.depth_rows(
        tick=68196,
        position_liquidity=2 * 6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
        band_state=d.BAND_DEPLOYED,
    )
    poorer = d.depth_rows(
        tick=68196,
        position_liquidity=0.5 * 6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
        band_state=d.BAND_DEPLOYED,
    )
    for b, r, p in zip(base, richer, poorer):
        assert r["eth_paid"] > b["eth_paid"] > p["eth_paid"]


def test_the_ladder_is_cumulative_and_band_use_never_exceeds_one():
    rows = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
        band_state=d.BAND_DEPLOYED,
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
        band_state=d.BAND_DEPLOYED,
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
        band_state=d.BAND_DEPLOYED,
    )
    none_at_all = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=None,
        band_liquidity=None,
        band_state=d.BAND_NONE,
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
            band_state=d.BAND_DEPLOYED,
        )
        is None
    )
    assert (
        d.depth_rows(
            tick=68196,
            position_liquidity=None,
            band_lower_tick=68280,
            band_liquidity=8.0e20,
            band_state=d.BAND_DEPLOYED,
        )
        is None
    )


def test_no_band_still_gives_a_ladder_from_the_full_range_position():
    """No backstop deployed is a real state, not a failure: the full-range
    position still bids. band_used_pct is 0.0, not None.

    ``band_state="none"`` is what makes this claim, and since WP11 it is the
    *only* thing that can: the same call with the state unread returns ``None``
    on every rung, which is the test below.
    """
    rows = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=None,
        band_liquidity=None,
        band_state=d.BAND_NONE,
    )
    assert rows is not None
    assert all(r["band_used_pct"] == 0.0 for r in rows)
    assert all(r["eth_paid"] > 0.0 for r in rows)


# ===========================================================================
# WP11 -- an unread band is not an absent one (PRD 6.5, AMENDED 2026-09-11)
# ===========================================================================


def test_an_unread_band_does_not_render_as_an_unused_one():
    """The defect this task exists for. Measured before the fix: these two
    returned equal lists and the rendered column was byte-identical."""
    common = dict(tick=68181, position_liquidity=6.9047e20, band_lower_tick=68340)
    unread = d.depth_rows(**common, band_liquidity=None, band_state=None)
    absent = d.depth_rows(**common, band_liquidity=0, band_state="none")

    assert [r["band_used_pct"] for r in unread] == [None] * len(unread)
    assert [r["band_used_pct"] for r in absent] == [0.0] * len(absent)
    assert unread != absent

    # the full-range leg survives an unread band -- the position is still readable
    assert all(r["eth_paid"] > 0.0 for r in unread)


def test_a_deployed_band_whose_amount_is_unreadable_is_also_unread():
    """The state word alone is not enough, and this is the half a reading of
    the spec could miss.

    ``pool4_backstop_state == "deployed"`` says a band exists; it does not say
    the band's liquidity came back. If the amount is missing under that word we
    are in the same position as with no word at all -- we cannot compute a share
    of the band -- so the honest answer is ``None`` and not the ``0.0`` the old
    ``has_band`` fold produced. Without this branch the WP11 registration probe
    for ``pool4_backstop_liquidity`` could not pair: its zero and its failed read
    would render alike again, one state word further in.
    """
    rows = d.depth_rows(
        tick=68181,
        position_liquidity=6.9047e20,
        band_lower_tick=68340,
        band_liquidity=None,
        band_state=d.BAND_DEPLOYED,
    )
    assert [r["band_used_pct"] for r in rows] == [None] * len(rows)
    assert all(r["eth_paid"] > 0.0 for r in rows)


def test_a_deployed_band_of_exactly_zero_is_a_representable_zero():
    """The other side of the pair above, and the one the probe needs.

    A band the chain reports as holding nothing has a true ``0.0`` consumed --
    we looked, and none of it went anywhere. It must not borrow the unread
    answer any more than the unread case may borrow this one.
    """
    rows = d.depth_rows(
        tick=68181,
        position_liquidity=6.9047e20,
        band_lower_tick=68340,
        band_liquidity=0,
        band_state=d.BAND_DEPLOYED,
    )
    assert [r["band_used_pct"] for r in rows] == [0.0] * len(rows)


def test_an_unrecognised_state_word_reads_as_unknown_and_never_as_deployed():
    """An allowlist, not a pass-through -- ``_pool4.network_word``'s rule.

    A fourth state word is a build that has learned something this module has
    not, and the failure mode to refuse is the quiet one: falling through to the
    ``deployed`` arithmetic and painting a share of a band whose state nobody
    here understands.
    """
    rows = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
        band_state="retired",
    )
    assert [r["band_used_pct"] for r in rows] == [None] * len(rows)


def test_the_state_default_is_the_fail_safe_end_and_not_a_confident_zero():
    """A caller that forgets the keyword gets ``unknown``, never ``0.0%``.

    The argument has a default at all because ``tests/data/
    test_surf_pool4_oracle.py`` -- a file this task does not own -- calls
    ``depth_rows`` for its ``eth_paid`` cross-check and has no state to pass. A
    default of ``"deployed"`` would have kept that green too, and would have
    restored the exact defect for every future caller who forgets.
    """
    forgot = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
    )
    assert [r["band_used_pct"] for r in forgot] == [None] * len(forgot)
    # ...and the ETH leg is untouched by the default, which is what keeps the
    # oracle cross-check measuring the arithmetic rather than this branch.
    deployed = d.depth_rows(
        tick=68196,
        position_liquidity=6.948e20,
        band_lower_tick=68280,
        band_liquidity=8.0e20,
        band_state=d.BAND_DEPLOYED,
    )
    assert [r["eth_paid"] for r in forgot] == [r["eth_paid"] for r in deployed]


def test_the_state_vocabulary_agrees_with_the_contract_in_both_directions():
    """Restated, not imported -- so the two copies have to be made to agree.

    ``analytics/`` is certified stdlib-only by the widget-contract purity walk
    and may not import ``data/``. ``_GAME_CYCLE``'s redundancy-plus-agreement
    shape applies: a third backstop state reddens this instead of silently
    landing in the unknown branch on one side and the deployed branch on the
    other.
    """
    from maxpane_dashboard.data.surf_models import POOL4_BACKSTOP_STATES

    assert d.BAND_STATES == POOL4_BACKSTOP_STATES
    assert (d.BAND_DEPLOYED, d.BAND_NONE) == POOL4_BACKSTOP_STATES


# ===========================================================================
# band_reached -- from the ticks, never from the share (2026-09-14)
# ===========================================================================

#: The live mainnet reading that prompted the key: the band opens at 69300,
#: 29.33% under a spot of 65858, after a rally with no rebalance. The
#: independent reader (``pool4hook.ts depth``) agrees rung for rung:
#: 0 / 0 / 0 / 0 / 16%.
LIVE_TICK = 65858
LIVE_BAND_LOWER = 69300
BAND_L = 7.468554033980641e20


def test_the_existing_row_keys_are_unchanged_and_band_reached_joins_them():
    rows = d.depth_rows(
        tick=LIVE_TICK,
        position_liquidity=6.9047e20,
        band_lower_tick=LIVE_BAND_LOWER,
        band_liquidity=BAND_L,
        band_state=d.BAND_DEPLOYED,
    )
    for row in rows:
        assert set(row) == {"move_pct", "eth_paid", "band_used_pct", "band_reached"}


def test_rungs_short_of_a_live_shaped_band_are_not_reached_and_the_deep_one_is():
    """The measured state, asserted on both halves of the row.

    The share on the short rungs stays a true ``0.0`` -- the math did not
    change, only what the widget may say about it -- and -50% (target 72789)
    is the one rung past 69300.
    """
    rows = d.depth_rows(
        tick=LIVE_TICK,
        position_liquidity=6.9047e20,
        band_lower_tick=LIVE_BAND_LOWER,
        band_liquidity=BAND_L,
        band_state=d.BAND_DEPLOYED,
    )
    assert [r["band_reached"] for r in rows] == [False, False, False, False, True]
    assert [r["band_used_pct"] for r in rows[:4]] == [0.0] * 4
    assert rows[4]["band_used_pct"] > 0.0


def test_a_sliver_past_the_band_is_reached_even_though_its_share_rounds_to_zero():
    """**The trap.** A share that paints ``0.0%`` is not evidence of no reach.

    The -1% rung's target is put exactly one tick past the band's lower tick,
    so the band leg is real and tiny. ``band_reached`` must say ``True`` there;
    an implementation that derived it from ``band_used_pct`` rounding to zero
    would say ``False`` and paint ``not reached`` over a band the move entered.
    """
    target = d.tick_for_price_drop(68181, 1.0)
    rows = d.depth_rows(
        tick=68181,
        position_liquidity=6.9047e20,
        band_lower_tick=target - 1,
        band_liquidity=BAND_L,
        band_state=d.BAND_DEPLOYED,
    )
    first = rows[0]
    assert first["move_pct"] == 1
    assert first["band_reached"] is True
    assert 0.0 < first["band_used_pct"]
    assert f"{first['band_used_pct']:.1f}" == "0.0"


def test_a_band_holding_nothing_is_still_reached_where_the_ticks_say_so():
    """The exact-zero twin of the sliver: a deployed band the chain reports as
    empty gives ``band_used_pct == 0.0`` on *every* rung, so equality with zero
    cannot decide reach either. Only the -1% rung (target 68282) is short of
    68340.
    """
    rows = d.depth_rows(
        tick=68181,
        position_liquidity=6.9047e20,
        band_lower_tick=68340,
        band_liquidity=0,
        band_state=d.BAND_DEPLOYED,
    )
    assert [r["band_used_pct"] for r in rows] == [0.0] * len(rows)
    assert [r["band_reached"] for r in rows] == [False, True, True, True, True]


def test_a_target_landing_exactly_on_the_lower_tick_has_not_entered_the_band():
    """The boundary uses the band leg's own predicate, ``target > lower``:
    at equality ``eth_between`` pays nothing, so "reached" there would name a
    band the move did not take a wei from."""
    target = d.tick_for_price_drop(68181, 1.0)
    rows = d.depth_rows(
        tick=68181,
        position_liquidity=6.9047e20,
        band_lower_tick=target,
        band_liquidity=BAND_L,
        band_state=d.BAND_DEPLOYED,
    )
    assert rows[0]["band_reached"] is False
    assert rows[0]["band_used_pct"] == 0.0


@pytest.mark.parametrize(
    "state,lower,liquidity",
    [
        (None, LIVE_BAND_LOWER, BAND_L),          # unread state word
        (d.BAND_DEPLOYED, LIVE_BAND_LOWER, None),  # deployed, amount unread
        (d.BAND_NONE, None, None),                 # no band at all
        ("retired", LIVE_BAND_LOWER, BAND_L),      # unrecognised state word
    ],
    ids=["unread-state", "deployed-amount-unread", "no-band", "unknown-word"],
)
def test_band_reached_has_no_answer_without_a_read_deployed_band(state, lower, liquidity):
    """``None``, never ``False``, in every case where the ticks alone would
    have given an answer the rest of the row cannot back. The unread cases
    carry a real lower tick on purpose: from the ticks, four rungs are short
    of it, and ``False`` there would let ``not reached`` out-rank ``unknown``."""
    rows = d.depth_rows(
        tick=LIVE_TICK,
        position_liquidity=6.9047e20,
        band_lower_tick=lower,
        band_liquidity=liquidity,
        band_state=state,
    )
    assert [r["band_reached"] for r in rows] == [None] * len(rows)


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
