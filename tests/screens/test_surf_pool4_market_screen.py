"""WP7 -- the ``4`` POOL4 MARKET body: its key, its hero swap, its dispatch.

Four claims this file exists for, and each of them is about the *screen*
rather than about a panel (the five panels have their own widget tests):

1. ``4`` opens the body and ``escape`` backs out, one-way, exactly as ``l``
   and ``p`` do -- and ``4`` is also its own way back.
2. **Exactly one hero shows in every mode.** This body is the first on this
   screen to swap the hero with the body (PRD §3 argues the break), so the
   invariant "a hero is on screen, and only one" is new here and is the one
   an ordinary edit breaks.
3. Every key the body declares reaches a **pixel**, not merely a widget.
4. RECENT FLOW is the ``p`` body's own ``SurfPool4Flow`` mounted twice, never
   a second module -- and both instances are handed the same rows.

Everything is asserted against **composited output** (``render_strips()``),
joined per row and then by newline: a string that never reaches a pixel
passes a naive test while being invisible to the user.

No network: the harness is the screen-test module's ``_FakeManager`` over a
committed fixture, and nothing here constructs a client.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.screens.surf import (
    MODE_DASHBOARD,
    MODE_LAUNCHPAD,
    MODE_POOL4,
    MODE_POOL4_USER,
    LAUNCHPAD_BODY_ID,
    POOL4_BODY_ID,
    POOL4_LEFT_ID,
    POOL4_USER_BODY_ID,
    POOL4_USER_BOTTOM_ID,
    POOL4_USER_MIDDLE_ID,
    POOL4_USER_RAIL_ID,
    SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfHero,
    SurfPool4Flow,
    SurfPool4UBurn,
    SurfPool4UDepth,
    SurfPool4USignals,
    SurfPool4UStakers,
    SurfPool4UserHero,
)

# The screen-test module owns the payload fixture and the harness. Imported
# rather than restated: a second copy of `_sample_data` would drift, and the
# dispatch sweep below is only meaningful against the *same* payload the
# contract tests measure.
from tests.screens.test_surf_screen import (
    SURF_WIDGET_SIGNATURES,
    _frozen_payload,
    _region_text,
    _screen_text,
    _surf_app,
)

#: (150, 50) rather than the pinned width: this file is about wiring, not
#: about the layout pin, and a size that is comfortably larger than anything
#: measured keeps a panel's `‹ widen` elision out of the string assertions.
#: WP10 owns the measured pins and their own sweep.
_SIZE = (150, 50)

#: The five panel classes that live in the `4` body, in compose order.
#: `SurfPool4Flow` is deliberately absent -- see
#: `test_recent_flow_is_the_same_class_mounted_twice`, which is where the
#: reused instance is asserted instead.
_MARKET_PANELS = (
    SurfPool4UStakers,
    SurfPool4UBurn,
    SurfPool4USignals,
    SurfPool4UDepth,
)


async def _open_market(pilot):
    """Refresh, press ``4``, and settle the layout."""
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press("4")
    await pilot.pause()
    await pilot.pause()
    return pilot.app.screen


def _market_text(app) -> str:
    """Composited text of the market body AND its hero, and nothing else.

    Scoped rather than whole-screen because three of this body's keys are
    dispatched to the ``p`` body as well (``pool4_flow``,
    ``pool4_current_tick``, ``pool4_as_of_hhmm``): a whole-screen diff would
    show a change made in a body that is not on screen and report a key as
    "reaching a pixel" when the pixel it reached belongs to another view.
    """
    screen = app.screen
    return "\n".join((
        _region_text(app, screen.query_one(SurfPool4UserHero)),
        _region_text(app, screen.query_one(f"#{POOL4_USER_BODY_ID}")),
    ))


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------


async def test_four_opens_the_market_body_and_escape_backs_out() -> None:
    """``4`` in, ``escape`` out -- one-way, exactly like ``l`` and ``p``."""
    async with _surf_app().run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        assert screen._mode == MODE_POOL4_USER
        assert screen.query_one(f"#{POOL4_USER_BODY_ID}").display is True
        assert screen.query_one("#middle-row").display is False
        assert screen.query_one("#separator").display is False
        assert screen.query_one("#bottom-row").display is False

        await pilot.press("escape")
        await pilot.pause()
        assert screen._mode == MODE_DASHBOARD
        assert screen.query_one(f"#{POOL4_USER_BODY_ID}").display is False
        assert screen.query_one("#middle-row").display is True


async def test_pressing_four_twice_returns_to_the_dashboard() -> None:
    """``action_toggle_launchpad``'s contract: the key is also its own way back.

    Idempotence here is not a nicety. A second ``4`` that did nothing would
    be the only place on this screen where a view key was inert, and the
    reader who pressed it once to look and once to leave would be stuck in a
    body with no visible way out (``escape`` is not on the status bar).
    """
    async with _surf_app().run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        assert screen._mode == MODE_POOL4_USER
        await pilot.press("4")
        await pilot.pause()
        assert screen._mode == MODE_DASHBOARD
        assert screen.query_one("#middle-row").display is True
        assert screen.query_one(f"#{POOL4_USER_BODY_ID}").display is False


async def test_four_switches_directly_from_either_other_body() -> None:
    """No ``escape`` first, for ``action_toggle_pool4``'s reason.

    And the half that actually bites: the body being *left* must go dark. A
    ``_show_mode`` written as booleans rather than as one comparison against
    ``self._mode`` paints the new body on top of an old one that never went
    away, which is the defect that method's own docstring records.
    """
    bodies = (
        "#middle-row",
        f"#{LAUNCHPAD_BODY_ID}",
        f"#{POOL4_BODY_ID}",
        f"#{POOL4_USER_BODY_ID}",
    )
    async with _surf_app().run_test(size=_SIZE) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        for keys, expected in (
            ((), "#middle-row"),
            (("l",), f"#{LAUNCHPAD_BODY_ID}"),
            (("4",), f"#{POOL4_USER_BODY_ID}"),
            (("p",), f"#{POOL4_BODY_ID}"),
            (("4",), f"#{POOL4_USER_BODY_ID}"),
            (("l",), f"#{LAUNCHPAD_BODY_ID}"),
            (("escape",), "#middle-row"),
            (("4",), f"#{POOL4_USER_BODY_ID}"),
            (("escape",), "#middle-row"),
        ):
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            showing = [b for b in bodies if screen.query_one(b).display]
            assert showing == [expected], (keys, showing)


# ---------------------------------------------------------------------------
# the hero swap -- this body's one break of surf precedent
# ---------------------------------------------------------------------------


#: ``(mode, keys to reach it from a fresh screen, the hero that must show)``.
#:
#: Hand-typed, and the hero column especially: deriving it from
#: ``_SURF_HERO_MODES`` would make the test reconstruct the very mapping it
#: is checking and it could never fail.
_HERO_PER_MODE = (
    (MODE_DASHBOARD, (), SurfHero),
    (MODE_LAUNCHPAD, ("l",), SurfHero),
    (MODE_POOL4, ("p",), SurfHero),
    (MODE_POOL4_USER, ("4",), SurfPool4UserHero),
)


@pytest.mark.parametrize(
    "mode,keys,hero_cls", _HERO_PER_MODE, ids=[m for m, _k, _h in _HERO_PER_MODE],
)
async def test_exactly_one_hero_shows_in_every_mode(mode, keys, hero_cls) -> None:
    """The repurposed hero is a SECOND widget toggled with the body.

    Curator's per-mode hero pattern, not one widget with a mode branch inside
    it -- which would couple two subjects into one class and make their tests
    share a fixture (PRD §3).

    **Two heroes showing at once, and none showing at all, are both reachable
    if the visibilities are derived separately rather than from one
    comparison against ``self._mode``.** That is why all four modes are swept
    rather than the two the swap is between: the failure this exists to catch
    is a *third* mode inheriting the wrong answer, which is exactly the ``not
    launchpad`` shape ``_show_mode``'s own docstring records from the ``p``
    body's arrival.

    **PARAMETRISED PER MODE, AND THAT IS THE POINT (A38's shape).** This was
    one test with the assertion inside a loop, and the mutation proof is what
    said otherwise: giving both heroes ``display = True`` unconditionally
    reddened it on the FIRST mode and stopped, so one failure was all the
    suite reported and there was no way to tell a check that covers four
    branches from one that covers one and passes the rest by luck. Four
    independent claims have to fail like four. Under that same mutation this
    now reports **four** failures, one per mode.

    Asserted on the class too, not only the count: a version checking
    ``len(shown) == 1`` alone passes with the WRONG hero showing in every
    mode, and the wrong hero is the one of those two failures a reader cannot
    see is wrong.
    """
    async with _surf_app().run_test(size=_SIZE) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
        assert screen._mode == mode

        shown = [h for h in screen.query(".surf-hero") if h.display]
        assert len(shown) == 1, (
            f"{mode}: {[type(h).__name__ for h in shown]} heroes are "
            "showing -- exactly one must"
        )
        assert isinstance(shown[0], hero_cls), (
            f"{mode} shows {type(shown[0]).__name__}, not {hero_cls.__name__}"
        )
        # ...and the row itself never hides, which is the half of the old
        # "the hero is never touched by either swap" promise that DID
        # survive: a hero is on screen in every mode, only *which* moved.
        assert screen.query_one("#hero-row").display is True


async def test_exactly_one_hero_survives_every_transition_between_bodies() -> None:
    """The per-mode sweep's other half: the walk, not the destinations.

    Each case above starts from a fresh screen, so between them they prove
    every mode is *reachable* with one hero showing. They cannot prove the
    invariant holds through a swap -- a ``_show_mode`` that set the new
    hero before clearing the old one, or one whose ``escape`` path differed
    from its key path, would satisfy all four and still flash two heroes on
    every transition. This walks the transitions instead, including the two
    ways out of the market body (``4`` again, and ``escape``).
    """
    expected = {
        MODE_DASHBOARD: SurfHero,
        MODE_LAUNCHPAD: SurfHero,
        MODE_POOL4: SurfHero,
        MODE_POOL4_USER: SurfPool4UserHero,
    }
    async with _surf_app().run_test(size=_SIZE) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        screen = pilot.app.screen
        for key, mode in (
            ("4", MODE_POOL4_USER),
            ("p", MODE_POOL4),
            ("4", MODE_POOL4_USER),
            ("l", MODE_LAUNCHPAD),
            ("4", MODE_POOL4_USER),
            ("4", MODE_DASHBOARD),
            ("4", MODE_POOL4_USER),
            ("escape", MODE_DASHBOARD),
        ):
            await pilot.press(key)
            await pilot.pause()
            assert screen._mode == mode, key
            shown = [h for h in screen.query(".surf-hero") if h.display]
            assert [type(h) for h in shown] == [expected[mode]], (
                f"after {key!r} ({mode}): "
                f"{[type(h).__name__ for h in shown]}"
            )


async def test_the_market_hero_really_reaches_the_compositor() -> None:
    """The swap is not just a ``display`` flag: the cards composite.

    A hero whose ``display`` is ``True`` inside a row the layout gave no
    height would satisfy every assertion in the test above and paint nothing.
    Asserted against the hero's OWN region, because the panels below it
    composite the words ``STAKERS`` and ``SIGNALS`` themselves and a
    whole-screen substring check would pass with the hero unmounted entirely.
    """
    async with _surf_app().run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        hero = _region_text(pilot.app, screen.query_one(SurfPool4UserHero))
        for title in ("IMD PRICE", "DOWNSIDE BID", "STAKING"):
            assert title in hero, f"the market hero lost its {title} card"
        # The fixture's own numbers, so this cannot pass on a placeholder.
        assert "$2.845" in hero
        assert "24.40 ETH" in hero
        assert "3.4% trailing 7d" in hero
        # ...and surf's own hero is NOT on screen, which is the break itself.
        whole = _screen_text(pilot.app)
        assert "LAUNCHPAD" not in whole, (
            "both heroes composited at once -- the market body's swap did "
            "not hide SurfHero"
        )


# ---------------------------------------------------------------------------
# the body's shape
# ---------------------------------------------------------------------------


async def test_the_market_body_is_bakerys_two_rows() -> None:
    """Asserted on each container's own children, never on a screen-wide query.

    A panel mounted into the wrong row still answers ``query_one`` from the
    screen and would leave this green. The arrangement is PRD §4's: a
    leaderboard beside a chart-over-signals column, then an activity log
    beside the EV table.
    """
    async with _surf_app().run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}")
        middle = screen.query_one(f"#{POOL4_USER_MIDDLE_ID}")
        rail = screen.query_one(f"#{POOL4_USER_RAIL_ID}")
        bottom = screen.query_one(f"#{POOL4_USER_BOTTOM_ID}")

        assert [c.id for c in body.children] == [
            POOL4_USER_MIDDLE_ID, POOL4_USER_BOTTOM_ID,
        ]
        assert [type(w) for w in middle.children] == [SurfPool4UStakers, type(rail)]
        assert [type(w) for w in rail.children] == [
            SurfPool4UBurn, SurfPool4USignals,
        ]
        assert [type(w) for w in bottom.children] == [
            SurfPool4Flow, SurfPool4UDepth,
        ]

        # ...and the rows really are stacked and the columns really are side
        # by side, which the child lists above are identical either way.
        stakers = screen.query_one(SurfPool4UStakers)
        assert stakers.region.right <= rail.region.x
        assert stakers.region.y == rail.region.y
        assert middle.region.y + middle.region.height <= bottom.region.y


async def test_every_market_panel_reaches_the_compositor() -> None:
    """Five titles on screen, read off the body's own region.

    The cheapest way for this body to be broken is for one panel to be given
    no height -- the ``1fr``-without-a-floor defect -- which leaves it
    mounted, displayed and invisible.
    """
    async with _surf_app().run_test(size=_SIZE) as pilot:
        await _open_market(pilot)
        text = _market_text(pilot.app)
        for title in ("STAKERS", "BURN & SUPPLY", "SIGNALS", "POOL4 FLOW",
                      "IF IMD FALLS"):
            assert title in text, f"{title} did not reach a pixel"


async def test_recent_flow_is_the_same_class_mounted_twice() -> None:
    """PRD §6.4's reuse, asserted as the two-instance fact it actually is.

    RECENT FLOW is ``widgets/surf/pool4_flow.py`` unchanged -- the module the
    ``p`` body already uses -- mounted a second time. Two things follow and
    both are pinned here:

    * There are exactly **two** instances, one per body. Textual's
      ``query_one`` returns the FIRST match rather than raising on several,
      so nothing anywhere else would notice a third appearing, or a second
      module being written instead.
    * Both are handed the **same rows**, because the screen dispatches with
      ``self.query(SurfPool4Flow)`` in one statement. Two panels showing the
      same key with different contents is the divergence that copying the
      module would have made possible, and it is what this reuse buys.
    """
    async with _surf_app().run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        flows = list(screen.query(SurfPool4Flow))
        assert len(flows) == 2, [f.parent.id for f in flows]
        assert {f.parent.id for f in flows} == {
            POOL4_LEFT_ID, POOL4_USER_BOTTOM_ID,
        }
        # One payload, both panels: compare what each actually holds rather
        # than trusting that one statement fed both.
        assert flows[0]._payload == flows[1]._payload
        assert flows[0]._payload.get("rows"), (
            "neither instance was dispatched anything -- the comparison "
            "above would hold vacuously"
        )


# ---------------------------------------------------------------------------
# dispatch -- every declared key reaches a pixel
# ---------------------------------------------------------------------------

#: Every contract key the market body's five panels declare, deduplicated.
#: Derived from the screen-test module's signature map rather than retyped,
#: so a key added to a panel is swept here the day it is added.
_MARKET_KEYS = sorted({
    key
    for name in (
        "SurfPool4UserHero", "SurfPool4UStakers", "SurfPool4UBurn",
        "SurfPool4USignals", "SurfPool4UDepth",
    )
    for key in SURF_WIDGET_SIGNATURES[name]
})


def test_the_market_key_sweep_is_not_empty() -> None:
    """The derivation has to be able to fail.

    A signature map that stopped naming these five panels would make the
    parametrised sweep below run over nothing and pass, which is the shape
    this repo keeps finding rather than the shape it keeps fixing.
    """
    assert len(_MARKET_KEYS) >= 20, _MARKET_KEYS
    assert all(k.startswith("pool4_") for k in _MARKET_KEYS), _MARKET_KEYS


@pytest.mark.parametrize("key", _MARKET_KEYS, ids=_MARKET_KEYS)
async def test_the_market_body_dispatches_every_key_it_declares(key) -> None:
    """A ``**_kwargs`` widget can absorb a dispatched key with every signature
    guard green (open finding S23).

    Every ``update_data`` on this screen ends in ``**_kwargs`` so the screen
    can splat the whole payload and a future key cannot raise. The cost is
    that a key the widget accepts and never renders is invisible: the
    dispatch is correct, the kwarg-name check passes, the value reaches
    nothing, and no name-based test anywhere disagrees.

    So this renders twice and **diffs**: once with the fixture's value and
    once with that one key set to ``None``. If the composited body is
    byte-identical, the key reached no pixel.

    Scoped to the market body and its hero (see ``_market_text``): three of
    these keys are dispatched to the ``p`` body as well, and a whole-screen
    diff would report a change made in a view that is not on screen.
    """
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        await _open_market(pilot)
        full = _market_text(pilot.app)

    async with _surf_app(_frozen_payload(**{key: None})).run_test(
        size=_SIZE
    ) as pilot:
        await _open_market(pilot)
        without = _market_text(pilot.app)

    assert full != without, (
        f"{key} is dispatched to a market panel that renders nothing from "
        "it: the body composites identically with the key set to None. "
        "Either render it or stop dispatching it -- an accepted-and-dropped "
        "kwarg is the S23 shape every name-based guard is blind to."
    )
