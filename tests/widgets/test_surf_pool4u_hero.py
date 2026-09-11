"""WP5 -- the `4` POOL4 MARKET body's own hero: IMD PRICE / DOWNSIDE BID / STAKING.

Every layout assertion here goes against **composited output**
(``screen._compositor.render_strips()``), joining segments per *row* first and
then rows by newline. Joining every segment with a newline instead splits one
painted row into several apparent lines the moment a row carries two styles --
and this row carries three boxes side by side, each with a dim label, a bold
value and a dim subtitle, so a per-segment join would turn one hero row into a
dozen fictional lines and every assertion below would be measuring the fiction.

No shared compositing helper exists in ``tests/widgets/``
---------------------------------------------------------
The plan's WP5 snippet imports ``composite`` from ``tests.widgets.
surf_compositing`` and calls it "existing helper". **There is no such module.**
What exists is a per-file ``_lines`` in ``tests/widgets/test_surf_pool4_left.py``
(and its siblings), each private to its own file. :func:`_lines` below is that
same helper, restated here rather than hoisted: a third package (WP9) is writing
its own pool4u test files in this tree right now, and two agents creating one
shared module is a collision, not convergence. Filed as a follow-up -- the hoist
is worth doing once the wave has landed.

What this file exists to pin above everything else
--------------------------------------------------
**The backstop card's three states are three different sentences.** ``none
deployed`` and ``unavailable`` answer different questions -- one says we looked
and there is no band, the other says we could not look -- and rendering them
identically is the curator rail bug verbatim, where a dead group's ``-- unknown``
and a genuine ``none yet`` both read confident and green straight through an
outage.
"""

from __future__ import annotations

import pytest
from textual.app import App

from maxpane_dashboard.data.surf_models import (
    POOL4_BACKSTOP_STATES,
    POOL4_VENUE_WORDS,
    SURF_KEYS,
)
from maxpane_dashboard.widgets.surf import pool4u_hero as hero_mod
from maxpane_dashboard.widgets.surf.pool4u_hero import (
    BACKSTOP_STATES,
    CARD_IDS,
    NO_BAND,
    NO_VENUE_EDGE,
    STAKING_WINDOW,
    TITLE_BID,
    TITLE_PRICE,
    TITLE_STAKING,
    UNAVAILABLE,
    VENUE_WORDS,
    SurfPool4UserHero,
    band_distance_pct,
    fmt_price_usd,
)

# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


async def _lines(payload: dict, size=(120, 10)) -> list[str]:
    """Composited output, **one string per painted terminal row**.

    Segments are joined per strip first -- see the module docstring for what
    the other join would measure instead.
    """

    class _A(App):
        def compose(self):
            yield SurfPool4UserHero()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfPool4UserHero)
        widget.update_data(**payload)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        return ["".join(seg.text for seg in strip).rstrip() for strip in strips]


async def _text(payload: dict, size=(120, 10)) -> str:
    return "\n".join(await _lines(payload, size))


#: A healthy price card, so a test about a *different* card cannot be satisfied
#: (or broken) by this one's unavailable state.
PRICE_OK = {
    "pool4_price_usd": 2.845,
    "pool4_venue_gap_pct": 1.46,
    "pool4_cheaper_venue": None,
}

#: Likewise for STAKING.
STAKING_OK = {
    "pool4_trailing_return_pct": 4.01,
    "pool4_vault_assets": 1_359_676.0,
    "pool4_staker_count": 66,
}


# ---------------------------------------------------------------------------
# The three-state card -- the reason this widget exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_backstop_card_tells_no_band_apart_from_no_read() -> None:
    """Three states, not two. PRD 5.2.

    ``none deployed`` and ``unavailable`` are DIFFERENT answers: one says we
    looked and there is no band, the other says we could not look. Rendering
    them identically is the curator rail bug -- a real negative with no
    representable value reads confident and green straight through an outage.

    **The other two cards are given real values in all three payloads**, which
    is a deviation from the plan's snippet and the thing that makes the
    assertions bite. That snippet handed the widget ``{"pool4_backstop_state":
    "none"}`` alone and then asserted ``"unavailable" not in absent`` -- but
    with no price and no staking data those two cards correctly render
    ``unavailable``, so the assertion could only ever fail, and fail for a
    reason that has nothing to do with the backstop. Feeding the neighbours
    leaves the backstop card as the only thing in the row that can produce
    either word.
    """
    deployed = await _text({
        **PRICE_OK, **STAKING_OK,
        "pool4_backstop_state": "deployed",
        "pool4_backstop_eth": 24.419,
        # 84 ticks under spot -> 0.84%. Derived, not handed over: there is no
        # `pool4_backstop_distance_pct` key (see the widget's docstring).
        "pool4_current_tick": 68196,
        "pool4_backstop_lower_tick": 68280,
    })
    assert "24.4" in deployed and "0.84" in deployed
    assert UNAVAILABLE not in deployed
    assert NO_BAND not in deployed

    absent = await _text({**PRICE_OK, **STAKING_OK, "pool4_backstop_state": "none"})
    assert NO_BAND in absent
    assert UNAVAILABLE not in absent

    unread = await _text({**PRICE_OK, **STAKING_OK, "pool4_backstop_state": None})
    assert UNAVAILABLE in unread
    assert NO_BAND not in unread


@pytest.mark.asyncio
async def test_the_backstop_card_branches_on_state_and_not_on_the_eth_amount() -> None:
    """A deployed band whose ETH failed to read is still a deployed band.

    The plausible shortcut -- branch on ``pool4_backstop_eth is None`` -- makes
    an unread amount indistinguishable from a band that genuinely is not
    deployed, and would tell the reader there is no bid under them at all. The
    card shows the dash and keeps the state.
    """
    out = await _text({
        **PRICE_OK, **STAKING_OK,
        "pool4_backstop_state": "deployed",
        "pool4_backstop_eth": None,
        "pool4_current_tick": 68196,
        "pool4_backstop_lower_tick": 68280,
    })
    assert "-- ETH" in out
    assert NO_BAND not in out
    assert UNAVAILABLE not in out
    assert "0.84" in out


@pytest.mark.asyncio
async def test_an_unread_tick_costs_the_distance_and_not_the_card() -> None:
    """The two halves of the card fail apart.

    Folding an unread tick into the whole card's unavailable state would
    overstate the outage: the ETH standing in the band was read and is the
    number a reader came for.
    """
    out = await _text({
        **PRICE_OK, **STAKING_OK,
        "pool4_backstop_state": "deployed",
        "pool4_backstop_eth": 24.419,
        "pool4_current_tick": None,
        "pool4_backstop_lower_tick": 68280,
    })
    assert "24.4" in out
    assert "distance unread" in out
    assert UNAVAILABLE not in out


# ---------------------------------------------------------------------------
# The row as a whole
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_card_shows_unavailable_rather_than_going_blank() -> None:
    """MEDI-38. A card skipped when its value is missing keeps whatever it last
    showed -- or 'Loading...' forever if the first poll was the one that
    failed -- and a reader cannot tell stale from live.
    """
    out = await _text({})
    assert out.count(UNAVAILABLE) == 3
    assert "Loading" not in out


@pytest.mark.asyncio
async def test_a_poll_that_loses_one_value_does_not_leave_the_old_one_on_screen() -> None:
    """Every card is written on every call, never skipped.

    This is the failure MEDI-38 names and it is invisible to a one-shot render
    test: the first payload paints, the second drops a key, and a widget that
    returns early leaves the first payload's number under a title bar claiming
    the data is seconds old.
    """

    class _A(App):
        def compose(self):
            yield SurfPool4UserHero()

    async with _A().run_test(size=(120, 10)) as pilot:
        widget = pilot.app.query_one(SurfPool4UserHero)
        widget.update_data(**PRICE_OK, **STAKING_OK)
        await pilot.pause()
        first = "\n".join(
            "".join(seg.text for seg in strip)
            for strip in pilot.app.screen._compositor.render_strips()
        )
        assert "2.845" in first

        widget.update_data(**STAKING_OK)
        await pilot.pause()
        second = "\n".join(
            "".join(seg.text for seg in strip)
            for strip in pilot.app.screen._compositor.render_strips()
        )
        assert "2.845" not in second
        assert UNAVAILABLE in second


@pytest.mark.asyncio
async def test_all_three_labels_are_painted() -> None:
    """The row is three cards, and a test that never sees a label would pass
    just as well against one card rendered three times."""
    out = await _text({**PRICE_OK, **STAKING_OK})
    for label in (TITLE_PRICE, TITLE_BID, TITLE_STAKING):
        assert label in out, label


# ---------------------------------------------------------------------------
# STAKING
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_staking_card_never_says_bare_apr() -> None:
    """PRD 8.1. The window is part of the number: this figure is lumpy by
    construction and a bare rate over-promises it."""
    out = await _text(STAKING_OK)
    assert "trailing" in out and "7d" in out
    assert "APR" not in out
    assert "apr" not in out.lower()


@pytest.mark.asyncio
async def test_a_quiet_week_renders_zero_rather_than_unavailable() -> None:
    """``0.0`` is a real answer -- the drip genuinely delivered nothing -- and
    must not collapse into the word reserved for a read that failed."""
    out = await _text({"pool4_trailing_return_pct": 0.0})
    assert f"0.0% {STAKING_WINDOW}" in out
    # The other two cards are unavailable; this card is not one of them.
    assert out.count(UNAVAILABLE) == 2


# ---------------------------------------------------------------------------
# IMD PRICE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_price_card_says_nothing_about_venues_below_the_fee_floor() -> None:
    """cheaper_venue is None when the gap cannot be arbitraged. The card must
    stay silent, not fall through to naming a venue anyway."""
    out = await _text({
        "pool4_price_usd": 2.845,
        "pool4_venue_gap_pct": 1.46,
        "pool4_cheaper_venue": None,
    })
    assert "2.845" in out
    assert "reference" not in out.lower()
    assert NO_VENUE_EDGE in out


@pytest.mark.asyncio
async def test_an_unread_gap_and_a_gap_below_the_fees_are_different_lines() -> None:
    """The pair that must not merge.

    ``cheaper_venue is None`` means both "we could not read the gap" and "the
    gap does not clear the fees" if the card reads only that key. It reads the
    gap too, so an outage cannot paint the confident "no edge" sentence.
    """
    within_fees = await _text({
        "pool4_price_usd": 2.845,
        "pool4_venue_gap_pct": 1.46,
        "pool4_cheaper_venue": None,
    })
    unread = await _text({
        "pool4_price_usd": 2.845,
        "pool4_venue_gap_pct": None,
        "pool4_cheaper_venue": None,
    })
    assert NO_VENUE_EDGE in within_fees
    assert NO_VENUE_EDGE not in unread
    assert "venue gap --" in unread


@pytest.mark.asyncio
async def test_a_cleared_gap_names_its_venue_in_both_directions() -> None:
    """One direction cannot see a sign or a lookup error."""
    ref = await _text({
        "pool4_price_usd": 2.845,
        "pool4_venue_gap_pct": 3.1,
        "pool4_cheaper_venue": "reference",
    })
    assert "cheaper on reference" in ref and "3.10%" in ref

    here = await _text({
        "pool4_price_usd": 2.845,
        "pool4_venue_gap_pct": -3.1,
        "pool4_cheaper_venue": "here",
    })
    assert "cheaper here" in here and "3.10%" in here
    assert "reference" not in here.lower()


# ---------------------------------------------------------------------------
# Pure helpers and the restated vocabularies
# ---------------------------------------------------------------------------


def test_the_restated_vocabularies_agree_with_the_contract_in_both_directions() -> None:
    """A widget may not import ``data/``, so the two closed vocabularies it
    branches on are restated -- and pinned, in **both** directions.

    One direction alone is not enough: a member added to the contract and not
    here would fall through the widget's ``else`` and be painted as an outage,
    and a member here that the contract dropped would keep a dead branch alive
    for the next reader to trust. ``_pool4.NETWORK_WORDS`` is the established
    shape and this is the same one.
    """
    assert set(BACKSTOP_STATES) == set(POOL4_BACKSTOP_STATES)
    assert set(VENUE_WORDS) == set(POOL4_VENUE_WORDS)


def test_every_update_data_kwarg_is_a_frozen_contract_key() -> None:
    """The screen splats the manager's flat dict, so a kwarg that is not a key
    is a silent no-op -- and ``test_surf_widget_contract.py`` will fail on it
    the day WP7 exports this class. Checked here too, because that sweep reads
    ``widgets/surf/__init__.__all__`` and this widget is deliberately not in it
    yet.
    """
    import inspect

    names = [
        name
        for name, param in inspect.signature(
            SurfPool4UserHero.update_data
        ).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    ]
    assert names, "a signature with no kwargs would make this vacuous"
    unknown = [name for name in names if name not in SURF_KEYS]
    assert not unknown, unknown


def test_the_band_distance_reproduces_the_plans_own_figure() -> None:
    """Derived from the ticks, checked against a number this code did not
    produce: the plan's WP5 snippet passed ``0.84`` alongside the WP1 fixture's
    ``tick=68196`` / ``band_lower_tick=68280``, and this is the same pair.
    """
    assert band_distance_pct(68196, 68280) == pytest.approx(0.8365, abs=0.002)


def test_the_band_distance_is_a_price_fall_and_therefore_a_tick_rise() -> None:
    """ETH is currency0, so tick up means IMD is cheaper. A band whose lower
    tick is ABOVE spot sits BELOW spot in price -- the single most plausible
    sign error in this file, and one that would render a band under the reader
    as a band over them.
    """
    assert band_distance_pct(68196, 68400) > band_distance_pct(68196, 68280) > 0.0


def test_the_band_distance_is_zero_at_the_money_and_none_when_unread() -> None:
    """``0.0`` is representable -- the band opens at spot -- and ``None`` means
    a tick could not be read. A failed read is never a zero."""
    assert band_distance_pct(68196, 68196) == 0.0
    assert band_distance_pct(68196, 68000) == 0.0
    assert band_distance_pct(None, 68280) is None
    assert band_distance_pct(68196, None) is None


def test_the_price_is_shown_finely_enough_to_corroborate_the_venue_clause() -> None:
    """Three decimals, not two.

    At cent precision a 0.2% gap on a $2.85 token is invisible and a 1.5% one
    is two ticks of the last digit, so the card would carry a venue clause the
    number beside it could not support. ``--`` on an unread price, never
    ``$0.00``, which is a claim.
    """
    assert fmt_price_usd(2.845) == "$2.845"
    assert fmt_price_usd(None) == "--"
    assert fmt_price_usd(0.0) == "$0.000"


def test_the_module_names_a_card_for_every_id_it_composes() -> None:
    """Three ids, three labels, one row. A drifted pair would leave a card
    permanently on ``Loading...`` because nothing ever queried its id."""
    assert len(CARD_IDS) == len({*CARD_IDS}) == 3
    assert hero_mod.TITLE_PRICE and hero_mod.TITLE_BID and hero_mod.TITLE_STAKING
