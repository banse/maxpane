"""WP9 -- the `4` body's IF IMD FALLS panel: the hook's bid ladder.

Every layout assertion here goes against **composited output**
(``screen._compositor.render_strips()``), joining segments per *row* first and
then rows by newline. A ``DataTable`` paints each cell as its own segment, so
joining every segment with a newline would turn one three-column row into three
apparent lines and every assertion below would be measuring the fiction -- and
in particular the forbidden-word check, whose whole point is to read what the
reader reads.

There is no shared compositing helper in ``tests/widgets/``: the plan's
``tests.widgets.surf_compositing`` does not exist, and every sibling file
carries its own private ``_lines``. :func:`_lines` is that same helper,
restated rather than hoisted while two packages are writing in this tree.

What this file exists to pin above everything else
--------------------------------------------------
1. **The ladder never promises protection** (PRD §8.2). These are quotes from
   the position *as it stands now*; a ``rebalance()`` closes the backstop band
   and redeploys it from just above spot, so every number here can move the
   moment a keeper acts. *guaranteed*, *protected*, *safe* and *floor* are
   forbidden, in the **composited body** -- a source grep is the known-fake
   shape here, green on a word that reaches a pixel through a payload value
   and red on a docstring that merely explains the rule.
2. **An unreadable position says so instead of painting an empty table.** An
   empty table under a live title bar is the picture of a hook that bids
   nothing, which is a confident wrong answer to a question we could not
   answer at all.
3. **No band deployed is not an unreadable position.** The full-range position
   still bids, so the ladder is real and ``band used`` is a true ``0.0%``.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.analytics import surf_pool4_depth
from maxpane_dashboard.analytics.surf_pool4_depth import DEPTH_MOVES
from maxpane_dashboard.data.surf_models import SURF_KEYS
from maxpane_dashboard.widgets.surf import _pool4
from maxpane_dashboard.widgets.surf import pool4u_depth as depth_mod
from maxpane_dashboard.widgets.surf.pool4u_depth import (
    CAPTION,
    COMPACT_WIDTH,
    FULL_WIDTH,
    HEADERS,
    TABLE_ID,
    TITLE,
    UNAVAILABLE_LINE,
    SurfPool4UDepth,
    ladder_cells,
)

#: PRD §8.2's forbidden list. ``floor`` is on it in the *protective* sense and
#: is refused outright rather than contextually: this panel has no line that
#: needs the word, THE RATCHET one body over owns the hook's actual deployment
#: floor, and a rule a renderer has to reason about is a rule that erodes.
FORBIDDEN = ("guaranteed", "protected", "protection", "safe", "floor")

# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


async def _lines(payload: dict, size=(120, 16)) -> list[str]:
    """Composited output, **one string per painted terminal row**."""

    class _A(App):
        def compose(self):
            yield SurfPool4UDepth()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfPool4UDepth)
        widget.update_data(**payload)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        return ["".join(seg.text for seg in strip).rstrip() for strip in strips]


async def _text(payload: dict, size=(120, 16)) -> str:
    return "\n".join(await _lines(payload, size))


#: The committed oracle capture's own inputs -- block 25955365, the values
#: ``tests/fixtures/surf/pool4/oracle_25955365.json`` was taken at. Used here
#: so the rows this panel paints are rows an independent implementation (the
#: protocol author's own TypeScript) has been asked the same question about.
ORACLE = {
    "pool4_current_tick": 68181,
    "pool4_position_liquidity": 690471276437502400000,
    "pool4_backstop_lower_tick": 68340,
    "pool4_backstop_liquidity": 746855403398064100000,
    "pool4_network": "MAINNET",
    "pool4_as_of_hhmm": "14:07",
}


# ===========================================================================
# The contract WP9 was written for
# ===========================================================================


@pytest.mark.asyncio
async def test_the_ladder_never_promises_protection() -> None:
    """PRD §8.2.

    These are quotes from the position as it stands; a rebalance relocates the
    band. THE RATCHET's ``observed``-not-``guaranteed`` rule, one panel over.
    """
    out = await _text(ORACLE)
    for forbidden in FORBIDDEN:
        assert forbidden not in out.lower(), forbidden
    assert "now" in out.lower()          # the title says what it is a quote of


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        ORACLE,
        {**ORACLE, "pool4_backstop_lower_tick": None,
         "pool4_backstop_liquidity": None},
        {**ORACLE, "pool4_network": "SEPOLIA"},
        {"pool4_current_tick": None},
        {},
    ],
    ids=["oracle", "no-band", "sepolia", "unreadable", "empty"],
)
async def test_no_reachable_state_of_this_panel_promises_protection(payload) -> None:
    """The forbidden words are forbidden in **every** state, not one.

    The unavailable branch is where a reassuring sentence is most likely to be
    written later -- "nothing to show, but the band is safe" is exactly the
    line this rule exists to refuse.
    """
    out = (await _text(payload)).lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in out, (forbidden, payload)


@pytest.mark.asyncio
async def test_an_unreadable_position_says_so_instead_of_showing_an_empty_table() -> None:
    """``depth_rows`` returns ``None`` when the tick or the position's
    liquidity could not be read, and ``None`` is a sentence, not a zero ladder.

    A zero ladder paints "this pool bids nothing". An empty table paints the
    same thing more quietly.
    """
    out = await _text({"pool4_current_tick": None, "pool4_position_liquidity": None})
    assert UNAVAILABLE_LINE in out
    assert "unavailable" in out
    assert CAPTION not in out          # the quote clause belongs to a quote


@pytest.mark.asyncio
async def test_no_band_deployed_is_not_an_unreadable_position() -> None:
    """The full-range position still bids, so the ladder is real.

    ``band used`` is then a true ``0.0%`` and not a dash: we looked, and the
    band consumed is none of a band that does not exist.
    """
    out = await _text(
        {**ORACLE, "pool4_backstop_lower_tick": None, "pool4_backstop_liquidity": None}
    )
    assert UNAVAILABLE_LINE not in out
    assert CAPTION in out
    assert "0.0%" in out


# ===========================================================================
# The ladder itself
# ===========================================================================


@pytest.mark.asyncio
async def test_the_panel_paints_one_row_per_rung_in_ladder_order() -> None:
    """Five rungs, deepening. Asserted on composited output against the rung
    labels, so a row a fitting pass silently dropped fails here rather than on
    a reader's screen.
    """
    lines = await _lines(ORACLE)
    positions = []
    for move in DEPTH_MOVES:
        hits = [i for i, line in enumerate(lines) if f"-{move}%" in line]
        assert hits, move
        positions.append(hits[0])
    assert positions == sorted(positions), positions
    assert len(set(positions)) == len(DEPTH_MOVES)


@pytest.mark.asyncio
async def test_the_rows_paint_the_numbers_the_independent_oracle_produced() -> None:
    """The expectation comes from **outside** this code path.

    ``tests/fixtures/surf/pool4/oracle_25955365.json`` is the protocol author's
    own TypeScript answering the same question at the same block -- two
    independent implementations rather than one self-consistency check, which
    is how the ``0x840`` / ``0x2840`` flag error would have been caught on day
    one. The numbers are read out of the **painted cells** and compared to the
    fixture, rather than to ``depth_rows``'s return value: a table compared
    against the function that filled it proves only that the renderer can copy,
    and the thing under test here is the whole path from four payload keys to a
    number a reader sees.

    Tolerances are the two roundings between the implementations and nothing
    more: the skill's text table is already rounded to 0.01 ETH and to whole
    percent, and this panel rounds again to 0.01 and 0.1. They are *absolute*
    because a relative tolerance on the 0.11 ETH rung would have to be 5% to
    pass on rounding alone, and 5% of the 13.73 rung is a real disagreement
    this would then wave through.
    """
    oracle = json.loads(
        (Path(__file__).resolve().parents[1]
         / "fixtures/surf/pool4/oracle_25955365.json").read_text()
    )
    # The fixture is the block ORACLE transcribes; if that ever drifts, every
    # comparison below would be against a different position.
    assert oracle["tick"] == ORACLE["pool4_current_tick"]
    assert oracle["backstop_lower"] == ORACLE["pool4_backstop_lower_tick"]
    reference = {row["move_pct"]: row for row in oracle["sell_side"]}

    lines = await _lines(ORACLE, size=(160, 16))
    checked = 0
    for move in DEPTH_MOVES:
        assert move in reference, move
        painted = [line.strip() for line in lines if line.strip().startswith(f"-{move}%")]
        assert len(painted) == 1, (move, lines)
        cells = painted[0].split()
        assert len(cells) == 3, (move, cells)
        eth = float(cells[1].replace(",", ""))
        used = float(cells[2].rstrip("%"))
        assert eth == pytest.approx(reference[move]["hook_total_eth"], abs=0.02), move
        assert used == pytest.approx(reference[move]["band_used_pct"], abs=0.6), move
        checked += 1
    assert checked == len(DEPTH_MOVES), checked


def test_the_rungs_are_this_panels_only_source_of_rows() -> None:
    """Carry-over C1's shape, one panel over: the ladder is computed once.

    The plan specified a ``pool4_depth_rows`` payload key and **there is no
    such key** -- WP0 froze the contract without it, and the widget-contract
    test refuses a kwarg that is not in ``SURF_KEYS``. So the panel calls the
    pure function directly, and this pins that it is *that* function and not a
    second copy of the tick math living in a widget.
    """
    assert depth_mod.depth_rows is surf_pool4_depth.depth_rows
    assert "pool4_depth_rows" not in SURF_KEYS


def test_a_malformed_rung_costs_its_own_row_and_not_the_panel() -> None:
    """One bad row is a dropped row, never an exception in the render path."""
    assert ladder_cells(None) is None
    assert ladder_cells("nope") is None
    assert ladder_cells({}) == ("--", "--", "--")
    assert ladder_cells(
        {"move_pct": 5, "eth_paid": None, "band_used_pct": 2.0}
    ) == ("-5%", "--", "2.0%")


def test_an_unread_eth_leg_is_a_dash_and_never_a_zero() -> None:
    """``0.00`` is a real answer on this panel -- the price never reached that
    rung's range -- so the dash has to stay available to mean something else.
    """
    assert ladder_cells({"move_pct": 1, "eth_paid": 0.0, "band_used_pct": 0.0})[1] == "0.00"
    assert ladder_cells({"move_pct": 1, "eth_paid": None, "band_used_pct": 0.0})[1] == "--"


# ===========================================================================
# Width, title and safety
# ===========================================================================


@pytest.mark.asyncio
async def test_the_title_carries_the_network_word_from_the_shared_helper() -> None:
    """One implementation of the network word.

    Compared against ``_pool4.panel_title``'s own output rather than against a
    literal, so a change to the separator cannot leave this green while five
    titles disagree. An unrecognised network renders the dash: naming a chain
    this build has not been taught is a provenance claim nothing supports.
    """
    out = await _text({**ORACLE, "pool4_network": "SEPOLIA"})
    assert _pool4.panel_title(TITLE, "SEPOLIA") in out

    unknown = await _text({**ORACLE, "pool4_network": "BASE"})
    assert _pool4.panel_title(TITLE, "BASE") in unknown
    assert "BASE" not in unknown


@pytest.mark.asyncio
async def test_the_narrow_tier_removes_the_band_column_rather_than_blanking_it() -> None:
    """Writing empty cells into a fixed-width column frees nothing.

    A "compact" tier that blanked ``band used`` would light the widen marker
    and still overflow by exactly the width it claimed to have shed. The ETH
    column survives: a table of percentages of a number no longer on screen is
    worse than a table with one fewer column.
    """
    narrow = await _text(ORACLE, size=(FULL_WIDTH + 1, 16))
    assert HEADERS[2] not in narrow
    assert HEADERS[1] in narrow
    assert "-50%" in narrow
    # One column below the pin is still wide enough to *say* it lost one, and
    # ``title_text`` places the longest hint that fits -- here the bare glyph,
    # because the network word is on this title too and ``IF IMD FALLS ·
    # MAINNET  ‹ widen`` does not fit a rail this narrow.
    assert _pool4.GLYPH_HINT in narrow

    wide = await _text(ORACLE, size=(120, 16))
    assert HEADERS[2] in wide
    assert _pool4.WIDEN_HINT not in wide and _pool4.GLYPH_HINT not in wide


@pytest.mark.asyncio
async def test_the_width_pins_are_what_the_table_actually_reserves() -> None:
    """``==``, so each pin reddens whether it is set too low or too high.

    Asserted against ``DataTable.virtual_size``, which is the width the layout
    engine actually reserves, rather than against a composited row: a painted
    row has its trailing spaces stripped, so its width moves with how long the
    last cell's *value* happens to be and an ``==`` on it would be pinning
    today's data. The composited half of the claim is the second assertion --
    no row this panel paints is ever wider than the pin that governs it.

    ``DataTable`` pads every column including the last, which is why these two
    numbers are not ``_rowfit.row_cols``'s arithmetic: that charges a gap
    *between* cells and is a ``RichLog`` row's formula.
    ``SurfPool4UStakers`` records the same decision.
    """
    for size, pin in (((160, 16), FULL_WIDTH), ((FULL_WIDTH + 1, 16), COMPACT_WIDTH)):

        class _A(App):
            def compose(self):
                yield SurfPool4UDepth()

        async with _A().run_test(size=size) as pilot:
            widget = pilot.app.query_one(SurfPool4UDepth)
            widget.update_data(**ORACLE)
            await pilot.pause()
            table = pilot.app.query_one(f"#{TABLE_ID}")
            assert table.virtual_size.width == pin, (size, table.virtual_size)
            painted = max(
                (
                    cell_len("".join(seg.text for seg in strip).strip())
                    for strip in pilot.app.screen._compositor.render_strips()
                    if "-50%" in "".join(seg.text for seg in strip)
                ),
                default=0,
            )
            assert 0 < painted <= pin, (size, painted, pin)
    assert COMPACT_WIDTH < FULL_WIDTH


@pytest.mark.asyncio
async def test_a_hostile_network_word_is_escaped_rather_than_parsed() -> None:
    """Textual defers ``Content.from_markup`` into the message pump, so an
    unescaped ``[/x]`` raises *outside* this widget's ``try`` and takes the app
    down. Surviving the render at all is most of this assertion.
    """
    out = await _text({**ORACLE, "pool4_network": "[/x]MAINNET",
                       "pool4_as_of_hhmm": "[bold red]14:07"})
    assert TITLE in out
    assert "[/x]" not in out and "[bold red]" not in out


# ===========================================================================
# The contract
# ===========================================================================


def test_every_update_data_kwarg_is_a_frozen_contract_key() -> None:
    """Contract §0.1: no short kwargs, no invented keys."""
    params = [
        name
        for name, param in inspect.signature(
            SurfPool4UDepth.update_data
        ).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    ]
    assert params, "the signature is empty; this test would prove nothing"
    for name in params:
        assert name in SURF_KEYS, name
        assert name.startswith("pool4_"), name


def test_the_panel_declares_the_two_keys_nothing_else_on_this_body_renders() -> None:
    """``pool4_backstop_liquidity`` and ``pool4_position_liquidity`` reach a
    reader only through this panel.

    Named explicitly because a key with no renderer is a key the manager
    computes, persists and degrades for that nobody ever sees -- and because
    ``**_kwargs`` swallows a key a widget forgot to declare in total silence.
    """
    declared = {
        name
        for name, param in inspect.signature(
            SurfPool4UDepth.update_data
        ).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    }
    assert {"pool4_position_liquidity", "pool4_backstop_liquidity"} <= declared


@pytest.mark.asyncio
async def test_no_args_and_all_none_render_without_raising() -> None:
    """The outage path is a path, and it is the one nobody exercises by hand."""
    class _A(App):
        def compose(self):
            yield SurfPool4UDepth()

    async with _A().run_test(size=(120, 16)) as pilot:
        widget = pilot.app.query_one(SurfPool4UDepth)
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
