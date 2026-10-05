"""The ``l`` LAUNCHPAD body of the surf screen: the swap, its five panels, its pins.

Split out of ``test_surf_screen.py`` on 2026-10-05 so a launchpad change runs the launchpad's
own composites, not the whole screen's. The harness, the payloads and the shared CSS and
geometry helpers stay in ``test_surf_screen.py`` and are imported from there; its docstring's
rules hold here too: composited output only, no network, no wall clock.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.screens.surf import (
    LAUNCHPAD_BODY_ID,
    LAUNCHPAD_LEFT_ID,
    LAUNCHPAD_RAIL_ID,
    MODE_LAUNCHPAD,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_ROWS,
    TALLER_HINT,
    SurfScreen,
    SURF_FULL_LAYOUT_COLUMNS,
)
from tests.screens._sweeps import boundary_set
from maxpane_dashboard.widgets.surf import (
    SurfBurnkeepers,
    SurfBurnPipeline,
    SurfCurveFlow,
    SurfHero,
    SurfLaunchpadActivity,
    SurfLaunchpadCoins,
)
from tests.screens.test_surf_screen import (
    _AS_OF_HHMM,
    _css_rules,
    _expand_css_box,
    _frozen_payload,
    _LAUNCHPAD_CSS_SHORTHAND_DEFAULTS,
    _LAUNCHPAD_CSS_STRUCTURAL,
    _LAUNCHPAD_WIDGET_CLASSES,
    _plain,
    _region_text,
    _screen_at,
    _screen_text,
    _status_bar_whole,
    _surf_app,
    _surf_stylesheet_block,
)


async def test_l_swaps_the_body_and_keeps_the_hero() -> None:
    """Body swap on curator's y/f precedent: the hero never leaves."""
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is True
        assert pilot.app.screen.query_one(SurfHero).display is True
        assert pilot.app.screen.query_one("#middle-row").display is False


async def test_escape_backs_out_one_way() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        await pilot.press("escape")
        assert pilot.app.screen.query_one("#middle-row").display is True


async def test_l_is_idempotent_and_toggles_back() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        await pilot.press("l")
        assert pilot.app.screen.query_one("#middle-row").display is True


async def test_the_status_hint_names_the_new_view() -> None:
    async with _surf_app().run_test() as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for s in strips for seg in s)
        assert "l launchpad" in text


async def test_l_also_hides_the_separator_and_bottom_row() -> None:
    """The brief's own test only names ``#middle-row``; the other two rows
    of the dashboard body must not be left showing under the launchpad
    body, or the screen would render both stacked on top of each other."""
    async with _surf_app().run_test() as pilot:
        await pilot.press("l")
        assert pilot.app.screen.query_one("#separator").display is False
        assert pilot.app.screen.query_one("#bottom-row").display is False


async def test_the_launchpad_widgets_are_dispatched_hidden_before_l_is_pressed() -> None:
    """Composed-once-shown-by-display: the first ``l`` paints a complete
    frame, not a blank one that fills in a beat later (curator's own reason
    for dispatching its `f`/`l` bodies whether or not they are showing)."""
    async with _surf_app().run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        coins = pilot.app.screen.query_one(SurfLaunchpadCoins)
        # The widget's own ``.display`` is untouched by ``_show_mode`` --
        # only the container's is set, and it is what actually hides
        # everything inside it -- so this checks the container, not the
        # child.
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is False
        # Dispatched: the population note has moved off its "Loading"
        # placeholder even though nothing has displayed it yet. It rides on
        # the panel's own title row since Task 11 -- `#surf-lpc-note` is
        # gone, and a widget whose whole job was a blank line was renamed
        # `#surf-lpc-gap` rather than left carrying a name it had stopped
        # earning. ``_plain`` reads the widget's own visual directly, unlike
        # ``_screen_text`` -- a hidden widget reaches no compositor row at
        # all.
        title = coins.query_one("#surf-lpc-title")
        assert "146 coins" in _plain(title)


# -- the launchpad body's right rail (2026-08-24) -------------------------


async def test_the_launchpad_summary_panels_sit_beside_the_coins_table() -> None:
    """CURVE FLOW and BURN PIPELINE moved out from under the coin table.

    Stacked, the two summary panels took eleven rows off the one panel in
    this body whose row count is real data -- their own ten lines are
    label/value text that never grows. Beside the table they cost columns
    instead, which is the currency a fixed-column ``DataTable`` was already
    spending a constant amount of.

    ``_surf_app`` is the **themed** harness, and that is load-bearing here:
    the app stylesheet outranks ``SurfScreen.DEFAULT_CSS``, so a rail written
    into ``DEFAULT_CSS`` alone would leave ``minimal.tcss``'s own
    ``SurfLaunchpadCoins { width: 100% }`` in charge and put the rail back
    under the table with nothing raising. This test is what notices.
    """
    async with _surf_app().run_test(size=(150, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen

        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        coins = screen.query_one(SurfLaunchpadCoins)
        flow = screen.query_one(SurfCurveFlow)
        pipeline = screen.query_one(SurfBurnPipeline)

        assert [type(c).__name__ for c in rail.children] == [
            "SurfCurveFlow", "SurfBurnPipeline", "SurfBurnkeepers",
        ]
        # To the RIGHT of the table, and beside it rather than below.
        assert coins.region.right <= rail.region.x
        assert flow.region.x >= rail.region.x
        assert flow.region.y < coins.region.bottom
        # Stacked inside the rail, flow above the pipeline, same column.
        assert flow.region.x == pipeline.region.x
        assert flow.region.bottom <= pipeline.region.y
        # Composited, not merely laid out: both titles reach a pixel while
        # the table is on screen, and the table keeps the screen's spare rows.
        rail_text = _region_text(pilot.app, rail)
        assert "CURVE FLOW" in rail_text and "BURN PIPELINE" in rail_text
        # The spare rows CHANGED HANDS on 2026-08-25 and this is where that
        # is visible. It used to read ``coins.region.height >
        # flow.region.height``, on the grounds that the table was the one
        # panel here whose row count was real data. The table is capped at
        # ten rows now, so it sizes to its content like the summary panels
        # do, and the two panels that grow are the ones with unbounded
        # content: LAUNCHPAD ACTIVITY in the left column, BURNKEEPERS in the
        # rail. Left as it was, this line would assert the old regime and
        # go red for the right reason -- so it is restated, not deleted.
        activity = screen.query_one(SurfLaunchpadActivity)
        keepers = screen.query_one(SurfBurnkeepers)
        assert activity.region.height > flow.region.height
        assert keepers.region.height > flow.region.height


# -- the l body's two columns and five panels (2026-08-25) ----------------


async def test_the_launchpad_body_holds_five_panels_in_two_columns() -> None:
    """Two columns, five panels, and the order within each is the layout.

    ``#surf-launchpad-left`` is new: the coin table is capped at ten rows, so
    it has no use for the body's spare rows and LAUNCHPAD ACTIVITY -- a feed,
    whose content is unbounded -- takes them. Asserted on the *children* of
    each container rather than on a screen-wide query, because a panel
    mounted into the wrong column still answers ``query_one`` from the
    screen and would leave this green.
    """
    async with _surf_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        left = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        assert [type(w) for w in left.children] == [
            SurfLaunchpadCoins, SurfLaunchpadActivity,
        ]
        assert [type(w) for w in rail.children] == [
            SurfCurveFlow, SurfBurnPipeline, SurfBurnkeepers,
        ]
        # ...and the two columns really are side by side, not stacked: the
        # child lists above are identical either way.
        assert left.region.right <= rail.region.x
        assert left.region.y == rail.region.y


async def test_both_new_panels_are_dispatched_on_every_refresh() -> None:
    """Dispatched whether or not ``l`` is showing, so the first keypress
    paints a complete frame instead of a blank one -- the contract the other
    three launchpad panels already keep.
    """
    async with _surf_app().run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        # Still in MODE_DASHBOARD: neither panel has been displayed once.
        assert pilot.app.screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is False
        assert pilot.app.screen.query_one(SurfLaunchpadActivity)._payload
        assert pilot.app.screen.query_one(SurfBurnkeepers)._payload
        await pilot.press("l")
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "LAUNCHPAD ACTIVITY" in text and "BURNKEEPERS" in text
    # The payload, not just the titles -- a dispatched panel that rendered
    # its empty state would satisfy the two title checks above.
    assert "PANE" in text and "0xbbbb…bbbb" in text


async def test_a_dead_launchpad_sweep_leaves_both_new_panels_explicit() -> None:
    """No blank panel, no stale number presented as live."""
    from maxpane_dashboard.widgets.surf.burnkeepers import UNAVAILABLE_LINE as BK
    from maxpane_dashboard.widgets.surf.launchpad_activity import (
        UNAVAILABLE_LINE as ACT,
    )
    payload = _frozen_payload(
        launchpad_activity=None, launchpad_burnkeepers=None
    )
    async with _surf_app(payload).run_test(size=(150, 50)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("l")
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert ACT in text and BK in text


async def test_the_coins_take_the_rows_the_feed_used_to_hold() -> None:
    """The owner's 2026-09-15 trade, measured at four terminal heights.

    It replaces ``test_the_rows_the_capped_coin_table_gave_up_go_to_the_feed``,
    which pinned the opposite regime: a ten-row table that never grew and a
    feed that took every spare row. The owner's screenshot showed exactly
    that, ten coins over a mostly empty feed, and asked for the reverse.

    The claims are properties of the heights rather than literals:

    * from the pin up, COINS is taller than ACTIVITY and draws every coin it
      has room for, never fewer than the ten it drew before;
    * COINS stops at its 23-row ceiling, and after that every extra
      terminal row goes to the feed.
    """
    measured: dict[int, tuple[int, int, int]] = {}
    for rows in (SURF_LAUNCHPAD_FULL_LAYOUT_ROWS, 40, 50, 60):
        async with _surf_app(_twenty_coin_payload()).run_test(
            size=(150, rows)
        ) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.press("l")
            await pilot.pause()
            await pilot.pause()
            screen = pilot.app.screen
            coins = screen.query_one(SurfLaunchpadCoins)
            measured[rows] = (
                coins.region.height,
                screen.query_one(SurfLaunchpadActivity).region.height,
                coins.query_one("DataTable").row_count,
            )

    for rows, (coins_h, feed_h, drawn) in measured.items():
        if coins_h < 23:
            # Under the coins' ceiling they hold the larger share. At and past
            # it the feed may overtake them, which is the second claim.
            assert coins_h > feed_h, (rows, measured)
        assert drawn == min(20, coins_h - 3), (rows, measured)
        assert drawn >= 10, (rows, measured)
    (c50, f50, _), (c60, f60, _) = measured[50], measured[60]
    assert c50 == c60 == 23, measured
    assert f60 - f50 == 10, (measured, "the rows past the coins' ceiling went elsewhere")


async def test_the_floored_panels_never_thin_out_below_their_floor() -> None:
    """``min-height`` on a ``1fr`` child is load-bearing, not decoration.

    A ``1fr`` child cannot overflow its container -- it SHRINKS -- so without
    a floor each of these two panels sheds one line per terminal row down to
    a bare title, with no scrollbar, no ``‹ widen`` and no other trace
    anywhere on screen. The floor is what turns that into an overflow the
    containing column's ``overflow-y: auto`` can show, and the title bar's
    ``‹ taller`` is what advertises it.

    **Asserted on the laid-out height AND on the marker, not on composited
    cells, and the difference matters both ways.** A floored panel that the
    column has scrolled past composites *zero* rows -- correctly: it is
    below the fold, reachable by scrolling, and ``‹ taller`` says so. So a
    composited-cell assertion here would fail on a layout that is behaving
    exactly as designed. What the earlier version of this test was missing
    is the other half: it proved the panels keep their rows without proving
    anything on screen tells the reader those rows are off the fold. Both
    are asserted now, at a height short enough that the body genuinely
    cannot fit them.
    """
    async with _surf_app().run_test(size=(150, 20)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        activity = screen.query_one(SurfLaunchpadActivity)
        keepers = screen.query_one(SurfBurnkeepers)
        assert activity.region.height >= 6, activity.region.height
        assert keepers.region.height >= 5, keepers.region.height
        # The floors are only honest if the overflow they create is visible
        # somewhere. It is not the panels' own job -- they have no marker --
        # so it has to be the title bar's, on the row that cannot be pushed
        # off. Without this the assertions above are green in a state where
        # BURNKEEPERS reaches the screen as nothing at all.
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]
        assert (
            screen.query_one(f"#{LAUNCHPAD_LEFT_ID}").show_vertical_scrollbar
            or screen.query_one(f"#{LAUNCHPAD_RAIL_ID}").show_vertical_scrollbar
        ), "neither column is scrolling, so the floors are not being tested"


#: The two heights the gutter proof is measured at, and neither is arbitrary.
#:
#: The launchpad rail first overflows at **22** rows (measured: 23 shows no
#: scrollbar, 22 does), so 46 is comfortably on the roomy side and 22 is the
#: first row count where the scrollbar actually exists. A pair of heights that
#: both sit above the crossover cannot fail -- fix round 1 shipped exactly
#: that mistake with (46, 24), and the reviewer caught it by deleting the
#: property and watching the "proof" stay green.
_RAIL_ROOMY_ROWS = 46
_RAIL_OVERFLOWING_ROWS = 22


async def _launchpad_rail_widths(height: int, width: int = 150) -> dict:
    """Rail geometry in the ``l`` body at *height* rows -- the widths the
    gutter is actually about, plus whether the scrollbar is really there."""
    async with _surf_app().run_test(size=(width, height)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        return {
            "flow": screen.query_one(SurfCurveFlow).region.width,
            "pipeline": screen.query_one(SurfBurnPipeline).region.width,
            "coins": screen.query_one(SurfLaunchpadCoins).region.width,
            "overflowing": rail.show_vertical_scrollbar,
        }


async def test_the_launchpad_rail_reserves_its_scrollbar_gutter() -> None:
    """Curator's ``#curator-right-rail`` bug, pre-empted -- and *proved*.

    Without ``scrollbar-gutter: stable`` the rail's scrollbar takes a column
    away the moment the rail overflows, so the layout's WIDTH requirement
    moves with its HEIGHT: the width Task 13 pins at one terminal height is a
    column short at another. Curator shipped exactly that -- one pin true at
    48 rows and one column short at 40.

    **The column belongs to the rail's own children, not to the table beside
    it.** That is the whole subject of this test and fix round 1 got it
    wrong: it compared ``SurfLaunchpadCoins.region.width``, which a ``7fr``
    seam fixes at 80 regardless of the rail's scrollbar, at two heights that
    were *both* above the overflow crossover. Two independent reasons it
    could never fail. Measured with the property deleted from both
    stylesheets:

    * ``coins`` -- 80 at 46 rows and 80 at 22. Unchanged by the mutation.
      The wrong subject.
    * ``flow``/``pipeline`` -- 70 at 46 rows, 69 at 22. **That** is the
      column the gutter reserves, and reserving it is what makes the two
      heights agree.

    So the assertion is: the rail's children are the same width whether or
    not the rail is tall enough to need a scrollbar. It is checked against
    laid-out regions rather than ``styles.scrollbar_gutter`` because a style
    read cannot see a one-copy CSS deletion (the app stylesheet and
    ``DEFAULT_CSS`` cover for each other) -- that half is guarded by
    ``test_the_launchpad_body_css_agrees_between_default_css_and_the_stylesheet``
    instead, which compares the property between the two copies.
    """
    roomy = await _launchpad_rail_widths(_RAIL_ROOMY_ROWS)
    cramped = await _launchpad_rail_widths(_RAIL_OVERFLOWING_ROWS)

    # The premise: the two heights straddle the overflow crossover. Without
    # this the comparison below is trivially true and tests nothing -- which
    # is precisely how the first version of this test passed.
    assert not roomy["overflowing"], (
        f"the rail already overflows at {_RAIL_ROOMY_ROWS} rows -- both "
        "sample heights are on the same side of the crossover"
    )
    assert cramped["overflowing"], (
        f"the rail does not overflow at {_RAIL_OVERFLOWING_ROWS} rows -- the "
        "condition this test exists to measure never occurs"
    )

    for panel in ("flow", "pipeline"):
        assert roomy[panel] == cramped[panel], (
            f"{panel} is {roomy[panel]} columns at {_RAIL_ROOMY_ROWS} rows "
            f"and {cramped[panel]} at {_RAIL_OVERFLOWING_ROWS}: the "
            "scrollbar took a column instead of using its reserved gutter, "
            "so this layout's width requirement now moves with its height"
        )

    # The declaration itself, so a rail that happened to agree for some other
    # reason still names the property it is relying on.
    async with _surf_app().run_test(size=(150, _RAIL_ROOMY_ROWS)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        rail = pilot.app.screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        assert "stable" in str(rail.styles.scrollbar_gutter)


async def test_the_hero_survives_the_launchpad_body_swap() -> None:
    """The hero is outside ``#surf-launchpad-body``, so nothing it tracks
    goes dark when ``l`` swaps the body underneath it.

    Asserted against the hero's **own region**, not the whole screen: three
    of its four box titles are words the launchpad panels also composite
    (``LAUNCHPAD COINS``, ``CURVE FLOW``'s numbers, ``BURN PIPELINE``), so a
    whole-screen substring check would pass with the hero unmounted entirely.
    """
    async with _surf_app().run_test(size=(150, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.query_one(f"#{LAUNCHPAD_BODY_ID}").display is True

        hero = _region_text(pilot.app, screen.query_one(SurfHero))
        for title in ("LAUNCHPAD", "FLOW", "BURN", "BOARDS"):
            assert title in hero, f"the hero lost its {title} box under `l`"
        # The live numbers, not just the frame: BURN reads the fast tier and
        # would go dark if the hero were swapped.
        assert "'b' - leaderboard" in hero
        assert "READY" in hero

_LAUNCHPAD_CSS_SELECTORS = (
    f"#{LAUNCHPAD_BODY_ID}", f"#{LAUNCHPAD_LEFT_ID}", f"#{LAUNCHPAD_RAIL_ID}",
    "SurfLaunchpadCoins",
    # The `1fr` the coin table used to carry really lives on its DataTable
    # (`widgets/surf/launchpad.py`'s own DEFAULT_CSS), so the override that
    # takes it to `auto` is geometry like any other and has to agree across
    # both copies -- this is the selector that would silently disagree
    # otherwise, and the panel above it would look identical in both files
    # while rendering differently.
    "SurfLaunchpadCoins > DataTable",
    "SurfLaunchpadActivity",
    "SurfCurveFlow", "SurfBurnPipeline", "SurfBurnkeepers",
)


def test_the_launchpad_body_css_agrees_between_default_css_and_the_stylesheet() -> None:
    """``SurfScreen.DEFAULT_CSS`` and the surf block in ``minimal.tcss`` must
    describe the launchpad body's geometry identically -- edit both or
    neither. The app stylesheet is what actually renders (it outranks
    ``DEFAULT_CSS``); ``DEFAULT_CSS`` is what keeps the screen correctly
    proportioned when it is reviewed or mounted without the app stylesheet.
    """
    fallback = _css_rules(SurfScreen.DEFAULT_CSS)
    block = _css_rules(_surf_stylesheet_block())

    for selector in _LAUNCHPAD_CSS_SELECTORS:
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


# -- the l body's own measured width (Task 13; re-swept 2026-08-25) -------
#
# ``SURF_FULL_LAYOUT_COLUMNS`` (this screen) and ``__main__.FULL_LAYOUT_
# COLUMNS`` (the app) are FWA's 143 and this task moves neither -- the
# measurement, the binding panel, the per-seam table and why the CLAUDE.md
# width record is not appended to are all in
# ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``'s own docstring in
# ``screens/surf.py``.
#
# The sweep below runs 128..150: comfortably below *and* above the measured
# 138, and never starting at it, so it could not agree with the pin by
# construction.
#
# It ran 80..105 until 2026-08-24 and 120..145 until 2026-08-25. Each range
# was right for the body it was written against -- three stacked full-width
# panels binding at 93, then a 12:5 rail binding at 135 -- and each had to
# move when the pin did. Re-centre the range whenever the pin moves.


def _title_text(pilot) -> str:
    """Composited screen text, named for this task's own sweep pseudocode.

    Not just row 0: the marker this task adds lives on the binding panel's
    *own* title (``SurfLaunchpadCoins``, the ``SurfMarket``/curator
    ``CuratorOperators`` idiom), not a screen-wide banner the way
    ``TALLER_HINT`` is -- curator's own ``_analysis_view_text`` returns the
    whole composited screen for the identical reason.
    """
    return _screen_text(pilot.app)


def _clipped_launchpad_lines(app, screen) -> list[str]:
    """Every composited line in the ``l`` body that ends in a truncation.

    **Asked of the five panels, never of their two containers**, and that is
    a correctness fix rather than a tidy-up. ``_region_text`` slices the
    compositor to a widget's rectangle, and a *container*'s rectangle
    includes the column reserved by ``scrollbar-gutter: stable`` -- so on any
    row where the scrollbar glyph is painted, a genuinely clipped line no
    longer *ends* in ``…`` and the check goes quiet exactly when the layout
    is under most pressure. Each panel's own rectangle excludes that gutter.

    It asks whether a line ENDS in ``…``, not whether one contains one.
    ``text-overflow: ellipsis`` puts its ellipsis at the truncation point,
    which is the end of the rendered line, so this catches every clip a bare
    ``in`` would. What it stops catching is a false positive that arrived
    with BURNKEEPERS (2026-08-25): its wallet cell is a deliberate
    anti-poisoning *window*, ``0xbbbb…bbbb``, whose ellipsis is a glyph in
    the middle of a line that fits perfectly well. Left as ``in``, the sweep
    below failed at every width from the pin up while nothing was clipped
    anywhere -- a red test that would have been "fixed" by moving a pin.
    """
    out = []
    for cls in _LAUNCHPAD_WIDGET_CLASSES.values():
        for line in _region_text(app, screen.query_one(cls)).split("\n"):
            if line.rstrip().endswith("…"):
                out.append(line)
    return out


@pytest.mark.parametrize(
    "payload", [None, "ordinary"], ids=["committed-capture", "ordinary-burn-line"]
)
#: Boundary set (2026-09-19, HANDOVER.md §2.3): 132 closes the 129..132 band the
#: shipped seam clipped in, 136 the qualifying-seam pins either side of 138, 140
#: the 2026-09-15 defect band. See tests/screens/_sweeps.py.
@pytest.mark.parametrize(
    "width",
    boundary_set(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, 128, 150, 132, 136, 140),
)
async def test_the_launchpad_body_is_whole_from_its_pinned_width(width, payload) -> None:
    """Start the sweep away from the pin: a sweep that began at the constant
    would agree with it by construction.

    **Swept against both payload magnitudes**, because the rail's need is
    data-dependent (see :func:`_ordinary_burn_payload`) and this pin's whole
    claim is that it is *not*. A capture-only sweep pins the pin from below
    for the small case only; running the same widths against an ordinary
    burn line is what makes "138 either way" an assertion rather than a
    sentence in a docstring.

    The dashboard body's own widen marker (the announce feed's linked-tx
    post, deliberately excluded from ``_widen_sweep_payload`` -- see that
    fixture's own docstring) cannot contaminate this sweep: ``#middle-row``
    is hidden in ``MODE_LAUNCHPAD``, so nothing it composites reaches the
    screen while ``l`` is showing.

    **Whole means the whole body, not merely the panels that can say so.**
    Three of the five panels here advertise ``‹ widen`` and two --
    ``SurfCurveFlow`` and ``SurfBurnPipeline`` -- are plain label/value
    ``Static``s that ellipsise and go quiet. Asserting only on the marker
    would therefore accept a seam whose *rail* binds, and that is not a
    hypothetical: it is what the ``12fr:5fr`` seam this body shipped with
    actually did: as shipped it clipped ``accrued 1.2K IMD · staged 45.00
    I…`` at 129..132 (131..132 once the left column reserved its own
    scrollbar gutter) with no ``‹ widen`` anywhere on screen, which is why
    **no value of the constant could make this sweep green** and the fix
    was a re-seam rather than a re-typed number. The clip check below is what makes that a
    failure instead of a green sweep.
    """
    pl = _ordinary_burn_payload() if payload == "ordinary" else None
    async with _surf_app(pl).run_test(size=(width, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        title = _title_text(pilot)
        clipped = _clipped_launchpad_lines(pilot.app, pilot.app.screen)
        bar_whole = _status_bar_whole(pilot.app)
        if width >= SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS:
            assert bar_whole, width
            assert "‹ widen" not in title, width
            assert not clipped, (
                f"at {width} the l body is clipping a line and nothing on "
                f"screen says so: {clipped}"
            )
        else:
            assert "‹ widen" in _region_text(pilot.app, pilot.app.screen.query_one("#surf-lpc-title")), width


#: The burn pipeline in the state the data is normally in.
#:
#: The committed capture is the **small** case for this rail:
#: ``accrued 1.2K IMD · staged 45.00 IMD`` is 35 cells, and the rail needs
#: 40 screen columns for it. ``_fmt.fmt_imd`` renders 100.00..999.99 at six
#: columns and compacts only above 1000, so an ordinary launchpad -- one
#: whose 500 IMD minimum bridge has been met and whose hook is refilling --
#: prints ``accrued 620.00 IMD · staged 500.00 IMD``, 38 cells and 43
#: columns, which is also the widest that line can ever be.
#:
#: That three-column difference is the whole subject of the seam sweep in
#: ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``: four of the seams that look
#: cheapest against the capture stop qualifying against this payload,
#: because the rail becomes the binding panel and the rail is two plain
#: ``Static``s with no ``‹ widen`` between them. CLAUDE.md's standing rule
#: is to measure a data-dependent width against the state the data is
#: normally in; this is that state.
def _ordinary_burn_payload() -> dict:
    return _frozen_payload(burn_accrued=620.0, burn_staged=500.0)


@pytest.mark.parametrize(
    "payload", [None, "ordinary"], ids=["committed-capture", "ordinary-burn-line"]
)
#: Boundary set (2026-09-19): 117 and 126 are the two payload-specific clip
#: onsets the docstring names; 132 the mutation band. See tests/screens/_sweeps.py.
@pytest.mark.parametrize(
    "width",
    boundary_set(
        SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS - 1, 112,
        SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS - 1, 117, 126, 132,
    ),
)
async def test_nothing_below_the_pin_clips_without_saying_so(width, payload) -> None:
    """The seam's *disqualifying* property, asserted rather than asserted-in-
    prose.

    CLAUDE.md's rule is that below the pin the only panel allowed to clip is
    one that advertises the loss. Two of this body's five cannot: the rail's
    ``SurfCurveFlow`` and ``SurfBurnPipeline`` are plain ``Static``s. So a
    seam that hands the rail less than it needs while the marked coin table
    is already clean renders a truncated line with nothing on screen asking
    to be widened -- exactly what ``5:2`` was rejected for in the 2026-08-24
    sweep, and exactly what ``12fr:5fr`` did once MCAP took four columns off
    the table.

    The sibling sweep above only checks the marker below the pin, which is
    green in that state. This is the half that bites, and it needs **both**
    payloads to bite at every seam worth rejecting: mutate the seam in both
    stylesheets to ``12fr:5fr`` and the committed-capture half reddens at
    131..132; mutate it to ``23fr:10fr`` or ``16fr:7fr`` -- the seams that
    look cheapest by arithmetic -- and only the ordinary-burn-line half
    does. A single-payload version of this test greens one of those two
    mistakes.

    **The range starts at 112, not at the pin's neighbourhood**, because on
    the seam that is actually pinned nothing clips anywhere in 128..137 --
    the whole point of choosing it -- so a sweep confined to those widths
    executes its ``if`` body zero times and is a guard with no positive
    behind it. At 2:1 the rail falls under ``SurfBurnPipeline``'s need from
    117 down against the capture and from 126 down against an ordinary burn
    line, so the lower widths are where this test does its real work: they
    are widths at which the body *is* clipping, and the assertion is that
    ``SurfLaunchpadCoins`` is lit through all of them.
    """
    pl = _ordinary_burn_payload() if payload == "ordinary" else None
    async with _surf_app(pl).run_test(size=(width, 46)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        clipped = _clipped_launchpad_lines(pilot.app, pilot.app.screen)
        if clipped:
            assert "‹ widen" in _title_text(pilot), (
                f"at {width} the l body clips {clipped} and no panel on "
                "screen advertises the loss"
            )


async def test_the_launchpad_body_binding_panel_is_the_coins_table() -> None:
    """Pinned by a test, not by a sentence in CLAUDE.md (curator's own
    ``test_the_analysis_binding_panel_is_the_operators_table`` precedent):
    ``SurfLaunchpadCoins`` -- its ``DataTable``'s nine fixed columns -- is
    the ``l`` body's binder, and it is the binder **by construction of the
    seam** rather than by luck.

    Re-checked against the ``2fr:1fr`` seam (2026-08-25) rather than
    assumed. The left column needs 92 screen columns and cannot give one
    back; the rail needs 40 against the committed capture and 43 against any
    ordinary one, and 2:1 hands it **46** at the pin. So one column below
    the pin the coin table is the only panel with anything to say, and it
    stays the only one under every payload this pipeline can produce --
    which is the property that chose this seam over ``13:6``, which collects
    135 with *zero* margin on a rail whose own binding panel cannot mark
    (``SurfBurnkeepers`` has a ``‹ widen`` but clears at 37, well under the
    rail's 40..43, so it is never the panel asking for columns). See
    ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``."""
    async with _surf_app().run_test(
        size=(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS - 1, 46)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        marked = {
            name
            for name, cls in _LAUNCHPAD_WIDGET_CLASSES.items()
            if "‹ widen" in _region_text(pilot.app, screen.query_one(cls))
        }
    assert marked == {"SurfLaunchpadCoins"}, marked


# -- the l body's own measured height (2026-08-25) ------------------------
#
# New with the five-panel body: three panels never came close to running out
# of rows, five do. Curator's ``f``/``y`` precedent -- the body is whole from
# ``SURF_LAUNCHPAD_FULL_LAYOUT_ROWS``, and below it the body scrolls and the
# title bar says ``‹ taller``. Note where each marker lives: ``‹ taller`` is
# screen-wide and rides row 0, the one row a short terminal can never push
# off; ``‹ widen`` rides the binding panel's own title.
#
# The sweep runs 24..45 -- seven rows below the measured 31 and fourteen
# above, never starting at it.


#: The coin table at the twenty rows it is capped at (ten until 2026-09-15).
#:
#: ``_sample_data``'s ``launchpad_coins`` has **two** rows, so in every other
#: test in this file ``SurfLaunchpadCoins`` draws two coins. The pin's own
#: derivation is written against a full table -- the coin panel on its
#: 13-row floor (title, blank, header, ten coins), the one-row gap under it,
#: and ``SurfLaunchpadActivity``'s floor of 6 = **20** -- and the committed
#: capture cannot exercise that: its table never has more coins than rows.
#:
#: Measured with this payload the left column is 20 and the rail 20 at the
#: pin, so the pin holds at 31 with **no row of margin** (the gap spent the
#: one it had). Unlike the capture, this payload fills the table at every
#: height, so a blank row under it is the margin and not an unfilled table.
#: It is the height sweep's counterpart to
#: :func:`_ordinary_burn_payload` on the width side, and it exists for the
#: same reason: the committed capture is the small case, and a pin measured
#: only against the small case is a pin nobody has tested.
#:
#: The tickers are rewritten per row so the ten are distinguishable on
#: screen; every other field is the fixture's own, so no row shape is
#: invented here (``test_every_list_row_in_the_fixture_matches_the_frozen_
#: row_shape`` still owns that claim for the fixture itself).
def _twenty_coin_payload() -> dict:
    """The coin table at its cap, twenty since 2026-09-15.

    The docstring above was written for ten; the reasoning carries over, one
    size larger. Forty activity rows as well, so the feed is full at every
    height and a blank row under the coins cannot be an empty log.
    """
    payload = _frozen_payload()
    rows = payload["launchpad_coins"]
    payload["launchpad_coins"] = [
        {**rows[i % len(rows)], "ticker": f"C{i:02d}"} for i in range(20)
    ]
    act = payload["launchpad_activity"]
    payload["launchpad_activity"] = [dict(act[i % len(act)]) for i in range(40)]
    return payload


@pytest.mark.parametrize(
    "payload", [None, "twenty-coins"], ids=["committed-capture", "twenty-coin-table"]
)
#: Boundary set (2026-09-19): 28 is where COINS used to read its ceiling, 30
#: where it reads it now (the pin's ``#:`` block). See tests/screens/_sweeps.py.
@pytest.mark.parametrize(
    "rows", boundary_set(SURF_LAUNCHPAD_FULL_LAYOUT_ROWS, 24, 45, 28, 30)
)
async def test_the_launchpad_body_is_whole_from_its_pinned_height(
    rows, payload
) -> None:
    """Curator's ``f``/``y`` precedent, applied to surf's own second body.

    Started away from the pin, like every other sweep in this module. 150
    columns is comfortably past ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``, so
    nothing here is measuring a width.

    **Swept against a twenty-coin table as well as the capture**, for the
    reason :func:`_twenty_coin_payload` records: the pin's derivation is
    written about a full table -- a 13-row coin panel, the gap and a 6-row
    feed, a 20-row left column level with the rail -- and the committed
    capture's two coins cannot fill it, so half of what the pin is about
    would be unexercised.
    """
    pl = _twenty_coin_payload() if payload == "twenty-coins" else None
    async with _surf_app(pl).run_test(size=(150, rows)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        text = _screen_text(pilot.app)
        if rows >= SURF_LAUNCHPAD_FULL_LAYOUT_ROWS:
            assert TALLER_HINT not in text, rows
        else:
            assert TALLER_HINT in text, rows


async def test_the_height_pin_is_measured_against_the_column_it_describes() -> None:
    """The pin's *derivation*, asserted -- not just its threshold.

    ``SURF_LAUNCHPAD_FULL_LAYOUT_ROWS``' docstring says both columns bind at
    20 rows: the rail's content, and the left column's floors (coin panel
    13, gap 1, feed 6). The sweep above can only ever see the resulting
    threshold, so it stays green if those numbers drift or were never true.

    This is the row-wise counterpart of the width side's in-situ half-
    measurements. It is also the guard that would catch a floor changing:
    raise the coin panel's or the feed's ``min-height`` and the left column
    becomes the binder, at which point the pin moves and this test names the
    reason.

    **Measured AT the pin since 2026-09-15, and one row under it.** It used to
    be read at 28 rows, where both ``1fr`` children sat on their floors. The
    coin panel is a ``2fr`` share with a ceiling now, and below the pin the
    column's ``fr`` children inflate while it scrolls (COINS reads its 23-row
    ceiling at 30 rows), so 28 rows no longer shows the floors. At the pin
    both columns fit exactly. The left column is COINS on its 13-row floor,
    the one-row gap and ACTIVITY on its 6-row floor, 20 in all, level with
    the rail's 20. The gap spent the one row of margin the left column used
    to have. One row under, the body scrolls and the title bar says so.
    """
    pin = SURF_LAUNCHPAD_FULL_LAYOUT_ROWS
    async with _surf_app(_twenty_coin_payload()).run_test(size=(150, pin)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        column = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
        rail = screen.query_one(f"#{LAUNCHPAD_RAIL_ID}")
        coins = screen.query_one(SurfLaunchpadCoins)
        activity = screen.query_one(SurfLaunchpadActivity)
        assert coins.size.height == 13, (
            "the coin panel is not on the 13-row floor the pin is derived "
            f"from: {coins.size.height}"
        )
        assert coins.query_one("DataTable").row_count == 10
        assert activity.size.height == 6, activity.size.height
        assert column.virtual_size.height == 13 + 1 + 6, column.virtual_size.height
        assert rail.virtual_size.height == 20, rail.virtual_size.height
        assert column.virtual_size.height == column.size.height, (
            "the left column holds more than the pin shows"
        )
        assert rail.virtual_size.height == rail.size.height
        # ...and the pin is that content plus the body's own chrome: the
        # title bar, the hero row and its top margin, this body's top margin
        # and the StatusBar. Derived from the laid-out screen rather than
        # retyped, so a hero that grew a row moves this rather than silently
        # disagreeing with the constant.
        chrome = pilot.app.size.height - column.size.height
        assert rail.virtual_size.height + chrome == SURF_LAUNCHPAD_FULL_LAYOUT_ROWS
        assert TALLER_HINT not in _screen_text(pilot.app).split("\n")[0]

    async with _surf_app(_twenty_coin_payload()).run_test(
        size=(150, pin - 1)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.pause()
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]


@pytest.mark.parametrize("rows", [SURF_LAUNCHPAD_FULL_LAYOUT_ROWS, 40, 50])
async def test_a_blank_row_separates_the_coin_table_from_the_activity_title(
    rows,
) -> None:
    """The owner's 2026-09-15 screenshot: the coin table ran into the title.

    Composited, across the left column: the row directly above
    ``LAUNCHPAD ACTIVITY`` is blank, and the row above that is a coin. The
    coin half is the premise. A table that drew fewer rows than its panel
    holds would leave a blank there with or without the margin, which is why
    this runs against twenty coins.
    """
    async with _surf_app(_twenty_coin_payload()).run_test(
        size=(150, rows)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        activity = screen.query_one(SurfLaunchpadActivity)
        coins = screen.query_one(SurfLaunchpadCoins)
        lines = _screen_text(pilot.app).split("\n")
        y = activity.region.y
        x0, x1 = coins.region.x, coins.region.right
        taller = TALLER_HINT in lines[0]

    assert not taller, rows
    assert "LAUNCHPAD ACTIVITY" in lines[y][x0:x1], lines[y]
    assert not lines[y - 1][x0:x1].strip(), (
        f"at {rows} rows the coin table runs into the ACTIVITY title: "
        f"{lines[y - 1][x0:x1]!r}"
    )
    assert lines[y - 2][x0:x1].strip().startswith("C"), (
        f"at {rows} rows the row above the gap is not a coin, so the blank "
        f"could be an unfilled table: {lines[y - 2][x0:x1]!r}"
    )


@pytest.mark.parametrize("rows", [SURF_LAUNCHPAD_FULL_LAYOUT_ROWS, 60])
async def test_the_width_pin_holds_at_every_height_the_coin_table_is_fitted_to(
    rows,
) -> None:
    """The column pin, at the pin height and at a tall one, with twenty coins.

    The width sweep above runs at 46 rows against a two-coin capture, where
    the coin table never had to choose how many rows to draw. At 31 rows it
    draws ten of twenty, and an earlier cut of this change handed it all
    twenty. The table then scrolled inside itself, and its scrollbar cut
    ``BURNED`` at 138-140 with the marker dark. Both directions are asserted
    against the constant: the marker lit one column under it, and nothing
    marked or clipped at it, with the header whole.
    """
    pin = SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS  # COINS binds the documented body width
    seen = {}
    for width in (pin - 1, pin):
        async with _surf_app(_twenty_coin_payload()).run_test(
            size=(width, rows)
        ) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            await pilot.pause()
            screen = pilot.app.screen
            table = screen.query_one(SurfLaunchpadCoins).query_one("DataTable")
            lines = _screen_text(pilot.app).split("\n")
            seen[width] = {
                "marked": "‹ widen" in "\n".join(lines),
                "clipped": _clipped_launchpad_lines(pilot.app, screen),
                "header": lines[table.region.y][table.region.x:table.region.right],
                "scrolls": table.max_scroll_y > 0,
            }
    assert seen[pin - 1]["marked"], (rows, seen[pin - 1])
    assert not seen[pin]["marked"], (rows, seen[pin])
    assert not seen[pin]["clipped"], (rows, seen[pin])
    assert "BURNED" in seen[pin]["header"], (rows, seen[pin])
    assert not seen[pin]["scrolls"], (rows, "the coin table scrolls inside itself")


async def test_the_row_marker_answers_for_the_body_that_is_showing() -> None:
    """``_rail_is_cut`` used to ask one fixed container and got it wrong.

    It read ``#surf-right-rail`` unconditionally. In ``MODE_LAUNCHPAD`` that
    container sits inside a ``display: none`` ``#middle-row``, is never laid
    out, and reports ``show_vertical_scrollbar is False`` at *every* terminal
    height -- so the one advertisement this screen has for a row gone off the
    bottom was dark across the whole of the ``l`` view while the launchpad
    rail was visibly scrolling.

    The two bodies have different thresholds (36 rows and 31), and both
    heights where they *disagree* and where they *agree* are exercised here,
    because only the pair together says what the marker is answering for:

    * **33 rows** -- short for the dashboard body, whole for the launchpad
      one. A marker still wired to the dashboard rail stays lit after ``l``
      and fails this half.
    * **28 rows** -- short for both. The marker must be lit in *both* modes,
      which is what stops the fix being "make it dark in MODE_LAUNCHPAD".
      That mutation passes the 33-row half on its own.
    """
    for rows, launchpad_marker in ((33, False), (28, True)):
        async with _surf_app().run_test(size=(150, rows)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            screen = pilot.app.screen
            assert TALLER_HINT in _screen_text(pilot.app), (
                f"{rows} rows is meant to be short for the dashboard body -- "
                "if it is not, this test's premise is gone and it can no "
                "longer fail"
            )
            assert screen.query_one("#surf-right-rail").display is True, (
                "the premise of the bug: the dashboard rail's own `display` "
                "stays True inside the hidden #middle-row"
            )
            await pilot.press("l")
            await pilot.pause()
            lit = TALLER_HINT in _screen_text(pilot.app)
            assert lit is launchpad_marker, (
                f"at {rows} rows the launchpad body's marker is "
                f"{'lit' if lit else 'dark'} and should be "
                f"{'lit' if launchpad_marker else 'dark'} -- the marker is "
                "not answering for the body that is showing"
            )


async def test_the_launchpad_left_column_scrolls_rather_than_clipping() -> None:
    """The regression test for the column's own arrival defect.

    ``#surf-launchpad-left`` shipped (2026-08-25) with ``height: 1fr`` and no
    ``overflow-y``. A ``Vertical`` defaults to ``overflow: hidden hidden``,
    so on a short terminal LAUNCHPAD ACTIVITY's rows were clipped straight
    out of the column -- no scrollbar, no ``‹ widen`` (the panel is not the
    one binding on width), and no ``‹ taller`` either, because
    ``_rail_is_cut`` was still asking the *dashboard* body's rail. Every row
    below the fold was unreachable and nothing on screen said a row existed.

    Both halves of the fix are asserted, because either alone is a different
    bug: the column must **scroll** (the affordance -- nothing is dropped,
    it is all still reachable) and the title bar must **say so** (the
    advertisement, on row 0, which no short terminal can push off).
    ``min-height`` on the ``1fr`` child is what turns "the column is short"
    into an overflow at all, so this is also that floor's proof.
    """
    async with _surf_app().run_test(size=(150, 20)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        column = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
        assert column.virtual_size.height > column.size.height, (
            "the left column holds no more than it shows at 20 rows -- this "
            "test's premise is gone and it can no longer fail"
        )
        assert column.show_vertical_scrollbar, (
            "the left column holds more than it shows and is not scrolling: "
            "those rows are clipped, not merely off the fold"
        )
        assert TALLER_HINT in _screen_text(pilot.app).split("\n")[0]


async def test_the_launchpad_left_column_reserves_its_scrollbar_gutter() -> None:
    """``#surf-launchpad-rail``'s own gutter test, for the column that did
    not have one.

    ``#surf-launchpad-left`` arrived (2026-08-25) with ``height: 1fr`` and no
    ``overflow-y`` at all, and a ``Vertical`` defaults to ``overflow: hidden
    hidden`` -- so the activity feed was clipped straight out of the column
    below 22 rows with no scrollbar and no other trace. Giving it
    ``overflow-y: auto`` without ``scrollbar-gutter: stable`` would have
    traded that for the bug curator shipped instead: the scrollbar taking a
    column out of the coin table on short terminals only, so this layout's
    WIDTH pin becomes a function of its HEIGHT.

    Measured across the column's own overflow crossover, which is **21**
    rows with the committed capture (22 shows no scrollbar, 21 does). A pair
    of heights on the same side of it could not fail.

    **There is deliberately no ``styles.scrollbar_gutter`` assertion here.**
    Reading the declaration back is CSS compared against CSS: it cannot fail
    for a layout reason, and it cannot even see a one-copy deletion, because
    the app stylesheet and ``DEFAULT_CSS`` cover for each other. The
    width-equality assertions below are the ones that bite (measured with
    the property deleted: ``coins`` 100 columns at 46 rows and 99 at 20),
    and the two-copy agreement is
    ``test_the_launchpad_body_css_agrees_between_default_css_and_the_stylesheet``'s
    job.
    """
    async def widths(height: int) -> dict:
        async with _surf_app().run_test(size=(150, height)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            screen = pilot.app.screen
            column = screen.query_one(f"#{LAUNCHPAD_LEFT_ID}")
            return {
                "coins": screen.query_one(SurfLaunchpadCoins).region.width,
                "activity": screen.query_one(SurfLaunchpadActivity).region.width,
                "overflowing": column.show_vertical_scrollbar,
            }

    roomy = await widths(46)
    cramped = await widths(20)

    assert not roomy["overflowing"], (
        "the left column already overflows at 46 rows -- both sample "
        "heights are on the same side of the crossover"
    )
    assert cramped["overflowing"], (
        "the left column does not overflow at 20 rows -- the condition this "
        "test exists to measure never occurs"
    )
    for panel in ("coins", "activity"):
        assert roomy[panel] == cramped[panel], (
            f"{panel} is {roomy[panel]} columns at 46 rows and "
            f"{cramped[panel]} at 20: the scrollbar took a column instead of "
            "using its reserved gutter, so this layout's width requirement "
            "now moves with its height"
        )


async def test_every_coin_column_header_reaches_the_screen_whole_and_distinct() -> None:
    """No two columns may render the same header, and none may be cut.

    ``DataTable`` truncates a header to its column width with **no ellipsis
    and no other trace** -- so a label longer than its column is lost in
    silence, and two labels that share a prefix longer than their columns
    become the *same word on screen*. Both happened here: ``SWAPS 24H`` and
    ``SWAPS ALL`` are 9 characters in 6-column cells, so the table rendered
    ``SWAPS   SWAPS`` at every width including the full layout, with 41 and
    977 underneath. A reader could not tell the day count from the all-time
    one, which defeats the column Task 11 added.

    The assertion is deliberately **not** "some expected substring is
    present" -- that shape passes while the screen shows nothing of the
    kind. It reads the labels off the table itself (never retyped here, so
    a renamed column cannot leave a stale literal behind), then requires
    three things of the *composited* header row at the pinned width:

    1. every label appears in it **verbatim** -- a truncated header does
       not, which is the truncation half;
    2. the labels are pairwise distinct -- which is the collision half, and
       the half a presence check cannot make;
    3. they appear **in declaration order and without overlapping** -- so
       "found" means "found in its own column", not matched inside a
       neighbour's text.
    """
    from textual.widgets import DataTable

    async with _surf_app().run_test(
        size=(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        screen = pilot.app.screen
        table = screen.query_one("#surf-lpc-table", DataTable)
        labels = [str(column.label) for column in table.columns.values()]
        panel = _region_text(pilot.app, screen.query_one(SurfLaunchpadCoins))

    assert len(labels) == 9, labels
    assert len(set(labels)) == len(labels), (
        f"two coin columns declare the same header, so the screen shows one "
        f"word over two different numbers: {labels}"
    )

    header = next((line for line in panel.split("\n") if labels[0] in line), None)
    assert header is not None, f"no header row composited:\n{panel}"

    cursor = 0
    for label in labels:
        found = header.find(label, cursor)
        assert found >= 0, (
            f"the {label!r} header does not reach the screen whole at "
            f"{SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS} columns -- DataTable cut it "
            f"and said nothing:\n{header!r}"
        )
        cursor = found + len(label)


async def test_the_freshness_marker_survives_the_launchpad_swap():
    """I4: the one tier with a DETACHED sweep must not be the one whose
    staleness the default view cannot show.

    ``l`` swaps the whole dashboard body, so the launchpad's own ``as of
    HH:MM`` (inside ``SurfBurnPipeline``/``SurfLaunchpadCoins``) is invisible
    from the dashboard and every panel that could carry one is invisible from
    the launchpad. ``#title-bar`` is outside both bodies and is the only place
    a reader can see, in either mode, that the numbers stopped moving --
    which is exactly why opting into the StatusBar's key hints (and giving up
    its ``updated Ns ago``) is defensible here at all.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 48) as (app, screen, pilot):
        assert f"as of {_AS_OF_HHMM}" in _screen_text(app).split("\n")[0]
        await pilot.press("l")
        await pilot.pause()
        assert screen._mode == MODE_LAUNCHPAD
        assert f"as of {_AS_OF_HHMM}" in _screen_text(app).split("\n")[0], (
            "the freshness marker went away with the dashboard body"
        )

async def test_launchpad_full_width_is_bound_by_coins_with_status_already_whole():
    for width in (SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS-1,SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS):
        async with _surf_app(_ordinary_burn_payload()).run_test(size=(width,SURF_LAUNCHPAD_FULL_LAYOUT_ROWS)) as pilot:
            await pilot.app.screen._do_refresh();await pilot.press('l');await pilot.pause()
            assert _status_bar_whole(pilot.app)
            title=_region_text(pilot.app,pilot.app.screen.query_one("#surf-lpc-title"))
            assert ("‹ widen" in title) == (width < SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS)
            assert not _clipped_launchpad_lines(pilot.app,pilot.app.screen)
