"""WP10 -- the `4` POOL4 MARKET body's own measured layout.

Two pins live here and nowhere else: ``SURF_POOL4_USER_FULL_LAYOUT_COLUMNS``
and ``SURF_POOL4_USER_FULL_LAYOUT_ROWS``. Their measurement method, their
binding panels and their per-panel derivation are in their own ``#:`` blocks
in ``screens/surf.py``; this file is what makes those blocks fail when they
stop being true.

Three things this file exists to pin above the rest
---------------------------------------------------
1. **Both pins fail in BOTH directions.** Every threshold assertion here is
   written against the constant (``if width >= PIN: ... else: ...``), so
   setting a pin too low reddens the "and above it nothing is marked" half
   and setting it too high reddens the "below it something is" half. A
   one-directional width test is the defect that shipped on this screen
   before, and the mutation run for this file is recorded in
   ``docs/surf_pool4_followups.md``.
2. **The claims are properties, never literals.** "Whenever a row would clip,
   some panel on this body advertises the loss" cannot go stale; "the marker
   lights below 105" goes stale the moment a panel changes and says nothing.
   The one place a literal appears is :data:`MEASURED_MARKET_COLUMNS` /
   :data:`MEASURED_MARKET_ROWS`, which are hand-typed **on purpose**: a test
   that imported the constant it explains would compare a number with itself.
3. **The sweeps do not start at the pin.** A range beginning on the constant
   agrees with it by construction. The width sweep runs 38..156 -- eighty-one
   columns below the number it collects and thirty-seven above, crossing the
   ``p`` body's 106, the ``l`` body's 138 and the screen's own 143 so
   agreeing with any of them would have to show up as a sweep result. The
   height sweep runs **24..46**, eleven rows under the number it collects and
   eleven over, and it is re-centred every time the pin moves -- it ran
   24..45 against a pin of 35, then 24..46 against 32, and the straddle band
   the payload magnitudes run moves with it every time.

The 2026-09-12 restructure
--------------------------
The owner read the live screen and asked for three things: STAKERS below
RECENT FLOW rather than above it, STAKERS wide enough to print a **whole**
42-character address, and IF IMD FALLS narrower because "half of its space is
empty". Both pins moved and both were re-swept from scratch: **105 -> 119**
and **32 -> 35**. The binder of the width pin changed with them, from
``SurfPool4Flow`` to ``SurfPool4UStakers``, which is why
``test_the_market_binding_panel_is_the_flow_log`` is now
``test_the_market_binding_panel_is_the_staker_table`` -- a renamed test rather
than an edited assertion, because a pin whose binder silently changes identity
is exactly what that test exists to catch.

The third ask is the one that did not come free, and this file pins the reason.
IF IMD FALLS's *table* is 29 cells, but its caption is 41, and below 45 columns
that caption is cut by CSS with **no ``‹`` marker** -- the panel's widen tier is
decided by its table. So 45 is a floor rather than a preference, it is spent
rather than chosen, and ``test_the_ladder_column_is_exactly_the_width_of_its_
own_caption`` measures it in both directions.

The marker-dark window, and why it is gone
------------------------------------------
Until 2026-09-12 this file carried a paragraph here about **32** rows -- one
under the then-pin -- where the ladder's ``-50%`` row went behind
``SurfPool4UDepth``'s own ``DataTable`` scrollbar while the screen-wide
``‹ taller`` marker stayed dark, because ``_rail_is_cut`` asks two containers
for ``show_vertical_scrollbar`` and neither can see a table scrolling inside a
panel. It was filed as F6 and pinned by a test that was written to redden the
day it was fixed.

It reddened. The screenshot-review pass raised
``#surf-pool4-user-bottom``'s floor from 8 to the ladder's own ten rows (the
panel grew the repo-wide blank row under its title), and a panel that can no
longer be squeezed under its own content can no longer scroll internally
while the body does not.

**The same trap was still set on the panel itself and was disarmed later that
day.** ``SurfPool4UDepth``'s own ``min-height`` stayed at 8 through all of
that, one under its content, protected only by the container around it -- so
the floor that closed the window was a neighbour's rather than its own. When
the per-panel ``as of`` markers came off this body the ladder's content fell
to nine rows and the container floor came down with it, and the panel's own
floor was raised 8 -> 9 in the same pass. Both are now exactly the content
they hold. Every height below the pin scrolls the **body** and lights the
marker, swept over 24..46 and all ten payloads: content whole from 32, marker
dark from 32, no row between them.

What has **not** changed is ``_rail_is_cut`` itself, so the height pin is
still measured against the body's **content** and never against the marker --
the next panel floored below its own content brings the window straight back.
That is why ``test_the_market_body_is_whole_from_its_pinned_height`` keeps
both halves rather than simplifying to the marker now that the two agree.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.screens.surf import (
    POOL4_USER_BODY_ID,
    POOL4_USER_BOTTOM_ID,
    POOL4_USER_MIDDLE_ID,
    POOL4_USER_RAIL_ID,
    SURF_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_ROWS,
    SURF_POOL4_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_ROWS,
    SURF_POOL4_USER_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_USER_FULL_LAYOUT_ROWS,
    SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfPool4Flow,
    SurfPool4UBurn,
    SurfPool4UDepth,
    SurfPool4USignals,
    SurfPool4UStakers,
    SurfPool4UserHero,
)
from maxpane_dashboard.widgets.surf.pool4u_depth import CAPTION as DEPTH_CAPTION
from maxpane_dashboard.widgets.surf.pool4u_depth import (
    PANEL_COLUMNS as DEPTH_PANEL_COLUMNS,
)

# The screen-test module owns the payload fixtures and the themed harness.
# Imported rather than restated: a second copy of the capture would drift,
# and a pin measured against a private fixture is a pin measured against
# nothing the rest of the suite can see.
from tests.screens.test_surf_screen import (
    TALLER_HINT,
    _css_clipped_lines,
    _css_rules,
    _surf_stylesheet_block,
    _frozen_payload,
    _mainnet_pool4_payload,
    _ordinary_pool4_payload,
    _region_text,
    _screen_text,
    _surf_app,
)

#: Independent literals for the same reason ``MEASURED_POOL4_COLUMNS`` is one
#: next door: a test that aliased the screen's constant would compare a
#: number against itself and pin nothing.
MEASURED_MARKET_COLUMNS = 119
MEASURED_MARKET_ROWS = 35

#: How many address rows ``SurfPool4UStakers`` painted at the body's pinned
#: height **before** the 2026-09-12 swap, when it sat in the top row against
#: that row's floor of 12. Measured on the pre-swap tree at (105, 32) with the
#: twenty-row staker payload, and hand-typed here because there is nothing in
#: this tree left to derive it from.
#:
#: It is the number the bottom row's raised floor was bought to protect: in a
#: nine-row slot -- the ladder's own content height, which is what that row was
#: floored at -- the same panel prints **five**.
PRE_SWAP_STAKER_ROWS_AT_PIN = 9

#: What ``SurfPool4UStakers`` needs for itself in this body, measured at the
#: width where its own marker goes dark. Hand-typed rather than imported for
#: the reason above.
#:
#: **48 until 2026-09-12, when the address column went whole.** ``_ADDR_COLS``
#: 17 -> 42 took ``FULL_WIDTH`` 44 -> 69, and the panel needs four columns more
#: than its table does: two for its own ``padding: 0 1`` and two for the
#: ``Static``'s, since Textual's ``size`` is already the content size. That
#: second pair is the arithmetic trap this file refuses to do -- the number is
#: read off the sweep.
MARKET_STAKERS_NEED = 73

#: What the fixed ladder column is, restated from CSS. It is
#: ``pool4u_depth.PANEL_COLUMNS``, which is ``CAPTION``'s 41 cells plus the
#: same four columns of padding -- **not** the ladder table's 29 (27 until
#: ``not reached`` widened ``band used`` on 2026-09-14; this did not move).
MARKET_DEPTH_COLUMNS = 45

#: What ``SurfPool4Flow`` needs for itself in this body, measured at the width
#: where its own marker goes dark. It bound this pin until 2026-09-12 and no
#: longer does: the top row is ``1fr:1fr`` so it asks for 1 + 2 x 52 = 105,
#: fourteen columns under what the bottom row now asks for. Kept because "the
#: binder changed" is only a claim if the old binder's need is still measured.
#: It is **not** the 53 the ``p`` body's ``POOL4_LEFT_NEED`` recorded until
#: 2026-09-14, when FLOW left that body: there the panel's column reserved a
#: scrollbar gutter of its own and here the top row does not.
MARKET_FLOW_NEED = 52

#: The panels whose painted line count is a **constant**, and what that
#: constant is. These four are what the height pin covers. ``STAKERS`` and
#: ``FLOW`` are absent on purpose -- both scroll inside themselves by design
#: (a leaderboard capped at ``MAX_ROWS`` and an unbounded log), so neither
#: sets a height requirement, exactly as FLOW does not set the ``p`` body's.
#: **Painted lines, not rows.** ``_painted_lines`` counts non-blank rows, so
#: the blank each panel now carries under its title (2026-09-12) is not in
#: these numbers even though it is very much in the pin -- which is exactly
#: why the pin is swept rather than derived from this table.
#:
#: **Each of these came down one on 2026-09-12** when the body's per-panel
#: ``as of`` markers were removed (``_pool4``'s *One clock on the `4` body*):
#: BURN 5 -> 4, SIGNALS 6 -> 5, the ladder 9 -> 8. The hero never had one.
#: SIGNALS is 5 rather than 7 for two separate reasons a day apart -- the
#: state-summary line went first, the clock second -- and neither is
#: recoverable from this table alone, which is why the pin is swept.
FIXED_PANEL_LINES = {
    SurfPool4UserHero: 6,
    SurfPool4UBurn: 4,
    SurfPool4USignals: 5,
    SurfPool4UDepth: 8,
}

#: The five panels of the `4` body plus its hero, by the name the failure
#: messages should print.
_MARKET_CLASSES = {
    "SurfPool4UStakers": SurfPool4UStakers,
    "SurfPool4UBurn": SurfPool4UBurn,
    "SurfPool4USignals": SurfPool4USignals,
    "SurfPool4Flow": SurfPool4Flow,
    "SurfPool4UDepth": SurfPool4UDepth,
    "SurfPool4UserHero": SurfPool4UserHero,
}


# ---------------------------------------------------------------------------
# Payloads -- the magnitudes the pins were swept against
# ---------------------------------------------------------------------------


#: Rows in :func:`_wide_staker_payload`. Hand-typed at the old renderer cap of
#: twenty rather than read off ``pool4u_stakers.MAX_ROWS``, which became 999
#: on 2026-09-15: every width in the 38..156 sweep would otherwise render a
#: 999-row table, and a column's width does not depend on how many rows share
#: it. The row *count* at the owner's live population is exercised by
#: :func:`_every_staker_payload` at the pin boundary instead.
WIDE_STAKER_ROWS = 20

#: The live vault's holder count on 2026-09-15, when the owner asked to see
#: every one of them.
LIVE_STAKER_COUNT = 353


def _wide_staker_payload(**extra) -> dict:
    """A staker page of twenty rows, with the widest cell values.

    Twenty rows rather than the capture's five, and holdings in the
    ``999.9B`` band ``_fmt_imd_cell``'s budget was sized for. The committed
    capture is this panel's *narrow* case, so a sweep that only saw it could
    not tell "the width does not move with the data" apart from "we only ever
    measured one payload".
    """
    rows = [
        {
            "rank": i + 1,
            "address": "0x" + f"{i:x}".rjust(40, "e"),
            "imd": 999_900_000_000.0,
            "pct": 100.0,
        }
        for i in range(WIDE_STAKER_ROWS)
    ]
    return _frozen_payload(
        pool4_stakers=rows,
        pool4_staker_count=999_999,
        pool4_staker_top3_pct=99.9,
        **extra,
    )


def _every_staker_payload() -> dict:
    """Every staker the live vault had when the owner asked to see them all.

    353 rows, so the rank column reaches three digits, at the widest holding
    budget. Checked at the pin boundary in both dimensions, which is where a
    pin that moved with the row count would show it.
    """
    rows = [
        {
            "rank": i + 1,
            "address": "0x" + f"{i:x}".rjust(40, "e"),
            "imd": 999_900_000_000.0,
            "pct": 100.0,
        }
        for i in range(LIVE_STAKER_COUNT)
    ]
    return _frozen_payload(
        pool4_stakers=rows,
        pool4_staker_count=LIVE_STAKER_COUNT,
        pool4_staker_top3_pct=19.3,
    )


def _widest_payload() -> dict:
    """Both tables and the log at their widest at once."""
    return _wide_staker_payload(
        pool4_flow=_ordinary_pool4_payload()["pool4_flow"]
    )


#: Every payload state the pins were swept against. The two the parametrised
#: width sweep runs are ``capture`` (the committed one) and ``ordinary``
#: (``_ordinary_pool4_payload``'s widest flow formats, the one magnitude that
#: could move the *binding* panel); the rest are checked at the boundary,
#: which is where a pin that moved with the data would show it.
MARKET_PAYLOADS = {
    "capture": lambda: None,
    "ordinary": _ordinary_pool4_payload,
    "mainnet": _mainnet_pool4_payload,
    "wide-stakers": _wide_staker_payload,
    "every-staker": _every_staker_payload,
    "widest": _widest_payload,
    "unread-stakers": lambda: _frozen_payload(
        pool4_stakers=None, pool4_staker_count=None, pool4_staker_top3_pct=None
    ),
    "empty-stakers": lambda: _frozen_payload(
        pool4_stakers=[], pool4_staker_count=0, pool4_staker_top3_pct=None
    ),
    "no-band": lambda: _frozen_payload(
        pool4_backstop_state="none",
        pool4_backstop_lower_tick=None,
        pool4_backstop_liquidity=None,
        pool4_backstop_eth=None,
    ),
    "unread-band": lambda: _frozen_payload(
        pool4_backstop_state=None,
        pool4_backstop_lower_tick=None,
        pool4_backstop_liquidity=None,
        pool4_backstop_eth=None,
    ),
    # The live mainnet shape of 2026-09-14: the band opens at 69300, 29% under
    # a spot of 65858, so four rungs paint `not reached` -- the widest value
    # the ladder's `band used` column holds. None of the payloads above
    # produces that cell, so without this one the pin boundary could not see
    # the column it was re-swept for.
    "band-not-reached": lambda: _frozen_payload(
        pool4_current_tick=65_858,
        pool4_backstop_lower_tick=69_300,
        pool4_backstop_state="deployed",
    ),
}


#: The ladder's own five inputs, lifted off the committed capture, for the one
#: measurement in this file made on the panel ALONE rather than on the body:
#: how narrow IF IMD FALLS can be before its caption goes. A bare mount is the
#: right harness for that -- it is a fact about the panel, not about the seam
#: -- and ``css_path`` loads ``minimal.tcss`` so the panel carries the same
#: ``padding: 0 1`` it has in the app.
_DEPTH_KWARGS = {
    key: _frozen_payload()[key]
    for key in (
        "pool4_current_tick",
        "pool4_position_liquidity",
        "pool4_backstop_lower_tick",
        "pool4_backstop_liquidity",
        "pool4_backstop_state",
        "pool4_network",
    )
}


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


def _market_widgets(screen) -> dict:
    """The `4` body's own panels, resolved through the body container.

    **Never ``screen.query_one(cls)``.** ``SurfPool4Flow`` was mounted twice
    on this screen -- once in the ``p`` body and once here (PRD 6.4) -- until
    2026-09-14, and ``query_one`` does **not** raise on multiple matches in
    this version of Textual, it returns the first. It is mounted here only
    now, but resolving through the body is still the rule: a pin measured on
    the wrong instance would be measuring a body that is not on screen, and
    nothing stops a second mount coming back.
    """
    body = screen.query_one(f"#{POOL4_USER_BODY_ID}")
    out = {"SurfPool4UserHero": screen.query_one(SurfPool4UserHero)}
    for name, cls in _MARKET_CLASSES.items():
        if name == "SurfPool4UserHero":
            continue
        found = list(body.query(cls))
        assert len(found) == 1, f"{name}: {len(found)} instances inside the body"
        out[name] = found[0]
    return out


def _market_marked(app, screen) -> set[str]:
    """Which `4`-body panels have a ``‹`` marker lit, by class name.

    ``‹`` rather than ``‹ widen``: these panels fall back to the bare glyph
    when the title plus its network word no longer fits
    (``widgets/surf/_pool4.GLYPH_HINT``), and a check written against the long
    spelling alone would call a marked panel unmarked at exactly the widths
    where it is under most pressure.
    """
    return {
        name
        for name, widget in _market_widgets(screen).items()
        if "‹" in _region_text(app, widget)
    }


def _market_clipped(app, screen) -> list[tuple[str, str]]:
    """Every composited line in the `4` body that **CSS** truncated.

    The panels, never their containers -- and through
    :func:`_css_clipped_lines`, which walks each panel to the leaf that
    actually painted the line and measures that leaf's own
    ``content_region`` rather than subtracting a guessed padding depth from
    the panel's rectangle. Read that function for both properties this
    docstring used to state itself.

    **This body is why it had to change.** ``SurfPool4UStakers`` paints its
    concentration footer into a ``Static`` with ``padding: 0 1`` inside a
    panel with ``padding: 0 1``, so CSS cuts that line four columns inside
    the panel's rectangle and the composited row right-strips to two --
    one short of the old ``region.width - 1`` edge, which made the clip
    structurally invisible. The 49-cell worst-case footer shipped as
    ``· sta…`` past a green sweep because of it.
    """
    out: list[tuple[str, str]] = []
    for name, widget in _market_widgets(screen).items():
        out.extend((name, body) for body in _css_clipped_lines(app, widget))
    return out


#: The narrowest ``SurfPool4UStakers`` that can paint its whole footer, and
#: the width one column under it. Hand-typed, not derived: the point of the
#: test below is that the two differ by exactly one column of *CSS* budget,
#: and a pair computed from the panel's own constants would agree with the
#: panel by construction and pin nothing.
#:
#: 52/53 until 2026-09-15. 52 was the width this panel actually had until
#: 2026-09-12, so the clip it produced was the shipped defect rather than an
#: invented one. Fix round 1 (item 4) made the fixture's footer longer: its
#: 20 rows against a population of 999,999 now read ``showing 20 of 999,999
#: addresses · top 3 = 100% of vault · stale``, 63 cells. Re-measured with
#: this probe over 50..70: clipped through 66, whole from 67, and the old
#: panel-edge rule still blind at 66, so the test's premise holds one
#: sentence longer.
_STAKERS_FOOTER_CLIPS_AT = 66
_STAKERS_FOOTER_FITS_AT = 67


async def _stakers_clip_probe(width: int) -> dict:
    """``SurfPool4UStakers`` alone at *width*, judged by both clip rules.

    A bare mount with an inline ``styles.width``, on ``_ladder_lines_at``'s
    reasoning: ``minimal.tcss`` pins this panel through the body's grid, so
    only an inline width outranks the stylesheet, and only a solo mount can
    ask "what does this panel do at exactly N columns".
    """
    from textual.app import App as _App

    class _Solo(_App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield SurfPool4UStakers()

    async with _Solo().run_test(size=(width + 40, 24)) as pilot:
        panel = pilot.app.query_one(SurfPool4UStakers)
        panel.styles.width = width
        panel.update_data(**_wide_staker_payload())
        await pilot.pause()
        await pilot.pause()
        assert panel.region.width == width, (
            f"the inline width override did not take: {panel.region.width}"
        )
        rows = [
            line.rstrip()
            for line in _region_text(pilot.app, panel).split("\n")
        ]
        # The rule this file carried until 2026-09-12, kept verbatim so the
        # blind spot stays demonstrable rather than described.
        edge = panel.region.width - 1
        return {
            "rows": rows,
            "panel_edge_rule": [
                body for body in rows
                if body.endswith("\u2026") and len(body) >= edge
            ],
            "content_box_rule": _css_clipped_lines(pilot.app, panel),
        }


async def test_the_clip_detector_sees_a_clip_inside_a_doubly_padded_leaf() -> None:
    """The detector's own regression lock, and the defect that bought it.

    ``SurfPool4UStakers`` paints its concentration footer into a ``Static``
    with ``padding: 0 1``, mounted in a panel with ``padding: 0 1``. CSS
    therefore cuts that line **four** columns inside the panel's rectangle
    and the composited row right-strips to **two** -- so the old rule, which
    asked whether a line reached ``panel.region.width - 1``, was one column
    short of ever seeing it. At the panel's pre-2026-09-12 width of 52 the
    49-cell worst-case footer shipped as ``· sta…`` with no ``‹`` marker and
    a green layout sweep.

    Three assertions, and the middle one is the reason this test exists: it
    pins the **blind spot**, not the fix. If somebody reintroduces the panel-
    edge arithmetic, ``content_box_rule`` goes empty and this reddens; if
    somebody widens ``_css_clipped_lines`` into a bare ``endswith("…")``,
    ``panel_edge_rule`` is no longer the interesting half and the
    ``_FITS_AT`` case below reddens instead.

    The fourth assertion is what stops the detector from being a constant:
    one column wider, the same payload in the same panel is clean. A
    detector that fires at every width is not measuring anything.
    """
    clipped = await _stakers_clip_probe(_STAKERS_FOOTER_CLIPS_AT)
    footer = clipped["rows"][-1]

    assert footer.endswith("\u2026"), (
        f"the fixture no longer clips at {_STAKERS_FOOTER_CLIPS_AT}: {footer!r} "
        "-- the probe is measuring nothing"
    )
    assert not clipped["panel_edge_rule"], (
        "the OLD panel-edge rule now sees this clip, so it is no longer the "
        f"blind spot this test demonstrates: {clipped['panel_edge_rule']}"
    )
    assert clipped["content_box_rule"] == [footer.lstrip()], (
        "the content-box rule missed the clip that motivated it: "
        f"{clipped['content_box_rule']} vs {footer!r}"
    )

    fits = await _stakers_clip_probe(_STAKERS_FOOTER_FITS_AT)
    assert not fits["content_box_rule"], (
        f"one column wider nothing is cut, yet the detector still fires: "
        f"{fits['content_box_rule']}"
    )
    assert fits["rows"][-1].endswith("stale"), (
        f"the whole footer should be on screen at "
        f"{_STAKERS_FOOTER_FITS_AT}: {fits['rows'][-1]!r}"
    )


def _painted_lines(app, widget) -> int:
    """How many non-blank rows of *widget* actually reached the compositor."""
    return len(
        [line for line in _region_text(app, widget).split("\n") if line.strip()]
    )


async def _ladder_lines_at(width: int) -> list[str]:
    """IF IMD FALLS alone at exactly *width* columns, composited.

    **Not ``composite_lines``**, and the reason is the change this file is
    about: ``minimal.tcss`` now pins ``SurfPool4UDepth`` to a fixed width, so
    a bare mount inside a narrower terminal hands the panel its CSS width
    anyway and overflows the screen rather than shrinking. An inline
    ``styles.width`` is the one thing that outranks the stylesheet, which is
    what makes "one column under its own pin" a question this harness can
    actually ask.
    """
    from textual.app import App as _App

    class _Solo(_App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield SurfPool4UDepth()

    async with _Solo().run_test(size=(width + 40, 20)) as pilot:
        panel = pilot.app.query_one(SurfPool4UDepth)
        panel.styles.width = width
        panel.update_data(**_DEPTH_KWARGS)
        await pilot.pause()
        await pilot.pause()
        assert panel.region.width == width, (
            f"the inline width override did not take: {panel.region.width}"
        )
        return [
            line.rstrip()
            for line in _region_text(pilot.app, panel).split("\n")
        ]


def _staker_rows(app, widget) -> int:
    """How many ADDRESS rows the leaderboard actually paints.

    Counted off composited output rather than taken from the panel's height:
    a twelve-row panel painting five entries is exactly the regression the
    bottom row's floor was raised to prevent, and a height check cannot see
    it. A row is one whose first painted character is its rank digit, which
    excludes the title, the blank under it, the header and the footer.
    """
    return len([
        line for line in _region_text(app, widget).split("\n")
        if line.strip() and line.strip()[0].isdigit()
    ])


async def _render(payload, size):
    """Open the `4` body at *size* and hand back everything measured from it."""
    app = _surf_app(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        widgets = _market_widgets(screen)
        stakers_table = widgets["SurfPool4UStakers"].query_one("DataTable")
        return {
            # A DataTable that is too narrow for its columns does not
            # ellipsise, so ``clipped`` cannot see it: it scrolls
            # horizontally and hides the rightmost cells. ``max_scroll_x`` is
            # how many columns are hidden that way (fix round 1, item 2).
            "stakers_hidden_cols": stakers_table.max_scroll_x,
            "stakers_header": next(
                (line for line in _region_text(
                    pilot.app, widgets["SurfPool4UStakers"]).split("\n")
                 if "address" in line),
                "",
            ),
            "marked": _market_marked(pilot.app, screen),
            "clipped": _market_clipped(pilot.app, screen),
            "text": _screen_text(pilot.app),
            "widths": {n: w.region.width for n, w in widgets.items()},
            "lines": {n: _painted_lines(pilot.app, w) for n, w in widgets.items()},
            "staker_rows": _staker_rows(
                pilot.app, widgets["SurfPool4UStakers"]
            ),
            "depth_text": _region_text(pilot.app, widgets["SurfPool4UDepth"]),
        }


# ---------------------------------------------------------------------------
# The column pin
# ---------------------------------------------------------------------------


#: The width sweep, as an explicit ``(payload, width)`` list rather than two
#: crossed ``parametrize`` decorators.
#:
#: The committed capture runs the **whole** range, 38..156. The widest flow
#: magnitudes run the twenty-one columns either side of the pin, which is the
#: only band where a payload that moved the threshold could show it -- a
#: hundred more renders of a payload agreeing with the first one outside that
#: band buys nothing and costs a minute of every full-suite run. The
#: boundary itself is checked against **all ten** payload states by
#: ``test_the_market_column_pin_does_not_move_with_the_payload`` below, which
#: is the stronger of the two claims anyway.
#:
#: **``every-staker`` joined on 2026-09-15 (fix round 1)**, over 109..130.
#: 353 rows always overflow the panel, so the table always paints its
#: two-cell vertical scrollbar, where twenty rows on a tall terminal may not.
#: That scrollbar takes its cells from the columns, and at the full and whole
#: tiers the table fits beside it with zero cells to spare (measured in situ at
#: 35, 50 and 60 rows). The band covers both tier thresholds, 119 and 121.
#: The sweep reads the table's own horizontal overflow at and above the pin,
#: because a DataTable that runs out of width hides cells rather than
#: ellipsising them, and ``clipped`` only sees ellipses.
_WIDTH_SWEEP = [("capture", w) for w in range(38, 157)] + [
    ("ordinary", w) for w in range(109, 130)
] + [("every-staker", w) for w in range(109, 131)]


@pytest.mark.parametrize("payload_name,width", _WIDTH_SWEEP)
async def test_the_market_body_is_whole_from_its_pinned_width(
    width, payload_name
) -> None:
    """The sweep, and it starts sixty-seven columns away from the pin.

    **Whole means the whole body, not merely the panels that can say so.** At
    and above the pin both halves are asserted -- no marker anywhere *and* no
    CSS-clipped line anywhere -- because a seam whose binder went quiet would
    satisfy the marker half on its own.

    Below the pin the claim is the marker's, and it is stated as a property
    rather than as a threshold: *something* must be asking for the columns,
    and anything that has actually lost a character must have a marker
    somewhere on the body to account for it. The clip half is not vacuous --
    ``SurfPool4UStakers`` really does lose its address cell in the high
    thirties, which is why this range starts there rather than at a
    comfortable width.

    Swept against two payload magnitudes. ``ordinary`` was the one that could
    move the *old* binding panel, FLOW: ``_fmt.fmt_imd`` compacts everything
    above 1,000, so the committed capture's ``1.2K`` is FLOW's narrow case and
    a three-digit-and-two-decimals row is its widest. Since 2026-09-12 the
    binder is the staker table, whose widest cell is an address, and an
    address is 42 characters whatever the wallet. Both magnitudes are still
    run: ``ordinary`` is the state that would show FLOW taking the seam back,
    and a payload that cannot move a pin is worth having as a measurement.
    """
    r = await _render(MARKET_PAYLOADS[payload_name](), (width, 50))
    if width >= SURF_POOL4_USER_FULL_LAYOUT_COLUMNS:
        assert not r["marked"], (width, sorted(r["marked"]))
        assert not r["clipped"], (
            f"at {width} the 4 body is clipping a line and nothing on screen "
            f"says so: {r['clipped']}"
        )
        assert r["stakers_hidden_cols"] == 0, (
            f"{payload_name} at {width}: STAKERS' table hides "
            f"{r['stakers_hidden_cols']} column(s) behind a horizontal scroll "
            "with no marker -- its vertical scrollbar took the cells"
        )
        assert "share" in r["stakers_header"], (payload_name, width, r["stakers_header"])
    else:
        assert r["marked"], width
        # There is deliberately no second assertion here, and the reason is
        # worth more than the line that used to sit in this branch.
        #
        # It read `if r["clipped"]: assert r["marked"], "<clip-specific
        # message>"` -- implied by the line above, so it could never fail
        # independently and its message could never print. Decoration.
        #
        # The claim that is NOT implied is *which* panel advertises: a body
        # can be marked because one panel lit `‹` while a different one lost
        # the line. `p`'s sibling test says exactly that in its docstring, so
        # the obvious repair is `{name for name, _ in r["clipped"]} <=
        # r["marked"]`.
        #
        # **That was tried, and it is FALSE on this body: 43 of the 140
        # width/payload cases in this sweep clip one panel while another
        # carries the marker.** So it is not a missing assertion, it is an
        # unmet property -- filed in docs/surf_pool4_followups.md rather than
        # asserted here, because turning it on reddens a sweep that is
        # otherwise green and the fix belongs in the panels' marker logic, not
        # in this file. Do not "restore" the old line: it asserted nothing.


@pytest.mark.parametrize("payload_name", sorted(MARKET_PAYLOADS))
async def test_the_market_column_pin_does_not_move_with_the_payload(
    payload_name,
) -> None:
    """Every payload state, asked at the boundary rather than over the range.

    The parametrised sweep above runs two magnitudes over a hundred widths;
    this asks the remaining eight the one question a sweep would have to
    answer differently if a pin moved with the data -- is the body clean at
    the pin and marked one column under it. Both halves, so a payload that
    needed *more* columns and one that needed *fewer* would each redden.
    """
    pin = SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    at = await _render(MARKET_PAYLOADS[payload_name](), (pin, 50))
    under = await _render(MARKET_PAYLOADS[payload_name](), (pin - 1, 50))
    assert not at["marked"], (payload_name, sorted(at["marked"]))
    assert not at["clipped"], (payload_name, at["clipped"])
    assert under["marked"], (
        f"{payload_name}: nothing asks for a column at {pin - 1}, so the pin "
        "is loose for this payload"
    )


@pytest.mark.parametrize("payload_name", sorted(MARKET_PAYLOADS))
async def test_the_market_binding_panel_is_the_staker_table(payload_name) -> None:
    """Pinned by a test, not by a sentence, and under every payload.

    The sweep can only see the resulting number, so it stays green if a
    different panel became the binder -- which is the half that matters for
    the standing rule that a panel which can bind must be able to *mark*. One
    column under the pin ``SurfPool4UStakers`` is the only panel with anything
    to say, and it says it: it drops its ``share`` column and lights ``‹`` in
    its own title.

    **It was ``SurfPool4Flow`` until 2026-09-12** and this test was renamed
    rather than edited, because a binder that changes identity while a test
    keeps its old name is a pin nobody re-measured.
    """
    r = await _render(
        MARKET_PAYLOADS[payload_name](),
        (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS - 1, 50),
    )
    assert r["marked"] == {"SurfPool4UStakers"}, (
        payload_name, sorted(r["marked"])
    )


async def test_the_market_column_pin_is_the_bottom_rows_two_needs() -> None:
    """The pin's *derivation*, not just its threshold.

    **It stopped being "the widest need, doubled" on 2026-09-12.** The top row
    is still ``1fr:1fr`` and still asks for ``1 + 2 x 52 = 105``; the bottom
    row is now a ``1fr`` leaderboard beside a **fixed** ladder column, so it
    asks for ``STAKERS' need + the ladder's column``, and the body's own
    ``scrollbar-gutter: stable`` adds the one column it always did. Measured
    at the pin itself, where that arithmetic is visible on screen, and
    asserted with ``==`` so a need that drifted in either direction reddens.

    ``MARKET_STAKERS_NEED``, ``MARKET_DEPTH_COLUMNS`` and ``MARKET_FLOW_NEED``
    are hand-typed literals rather than imports of the constants they explain,
    for the reason in this module's docstring. The old binder's need is still
    asserted: "the binder changed" is only a measurement if the panel that
    used to hold the seam is still measured holding less of it.
    """
    app = _surf_app(None)
    async with app.run_test(
        size=(SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, 50)
    ) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        widgets = _market_widgets(screen)
        flow = widgets["SurfPool4Flow"].region.width
        depth = widgets["SurfPool4UDepth"].region.width
        stakers = widgets["SurfPool4UStakers"].region.width
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}").region.width
        middle = screen.query_one(f"#{POOL4_USER_MIDDLE_ID}").region.width
        bottom = screen.query_one(f"#{POOL4_USER_BOTTOM_ID}").region.width
        rail = screen.query_one(f"#{POOL4_USER_RAIL_ID}").region.width

    assert stakers == MARKET_STAKERS_NEED, (
        f"STAKERS gets {stakers} columns at the pin, not the "
        f"{MARKET_STAKERS_NEED} the constant is built from -- re-sweep it"
    )
    assert depth == MARKET_DEPTH_COLUMNS, (
        f"the ladder is {depth} columns wide at the pin, not the fixed "
        f"{MARKET_DEPTH_COLUMNS} its CSS declares"
    )
    # The body really does pay one column for its gutter, which is the whole
    # of the difference between this pin and the bottom row's two needs.
    assert body == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    assert bottom == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS - 1
    assert middle == bottom
    assert (
        1 + MARKET_STAKERS_NEED + MARKET_DEPTH_COLUMNS
        == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    )
    # The top row is still an even seam and still asks for less than the
    # bottom one, which is what "the binder moved downstairs" means.
    assert abs(flow - rail) <= 1
    assert abs(middle - 2 * rail) <= 1
    assert 1 + 2 * MARKET_FLOW_NEED < SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    assert MEASURED_MARKET_COLUMNS == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS


async def test_the_ladder_column_is_exactly_the_width_of_its_own_caption() -> None:
    """IF IMD FALLS is a fixed column, and the number is the caption's.

    Three claims, and the third is the one that makes the other two worth
    asserting:

    1. the ladder's column really is :data:`MARKET_DEPTH_COLUMNS` on screen,
       and the caption is painted **whole** inside it -- the whole sentence,
       not merely "no ellipsis", because an ellipsis check passes on a blank
       line;
    2. it does **not** grow with the terminal. That is the owner's actual
       request -- a ``fr`` seam would have handed this panel a *share* and
       grown it back past the 52 it started from on a wide screen -- so the
       panel is measured at the pin, at ``SURF_FULL_LAYOUT_COLUMNS`` and at
       200, and STAKERS is measured taking every one of those extra columns;
    3. one column narrower the caption is **cut in silence**. The widen tier
       on this panel is decided from its table's width, so between 33 and 44
       columns it clips with no ``‹`` anywhere in its own region. That is the
       standing "a panel that can bind must be able to mark" rule failing,
       and it is the entire reason the ladder's column stops at 45 rather
       than at the table's 31. Asserted, not narrated, so a future widen tier
       that learned about the caption reddens this and gets the sentence in
       ``pool4u_depth.PANEL_COLUMNS`` rewritten rather than left stale.
    """
    seen: dict[int, tuple[int, int]] = {}
    for width in (
        SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, SURF_FULL_LAYOUT_COLUMNS, 200
    ):
        app = _surf_app(None)
        async with app.run_test(size=(width, 50)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("4")
            await pilot.pause()
            await pilot.pause()
            widgets = _market_widgets(pilot.app.screen)
            depth = widgets["SurfPool4UDepth"]
            text = _region_text(pilot.app, depth)
            seen[width] = (depth.region.width,
                           widgets["SurfPool4UStakers"].region.width)
        painted = [ln.rstrip() for ln in text.split("\n") if ln.strip()]
        assert DEPTH_CAPTION in text, (
            f"at {width} columns the ladder's caption is not painted whole: "
            f"{painted}"
        )

    widths = {w for w, _ in seen.values()}
    assert widths == {MARKET_DEPTH_COLUMNS}, (
        f"the ladder's column moved with the terminal: {seen} -- a fixed "
        "column is the whole point of this seam"
    )
    assert DEPTH_PANEL_COLUMNS == MARKET_DEPTH_COLUMNS
    stakers_widths = [w for _, w in seen.values()]
    assert stakers_widths == sorted(stakers_widths) and len(
        set(stakers_widths)
    ) == len(stakers_widths), (
        f"STAKERS did not take every extra column: {seen}"
    )

    # ...and one column narrower the sentence goes, with nothing to say so.
    lines = await _ladder_lines_at(MARKET_DEPTH_COLUMNS - 1)
    joined = "\n".join(lines)
    whole = await _ladder_lines_at(MARKET_DEPTH_COLUMNS)
    assert DEPTH_CAPTION in "\n".join(whole), (
        "the standalone harness does not paint the caption whole at the "
        "pinned width either -- it is measuring something other than the seam"
    )
    assert DEPTH_CAPTION not in joined, (
        "the caption still fits one column under the pinned ladder width, so "
        f"{MARKET_DEPTH_COLUMNS} is loose -- re-measure it"
    )
    assert any(ln.rstrip().endswith("…") for ln in lines), (
        "the caption is gone and nothing was truncated -- this test is no "
        "longer measuring what it claims"
    )
    assert "‹" not in joined, (
        "IF IMD FALLS now advertises the loss of its caption. That is a "
        "FIX, not a failure: the fixed-column seam exists because it could "
        "not, so update `pool4u_depth.PANEL_COLUMNS` and the seam's own "
        "reasoning rather than re-widening the panel."
    )


def test_the_market_body_fits_inside_the_documented_app_width() -> None:
    """The standing rule, asserted rather than assumed: a body measured wider
    than ``__main__.FULL_LAYOUT_COLUMNS`` means shortening a value, never
    raising the app's number.

    Four bodies, four independently measured pins. They are allowed to be
    equal -- but if two of them ever ARE it should be because somebody
    measured it, so the constants stay separate and this is the note that
    says so rather than a test forbidding the coincidence.

    **This body was the narrowest of the four and is not any more.** At 105 it
    sat one column under the ``p`` body's 106 with the same panel binding
    both; at 119 it is thirteen over, and a different panel binds it. The
    assertion that recorded the old relation is gone rather than inverted: a
    ``>`` here would pin a fact about two independently swept numbers that
    nobody has any reason to keep true. What is still asserted is the only
    relation that decides anything for a reader -- the body fits the width the
    app documents, so a terminal that can open surf can open this.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_POOL4_USER_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_POOL4_USER_FULL_LAYOUT_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS
    assert (
        SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
        < SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
    ), (
        "the market body now needs a wider terminal than the `l` launchpad "
        "body -- that is a real regression for a reader, not a constant to "
        "adjust"
    )


# ---------------------------------------------------------------------------
# The row pin
# ---------------------------------------------------------------------------


#: The height sweep, on :data:`_WIDTH_SWEEP`'s reasoning: the committed
#: capture over the whole 24..46 range, and the two payloads that move a
#: panel's line count over the eight rows that straddle the pin.
#:
#: **Re-centred with the pin twice on 2026-09-12** (35 -> 32 -> 35): the
#: straddle band moved 29..36 -> 26..33 -> 29..36, because a band that no
#: longer contains the threshold checks the payload magnitudes at heights
#: where nothing is under pressure and calls that agreement.
_HEIGHT_SWEEP = [("capture", r) for r in range(24, 47)] + [
    (name, r) for name in ("mainnet", "widest") for r in range(29, 37)
]


@pytest.mark.parametrize("payload_name,rows", _HEIGHT_SWEEP)
async def test_the_market_body_is_whole_from_its_pinned_height(
    rows, payload_name
) -> None:
    """150 columns is comfortably past the width pin, so nothing here is
    measuring a width.

    **Whole is asserted against the content, not against the marker**, and
    that is the substance of this test rather than a detail of it. The
    screen-wide ``‹ taller`` goes dark one row *before* the body is actually
    whole, because ``SurfPool4UDepth``'s ladder loses its deepest row behind
    the ``DataTable``'s own scrollbar and ``_rail_is_cut`` cannot see inside a
    panel. A height pin measured on the marker would therefore be a row
    optimistic -- which is exactly the shape of the 2026-09-02 defect one body
    over, arriving by a different route.

    So: at and above the pin, every fixed-height panel paints every line it
    has and the marker is dark. Below it, the body is **not** whole -- either
    the marker is lit or one of those panels is short. Both directions, and
    both stated as properties of the pin rather than of a particular height.
    """
    r = await _render(MARKET_PAYLOADS[payload_name](), (150, rows))
    short = {
        cls.__name__: (r["lines"][cls.__name__], expected)
        for cls, expected in FIXED_PANEL_LINES.items()
        if r["lines"][cls.__name__] < expected
    }
    if rows >= SURF_POOL4_USER_FULL_LAYOUT_ROWS:
        assert not short, (rows, payload_name, short)
        assert TALLER_HINT not in r["text"], (rows, payload_name)
    else:
        assert short or TALLER_HINT in r["text"], (
            f"{payload_name}: at {rows} rows the body claims to be whole one "
            "row under its own pin -- the pin is loose"
        )


async def test_the_market_height_pin_is_the_two_rows_floors() -> None:
    """The pin's *derivation*, not just its threshold.

    **What binds changed on 2026-09-12 and the test changed with it.** It used
    to be one line -- the ladder's ``-50%`` rung, on screen at the pin and gone
    one row under it -- because ``#surf-pool4-user-bottom``'s floor was the
    ladder's own nine rows. STAKERS moved into that row and the floor was
    raised to the top row's 12 so a leaderboard in it prints what it printed
    upstairs, so the pin is now the two floors plus the bottom row's one-row
    margin, and the first thing a row short of it takes is the pair of
    **caption lines** at the bottom of the body.

    Both are asserted, in both directions: at the pin the ladder's deepest
    rung, the ladder's caption and STAKERS' concentration footer are all on
    screen; one row under it at least one of them is gone. Asserted on the
    **painted column** rather than on the panel's height, because a panel that
    were merely one row taller with a blank in it would satisfy a height check
    and still be missing the number.
    """
    at = await _render(None, (150, SURF_POOL4_USER_FULL_LAYOUT_ROWS))
    under = await _render(None, (150, SURF_POOL4_USER_FULL_LAYOUT_ROWS - 1))

    assert "-50%" in at["depth_text"], (
        "the ladder's deepest rung is not on screen at the body's own pinned "
        "height -- re-sweep it"
    )
    assert DEPTH_CAPTION in at["depth_text"], (
        "the ladder's caption is not on screen at the pinned height"
    )
    assert at["lines"]["SurfPool4UDepth"] == FIXED_PANEL_LINES[SurfPool4UDepth]

    lost_under = [
        name
        for name, present in (
            ("the -50% rung", "-50%" in under["depth_text"]),
            ("the ladder's caption", DEPTH_CAPTION in under["depth_text"]),
        )
        if not present
    ]
    assert lost_under, (
        "the ladder still paints every line it has one row below the pin, so "
        "the pin is loose"
    )
    assert MEASURED_MARKET_ROWS == SURF_POOL4_USER_FULL_LAYOUT_ROWS


async def test_the_bottom_rows_floor_is_bought_for_the_leaderboard() -> None:
    """The one floor on this body that is **not** its panel's own content.

    Every other ``min-height`` here is the height of the lines the panel
    paints. ``#surf-pool4-user-bottom``'s is three rows over IF IMD FALLS's
    eight-over-nine, and the three rows are spent so ``SurfPool4UStakers``
    prints as many addresses in the bottom row as it did in the top one.
    The terminal-layout skill's rule for that is to buy the margin
    **deliberately and say so**, so this is the saying-so, asserted:

    * at the pin the leaderboard paints at least as many address rows as the
      body printed before the swap (nine, measured against the same payload on
      the pre-swap tree);
    * and the margin is real -- the row's floor is strictly greater than the
      ladder's own, so a future edit that "tidied" the two back together would
      redden here rather than quietly halve the leaderboard.

    The row count is read off **composited output**, not off a height: a panel
    can be twelve rows tall and painting five entries.
    """
    from maxpane_dashboard.screens.surf import SurfScreen as _S

    r = await _render(_wide_staker_payload(),
                      (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS,
                       SURF_POOL4_USER_FULL_LAYOUT_ROWS))
    assert r["staker_rows"] >= PRE_SWAP_STAKER_ROWS_AT_PIN, (
        f"the leaderboard prints {r['staker_rows']} addresses at the pin "
        f"against the {PRE_SWAP_STAKER_ROWS_AT_PIN} it printed in the top "
        "row before the swap -- the rebalance has stopped paying for itself"
    )

    block = _css_rules(_surf_stylesheet_block())
    row_floor = int(block[f"#{POOL4_USER_BOTTOM_ID}"]["min-height"])
    ladder_floor = int(block["SurfPool4UDepth"]["min-height"])
    stakers_floor = int(block["SurfPool4UStakers"]["min-height"])
    assert row_floor > ladder_floor, (
        f"#{POOL4_USER_BOTTOM_ID} is floored at {row_floor}, the ladder's own "
        f"content height -- the margin bought for the leaderboard is gone"
    )
    assert stakers_floor == row_floor, (
        "the leaderboard's own floor and its row's have drifted apart: a "
        "child floored ABOVE its row is a child the row cannot hold, and one "
        "floored below it gives the margin straight back"
    )
    assert int(_css_rules(_S.DEFAULT_CSS)[f"#{POOL4_USER_BOTTOM_ID}"]
               ["min-height"]) == row_floor


@pytest.mark.parametrize(
    "size",
    [
        (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, SURF_POOL4_USER_FULL_LAYOUT_ROWS),
        (150, 46),
        (169, 50),
    ],
)
async def test_a_blank_row_separates_recent_flow_from_the_stakers_title(size) -> None:
    """The owner's 2026-09-15 screenshot: FLOW's table ran into ``STAKERS``.

    The fix is FLOW's own ``margin: 0 0 1 0``, which takes one row out of the
    log rather than adding one to the body. Asserted on composited output
    across FLOW's own columns: the row directly above the STAKERS title is
    blank, and the row above that is FLOW's last log line.

    **Run against a full 25-row log**, the state the live screen was in. The
    committed capture's log is a few rows long, so the bottom of the panel is
    blank whether or not the margin exists, and a test run against it cannot
    fail. The second assertion is the premise that rules that out.
    """
    async with _surf_app(_widest_payload()).run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        flow = screen.query_one(SurfPool4Flow)
        stakers = screen.query_one(SurfPool4UStakers)
        rows = _screen_text(pilot.app).split("\n")
        # Read every region INSIDE the harness: once the app exits, a
        # widget's region is zeroed and a slice taken from it is empty.
        x0, x1 = flow.region.x, flow.region.right
        sx0, sx1 = stakers.region.x, stakers.region.right
        title_y = stakers.region.y
        taller = TALLER_HINT in rows[0]

    assert not taller, f"{size}: the body is not whole, so this measures nothing"
    assert "STAKERS" in rows[title_y][sx0:sx1]
    assert rows[title_y - 2][x0:x1].strip(), (
        f"{size}: FLOW's log does not reach the row above the gap, so the "
        "blank row could be an empty log rather than the margin"
    )
    assert not rows[title_y - 1][x0:x1].strip(), (
        f"{size}: RECENT FLOW's table runs straight into the STAKERS title: "
        f"{rows[title_y - 1][x0:x1]!r}"
    )


@pytest.mark.parametrize("rows", list(range(24, 47)))
async def test_no_height_loses_a_row_of_this_body_in_silence(rows) -> None:
    """Finding **F6, closed for this body on 2026-09-12** -- and this is what
    replaced the test that pinned it open.

    F6 was a one-row window under the old pin where the ladder's ``-50%``
    rung went behind ``SurfPool4UDepth``'s own ``DataTable`` scrollbar while
    the screen-wide ``‹ taller`` marker stayed **dark**: ``_rail_is_cut``
    asks two containers for ``show_vertical_scrollbar``, and a table
    scrolling inside a panel is invisible to both. The old test asserted that
    behaviour so a fix could not land quietly, and named what to update when
    it reddened.

    It reddened. ``#surf-pool4-user-bottom``'s floor has been at or above the
    ladder's own content ever since -- ten rows then, **nine** when the
    ``as of`` markers came off this body, and **twelve** since STAKERS moved
    into that row -- so the panel cannot be squeezed into a height where its
    table scrolls internally while the body does not; every height under the
    pin scrolls the body instead, which the marker *can* see.

    The caption is checked alongside the ``-50%`` rung from 2026-09-12,
    because with the row floored above the ladder's content it is the caption,
    not the deepest rung, that the first missing row takes.

    So the claim is now the general one rather than the exception, and it is
    swept over the same range the pin was: **at no height does this body lose
    a line with nothing on screen to say so.** That is strictly stronger than
    the test it replaces, and it is the claim that reddens if a future floor
    ever drops below its panel's content again -- which is the half of F6
    that is *not* fixed, since ``_rail_is_cut`` is unchanged.
    """
    r = await _render(None, (150, rows))
    short = {
        cls.__name__: (r["lines"][cls.__name__], expected)
        for cls, expected in FIXED_PANEL_LINES.items()
        if r["lines"][cls.__name__] < expected
    }
    lost = short or next(
        (
            name
            for name, present in (
                ("the ladder's -50% rung", "-50%" in r["depth_text"]),
                ("the ladder's caption", DEPTH_CAPTION in r["depth_text"]),
            )
            if not present
        ),
        None,
    )
    if lost:
        assert TALLER_HINT in r["text"], (
            f"at {rows} rows the body loses {lost} and the screen-wide "
            "taller marker is dark -- a row is being cut in silence"
        )


def test_the_market_body_is_shorter_than_p_and_taller_than_the_launchpad() -> None:
    """W7's answer for this body, asserted rather than left in prose.

    The PRD predicted a bakery-shaped body would land nearer the ``l`` body's
    31 rows than the ``p`` body's 45. It still does -- **35**, ten rows under
    ``p`` and four over ``l`` -- but the *other* half of that prediction, that
    it would be wide-and-short, has now come true in the direction nobody
    expected: after the whole-address change this body is the **widest** of
    the three swapped bodies bar the launchpad's, and thirteen columns wider
    than ``p``.

    **The name of this test changed with the fact.** It was
    ``..._but_not_the_shortest_pin`` and asserted
    ``COLUMNS < SURF_POOL4_FULL_LAYOUT_COLUMNS``; that assertion is deleted
    rather than inverted, because two independently swept pins have no reason
    to hold an order. The margin note it carried is kept and re-measured: the
    ``> SURF_LAUNCHPAD_FULL_LAYOUT_ROWS`` half now has **four** rows of
    margin where it had one, which is a fact about the next change rather than
    this one.
    """
    assert SURF_POOL4_USER_FULL_LAYOUT_ROWS < SURF_POOL4_FULL_LAYOUT_ROWS
    assert SURF_POOL4_USER_FULL_LAYOUT_ROWS > SURF_LAUNCHPAD_FULL_LAYOUT_ROWS


# ---------------------------------------------------------------------------
# The status hint
# ---------------------------------------------------------------------------

#: The whole phrase, as one contiguous string. ``l launchpad`` is the half
#: that must never shorten -- an app-level acceptance test greps for it -- so
#: if this ever stops fitting, ``4 pool4`` is what gives way.
#:
#: **Two parts since 2026-09-15.** It was ``l launchpad · p pool4 · 4
#: market``. The owner took ``p pool4`` off the bar (the protocol body is now
#: the unadvertised, experimental ``e``) and renamed ``4 market`` to ``4
#: pool4``.
KEY_HINT_PHRASE = "l launchpad · 4 pool4"


async def test_the_key_hint_fits_the_status_bar_at_the_full_layout() -> None:
    """Measured against the bar's own budget, never counted.

    ``StatusBar``'s left label is the segment the bar cuts first, so the
    question is settled
    by reading the phrase back off **composited output** at
    :data:`SURF_FULL_LAYOUT_COLUMNS` and then one column at a time down the
    band below it -- the test says *where* it stops fitting rather than only
    that it fits somewhere.

    Two assertions, and the second is the one a row-join is blind to.
    ``_screen_text`` joins a strip's segments with ``""``, so a per-letter
    ``[dim]`` tag that split the hint into ``4`` / `` pool4`` would leave the
    row-joined text byte-identical while every app-level grep for the
    contiguous phrase failed and the bar itself looked perfectly correct.

    The third assertion is the owner's removal: the experimental key and
    the old words are nowhere on the composited bar.
    """
    async with _surf_app().run_test(
        size=(SURF_FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = _screen_text(pilot.app)
        segments = [seg.text for strip in strips for seg in strip]

    assert KEY_HINT_PHRASE in text, (
        "the hint did not reach a pixel at the documented layout "
        "width -- shorten '4 pool4', never 'l launchpad'"
    )
    assert any(KEY_HINT_PHRASE in segment for segment in segments), (
        "the hint reaches the screen but is split across Segments: KEY_HINTS "
        "must be ONE markup run, not per-letter tags"
    )
    status_row = text.split("\n")[-1]
    for gone in ("p pool4", "4 market", "e pool4", "experimental"):
        assert gone not in status_row, (
            f"{gone!r} is on the status bar; the owner took it off: {status_row!r}"
        )
    assert SurfScreen.KEY_HINTS == f"[dim]{KEY_HINT_PHRASE}[/]"


async def test_the_key_hint_has_room_to_spare_below_the_full_layout() -> None:
    """Where it stops fitting, not merely that it fits.

    Swept downward from the documented width. The phrase must survive past
    the widest pin on this screen with margin, or the next hint word is one
    edit away from silently cutting the tail off the row that says which
    views exist.
    """
    lost_at = None
    for width in range(SURF_FULL_LAYOUT_COLUMNS, 79, -1):
        async with _surf_app().run_test(size=(width, 46)) as pilot:
            await pilot.pause()
            if KEY_HINT_PHRASE not in _screen_text(pilot.app):
                lost_at = width
                break
    assert lost_at is None or lost_at < SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, (
        f"the key hint is already cut at {lost_at} columns, which is at or "
        f"above this body's own pinned width -- shorten '4 pool4'"
    )
