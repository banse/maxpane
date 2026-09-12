"""WP9 -- the `4` body's SIGNALS panel: four states in one label column.

Every layout assertion here goes against **composited output**
(``screen._compositor.render_strips()``), joining segments per *row* first and
then rows by newline. Joining every segment with a newline instead splits one
painted row into several apparent lines the moment a row carries two styles --
and every row on this panel carries two (a dim label and a coloured value), so
a per-segment join would double the panel's apparent height and every
assertion below would be measuring the fiction.

:func:`_lines` delegates to ``tests.widgets.surf_compositing.
composite_lines``, the one shared copy. It was written by hand in five sibling
files while this body was being built and hoisted as carry-over C5 once the
wave landed.

What this file exists to pin above everything else
--------------------------------------------------
1. **The panel never gives advice** (PRD §8.4). Bakery's signals template
   ends on ``→ Recommendation: BUY``; on a market panel in a strictly
   read-only tool that would be the first thing on screen that reads as a
   trade. This was aimed at the state-summary line until 2026-09-12, when
   that line was dropped; the constraint was never about one line, so the
   check is aimed at the whole panel and at five payload states. It greps the
   **composited body**, because a bare-word grep over this module's source is
   the known-fake shape in this repo's taxonomy: it passes while the reader
   sees something else, and it fails on a docstring that merely *documents*
   the forbidden word.
2. **``burning`` tells three states apart, and all three are asserted.** A
   checker that compares only the ``None`` word is a logged defect here: it
   cannot distinguish "the cap binds" from "we could not read the cap", and
   the second is what an outage looks like.
3. **Unread and "read, and there is nothing" are different sentences**, on
   every row that has both. That is the curator rail bug, where a dead group's
   ``-- unknown`` and a genuine ``none yet`` both read confident and green.
"""

from __future__ import annotations

import inspect

import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.analytics import surf_pool4_depth
from maxpane_dashboard.data.surf_models import (
    POOL4_BACKSTOP_STATES,
    POOL4_VENUE_WORDS,
    SURF_KEYS,
)
from maxpane_dashboard.widgets.surf import _pool4
from maxpane_dashboard.widgets.surf._rowfit import pad
from maxpane_dashboard.widgets.surf import pool4u_hero as hero_mod
from maxpane_dashboard.widgets.surf import pool4u_signals as sig_mod
from maxpane_dashboard.widgets.surf.pool4u_signals import (
    BURNING_OFF,
    BURNING_ON,
    COMPACT_WIDTH,
    DEEP_BACKLOG_DAYS,
    FULL_WIDTH,
    LABEL_COLS,
    NO_BACKLOG,
    NO_BAND,
    NO_EDGE,
    ROW_LABELS,
    TITLE,
    UNAVAILABLE_LINE,
    UNKNOWN,
    VENUE_WORDS,
    SurfPool4USignals,
    backlog_cell,
    backstop_cell,
    burning_state,
    venue_cell,
)

from tests.widgets.surf_compositing import composite_lines

# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


async def _lines(payload: dict, size=(120, 14)) -> list[str]:
    """Composited output, **one string per painted terminal row**.

    The join is ``surf_compositing.composite_lines``' -- segments per
    strip, then rows by newline in :func:`_text`. See that module for
    what the other join would measure instead.
    """
    return await composite_lines(SurfPool4USignals, size, **payload)


async def _text(payload: dict, size=(120, 14)) -> str:
    return "\n".join(await _lines(payload, size))


#: A fully-readable payload, so a test about one row cannot be satisfied (or
#: broken) by another row's unavailable state.
HEALTHY = {
    "pool4_cap_headroom": 0.0,
    "pool4_cheaper_venue": "reference",
    "pool4_venue_gap_pct": 3.1,
    "pool4_reference_pool_tick": 68180,
    "pool4_current_tick": 68196,
    "pool4_backstop_state": "deployed",
    "pool4_backstop_lower_tick": 68280,
    "pool4_backstop_eth": 24.51,
    "pool4_backlog_days": 0.0,
    "pool4_network": "MAINNET",
    "pool4_as_of_hhmm": "14:07",
}


# ===========================================================================
# The two contracts WP9 was written for
# ===========================================================================


@pytest.mark.asyncio
async def test_burning_tells_all_three_states_apart() -> None:
    """on / off / unknown, asserted as three.

    A checker that compares only the ``None`` word is a logged defect in this
    repo -- assert all three or this test is sampling.

    The state is derived from ``pool4_cap_headroom`` rather than taken as a
    word: the plan's snippet passed ``pool4_burning``, and **there is no such
    key** (WP0 froze nine fast-tier names and that is not one of them). PRD §7
    names ``pool4_cap_headroom`` as the read behind this signal, and §7.4 asks
    that ``False`` -- headroom above zero, genuinely off -- stay separable from
    ``None``, which is what a failed read looks like. That separation is the
    whole subject of this test.
    """
    on = await _text({**HEALTHY, "pool4_cap_headroom": 0.0})
    assert BURNING_ON in on and "headroom 0" in on

    off = await _text({**HEALTHY, "pool4_cap_headroom": 1240.0})
    assert BURNING_OFF in off and "1,240" in off

    unknown = await _text({**HEALTHY, "pool4_cap_headroom": None})
    assert BURNING_ON not in unknown and BURNING_OFF not in unknown
    assert UNKNOWN in unknown

    # ...and the three really are three different paintings, not one word
    # appearing in three payloads that happen to share the rest of the panel.
    assert on != off != unknown != on


@pytest.mark.asyncio
async def test_the_panel_never_gives_advice() -> None:
    """PRD §8.4.

    Bakery's template ends with a recommendation. That is fine for a cookie
    game and is something else on a financial market: this repo ships a
    strictly read-only tool, and a bottom-line "buy" would be the first thing
    on screen that reads as advice.

    **This was ``test_the_summary_line_never_gives_advice`` until 2026-09-12**,
    when the state-summary line it was named for was dropped (see the module
    docstring). The constraint did not move with the line: §8.4 is about
    anything on this panel reading as advice, not about one sentence, so the
    check is aimed at the whole composited panel -- which is where it should
    always have been pointed and is strictly the stronger claim. The
    parametrised sweep below runs the same words over five payload states.

    Grep the **composited body**, not the source. A bare-word source grep is a
    known-fake shape here: it reddens on a docstring explaining the rule and
    stays green on a word that reaches a pixel through a payload value.

    The positive half is what stops this passing on a blank panel: the four
    rows have to be *there* for their absence of advice to mean anything.
    """
    out = await _text(HEALTHY)
    for forbidden in ("buy", "sell", "should", "recommend"):
        assert forbidden not in out.lower(), forbidden
    for label in ROW_LABELS:
        assert label in out, label
    assert BURNING_ON in out


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        HEALTHY,
        {**HEALTHY, "pool4_cap_headroom": 1240.0, "pool4_cheaper_venue": "here"},
        {**HEALTHY, "pool4_backstop_state": "none", "pool4_backlog_days": 4.2},
        {**HEALTHY, "pool4_cheaper_venue": None, "pool4_cap_headroom": None},
        {},
    ],
    ids=["healthy", "off-here", "no-band-deep", "no-edge-unknown", "empty"],
)
async def test_no_reachable_state_of_this_panel_gives_advice(payload) -> None:
    """The forbidden words are forbidden in **every** state, not one.

    One payload proves one painting. Each branch below reaches a different
    combination of row words, and the unavailable state reaches none of them
    -- which is where a "nothing to say, so here is what to do" line would
    most plausibly be written by someone later.
    """
    out = (await _text(payload)).lower()
    for forbidden in ("buy", "sell", "should", "recommend"):
        assert forbidden not in out, (forbidden, payload)


# ===========================================================================
# The four rows
# ===========================================================================


@pytest.mark.asyncio
async def test_the_panel_paints_exactly_the_four_rows_in_order() -> None:
    """PRD §6.3's four rows, and the reading order it sets out.

    Asserted on composited output against the row *labels*, so a row silently
    dropped by a fitting pass fails here rather than being noticed on a
    reader's screen.
    """
    lines = await _lines(HEALTHY)
    positions = []
    for label in ROW_LABELS:
        hits = [
            i for i, line in enumerate(lines)
            if line.strip().startswith(pad(label, LABEL_COLS))
        ]
        assert hits, label
        positions.append(hits[0])
    assert positions == sorted(positions), positions


def test_burning_is_a_word_from_a_closed_set_and_never_a_bool() -> None:
    """``False`` and ``None`` are different answers and a bool cannot hold
    both. PRD §7.4.
    """
    assert burning_state(None) is None
    assert burning_state(0.0) == BURNING_ON
    assert burning_state(-5.0) == BURNING_ON       # inventory above the cap
    assert burning_state(1.0) == BURNING_OFF
    assert burning_state("nonsense") is None


def test_the_venue_vocabulary_agrees_with_the_producers() -> None:
    """Redundancy plus an agreement test, in **both directions**.

    ``VENUE_WORDS`` restates ``surf_models.POOL4_VENUE_WORDS`` because a widget
    may not import ``data/``. Deriving one from the other would make this
    compare a constant against itself and it could never fail again; a third
    venue word now reddens here rather than falling through this module's
    ``else`` and rendering as an unread gap.
    """
    assert set(VENUE_WORDS) == set(POOL4_VENUE_WORDS)
    assert len(VENUE_WORDS) == len(POOL4_VENUE_WORDS)


@pytest.mark.asyncio
async def test_an_unread_gap_and_a_gap_below_fees_are_different_sentences() -> None:
    """PRD §8.3, and the curator rail bug one row down.

    ``pool4_cheaper_venue is None`` means two different things depending on the
    gap beside it: *the gap does not clear the two pools' fees summed* (a real
    answer -- there is nothing to arbitrage) and *the gap was not read* (an
    outage). Rendering both as silence merges them.

    Neither spelling names a venue, which is the half §8.3 actually
    constrains: the panel may say an edge does not exist, never which side it
    would have been on.
    """
    below_fees = await _text(
        {**HEALTHY, "pool4_cheaper_venue": None, "pool4_venue_gap_pct": 0.2}
    )
    unread = await _text(
        {**HEALTHY, "pool4_cheaper_venue": None, "pool4_venue_gap_pct": None}
    )
    assert NO_EDGE in below_fees
    assert NO_EDGE not in unread
    assert UNKNOWN in unread
    for word in POOL4_VENUE_WORDS:
        assert word.upper() not in below_fees


def test_the_two_no_edge_spellings_make_the_same_claim() -> None:
    """The hero card and this row say the same thing at two widths.

    They are two spellings on purpose -- the card has a subtitle line to fill,
    this is a value cell whose label already reads ``cheaper pool`` -- and the
    property that must hold of both is the one §8.3 sets: **no venue word**.
    A spelling that named a side would be advice wearing a state's clothes.
    """
    assert NO_EDGE != hero_mod.NO_VENUE_EDGE          # two widths, not one copy
    for phrase in (NO_EDGE, hero_mod.NO_VENUE_EDGE):
        assert "edge" in phrase
        for word in POOL4_VENUE_WORDS:
            assert word not in phrase.lower(), (phrase, word)


def test_the_venue_row_renders_the_magnitude_and_not_the_payloads_own_sign() -> None:
    """``pool4_venue_gap_pct`` is signed ``+ = IMD dearer here``.

    Printing that sign beside a venue word is a double negative: ``REFERENCE
    +3.10%`` reads as *reference is dearer* while the word says the opposite.
    The rendered ``−`` is fixed and means "that much cheaper on the named
    venue", so the same magnitude renders identically whichever side it is on.
    """
    there, _ = venue_cell("reference", 3.1, None, None)
    here, _ = venue_cell("here", -3.1, None, None)
    assert there == "REFERENCE −3.10%"
    assert here == "HERE −3.10%"


@pytest.mark.asyncio
async def test_the_venue_row_publishes_the_two_ticks_its_verdict_came_from() -> None:
    """PRD §8.3 records the gap derivation as an **unresolved** contradiction
    between two implementations.

    Prevention was not available; disclosure was. The two ticks the verdict was
    derived from ride on the same row at the full tier, so a reader can check
    the verdict rather than take it -- THE SPLIT's drift line, one body over.
    """
    out = await _text(HEALTHY)
    assert "68196/68180" in out

    # An unread reference tick drops the tail rather than printing half of it:
    # one tick beside a verdict about two is worse than none.
    half = await _text({**HEALTHY, "pool4_reference_pool_tick": None})
    assert "68196/" not in half
    assert "REFERENCE" in half          # the verdict itself survives


def test_the_backstop_row_branches_on_the_state_word_and_nothing_else() -> None:
    """Three states. PRD §5.2's rule, one panel down from the hero card.

    Branching on ``backstop_eth is None`` instead would make an unread amount
    indistinguishable from a band that genuinely is not deployed -- and a
    deployed band whose ETH failed to read would claim there is no bid under
    the reader at all, which is the most expensive wrong answer this panel can
    give.
    """
    deployed, _ = backstop_cell("deployed", 68196, 68280, 24.51)
    assert "0.84% under" in deployed and "24.51 ETH" in deployed

    # deployed, but the ETH did not read: the distance still stands.
    partial, _ = backstop_cell("deployed", 68196, 68280, None)
    assert "0.84% under" in partial and "-- ETH" in partial

    assert backstop_cell("none", None, None, None)[0] == NO_BAND
    assert backstop_cell(None, 68196, 68280, 24.51)[0] == UNKNOWN
    # A vocabulary member this build has not been taught is not a band.
    assert backstop_cell("retired", 68196, 68280, 24.51)[0] == UNKNOWN


def test_the_no_band_spelling_is_the_heros_spelling() -> None:
    """One state, one wording, across the two panels that render it.

    Restated rather than imported (a widget importing a sibling widget's
    constant is a coupling, not a hoist), so this is the agreement test that
    redundancy owes -- it fails in both directions the day either is reworded.
    """
    assert NO_BAND == hero_mod.NO_BAND
    assert "none" in POOL4_BACKSTOP_STATES


def test_the_backstop_distance_comes_from_the_one_shared_implementation() -> None:
    """Carry-over C1: one source for the tick->percent conversion.

    Identity, not a value match. Two copies agreeing today is exactly the state
    the hero and this panel were in before the hoist, and it says nothing about
    tomorrow: the failure this guards is two panels on one screen printing
    different numbers for one fact.
    """
    assert sig_mod.band_distance_pct is surf_pool4_depth.band_distance_pct
    assert hero_mod.band_distance_pct is surf_pool4_depth.band_distance_pct


def test_the_backlog_row_separates_zero_from_unread() -> None:
    """``0`` is a representable answer -- the dripper holds nothing -- and
    reaches :data:`NO_BACKLOG`, never :data:`UNKNOWN`.

    The row exists for one reason: to say whether STAKING's trailing return
    understates. ``unknown`` there means "we cannot tell you whether it does",
    which is a different and weaker statement from "it does not".
    """
    assert backlog_cell(0.0)[0] == NO_BACKLOG
    assert backlog_cell(None)[0] == UNKNOWN
    assert backlog_cell(0.4)[0] == "0.4d"
    deep, style = backlog_cell(3.2)
    assert deep.startswith("deep · 3.2d") and style == "yellow"
    # The threshold is a boundary, and a boundary test is worth its line.
    assert backlog_cell(DEEP_BACKLOG_DAYS)[0].startswith("deep")
    assert not backlog_cell(DEEP_BACKLOG_DAYS - 0.01)[0].startswith("deep")


# ===========================================================================
# The shape of the panel
# ===========================================================================


@pytest.mark.asyncio
async def test_the_panel_is_four_labelled_rows_and_a_clock_and_nothing_else()\
        -> None:
    """The state-summary line is gone, and this is what stops it drifting back.

    It was dropped on 2026-09-12 for two reasons the module docstring records:
    it restated three of the four rows above it, and it was the one line on
    the panel that did not sit in the label column -- on a body whose whole
    screenshot-review complaint was ragged alignment.

    Asserted as a **line count and a shape**, not as the absence of a
    sentence: a check for one particular restated phrase would go green the
    moment someone reworded it. Every content row either begins with one of
    :data:`ROW_LABELS` or is the ``as of`` marker, and there are exactly as
    many of them as there are labels plus that marker.
    """
    lines = [ln.strip() for ln in await _lines(HEALTHY) if ln.strip()]
    assert lines[0].startswith(TITLE)
    body = lines[1:]
    assert len(body) == len(ROW_LABELS) + 1, body
    for line, label in zip(body, ROW_LABELS):
        assert line.startswith(label), (line, label)
    assert body[-1].startswith("as of")


# ===========================================================================
# Degradation, safety and width
# ===========================================================================


@pytest.mark.asyncio
async def test_a_wholly_unread_panel_says_so_once() -> None:
    """Not four repetitions of ``unknown``: one sentence.

    Four rows each saying the same word is a panel that looks broken rather
    than a panel reporting an outage, and it costs three rows on a body whose
    height budget nobody has measured on a real laptop yet.
    """
    out = await _text({"pool4_network": "SEPOLIA"})
    assert UNAVAILABLE_LINE in out
    assert out.count(UNKNOWN) == 0
    assert TITLE in out


@pytest.mark.asyncio
async def test_a_read_band_alone_is_not_an_unread_panel() -> None:
    """``none deployed`` with every number beside it unread is an **answer**.

    The blank test above must not swallow it: a state word is a read, and
    collapsing it into the whole-panel outage is the same two-into-one this
    file keeps finding.
    """
    out = await _text({"pool4_backstop_state": "none", "pool4_network": "MAINNET"})
    assert UNAVAILABLE_LINE not in out
    assert NO_BAND in out


@pytest.mark.asyncio
async def test_a_hostile_state_word_is_escaped_rather_than_parsed() -> None:
    """``pool4_cheaper_venue`` and ``pool4_backstop_state`` are third-party
    strings by the time they reach here -- a hand-edited cache file is
    third-party input too.

    Textual defers ``Content.from_markup`` into the message pump, so an
    unescaped ``[/x]`` raises *outside* this widget's ``try`` and takes the app
    down. Surviving the render at all is most of this assertion.
    """
    out = await _text(
        {
            **HEALTHY,
            "pool4_cheaper_venue": "[/x]reference",
            "pool4_backstop_state": "[bold red]deployed",
            "pool4_as_of_hhmm": "[/]14:07",
        }
    )
    assert TITLE in out
    assert "[/x]" not in out and "[bold red]" not in out


@pytest.mark.asyncio
async def test_the_title_carries_the_network_word_from_the_shared_helper() -> None:
    """One implementation of the network word, and the panel's claim about the
    provenance of its own numbers.

    Compared against ``_pool4.panel_title``'s own output rather than against a
    literal, so a change to the separator cannot leave this green while five
    titles disagree.
    """
    out = await _text({**HEALTHY, "pool4_network": "SEPOLIA"})
    assert _pool4.panel_title(TITLE, "SEPOLIA") in out

    unknown = await _text({**HEALTHY, "pool4_network": "BASE"})
    assert _pool4.panel_title(TITLE, "BASE") in unknown
    assert "BASE" not in unknown

    # ``MAINNET`` is the one word this body leaves unsaid (2026-09-12; see
    # ``_pool4.QUIET_NETWORK``). Asserted beside the two that still print, so
    # an implementation that dropped the word unconditionally -- which would
    # let a reader take Sepolia numbers for real ones -- fails here.
    mainnet = await _lines({**HEALTHY, "pool4_network": "MAINNET"})
    title_row = next(ln for ln in mainnet if TITLE in ln)
    assert title_row.strip() == TITLE
    assert "MAINNET" not in "\n".join(mainnet)


@pytest.mark.asyncio
async def test_the_narrow_tier_sheds_detail_and_never_a_signal() -> None:
    """A signals panel that drops a signal has not got narrower; it has started
    lying by omission, and the row it drops is as likely as any to be the one
    that mattered.

    What goes is the tick tail, the backstop's ETH and the backlog's clause.
    What stays is four labels and four states.
    """
    narrow = await _text(HEALTHY, size=(COMPACT_WIDTH + 6, 14))
    for label in ROW_LABELS:
        assert label in narrow, label
    assert "68196/68180" not in narrow
    assert "24.51 ETH" not in narrow
    assert "0.84% under" in narrow
    assert _pool4.WIDEN_HINT in narrow or _pool4.GLYPH_HINT in narrow


@pytest.mark.asyncio
async def test_the_width_pins_are_what_the_rows_actually_paint() -> None:
    """The pin fails in **both** directions.

    ``>=`` would pass for a pin set far too low and ``<=`` for one set far too
    high, and either leaves the widen marker pointing at a width nothing is
    laid out to. Measured off composited output at a width wide enough that
    nothing is clipped, over a payload built to hit each column's widest cell.
    """
    wide = {
        **HEALTHY,
        "pool4_cap_headroom": 999_999.0,
        "pool4_venue_gap_pct": 99.99,
        "pool4_backstop_eth": 999.99,
        "pool4_backlog_days": 999.9,
        "pool4_current_tick": 887272,
        "pool4_reference_pool_tick": 887272,
    }
    lines = await _lines(wide, size=(200, 14))
    # Matched on the **padded** label, not the bare one. The state-summary
    # line that used to begin ``burning off ...`` is gone, but the padding is
    # what makes this a match on a *row* rather than on any line that happens
    # to start with a label word -- and the next line added under these four
    # should have to answer for itself here rather than be swept in.
    rows = [
        line for line in lines
        if any(line.strip().startswith(pad(label, LABEL_COLS))
               for label in ROW_LABELS)
    ]
    assert len(rows) == len(ROW_LABELS), rows
    # ``> Static``'s own padding costs a column on the left of every row.
    widest = max(cell_len(line.strip()) for line in rows)
    assert widest == FULL_WIDTH, (widest, FULL_WIDTH, rows)
    assert COMPACT_WIDTH < FULL_WIDTH


def test_the_label_column_is_wide_enough_for_every_label() -> None:
    """Measured in **terminal cells**, never ``len()``.

    A label column sized by character count under-pads the moment a label is
    reworded with anything wide, and the value cell then starts one column
    left of every other row with nothing to say so.
    """
    assert max(cell_len(label) for label in ROW_LABELS) < LABEL_COLS


# ===========================================================================
# The contract
# ===========================================================================


def test_every_update_data_kwarg_is_a_frozen_contract_key() -> None:
    """Contract §0.1: no short kwargs, no invented keys.

    The launchpad trio's ``as_of_hhmm`` elision is a carve-out for one name on
    one body and no pool4 panel takes it -- one kwarg name answering for two
    different contract keys is how a payload key silently reaches nothing.
    """
    params = [
        name
        for name, param in inspect.signature(
            SurfPool4USignals.update_data
        ).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    ]
    assert params, "the signature is empty; this test would prove nothing"
    for name in params:
        assert name in SURF_KEYS, name
        assert name.startswith("pool4_"), name


@pytest.mark.asyncio
async def test_no_args_and_all_none_render_without_raising() -> None:
    """The outage path is a path, and it is the one nobody exercises by hand."""
    class _A(App):
        def compose(self):
            yield SurfPool4USignals()

    async with _A().run_test(size=(120, 14)) as pilot:
        widget = pilot.app.query_one(SurfPool4USignals)
        widget.update_data()
        await pilot.pause()
        widget.update_data(
            **{
                name: None
                for name, param in inspect.signature(
                    widget.update_data
                ).parameters.items()
                if param.kind is not param.VAR_KEYWORD and name != "self"
            }
        )
        await pilot.pause()
