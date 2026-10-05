"""The ``e`` POOL4 protocol body, its mainnet deployment, and the ``4`` market body's CSS.

Split out of ``test_surf_screen.py`` on 2026-10-05 so a POOL4 change runs POOL4's own
composites, not the whole screen's. The ``4`` market body's screen and layout tests are
``test_surf_pool4_market_screen.py`` and ``test_surf_pool4_market_layout.py``; only its
stylesheet-agreement and ``fr``-floor checks live here, beside the ``e`` body's they mirror.
The harness, the payloads and the shared helpers stay in ``test_surf_screen.py``; its
docstring's rules hold here too: composited output only, no network, no wall clock.
"""

from __future__ import annotations

import pytest

from pathlib import Path
from textual.app import App
from maxpane_dashboard.data.surf_models import (
    POOL4_KEYS,
    POOL4_COUNTER_STATES,
    POOL4_DISCOVERY_SOURCES,
    POOL4_DISCOVERY_STATES,
    POOL4_FLOW_SIDES,
    POOL4_HATCH_LABELS,
    POOL4_HATCH_SCOPES,
    POOL4_HATCH_STATES,
    POOL4_NETWORKS,
    POOL4_REWARD_PATHS,
)
from maxpane_dashboard.screens.surf import (
    LAUNCHPAD_BODY_ID,
    POOL4_BODY_ID,
    POOL4_LEFT_ID,
    POOL4_RAIL_ID,
    POOL4_USER_BODY_ID,
    POOL4_USER_BOTTOM_ID,
    POOL4_USER_MIDDLE_ID,
    POOL4_USER_RAIL_ID,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_ROWS,
    TALLER_HINT,
    SurfScreen,
    SURF_FULL_LAYOUT_COLUMNS,
)
from tests.screens._sweeps import boundary_set
from maxpane_dashboard.widgets.surf import (
    SurfHero,
    SurfPool4Flow,
    SurfPool4Hatches,
    SurfPool4Ratchet,
    SurfPool4Split,
    SurfPool4Vault,
)
from tests.screens.test_surf_screen import (
    _ADOPTED_DISCOVERY_DETAIL,
    _ADOPTED_SOURCE_TX,
    _ALL_WIDGET_CLASSES,
    _css_clipped_lines,
    _css_rules,
    _expand_css_box,
    _frozen_payload,
    _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS,
    _LAUNCHPAD_CSS_STRUCTURAL,
    _mainnet_pool4_payload,
    _ordinary_pool4_payload,
    _POOL4_WIDGET_CLASSES,
    _region_text,
    _sample_data,
    _screen_text,
    _surf_app,
    _surf_stylesheet_block,
    SURF_WIDGET_SIGNATURES,
)


# =========================================================================
# The ``p`` POOL4 view (2026-09-01) -- the third body on this screen
# =========================================================================
#
# The `l` body's tests (``test_surf_launchpad_screen.py``) are the template and
# most of this file is that template applied to a second swap. Three things are
# genuinely new and are worth reading rather than skimming:
#
# 1.  A `…` at the end of a pool4 line is NOT necessarily a clip. Four of the
#     five panels fit their own third-party strings to their own tier width,
#     so HATCHES paints `no self-post in the announce chann…` at 47 cells
#     inside a 99-cell panel and means it. `_clipped_pool4_lines` compares
#     against the panel's own edge instead, and the launchpad's bare
#     `endswith("…")` would have reported this whole body as permanently
#     clipped at every width including 200.
# 2.  The height pin is a CONSTANT under every payload, and that is a design
#     property this section asserts directly rather than inferring from one
#     sweep -- see `test_the_pool4_height_pin_does_not_move_with_the_hatch_
#     count`.
# 3.  `_SCROLL_COLUMNS` gaining a MODE_POOL4 entry is the 2026-08-25 defect's
#     own regression lock, and it is guarded twice: once for the marker
#     really lighting on this body, once for the mapping being total over
#     every mode the screen has.


def _pool4_app(payload: dict | None = None) -> App:
    """The themed harness, so the real ``minimal.tcss`` pool4 block renders.

    Load-bearing, not tidiness: an app stylesheet outranks ``DEFAULT_CSS``,
    so a seam written into ``DEFAULT_CSS`` alone would leave whatever
    ``minimal.tcss`` says in charge and every width number below would be
    measuring the wrong file.
    """
    return _surf_app(payload)


#: The two column widths the width pin is assembled from, measured in situ.
#: Restated here as independent literals rather than imported from
#: ``screens/surf.py``'s docstring prose (which is prose, and cannot be
#: imported anyway), so ``test_the_pool4_pin_is_the_sum_of_the_needs_it_
#: claims`` compares two things rather than one thing with itself.
#:
#: **Neither number may be quoted as a reason for the panel arrangement**, and
#: :data:`POOL4_RAIL_NEED` especially not -- a warning that survived the
#: mainnet rebalance by changing sides. It used to read "the rail needs 43
#: *because* ``SurfPool4Hatches`` is in the other column". HATCHES is now in
#: the rail, the rail needs 50 *because* it is, and quoting that 50 as
#: evidence the swap was right is the identical circle mirrored. The
#: arrangement was chosen on rows, not columns --
#: ``screens/surf.SURF_POOL4_FULL_LAYOUT_ROWS`` carries that measurement.
#:
#: Re-measured on 2026-09-02 across all three payload magnitudes, and again on
#: **2026-09-14** when POOL4 FLOW left the body: left = max(RATCHET 45,
#: SPLIT 36) -- it was FLOW's 53 -- and rail = max(HATCHES 50, VAULT 44),
#: unchanged. The rail binds now.
POOL4_LEFT_NEED = 45        # SurfPool4Ratchet's, plus the column's own gutter
POOL4_RAIL_NEED = 50        # SurfPool4Hatches', plus the column's own gutter

#: An independent literal for the same reason ``MEASURED_FULL_LAYOUT_COLUMNS``
#: is one: a test that aliased the screen's constant would compare a number
#: against itself and pin nothing. 106 until 2026-09-14; swept 86..125 on
#: three payloads when POOL4 FLOW left the body.
MEASURED_POOL4_COLUMNS = 99
MEASURED_POOL4_ROWS = 45


def _pool4_payload(**overrides) -> dict:
    return _frozen_payload(**overrides)


def _pool4_hatch_payload(rows: int) -> dict:
    """The fixture's hatch list re-cut to *rows* levers.

    The producer emits ten and the widget caps at twelve, so the interesting
    magnitudes are 0, 10 and 12 -- and the height pin's whole claim is that
    none of them moves it.
    """
    base = _sample_data()["pool4_hatches"]
    labels = ("owner", "paused", "rescue", "market", "rebalance",
              "burn sink", "rewards", "deployed")
    return _frozen_payload(pool4_hatches=[
        {**base[i % len(base)], "label": labels[i % len(labels)]}
        for i in range(rows)
    ])


def _clipped_pool4_lines(app, screen) -> list[str]:
    """Every composited line in the ``p`` body that **CSS** truncated.

    The panels, never their two containers -- four since POOL4 FLOW left
    the body on 2026-09-14 -- and through
    :func:`_css_clipped_lines`, which walks each panel to the leaf that
    actually painted the line and measures that leaf's own
    ``content_region``. Read that function for why both halves of the old
    rule survive the change; the half this body specifically depends on is
    its third test -- the source line must have been wider than the box --
    because these panels fit their own third-party strings to their own tier
    width and HATCHES means its ellipsis. Without it this
    body reports 66 clipped lines it never lost a character to, measured.

    It used to do the arithmetic here, as ``region.width - 1`` on the panel,
    which is right only while the painting leaf sits flush against the
    panel's content edge. It does not on the ``4`` body next door, and a
    shipped clip hid in the two columns of difference.
    """
    out = []
    for cls in _POOL4_WIDGET_CLASSES.values():
        out.extend(_css_clipped_lines(app, screen.query_one(cls)))
    return out


def _pool4_marked(app, screen) -> set[str]:
    """Which pool4 panels have a ``‹`` marker lit, by class name.

    ``‹`` rather than ``‹ widen``: this body's rail panels fall back to a bare
    glyph when the title plus its network word plus the words no longer fit
    (``widgets/surf/_pool4.GLYPH_HINT``), and a check written against the
    long spelling alone would call a marked panel unmarked at exactly the
    widths where it is under most pressure.
    """
    return {
        name
        for name, cls in _POOL4_WIDGET_CLASSES.items()
        if "‹" in _region_text(app, screen.query_one(cls))
    }


# -- the swap itself ------------------------------------------------------


def test_the_bindings_are_refresh_and_the_two_view_toggles():
    """``c`` is still gone; ``l``, ``p``, ``4`` and ``escape`` are not a return of it.

    ``c`` existed only because the announce feed and the dev-activity panel
    shared one slot, and a key that hides half a screen still has nothing to
    offer this layout. ``l`` and ``p`` are a different shape of key: each
    swaps the *whole* dashboard body for an unrelated second view (curator's
    ``y``/``f`` precedent) and leaves the hero mounted above it.
    ``o``/``O`` sort the LEADERBOARD and are not a body toggle; nor is ``x``
    (2026-10-03), which folds THROUGHPUT's blocks inside the SWARM body.

    This replaces ``test_the_bindings_are_refresh_and_the_launchpad_toggle``
    rather than sitting beside it: two tests asserting different exact
    contents of one ``BINDINGS`` set cannot both pass, and the older one's
    ``keys == {"r", "l", "escape"}`` is the assertion this task changes.
    """
    keys = {binding.key for binding in SurfScreen.BINDINGS}
    assert keys == {"r", "l", "e", "4", "s", "a", "b", "i", "o", "O", "f", "x", "escape"}
    assert not hasattr(SurfScreen, "action_toggle_view"), (
        "the old c-swap action outlived its binding -- an action with no key "
        "is a surface nobody can reach and nobody maintains"
    )
    for action in ("action_toggle_launchpad", "action_toggle_pool4",
                   "action_toggle_pool4_user", "action_toggle_swarm",
                   "action_toggle_agent", "action_toggle_board", "action_set_seat",
                   "action_show_dashboard"):
        assert hasattr(SurfScreen, action), action


async def test_e_swaps_the_body_and_keeps_the_hero() -> None:
    async with _pool4_app().run_test() as pilot:
        await pilot.press("e")
        screen = pilot.app.screen
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is True
        assert screen.query_one(SurfHero).display is True
        assert screen.query_one("#middle-row").display is False
        assert screen.query_one("#separator").display is False
        assert screen.query_one("#bottom-row").display is False


async def test_escape_backs_out_of_the_pool4_body_too() -> None:
    async with _pool4_app().run_test() as pilot:
        await pilot.press("e")
        await pilot.press("escape")
        assert pilot.app.screen.query_one("#middle-row").display is True
        assert pilot.app.screen.query_one(f"#{POOL4_BODY_ID}").display is False


async def test_e_is_idempotent_and_toggles_back() -> None:
    async with _pool4_app().run_test() as pilot:
        await pilot.press("e")
        await pilot.press("e")
        assert pilot.app.screen.query_one("#middle-row").display is True
        assert pilot.app.screen.query_one(f"#{POOL4_BODY_ID}").display is False


async def test_p_no_longer_opens_the_pool4_body() -> None:
    """The owner moved the POOL4 protocol body from ``p`` to ``e`` (2026-09-15).

    Asserted from the keyboard, not off ``BINDINGS``: ``p`` pressed on the
    dashboard and on the ``4`` body changes nothing, and ``e`` from the same
    starting points does open the body. A leftover ``p`` binding would still
    work even though the hint no longer names it.
    """
    async with _pool4_app().run_test() as pilot:
        screen = pilot.app.screen
        await pilot.press("p")
        await pilot.pause()
        assert screen.query_one("#middle-row").display is True
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is False
        await pilot.press("4")
        await pilot.press("p")
        await pilot.pause()
        assert screen.query_one(f"#{POOL4_USER_BODY_ID}").display is True
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is False
        await pilot.press("e")
        await pilot.pause()
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is True


async def test_the_three_bodies_are_never_showing_at_once() -> None:
    """Exactly one body at a time, through every transition between them.

    This is the test for the edit ``_show_mode`` was most likely to receive:
    keeping the old ``launchpad = self._mode == MODE_LAUNCHPAD`` boolean and
    adding a second one beside it leaves the dashboard rows reading ``not
    launchpad``, which is **true** in MODE_POOL4 -- so ``p`` would paint the
    pool4 body on top of a dashboard body that never went away. Every
    assertion below passes under that mutation except the ones about
    ``#middle-row``, which is why the dashboard rows are checked on every
    hop rather than only on the way home.
    """
    bodies = ("#middle-row", f"#{LAUNCHPAD_BODY_ID}", f"#{POOL4_BODY_ID}")
    async with _pool4_app().run_test() as pilot:
        screen = pilot.app.screen
        for keys, expected in (
            ((), "#middle-row"),
            (("l",), f"#{LAUNCHPAD_BODY_ID}"),
            (("e",), f"#{POOL4_BODY_ID}"),
            (("l",), f"#{LAUNCHPAD_BODY_ID}"),
            (("escape",), "#middle-row"),
            (("e",), f"#{POOL4_BODY_ID}"),
            (("escape",), "#middle-row"),
        ):
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            showing = [b for b in bodies if screen.query_one(b).display]
            assert showing == [expected], (keys, showing)
            # ...and the hero is never part of any of it.
            assert screen.query_one(SurfHero).display is True


async def test_the_status_hint_names_both_views() -> None:
    """The phrase reaches a pixel, and reaches it as ONE ``Segment``.

    Two assertions, and the second one is the whole point. ``_screen_text``
    joins a strip's segments with ``""``, which is the right instrument for
    every other composited assertion in this file and is **blind to exactly
    the defect this test exists to catch**: a per-letter ``[dim]`` tag splits
    the hint into ``l`` / `` launchpad · `` / ``p`` / `` pool4`` and the
    row-joined text is byte-identical either way.

    Proven, not assumed. Mutating ``KEY_HINTS`` to
    ``"[dim]l[/] launchpad · [dim]p[/] pool4"`` left the row-join version of
    this test green; it is the segment check below that reddens.

    Why the segment boundary is the subject at all: the app-level acceptance
    grep in ``tests/test_surf_registration.py`` and the launchpad hint test
    above both join **every segment with a newline**, which is the join
    CLAUDE.md warns against for ordinary layout assertions precisely because
    it splits a styled row into several apparent lines. Here that is the
    measurement rather than the mistake -- the claim being made is "this
    phrase is one styled run", and a split is what makes those greps fail
    while the status bar looks perfectly correct on screen.
    """
    phrase = "l launchpad · 4 pl4"
    async with _pool4_app().run_test() as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = _screen_text(pilot.app)
        segments = [seg.text for strip in strips for seg in strip]

    assert phrase in text, (
        "the hint did not reach a pixel -- check the StatusBar had room for "
        "it at this width"
    )
    assert any(phrase in segment for segment in segments), (
        "the hint reaches the screen but is split across Segments: "
        "KEY_HINTS must be ONE markup run, not per-letter tags, or the "
        "app-level acceptance greps for the contiguous phrase fail while "
        "the bar itself looks right"
    )


async def test_the_pool4_key_hint_fits_the_status_bar_at_the_full_layout() -> None:
    """Measured against the bar's own budget, never counted.

    This hint is nine columns longer than the one that shipped, and the
    StatusBar's left label is the segment that loses characters when the bar
    runs out. Asserted at ``SURF_FULL_LAYOUT_COLUMNS`` -- the width the whole
    dashboard is documented to need -- and, one column at a time, over the
    band below it, so the test says *where* it stops fitting rather than only
    that it fits somewhere.

    Both halves of the phrase are checked. ``l launchpad`` alone survives
    several columns further than the whole hint does, so a test that only
    looked for the new half would call the row healthy while the old half
    had been cut off the other end.
    """
    async with _pool4_app().run_test(
        size=(SURF_FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "l launchpad · 4 pl4" in text

    # The band below it: find where the whole phrase stops reaching a pixel,
    # and assert that width is under the documented layout rather than over.
    lost_at = None
    for width in range(SURF_FULL_LAYOUT_COLUMNS, 79, -1):
        async with _pool4_app().run_test(size=(width, 46)) as pilot:
            await pilot.pause()
            if "l launchpad · 4 pl4" not in _screen_text(pilot.app):
                lost_at = width
                break
    assert lost_at is None or lost_at < SURF_FULL_LAYOUT_COLUMNS, (
        f"the key hint is already cut at {lost_at} columns, which is at or "
        f"above the documented {SURF_FULL_LAYOUT_COLUMNS} -- shorten the hint"
    )


# -- the body's shape and its dispatch ------------------------------------


async def test_the_pool4_body_holds_four_panels_in_two_columns() -> None:
    """Asserted on each container's own children, never on a screen-wide
    query: a panel mounted into the wrong column still answers ``query_one``
    from the screen and would leave this green.

    The order is the layout and both halves of it are deliberate. HATCHES
    leads the RAIL: plan section 5 R4's day-one state is *undiscovered*, and
    HATCHES is the panel that says so, so it sits at the top of its column
    rather than under a summary of numbers the view has not earned yet. The
    left column is THE SPLIT over THE RATCHET.

    **Four, not five, since 2026-09-14.** This was
    ``test_the_pool4_body_holds_five_panels_in_two_columns`` and its left
    column ended in the flow log; the owner removed POOL4 FLOW from ``p``
    because the ``4`` body's RECENT FLOW renders the same rows. The columns no
    longer balance -- 28 rows on the left against the rail's 34 at the worst
    payload -- so the rail alone is what ``SURF_POOL4_FULL_LAYOUT_ROWS`` is
    measured from.

    This docstring said "the rail stacks the three panels whose line count is
    a constant, which is what makes the pin the same number under every
    payload" until 2026-09-02. That property was real and is gone: mainnet's
    three-way split made THE SPLIT payload-sized as well.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}")
        rail = screen.query_one(f"#{POOL4_RAIL_ID}")
        assert [type(w) for w in left.children] == [
            SurfPool4Split, SurfPool4Ratchet,
        ]
        assert [type(w) for w in rail.children] == [
            SurfPool4Hatches, SurfPool4Vault,
        ]
        # ...and the two columns really are side by side, not stacked: the
        # child lists above are identical either way.
        assert left.region.right <= rail.region.x
        assert left.region.y == rail.region.y


#: How the two column ``#:`` blocks spell each panel, so the agreement test
#: below can compare prose against ``compose``.
#:
#: Hand-typed rather than derived from the class names: deriving it would
#: make the test reconstruct the very sentence it is checking, and it could
#: never fail. The prose names are the ones a reader sees on screen, which is
#: why the blocks use them.
_POOL4_PANEL_PROSE = {
    # "POOL4 FLOW" left this map on 2026-09-14 with the panel: the owner
    # removed it from the `p` body, so a column block that names it again is
    # naming a panel this body does not have, and should fail as unknown.
    "THE SPLIT": SurfPool4Split,
    "THE RATCHET": SurfPool4Ratchet,
    "HATCHES": SurfPool4Hatches,
    "sIMD VAULT": SurfPool4Vault,
}


def _pool4_column_block(constant: str) -> str:
    """The ``#:`` block immediately above *constant* in ``screens/surf.py``,
    as one whitespace-normalised string."""
    import re

    from maxpane_dashboard.screens import surf as surf_module

    source = Path(surf_module.__file__).read_text()
    lines = source.splitlines()
    index = next(
        i for i, line in enumerate(lines) if line.startswith(f"{constant} = ")
    )
    block: list[str] = []
    i = index - 1
    while i >= 0 and lines[i].startswith("#:"):
        block.append(lines[i][2:].strip())
        i -= 1
    return re.sub(r"\s+", " ", " ".join(reversed(block)))


@pytest.mark.parametrize(
    "constant,container_id",
    [("POOL4_LEFT_ID", POOL4_LEFT_ID), ("POOL4_RAIL_ID", POOL4_RAIL_ID)],
    ids=["left", "rail"],
)
async def test_the_pool4_column_blocks_name_the_panels_compose_builds(
    constant, container_id,
) -> None:
    """⚠ The recurring defect on this branch, turned into a red suite.

    ``POOL4_LEFT_ID`` and ``POOL4_RAIL_ID`` do not carry labels, they carry
    **reasoned blocks that argue why an arrangement is correct** -- and a
    persuasive wrong explanation is what the next reader trusts. CLAUDE.md's
    convention is that the ``#:`` block beside the code is the authority
    *because* it sits beside the code and cannot drift the way a copy in
    another file can. When the authority is the copy that drifted, a reader
    has no way to tell which half of the file to believe, and this file has
    a correct ``SURF_POOL4_FULL_LAYOUT_ROWS`` block three hundred lines away
    that would then be saying something incompatible.

    **It has drifted twice and been suspected a third time.** Once before the
    W3 follow-up, once when the mainnet rebalance recut the body, and once
    more as a false alarm from a reader working off a pre-edit copy -- which
    cost a round trip to refute and is its own argument for a check that
    answers in a second. Every one of those was a human noticing; none of
    them was a test.

    So the block's opening arrangement sentence is parsed and compared
    against what ``compose`` actually builds, per column, in order. The
    convention it pins is small and worth stating: **each column block leads
    with a bold run naming its panels top to bottom, joined by "over"**. A
    future rebalance that moves a panel and not the sentence fails here on
    the same commit rather than in someone's reading months later.

    What this does NOT check, said plainly so nobody mistakes its scope: the
    blocks' claims about which child carries the ``1fr``. That is guarded one
    layer down by
    ``test_the_pool4_rail_has_one_floored_fr_and_the_left_column_none``
    (``test_exactly_one_pool4_child_per_column_carries_the_fr`` until POOL4
    FLOW left the body on 2026-09-14), which reads
    ``minimal.tcss`` -- the copy that actually renders. Asserting the prose
    version here as well was tried and dropped: every phrasing that survived
    a paragraph reflow also passed for a sentence naming the wrong panel,
    which is the tests-that-cannot-fail shape this repo keeps a taxonomy of.
    """
    import re

    block = _pool4_column_block(constant)
    bold = re.search(r"\*\*(.+?)\*\*", block)
    assert bold, (
        f"{constant}'s block has no bold arrangement sentence -- the "
        "convention this test pins is that it leads with one"
    )
    named = [part.strip(" .`") for part in bold.group(1).split(" over ")]
    unknown = [n for n in named if n not in _POOL4_PANEL_PROSE]
    assert not unknown, (
        f"{constant}'s block names {unknown}, which is not a panel on this "
        f"body -- known names are {sorted(_POOL4_PANEL_PROSE)}"
    )

    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        built = [
            type(w) for w in pilot.app.screen.query_one(f"#{container_id}").children
        ]

    assert [_POOL4_PANEL_PROSE[n] for n in named] == built, (
        f"{constant}'s block says the column is {named}, but compose builds "
        f"{[c.__name__ for c in built]}. The block is not a label, it is the "
        "argument for the layout -- correct it in the same change that moved "
        "the panel, and record the drift rather than overwriting it"
    )


#: Every pool4 payload key whose contract is a CLOSED vocabulary, mapped to
#: the tuple it must draw from -- scalars first, then the fields on row
#: payloads.
#:
#: Hand-typed, on this file's standing rule: deriving the map from the
#: contract would make the sweep below compare the vocabulary against itself.
#: The names are imported, so a RENAMED vocabulary fails at import; only the
#: key-to-vocabulary pairing is restated.
_POOL4_CLOSED_VOCABULARIES = {
    "pool4_network": POOL4_NETWORKS,
    "pool4_discovery_state": POOL4_DISCOVERY_STATES,
    "pool4_discovery_source": POOL4_DISCOVERY_SOURCES,
    "pool4_counter_state": POOL4_COUNTER_STATES,
    "pool4_reward_path": POOL4_REWARD_PATHS,
}
_POOL4_ROW_VOCABULARIES = {
    "pool4_flow": {"side": POOL4_FLOW_SIDES},
    "pool4_hatches": {
        "scope": POOL4_HATCH_SCOPES,
        "label": POOL4_HATCH_LABELS,
        "state": POOL4_HATCH_STATES,
    },
}


def _all_pool4_fixtures() -> dict[str, dict]:
    """Every pool4 payload this module hands to a real screen."""
    return {
        "_pool4_payload": _pool4_payload(),
        "_mainnet_pool4_payload": _mainnet_pool4_payload(),
        "_ordinary_pool4_payload": _ordinary_pool4_payload(),
        "_pool4_hatch_payload(0)": _pool4_hatch_payload(0),
        "_pool4_hatch_payload(10)": _pool4_hatch_payload(10),
        "_pool4_hatch_payload(12)": _pool4_hatch_payload(12),
        **{
            f"_POOL4_HEIGHT_PAYLOADS[{name!r}]": build()
            for name, build in _POOL4_HEIGHT_PAYLOADS.items()
            if build() is not None
        },
    }


def test_every_closed_vocabulary_fixture_value_is_a_member() -> None:
    """⚠ A fixture may not invent a word, and nothing checked that until now.

    WP0's agreement tests pin that each closed vocabulary and its renderers
    agree. **Neither direction looks at a fixture**, so a payload built here
    with a word that is in no vocabulary satisfied every existing guard: the
    key is present, correctly named, dispatched, and declared by its panel,
    so the kwarg sweep, the renderer-count sweep and the swallow check are
    all green. Only a vocabulary check or a rendered-output diff can see that
    the value means nothing.

    That is S21's lesson reaching a new layer. S21 was a key that reached no
    *renderer*; this is a key that reaches its renderer carrying a word the
    renderer cannot interpret, which is worse, because the panel then
    exercises its own unknown branch while the fixture's name says otherwise.

    **It had two live instances, and this test was written because of them.**
    ``_pool4_payload`` carried ``"two-way"`` and ``_mainnet_pool4_payload``
    carried ``"three-way"``; ``POOL4_REWARD_PATHS`` is
    ``("direct", "via-distributor")``. Both words describe the SPLIT's shape
    rather than the TOPOLOGY the key carries, and the comment beside the
    first one said "the reward path is the two-way one", which is why it read
    as correct on every re-read. ``SurfPool4Split`` treats an unrecognised
    path as unknown and annotates nothing -- deliberately, because guessing
    either way is the 3x error between the 4.5% staker leg and the 15% reward
    share -- so the mainnet fixture rendered
    ``measured stakers 9.89%`` where it should have rendered
    ``measured stakers 9.89% (staking leg)``, on the one line whose whole job
    is to say which leg the reader is looking at.

    ``None`` is skipped rather than rejected: it is the honest "not read" or
    "no such thing" on several of these keys, and the vocabularies
    deliberately exclude it.
    """
    offenders: list[str] = []
    for name, payload in _all_pool4_fixtures().items():
        for key, vocabulary in _POOL4_CLOSED_VOCABULARIES.items():
            value = payload.get(key)
            if value is not None and value not in vocabulary:
                offenders.append(
                    f"{name}[{key!r}] = {value!r}, not one of {vocabulary}"
                )
        for key, fields in _POOL4_ROW_VOCABULARIES.items():
            for index, row in enumerate(payload.get(key) or ()):
                for field, vocabulary in fields.items():
                    value = row.get(field)
                    if value is not None and value not in vocabulary:
                        offenders.append(
                            f"{name}[{key!r}][{index}][{field!r}] = {value!r}, "
                            f"not one of {vocabulary}"
                        )

    assert not offenders, (
        "fixture values outside their closed vocabulary -- the panel will "
        "render its unknown branch while this fixture's name claims "
        "otherwise:\n  " + "\n  ".join(offenders)
    )


def test_the_two_pool4_fixtures_disagree_about_the_reward_path() -> None:
    """The premise the sweep above cannot supply, and without it the fix is
    only half checked.

    Both fixtures could be corrected to the *same* member and stay green
    there -- but the Sepolia fixture exists to be the ``direct`` deployment
    and the mainnet one to be the ``via-distributor`` deployment, which is
    the whole reason the pair is swept side by side. A fix that collapsed
    them onto one word would lose the case the key exists for.
    """
    assert _pool4_payload()["pool4_reward_path"] == "direct"
    assert _mainnet_pool4_payload()["pool4_reward_path"] == "via-distributor"
    # ...and the topology really is the thing that differs, not just a string:
    assert _pool4_payload()["pool4_distributor_addr"] is None
    assert _mainnet_pool4_payload()["pool4_distributor_addr"] is not None


async def test_every_pool4_panel_is_dispatched_before_p_is_pressed() -> None:
    """Composed-once-shown-by-``display``: the first ``p`` paints a complete
    frame, not a blank one that fills in a beat later.

    Checked on the widgets' own stored payloads while the body is still
    hidden -- a hidden widget reaches no compositor row at all, so there is
    nothing to read off the screen -- and then on composited output once
    ``p`` has been pressed, because a panel that stored a payload and
    rendered nothing would satisfy the first half alone.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is False
        for name, cls in _POOL4_WIDGET_CLASSES.items():
            assert screen.query_one(cls)._payload, (
                f"{name} was not dispatched while the body was hidden -- the "
                "first `p` will paint it blank"
            )
        await pilot.press("e")
        await pilot.pause()
        text = _screen_text(pilot.app)

    for title in ("HATCHES", "THE SPLIT", "THE RATCHET", "sIMD VAULT"):
        assert title in text, title
    # The payload, not just the titles -- a dispatched panel rendering its
    # empty state would satisfy the four checks above. `SELL` was the third
    # value here, off POOL4 FLOW, until the owner removed that panel from `p`
    # on 2026-09-14; THE SPLIT's and sIMD VAULT's values still prove two
    # panels in different columns rendered their payload, not a placeholder.
    assert "SELL" not in text
    assert "89.10%" in text and "1.302986" in text


async def test_every_pool4_panel_titles_the_network_it_is_showing() -> None:
    """Plan section 5 R4, and it is a hard failure rather than a cosmetic one.

    There is no pool4 hook on mainnet, so what runs on day one is discovery
    finding nothing and every panel rendering **Sepolia** numbers. A testnet
    number on an unmarked panel is not merely stale, it is fiction presented
    as live -- so the network word rides every panel's own title, not a
    footnote and not a status-bar mention, and all of them have to agree
    (four since POOL4 FLOW left the body on 2026-09-14; its title is checked
    in the ``4`` body now).

    Asserted per panel region rather than on the whole screen: ``SEPOLIA``
    appearing four times anywhere would pass a screen-wide count while three
    panels went networkless.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        for name, cls in _POOL4_WIDGET_CLASSES.items():
            region = _region_text(pilot.app, screen.query_one(cls))
            assert "SEPOLIA" in region, (
                f"{name} does not name the network its numbers came from"
            )
            assert "MAINNET" not in region, name


async def test_a_dead_pool4_sweep_leaves_every_panel_explicit() -> None:
    """No blank panel, no stale number presented as live.

    The whole-payload outage: every pool4 key ``None``, which is what a tier
    that has never landed looks like. Each panel must say so in its own
    words, and the network word falls back to the em dash rather than
    guessing a chain.

    **Four unavailable lines, not five, since 2026-09-14.** POOL4 FLOW's was
    one of them until the owner removed that panel from ``p`` as a duplicate
    of the ``4`` body's RECENT FLOW. Its line is now asserted absent from
    this body, so a flow panel that came back here would redden this test.
    The ``4`` body's own outage state is pinned in
    ``tests/test_surf_registration.py``.
    """
    from maxpane_dashboard.widgets.surf.pool4_flow import (
        UNAVAILABLE_LINE as FLOW_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.pool4_hatches import (
        UNAVAILABLE_LINE as HATCHES_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.pool4_ratchet import (
        UNAVAILABLE_LINE as RATCHET_UNAVAILABLE,
    )
    from maxpane_dashboard.widgets.surf.pool4_vault import (
        UNAVAILABLE_LINE as VAULT_UNAVAILABLE,
    )

    payload = _frozen_payload(**{key: None for key in POOL4_KEYS})
    async with _pool4_app(payload).run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("e")
        await pilot.pause()
        text = _screen_text(pilot.app)
    for line in (HATCHES_UNAVAILABLE, RATCHET_UNAVAILABLE, VAULT_UNAVAILABLE):
        assert line in text, line
    assert FLOW_UNAVAILABLE not in text, (
        "POOL4 FLOW's unavailable line composited on the `p` body, which has "
        "not carried that panel since 2026-09-14"
    )
    # The network word is the em dash, not a guessed chain.
    assert "SEPOLIA" not in text and "MAINNET" not in text


async def test_a_quiet_pool4_sweep_is_not_a_dead_one() -> None:
    """``[]`` and ``None`` must not composite to the same sentence.

    This is CLAUDE.md's FARM/HOUR-SAVED rule at the screen level: a swept-
    and-quiet window and a read that failed are different facts, and a panel
    that renders them identically reads confident and green through an
    outage. The widget's own tests pin the two strings; this pins that the
    *screen* hands the widget the distinction rather than flattening it on
    the way (``data.get`` returns ``None`` for a missing key and ``[]`` for
    an empty one, and only one of those is an outage).

    **Read off the ``4`` body since 2026-09-14.** It pressed ``p`` until the
    owner removed POOL4 FLOW from that body as a duplicate of RECENT FLOW. The
    claim is about the screen's dispatch of ``pool4_flow``, which is
    unchanged, so the test keeps its name and moves to the one body that
    still composites the panel.
    """
    from maxpane_dashboard.widgets.surf.pool4_flow import (
        EMPTY_LINE, UNAVAILABLE_LINE,
    )

    async with _pool4_app(_frozen_payload(pool4_flow=[])).run_test(
        size=(150, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("4")
        await pilot.pause()
        quiet = _screen_text(pilot.app)
    async with _pool4_app(_frozen_payload(pool4_flow=None)).run_test(
        size=(150, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("4")
        await pilot.pause()
        dead = _screen_text(pilot.app)

    assert EMPTY_LINE in quiet and UNAVAILABLE_LINE not in quiet
    assert UNAVAILABLE_LINE in dead and EMPTY_LINE not in dead


# -- the p body's own measured width (2026-09-01) -------------------------
#
# ``SURF_FULL_LAYOUT_COLUMNS`` (this screen, 143),
# ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`` (the ``l`` body, 138) and
# ``__main__.FULL_LAYOUT_COLUMNS`` (the app, 143) are all untouched by this
# task -- the measurement, the binding panel, the per-seam table and why the
# CLAUDE.md width record is not appended to are in
# ``SURF_POOL4_FULL_LAYOUT_COLUMNS``' own docstring in ``screens/surf.py``.
#
# The sweep runs **86..152**: thirteen columns below the measured 99 and
# fifty-three above it, never starting at it, and crossing the old 106 and
# BOTH neighbouring pins (138 and 143) so agreeing with any of them would have
# to show up as a sweep result. It ran 96..152 against the old pin of 106 and
# was re-centred downward on 2026-09-14, when POOL4 FLOW left the body and the
# pin fell to 99: 96 would have left only three widths under the new pin.


@pytest.mark.parametrize(
    "payload", [None, "ordinary"],
    ids=["committed-capture", "ordinary-magnitudes"],
)
#: Boundary set (2026-09-19): the band still crosses both neighbouring pins
#: (138 and 143), as the block above says it must. See tests/screens/_sweeps.py.
@pytest.mark.parametrize(
    "width",
    boundary_set(
        SURF_POOL4_FULL_LAYOUT_COLUMNS, 86, 152,
        SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, SURF_FULL_LAYOUT_COLUMNS,
    ),
)
async def test_the_pool4_body_is_whole_from_its_pinned_width(
    width, payload
) -> None:
    """Start the sweep away from the pin: one that began at the constant
    would agree with it by construction.

    **Whole means the whole body, not merely the panels that can say so.**
    Both halves are asserted at and above the pin -- no marker anywhere *and*
    no CSS-clipped line anywhere -- because a seam whose binder went quiet
    would satisfy the marker half alone. Below the pin the claim is the
    marker's: something must be asking for the columns.

    **Swept against two payload magnitudes**, on
    ``_ordinary_burn_payload``'s reasoning (``test_surf_launchpad_screen.py``). It does not move a
    single number here, and *that* is the result worth having: this panel's
    columns are floored at their own header labels, so the widest data cell
    never exceeds them. A capture-only sweep could not have told the
    difference between "the width does not move with the data" and "we only
    ever measured one payload".

    The dashboard body's own markers cannot contaminate this: ``#middle-row``
    is hidden in MODE_POOL4, so nothing it composites reaches the screen.
    """
    pl = _ordinary_pool4_payload() if payload == "ordinary" else None
    async with _pool4_app(pl).run_test(size=(width, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        marked = _pool4_marked(pilot.app, screen)
        clipped = _clipped_pool4_lines(pilot.app, screen)
        if width >= SURF_POOL4_FULL_LAYOUT_COLUMNS:
            assert not marked, (width, marked)
            assert not clipped, (
                f"at {width} the p body is clipping a line and nothing on "
                f"screen says so: {clipped}"
            )
        else:
            assert marked, width


#: Boundary set (2026-09-19): 96 is where the docstring says clipping stops
#: on the pinned seam. See tests/screens/_sweeps.py.
@pytest.mark.parametrize(
    "width",
    boundary_set(
        SURF_POOL4_FULL_LAYOUT_COLUMNS - 1, 80, SURF_POOL4_FULL_LAYOUT_COLUMNS - 1, 96,
    ),
)
async def test_nothing_below_the_pool4_pin_clips_without_saying_so(
    width,
) -> None:
    """Below the pin the only panel allowed to lose anything is one that
    advertises the loss.

    The sibling sweep above only checks that *something* is marked below the
    pin, which stays green even if the marked panel and the clipping panel
    are different widgets. This is the half that would catch that, and it is
    also the half that would catch a future rail panel losing its marker: it
    asks, per width, whether every CSS-clipped line has a marker somewhere on
    the body to account for it.

    **The range starts at 80, well under the pin's neighbourhood**, because
    on the pinned seam nothing clips anywhere between 96 and 105 -- the whole
    point of choosing it -- so a sweep confined to those widths would execute
    its ``if`` body zero times and be a guard with no positive behind it.
    """
    async with _pool4_app().run_test(size=(width, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        clipped = _clipped_pool4_lines(pilot.app, screen)
        if clipped:
            assert _pool4_marked(pilot.app, screen), (
                f"at {width} the p body clips {clipped} and no panel on "
                "screen advertises the loss"
            )


async def test_the_pool4_binding_panel_is_hatches() -> None:
    """Pinned by a test, not by a sentence.

    **Rewritten on 2026-09-14, when the owner removed POOL4 FLOW from this
    body** ("it already is covered in the market view now (4)"). Until then
    this was ``test_the_pool4_binding_panel_is_the_flow_log``: the left column
    needed FLOW's 53, and under 1:1 the flow log was the only marked panel one
    column under 106. With FLOW gone the left column needs THE RATCHET's 45
    and the rail HATCHES' 50, so under the same, un-re-cut 1:1 seam the RAIL
    binds. One column under the new pin, HATCHES is the only panel with
    anything to say, on every payload magnitude the re-sweep ran (86..125:
    the committed capture, the ordinary magnitudes, mainnet with twelve
    levers).

    It is asserted separately from the pin because two seams can collect
    one pin with different panels binding it, and because "a panel that can
    bind must be able to mark" is a claim about *this* panel. HATCHES'
    marker is appended to a title, which is the first place a narrow panel
    gives one up -- the reason the old seam kept it out of the binder role.
    """
    async with _pool4_app().run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS - 1, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        marked = _pool4_marked(pilot.app, pilot.app.screen)
    assert marked == {"SurfPool4Hatches"}, marked


async def test_the_pool4_pin_is_the_sum_of_the_needs_it_claims() -> None:
    """The pin's *derivation*, not just its threshold.

    The sweep above can only see the resulting number, so it stays green if
    the two column needs the docstring names swapped, drifted, or were never
    true. Measured at the pin itself, where 1:1 gives the rail -- the binder
    -- exactly its 50 (an odd width's odd column goes to the rail) and the
    left column 49.

    **The margin changed sides on 2026-09-14, and this is where that is
    asserted.** The seam was chosen to buy the RAIL three columns of margin
    while FLOW bound the left column with none. The owner removed FLOW from
    this body, so the rail now binds with zero margin and four spare columns
    sit in the left column over THE RATCHET's 45. Both are asserted as
    numbers, so a seam change or a panel growing a column shows up here
    rather than as a silent shift in which half is thin.

    ``POOL4_LEFT_NEED``/``POOL4_RAIL_NEED`` are hand-typed literals here
    rather than imported from the screen: deriving them from the constant
    they explain would make this compare a number with itself.
    """
    async with _pool4_app().run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}").region.width
        rail = screen.query_one(f"#{POOL4_RAIL_ID}").region.width

    assert rail == POOL4_RAIL_NEED, (
        f"the rail gets {rail} columns at the pin, not the "
        f"{POOL4_RAIL_NEED} its binder needs -- re-derive it"
    )
    assert left >= POOL4_LEFT_NEED
    assert left - POOL4_LEFT_NEED == 4, (
        f"the left column's margin is {left - POOL4_LEFT_NEED}, not the four "
        "it was measured at when POOL4 FLOW left the body (2026-09-14). It "
        "was zero while FLOW bound this column at 53"
    )
    # ...and the pin really is what those two needs add up to under this
    # seam, which is the arithmetic the docstring's per-seam table rests on.
    assert left + rail == SURF_POOL4_FULL_LAYOUT_COLUMNS
    assert MEASURED_POOL4_COLUMNS == SURF_POOL4_FULL_LAYOUT_COLUMNS


def test_the_pool4_body_fits_inside_the_documented_app_width() -> None:
    """The standing rule, asserted rather than assumed: a body measured wider
    than ``__main__.FULL_LAYOUT_COLUMNS`` means shortening a value, never
    raising the app's number.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_POOL4_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_POOL4_FULL_LAYOUT_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS
    # Three bodies, three independently measured pins. They are allowed to
    # be equal -- but if two of them ever ARE equal it should be because
    # somebody measured it, so the constants are kept separate and this is
    # the note that says so rather than a test forbidding the coincidence.
    assert SURF_POOL4_FULL_LAYOUT_COLUMNS != SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS


# -- the p body's own measured height (2026-09-01, re-swept 2026-09-02) ---
#
# The sweep runs 36..55 -- nine rows below the measured 45 and ten above,
# never starting at it, and never starting at the 44 it replaced either. It
# has been re-centred three times as the pin moved (43 -> 46 -> 44 -> 45);
# the rule is that the range straddles the pin generously and never begins on
# it, not that the endpoints are fixed.


#: The payloads the height sweep runs, and the last one is the pin's own.
#:
#: **The network dimension is not decoration.** Every Sepolia body here fits
#: in 43 or less -- the twelve-lever one needs exactly 43 -- so a sweep of
#: Sepolia payloads alone can say nothing about a pin of 44 from underneath,
#: and the first version of this test after the mainnet re-sweep made its
#: below-the-pin claim against ``_pool4_hatch_payload(12)`` for exactly that
#: reason and passed at 43 with the pin one row above it. THE SPLIT is three
#: rows taller on mainnet, so ``mainnet-capped`` is the body the pin actually
#: describes and is the only payload the below-the-pin branch may assert on.
_POOL4_HEIGHT_PAYLOADS = {
    "ten-levers": lambda: None,
    "no-levers": lambda: _pool4_hatch_payload(0),
    "capped-levers": lambda: _pool4_hatch_payload(12),
    "mainnet-capped": lambda: _mainnet_pool4_payload(
        pool4_hatches=_pool4_hatch_payload(12)["pool4_hatches"]
    ),
}


@pytest.mark.parametrize("payload_name", sorted(_POOL4_HEIGHT_PAYLOADS))
#: Boundary set (2026-09-19): 43 is the height every Sepolia body fits in
#: (the block above). See tests/screens/_sweeps.py.
@pytest.mark.parametrize(
    "rows", boundary_set(SURF_POOL4_FULL_LAYOUT_ROWS, 36, 55, 43)
)
async def test_the_pool4_body_is_whole_from_its_pinned_height(
    rows, payload_name
) -> None:
    """150 columns is comfortably past the width pin, so nothing here is
    measuring a width.

    **The two halves are not symmetric, and that asymmetry is the pin's
    definition rather than a weakness in the test.** At and above the pin
    EVERY payload must fit -- that is what "the body is whole from here"
    claims, and it is checked for all three. Below the pin only the payload
    the pin was measured against need overflow: a body with no levers at all
    is fourteen rows shorter and legitimately fits at 42, so asserting the
    marker lit below the pin for every payload would be asserting that a
    small payload must pretend not to fit.

    That is exactly what the first version of this test did after the
    mainnet re-sweep, and it failed on six parametrisations for the right
    reason -- the pin had become a worst case over payloads where it used to
    be a constant, and the sweep had not been told.

    So the below-the-pin claim is made against ``mainnet-capped``, which is
    the worst case the widgets can render and therefore the payload the pin
    actually describes. It was made against the *Sepolia* capped-lever list
    until 2026-09-02, and that was a second version of the same mistake one
    dimension over: a twelve-lever Sepolia body needs 43, so it fits one row
    below a 44 pin and the "the pin is tight" half of this test was asserting
    something false about the right layout.
    """
    payload = _POOL4_HEIGHT_PAYLOADS[payload_name]()
    async with _pool4_app(payload).run_test(size=(150, rows)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()
        text = _screen_text(pilot.app)

    if rows >= SURF_POOL4_FULL_LAYOUT_ROWS:
        assert TALLER_HINT not in text, (rows, payload_name)
    elif payload_name == "mainnet-capped":
        assert TALLER_HINT in text, (rows, payload_name)


async def test_the_pool4_height_pin_is_measured_against_the_column_it_describes() -> None:
    """The pin's *derivation*, not just its threshold.

    **Measured below the pin, not at it.** The rail's ``1fr`` child grows on
    a terminal with rows to spare, so at the pin itself that column reports
    the body's own height and the content the docstring derives is nowhere on
    screen. At 34 rows the rail sits on its floor and each column's
    ``virtual_size`` is its real content.

    The binder switched with the payload while the left column held
    THE SPLIT, THE RATCHET and the flow log's floor: that column bound on
    mainnet and on a short lever list, and the rail bound once the hatch
    list was long. **Since 2026-09-14 the rail binds on both payloads
    measured here.** The owner removed POOL4 FLOW from this body as a
    duplicate of the ``4`` body's RECENT FLOW, and the left column's content
    fell to 28 rows on mainnet and 25 on the capture. The assertion stays on
    the *worst case over payloads* -- 34, which is what the pin actually is.

    **``mainnet-capped`` joined the payload list on the same day, and the
    removal is why.** The two payloads above used to reach 34 through
    mainnet's LEFT column, which tied the rail. Without FLOW, this test's
    first run after the removal measured the worst of those two at **33**
    (Sepolia's twelve-lever rail; plain mainnet's ten-lever rail is 32). The
    pin had not moved -- ``test_the_pool4_height_pin_covers_every_payload_the_widgets_render``
    still finds 44 lit and 45 whole on ``mainnet-capped``. What had gone is
    this test's route to the pin's own binder: mainnet's rail at the
    twelve-lever cap. So that payload is measured here directly, rather than
    the expected 34 being lowered to whatever these two payloads now give.
    """
    worst = 0
    for label, payload in (
        ("sepolia-12-levers", _pool4_hatch_payload(12)),
        ("mainnet", _mainnet_pool4_payload()),
        ("mainnet-capped", _mainnet_pool4_payload(
            pool4_hatches=_pool4_hatch_payload(12)["pool4_hatches"]
        )),
    ):
        async with _pool4_app(payload).run_test(size=(150, 34)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            await pilot.pause()
            screen = pilot.app.screen
            left = screen.query_one(f"#{POOL4_LEFT_ID}")
            rail = screen.query_one(f"#{POOL4_RAIL_ID}")
            assert left.size.height < left.virtual_size.height or \
                rail.size.height < rail.virtual_size.height, (
                    f"{label}: 34 rows no longer squeezes the body, so both "
                    "columns report the terminal's height and this test is "
                    "measuring nothing"
                )
            worst = max(worst, left.virtual_size.height,
                        rail.virtual_size.height)
            chrome = pilot.app.size.height - left.size.height

    assert worst == 34, (
        f"the body's worst-case content is {worst} rows, not the 34 the pin "
        "is derived from -- re-sweep it"
    )
    assert worst + chrome == SURF_POOL4_FULL_LAYOUT_ROWS
    assert MEASURED_POOL4_ROWS == SURF_POOL4_FULL_LAYOUT_ROWS


async def test_the_pool4_height_pin_covers_every_payload_the_widgets_render() -> None:
    """The property that REPLACED "the pin does not move with the payload".

    That claim was true while every panel whose line count answered to the
    data was kept out of the binding column. Mainnet ended it: THE SPLIT is
    12 rows on Sepolia and 15 on mainnet, HATCHES is 13 to 24 rows depending
    on the lever list, and any two-column arrangement of these five panels
    puts one of them in the binder. Asserting the old property now would be
    asserting something the layout cannot deliver, and quietly dropping it
    would leave the pin covering whichever payload somebody happened to
    sweep.

    So the claim is the honest one: the pin covers the WORST case over every
    payload the widgets can render -- including the twelve-lever list at
    ``pool4_hatches.MAX_ROWS``, which is above what the producer emits today
    and is exactly the case a pin measured against "the state the data is in"
    would have missed.
    """
    from maxpane_dashboard.widgets.surf.pool4_hatches import MAX_ROWS

    heights: dict[str, int] = {}
    for label, payload in (
        ("no-levers", _pool4_hatch_payload(0)),
        ("ten-levers", _pool4_hatch_payload(10)),
        ("capped-levers", _pool4_hatch_payload(MAX_ROWS)),
        ("mainnet", _mainnet_pool4_payload()),
        # The worst case, and the one the tightness probe below uses -- the
        # two halves have to be about the same body or "fits at the pin, not
        # one row under it" is a claim about two different layouts.
        ("mainnet-capped", _mainnet_pool4_payload(
            pool4_hatches=_pool4_hatch_payload(MAX_ROWS)["pool4_hatches"]
        )),
    ):
        async with _pool4_app(payload).run_test(
            size=(150, SURF_POOL4_FULL_LAYOUT_ROWS)
        ) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            await pilot.pause()
            text = _screen_text(pilot.app)
            assert TALLER_HINT not in text, (
                f"{label}: the body does not fit at its own pinned height"
            )
            heights[label] = pilot.app.screen.query_one(
                SurfPool4Hatches
            ).region.height

    # The premise: the hatch count really is changing the panel, or the four
    # cases above are one case measured four times.
    assert heights["no-levers"] < heights["ten-levers"] < \
        heights["capped-levers"], heights
    # ...and one row below the pin, the worst of them does NOT fit -- so the
    # pin is tight rather than merely generous.
    #
    # THE WORST PAYLOAD IS MAINNET'S, not the capped Sepolia list this used
    # to probe: THE SPLIT is 15 rows on mainnet against 12 on Sepolia, which
    # is three of the four rows separating a Sepolia body that fits in 43
    # from a mainnet one that needs 44. Probing the Sepolia list here asked
    # whether a body the pin does not describe fits one row under it, and
    # the honest answer was yes.
    worst_payload = _mainnet_pool4_payload(
        pool4_hatches=_pool4_hatch_payload(MAX_ROWS)["pool4_hatches"]
    )
    async with _pool4_app(worst_payload).run_test(
        size=(150, SURF_POOL4_FULL_LAYOUT_ROWS - 1)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()
        assert TALLER_HINT in _screen_text(pilot.app), (
            "the body still fits one row below the pin -- the pin is loose"
        )


async def test_the_pool4_floors_never_thin_a_panel_below_its_content() -> None:
    """``min-height`` on a ``1fr`` child is load-bearing, not decoration --
    and the two columns pick their ``1fr`` child by different rules.

    A ``1fr`` child cannot overflow a scroll container, it SHRINKS, so one
    given fewer rows than its content loses them with no scrollbar, no
    ``‹ widen`` and no other trace **unless it scrolls inside itself**. None
    of this body's four panels does. So:

    * THE SPLIT and THE RATCHET are ``auto`` and the left column has **no**
      ``1fr`` child, so both are exactly their content at every height. That
      bullet read "FLOW may be squeezed to its floor of 6" until 2026-09-14,
      when the owner removed POOL4 FLOW from this body as a duplicate of the
      ``4`` body's RECENT FLOW. Its floor went with it, and what replaced it
      is the stronger claim that nothing in the left column is ever shrunk;
    * ``sIMD VAULT`` carries the rail's ``1fr`` **because its line count is a
      constant**, so ``min-height: 10`` is both floor and ceiling and it can
      never be cut. Asserted against its content, not against the constant:
      a panel that grew an eleventh line would fail here rather than lose it;
    * HATCHES is ``auto`` and is therefore never shrunk at all, at any
      height, under any lever count -- which is the assertion that would have
      caught the arrangement this one replaced, where HATCHES carried the
      rail's ``1fr`` and silently lost two rows of a twelve-lever payload in
      the narrow window before the column began to scroll.

    Asserted on laid-out heights and on the marker, never on composited
    cells: a floored panel the column has scrolled past composites *zero*
    rows, correctly, and ``‹ taller`` is what says so.
    """
    async with _pool4_app(_pool4_hatch_payload(12)).run_test(
        size=(150, 24)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}")
        vault = screen.query_one(SurfPool4Vault)
        hatches = screen.query_one(SurfPool4Hatches)

        # The left column holds no flow log any more (2026-09-14) -- so no
        # `1fr` and no floor -- and both panels in it are never shrunk. At
        # 24 rows the column scrolls, and a panel the column has scrolled
        # past is still laid out at its full height, so region == content is
        # the claim at every height rather than only at roomy ones.
        assert not list(left.query(SurfPool4Flow)), (
            "a flow log is back in the `p` body's left column"
        )
        for panel in (left.query_one(SurfPool4Split),
                      left.query_one(SurfPool4Ratchet)):
            assert panel.region.height == panel.virtual_size.height, (
                f"{type(panel).__name__} is {panel.region.height} rows "
                f"against {panel.virtual_size.height} of content: it is being "
                "shrunk, so something in the left column took a `1fr` and "
                "this `Static` is losing rows with nothing on screen saying so"
            )
        assert vault.region.height >= vault.virtual_size.height, (
            f"sIMD VAULT is {vault.region.height} rows against "
            f"{vault.virtual_size.height} of content -- the panel chosen for "
            "the rail's 1fr because it cannot be cut is being cut"
        )
        assert hatches.region.height == hatches.virtual_size.height, (
            f"HATCHES is {hatches.region.height} rows against "
            f"{hatches.virtual_size.height} of content: it is being shrunk, "
            "so it is no longer `height: auto` and its rows are being lost "
            "with nothing on screen saying so"
        )
        # The floors are only honest if the overflow they create is visible.
        # Without this the assertions above are green in a state where half
        # the body reaches the screen as nothing at all.
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]
        assert (
            screen.query_one(f"#{POOL4_LEFT_ID}").show_vertical_scrollbar
            or screen.query_one(f"#{POOL4_RAIL_ID}").show_vertical_scrollbar
        ), "neither column is scrolling, so the floors are not being tested"


# -- the blank row under every `p`-body title -----------------------------


#: The panels of the ``p`` POOL4 body, with the container each one is
#: mounted in -- **four** since 2026-09-14. ``SurfPool4Flow`` was the fifth
#: case until the owner removed it from this body as a duplicate of the ``4``
#: body's RECENT FLOW; its blank-row case lives on in
#: ``test_every_market_panel_paints_a_blank_row_under_its_title``, where the
#: panel still renders. The container stays in each entry: it is what made
#: the flow case measure the right instance while the class was mounted twice,
#: and Textual's ``query_one`` still returns the first match rather than
#: raising on several.
_POOL4_PANELS = (
    (SurfPool4Split, POOL4_LEFT_ID),
    (SurfPool4Ratchet, POOL4_LEFT_ID),
    (SurfPool4Hatches, POOL4_RAIL_ID),
    (SurfPool4Vault, POOL4_RAIL_ID),
)


@pytest.mark.parametrize(
    "cls, container_id", _POOL4_PANELS, ids=[c.__name__ for c, _ in _POOL4_PANELS]
)
async def test_every_pool4_panel_paints_a_blank_row_under_its_title(
    cls, container_id
) -> None:
    """The repo-wide convention, on the body that used to be exempt from it.

    ``ActivityFeed > .feed-title`` and five siblings carry ``margin: 0 0 1 0``
    in ``minimal.tcss``; the ``4`` market body took the same row on
    2026-09-12 (``test_every_market_panel_paints_a_blank_row_under_its_title``,
    the sibling this is modelled on) and this body was the last holdout,
    filed as **F10b** on the argument that its 44-row pin could not afford it.
    It could: the pin moved to 45, which is one row, and
    ``SURF_POOL4_FULL_LAYOUT_ROWS`` carries the measurement.

    **PARAMETRISED PER PANEL, NOT LOOPED.** A single test looping over the
    five would stop at the first failure and report one panel when three were
    broken -- and worse, a fix that satisfied the first would turn the suite
    green with the rest still flush. Five cases, five independent verdicts.

    **Two mechanisms, one contract.** Four of these panels paint their title
    and their body into ONE ``Static``, so their blank row is a rendered
    ``Text("")`` and no CSS margin could produce it; ``SurfPool4Flow`` has a
    separate title ``Static`` and takes the margin. That is exactly why the
    assertion is made against **composited output on the real screen** rather
    than against either source: it is the only question that is the same
    question for both shapes, and the app stylesheet outranks a widget's
    ``DEFAULT_CSS`` so nothing short of a pixel is evidence.

    Row 0 title, row 1 blank, row 2 content. The third assertion is what
    stops this passing on a panel that has simply gone dark, and the height
    is comfortably past the pin so no panel here is scrolled or floored.
    """
    payload = _mainnet_pool4_payload(
        pool4_hatches=_pool4_hatch_payload(12)["pool4_hatches"]
    )
    async with _pool4_app(payload).run_test(size=(150, 60)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()
        container = pilot.app.screen.query_one(f"#{container_id}")
        found = list(container.query(cls))
        assert len(found) == 1, f"{cls.__name__}: {len(found)} instances"
        rows = _region_text(pilot.app, found[0]).split("\n")

    assert rows[0].strip(), f"{cls.__name__} has no title row"
    assert not rows[1].strip(), (
        f"{cls.__name__} paints content directly under its title -- the "
        "blank row every other dashboard's title carries is missing. "
        f"Composited rows: {rows[:4]}"
    )
    assert rows[2].strip(), (
        f"{cls.__name__} paints nothing under the blank, so the blank above "
        "is the panel being empty rather than its title's own row"
    )



# -- the row marker on the third body, and the mapping that feeds it ------


async def test_the_taller_marker_lights_on_the_pool4_body() -> None:
    """The 2026-08-25 defect's regression lock, applied to the third body.

    ``_rail_is_cut`` reads ``_SCROLL_COLUMNS[self._mode]`` and falls back to
    ``()`` for a mode that is not in it. A ``MODE_POOL4`` body added without
    its entry therefore reports "nothing is cut" at **every** terminal height
    while both its columns visibly scroll -- which is exactly what
    ``MODE_LAUNCHPAD`` did, for the whole of that view's existence, because
    the method read one hardcoded container id.

    Three heights, and the trio is what makes this bite rather than any one
    of them:

    * **50 rows** -- whole for the pool4 body (42 for this default Sepolia
      payload, against a 45 pin measured on mainnet's) and whole for the
      dashboard body (36). The marker must be dark in both, or the test
      below cannot tell a wired marker from a stuck-on one.
    * **40 rows** -- short for pool4, whole for the dashboard. This is the
      half a missing ``_SCROLL_COLUMNS`` entry fails: the marker is dark
      before ``p`` and must be **lit** after it.
    * **28 rows** -- short for both. The marker must stay lit through the
      swap, which is what stops the fix being "light it whenever the mode is
      MODE_POOL4"; that mutation passes the 40-row half on its own.
    """
    for rows, before, after in ((50, False, False), (40, False, True),
                                (28, True, True)):
        async with _pool4_app().run_test(size=(150, rows)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            assert (TALLER_HINT in _screen_text(pilot.app)) is before, (
                f"{rows} rows: the DASHBOARD body's marker is not in the "
                "state this test's premise needs"
            )
            await pilot.press("e")
            await pilot.pause()
            assert (TALLER_HINT in _screen_text(pilot.app)) is after, (
                f"{rows} rows: the pool4 body's marker should be "
                f"{'lit' if after else 'dark'}"
            )


#: The two heights the pool4 gutter proof is measured at, and neither is
#: arbitrary. On the committed capture the columns first overflow at 40 rows
#: (measured, 2026-09-02: 41 shows no scrollbar, 40 does), so 50 is
#: comfortably on the roomy side and 40 is the first row count where the
#: scrollbar actually exists. A pair of heights both above the crossover
#: cannot fail -- the ``l`` body's own version of this test shipped exactly
#: that mistake once, and this one nearly repeated it: the crossover was 42
#: until WP4 shortened HATCHES, and the stale 42 left the premise assertion
#: failing rather than the comparison silently passing, which is the whole
#: reason the premise is asserted.
#:
#: Note this is the CAPTURE's crossover, not the pin's. The pin (45) is the
#: worst case over every payload; the committed capture is a Sepolia body
#: that legitimately fits in 42. Two different questions, two different
#: numbers.
#:
#: **40 -> 34 on 2026-09-14, because the LEFT column's crossover moved.**
#: POOL4 FLOW left this body, and the left column's content fell from 31 rows
#: to 25 on the capture. Measured the same day at 150 columns: the rail
#: still overflows from 41 rows down, but the left column now overflows only
#: from 35 down. At 40 the rail had a scrollbar and the left column did not,
#: so the left gutter was never exercised and the ``split`` comparison below
#: would have passed whether or not that gutter was reserved. 34 is the first
#: height where both columns overflow, and the premise now asserts both.
_POOL4_ROOMY_ROWS = 50
_POOL4_OVERFLOWING_ROWS = 34


async def _pool4_column_widths(height: int, width: int = 150) -> dict:
    async with _pool4_app().run_test(size=(width, height)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}")
        rail = screen.query_one(f"#{POOL4_RAIL_ID}")
        # Resolved through each column rather than from the screen. The
        # `"flow"` key this dict carried until 2026-09-14 had to be scoped
        # because the class was mounted twice; it went when POOL4 FLOW left
        # the body, and THE RATCHET takes its place as the left column's
        # second witness.
        return {
            "split": left.query_one(SurfPool4Split).region.width,
            "ratchet": left.query_one(SurfPool4Ratchet).region.width,
            "vault": rail.query_one(SurfPool4Vault).region.width,
            "left_overflowing": left.show_vertical_scrollbar,
            "rail_overflowing": rail.show_vertical_scrollbar,
        }


async def test_the_pool4_columns_reserve_their_scrollbar_gutters() -> None:
    """Without ``scrollbar-gutter: stable`` a column's scrollbar takes a
    column away the moment it overflows, so this layout's WIDTH requirement
    would move with its HEIGHT and the pin measured at 50 rows would be one
    column short at 42. Curator shipped exactly that.

    **The column belongs to the column's own children, not to the panels
    beside them**, so the widths compared are the panels' -- and the premise
    that the two heights straddle the overflow crossover is asserted first,
    because without it the comparison is trivially true and tests nothing.

    Checked against laid-out regions rather than ``styles.scrollbar_gutter``,
    because a style read cannot see a one-copy CSS deletion (the app
    stylesheet and ``DEFAULT_CSS`` cover for each other); that half is guarded
    by the property-by-property agreement test below.
    """
    roomy = await _pool4_column_widths(_POOL4_ROOMY_ROWS)
    cramped = await _pool4_column_widths(_POOL4_OVERFLOWING_ROWS)

    # BOTH columns, since 2026-09-14. The premise used to check the rail
    # alone, which was enough while FLOW made the left column overflow first.
    # Now the left column is the one that overflows LATER, so a rail-only
    # premise would leave the left gutter unexercised and `split`/`ratchet`
    # below comparing two identical non-scrolling layouts.
    for column in ("left", "rail"):
        assert not roomy[f"{column}_overflowing"], (
            f"the {column} column already overflows at {_POOL4_ROOMY_ROWS} "
            "rows -- both sample heights are on the same side of the crossover"
        )
        assert cramped[f"{column}_overflowing"], (
            f"the {column} column does not overflow at "
            f"{_POOL4_OVERFLOWING_ROWS} rows -- the condition this test exists "
            "to measure never occurs for it"
        )

    for panel in ("split", "ratchet", "vault"):
        assert roomy[panel] == cramped[panel], (
            f"{panel} is {roomy[panel]} columns at {_POOL4_ROOMY_ROWS} rows "
            f"and {cramped[panel]} at {_POOL4_OVERFLOWING_ROWS}: a scrollbar "
            "took a column instead of using its reserved gutter, so this "
            "layout's width requirement now moves with its height"
        )

    async with _pool4_app().run_test(size=(150, _POOL4_ROOMY_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        for column in (POOL4_LEFT_ID, POOL4_RAIL_ID):
            gutter = pilot.app.screen.query_one(f"#{column}").styles.scrollbar_gutter
            assert "stable" in str(gutter), column


async def test_the_hero_survives_the_pool4_body_swap() -> None:
    """The hero is outside ``#surf-pool4-body``, so nothing it tracks goes
    dark when ``p`` swaps the body underneath it.

    Asserted against the hero's **own region**, not the whole screen: the
    pool4 panels composite the words ``BURN``, ``FLOW`` and ``SUPPLY``
    themselves, so a whole-screen substring check would pass with the hero
    unmounted entirely.
    """
    async with _pool4_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.query_one(f"#{POOL4_BODY_ID}").display is True
        hero = _region_text(pilot.app, screen.query_one(SurfHero))
        for title in ("LAUNCHPAD", "FLOW", "BURN", "BOARDS"):
            assert title in hero, f"the hero lost its {title} box under `p`"
        assert "'4' - pool4" in hero
        assert "READY" in hero


# -- the p body's CSS, in agreement ---------------------------------------

_POOL4_CSS_SELECTORS = (
    f"#{POOL4_BODY_ID}", f"#{POOL4_LEFT_ID}", f"#{POOL4_RAIL_ID}",
    "SurfPool4Hatches",
    "SurfPool4Split", "SurfPool4Ratchet", "SurfPool4Vault",
    # "SurfPool4Flow" moved to `_POOL4_USER_CSS_SELECTORS` on 2026-09-14, when
    # the owner removed POOL4 FLOW from this body: its one unscoped rule now
    # styles the `4` body's instance only, so that body's agreement and
    # floor sweeps are the ones that have to cover it.
)


def test_the_pool4_body_css_agrees_between_default_css_and_the_stylesheet() -> None:
    """``SurfScreen.DEFAULT_CSS`` and the surf block in ``minimal.tcss`` must
    describe the pool4 body's geometry identically -- edit both or neither.

    The app stylesheet is what actually renders (it outranks
    ``DEFAULT_CSS``); ``DEFAULT_CSS`` is what keeps the screen correctly
    proportioned when it is reviewed or mounted without it. A property
    declared in one copy and not the other is *invisible* rather than
    conflicting: Textual falls back to ``DEFAULT_CSS`` for anything the app
    stylesheet never mentions, so the layout is right under both copies today
    and wrong under one of them the moment either value changes.

    Reuses the ``l`` body's own comparator and property list, which already
    covers ``overflow-y``, ``scrollbar-gutter`` and ``scrollbar-size`` -- all
    three load-bearing here for the same reasons they are next door.
    """
    fallback = _css_rules(SurfScreen.DEFAULT_CSS)
    block = _css_rules(_surf_stylesheet_block())

    for selector in _POOL4_CSS_SELECTORS:
        assert selector in fallback, (
            f"{selector} is not styled in SurfScreen.DEFAULT_CSS"
        )
        assert selector in block, (
            f"{selector} is not styled in the surf block of minimal.tcss"
        )
        for prop in _LAUNCHPAD_CSS_STRUCTURAL:
            default = _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS.get(prop)
            left = fallback[selector].get(prop, default)
            right = block[selector].get(prop, default)
            if left is None and right is None:
                continue
            assert left is not None and right is not None, (
                f"{selector}: {prop} is declared in only one copy "
                f"(DEFAULT_CSS={left!r}, minimal.tcss={right!r})"
            )
            if prop in _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS:
                assert _expand_css_box(left) == _expand_css_box(right), (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )
            else:
                assert left == right, (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )


# -- the 4 body's CSS, in agreement --------------------------------------

_POOL4_USER_CSS_SELECTORS = (
    f"#{POOL4_USER_BODY_ID}", f"#{POOL4_USER_MIDDLE_ID}",
    f"#{POOL4_USER_RAIL_ID}", f"#{POOL4_USER_BOTTOM_ID}",
    "SurfPool4UStakers", "SurfPool4UBurn", "SurfPool4USignals",
    "SurfPool4UDepth",
    # `SurfPool4Flow` JOINED this list on 2026-09-14. It was deliberately
    # absent while RECENT FLOW was a second instance of a class the `p` body
    # already styled, and `_POOL4_CSS_SELECTORS` covered the rule for both.
    # The owner removed the `p` body's copy as a duplicate of this one, so the
    # unscoped `SurfPool4Flow` rule styles this body's instance alone and
    # this body's agreement and floor sweeps are the ones that must see it.
    # It is still the UNSCOPED selector, never `#surf-pool4-user-middle
    # SurfPool4Flow`: `test_the_market_body_needs_no_scoped_rule_for_the_flow_panel`
    # is what keeps it that way.
    "SurfPool4Flow",
)


def test_the_market_body_css_agrees_between_default_css_and_the_stylesheet() -> None:
    """``SurfScreen.DEFAULT_CSS`` and the surf block in ``minimal.tcss`` must
    describe the ``4`` body's geometry identically -- edit both or neither.

    The app stylesheet is what actually renders (it outranks
    ``DEFAULT_CSS``); ``DEFAULT_CSS`` is what keeps the screen correctly
    proportioned when it is reviewed or mounted without it. A property
    declared in one copy and not the other is *invisible* rather than
    conflicting: Textual falls back to ``DEFAULT_CSS`` for anything the app
    stylesheet never mentions, so the layout is right under both copies today
    and wrong under one of them the moment either value changes.

    Reuses the ``l`` body's comparator and property list, which already
    covers ``overflow-y``, ``scrollbar-gutter`` and ``scrollbar-size`` -- all
    three load-bearing here for the reasons they are in the other two bodies.
    """
    fallback = _css_rules(SurfScreen.DEFAULT_CSS)
    block = _css_rules(_surf_stylesheet_block())

    for selector in _POOL4_USER_CSS_SELECTORS:
        assert selector in fallback, (
            f"{selector} is not styled in SurfScreen.DEFAULT_CSS"
        )
        assert selector in block, (
            f"{selector} is not styled in the surf block of minimal.tcss"
        )
        for prop in _LAUNCHPAD_CSS_STRUCTURAL:
            default = _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS.get(prop)
            left = fallback[selector].get(prop, default)
            right = block[selector].get(prop, default)
            if left is None and right is None:
                continue
            assert left is not None and right is not None, (
                f"{selector}: {prop} is declared in only one copy "
                f"(DEFAULT_CSS={left!r}, minimal.tcss={right!r})"
            )
            if prop in _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS:
                assert _expand_css_box(left) == _expand_css_box(right), (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )
            else:
                assert left == right, (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )


def test_every_fr_child_of_the_market_body_is_floored() -> None:
    """A ``1fr`` child cannot overflow a scroll container -- it SHRINKS.

    Without a ``min-height`` it sheds a line per terminal row down to a bare
    title with no scrollbar, no marker and no other trace, which is what the
    floor under ``SurfDevActivity`` exists to stop in the dashboard body and
    what ``SurfPool4Flow``'s exists to stop in the ``p`` one. Asserted
    against ``minimal.tcss``, the copy that actually renders, rather than
    against ``compose``: this is the property a stylesheet edit removes
    without touching a line of Python.

    The two scrolling containers are checked here too, and the gutter is not
    decoration: without ``scrollbar-gutter: stable`` the scrollbar takes
    its column out of the panel beside it only on terminals short enough to
    overflow, so the layout's WIDTH requirement would become a function of
    its HEIGHT and a pin measured tall would be a column short when short.
    """
    block = _css_rules(_surf_stylesheet_block())

    #: The ONE exemption, named rather than filtered by a rule: the body
    #: container is a ``1fr`` sibling of ``#middle-row`` on the SCREEN, which
    #: is not a scroll container -- exactly like ``#surf-launchpad-body`` and
    #: ``#surf-pool4-body``, neither of which carries a floor either. Naming
    #: it means a future ``1fr`` that really is inside a scrolling column
    #: cannot join it by accident.
    exempt = {f"#{POOL4_USER_BODY_ID}"}

    for selector in _POOL4_USER_CSS_SELECTORS:
        if selector in exempt or block[selector].get("height") != "1fr":
            continue
        assert block[selector].get("min-height"), (
            f"{selector} carries a `1fr` with no `min-height`: it cannot "
            "overflow a scroll container, it shrinks, so it sheds a line "
            "per terminal row down to a bare title with no trace"
        )

    # ...and the walk really reached some, so a selector list that stopped
    # matching cannot pass this vacuously.
    floored = [
        sel for sel in _POOL4_USER_CSS_SELECTORS
        if sel not in exempt and block[sel].get("height") == "1fr"
    ]
    assert len(floored) >= 4, floored

    for container in (POOL4_USER_BODY_ID, POOL4_USER_RAIL_ID):
        rules = block[f"#{container}"]
        assert rules.get("overflow-y") == "auto", container
        assert rules.get("scrollbar-gutter") == "stable", container


def test_the_rail_gives_its_fr_to_the_panel_that_can_never_be_cut() -> None:
    """The ``p`` body's rail rule, inherited deliberately rather than copied.

    Neither BURN & SUPPLY nor SIGNALS scrolls inside itself, so whichever
    carries the rail's ``1fr`` must be the one that can never actually be
    cut. SIGNALS renders a title, four state rows and one summary line and
    never more, so its ``min-height`` is both its floor and its ceiling --
    the same inversion ``sIMD VAULT`` makes next door, and the opposite of
    the rule every other column on this screen follows.

    Exactly one child per column may grow: two split the slack and neither
    reaches the floor the layout was measured with, none at all strands the
    column's spare rows above the fold, and both are silent.
    """
    block = _css_rules(_surf_stylesheet_block())
    rail = ("SurfPool4UBurn", "SurfPool4USignals")
    growing = [p for p in rail if block[p].get("height") == "1fr"]
    assert growing == ["SurfPool4USignals"], growing
    assert block["SurfPool4UBurn"].get("height") == "auto"
    assert block["SurfPool4UBurn"].get("margin"), (
        "BURN & SUPPLY has no bottom margin -- flush against SIGNALS the two "
        "read as one block, which is what the margin in the other two rails "
        "exists to stop"
    )


def test_the_market_body_needs_no_scoped_rule_for_the_flow_panel() -> None:
    """One unscoped rule for RECENT FLOW's geometry, asserted as an absence.

    **Renamed on 2026-09-14** from ``..._for_the_reused_flow_panel``. The
    ``p`` body's ``SurfPool4Flow`` was mounted here a second time (PRD §6.4)
    until the owner removed the ``p`` copy as a duplicate of this one, so
    "reused" stopped describing it. The assertion did not change, because its
    reason survived: the market body's top-row seam is ``1fr:1fr`` precisely
    so that the one unscoped ``SurfPool4Flow`` rule is the rule the panel
    wants. A ``#surf-pool4-user-middle SurfPool4Flow { ... }`` would state
    that panel's geometry in two places, and the next fix would reach one of
    them. That should be a decision somebody makes here, not a line somebody
    adds -- and it matters more now that the unscoped rule has only one
    instance left to keep it honest.
    """
    for css in (SurfScreen.DEFAULT_CSS, _surf_stylesheet_block()):
        for selector in _css_rules(css):
            if "SurfPool4Flow" not in selector:
                continue
            assert selector == "SurfPool4Flow", (
                f"{selector!r} scopes the flow panel to one body -- "
                "its geometry is now stated in two places"
            )


def test_the_pool4_rail_has_one_floored_fr_and_the_left_column_none() -> None:
    """The rule the body is built on, read off the CSS rather than the code.

    **Rewritten on 2026-09-14**, from
    ``test_exactly_one_pool4_child_per_column_carries_the_fr``, when the owner
    removed POOL4 FLOW -- the left column's ``1fr`` -- from this body as a
    duplicate of the ``4`` body's RECENT FLOW. The decision that replaced it
    is that the left column carries **no** ``1fr`` child at all:

    * The RAIL keeps exactly one, floored. Two ``1fr`` children in one column
      split its slack and neither reaches the floor the layout was measured
      with, and a ``1fr`` without ``min-height`` cannot overflow a scroll
      container -- it shrinks, shedding a line per row with no trace.
    * The LEFT column has none, because neither THE SPLIT nor THE RATCHET
      scrolls inside itself. A ``1fr`` on either is a ``Static`` that can be
      cut in silence, and THE SPLIT is payload-sized, so no floor stays equal
      to its content. Both ``auto``: the spare rows are blank at the column's
      foot, and too few rows make the column scroll, which ``‹ taller`` sees.
      The old test's "none at all strands the column's spare rows" worry is
      what this accepts on purpose; ``POOL4_LEFT_ID``'s block argues it.

    Both are the kind of thing an edit to the stylesheet makes without
    touching a line of Python -- which is why this is asserted against
    ``minimal.tcss``, the copy that actually renders, and not against
    ``compose``.
    """
    block = _css_rules(_surf_stylesheet_block())

    left = ("SurfPool4Split", "SurfPool4Ratchet")
    growing = [p for p in left if block[p].get("height") == "1fr"]
    assert growing == [], (
        f"#{POOL4_LEFT_ID} has a `height: 1fr` child ({growing}). Neither panel "
        "in it scrolls inside itself, so a `1fr` there is a `Static` that "
        "loses rows with no scrollbar and no trace"
    )
    for panel in left:
        assert block[panel].get("height") == "auto", panel

    rail = ("SurfPool4Hatches", "SurfPool4Vault")
    growing = [p for p in rail if block[p].get("height") == "1fr"]
    assert growing == ["SurfPool4Vault"], (
        f"#{POOL4_RAIL_ID} grows {growing}; exactly sIMD VAULT may"
    )
    assert block["SurfPool4Vault"].get("min-height"), (
        "SurfPool4Vault carries a `1fr` with no `min-height`: a `1fr` "
        "child cannot overflow a scroll container, it shrinks, so "
        "without a floor it sheds a line per terminal row down to a bare "
        "title with no scrollbar and no trace"
    )

    for column in (POOL4_LEFT_ID, POOL4_RAIL_ID):
        assert block[f"#{column}"].get("overflow-y") == "auto", column
        assert block[f"#{column}"].get("scrollbar-gutter") == "stable", column


async def test_the_adopted_discovery_detail_does_not_move_the_pool4_pin() -> None:
    """D8: the day-one payload is the *short* discovery detail, so the pin
    was first measured against the narrow case.

    CLAUDE.md's rule is to measure a data-dependent width against the state
    the data is normally in, and "normally" for this key changes the moment a
    mainnet hook is adopted: the detail goes from one clause to a sentence
    plus a 66-character transaction hash. On the binding column. That is the
    shape that moves pins, so it is measured rather than assumed.

    It does not move this one, and the second half of this test is what
    explains why -- but the property it asserts **changed with S18 and the
    old one was the defect**. It used to assert *constancy*: that the block
    rendered identically at every width. That was true, and it was true
    because ``_discovery_markup`` windowed the detail to its tier's own
    width, a fixed 35 cells, leaving 115 spare columns unused beside an
    ellipsis at 150. The correct property is **monotonicity** -- a wider
    panel renders more and never less -- transcribed from WP4's own
    ``test_the_discovery_block_is_fitted_to_the_panel_not_to_a_constant``.

    A test asserting the old property would now fail *for the right reason*
    and be "fixed" by reverting a real improvement, which is the second-worst
    outcome available; asserting nothing at all would leave the pin half
    green if the widget ever went back to a constant. So the property is
    restated rather than dropped.
    """
    payload = _frozen_payload(
        pool4_network="MAINNET",
        pool4_discovery_state="adopted",
        pool4_discovery_detail=_ADOPTED_DISCOVERY_DETAIL,
        pool4_discovery_source_tx=_ADOPTED_SOURCE_TX,
    )
    assert len(_ADOPTED_DISCOVERY_DETAIL) > 80, (
        "the fixture stopped being the long-detail case it is named for"
    )
    assert "· tx" not in _ADOPTED_DISCOVERY_DETAIL, (
        "the fixture merged the citation back into the detail -- the "
        "producer has not composed it that way since S18"
    )

    widths: dict[int, int] = {}
    for width in (SURF_POOL4_FULL_LAYOUT_COLUMNS, 120, 152, 200):
        async with _pool4_app(payload).run_test(size=(width, 60)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            screen = pilot.app.screen
            hatches = screen.query_one(SurfPool4Hatches)
            body = _region_text(pilot.app, hatches)
            widths[width] = max(
                (len(line.rstrip()) for line in body.split("\n")), default=0
            )
            if width == SURF_POOL4_FULL_LAYOUT_COLUMNS:
                # THE PIN HALF, unchanged: at the pin nothing is marked and
                # nothing is CSS-clipped, on the adopted path.
                assert not _pool4_marked(pilot.app, screen), (
                    "the adopted detail lights a marker at the pin -- the "
                    "pin was measured against the short detail only"
                )
                assert not _clipped_pool4_lines(pilot.app, screen)

    # THE MONOTONICITY HALF, replacing the constancy one.
    ordered = [widths[w] for w in sorted(widths)]
    assert ordered == sorted(ordered), (
        f"HATCHES renders LESS on a wider panel: {widths}"
    )
    assert len(set(ordered)) > 1, (
        f"HATCHES renders identically at every width: {widths} -- the "
        "discovery block is being fitted to a constant again, so the spare "
        "columns of a wide terminal are going unused beside an ellipsis"
    )
    # ...and the citation, which is the part a reader can actually rely on,
    # survives in full at the pin rather than being the thing that got cut.
    async with _pool4_app(payload).run_test(
        size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 60)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        hatch_text = _region_text(
            pilot.app, pilot.app.screen.query_one(SurfPool4Hatches)
        )
    assert _ADOPTED_SOURCE_TX[:10] in hatch_text, (
        "the citation does not reach the screen at the pinned width"
    )


# =========================================================================
# The mainnet deployment (2026-09-02): three-way split, inventory ceiling
# =========================================================================


def test_the_cap_headroom_keeps_its_operand_order() -> None:
    """⚠ The sign trap, pinned against its OPERANDS rather than a literal.

    ``pool4_floor_distance`` is ``reserve − floor``. ``pool4_cap_headroom``
    is ``cap − reserve``. The operand order flips between the two so that
    both read positive when healthy -- which is what makes them legible side
    by side, and is also exactly why writing the ceiling half "by analogy"
    with the floor half is such an easy mistake: ``reserve − cap`` gives
    −94.68 on the live mainnet numbers and renders a **binding cap as
    slack**, which is the one reading this key exists to prevent.

    Asserted against the two operands, never against ``+94.683763``. A
    literal would pass just as happily if the fixture and the constant were
    reversed together, which is the shape a mistake here actually takes: the
    author flips the subtraction and updates the expected number to match.
    """
    payload = _mainnet_pool4_payload()
    reserve = payload["pool4_tokens_in_pool"]
    cap = payload["pool4_inventory_cap"]
    floor = payload["pool4_cap_floor"]

    # The premise: on mainnet the cap really is above the reserve and really
    # does bind. Without this the sign assertions below are about a fixture
    # where either order happens to be positive.
    assert cap > reserve > floor, (reserve, cap, floor)

    assert payload["pool4_cap_headroom"] == cap - reserve, (
        "pool4_cap_headroom is not cap − reserve -- if it was written as "
        "reserve − cap it now reports a binding cap as slack"
    )
    assert payload["pool4_cap_headroom"] > 0
    assert payload["pool4_floor_distance"] == reserve - floor, (
        "pool4_floor_distance is not reserve − floor"
    )
    assert payload["pool4_floor_distance"] > 0
    # ...and the two really are opposite orders, which is the whole claim.
    assert payload["pool4_cap_headroom"] != reserve - cap


def test_the_reward_topology_reaches_exactly_two_panels() -> None:
    """WP0 pins the count; this pins that our copy agrees with it.

    ``pool4_reward_path`` says whether a Distributor is in the path and the
    staker leg is split again. It belongs on THE SPLIT (which renders the
    legs) and on HATCHES (which renders the trust surface the extra hop
    adds), and nowhere else -- a third panel acquiring it would be a second
    place for the topology to be stated and therefore a second place for it
    to disagree with itself.
    """
    from tests.data.test_surf_pool4_models import POOL4_WIDGET_SIGNATURES

    mine = {n for n, sig in SURF_WIDGET_SIGNATURES.items()
            if "pool4_reward_path" in sig}
    theirs = {n for n, sig in POOL4_WIDGET_SIGNATURES.items()
              if "pool4_reward_path" in sig}
    assert mine == theirs == {"SurfPool4Split", "SurfPool4Hatches"}, (mine, theirs)
    # The distributor address rides with it on both.
    for panel in mine:
        assert "pool4_distributor_addr" in SURF_WIDGET_SIGNATURES[panel], panel


def test_every_contract_key_is_a_real_parameter_of_its_panel() -> None:
    """A panel must DECLARE the keys the contract says it renders.

    ``**_kwargs`` is mandatory on all five ``update_data`` methods so the
    screen can splat the whole payload and a future key cannot raise. Its
    cost is that a key the widget forgot to declare is swallowed in silence
    -- the dispatch is correct, the kwarg-name check passes, the value
    reaches nothing, and no test anywhere disagrees. Every guard that
    predates this one stayed green through two live instances of exactly
    that, because ``**_kwargs`` accepts everything and therefore cannot tell
    **rendered** from **accepted and dropped** (follow-up S21).

    So the contract is compared against the real signatures, with **no
    exemptions**.

    There was a ``_KEYS_THE_WIDGET_SWALLOWS`` mapping here while the two
    known instances were open -- ``pool4_cap_headroom`` on
    ``SurfPool4Ratchet`` and ``pool4_reward_path`` on ``SurfPool4Hatches``,
    each verified twice (the word appeared nowhere in the widget's source,
    and zeroing the key through the real screen produced no new composited
    line where every other numeric key produced one). It was guarded so that
    a THIRD entry or a FIX of either reddened this test, and the fix is what
    happened: both landed in ``widgets/surf/`` and the handshake fired here.

    The **whole mechanism is gone** rather than left as an empty dict, on
    ``tests/widgets/test_surf_pool4_shared.py``'s ``_PENDING_MIGRATION``
    precedent -- a self-clearing list that has cleared has done its job, and
    an empty one is an invitation to add the next panel to it instead of
    fixing that panel. What the list was protecting is kept as the rule it
    always was: a dispatched key reaching no pixel is a defect, named here
    on the day it is written.
    """
    import inspect

    from tests.data.test_surf_pool4_models import POOL4_WIDGET_SIGNATURES

    swallowed = {}
    for panel, keys in POOL4_WIDGET_SIGNATURES.items():
        cls = _ALL_WIDGET_CLASSES[panel]
        declared = {
            name
            for name, param in inspect.signature(cls.update_data).parameters.items()
            if param.kind is not param.VAR_KEYWORD and name != "self"
        }
        for key in keys:
            if key not in declared:
                swallowed[key] = panel

    assert not swallowed, (
        f"contract keys dispatched to a panel that does not declare them, so "
        f"`**_kwargs` swallows them and they reach no pixel: {swallowed}. "
        "Declare the parameter on that panel's `update_data` and render it "
        "-- do not park it in an exemption list here."
    )


#: Payload/height pairs the row-marker property is swept over.
#:
#: The heights are a band, not a guess, and the PAYLOADS are the part that
#: matters: the one-row boundary this test exists to catch moves with the
#: body's content, so a sweep pinned to one payload catches it only where
#: that payload happens to sit. Measured with the fix disabled, the
#: disagreement appears on the **no-lever** body at 41 rows and nowhere else
#: in 36..53 -- so a lock written against the mainnet payload alone (which
#: is what the first version of this test did) passes with the fix removed
#: and locks nothing. Four payloads, eighteen heights.
_ROW_MARKER_SWEEP = [
    (name, rows)
    for name in ("no-levers", "ten-levers", "capped-levers", "mainnet")
    #: Boundary set (2026-09-19): 41 is the one height the block above says
    #: the fix-disabled disagreement appears at, and it stays on every payload.
    for rows in boundary_set(SURF_POOL4_FULL_LAYOUT_ROWS, 36, 53, 41)
]


@pytest.mark.parametrize(
    "payload_name,rows", _ROW_MARKER_SWEEP,
    ids=[f"{n}-{r}" for n, r in _ROW_MARKER_SWEEP],
)
async def test_the_row_marker_agrees_with_the_scrollbar_at_every_height(
    payload_name, rows,
) -> None:
    """``‹ taller`` must be lit exactly when a column is actually scrolling.

    The regression lock for a defect that shipped and was measured rather
    than reasoned about (2026-09-02). ``_show_mode`` and ``on_resize`` defer
    ``_render_title`` through ``call_after_refresh`` because the newly-shown
    body has not been laid out when they return -- correct, and at the
    **one-row** boundary still one pass short. A column whose content
    exceeds its height by exactly one row acquires its scrollbar on a later
    pass, so the title was composed while ``_rail_is_cut()`` still said
    ``False`` and nothing recomposed it.

    The result was the marker DARK on a body that was scrolling, at exactly
    the height where a reader most needs it: one row from fitting. WP5 saw
    this shape, could not separate it from its own dispatch injection, and
    reported it as unverified rather than dressing it up -- which was the
    right call, and it is real.

    Note what this asserts and what it does not: it compares the marker
    against the columns' **own** ``show_vertical_scrollbar``, not against a
    height threshold. A literal would go stale the next time a panel gains a
    line; the property cannot. ``_rail_is_cut`` was never wrong -- it
    returned ``True`` throughout -- so a test of that method alone would
    have stayed green. Only what reached a pixel was wrong, so that is what
    is measured.
    """
    payload = {
        "no-levers": lambda: _pool4_hatch_payload(0),
        "ten-levers": lambda: _pool4_hatch_payload(10),
        "capped-levers": lambda: _pool4_hatch_payload(12),
        "mainnet": _mainnet_pool4_payload,
    }[payload_name]()
    async with _pool4_app(payload).run_test(size=(150, rows)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{POOL4_LEFT_ID}")
        rail = screen.query_one(f"#{POOL4_RAIL_ID}")
        scrolling = (
            left.show_vertical_scrollbar or rail.show_vertical_scrollbar
        )
        lit = TALLER_HINT in _screen_text(pilot.app).split("\n")[0]

    assert lit is scrolling, (
        f"{payload_name} at {rows} rows: a column is "
        f"{'scrolling' if scrolling else 'not scrolling'} but the marker is "
        f"{'lit' if lit else 'dark'} -- the title was composed before the "
        "layout settled and nothing recomposed it"
    )
