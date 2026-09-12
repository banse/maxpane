"""WP7 -- the ``4`` POOL4 MARKET body: its key, its hero swap, its dispatch.

Five claims this file exists for, and each of them is about the *screen*
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
5. **The two per-instance opt-ins set at that one mount site stay there.**
   This body leaves ``MAINNET`` unsaid and prints no per-panel ``as of``; the
   ``p`` body does neither. Both claims are swept per panel *and* from the
   other side, because a "fix" applied to the shared helper or to the class
   would satisfy every ``4``-body case and strip the auditor body in silence.

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
    SurfPool4Hatches,
    SurfPool4Ratchet,
    SurfPool4Split,
    SurfPool4UBurn,
    SurfPool4UDepth,
    SurfPool4USignals,
    SurfPool4UStakers,
    SurfPool4UserHero,
    SurfPool4Vault,
)

# The screen-test module owns the payload fixture and the harness. Imported
# rather than restated: a second copy of `_sample_data` would drift, and the
# dispatch sweep below is only meaningful against the *same* payload the
# contract tests measure.
from tests.screens.test_surf_screen import (
    SURF_WIDGET_SIGNATURES,
    _frozen_payload,
    _mainnet_pool4_payload,
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
#: `SurfPool4Flow` JOINED this tuple on 2026-09-12 -- it was deliberately
#: absent while it was the one panel still printing `· MAINNET` here. It is
#: the `p` body's own panel mounted a second time, and it is quiet in this
#: body *only* because the screen passes `quiet_mainnet=True` at this mount
#: site. `test_the_p_body_still_names_mainnet_on_the_same_class` is the other
#: half of that claim and has to be read beside this one: a fix that quieted
#: the shared helper or the class would satisfy every sweep below and strip
#: five `p`-body titles in silence.
_MARKET_PANELS = (
    SurfPool4UStakers,
    SurfPool4UBurn,
    SurfPool4USignals,
    SurfPool4UDepth,
    SurfPool4Flow,
)

#: The `p` AUDITOR body's five panels, in compose order -- the complement of
#: the tuple above and the other half of every claim made about it. Two of the
#: three per-instance decisions this screen makes (`quiet_mainnet`,
#: `quiet_as_of`) are set at ONE mount site on a class that is mounted twice,
#: and the failure mode both times is a "fix" applied to the shared helper or
#: to the class instead -- which satisfies every `4`-body sweep and strips the
#: `p` body in silence. A sweep with no complement cannot see that.
_AUDITOR_PANELS = (
    SurfPool4Split,
    SurfPool4Ratchet,
    SurfPool4Flow,
    SurfPool4Hatches,
    SurfPool4Vault,
)

#: The exact rendered prefix of a per-panel clock, as `_pool4` spells it. A
#: bare `"as"` would match `ASSETS`; the space matters and so does the case.
_AS_OF = "as of"


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
    screen and would leave this green.

    **The two left-hand panels traded rows on 2026-09-12** and PRD §4 was
    amended with them. It is the activity log beside the chart-over-signals
    column now, then the leaderboard beside the EV table -- the owner read the
    live screen and asked for STAKERS under RECENT FLOW. The rail did not
    move, which is the half that keeps ``_SCROLL_COLUMNS`` correct.

    Asserted against the real screen rather than against ``compose``'s source,
    and in both directions: each row's children **and** the geometry that says
    they are where the ids claim.
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
        assert [type(w) for w in middle.children] == [SurfPool4Flow, type(rail)]
        assert [type(w) for w in rail.children] == [
            SurfPool4UBurn, SurfPool4USignals,
        ]
        assert [type(w) for w in bottom.children] == [
            SurfPool4UStakers, SurfPool4UDepth,
        ]

        # ...and the rows really are stacked and the columns really are side
        # by side, which the child lists above are identical either way.
        flow = [w for w in middle.children if isinstance(w, SurfPool4Flow)][0]
        stakers = [
            w for w in bottom.children if isinstance(w, SurfPool4UStakers)
        ][0]
        depth = [w for w in bottom.children if isinstance(w, SurfPool4UDepth)][0]
        assert flow.region.right <= rail.region.x
        assert flow.region.y == rail.region.y
        assert stakers.region.right <= depth.region.x
        assert stakers.region.y == depth.region.y
        assert middle.region.y + middle.region.height <= bottom.region.y

        # ...and the leaderboard really is BELOW the log, which is the ask.
        assert flow.region.y < stakers.region.y


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
            POOL4_LEFT_ID, POOL4_USER_MIDDLE_ID,
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


#: Keys the default probe cannot see, and the payload pair that can.
#:
#: The probe below renders twice and diffs: the frozen payload, then the same
#: payload with one key set to ``None``. That works for a key whose value is
#: unconditional. It cannot work for a key that is only *meaningful* under
#: conditions the frozen payload does not meet, and asserting it anyway
#: demands that a widget render something it is correct to ignore.
#:
#: ``pool4_stakers_state`` is the first such key and both halves bite:
#:
#: 1. **It is silent while there are rows.** With staker rows on hand the rows
#:    ARE the answer, so the manager publishes ``None`` for the state (see
#:    ``POOL4_STAKERS_STATES``). The frozen payload has rows.
#: 2. **Its ``None`` aliases to ``pending`` on purpose.** An absent or
#:    unrecognised state must fall to the quiet line, never the warning
#:    triangle -- that is the whole point of the key. So even without rows,
#:    flipping the value to ``None`` changes no pixel.
#:
#: The pair therefore drops the rows (so the state speaks) and flips ``failed``
#: to ``None`` (so the two states it distinguishes actually differ on screen).
#: An override is a claim that the default probe is wrong for this key, not a
#: way to quiet it -- ``test_every_conditional_probe_really_needs_one`` proves
#: each one is necessary by running the default probe and requiring it to fail.
_CONDITIONAL_PROBES: dict[str, tuple[dict, dict]] = {
    "pool4_stakers_state": (
        {"pool4_stakers": None, "pool4_stakers_state": "failed"},
        {"pool4_stakers": None, "pool4_stakers_state": None},
    ),
}


@pytest.mark.parametrize("key", sorted(_CONDITIONAL_PROBES), ids=sorted(_CONDITIONAL_PROBES))
def test_every_conditional_probe_really_needs_one(key) -> None:
    """An override must be a necessity, never a convenience.

    **This test was written once as "run the default probe and require it to
    fail", and that version could not fail.** The default probe renders the
    frozen payload, then the same payload with one key set to ``None``. For a
    key the fixture never sets, *both* renders already carry ``None`` -- so the
    two are identical no matter what the widget does, and the assertion held
    for a reason that had nothing to do with the claim. Two separate mutations
    to the widget left it green before that was noticed.

    The falsifiable claim underneath is about the **fixture**, not the render:
    the default probe is vacuous for this key precisely because the frozen
    payload carries no distinguishable value to flip. Assert that directly.
    Give the fixture a real value and this reddens, which is the moment to ask
    whether the override is still earning its place.
    """
    payload = _frozen_payload()
    assert payload.get(key) is None, (
        f"{key} now has a real value in the frozen payload, so the default "
        "flip-to-None probe is no longer vacuous for it. Re-check whether its "
        "_CONDITIONAL_PROBES entry is still needed, and delete it if not."
    )
    present, absent = _CONDITIONAL_PROBES[key]
    assert present.get(key) != absent.get(key), (
        f"{key}'s override renders the same value twice -- it cannot see the "
        "key any better than the default probe it replaced"
    )


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
    present, absent = _CONDITIONAL_PROBES.get(key, ({key: ...}, {key: None}))
    if present.get(key) is ...:
        present = {}

    async with _surf_app(_frozen_payload(**present)).run_test(size=_SIZE) as pilot:
        await _open_market(pilot)
        full = _market_text(pilot.app)

    async with _surf_app(_frozen_payload(**absent)).run_test(
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


# ---------------------------------------------------------------------------
# the blank row under every panel title (2026-09-12 screenshot review)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls", _MARKET_PANELS, ids=[c.__name__ for c in _MARKET_PANELS]
)
async def test_every_market_panel_paints_a_blank_row_under_its_title(cls) -> None:
    """The repo-wide convention this body shipped without.

    ``ActivityFeed > .feed-title``, ``VolumeSparklines > .volspark-title``,
    ``PriceSparklines > .spark-title``, ``TopMovers > .movers-title``,
    ``GeckoPools > .gecko-title`` and ``LaunchFeed > .launch-feed-title`` all
    carry ``margin: 0 0 1 0`` in ``minimal.tcss``; the `4` body's four panels
    carried none, which is what the 2026-09-12 screenshot review reported
    first.

    Asserted against **composited output on the real screen**, not against the
    CSS string and not against a panel mounted alone in a bare ``App``. The
    app stylesheet outranks a widget's ``DEFAULT_CSS``, so the only honest
    question is whether the row reaches a pixel *here*, with every rule in
    play -- and two of these four paint their title into a ``Static`` they
    share with nothing while the other two have a ``DataTable`` under it, so
    a source-level check would have to know which shape it was looking at.

    Row 0 carries the title, row 1 is blank, row 2 carries content. The third
    assertion is the one that stops this passing on a panel that has simply
    gone dark.
    """
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}")
        found = list(body.query(cls))
        assert len(found) == 1, f"{cls.__name__}: {len(found)} instances"
        rows = _region_text(pilot.app, found[0]).split("\n")

    assert rows[0].strip(), f"{cls.__name__} has no title row"
    assert not rows[1].strip(), (
        f"{cls.__name__} paints content directly under its title -- the "
        "`margin: 0 0 1 0` blank row every other dashboard's title class "
        f"carries is missing. Composited rows: {rows[:4]}"
    )
    assert rows[2].strip(), (
        f"{cls.__name__} paints nothing under the blank, so the blank above "
        "is the panel being empty rather than the title's margin"
    )


# ---------------------------------------------------------------------------
# one clock on the body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _MARKET_PANELS, ids=[c.__name__ for c in _MARKET_PANELS])
async def test_no_market_panel_renders_an_as_of_marker(cls) -> None:
    """The `4` body prints ONE ``as of``, and it is the screen's title row.

    All five panels carried their own until 2026-09-12 (`_pool4`'s *One clock
    on the `4` body*). Parametrised per panel rather than joined into one
    assertion so a panel that grows the line back reddens **its own** case and
    names itself in the failure, instead of one opaque red for "somewhere on
    this body".

    Composited output, over the panel's own rectangle: a marker that is built
    and never painted is not the thing the owner asked to have removed, and a
    whole-screen grep would match the title row's own legitimate marker and
    pass for a reason that is not the claim.
    """
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}")
        panel = list(body.query(cls))[0]
        text = _region_text(pilot.app, panel)

    assert _AS_OF not in text, (
        f"{cls.__name__} is painting a per-panel clock again:\n{text}"
    )


async def test_the_market_title_row_still_carries_the_bodys_one_clock() -> None:
    """The complement inside this body: removing five markers left one.

    Without this, every assertion above is satisfied by a payload that simply
    has no marker to print, and the sweep would be green on a body whose
    freshness a reader cannot see at all -- which is the opposite of what was
    asked for.
    """
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        await _open_market(pilot)
        whole = _screen_text(pilot.app)
        body_only = _market_text(pilot.app)

    assert _AS_OF in whole, whole.split("\n")[0]
    assert _AS_OF not in body_only


@pytest.mark.parametrize("cls", _AUDITOR_PANELS, ids=[c.__name__ for c in _AUDITOR_PANELS])
async def test_every_auditor_panel_still_renders_its_own_as_of_marker(cls) -> None:
    """The `p` body is untouched, and this is the only test that can say so.

    ``SurfPool4Flow`` is mounted in both bodies and the ``4`` instance is quiet
    because **the screen passes ``quiet_as_of=True`` at that one mount site**.
    Quieting the class, its default, or the note helper instead would satisfy
    every case in the sweep above and strip the auditor body's markers in
    silence -- exactly the failure ``test_the_p_body_still_names_mainnet_on_
    the_same_class`` exists for one field over.

    Proven by mutation: flipping ``SurfPool4Flow.__init__``'s ``quiet_as_of``
    default to ``True`` leaves every ``4``-body case green and reddens this
    one, on ``SurfPool4Flow``.
    """
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        await pilot.press("escape")
        await pilot.press("p")
        await pilot.pause()
        await pilot.pause()
        body = screen.query_one(f"#{POOL4_BODY_ID}")
        panel = list(body.query(cls))[0]
        text = _region_text(pilot.app, panel)

    assert _AS_OF in text, (
        f"the `p` body's {cls.__name__} lost its clock -- the `4` body's "
        f"quiet-marker opt-in leaked out of its mount site:\n{text}"
    )


# ---------------------------------------------------------------------------
# the network word, and the one network this body leaves unsaid
# ---------------------------------------------------------------------------


async def test_the_market_panels_leave_mainnet_unsaid_and_say_everything_else()\
        -> None:
    """"mainnet shouldn't be mentioned" -- and the word still has a job.

    The `4` body's four panels call ``_pool4.market_title_text``, which is
    ``panel_title`` with :data:`~maxpane_dashboard.widgets.surf._pool4.
    QUIET_NETWORK` left unsaid. The temptation was to delete the network word
    from these titles altogether; that would have thrown away the property it
    exists for, because this view renders a live **Sepolia** deployment
    whenever no mainnet hook has been adopted and a reader must never take
    those numbers for real ones.

    So both halves are asserted against composited output on the real screen,
    over the two committed captures: the mainnet one paints bare titles, and
    the Sepolia one still paints ``· SEPOLIA`` on every panel that has a
    network word.
    """
    async with _surf_app(_mainnet_pool4_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}")
        for cls in _MARKET_PANELS:
            panel = list(body.query(cls))[0]
            rows = _region_text(pilot.app, panel).split("\n")
            assert "MAINNET" not in rows[0], (cls.__name__, rows[0])
            assert "·" not in rows[0], (cls.__name__, rows[0])

    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        body = screen.query_one(f"#{POOL4_USER_BODY_ID}")
        for cls in _MARKET_PANELS:
            panel = list(body.query(cls))[0]
            rows = _region_text(pilot.app, panel).split("\n")
            assert "SEPOLIA" in rows[0], (cls.__name__, rows[0])


async def test_the_p_body_still_names_mainnet_on_the_same_class() -> None:
    """The other half of the quiet-title claim, and why the opt-in is per instance.

    ``SurfPool4Flow`` is mounted twice. The ``4`` body's instance leaves
    ``MAINNET`` unsaid; the ``p`` body's must go on printing it, because that
    body is an auditor's view where the network word is load-bearing. A fix
    that quieted the shared helper, or the class itself, would pass the sweep
    above and silently strip five ``p``-body titles -- so this test exists to
    fail in that case, and it is the only test that can.

    It replaces ``test_recent_flow_still_names_mainnet_in_this_body``, which
    pinned the finding open and instructed its own deletion on the day the
    finding was fixed.
    """
    async with _surf_app(_mainnet_pool4_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open_market(pilot)
        await pilot.press("escape")
        await pilot.press("p")
        await pilot.pause()
        body = screen.query_one(f"#{POOL4_BODY_ID}")
        flow = list(body.query(SurfPool4Flow))[0]
        rows = _region_text(pilot.app, flow).split("\n")

    assert "MAINNET" in rows[0], (
        "the `p` body's RECENT FLOW stopped naming MAINNET -- the quiet-title "
        "opt-in leaked out of the `4` body's mount site: " + rows[0]
    )
