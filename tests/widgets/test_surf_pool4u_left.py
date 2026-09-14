"""WP5 -- the `4` body's left column: ``SurfPool4UStakers`` and ``SurfPool4UBurn``.

Every layout assertion here goes against **composited output**
(``screen._compositor.render_strips()``), joining segments per *row* first and
then rows by newline: joining every segment with a newline splits one painted
row into several apparent lines the moment a row carries two styles, and a test
written that way passes while the user sees something else.

``_lines`` **is** ``tests.widgets.surf_compositing.composite_lines``, the one
shared copy. It was written by hand in five sibling files while this body was
being built -- the right call while two packages were writing in this tree --
and hoisted as carry-over C5 once the wave landed.

Three things this file exists to pin above the rest:

1. **``top 3 = --`` is a real state and is never computed around.** A partial
   sweep ranked as though it were the whole vault understates concentration --
   the one direction that makes a risk look smaller than it is -- and this is
   ``clean_routed_eth``'s guard verbatim (PRD §7.4).
2. **Unread and empty are two different sentences on both panels.** ``None``
   rows and ``[]`` rows, ``None`` flow and ``[]`` flow: four states, four
   words. Collapsing either pair is the curator rail bug, where a dead group's
   ``-- unknown`` and a genuine ``none yet`` both read confident and green.
3. **A ``None`` burn sample is a gap, never a zero.** A zero written into a
   burn series reads as *burning stopped*, which is a different and wrong
   claim from *we did not read that leg*.
"""

from __future__ import annotations


import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.data.surf_cache import (
    TIER_POOL4,
    TIER_POOL4_STAKERS,
    TIER_TTL_SECONDS,
)
from maxpane_dashboard.data.surf_models import (
    POOL4_FLOW_LIMIT,
    SURF_KEYS,
    SURF_ROW_KEYS,
)
from maxpane_dashboard.widgets import sparkline_common
from maxpane_dashboard.widgets.surf import _pool4
from maxpane_dashboard.widgets.surf import pool4u_burn as burn_mod
from maxpane_dashboard.widgets.surf import pool4u_hero as hero_mod
from maxpane_dashboard.widgets.address import COPY_GLYPH, short_address
from maxpane_dashboard.widgets.surf._fmt import ANTI_POISONING_COLS
from maxpane_dashboard.widgets.surf._rowfit import pad
from maxpane_dashboard.widgets.surf.pool4u_burn import (
    COMPACT_WIDTH as BURN_COMPACT_WIDTH,
    EMPTY_LINE as BURN_EMPTY_LINE,
    FULL_WIDTH as BURN_FULL_WIDTH,
    LABEL_COLS as BURN_LABEL_COLS,
    MIN_PACE_WINDOW_S,
    ROW_LABELS as BURN_ROW_LABELS,
    PACE_UNAVAILABLE,
    SPARK_COLS,
    UNAVAILABLE_LINE as BURN_UNAVAILABLE_LINE,
    SurfPool4UBurn,
    burn_points,
    burn_window,
    pace_per_day,
)
from maxpane_dashboard.widgets.surf.pool4u_burn import TITLE as BURN_TITLE
from maxpane_dashboard.widgets.surf.pool4u_stakers import (
    COMPACT_WIDTH as STAKERS_COMPACT_WIDTH,
    EMPTY_LINE as STAKERS_EMPTY_LINE,
    FULL_WIDTH as STAKERS_FULL_WIDTH,
    MAX_ROWS,
    PENDING_LINE as STAKERS_PENDING_LINE,
    STALE_AFTER_S,
    STALE_WORD,
    STAKER_STATES,
    SWEEPING_LINE as STAKERS_SWEEPING_LINE,
    TABLE_ID,
    TOP_N,
    UNAVAILABLE_LINE as STAKERS_UNAVAILABLE_LINE,
    SurfPool4UStakers,
    fold_is_stale,
    footer_line,
    no_rows_line,
    staker_cells,
)
from maxpane_dashboard.widgets.surf.pool4u_stakers import TITLE as STAKERS_TITLE

from tests.widgets.surf_compositing import composite_lines

# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


_lines = composite_lines


#: The default width every STAKERS assertion below is made at.
#:
#: **60 until 2026-09-12, when the address column went whole.** ``FULL_WIDTH``
#: is 69 now and a bare mount needs two columns more than that for its own
#: ``padding: 0 1``, so 60 puts every one of these tests in the *compact*
#: tier -- where the ``share`` column is gone and a ``DataTable`` scrolls the
#: address out of the painted row. Tests that went on asserting an address
#: were not asserting it about the panel the app renders. 80 clears the full
#: tier with room and is deliberately not 71: a default sitting on a
#: threshold makes every test in the file a width measurement by accident.
_STAKERS_WIDTH = 80


async def _stakers(size=(_STAKERS_WIDTH, 20), **kwargs) -> tuple[list[str], str]:
    kwargs.setdefault("pool4_network", "MAINNET")
    lines = await _lines(SurfPool4UStakers, size, **kwargs)
    return lines, "\n".join(lines)


async def _burn(size=(60, 12), **kwargs) -> tuple[list[str], str]:
    kwargs.setdefault("pool4_network", "MAINNET")
    lines = await _lines(SurfPool4UBurn, size, **kwargs)
    return lines, "\n".join(lines)


# ---------------------------------------------------------------------------
# Payloads -- shaped by the frozen contract, never by a live read
# ---------------------------------------------------------------------------

#: Three holders whose shares sum to the ``top3_pct`` the producer would have
#: reported, so a test that *computed* the footer from the rows would pass and
#: a test that reads the key would too. The incomplete-fold test below is what
#: tells them apart.
STAKER_ROWS = [
    {"rank": 1, "address": "0x" + "f5" * 20, "imd": 184_200.0, "pct": 18.4},
    {"rank": 2, "address": "0x" + "a9" * 20, "imd": 151_800.0, "pct": 9.2},
    {"rank": 3, "address": "0x" + "4c" * 20, "imd": 97_400.0, "pct": 4.8},
]

STAKERS_KW = {
    "pool4_stakers": STAKER_ROWS,
    "pool4_staker_count": 66,
    "pool4_staker_top3_pct": 32.4,
    "pool4_stakers_as_of_hhmm": "14:32",
}


def _flow(count: int, *, step_s: float = 3600.0, burned=None) -> list[dict]:
    """``pool4_flow``-shaped rows, ``count`` of them, ``step_s`` apart."""
    return [
        {
            "ts": 1_756_000_000.0 + i * step_s,
            "age_s": 0.0,
            "side": "sell",
            "size_imd": 1000.0,
            "burned_imd": (i * 37.5) if burned is None else burned[i],
            "stakers_imd": 0.0,
            "settled": True,
        }
        for i in range(count)
    ]


BURN_KW = {
    "pool4_flow": _flow(12),
    "pool4_total_burned": 26_289.0,
    "pool4_burned_supply_pct": 0.1234,
    "pool4_total_supply": 2_376_732.0,
    "pool4_as_of_hhmm": "14:32",
}


# ===========================================================================
# STAKERS
# ===========================================================================


@pytest.mark.asyncio
async def test_the_footer_shows_the_dash_on_an_incomplete_fold() -> None:
    """PRD 7.4. ``pool4_staker_top3_pct is None`` means the sweep did not
    finish, and the footer must NOT fall back to summing the rows it has.

    The rows handed in here sum to 32.4 -- exactly the number the complete
    case reports -- so a widget that computed the footer instead of reading
    the key would be indistinguishable in the first assertion and caught only
    by the second.
    """
    _, complete = await _stakers(**STAKERS_KW)
    assert f"top {TOP_N} = 32% of vault" in complete

    _, partial = await _stakers(**dict(STAKERS_KW, pool4_staker_top3_pct=None))
    assert f"top {TOP_N} = -- of vault" in partial
    assert "32%" not in partial


@pytest.mark.asyncio
async def test_unread_stakers_and_an_empty_vault_are_different_sentences() -> None:
    """``None`` is "we could not look"; ``[]`` is "we looked and nobody holds".

    The curator rail bug is these two rendering identically, which reads
    confident and green straight through an outage.

    The unread half now carries ``pool4_stakers_state="failed"``, because that
    is the only state the warning belongs to -- see the three-state test below
    for the other two, which is where the rest of this claim went.
    """
    _, unread = await _stakers(
        **dict(STAKERS_KW, pool4_stakers=None, pool4_stakers_state="failed")
    )
    assert STAKERS_UNAVAILABLE_LINE in unread
    assert STAKERS_EMPTY_LINE not in unread

    _, empty = await _stakers(**dict(STAKERS_KW, pool4_stakers=[]))
    assert STAKERS_EMPTY_LINE in empty
    assert STAKERS_UNAVAILABLE_LINE not in empty


@pytest.mark.asyncio
async def test_the_three_reasons_for_an_empty_panel_are_three_sentences() -> None:
    """The 2026-09-12 defect, pinned where the reader actually meets it.

    ``pool4_stakers`` is ``None`` for three different facts and this panel
    painted ``⚠ stakers unavailable`` for all of them. Two of the three are
    not faults at all: the sweep is **detached** so tick 1's payload is always
    built before the first fold can land, and a transient failure backs the
    tier off 300 s, so the warning then stood for five more minutes. A reader
    acts differently on each, and a warning triangle for "not finished yet" is
    the first thing a fresh launch shows.

    **Asserting the three lines differ is not enough**, and this repo has a
    logged defect class for exactly that shape: a checker that only compares
    the words would pass a build where `pending` rendered
    ``⚠ pending unavailable``. So the two quiet states are additionally
    asserted to carry no ``⚠`` and not the word ``unavailable`` -- which is
    the actual claim the screenshot was about.
    """
    _, failed = await _stakers(
        **dict(STAKERS_KW, pool4_stakers=None, pool4_stakers_state="failed")
    )
    _, sweeping = await _stakers(
        **dict(STAKERS_KW, pool4_stakers=None, pool4_stakers_state="sweeping")
    )
    _, pending = await _stakers(
        **dict(STAKERS_KW, pool4_stakers=None, pool4_stakers_state="pending")
    )

    assert STAKERS_UNAVAILABLE_LINE in failed
    assert "⚠" in failed

    assert STAKERS_SWEEPING_LINE in sweeping
    assert STAKERS_PENDING_LINE in pending

    # The half that bites. Neither quiet state may wear the alarm.
    for quiet, word in ((sweeping, "sweeping"), (pending, "pending")):
        assert "⚠" not in quiet, f"{word} paints a warning triangle"
        assert "unavailable" not in quiet, f"{word} says unavailable"

    # ...and the three really are three, not two that happen to share a line.
    assert len({failed, sweeping, pending}) == 3


@pytest.mark.asyncio
async def test_an_unknown_state_falls_to_the_quiet_line_and_never_the_alarm() -> None:
    """``None``, and anything outside the vocabulary, is not evidence of a fault.

    The direction matters: a producer bug that stopped setting the key, or a
    payload written by an older build, must degrade to "we have not got there
    yet" rather than to a standing warning that nothing is wrong with. ``⚠``
    iff ``failed``, and this is the *iff* half.
    """
    for unknown in (None, "", "whatever", 0):
        _, out = await _stakers(
            **dict(STAKERS_KW, pool4_stakers=None, pool4_stakers_state=unknown)
        )
        assert STAKERS_PENDING_LINE in out, unknown
        assert "⚠" not in out, unknown
        assert STAKERS_UNAVAILABLE_LINE not in out, unknown


def test_the_widget_restates_the_contracts_staker_vocabulary() -> None:
    """The restatement is checked in BOTH directions, `_GAME_CYCLE`'s shape.

    A widget may not import ``data/``, so the three words live twice. A fourth
    word added to the contract and not to the widget would fall through
    ``no_rows_line``'s ``else`` and render as ``pending`` -- a new state
    silently wearing an old state's sentence. This is what reddens instead.
    """
    from maxpane_dashboard.data.surf_models import POOL4_STAKERS_STATES

    assert STAKER_STATES == POOL4_STAKERS_STATES
    assert set(STAKER_STATES) == set(POOL4_STAKERS_STATES)
    # Only one of them may ever be the alarm.
    alarming = [w for w in STAKER_STATES if "⚠" in no_rows_line(w)[0]]
    assert alarming == ["failed"]


@pytest.mark.asyncio
async def test_an_unread_sweep_paints_no_rows_at_all() -> None:
    """The unavailable line is not enough on its own: a table still holding
    the previous poll's rows under an "unavailable" footer is a stale number
    presented as live.
    """

    class _A(App):
        def compose(self):
            yield SurfPool4UStakers()

    async with _A().run_test(size=(60, 20)) as pilot:
        widget = pilot.app.query_one(SurfPool4UStakers)
        widget.update_data(**STAKERS_KW, pool4_network="MAINNET")
        await pilot.pause()
        table = pilot.app.query_one(f"#{TABLE_ID}")
        assert table.row_count == 3

        widget.update_data(**dict(STAKERS_KW, pool4_stakers=None),
                           pool4_network="MAINNET")
        await pilot.pause()
        assert table.row_count == 0


@pytest.mark.asyncio
async def test_the_whole_address_reaches_the_screen() -> None:
    """All 42 characters, painted, in one piece (2026-09-12).

    **Asserted as the presence of the whole string, never as the absence of an
    ellipsis.** "no ``…`` in this panel" passes on a blank cell, on a dropped
    row and on a panel that failed to render at all, which is the
    known-unfalsifiable shape in this repo's taxonomy. So the claim is that
    ``0x`` + the forty hex characters the payload carries is *in* composited
    output, and that it is in **one** composited row rather than split across
    two by a wrap.

    The panel shortened this with ``_fmt.long_addr`` until the owner read the
    live screen and asked for the whole thing. Both shorter forms are still
    asserted absent, and the older of the two matters most: ``0xABCD..1234``
    is the leaderboard template's form and it *collides* with live spoofs of
    surf's own fee recipients. Neither may come back by accident.
    """
    lines, out = await _stakers(**STAKERS_KW)
    addr = STAKER_ROWS[0]["address"]
    assert len(addr) == 42, "the fixture stopped being a real-length address"

    assert addr in out, (
        "the whole address did not reach the compositor: "
        f"{[ln for ln in lines if ln.strip()]}"
    )
    assert sum(1 for line in lines if addr in line) == 1, (
        "the address is on the screen but not on one row -- it wrapped"
    )
    # The whole address carries its copy icon, on the same row
    # (docs/address_copy_PRD.md; this width is at least ``WHOLE_WIDTH``).
    assert f"{addr} {COPY_GLYPH}" in out

    # Neither shortener may come back, and the template's is the dangerous one.
    assert short_address(addr, ANTI_POISONING_COLS) not in out
    assert f"{addr[:6]}..{addr[-4:]}" not in out


@pytest.mark.asyncio
async def test_the_other_callers_of_the_short_form_are_untouched() -> None:
    """The anti-poisoning window this panel left behind was **not** narrowed.

    HATCHES' address block on the ``p`` body and the dashboard body's
    activity feed still show it, and this panel did until 2026-09-12. The
    change the owner asked for was this panel's, so the whole address was
    added beside the window rather than the window being changed under two
    other callers. ``_fmt.long_addr`` rendered it until 2026-09-14; it is now
    ``widgets/address.short_address`` at ``_fmt.ANTI_POISONING_COLS``, and if
    somebody "simplifies" that constant down, the window disappears from two
    panels that still need it and this is what says so.
    """
    addr = STAKER_ROWS[0]["address"]
    shown = short_address(addr, ANTI_POISONING_COLS)
    assert "…" in shown and len(shown) == 17
    assert shown == f"{addr[:10]}…{addr[-6:]}"


@pytest.mark.asyncio
async def test_a_hostile_address_is_escaped_rather_than_parsed() -> None:
    """Chain-sourced strings reach a ``DataTable``, which defers
    ``Text.from_markup`` into its idle handler -- so an unescaped ``[/x]``
    raises outside the screen's ``try/except`` and takes the app down.

    Rendering at all is most of the assertion; the rest is that the row did not
    silently vanish and take a real holder's rank with it.
    """
    hostile = dict(STAKER_ROWS[0], address="0x[/x]" + "ab" * 18)
    lines, out = await _stakers(
        **dict(STAKERS_KW, pool4_stakers=[hostile, *STAKER_ROWS[1:]])
    )
    assert f"top {TOP_N} = 32% of vault" in out
    assert sum(1 for line in lines if STAKER_ROWS[1]["address"] in line) == 1


@pytest.mark.asyncio
async def test_a_malformed_row_costs_its_own_row_and_not_the_panel() -> None:
    _, out = await _stakers(
        **dict(STAKERS_KW, pool4_stakers=["not a row", None, *STAKER_ROWS])
    )
    assert STAKER_ROWS[0]["address"] in out
    assert f"top {TOP_N} = 32% of vault" in out


@pytest.mark.asyncio
async def test_the_panel_prints_neither_clock() -> None:
    """PRD 7.2 as amended 2026-09-12: the ``4`` body prints one ``as of`` and
    it is the screen's title row, not any panel's.

    Both markers still arrive -- one is subtracted from the other -- and
    **neither is rendered**. Asserted against both spellings rather than
    against the phrase ``as of``, because a panel that printed a bare
    ``14:32`` with no label would satisfy a phrase check and still be the
    per-panel clock the owner asked to have removed.
    """
    _, out = await _stakers(
        **dict(STAKERS_KW, pool4_stakers_as_of_hhmm="14:32"),
        pool4_as_of_hhmm="14:40",
    )
    assert "as of" not in out
    assert "14:32" not in out
    assert "14:40" not in out


@pytest.mark.asyncio
async def test_the_footer_says_stale_when_the_fold_has_missed_a_cycle() -> None:
    """What replaced the marker, and the half a one-directional test can see.

    The rows ride an 1800 s tier and the body's clock a 600 s one, so a fold
    an hour and a half behind really is what a reader would have been shown
    under a title row reading *now* -- the live case this was built for sat at
    13:52 against 15:29.
    """
    _, out = await _stakers(
        **dict(STAKERS_KW, pool4_stakers_as_of_hhmm="13:52"),
        pool4_as_of_hhmm="15:29",
    )
    assert f"of vault · {STALE_WORD}" in out, out


@pytest.mark.asyncio
async def test_the_footer_says_nothing_when_the_fold_is_merely_not_yet_due()\
        -> None:
    """The half that cannot be checked by looking at a stale panel.

    **This is the assertion the owner's request actually turns on.** The five
    per-panel markers were removed because they were clutter; a word that
    printed in the ordinary case would be the same clutter under a different
    spelling, and a test that only ever renders an old fold cannot tell a
    conditional word from an unconditional one.

    Twenty-five minutes apart is inside a single ``TIER_POOL4_STAKERS``
    period: the fold is not even due yet, which is the most ordinary state
    this panel has.
    """
    _, out = await _stakers(
        **dict(STAKERS_KW, pool4_stakers_as_of_hhmm="15:04"),
        pool4_as_of_hhmm="15:29",
    )
    assert "of vault" in out, out
    assert STALE_WORD not in out, out


@pytest.mark.parametrize(
    "mine,theirs,expected",
    [
        # Exactly at the threshold is NOT stale -- 2400 s is the largest gap
        # healthy operation can produce, so the word starts one minute later.
        ("14:00", "14:40", False),
        ("14:00", "14:41", True),
        # Across midnight, in both directions.
        ("23:30", "00:31", True),
        ("23:30", "00:10", False),
        # This panel's marker AHEAD of the body's: ordinary, not 23h behind.
        ("15:29", "13:52", False),
        # Nothing to compare, and nothing said.
        (None, "15:29", False),
        ("13:52", None, False),
        ("not a time", "15:29", False),
        ("25:99", "15:29", False),
        ("[/x]13:52", "15:29", True),
    ],
)
def test_fold_is_stale_answers_from_two_payload_strings(mine, theirs, expected)\
        -> None:
    """The decision is pure, total, and takes **no clock**.

    Every case here is a payload a persisted cache file can carry -- a
    hand-edited one included, which is why the bracket-run case is in the
    table and expects the same answer as the clean string beside it rather
    than a crash or a silent ``False``.
    """
    assert fold_is_stale(mine, theirs) is expected


def test_the_stale_threshold_is_the_two_tiers_it_is_derived_from() -> None:
    """:data:`STALE_AFTER_S` is a derivation, not a taste judgement.

    The quantity is the difference between two markers, so each contributes
    its own tier's ordinary lag: the staker fold may be a full
    ``TIER_POOL4_STAKERS`` old before the next one is due, and the marker it
    is compared against may have just advanced on ``TIER_POOL4``. Their sum is
    the largest gap healthy operation can produce.

    Imported from ``data/`` **here and not in the widget** -- a widget may not
    import that layer (contract §0.5), so the two numbers live apart and this
    is the agreement test that keeps them honest. Move either TTL and the
    threshold is wrong by exactly that amount, and this reddens rather than
    the word quietly starting to fire in the ordinary case.
    """
    assert STALE_AFTER_S == (
        TIER_TTL_SECONDS[TIER_POOL4_STAKERS] + TIER_TTL_SECONDS[TIER_POOL4]
    )
    assert STALE_AFTER_S > TIER_TTL_SECONDS[TIER_POOL4_STAKERS], (
        "a threshold at or under the staker tier's own period fires on a fold "
        "the tier has only just made due, which is the most ordinary state "
        "this panel has"
    )


@pytest.mark.asyncio
async def test_the_title_carries_the_network_word_from_the_shared_helper() -> None:
    """Imported from ``_pool4``, never restated: two packages once wrote
    ``network_word`` twice with different behaviour on unknown input, and one
    body painted ``THE SPLIT · —`` beside ``THE RATCHET · BASE``.

    The ``4`` body calls ``market_title_text``, so ``MAINNET`` is the one word
    it leaves unsaid (2026-09-12; see ``_pool4.QUIET_NETWORK``). Everything
    the allowlist is careful about survives that, and all three cases are
    asserted here rather than only the one that changed -- an implementation
    that dropped the word unconditionally would pass a mainnet-only check.
    """
    lines, mainnet = await _stakers(**STAKERS_KW, pool4_network="MAINNET")
    assert _pool4.market_panel_title(STAKERS_TITLE, "MAINNET") in mainnet
    assert STAKERS_TITLE in mainnet
    assert "MAINNET" not in mainnet
    # The separator is asserted against the **title row** rather than the
    # panel: the footer's own `` · `` is a different line's punctuation, and
    # a panel-wide check would be green for a reason that is not the claim.
    title_row = next(ln for ln in lines if STAKERS_TITLE in ln)
    assert _pool4.TITLE_SEP not in title_row

    _, sepolia = await _stakers(**STAKERS_KW, pool4_network="SEPOLIA")
    assert _pool4.panel_title(STAKERS_TITLE, "SEPOLIA") in sepolia

    _, unknown = await _stakers(**STAKERS_KW, pool4_network="BASE")
    assert f"{STAKERS_TITLE}{_pool4.TITLE_SEP}{_pool4.NETWORK_UNKNOWN}" in unknown
    assert "BASE" not in unknown


@pytest.mark.asyncio
async def test_the_narrow_tier_removes_the_share_column_rather_than_blanking_it() -> None:
    """Writing empty cells into a fixed-width column frees nothing.

    A "compact" tier that did that would light the widen marker and still
    overflow by exactly the width it claimed to have shed -- so the column is
    removed, and the header word goes with it.
    """
    _, wide = await _stakers(size=(_STAKERS_WIDTH, 20), **STAKERS_KW)
    assert "share" in wide
    assert "18.4%" in wide

    _, narrow = await _stakers(size=(38, 20), **STAKERS_KW)
    assert "share" not in narrow
    assert "18.4%" not in narrow
    # The address COLUMN survives the tier drop -- it is the last thing this
    # panel would give up. Asserted on the column and a prefix of its value
    # rather than on the whole 42 characters, because 38 columns cannot paint
    # 42 of anything: what the compact tier sheds is `share`, and what a
    # too-narrow terminal does to the address on top of that is the `‹`
    # marker's business, asserted on the line below.
    assert "address" in narrow
    assert STAKER_ROWS[0]["address"][:20] in narrow
    assert _pool4.WIDEN_HINT in narrow or _pool4.GLYPH_HINT in narrow


@pytest.mark.asyncio
async def test_the_stakers_width_pins_are_what_the_table_actually_reserves() -> None:
    """``==``, so each pin reddens whether it is set too low or too high.

    Asserted against ``DataTable.virtual_size``, which is the width the layout
    engine actually reserves, rather than against a composited row: a painted
    row has its trailing spaces stripped, so its width moves with how long the last cell's
    *value* happens to be and an ``==`` on it would be pinning today's data.
    The composited half of the claim is the second assertion -- no row this
    panel paints is ever wider than the pin that governs it. **It used to look
    only at rows carrying a ``…``** and went vacuous on 2026-09-12: with whole
    addresses at the full tier nothing on this panel is truncated at all, so
    the ``max`` fell through to its ``default=0`` and ``0 < painted`` was the
    only thing keeping the test from passing on an empty panel. Every painted
    row is measured now.

    ``DataTable`` pads every column including the last, which is why these two
    numbers are not ``_rowfit.row_cols``'s arithmetic: that charges a gap
    *between* cells and is a ``RichLog`` row's formula. Borrowing the wrong one
    would put the marker a column or two off the width it is marking.
    """
    # Three tiers since 2026-09-14 (``docs/address_copy_PRD.md`` §5): the
    # whole address and its icon at 80, the address windowed to 40 beside its
    # icon at 72 (a text budget of 70, one under ``WHOLE_WIDTH``), and the
    # share column shed at 38.
    from maxpane_dashboard.widgets.surf.pool4u_stakers import WHOLE_WIDTH

    for size, pin in (((80, 20), WHOLE_WIDTH), ((72, 20), STAKERS_FULL_WIDTH),
                      ((38, 20), STAKERS_COMPACT_WIDTH)):

        class _A(App):
            def compose(self):
                yield SurfPool4UStakers()

        async with _A().run_test(size=size) as pilot:
            widget = pilot.app.query_one(SurfPool4UStakers)
            widget.update_data(**STAKERS_KW, pool4_network="MAINNET")
            await pilot.pause()
            table = pilot.app.query_one(f"#{TABLE_ID}")
            assert table.virtual_size.width == pin, (size, table.virtual_size)
            painted = max(
                (
                    cell_len("".join(seg.text for seg in strip).strip())
                    for strip in pilot.app.screen._compositor.render_strips()
                ),
                default=0,
            )
            assert 0 < painted <= pin, (size, painted, pin)


def test_the_footer_drops_the_count_rather_than_dashing_it() -> None:
    """The concentration half is the half a reader acts on; it must not be
    pushed along by a dash standing in for an unread address count."""
    assert footer_line(66, 32.4) == f"66 addresses · top {TOP_N} = 32% of vault"
    assert footer_line(None, 32.4) == f"top {TOP_N} = 32% of vault"
    assert footer_line(66, None) == f"66 addresses · top {TOP_N} = -- of vault"


def test_an_unread_holding_is_a_dash_and_never_a_zero() -> None:
    """A zero would rank a wallet as holding nothing when we simply could not
    convert its shares -- a confident wrong answer about a named address."""
    cells = staker_cells({"rank": 1, "address": "0x" + "ab" * 20, "imd": None,
                          "pct": None})
    assert cells is not None
    assert cells[2] == "--"
    assert cells[3] == "--"


def test_the_row_address_is_read_under_the_declared_name_only() -> None:
    """Carry-over C2 closed: one spelling, and the other is now a defect.

    The row shape was specified two ways while this panel was written, so
    ``staker_cells`` read ``address`` with an ``addr`` fallback and the
    divergence was filed. ``SURF_ROW_KEYS["pool4_stakers"]`` now declares
    ``address`` and the producer emits it, so the fallback is gone -- and this
    test is its mirror image rather than its deletion: a row arriving with
    ``addr`` is a producer bug, and it must render the dash that says so
    instead of a correct-looking column that hides it.

    Read off ``SURF_ROW_KEYS`` rather than from a literal, so the day the
    contract renames the field this fails instead of pinning the old name.
    """
    name = SURF_ROW_KEYS["pool4_stakers"][1]
    assert name == "address"
    addr = "0x" + "ab" * 20
    assert staker_cells({"rank": 1, name: addr, "imd": 1.0, "pct": 1.0})[1] == addr
    stale = staker_cells({"rank": 1, "addr": addr, "imd": 1.0, "pct": 1.0})
    assert stale[1] == "--", stale


def test_the_row_cap_is_below_the_producers_own_limit() -> None:
    """The renderer's guard exists so a longer list cannot push the footer --
    the panel's actual subject -- off a short panel."""
    assert MAX_ROWS >= 3
    assert MAX_ROWS <= 20


# ===========================================================================
# BURN & SUPPLY
# ===========================================================================


@pytest.mark.asyncio
async def test_the_burn_panel_draws_its_sparkline_and_names_its_window() -> None:
    """The pace carries the window it was measured over, the way the hero's
    trailing return carries ``7d``: ``pool4_flow`` is capped at
    ``POOL4_FLOW_LIMIT`` events, so this is recent burn and the label says so.
    """
    _, out = await _burn(**BURN_KW)
    assert any(ch in out for ch in sparkline_common.SPARK_CHARS[1:])
    assert "/day over 11h" in out
    # Label/value columns since 2026-09-12: the label owns the left column and
    # the number follows it, rather than the number carrying its own noun.
    assert f"{pad('retired', BURN_LABEL_COLS)}26.3K · 0.12% of supply" in out
    assert POOL4_FLOW_LIMIT == 25


@pytest.mark.asyncio
async def test_unread_flow_and_a_quiet_window_are_different_sentences() -> None:
    """An empty series draws a flat baseline, which is the picture of a hook
    that has stopped burning. That must not be what an unread flow looks like.
    """
    _, unread = await _burn(**dict(BURN_KW, pool4_flow=None))
    assert BURN_UNAVAILABLE_LINE in unread
    assert BURN_EMPTY_LINE not in unread
    # The totals were read and are still shown: one dead key must not black out
    # the whole panel.
    assert f"{pad('retired', BURN_LABEL_COLS)}26.3K" in unread

    _, quiet = await _burn(**dict(BURN_KW, pool4_flow=[]))
    assert BURN_EMPTY_LINE in quiet
    assert BURN_UNAVAILABLE_LINE not in quiet


@pytest.mark.asyncio
async def test_a_wholly_unread_panel_says_so_once() -> None:
    _, out = await _burn(
        pool4_flow=None, pool4_total_burned=None,
        pool4_burned_supply_pct=None, pool4_total_supply=None,
    )
    assert BURN_UNAVAILABLE_LINE in out
    assert out.count("retired") == 0


@pytest.mark.asyncio
async def test_the_burn_title_carries_the_network_word_from_the_shared_helper() -> None:
    _, out = await _burn(**BURN_KW, pool4_network="SEPOLIA")
    assert _pool4.panel_title(BURN_TITLE, "SEPOLIA") in out

    _, unknown = await _burn(**BURN_KW, pool4_network=None)
    assert f"{BURN_TITLE}{_pool4.TITLE_SEP}{_pool4.NETWORK_UNKNOWN}" in unknown


@pytest.mark.asyncio
async def test_the_narrow_tier_keeps_the_window_by_moving_it() -> None:
    """The window is the clause that stops the pace reading as a measured
    daily rate, so it is the last thing shed -- it moves to the totals line
    rather than disappearing when the pace line runs out of room.
    """
    _, wide = await _burn(size=(60, 12), **BURN_KW)
    assert "/day over 11h" in wide

    _, narrow = await _burn(size=(30, 12), **BURN_KW)
    assert "/day over" not in narrow
    assert "/day 11h" in narrow
    assert _pool4.WIDEN_HINT in narrow or _pool4.GLYPH_HINT in narrow
    # And nothing on the narrow panel was handed to CSS to clip in silence:
    # `text-overflow: ellipsis` eating a line is exactly what the marker is
    # supposed to make unnecessary.
    assert "…" not in narrow


def test_a_none_burn_leg_is_a_gap_and_never_a_zero() -> None:
    """A zero written into a burn series reads as *burning stopped*, which is a
    different and wrong claim from *we did not read that leg*. The sample is
    dropped; a genuine ``0.0`` on a BUY row stays.
    """
    rows = _flow(3, burned=[100.0, None, 300.0])
    pts = burn_points(rows)
    assert [value for _, value in pts] == [100.0, 300.0]

    rows = _flow(3, burned=[100.0, 0.0, 300.0])
    assert [value for _, value in burn_points(rows)] == [100.0, 0.0, 300.0]


def test_unread_flow_gives_none_and_an_empty_window_gives_an_empty_list() -> None:
    assert burn_points(None) is None
    assert burn_points([]) == []


def test_the_pace_refuses_to_annualise_a_window_too_short_to_mean_anything() -> None:
    """A five-minute window multiplied by 288 turns one trim into a headline
    burn rate. ``None``, and the panel says ``--/day``."""
    short = burn_points(_flow(4, step_s=60.0))
    assert burn_window(short) == pytest.approx(180.0)
    assert burn_window(short) < MIN_PACE_WINDOW_S
    assert pace_per_day(short) is None
    assert PACE_UNAVAILABLE == "--/day"


def test_a_usable_window_with_no_burns_paces_zero_rather_than_unavailable() -> None:
    """``0.0`` is a real answer: the window was long enough and nothing burned
    in it. Only an unusable window is ``None``."""
    points = burn_points(_flow(4, step_s=7200.0, burned=[0.0] * 4))
    assert burn_window(points) >= MIN_PACE_WINDOW_S
    assert pace_per_day(points) == 0.0


def test_the_pace_is_the_window_total_annualised_and_not_the_last_sample() -> None:
    """Derived outside the implementation: four samples six hours apart span
    eighteen hours and carry 400 IMD, which is ``400 / 18 * 24`` per day.
    """
    points = burn_points(_flow(4, step_s=6 * 3600.0, burned=[100.0] * 4))
    assert pace_per_day(points) == pytest.approx(400.0 / 18.0 * 24.0, rel=1e-9)


def test_the_window_needs_two_distinct_timestamps() -> None:
    assert burn_window(burn_points(_flow(1))) is None
    assert burn_window(burn_points(_flow(2, step_s=0.0))) is None


# ===========================================================================
# Reuse, not re-implementation -- the rules the parent package made hard
# ===========================================================================

#: The three local sweeps that used to sit here -- "no ``pool4u_`` module
#: restates a shared primitive", "...imports the data layer", "...puts a theme
#: token inside its own markup" -- **are gone, and the glob that made them
#: necessary is what was actually wrong** (carry-over C3).
#:
#: ``tests/widgets/test_surf_pool4_shared.py`` ran all three by discovery over
#: ``pool4_*.py``, and that glob does not match ``pool4u_*.py``: the `4` body's
#: widgets were outside every one of them for the whole of their existence. WP5
#: wrote local copies here to cover the gap and said so. The glob is now
#: ``pool4*.py``, the shared file discovers all ten widget modules, and keeping
#: the copies would be the divergence this repo keeps paying for -- three
#: sweeps over three modules beside three sweeps over ten, and a fix landing in
#: one of them.
#:
#: What is kept below is the one check the shared file cannot make: an
#: **identity** assertion that this panel's sparkline helpers are the shared
#: module's objects and not same-named locals. The shared sweep proves no pool4
#: module *defines* them; only this can prove which ones this module *calls*.

def test_the_burn_panel_uses_the_shared_sparkline_helper_itself() -> None:
    """Identity, not a name match: three dashboards once carried byte-identical
    copies of these helpers and a fix reached none of the others (MEDI-36).
    """
    assert (
        burn_mod.build_sparkline_from_points
        is sparkline_common.build_sparkline_from_points
    )
    assert burn_mod.coerce_points is sparkline_common.coerce_points


def test_every_update_data_kwarg_on_this_column_is_a_frozen_contract_key() -> None:
    """The screen splats the manager's flat dict, so a kwarg that is not a key
    is a silent no-op. ``test_surf_widget_contract.py`` enforces this for
    exported widgets; these three are not exported yet (WP7's job), so it is
    enforced here until they are.
    """
    import inspect

    for cls in (SurfPool4UStakers, SurfPool4UBurn, hero_mod.SurfPool4UserHero):
        names = [
            name
            for name, param in inspect.signature(cls.update_data).parameters.items()
            if param.kind is not param.VAR_KEYWORD and name != "self"
        ]
        assert names, cls.__name__
        assert all(name in SURF_KEYS for name in names), (
            cls.__name__, [n for n in names if n not in SURF_KEYS]
        )
        # And the `pool4_` prefix is never elided: `as_of_hhmm` already stands
        # for `launchpad_as_of_hhmm` and cannot answer for two contract keys.
        assert "as_of_hhmm" not in names, cls.__name__


@pytest.mark.parametrize(
    "cls", [SurfPool4UStakers, SurfPool4UBurn], ids=lambda c: c.__name__
)
@pytest.mark.asyncio
async def test_no_args_and_all_none_render_without_raising(cls) -> None:
    """A widget that raises inside Textual's message pump takes the app down.

    The same sweep ``test_surf_widget_contract.py`` runs over every exported
    widget, run here because these are not exported yet.
    """
    import inspect

    class _A(App):
        def compose(self):
            yield cls()

    async with _A().run_test(size=(120, 20)) as pilot:
        widget = pilot.app.query_one(cls)
        widget.update_data()
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
        strips = pilot.app.screen._compositor.render_strips()
        assert strips is not None


def test_the_burn_width_pins_are_ordered_and_distinct() -> None:
    """A compact tier that is not narrower than the full one sheds nothing and
    lights a marker for no reason."""
    assert BURN_COMPACT_WIDTH < BURN_FULL_WIDTH
    assert STAKERS_COMPACT_WIDTH < STAKERS_FULL_WIDTH
    # The sparkline is itself a tier. A compact tier that shed only words would
    # light the marker and still overflow by whatever the fixed-width line is
    # over budget -- which is what the first draft of this panel did.
    assert SPARK_COLS["compact"] < SPARK_COLS["full"] <= sparkline_common.SPARK_WIDTH


# ===========================================================================
# BURN & SUPPLY's label column (2026-09-12 screenshot review)
# ===========================================================================


@pytest.mark.asyncio
async def test_the_burn_panel_paints_its_three_rows_in_one_label_column() -> None:
    """The defect the 2026-09-12 screenshot review named on this panel.

    It rendered as a ragged block -- a sparkline with a pace glued to it, then
    a sentence carrying its own noun (``26.6K retired``), then a line that led
    with a word (``supply 3.4M IMD``). Three lines, three different shapes,
    nothing to run an eye down.

    Asserted as an **alignment**, not as three separate string matches: every
    row's value has to begin at the same column, which is the property a
    reader actually sees and the one a reworded label cannot fake. Read off
    composited output, and measured in ``cell_len`` rather than ``len`` --
    a sparkline block is one cell per character here but the rule is the rule.
    """
    lines, _ = await _burn(size=(80, 12), **BURN_KW)
    rows = [ln for ln in lines if any(
        ln.strip().startswith(label) for label in BURN_ROW_LABELS)]
    assert len(rows) == len(BURN_ROW_LABELS), rows

    # in order, top to bottom
    for row, label in zip(rows, BURN_ROW_LABELS):
        assert row.strip().startswith(label), (row, label)

    # and every value starts in the same column
    starts = {cell_len(row[:row.index(label) + BURN_LABEL_COLS])
              for row, label in zip(rows, BURN_ROW_LABELS)}
    assert len(starts) == 1, (starts, rows)


def test_the_rail_panels_share_one_label_column() -> None:
    """BURN & SUPPLY sits directly above SIGNALS in the `4` body's rail, so a
    reader's eye runs straight from one label column into the other.

    Two different widths there is the ragged look the screenshot review named,
    one panel further out. ``LABEL_COLS`` is **restated** in each module
    rather than imported across the ownership seam (a widget importing a
    sibling widget's constant is a coupling, not a hoist -- the reason
    ``NO_BAND`` is spelled twice in this body too), and this is the agreement
    test that shape requires. It compares the two constants in both
    directions, so widening either one alone reddens here.
    """
    from maxpane_dashboard.widgets.surf.pool4u_signals import (
        LABEL_COLS as SIGNALS_LABEL_COLS,
    )

    assert BURN_LABEL_COLS == SIGNALS_LABEL_COLS

    # ...and it is actually wide enough for this panel's own labels, which the
    # equality above cannot tell you: a matched pair of too-narrow columns
    # agrees with itself while both panels run their labels into their values.
    for label in BURN_ROW_LABELS:
        assert cell_len(label) < BURN_LABEL_COLS, label
