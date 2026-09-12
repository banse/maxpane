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
   agrees with it by construction. The width sweep runs 38..144 -- sixty-seven
   columns below the number it collects and thirty-nine above, crossing the
   ``p`` body's 106, the ``l`` body's 138 and the screen's own 143 so
   agreeing with any of them would have to show up as a sweep result. The
   height sweep runs 24..45.

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
while the body does not. Every height below the pin now scrolls the **body**
and lights the marker, swept over 24..45 and three payloads.

What has **not** changed is ``_rail_is_cut`` itself, so the height pin is
still measured against the body's **content** and never against the marker --
the next panel floored below its own content brings the window straight back.
That is why ``test_the_market_body_is_whole_from_its_pinned_height`` keeps
both halves rather than simplifying to the marker now that the two agree.
"""

from __future__ import annotations

import pytest

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
from maxpane_dashboard.widgets.surf.pool4u_stakers import MAX_ROWS as STAKER_MAX_ROWS

# The screen-test module owns the payload fixtures and the themed harness.
# Imported rather than restated: a second copy of the capture would drift,
# and a pin measured against a private fixture is a pin measured against
# nothing the rest of the suite can see.
from tests.screens.test_surf_screen import (
    TALLER_HINT,
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
MEASURED_MARKET_COLUMNS = 105
MEASURED_MARKET_ROWS = 35

#: What ``SurfPool4Flow`` needs for itself in this body, measured at the width
#: where its own marker goes dark. Hand-typed rather than imported for the
#: reason above, and it is **not** the 53 the ``p`` body's
#: ``POOL4_LEFT_NEED`` records: there the panel's column reserves a scrollbar
#: gutter of its own and here the bottom row does not.
MARKET_FLOW_NEED = 52

#: The panels whose painted line count is a **constant**, and what that
#: constant is. These four are what the height pin covers. ``STAKERS`` and
#: ``FLOW`` are absent on purpose -- both scroll inside themselves by design
#: (a leaderboard capped at ``MAX_ROWS`` and an unbounded log), so neither
#: sets a height requirement, exactly as FLOW does not set the ``p`` body's.
#: **Painted lines, not rows.** ``_painted_lines`` counts non-blank rows, so
#: the blank each panel now carries under its title (2026-09-12) is not in
#: these numbers even though it is very much in the pin -- which is exactly
#: why the pin is swept rather than derived from this table. SIGNALS is 6
#: rather than 7 because the same pass dropped its state-summary line.
FIXED_PANEL_LINES = {
    SurfPool4UserHero: 6,
    SurfPool4UBurn: 5,
    SurfPool4USignals: 6,
    SurfPool4UDepth: 9,
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


def _wide_staker_payload(**extra) -> dict:
    """A staker page at the renderer's own cap, with the widest cell values.

    ``MAX_ROWS`` rows rather than the capture's five, and holdings in the
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
        for i in range(STAKER_MAX_ROWS)
    ]
    return _frozen_payload(
        pool4_stakers=rows,
        pool4_staker_count=999_999,
        pool4_staker_top3_pct=99.9,
        **extra,
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
}


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


def _market_widgets(screen) -> dict:
    """The `4` body's own panels, resolved through the body container.

    **Never ``screen.query_one(cls)``.** ``SurfPool4Flow`` is mounted twice on
    this screen -- once in the ``p`` body and once here (PRD 6.4) -- and
    ``query_one`` does **not** raise on multiple matches in this version of
    Textual, it returns the first. A pin measured on the wrong instance would
    be measuring a body that is not on screen.
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

    Asked of the panels, never of their containers: a container's rectangle
    includes the cell reserved by ``scrollbar-gutter: stable``, so on any row
    where the scrollbar glyph is painted a genuinely clipped line no longer
    *ends* in ``…`` and the check goes quiet exactly when the layout is under
    most pressure.

    And the length is compared against the panel's own content edge rather
    than a bare ``endswith("…")``, for ``_clipped_pool4_lines``' reason:
    these panels fit their own third-party strings to their own tier width,
    so a trailing ``…`` is routinely the panel saying "this detail is longer
    than the column I gave it" rather than CSS saying "this line is longer
    than the panel".
    """
    out: list[tuple[str, str]] = []
    for name, widget in _market_widgets(screen).items():
        edge = widget.region.width - 1
        for line in _region_text(app, widget).split("\n"):
            body = line.rstrip()
            if body.endswith("…") and len(body) >= edge:
                out.append((name, body))
    return out


def _painted_lines(app, widget) -> int:
    """How many non-blank rows of *widget* actually reached the compositor."""
    return len(
        [line for line in _region_text(app, widget).split("\n") if line.strip()]
    )


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
        return {
            "marked": _market_marked(pilot.app, screen),
            "clipped": _market_clipped(pilot.app, screen),
            "text": _screen_text(pilot.app),
            "widths": {n: w.region.width for n, w in widgets.items()},
            "lines": {n: _painted_lines(pilot.app, w) for n, w in widgets.items()},
            "depth_text": _region_text(pilot.app, widgets["SurfPool4UDepth"]),
        }


# ---------------------------------------------------------------------------
# The column pin
# ---------------------------------------------------------------------------


#: The width sweep, as an explicit ``(payload, width)`` list rather than two
#: crossed ``parametrize`` decorators.
#:
#: The committed capture runs the **whole** range, 38..144. The widest flow
#: magnitudes run the twenty-one columns either side of the pin, which is the
#: only band where a payload that moved the threshold could show it -- a
#: hundred more renders of a payload agreeing with the first one outside that
#: band buys nothing and costs a minute of every full-suite run. The
#: boundary itself is checked against **all nine** payload states by
#: ``test_the_market_column_pin_does_not_move_with_the_payload`` below, which
#: is the stronger of the two claims anyway.
_WIDTH_SWEEP = [("capture", w) for w in range(38, 145)] + [
    ("ordinary", w) for w in range(95, 116)
]


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

    Swept against two payload magnitudes. ``ordinary`` is the one that could
    move the *binding* panel: ``_fmt.fmt_imd`` compacts everything above
    1,000, so the committed capture's ``1.2K`` is FLOW's narrow case and a
    three-digit-and-two-decimals row is its widest. It does not move the pin,
    and that is the result worth having.
    """
    r = await _render(MARKET_PAYLOADS[payload_name](), (width, 50))
    if width >= SURF_POOL4_USER_FULL_LAYOUT_COLUMNS:
        assert not r["marked"], (width, sorted(r["marked"]))
        assert not r["clipped"], (
            f"at {width} the 4 body is clipping a line and nothing on screen "
            f"says so: {r['clipped']}"
        )
    else:
        assert r["marked"], width
        if r["clipped"]:
            assert r["marked"], (
                f"at {width} the 4 body clips {r['clipped']} and no panel on "
                "screen advertises the loss"
            )


@pytest.mark.parametrize("payload_name", sorted(MARKET_PAYLOADS))
async def test_the_market_column_pin_does_not_move_with_the_payload(
    payload_name,
) -> None:
    """Every payload state, asked at the boundary rather than over the range.

    The parametrised sweep above runs two magnitudes over a hundred widths;
    this asks the remaining seven the one question a sweep would have to
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
async def test_the_market_binding_panel_is_the_flow_log(payload_name) -> None:
    """Pinned by a test, not by a sentence, and under every payload.

    The sweep can only see the resulting number, so it stays green if a
    different panel became the binder -- which is the half that matters for
    the standing rule that a panel which can bind must be able to *mark*. One
    column under the pin ``SurfPool4Flow`` is the only panel with anything to
    say, and it says it.
    """
    r = await _render(
        MARKET_PAYLOADS[payload_name](),
        (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS - 1, 50),
    )
    assert r["marked"] == {"SurfPool4Flow"}, (payload_name, sorted(r["marked"]))


async def test_the_market_column_pin_is_the_need_it_claims_doubled() -> None:
    """The pin's *derivation*, not just its threshold.

    Both rows are ``1fr:1fr``, so the pin is the widest single panel need,
    doubled, plus the one column ``#surf-pool4-user-body`` reserves for its
    own ``scrollbar-gutter: stable``. Measured at the pin itself, where that
    arithmetic is visible on screen, and asserted with ``==`` so a need that
    drifted in either direction reddens.

    ``MARKET_FLOW_NEED`` is a hand-typed literal rather than an import of the
    constant it explains, for the reason in this module's docstring.
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
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}").region.width
        middle = screen.query_one(f"#{POOL4_USER_MIDDLE_ID}").region.width
        bottom = screen.query_one(f"#{POOL4_USER_BOTTOM_ID}").region.width
        rail = screen.query_one(f"#{POOL4_USER_RAIL_ID}").region.width

    assert flow == MARKET_FLOW_NEED, (
        f"FLOW gets {flow} columns at the pin, not the {MARKET_FLOW_NEED} the "
        "constant is built from -- re-sweep it"
    )
    # The body really does pay one column for its gutter, which is the whole
    # of the difference between this pin and twice the binder's need.
    assert body == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    assert bottom == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS - 1
    assert middle == bottom
    assert 1 + 2 * MARKET_FLOW_NEED == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    # ...and the seam really is even, so "doubled" is the right arithmetic
    # rather than a coincidence of one particular ratio. The right-hand half
    # of the bottom row absorbs the odd column when the row is odd-width.
    assert abs(flow - depth) <= 1
    assert abs(middle - 2 * rail) <= 1
    assert MEASURED_MARKET_COLUMNS == SURF_POOL4_USER_FULL_LAYOUT_COLUMNS


def test_the_market_body_fits_inside_the_documented_app_width() -> None:
    """The standing rule, asserted rather than assumed: a body measured wider
    than ``__main__.FULL_LAYOUT_COLUMNS`` means shortening a value, never
    raising the app's number.

    Four bodies, four independently measured pins. They are allowed to be
    equal -- but if two of them ever ARE it should be because somebody
    measured it, so the constants stay separate and this is the note that
    says so rather than a test forbidding the coincidence. This one is the
    narrowest of the four, one column under the ``p`` body's, and the same
    panel binds both: see the constant's own block for why that is a
    measurement and not a contradiction.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_POOL4_USER_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_POOL4_USER_FULL_LAYOUT_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS
    assert SURF_POOL4_USER_FULL_LAYOUT_COLUMNS < SURF_POOL4_FULL_LAYOUT_COLUMNS
    assert (
        SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
        < SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
    )


# ---------------------------------------------------------------------------
# The row pin
# ---------------------------------------------------------------------------


#: The height sweep, on :data:`_WIDTH_SWEEP`'s reasoning: the committed
#: capture over the whole 24..45 range, and the two payloads that move a
#: panel's line count over the eight rows that straddle the pin.
_HEIGHT_SWEEP = [("capture", r) for r in range(24, 46)] + [
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


async def test_the_market_height_pin_is_the_ladders_ninth_line() -> None:
    """The pin's *derivation*, not just its threshold.

    ``SurfPool4UDepth`` binds, and what it binds on is one specific line: the
    ``-50%`` rung, the deepest quote the panel makes. It is on screen at the
    pin and gone one row under it, which is the measurement the constant's
    ``#:`` block records -- nine painted lines in a row whose ``min-height``
    is eight.

    Asserted on the **painted column** rather than on the panel's height,
    because a panel that were merely one row taller with a blank in it would
    satisfy a height check and still be missing the number.
    """
    at = await _render(None, (150, SURF_POOL4_USER_FULL_LAYOUT_ROWS))
    under = await _render(None, (150, SURF_POOL4_USER_FULL_LAYOUT_ROWS - 1))

    assert "-50%" in at["depth_text"], (
        "the ladder's deepest rung is not on screen at the body's own pinned "
        "height -- re-sweep it"
    )
    assert "-50%" not in under["depth_text"], (
        "the ladder still paints its deepest rung one row below the pin, so "
        "the pin is loose"
    )
    assert at["lines"]["SurfPool4UDepth"] == FIXED_PANEL_LINES[SurfPool4UDepth]
    assert MEASURED_MARKET_ROWS == SURF_POOL4_USER_FULL_LAYOUT_ROWS


@pytest.mark.parametrize("rows", list(range(24, 46)))
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

    It reddened. ``#surf-pool4-user-bottom``'s floor is now the ladder's own
    ten rows, so the panel cannot be squeezed into a height where its table
    scrolls internally while the body does not -- every height under the pin
    scrolls the body instead, which the marker *can* see.

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
    lost = short or ("the ladder's -50% rung"
                     if "-50%" not in r["depth_text"] else None)
    if lost:
        assert TALLER_HINT in r["text"], (
            f"at {rows} rows the body loses {lost} and the screen-wide "
            "taller marker is dark -- a row is being cut in silence"
        )


def test_the_market_body_is_the_shortest_surf_body_but_not_the_shortest_pin() -> None:
    """W7's answer for this body, asserted rather than left in prose.

    The PRD predicted a bakery-shaped body would land nearer the ``l`` body's
    31 rows than the ``p`` body's 44. It does -- 33 -- and the *other* half of
    that prediction, that it would be wide-and-short, is refuted: this body is
    narrower than ``p`` as well. Both halves are pinned so a future re-sweep
    that moved either one has to come back to the W7 note in the constant's
    own block.
    """
    assert SURF_POOL4_USER_FULL_LAYOUT_ROWS < SURF_POOL4_FULL_LAYOUT_ROWS
    assert SURF_POOL4_USER_FULL_LAYOUT_ROWS > SURF_LAUNCHPAD_FULL_LAYOUT_ROWS
    assert SURF_POOL4_USER_FULL_LAYOUT_COLUMNS < SURF_POOL4_FULL_LAYOUT_COLUMNS


# ---------------------------------------------------------------------------
# The status hint
# ---------------------------------------------------------------------------

#: The whole phrase, as one contiguous string. ``l launchpad`` is the half
#: that must never shorten -- an app-level acceptance test greps for it -- so
#: if this ever stops fitting, ``4 market`` is what gives way.
KEY_HINT_PHRASE = "l launchpad · p pool4 · 4 market"


async def test_the_three_part_key_hint_fits_the_status_bar_at_the_full_layout() -> None:
    """Measured against the bar's own budget, never counted.

    ``4 market`` took this label from 21 columns to 32, and ``StatusBar``'s
    left label is the segment the bar cuts first, so the question is settled
    by reading the phrase back off **composited output** at
    :data:`SURF_FULL_LAYOUT_COLUMNS` and then one column at a time down the
    band below it -- the test says *where* it stops fitting rather than only
    that it fits somewhere.

    Two assertions, and the second is the one a row-join is blind to.
    ``_screen_text`` joins a strip's segments with ``""``, so a per-letter
    ``[dim]`` tag that split the hint into ``4`` / `` market`` would leave the
    row-joined text byte-identical while every app-level grep for the
    contiguous phrase failed and the bar itself looked perfectly correct.
    """
    async with _surf_app().run_test(
        size=(SURF_FULL_LAYOUT_COLUMNS, 46)
    ) as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = _screen_text(pilot.app)
        segments = [seg.text for strip in strips for seg in strip]

    assert KEY_HINT_PHRASE in text, (
        "the three-part hint did not reach a pixel at the documented layout "
        "width -- shorten '4 market', never 'l launchpad'"
    )
    assert any(KEY_HINT_PHRASE in segment for segment in segments), (
        "the hint reaches the screen but is split across Segments: KEY_HINTS "
        "must be ONE markup run, not per-letter tags"
    )
    assert SurfScreen.KEY_HINTS == f"[dim]{KEY_HINT_PHRASE}[/]"


async def test_the_three_part_key_hint_has_room_to_spare_below_the_full_layout() -> None:
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
        f"above this body's own pinned width -- shorten '4 market'"
    )
